(function () {
  var preference;
  var query = new URLSearchParams(window.location.search).get("theme");
  try { preference = localStorage.getItem("tory-ui-theme"); } catch (error) {}
  var systemDark = window.matchMedia && window.matchMedia("(prefers-color-scheme: dark)").matches;
  var theme = query === "light" || query === "dark" ? query : preference;
  document.documentElement.dataset.theme = theme === "light" || theme === "dark" ? theme : (systemDark ? "dark" : "light");
})();