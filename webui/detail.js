const params = new URLSearchParams(window.location.search);
const bookId = Number(params.get('id'));
const channel = new BroadcastChannel('library-web-app');

const els = {
  toast: document.getElementById('toast'),
  detailCard: document.getElementById('detailCard'),
  detailCover: document.getElementById('detailCover'),
  detailCoverFallback: document.getElementById('detailCoverFallback'),
  detailUpdated: document.getElementById('detailUpdated'),
  detailTitle: document.getElementById('detailTitle'),
  detailAuthor: document.getElementById('detailAuthor'),
  detailType: document.getElementById('detailType'),
  detailCategory: document.getElementById('detailCategory'),
  detailStatus: document.getElementById('detailStatus'),
  detailProgressSummary: document.getElementById('detailProgressSummary'),
  detailToggleProgress: document.getElementById('detailToggleProgress'),
  detailProgressHint: document.getElementById('detailProgressHint'),
  detailProgressWrap: document.getElementById('detailProgressWrap'),
  detailProgressFill: document.getElementById('detailProgressFill'),
  detailProgressCaption: document.getElementById('detailProgressCaption'),
  detailProgressPercent: document.getElementById('detailProgressPercent'),
  detailContinue: document.getElementById('detailContinue'),
  detailEdit: document.getElementById('detailEdit'),
  detailOpenLink: document.getElementById('detailOpenLink'),
  detailCopyLink: document.getElementById('detailCopyLink'),
  detailOpenCover: document.getElementById('detailOpenCover'),
  detailDelete: document.getElementById('detailDelete'),
  detailLink: document.getElementById('detailLink'),
  detailNotes: document.getElementById('detailNotes'),
};

let currentBook = null;
let detailProgressVisible = false;

const confirmDialog = window.createConfirmDialog();
const bookModal = window.createBookModal({
  api,
  toast,
  channel,
  getDefaultBookType: () => currentBook?.book_type || 'Livro',
  getCategoryOptions: async () => {
    const payload = await api('/api/categories');
    return payload.categories || [];
  },
  onSaved: async () => {
    await loadBook();
  },
});

function toast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.remove('hidden');
  els.toast.style.borderColor = isError ? 'rgba(223, 54, 80, 0.42)' : 'rgba(24, 182, 255, 0.32)';
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => els.toast.classList.add('hidden'), 2600);
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json', ...(options.headers || {}) },
    ...options,
  });
  const contentType = response.headers.get('content-type') || '';
  const payload = contentType.includes('application/json') ? await response.json() : null;
  if (!response.ok) {
    const error = new Error((payload && payload.error) || 'Nao foi possivel concluir a operacao.');
    error.status = response.status;
    error.payload = payload;
    throw error;
  }
  return payload;
}

function applyProgressVisibility() {
  els.detailProgressWrap.classList.toggle('hidden', !detailProgressVisible);
  els.detailProgressHint.classList.toggle('hidden', detailProgressVisible);
  els.detailToggleProgress.classList.toggle('is-active', detailProgressVisible);
}

function renderCategoryChips(rawCategory) {
  const tags = (rawCategory || '')
    .split(',')
    .map((value) => value.trim())
    .filter((value) => value && value.toLowerCase() !== 'sem categoria');
  els.detailCategory.innerHTML = '';
  if (!tags.length) {
    const span = document.createElement('span');
    span.className = 'chip chip-neutral';
    span.textContent = 'Sem categoria';
    els.detailCategory.appendChild(span);
    return;
  }
  tags.forEach((tag) => {
    const span = document.createElement('span');
    span.className = 'chip chip-neutral';
    span.textContent = tag;
    els.detailCategory.appendChild(span);
  });
}

