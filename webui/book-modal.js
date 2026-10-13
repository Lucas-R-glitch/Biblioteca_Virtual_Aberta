const DEFAULT_CATEGORY_OPTIONS = [
  'Romance',
  'Aventura',
  'Comedia',
  'Suspense',
];

function sanitizeAuthor(author) {
  const text = (author || '').trim();
  if (!text) return '';
  if (text.toLowerCase().includes('autor') && text.toLowerCase().includes('informado')) {
    return '';
  }
  return text;
}

function normalizeCategoryValue(value) {
  const text = (value || '').trim();
  if (!text || text.toLowerCase() === 'sem categoria') {
    return '';
  }
  return text;
}

function createConfirmDialog() {
  const modal = document.createElement('div');
  modal.className = 'app-modal-overlay confirm-modal-overlay';
  modal.innerHTML = `
    <div class="confirm-modal-card" role="dialog" aria-modal="true" aria-labelledby="confirmModalTitle">
      <p class="eyebrow">Confirmacao</p>
      <h2 id="confirmModalTitle">Confirmar acao</h2>
      <p class="confirm-copy" id="confirmModalMessage">Tem certeza de que deseja continuar?</p>
      <div class="confirm-actions">
        <button type="button" class="btn btn-muted" data-action="cancel">Cancelar</button>
        <button type="button" class="btn btn-danger" data-action="confirm">Excluir</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const els = {
    modal,
    title: modal.querySelector('#confirmModalTitle'),
    message: modal.querySelector('#confirmModalMessage'),
    cancelButton: modal.querySelector('[data-action="cancel"]'),
    confirmButton: modal.querySelector('[data-action="confirm"]'),
  };

  let resolver = null;

  function close(result = false) {
    els.modal.classList.remove('is-open');
    document.body.classList.remove('modal-open');
    if (resolver) {
      resolver(result);
      resolver = null;
    }
  }

  els.cancelButton.addEventListener('click', () => close(false));
  els.confirmButton.addEventListener('click', () => close(true));

  return {
    open({
      title = 'Confirmar acao',
      message = 'Tem certeza de que deseja continuar?',
      confirmText = 'Confirmar',
      cancelText = 'Cancelar',
      tone = 'danger',
    } = {}) {
      els.title.textContent = title;
      els.message.textContent = message;
      els.cancelButton.textContent = cancelText;
      els.confirmButton.textContent = confirmText;
      els.confirmButton.className = `btn ${tone === 'danger' ? 'btn-danger' : 'btn-primary'}`;
      document.body.appendChild(els.modal);
      document.body.classList.add('modal-open');
      els.modal.classList.add('is-open');
      return new Promise((resolve) => {
        resolver = resolve;
      });
    },
  };
}

function createInputDialog() {
  const modal = document.createElement('div');
  modal.className = 'app-modal-overlay input-modal-overlay';
  modal.innerHTML = `
    <div class="confirm-modal-card input-modal-card" role="dialog" aria-modal="true" aria-labelledby="inputModalTitle">
      <p class="eyebrow">Nova tag</p>
      <h2 id="inputModalTitle">Adicionar categoria</h2>
      <p class="confirm-copy" id="inputModalMessage">Informe o nome da nova tag para usar na biblioteca.</p>
      <div class="field input-modal-field">
        <label for="inputModalValue">Nome da tag</label>
        <input type="text" id="inputModalValue" placeholder="Ex: Fantasia, Acao, Suspense">
      </div>
      <div class="confirm-actions input-modal-actions">
        <button type="button" class="btn btn-muted" data-action="cancel">Cancelar</button>
        <button type="button" class="btn btn-primary" data-action="confirm">Adicionar</button>
      </div>
    </div>
  `;
  document.body.appendChild(modal);

  const els = {
    modal,
    title: modal.querySelector('#inputModalTitle'),
    message: modal.querySelector('#inputModalMessage'),
    input: modal.querySelector('#inputModalValue'),
    cancelButton: modal.querySelector('[data-action="cancel"]'),
    confirmButton: modal.querySelector('[data-action="confirm"]'),
  };

  let resolver = null;

  function close(value = null) {
    els.modal.classList.remove('is-open');
    document.body.classList.remove('modal-open');
    if (resolver) {
      resolver(value);
      resolver = null;
    }
  }

  els.cancelButton.addEventListener('click', () => close(null));
  els.confirmButton.addEventListener('click', () => close(els.input.value.trim()));
  els.input.addEventListener('keydown', (event) => {
    if (event.key === 'Enter') {
      event.preventDefault();
      close(els.input.value.trim());
    }
  });

  return {
    open({
      title = 'Adicionar categoria',
      message = 'Informe o nome da nova tag.',
      label = 'Nome da tag',
      placeholder = 'Ex: Fantasia',
      confirmText = 'Adicionar',
      initialValue = '',
    } = {}) {
      els.title.textContent = title;
      els.message.textContent = message;
      const labelNode = els.input.closest('.field')?.querySelector('label');
      if (labelNode) labelNode.textContent = label;
      els.input.placeholder = placeholder;
      els.input.value = initialValue;
      els.confirmButton.textContent = confirmText;
      document.body.appendChild(els.modal);
      document.body.classList.add('modal-open');
      els.modal.classList.add('is-open');
      requestAnimationFrame(() => {
        els.input.focus();
        els.input.select();
      });
      return new Promise((resolve) => {
        resolver = resolve;
      });
    },
  };
}

function createBookModal(options = {}) {
  const confirmDialog = window.createConfirmDialog?.() || createConfirmDialog();
  const inputDialog = window.createInputDialog?.() || createInputDialog();
  const modal = document.createElement('div');
  modal.className = 'app-modal-overlay';
  modal.innerHTML = `
    <div class="app-modal-dialog" role="dialog" aria-modal="true" aria-labelledby="modalFormTitle">
      <section class="form-card modal-form-card">
        <div class="form-heading form-heading-inline">
          <div>
            <p class="eyebrow">Organizacao da estante</p>
            <h1 id="modalFormTitle">Adicionar livro</h1>
            <p class="subtitle" id="modalFormSubtitle">Preencha os campos para salvar o livro com capa, status, progresso e link.</p>
          </div>
          <button type="button" class="mini-btn modal-close-btn" data-action="close-modal">Fechar</button>
        </div>

        <form id="modalBookForm" class="modern-form">
          <div class="form-layout">
            <section class="form-section">
              <h2>Informacoes principais</h2>
              <div class="field-grid field-grid-2">
                <div class="field">
                  <label for="modalTitleInput">Titulo</label>
                  <input type="text" id="modalTitleInput" placeholder="Nome da obra">
                </div>
                <div class="field">
                  <label for="modalAuthorInput">Autor</label>
                  <input type="text" id="modalAuthorInput" placeholder="Autor ou grupo">
                </div>
              </div>

              <input type="hidden" id="modalTypeInput" value="Livro">

              <div class="field-grid field-grid-2">
                <div class="field">
                  <label for="modalStatusInput">Status</label>
                  <select id="modalStatusInput">
                    <option value="Quero Ler">Quero Ler</option>
                    <option value="Lendo">Lendo</option>
                    <option value="Conclu?do">Concluido</option>
                  </select>
                </div>
                <div class="field">
                  <div class="field-label-row">
                    <label>Categorias</label>
                    <button type="button" class="mini-btn field-add-btn" id="modalAddCategoryButton">+ Tag</button>
                  </div>
                  <div class="tag-balloon-picker" id="modalCategoryPicker"></div>
                </div>
              </div>

              <div class="field">
                <label for="modalCoverInput">Capa (URL ou caminho local)</label>
                <input type="text" id="modalCoverInput" placeholder="Cole o link da capa ou informe o caminho local">
              </div>
              <div class="cover-picker">
                <input type="file" id="modalCoverFileInput" accept="image/*">
                <button type="button" class="btn btn-secondary" id="modalCoverFileButton">Escolher imagem</button>
                <span>Ou cole uma imagem copiada no modal com Ctrl+V.</span>
              </div>

              <div class="field-grid field-grid-2">
                <div class="field">
                  <label for="modalLastPageInput">Ultima pagina / capitulo</label>
                  <input type="text" id="modalLastPageInput" placeholder="Ex: 111">
                </div>
                <div class="field">
                  <label for="modalTotalPagesInput">Total de paginas</label>
                  <input type="text" id="modalTotalPagesInput" placeholder="Ex: 143">
                </div>
              </div>

              <div class="field">
                <label for="modalLinkInput">Link salvo</label>
                <input type="text" id="modalLinkInput" placeholder="https://...">
              </div>

              <div class="field">
                <label for="modalNotesInput">Observacoes</label>
                <textarea id="modalNotesInput" placeholder="Alguma anotacao importante sobre a leitura..."></textarea>
              </div>
            </section>

            <aside class="form-preview-panel">
              <h2>Previa da capa</h2>
              <div class="cover-preview-frame" id="modalCoverDropZone" tabindex="0">
                <img id="modalCoverPreview" data-adaptive-cover="form" alt="Previa da capa">
                <div class="cover-fallback" id="modalCoverFallback">Sem imagem</div>
              </div>
              <p class="subtitle" id="modalPreviewCaption">Use URL, caminho local, arquivo do computador ou imagem colada.</p>
            </aside>
          </div>

          <div class="form-actions">
            <button type="submit" class="btn btn-primary" id="modalSaveButton">Salvar</button>
            <button type="button" class="btn btn-secondary" id="modalCancelButton">Cancelar</button>
          </div>
        </form>
      </section>
    </div>
  `;
  document.body.appendChild(modal);

  const state = {
    bookId: null,
    defaultType: 'Livro',
    categories: [...DEFAULT_CATEGORY_OPTIONS],
    selectedCategories: new Set(),
  };

  const els = {
    modal,
    title: modal.querySelector('#modalFormTitle'),
    subtitle: modal.querySelector('#modalFormSubtitle'),
    form: modal.querySelector('#modalBookForm'),
    titleInput: modal.querySelector('#modalTitleInput'),
    authorInput: modal.querySelector('#modalAuthorInput'),
    typeInput: modal.querySelector('#modalTypeInput'),
    statusInput: modal.querySelector('#modalStatusInput'),
    categoryPicker: modal.querySelector('#modalCategoryPicker'),
    addCategoryButton: modal.querySelector('#modalAddCategoryButton'),
    coverInput: modal.querySelector('#modalCoverInput'),
    coverFileInput: modal.querySelector('#modalCoverFileInput'),
    coverFileButton: modal.querySelector('#modalCoverFileButton'),
    coverDropZone: modal.querySelector('#modalCoverDropZone'),
    lastPageInput: modal.querySelector('#modalLastPageInput'),
    totalPagesInput: modal.querySelector('#modalTotalPagesInput'),
    linkInput: modal.querySelector('#modalLinkInput'),
    notesInput: modal.querySelector('#modalNotesInput'),
    coverPreview: modal.querySelector('#modalCoverPreview'),
    coverFallback: modal.querySelector('#modalCoverFallback'),
    previewCaption: modal.querySelector('#modalPreviewCaption'),
    cancelButton: modal.querySelector('#modalCancelButton'),
    closeButton: modal.querySelector('[data-action="close-modal"]'),
  };

  function coverSourceForPreview(value) {
    const source = (value || '').trim();
    if (!source) return '';
    return `/api/cover?path=${encodeURIComponent(source)}`;
  }

  function updatePreview() {
    const source = coverSourceForPreview(els.coverInput.value);
    if (!source) {
      els.coverPreview.removeAttribute('src');
      els.coverPreview.style.display = 'none';
      els.coverFallback.classList.remove('hidden');
      return;
    }
    els.coverPreview.onload = () => {
      els.coverPreview.style.display = 'block';
      els.coverFallback.classList.add('hidden');
      window.applyAdaptiveCover?.(els.coverPreview);
    };
    els.coverPreview.onerror = () => {
      els.coverPreview.removeAttribute('src');
      els.coverPreview.style.display = 'none';
      els.coverFallback.classList.remove('hidden');
    };
    els.coverPreview.src = source;
  }

  function parseCategoryList(raw) {
    return (raw || '')
      .split(',')
      .map((value) => value.trim())
      .filter((value) => value && value.toLowerCase() !== 'sem categoria');
  }

  function renderCategoryPicker() {
    const esc = window.escapeHtml || ((value) => String(value ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;'));
    const merged = [];
    const seen = new Set();
    [...DEFAULT_CATEGORY_OPTIONS, ...(state.categories || [])].forEach((value) => {
      const normalized = normalizeCategoryValue(value);
      if (!normalized) return;
      const key = normalized.toLowerCase();
      if (seen.has(key)) return;
      seen.add(key);
      merged.push(normalized);
    });

    if (!merged.length) {
      els.categoryPicker.innerHTML = '<p class="tag-picker-empty">Nenhuma tag cadastrada ainda. Use o botao "+ Tag" para criar a primeira.</p>';
      return;
    }

    els.categoryPicker.innerHTML = merged.map((name) => {
      const isActive = state.selectedCategories.has(name.toLowerCase());
      return `<button type="button" class="tag-chip ${isActive ? 'is-active' : ''}" data-category-option="${esc(name)}">${esc(name)}</button>`;
    }).join('');
  }

  els.categoryPicker.addEventListener('click', (event) => {
    const chip = event.target.closest('.tag-chip');
    if (!chip) return;
    const value = chip.getAttribute('data-category-option');
    const key = value.toLowerCase();
    if (state.selectedCategories.has(key)) {
      state.selectedCategories.delete(key);
    } else {
      state.selectedCategories.add(key);
    }
    chip.classList.toggle('is-active');
  });

  async function loadCategoryOptions(selected = '') {
    const categories = (await options.getCategoryOptions?.()) || DEFAULT_CATEGORY_OPTIONS;
    state.categories = categories;
    state.selectedCategories = new Set(parseCategoryList(selected).map((value) => value.toLowerCase()));
    renderCategoryPicker();
  }

  function selectedCategoriesDisplay() {
    const merged = [...DEFAULT_CATEGORY_OPTIONS, ...(state.categories || [])];
    const byKey = new Map(merged.map((value) => [normalizeCategoryValue(value).toLowerCase(), normalizeCategoryValue(value)]));
    return Array.from(state.selectedCategories)
      .map((key) => byKey.get(key) || key)
      .join(', ');
  }

  function resetForm(defaultType) {
    state.bookId = null;
    state.defaultType = 'Livro';
    els.title.textContent = 'Adicionar livro';
    els.subtitle.textContent = 'Preencha os campos para salvar o livro com capa, status, progresso e link.';
    els.form.reset();
    els.typeInput.value = 'Livro';
    els.statusInput.value = 'Quero Ler';
    state.selectedCategories = new Set();
    renderCategoryPicker();
    els.previewCaption.textContent = 'Use URL, caminho local, arquivo do computador ou imagem colada.';
    updatePreview();
  }

  function fillForm(book) {
    state.bookId = book.id;
    els.title.textContent = 'Editar livro';
    els.subtitle.textContent = 'Atualize capa, status, paginas, categoria e link mantendo tudo salvo nesta biblioteca.';
    els.titleInput.value = book.title || '';
    els.authorInput.value = sanitizeAuthor(book.author);
    els.typeInput.value = 'Livro';
    els.statusInput.value = book.status === 'Conclu?do' ? 'Conclu?do' : (book.status || 'Quero Ler');
    state.selectedCategories = new Set(parseCategoryList(book.category).map((value) => value.toLowerCase()));
    renderCategoryPicker();
    els.coverInput.value = book.cover_path || '';
    els.lastPageInput.value = book.last_page || '';
    els.totalPagesInput.value = book.total_pages || '';
    els.linkInput.value = book.reading_link || '';
    els.notesInput.value = book.notes || '';
    els.previewCaption.textContent = 'A capa continua local ao app e sera salva junto com os demais dados.';
    updatePreview();
  }

  function payloadFromForm() {
    return {
      title: els.titleInput.value.trim(),
      author: els.authorInput.value.trim(),
      book_type: 'Livro',
      status: els.statusInput.value,
      category: selectedCategoriesDisplay(),
      cover_path: els.coverInput.value.trim(),
      last_page: els.lastPageInput.value.trim(),
      total_pages: els.totalPagesInput.value.trim(),
      reading_link: els.linkInput.value.trim(),
      notes: els.notesInput.value.trim(),
    };
  }

  async function uploadCoverFile(file) {
    if (!file || !file.type?.startsWith('image/')) {
      throw new Error('Escolha um arquivo de imagem valido para a capa.');
    }
    const data_url = await new Promise((resolve, reject) => {
      const reader = new FileReader();
      reader.onload = () => resolve(String(reader.result || ''));
      reader.onerror = () => reject(new Error('Nao foi possivel ler a imagem selecionada.'));
      reader.readAsDataURL(file);
    });
    const response = await options.api('/api/cover-upload', {
      method: 'POST',
      body: JSON.stringify({ data_url, filename: file.name || 'capa' }),
    });
    els.coverInput.value = response.path || '';
    els.previewCaption.textContent = 'Imagem salva localmente em covers_cache.';
    updatePreview();
    options.toast?.('Capa adicionada com sucesso.');
  }

  function firstImageFromClipboard(event) {
    const items = Array.from(event.clipboardData?.items || []);
    const imageItem = items.find((item) => item.type?.startsWith('image/'));
    return imageItem?.getAsFile?.() || null;
  }

  function openBase() {
    document.body.appendChild(els.modal);
    document.body.classList.add('modal-open');
    els.modal.classList.add('is-open');
    requestAnimationFrame(() => els.titleInput.focus());
  }

  function close() {
    els.modal.classList.remove('is-open');
    document.body.classList.remove('modal-open');
  }

  async function requestNewCategory() {
    const categoryName = await inputDialog.open({
      title: 'Adicionar categoria',
      message: 'Crie uma nova tag para usar na busca e no cadastro das obras.',
      label: 'Nome da tag',
      placeholder: 'Ex: Fantasia, Poesia, Estudos',
      confirmText: 'Adicionar',
    });

    if (!categoryName) return;

    const response = await options.api('/api/categories', {
      method: 'POST',
      body: JSON.stringify({ name: categoryName }),
    });

    state.categories = (await options.getCategoryOptions?.()) || DEFAULT_CATEGORY_OPTIONS;
    state.selectedCategories.add((response.category || categoryName).toLowerCase());
    renderCategoryPicker();
    options.channel?.postMessage({ type: 'categories-changed' });
    options.toast?.('Nova tag adicionada com sucesso.');
  }

  async function submitPayload(allowDuplicate = false) {
    const payload = {
      ...payloadFromForm(),
      allow_duplicate: allowDuplicate,
    };

    const response = state.bookId
      ? await options.api(`/api/book/${state.bookId}`, {
          method: 'PUT',
          body: JSON.stringify(payload),
        })
      : await options.api('/api/books', {
          method: 'POST',
          body: JSON.stringify(payload),
        });

    options.channel?.postMessage({ type: 'books-changed' });
    options.toast?.(state.bookId ? 'Livro atualizado com sucesso.' : 'Livro adicionado com sucesso.');
    close();
    await options.onSaved?.(response.book);
  }

  async function save(event) {
    event.preventDefault();
    try {
      await submitPayload(false);
    } catch (error) {
      if (error?.status === 409 && error?.payload?.duplicate) {
        const duplicateTitle = error.payload?.existing_book?.title || els.titleInput.value.trim();
        const keep = await confirmDialog.open({
          title: 'Obra ja cadastrada',
          message: `A obra \"${duplicateTitle}\" ja existe na sua biblioteca. Deseja manter mesmo assim ou corrigir o titulo?`,
          confirmText: 'Manter',
          cancelText: 'Corrigir',
          tone: 'primary',
        });
        if (keep) {
          await submitPayload(true);
          return;
        }
        els.titleInput.focus();
        els.titleInput.select();
        return;
      }
      throw error;
    }
  }

  async function openCreate(defaultType) {
    resetForm(defaultType);
    await loadCategoryOptions('');
    openBase();
  }

  async function openEdit(bookId, fallbackType) {
    resetForm(fallbackType);
    const payload = await options.api(`/api/book/${bookId}`);
    await loadCategoryOptions(payload.book?.category || '');
    fillForm(payload.book);
    openBase();
  }

  els.form.addEventListener('submit', (event) => {
    save(event).catch((error) => options.toast?.(error.message || 'Nao foi possivel salvar o livro.', true));
  });
  els.coverInput.addEventListener('input', updatePreview);
  els.coverFileButton.addEventListener('click', () => els.coverFileInput.click());
  els.coverFileInput.addEventListener('change', () => {
    uploadCoverFile(els.coverFileInput.files?.[0]).catch((error) => options.toast?.(error.message, true));
    els.coverFileInput.value = '';
  });
  modal.addEventListener('paste', (event) => {
    const file = firstImageFromClipboard(event);
    if (!file) return;
    event.preventDefault();
    uploadCoverFile(file).catch((error) => options.toast?.(error.message, true));
  });
  els.coverDropZone.addEventListener('dragover', (event) => {
    event.preventDefault();
    els.coverDropZone.classList.add('is-dragging');
  });
  els.coverDropZone.addEventListener('dragleave', () => {
    els.coverDropZone.classList.remove('is-dragging');
  });
  els.coverDropZone.addEventListener('drop', (event) => {
    event.preventDefault();
    els.coverDropZone.classList.remove('is-dragging');
    uploadCoverFile(event.dataTransfer?.files?.[0]).catch((error) => options.toast?.(error.message, true));
  });
  els.cancelButton.addEventListener('click', close);
  els.closeButton.addEventListener('click', close);
  els.addCategoryButton.addEventListener('click', () => {
    requestNewCategory().catch((error) => options.toast?.(error.message || 'Nao foi possivel adicionar a tag.', true));
  });

  return {
    openCreate,
    openEdit,
    close,
  };
}

window.createBookModal = createBookModal;
window.createConfirmDialog = createConfirmDialog;
window.createInputDialog = createInputDialog;
