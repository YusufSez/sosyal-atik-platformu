/**
 * Belediye il/ilçe/mahalle kaskadı — CSP uyumlu (inline script yok).
 * Form: #belediyeFilterForm veya #filtreIl data-geo-url
 */
(function () {
  var form = document.getElementById("belediyeFilterForm");
  var il = document.getElementById("filtreIl");
  var ilce = document.getElementById("filtreIlce");
  var mahalle = document.getElementById("filtreMahalle");
  if (!il || !ilce) return;

  var geoUrl =
    (form && form.getAttribute("data-geo-url")) ||
    il.getAttribute("data-geo-url") ||
    "/belediye/api/geography";

  function fillSelect(el, items, selected) {
    if (!el) return;
    var keep = el.options[0]
      ? el.options[0].outerHTML
      : '<option value="">Tümü</option>';
    el.innerHTML = keep;
    (items || []).forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      if (selected && selected === v) opt.selected = true;
      el.appendChild(opt);
    });
  }

  function loadGeo() {
    var params = new URLSearchParams();
    if (il.value) params.set("il", il.value);
    if (ilce.value) params.set("ilce", ilce.value);
    fetch(geoUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        fillSelect(ilce, data.ilceler || [], ilce.value);
        if (mahalle) fillSelect(mahalle, data.mahalleler || [], mahalle.value);
      })
      .catch(function () {});
  }

  if (il.value && !il.disabled) loadGeo();
  else if (il.value && il.disabled) loadGeo();

  il.addEventListener("change", function () {
    if (ilce) ilce.value = "";
    if (mahalle) mahalle.value = "";
    loadGeo();
  });
  ilce.addEventListener("change", function () {
    if (mahalle) mahalle.value = "";
    loadGeo();
  });
})();
