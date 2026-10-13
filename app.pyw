
import sqlite3
import hashlib
import hmac
import base64
import mimetypes
import webbrowser
import io
import secrets
import threading
import urllib.request
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse
import tkinter as tk
from tkinter import messagebox, filedialog

try:
    from PIL import Image, ImageTk
    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False

DB_PATH = Path(__file__).with_name("biblioteca.db")
from web_runtime import LoginRateLimiter, MIN_PASSWORD_LENGTH  # noqa: E402
COVER_CACHE_DIR = Path(__file__).with_name("covers_cache")
APP_ROOT = Path(__file__).resolve().parent

BG = "#050816"
SURFACE = "#0f1730"
PANEL = "#101a32"
CARD = "#17284c"
CARD_HOVER = "#20355f"
CARD_SELECTED = "#243b69"
BORDER = "#182847"
TEXT = "#f2f6ff"
MUTED = "#94a7cf"
BLUE = "#2f67ff"
BLUE_HOVER = "#2757dd"
GREEN = "#18b86a"
GREEN_HOVER = "#119155"
RED = "#d92e40"
RED_HOVER = "#b82433"
PURPLE = "#7b5cff"
PURPLE_HOVER = "#6545ea"
CYAN = "#18b6ff"
CYAN_HOVER = "#0f95d8"
AMBER = "#f59e0b"
AMBER_HOVER = "#dd8707"
SURFACE_ALT = "#0b1328"
SURFACE_GLOW = "#18274d"
INPUT_BG = "#091123"
CHIP_BG = "#101d3d"
CHIP_BORDER = "#27406c"
DETAIL_PANEL = "#0c142c"
SOFT_TEXT = "#d1dcf7"
SHADOW = "#050b19"
BORDER_GLOW = "#2a4779"


def button_border_color(bg_color):
    mapping = {
        GREEN: "#14955e",
        RED: "#b92e40",
        BLUE: "#3b62db",
        CYAN: "#1c92d1",
        PURPLE: "#6b4de3",
        AMBER: "#c48114",
        SURFACE_GLOW: "#365486",
        SURFACE_ALT: BORDER,
        CHIP_BG: CHIP_BORDER,
    }
    return mapping.get(bg_color, BORDER)


class _DatabaseBase:
    def delete_book(self, book_id: int, user_id: int):
        cur = self.conn.cursor()
        cur.execute("DELETE FROM books WHERE id = ? AND user_id = ?", (book_id, user_id))
        self.conn.commit()

    def get_book(self, book_id: int, user_id: int):
        cur = self.conn.cursor()
        cur.execute("SELECT * FROM books WHERE id = ? AND user_id = ?", (book_id, user_id))
        return cur.fetchone()


class SoftButton(tk.Button):
    def __init__(self, master, text, bg_color, hover_color, command=None):
        super().__init__(
            master,
            text=text,
            command=command,
            bg=bg_color,
            fg="white",
            activebackground=hover_color,
            activeforeground="white",
            relief="flat",
            bd=0,
            padx=18,
            pady=9,
            cursor="hand2",
            font=("Segoe UI", 9, "bold"),
            disabledforeground=MUTED,
            highlightthickness=1,
            highlightbackground=button_border_color(bg_color),
            highlightcolor=button_border_color(bg_color),
            overrelief="flat",
        )
        self.default_bg = bg_color
        self.hover_bg = hover_color
        self.default_border = button_border_color(bg_color)
        self.bind("<Enter>", lambda e: self._apply_hover(True))
        self.bind("<Leave>", lambda e: self._apply_hover(False))

    def _apply_hover(self, active):
        if str(self.cget("state")) == "disabled":
            return
        self.config(
            bg=(self.hover_bg if active else self.default_bg),
            highlightbackground=(self.hover_bg if active else self.default_border),
        )


class EntryField(tk.Frame):
    def __init__(self, master, label, textvariable=None, show=None, allow_toggle=False):
        container_bg = master.cget("bg") if hasattr(master, "cget") else PANEL
        super().__init__(master, bg=container_bg)
        self.default_show = show or ""
        self.allow_toggle = bool(allow_toggle and show)
        self.password_visible = False
        tk.Label(self, text=label, bg=container_bg, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 7))
        shell = tk.Frame(
            self,
            bg=INPUT_BG,
            highlightthickness=1,
            highlightbackground=BORDER,
            highlightcolor=CYAN,
            padx=12,
            pady=2,
        )
        shell.pack(fill="x")
        self.entry = tk.Entry(
            shell,
            textvariable=textvariable,
            show=self.default_show,
            bg=INPUT_BG,
            fg=TEXT,
            insertbackground=TEXT,
            relief="flat",
            highlightthickness=0,
            bd=0,
            font=("Segoe UI", 10),
        )
        self.entry.pack(side="left", fill="x", expand=True, ipady=10)
        if self.allow_toggle:
            self.toggle_button = tk.Label(
                shell,
                text="Mostrar",
                bg=CHIP_BG,
                fg=SOFT_TEXT,
                font=("Segoe UI", 8, "bold"),
                padx=10,
                pady=6,
                cursor="hand2",
                highlightthickness=1,
                highlightbackground=CHIP_BORDER,
            )
            self.toggle_button.pack(side="left", padx=(10, 0))
            self.toggle_button.bind("<Button-1>", self._toggle_password_visibility)

    def _toggle_password_visibility(self, _event=None):
        self.password_visible = not self.password_visible
        self.entry.configure(show=("" if self.password_visible else self.default_show))
        if hasattr(self, "toggle_button") and self.toggle_button.winfo_exists():
            self.toggle_button.configure(text=("Ocultar" if self.password_visible else "Mostrar"))
        return "break"


def segment_accent(value, label):
    text = f"{value} {label}".casefold()
    if "light novel" in text:
        return PURPLE
    if "livro" in text and "light" not in text:
        return CYAN
    if "quero" in text:
        return AMBER
    if "lendo" in text:
        return BLUE
    if "conclu" in text:
        return GREEN
    if "progress" in text:
        return PURPLE
    if "recent" in text:
        return BLUE
    if "a-z" in text:
        return CYAN
    return BLUE


class SegmentedButtonGroup(tk.Frame):
    def __init__(self, master, variable, options, callback):
        super().__init__(
            master,
            bg=SURFACE_ALT,
            highlightthickness=1,
            highlightbackground=BORDER,
            padx=6,
            pady=6,
        )
        self.variable = variable
        self.callback = callback
        self.buttons = {}
        for value, label in options:
            btn = tk.Button(
                self,
                text=label,
                command=lambda v=value: self.select(v),
                bg=SURFACE_ALT,
                fg=SOFT_TEXT,
                activebackground=CARD_HOVER,
                activeforeground="white",
                relief="flat",
                bd=0,
                padx=18,
                pady=8,
                cursor="hand2",
                font=("Segoe UI", 9, "bold"),
                highlightthickness=1,
                highlightbackground=SURFACE_ALT,
                highlightcolor=SURFACE_ALT,
            )
            btn.pack(side="left", padx=(0, 6))
            btn.segment_accent = segment_accent(value, label)
            btn.bind("<Enter>", lambda _event, v=value: self._set_hover(v, True))
            btn.bind("<Leave>", lambda _event, v=value: self._set_hover(v, False))
            self.buttons[value] = btn
        self.refresh()

    def select(self, value):
        self.variable.set(value)
        self.refresh()
        self.callback()

    def refresh(self):
        for value, btn in self.buttons.items():
            if self.variable.get() == value:
                accent = getattr(btn, "segment_accent", BLUE)
                btn.config(
                    bg=accent,
                    fg="white",
                    activebackground=accent,
                    highlightbackground=button_border_color(accent),
                )
            else:
                btn.config(
                    bg=SURFACE_ALT,
                    fg=SOFT_TEXT,
                    activebackground=CARD_HOVER,
                    highlightbackground=SURFACE_ALT,
                )

    def _set_hover(self, value, active):
        if self.variable.get() == value:
            return
        btn = self.buttons.get(value)
        if not btn:
            return
        btn.config(
            bg=("#162649" if active else SURFACE_ALT),
            fg=("white" if active else SOFT_TEXT),
            highlightbackground=(BORDER_GLOW if active else SURFACE_ALT),
        )


class CoverPreview(tk.Frame):
    def __init__(self, master, width=230, height=300):
        super().__init__(master, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER_GLOW, width=width, height=height)
        self.pack_propagate(False)
        self.inner = tk.Frame(self, bg=INPUT_BG)
        self.inner.pack(fill="both", expand=True, padx=10, pady=10)
        self.label = tk.Label(
            self.inner,
            text="Sem capa",
            bg=INPUT_BG,
            fg=MUTED,
            font=("Segoe UI", 10, "bold"),
            justify="center",
            wraplength=max(100, width - 24),
        )
        self.label.pack(fill="both", expand=True)
        self.image_ref = None

    def set_text(self, text):
        self.image_ref = None
        self.label.configure(image="", text=text, fg=MUTED, bg=INPUT_BG)

    def set_image(self, image):
        self.image_ref = image
        self.label.configure(image=self.image_ref, text="")


class _BookCardBase(tk.Frame):
    def __init__(self, master, book, on_select, selected=False):
        bg = CARD_SELECTED if selected else CARD
        border = BLUE if selected else BORDER
        super().__init__(master, bg=bg, highlightthickness=1, highlightbackground=border, cursor="hand2")
        self.book = book
        self.on_select = on_select
        self.default_bg = bg
        self.hover_bg = CARD_HOVER if not selected else CARD_SELECTED

        accent = {
            "Quero Ler": PURPLE,
            "Lendo": BLUE,
            "Concluído": GREEN,
        }.get(book["status"], CYAN)

        left_bar = tk.Frame(self, bg=accent, width=6)
        left_bar.pack(side="left", fill="y")

        body = tk.Frame(self, bg=bg)
        body.pack(side="left", fill="both", expand=True)

        top = tk.Frame(body, bg=bg)
        top.pack(fill="x", padx=14, pady=(12, 6))

        title = tk.Label(top, text=book["title"], bg=bg, fg="white", font=("Segoe UI", 12, "bold"), anchor="w")
        title.pack(side="left", fill="x", expand=True)

        badge = tk.Label(top, text=book["status"], bg=accent, fg="white", font=("Segoe UI", 9, "bold"), padx=10, pady=4)
        badge.pack(side="right")

        subtitle = tk.Label(body, text=f"{book['author'] or 'Autor não informado'}  •  {book['category'] or 'Sem categoria'}", bg=bg, fg=MUTED, font=("Segoe UI", 9), anchor="w")
        subtitle.pack(fill="x", padx=14)

        meta = tk.Label(body, text=f"Capítulo: {book['current_chapter'] or '-'}   •   Temporada: {book['season'] or '-'}", bg=bg, fg=TEXT, font=("Segoe UI", 9), anchor="w")
        meta.pack(fill="x", padx=14, pady=(8, 4))

        updated = tk.Label(body, text=f"Atualizado: {book['updated_at']}", bg=bg, fg=MUTED, font=("Segoe UI", 8), anchor="w")
        updated.pack(fill="x", padx=14, pady=(0, 12))

        self._bind_recursive(self)
        self._bind_hover_recursive(self)

    def _bind_recursive(self, widget):
        widget.bind("<Button-1>", self._handle_click)
        for child in widget.winfo_children():
            self._bind_recursive(child)

    def _bind_hover_recursive(self, widget):
        widget.bind("<Enter>", lambda e: self._set_hover(True))
        widget.bind("<Leave>", lambda e: self._set_hover(False))
        for child in widget.winfo_children():
            self._bind_hover_recursive(child)

    def _handle_click(self, _event=None):
        self.on_select(self.book["id"])


class _ScrollableCardsBase(tk.Frame):
    def __init__(self, master, bg):
        super().__init__(master, bg=bg)
        self.canvas = tk.Canvas(self, bg=bg, highlightthickness=0, bd=0)
        self.scrollbar = tk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.inner = tk.Frame(self.canvas, bg=bg)

        self.window_id = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.canvas.configure(yscrollcommand=self.scrollbar.set)

        self.inner.bind("<Configure>", self._on_inner_configure)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")

    def _on_inner_configure(self, _event=None):
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _on_canvas_configure(self, event):
        self.canvas.itemconfigure(self.window_id, width=event.width)


class _BookFormBase(tk.Toplevel):
    def choose_cover(self):
        path = filedialog.askopenfilename(title="Escolher capa", filetypes=[("Imagens", "*.png *.jpg *.jpeg *.gif *.webp"), ("Todos os arquivos", "*.*")])
        if path:
            self.vars["cover_path"].set(path)
            self.update_preview()

    def open_cover_source(self):
        source = self.vars["cover_path"].get().strip()
        if not source:
            messagebox.showwarning("Aviso", "Informe uma capa primeiro.")
            return
        resolved = resolve_cover_source(source, allow_download=True)
        try:
            if is_remote_source(resolved):
                webbrowser.open(resolved)
            else:
                webbrowser.open(Path(resolved).resolve().as_uri())
            return
        except Exception:
            pass
        try:
            if source.startswith(("http://", "https://")):
                webbrowser.open(source)
            else:
                webbrowser.open(Path(source).resolve().as_uri())
        except Exception:
            messagebox.showwarning("Aviso", "Não foi possível abrir a capa.")

    def save(self):
        data = {k: v.get() for k, v in self.vars.items()}
        data["notes"] = self.notes.get("1.0", "end").strip()
        error = self.validate_data(data)
        if error:
            messagebox.showwarning("Aviso", error)
            return
        self.on_save(data)
        self.destroy()


