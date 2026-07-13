/**
 * Bakanlık drilldown kaskadı — CSP uyumlu.
 * Form #ministryFilterForm data-drill-url
 */
(function () {
  var form = document.getElementById("ministryFilterForm");
  var il = document.getElementById("minFiltreIl");
  var ilce = document.getElementById("minFiltreIlce");
  var bel = document.getElementById("minFiltreBelediye");
  var kurum = document.getElementById("minFiltreKurum");
  if (!il) return;

  var drillUrl =
    (form && form.getAttribute("data-drill-url")) ||
    "/minister/api/drilldown";

  function fillSimple(el, items, selected) {
    if (!el) return;
    var first = el.options[0]
      ? el.options[0].outerHTML
      : '<option value="">Tümü</option>';
    el.innerHTML = first;
    (items || []).forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      if (selected && selected === v) opt.selected = true;
      el.appendChild(opt);
    });
  }

  function fillEntities(el, items, selected) {
    if (!el) return;
    var first = el.options[0]
      ? el.options[0].outerHTML
      : '<option value="">Tümü</option>';
    el.innerHTML = first;
    (items || []).forEach(function (item) {
      var opt = document.createElement("option");
      opt.value = item.id;
      opt.textContent = item.ad + (item.ilce ? " (" + item.ilce + ")" : "");
      if (selected && String(selected) === String(item.id)) opt.selected = true;
      el.appendChild(opt);
    });
  }

  function loadDrill() {
    var params = new URLSearchParams();
    if (il.value) params.set("il", il.value);
    if (ilce && ilce.value) params.set("ilce", ilce.value);
    if (bel && bel.value) params.set("belediye_id", bel.value);
    fetch(drillUrl + "?" + params.toString(), { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (data) {
        if (ilce) fillSimple(ilce, data.ilceler || [], ilce.value);
        if (bel) fillEntities(bel, data.belediyeler || [], bel.value);
        if (kurum) fillEntities(kurum, data.kurumlar || [], kurum.value);
      })
      .catch(function () {});
  }

  il.addEventListener("change", function () {
    if (ilce) ilce.value = "";
    if (bel) bel.value = "";
    if (kurum) kurum.value = "";
    loadDrill();
  });
  if (ilce) {
    ilce.addEventListener("change", function () {
      if (bel) bel.value = "";
      if (kurum) kurum.value = "";
      loadDrill();
    });
  }
  if (bel) {
    bel.addEventListener("change", function () {
      if (kurum) kurum.value = "";
      loadDrill();
    });
  }
})();
