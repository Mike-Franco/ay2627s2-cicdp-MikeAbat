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

  // Menus built on <details> (TORY-68): Enter/Space on the button opens, Escape closes,
  // ArrowUp/ArrowDown/Home/End move between items, Tab or a click elsewhere closes.
  // Inside a scrolling table the list is placed with position:fixed so it is never clipped.
  var menus = document.querySelectorAll('details[data-menu]');
  function menuItems(menu) { return Array.prototype.slice.call(menu.querySelectorAll('[role="menuitem"]')); }
  function placeMenu(menu) {
    var list = menu.querySelector('.more-items');
    var summary = menu.querySelector('summary');
    if (!list || !menu.closest('.table-scroll, .ph-actions')) return;
    list.classList.add('is-fixed');
    var rect = summary.getBoundingClientRect();
    var width = list.offsetWidth;
    var left = Math.max(8, Math.min(rect.right - width, window.innerWidth - width - 8));
    var top = rect.bottom + 4;
    if (top + list.offsetHeight > window.innerHeight - 8) top = Math.max(8, rect.top - list.offsetHeight - 4);
    list.style.left = left + 'px';
    list.style.top = top + 'px';
  }
  function closeMenu(menu, focusButton) {
    if (!menu.open) return;
    menu.open = false;
    if (focusButton) menu.querySelector('summary').focus();
  }
  menus.forEach(function (menu) {
    var summary = menu.querySelector('summary');
    summary.setAttribute('aria-expanded', 'false');
    menuItems(menu).forEach(function (item) { item.setAttribute('tabindex', '-1'); });
    menu.addEventListener('toggle', function () {
      summary.setAttribute('aria-expanded', String(menu.open));
      if (!menu.open) return;
      menus.forEach(function (other) { if (other !== menu) other.open = false; });
      placeMenu(menu);
      var items = menuItems(menu);
      if (items.length) items[0].focus();
    });
    summary.addEventListener('keydown', function (event) {
      if ((event.key === 'ArrowDown' || event.key === 'ArrowUp') && !menu.open) {
        event.preventDefault();
        menu.open = true;
      }
    });
    menu.addEventListener('keydown', function (event) {
      var items = menuItems(menu);
      var index = items.indexOf(document.activeElement);
      if (event.key === 'Escape') { event.preventDefault(); closeMenu(menu, true); return; }
      if (!menu.open || index === -1) return;
      var next = null;
      if (event.key === 'ArrowDown') next = items[(index + 1) % items.length];
      else if (event.key === 'ArrowUp') next = items[(index - 1 + items.length) % items.length];
      else if (event.key === 'Home') next = items[0];
      else if (event.key === 'End') next = items[items.length - 1];
      else if (event.key === 'Tab') { closeMenu(menu, false); return; }
      else if (event.key === ' ') { event.preventDefault(); document.activeElement.click(); return; }
      if (next) { event.preventDefault(); next.focus(); }
    });
  });
  document.addEventListener('click', function (event) {
    menus.forEach(function (menu) { if (menu.open && !menu.contains(event.target)) menu.open = false; });
  });
  function closeFixedMenus() {
    menus.forEach(function (menu) {
      var list = menu.querySelector('.more-items');
      if (menu.open && list && list.classList.contains('is-fixed')) menu.open = false;
    });
  }
  window.addEventListener('resize', closeFixedMenus);
  document.querySelectorAll('.table-scroll').forEach(function (scroller) {
    scroller.addEventListener('scroll', closeFixedMenus, { passive: true });
  });
  window.addEventListener('scroll', closeFixedMenus, { passive: true });

  // File drop zones (TORY-69): show the chosen or dropped file name. The input covers the zone,
  // so clicking and dropping both work natively; this only updates the label.
  document.querySelectorAll('[data-file-drop]').forEach(function (zone) {
    var input = zone.querySelector('input[type="file"]');
    var label = zone.querySelector('[data-file-name]');
    if (!input || !label) return;
    var empty = label.textContent;
    function show() {
      var file = input.files && input.files[0];
      label.textContent = file ? file.name + ' · ' + Math.max(1, Math.round(file.size / 1024)) + ' KB' : empty;
      zone.classList.toggle('has-file', Boolean(file));
    }
    input.addEventListener('change', show);
    input.addEventListener('dragenter', function () { zone.classList.add('is-over'); });
    ['dragleave', 'drop'].forEach(function (name) {
      input.addEventListener(name, function () { zone.classList.remove('is-over'); });
    });
    show();
  });

  // "Select all" for checklists (TORY-68). The button stays hidden without JavaScript.
  document.querySelectorAll('[data-select-all-scope]').forEach(function (scope) {
    var button = scope.querySelector('[data-select-all]');
    var boxes = scope.querySelectorAll('input[type="checkbox"]:not([disabled])');
    if (!button || !boxes.length) return;
    button.hidden = false;
    function sync() {
      var all = Array.prototype.every.call(boxes, function (box) { return box.checked; });
      button.textContent = all ? 'Clear all' : 'Select all';
    }
    button.addEventListener('click', function () {
      var all = Array.prototype.every.call(boxes, function (box) { return box.checked; });
      boxes.forEach(function (box) { box.checked = !all; });
      sync();
    });
    boxes.forEach(function (box) { box.addEventListener('change', sync); });
    sync();
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
    if (!tip.closest('.table-scroll')) return;
    var bubble = tip.querySelector('.tip');
    function place() {
      var rect = tip.getBoundingClientRect();
      bubble.classList.add('is-fixed');
      var width = bubble.offsetWidth || 280;
      bubble.style.left = Math.max(8, Math.min(rect.left - 8, window.innerWidth - width - 8)) + 'px';
      bubble.style.top = (rect.bottom + 6) + 'px';
    }
    tip.addEventListener('mouseenter', place);
    tip.addEventListener('focusin', place);
    tip.querySelector('.help-btn').addEventListener('click', place);
  });
  tips.forEach(function (tip) {
    tip.addEventListener('focusout', function () { tip.classList.remove('dismissed'); });
    tip.addEventListener('mouseleave', function () { tip.classList.remove('dismissed'); });
  });

  // Filter and rows-per-page forms apply on change; the Apply button is the no-JavaScript fallback.
  document.querySelectorAll('form[data-autosubmit]').forEach(function (form) {
    var button = form.querySelector('[data-autosubmit-button]');
    if (button) button.hidden = true;
    // Text and search boxes submit with Enter; selects, dates and checkboxes apply as soon as they change.
    form.querySelectorAll('select, input[type="date"], input[type="checkbox"]').forEach(function (field) {
      field.addEventListener('change', function () { form.submit(); });
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