function renderBook(book) {
  currentBook = book;
  document.title = `Detalhes - ${book.title}`;
  els.detailTitle.textContent = book.title;
  els.detailAuthor.textContent = book.author;
  els.detailUpdated.textContent = `Atualizado: ${book.updated_at_display || '-'}`;
  els.detailType.textContent = book.book_type;
  els.detailType.className = `chip chip-type ${book.book_type_slug}`;
  renderCategoryChips(book.category);
  els.detailStatus.textContent = book.status;
  els.detailStatus.className = `chip chip-status ${book.status_slug}`;
  els.detailProgressSummary.textContent = book.progress_hidden_caption;
  els.detailProgressCaption.textContent = book.progress_caption;
  els.detailProgressPercent.textContent = book.progress_percent == null ? 'Sem total' : `${book.progress_percent}%`;
  els.detailProgressFill.style.width = book.progress_percent == null ? '0%' : `${Math.max(4, Math.min(100, book.progress_percent))}%`;
  els.detailLink.textContent = book.reading_link || 'Nenhum link salvo.';
  els.detailNotes.textContent = book.notes || 'Nenhuma observacao salva.';

  if (book.cover_url) {
    els.detailCover.onerror = () => {
      els.detailCover.style.display = 'none';
      els.detailCoverFallback.classList.remove('hidden');
    };
    els.detailCover.src = book.cover_url;
    els.detailCover.style.display = 'block';
    els.detailCoverFallback.classList.add('hidden');
    window.applyAdaptiveCover?.(els.detailCover);
  } else {
    els.detailCover.removeAttribute('src');
    els.detailCover.style.display = 'none';
    els.detailCoverFallback.classList.remove('hidden');
  }

  const hasLink = !!book.reading_link;
  const hasCover = !!book.cover_path;
  els.detailContinue.disabled = !hasLink;
  els.detailOpenLink.disabled = !hasLink;
  els.detailCopyLink.disabled = !hasLink;
  els.detailOpenCover.disabled = !hasCover;
  els.detailCard.classList.remove('hidden');
  detailProgressVisible = false;
  applyProgressVisibility();
}

async function loadBook() {
  const payload = await api(`/api/book/${bookId}`);
  renderBook(payload.book);
}

async function openLink() {
  await api(`/api/book/${bookId}/open-link`, { method: 'POST' });
}

async function copyLink() {
  if (!currentBook?.reading_link) throw new Error('Nenhum link salvo para esta obra.');
  await navigator.clipboard.writeText(currentBook.reading_link);
  toast('Link copiado com sucesso.');
}

function openForm() {
  return bookModal.openEdit(bookId, currentBook?.book_type || 'Livro');
}

async function deleteBook() {
  const confirmed = await confirmDialog.open({
    title: 'Excluir obra',
    message: 'Deseja realmente excluir esta obra? Essa acao nao pode ser desfeita.',
    confirmText: 'Excluir obra',
    cancelText: 'Cancelar',
    tone: 'danger',
  });
  if (!confirmed) return;

  await api(`/api/book/${bookId}`, { method: 'DELETE' });
  channel.postMessage({ type: 'books-changed' });
  toast('Obra excluida com sucesso.');
  setTimeout(() => closeThisWindow(), 300);
}

function closeThisWindow() {
  const token = new URLSearchParams(location.search).get('v') || '';
  api('/api/close-window', { method: 'POST', body: JSON.stringify({ token }) })
    .catch(() => {})
    .finally(() => window.close());
}

els.detailToggleProgress.addEventListener('click', () => {
  detailProgressVisible = !detailProgressVisible;
  applyProgressVisibility();
});
els.detailContinue.addEventListener('click', () => openLink().catch((error) => toast(error.message, true)));
els.detailOpenLink.addEventListener('click', () => openLink().catch((error) => toast(error.message, true)));
els.detailCopyLink.addEventListener('click', () => copyLink().catch((error) => toast(error.message, true)));
els.detailEdit.addEventListener('click', () => openForm().catch((error) => toast(error.message, true)));
els.detailDelete.addEventListener('click', () => deleteBook().catch((error) => toast(error.message, true)));
els.detailOpenCover.addEventListener('click', () => {
  if (currentBook?.cover_url) window.open(currentBook.cover_url, '_blank', 'noopener');
});

channel.onmessage = (event) => {
  if (event.data?.type === 'books-changed' || event.data?.type === 'categories-changed') {
    loadBook().catch((error) => toast(error.message, true));
  }
};

loadBook().catch((error) => toast(error.message, true));
