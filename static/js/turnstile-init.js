(function () {
  window.turnstileWidgetsInit = function () {
    if (typeof turnstile === "undefined") return;

    document.querySelectorAll(".turnstile-widget[data-sitekey]").forEach(function (el) {
      if (el.dataset.turnstileRendered === "1") return;

      turnstile.render(el, {
        sitekey: el.dataset.sitekey,
        language: el.dataset.language || "tr",
        theme: el.dataset.theme || "auto",
      });
      el.dataset.turnstileRendered = "1";
    });
  };
})();
