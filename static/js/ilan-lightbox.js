(function () {
  var overlay = null;
  var images = [];
  var index = 0;
  var touchStartX = 0;

  function ensureOverlay() {
    if (overlay) return overlay;
    overlay = document.createElement("div");
    overlay.className = "ilan-lightbox";
    overlay.setAttribute("role", "dialog");
    overlay.setAttribute("aria-modal", "true");
    overlay.innerHTML =
      '<button type="button" class="ilan-lightbox-close" aria-label="Kapat">&times;</button>' +
      '<button type="button" class="ilan-lightbox-prev" aria-label="Önceki">&#10094;</button>' +
      '<button type="button" class="ilan-lightbox-next" aria-label="Sonraki">&#10095;</button>' +
      '<div class="ilan-lightbox-stage"><img class="ilan-lightbox-img" alt=""></div>' +
      '<div class="ilan-lightbox-counter"></div>';
    document.body.appendChild(overlay);

    overlay.querySelector(".ilan-lightbox-close").addEventListener("click", close);
    overlay.querySelector(".ilan-lightbox-prev").addEventListener("click", function () {
      show(index - 1);
    });
    overlay.querySelector(".ilan-lightbox-next").addEventListener("click", function () {
      show(index + 1);
    });
    overlay.addEventListener("click", function (e) {
      if (e.target === overlay) close();
    });
    overlay.addEventListener("wheel", function (e) {
      e.preventDefault();
      if (e.deltaY > 0) show(index + 1);
      else show(index - 1);
    }, { passive: false });
    overlay.addEventListener("touchstart", function (e) {
      touchStartX = e.changedTouches[0].clientX;
    }, { passive: true });
    overlay.addEventListener("touchend", function (e) {
      var dx = e.changedTouches[0].clientX - touchStartX;
      if (Math.abs(dx) < 40) return;
      if (dx < 0) show(index + 1);
      else show(index - 1);
    }, { passive: true });

    document.addEventListener("keydown", onKey);
    return overlay;
  }

  function onKey(e) {
    if (!overlay || !overlay.classList.contains("is-open")) return;
    if (e.key === "Escape") close();
    else if (e.key === "ArrowRight") show(index + 1);
    else if (e.key === "ArrowLeft") show(index - 1);
  }

  function show(nextIndex) {
    if (!images.length) return;
    index = (nextIndex + images.length) % images.length;
    var img = overlay.querySelector(".ilan-lightbox-img");
    img.src = images[index];
    overlay.querySelector(".ilan-lightbox-counter").textContent =
      index + 1 + " / " + images.length;
    overlay.querySelector(".ilan-lightbox-prev").style.display =
      images.length > 1 ? "" : "none";
    overlay.querySelector(".ilan-lightbox-next").style.display =
      images.length > 1 ? "" : "none";
  }

  function open(urls, startIndex) {
    images = urls.slice();
    if (!images.length) return;
    index = Math.max(0, Math.min(startIndex || 0, images.length - 1));
    ensureOverlay();
    overlay.classList.add("is-open");
    document.body.classList.add("ilan-lightbox-open");
    show(index);
  }

  function close() {
    if (!overlay) return;
    overlay.classList.remove("is-open");
    document.body.classList.remove("ilan-lightbox-open");
  }

  function bindGallery(root) {
    if (!root) return;
    var imgs = root.querySelectorAll(".ilan-galeri-img");
    if (!imgs.length) return;
    var urls = Array.prototype.map.call(imgs, function (el) {
      return el.getAttribute("src");
    });
    imgs.forEach(function (el, i) {
      el.style.cursor = "zoom-in";
      el.addEventListener("click", function () {
        open(urls, i);
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.querySelectorAll(".ilan-galeri-inner").forEach(function (el) {
      bindGallery(el.closest(".carousel"));
    });
  });

  window.IlanLightbox = { open: open, close: close, bindGallery: bindGallery };
})();
