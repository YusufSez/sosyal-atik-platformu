/**
 * CSP: data-pct / --pct değerlerini JS ile uygular (skeleton, progress, ss-ring).
 * Inline style="" kullanmaz (element.style CSP style-src ihlali değildir).
 */
(function () {
  function applyPctBars(root) {
    (root || document)
      .querySelectorAll("[data-pct]")
      .forEach(function (el) {
        var pct = Number(el.getAttribute("data-pct"));
        if (isNaN(pct)) return;
        pct = Math.max(0, Math.min(100, pct));
        if (el.classList.contains("progress-bar") || el.getAttribute("role") === "progressbar") {
          el.style.width = pct + "%";
        } else if (el.classList.contains("ss-ring") || el.hasAttribute("data-ring")) {
          el.style.setProperty("--pct", String(pct));
        } else if (el.classList.contains("ap-skeleton-line")) {
          el.style.width = pct + "%";
        } else {
          el.style.width = pct + "%";
        }
      });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () {
      applyPctBars(document);
    });
  } else {
    applyPctBars(document);
  }

  window.AtikPortApplyPct = applyPctBars;
})();
