import json
import base64
import mimetypes
import re
import socketserver
import sqlite3
import subprocess  # nosec B404 (usado só para abrir o navegador escolhido pelo usuário)
import threading
import time
import uuid
import webbrowser
from http import HTTPStatus
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlparse

try:
    import webview  # type: ignore
    WEBVIEW_AVAILABLE = True
except Exception:
    webview = None
    WEBVIEW_AVAILABLE = False


APP_ROOT = Path(__file__).resolve().parent
MIN_PASSWORD_LENGTH = 8


class LoginRateLimiter:
    """Freia tentativas de login por força bruta (thread-safe, só em memória).

    Bloqueia um login depois de MAX_FAILURES erros dentro de WINDOW segundos e
    também aplica um teto global, para que variar o nome de usuário a cada
    tentativa não contorne o limite.
    """

    MAX_FAILURES = 5
    WINDOW = 300
    LOCKOUT = 60
    GLOBAL_MAX_FAILURES = 30

    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._failures = {}
        self._locked_until = {}

    GLOBAL_KEY = "\0global"

    def _prune(self, key, now):
        recent = [t for t in self._failures.get(key, []) if now - t < self.WINDOW]
        if recent:
            self._failures[key] = recent
        else:
            self._failures.pop(key, None)
        return recent

    def blocked_for(self, key):
        """Segundos restantes de bloqueio (0 se liberado)."""
        now = self._clock()
        with self._lock:
            remaining = 0
            for k in (key, self.GLOBAL_KEY):
                until = self._locked_until.get(k, 0)
                if until > now:
                    remaining = max(remaining, int(until - now) + 1)
                elif k in self._locked_until:
                    del self._locked_until[k]
            return remaining

    def register_failure(self, key):
        now = self._clock()
        with self._lock:
            for k, limit in ((key, self.MAX_FAILURES), (self.GLOBAL_KEY, self.GLOBAL_MAX_FAILURES)):
                recent = self._prune(k, now)
                recent.append(now)
                self._failures[k] = recent
                if len(recent) >= limit:
                    self._locked_until[k] = now + self.LOCKOUT
                    self._failures.pop(k, None)
            # evita crescimento ilimitado do dicionário
            if len(self._failures) > 1000:
                for k in list(self._failures):
                    self._prune(k, now)

    def register_success(self, key):
        with self._lock:
            self._failures.pop(key, None)
            self._locked_until.pop(key, None)
# Raster images only: SVG can embed <script>, so it is never served as a cover.
ALLOWED_COVER_MIMES = {"image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp"}


def _is_within_app_storage(path: Path) -> bool:
    try:
        path.resolve().relative_to(APP_ROOT)
        return True
    except ValueError:
        return False


def _resolve_storage_path(source: str) -> Path:
    path = Path((source or "").strip()).expanduser()
    if not path.is_absolute():
        path = APP_ROOT / path
    return path


def _slug(text):
    return (text or "").strip().replace(" ", "-").lower()


class DuplicateBookError(ValueError):
    def __init__(self, message, existing_book=None):
        super().__init__(message)
        self.existing_book = existing_book


