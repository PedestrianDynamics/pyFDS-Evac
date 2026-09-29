// Make boxes that scroll sideways (equations, tables, code) reachable by
// keyboard in every browser, with a name for screen readers.
(function () {
  "use strict";
  var kinds = [
    [".content .katex-display", "Scrollable equation"],
    [".content table", "Scrollable table"],
    [".content pre", "Scrollable code"],
  ];
  function mark() {
    kinds.forEach(function (kind) {
      document.querySelectorAll(kind[0]).forEach(function (el) {
        var overflows = el.scrollWidth > el.clientWidth + 1;
        if (overflows && !el.hasAttribute("tabindex")) {
          el.setAttribute("tabindex", "0");
          el.setAttribute("role", "region");
          el.setAttribute("aria-label", kind[1]);
          el.dataset.scrollRegion = "";
        } else if (!overflows && el.dataset.scrollRegion !== undefined) {
          el.removeAttribute("tabindex");
          el.removeAttribute("role");
          el.removeAttribute("aria-label");
          delete el.dataset.scrollRegion;
        }
      });
    });
  }
  var timer;
  function schedule() {
    clearTimeout(timer);
    timer = setTimeout(mark, 150);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mark);
  } else {
    mark();
  }
  window.addEventListener("load", mark);
  window.addEventListener("resize", schedule);
})();
