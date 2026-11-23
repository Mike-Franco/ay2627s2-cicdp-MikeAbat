(() => {
  const root = document.documentElement;
  const charts = [];
  const currency = new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" });

  function column(rows, key) {
    return rows.map(row => row[key]);
  }

  function numberColumn(rows, key) {
    return rows.map(row => row[key] === null ? null : Number(row[key]));
  }

  function draw() {
    const style = getComputedStyle(root);
    const ink = style.getPropertyValue("--ink").trim();
    const grid = style.getPropertyValue("--line").trim();
    const dark = root.dataset.bsTheme === "dark";
    const colours = dark
      ? ["#6fdbb4", "#f6bd68", "#a0b7ff", "#f98b84", "#d2a5f4", "#74d3de", "#dfd57a"]
      : ["#167655", "#996019", "#425caf", "#a74137", "#854c99", "#1b7486", "#766c24"];
    const [accent, amber, blue] = colours;
    const axes = { ticks: { color: ink }, grid: { color: grid } };

    function chart(key, build) {
      const canvas = document.getElementById(key + "-chart");
      if (!canvas) return;
      const rows = JSON.parse(document.getElementById(key + "-data").textContent);
      const config = build(rows);
      const { type, labels, datasets, options = {} } = config;
      charts.push(new Chart(canvas, {
        type,
        data: { labels, datasets },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          plugins: { legend: { position: "bottom", labels: { color: ink } } },
          ...options
        }
      }));
    }

    function line(label, values, colour, dash = []) {
      return {
        label, data: values, borderColor: colour, backgroundColor: colour,
        borderDash: dash, pointRadius: 0, spanGaps: false
      };
    }

    function bar(label, values, colour) {
      return { label, data: values, backgroundColor: colour };
    }

    const unitScales = { x: axes, y: { ...axes, beginAtZero: true } };
    chart("stock", rows => ({
      type: "line", labels: column(rows, "day"),
      datasets: [
        line("On hand", column(rows, "on_hand"), accent),
        line("Reorder point", numberColumn(rows, "reorder_point"), amber, [6, 4]),
        line("Safety stock", numberColumn(rows, "safety_stock"), blue, [2, 4])
      ],
      options: { scales: unitScales }
    }));
    chart("traffic", rows => ({
      type: "bar", labels: column(rows, "week"),
      datasets: [
        bar("Received", column(rows, "received"), accent),
        bar("Issued", column(rows, "issued"), blue)
      ],
      options: { scales: unitScales }
    }));
    chart("supply", rows => ({
      type: "bar", labels: column(rows, "sku"),
      datasets: [bar("Days of supply", column(rows, "days"), accent)],
      options: { indexAxis: "y", scales: { x: { ...axes, beginAtZero: true }, y: axes } }
    }));
    chart("value", rows => ({
      type: "doughnut", labels: column(rows, "label"),
      datasets: [{
        label: "Retail value", data: numberColumn(rows, "value"),
        backgroundColor: rows.map((_, index) => colours[index % colours.length]),
        borderColor: style.getPropertyValue("--panel").trim()
      }],
      options: {
        plugins: {
          legend: { position: "bottom", labels: { color: ink } },
          tooltip: { callbacks: { label: item => item.label + " " + currency.format(item.raw) } }
        }
      }
    }));
    chart("demand", rows => ({
      type: "line", labels: column(rows, "day"),
      datasets: [
        line("Units issued", column(rows, "issued"), accent),
        line("Verified seven-day average", numberColumn(rows, "verified_average"), amber, [6, 4])
      ],
      options: { scales: unitScales }
    }));
    chart("expiry", rows => ({
      type: "bar", labels: column(rows, "week"),
      datasets: [bar("Eligible units expiring", column(rows, "units"), amber)],
      options: { scales: unitScales }
    }));
  }

  if (typeof Chart === "undefined") return;
  draw();
  new MutationObserver(() => {
    for (const chart of charts) chart.destroy();
    charts.length = 0;
    draw();
  }).observe(root, { attributes: true, attributeFilter: ["data-bs-theme"] });
})();
