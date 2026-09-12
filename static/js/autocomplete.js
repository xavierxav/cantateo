/**
 * Autocomplete search functionality for HTMX integration
 */
(function () {
  const searchInput = document.getElementById('navbar-search');
  const dropdown = document.getElementById('autocomplete-dropdown');
  const form = document.getElementById('navbar-search-form');
  if (!searchInput || !dropdown || searchInput.dataset.autocompleteBound === 'true') return;

  const state = {
    activeIndex: -1
  };

  searchInput.dataset.autocompleteBound = 'true';
  dropdown.setAttribute('role', 'listbox');
  dropdown.setAttribute('aria-label', 'Résultats de recherche');

  function getOptions() {
    return Array.from(dropdown.querySelectorAll('[data-autocomplete-option="true"]'));
  }

  function setExpanded(expanded) {
    searchInput.setAttribute('aria-expanded', expanded ? 'true' : 'false');
    dropdown.style.display = expanded ? 'block' : 'none';
  }

  function clearActive() {
    state.activeIndex = -1;
    searchInput.removeAttribute('aria-activedescendant');
    getOptions().forEach(option => {
      option.classList.remove('active');
      option.setAttribute('aria-selected', 'false');
      option.tabIndex = -1;
    });
  }

  function setActive(index) {
    const options = getOptions();
    if (!options.length) {
      clearActive();
      return null;
    }

    const nextIndex = ((index % options.length) + options.length) % options.length;
    state.activeIndex = nextIndex;
    options.forEach((option, idx) => {
      const isActive = idx === nextIndex;
      option.classList.toggle('active', isActive);
      option.setAttribute('aria-selected', isActive ? 'true' : 'false');
      option.tabIndex = isActive ? 0 : -1;
    });

    const active = options[nextIndex];
    searchInput.setAttribute('aria-activedescendant', active.id);
    active.scrollIntoView({ block: 'nearest' });
    return active;
  }

  function updateLayout() {
    const hasContent = Boolean(dropdown.textContent.trim());
    setExpanded(hasContent);
    if (!hasContent) {
      clearActive();
      return;
    }

    const options = getOptions();
    options.forEach(option => {
      option.style.whiteSpace = 'normal';
      option.style.wordBreak = 'break-word';
    });

    if (searchInput.value.length >= 2 && options.length) {
      setActive(state.activeIndex >= 0 ? state.activeIndex : 0);
    } else {
      clearActive();
    }
  }

  document.body.addEventListener('htmx:afterSwap', function (evt) {
    if (evt.detail.target === dropdown) {
      updateLayout();
    }
  });

  document.addEventListener('click', function (e) {
    if (!searchInput.contains(e.target) && !dropdown.contains(e.target)) {
      setExpanded(false);
      clearActive();
    }
  });

  if (form) {
    form.addEventListener('submit', function (e) {
      e.preventDefault();
    });
  }

  searchInput.addEventListener('keydown', function (e) {
    const options = getOptions();
    if (!options.length) {
      if (e.key === 'Escape') {
        setExpanded(false);
      }
      return;
    }

    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setExpanded(true);
      setActive(state.activeIndex < 0 ? 0 : state.activeIndex + 1);
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setExpanded(true);
      setActive(state.activeIndex < 0 ? options.length - 1 : state.activeIndex - 1);
    } else if (e.key === 'Home') {
      e.preventDefault();
      setExpanded(true);
      setActive(0);
    } else if (e.key === 'End') {
      e.preventDefault();
      setExpanded(true);
      setActive(options.length - 1);
    } else if (e.key === 'Enter') {
      const active = state.activeIndex >= 0 ? options[state.activeIndex] : options[0];
      if (active) {
        e.preventDefault();
        window.location.href = active.href;
      }
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setExpanded(false);
      clearActive();
      searchInput.blur();
    }
  });

  searchInput.addEventListener('focus', function () {
    if (searchInput.value.length >= 2 && dropdown.textContent.trim()) {
      updateLayout();
    }
  });

  searchInput.addEventListener('input', function () {
    if (searchInput.value.length < 2) {
      dropdown.innerHTML = '';
      setExpanded(false);
      clearActive();
      return;
    }

    if (dropdown.textContent.trim()) {
      updateLayout();
    }
  });

  updateLayout();
})();
