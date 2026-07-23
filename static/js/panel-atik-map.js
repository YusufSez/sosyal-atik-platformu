(function () {
  function trTitleCaseStandalone(value) {
    var text = String(value || "").trim();
    if (!text) return "";
    return text
      .split(/(\s+|\/|-)/)
      .map(function (token) {
        if (!token || /^\s+$/.test(token) || token === "/" || token === "-") return token;
        var low = token
          .replace(/I/g, "ı")
          .replace(/İ/g, "i")
          .replace(/Ğ/g, "ğ")
          .replace(/Ü/g, "ü")
          .replace(/Ş/g, "ş")
          .replace(/Ö/g, "ö")
          .replace(/Ç/g, "ç")
          .toLowerCase();
        var first = low.charAt(0);
        var rest = low.slice(1);
        if (first === "i") first = "İ";
        else first = first.toUpperCase();
        return first + rest;
      })
      .join("");
  }

  function fillCitySelectStandalone(values) {
    var el = document.getElementById("mw-filter-city");
    if (!el) return;
    var current = el.value;
    el.innerHTML = "";
    var opt0 = document.createElement("option");
    opt0.value = "";
    opt0.textContent = "İl (hepsi)";
    el.appendChild(opt0);
    (values || []).forEach(function (v) {
      var opt = document.createElement("option");
      opt.value = v;
      opt.textContent = v;
      el.appendChild(opt);
    });
    if (current && values && values.indexOf(current) >= 0) el.value = current;
  }

  /** Harita init başarısız olsa bile il dropdown doldurulsun. */
  function ensureProvincesLoaded() {
    var cityEl = document.getElementById("mw-filter-city");
    if (!cityEl || cityEl.options.length > 1) return;
    fetch("/api/turkey/provinces", { credentials: "same-origin" })
      .then(function (res) {
        if (!res.ok) throw new Error("http_" + res.status);
        return res.json();
      })
      .then(function (data) {
        var provinces = (data && data.provinces) || [];
        if (!provinces.length) throw new Error("empty");
        fillCitySelectStandalone(provinces);
      })
      .catch(function () {
        return fetch("/static/data/il-ilce-list.json", { credentials: "same-origin" })
          .then(function (res) {
            if (!res.ok) throw new Error("static_http_" + res.status);
            return res.json();
          })
          .then(function (raw) {
            var provinces = (Array.isArray(raw) ? raw : [])
              .map(function (e) {
                return trTitleCaseStandalone((e && e.name) || "");
              })
              .filter(Boolean);
            fillCitySelectStandalone(provinces);
          })
          .catch(function (err) {
            console.error("İl listesi (erken yükleme) başarısız:", err);
          });
      });
  }

  function initMap() {
    var configEl = document.getElementById("atik-harita-config");
    if (!configEl || typeof L === "undefined") {
      ensureProvincesLoaded();
      return;
    }

    var config;
    try {
      config = JSON.parse(configEl.textContent);
    } catch (e) {
      console.error("Harita yapılandırması okunamadı", e);
      return;
    }

    var haritaNoktalari = config.harita_noktalari || [];
    var detayPrefix = config.detay_prefix || "/atik/";
    var mapEl = document.getElementById("map");
    if (!mapEl) return;

    var urlParams = new URLSearchParams(window.location.search || "");
    var state = {
      source: (config.municipal_source || urlParams.get("source") || urlParams.get("mw_source") || "").trim(),
      city: "",
      district: "",
      facility_type: "",
      waste_type: "",
      nearby: false,
      userLat: null,
      userLng: null,
      nearbyLimit: 20,
      disableClusteringAtZoom: 15,
    };

    function popupIcerik(nokta) {
      var html = "";
      nokta.ilanlar.forEach(function (i) {
        html +=
          '<div class="mb-1"><b>' +
          i.baslik +
          '</b><br><a href="' +
          detayPrefix +
          i.id +
          '">İncele</a></div>';
      });
      return html;
    }

    function markerKonumlari(noktalar) {
      var sonuc = [];
      noktalar.forEach(function (nokta) {
        if (nokta.ilanlar.length === 1) {
          sonuc.push({ lat: nokta.lat, lng: nokta.lng, nokta: nokta });
          return;
        }
        var adim = (2 * Math.PI) / nokta.ilanlar.length;
        var yaricap = 0.0015 * Math.min(nokta.ilanlar.length, 10);
        nokta.ilanlar.forEach(function (_, idx) {
          sonuc.push({
            lat: nokta.lat + yaricap * Math.cos(idx * adim),
            lng: nokta.lng + yaricap * Math.sin(idx * adim),
            nokta: nokta,
          });
        });
      });
      return sonuc;
    }

    function escapeHtml(text) {
      return String(text || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;");
    }

    var map = L.map(mapEl).setView([41.015, 28.979], 11);
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: "© OpenStreetMap",
    }).addTo(map);

    var ilanSinirlar = [];
    var clusterOpts = {
      showCoverageOnHover: false,
      maxClusterRadius: 55,
      disableClusteringAtZoom: state.disableClusteringAtZoom,
      spiderfyOnMaxZoom: true,
      chunkedLoading: true,
    };
    var hasCluster = typeof L.markerClusterGroup === "function";
    var ibbKatmani = hasCluster ? L.markerClusterGroup(clusterOpts) : L.layerGroup();
    var municipalKatmani = hasCluster ? L.markerClusterGroup(Object.assign({}, clusterOpts)) : L.layerGroup();
    ibbKatmani.addTo(map);
    municipalKatmani.addTo(map);

    var mapLocate = window.MapLocate ? MapLocate.init(map, { popupText: "📍 Sen buradasın" }) : null;
    var fetchTimer = null;
    var requestSeq = 0;
    var statusEl = document.getElementById("mw-map-status");

    markerKonumlari(haritaNoktalari).forEach(function (m) {
      L.circleMarker([m.lat, m.lng], {
        radius: 10,
        color: "#146c43",
        fillColor: "#198754",
        fillOpacity: 0.9,
        weight: 2,
      })
        .addTo(map)
        .bindPopup(
          '<span class="badge bg-success">Kullanıcı İlanı</span><br>' + popupIcerik(m.nokta)
        );
      ilanSinirlar.push([m.lat, m.lng]);
    });

    function setStatus(text) {
      if (statusEl) statusEl.textContent = text || "";
    }

    function ilanlaraOrtala(extraBounds) {
      if (ilanSinirlar.length === 1) {
        map.setView(ilanSinirlar[0], 14);
        return;
      }
      if (ilanSinirlar.length > 1) {
        map.fitBounds(ilanSinirlar, { padding: [40, 40], maxZoom: 14 });
        return;
      }
      if (extraBounds && extraBounds.length) {
        map.fitBounds(extraBounds, { padding: [40, 40], maxZoom: 12 });
      }
    }

    function makeCircleMarker(m, options) {
      var color = options.color || "#0d6efd";
      var fill = options.fillColor || "#3d8bfd";
      var label = options.label || "Belediye Atık Noktası";
      var waste =
        m.waste_types && m.waste_types.length
          ? "<br><small>" + escapeHtml(m.waste_types.join(", ")) + "</small>"
          : "";
      var facility = m.facility_type
        ? "<br><small>" + escapeHtml(m.facility_type) + "</small>"
        : "";
      var mesafe =
        m.mesafe !== undefined ? "<br><small>~" + m.mesafe + " km</small>" : "";
      return L.circleMarker([m.lat, m.lng], {
        radius: 7,
        color: color,
        fillColor: fill,
        fillOpacity: 0.85,
        weight: 2,
      }).bindPopup(
        "<b>" +
          escapeHtml(label) +
          "</b><br><b>" +
          escapeHtml(m.ad) +
          "</b>" +
          facility +
          "<br>" +
          escapeHtml(m.adres || "") +
          waste +
          mesafe
      );
    }

    function fillLayer(layer, merkezler, options) {
      if (layer.clearLayers) layer.clearLayers();
      var bounds = [];
      (merkezler || []).forEach(function (m) {
        if (typeof m.lat !== "number" || typeof m.lng !== "number") return;
        bounds.push([m.lat, m.lng]);
        makeCircleMarker(m, options).addTo(layer);
      });
      return bounds;
    }

    function readFiltersFromDom() {
      var cityEl = document.getElementById("mw-filter-city");
      var districtEl = document.getElementById("mw-filter-district");
      var facilityEl = document.getElementById("mw-filter-facility");
      var wasteEl = document.getElementById("mw-filter-waste");
      state.city = cityEl ? cityEl.value : "";
      state.district = districtEl ? districtEl.value : "";
      state.facility_type = facilityEl ? facilityEl.value : "";
      state.waste_type = wasteEl ? wasteEl.value : "";
    }

    function buildMunicipalQuery() {
      var q = new URLSearchParams();
      if (state.source) q.set("source", state.source);
      if (state.city) q.set("city", state.city);
      if (state.district) q.set("district", state.district);
      if (state.facility_type) q.set("facility_type", state.facility_type);
      if (state.waste_type) q.set("waste_type", state.waste_type);

      if (state.nearby && state.userLat !== null && state.userLng !== null) {
        q.set("nearby", "1");
        q.set("lat", String(state.userLat));
        q.set("lng", String(state.userLng));
        q.set("limit", String(state.nearbyLimit));
        return "/api/municipal_waste_centers?" + q.toString();
      }

      // İl seçili değilken bbox UYGULAMA.
      // Varsayılan harita İstanbul'da açıldığı için bbox Konya'yı (ve diğer
      // şehirleri) kesiyordu; filtresiz modda İBB + Konya birlikte görünmeli.
      // İl seçiliyse zaten tüm il kayıtları gelir (bbox yok).
      q.set("limit", "2500");
      return "/api/municipal_waste_centers?" + q.toString();
    }

    function buildIbbQuery() {
      var q = new URLSearchParams();
      if (state.source) q.set("source", state.source);
      if (state.city) q.set("city", state.city);
      if (state.district) q.set("district", state.district);
      // facility/waste İBB canlı katmanını sıfırlamamalı — API tarafında korunur;
      // yine de tutarlılık için gönderilir (eşleşmezse İBB kalır).
      if (state.facility_type) q.set("facility_type", state.facility_type);
      if (state.waste_type) q.set("waste_type", state.waste_type);

      if (state.nearby && state.userLat !== null && state.userLng !== null) {
        q.set("nearby", "1");
        q.set("lat", String(state.userLat));
        q.set("lng", String(state.userLng));
        q.set("limit", String(state.nearbyLimit));
        return "/api/ibb_atik_merkezleri?" + q.toString();
      }

      if (!state.city) {
        var b = map.getBounds();
        q.set("north", String(b.getNorth()));
        q.set("south", String(b.getSouth()));
        q.set("east", String(b.getEast()));
        q.set("west", String(b.getWest()));
      }
      q.set("limit", "500");
      return "/api/ibb_atik_merkezleri?" + q.toString();
    }

    var EMPTY_REGION_MSG =
      "Bu bölge için henüz belediye atık merkezi verisi bulunmuyor.";

    function shouldLoadIbb() {
      if (state.source && state.source !== "ibb") return false;
      return true;
    }

    function shouldLoadMunicipal() {
      if (state.source === "ibb") return false;
      return true;
    }

    function mergeNearbyByDistance(ibbList, mwList, limit) {
      var tagged = [];
      (ibbList || []).forEach(function (row) {
        tagged.push({ src: "ibb", mesafe: row.mesafe, row: row });
      });
      (mwList || []).forEach(function (row) {
        tagged.push({ src: "mw", mesafe: row.mesafe, row: row });
      });
      tagged.sort(function (a, b) {
        var da = typeof a.mesafe === "number" ? a.mesafe : Number.POSITIVE_INFINITY;
        var db = typeof b.mesafe === "number" ? b.mesafe : Number.POSITIVE_INFINITY;
        return da - db;
      });
      var top = tagged.slice(0, limit);
      return {
        ibb: top
          .filter(function (t) {
            return t.src === "ibb";
          })
          .map(function (t) {
            return t.row;
          }),
        mw: top
          .filter(function (t) {
            return t.src === "mw";
          })
          .map(function (t) {
            return t.row;
          }),
      };
    }

    function fetchIbbData() {
      if (!shouldLoadIbb()) return Promise.resolve([]);
      return fetch(buildIbbQuery())
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          return Array.isArray(data) ? data : [];
        })
        .catch(function (err) {
          console.error("İBB harita hatası:", err);
          return [];
        });
    }

    function fetchMunicipalData() {
      if (!shouldLoadMunicipal()) return Promise.resolve([]);
      var seq = ++requestSeq;
      return fetch(buildMunicipalQuery())
        .then(function (res) {
          return res.json();
        })
        .then(function (data) {
          if (seq !== requestSeq) return null;
          return Array.isArray(data) ? data : [];
        })
        .catch(function (err) {
          console.error("Belediye harita hatası:", err);
          return [];
        });
    }

    function loadIbb() {
      return fetchIbbData().then(function (data) {
        return fillLayer(ibbKatmani, data, {
          label: "İBB Atık Merkezi",
          color: "#dc3545",
          fillColor: "#ff4444",
        });
      });
    }

    function loadMunicipal() {
      return fetchMunicipalData().then(function (liste) {
        if (liste === null) return { bounds: [], count: -1 };
        if (!shouldLoadMunicipal()) {
          if (municipalKatmani.clearLayers) municipalKatmani.clearLayers();
          return { bounds: [], count: 0 };
        }
        var bounds = fillLayer(municipalKatmani, liste, {
          label: "Belediye Atık Noktası",
          color: "#0d6efd",
          fillColor: "#3d8bfd",
        });
        return { bounds: bounds, count: liste.length };
      });
    }

    function refreshLayers(immediate, options) {
      options = options || {};
      if (fetchTimer) clearTimeout(fetchTimer);
      var run = function () {
        setStatus("Merkezler yükleniyor…");
        // Nearby birleşik sıralama için her kaynaktan daha geniş aday havuzu
        var prevLimit = state.nearbyLimit;
        if (state.nearby) state.nearbyLimit = Math.max(prevLimit, 40);

        Promise.all([fetchIbbData(), fetchMunicipalData()]).then(function (results) {
          if (state.nearby) state.nearbyLimit = prevLimit;
          var ibbList = results[0] || [];
          var mwList = results[1];
          if (mwList === null) return;

          if (!shouldLoadIbb()) {
            ibbList = [];
            if (ibbKatmani.clearLayers) ibbKatmani.clearLayers();
          }
          if (!shouldLoadMunicipal()) {
            mwList = [];
            if (municipalKatmani.clearLayers) municipalKatmani.clearLayers();
          }

          if (state.nearby) {
            var merged = mergeNearbyByDistance(ibbList, mwList, prevLimit);
            ibbList = merged.ibb;
            mwList = merged.mw;
          }

          var ibbBounds = fillLayer(ibbKatmani, ibbList, {
            label: "İBB Atık Merkezi",
            color: "#dc3545",
            fillColor: "#ff4444",
          });
          var mwBounds = fillLayer(municipalKatmani, mwList, {
            label: "Belediye Atık Noktası",
            color: "#0d6efd",
            fillColor: "#3d8bfd",
          });

          var ibbCount = ibbList.length;
          var mwCount = mwList.length;
          var total = ibbCount + mwCount;

          if (total === 0 && state.city) {
            setStatus(EMPTY_REGION_MSG);
          } else {
            setStatus(
              (state.nearby ? "Yakınımdakiler: " : state.city ? "Seçilen bölge: " : "Görünen alan: ") +
                total +
                " nokta" +
                (ibbCount && mwCount ? " (İBB " + ibbCount + " + belediye " + mwCount + ")" : "") +
                (hasCluster ? " (cluster)" : "")
            );
          }

          if (options.fitBounds) {
            var allBounds = (ibbBounds || []).concat(mwBounds || []);
            if (allBounds.length) {
              map.fitBounds(allBounds, { padding: [40, 40], maxZoom: 12 });
            }
          }
        });
      };
      if (immediate) run();
      else fetchTimer = setTimeout(run, 280);
    }

    function fillSelect(el, values, placeholder) {
      if (!el) return;
      var current = el.value;
      el.innerHTML = "";
      var opt0 = document.createElement("option");
      opt0.value = "";
      opt0.textContent = placeholder;
      el.appendChild(opt0);
      (values || []).forEach(function (v) {
        var opt = document.createElement("option");
        opt.value = v;
        opt.textContent = v;
        el.appendChild(opt);
      });
      if (current && values && values.indexOf(current) >= 0) el.value = current;
    }

    function setDistrictEnabled(enabled) {
      var districtEl = document.getElementById("mw-filter-district");
      if (!districtEl) return;
      districtEl.disabled = !enabled;
      if (!enabled) {
        fillSelect(districtEl, [], "İlçe (önce il seçin)");
        districtEl.value = "";
        state.district = "";
      }
    }

    function trTitleCase(value) {
      var text = String(value || "").trim();
      if (!text) return "";
      return text
        .split(/(\s+|\/|-)/)
        .map(function (token) {
          if (!token || /^\s+$/.test(token) || token === "/" || token === "-") return token;
          var low = token
            .replace(/I/g, "ı")
            .replace(/İ/g, "i")
            .replace(/Ğ/g, "ğ")
            .replace(/Ü/g, "ü")
            .replace(/Ş/g, "ş")
            .replace(/Ö/g, "ö")
            .replace(/Ç/g, "ç")
            .toLowerCase();
          var first = low.charAt(0);
          var rest = low.slice(1);
          if (first === "i") first = "İ";
          else first = first.toUpperCase();
          return first + rest;
        })
        .join("");
    }

    function provincesFromStaticJson(raw) {
      if (!Array.isArray(raw)) return [];
      return raw
        .map(function (entry) {
          return trTitleCase((entry && entry.name) || "");
        })
        .filter(Boolean);
    }

    function districtsFromStaticJson(raw, city) {
      if (!Array.isArray(raw) || !city) return [];
      var needle = trTitleCase(city);
      for (var i = 0; i < raw.length; i++) {
        var entry = raw[i];
        if (!entry || trTitleCase(entry.name || "") !== needle) continue;
        return (entry.districts || [])
          .map(function (d) {
            return trTitleCase((d && d.name) || "");
          })
          .filter(Boolean)
          .sort(function (a, b) {
            return a.localeCompare(b, "tr");
          });
      }
      return [];
    }

    function loadProvinces() {
      var cityEl = document.getElementById("mw-filter-city");
      if (!cityEl) {
        console.error("İl dropdown (#mw-filter-city) bulunamadı");
        return Promise.resolve();
      }
      return fetch("/api/turkey/provinces", { credentials: "same-origin" })
        .then(function (res) {
          if (!res.ok) {
            console.error("İl listesi HTTP", res.status, res.statusText);
            return res.json().catch(function () {
              return {};
            }).then(function (body) {
              throw new Error(
                "provinces_http_" + res.status + (body && body.error ? ":" + body.error : "")
              );
            });
          }
          return res.json();
        })
        .then(function (data) {
          var provinces = (data && data.provinces) || [];
          if (!provinces.length) {
            throw new Error("provinces_empty");
          }
          fillSelect(cityEl, provinces, "İl (hepsi)");
          setDistrictEnabled(false);
          console.info("İl listesi yüklendi:", provinces.length);
        })
        .catch(function (err) {
          console.error("İl listesi API hatası, static JSON deneniyor:", err);
          return fetch("/static/data/il-ilce-list.json", { credentials: "same-origin" })
            .then(function (res) {
              if (!res.ok) throw new Error("static_il_ilce_http_" + res.status);
              return res.json();
            })
            .then(function (raw) {
              var provinces = provincesFromStaticJson(raw);
              if (!provinces.length) throw new Error("static_provinces_empty");
              fillSelect(cityEl, provinces, "İl (hepsi)");
              setDistrictEnabled(false);
              console.info("İl listesi static JSON ile yüklendi:", provinces.length);
            })
            .catch(function (fallbackErr) {
              console.error("İl listesi yüklenemedi:", fallbackErr);
              setStatus("İl listesi yüklenemedi");
            });
        });
    }

    function loadDistrictsForCity(city) {
      var districtEl = document.getElementById("mw-filter-district");
      if (!city) {
        setDistrictEnabled(false);
        return Promise.resolve();
      }
      setDistrictEnabled(true);
      fillSelect(districtEl, [], "İlçe yükleniyor…");
      return fetch("/api/turkey/districts?city=" + encodeURIComponent(city), {
        credentials: "same-origin",
      })
        .then(function (res) {
          if (!res.ok) {
            console.error("İlçe listesi HTTP", res.status);
            return res.json().catch(function () {
              return {};
            }).then(function (body) {
              throw new Error(
                "districts_http_" + res.status + (body && body.error ? ":" + body.error : "")
              );
            });
          }
          return res.json();
        })
        .then(function (body) {
          var districts = (body && body.districts) || [];
          fillSelect(districtEl, districts, "İlçe (hepsi)");
          districtEl.disabled = false;
        })
        .catch(function (err) {
          console.error("İlçe listesi API hatası, static JSON deneniyor:", err);
          return fetch("/static/data/il-ilce-list.json", { credentials: "same-origin" })
            .then(function (res) {
              if (!res.ok) throw new Error("static_il_ilce_http_" + res.status);
              return res.json();
            })
            .then(function (raw) {
              var districts = districtsFromStaticJson(raw, city);
              fillSelect(districtEl, districts, "İlçe (hepsi)");
              districtEl.disabled = false;
            })
            .catch(function (fallbackErr) {
              console.error("İlçe listesi yüklenemedi:", fallbackErr);
              fillSelect(districtEl, [], "İlçe (hepsi)");
              districtEl.disabled = false;
            });
        });
    }

    function loadMeta() {
      var metaUrl = "/api/municipal_waste_centers/meta";
      if (state.source) metaUrl += "?source=" + encodeURIComponent(state.source);
      return fetch(metaUrl)
        .then(function (res) {
          return res.json();
        })
        .then(function (meta) {
          fillSelect(
            document.getElementById("mw-filter-facility"),
            meta.facility_types || [],
            "Tesis tipi (hepsi)"
          );
          fillSelect(
            document.getElementById("mw-filter-waste"),
            meta.waste_types || [],
            "Atık türü (hepsi)"
          );
        })
        .catch(function (err) {
          console.error("Filtre meta hatası:", err);
        });
    }

    function wireFilters() {
      var cityEl = document.getElementById("mw-filter-city");
      if (cityEl) {
        cityEl.addEventListener("change", function () {
          readFiltersFromDom();
          state.district = "";
          state.nearby = false;
          var nearbyBtn = document.getElementById("mw-nearby-btn");
          if (nearbyBtn) nearbyBtn.classList.remove("active");
          loadDistrictsForCity(state.city).then(function () {
            refreshLayers(true, { fitBounds: !!state.city });
          });
        });
      }

      ["mw-filter-district", "mw-filter-facility", "mw-filter-waste"].forEach(function (id) {
        var el = document.getElementById(id);
        if (!el) return;
        el.addEventListener("change", function () {
          readFiltersFromDom();
          state.nearby = false;
          var nearbyBtn = document.getElementById("mw-nearby-btn");
          if (nearbyBtn) nearbyBtn.classList.remove("active");
          refreshLayers(true, {
            fitBounds: id === "mw-filter-district" && !!state.district,
          });
        });
      });

      var nearbyBtn = document.getElementById("mw-nearby-btn");
      if (nearbyBtn) {
        nearbyBtn.addEventListener("click", function () {
          function enableNearby(lat, lng) {
            state.userLat = lat;
            state.userLng = lng;
            state.nearby = true;
            nearbyBtn.classList.add("active");
            map.setView([lat, lng], 13);
            refreshLayers(true);
          }
          if (state.userLat !== null && state.userLng !== null) {
            enableNearby(state.userLat, state.userLng);
            return;
          }
          if (!navigator.geolocation) {
            setStatus("Konum desteklenmiyor");
            return;
          }
          setStatus("Konum alınıyor…");
          navigator.geolocation.getCurrentPosition(
            function (pos) {
              enableNearby(pos.coords.latitude, pos.coords.longitude);
            },
            function () {
              setStatus("Konum alınamadı");
            },
            { enableHighAccuracy: true, timeout: 10000 }
          );
        });
      }

      var clearBtn = document.getElementById("mw-filter-clear");
      if (clearBtn) {
        clearBtn.addEventListener("click", function () {
          state.nearby = false;
          state.city = state.district = state.facility_type = state.waste_type = "";
          var citySelect = document.getElementById("mw-filter-city");
          if (citySelect) citySelect.value = "";
          setDistrictEnabled(false);
          ["mw-filter-facility", "mw-filter-waste"].forEach(function (id) {
            var el = document.getElementById(id);
            if (el) el.value = "";
          });
          if (nearbyBtn) nearbyBtn.classList.remove("active");
          refreshLayers(true);
        });
      }
    }

    map.on("moveend", function () {
      if (state.nearby || state.city) return;
      // Belediye katmanı bbox kullanmaz (Konya kaybolmasın).
      // Pan'de yalnızca İBB canlı katmanını viewport'a göre yenile.
      if (fetchTimer) clearTimeout(fetchTimer);
      fetchTimer = setTimeout(function () {
        fetchIbbData().then(function (ibbList) {
          if (!shouldLoadIbb()) {
            if (ibbKatmani.clearLayers) ibbKatmani.clearLayers();
            return;
          }
          fillLayer(ibbKatmani, ibbList || [], {
            label: "İBB Atık Merkezi",
            color: "#dc3545",
            fillColor: "#ff4444",
          });
        });
      }, 280);
    });

    wireFilters();
    loadProvinces();
    loadMeta();

    function bootstrap(userLat, userLng) {
      if (userLat !== null && userLng !== null) {
        state.userLat = userLat;
        state.userLng = userLng;
      }
      setStatus("Merkezler yükleniyor…");
      Promise.all([loadIbb(), loadMunicipal()]).then(function (results) {
        var ibbBounds = results[0] || [];
        var mwResult = results[1] || { bounds: [], count: 0 };
        var ibbCount = Array.isArray(ibbBounds) ? ibbBounds.length : 0;
        var mwCount = mwResult.count || 0;
        var total = ibbCount + mwCount;
        setStatus(
          total +
            " nokta" +
            (ibbCount && mwCount ? " (İBB " + ibbCount + " + belediye " + mwCount + ")" : "") +
            (hasCluster ? " (cluster)" : "")
        );
        if (!state.nearby) {
          ilanlaraOrtala((ibbBounds || []).concat(mwResult.bounds || []));
        }
      });
    }

    if (mapLocate) {
      mapLocate.acquireLocation({
        fly: false,
        onSuccess: function (userLat, userLng) {
          bootstrap(userLat, userLng);
        },
        onError: function () {
          bootstrap(null, null);
        },
      });
    } else {
      bootstrap(null, null);
    }

    setTimeout(function () {
      map.invalidateSize();
    }, 100);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", initMap);
  } else {
    initMap();
  }
})();
