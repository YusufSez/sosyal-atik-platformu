(function () {
  if (typeof L === "undefined") return;

  var meta = document.querySelector('meta[name="leaflet-icon-base"]');
  var base = meta ? meta.content : "/static/vendor/leaflet/1.9.4/images/";
  if (!base.endsWith("/")) {
    base += "/";
  }

  delete L.Icon.Default.prototype._getIconUrl;
  L.Icon.Default.mergeOptions({
    iconRetinaUrl: base + "marker-icon-2x.png",
    iconUrl: base + "marker-icon.png",
    shadowUrl: base + "marker-shadow.png",
  });
})();
