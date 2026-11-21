(function () {
  function read(id) {
    return JSON.parse(document.getElementById(id).textContent);
  }

  function drawCharts() {
    var style = getComputedStyle(document.documentElement);
    var textColor = style.getPropertyValue("--ink").trim() || "#20251f";
    var gridColor = style.getPropertyValue("--line").trim() || "#d9ded8";
    var accent = style.getPropertyValue("--accent").trim() || "#176b50";
    var demand = read("demand-data");
    var products = read("reorder-data");
    var expiries = read("expiry-data");
    var axes = {
      x: { ticks: { color: textColor }, grid: { color: gridColor } },
      y: { beginAtZero: true, ticks: { color: textColor }, grid: { color: gridColor } }
    };

    new Chart(document.getElementById("demand-chart"), {
      type: "line",
      data: { labels: demand.map(function (row) { return row.day; }), datasets: [
        { label: "Units issued", data: demand.map(function (row) { return row.issued; }),
          borderColor: accent, backgroundColor: accent, tension: 0.2 },
        { label: "Verified seven-day average", data: demand.map(function (row) {
          return row.verified_average === null ? null : Number(row.verified_average);
        }), borderColor: "#be7b28", borderDash: [6, 4], pointRadius: 0, spanGaps: false }
      ] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: textColor } } },
        scales: axes }
    });

    new Chart(document.getElementById("reorder-chart"), {
      type: "bar",
      data: { labels: products.map(function (row) { return row.sku + " · " + row.name; }),
        datasets: [
          // Separate datasets so each legend swatch matches its bars exactly;
          // skipNull keeps one bar per product in the right slot.
          { label: "Available units", data: products.map(function (row) { return row.alert ? null : row.available; }),
            backgroundColor: accent, skipNull: true },
          { label: "Available, at or below reorder point", data: products.map(function (row) {
            return row.alert ? row.available : null;
          }), backgroundColor: "#b74638", skipNull: true },
          { label: "Reorder point", data: products.map(function (row) {
            return row.reorder_point === null ? null : Number(row.reorder_point);
          }), backgroundColor: "#be7b28", skipNull: true }
        ] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: textColor } } }, scales: axes }
    });

    new Chart(document.getElementById("expiry-chart"), {
      type: "bar",
      data: { labels: expiries.map(function (row) { return row.week; }), datasets: [
        { label: "Eligible units expiring", data: expiries.map(function (row) { return row.units; }),
          backgroundColor: "#be7b28" }
      ] },
      options: { responsive: true, maintainAspectRatio: false,
        plugins: { legend: { labels: { color: textColor } } }, scales: axes }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (typeof Chart !== "undefined" && document.getElementById("demand-chart")) {
      drawCharts();
    }
  });
})();
