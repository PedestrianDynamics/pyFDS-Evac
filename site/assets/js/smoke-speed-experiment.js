// Interactive smoke-speed experiment for the Quickstart page.
//
// Evaluates the default ("lund") speed law of pyFDS-Evac,
//   factor = clamp(1 + beta * K / alpha, min_speed_factor, 1),
// and the visibility S = C / K. It mirrors speed_factor_from_extinction in
// pyfds_evac/core/smoke_speed.py; the parameters are not written here but read
// from the element's data-* attributes, which the smoke-speed-experiment
// shortcode fills from site/data/smoke_speed.json (generated from
// SmokeSpeedConfig by scripts/docs/smoke_speed_widget_data.py).
// tests/test_smoke_speed_widget.py runs speedFactor and visibility under Node
// and compares them with the Python functions.
(function () {
  "use strict";

  function cleanK(K) {
    // As the Python law: a non-finite or negative K counts as clear air.
    return Number.isFinite(K) && K > 0 ? K : 0;
  }

  function speedFactor(K, alpha, beta, minFactor) {
    const raw = 1 + (beta * cleanK(K)) / alpha;
    return Math.min(1, Math.max(minFactor, raw));
  }

  function visibility(K, C) {
    const k = cleanK(K);
    return k === 0 ? Infinity : C / k;
  }

  const api = { speedFactor, visibility };
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  if (typeof document === "undefined") {
    return;
  }

  function init(root) {
    const alpha = Number(root.dataset.alpha);
    const beta = Number(root.dataset.beta);
    const minFactor = Number(root.dataset.minFactor);
    const c = Number(root.dataset.visibilityFactor);
    const input = root.querySelector("input[type=range]");
    const out = (name) => root.querySelector(`[data-out="${name}"]`);
    const bar = root.querySelector("[data-bar=smoke]");

    function update() {
      const K = Number(input.value);
      const s = visibility(K, c);
      const f = speedFactor(K, alpha, beta, minFactor);
      const pct = (100 * f).toFixed(1);
      out("k").textContent = `K = ${K.toFixed(1)} 1/m`;
      out("visibility").textContent =
        s === Infinity ? "∞ (clear air)" : `≈ ${s.toFixed(2)} m`;
      out("factor").textContent = f.toFixed(3);
      out("percent").textContent = `${pct} %`;
      out("bar").textContent = `${pct} %`;
      bar.style.width = `${pct}%`;
      input.setAttribute("aria-valuetext", `${K.toFixed(1)} per metre`);
    }

    input.addEventListener("input", update);
    root.querySelector("[data-live]").hidden = false;
    update();
  }

  function initAll() {
    document.querySelectorAll("[data-smoke-speed-experiment]").forEach(init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initAll);
  } else {
    initAll();
  }
})();