class LibraryRequestHandler(SimpleHTTPRequestHandler):
    server_version = "BibliotecaVirtualAbertaWeb/1.0"

    def log_message(self, format, *args):
        return

    @property
    def backend(self):
        return self.server.backend

    def _send_error(self, status, message=None):
        self.send_response(status)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        body = (message or status.phrase).encode("utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_json(self, payload, status=HTTPStatus.OK, extra_headers=None):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        for name, value in (extra_headers or {}).items():
            self.send_header(name, value)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _send_file(self, path: Path):
        if not path.exists() or not path.is_file():
            self._send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        mime, _ = mimetypes.guess_type(path.name)
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", mime or "application/octet-stream")
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("Content-Length", str(len(content)))
        self.end_headers()
        self.wfile.write(content)

    def _send_bytes(self, payload: bytes, content_type: str):
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", content_type)
        self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
        self.send_header("Pragma", "no-cache")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Security-Policy", "sandbox; default-src 'none'; img-src 'self' data:; style-src 'unsafe-inline'")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    MAX_REQUEST_BODY = 16 * 1024 * 1024  # generous headroom over the 8MB cover-upload cap

    def _body_too_large(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length > self.MAX_REQUEST_BODY:
            self._send_error(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, "Requisição excede o tamanho máximo permitido.")
            return True
        return False

    def _read_json(self):
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        raw = self.rfile.read(length)
        if not raw:
            return {}
        return json.loads(raw.decode("utf-8"))

    def _book_id_from_path(self, parsed_path):
        parts = [part for part in parsed_path.path.split("/") if part]
        if len(parts) < 3:
            return None
        try:
            return int(parts[2])
        except ValueError:
            return None

    def _serve_static(self, parsed):
        path = parsed.path
        if path in ("", "/"):
            path = "/index.html"
        static_path = (self.backend.static_dir / path.lstrip("/")).resolve()
        try:
            static_path.relative_to(self.backend.static_dir.resolve())
        except ValueError:
            self._send_error(HTTPStatus.FORBIDDEN)
            return
        self._send_file(static_path)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/session":
            self._send_json({"user": self.backend.serialize_user(self.backend.current_user)})
            return

        if parsed.path == "/api/dashboard":
            try:
                payload = self.backend.get_dashboard_payload(
                    search=parse_qs(parsed.query).get("search", [""])[0],
                    status=parse_qs(parsed.query).get("status", [""])[0],
                    sort=parse_qs(parsed.query).get("sort", ["recent"])[0],
                    collection=parse_qs(parsed.query).get("collection", [""])[0],
                    category=parse_qs(parsed.query).get("category", [""])[0],
                    book_type=parse_qs(parsed.query).get("book_type", [self.backend.type_book])[0],
                )
                self._send_json(payload)
            except PermissionError:
                self._send_json({"error": "Sessão expirada."}, status=HTTPStatus.UNAUTHORIZED)
            return

        if parsed.path.startswith("/api/book/"):
            try:
                book_id = self._book_id_from_path(parsed)
                if book_id is None:
                    self._send_json({"error": "Livro inválido."}, status=HTTPStatus.BAD_REQUEST)
                    return
                book = self.backend.get_book_payload(book_id)
                self._send_json({"book": book})
            except PermissionError:
                self._send_json({"error": "Sessão expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except LookupError:
                self._send_json({"error": "Livro não encontrado."}, status=HTTPStatus.NOT_FOUND)
            return

        if parsed.path == "/api/categories":
            try:
                self._send_json({"categories": self.backend.list_categories()})
            except PermissionError:
                self._send_json({"error": "Sessao expirada."}, status=HTTPStatus.UNAUTHORIZED)
            return

        if parsed.path == "/api/cover":
            query = parse_qs(parsed.query)
            source = unquote(query.get("path", [""])[0]).strip()
            if not source:
                self._send_error(HTTPStatus.NOT_FOUND)
                return
            try:
                payload, content_type = self.backend.read_cover_bytes(source)
                self._send_bytes(payload, content_type)
            except PermissionError:
                self._send_json({"error": "Sessão expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except FileNotFoundError:
                self._send_error(HTTPStatus.NOT_FOUND)
            return

        self._serve_static(parsed)

    def _origin_allowed(self):
        origin = self.headers.get("Origin")
        if not origin:
            return True
        return origin.rstrip("/") == self.backend.base_url.rstrip("/")

    def do_POST(self):
        if not self._origin_allowed():
            self._send_error(HTTPStatus.FORBIDDEN)
            return
        if self._body_too_large():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/api/login":
            data = self._read_json()
            wait = self.backend.login_blocked_for(data.get("email", ""))
            if wait:
                self._send_json(
                    {"error": f"Muitas tentativas. Aguarde {wait} segundos e tente de novo."},
                    status=HTTPStatus.TOO_MANY_REQUESTS,
                    extra_headers={"Retry-After": str(wait)},
                )
                return
            user = self.backend.login(data.get("email", ""), data.get("password", ""))
            if not user:
                self._send_json({"error": "Login ou senha inválidos."}, status=HTTPStatus.UNAUTHORIZED)
                return
            self._send_json({"user": self.backend.serialize_user(user)})
            return

        if parsed.path == "/api/register":
            data = self._read_json()
            try:
                user = self.backend.register(data)
                self._send_json({"user": self.backend.serialize_user(user)})
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            except sqlite3.IntegrityError:
                self._send_json({"error": "Já existe uma conta com esse email."}, status=HTTPStatus.CONFLICT)
            return

        if parsed.path == "/api/logout":
            self.backend.logout()
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/close-window":
            data = self._read_json()
            self.backend.close_child_window(data.get("token", ""))
            self._send_json({"ok": True})
            return

        if parsed.path == "/api/books":
            try:
                data = self._read_json()
                book = self.backend.create_book(data)
                self._send_json({"book": book}, status=HTTPStatus.CREATED)
            except PermissionError:
                self._send_json({"error": "Sessao expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except DuplicateBookError as exc:
                self._send_json(
                    {"error": str(exc), "duplicate": True, "existing_book": exc.existing_book},
                    status=HTTPStatus.CONFLICT,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/categories":
            try:
                data = self._read_json()
                category = self.backend.add_category(data.get("name", ""))
                self._send_json(
                    {"category": category, "categories": self.backend.list_categories()},
                    status=HTTPStatus.CREATED,
                )
            except PermissionError:
                self._send_json({"error": "Sessao expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path == "/api/cover-upload":
            try:
                data = self._read_json()
                path = self.backend.save_uploaded_cover(
                    data.get("data_url", ""),
                    data.get("filename", ""),
                )
                self._send_json({"path": path}, status=HTTPStatus.CREATED)
            except PermissionError:
                self._send_json({"error": "Sessao expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path.startswith("/api/book/") and parsed.path.endswith("/open-link"):
            try:
                book_id = self._book_id_from_path(parsed)
                self.backend.open_book_link(book_id)
                self._send_json({"ok": True})
            except PermissionError:
                self._send_json({"error": "Sessão expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except LookupError:
                self._send_json({"error": "Livro não encontrado."}, status=HTTPStatus.NOT_FOUND)
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        if parsed.path.startswith("/api/book/") and parsed.path.endswith("/favorite"):
            try:
                book_id = self._book_id_from_path(parsed)
                data = self._read_json()
                book = self.backend.set_book_favorite(book_id, bool(data.get("favorite")))
                self._send_json({"book": book})
            except PermissionError:
                self._send_json({"error": "Sessão expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except LookupError:
                self._send_json({"error": "Livro não encontrado."}, status=HTTPStatus.NOT_FOUND)
            return

        self._send_error(HTTPStatus.NOT_FOUND)

    def do_PUT(self):
        if not self._origin_allowed():
            self._send_error(HTTPStatus.FORBIDDEN)
            return
        if self._body_too_large():
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/book/"):
            try:
                book_id = self._book_id_from_path(parsed)
                data = self._read_json()
                book = self.backend.update_book(book_id, data)
                self._send_json({"book": book})
            except PermissionError:
                self._send_json({"error": "Sessao expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except LookupError:
                self._send_json({"error": "Livro nao encontrado."}, status=HTTPStatus.NOT_FOUND)
            except DuplicateBookError as exc:
                self._send_json(
                    {"error": str(exc), "duplicate": True, "existing_book": exc.existing_book},
                    status=HTTPStatus.CONFLICT,
                )
            except ValueError as exc:
                self._send_json({"error": str(exc)}, status=HTTPStatus.BAD_REQUEST)
            return

        self._send_error(HTTPStatus.NOT_FOUND)

    def do_DELETE(self):
        if not self._origin_allowed():
            self._send_error(HTTPStatus.FORBIDDEN)
            return
        parsed = urlparse(self.path)
        if parsed.path.startswith("/api/book/"):
            try:
                book_id = self._book_id_from_path(parsed)
                self.backend.delete_book(book_id)
                self._send_json({"ok": True})
            except PermissionError:
                self._send_json({"error": "Sessão expirada."}, status=HTTPStatus.UNAUTHORIZED)
            except LookupError:
                self._send_json({"error": "Livro não encontrado."}, status=HTTPStatus.NOT_FOUND)
            return

        self._send_error(HTTPStatus.NOT_FOUND)


class LibraryHttpServer(socketserver.ThreadingMixIn, HTTPServer):
    daemon_threads = True

    def __init__(self, server_address, handler_class, backend, static_dir):
        super().__init__(server_address, handler_class)
        self.backend = backend
        self.static_dir = static_dir


class DesktopBridge:
    def __init__(self, app):
        self.app = app

    def open_details(self, book_id, screen_width=None, screen_height=None):
        self.app.open_details_window(int(book_id), screen_width=screen_width, screen_height=screen_height)
        return True


def _screen_size():
    try:
        import ctypes
        user32 = ctypes.windll.user32
        width = user32.GetSystemMetrics(0)
        height = user32.GetSystemMetrics(1)
        if width and height:
            return width, height
    except Exception:
        pass
    if WEBVIEW_AVAILABLE:
        try:
            screen = webview.screens[0]
            if screen.width and screen.height:
                return screen.width, screen.height
        except Exception:
            pass
    return 1920, 1080


def _centered_position(width, height, screen_width=None, screen_height=None):
    if not screen_width or not screen_height:
        screen_width, screen_height = _screen_size()
    x = max((screen_width - width) // 2, 0)
    y = max((screen_height - height) // 2, 0)
    return x, y


class DesktopWebApp:
    def __init__(
        self,
        db_factory,
        db_path,
        row_value,
        progress_numbers,
        format_display_datetime,
        resolve_cover_source,
        type_book,
        type_light_novel,
        type_adult,
        status_want,
        status_reading,
        status_done,
    ):
        self.db = db_factory(db_path)
        self.row_value = row_value
        self.progress_numbers = progress_numbers
        self.format_display_datetime = format_display_datetime
        self.resolve_cover_source = resolve_cover_source
        self.type_book = type_book
        self.type_light_novel = type_light_novel
        self.type_adult = type_adult
        self.status_want = status_want
        self.status_reading = status_reading
        self.status_done = status_done
        self.favorite_collection = "__favorites__"
        self.static_dir = Path(__file__).with_name("webui")
        self.current_user = None
        self.login_limiter = LoginRateLimiter()
        self.server = None
        self.server_thread = None
        self.base_url = None
        self.bridge = DesktopBridge(self)
        self.windows = {}

    def run(self):
        if not WEBVIEW_AVAILABLE or not self.static_dir.exists():
            return False
        self.start_server()
        version = uuid.uuid4().hex
        self.windows["main"] = webview.create_window(
            "Biblioteca Virtual Aberta",
            f"{self.base_url}/index.html?v={version}",
            js_api=self.bridge,
            width=1440,
            height=960,
            min_size=(1180, 760),
            background_color="#050816",
        )
        try:
            webview.start(debug=False)
        finally:
            self.stop()
        return True

    def start_server(self):
        self.server = LibraryHttpServer(("127.0.0.1", 0), LibraryRequestHandler, self, self.static_dir)
        self.base_url = f"http://127.0.0.1:{self.server.server_port}"
        self.server_thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.server_thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        if hasattr(self.db, "close"):
            self.db.close()

    def serialize_user(self, user):
        if not user:
            return None
        return {"id": int(user["id"]), "name": user["name"], "email": user["email"]}

    def require_user(self):
        if not self.current_user:
            raise PermissionError("Sessão expirada.")
        return self.current_user

    def login_blocked_for(self, email):
        return self.login_limiter.blocked_for((email or "").strip().lower())

    def login(self, email, password):
        key = (email or "").strip().lower()
        user = self.db.get_user_by_credentials(email, password)
        if not user:
            # uma tentativa errada não derruba uma sessão já aberta
            self.login_limiter.register_failure(key)
            return None
        self.login_limiter.register_success(key)
        self.current_user = user
        return user

    def register(self, data):
        name = (data.get("name") or "").strip()
        email = (data.get("email") or "").strip()
        password = (data.get("password") or "").strip()
        confirm = (data.get("confirm_password") or "").strip()
        if not name or not email or not password or not confirm:
            raise ValueError("Preencha todos os campos.")
        if password != confirm:
            raise ValueError("As senhas não coincidem.")
        if len(password) < MIN_PASSWORD_LENGTH:
            raise ValueError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
        if self.db.name_exists(name):
            raise ValueError("Ja existe uma conta com esse nome de usuario. Escolha outro nome.")
        self.db.create_user(name, email, password)
        user = self.db.get_user_by_credentials(email, password)
        self.current_user = user
        return user

    def logout(self):
        self.current_user = None

    def _normalize_book_type(self, value):
        return self.type_book

    def _resolve_collection_filter(self, collection="", book_type=""):
        normalized_collection = unquote((collection or "").strip())
        if normalized_collection == self.favorite_collection:
            return "", True, self.favorite_collection
        return self.type_book, False, self.type_book

    def _sort_books(self, books, sort_mode):
        if sort_mode == "title":
            return sorted(books, key=lambda book: self.row_value(book, "title").casefold())
        if sort_mode == "progress":
            def progress_key(book):
                _current, _total, percent = self.progress_numbers(
                    self.row_value(book, "last_page", "current_chapter"),
                    self.row_value(book, "total_pages"),
                )
                return (
                    percent if percent is not None else -1,
                    self.row_value(book, "updated_at"),
                    int(book["id"]),
                )
            return sorted(books, key=progress_key, reverse=True)
        return books

    def _cover_url(self, source):
        source = (source or "").strip()
        if not source:
            return ""
        if source.startswith(("http://", "https://")):
            # Never block the dashboard response on a network fetch: let the
            # browser's own <img> tag load remote covers directly. If we've
            # already cached a local copy from a previous successful load,
            # prefer that (works offline / faster); otherwise hand back the
            # raw URL as-is.
            cached = self.resolve_cover_source(source, allow_download=False) if self.resolve_cover_source else source
            if cached and not cached.startswith(("http://", "https://")):
                return f"/api/cover?path={quote(cached)}"
            return source
        resolved = self.resolve_cover_source(source, allow_download=True) if self.resolve_cover_source else source
        if resolved.startswith(("http://", "https://")):
            return resolved
        if not _is_within_app_storage(_resolve_storage_path(resolved)):
            # Import was refused (not a raster image, too large, unreadable...):
            # report "no cover" instead of leaking an absolute path into the page.
            return ""
        return f"/api/cover?path={quote(resolved)}"

    def _status_slug(self, status):
        if status == self.status_done:
            return "done"
        if status == self.status_reading:
            return "reading"
        if status == self.status_want:
            return "want"
        return "other"

    def serialize_book(self, book):
        current_page, total_pages, percent = self.progress_numbers(
            self.row_value(book, "last_page", "current_chapter"),
            self.row_value(book, "total_pages"),
        )
        status = self.row_value(book, "status") or self.status_want
        book_type = self.row_value(book, "book_type") or self.type_book
        is_favorite = bool(book["is_favorite"]) if hasattr(book, "keys") and "is_favorite" in book.keys() else False
        if current_page != "-":
            hidden_caption = f"Último visto: página {current_page}"
        else:
            hidden_caption = "Último visto ainda não informado"
        progress_caption = f"Página atual: {current_page}"
        if total_pages:
            progress_caption += f" de {total_pages}"
        visible_line = f"{current_page or '-'} / {total_pages or '?'}"
        updated_raw = self.row_value(book, "updated_at")
        reading_link = self.row_value(book, "reading_link")
        return {
            "id": int(book["id"]),
            "title": self.row_value(book, "title"),
            "author": self.row_value(book, "author") or "Autor não informado",
            "status": status,
            "status_slug": self._status_slug(status),
            "book_type": book_type,
            "book_type_slug": (
                "light-novel"
                if book_type == self.type_light_novel
                else ("adult" if book_type == self.type_adult else "book")
            ),
            "category": self.row_value(book, "category") or "Sem categoria",
            "cover_path": self.row_value(book, "cover_path"),
            "cover_url": self._cover_url(self.row_value(book, "cover_path")),
            "reading_link": reading_link,
            "notes": self.row_value(book, "notes") or "",
            "updated_at": updated_raw or "",
            "updated_at_display": self.format_display_datetime(updated_raw),
            "last_page": self.row_value(book, "last_page", "current_chapter") or "",
            "total_pages": self.row_value(book, "total_pages") or "",
            "progress_percent": percent,
            "progress_hidden_caption": hidden_caption,
            "progress_caption": progress_caption,
            "progress_hint": "Revele o progresso quando quiser ver percentual e total.",
            "progress_visible_line": visible_line,
            "has_link": bool(reading_link),
            "has_cover": bool(self.row_value(book, "cover_path")),
            "is_favorite": is_favorite,
            "notes_short": (self.row_value(book, "notes") or "").strip()[:120],
            "link_short": (reading_link or "").strip()[:120],
        }

    def get_dashboard_payload(self, search="", status="", sort="recent", collection="", category="", book_type=""):
        user = self.require_user()
        normalized_type, favorites_only, active_collection = self._resolve_collection_filter(collection, book_type)
        books = list(
            self.db.list_books(
                user["id"],
                search=search or "",
                status=status or "",
                book_type=normalized_type,
                category=category or "",
                favorites_only=favorites_only,
            )
        )
        books = self._sort_books(books, sort or "recent")
        counts = self.db.count_by_status(
            user["id"],
            book_type=normalized_type,
            category=category or "",
            favorites_only=favorites_only,
        )
        return {
            "user": self.serialize_user(user),
            "book_type": normalized_type,
            "collection": active_collection,
            "category": (category or "").strip(),
            "categories": self.list_categories(),
            "counts": counts,
            "books": [self.serialize_book(book) for book in books],
        }

    def list_categories(self):
        user = self.require_user()
        return self.db.list_categories(user["id"])

    def add_category(self, name):
        user = self.require_user()
        return self.db.add_category(user["id"], name)

    def save_uploaded_cover(self, data_url, filename=""):
        self.require_user()
        if not isinstance(data_url, str) or not data_url.startswith("data:image/"):
            raise ValueError("Envie uma imagem valida para a capa.")
        header, _, encoded = data_url.partition(",")
        if not encoded:
            raise ValueError("Imagem sem conteudo.")
        mime = header[5:].split(";", 1)[0].strip().lower()
        extension = mimetypes.guess_extension(mime) or Path(filename or "").suffix.lower() or ".img"
        if extension == ".jpe":
            extension = ".jpg"
        if extension not in {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".img"}:
            extension = ".img"
        try:
            payload = base64.b64decode(encoded, validate=True)
        except Exception as exc:
            raise ValueError("Nao foi possivel ler a imagem enviada.") from exc
        if not payload:
            raise ValueError("Imagem sem conteudo.")
        if len(payload) > 8 * 1024 * 1024:
            raise ValueError("A imagem da capa deve ter ate 8 MB.")
        cache_dir = Path(__file__).with_name("covers_cache")
        cache_dir.mkdir(exist_ok=True)
        cache_path = cache_dir / f"uploaded_{uuid.uuid4().hex}{extension}"
        cache_path.write_bytes(payload)
        return str(cache_path.relative_to(APP_ROOT))

    def _book_data_from_payload(self, data):
        title = (data.get("title") or "").strip()
        if not title:
            raise ValueError("Informe pelo menos o título da obra.")
        return {
            "title": title,
            "book_type": self._normalize_book_type(data.get("book_type") or self.type_book),
            "author": (data.get("author") or "").strip(),
            "status": (data.get("status") or self.status_want).strip(),
            "last_page": (data.get("last_page") or "").strip(),
            "total_pages": (data.get("total_pages") or "").strip(),
            "category": (data.get("category") or "").strip(),
            "cover_path": (data.get("cover_path") or "").strip(),
            "reading_link": (data.get("reading_link") or "").strip(),
            "notes": (data.get("notes") or "").strip(),
            "is_favorite": bool(data.get("is_favorite")),
        }

    def _find_book(self, book_id):
        user = self.require_user()
        book = self.db.get_book(int(book_id), user["id"])
        if not book:
            raise LookupError("Livro não encontrado.")
        return book

    def get_book_payload(self, book_id):
        return self.serialize_book(self._find_book(book_id))

    def create_book(self, data):
        user = self.require_user()
        payload = self._book_data_from_payload(data)
        allow_duplicate = bool(data.get("allow_duplicate"))
        if not allow_duplicate:
            duplicate = self.db.find_duplicate_book(user["id"], payload["title"])
            if duplicate:
                raise DuplicateBookError(
                    "Ja existe uma obra com esse titulo na sua biblioteca.",
                    existing_book=self.serialize_book(duplicate),
                )
        book_id = self.db.add_book(user["id"], payload)
        return self.get_book_payload(book_id)

    def update_book(self, book_id, data):
        user = self.require_user()
        self._find_book(book_id)
        payload = self._book_data_from_payload(data)
        allow_duplicate = bool(data.get("allow_duplicate"))
        if not allow_duplicate:
            duplicate = self.db.find_duplicate_book(user["id"], payload["title"], exclude_book_id=book_id)
            if duplicate:
                raise DuplicateBookError(
                    "Ja existe outra obra com esse titulo na sua biblioteca.",
                    existing_book=self.serialize_book(duplicate),
                )
        self.db.update_book(int(book_id), user["id"], payload)
        return self.get_book_payload(book_id)

    def delete_book(self, book_id):
        user = self.require_user()
        self._find_book(book_id)
        self.db.delete_book(int(book_id), user["id"])

    def set_book_favorite(self, book_id, favorite):
        user = self.require_user()
        self._find_book(book_id)
        self.db.set_book_favorite(int(book_id), user["id"], bool(favorite))
        return self.get_book_payload(book_id)

    def open_book_link(self, book_id):
        book = self._find_book(book_id)
        link = (self.row_value(book, "reading_link") or "").strip()
        if not link:
            raise ValueError("Nenhum link salvo para esta obra.")
        if not link.startswith(("http://", "https://")):
            # outro esquema (javascript:, file:, data:...) é recusado; "site.com:8080" é só porta
            if re.match(r"^[a-z][a-z0-9+.\-]*:(?!\d)", link, re.IGNORECASE):
                raise ValueError("O link salvo nesta obra não é um endereço web válido.")
            link = "https://" + link
        try:
            parsed = urlparse(link)
            parsed.port  # levanta ValueError se a porta for inválida
            valid_link = bool(parsed.hostname)
        except ValueError:  # porta inválida, colchetes soltos etc.
            valid_link = False
        if not valid_link or any(ch.isspace() or ord(ch) < 32 for ch in link):
            raise ValueError("O link salvo nesta obra não é um endereço web válido.")
        self._open_in_preferred_browser(link)

    def _open_in_preferred_browser(self, link):
        """
        Abre o link no navegador configurado em browser_config.json (se existir
        e o executavel for valido). Caso contrario, usa o navegador padrao do
        Windows via webbrowser.open_new_tab.

        Para configurar: crie um arquivo "browser_config.json" na mesma pasta
        deste app.pyw com o conteudo:
        {"browser_path": "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe"}
        """
        config_path = Path(__file__).with_name("browser_config.json")
        if config_path.exists():
            try:
                config = json.loads(config_path.read_text(encoding="utf-8"))
                browser_path = (config.get("browser_path") or "").strip()
                if browser_path and Path(browser_path).exists():
                    # lista de args (sem shell); o link já foi forçado a http(s) e validado
                    subprocess.Popen([browser_path, link])  # nosec B603
                    return
            except Exception:
                pass
        webbrowser.open_new_tab(link)

    def read_cover_bytes(self, source):
        self.require_user()
        path = _resolve_storage_path(source)
        if not _is_within_app_storage(path):
            raise FileNotFoundError(source)
        if not path.exists() or not path.is_file():
            raise FileNotFoundError(source)
        mime, _ = mimetypes.guess_type(path.name)
        if mime not in ALLOWED_COVER_MIMES:
            raise FileNotFoundError(source)
        payload = path.read_bytes()
        return payload, mime

    def open_details_window(self, book_id, screen_width=None, screen_height=None):
        if not WEBVIEW_AVAILABLE:
            return False
        detail_id = int(book_id)
        book = self.get_book_payload(detail_id)
        slug = _slug(book["title"])
        token = uuid.uuid4().hex
        width, height = 980, 780
        x, y = _centered_position(width, height, screen_width, screen_height)
        window = webview.create_window(
            f"Detalhes - {book['title']}",
            f"{self.base_url}/detail.html?id={detail_id}&slug={slug}&v={token}",
            width=width,
            height=height,
            x=x,
            y=y,
            min_size=(860, 640),
            background_color="#050816",
        )
        self._track_child_window(token, window)
        return True

    def _track_child_window(self, token, window):
        self.windows[token] = window
        try:
            window.events.closed += lambda: self.windows.pop(token, None)
        except Exception:
            pass

    def close_child_window(self, token):
        window = self.windows.pop((token or "").strip(), None)
        if window is None:
            return False
        try:
            window.destroy()
        except Exception:
            pass
        return True
