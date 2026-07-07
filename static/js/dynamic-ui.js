(function () {
  document.querySelectorAll("[data-progress]").forEach(function (el) {
    var value = parseFloat(el.dataset.progress);
    if (!isNaN(value)) {
      el.style.width = Math.min(100, Math.max(0, value)) + "%";
    }
  });

  document.querySelectorAll("[data-bar-height]").forEach(function (el) {
    var value = parseInt(el.dataset.barHeight, 10);
    if (!isNaN(value)) {
      el.style.height = Math.max(4, value) + "px";
    }
  });
})();
