(function () {
  var choice;
  try { choice = localStorage.getItem('tory-ui-theme'); } catch (error) {}
  var dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  var theme = choice === 'light' || choice === 'dark' ? choice : (dark ? 'dark' : 'light');
  document.documentElement.dataset.theme = theme;
  document.documentElement.dataset.bsTheme = theme;
})();
