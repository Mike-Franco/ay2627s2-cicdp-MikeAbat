/*
 * Runs in <head> before first paint (an external file, so the strict CSP needs
 * no 'unsafe-inline'). An explicit choice ("light" or "dark") is stored in
 * localStorage and set as data-theme; without one, tokens.css follows the
 * operating system through prefers-color-scheme. data-bs-theme always holds the
 * resolved theme for Bootstrap and for scripts such as the Insights charts.
 */
(function () {
  var root = document.documentElement;
  var choice = null;
  try { choice = localStorage.getItem('tory-ui-theme'); } catch (error) { /* storage blocked */ }
  var query = window.matchMedia ? window.matchMedia('(prefers-color-scheme: dark)') : null;
  function apply(value) {
    if (value === 'light' || value === 'dark') {
      root.dataset.theme = value;
      root.dataset.bsTheme = value;
    } else {
      delete root.dataset.theme;
      root.dataset.bsTheme = query && query.matches ? 'dark' : 'light';
    }
  }
  apply(choice);
  if (query && query.addEventListener) {
    query.addEventListener('change', function () { if (!root.dataset.theme) apply(null); });
  }
  window.toryTheme = {
    choice: function () { return root.dataset.theme || 'system'; },
    set: function (value) {
      try {
        if (value === 'light' || value === 'dark') localStorage.setItem('tory-ui-theme', value);
        else localStorage.removeItem('tory-ui-theme');
      } catch (error) { /* storage blocked: still apply for this page */ }
      apply(value);
    }
  };
})();