class _AppBase(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Biblioteca Virtual Aberta")
        self.geometry("1360x860")
        self.minsize(1220, 780)
        self.configure(bg=BG)

        self.db = Database(DB_PATH)
        self._login_limiter = LoginRateLimiter()
        self.current_user = None
        self.selected_book_id = None
        self.detail_cover_ref = None

        self.search_var = tk.StringVar()
        self.status_filter_var = tk.StringVar(value="")
        self.summary_vars = {
            "total": tk.StringVar(value="0"),
            "lendo": tk.StringVar(value="0"),
            "quero_ler": tk.StringVar(value="0"),
            "concluidos": tk.StringVar(value="0"),
        }

        self.show_login()

    def show_login(self):
        self.clear_window()
        self.current_user = None

        outer = tk.Frame(self, bg=BG)
        outer.pack(fill="both", expand=True)

        card = tk.Frame(outer, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, padx=34, pady=28)
        card.place(relx=0.5, rely=0.5, anchor="center", width=460, height=590)

        tk.Label(card, text="Biblioteca Virtual Aberta", bg=PANEL, fg="white", font=("Segoe UI", 24, "bold")).pack(pady=(10, 6))
        tk.Label(card, text="Aplicativo local para organizar suas leituras", bg=PANEL, fg=MUTED, font=("Segoe UI", 10)).pack(pady=(0, 22))

        self.login_email = tk.StringVar()
        self.login_password = tk.StringVar()
        self.register_name = tk.StringVar()
        self.register_email = tk.StringVar()
        self.register_password = tk.StringVar()
        self.register_confirm_password = tk.StringVar()

        tabs = tk.Frame(card, bg=PANEL)
        tabs.pack(fill="x", pady=(0, 16))
        self.login_tab_btn = SoftButton(tabs, "Entrar", BLUE, BLUE_HOVER, self.show_login_tab)
        self.login_tab_btn.pack(side="left", fill="x", expand=True, padx=(0, 8))
        self.register_tab_btn = SoftButton(tabs, "Cadastrar", CARD, CARD_HOVER, self.show_register_tab)
        self.register_tab_btn.pack(side="left", fill="x", expand=True)

        self.tab_content = tk.Frame(card, bg=PANEL)
        self.tab_content.pack(fill="both", expand=True)
        self.show_login_tab()

    def clear_tab(self):
        for widget in self.tab_content.winfo_children():
            widget.destroy()

    def activate_tab(self, tab_name):
        if tab_name == "login":
            self.login_tab_btn.config(bg=BLUE)
            self.login_tab_btn.default_bg = BLUE
            self.register_tab_btn.config(bg=CARD)
            self.register_tab_btn.default_bg = CARD
        else:
            self.login_tab_btn.config(bg=CARD)
            self.login_tab_btn.default_bg = CARD
            self.register_tab_btn.config(bg=BLUE)
            self.register_tab_btn.default_bg = BLUE

    def show_login_tab(self):
        self.clear_tab()
        self.activate_tab("login")
        EntryField(self.tab_content, "Email ou usuario", self.login_email).pack(fill="x", pady=(0, 12))
        EntryField(self.tab_content, "Senha", self.login_password, show="*", allow_toggle=True).pack(fill="x", pady=(0, 16))
        SoftButton(self.tab_content, "Entrar", BLUE, BLUE_HOVER, self.handle_login).pack(fill="x", pady=(8, 0))

    def show_register_tab(self):
        self.clear_tab()
        self.activate_tab("register")
        EntryField(self.tab_content, "Nome", self.register_name).pack(fill="x", pady=(0, 10))
        EntryField(self.tab_content, "Email ou usuario", self.register_email).pack(fill="x", pady=(0, 10))
        EntryField(self.tab_content, "Senha", self.register_password, show="*", allow_toggle=True).pack(fill="x", pady=(0, 10))
        EntryField(self.tab_content, "Confirmar senha", self.register_confirm_password, show="*", allow_toggle=True).pack(fill="x", pady=(0, 16))
        SoftButton(self.tab_content, "Criar conta", GREEN, GREEN_HOVER, self.handle_register).pack(fill="x", pady=(8, 0))

    def handle_login(self):
        login_key = self.login_email.get().strip().lower()
        wait = self._login_limiter.blocked_for(login_key)
        if wait:
            messagebox.showwarning("Aviso", f"Muitas tentativas. Aguarde {wait} segundos e tente de novo.")
            return
        user = self.db.get_user_by_credentials(self.login_email.get(), self.login_password.get())
        if not user:
            self._login_limiter.register_failure(login_key)
            messagebox.showerror("Erro", "Login ou senha invalidos.")
            return
        self._login_limiter.register_success(login_key)
        self.current_user = user
        self.show_main()

    def handle_register(self):
        name = self.register_name.get().strip()
        email = self.register_email.get().strip().lower()
        password = self.register_password.get().strip()
        confirm_password = self.register_confirm_password.get().strip()
        if not name or not email or not password or not confirm_password:
            messagebox.showwarning("Aviso", "Preencha nome, email, senha e confirmação.")
            return
        if password != confirm_password:
            messagebox.showerror("Erro", "As senhas não coincidem.")
            return
        try:
            self.db.create_user(name, email, password)
        except ValueError as exc:
            messagebox.showerror("Erro", str(exc))
            return
        except sqlite3.IntegrityError:
            messagebox.showerror("Erro", "Já existe uma conta com esse email.")
            return
        messagebox.showinfo("Sucesso", "Conta criada com sucesso. Agora você já pode entrar.")
        self.login_email.set(email)
        self.login_password.set("")
        self.register_name.set("")
        self.register_email.set("")
        self.register_password.set("")
        self.register_confirm_password.set("")
        self.show_login_tab()

    def current_book(self):
        if not self.selected_book_id:
            return None
        return self.db.get_book(self.selected_book_id, self.current_user["id"])

    def copy_link(self):
        book = self.current_book()
        if not book or not book["reading_link"]:
            messagebox.showwarning("Aviso", "Este livro não possui link salvo.")
            return
        self.clipboard_clear()
        self.clipboard_append(book["reading_link"])
        messagebox.showinfo("Copiado", "Link copiado para a área de transferência.")


STATUS_WANT = "Quero Ler"
STATUS_READING = "Lendo"
STATUS_DONE = "Conclu\u00eddo"
TYPE_BOOK = "Livro"
TYPE_LIGHT_NOVEL = "Light Novel"
TYPE_ADULT = "Adulto"
DEFAULT_CATEGORY_OPTIONS = ("Romance", "Aventura", "Comedia", "Suspense")
PBKDF2_ITERATIONS = 200_000
REMOTE_IMAGE_TIMEOUT = 10
# Only raster images are accepted as covers. SVG is deliberately excluded: it can
# carry <script> and would run in the app's origin if opened directly.
ALLOWED_COVER_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
MAX_COVER_IMPORT_BYTES = 25 * 1024 * 1024


def legacy_hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    derived = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        PBKDF2_ITERATIONS,
    )
    return f"pbkdf2_sha256${PBKDF2_ITERATIONS}${salt}${derived.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    if not stored_hash:
        return False
    if stored_hash.startswith("pbkdf2_sha256$"):
        try:
            _, iterations_text, salt, expected_hash = stored_hash.split("$", 3)
            iterations = int(iterations_text)
        except (TypeError, ValueError):
            return False
        derived = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            iterations,
        )
        return hmac.compare_digest(derived.hex(), expected_hash)
    return hmac.compare_digest(legacy_hash_password(password), stored_hash)


def needs_password_upgrade(stored_hash: str) -> bool:
    return not (stored_hash or "").startswith("pbkdf2_sha256$")


def is_remote_source(source: str) -> bool:
    return (source or "").strip().startswith(("http://", "https://"))


def ensure_cover_cache_dir() -> Path:
    COVER_CACHE_DIR.mkdir(exist_ok=True)
    return COVER_CACHE_DIR


def cover_cache_key(source: str) -> str:
    return hashlib.sha1((source or "").strip().encode("utf-8"), usedforsecurity=False).hexdigest()


def find_cached_cover(source: str):
    if not is_remote_source(source):
        path = resolve_storage_path(source)
        return path if path.exists() else None
    cache_dir = ensure_cover_cache_dir()
    key = cover_cache_key(source)
    matches = sorted(cache_dir.glob(f"{key}.*"))
    for match in matches:
        if match.is_file():
            return match
    return None


def guess_cover_extension(source: str, content_type: str = "") -> str:
    mime = (content_type or "").split(";", 1)[0].strip().lower()
    extension = mimetypes.guess_extension(mime) if mime else None
    if extension == ".jpe":
        extension = ".jpg"
    if not extension:
        parsed = urlparse((source or "").strip())
        suffix = Path(parsed.path).suffix.lower()
        extension = suffix or ".img"
    return extension


def is_within_app_storage(path: Path) -> bool:
    try:
        path.resolve().relative_to(APP_ROOT)
        return True
    except ValueError:
        return False


def to_relative_storage_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(APP_ROOT))
    except ValueError:
        return str(path)


def resolve_storage_path(source: str) -> Path:
    path = Path((source or "").strip()).expanduser()
    if not path.is_absolute():
        path = APP_ROOT / path
    return path


def cache_local_cover(source: str):
    source = (source or "").strip()
    if not source:
        return source
    path = Path(source).expanduser()
    if not path.is_file():
        return source
    if is_within_app_storage(path):
        return to_relative_storage_path(path)
    cache_dir = ensure_cover_cache_dir()
    key = cover_cache_key(str(path.resolve()))
    for match in sorted(cache_dir.glob(f"{key}.*")):
        if match.is_file() and match.suffix.lower() in ALLOWED_COVER_EXTENSIONS:
            return to_relative_storage_path(match)
    try:
        extension = path.suffix.lower()
        if extension not in ALLOWED_COVER_EXTENSIONS:
            return source
        if path.stat().st_size > MAX_COVER_IMPORT_BYTES:
            return source
        cache_path = cache_dir / f"{key}{extension}"
        temp_path = cache_dir / f"{cache_path.name}.tmp"
        temp_path.write_bytes(path.read_bytes())
        temp_path.replace(cache_path)
        return to_relative_storage_path(cache_path)
    except Exception:
        return source


def cache_remote_cover(source: str):
    source = (source or "").strip()
    if not is_remote_source(source):
        return source
    cached = find_cached_cover(source)
    if cached:
        return to_relative_storage_path(cached)
    try:
        cache_dir = ensure_cover_cache_dir()
        request = urllib.request.Request(source, headers={"User-Agent": "BibliotecaVirtualAberta/1.0"})
        # só http/https chegam aqui (is_remote_source); file:// e afins nunca
        with urllib.request.urlopen(request, timeout=REMOTE_IMAGE_TIMEOUT) as response:  # nosec B310
            payload = response.read(MAX_COVER_IMPORT_BYTES + 1)
            content_type = response.headers.get("Content-Type", "")
        if not payload or len(payload) > MAX_COVER_IMPORT_BYTES:
            return source
        extension = guess_cover_extension(source, content_type)
        if extension not in ALLOWED_COVER_EXTENSIONS:
            return source
        cache_path = cache_dir / f"{cover_cache_key(source)}{extension}"
        temp_path = cache_dir / f"{cache_path.name}.tmp"
        temp_path.write_bytes(payload)
        temp_path.replace(cache_path)
        return to_relative_storage_path(cache_path)
    except Exception:
        return source


def resolve_cover_source(source: str, allow_download: bool = True) -> str:
    source = (source or "").strip()
    if not source:
        return ""
    if is_remote_source(source):
        cached = find_cached_cover(source)
        if cached:
            return to_relative_storage_path(cached)
        if allow_download:
            cached_source = cache_remote_cover(source)
            if cached_source and not is_remote_source(cached_source):
                return cached_source
        return source
    path = resolve_storage_path(source)
    if allow_download:
        if path.is_file():
            return cache_local_cover(str(path))
        return source
    if path.exists():
        return str(path)
    return source


def read_image_bytes(source: str):
    source = resolve_cover_source(source, allow_download=True)
    if not source:
        return None
    try:
        if is_remote_source(source):
            request = urllib.request.Request(source, headers={"User-Agent": "BibliotecaVirtualAberta/1.0"})
            with urllib.request.urlopen(request, timeout=REMOTE_IMAGE_TIMEOUT) as response:  # nosec B310 (só http/https)
                payload = response.read(MAX_COVER_IMPORT_BYTES + 1)
            return payload if len(payload) <= MAX_COVER_IMPORT_BYTES else None
        path = Path(source)
        if path.exists():
            return path.read_bytes()
    except Exception:
        return None
    return None


