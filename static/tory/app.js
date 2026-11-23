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

  // "?" help tips: CSS opens them on hover and focus; a tap toggles them, Escape or a tap elsewhere closes.
  var tips = document.querySelectorAll('.help');
  function closeTips(except) {
    tips.forEach(function (tip) {
      if (tip !== except && tip.classList.contains('open')) {
        tip.classList.remove('open');
        tip.querySelector('.help-btn').setAttribute('aria-expanded', 'false');
      }
    });
  }
  tips.forEach(function (tip) {
    var button = tip.querySelector('.help-btn');
    button.addEventListener('click', function (event) {
      event.stopPropagation();
      var open = !tip.classList.contains('open');
      closeTips(tip);
      tip.classList.toggle('open', open);
      button.setAttribute('aria-expanded', String(open));
    });
  });
  document.addEventListener('click', function () { closeTips(null); });
  document.addEventListener('keydown', function (event) {
    if (event.key !== 'Escape') return;
    var focused = document.activeElement && document.activeElement.closest ? document.activeElement.closest('.help') : null;
    closeTips(null);
    if (focused) focused.classList.add('dismissed');
  });
  tips.forEach(function (tip) {
    tip.addEventListener('focusout', function () { tip.classList.remove('dismissed'); });
    tip.addEventListener('mouseleave', function () { tip.classList.remove('dismissed'); });
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
