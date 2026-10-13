const channel = new BroadcastChannel('library-web-app');
const FAVORITES_COLLECTION = '__favorites__';
const REMEMBER_LOGIN_KEY = 'libraryRememberedLogin';
const REMEMBER_LOGIN_ENABLED_KEY = 'libraryRememberLoginEnabled';

const state = {
  user: null,
  currentCollection: 'Livro',
  lastTypeCollection: 'Livro',
  currentCategory: '',
  availableCategories: [],
  status: '',
  sort: 'recent',
  search: '',
  revealed: new Set(),
  expandedCards: new Set(),
  focusedBookId: null,
};

const els = {
  authScreen: document.getElementById('authScreen'),
  dashboardScreen: document.getElementById('dashboardScreen'),
  loginPane: document.getElementById('loginPane'),
  registerPane: document.getElementById('registerPane'),
  loginTabBtn: document.getElementById('loginTabBtn'),
  registerTabBtn: document.getElementById('registerTabBtn'),
  demoLoginBtn: document.getElementById('demoLoginBtn'),
  loginEmail: document.getElementById('loginEmail'),
  loginPassword: document.getElementById('loginPassword'),
  rememberLogin: document.getElementById('rememberLogin'),
  registerName: document.getElementById('registerName'),
  registerEmail: document.getElementById('registerEmail'),
  registerPassword: document.getElementById('registerPassword'),
  registerPasswordConfirm: document.getElementById('registerPasswordConfirm'),
  loginButton: document.getElementById('loginButton'),
  registerButton: document.getElementById('registerButton'),
  heroGreeting: document.getElementById('heroGreeting'),
  addBookButton: document.getElementById('addBookButton'),
  logoutButton: document.getElementById('logoutButton'),
  collectionTabs: document.getElementById('collectionTabs'),
  totalCount: document.getElementById('totalCount'),
  readingCount: document.getElementById('readingCount'),
  wantCount: document.getElementById('wantCount'),
  doneCount: document.getElementById('doneCount'),
  searchInput: document.getElementById('searchInput'),
  categoryFilter: document.getElementById('categoryFilter'),
  addCategoryButton: document.getElementById('addCategoryButton'),
  statusFilter: document.getElementById('statusFilter'),
  sortFilter: document.getElementById('sortFilter'),
  booksGrid: document.getElementById('booksGrid'),
  collectionTitle: document.getElementById('collectionTitle'),
  collectionSubtitle: document.getElementById('collectionSubtitle'),
  scrollTopButton: document.getElementById('scrollTopButton'),
  toast: document.getElementById('toast'),
};

const confirmDialog = window.createConfirmDialog();
const inputDialog = window.createInputDialog();
const bookModal = window.createBookModal({
  api,
  toast,
  channel,
  getDefaultBookType: () => (
    state.currentCollection === FAVORITES_COLLECTION ? state.lastTypeCollection : state.currentCollection
  ),
  getCategoryOptions: async () => {
    const payload = await api('/api/categories');
    return payload.categories || [];
  },
  onSaved: async (book) => {
    if (book?.id) {
      state.focusedBookId = book.id;
    }
    if (book?.category && book.category !== 'Sem categoria') {
      state.currentCategory = book.category;
    }
    await loadDashboard();
  },
});

