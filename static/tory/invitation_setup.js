(() => {
  "use strict";
  const token = window.location.hash.slice(1);
  window.history.replaceState(null, "", window.location.pathname);
  document.addEventListener("DOMContentLoaded", () => {
    const form = document.getElementById("staff-setup-form");
    const error = document.getElementById("setup-error");
    if (!token) {
      form.hidden = true;
      document.getElementById("link-error").hidden = false;
      return;
    }
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const button = form.querySelector('button[type="submit"]');
      button.disabled = true;
      error.hidden = true;
      for (const [field, list] of [["password", "password-errors"], ["password-confirm", "confirmation-errors"]]) {
        document.getElementById(field).removeAttribute("aria-invalid");
        document.getElementById(list).replaceChildren();
      }
      let navigating = false;
      try {
        const fields = new FormData(form);
        fields.set("token", token);
        const response = await fetch(window.location.pathname, {
          method: "POST", body: fields, credentials: "same-origin",
          cache: "no-store", referrerPolicy: "no-referrer",
          headers: {"Accept": "application/json"},
        });
        const result = response.headers.get("content-type")?.includes("application/json")
          ? await response.json() : null;
        if (response.ok && result?.ok === true && typeof result.sign_in_url === "string") {
          const destination = new URL(result.sign_in_url, window.location.origin);
          if (destination.origin === window.location.origin && !destination.hash && !destination.search) {
            navigating = true;
            window.location.assign(destination.pathname);
            return;
          }
        }
        if (response.ok && result?.ok === false) {
          for (const [key, field, list] of [["password", "password", "password-errors"], ["password_confirm", "password-confirm", "confirmation-errors"]]) {
            const messages = result.errors?.[key];
            if (Array.isArray(messages) && messages.length) {
              document.getElementById(field).setAttribute("aria-invalid", "true");
              for (const message of messages) {
                if (typeof message !== "string") continue;
                const item = document.createElement("li");
                item.textContent = message;
                document.getElementById(list).append(item);
              }
            }
          }
        }
        error.textContent = response.ok && result?.ok === false && typeof result.error === "string"
          ? result.error : "Password setup could not be completed. Please try again.";
      } catch (_) {
        error.textContent = "Password setup could not be completed. Please try again.";
      } finally {
        button.disabled = false;
        error.hidden = navigating;
        if (!navigating) error.focus();
      }
    });
  });
})();
