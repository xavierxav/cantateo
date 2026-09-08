(function () {
  'use strict';

  function normalize(value) {
    return (value || '')
      .toString()
      .normalize('NFD')
      .replace(/[\u0300-\u036f]/g, '')
      .toLowerCase();
  }

  function getRows(picker) {
    return Array.from(picker.querySelectorAll('input[type="checkbox"]'))
      .map((input) => {
        const label = input.closest('label');
        return input.closest('li') || (label ? label.parentElement : null);
      })
      .filter(Boolean);
  }

  function updateCount(picker) {
    const counter = document.querySelector('[data-moment-selected-count]');
    if (!counter) {
      return;
    }
    const selected = picker.querySelectorAll('input[type="checkbox"]:checked').length;
    counter.textContent = String(selected);
  }

  function filterRows(search, picker) {
    const query = normalize(search.value);
    getRows(picker).forEach((row) => {
      row.hidden = query && !normalize(row.textContent).includes(query);
    });
  }

  function preventSearchSubmit(search) {
    search.addEventListener('keydown', (event) => {
      if (event.key === 'Enter') {
        event.preventDefault();
        event.stopPropagation();
      }
    });
  }

  document.addEventListener('DOMContentLoaded', () => {
    const search = document.querySelector('[data-moment-search]');
    const picker = document.querySelector('[data-moment-picker]');
    if (!search || !picker) {
      return;
    }

    search.addEventListener('input', () => filterRows(search, picker));
    search.addEventListener('search', () => filterRows(search, picker));
    preventSearchSubmit(search);
    picker.addEventListener('change', (event) => {
      if (event.target.matches('input[type="checkbox"]')) {
        updateCount(picker);
      }
    });
    updateCount(picker);
  });
}());
