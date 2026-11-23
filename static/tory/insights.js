(() => {
  // Insights charts (TORY-64). Data comes from json_script blocks; colours come from tokens.css,
  // so the charts redraw when the theme changes. Each chart also has a text table under "Show data".
  const root = document.documentElement;
  const charts = [];
  const currency = new Intl.NumberFormat("en-SG", { style: "currency", currency: "SGD" });

  function data(key) {
    const node = document.getElementById(key + "-data");
    return node ? JSON.parse(node.textContent) : [];
  }

  function draw() {
    const style = getComputedStyle(root);
    const token = name => style.getPropertyValue(name).trim();
    const ink = token("--text");
    const muted = token("--muted");
    const grid = token("--line");
    const accent = token("--accent");
    const red = token("--red");
    const amber = token("--amber");
    const green = token("--green");
    const blue = token("--blue");
    const panel = token("--panel");
    const palette = [accent, blue, green, amber, red, muted];
    const axes = { ticks: { color: muted }, grid: { color: grid } };
    const scales = { x: { ...axes, grid: { display: false } }, y: { ...axes, beginAtZero: true } };
    const legend = { position: "bottom", labels: { color: ink, boxWidth: 10 } };

    function chart(key, config) {
      const canvas = document.getElementById(key + "-chart");
      if (!canvas) return;
      charts.push(new Chart(canvas, {
        ...config,
        options: { responsive: true, maintainAspectRatio: false, plugins: { legend }, ...config.options }
      }));
    }

    const stock = data("stock");
    chart("stock", {
      type: "bar",
      data: {
        labels: stock.map(row => row.sku),
        datasets: [
          { type: "bar", label: "Available", data: stock.map(row => row.available),
            backgroundColor: stock.map(row => row.below ? red : accent), order: 2 },
          { type: "line", label: "Reorder point", data: stock.map(row => row.reorder_point),
            showLine: false, pointStyle: "line", pointRadius: 12, pointBorderWidth: 2,
            borderColor: ink, backgroundColor: ink, order: 1 }
        ]
      },
      options: { scales }
    });

    const traffic = data("traffic");
    chart("traffic", {
      type: "bar",
      data: {
        labels: traffic.map(row => row.week),
        datasets: [
          { label: "Received", data: traffic.map(row => row.received), backgroundColor: green },
          { label: "Issued", data: traffic.map(row => row.issued), backgroundColor: blue }
        ]
      },
      options: { scales }
    });

    const value = data("value");
    chart("value", {
      type: "doughnut",
      data: {
        labels: value.map(row => row.label),
        datasets: [{ data: value.map(row => Number(row.value)), borderColor: panel,
                     backgroundColor: value.map((_, index) => palette[index % palette.length]) }]
      },
      options: {
        cutout: "62%",
        plugins: { legend, tooltip: { callbacks: { label: item => item.label + " " + currency.format(item.raw) } } }
      }
    });

    const history = data("demand");
    const forecast = data("forecast");
    const labels = history.map(row => row.day).concat(forecast.map(row => row.day));
    const blanks = n => new Array(n).fill(null);
    const last = history.length ? history[history.length - 1].issued : null;
    chart("demand", {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Demand", data: history.map(row => row.issued).concat(blanks(forecast.length)),
            borderColor: accent, backgroundColor: accent, tension: 0.2,
            pointRadius: 3,
            // Unverified days are hollow amber points: the forecast ignores them.
            pointBackgroundColor: history.map(row => row.verified ? accent : panel),
            pointBorderColor: history.map(row => row.verified ? accent : amber) },
          { label: "Forecast (7 days)",
            data: forecast.length ? blanks(history.length - 1).concat([last], forecast.map(row => Number(row.forecast))) : [],
            borderColor: accent, borderDash: [6, 4], pointRadius: 0, backgroundColor: accent }
        ]
      },
      options: { scales }
    });
  }

  if (typeof Chart === "undefined") return;
  draw();
  new MutationObserver(() => {
    for (const chart of charts) chart.destroy();
    charts.length = 0;
    draw();
  }).observe(root, { attributes: true, attributeFilter: ["data-bs-theme"] });
})();