def create_file_photo_image(source: str, size):
    source = resolve_cover_source(source, allow_download=False)
    path = Path(source)
    if not path.exists():
        return None
    try:
        photo = tk.PhotoImage(file=str(path))
        max_width, max_height = size
        scale_x = max(1, (photo.width() + max_width - 1) // max_width) if max_width else 1
        scale_y = max(1, (photo.height() + max_height - 1) // max_height) if max_height else 1
        scale = max(scale_x, scale_y)
        if scale > 1:
            photo = photo.subsample(scale, scale)
        return photo
    except Exception:
        return None


def create_photo_image(raw: bytes, size):
    if not raw:
        return None
    if PIL_AVAILABLE:
        image = Image.open(io.BytesIO(raw))
        image.thumbnail(size)
        return ImageTk.PhotoImage(image)
    try:
        encoded = base64.b64encode(raw).decode("ascii")
        photo = tk.PhotoImage(data=encoded)
        max_width, max_height = size
        scale_x = max(1, (photo.width() + max_width - 1) // max_width) if max_width else 1
        scale_y = max(1, (photo.height() + max_height - 1) // max_height) if max_height else 1
        scale = max(scale_x, scale_y)
        if scale > 1:
            photo = photo.subsample(scale, scale)
        return photo
    except Exception:
        return None


def image_probably_needs_pillow(source: str) -> bool:
    if PIL_AVAILABLE:
        return False
    source = (source or "").strip().lower()
    if not source:
        return False
    source = source.split("?", 1)[0].split("#", 1)[0]
    return source.endswith((".jpg", ".jpeg", ".webp", ".bmp", ".tiff", ".tif", ".ico"))


def cover_unavailable_text(source: str) -> str:
    if image_probably_needs_pillow(source):
        return "Instale Pillow\npara JPG/WEBP"
    return "Use Abrir capa\npara visualizar"


def cover_help_text(source: str) -> str:
    if image_probably_needs_pillow(source):
        return "Essa capa parece usar JPG/WEBP. Rode install_pillow.bat uma vez."
    return "Verifique o caminho/URL da capa."


def row_value(row, key, *fallback_keys):
    if not row:
        return ""
    keys = set(row.keys()) if hasattr(row, "keys") else set()
    if key in keys and row[key] is not None:
        return str(row[key])
    for fallback_key in fallback_keys:
        if fallback_key in keys and row[fallback_key] is not None:
            return str(row[fallback_key])
    return ""


def format_display_datetime(value: str) -> str:
    raw = (value or "").strip()
    if not raw:
        return "-"

    has_time = len(raw) > 10 or " " in raw or "T" in raw
    normalized = raw.replace("Z", "+00:00")

    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        parsed = None
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
            try:
                parsed = datetime.strptime(raw, fmt)
                break
            except ValueError:
                pass
        if parsed is None:
            return raw

    if has_time:
        return parsed.strftime("%d/%m/%Y %H:%M:%S")
    return parsed.strftime("%d/%m/%Y")


def truncate_text(value: str, limit: int = 56) -> str:
    text = (value or "").strip()
    if not text:
        return "-"
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 3)].rstrip() + "..."


class Database(_DatabaseBase):
    def __init__(self, db_path: Path):
        self.conn = sqlite3.connect(db_path, check_same_thread=False, timeout=30)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA foreign_keys = ON")
        self.conn.execute("PRAGMA journal_mode = WAL")
        self.conn.execute("PRAGMA busy_timeout = 30000")
        self.create_tables()
        self.migrate_books_table()

    def create_tables(self):
        cur = self.conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS books (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                book_type TEXT DEFAULT '{TYPE_BOOK}',
                author TEXT,
                status TEXT DEFAULT '{STATUS_WANT}',
                last_page TEXT,
                total_pages TEXT,
                cover_path TEXT,
                reading_link TEXT,
                notes TEXT,
                category TEXT,
                is_favorite INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        cur.execute("""
            CREATE TABLE IF NOT EXISTS book_categories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL COLLATE NOCASE,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, name),
                FOREIGN KEY(user_id) REFERENCES users(id) ON DELETE CASCADE
            )
        """)
        self.conn.commit()

    def migrate_books_table(self):
        cur = self.conn.cursor()
        cur.execute("PRAGMA table_info(books)")
        columns = {row["name"] for row in cur.fetchall()}
        additions = {
            "book_type": f"ALTER TABLE books ADD COLUMN book_type TEXT DEFAULT '{TYPE_BOOK}'",
            "category": "ALTER TABLE books ADD COLUMN category TEXT",
            "last_page": "ALTER TABLE books ADD COLUMN last_page TEXT",
            "total_pages": "ALTER TABLE books ADD COLUMN total_pages TEXT",
            "is_favorite": "ALTER TABLE books ADD COLUMN is_favorite INTEGER DEFAULT 0",
        }
        for col, sql in additions.items():
            if col not in columns:
                cur.execute(sql)
                columns.add(col)
        if "current_chapter" in columns and "last_page" in columns:
            cur.execute("""
                UPDATE books
                SET last_page = current_chapter
                WHERE COALESCE(NULLIF(last_page, ''), '') = ''
                  AND COALESCE(NULLIF(current_chapter, ''), '') <> ''
            """)
        if "book_type" in columns:
            cur.execute(
                """
                UPDATE books
                SET book_type = ?
                WHERE COALESCE(NULLIF(book_type, ''), '') = ''
                """,
                (TYPE_BOOK,),
            )
        if "is_favorite" in columns:
            cur.execute(
                """
                UPDATE books
                SET is_favorite = 0
                WHERE is_favorite IS NULL
                """
            )
        self.conn.commit()

    def close(self):
        self.conn.close()

    @staticmethod
    def _normalize_category_text(name: str) -> str:
        text = (name or "").strip()
        if not text or text.casefold() == "sem categoria":
            return ""
        return text

    def ensure_category(self, user_id: int, name: str) -> str:
        category = self._normalize_category_text(name)
        if not category:
            return ""
        cur = self.conn.cursor()
        cur.execute(
            """
            INSERT OR IGNORE INTO book_categories (user_id, name)
            VALUES (?, ?)
            """,
            (user_id, category),
        )
        self.conn.commit()
        cur.execute(
            """
            SELECT name
            FROM book_categories
            WHERE user_id = ? AND LOWER(name) = LOWER(?)
            LIMIT 1
            """,
            (user_id, category),
        )
        row = cur.fetchone()
        return row["name"] if row and row["name"] else category

    def ensure_categories(self, user_id: int, names) -> str:
        """Aceita uma string com tags separadas por virgula (ou uma lista),
        registra cada uma individualmente e retorna a string normalizada
        pronta para salvar em books.category."""
        if isinstance(names, str):
            raw_items = names.split(",")
        else:
            raw_items = list(names or [])
        normalized = []
        seen_lower = set()
        for raw in raw_items:
            resolved = self.ensure_category(user_id, raw)
            if not resolved:
                continue
            key = resolved.casefold()
            if key in seen_lower:
                continue
            seen_lower.add(key)
            normalized.append(resolved)
        return ", ".join(normalized)

    def add_category(self, user_id: int, name: str) -> str:
        category = self.ensure_category(user_id, name)
        if not category:
            raise ValueError("Informe um nome valido para a tag.")
        return category

    def list_categories(self, user_id: int):
        cur = self.conn.cursor()
        seen = set()
        result = []

        def add(value: str):
            category = self._normalize_category_text(value)
            if not category:
                return
            key = category.casefold()
            if key in seen:
                return
            seen.add(key)
            result.append(category)

        for option in DEFAULT_CATEGORY_OPTIONS:
            add(option)

        cur.execute(
            """
            SELECT DISTINCT category
            FROM books
            WHERE user_id = ?
              AND COALESCE(TRIM(category), '') <> ''
            """,
            (user_id,),
        )
        db_categories_raw = [row["category"] for row in cur.fetchall()]
        db_categories = []
        for combined in db_categories_raw:
            db_categories.extend((combined or "").split(","))
        cur.execute(
            """
            SELECT name
            FROM book_categories
            WHERE user_id = ?
            ORDER BY name COLLATE NOCASE
            """,
            (user_id,),
        )
        custom_categories = [row["name"] for row in cur.fetchall()]

        for value in sorted(db_categories + custom_categories, key=lambda text: (text or "").casefold()):
            add(value)
        return result

    def find_duplicate_book(self, user_id: int, title: str, exclude_book_id=None):
        normalized_title = (title or "").strip().casefold()
        if not normalized_title:
            return None
        cur = self.conn.cursor()
        query = """
            SELECT *
            FROM books
            WHERE user_id = ?
              AND LOWER(TRIM(title)) = ?
        """
        params = [user_id, normalized_title]
        if exclude_book_id is not None:
            query += " AND id <> ?"
            params.append(int(exclude_book_id))
        query += " ORDER BY id ASC LIMIT 1"
        cur.execute(query, params)
        return cur.fetchone()

    def name_exists(self, name: str) -> bool:
        cur = self.conn.cursor()
        cur.execute("SELECT 1 FROM users WHERE LOWER(name) = LOWER(?) LIMIT 1", (name.strip(),))
        return cur.fetchone() is not None

    def create_user(self, name: str, email: str, password: str):
        if len(password or "") < MIN_PASSWORD_LENGTH:
            raise ValueError(f"A senha precisa ter pelo menos {MIN_PASSWORD_LENGTH} caracteres.")
        cur = self.conn.cursor()
        cur.execute(
            "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
            (name.strip(), email.strip().lower(), hash_password(password)),
        )
        self.conn.commit()

    def get_user_by_credentials(self, login: str, password: str):
        login_value = login.strip()
        normalized_login = login_value.lower()
        cur = self.conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM users
            WHERE LOWER(email) = ?
               OR LOWER(name) = ?
            ORDER BY id ASC
            LIMIT 1
            """,
            (normalized_login, normalized_login),
        )
        user = cur.fetchone()
        if not user or not verify_password(password, user["password_hash"]):
            return None
        if needs_password_upgrade(user["password_hash"]):
            cur.execute(
                "UPDATE users SET password_hash = ? WHERE id = ?",
                (hash_password(password), user["id"]),
            )
            self.conn.commit()
            cur.execute("SELECT * FROM users WHERE id = ?", (user["id"],))
            user = cur.fetchone()
        return user

    def add_book(self, user_id: int, data: dict):
        category = self.ensure_categories(user_id, data["category"])
        cur = self.conn.cursor()
        cur.execute("""
            INSERT INTO books (
                user_id, title, book_type, author, status, last_page, total_pages,
                category, cover_path, reading_link, notes, is_favorite, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
        """, (
            user_id,
            data["title"].strip(),
            (data.get("book_type") or TYPE_BOOK).strip() or TYPE_BOOK,
            data["author"].strip(),
            data["status"].strip(),
            data["last_page"].strip(),
            data["total_pages"].strip(),
            category,
            data["cover_path"].strip(),
            data["reading_link"].strip(),
            data["notes"].strip(),
            (1 if data.get("is_favorite") else 0),
        ))
        self.conn.commit()
        return cur.lastrowid

    def update_book(self, book_id: int, user_id: int, data: dict):
        category = self.ensure_categories(user_id, data["category"])
        cur = self.conn.cursor()
        cur.execute("""
            UPDATE books
            SET title = ?, book_type = ?, author = ?, status = ?, last_page = ?, total_pages = ?,
                category = ?, cover_path = ?, reading_link = ?, notes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
        """, (
            data["title"].strip(),
            (data.get("book_type") or TYPE_BOOK).strip() or TYPE_BOOK,
            data["author"].strip(),
            data["status"].strip(),
            data["last_page"].strip(),
            data["total_pages"].strip(),
            category,
            data["cover_path"].strip(),
            data["reading_link"].strip(),
            data["notes"].strip(),
            book_id,
            user_id,
        ))
        self.conn.commit()

    def list_books(self, user_id: int, search: str = "", status: str = "", book_type: str = "", category: str = "", favorites_only: bool = False):
        cur = self.conn.cursor()
        query = "SELECT * FROM books WHERE user_id = ?"
        params = [user_id]
        if book_type.strip():
            query += " AND book_type = ?"
            params.append(book_type.strip())
        normalized_category = self._normalize_category_text(category)
        if normalized_category:
            query += " AND (',' || LOWER(REPLACE(COALESCE(category, ''), ' ', '')) || ',') LIKE ?"
            params.append('%,' + normalized_category.casefold().replace(' ', '') + ',%')
        if favorites_only:
            query += " AND is_favorite = 1"
        if search.strip():
            query += """
                AND (
                    LOWER(title) LIKE ?
                    OR LOWER(author) LIKE ?
                    OR LOWER(category) LIKE ?
                    OR LOWER(reading_link) LIKE ?
                    OR LOWER(notes) LIKE ?
                )
            """
            s = f"%{search.strip().lower()}%"
            params.extend([s, s, s, s, s])
        if status.strip():
            query += " AND status = ?"
            params.append(status.strip())
        query += " ORDER BY updated_at DESC, id DESC"
        cur.execute(query, params)
        return cur.fetchall()

    def count_by_status(self, user_id: int, book_type: str = "", category: str = "", favorites_only: bool = False):
        cur = self.conn.cursor()
        query = """
            SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS lendo,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS quero_ler,
                SUM(CASE WHEN status = ? THEN 1 ELSE 0 END) AS concluidos
            FROM books
            WHERE user_id = ?
        """
        params = [STATUS_READING, STATUS_WANT, STATUS_DONE, user_id]
        if book_type.strip():
            query += " AND book_type = ?"
            params.append(book_type.strip())
        normalized_category = self._normalize_category_text(category)
        if normalized_category:
            query += " AND (',' || LOWER(REPLACE(COALESCE(category, ''), ' ', '')) || ',') LIKE ?"
            params.append('%,' + normalized_category.casefold().replace(' ', '') + ',%')
        if favorites_only:
            query += " AND is_favorite = 1"
        cur.execute(query, params)
        row = cur.fetchone()
        return {
            "total": row["total"] or 0,
            "lendo": row["lendo"] or 0,
            "quero_ler": row["quero_ler"] or 0,
            "concluidos": row["concluidos"] or 0,
        }

    def set_book_favorite(self, book_id: int, user_id: int, favorite: bool):
        cur = self.conn.cursor()
        cur.execute(
            """
            UPDATE books
            SET is_favorite = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ? AND user_id = ?
            """,
            (1 if favorite else 0, book_id, user_id),
        )
        self.conn.commit()


class BookForm(_BookFormBase):
    def __init__(self, master, on_save, book=None):
        tk.Toplevel.__init__(self, master)
        self.context_type = (
            row_value(book, "book_type")
            or (master.library_var.get() if hasattr(master, "library_var") else TYPE_BOOK)
            or TYPE_BOOK
        )
        self.title(self.context_type)
        self.geometry("920x730")
        self.configure(bg=BG)
        self.resizable(False, False)
        self.on_save = on_save
        self.book = book
        self.preview_request_id = 0

        self.vars = {
            "title": tk.StringVar(value=row_value(book, "title")),
            "book_type": tk.StringVar(
                value=(
                    row_value(book, "book_type")
                    or self.context_type
                    or TYPE_BOOK
                )
            ),
            "author": tk.StringVar(value=row_value(book, "author")),
            "status": tk.StringVar(value=row_value(book, "status") or STATUS_WANT),
            "last_page": tk.StringVar(value=row_value(book, "last_page", "current_chapter")),
            "total_pages": tk.StringVar(value=row_value(book, "total_pages")),
            "category": tk.StringVar(value=row_value(book, "category")),
            "cover_path": tk.StringVar(value=row_value(book, "cover_path")),
            "reading_link": tk.StringVar(value=row_value(book, "reading_link")),
        }

        self.build_ui()
        self.transient(master)
        self.grab_set()
        self.update_preview()

    def build_ui(self):
        panel = tk.Frame(self, bg=DETAIL_PANEL, highlightthickness=1, highlightbackground=BORDER_GLOW)
        panel.place(x=18, y=18, relwidth=1, relheight=1, width=-36, height=-36)
        tk.Frame(panel, bg=PURPLE, height=2).pack(fill="x")

        footer = tk.Frame(panel, bg=DETAIL_PANEL, padx=22, pady=16)
        footer.pack(side="bottom", fill="x")

        self.form_area = ScrollableCards(panel, DETAIL_PANEL)
        self.form_area.pack(side="top", fill="both", expand=True)
        self.form_area.canvas.configure(yscrollincrement=18, highlightthickness=0, bd=0)
        if hasattr(self, "master") and hasattr(self.master, "style_scrollbar"):
            self.master.style_scrollbar(self.form_area.scrollbar)

        body = tk.Frame(self.form_area.inner, bg=DETAIL_PANEL, padx=22, pady=22)
        body.pack(fill="both", expand=True)

        heading = f"Editar {self.vars['book_type'].get() or TYPE_BOOK}" if self.book else f"Adicionar {self.context_type}"
        tk.Label(body, text=heading, bg=DETAIL_PANEL, fg="white", font=("Segoe UI", 22, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(body, text="Organize capa, progresso, categoria e link em um formulario mais limpo e integrado ao visual da biblioteca.", bg=DETAIL_PANEL, fg=SOFT_TEXT, font=("Segoe UI", 10)).pack(anchor="w", pady=(0, 18))

        content = tk.Frame(body, bg=DETAIL_PANEL)
        content.pack(fill="both", expand=True)

        left = tk.Frame(content, bg=DETAIL_PANEL)
        left.pack(side="left", fill="both", expand=True, padx=(0, 16))

        right = tk.Frame(content, bg=DETAIL_PANEL)
        right.pack(side="left", fill="y")

        def section(master, title, subtitle=None):
            shell = tk.Frame(master, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER, padx=16, pady=16)
            shell.pack(fill="x", pady=(0, 12))
            tk.Label(shell, text=title, bg=SURFACE_ALT, fg="white", font=("Segoe UI", 12, "bold")).pack(anchor="w")
            if subtitle:
                tk.Label(shell, text=subtitle, bg=SURFACE_ALT, fg=SOFT_TEXT, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 12))
            content_frame = tk.Frame(shell, bg=SURFACE_ALT)
            content_frame.pack(fill="both", expand=True)
            return content_frame

        basic_section = section(left, "Informacoes principais", "Titulo, autor e o contexto desta obra.")
        row1 = tk.Frame(basic_section, bg=SURFACE)
        row1.pack(fill="x", pady=(0, 10))
        EntryField(row1, "Titulo", self.vars["title"]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        EntryField(row1, "Autor", self.vars["author"]).pack(side="left", fill="x", expand=True)

        if self.book:
            type_wrap = tk.Frame(basic_section, bg=SURFACE)
            type_wrap.pack(fill="x")
            tk.Label(type_wrap, text="Tipo da obra", bg=SURFACE, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
            SegmentedButtonGroup(
                type_wrap,
                self.vars["book_type"],
                [(TYPE_BOOK, "Livro"), (TYPE_LIGHT_NOVEL, "Light Novel"), (TYPE_ADULT, "Adulto")],
                lambda: None,
            ).pack(anchor="w")
        else:
            context_wrap = tk.Frame(basic_section, bg=SURFACE)
            context_wrap.pack(fill="x")
            tk.Label(
                context_wrap,
                text=f"Colecao atual: {self.context_type}",
                bg=SURFACE,
                fg=SOFT_TEXT,
                font=("Segoe UI", 10, "bold"),
            ).pack(anchor="w")

        cover_section = section(left, "Capa e acesso", "Use URL ou caminho local para destacar a obra.")
        EntryField(cover_section, "Capa (caminho local ou URL)", self.vars["cover_path"]).pack(fill="x", pady=(0, 10))
        cover_buttons = tk.Frame(cover_section, bg=SURFACE)
        cover_buttons.pack(fill="x")
        SoftButton(cover_buttons, "Escolher arquivo", CYAN, CYAN_HOVER, self.choose_cover).pack(side="left", padx=(0, 8))
        SoftButton(cover_buttons, "Atualizar previa", AMBER, AMBER_HOVER, self.update_preview).pack(side="left")
        SoftButton(cover_buttons, "Abrir capa", PURPLE, PURPLE_HOVER, self.open_cover_source).pack(side="left", padx=(8, 0))

        reading_section = section(left, "Leitura e progresso", "Status atual e avancos da leitura.")
        row2 = tk.Frame(reading_section, bg=SURFACE)
        row2.pack(fill="x")
        status_wrap = tk.Frame(row2, bg=SURFACE)
        status_wrap.pack(side="left", fill="x", expand=True, padx=(0, 8))
        tk.Label(status_wrap, text="Status", bg=SURFACE, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        SegmentedButtonGroup(
            status_wrap,
            self.vars["status"],
            [(STATUS_WANT, "Quero Ler"), (STATUS_READING, "Lendo"), (STATUS_DONE, "Concluido")],
            lambda: None
        ).pack(anchor="w")

        EntryField(row2, "Ultima pagina", self.vars["last_page"]).pack(side="left", fill="x", expand=True, padx=(0, 8))
        EntryField(row2, "Total de paginas", self.vars["total_pages"]).pack(side="left", fill="x", expand=True)

        notes_section = section(left, "Categoria, link e observacoes", "Campos extras para organizar melhor sua biblioteca.")
        EntryField(notes_section, "Categoria / genero", self.vars["category"]).pack(fill="x", pady=(0, 10))
        EntryField(notes_section, "Link de leitura", self.vars["reading_link"]).pack(fill="x", pady=(0, 10))

        tk.Label(notes_section, text="Observacoes", bg=SURFACE, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self.notes = tk.Text(notes_section, height=8, wrap="word", bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat", highlightthickness=1, highlightbackground=BORDER, highlightcolor=CYAN, bd=0, font=("Segoe UI", 10))
        self.notes.pack(fill="both", expand=True)
        if row_value(self.book, "notes"):
            self.notes.insert("1.0", row_value(self.book, "notes"))

        preview_shell = tk.Frame(right, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER, padx=18, pady=18)
        preview_shell.pack(fill="y")
        tk.Frame(preview_shell, bg=CYAN, height=2).pack(fill="x", pady=(0, 14))
        tk.Label(preview_shell, text="Previa da capa", bg=SURFACE_ALT, fg="white", font=("Segoe UI", 14, "bold")).pack(anchor="w", pady=(0, 8))
        tk.Label(preview_shell, text="Uma capa forte deixa a obra mais viva e melhora bastante a leitura visual da colecao.", bg=SURFACE_ALT, fg=SOFT_TEXT, justify="left", wraplength=260, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 14))
        self.preview = CoverPreview(preview_shell, width=250, height=330)
        self.preview.pack()
        self.preview_status = tk.Label(preview_shell, text="Dica: use capa local ou URL.\nPara JPG/WEBP, instale Pillow.", bg=SURFACE_ALT, fg=MUTED, justify="left", wraplength=250, font=("Segoe UI", 9))
        self.preview_status.pack(anchor="w", pady=(12, 0))

        self.form_area.register_mousewheel(body)
        self.form_area.register_mousewheel(content)
        self.form_area.register_mousewheel(left)
        self.form_area.register_mousewheel(right)
        self.form_area.scroll_to_top()

        SoftButton(footer, "Salvar", BLUE, BLUE_HOVER, self.save).pack(side="left", fill="x", expand=True, padx=(0, 8))
        SoftButton(footer, "Cancelar", RED, RED_HOVER, self.destroy).pack(side="left", fill="x", expand=True)

    def update_preview(self):
        source = self.vars["cover_path"].get().strip()
        self.preview_request_id += 1
        request_id = self.preview_request_id
        if not source:
            self.preview.set_text("Previa da capa\n\nSem imagem")
            self.preview_status.config(text="Informe um caminho local ou URL.")
            return
        if not PIL_AVAILABLE and not source.startswith(("http://", "https://")):
            photo = create_file_photo_image(source, (250, 330))
            if photo:
                self.preview.set_image(photo)
                self.preview_status.config(text="Previa carregada com imagem local.")
                return
        if source.startswith(("http://", "https://")):
            self.preview.set_text("Carregando\ncapa...")
            self.preview_status.config(text="Baixando a imagem da capa...")
            threading.Thread(
                target=self._load_preview_async,
                args=(request_id, source),
                daemon=True,
            ).start()
            return
        raw = read_image_bytes(source)
        self._apply_preview_data(request_id, raw, source)

    def _load_preview_async(self, request_id, source):
        raw = read_image_bytes(source)
        try:
            self.after(0, lambda: self._apply_preview_data(request_id, raw, source))
        except tk.TclError:
            pass

    def _apply_preview_data(self, request_id, raw, source):
        if request_id != self.preview_request_id or not self.winfo_exists():
            return
        if raw is None:
            self.preview.set_text("Nao foi possivel\ncarregar a imagem")
            self.preview_status.config(text=cover_help_text(source))
            return
        try:
            photo = create_photo_image(raw, (250, 330))
            if photo:
                self.preview.set_image(photo)
                self.preview_status.config(text="Previa carregada com sucesso.")
            else:
                self.preview.set_text(cover_unavailable_text(source))
                self.preview_status.config(text=cover_help_text(source))
        except Exception:
            self.preview.set_text(cover_unavailable_text(source))
            self.preview_status.config(text=cover_help_text(source))

    def validate_data(self, data):
        if not data["title"].strip():
            return "Informe pelo menos o titulo do livro."
        last_page = data["last_page"].strip()
        total_pages = data["total_pages"].strip()
        if last_page and not last_page.isdigit():
            return "O campo Ultima pagina deve conter apenas numeros."
        if total_pages and not total_pages.isdigit():
            return "O campo Total de paginas deve conter apenas numeros."
        if last_page and total_pages and int(last_page) > int(total_pages):
            return "A ultima pagina nao pode ser maior que o total de paginas."
        link = data["reading_link"].strip()
        if link and " " in link:
            return "O link salvo parece invalido. Remova espacos."
        return None


class _AppExtended(_AppBase):
    def __init__(self):
        self.detail_cover_request_id = 0
        super().__init__()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def clear_window(self):
        self.detail_cover_request_id = getattr(self, "detail_cover_request_id", 0) + 1
        for widget in self.winfo_children():
            widget.destroy()

    def on_close(self):
        try:
            self.db.close()
        except Exception:
            pass
        self.destroy()


def progress_numbers(last_page: str, total_pages: str):
    current = (last_page or "").strip()
    total = (total_pages or "").strip()
    if current.isdigit() and total.isdigit() and int(total) > 0:
        current_number = min(int(current), int(total))
        percent = round((current_number / int(total)) * 100)
        return current or "-", total or "", percent
    return current or "-", total or "", None


def status_accent_color(status: str) -> str:
    return {
        STATUS_WANT: PURPLE,
        STATUS_READING: BLUE,
        STATUS_DONE: GREEN,
    }.get(status, CYAN)


def status_badge_colors(status: str):
    if status == STATUS_READING:
        return "#14213d", "#93c5fd"
    if status == STATUS_WANT:
        return "#332411", "#fde68a"
    if status == STATUS_DONE:
        return "#16311d", "#86efac"
    return "#12324a", "#7dd3fc"


class BookCard(_BookCardBase):
    def __init__(self, master, book, on_select, request_cover=None, register_mousewheel=None, on_continue=None, on_toggle_progress=None, on_open_link=None, on_copy_link=None, on_edit=None, on_delete=None, selected=False, show_progress=False):
        self.accent_color = status_accent_color(book["status"])
        tk.Frame.__init__(self, master, bg=BG, cursor="hand2")
        self.book = book
        self.on_select = on_select
        self.selected = selected
        self.request_cover = request_cover
        self.register_mousewheel = register_mousewheel
        self.on_continue = on_continue
        self.on_toggle_progress = on_toggle_progress
        self.on_open_link = on_open_link
        self.on_copy_link = on_copy_link
        self.on_edit = on_edit
        self.on_delete = on_delete
        self.default_bg = "#10182f"
        self.hover_bg = "#142243"
        self.selected_bg = "#15244a"
        self.has_link = bool(row_value(book, "reading_link"))
        self.book_type = row_value(book, "book_type") or TYPE_BOOK
        self.show_progress = show_progress

        self.badge_bg, self.badge_fg = status_badge_colors(book["status"])

        current_page, total_pages, percent = progress_numbers(
            row_value(book, "last_page", "current_chapter"),
            row_value(book, "total_pages"),
        )
        self.progress_percent = percent
        self.current_page = current_page
        self.total_pages = total_pages
        self.cover_image_ref = None
        self.cover_source = row_value(book, "cover_path")
        self.surface_widgets = []
        self.hovered = False

        if current_page != "-":
            self.hidden_progress_caption = f"Ultimo visto: pagina {current_page}"
        else:
            self.hidden_progress_caption = "Ultimo visto ainda nao informado"
        self.visible_progress_caption = f"Pagina {current_page}"
        if total_pages:
            self.visible_progress_caption += f" de {total_pages}"
        elif current_page == "-":
            self.visible_progress_caption = "Progresso ainda nao informado"

        self.shell = tk.Frame(self, bg=self.default_bg, highlightthickness=1, highlightbackground=BORDER)
        self.shell.pack(fill="both", expand=True, padx=6, pady=8)

        self.cover_wrap = tk.Frame(self.shell, bg=self.default_bg, padx=14, pady=14)
        self.cover_wrap.pack(fill="x")
        self._register_surface(self.cover_wrap)
        self.cover_frame = tk.Frame(
            self.cover_wrap,
            bg=INPUT_BG,
            highlightthickness=1,
            highlightbackground=CHIP_BORDER,
            padx=8,
            pady=8,
        )
        self.cover_frame.pack(fill="x")
        self.cover_box = tk.Frame(
            self.cover_frame,
            bg=INPUT_BG,
            width=248,
            height=220,
            highlightthickness=0,
        )
        self.cover_box.pack()
        self.cover_box.pack_propagate(False)
        self._show_cover_placeholder()

        info = tk.Frame(self.shell, bg=self.default_bg, padx=16, pady=16)
        info.pack(fill="both", expand=True)
        self._register_surface(info)

        top = tk.Frame(info, bg=self.default_bg)
        top.pack(fill="x")
        self._register_surface(top)

        self.title_label = tk.Label(
            top,
            text=book["title"],
            bg=self.default_bg,
            fg="white",
            font=("Segoe UI", 16, "bold"),
            anchor="w",
            wraplength=252,
            justify="left",
        )
        self.title_label.pack(side="left", fill="x", expand=True, pady=(0, 6))
        self._register_surface(self.title_label)

        self.badge = tk.Label(
            top,
            text=book["status"],
            bg=self.badge_bg,
            fg=self.badge_fg,
            font=("Segoe UI", 9, "bold"),
            padx=11,
            pady=5,
            highlightthickness=1,
            highlightbackground=self.accent_color,
        )
        self.badge.pack(side="right", padx=(10, 0), anchor="n")

        self.author_label = tk.Label(
            info,
            text=book["author"] or "Autor nao informado",
            bg=self.default_bg,
            fg=SOFT_TEXT,
            font=("Segoe UI", 10),
            anchor="w",
        )
        self.author_label.pack(anchor="w", pady=(0, 10))
        self._register_surface(self.author_label)

        chips_row = tk.Frame(info, bg=self.default_bg)
        chips_row.pack(fill="x", pady=(0, 12))
        self._register_surface(chips_row)

        self.type_chip = tk.Label(
            chips_row,
            text=self.book_type,
            bg=CHIP_BG,
            fg=(PURPLE if self.book_type == TYPE_LIGHT_NOVEL else CYAN),
            font=("Segoe UI", 8, "bold"),
            padx=8,
            pady=4,
            highlightthickness=1,
            highlightbackground=button_border_color(PURPLE if self.book_type == TYPE_LIGHT_NOVEL else CYAN),
        )
        self.type_chip.pack(side="left")

        self.category_chip = tk.Label(
            chips_row,
            text=row_value(book, "category") or "Sem categoria",
            bg=CHIP_BG,
            fg=SOFT_TEXT,
            font=("Segoe UI", 8, "bold"),
            padx=9,
            pady=4,
            highlightthickness=1,
            highlightbackground=CHIP_BORDER,
        )
        self.category_chip.pack(side="left", padx=(8, 0))

        self.meta = tk.Label(
            info,
            text=self.hidden_progress_caption,
            bg=self.default_bg,
            fg="white",
            font=("Segoe UI", 12, "bold"),
            anchor="w",
            justify="left",
            wraplength=252,
        )
        self.meta.pack(fill="x", pady=(0, 7))
        self._register_surface(self.meta)

        self.progress_card = tk.Frame(info, bg=self.default_bg, highlightthickness=0, padx=0, pady=0)
        self._register_surface(self.progress_card)

        progress_wrap = tk.Frame(self.progress_card, bg=self.default_bg)
        progress_wrap.pack(fill="x")
        self._register_surface(progress_wrap)
        self.progress_track = tk.Frame(progress_wrap, bg=INPUT_BG, height=8, highlightthickness=1, highlightbackground=BORDER)
        self.progress_track.pack(side="left", fill="x", expand=True, pady=(0, 8))
        self.progress_fill = tk.Frame(self.progress_track, bg=self.accent_color, height=8)
        self.progress_fill.place(relx=0, rely=0, relheight=1, relwidth=0)

        self.progress_text = tk.Label(
            progress_wrap,
            text=(f"{percent}%" if percent is not None else "Sem total"),
            bg=self.default_bg,
            fg=SOFT_TEXT,
            font=("Segoe UI", 8, "bold"),
            anchor="e",
            width=9,
        )
        self.progress_text.pack(side="left", padx=(10, 0))

        stats_row = tk.Frame(self.progress_card, bg=self.default_bg)
        stats_row.pack(fill="x")
        self._register_surface(stats_row)
        self.progress_hint = tk.Label(
            stats_row,
            text=("Leitura em andamento" if percent not in (None, 100) else ("Leitura concluida" if percent == 100 else "Sem total definido")),
            bg=self.default_bg,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.progress_hint.pack(side="left")
        self.pages_label = tk.Label(
            stats_row,
            text=f"{current_page or '-'} / {total_pages or '?'}",
            bg=self.default_bg,
            fg=SOFT_TEXT,
            font=("Segoe UI", 8, "bold"),
            anchor="e",
        )
        self.pages_label.pack(side="right")

        self.hidden_hint = tk.Label(
            info,
            text="Revele o progresso apenas quando quiser ver paginas e percentual.",
            bg=self.default_bg,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=240,
        )
        self._register_surface(self.hidden_hint)

        footer = tk.Frame(info, bg=self.default_bg)
        footer.pack(fill="x", pady=(4, 10))
        self._register_surface(footer)
        self.updated = tk.Label(
            footer,
            text=f"Atualizado: {format_display_datetime(row_value(book, 'updated_at'))}",
            bg=self.default_bg,
            fg=MUTED,
            font=("Segoe UI", 8),
            anchor="w",
        )
        self.updated.pack(anchor="w")
        self._register_surface(self.updated)

        self.note_line = tk.Label(
            footer,
            text=f"Observacao: {truncate_text(row_value(book, 'notes'), 44)}",
            bg=self.default_bg,
            fg=SOFT_TEXT,
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=252,
        )
        self.note_line.pack(anchor="w", pady=(3, 0))
        self._register_surface(self.note_line)

        self.link_line = tk.Label(
            footer,
            text=f"Link salvo: {truncate_text(row_value(book, 'reading_link'), 44)}",
            bg=self.default_bg,
            fg=SOFT_TEXT,
            font=("Segoe UI", 8),
            anchor="w",
            justify="left",
            wraplength=252,
        )
        self.link_line.pack(anchor="w", pady=(2, 0))
        self._register_surface(self.link_line)

        actions = tk.Frame(info, bg=self.default_bg)
        actions.pack(fill="x")
        self._register_surface(actions)

        quick_label = "Continuar leitura" if self.has_link else "Sem link salvo"
        self.quick_hint = tk.Label(
            actions,
            text=quick_label,
            bg=(GREEN if self.has_link else CHIP_BG),
            fg=("white" if self.has_link else MUTED),
            font=("Segoe UI", 9, "bold"),
            anchor="center",
            padx=14,
            pady=8,
            cursor="hand2" if row_value(book, "reading_link") else "arrow",
            highlightthickness=1,
            highlightbackground=(button_border_color(GREEN) if self.has_link else CHIP_BORDER),
        )
        self.quick_hint.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.progress_toggle = tk.Label(
            actions,
            text="Progresso",
            bg=CHIP_BG,
            fg=SOFT_TEXT,
            font=("Segoe UI", 9, "bold"),
            anchor="center",
            padx=14,
            pady=8,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=CHIP_BORDER,
        )
        self.progress_toggle.pack(side="left", fill="x", expand=True, padx=(6, 0))

        utility_actions = tk.Frame(info, bg=self.default_bg)
        utility_actions.pack(fill="x", pady=(10, 0))
        self._register_surface(utility_actions)

        self.open_link_card = tk.Label(
            utility_actions,
            text="Abrir Link",
            bg=(CYAN if self.has_link else SURFACE_ALT),
            fg=("white" if self.has_link else MUTED),
            font=("Segoe UI", 9, "bold"),
            anchor="center",
            padx=12,
            pady=8,
            cursor="hand2" if self.has_link else "arrow",
            highlightthickness=1,
            highlightbackground=(button_border_color(CYAN) if self.has_link else BORDER),
        )
        self.open_link_card.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.copy_link_card = tk.Label(
            utility_actions,
            text="Copiar Link",
            bg=(PURPLE if self.has_link else SURFACE_ALT),
            fg=("white" if self.has_link else MUTED),
            font=("Segoe UI", 9, "bold"),
            anchor="center",
            padx=12,
            pady=8,
            cursor="hand2" if self.has_link else "arrow",
            highlightthickness=1,
            highlightbackground=(button_border_color(PURPLE) if self.has_link else BORDER),
        )
        self.copy_link_card.pack(side="left", fill="x", expand=True, padx=(6, 0))

        manage_actions = tk.Frame(info, bg=self.default_bg)
        manage_actions.pack(fill="x", pady=(10, 0))
        self._register_surface(manage_actions)

        self.edit_card = tk.Label(
            manage_actions,
            text="Editar",
            bg=BLUE,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            anchor="center",
            padx=12,
            pady=8,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=button_border_color(BLUE),
        )
        self.edit_card.pack(side="left", fill="x", expand=True, padx=(0, 6))

        self.delete_card = tk.Label(
            manage_actions,
            text="Excluir",
            bg=RED,
            fg="white",
            font=("Segoe UI", 9, "bold"),
            anchor="center",
            padx=12,
            pady=8,
            cursor="hand2",
            highlightthickness=1,
            highlightbackground=button_border_color(RED),
        )
        self.delete_card.pack(side="left", fill="x", expand=True, padx=(6, 0))

        self._set_progress_fill(self.progress_percent)
        self.set_selected(selected)
        self._bind_recursive(self)
        self._bind_hover_recursive(self)
        self.progress_toggle.bind("<Button-1>", self._handle_toggle_progress)
        if self.has_link and self.on_continue:
            self.quick_hint.bind("<Button-1>", self._handle_continue)
        if self.has_link and self.on_open_link:
            self.open_link_card.bind("<Button-1>", self._handle_open_link)
        if self.has_link and self.on_copy_link:
            self.copy_link_card.bind("<Button-1>", self._handle_copy_link)
        if self.on_edit:
            self.edit_card.bind("<Button-1>", self._handle_edit)
        if self.on_delete:
            self.delete_card.bind("<Button-1>", self._handle_delete)
        if self.request_cover and self.cover_source:
            self.request_cover(self, self.cover_source)
        self.set_progress_visible(self.show_progress)

    def _show_cover_placeholder(self):
        for child in self.cover_box.winfo_children():
            child.destroy()
        placeholder = tk.Frame(self.cover_box, bg=INPUT_BG)
        placeholder.pack(fill="both", expand=True)
        tk.Label(
            placeholder,
            text=("LN" if self.book_type == TYPE_LIGHT_NOVEL else (self.book["title"][:1] or "?").upper()),
            bg=INPUT_BG,
            fg=self.accent_color,
            font=("Segoe UI", 30, "bold"),
        ).pack(expand=True)
        tk.Label(
            placeholder,
            text="Sem capa",
            bg=INPUT_BG,
            fg=MUTED,
            font=("Segoe UI", 7, "bold"),
        ).pack(pady=(0, 6))

    def set_cover_image(self, photo):
        if not self.winfo_exists():
            return
        self.cover_image_ref = photo
        for child in self.cover_box.winfo_children():
            child.destroy()
        label = tk.Label(self.cover_box, image=self.cover_image_ref, bg=INPUT_BG)
        label.pack(fill="both", expand=True)
        self._bind_recursive(label)
        self._bind_hover_recursive(label)
        if self.register_mousewheel:
            self.register_mousewheel(label)

    def _set_progress_fill(self, percent):
        if not self.progress_fill or not self.progress_track:
            return
        relwidth = 0
        if percent is not None:
            relwidth = max(0.04, min(1, percent / 100))
        self.progress_fill.place(relx=0, rely=0, relheight=1, relwidth=relwidth)

    def _register_surface(self, widget):
        self.surface_widgets.append(widget)

    def _apply_surface_bg(self, color):
        for widget in self.surface_widgets:
            if widget.winfo_exists():
                try:
                    widget.configure(bg=color)
                except Exception:
                    pass
        self.quick_hint.configure(
            bg=(GREEN if self.has_link else CHIP_BG),
            fg=("white" if self.has_link else MUTED),
            highlightbackground=(button_border_color(GREEN) if self.has_link else CHIP_BORDER),
        )
        if self.progress_text and self.progress_text.winfo_exists():
            self.progress_text.configure(bg=color)
        if self.progress_hint and self.progress_hint.winfo_exists():
            self.progress_hint.configure(bg=color)
        if self.pages_label and self.pages_label.winfo_exists():
            self.pages_label.configure(bg=color)

    def _set_hover(self, active):
        self.hovered = active
        self._apply_card_state()

    def set_selected(self, selected):
        self.selected = selected
        self._apply_card_state()

    def _handle_continue(self, _event=None):
        if self.on_continue:
            self.on_continue(self.book["id"])
            return "break"

    def _handle_open_link(self, _event=None):
        if self.on_open_link:
            self.on_open_link(self.book["id"])
            return "break"

    def _handle_copy_link(self, _event=None):
        if self.on_copy_link:
            self.on_copy_link(self.book["id"])
            return "break"

    def _handle_edit(self, _event=None):
        if self.on_edit:
            self.on_edit(self.book["id"])
            return "break"

    def _handle_delete(self, _event=None):
        if self.on_delete:
            self.on_delete(self.book["id"])
            return "break"

    def _apply_card_state(self):
        if self.selected:
            outer_bg = "#2ce0ff"
            shell_bg = self.selected_bg
            shell_border = CYAN
            cover_bg = "#111a33"
            cover_border = CYAN
        elif self.hovered:
            outer_bg = "#13203d"
            shell_bg = self.hover_bg
            shell_border = BORDER_GLOW
            cover_bg = "#0f1830"
            cover_border = BORDER_GLOW
        else:
            outer_bg = BG
            shell_bg = self.default_bg
            shell_border = BORDER
            cover_bg = INPUT_BG
            cover_border = CHIP_BORDER

        self.configure(bg=outer_bg)
        self.shell.configure(bg=shell_bg, highlightbackground=shell_border)
        self.cover_wrap.configure(bg=shell_bg)
        self._apply_surface_bg(shell_bg)
        self.cover_frame.configure(bg=cover_bg, highlightbackground=cover_border)
        self.badge.configure(bg=self.badge_bg, fg=self.badge_fg)
        self._set_progress_fill(self.progress_percent)
        self._refresh_progress_toggle_style()

    def _refresh_progress_toggle_style(self):
        active_bg = BLUE if self.show_progress else CHIP_BG
        active_fg = "white" if self.show_progress else SOFT_TEXT
        active_border = button_border_color(BLUE) if self.show_progress else CHIP_BORDER
        self.progress_toggle.configure(
            bg=active_bg,
            fg=active_fg,
            highlightbackground=active_border,
        )

    def set_progress_visible(self, visible):
        self.show_progress = bool(visible)
        self.meta.configure(text=(self.visible_progress_caption if self.show_progress else self.hidden_progress_caption))

        if self.show_progress:
            if self.hidden_hint.winfo_manager():
                self.hidden_hint.pack_forget()
            if not self.progress_card.winfo_manager():
                self.progress_card.pack(fill="x", pady=(0, 10))
            self._set_progress_fill(self.progress_percent)
        else:
            if self.progress_card.winfo_manager():
                self.progress_card.pack_forget()
            if not self.hidden_hint.winfo_manager():
                self.hidden_hint.pack(fill="x", pady=(0, 10))

        self._refresh_progress_toggle_style()

    def _handle_toggle_progress(self, _event=None):
        if self.on_toggle_progress:
            self.on_toggle_progress(self.book["id"])
            return "break"


class ScrollableCards(_ScrollableCardsBase):
    def __init__(self, master, bg):
        super().__init__(master, bg)
        self.register_mousewheel(self.canvas)
        self.register_mousewheel(self.inner)
        self.register_mousewheel(self.scrollbar)

    def register_mousewheel(self, widget):
        widget.bind("<MouseWheel>", self._on_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_mousewheel_linux, add="+")
        widget.bind("<Button-5>", self._on_mousewheel_linux, add="+")
        for child in widget.winfo_children():
            self.register_mousewheel(child)

    def _on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _on_mousewheel_linux(self, event):
        if event.num == 4:
            self.canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            self.canvas.yview_scroll(1, "units")

    def scroll_to_top(self):
        self.canvas.yview_moveto(0)

class App(_AppExtended):
    def __init__(self):
        self.detail_window = None
        self.page_area = None
        self.nebula_background_label = None
        self.nebula_background_photo = None
        self.nebula_background_base = None
        self._nebula_refresh_job = None
        self._clear_detail_widget_refs()
        super().__init__()
        self.sort_var = tk.StringVar(value="recent")
        self.library_var = tk.StringVar(value=TYPE_BOOK)
        self.book_cards = {}
        self.books_by_id = {}
        self.revealed_progress_books = set()
        self.cover_raw_cache = {}
        self.cover_photo_cache = {}
        self.cover_requests = {}
        self.cover_failed_sources = set()
        self.last_query_signature = None
        self.detail_cover_hint_var = tk.StringVar(value="Selecione um livro para ver a capa.")
        self.nebula_background_path = Path(__file__).resolve().parent / "assets" / "nebula_bg.ppm"

    def current_library_type(self):
        return TYPE_LIGHT_NOVEL if self.library_var.get() == TYPE_LIGHT_NOVEL else TYPE_BOOK

    def library_section_title(self):
        return "Suas Light Novels" if self.current_library_type() == TYPE_LIGHT_NOVEL else "Seus livros"

    def library_item_singular(self):
        return TYPE_LIGHT_NOVEL if self.current_library_type() == TYPE_LIGHT_NOVEL else TYPE_BOOK

    def library_item_plural_lower(self):
        return "light novels" if self.current_library_type() == TYPE_LIGHT_NOVEL else "livros"

    def handle_library_change(self):
        self.selected_book_id = None
        self.last_query_signature = None
        self.close_detail_window()
        self.show_main()

    def show_login(self):
        self.close_detail_window()
        super().show_login()

    def summary_card(self, master, title, variable, accent):
        frame = tk.Frame(master, bg=BG)
        frame.pack(side="left", fill="x", expand=True, padx=8, pady=2)
        shell = tk.Frame(frame, bg="#0f172a", highlightthickness=1, highlightbackground="#223250")
        shell.pack(fill="both", expand=True)
        content = tk.Frame(shell, bg="#0f172a", padx=18, pady=18)
        content.pack(fill="both", expand=True)
        header = tk.Frame(content, bg="#0f172a")
        header.pack(fill="x")
        tk.Label(header, text=title, bg="#0f172a", fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(content, textvariable=variable, bg="#0f172a", fg="white", font=("Segoe UI", 28, "bold")).pack(anchor="w", pady=(12, 0))
        return frame

    def attach_nebula_background(self, host):
        if not host or not host.winfo_exists():
            return
        self.nebula_background_label = tk.Label(host, bg=BG, bd=0, highlightthickness=0, anchor="nw")
        self.nebula_background_label.place(relx=0, rely=0, relwidth=1, relheight=1)
        self.nebula_background_label.lower()
        if not self.nebula_background_path.exists():
            return
        try:
            if PIL_AVAILABLE:
                if self.nebula_background_base is None:
                    self.nebula_background_base = Image.open(self.nebula_background_path).convert("RGB")
                self.refresh_nebula_background()
                host.bind("<Configure>", self.schedule_nebula_background_refresh, add="+")
            else:
                if self.nebula_background_photo is None:
                    self.nebula_background_photo = tk.PhotoImage(file=str(self.nebula_background_path))
                self.nebula_background_label.configure(image=self.nebula_background_photo)
        except Exception:
            self.nebula_background_label.configure(image="", bg=BG)

    def schedule_nebula_background_refresh(self, _event=None):
        if self._nebula_refresh_job:
            try:
                self.after_cancel(self._nebula_refresh_job)
            except Exception:
                pass
        self._nebula_refresh_job = self.after(60, self.refresh_nebula_background)

    def refresh_nebula_background(self):
        self._nebula_refresh_job = None
        if not PIL_AVAILABLE or self.nebula_background_base is None:
            return
        if not self.nebula_background_label or not self.nebula_background_label.winfo_exists():
            return
        width = max(1, self.nebula_background_label.winfo_width())
        height = max(1, self.nebula_background_label.winfo_height())
        source = self.nebula_background_base
        scale = max(width / source.width, height / source.height)
        resized_size = (
            max(1, int(source.width * scale)),
            max(1, int(source.height * scale)),
        )
        resized = source.resize(resized_size, Image.LANCZOS)
        left = max(0, (resized.width - width) // 2)
        top = max(0, (resized.height - height) // 2)
        cropped = resized.crop((left, top, left + width, top + height))
        self.nebula_background_photo = ImageTk.PhotoImage(cropped)
        self.nebula_background_label.configure(image=self.nebula_background_photo)

    def _clear_detail_widget_refs(self):
        self.detail_area = None
        self.detail_cover = None
        self.detail_cover_ref = None
        self.details_text = None
        self.detail_title_var = None
        self.detail_meta_var = None
        self.detail_author_var = None
        self.detail_progress_var = None
        self.detail_type_badge = None
        self.detail_category_badge = None
        self.detail_status_badge = None
        self.detail_progress_summary_var = None
        self.detail_progress_summary_label = None
        self.detail_progress_card = None
        self.detail_progress_track = None
        self.detail_progress_fill = None
        self.detail_progress_toggle_button = None
        self.detail_continue_button = None
        self.detail_edit_button = None
        self.detail_link_button = None
        self.detail_cover_button = None
        self.detail_copy_button = None
        self.detail_delete_button = None
        self.detail_progress_visible = False

    def close_detail_window(self):
        window = getattr(self, "detail_window", None)
        if window and window.winfo_exists():
            self.detail_window.destroy()
        self.detail_window = None
        self._clear_detail_widget_refs()

    def _handle_detail_window_close(self):
        self.close_detail_window()

    def ensure_detail_window(self):
        if self.detail_window and self.detail_window.winfo_exists():
            self.detail_window.deiconify()
            self.detail_window.lift()
            return self.detail_window

        self.detail_window = tk.Toplevel(self)
        self.detail_window.title("Detalhes da obra")
        self.detail_window.geometry("720x820")
        self.detail_window.minsize(640, 720)
        self.detail_window.configure(bg=BG)
        self.detail_window.transient(self)
        self.detail_window.protocol("WM_DELETE_WINDOW", self._handle_detail_window_close)

        shell = tk.Frame(self.detail_window, bg=DETAIL_PANEL, highlightthickness=1, highlightbackground=BORDER_GLOW)
        shell.place(x=16, y=16, relwidth=1, relheight=1, width=-32, height=-32)
        tk.Frame(shell, bg=PURPLE, height=2).pack(fill="x")

        self.detail_area = ScrollableCards(shell, DETAIL_PANEL)
        self.detail_area.pack(fill="both", expand=True)
        self.style_scrollbar(self.detail_area.scrollbar)
        self.detail_area.canvas.configure(yscrollincrement=18)

        detail = tk.Frame(self.detail_area.inner, bg=DETAIL_PANEL, padx=22, pady=22)
        detail.pack(fill="both", expand=True)

        def compact_button(master, text, bg_color, hover_color, command, font_size=9):
            btn = SoftButton(master, text, bg_color, hover_color, command)
            btn.enabled_bg = bg_color
            btn.enabled_hover = hover_color
            btn.enabled_border = button_border_color(bg_color)
            btn.configure(
                font=("Segoe UI", font_size, "bold"),
                padx=14,
                pady=9,
                highlightbackground=btn.enabled_border,
                highlightcolor=btn.enabled_border,
            )
            return btn

        tk.Label(detail, text="Detalhes", bg=DETAIL_PANEL, fg="white", font=("Segoe UI", 22, "bold")).pack(anchor="w", pady=(0, 10))
        tk.Label(detail, text="Foco total em uma obra, com capa, progresso, notas e acoes rapidas.", bg=DETAIL_PANEL, fg=SOFT_TEXT, font=("Segoe UI", 9)).pack(anchor="w", pady=(0, 16))

        detail_hero = tk.Frame(detail, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER, padx=20, pady=20)
        detail_hero.pack(fill="x", pady=(0, 14))

        cover_panel = tk.Frame(detail_hero, bg=SURFACE_ALT, highlightthickness=0)
        cover_panel.pack(side="left", anchor="n")
        cover_shell = tk.Frame(cover_panel, bg=SURFACE_GLOW, highlightthickness=1, highlightbackground=BORDER_GLOW, padx=12, pady=12)
        cover_shell.pack(anchor="center")
        self.detail_cover = CoverPreview(cover_shell, width=210, height=300)
        self.detail_cover.pack(anchor="center")
        tk.Label(
            cover_panel,
            textvariable=self.detail_cover_hint_var,
            bg=SURFACE_ALT,
            fg=MUTED,
            justify="center",
            wraplength=210,
            font=("Segoe UI", 8),
        ).pack(anchor="center", pady=(10, 0))

        info_panel = tk.Frame(detail_hero, bg=SURFACE_ALT)
        info_panel.pack(side="left", fill="both", expand=True, padx=(20, 0))

        self.detail_title_var = tk.StringVar(value="Selecione um livro")
        self.detail_meta_var = tk.StringVar(value="")
        self.detail_author_var = tk.StringVar(value="Escolha um card para abrir os detalhes da obra.")
        self.detail_progress_var = tk.StringVar(value="Progresso: -")
        self.detail_progress_summary_var = tk.StringVar(value="Ultimo visto ainda nao informado")
        header_block = tk.Frame(info_panel, bg=SURFACE_ALT)
        header_block.pack(fill="x", pady=(0, 12))
        tk.Label(header_block, textvariable=self.detail_title_var, bg=SURFACE_ALT, fg="white", font=("Segoe UI", 25, "bold"), wraplength=360, justify="left").pack(anchor="w")
        tk.Label(header_block, textvariable=self.detail_author_var, bg=SURFACE_ALT, fg=SOFT_TEXT, font=("Segoe UI", 11), wraplength=360, justify="left").pack(anchor="w", pady=(8, 4))
        tk.Label(header_block, textvariable=self.detail_meta_var, bg=SURFACE_ALT, fg=MUTED, font=("Segoe UI", 8), wraplength=360, justify="left").pack(anchor="w", pady=(0, 12))

        meta_row = tk.Frame(header_block, bg=SURFACE_ALT)
        meta_row.pack(fill="x")
        self.detail_type_badge = tk.Label(meta_row, text="", bg=CHIP_BG, fg=PURPLE, font=("Segoe UI", 8, "bold"), padx=10, pady=5, highlightthickness=1, highlightbackground=button_border_color(PURPLE))
        self.detail_type_badge.pack(side="left")
        self.detail_category_badge = tk.Label(meta_row, text="", bg=CHIP_BG, fg=SOFT_TEXT, font=("Segoe UI", 8, "bold"), padx=10, pady=5, highlightthickness=1, highlightbackground=CHIP_BORDER)
        self.detail_category_badge.pack(side="left", padx=(8, 0))
        self.detail_status_badge = tk.Label(meta_row, text="", bg=CARD, fg=MUTED, font=("Segoe UI", 8, "bold"), padx=11, pady=5, highlightthickness=1, highlightbackground=BORDER)
        self.detail_status_badge.pack(side="right")

        self.detail_progress_summary_label = tk.Label(
            info_panel,
            textvariable=self.detail_progress_summary_var,
            bg=SURFACE_ALT,
            fg=SOFT_TEXT,
            font=("Segoe UI", 11, "bold"),
            anchor="w",
        )
        self.detail_progress_summary_label.pack(fill="x", pady=(14, 8))

        self.detail_progress_card = tk.Frame(info_panel, bg=INPUT_BG, highlightthickness=1, highlightbackground=BORDER_GLOW, padx=16, pady=14)
        tk.Label(self.detail_progress_card, text="Leitura atual", bg=INPUT_BG, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(0, 6))
        tk.Label(self.detail_progress_card, textvariable=self.detail_progress_var, bg=INPUT_BG, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 8))
        self.detail_progress_track = tk.Frame(self.detail_progress_card, bg=BG, height=11, highlightthickness=1, highlightbackground=CHIP_BORDER)
        self.detail_progress_track.pack(fill="x")
        self.detail_progress_fill = tk.Frame(self.detail_progress_track, bg=CYAN, height=11)
        self.detail_progress_fill.place(relx=0, rely=0, relheight=1, relwidth=0)

        action_grid = tk.Frame(info_panel, bg=SURFACE_ALT)
        action_grid.pack(fill="x")
        action_grid.grid_columnconfigure(0, weight=1, uniform="detail-actions")
        action_grid.grid_columnconfigure(1, weight=1, uniform="detail-actions")

        self.detail_continue_button = compact_button(action_grid, "Continuar leitura", GREEN, GREEN_HOVER, self.continue_reading, font_size=10)
        self.detail_continue_button.grid(row=0, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))
        self.detail_progress_toggle_button = compact_button(action_grid, "Progresso", BLUE, BLUE_HOVER, self.toggle_detail_progress, font_size=9)
        self.detail_progress_toggle_button.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        self.detail_edit_button = compact_button(action_grid, "Editar", BLUE, BLUE_HOVER, self.edit_book, font_size=9)
        self.detail_edit_button.grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))
        self.detail_link_button = compact_button(action_grid, "Abrir link", CYAN, CYAN_HOVER, self.open_link, font_size=9)
        self.detail_link_button.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        self.detail_cover_button = compact_button(action_grid, "Abrir capa", SURFACE_GLOW, CARD_HOVER, self.open_cover, font_size=8)
        self.detail_cover_button.grid(row=2, column=0, sticky="ew", padx=(0, 6), pady=(0, 8))
        self.detail_copy_button = compact_button(action_grid, "Copiar link", SURFACE_GLOW, CARD_HOVER, self.copy_link, font_size=8)
        self.detail_copy_button.grid(row=2, column=1, sticky="ew", padx=(6, 0), pady=(0, 8))

        self.detail_delete_button = compact_button(action_grid, "Excluir obra", RED, RED_HOVER, self.delete_book, font_size=8)
        self.detail_delete_button.grid(row=3, column=0, columnspan=2, sticky="ew")

        notes_wrap = tk.Frame(detail, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER, padx=16, pady=16)
        notes_wrap.pack(fill="both", expand=True)
        tk.Label(notes_wrap, text="Link salvo e observacoes", bg=SURFACE_ALT, fg=TEXT, font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(0, 10))
        self.details_text = tk.Text(notes_wrap, wrap="word", bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat", highlightthickness=1, highlightbackground=CHIP_BORDER, highlightcolor=CYAN, bd=0, font=("Segoe UI", 10), height=8, padx=14, pady=12, selectbackground=BLUE_HOVER, selectforeground="white")
        self.details_text.pack(fill="both", expand=True)
        self.details_text.configure(state="disabled")

        self.detail_area.register_mousewheel(detail)
        return self.detail_window

    def show_main(self):
        self.clear_window()
        self.book_cards = {}
        self.books_by_id = {}

        self.page_area = ScrollableCards(self, BG)
        self.page_area.pack(fill="both", expand=True)
        self.style_scrollbar(self.page_area.scrollbar)
        self.page_area.canvas.configure(yscrollincrement=18)

        outer = tk.Frame(self.page_area.inner, bg=BG, padx=26, pady=26)
        outer.pack(fill="both", expand=True)
        self.attach_nebula_background(outer)

        hero = tk.Frame(outer, bg=BG)
        hero.pack(fill="x", pady=(0, 18))

        hero_top = tk.Frame(hero, bg=BG)
        hero_top.pack(fill="x")

        left_hero = tk.Frame(hero_top, bg=BG)
        left_hero.pack(side="left", fill="x", expand=True)
        tk.Label(left_hero, text="Biblioteca Virtual Aberta", bg=BG, fg="white", font=("Segoe UI", 34, "bold")).pack(anchor="w")
        tk.Label(
            left_hero,
            text=f"Bem-vindo, {self.current_user['name']}. Sua estante premium para acompanhar {self.library_item_plural_lower()}, links e progresso de leitura.",
            bg=BG,
            fg=SOFT_TEXT,
            font=("Segoe UI", 12),
        ).pack(anchor="w", pady=(6, 14))

        collection_row = tk.Frame(left_hero, bg=BG)
        collection_row.pack(anchor="w")
        tk.Label(collection_row, text="Colecao", bg=BG, fg=MUTED, font=("Segoe UI", 10, "bold")).pack(side="left", padx=(0, 12))
        self.library_tabs = SegmentedButtonGroup(
            collection_row,
            self.library_var,
            [(TYPE_BOOK, "Livros"), (TYPE_LIGHT_NOVEL, "Light Novels")],
            self.handle_library_change,
        )
        self.library_tabs.pack(side="left")

        right_hero = tk.Frame(hero_top, bg=BG)
        right_hero.pack(side="right")
        SoftButton(right_hero, f"+ Adicionar {self.library_item_singular()}", GREEN, GREEN_HOVER, self.add_book).pack(side="left", padx=(0, 8))
        SoftButton(right_hero, "Sair", RED, RED_HOVER, self.show_login).pack(side="left")

        summary = tk.Frame(outer, bg=BG)
        summary.pack(fill="x", pady=(0, 18))
        self.summary_card(summary, f"Total de {self.library_item_plural_lower()}", self.summary_vars["total"], CYAN)
        self.summary_card(summary, STATUS_READING, self.summary_vars["lendo"], BLUE)
        self.summary_card(summary, STATUS_WANT, self.summary_vars["quero_ler"], PURPLE)
        self.summary_card(summary, "Concluidos", self.summary_vars["concluidos"], GREEN)

        filter_content = tk.Frame(outer, bg=BG)
        filter_content.pack(fill="x", pady=(0, 18))

        search_wrap = tk.Frame(filter_content, bg=BG)
        search_wrap.pack(side="left", fill="x", expand=True, padx=(0, 18))
        tk.Label(search_wrap, text="Buscar", bg=BG, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 7))
        search_shell = tk.Frame(search_wrap, bg=INPUT_BG, highlightthickness=1, highlightbackground=CHIP_BORDER, highlightcolor=CYAN, padx=12, pady=2)
        search_shell.pack(fill="x")
        self.search_entry = tk.Entry(search_shell, textvariable=self.search_var, bg=INPUT_BG, fg=TEXT, insertbackground=TEXT, relief="flat", highlightthickness=0, bd=0, font=("Segoe UI", 10))
        self.search_entry.pack(fill="x", ipady=10)
        self.search_entry.bind("<KeyRelease>", lambda _event: self.refresh_books())

        controls_wrap = tk.Frame(filter_content, bg=BG)
        controls_wrap.pack(side="left", anchor="n")

        chips_wrap = tk.Frame(controls_wrap, bg=BG)
        chips_wrap.pack(anchor="w")
        tk.Label(chips_wrap, text="Filtrar por status", bg=BG, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 6))
        self.chips = SegmentedButtonGroup(
            chips_wrap,
            self.status_filter_var,
            [("", "Todos"), (STATUS_WANT, "Quero Ler"), (STATUS_READING, "Lendo"), (STATUS_DONE, "Concluidos")],
            self.refresh_books
        )
        self.chips.pack(anchor="w")

        sort_wrap = tk.Frame(controls_wrap, bg=BG)
        sort_wrap.pack(anchor="w", pady=(8, 0))
        tk.Label(sort_wrap, text="Ordenar por", bg=BG, fg=SOFT_TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w", pady=(0, 5))
        self.sort_chips = SegmentedButtonGroup(
            sort_wrap,
            self.sort_var,
            [("recent", "Recentes"), ("progress", "Progresso"), ("title", "A-Z")],
            self.refresh_books,
        )
        self.sort_chips.pack(anchor="w")

        collection_header = tk.Frame(outer, bg=BG)
        collection_header.pack(fill="x", pady=(2, 8))
        tk.Label(collection_header, text=self.library_section_title(), bg=BG, fg="white", font=("Segoe UI", 21, "bold")).pack(anchor="w")
        tk.Label(
            collection_header,
            text=f"Colecao ampla com cards visuais. Clique em uma obra para abrir a janela de detalhes.",
            bg=BG,
            fg=SOFT_TEXT,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

        list_wrap = tk.Frame(outer, bg=BG)
        list_wrap.pack(fill="both", expand=True, pady=(4, 0))

        self.cards_area = ScrollableCards(list_wrap, BG)
        self.cards_area.pack(fill="both", expand=True)
        self.style_scrollbar(self.cards_area.scrollbar)

        self.register_main_page_scroll(outer)
        self.page_area.scroll_to_top()
        self.refresh_books()

    def set_detail_progress(self, percent, accent=CYAN):
        if not self.detail_progress_fill or not self.detail_progress_fill.winfo_exists():
            return
        relwidth = 0
        if percent is not None:
            relwidth = max(0.04, min(1, percent / 100))
        self.detail_progress_fill.configure(bg=accent)
        self.detail_progress_fill.place(relx=0, rely=0, relheight=1, relwidth=relwidth)

    def _refresh_detail_progress_toggle_style(self):
        if not self.detail_progress_toggle_button or not self.detail_progress_toggle_button.winfo_exists():
            return
        if self.detail_progress_visible:
            self.detail_progress_toggle_button.enabled_bg = BLUE
            self.detail_progress_toggle_button.enabled_hover = BLUE_HOVER
            self.detail_progress_toggle_button.enabled_border = button_border_color(BLUE)
        else:
            self.detail_progress_toggle_button.enabled_bg = INPUT_BG
            self.detail_progress_toggle_button.enabled_hover = CARD_HOVER
            self.detail_progress_toggle_button.enabled_border = BORDER

        self.set_action_button_state(
            self.detail_progress_toggle_button,
            bool(self.current_book()) if self.detail_window and self.detail_window.winfo_exists() else False,
        )

    def set_detail_progress_visible(self, visible):
        self.detail_progress_visible = bool(visible)
        if self.detail_progress_card and self.detail_progress_card.winfo_exists():
            if self.detail_progress_visible:
                if not self.detail_progress_card.winfo_manager():
                    self.detail_progress_card.pack(fill="x", pady=(0, 14), before=self.detail_continue_button.master)
            else:
                if self.detail_progress_card.winfo_manager():
                    self.detail_progress_card.pack_forget()
        self._refresh_detail_progress_toggle_style()

    def toggle_detail_progress(self):
        if not self.current_book():
            return
        self.set_detail_progress_visible(not self.detail_progress_visible)

    def style_scrollbar(self, scrollbar):
        scrollbar.configure(
            width=9,
            bg=SURFACE_GLOW,
            activebackground="#23406d",
            troughcolor="#07101f",
            relief="flat",
            bd=0,
            highlightthickness=0,
        )

    def _scroll_main_page(self, delta):
        if hasattr(self, "page_area") and self.page_area and self.page_area.winfo_exists():
            self.page_area.canvas.yview_scroll(delta, "units")

    def _on_main_page_mousewheel(self, event):
        self._scroll_main_page(int(-1 * (event.delta / 120)))

    def _on_main_page_mousewheel_linux(self, event):
        if event.num == 4:
            self._scroll_main_page(-1)
        elif event.num == 5:
            self._scroll_main_page(1)

    def register_main_page_scroll(self, widget):
        if not widget or not widget.winfo_exists():
            return
        self._bind_main_page_scroll_recursive(widget)

    def _bind_main_page_scroll_recursive(self, widget):
        if widget is getattr(self, "cards_area", None) or widget is getattr(self, "detail_area", None):
            return
        widget.bind("<MouseWheel>", self._on_main_page_mousewheel, add="+")
        widget.bind("<Button-4>", self._on_main_page_mousewheel_linux, add="+")
        widget.bind("<Button-5>", self._on_main_page_mousewheel_linux, add="+")
        for child in widget.winfo_children():
            self._bind_main_page_scroll_recursive(child)

    def set_action_button_state(self, button, enabled):
        enabled_bg = getattr(button, "enabled_bg", button.default_bg)
        enabled_hover = getattr(button, "enabled_hover", button.hover_bg)
        enabled_border = getattr(button, "enabled_border", button_border_color(enabled_bg))
        if enabled:
            button.default_bg = enabled_bg
            button.hover_bg = enabled_hover
            button.default_border = enabled_border
            button.configure(
                state="normal",
                bg=enabled_bg,
                fg="white",
                activebackground=enabled_hover,
                activeforeground="white",
                disabledforeground="white",
                cursor="hand2",
                highlightbackground=enabled_border,
                highlightcolor=enabled_border,
            )
            return

        disabled_bg = SURFACE_ALT
        button.default_bg = disabled_bg
        button.hover_bg = disabled_bg
        button.default_border = BORDER
        button.configure(
            state="disabled",
            bg=disabled_bg,
            fg=MUTED,
            activebackground=disabled_bg,
            activeforeground=MUTED,
            disabledforeground=MUTED,
            cursor="arrow",
            highlightbackground=BORDER,
            highlightcolor=BORDER,
        )

    def refresh_detail_actions(self, book):
        if not self.detail_window or not self.detail_window.winfo_exists():
            return
        has_book = bool(book)
        has_link = bool(row_value(book, "reading_link")) if book else False
        has_cover = bool(row_value(book, "cover_path")) if book else False
        self.set_action_button_state(self.detail_continue_button, has_book and has_link)
        self.set_action_button_state(self.detail_progress_toggle_button, has_book)
        self.set_action_button_state(self.detail_edit_button, has_book)
        self.set_action_button_state(self.detail_link_button, has_book and has_link)
        self.set_action_button_state(self.detail_cover_button, has_book and has_cover)
        self.set_action_button_state(self.detail_copy_button, has_book and has_link)
        self.set_action_button_state(self.detail_delete_button, has_book)
        self._refresh_detail_progress_toggle_style()

    def request_cached_image(self, source, size, on_ready, on_missing=None):
        source = (source or "").strip()
        if not source:
            if on_missing:
                on_missing()
            return
        cache_key = (source, size[0], size[1])
        if cache_key in self.cover_photo_cache:
            on_ready(self.cover_photo_cache[cache_key])
            return
        if source in self.cover_raw_cache:
            self._dispatch_cached_image(source, size, on_ready, on_missing)
            return
        if source in self.cover_failed_sources:
            if on_missing:
                on_missing()
            return
        waiters = self.cover_requests.setdefault(source, [])
        waiters.append((size, on_ready, on_missing))
        if len(waiters) > 1:
            return
        if source.startswith(("http://", "https://")):
            threading.Thread(target=self._load_cached_image_async, args=(source,), daemon=True).start()
            return
        raw = read_image_bytes(source)
        self._finish_cached_image_request(source, raw)

    def _load_cached_image_async(self, source):
        raw = read_image_bytes(source)
        try:
            self.after(0, lambda: self._finish_cached_image_request(source, raw))
        except (tk.TclError, RuntimeError):
            pass

    def _finish_cached_image_request(self, source, raw):
        if raw is None:
            self.cover_failed_sources.add(source)
        else:
            self.cover_raw_cache[source] = raw
            self.cover_failed_sources.discard(source)
        waiters = self.cover_requests.pop(source, [])
        for size, on_ready, on_missing in waiters:
            self._dispatch_cached_image(source, size, on_ready, on_missing)

    def _dispatch_cached_image(self, source, size, on_ready, on_missing=None):
        cache_key = (source, size[0], size[1])
        photo = self.cover_photo_cache.get(cache_key)
        if photo is None and source in self.cover_raw_cache:
            photo = self._build_cached_photo(source, self.cover_raw_cache[source], size)
            if photo:
                self.cover_photo_cache[cache_key] = photo
        if photo:
            on_ready(photo)
        elif on_missing:
            on_missing()

    def _build_cached_photo(self, source, raw, size):
        if not raw:
            return None
        if not PIL_AVAILABLE and not source.startswith(("http://", "https://")):
            photo = create_file_photo_image(source, size)
            if photo:
                return photo
        try:
            return create_photo_image(raw, size)
        except Exception:
            return None

    def request_card_cover(self, card, source):
        self.request_cached_image(
            source,
            (248, 220),
            lambda photo, widget=card, requested_source=(source or "").strip(): self._apply_card_cover(widget, requested_source, photo),
        )

    def _apply_card_cover(self, card, source, photo):
        if not card.winfo_exists():
            return
        if (row_value(card.book, "cover_path") or "").strip() != source:
            return
        card.set_cover_image(photo)

    def load_detail_cover(self, book):
        if not self.detail_window or not self.detail_window.winfo_exists():
            return
        source = row_value(book, "cover_path")
        request_id = self.detail_cover_request_id
        if not source:
            self.detail_cover.set_text("Sem capa\ncadastrada")
            self.detail_cover_hint_var.set("Nenhuma capa foi cadastrada para esta obra.")
            return
        if source.startswith(("http://", "https://")):
            self.detail_cover.set_text("Carregando\ncapa...")
            self.detail_cover_hint_var.set("Buscando a capa salva...")
        self.request_cached_image(
            source,
            (168, 236),
            lambda photo, current_request=request_id: self._apply_detail_cover_photo(current_request, photo),
            lambda current_request=request_id, requested_source=source: self._apply_detail_cover_missing(current_request, requested_source),
        )

    def _apply_detail_cover_photo(self, request_id, photo):
        if request_id != self.detail_cover_request_id:
            return
        if not self.detail_window or not self.detail_window.winfo_exists():
            return
        if not hasattr(self, "detail_cover") or not self.detail_cover or not self.detail_cover.winfo_exists():
            return
        self.detail_cover.set_image(photo)
        self.detail_cover_ref = photo
        self.detail_cover_hint_var.set("Previa carregada no aplicativo.")

    def _apply_detail_cover_missing(self, request_id, source):
        if request_id != self.detail_cover_request_id:
            return
        if not self.detail_window or not self.detail_window.winfo_exists():
            return
        if not hasattr(self, "detail_cover") or not self.detail_cover or not self.detail_cover.winfo_exists():
            return
        self.detail_cover.set_text(cover_unavailable_text(source))
        self.detail_cover_hint_var.set(cover_help_text(source))

    def _book_progress_sort_key(self, book):
        _current_page, _total_pages, percent = progress_numbers(
            row_value(book, "last_page", "current_chapter"),
            row_value(book, "total_pages"),
        )
        return (
            percent if percent is not None else -1,
            row_value(book, "updated_at"),
            int(book["id"]),
        )

    def sort_books(self, books):
        mode = self.sort_var.get()
        if mode == "title":
            return sorted(books, key=lambda book: row_value(book, "title").casefold())
        if mode == "progress":
            return sorted(books, key=self._book_progress_sort_key, reverse=True)
        return books

    def sync_cards_view(self, reset_scroll=False):
        if not hasattr(self, "cards_area") or not self.cards_area.winfo_exists():
            return
        if reset_scroll:
            self.cards_area.scroll_to_top()

    def get_book_record(self, book_id=None):
        if book_id is None:
            return self.current_book()
        if book_id in self.books_by_id:
            return self.books_by_id[book_id]
        return self.db.get_book(int(book_id), self.current_user["id"])

    def open_book_link(self, book):
        if not book or not book["reading_link"]:
            messagebox.showwarning("Aviso", "Este livro nao possui link salvo.")
            return
        link = book["reading_link"].strip()
        if not link.startswith(("http://", "https://")):
            link = "https://" + link
        try:
            webbrowser.open_new_tab(link)
        except Exception:
            messagebox.showerror("Erro", "Nao foi possivel abrir o link salvo.")

    def continue_reading_book(self, book_id):
        self.open_book_link(self.get_book_record(int(book_id)))

    def focus_book(self, book_id):
        book_id = int(book_id)
        self.selected_book_id = book_id
        for existing_id, card in self.book_cards.items():
            if card.winfo_exists():
                card.set_selected(existing_id == book_id)

    def open_link_by_id(self, book_id):
        self.open_book_link(self.get_book_record(int(book_id)))

    def copy_link_by_id(self, book_id):
        book = self.get_book_record(int(book_id))
        if not book or not row_value(book, "reading_link"):
            messagebox.showwarning("Aviso", "Este livro nao possui link salvo.")
            return
        try:
            self.clipboard_clear()
            self.clipboard_append(row_value(book, "reading_link"))
            messagebox.showinfo("Copiado", "O link salvo foi copiado para a area de transferencia.")
        except Exception:
            messagebox.showerror("Erro", "Nao foi possivel copiar o link.")

    def edit_book_by_id(self, book_id):
        self.focus_book(book_id)
        self.edit_book()

    def delete_book_by_id(self, book_id):
        self.focus_book(book_id)
        self.delete_book()

    def refresh_books(self):
        if not self.current_user:
            return

        query_signature = (
            self.current_library_type(),
            self.search_var.get().strip().casefold(),
            self.status_filter_var.get(),
            self.sort_var.get(),
        )
        reset_scroll = query_signature != self.last_query_signature
        self.last_query_signature = query_signature

        counts = self.db.count_by_status(self.current_user["id"], book_type=self.current_library_type())
        self.summary_vars["total"].set(str(counts["total"]))
        self.summary_vars["lendo"].set(str(counts["lendo"]))
        self.summary_vars["quero_ler"].set(str(counts["quero_ler"]))
        self.summary_vars["concluidos"].set(str(counts["concluidos"]))
        self.chips.refresh()
        self.sort_chips.refresh()
        self.library_tabs.refresh()

        for widget in self.cards_area.inner.winfo_children():
            widget.destroy()

        books = self.db.list_books(
            self.current_user["id"],
            search=self.search_var.get(),
            status=self.status_filter_var.get(),
            book_type=self.current_library_type(),
        )
        books = self.sort_books(list(books))
        self.books_by_id = {book["id"]: book for book in books}
        self.book_cards = {}

        if self.selected_book_id is not None and self.selected_book_id not in self.books_by_id:
            self.selected_book_id = None
        self.revealed_progress_books.intersection_update(self.books_by_id.keys())

        if not books:
            self.selected_book_id = None
            empty = tk.Frame(self.cards_area.inner, bg=BG, pady=64)
            empty.pack(fill="both", expand=True)
            empty_shell = tk.Frame(empty, bg=SURFACE_ALT, highlightthickness=1, highlightbackground=BORDER_GLOW, padx=34, pady=30)
            empty_shell.pack(padx=24, pady=8)
            tk.Label(empty_shell, text="Sua estante ainda nao tem capas por aqui", bg=SURFACE_ALT, fg="white", font=("Segoe UI", 18, "bold")).pack(pady=(0, 8))
            tk.Label(
                empty_shell,
                text=f"Adicione seu primeiro {self.library_item_singular().lower()} para preencher esta colecao com progresso, link e capa.",
                bg=SURFACE_ALT,
                fg=SOFT_TEXT,
                font=("Segoe UI", 10),
            ).pack()
            SoftButton(empty_shell, f"Adicionar {self.library_item_singular()}", GREEN, GREEN_HOVER, self.add_book).pack(pady=(18, 0))
            self.cards_area.register_mousewheel(empty)
            self.cards_area.scroll_to_top()
            self.close_detail_window()
            return

        if self.selected_book_id is None:
            self.selected_book_id = books[0]["id"]

        cards_grid = tk.Frame(self.cards_area.inner, bg=BG)
        cards_grid.pack(fill="both", expand=True)
        self.cards_area.register_mousewheel(cards_grid)
        window_width = self.winfo_width()
        if window_width >= 1650:
            columns = 4
        elif window_width >= 1180:
            columns = 3
        elif window_width >= 820:
            columns = 2
        else:
            columns = 1
        for col in range(columns):
            cards_grid.grid_columnconfigure(col, weight=1, uniform="library-grid")

        for index, book in enumerate(books):
            card = BookCard(
                cards_grid,
                book,
                self.select_book,
                request_cover=self.request_card_cover,
                register_mousewheel=self.cards_area.register_mousewheel,
                on_continue=self.continue_reading_book,
                on_toggle_progress=self.toggle_book_progress,
                on_open_link=self.open_link_by_id,
                on_copy_link=self.copy_link_by_id,
                on_edit=self.edit_book_by_id,
                on_delete=self.delete_book_by_id,
                selected=(book["id"] == self.selected_book_id),
                show_progress=(book["id"] in self.revealed_progress_books),
            )
            row = index // columns
            column = index % columns
            top_pad = 8 if row == 0 else 10
            card.grid(row=row, column=column, sticky="n", padx=8, pady=(top_pad, 12))
            self.cards_area.register_mousewheel(card)
            self.book_cards[book["id"]] = card

        if self.detail_window and self.detail_window.winfo_exists():
            selected_book = self.books_by_id.get(self.selected_book_id)
            if selected_book:
                self.show_details(selected_book)
            else:
                self.close_detail_window()
        self.after_idle(lambda should_reset=reset_scroll: self.sync_cards_view(reset_scroll=should_reset))

    def select_book(self, book_id):
        book_id = int(book_id)
        same_book = book_id == self.selected_book_id
        previous_id = self.selected_book_id
        self.selected_book_id = book_id
        if not same_book and previous_id in self.book_cards:
            self.book_cards[previous_id].set_selected(False)
        if book_id in self.book_cards:
            self.book_cards[book_id].set_selected(True)
        self.show_details(self.books_by_id.get(book_id))

    def toggle_book_progress(self, book_id):
        book_id = int(book_id)
        if book_id in self.revealed_progress_books:
            self.revealed_progress_books.discard(book_id)
            visible = False
        else:
            self.revealed_progress_books.add(book_id)
            visible = True
        card = self.book_cards.get(book_id)
        if card and card.winfo_exists():
            card.set_progress_visible(visible)

    def show_details(self, book):
        if not book:
            self.close_detail_window()
            return

        self.ensure_detail_window()
        self.detail_window.title(f"Detalhes - {book['title']}")
        self.detail_window.lift()
        if hasattr(self, "detail_area") and self.detail_area and self.detail_area.winfo_exists():
            self.detail_area.scroll_to_top()
        self.details_text.configure(state="normal")
        self.details_text.delete("1.0", "end")
        self.detail_cover_ref = None
        self.detail_cover_request_id += 1

        self.load_detail_cover(book)
        self.refresh_detail_actions(book)
        accent = {
            STATUS_WANT: PURPLE,
            STATUS_READING: BLUE,
            STATUS_DONE: GREEN,
        }.get(book["status"], CYAN)
        current_page, total_pages, percent = progress_numbers(
            row_value(book, "last_page", "current_chapter"),
            row_value(book, "total_pages"),
        )

        self.detail_title_var.set(book["title"])
        self.detail_meta_var.set(f"Atualizado: {format_display_datetime(row_value(book, 'updated_at'))}")
        self.detail_author_var.set(book["author"] or "Autor nao informado")
        type_accent = PURPLE if (row_value(book, "book_type") or TYPE_BOOK) == TYPE_LIGHT_NOVEL else CYAN
        status_bg, status_fg = status_badge_colors(book["status"])
        self.detail_type_badge.configure(
            text=row_value(book, "book_type") or TYPE_BOOK,
            bg=CHIP_BG,
            fg=type_accent,
            highlightbackground=button_border_color(type_accent),
        )
        self.detail_category_badge.configure(
            text=row_value(book, "category") or "Sem categoria",
            bg=CHIP_BG,
            fg=SOFT_TEXT,
            highlightbackground=CHIP_BORDER,
        )
        self.detail_status_badge.configure(text=book["status"], bg=status_bg, fg=status_fg, highlightbackground=accent)
        if current_page != "-":
            self.detail_progress_summary_var.set(f"Ultimo visto: pagina {current_page}")
        else:
            self.detail_progress_summary_var.set("Ultimo visto ainda nao informado")
        progress_text = f"Pagina atual: {current_page}"
        if total_pages:
            progress_text += f" de {total_pages}"
        if percent is not None:
            progress_text += f"  ({percent}%)"
        self.detail_progress_var.set(progress_text)
        self.set_detail_progress(percent, accent=accent)
        self.set_detail_progress_visible(False)

        content = [
            "Link salvo",
            f"{book['reading_link'] or 'Nenhum link salvo.'}",
            "",
            "Observacoes",
            f"{book['notes'] or 'Nenhuma observacao salva.'}",
        ]
        self.details_text.insert("1.0", "\n".join(content))
        self.details_text.configure(state="disabled")

    def add_book(self):
        BookForm(self, self.save_new_book)

    def save_new_book(self, data):
        self.library_var.set((data.get("book_type") or TYPE_BOOK).strip() or TYPE_BOOK)
        self.selected_book_id = self.db.add_book(self.current_user["id"], data)
        self.last_query_signature = None
        self.show_main()
        if self.detail_window and self.detail_window.winfo_exists():
            self.show_details(self.current_book())

    def edit_book(self):
        book = self.current_book()
        if not book:
            messagebox.showwarning("Aviso", "Selecione um item para editar.")
            return
        BookForm(self, self.save_existing_book, book=book)

    def save_existing_book(self, data):
        if self.selected_book_id:
            self.library_var.set((data.get("book_type") or TYPE_BOOK).strip() or TYPE_BOOK)
            self.db.update_book(self.selected_book_id, self.current_user["id"], data)
            self.last_query_signature = None
            self.show_main()
            if self.detail_window and self.detail_window.winfo_exists():
                self.show_details(self.current_book())

    def continue_reading(self):
        self.open_book_link(self.current_book())

    def open_link(self):
        self.open_book_link(self.current_book())

    def open_cover(self):
        book = self.current_book()
        if not book or not book["cover_path"]:
            messagebox.showwarning("Aviso", "Este livro nao possui capa salva.")
            return
        source = book["cover_path"].strip()
        try:
            resolved = resolve_cover_source(source, allow_download=True)
            if is_remote_source(resolved):
                webbrowser.open_new_tab(resolved)
            else:
                webbrowser.open(Path(resolved).resolve().as_uri())
        except Exception:
            messagebox.showerror("Erro", "Nao foi possivel abrir a capa.")

    def delete_book(self):
        book = self.current_book()
        if not book:
            messagebox.showwarning("Aviso", "Selecione um item para excluir.")
            return
        if messagebox.askyesno("Confirmar", "Deseja realmente excluir esta obra?"):
            self.revealed_progress_books.discard(int(book["id"]))
            self.db.delete_book(self.selected_book_id, self.current_user["id"])
            self.selected_book_id = None
            self.last_query_signature = None
            self.close_detail_window()
            self.show_main()


if __name__ == "__main__":
    try:
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PROCESS_PER_MONITOR_DPI_AWARE
    except Exception:
        try:
            import ctypes
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass

    launched_web = False
    try:
        from web_runtime import DesktopWebApp

        web_app = DesktopWebApp(
            db_factory=Database,
            db_path=DB_PATH,
            row_value=row_value,
            progress_numbers=progress_numbers,
            format_display_datetime=format_display_datetime,
            resolve_cover_source=resolve_cover_source,
            type_book=TYPE_BOOK,
            type_light_novel=TYPE_LIGHT_NOVEL,
            type_adult=TYPE_ADULT,
            status_want=STATUS_WANT,
            status_reading=STATUS_READING,
            status_done=STATUS_DONE,
        )
        launched_web = web_app.run()
    except Exception:
        launched_web = False

    if not launched_web:
        app = App()
        app.mainloop()
