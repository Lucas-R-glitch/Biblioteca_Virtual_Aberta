(function () {
  function escapeHtml(text) {
    return String(text ?? '')
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#039;');
  }

  window.escapeHtml = escapeHtml;

  function classifyCover(img) {
    const frame = img.closest('.book-cover-frame, .detail-cover-frame, .cover-preview-frame');
    const frameWidth = frame?.clientWidth || 0;
    const frameHeight = frame?.clientHeight || 0;
    const naturalWidth = img.naturalWidth || 0;
    const naturalHeight = img.naturalHeight || 0;

    img.classList.remove('is-cover-fill', 'is-cover-fit', 'is-cover-soft');

    if (!naturalWidth || !naturalHeight) {
      img.classList.add('is-cover-fit');
      return;
    }

    const ratio = naturalWidth / naturalHeight;
    const portraitLike = ratio >= 0.56 && ratio <= 0.82;
    const hasResolution =
      !frameWidth ||
      !frameHeight ||
      (naturalWidth >= frameWidth * 0.95 && naturalHeight >= frameHeight * 0.95);

    if (portraitLike && hasResolution) {
      img.classList.add('is-cover-fill');
    } else {
      img.classList.add('is-cover-fit');
    }

    if (
      frameWidth &&
      frameHeight &&
      (naturalWidth < frameWidth * 0.82 || naturalHeight < frameHeight * 0.82)
    ) {
      img.classList.add('is-cover-soft');
    }
  }

  function applyAdaptiveCover(img) {
    if (!img) return;

    if (!img.dataset.coverAdaptiveBound) {
      img.dataset.coverAdaptiveBound = '1';
      img.addEventListener('load', () => requestAnimationFrame(() => classifyCover(img)));
      img.addEventListener('error', () => {
        img.classList.remove('is-cover-fill', 'is-cover-fit', 'is-cover-soft');
      });
    }

    if (img.complete && img.naturalWidth) {
      requestAnimationFrame(() => classifyCover(img));
    }
  }

  function setupAdaptiveCovers(root = document) {
    root.querySelectorAll('img[data-adaptive-cover]').forEach((img) => applyAdaptiveCover(img));
  }

  window.applyAdaptiveCover = applyAdaptiveCover;
  window.setupAdaptiveCovers = setupAdaptiveCovers;

  window.addEventListener('resize', () => {
    setupAdaptiveCovers(document);
  });
})();
