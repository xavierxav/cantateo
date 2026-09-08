document.addEventListener('DOMContentLoaded', function() {
    var overlay = document.getElementById('site-banner-overlay');
    var closeBtn = document.getElementById('banner-close-btn');
    if (!overlay || !closeBtn) return;

    var bannerId = overlay.dataset.bannerId;

    if (localStorage.getItem('banner-dismissed-id') === bannerId) {
        overlay.classList.add('d-none');
    }

    closeBtn.addEventListener('click', function() {
        localStorage.setItem('banner-dismissed-id', bannerId);
        overlay.classList.add('d-none');
    });
});
