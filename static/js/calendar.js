/**
 * Date loading functionality for psalm navigation with Flatpickr (French locale)
 * Guarantees Monday as first day of week and French month names.
 */

function initFlatpickr() {
  const jumpInput = document.getElementById('jump-date');
  if (!jumpInput) return;

  if (jumpInput._flatpickr) {
    jumpInput._flatpickr.destroy();
  }

  // Initialize Flatpickr
  const fp = flatpickr(jumpInput, {
    locale: "fr",
    firstDayOfWeek: 1, // Lundi
    dateFormat: "Y-m-d",
    altInput: false, // Keep original hidden input for HTMX trigger
    disableMobile: "true", // Force Flatpickr UI on mobile to keep French norm
    onChange: function(selectedDates, dateStr) {
      if (dateStr) {
        // Manually dispatch change event for HTMX hx-trigger="change"
        jumpInput.dispatchEvent(new Event('change', { bubbles: true }));
      }
    }
  });

  // Attach to button for manual open
  const btn = document.getElementById('btn-autres-dates');
  if (btn) {
    btn.onclick = () => fp.open();
  }
}

function formatLocalDate(date) {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  return `${year}-${month}-${day}`;
}

// Initial load
document.addEventListener('DOMContentLoaded', initFlatpickr);

// Re-initialize after HTMX swaps (navigation replaces the header)
document.addEventListener('htmx:afterSwap', (event) => {
  if (event.detail.target.id === 'psaume-details' || event.detail.target.id === 'psaume-main' || event.detail.target.querySelector?.('#jump-date')) {
    initFlatpickr();
  }
});

/**
 * Calculates the ISO date string for the upcoming Sunday.
 */
function getNextSunday() {
  const today = new Date();
  const dayOfWeek = today.getDay();
  // If today is Sunday (0), return today.
  if (dayOfWeek === 0) return formatLocalDate(today);
  const nextSunday = new Date(today);
  nextSunday.setDate(today.getDate() + (7 - dayOfWeek));
  return formatLocalDate(nextSunday);
}

window.getNextSunday = getNextSunday;

// Export for manual calls if needed
window.initFlatpickr = initFlatpickr;

document.addEventListener('click', (event) => {
  const control = event.target instanceof Element ? event.target.closest('[data-action="next-sunday"]') : null;
  if (!control) return;
  const input = document.getElementById('jump-date');
  if (!input) return;
  input.value = window.getNextSunday();
  input.dispatchEvent(new Event('change', { bubbles: true }));
});
