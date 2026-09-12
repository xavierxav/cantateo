/**
 * PDF Viewer using PDF.js
 * Provides cross-browser, cross-device PDF rendering
 */

if (typeof pdfjsLib !== 'undefined') {
  pdfjsLib.GlobalWorkerOptions.workerSrc = window.CANTATEO_PDF_WORKER_SRC || '/static/vendor/pdfjs/pdf.worker.min.js';
}

const pdfViewers = {};

function getViewerState(viewerId) {
  return pdfViewers[viewerId] || null;
}

function destroyPdfViewer(viewerId) {
  const state = pdfViewers[viewerId];
  if (!state) return;

  if (state.scrollHandler) {
    window.removeEventListener('scroll', state.scrollHandler);
  }
  if (state.resizeHandler) {
    window.removeEventListener('resize', state.resizeHandler);
  }
  if (state.loadingTask && typeof state.loadingTask.destroy === 'function') {
    state.loadingTask.destroy().catch(() => {});
  }
  delete pdfViewers[viewerId];
}

function destroyAllPdfViewers(root) {
  if (root && root.querySelectorAll) {
    root.querySelectorAll('[id^="pdf-viewer-"]').forEach(viewer => {
      destroyPdfViewer(viewer.id);
    });
    return;
  }

  Object.keys(pdfViewers).forEach(destroyPdfViewer);
}

function syncPdfControls(viewerId) {
  const viewer = pdfViewers[viewerId];
  if (!viewer || !viewer.viewerEl || !viewer.controlsEl) return;

  const rect = viewer.viewerEl.getBoundingClientRect();
  const winH = window.innerHeight;

  if (rect.top > winH || rect.bottom < 80) {
    viewer.controlsEl.style.setProperty('display', 'none', 'important');
    return;
  }

  viewer.controlsEl.style.setProperty('display', 'flex', 'important');
  if (rect.bottom < winH) {
    viewer.controlsEl.style.setProperty('position', 'absolute', 'important');
    viewer.controlsEl.style.setProperty('bottom', '20px', 'important');
    viewer.controlsEl.style.setProperty('left', '50%', 'important');
  } else {
    viewer.controlsEl.style.setProperty('position', 'fixed', 'important');
    viewer.controlsEl.style.setProperty('bottom', '20px', 'important');
    viewer.controlsEl.style.setProperty('left', `${rect.left + (rect.width / 2)}px`, 'important');
  }
}

function attachViewerListeners(viewerId) {
  const state = pdfViewers[viewerId];
  if (!state || state.scrollHandler || state.resizeHandler) return;

  state.scrollHandler = () => syncPdfControls(viewerId);
  state.resizeHandler = () => syncPdfControls(viewerId);

  window.addEventListener('scroll', state.scrollHandler, { passive: true });
  window.addEventListener('resize', state.resizeHandler);
}

window.togglePdfViewer = function (viewerId, button, pdfUrl) {
  const viewer = document.getElementById(viewerId);
  if (!viewer) return;

  const btnText = button && typeof button.querySelector === 'function' ? button.querySelector('.btn-text') : null;
  const partitionId = viewerId.split('-').pop();
  const aelfText = document.getElementById(`aelf-text-${partitionId}`);
  const parentCard = viewer.closest('.card');
  const isHidden = window.getComputedStyle(viewer).display === 'none';
  const openLabel = 'Masquer la partition';
  const closeLabel = 'Afficher la partition';

  if (button) {
    button.setAttribute('aria-expanded', isHidden ? 'true' : 'false');
    button.setAttribute('aria-label', isHidden ? openLabel : closeLabel);
  }

  if (isHidden) {
    if (aelfText) aelfText.style.setProperty('display', 'none', 'important');
    viewer.style.setProperty('display', 'block', 'important');
    if (btnText) btnText.textContent = openLabel;
    if (parentCard) parentCard.classList.add('pdf-active');

    if (!pdfViewers[viewerId]) {
      loadPdf(viewerId, pdfUrl || viewer.dataset.pdfUrl);
    } else {
      syncPdfControls(viewerId);
    }
  } else {
    viewer.style.setProperty('display', 'none', 'important');
    if (aelfText) aelfText.style.setProperty('display', 'block', 'important');
    if (btnText) btnText.textContent = closeLabel;
    if (parentCard) parentCard.classList.remove('pdf-active');
  }
};

