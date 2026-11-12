document.addEventListener('DOMContentLoaded', function () {
  function syncTheme() {
    document.querySelectorAll('[data-set-theme]').forEach(function (button) {
      var active = button.dataset.setTheme === document.documentElement.dataset.theme;
      button.setAttribute('aria-pressed', String(active));
      button.setAttribute('aria-label', active ? button.textContent.trim() + ' mode selected' : 'Switch to ' + button.textContent.trim() + ' mode');
    });
  }
  document.querySelectorAll('[data-set-theme]').forEach(function (button) {
    button.addEventListener('click', function () {
      var theme = button.dataset.setTheme;
      document.documentElement.dataset.theme = theme;
      document.documentElement.dataset.bsTheme = theme;
      try { localStorage.setItem('tory-ui-theme', theme); } catch (error) {}
      syncTheme();
    });
  });
  syncTheme();

  var menu = document.querySelector('.menu-toggle');
  var sidebar = document.querySelector('.sidebar');
  var scrim = document.querySelector('.sidebar-scrim');
  if (menu && sidebar && scrim) {
    function setOpen(open) {
      sidebar.classList.toggle('is-open', open);
      menu.setAttribute('aria-expanded', String(open));
      scrim.hidden = !open;
      if (open) sidebar.querySelector('a').focus(); else menu.focus();
    }
    menu.addEventListener('click', function () { setOpen(true); });
    scrim.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (event) { if (event.key === 'Escape' && sidebar.classList.contains('is-open')) setOpen(false); });
  }
});
