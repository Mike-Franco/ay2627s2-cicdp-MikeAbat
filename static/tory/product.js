(() => {
  // Product page "Next 7 days" (TORY-66): projected available stock at the verified average,
  // with the reorder point as a dashed line. Colours come from tokens.css.
  const root = document.documentElement;
  const canvas = document.getElementById("outlook-chart");
  const source = document.getElementById("outlook-data");
  if (!canvas || !source || typeof Chart === "undefined") return;
  const rows = JSON.parse(source.textContent);
  let chart = null;

  function draw() {
    const style = getComputedStyle(root);
    const token = name => style.getPropertyValue(name).trim();
    const axes = { ticks: { color: token("--muted") }, grid: { color: token("--line") } };
    if (chart) chart.destroy();
    chart = new Chart(canvas, {
      type: "line",
      data: {
        labels: rows.map(row => row.day),
        datasets: [
          { label: "Projected available", data: rows.map(row => row.stock), borderColor: token("--accent"),
            backgroundColor: token("--accent"), pointRadius: 2, tension: 0 },
          { label: "Reorder point", data: rows.map(row => row.reorder_point), borderColor: token("--amber"),
            borderDash: [6, 4], pointRadius: 0, backgroundColor: token("--amber") }
        ]
      },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: { legend: { position: "bottom", labels: { color: token("--text"), boxWidth: 10 } } },
        scales: { x: { ...axes, grid: { display: false } }, y: { ...axes, beginAtZero: true } }
      }
    });
  }

  draw();
  new MutationObserver(draw).observe(root, { attributes: true, attributeFilter: ["data-bs-theme"] });
})();