async function loadPdf(viewerId, url) {
  const viewerEl = document.getElementById(viewerId);
  const partitionId = viewerId.replace('pdf-viewer-', '');
  const canvas = document.getElementById(`pdf-canvas-${partitionId}`);
  const loadingEl = document.getElementById(`pdf-loading-${partitionId}`);
  const controlsEl = document.getElementById(`pdf-controls-${partitionId}`);

  if (!canvas || typeof pdfjsLib === 'undefined') {
    if (loadingEl) {
      loadingEl.replaceChildren(createPdfMessage('Erreur de chargement du viewer PDF'));
    }
    return;
  }

  try {
    const loadingTask = pdfjsLib.getDocument(url);
    const pdf = await loadingTask.promise;

    pdfViewers[viewerId] = {
      pdf,
      loadingTask,
      currentPage: 1,
      scale: 1.5,
      partitionId,
      manualScale: false,
      viewerEl,
      controlsEl,
      syncControls: () => syncPdfControls(viewerId)
    };

    const pageCountEl = document.getElementById(`pdf-page-count-${partitionId}`);
    if (pageCountEl) {
      pageCountEl.textContent = pdf.numPages;
    }

    if (loadingEl) loadingEl.style.setProperty('display', 'none', 'important');
    if (controlsEl) {
      controlsEl.style.zIndex = '2000';
      controlsEl.style.background = 'rgba(255, 255, 255, 0.95)';
      controlsEl.style.backdropFilter = 'blur(8px)';
      controlsEl.style.padding = '10px 20px';
      controlsEl.style.borderRadius = '50px';
      controlsEl.style.boxShadow = '0 8px 32px rgba(0,0,0,0.15)';
      controlsEl.style.border = '1px solid rgba(0,0,0,0.1)';
      controlsEl.style.width = 'max-content';
      controlsEl.style.transform = 'translateX(-50%)';
      attachViewerListeners(viewerId);
    }

    await renderPage(viewerId);
    syncPdfControls(viewerId);
    setTimeout(() => syncPdfControls(viewerId), 100);
  } catch (error) {
    console.error('Error loading PDF:', error);
    if (loadingEl) {
      const message = createPdfMessage('Erreur de chargement du PDF. ');
      const link = document.createElement('a');
      link.href = url;
      link.target = '_blank';
      link.rel = 'noopener';
      link.textContent = 'Ouvrir dans un nouvel onglet';
      message.appendChild(link);
      loadingEl.replaceChildren(message);
    }
  }
}

function createPdfMessage(text) {
  const message = document.createElement('p');
  message.className = 'text-danger';
  message.textContent = text;
  return message;
}

async function renderPage(viewerId) {
  const viewer = getViewerState(viewerId);
  if (!viewer) return;

  const { pdf, currentPage, scale, partitionId } = viewer;
  const canvas = document.getElementById(`pdf-canvas-${partitionId}`);
  const container = document.getElementById(`pdf-canvas-container-${partitionId}`);

  if (!canvas || !container) return;

  try {
    const page = await pdf.getPage(currentPage);
    const dpr = window.devicePixelRatio || 1;
    let finalScale = viewer.scale || 1.5;

    if (!viewer.manualScale) {
      let containerWidth = container.clientWidth;
      if (!containerWidth) {
        const viewerEl = document.getElementById(viewerId);
        containerWidth = viewerEl ? viewerEl.clientWidth : (window.innerWidth - 32);
      }

      const viewport = page.getViewport({ scale: 1 });
      finalScale = (containerWidth - 60) / viewport.width;
      if (finalScale > 2) finalScale = 2;
      if (finalScale < 0.5) finalScale = 0.5;

      viewer.scale = finalScale;
    }

    const renderViewport = page.getViewport({ scale: finalScale * dpr });
    const cssViewport = page.getViewport({ scale: finalScale });
    const context = canvas.getContext('2d');
    canvas.height = renderViewport.height;
    canvas.width = renderViewport.width;
    canvas.style.width = cssViewport.width + 'px';
    canvas.style.height = cssViewport.height + 'px';

    await page.render({
      canvasContext: context,
      viewport: renderViewport
    }).promise;

    const pageNumEl = document.getElementById(`pdf-page-num-${partitionId}`);
    if (pageNumEl) {
      pageNumEl.textContent = currentPage;
    }
  } catch (error) {
    console.error('Error rendering page:', error);
  }
}

