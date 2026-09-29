// Time slider over pre-rendered frames (layouts/shortcodes/time-slider.html).
// The range input picks a frame t<NNN>.webp from the element's data-base
// and shows its time; nothing is computed here.
(function () {
  "use strict";

  function frame(base, t) {
    return `${base}t${String(t).padStart(3, "0")}.webp`;
  }

  function init(root) {
    const base = root.dataset.base;
    const img = root.querySelector("img");
    const input = root.querySelector("input[type=range]");
    const out = root.querySelector("output");
    const alt = img.dataset.alt;
    let preloaded = false;

    function preload() {
      if (preloaded) return;
      preloaded = true;
      const step = Number(input.step);
      for (let t = Number(input.min); t <= Number(input.max); t += step) {
        new Image().src = frame(base, t);
      }
    }

    function update() {
      const t = Number(input.value);
      img.src = frame(base, t);
      img.alt = `${alt} Frame at t = ${t} s.`;
      out.textContent = `t = ${t} s`;
      input.setAttribute("aria-valuetext", `${t} seconds after ignition`);
    }

    input.addEventListener("input", update);
    input.addEventListener("focus", preload);
    input.addEventListener("pointerdown", preload);
    root.querySelector("[data-live]").hidden = false;
    update();
  }

  function initAll() {
    document.querySelectorAll("[data-time-slider]").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
