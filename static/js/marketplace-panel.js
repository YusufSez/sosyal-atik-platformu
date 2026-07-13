(function () {
  var dataEl = document.getElementById("marketplace-listings-data");
  var cfgEl = document.getElementById("marketplace-panel-config");
  var cardsEl = document.getElementById("mpListingCards");
  if (!dataEl || !cfgEl || !cardsEl) return;

  var listings = [];
  var cfg = {};
  try {
    listings = JSON.parse(dataEl.textContent || "[]");
    cfg = JSON.parse(cfgEl.textContent || "{}");
  } catch (e) {
    cardsEl.innerHTML =
      '<div class="col-12"><div class="mp-empty text-danger">Katalog yüklenemedi</div></div>';
    return;
  }

  // Deduplicate by id (published + mine overlap)
  var seen = {};
  listings = listings.filter(function (row) {
    if (!row || seen[row.id]) return false;
    seen[row.id] = true;
    return true;
  });

  var origin = cfg.origin || { lat: 39, lng: 35 };
  var selectedId = null;
  var matchCache = {};

  function urlFor(tpl, id) {
    return String(tpl || "").replace("999001", String(id));
  }

  function escapeHtml(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function haversineKm(aLat, aLng, bLat, bLng) {
    var R = 6371;
    var toRad = Math.PI / 180;
    var dLat = (bLat - aLat) * toRad;
    var dLng = (bLng - aLng) * toRad;
    var lat1 = aLat * toRad;
    var lat2 = bLat * toRad;
    var h =
      Math.sin(dLat / 2) * Math.sin(dLat / 2) +
      Math.cos(lat1) * Math.cos(lat2) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
    return R * 2 * Math.atan2(Math.sqrt(h), Math.sqrt(1 - h));
  }

  function enrich(row) {
    var dist = haversineKm(origin.lat, origin.lng, row.lat, row.lng);
    row._mesafe = Math.round(dist * 10) / 10;
    // Görsel AI Match tahmini (kart); seçimde API skoru ile güncellenir
    var distScore = Math.max(0, 100 - dist * 1.5);
    var katBoost = row.kategori && row.kategori !== "Diğer" ? 8 : 0;
    row._matchEst = Math.max(
      12,
      Math.min(98, Math.round(distScore * 0.85 + katBoost + 10))
    );
    return row;
  }

  listings.forEach(enrich);

  function fillMalzemeOptions() {
    var sel = document.getElementById("mpFilterMalzeme");
    if (!sel) return;
    var units = {};
    listings.forEach(function (r) {
      if (r.birim) units[r.birim] = true;
    });
    Object.keys(units)
      .sort()
      .forEach(function (u) {
        var opt = document.createElement("option");
        opt.value = u;
        opt.textContent = u;
        sel.appendChild(opt);
      });
  }

  function filters() {
    return {
      kategori: (document.getElementById("mpFilterKategori") || {}).value || "",
      mesafe: (document.getElementById("mpFilterMesafe") || {}).value || "",
      malzeme: (document.getElementById("mpFilterMalzeme") || {}).value || "",
      durum: (document.getElementById("mpFilterDurum") || {}).value || "",
    };
  }

  function filtered() {
    var f = filters();
    var maxKm = f.mesafe ? Number(f.mesafe) : null;
    return listings.filter(function (r) {
      if (f.kategori && r.kategori !== f.kategori) return false;
      if (f.malzeme && r.birim !== f.malzeme) return false;
      if (f.durum && r.durum !== f.durum) return false;
      if (maxKm != null && r._mesafe > maxKm) return false;
      return true;
    });
  }

  function durumBadge(durum) {
    var map = {
      yayinda: "text-bg-success",
      rezerve: "text-bg-warning",
      anlasildi: "text-bg-info",
      teslim: "text-bg-primary",
      iptal: "text-bg-secondary",
    };
    return map[durum] || "text-bg-light border";
  }

  function matchPct(row) {
    if (matchCache[row.id] && matchCache[row.id].topScore != null) {
      return matchCache[row.id].topScore;
    }
    return row._matchEst;
  }

  function renderCards() {
    var rows = filtered();
    var countEl = document.getElementById("mpCardCount");
    if (countEl) countEl.textContent = rows.length + " kaynak";

    if (!rows.length) {
      cardsEl.innerHTML =
        '<div class="col-12"><div class="mp-empty text-muted">Filtrelere uygun kaynak yok.</div></div>';
      return;
    }

    cardsEl.innerHTML = "";
    rows.forEach(function (r) {
      var col = document.createElement("div");
      col.className = "col-sm-6";
      var active = selectedId === r.id ? " is-active" : "";
      var pct = matchPct(r);
      col.innerHTML =
        '<button type="button" class="mp-resource-card' +
        active +
        '" data-id="' +
        r.id +
        '">' +
        '<div class="mp-resource-top">' +
        '<div class="mp-resource-kicker">Kaynak</div>' +
        '<span class="badge ' +
        durumBadge(r.durum) +
        '">' +
        escapeHtml(r.durum) +
        "</span>" +
        "</div>" +
        '<div class="mp-resource-title">' +
        escapeHtml(r.baslik) +
        "</div>" +
        '<div class="mp-resource-firma"><i class="bi bi-building me-1"></i>' +
        escapeHtml(r.firma || "Firma") +
        "</div>" +
        '<div class="mp-resource-meta">' +
        '<span><i class="bi bi-geo-alt me-1"></i>' +
        r._mesafe +
        " km</span>" +
        '<span class="mp-match-pill">AI Match %' +
        pct +
        "</span>" +
        "</div>" +
        '<div class="mp-resource-sub small text-muted">' +
        escapeHtml(r.kategori) +
        (r.miktar != null
          ? " · " + r.miktar + " " + escapeHtml(r.birim || "")
          : "") +
        (r.il ? " · " + escapeHtml(r.il) : "") +
        "</div>" +
        "</button>";
      cardsEl.appendChild(col);
    });
  }

  function setBar(barId, valId, value) {
    var bar = document.getElementById(barId);
    var val = document.getElementById(valId);
    var n = value != null ? Number(value) : 0;
    if (bar) bar.style.width = Math.max(0, Math.min(100, n)) + "%";
    if (val) val.textContent = value != null ? Math.round(n) + "%" : "—";
  }

  function resetAiPanel(msg) {
    var explain = document.getElementById("mpAiExplain");
    var source = document.getElementById("mpAiSource");
    var reasons = document.getElementById("mpAiReasons");
    if (explain) explain.textContent = msg || "Bir kaynak kartı seçin.";
    if (source) source.textContent = "—";
    if (reasons) reasons.innerHTML = "";
    setBar("mpAiKatBar", "mpAiKatVal", null);
    setBar("mpAiMesBar", "mpAiMesVal", null);
    setBar("mpAiPuanBar", "mpAiPuanVal", null);
    setBar("mpAiAktBar", "mpAiAktVal", null);
  }

  function applyMatchReport(listingId, report) {
    var matches = (report && report.matches) || [];
    var top = matches[0];
    var det = (top && top.skor_detay) || {};
    var topScore = top ? top.eslesme_skoru : null;
    matchCache[listingId] = { topScore: topScore, report: report };

    var explain = document.getElementById("mpAiExplain");
    var source = document.getElementById("mpAiSource");
    var reasons = document.getElementById("mpAiReasons");
    var deep = document.getElementById("mpAiDeepLink");

    if (explain) {
      explain.textContent =
        (report && report.explanation) ||
        (top
          ? top.ad + " ile yüksek uyum."
          : "Bu kaynak için yakında uygun eşleşme bulunamadı.");
    }
    if (source) source.textContent = (report && report.explanation_source) || "rules";
    setBar("mpAiKatBar", "mpAiKatVal", det.kategori);
    setBar("mpAiMesBar", "mpAiMesVal", det.mesafe);
    setBar("mpAiPuanBar", "mpAiPuanVal", det.puan);
    setBar("mpAiAktBar", "mpAiAktVal", det.aktivite);

    if (reasons) {
      reasons.innerHTML = "";
      var nedenler = (top && top.nedenler) || [];
      nedenler.slice(0, 4).forEach(function (n) {
        var li = document.createElement("div");
        li.className = "mp-ai-reason";
        li.textContent = n;
        reasons.appendChild(li);
      });
    }
    if (deep) {
      deep.href = cfg.eslesmelerUrl + "?listing_id=" + listingId;
    }
    renderCards();
  }

  function renderNearby(report) {
    var box = document.getElementById("mpNearbyList");
    if (!box) return;
    var matches = (report && report.matches) || [];
    if (!matches.length) {
      box.innerHTML =
        '<p class="text-muted small mb-0">' +
        escapeHtml(
          (report && report.nearby_suggestion) ||
            "Yakında uygun kurum bulunamadı."
        ) +
        "</p>";
      return;
    }
    box.innerHTML = "";
    matches.slice(0, 6).forEach(function (m) {
      var row = document.createElement("div");
      row.className = "mp-nearby-item";
      row.innerHTML =
        '<div class="fw-semibold">' +
        escapeHtml(m.ad || "Kurum") +
        '</div><div class="small text-muted">' +
        (m.mesafe_km != null ? m.mesafe_km + " km" : "—") +
        (m.il ? " · " + escapeHtml(m.il) : "") +
        '</div><div class="mp-nearby-score">AI Match %' +
        (m.eslesme_skoru != null ? m.eslesme_skoru : "—") +
        "</div>";
      box.appendChild(row);
    });
  }

  function selectListing(id) {
    selectedId = id;
    renderCards();
    resetAiPanel("AI eşleşme analiz ediliyor…");
    var nearbyBox = document.getElementById("mpNearbyList");
    if (nearbyBox) {
      nearbyBox.innerHTML =
        '<p class="text-muted small mb-0">Yakındaki kurumlar yükleniyor…</p>';
    }

    if (matchCache[id] && matchCache[id].report) {
      applyMatchReport(id, matchCache[id].report);
      renderNearby(matchCache[id].report);
      return;
    }

    var url = urlFor(cfg.matchesUrlTpl, id);
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        return r.json();
      })
      .then(function (report) {
        applyMatchReport(id, report);
        renderNearby(report);
      })
      .catch(function () {
        resetAiPanel("Eşleşme verisi alınamadı.");
        if (nearbyBox) {
          nearbyBox.innerHTML =
            '<p class="text-danger small mb-0">Yakın kurumlar yüklenemedi.</p>';
        }
      });
  }

  cardsEl.addEventListener("click", function (e) {
    var btn = e.target.closest("[data-id]");
    if (!btn) return;
    selectListing(Number(btn.getAttribute("data-id")));
  });

  ["mpFilterKategori", "mpFilterMesafe", "mpFilterMalzeme", "mpFilterDurum"].forEach(
    function (id) {
      var el = document.getElementById(id);
      if (el) el.addEventListener("change", renderCards);
    }
  );

  fillMalzemeOptions();
  renderCards();

  // İlk kartı otomatik seç (varsa)
  var first = filtered()[0];
  if (first) selectListing(first.id);
})();