window.pdfPrevPage = function (partitionId) {
  const viewerId = `pdf-viewer-${partitionId}`;
  const viewer = getViewerState(viewerId);
  if (!viewer || viewer.currentPage <= 1) return;

  viewer.currentPage--;
  renderPage(viewerId);
};

window.pdfNextPage = function (partitionId) {
  const viewerId = `pdf-viewer-${partitionId}`;
  const viewer = getViewerState(viewerId);
  if (!viewer || viewer.currentPage >= viewer.pdf.numPages) return;

  viewer.currentPage++;
  renderPage(viewerId);
};

window.pdfZoomIn = function (partitionId) {
  const viewerId = `pdf-viewer-${partitionId}`;
  const viewer = getViewerState(viewerId);
  if (!viewer) return;

  const currentScale = parseFloat(viewer.scale) || 1.0;
  if (currentScale >= 5) return;

  viewer.scale = currentScale + 0.25;
  viewer.manualScale = true;
  renderPage(viewerId);
};

window.pdfZoomOut = function (partitionId) {
  const viewerId = `pdf-viewer-${partitionId}`;
  const viewer = getViewerState(viewerId);
  if (!viewer) return;

  const currentScale = parseFloat(viewer.scale) || 1.0;
  if (currentScale <= 0.25) return;

  viewer.scale = currentScale - 0.25;
  viewer.manualScale = true;
  renderPage(viewerId);
};

window.destroyPdfViewer = destroyPdfViewer;
window.destroyAllPdfViewers = destroyAllPdfViewers;

function autoOpenPdfViewers(root) {
  const scope = root && root.querySelectorAll ? root : document;
  scope.querySelectorAll('[id^="pdf-viewer-"][data-auto-open="true"]').forEach(viewer => {
    const partitionId = viewer.id.replace('pdf-viewer-', '');
    const btn = document.getElementById(`pdf-toggle-btn-${partitionId}`);
    if (window.getComputedStyle(viewer).display === 'none') {
      window.togglePdfViewer(viewer.id, btn, viewer.dataset.pdfUrl);
    }
  });
}

document.addEventListener('DOMContentLoaded', () => {
  autoOpenPdfViewers(document);
});

document.addEventListener('click', (event) => {
  const control = event.target instanceof Element ? event.target.closest('[data-pdf-action]') : null;
  if (!control) return;

  const action = control.dataset.pdfAction;
  if (action === 'toggle') {
    window.togglePdfViewer(control.dataset.viewerId, control, control.dataset.pdfUrl);
  } else if (action === 'zoom-out') {
    window.pdfZoomOut(control.dataset.partitionId);
  } else if (action === 'zoom-in') {
    window.pdfZoomIn(control.dataset.partitionId);
  } else if (action === 'prev') {
    window.pdfPrevPage(control.dataset.partitionId);
  } else if (action === 'next') {
    window.pdfNextPage(control.dataset.partitionId);
  }
});

document.addEventListener('htmx:afterSwap', function (evt) {
  autoOpenPdfViewers(evt.detail.target || document);
});

document.addEventListener('htmx:beforeSwap', function (evt) {
  if (evt.detail && evt.detail.target) {
    destroyAllPdfViewers(evt.detail.target);
  } else {
    destroyAllPdfViewers();
  }
});

window.addEventListener('beforeunload', () => {
  destroyAllPdfViewers();
});
