// TORY-54: live preview on the inventory form. Without JavaScript the form
// still works; only the preview stays as rendered.
(function () {
  const form = document.querySelector(".inventory-form");
  if (!form) return;
  const preview = form.querySelector("[data-preview]");
  const mark = preview.querySelector("[data-preview-mark]");
  const picture = preview.querySelector("[data-preview-picture]");
  const name = preview.querySelector("[data-preview-name]");
  const use = mark.querySelector("use");
  const sprite = form.dataset.sprite;
  const hadPicture = !picture.hidden;
  let newPicture = false;

  function showPicture(show) {
    picture.hidden = !show;
    mark.hidden = show;
  }

  form.addEventListener("input", (event) => {
    const target = event.target;
    if (target.name === "name") {
      name.textContent = target.value.trim() || "New inventory";
    } else if (target.name === "icon") {
      use.setAttribute("href", sprite + "#" + target.value);
    } else if (target.name === "colour") {
      mark.className = mark.className.replace(/\btone-[a-z]+\b/, "tone-" + target.value);
    }
  });

  form.addEventListener("change", (event) => {
    const target = event.target;
    if (target.matches("[data-picture-input]")) {
      const file = target.files && target.files[0];
      // data: URLs are allowed by the page CSP; blob: URLs are not.
      if (file && file.size <= 2 * 1024 * 1024 && /^image\/(jpeg|png|webp)$/.test(file.type)) {
        const reader = new FileReader();
        reader.onload = () => { picture.src = reader.result; newPicture = true; showPicture(true); };
        reader.readAsDataURL(file);
      } else {
        newPicture = false;
        showPicture(hadPicture);
      }
    } else if (target.matches("[data-remove-picture]")) {
      showPicture(!target.checked && (hadPicture || newPicture));
    }
  });
})();
