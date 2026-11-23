document.addEventListener('DOMContentLoaded', function () {
  // Theme: Light / Dark / System buttons (sidebar profile menu and public header).
  var labels = { light: 'Light', dark: 'Dark', system: 'System' };
  function syncTheme() {
    var current = window.toryTheme ? window.toryTheme.choice() : 'system';
    document.querySelectorAll('[data-set-theme]').forEach(function (button) {
      var value = button.dataset.setTheme;
      var active = value === current;
      button.setAttribute('aria-pressed', String(active));
      button.setAttribute('aria-label', active ? labels[value] + ' theme selected' : 'Use ' + labels[value].toLowerCase() + ' theme');
    });
  }
  document.querySelectorAll('[data-set-theme]').forEach(function (button) {
    button.addEventListener('click', function () {
      if (window.toryTheme) window.toryTheme.set(button.dataset.setTheme);
      syncTheme();
    });
  });
  syncTheme();

  // Menus built on <details>: close on Escape or a click elsewhere.
  var menus = document.querySelectorAll('details[data-menu]');
  document.addEventListener('click', function (event) {
    menus.forEach(function (menu) { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    menus.forEach(function (menu) {
      if (menu.open) { menu.open = false; menu.querySelector('summary').focus(); }
    });
  });

  // Rows-per-page selects submit straight away; the Apply button stays for no-JS.
  document.querySelectorAll('form[data-autosubmit]').forEach(function (form) {
    var button = form.querySelector('[data-autosubmit-button]');
    if (button) button.hidden = true;
    form.querySelectorAll('select').forEach(function (select) {
      select.addEventListener('change', function () { form.submit(); });
    });
  });

  // Mobile sidebar.
  var menu = document.querySelector('.menu-toggle');
  var sidebar = document.querySelector('.sidebar');
  var scrim = document.querySelector('.sidebar-scrim');
  if (menu && sidebar && scrim) {
    var setOpen = function (open) {
      sidebar.classList.toggle('is-open', open);
      menu.setAttribute('aria-expanded', String(open));
      scrim.hidden = !open;
      if (open) sidebar.querySelector('a').focus(); else menu.focus();
    };
    menu.addEventListener('click', function () { setOpen(true); });
    scrim.addEventListener('click', function () { setOpen(false); });
    document.addEventListener('keydown', function (event) {
      if (event.key === 'Escape' && sidebar.classList.contains('is-open')) setOpen(false);
    });
  }
});
