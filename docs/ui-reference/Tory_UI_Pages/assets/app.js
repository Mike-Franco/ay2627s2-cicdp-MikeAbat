
(function () {
  "use strict";

  const data = window.ToryData;
  const params = new URLSearchParams(window.location.search);
  const page = document.body.dataset.page;
  const managerPages = ["import", "catalogue", "adjust", "dispose", "reorder", "status"];
  const productPages = ["stock", "history", "forecast", "receive", "issue", "adjust", "dispose", "reorder", "status"];
  const storedRole = readPreference("tory-ui-role");
  const requestedRole = params.get("role") || storedRole;
  const role = requestedRole === "staff" ? "staff" : "manager";
  const persona = data.personas[role];
  const requestedInventory = params.get("inventory") || readPreference("tory-ui-inventory") || "pharmacy";
  const inventory = data.inventories.find(function (item) { return item.id === requestedInventory; }) || data.inventories[0];
  const inventoryAllowed = persona.inventories.includes(inventory.id);
  const inventoryProducts = data.products.filter(function (item) { return item.inventory === inventory.id; });
  const requestedProduct = params.get("product");
  const matchedProduct = inventoryProducts.find(function (item) { return item.id === requestedProduct; });
  const product = matchedProduct || inventoryProducts[0];
  const productMissing = requestedProduct && !matchedProduct && productPages.includes(page);
  let pageNumber = 1;
  const pageSize = 6;

  function readPreference(key) {
    try { return localStorage.getItem(key); } catch (error) { return null; }
  }

  function savePreference(key, value) {
    try { localStorage.setItem(key, value); } catch (error) {}
  }

  function escapeHtml(value) {
    return String(value).replace(/[&<>"']/g, function (character) {
      return {"&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"}[character];
    });
  }

  function icon(name, size) {
    return '<svg width="' + (size || 18) + '" height="' + (size || 18) +
      '" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' +
      (window.ToryIcons[name] || window.ToryIcons.box) + '</svg>';
  }

  function href(file, options) {
    const settings = options || {};
    const query = new URLSearchParams({
      inventory: settings.inventory || inventory.id,
      role: role,
      theme: document.documentElement.dataset.theme
    });
    if (settings.product !== false) {
      query.set("product", settings.product || product.id);
    }
    return file + "?" + query.toString();
  }

  function link(file, text, className, options) {
    return '<a class="' + (className || "") + '" href="' + escapeHtml(href(file, options)) + '">' + text + '</a>';
  }

  function badge(text, type) {
    return '<span class="badge ' + (type || "neutral") + '"><span class="badge-dot"></span>' + escapeHtml(text) + '</span>';
  }

  function reorderState(item) {
    if (item.reorderPoint === null) {
      return {label: "Point unavailable", full: "Reorder point unavailable", type: "neutral", key: "unavailable"};
    }
    if (item.available <= item.reorderPoint) {
      return {label: "At / below point", full: "At or below reorder point", type: "low", key: "low"};
    }
    return {label: "Above point", full: "Above reorder point", type: "good", key: "good"};
  }

  function productSymbol(item, large) {
    return '<span class="product-symbol ' + escapeHtml(item.color) + '"' +
      (large ? ' style="width:44px;height:44px"' : "") + '>' + icon(item.symbol, large ? 24 : 21) + '</span>';
  }

  function themeControl() {
    return '<div class="theme-control" role="group" aria-label="Colour theme">' +
      '<button type="button" data-theme-choice="light" aria-label="Use light mode" aria-pressed="false">' + icon("sun", 14) + '</button>' +
      '<button type="button" data-theme-choice="dark" aria-label="Use dark mode" aria-pressed="false">' + icon("moon", 14) + '</button></div>';
  }

  function brand() {
    return '<a class="brand" href="' + escapeHtml(href("index.html")) + '" aria-label="Tory products">' +
      '<span class="brand-mark">' + icon("box", 22) + '</span>' +
      '<span><span class="brand-word">Tory</span><span class="brand-tagline" style="display:block">Inventory made simple.</span></span></a>';
  }

  function sidebar() {
    const choices = data.inventories.filter(function (item) { return persona.inventories.includes(item.id); });
    const inventoryActive = page !== "catalogue";
    return '<aside class="sidebar" id="sidebar" aria-label="Workspace navigation">' + brand() +
      '<div class="switcher"><button class="inventory-switch" id="inventory-switch" aria-expanded="false" aria-controls="inventory-options">' +
      '<span class="location-mark">' + icon("store", 18) + '</span>' +
      '<span><span class="switcher-name">' + escapeHtml(inventoryAllowed ? inventory.name : "Choose inventory") + '</span>' +
      '<span class="switcher-label">' + escapeHtml(data.business) + '</span></span><span class="switch-chevron">' + icon("chevron", 13) + '</span></button>' +
      '<div class="switcher-popover" id="inventory-options" hidden>' +
      choices.map(function (item) {
        return link("index.html", icon("store", 14) + escapeHtml(item.name) + (item.id === inventory.id ? '<span style="margin-left:auto">' + icon("check", 13) + '</span>' : ""),
          "", {inventory:item.id, product:false});
      }).join("") +
      link("inventories.html", "View assigned inventories " + icon("arrow", 12), "", {product:false}) + '</div></div>' +
      '<nav><div class="nav-section"><p class="group-label">WORKSPACE</p>' +
      '<a class="nav-link ' + (inventoryActive ? "active" : "") + '" href="' + escapeHtml(href("index.html")) + '"' +
      (inventoryActive ? ' aria-current="page"' : "") + '>' + icon("box", 17) + 'Inventory<span class="nav-count">' + (inventoryAllowed ? inventoryProducts.length : "—") + '</span></a></div>' +
      (role === "manager" ? '<div class="nav-section"><p class="group-label">MANAGE</p>' +
        '<a class="nav-link ' + (page === "catalogue" ? "active" : "") + '" href="' + escapeHtml(href("catalogue.html")) + '"' +
        (page === "catalogue" ? ' aria-current="page"' : "") + '>' + icon("catalogue", 17) + 'Catalogue</a></div>' : "") +
      '</nav><div class="sidebar-bottom"><div class="inventory-note"><span class="group-label" style="margin:0">YOUR WORKSPACE</span>' +
      '<strong>' + persona.inventories.length + ' assigned ' + (persona.inventories.length === 1 ? "inventory" : "inventories") + '</strong>' +
      'Stock stays organised by location.</div>' +
      '<div class="user-card"><span class="avatar">' + escapeHtml(persona.initials) + '</span><span><span class="user-name">' +
      escapeHtml(persona.name) + '</span><span class="user-role">' + escapeHtml(persona.role) + '</span></span>' +
      '<a class="sign-out" href="' + escapeHtml(href("login.html")) + '" aria-label="Sign out of preview">' + icon("logout", 16) + '</a></div></div></aside>';
  }

  function breadcrumb(title) {
    return '<div class="breadcrumb" aria-label="Breadcrumb">' +
      link("inventories.html", "Inventory", "crumb-first") + '<span class="crumb-first">' + icon("right", 10) + '</span>' +
      link("index.html", escapeHtml(inventoryAllowed ? inventory.name : "Choose inventory")) + icon("right", 10) +
      '<span class="current">' + escapeHtml(title) + '</span></div>';
  }

  function previewDialogs() {
    return '<dialog id="preview-dialog"><div class="dialog-body"><div class="dialog-head"><div><p class="eyebrow">DESIGN PREVIEW</p><h2>Explore both roles</h2></div>' +
      '<button class="icon-button" data-close-dialog aria-label="Close preview settings">' + icon("close", 17) + '</button></div>' +
      '<p class="muted small">Sample accounts and inventory for 11 November 2026. Choose an account to review the navigation and available controls.</p>' +
      ["manager", "staff"].map(function (key) {
        const account = data.personas[key];
        return '<button class="preview-persona" data-persona="' + key + '" aria-pressed="' + (role === key) + '"><span class="avatar">' + account.initials +
          '</span><span><strong>' + account.name + '</strong><small>' + account.role + ' · ' + account.inventories.length + ' assigned ' +
          (account.inventories.length === 1 ? "inventory" : "inventories") + '</small></span>' + (role === key ? icon("check", 16) : "") + '</button>';
      }).join("") + '</div></dialog>' +
      '<dialog id="action-dialog"><div class="dialog-body" id="action-dialog-body"></div></dialog>';
  }

  function footer() {
    return '<footer class="preview-footer"><span class="preview-dot"></span>Tory UI preview · Sample stock for 11 Nov 2026</footer>';
  }

  function shell(title, content) {
    document.getElementById("app").innerHTML = '<a class="skip-link" href="#main">Skip to content</a>' +
      '<button class="drawer-overlay" id="drawer-overlay" aria-label="Close navigation" tabindex="-1"></button>' + sidebar() +
      '<div class="workspace"><header class="topbar"><button class="menu-toggle" id="menu-toggle" aria-label="Open navigation" aria-expanded="false" aria-controls="sidebar">' + icon("menu", 17) +
      '</button>' + breadcrumb(title) + '<div class="topbar-end"><button class="preview-control" id="preview-control" aria-label="Preview settings and sample accounts">' +
      '<span class="preview-dot"></span>Sample workspace</button>' + themeControl() + '</div></header>' +
      '<main class="content" id="main" tabindex="-1">' + content + footer() + '</main></div>' + previewDialogs();
  }

  function heading(title, description, actions, eyebrow) {
    return '<div class="page-heading"><div><p class="eyebrow">' + escapeHtml(eyebrow || inventory.name + " INVENTORY") + '</p><h1>' +
      escapeHtml(title) + '</h1><p>' + escapeHtml(description) + '</p></div><div class="heading-actions">' + (actions || "") + '</div></div>';
  }

  function stat(label, value, caption, iconName, emphasize) {
    return '<div class="stat-card ' + (emphasize ? "emphasized" : "") + '"><div class="stat-top"><span>' + escapeHtml(label) +
      '</span>' + icon(iconName || "box", 16) + '</div><div class="stat-value">' + value +
      '</div><div class="stat-caption">' + escapeHtml(caption) + '</div></div>';
  }

  function stockTabs() {
    const tabs = [["stock", "product.html", "Stock", "box"], ["history", "history.html", "Stock history", "history"], ["forecast", "forecast.html", "Demand forecast", "chart"]];
    return '<nav class="tabs" aria-label="Product pages">' + tabs.map(function (tab) {
      return '<a href="' + escapeHtml(href(tab[1])) + '"' + (page === tab[0] ? ' aria-current="page"' : "") + '>' +
        icon(tab[3], 14) + tab[2] + '</a>';
    }).join("") + '</nav>';
  }

  function productHeader(actions) {
    return link("index.html", icon("back", 13) + "Back to products", "back-link") +
      '<div class="page-heading product-heading"><div><div class="product-heading-title"><h1>' + escapeHtml(product.name) + '</h1>' + badge("Active", "good") +
      '</div><p>' + escapeHtml(product.sku) + ' · ' + escapeHtml(inventory.name) + ' · ' + escapeHtml(product.unit) +
      '</p></div><div class="heading-actions">' + (actions || "") + '</div></div>' + stockTabs();
  }

  function permissionPage(title, description) {
    return '<section class="panel empty-state">' + icon("shield", 36) + '<h2>' + escapeHtml(title) + '</h2><p>' +
      escapeHtml(description) + '</p>' + link("index.html", "Back to products " + icon("arrow", 13), "button primary", {inventory:inventoryAllowed ? inventory.id : persona.inventories[0], product:false}) + '</section>';
  }

  function productsPage() {
    const low = inventoryProducts.filter(function (item) { return reorderState(item).key === "low"; }).length;
    const unavailable = inventoryProducts.filter(function (item) { return item.available === 0; }).length;
    const quarantine = inventoryProducts.filter(function (item) { return item.quarantined > 0; }).length;
    const actions = role === "manager" ? link("import.html", icon("upload", 14) + "Import CSV", "button") : "";
    return heading("Products", "A clear view of stock in " + inventory.name + ".", actions) +
      '<div class="stats-grid">' + stat("Linked products", inventoryProducts.length, "In this inventory", "box", true) +
      stat("At / below reorder point", low, "Products needing attention", "warning") +
      stat("No available stock", unavailable, "Products with 0 to issue", "minus") +
      stat("With quarantined stock", quarantine, "Products with held stock", "shield") + '</div>' +
      '<section class="panel" aria-label="Products"><div class="toolbar"><label class="search-field">' + icon("search", 15) +
      '<span class="sr-only">Search products by name or SKU</span><input id="product-search" type="search" placeholder="Search products or SKU…" autocomplete="off"></label>' +
      '<div class="toolbar-spacer"><label class="sr-only" for="stock-filter">Filter by reorder status</label><select class="filter-select" id="stock-filter">' +
      '<option value="all">All reorder states</option><option value="low">At / below point</option><option value="good">Above point</option><option value="unavailable">Point unavailable</option></select>' +
      '<label class="sr-only" for="product-sort">Sort products</label><select class="filter-select" id="product-sort"><option value="name">Name A–Z</option><option value="available-up">Available ↑</option><option value="available-down">Available ↓</option></select></div></div>' +
      '<div class="table-scroll"><table><caption class="sr-only">Product quantities and reorder states for ' + escapeHtml(inventory.name) +
      '</caption><thead><tr><th scope="col">Product</th><th scope="col">SKU</th><th scope="col" class="numeric">Physical</th><th scope="col" class="numeric">Quarantined</th><th scope="col" class="numeric">Available</th><th scope="col">Reorder status</th><th scope="col"><span class="sr-only">Actions</span></th></tr></thead>' +
      '<tbody id="products-body"></tbody></table></div><div class="pagination"><span id="product-results" role="status"></span><div class="pagination-controls">' +
      '<button class="button compact" id="previous-products">' + icon("back", 12) + 'Previous</button><span class="page-number" id="product-page"></span><button class="button compact" id="next-products">Next' + icon("arrow", 12) + '</button></div></div></section>' +
      '<p class="explanation">' + icon("info", 13) + '<span>Available stock reflects what can be issued. Quarantined units remain part of physical stock.</span></p>';
  }

  function renderProductRows() {
    const search = document.getElementById("product-search");
    if (!search) return;
    const term = search.value.trim().toLowerCase();
    const filter = document.getElementById("stock-filter").value;
    const sort = document.getElementById("product-sort").value;
    const filtered = inventoryProducts.filter(function (item) {
      return (item.name + " " + item.sku).toLowerCase().includes(term) && (filter === "all" || reorderState(item).key === filter);
    }).sort(function (first, second) {
      if (sort === "available-up") return first.available - second.available;
      if (sort === "available-down") return second.available - first.available;
      return first.name.localeCompare(second.name);
    });
    const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
    pageNumber = Math.min(pageNumber, totalPages);
    const start = (pageNumber - 1) * pageSize;
    const rows = filtered.slice(start, start + pageSize);
    document.getElementById("products-body").innerHTML = rows.map(function (item) {
      const status = reorderState(item);
      return '<tr><td><div class="product-cell">' + productSymbol(item) + '<div>' +
        link("product.html", escapeHtml(item.name), "product-link", {product:item.id}) +
        '<div class="product-category">' + escapeHtml(item.category) + '</div></div></div></td><td class="sku">' + escapeHtml(item.sku) +
        '</td><td class="numeric"><span class="quantity">' + item.physical + '</span><span class="unit">' + item.unit + '</span></td>' +
        '<td class="numeric"><span class="quantity ' + (item.quarantined ? "negative" : "muted") + '">' + item.quarantined + '</span><span class="unit">' + item.unit + '</span></td>' +
        '<td class="numeric"><span class="quantity available">' + item.available + '</span><span class="unit">' + item.unit + '</span></td>' +
        '<td><span title="' + escapeHtml(status.full + (item.reorderPoint !== null ? " · " + item.reorderPoint + " " + item.unit : "")) + '">' +
        badge(status.label, status.type) + '</span></td><td><button class="icon-button" data-product-menu="' + item.id + '" aria-label="Actions for ' +
        escapeHtml(item.name) + '">' + icon("more", 16) + '</button></td></tr>';
    }).join("") || '<tr><td colspan="7"><div class="empty-state"><h2>No matching products</h2><p>Try a different name, SKU or reorder filter.</p><button class="text-button" id="clear-filters">Clear filters</button></div></td></tr>';
    document.getElementById("product-results").textContent = filtered.length ? "Showing " + (start + 1) + "–" + Math.min(start + pageSize, filtered.length) + " of " + filtered.length + " products" : "0 products";
    document.getElementById("product-page").textContent = pageNumber + " / " + totalPages;
    document.getElementById("previous-products").disabled = pageNumber === 1;
    document.getElementById("next-products").disabled = pageNumber === totalPages;
  }

  function batches(item) {
    if (item.id === "bandages") {
      return [
        {id:"B-017-01",quantity:12,received:"9 Nov 2026",expiry:"31 Jan 2027",state:"Available"},
        {id:"B-017-02",quantity:4,received:"9 Nov 2026",expiry:"30 Apr 2027",state:"Available"},
        {id:"B-017-03",quantity:4,received:"1 Nov 2026",expiry:"10 Nov 2026",state:"Quarantined"}
      ];
    }
    const rows = [];
    if (item.available) rows.push({id:"B-" + item.sku + "-01",quantity:item.available,received:"9 Nov 2026",expiry:item.expiry ? "30 Jun 2027" : "Undated",state:"Available"});
    if (item.quarantined) rows.push({id:"B-" + item.sku + "-02",quantity:item.quarantined,received:"1 Nov 2026",expiry:"10 Nov 2026",state:"Quarantined"});
    return rows;
  }

  function detailList(items) {
    return '<dl class="detail-list">' + items.map(function (item) {
      return '<div><dt>' + escapeHtml(item[0]) + '</dt><dd>' + item[1] + '</dd></div>';
    }).join("") + '</dl>';
  }

  function stockPage() {
    const actions = link("receive.html", icon("plus", 14) + "Receive stock", "button primary") +
      link("issue.html", icon("minus", 14) + "Issue stock", "button") +
      (role === "manager" ? '<button class="button" data-product-menu="' + product.id + '" aria-label="More stock actions">' + icon("more", 16) + '</button>' : "");
    const rows = batches(product);
    return productHeader(actions) + '<div class="balance-grid">' +
      stat("Available to issue", product.available + '<span class="balance-unit">' + product.unit + '</span>', "Eligible stock for this inventory", "check", true) +
      stat("Physical stock", product.physical + '<span class="balance-unit">' + product.unit + '</span>', "All recorded stock on hand", "box") +
      stat("Quarantined stock", product.quarantined + '<span class="balance-unit">' + product.unit + '</span>', "Held back from issue", "shield") + '</div>' +
      '<div class="two-columns"><section class="panel"><div class="panel-title"><div><h2>Stock by batch</h2><p>Eligible dated batches are issued by earliest expiry.</p></div>' +
      badge(rows.length + " batches", "neutral") + '</div><div class="table-scroll"><table><thead><tr><th scope="col">Batch</th><th scope="col">Received</th><th scope="col">Expiry date</th><th scope="col" class="numeric">Quantity</th><th scope="col">State</th></tr></thead><tbody>' +
      rows.map(function (batch) {
        return '<tr><td><strong class="small">' + batch.id + '</strong></td><td class="small muted">' + batch.received + '</td><td class="small">' + batch.expiry +
          '</td><td class="numeric">' + batch.quantity + '<span class="unit">' + product.unit + '</span></td><td>' +
          badge(batch.state, batch.state === "Available" ? "good" : "error") + '</td></tr>';
      }).join("") + (rows.length ? "" : '<tr><td colspan="5"><div class="empty-state"><p>No stock batches in this inventory.</p></div></td></tr>') +
      '</tbody></table></div></section><aside class="section-stack"><section class="panel"><div class="panel-title"><h2>Product details</h2></div><div class="card-body">' +
      detailList([["SKU",product.sku],["Category",escapeHtml(product.category)],["Base unit",product.unit],["Expiry tracking",product.expiry ? "Required" : "Optional"],["Inventory",inventory.name]]) +
      '</div></section><div class="note-box"><strong>Availability at a glance</strong><p>Quarantined stock is included in physical stock. Use the available balance when issuing or reviewing a reorder.</p></div></aside></div>';
  }

  function historyPage() {
    const activity = [
      {type:"Issued",icon:"minus",quantity:"−2",tone:"negative",time:"11 Nov 2026 · 09:40",actor:"Jamie Lim",reason:"Daily stock usage"},
      {type:"Quarantined",icon:"shield",quantity:String(product.quarantined || 0),tone:"muted",time:"11 Nov 2026 · 00:00",actor:"Expiry process",reason:"Expired batch · effective 11 Nov, recorded 00:03"},
      {type:"Received",icon:"plus",quantity:"+" + Math.max(product.physical, 2),tone:"positive",time:"9 Nov 2026 · 11:12",actor:"Alex Tan",reason:"Delivery received"},
      {type:"Count adjusted",icon:"edit",quantity:"+2",tone:"positive",time:"8 Nov 2026 · 14:25",actor:"Alex Tan",reason:"Shelf count reconciliation"},
      {type:"Disposed",icon:"trash",quantity:"−2",tone:"negative",time:"7 Nov 2026 · 10:18",actor:"Alex Tan",reason:"Expired stock"}
    ].filter(function (event) { return event.type !== "Quarantined" || product.quarantined > 0; });
    return productHeader() + '<section class="panel"><div class="panel-title"><div><h2>Stock history</h2><p>Recent sample activity · Times shown in Singapore time</p></div>' +
      '<label><span class="sr-only">Filter history by event</span><select class="filter-select" id="history-filter"><option value="all">All event types</option>' +
      activity.map(function (event) { return '<option>' + event.type + '</option>'; }).join("") + '</select></label></div>' +
      '<div class="table-scroll"><table><thead><tr><th scope="col">Event</th><th scope="col" class="numeric">Quantity</th><th scope="col">When · SGT</th><th scope="col">Recorded by</th><th scope="col">Reason / detail</th></tr></thead><tbody>' +
      activity.map(function (event) {
        return '<tr data-history-type="' + event.type + '"><td><div class="event-type"><span class="event-icon">' + icon(event.icon, 14) + '</span>' + event.type +
          '</div></td><td class="numeric ' + event.tone + '"><strong>' + event.quantity + '</strong><span class="unit">' + product.unit +
          '</span></td><td class="small">' + event.time + '</td><td class="small">' + event.actor + '</td><td class="small muted" style="max-width:270px;white-space:normal">' +
          event.reason + '</td></tr>';
      }).join("") + '</tbody></table></div><div class="pagination"><span>' + activity.length + ' sample events</span><span>Most recent first</span></div></section>';
  }


  function forecastPage() {
    const complete = product.demand !== null;
    const maximum = Math.max.apply(null, product.series.filter(function (value) { return value !== null; })) || 1;
    const state = reorderState(product);
    const actions = role === "manager" ? link("reorder-settings.html", icon("settings", 14) + "Reorder settings", "button") : "";
    const observationRows = product.series.map(function (value, index) {
      return '<li><span>' + data.days[index] + ' 2026</span><span class="muted">' + (value === null ? "—" : value + " " + product.unit) +
        '</span>' + badge(value === null ? "Incomplete" : "Verified", value === null ? "low" : "good") + '</li>';
    }).join("");
    return productHeader(actions) + '<div class="forecast-layout"><div class="section-stack"><section class="panel"><div class="panel-title"><div><h2>Seven-day demand</h2>' +
      '<p>4–10 November 2026 · Complete Singapore calendar days</p></div>' + badge(complete ? "7 / 7 days verified" : "6 / 7 days verified", complete ? "good" : "low") +
      '</div><div class="demand-chart" role="img" aria-label="Daily demand. Values are listed below for each day.">' +
      product.series.map(function (value) {
        return '<div class="demand-day"><span class="chart-value">' + (value === null ? "—" : value) + '</span><span class="bar" style="height:' +
          (value === null ? 12 : Math.max(3, value / maximum * 110)) + 'px;' + (value === null ? "background:var(--line)" : "") + '"></span></div>';
      }).join("") + '</div><div class="chart-labels">' + data.days.map(function (day) { return '<span>' + day + '</span>'; }).join("") + '</div></section>' +
      '<section class="panel"><div class="panel-title"><div><h2>Observation coverage</h2><p>Verified zero-demand days count towards coverage.</p></div></div><div class="card-body"><ul class="observation-list">' +
      observationRows + '</ul></div></section></div><aside class="section-stack"><section class="panel"><div class="card-body"><p class="eyebrow">ESTIMATED DAILY DEMAND</p>' +
      (complete ? '<div class="forecast-value">' + product.demand.toFixed(2) + '</div><p class="muted small">' + product.unit + ' per day</p>' :
        '<h2 style="margin:12px 0">Forecast unavailable</h2><p class="muted small">6 November is marked incomplete. An eligible seven-day observation window is needed.</p>') +
      '<div style="margin-top:23px">' + detailList([["Available stock",product.available + " " + product.unit],["Lead time",product.lead + " days"],["Safety stock",product.safety + " " + product.unit],
        ["Reorder point",complete ? product.reorderPoint + " " + product.unit : "Unavailable"]]) + '</div></div></section>' +
      '<div class="' + (state.key === "low" ? "attention-box" : "note-box") + '"><h3>' + escapeHtml(state.full) + '</h3><p style="margin:0">' +
      (complete ? (state.key === "low" ? "Available stock has reached the reorder threshold. Review replenishment for this product." : "Available stock is above the current reorder threshold.") :
        "Tory needs an eligible forecast before it can show a reorder recommendation.") + '</p></div></aside></div>';
  }

  function contextCard() {
    return '<div class="form-context">' + productSymbol(product, true) + '<div><strong>' + escapeHtml(product.name) +
      '</strong><span class="muted small">' + escapeHtml(product.sku) + ' · ' + escapeHtml(inventory.name) + '</span></div></div>';
  }

  function field(id, label, input, help) {
    return '<div class="field"><label for="' + id + '">' + label + '</label>' + input +
      (help ? '<p class="field-help" id="' + id + '-help">' + help + '</p>' : "") + '</div>';
  }

  function quantityField(label, minimum, maximum) {
    return field("quantity", label, '<div class="input-with-unit"><input id="quantity" name="quantity" type="number" inputmode="numeric" step="1" min="' + minimum + '"' +
      (maximum !== undefined ? ' max="' + maximum + '"' : "") + ' required placeholder="0"><span>' + product.unit + '</span></div>', "Enter a whole number of base units.");
  }

  function transactionPage() {
    const types = {
      receive:{title:"Receive stock",description:"Record stock arriving at this inventory.",button:"Review receipt",hint:"Receiving adds a batch. The product’s expiry policy applies to the receipt."},
      issue:{title:"Issue stock",description:"Record stock leaving this inventory.",button:"Review issue",hint:"Eligible dated batches are issued by earliest expiry, followed by undated batches in receipt order."},
      adjust:{title:"Adjust batch count",description:"Record a physical count for one eligible batch.",button:"Review adjustment",hint:"Enter the final counted quantity for the selected batch. An adjustment records a correction with your reason."},
      dispose:{title:"Dispose stock",description:"Record disposal from an eligible quarantined batch.",button:"Review disposal",hint:"Disposal records the quantity removed from the selected batch and the reason."}
    };
    const config = types[page];
    let inputs = "";
    let blocked = false;
    if (page === "receive") {
      inputs = quantityField("Quantity received", 1) + field("expiry", "Expiry date" + (product.expiry ? " · Required" : " · Optional"),
        '<input id="expiry" name="expiry" type="date" min="2026-11-12"' + (product.expiry ? " required" : "") + '>',
        product.expiry ? "This product requires an expiry date later than the sample workspace date." : "An undated batch can be recorded for this product.");
    }
    if (page === "issue") {
      blocked = product.available === 0;
      inputs = quantityField("Quantity to issue", 1, Math.max(1, product.available));
    }
    if (page === "adjust" || page === "dispose") {
      const eligible = batches(product).filter(function (batch) {
        return page === "dispose" ? batch.state === "Quarantined" : batch.state === "Available";
      });
      blocked = eligible.length === 0;
      inputs = field("batch", "Batch", '<select id="batch" name="batch" required>' +
        '<option value="">Select a batch</option>' + eligible.map(function (batch) {
          return '<option value="' + batch.id + '" data-quantity="' + batch.quantity + '">' + batch.id + " · " + batch.quantity + " " + product.unit + " · " + batch.expiry + '</option>';
        }).join("") + '</select>', "Current quantities are shown beside each batch.") +
        quantityField(page === "adjust" ? "Final counted quantity" : "Quantity to dispose", page === "adjust" ? 0 : 1) +
        field("reason", "Reason", '<textarea id="reason" name="reason" maxlength="500" required placeholder="Describe the reason for this stock change"></textarea>');
    }
    return link("product.html", icon("back", 13) + "Back to stock", "back-link") + heading(config.title, config.description) +
      '<div class="form-layout"><section class="panel form-panel"><div class="form-heading"><h2>Stock details</h2><p>' + escapeHtml(inventory.name) + ' inventory</p></div>' +
      contextCard() + '<form id="preview-form" data-operation="' + page + '">' + inputs +
      (blocked ? '<div class="note-box">' + (page === "issue" ? "This product has no available stock to issue." : "There are no eligible batches for this action in the sample inventory.") + '</div>' : "") +
      '<p class="form-error" id="form-error" role="alert"></p><div class="form-actions">' + link("product.html", "Cancel", "button") +
      '<button class="button primary" type="submit"' + (blocked ? " disabled" : "") + '>' + config.button + icon("arrow", 13) + '</button></div>' +
      '<div id="form-result" aria-live="polite"></div></form></section><aside class="section-stack"><section class="panel"><div class="panel-title"><h2>Current stock</h2></div><div class="card-body">' +
      detailList([["Inventory",inventory.name],["Physical",product.physical + " " + product.unit],["Quarantined",product.quarantined + " " + product.unit],["Available",product.available + " " + product.unit]]) +
      '</div></section><div class="note-box"><strong>' + (page === "adjust" || page === "dispose" ? "Manager action" : "Recording stock") + '</strong><p>' + config.hint + '</p></div></aside></div>';
  }

  function importPage() {
    return link("index.html", icon("back", 13) + "Back to products", "back-link") +
      heading("Import stock transactions", "Upload a transaction CSV for " + inventory.name + ".") +
      '<div class="form-layout"><section class="panel form-panel"><div class="form-heading"><h2>Choose your file</h2><p>The selected inventory applies to the entire import.</p></div>' +
      '<form id="import-form"><label class="upload-zone" id="upload-zone" for="csv-file"><span class="upload-icon">' + icon("upload", 32) +
      '</span><strong id="file-label">Drop a CSV here, or choose a file</strong><small id="file-detail">Stock transaction CSV</small><span class="button compact">Choose file</span></label>' +
      '<input id="csv-file" name="csv" type="file" accept=".csv,text/csv" class="sr-only" required>' +
      '<p class="form-error" id="import-error" role="alert"></p><div class="form-actions">' + link("index.html", "Cancel", "button") +
      '<button class="button primary" type="submit">Review file ' + icon("arrow", 13) + '</button></div><div id="import-result" aria-live="polite"></div></form></section>' +
      '<aside class="section-stack"><section class="panel"><div class="panel-title"><h2>Import destination</h2></div><div class="card-body">' +
      detailList([["Inventory",inventory.name],["Business",data.business],["Access",persona.role]]) +
      '</div></section><div class="note-box"><strong>One inventory, one import</strong><p>Each file applies to the selected inventory. The full file is validated before its transactions are committed.</p></div>' +
      '<div class="note-box"><strong>Expiry-tracked receipts</strong><p>Use manual receiving when an incoming product requires batch expiry details.</p></div></aside></div>';
  }

  function inventoriesPage() {
    const allowed = data.inventories.filter(function (item) { return persona.inventories.includes(item.id); });
    return heading("Your inventories", "Choose an assigned inventory to view its products.", "", data.business) +
      '<div class="inventory-cards">' + allowed.map(function (item) {
        const count = data.products.filter(function (entry) { return entry.inventory === item.id; }).length;
        return '<a class="inventory-card" href="' + escapeHtml(href("index.html", {inventory:item.id,product:false})) +
          '"><span class="location-mark">' + icon("store", 23) + '</span><p class="eyebrow">' + item.code + '</p><h2>' + item.name + '</h2><p>' + item.description +
          '</p><div class="inventory-card-bottom"><span>' + count + ' linked products</span><span style="color:var(--accent)">Open inventory ' + icon("arrow", 14) + '</span></div></a>';
      }).join("") + '</div>';
  }

  function cataloguePage() {
    return heading("Product catalogue", "Product definitions linked to " + inventory.name + ".", "", "MANAGE") +
      '<section class="panel"><div class="toolbar"><label class="search-field">' + icon("search", 15) +
      '<span class="sr-only">Search catalogue</span><input id="catalogue-search" type="search" placeholder="Search name or SKU…" autocomplete="off"></label>' +
      '<span class="muted small" style="margin-left:auto">' + inventory.name + ' · ' + inventoryProducts.length + ' products</span></div>' +
      '<div class="table-scroll"><table><thead><tr><th scope="col">Product</th><th scope="col">SKU</th><th scope="col">Base unit</th><th scope="col">Expiry policy</th><th scope="col">Status</th><th scope="col">Stock</th></tr></thead><tbody>' +
      inventoryProducts.map(function (item) {
        return '<tr data-catalogue-term="' + escapeHtml((item.name + " " + item.sku).toLowerCase()) + '"><td><div class="product-cell">' + productSymbol(item) +
          '<div><strong class="small">' + item.name + '</strong><div class="product-category">' + item.category + '</div></div></div></td><td class="sku">' + item.sku +
          '</td><td class="small">' + item.unit + '</td><td class="small">' + (item.expiry ? "Required" : "Optional") + '</td><td>' + badge("Active","good") +
          '</td><td>' + link("product.html", "View stock " + icon("arrow", 12), "text-button", {product:item.id}) + '</td></tr>';
      }).join("") + '</tbody></table></div><div class="empty-state" id="catalogue-empty" hidden><h2>No matching products</h2><p>Try another name or SKU.</p></div></section>';
  }

  function reorderPage() {
    return link("forecast.html", icon("back", 13) + "Back to forecast", "back-link") +
      heading("Reorder settings", "Manage the lead time and safety stock for this product.") +
      '<div class="form-layout"><section class="panel form-panel">' + contextCard() +
      '<form id="preview-form" data-operation="reorder">' +
      field("lead", "Supplier lead time", '<div class="input-with-unit"><input id="lead" name="lead" type="number" min="0" step="1" value="' + product.lead + '" required><span>days</span></div>', "Use the supplier lead time for this inventory’s product.") +
      field("safety", "Safety stock", '<div class="input-with-unit"><input id="safety" name="safety" type="number" min="0" step="1" value="' + product.safety + '" required><span>' + product.unit + '</span></div>', "Enter a nonnegative whole number of base units.") +
      '<p class="form-error" id="form-error" role="alert"></p><div class="form-actions">' + link("forecast.html", "Cancel", "button") +
      '<button class="button primary" type="submit">Review settings ' + icon("arrow", 13) + '</button></div><div id="form-result" aria-live="polite"></div></form></section>' +
      '<aside class="note-box"><strong>Reorder recommendations</strong><p>The available-to-issue balance and eligible seven-day demand determine the reorder state. Recommendations exclude pending deliveries.</p></aside></div>';
  }

  function statusPage() {
    const eligible = product.physical === 0;
    return link("product.html", icon("back", 13) + "Back to stock", "back-link") +
      heading("Product status", "Review the conditions for deactivating this product.") +
      '<div class="form-layout"><section class="panel form-panel">' + contextCard() +
      '<div class="status-heading"><h2 style="margin:0">Current status</h2>' + badge("Active", "good") + '</div><h3>Deactivation checks</h3>' +
      '<ul class="check-list"><li>' + icon("check", 16) + '<span>Manager access to every linked inventory in this sample.</span></li>' +
      '<li>' + icon(eligible ? "check" : "close", 16) + '<span class="' + (eligible ? "" : "blocked") + '">' +
      (eligible ? "Physical stock is zero, including quarantined units." : "Resolve the " + product.physical + " " + product.unit + " of physical stock, including quarantined units.") +
      '</span></li></ul><form id="preview-form" data-operation="status"><div class="form-actions">' + link("product.html", "Back to stock", "button") +
      '<button type="submit" class="button danger"' + (eligible ? "" : " disabled") + '>Preview deactivation</button></div><div id="form-result" aria-live="polite"></div></form></section>' +
      '<aside class="note-box"><strong>Catalogue lifecycle</strong><p>Manager access must cover every inventory linked to the product, including inactive inventories. Actual status changes are recorded in product history.</p></aside></div>';
  }

  function authPage() {
    const reset = page === "reset";
    const form = reset ?
      '<a class="back-link" href="' + escapeHtml(href("login.html")) + '">' + icon("back", 12) + 'Back to sign in</a><h1>Reset your password</h1><p>Enter an email address to preview the password reset confirmation.</p>' +
      '<form id="reset-form">' + field("email", "Email address", '<input id="email" name="email" type="email" required autocomplete="email" placeholder="you@example.com">') +
      '<button type="submit" class="button primary">Preview reset request ' + icon("arrow", 14) + '</button><div id="reset-result" aria-live="polite"></div></form>' :
      '<p class="eyebrow">WELCOME TO TORY</p><h1>Welcome back.</h1><p>Explore your inventory workspace with a sample account.</p><form id="login-form">' +
      field("sample-account", "Sample account", '<select id="sample-account" name="persona"><option value="manager">Alex Tan · Manager</option><option value="staff">Jamie Lim · Staff</option></select>') +
      field("login-email", "Email address", '<input id="login-email" type="email" value="alex@example.com" readonly aria-describedby="sample-login-help">') +
      field("login-password", "Password", '<input id="login-password" type="password" value="preview-password" readonly>') +
      '<p class="field-help" id="sample-login-help" style="margin-bottom:19px">These example fields show the sign-in layout.</p><button type="submit" class="button primary">Open sample workspace ' + icon("arrow", 14) +
      '</button></form><div style="text-align:center;margin-top:17px">' + link("reset-password.html", "Forgot password?", "text-button") + '</div>';
    document.getElementById("app").innerHTML = '<div class="auth-page"><aside class="auth-story">' + brand() +
      '<div class="auth-story-copy"><p class="eyebrow">EVERYDAY INVENTORY, CLEARLY</p><h1>Know your stock.<br><span>Plan your next move.</span></h1>' +
      '<p>Keep products, stock movements and demand in one organised workspace.</p><div class="auth-illustration">' +
      '<div class="auth-tile">' + icon("box", 18) + '<strong>Products</strong><small>Physical and available stock</small></div>' +
      '<div class="auth-tile">' + icon("history", 18) + '<strong>History</strong><small>Every recorded movement</small></div>' +
      '<div class="auth-tile">' + icon("chart", 18) + '<strong>Forecast</strong><small>Seven-day demand</small></div></div></div><small class="muted">Tory · Inventory made simple.</small></aside>' +
      '<main class="auth-main"><div class="auth-top">' + themeControl() + '</div><div class="auth-form">' + form +
      '</div><p class="auth-footnote">UI preview · Sample accounts and data</p></main></div>';
  }

  function showProductMenu(id) {
    const item = inventoryProducts.find(function (entry) { return entry.id === id; });
    if (!item) return;
    const options = {product:item.id};
    const links = [
      link("product.html", icon("box", 15) + "Stock view", "button", options),
      link("history.html", icon("history", 15) + "Stock history", "button", options),
      link("forecast.html", icon("chart", 15) + "Demand forecast", "button", options),
      link("receive.html", icon("plus", 15) + "Receive stock", "button", options),
      link("issue.html", icon("minus", 15) + "Issue stock", "button", options)
    ];
    if (role === "manager") {
      links.push(link("adjust.html", icon("edit", 15) + "Adjust batch count", "button", options));
      links.push(link("dispose.html", icon("trash", 15) + "Dispose stock", "button", options));
      links.push(link("product-status.html", icon("settings", 15) + "Product status", "button", options));
    }
    document.getElementById("action-dialog-body").innerHTML = '<div class="dialog-head"><div><p class="eyebrow">' + escapeHtml(item.sku) + '</p><h2>' +
      escapeHtml(item.name) + '</h2></div><button class="icon-button" data-close-dialog aria-label="Close product actions">' + icon("close", 17) +
      '</button></div><div class="section-stack" style="gap:8px">' + links.join("") + '</div>';
    document.getElementById("action-dialog").showModal();
  }

  function setTheme(theme) {
    document.documentElement.dataset.theme = theme;
    savePreference("tory-ui-theme", theme);
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.setAttribute("aria-pressed", String(button.dataset.themeChoice === theme));
    });
    document.querySelectorAll("a[href]").forEach(function (anchor) {
      const original = anchor.getAttribute("href");
      if (original.startsWith("#")) return;
      const target = new URL(anchor.href, window.location.href);
      if (!target.pathname.endsWith(".html")) return;
      target.searchParams.set("theme", theme);
      anchor.href = target.href;
    });
  }

  function enterPersona(nextRole) {
    const account = data.personas[nextRole];
    if (!account) return;
    savePreference("tory-ui-role", nextRole);
    const nextInventory = account.inventories.includes(inventory.id) ? inventory.id : account.inventories[0];
    const query = new URLSearchParams({inventory:nextInventory,role:nextRole,theme:document.documentElement.dataset.theme});
    window.location.href = "index.html?" + query.toString();
  }

  function bindCommon() {
    setTheme(document.documentElement.dataset.theme);
    document.querySelectorAll("[data-theme-choice]").forEach(function (button) {
      button.addEventListener("click", function () { setTheme(button.dataset.themeChoice); });
    });
    const switcher = document.getElementById("inventory-switch");
    if (switcher) {
      switcher.addEventListener("click", function () {
        const options = document.getElementById("inventory-options");
        options.hidden = !options.hidden;
        switcher.setAttribute("aria-expanded", String(!options.hidden));
      });
    }
    const toggle = document.getElementById("menu-toggle");
    const overlay = document.getElementById("drawer-overlay");
    function closeDrawer() {
      document.getElementById("sidebar").classList.remove("is-open");
      overlay.classList.remove("is-open");
      toggle.setAttribute("aria-expanded", "false");
      toggle.focus();
    }
    if (toggle) {
      toggle.addEventListener("click", function () {
        const open = document.getElementById("sidebar").classList.toggle("is-open");
        overlay.classList.toggle("is-open", open);
        toggle.setAttribute("aria-expanded", String(open));
      });
      overlay.addEventListener("click", closeDrawer);
    }
    document.addEventListener("keydown", function (event) {
      if (event.key === "Escape" && toggle && toggle.getAttribute("aria-expanded") === "true") closeDrawer();
      if (event.key === "Escape" && switcher) {
        document.getElementById("inventory-options").hidden = true;
        switcher.setAttribute("aria-expanded", "false");
      }
    });
    const preview = document.getElementById("preview-control");
    if (preview) preview.addEventListener("click", function () { document.getElementById("preview-dialog").showModal(); });
    document.querySelectorAll("[data-persona]").forEach(function (button) {
      button.addEventListener("click", function () { enterPersona(button.dataset.persona); });
    });
    document.addEventListener("click", function (event) {
      const close = event.target.closest("[data-close-dialog]");
      if (close) close.closest("dialog").close();
      const menu = event.target.closest("[data-product-menu]");
      if (menu) showProductMenu(menu.dataset.productMenu);
      const clear = event.target.closest("#clear-filters");
      if (clear) {
        document.getElementById("product-search").value = "";
        document.getElementById("stock-filter").value = "all";
        pageNumber = 1;
        renderProductRows();
      }
    });
  }

  function bindProductList() {
    if (!document.getElementById("product-search")) return;
    ["product-search", "stock-filter", "product-sort"].forEach(function (id) {
      document.getElementById(id).addEventListener(id === "product-search" ? "input" : "change", function () {
        pageNumber = 1;
        renderProductRows();
      });
    });
    document.getElementById("previous-products").addEventListener("click", function () { pageNumber -= 1; renderProductRows(); });
    document.getElementById("next-products").addEventListener("click", function () { pageNumber += 1; renderProductRows(); });
    renderProductRows();
  }

  function bindForms() {
    const form = document.getElementById("preview-form");
    if (form) form.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const values = new FormData(form);
      const operation = form.dataset.operation;
      const integerFields = operation === "reorder" ? ["lead", "safety"] : (operation === "status" ? [] : ["quantity"]);
      const valid = integerFields.every(function (name) { return Number.isSafeInteger(Number(values.get(name))); });
      const error = document.getElementById("form-error");
      if (!valid) {
        if (error) error.textContent = "Enter whole numbers within the supported numeric range.";
        return;
      }
      if (operation === "dispose") {
        const option = document.getElementById("batch").selectedOptions[0];
        if (Number(values.get("quantity")) > Number(option.dataset.quantity)) {
          error.textContent = "The quantity exceeds the selected batch balance.";
          return;
        }
      }
      if (error) error.textContent = "";
      let summary = "";
      if (operation === "reorder") summary = "Lead time " + values.get("lead") + " days · Safety stock " + values.get("safety") + " " + product.unit;
      else if (operation === "status") summary = "Deactivate " + product.name + " after the eligibility checks pass.";
      else summary = ({receive:"Receive",issue:"Issue",adjust:"Record final count of",dispose:"Dispose"})[operation] + " " + values.get("quantity") + " " + product.unit + " · " + product.name;
      document.getElementById("form-result").innerHTML = '<div class="inline-result"><strong>' + icon("check", 15) + ' Preview ready</strong><p>' +
        escapeHtml(summary) + '</p><p>Sample confirmation for your layout review.</p></div>';
    });

    const importForm = document.getElementById("import-form");
    if (importForm) {
      const fileInput = document.getElementById("csv-file");
      const zone = document.getElementById("upload-zone");
      function describeFile() {
        const file = fileInput.files[0];
        if (!file) return;
        document.getElementById("file-label").textContent = file.name;
        document.getElementById("file-detail").textContent = (file.size / 1024).toFixed(1) + " KB · " + inventory.name;
        document.getElementById("import-result").innerHTML = "";
      }
      fileInput.addEventListener("change", describeFile);
      zone.addEventListener("dragover", function (event) { event.preventDefault(); zone.classList.add("drag-over"); });
      zone.addEventListener("dragleave", function () { zone.classList.remove("drag-over"); });
      zone.addEventListener("drop", function (event) {
        event.preventDefault();
        zone.classList.remove("drag-over");
        if (event.dataTransfer.files.length) { fileInput.files = event.dataTransfer.files; describeFile(); }
      });
      importForm.addEventListener("submit", function (event) {
        event.preventDefault();
        const file = fileInput.files[0];
        if (!file) return;
        if (!file.name.toLowerCase().endsWith(".csv") || file.size === 0) {
          document.getElementById("import-error").textContent = "Choose a nonempty CSV file.";
          return;
        }
        document.getElementById("import-error").textContent = "";
        document.getElementById("import-result").innerHTML = '<div class="inline-result"><strong>' + icon("file", 15) +
          ' File selection preview</strong><p>' + escapeHtml(file.name) + ' · Destination ' + escapeHtml(inventory.name) +
          '</p><p>Sample file review screen.</p></div>';
      });
    }
  }

  function bindPageControls() {
    const historyFilter = document.getElementById("history-filter");
    if (historyFilter) historyFilter.addEventListener("change", function () {
      document.querySelectorAll("[data-history-type]").forEach(function (row) {
        row.hidden = historyFilter.value !== "all" && row.dataset.historyType !== historyFilter.value;
      });
    });
    const catalogueSearch = document.getElementById("catalogue-search");
    if (catalogueSearch) catalogueSearch.addEventListener("input", function () {
      let count = 0;
      document.querySelectorAll("[data-catalogue-term]").forEach(function (row) {
        row.hidden = !row.dataset.catalogueTerm.includes(catalogueSearch.value.trim().toLowerCase());
        if (!row.hidden) count += 1;
      });
      document.getElementById("catalogue-empty").hidden = count > 0;
    });
    const loginForm = document.getElementById("login-form");
    if (loginForm) {
      document.getElementById("sample-account").addEventListener("change", function (event) {
        document.getElementById("login-email").value = event.target.value === "staff" ? "jamie@example.com" : "alex@example.com";
      });
      loginForm.addEventListener("submit", function (event) { event.preventDefault(); enterPersona(document.getElementById("sample-account").value); });
    }
    const resetForm = document.getElementById("reset-form");
    if (resetForm) resetForm.addEventListener("submit", function (event) {
      event.preventDefault();
      if (!resetForm.reportValidity()) return;
      document.getElementById("reset-result").innerHTML = '<div class="inline-result"><strong>Reset request preview</strong><p>This is the confirmation state for a submitted reset request.</p></div>';
    });
  }

  const renderers = {
    products:productsPage, inventories:inventoriesPage, stock:stockPage, history:historyPage, forecast:forecastPage,
    receive:transactionPage, issue:transactionPage, adjust:transactionPage, dispose:transactionPage,
    import:importPage, catalogue:cataloguePage, reorder:reorderPage, status:statusPage
  };
  const titles = {
    products:"Products",inventories:"Your inventories",stock:"Product stock",history:"Stock history",forecast:"Demand forecast",
    receive:"Receive stock",issue:"Issue stock",adjust:"Adjust batch count",dispose:"Dispose stock",import:"Import CSV",
    catalogue:"Catalogue",reorder:"Reorder settings",status:"Product status"
  };

  if (page === "login" || page === "reset") {
    authPage();
  } else {
    let content;
    if (!inventoryAllowed) {
      content = permissionPage("Choose an assigned inventory", "This inventory is outside this sample account’s assignments. Choose Pharmacy from the inventory switcher.");
    } else if (managerPages.includes(page) && role !== "manager") {
      content = permissionPage("Manager access required", "This action belongs to a Manager. You can view stock, stock history and forecasts from your assigned inventory.");
    } else if (productMissing) {
      content = permissionPage("Product unavailable here", "Choose a product linked to the selected inventory.");
    } else {
      content = renderers[page] ? renderers[page]() : productsPage();
    }
    shell(titles[page] || "Products", content);
  }
  savePreference("tory-ui-role", role);
  if (inventoryAllowed) savePreference("tory-ui-inventory", inventory.id);
  bindCommon();
  bindProductList();
  bindForms();
  bindPageControls();
})();

