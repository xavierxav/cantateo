/**
 * PDF Auto-render for detail pages
 * Detects the PDF viewer and triggers initialization if togglePdfViewer is available
 */
document.addEventListener('DOMContentLoaded', () => {
    const v = document.querySelector('[id^="pdf-viewer-"]');
    if (v && typeof togglePdfViewer === 'function') {
        const btn = document.querySelector('[id^="pdf-toggle-btn-"]');
        togglePdfViewer(v.id, btn, v.dataset.pdfUrl);
    }
});

// HTMX support: re-check on swap
document.addEventListener('htmx:afterSwap', function(evt) {
    const v = document.querySelector('[id^="pdf-viewer-"]');
    // On the homepage index, we don't always want auto-render, 
    // but on detail pages or specific swaps we might.
    // For now, let's keep it specific to detail pages via detail_base inheritance if possible.
});