function toast(message, isError = false) {
  els.toast.textContent = message;
  els.toast.classList.remove('hidden');
  els.toast.style.borderColor = isError ? 'rgba(173, 91, 79, 0.5)' : 'rgba(201, 162, 39, 0.4)';
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

function switchAuthPane(mode) {
  const loginMode = mode === 'login';
  els.loginPane.classList.toggle('hidden', !loginMode);
  els.registerPane.classList.toggle('hidden', loginMode);
  els.loginTabBtn.classList.toggle('is-active', loginMode);
  els.registerTabBtn.classList.toggle('is-active', !loginMode);
}

function restoreRememberedLogin() {
  const enabled = localStorage.getItem(REMEMBER_LOGIN_ENABLED_KEY) === '1';
  const identifier = localStorage.getItem(REMEMBER_LOGIN_KEY) || '';
  els.rememberLogin.checked = enabled;
  els.loginEmail.value = enabled ? identifier : '';
}

function persistRememberedLogin() {
  if (els.rememberLogin.checked && els.loginEmail.value.trim()) {
    localStorage.setItem(REMEMBER_LOGIN_ENABLED_KEY, '1');
    localStorage.setItem(REMEMBER_LOGIN_KEY, els.loginEmail.value.trim());
    return;
  }
  localStorage.removeItem(REMEMBER_LOGIN_KEY);
  localStorage.removeItem(REMEMBER_LOGIN_ENABLED_KEY);
}

const GENERATED_COVER_PALETTES = [
  [58, 89, 120],
  [60, 110, 96],
  [120, 92, 52],
  [90, 70, 130],
];

function hashSeed(text) {
  let hash = 0;
  const str = String(text || '');
  for (let i = 0; i < str.length; i += 1) {
    hash = (hash * 31 + str.charCodeAt(i)) >>> 0;
  }
  return hash;
}

function lightenRgb([r, g, b], amt) {
  return [r, g, b].map((v) => Math.round(v + (255 - v) * amt));
}

function darkenRgb([r, g, b], amt) {
  return [r, g, b].map((v) => Math.round(v * (1 - amt)));
}

function rgbCss([r, g, b], alpha) {
  return alpha === undefined ? `rgb(${r},${g},${b})` : `rgba(${r},${g},${b},${alpha})`;
}

function generatedCoverMarkup(id, title, author) {
  const safeTitle = title || 'Sem titulo';
  const seedValue = id !== undefined && id !== null && id !== '' ? id : safeTitle;
  const palette = GENERATED_COVER_PALETTES[hashSeed(seedValue) % GENERATED_COVER_PALETTES.length];
  const top = lightenRgb(palette, 0.18);
  const bottom = darkenRgb(palette, 0.4);
  const accentA = lightenRgb(palette, 0.55);
  const accentB = darkenRgb(palette, 0.22);
  const background = `linear-gradient(180deg, ${rgbCss(top)} 0%, ${rgbCss(palette)} 45%, ${rgbCss(bottom)} 100%)`;
  const authorHtml = author
    ? `<span class="generated-cover-author">${escapeHtml(author)}</span>`
    : '';
  return `<div class="book-cover is-cover-fill generated-cover" style="background:${background}">` +
    `<span class="generated-cover-blob generated-cover-blob-a" style="background:${rgbCss(accentA, 0.16)}"></span>` +
    `<span class="generated-cover-blob generated-cover-blob-b" style="background:${rgbCss(accentB, 0.14)}"></span>` +
    `<span class="generated-cover-rule"></span>` +
    `<span class="generated-cover-title">${escapeHtml(safeTitle)}</span>` +
    authorHtml +
    `</div>`;
}

function handleCoverLoadError(imgEl) {
  const wrapper = document.createElement('div');
  wrapper.innerHTML = generatedCoverMarkup(imgEl.dataset.fallbackId, imgEl.dataset.fallbackTitle, imgEl.dataset.fallbackAuthor);
  imgEl.replaceWith(wrapper.firstElementChild);
}

function starIconMarkup(filled) {
  return filled
    ? '<svg viewBox="0 0 24 24" width="17" height="17" fill="currentColor" aria-hidden="true"><path d="M12 2.6l2.85 6.16 6.79.72-5.07 4.62L18.02 21 12 17.4 5.98 21l1.45-6.9L2.36 9.48l6.79-.72L12 2.6z"/></svg>'
    : '<svg viewBox="0 0 24 24" width="17" height="17" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round" aria-hidden="true"><path d="M12 2.6l2.85 6.16 6.79.72-5.07 4.62L18.02 21 12 17.4 5.98 21l1.45-6.9L2.36 9.48l6.79-.72L12 2.6z"/></svg>';
}

function coverMarkup(book) {
  if (book.cover_url) {
    return `<img class="book-cover" data-adaptive-cover="card" data-fallback-id="${escapeHtml(book.id)}" data-fallback-title="${escapeHtml(book.title || '')}" data-fallback-author="${escapeHtml(book.author || '')}" src="${book.cover_url}" alt="Capa de ${escapeHtml(book.title)}" onerror="handleCoverLoadError(this)">`;
  }
  return generatedCoverMarkup(book.id, book.title, book.author);
}

function progressMarkup(book) {
  const visible = state.revealed.has(book.id);
  const percentWidth = book.progress_percent !== null && book.progress_percent !== undefined
    ? `${Math.max(4, Math.min(100, book.progress_percent))}%`
    : '0%';

  if (!visible) {
    return `
      <div class="progress-card" id="progress-card-${book.id}">
        <strong>${escapeHtml(book.progress_hidden_caption)}</strong>
        <div class="progress-hidden-copy">${escapeHtml(book.progress_hint)}</div>
      </div>
    `;
  }

  return `
    <div class="progress-card" id="progress-card-${book.id}">
      <strong>${escapeHtml(book.progress_caption)}</strong>
      <div class="progress-shell">
        <div class="progress-track">
          <div class="progress-fill" style="width:${percentWidth}"></div>
        </div>
        <div class="progress-meta">
          <span>${escapeHtml(book.progress_visible_line)}</span>
          <span>${book.progress_percent == null ? 'Sem total' : `${book.progress_percent}%`}</span>
        </div>
      </div>
    </div>
  `;
}

function parseCategoryListFrontend(raw) {
  return (raw || '')
    .split(',')
    .map((value) => value.trim())
    .filter((value) => value && value.toLowerCase() !== 'sem categoria');
}

function categoryChipMarkup(book) {
  const tags = parseCategoryListFrontend(book.category);
  const visible = tags.slice(0, 3);
  const hasMore = tags.length > 3;
  const chips = visible.length
    ? visible.map((tag) => `<span class="chip chip-neutral">${escapeHtml(tag)}</span>`).join('')
    : `<span class="chip chip-neutral chip-empty">Sem categoria</span>`;
  const moreChip = hasMore
    ? `<span class="chip chip-more" title="+${tags.length - 3} categoria(s). Clique no livro para ver todas.">/</span>`
    : '';
  return chips + moreChip;
}

// Linha de tags do card: as tags quebram linha dentro da própria coluna e o
// botão "+" fica fixo na coluna da direita, sempre na mesma posição.
function chipRowMarkup(book) {
  const typeClass = book.book_type_slug === 'light-novel'
    ? 'light-novel'
    : (book.book_type_slug === 'adult' ? 'adult' : '');
  return `
    <div class="chip-tags">
      <span class="chip chip-type ${typeClass}">${escapeHtml(book.book_type)}</span>
      ${categoryChipMarkup(book)}
    </div>
    <button type="button" class="chip chip-quickset" data-action="quick-category" data-id="${book.id}" title="Gerenciar categorias">+</button>
  `;
}

function compactMetaLine(label, value, title) {
  return `<div title="${escapeHtml(title || value || '-')}"><strong>${label}:</strong> ${escapeHtml(value || '-')}</div>`;
}

function bookCardMarkup(book, index = 0) {
  const focused = state.focusedBookId === book.id;
  const animationDelay = Math.min(index * 40, 400);
  const typeClass = book.book_type_slug === 'light-novel'
    ? 'light-novel'
    : (book.book_type_slug === 'adult' ? 'adult' : '');

  const linkMarkup = book.has_link
    ? `<button class="btn btn-success" data-action="continue" data-id="${book.id}">Continuar leitura</button>`
    : `<button class="btn btn-muted is-disabled" disabled>Sem link salvo</button>`;

  const openLinkMarkup = book.has_link
    ? `<button class="btn btn-accent" data-action="open-link" data-id="${book.id}">Abrir link</button>`
    : `<button class="btn btn-muted is-disabled" disabled>Abrir link</button>`;

  const copyLinkMarkup = book.has_link
    ? `<button class="btn btn-secondary" data-action="copy-link" data-id="${book.id}">Copiar link</button>`
    : `<button class="btn btn-muted is-disabled" disabled>Copiar link</button>`;

  const expandIcon = '<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" class="expand-caret" aria-hidden="true"><path d="M6 9l6 6 6-6"/></svg>';
  const isExpanded = state.expandedCards.has(book.id);

  return `
    <article class="book-card ${focused ? 'is-focused' : ''} ${isExpanded ? 'is-expanded' : ''}" data-book-id="${book.id}" style="animation-delay: ${animationDelay}ms">
      <div class="book-cover-frame" data-action="details" data-id="${book.id}">
        ${coverMarkup(book)}
        <button
          class="favorite-toggle ${book.is_favorite ? 'is-active' : ''}"
          data-action="favorite"
          data-id="${book.id}"
          data-favorite="${book.is_favorite ? '0' : '1'}"
          aria-label="${book.is_favorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos'}"
        >${starIconMarkup(book.is_favorite)}</button>
        <span class="status-badge ${book.status_slug}">${escapeHtml(book.status)}</span>
      </div>

      <div class="book-body">
        <div class="book-heading-block">
          <h3 class="book-title" data-action="details" data-id="${book.id}" title="${escapeHtml(book.title)}">${escapeHtml(book.title)}</h3>
          <p class="book-author" title="${escapeHtml(book.author)}">${escapeHtml(book.author)}</p>
        </div>

        <div class="chip-row" id="chip-row-${book.id}">${chipRowMarkup(book)}</div>

        <button type="button" class="card-expand-toggle" data-action="toggle-expand" data-id="${book.id}" aria-expanded="${isExpanded ? 'true' : 'false'}">
          <span>${isExpanded ? 'Ver menos' : 'Ver mais'}</span>
          ${expandIcon}
        </button>

        <div class="book-extra">
          <div class="book-extra-inner">
            ${progressMarkup(book)}

            <div class="book-meta-list">
              ${compactMetaLine('Atualizado', book.updated_at_display || '-', book.updated_at_display || '-')}
              ${compactMetaLine('Observacao', book.notes_short || '-', book.notes || '-')}
              ${compactMetaLine('Link', book.link_short || '-', book.reading_link || '-')}
            </div>

            <div class="book-actions">
              ${linkMarkup}
              <button class="btn btn-muted" data-action="toggle-progress" data-id="${book.id}">Progresso</button>
            </div>

            <div class="book-secondary-actions">
              ${openLinkMarkup}
              ${copyLinkMarkup}
            </div>

            <div class="book-tertiary-actions">
              <button class="btn btn-secondary" data-action="edit" data-id="${book.id}">Editar</button>
              <button class="btn btn-danger" data-action="delete" data-id="${book.id}">Excluir</button>
            </div>
          </div>
        </div>
      </div>
    </article>
  `;
}

function updateSegmentActive(container, selector, value, attrName) {
  let activeButton = null;
  container.querySelectorAll(selector).forEach((button) => {
    const isActive = button.getAttribute(attrName) === value;
    button.classList.toggle('is-active', isActive);
    if (isActive) activeButton = button;
  });
  positionSegmentIndicator(container, activeButton);
}

function positionSegmentIndicator(container, activeButton) {
  const indicator = container.querySelector('.segment-indicator');
  if (!indicator || !activeButton) return;
  indicator.style.left = `${activeButton.offsetLeft}px`;
  indicator.style.width = `${activeButton.offsetWidth}px`;
  indicator.style.opacity = '1';
}

function refreshAllSegmentIndicators() {
  [els.collectionTabs, els.statusFilter, els.sortFilter].forEach((container) => {
    if (!container) return;
    const active = container.querySelector('.segment-btn.is-active');
    positionSegmentIndicator(container, active);
  });
}

let segmentIndicatorResizeTimer = null;
window.addEventListener('resize', () => {
  clearTimeout(segmentIndicatorResizeTimer);
  segmentIndicatorResizeTimer = setTimeout(refreshAllSegmentIndicators, 120);
});

function animateCountUp(el, target, duration = 650) {
  if (!el) return;
  const targetNum = Number(target) || 0;
  const start = Number(el.textContent) || 0;
  if (start === targetNum) {
    el.textContent = targetNum;
    return;
  }
  const startTime = performance.now();
  function tick(now) {
    const progress = Math.min((now - startTime) / duration, 1);
    const eased = 1 - Math.pow(1 - progress, 3);
    el.textContent = Math.round(start + (targetNum - start) * eased);
    if (progress < 1) requestAnimationFrame(tick);
    else el.textContent = targetNum;
  }
  requestAnimationFrame(tick);
}

function renderCategoryFilters() {
  if (!els.categoryFilter) return;
  const categories = state.availableCategories || [];
  const items = [
    `<button type="button" class="tag-chip ${state.currentCategory === '' ? 'is-active' : ''}" data-category="">Todas</button>`,
    ...categories.map((category) => `
      <button
        type="button"
        class="tag-chip ${state.currentCategory === category ? 'is-active' : ''}"
        data-category="${escapeHtml(category)}"
        title="${escapeHtml(category)}"
      >${escapeHtml(category)}</button>
    `),
  ];
  els.categoryFilter.innerHTML = items.join('');
}

function applyCollectionCopy() {
  if (state.currentCollection === FAVORITES_COLLECTION) {
    els.collectionTitle.textContent = 'Seus favoritos';
    els.collectionSubtitle.textContent = 'Obras marcadas com estrela para voce acessar mais rapido quando quiser.';
    return;
  }
  els.collectionTitle.textContent = 'Seus livros';
  els.collectionSubtitle.textContent = 'Explore sua colecao em cards visuais com capa em destaque, acoes rapidas e detalhes em janela separada.';
}

async function loadDashboard() {
  const data = await api(
    `/api/dashboard?search=${encodeURIComponent(state.search)}&status=${encodeURIComponent(state.status)}&sort=${encodeURIComponent(state.sort)}&collection=${encodeURIComponent(state.currentCollection)}&category=${encodeURIComponent(state.currentCategory)}`
  );

  state.user = data.user;
  state.availableCategories = data.categories || [];
  if (state.currentCategory && !state.availableCategories.some((category) => category === state.currentCategory)) {
    state.currentCategory = '';
  }

  els.heroGreeting.textContent = `Bem-vindo, ${state.user.name}. Organize sua biblioteca digital com livros, capas, links e progresso em um unico lugar.`;
  animateCountUp(els.totalCount, data.counts.total);
  animateCountUp(els.readingCount, data.counts.lendo);
  animateCountUp(els.wantCount, data.counts.quero_ler);
  animateCountUp(els.doneCount, data.counts.concluidos);

  updateSegmentActive(els.collectionTabs, '.segment-btn', encodeURIComponent(state.currentCollection), 'data-collection');
  updateSegmentActive(els.statusFilter, '.segment-btn', state.status, 'data-status');
  updateSegmentActive(els.sortFilter, '.segment-btn', state.sort, 'data-sort');
  renderCategoryFilters();
  applyCollectionCopy();

  if (!data.books.length) {
    els.booksGrid.innerHTML = `
      <article class="empty-state">
        <h3>Sua biblioteca ainda esta vazia</h3>
        <p>Adicione o primeiro livro para comecar a montar esta estante publica.</p>
        <button class="btn btn-success" id="emptyAddButton">+ Adicionar livro</button>
      </article>
    `;
    document.getElementById('emptyAddButton').addEventListener('click', () => {
      openFormWindow().catch((error) => toast(error.message, true));
    });
    return;
  }

  if (!state.focusedBookId || !data.books.some((book) => book.id === state.focusedBookId)) {
    state.focusedBookId = data.books[0].id;
  }

  state.booksById = new Map(data.books.map((book) => [book.id, book]));
  els.booksGrid.innerHTML = data.books.map((book, index) => bookCardMarkup(book, index)).join('');
  window.setupAdaptiveCovers?.(els.booksGrid);
}

async function bootstrap() {
  const session = await api('/api/session');
  if (session.user) {
    state.user = session.user;
    els.authScreen.classList.add('hidden');
    els.dashboardScreen.classList.remove('hidden');
    await loadDashboard();
    return;
  }

  els.authScreen.classList.remove('hidden');
  els.dashboardScreen.classList.add('hidden');
  switchAuthPane('login');
  els.loginPassword.value = '';
  restoreRememberedLogin();
}

async function login() {
  await api('/api/login', {
    method: 'POST',
    body: JSON.stringify({
      email: els.loginEmail.value.trim(),
      password: els.loginPassword.value.trim(),
    }),
  });
  persistRememberedLogin();
  els.loginPassword.value = '';
  toast('Login realizado com sucesso.');
  await bootstrap();
}

async function register() {
  await api('/api/register', {
    method: 'POST',
    body: JSON.stringify({
      name: els.registerName.value.trim(),
      email: els.registerEmail.value.trim(),
      password: els.registerPassword.value.trim(),
      confirm_password: els.registerPasswordConfirm.value.trim(),
    }),
  });
  els.registerName.value = '';
  els.registerEmail.value = '';
  els.registerPassword.value = '';
  els.registerPasswordConfirm.value = '';
  toast('Conta criada com sucesso.');
  await bootstrap();
}

async function logout() {
  await api('/api/logout', { method: 'POST' });
  state.user = null;
  state.revealed.clear();
  state.expandedCards.clear();
  state.focusedBookId = null;
  els.registerName.value = '';
  els.registerEmail.value = '';
  els.registerPassword.value = '';
  els.registerPasswordConfirm.value = '';
  els.loginPassword.value = '';
  toast('Sessao encerrada.');
  await bootstrap();
}

async function openLink(bookId) {
  await api(`/api/book/${bookId}/open-link`, { method: 'POST' });
}

async function copyLink(bookId) {
  const book = await api(`/api/book/${bookId}`);
  const value = book.book.reading_link || '';
  if (!value) {
    throw new Error('Esta obra nao possui link salvo.');
  }
  await navigator.clipboard.writeText(value);
  toast('Link copiado com sucesso.');
}

async function toggleFavorite(bookId, favorite) {
  await api(`/api/book/${bookId}/favorite`, {
    method: 'POST',
    body: JSON.stringify({ favorite }),
  });
  channel.postMessage({ type: 'books-changed' });
  toast(favorite ? 'Obra adicionada aos favoritos.' : 'Obra removida dos favoritos.');

  const book = state.booksById?.get(bookId);
  if (book) book.is_favorite = favorite;

  const removingFromFavoritesView = !favorite && state.currentCollection === FAVORITES_COLLECTION;

  if (removingFromFavoritesView) {
    if (state.focusedBookId === bookId) state.focusedBookId = null;
    const card = document.querySelector(`.book-card[data-book-id="${bookId}"]`);
    if (card) {
      card.style.transition = 'opacity 0.22s ease, transform 0.22s ease';
      card.style.opacity = '0';
      card.style.transform = 'scale(0.94)';
      setTimeout(() => loadDashboard().catch((error) => toast(error.message, true)), 200);
    } else {
      await loadDashboard();
    }
    return;
  }

  const starEl = document.querySelector(`.favorite-toggle[data-id="${bookId}"]`);
  if (starEl) {
    starEl.classList.toggle('is-active', favorite);
    starEl.setAttribute('data-favorite', favorite ? '0' : '1');
    starEl.setAttribute('aria-label', favorite ? 'Remover dos favoritos' : 'Adicionar aos favoritos');
    starEl.innerHTML = starIconMarkup(favorite);
    if (favorite) {
      starEl.classList.add('is-pulsing');
      starEl.addEventListener('animationend', () => starEl.classList.remove('is-pulsing'), { once: true });
    }
  }
}

function toggleCardExpand(bookId, buttonEl) {
  const expanded = state.expandedCards.has(bookId);
  if (expanded) {
    state.expandedCards.delete(bookId);
  } else {
    state.expandedCards.add(bookId);
  }
  const nowExpanded = !expanded;
  const cardEl = buttonEl?.closest('.book-card') || document.querySelector(`.book-card[data-book-id="${bookId}"]`);
  if (!cardEl) return;
  cardEl.classList.toggle('is-expanded', nowExpanded);
  const toggleBtn = cardEl.querySelector('[data-action="toggle-expand"]');
  if (toggleBtn) {
    toggleBtn.setAttribute('aria-expanded', nowExpanded ? 'true' : 'false');
    const label = toggleBtn.querySelector('span');
    if (label) label.textContent = nowExpanded ? 'Ver menos' : 'Ver mais';
  }
}

function toggleProgress(bookId) {
  if (state.revealed.has(bookId)) {
    state.revealed.delete(bookId);
  } else {
    state.revealed.add(bookId);
  }
  const book = state.booksById?.get(bookId);
  const container = document.getElementById(`progress-card-${bookId}`);
  if (book && container) {
    container.outerHTML = progressMarkup(book);
  } else {
    loadDashboard().catch((error) => toast(error.message, true));
  }
}

function openDetails(bookId) {
  state.focusedBookId = bookId;
  const cardEl = document.querySelector(`.book-card[data-book-id="${bookId}"]`);
  if (cardEl) {
    cardEl.classList.add('is-launching');
    setTimeout(() => cardEl.classList.remove('is-launching'), 420);
  }
  if (window.pywebview?.api?.open_details) {
    window.pywebview.api.open_details(bookId, window.screen.availWidth, window.screen.availHeight);
    loadDashboard().catch(() => {});
    return;
  }
  window.open(`/detail.html?id=${bookId}`, '_blank', 'width=1020,height=780');
}

function openFormWindow(bookId = null) {
  if (bookId) {
    return bookModal.openEdit(
      bookId,
      state.currentCollection === FAVORITES_COLLECTION ? state.lastTypeCollection : state.currentCollection
    );
  }
  return bookModal.openCreate(
    state.currentCollection === FAVORITES_COLLECTION ? state.lastTypeCollection : state.currentCollection
  );
}

async function deleteBook(bookId) {
  const confirmed = await confirmDialog.open({
    title: 'Excluir obra',
    message: 'Deseja realmente excluir esta obra? Essa acao nao pode ser desfeita.',
    confirmText: 'Excluir obra',
    cancelText: 'Cancelar',
    tone: 'danger',
  });

  if (!confirmed) return;

  await api(`/api/book/${bookId}`, { method: 'DELETE' });
  state.revealed.delete(bookId);
  if (state.focusedBookId === bookId) {
    state.focusedBookId = null;
  }
  channel.postMessage({ type: 'books-changed' });
  toast('Obra excluida com sucesso.');
  await loadDashboard();
}

async function openAddCategoryDialog() {
  const value = await inputDialog.open({
    title: 'Adicionar nova tag',
    message: 'Crie uma tag para ajudar na busca e organizacao da sua biblioteca.',
    label: 'Nome da tag',
    placeholder: 'Ex: Fantasia, Acao, Suspense',
    confirmText: 'Adicionar',
  });

  if (!value) return;

  const response = await api('/api/categories', {
    method: 'POST',
    body: JSON.stringify({ name: value }),
  });

  state.currentCategory = response.category || value;
  channel.postMessage({ type: 'categories-changed' });
  toast('Nova tag adicionada com sucesso.');
  await loadDashboard();
}

const categoryQuickPicker = (() => {
  const el = document.createElement('div');
  el.className = 'category-quick-picker';
  document.body.appendChild(el);
  let currentBookId = null;

  function close() {
    el.classList.remove('is-open');
    currentBookId = null;
  }

  function currentSelectedSet() {
    const book = state.booksById?.get(currentBookId);
    return new Set(parseCategoryListFrontend(book?.category).map((value) => value.toLowerCase()));
  }

  function renderOptions() {
    const categories = state.availableCategories || [];
    if (!categories.length) {
      el.innerHTML = `<div class="quick-picker-empty">Nenhuma categoria criada ainda. Use o "+" ao lado de "Tags e categorias" para criar uma.</div>`;
      return;
    }
    const selected = currentSelectedSet();
    el.innerHTML = categories.map((category) => {
      const isActive = selected.has(category.toLowerCase());
      return `
        <button type="button" class="quick-picker-option ${isActive ? 'is-selected' : ''}" data-category="${escapeHtml(category)}">
          <span class="quick-picker-check">${isActive ? '&#10003;' : ''}</span>
          <span>${escapeHtml(category)}</span>
        </button>
      `;
    }).join('');
  }

  el.addEventListener('click', (event) => {
    const option = event.target.closest('.quick-picker-option');
    if (!option || !currentBookId) return;
    const nowSelected = !option.classList.contains('is-selected');
    option.classList.toggle('is-selected', nowSelected);
    const check = option.querySelector('.quick-picker-check');
    if (check) check.innerHTML = nowSelected ? '&#10003;' : '';
    toggleQuickCategory(currentBookId, option.getAttribute('data-category'));
  });

  document.addEventListener('click', (event) => {
    if (!el.classList.contains('is-open')) return;
    if (el.contains(event.target) || event.target.closest('[data-action="quick-category"]')) return;
    close();
  });

  window.addEventListener('scroll', (event) => {
    if (el.contains(event.target)) return;
    close();
  }, true);

  return {
    open(anchorEl, bookId) {
      currentBookId = bookId;
      renderOptions();

      const categories = state.availableCategories || [];
      const estimatedHeight = Math.min(Math.max(categories.length, 1) * 38 + 16, 240);
      const rect = anchorEl.getBoundingClientRect();
      const spaceBelow = window.innerHeight - rect.bottom;
      const spaceAbove = rect.top;
      const margin = 8;

      let top;
      if (spaceBelow < estimatedHeight + margin && spaceAbove > spaceBelow) {
        top = rect.top + window.scrollY - estimatedHeight - margin;
        if (top < window.scrollY + margin) top = window.scrollY + margin;
      } else {
        top = rect.bottom + window.scrollY + margin;
      }

      el.style.top = `${top}px`;
      el.style.left = `${rect.left + window.scrollX}px`;
      el.classList.add('is-open');
    },
    refresh: renderOptions,
    close,
  };
})();

async function toggleQuickCategory(bookId, category) {
  const book = state.booksById?.get(bookId);
  if (!book) {
    await loadDashboard();
    return;
  }
  const current = parseCategoryListFrontend(book.category);
  const key = category.toLowerCase();
  const exists = current.some((value) => value.toLowerCase() === key);
  const next = exists
    ? current.filter((value) => value.toLowerCase() !== key)
    : [...current, category];
  const nextCategory = next.join(', ');
  const previousCategory = book.category;

  // Atualizacao otimista: reflete na tela na hora, sem esperar o servidor
  book.category = nextCategory;
  updateCardCategoryDisplay(bookId, book);

  try {
    await saveBookCategories(bookId, nextCategory);
  } catch (error) {
    book.category = previousCategory;
    updateCardCategoryDisplay(bookId, book);
    categoryQuickPicker.refresh();
    toast(error.message || 'Nao foi possivel atualizar a categoria.', true);
  }
}

function updateCardCategoryDisplay(bookId, book) {
  const chipRow = document.getElementById(`chip-row-${bookId}`);
  if (!chipRow) return;
  chipRow.innerHTML = chipRowMarkup(book);
}

async function saveBookCategories(bookId, category) {
  const book = state.booksById?.get(bookId);
  if (!book) {
    await loadDashboard();
    return;
  }
  const response = await api(`/api/book/${bookId}`, {
    method: 'PUT',
    body: JSON.stringify({
      title: book.title,
      author: book.author,
      book_type: book.book_type,
      status: book.status,
      last_page: book.last_page,
      total_pages: book.total_pages,
      category,
      cover_path: book.cover_path,
      reading_link: book.reading_link,
      notes: book.notes,
      is_favorite: book.is_favorite,
    }),
  });
  const updated = response.book;
  state.booksById.set(bookId, updated);
  updateCardCategoryDisplay(bookId, updated);
}

document.addEventListener('click', async (event) => {
  const actionTarget = event.target.closest('[data-action]');
  if (!actionTarget) return;
  const action = actionTarget.getAttribute('data-action');
  const bookId = Number(actionTarget.getAttribute('data-id'));

  try {
    if (action === 'details') openDetails(bookId);
    if (action === 'continue' || action === 'open-link') await openLink(bookId);
    if (action === 'copy-link') await copyLink(bookId);
    if (action === 'favorite') await toggleFavorite(bookId, actionTarget.getAttribute('data-favorite') === '1');
    if (action === 'toggle-progress') toggleProgress(bookId);
    if (action === 'toggle-expand') toggleCardExpand(bookId, actionTarget);
    if (action === 'quick-category') categoryQuickPicker.open(actionTarget, bookId);
    if (action === 'edit') await openFormWindow(bookId);
    if (action === 'delete') await deleteBook(bookId);
  } catch (error) {
    toast(error.message || 'Nao foi possivel concluir a acao.', true);
  }
});

els.loginTabBtn.addEventListener('click', () => switchAuthPane('login'));
els.registerTabBtn.addEventListener('click', () => switchAuthPane('register'));
els.demoLoginBtn?.addEventListener('click', () => {
  switchAuthPane('login');
  els.loginEmail.value = 'demo@bibliotecavirtual.app';
  els.loginPassword.value = 'demo1234';
  login().catch((error) => toast(error.message, true));
});
els.loginButton.addEventListener('click', () => login().catch((error) => toast(error.message, true)));
els.registerButton.addEventListener('click', () => register().catch((error) => toast(error.message, true)));
els.logoutButton.addEventListener('click', () => logout().catch((error) => toast(error.message, true)));
els.addBookButton.addEventListener('click', () => {
  openFormWindow().catch((error) => toast(error.message, true));
});
els.addCategoryButton?.addEventListener('click', () => {
  openAddCategoryDialog().catch((error) => toast(error.message, true));
});
els.searchInput.addEventListener('input', () => {
  state.search = els.searchInput.value;
  loadDashboard().catch((error) => toast(error.message, true));
});
els.rememberLogin.addEventListener('change', () => {
  persistRememberedLogin();
});
els.loginEmail.addEventListener('input', () => {
  if (els.rememberLogin.checked) {
    persistRememberedLogin();
  }
});

els.collectionTabs.addEventListener('click', (event) => {
  const button = event.target.closest('.segment-btn');
  if (!button) return;
  state.currentCollection = decodeURIComponent(button.getAttribute('data-collection'));
  if (state.currentCollection !== FAVORITES_COLLECTION) {
    state.lastTypeCollection = state.currentCollection;
  }
  state.focusedBookId = null;
  loadDashboard().catch((error) => toast(error.message, true));
});

els.statusFilter.addEventListener('click', (event) => {
  const button = event.target.closest('.segment-btn');
  if (!button) return;
  state.status = button.getAttribute('data-status');
  loadDashboard().catch((error) => toast(error.message, true));
});

els.sortFilter.addEventListener('click', (event) => {
  const button = event.target.closest('.segment-btn');
  if (!button) return;
  state.sort = button.getAttribute('data-sort');
  loadDashboard().catch((error) => toast(error.message, true));
});

els.categoryFilter?.addEventListener('click', (event) => {
  const button = event.target.closest('.tag-chip');
  if (!button) return;
  state.currentCategory = button.getAttribute('data-category') || '';
  loadDashboard().catch((error) => toast(error.message, true));
});

function updateScrollTopButton() {
  if (!els.scrollTopButton) return;
  els.scrollTopButton.classList.toggle('hidden', window.scrollY < 420);
}

els.scrollTopButton?.addEventListener('click', () => {
  window.scrollTo({ top: 0, behavior: 'smooth' });
});

window.addEventListener('scroll', updateScrollTopButton, { passive: true });
updateScrollTopButton();

channel.onmessage = (event) => {
  if (!event?.data?.type) return;
  if ((event.data.type === 'books-changed' || event.data.type === 'categories-changed') && !els.dashboardScreen.classList.contains('hidden')) {
    loadDashboard().catch((error) => toast(error.message, true));
  }
};

document.querySelectorAll('.password-toggle').forEach((button) => {
  button.addEventListener('click', () => {
    const input = document.getElementById(button.dataset.target);
    if (!input) return;
    const visible = input.type === 'text';
    input.type = visible ? 'password' : 'text';
    button.textContent = visible ? 'Mostrar' : 'Ocultar';
    button.classList.toggle('is-active', !visible);
  });
});

bootstrap().catch((error) => toast(error.message, true));
