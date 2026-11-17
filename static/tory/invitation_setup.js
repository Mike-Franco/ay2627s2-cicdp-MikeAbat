(() => {
  "use strict";
  const token = window.location.hash.slice(1);
  window.history.replaceState(null, "", window.location.pathname);
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("staff-setup-form");
    const error = document.getElementById("link-error");
    if (!token) {
      form.hidden = true;
      error.hidden = false;
      return;
    }
    form.addEventListener("submit", () => {
      document.getElementById("invitation-token").value = token;
    });
  });
})();
