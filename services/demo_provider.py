"""Demo Provider — MASTER_DATASET üzerinden sabit şehir senaryoları.

Rastgele veri üretmez. Tüm paneller aynı şehir paketinden beslenir.
Gerçek API / endpoint / DB akışını değiştirmez.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta
from typing import Any

from services.demo_dataset import (
    CATEGORY_KEYS,
    MARKETPLACE_ORGS,
    SUSTAINABILITY_TARGETS,
    _CITY_GEO,
    _CITY_SEEDS,
    _DISTRICTS,
)
from services.prediction_engine import (
    FORECAST_HORIZONS_DAYS,
    HORIZON_LABELS,
    LOOKBACK_MONTHS,
    METRIC_KEYS,
)
from utils import utc_now

DEFAULT_CITY = "Sakarya"

_MONTH_LABELS_TR = (
    "Oca", "Şub", "Mar", "Nis", "May", "Haz",
    "Tem", "Ağu", "Eyl", "Eki", "Kas", "Ara",
)


def _norm_city(il: str | None) -> str:
    if not il:
        return DEFAULT_CITY
    key = str(il).strip()
    if key in _CITY_SEEDS:
        return key
    lower_map = {k.casefold(): k for k in _CITY_SEEDS}
    return lower_map.get(key.casefold(), DEFAULT_CITY)


def _grade_for(puan: float) -> str:
    """Yedek harf notu (şehir hedefleri SUSTAINABILITY_TARGETS'tan gelir)."""
    from services.sustainability_scoring import grade_for_score

    return grade_for_score(puan)


def _raw_for_puan(puan: float) -> dict[str, float]:
    """Hedef puana yakın radar/kriter dağılımı (deterministik)."""
    base = max(35.0, min(98.0, float(puan)))
    return {
        "geri_donusum": round(base - 2, 1),
        "teslim": round(min(98.0, base + 4), 1),
        "katilim": round(base - 6, 1),
        "kaynak_paylasimi": round(base - 3, 1),
        "karbon": round(base - 8, 1),
        "teslim_suresi": round(min(96.0, base + 1), 1),
        "ai_dogruluk": round(base - 5, 1),
    }


def _month_keys(n: int, now: datetime | None = None) -> list[str]:
    now = now or utc_now()
    keys = []
    y, m = now.year, now.month
    for i in range(n - 1, -1, -1):
        mm = m - i
        yy = y
        while mm <= 0:
            mm += 12
            yy -= 1
        keys.append(f"{yy:04d}-{mm:02d}")
    return keys


def _trend_factor(kind: str, idx: int, n: int) -> float:
    """0..n-1 indeks için deterministik çarpan (rastgele değil)."""
    t = idx / max(n - 1, 1)
    if kind == "artan":
        return 0.82 + 0.28 * t
    if kind == "azalan":
        return 1.12 - 0.22 * t
    if kind == "kampanya_yukselen":
        # son 3 ayda yükseliş
        if idx >= n - 3:
            return 0.95 + 0.22 * ((idx - (n - 3)) / 2.0)
        return 0.78 + 0.08 * t
    return 0.96 + 0.04 * t  # sabit


def _build_monthly_history(seed: dict, *, months: int = 12, now: datetime | None = None) -> list[dict]:
    keys = _month_keys(months, now)
    total = seed["total_listings"]
    delivery = seed["delivery_pct"]
    citizen = seed["citizen_pct"]
    co2_month = (seed["co2_ton"] * 1000.0) / 12.0
    atik_base = total * 4.2  # kg proxy
    trends = seed["trends"]
    rows = []
    for i, ay in enumerate(keys):
        # genel hacim hafif yükseliş
        vol = 0.78 + 0.22 * (i / max(months - 1, 1))
        e_factor = _trend_factor(trends.get("Elektronik", "sabit"), i, months)
        rows.append({
            "ay": ay,
            "atik_kg": round(atik_base * vol / months * 1.15, 1),
            "co2_kg": round(co2_month * vol, 1),
            "kaynak_adet": int(round(total * 0.35 * vol / months)),
            "teslim_orani": round(delivery * (0.90 + 0.12 * (i / max(months - 1, 1))), 1),
            "katilim": round(citizen * (0.88 + 0.14 * (i / max(months - 1, 1))), 1),
            "elektronik_index": round(100 * e_factor, 1),
            "organik_index": round(
                100 * _trend_factor(trends.get("Organik", "azalan"), i, months), 1
            ),
            "yag_index": round(
                100 * _trend_factor(trends.get("Bitkisel yağ", "kampanya_yukselen"), i, months), 1
            ),
        })
    return rows


def _build_heatmap(city: str, *, count: int = 42) -> list[list[float]]:
    """Şehir merkezi yoğun, kırsal düşük — gerçekçi heat noktaları (rastgele değil)."""
    geo = _CITY_GEO[city]
    hotspots = geo["hotspots"]
    center_lat, center_lng = geo["center"]
    points: list[list[float]] = []
    # Merkez etrafında sıkı halka
    center_offsets = [
        (0.0, 0.0, 1.0),
        (0.003, 0.002, 0.95),
        (-0.002, 0.004, 0.92),
        (0.004, -0.003, 0.90),
        (-0.005, -0.002, 0.88),
        (0.006, 0.005, 0.85),
        (-0.004, 0.006, 0.84),
        (0.002, -0.006, 0.82),
        (0.007, -0.001, 0.80),
        (-0.006, 0.003, 0.78),
        (0.001, 0.008, 0.76),
        (-0.008, -0.004, 0.72),
    ]
    for ox, oy, intensity in center_offsets:
        points.append([
            round(center_lat + ox, 5),
            round(center_lng + oy, 5),
            round(intensity, 3),
        ])
    # Temalı hotspot'lar (sanayi / üniversite / AVM) — orta yoğunluk
    ring = [
        (0.0, 0.0), (0.005, 0.003), (-0.004, 0.006), (0.007, -0.005),
        (-0.006, -0.003), (0.003, 0.008), (-0.008, 0.002), (0.009, 0.004),
    ]
    i = 0
    while len(points) < count:
        _name, lat, lng, intensity = hotspots[i % len(hotspots)]
        ox, oy = ring[i % len(ring)]
        # Merkeze uzaklık arttıkça yoğunluk düşer
        dist = abs(lat - center_lat) + abs(lng - center_lng)
        rural_penalty = 0.55 if dist > 0.15 else (0.75 if dist > 0.08 else 1.0)
        points.append([
            round(lat + ox * 0.6, 5),
            round(lng + oy * 0.6, 5),
            round(min(1.0, intensity * rural_penalty * (0.95 - (i % 5) * 0.04)), 3),
        ])
        i += 1
    return points[:count]


def _build_activities(city: str, districts: dict, *, limit: int = 120) -> list[dict]:
    templates = [
        ("yeni_ilan", "{kat} Atık ilanı oluşturuldu", "atik"),
        ("teslim", "{kat} teslim edildi", "atik"),
        ("kampanya", "{kat} kampanyası tamamlandı", "kampanya"),
        ("rezervasyon", "Rezervasyon onaylandı", "kaynak"),
        ("yeni_ilan", "Kaynak paylaşım ilanı açıldı", "kaynak"),
        ("teslim", "Kaynak teslimi tamamlandı", "kaynak"),
        ("yogunluk", "{bolge} bölgesinde yoğunluk artışı", "ops"),
        ("yuksek_risk", "Yüksek riskli ilan incelendi", "moderasyon"),
    ]
    cats = list(CATEGORY_KEYS)
    dist_names = list(districts.keys()) or [city]
    items = []
    now = utc_now()
    for i in range(limit):
        tip, title_fmt, tur = templates[i % len(templates)]
        bolge = dist_names[i % len(dist_names)]
        kat = cats[i % len(cats)]
        mins = (i * 7 + 3) % 400
        zaman = now - timedelta(minutes=mins)
        if mins < 60:
            zaman_label = f"{mins} dk önce"
        elif mins < 180:
            zaman_label = f"{mins // 60} saat önce"
        else:
            zaman_label = f"{mins // 60} saat önce"
        baslik = title_fmt.format(kat=kat, bolge=bolge)
        items.append({
            "tip": tip,
            "baslik": baslik,
            "kategori": kat,
            "tur": tur,
            "zaman": zaman.isoformat(),
            "zaman_label": zaman_label,
            "meta": {"il": city, "ilce": bolge},
        })
    # en yeniler önce
    items.sort(key=lambda x: x["zaman"], reverse=True)
    return items


def _build_district_stats(seed: dict, districts: dict) -> list[dict]:
    total = seed["total_listings"]
    names = list(districts.keys())
    n = max(len(names), 1)
    # deterministik ağırlıklar
    weights = [max(1, (i * 3 + 7) % 11 + 4) for i in range(n)]
    wsum = sum(weights)
    rows = []
    for i, name in enumerate(names):
        share = weights[i] / wsum
        ilan = int(round(total * share * 0.55))
        rows.append({
            "bolge": name,
            "ilan_sayisi": ilan,
            "atik_kg": round(ilan * 18.5, 1),
            "kaynak_adet": int(round(ilan * 0.4)),
            "kullanici_yogunlugu": int(round(seed["population"] * share / 120)),
        })
    return sorted(rows, key=lambda r: (-r["ilan_sayisi"], r["bolge"]))


def _city_growth_pct(city: str, history: list[dict], trends: dict) -> float:
    """6–12 aylık hacim + kategori trendlerinden şehir bazlı gelişim % (puandan bağımsız)."""
    if len(history) >= 2:
        first = float(history[0].get("atik_kg") or 1)
        last = float(history[-1].get("atik_kg") or first)
        vol = ((last - first) / max(first, 1.0)) * 100.0
    else:
        vol = 5.0
    boost = 0.0
    for t in (trends or {}).values():
        if t == "artan":
            boost += 4.5
        elif t == "kampanya_yukselen":
            boost += 9.0
        elif t == "azalan":
            boost -= 3.5
    offset = (sum(ord(c) for c in city) % 17) - 8
    return round(vol * 0.55 + boost + offset * 0.35, 1)


def _risk_score(puan: float, teslim_orani: float, gelisim: float) -> float:
    """Yüksek = daha riskli (düşük skor + zayıf teslim + negatif gelişim)."""
    return round(
        max(0.0, 100.0 - float(puan))
        + max(0.0, 75.0 - float(teslim_orani)) * 0.35
        + max(0.0, -float(gelisim)) * 0.8,
        1,
    )


def _build_city_package(city: str) -> dict:
    seed = _CITY_SEEDS[city]
    districts = _DISTRICTS.get(city) or {}
    geo = _CITY_GEO[city]
    puan, grade = SUSTAINABILITY_TARGETS[city]
    puan = float(puan)
    raw = _raw_for_puan(puan)
    history = _build_monthly_history(seed, months=12)
    last = history[-1]
    aktif = int(round(seed["total_listings"] * 0.42))
    teslim = int(round(seed["total_listings"] * (seed["delivery_pct"] / 100.0) * 0.55))
    gunluk = int(round(seed["population"] * (seed["citizen_pct"] / 100.0) / 900))
    co2_kg = round(seed["co2_ton"] * 1000.0, 1)

    dashboard = {
        "bugun_ilan": max(8, int(seed["total_listings"] * 0.004)),
        "bugun_aktif_ilan": max(5, int(seed["total_listings"] * 0.003)),
        "toplam_aktif_ilan": seed["total_listings"],
        "aktif_kaynak": int(aktif * 0.45),
        "aktif_atik": int(aktif * 0.55),
        "toplam_teslim": teslim,
        "geri_kazanilan_atik_kg": round(seed["total_listings"] * 5.8, 1),
        "geri_kazanilan_kaynak_adet": int(teslim * 0.4),
        "geri_kazanilan_kaynak_skor": int(teslim * 42),
        "atik_teslim": int(teslim * 0.55),
        "gunluk_kullanici": gunluk,
        "aktif_kurum": max(4, len([o for o in MARKETPLACE_ORGS if o["il"] == city]) or 6),
        "ortalama_teslim_gun": round(3.8 - (seed["delivery_pct"] - 70) * 0.04, 1),
        "co2e_kg": co2_kg,
        "etki_adet": teslim,
        "vatandas_katilim_orani": seed["citizen_pct"],
        "teslim_orani": seed["delivery_pct"],
        "enerji_kwh": seed["energy_kwh"],
        "su_ton": seed["water_ton"],
        "population": seed["population"],
    }

    from constants import SUSTAINABILITY_CRITERION_LABELS, SUSTAINABILITY_WEIGHTS

    criteria = []
    weighted_sum = 0.0
    for key, weight in SUSTAINABILITY_WEIGHTS.items():
        part = raw[key] * (weight / 100.0)
        weighted_sum += part
        criteria.append({
            "key": key,
            "label": SUSTAINABILITY_CRITERION_LABELS[key],
            "score": raw[key],
            "weight": weight,
            "weighted": round(part, 2),
            "missing_data": False,
        })

    sustainability = {
        "il": city,
        "ilce": None,
        "mahalle": None,
        "puan": puan,
        "grade": grade,
        "criteria": criteria,
        "raw": raw,
        "missing": {k: False for k in raw},
        "metrics": {
            "total": seed["total_listings"],
            "atik_total": int(seed["total_listings"] * 0.55),
            "kaynak_total": int(seed["total_listings"] * 0.45),
            "teslim": teslim,
            "atik_teslim": int(teslim * 0.55),
            "kaynak_teslim": int(teslim * 0.45),
            "co2e_kg": co2_kg,
            "atik_kg": dashboard["geri_kazanilan_atik_kg"],
            "etki_adet": teslim,
            "ortalama_teslim_gun": dashboard["ortalama_teslim_gun"],
            "katilim_orani": seed["citizen_pct"],
            "kategori_paylari": dict(seed["categories"]),
            "teslim_orani": seed["delivery_pct"],
            "geri_donusum_orani": round(raw["geri_donusum"], 1),
            "enerji_kwh": seed["energy_kwh"],
            "su_ton": seed["water_ton"],
        },
    }

    # 6 aylık sustainability history — monthly_history ile uyumlu
    hist6 = history[-6:]
    gelisim = _city_growth_pct(city, history, seed["trends"])
    sus_series = []
    start_p = round(puan - max(3.0, abs(gelisim) * 0.35), 1)
    for i, row in enumerate(hist6):
        t = i / max(len(hist6) - 1, 1)
        p = round(start_p + (puan - start_p) * t, 1)
        sus_series.append({
            "ay": row["ay"],
            "puan": p,
            "teslim_orani": row["teslim_orani"],
            "geri_donusum": round(raw["geri_donusum"] - 4 + i, 1),
            "karbon": round(raw["karbon"] - 3 + i * 0.8, 1),
            "ilan": int(seed["total_listings"] * (0.7 + i * 0.05) / 12),
            "teslim": int(teslim * (0.7 + i * 0.05) / 12),
            "co2e_kg": row["co2_kg"],
        })

    district_rows = _build_district_stats(seed, districts)
    top_district = district_rows[0] if district_rows else None
    heat = _build_heatmap(
        city, count=48 if city in ("İstanbul", "Ankara", "İzmir") else 36
    )

    return {
        "population": seed["population"],
        "districts": districts,
        "neighborhoods": {
            d: list(mah) for d, mah in districts.items()
        },
        "waste_categories": dict(seed["categories"]),
        "monthly_history": history,
        "prediction": {
            "baseline_last": last,
            "trends": dict(seed["trends"]),
        },
        "sustainability": sustainability,
        "sustainability_history": {
            "months": 6,
            "series": sus_series,
            "labels": [s["ay"] for s in sus_series],
            "puanlar": [s["puan"] for s in sus_series],
            "change_pct": gelisim,
            "trend": "yukselis" if gelisim >= 0 else "dusus",
        },
        "gelisim_yuzde": gelisim,
        "risk_skoru": _risk_score(puan, seed["delivery_pct"], gelisim),
        "heatmap": heat,
        "heat_points": heat,
        "map_center": {
            "lat": geo["center"][0],
            "lng": geo["center"][1],
            "zoom": 11 if city == "İstanbul" else 12,
        },
        "leaderboard_meta": {"puan": puan, "grade": grade},
        "activities": _build_activities(city, districts, limit=120),
        "ai_summary": list(seed["ai_bullets"]),
        "marketplace": [o for o in MARKETPLACE_ORGS if o["il"] == city] or MARKETPLACE_ORGS[:5],
        "dashboard": dashboard,
        "district_stats": district_rows,
        "ops_cards": {
            "bugun_acilan": dashboard["bugun_ilan"],
            "bekleyen_teslimler": max(3, int(dashboard["bugun_ilan"] * 0.6)),
            "son_24_saat": {
                "ilan": dashboard["bugun_ilan"] + 4,
                "teslim": max(2, dashboard["bugun_ilan"] // 2),
            },
            "en_yogun_mahalle": top_district,
            "riskli_bolgeler": [
                {
                    "bolge": r["bolge"],
                    "ilan_sayisi": r["ilan_sayisi"],
                    "seviye": "yüksek" if i == 0 else "orta",
                }
                for i, r in enumerate(district_rows[:3])
            ],
            "kritik_kategori": {
                "kategori": "Elektronik",
                "degisim_yuzde": 18.0,
                "bu_hafta": max(12, int(seed["total_listings"] * 0.01)),
            },
            "vatandas_katilimi": {
                "gunluk": gunluk,
                "toplam": int(seed["population"] * seed["citizen_pct"] / 100 / 40),
                "oran": seed["citizen_pct"],
            },
            "ai_uyarilari": 3 if puan < 70 else 2,
            "yuksek_risk_ilan": 2 if puan < 70 else 1,
        },
        "center": geo["center"],
        "hotspots": geo["hotspots"],
        "trends": dict(seed["trends"]),
        "energy_kwh": seed["energy_kwh"],
        "water_ton": seed["water_ton"],
        "co2_ton": seed["co2_ton"],
    }


def _build_master_dataset() -> dict[str, dict]:
    return {city: _build_city_package(city) for city in _CITY_SEEDS}


MASTER_DATASET: dict[str, dict] = _build_master_dataset()


def get_city(il: str | None = None) -> dict:
    return MASTER_DATASET[_norm_city(il)]


def list_cities() -> list[str]:
    return sorted(MASTER_DATASET.keys(), key=lambda c: -SUSTAINABILITY_TARGETS[c][0])


def national_leaderboard() -> list[dict]:
    rows = []
    for i, city in enumerate(list_cities(), start=1):
        pkg = MASTER_DATASET[city]
        sus = pkg["sustainability"]
        rows.append({
            "sira": i,
            "belediye_id": -1000 - i,
            "belediye_adi": f"{city} Belediyesi",
            "il": city,
            "ilce": None,
            "puan": sus["puan"],
            "grade": sus["grade"],
            "scope": "il",
            "raw": sus["raw"],
        })
    return rows


# --- Panel API (mevcut şemalar) ---


def _district_share(pkg: dict, ilce: str | None = None, mahalle: str | None = None) -> float:
    """İlçe/mahalle seçilince MASTER toplamına göre ölçek (0.05–1)."""
    if not ilce:
        return 1.0
    stats = pkg.get("district_stats") or []
    total = sum(int(r.get("ilan_sayisi") or 0) for r in stats) or 1
    key = str(ilce).strip()
    row = next((r for r in stats if r.get("bolge") == key), None)
    if row is None:
        row = next(
            (
                r
                for r in stats
                if key.casefold() in str(r.get("bolge") or "").casefold()
                or str(r.get("bolge") or "").casefold() in key.casefold()
            ),
            None,
        )
    if row is None:
        share = 1.0 / max(len(stats), 1)
    else:
        share = float(row.get("ilan_sayisi") or 0) / total
    if mahalle and key in (pkg.get("districts") or {}):
        mahs = pkg["districts"][key]
        if mahalle in mahs and mahs:
            share = share / len(mahs)
    return max(0.05, min(1.0, round(share, 4)))


def _scale_number(value, share: float):
    if share >= 0.999:
        return value
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int):
        return max(0, int(round(value * share)))
    if isinstance(value, float):
        return round(value * share, 1)
    return value


def _scale_dashboard(data: dict, share: float) -> dict:
    if share >= 0.999:
        return data
    skip = {"teslim_orani", "vatandas_katilim_orani", "ortalama_teslim_gun", "filtre"}
    out = deepcopy(data)
    for k, v in list(out.items()):
        if k in skip:
            continue
        out[k] = _scale_number(v, share)
    return out


def dashboard_kpis(*, il=None, ilce=None, mahalle=None) -> dict:
    city = _norm_city(il)
    pkg = get_city(city)
    share = _district_share(pkg, ilce, mahalle)
    data = _scale_dashboard(deepcopy(pkg["dashboard"]), share)
    data["filtre"] = {"il": il or city, "ilce": ilce, "mahalle": mahalle}
    data["_district_share"] = share
    return data


def heat_map_points(*, il=None, ilce=None, mahalle=None, yogunluk="atik") -> list:
    pkg = get_city(il)
    pts = deepcopy(pkg.get("heat_points") or pkg["heatmap"])
    scale = {"kaynak": 0.85, "teslim": 1.1}.get((yogunluk or "atik").lower(), 1.0)
    pts = [[p[0], p[1], round(min(1.0, p[2] * scale), 3)] for p in pts]

    if ilce:
        key = str(ilce).strip().casefold()
        hotspots = pkg.get("hotspots") or []
        anchors = []
        for h in hotspots:
            if isinstance(h, (list, tuple)) and len(h) >= 3:
                name = str(h[0] or "").casefold()
                lat_h, lng_h = float(h[1]), float(h[2])
            elif isinstance(h, dict):
                name = str(h.get("name") or h.get("label") or "").casefold()
                lat_h, lng_h = float(h["lat"]), float(h["lng"])
            else:
                continue
            if key in name or name in key or any(
                part and part in name for part in key.split()
            ):
                anchors.append((lat_h, lng_h))
        # İlçe adıyla eşleşen hotspot yoksa district sırasına göre merkez kaydır
        if not anchors and pkg.get("center"):
            lat0, lng0 = pkg["center"]
            districts = list((pkg.get("districts") or {}).keys())
            idx = next(
                (i for i, d in enumerate(districts) if d.casefold() == key),
                0,
            )
            anchors = [(lat0 + (idx % 5 - 2) * 0.04, lng0 + (idx % 3 - 1) * 0.05)]

        filtered = []
        for p in pts:
            for alat, alng in anchors:
                if abs(p[0] - alat) <= 0.09 and abs(p[1] - alng) <= 0.11:
                    filtered.append(p)
                    break
        if len(filtered) >= 5:
            pts = filtered
        else:
            share = _district_share(pkg, ilce, mahalle)
            n = max(8, int(len(pts) * share))
            pts = pts[:n]

    return pts


def mahalle_rows(*, il=None, ilce=None, mahalle=None) -> list[dict]:
    pkg = get_city(il)
    if ilce and ilce in pkg["districts"]:
        mahalleler = pkg["districts"][ilce]
        base = next((r for r in pkg["district_stats"] if r["bolge"] == ilce), None)
        total = (base or {}).get("ilan_sayisi") or 40
        rows = []
        for i, m in enumerate(mahalleler):
            share = (len(mahalleler) - i) / sum(range(1, len(mahalleler) + 1))
            rows.append({
                "bolge": m,
                "ilan_sayisi": max(1, int(total * share)),
                "atik_kg": round(total * share * 18.5, 1),
                "kaynak_adet": max(1, int(total * share * 0.4)),
                "kullanici_yogunlugu": max(5, int(30 * share * 10)),
            })
        if mahalle:
            rows = [r for r in rows if r["bolge"] == mahalle] or rows
        return sorted(rows, key=lambda r: (-r["ilan_sayisi"], r["bolge"]))
    return deepcopy(pkg["district_stats"])


def geography_options(*, il=None, ilce=None) -> dict:
    """MASTER_DATASET ilçe / mahalle listesi."""
    city = _norm_city(il)
    pkg = get_city(city)
    districts = pkg["districts"]
    ilceler = list(districts.keys())
    mahalleler = []
    if ilce and ilce in districts:
        mahalleler = list(districts[ilce])
    return {
        "iller": list_cities(),
        "ilceler": ilceler,
        "mahalleler": mahalleler,
    }


def kategori_analizi(*, il=None, ilce=None, mahalle=None) -> dict:
    """Belediye kategori grafik şeması — MASTER waste_categories."""
    from constants import MUNICIPALITY_CATEGORY_GROUPS

    pkg = get_city(il)
    share = _district_share(pkg, ilce, mahalle)
    raw = pkg["waste_categories"]
    # MASTER "Bitkisel yağ" → UI grubu "Bitkisel Yağ"
    alias = {"Bitkisel yağ": "Bitkisel Yağ", "Elektronik": "Elektronik"}
    counts = {g: 0 for g in MUNICIPALITY_CATEGORY_GROUPS}
    total_listings = int(round(pkg["dashboard"]["toplam_aktif_ilan"] * share))
    for name, pct in raw.items():
        key = alias.get(name, name)
        if key not in counts:
            key = "Diğer"
        counts[key] = counts.get(key, 0) + int(round(total_listings * pct / 100.0))
    labels = list(MUNICIPALITY_CATEGORY_GROUPS)
    values = [counts[g] for g in labels]
    return {
        "labels": labels,
        "values": values,
        "adetler": values,
        "rows": [{"kategori": k, "adet": counts[k]} for k in labels],
        "toplam": sum(values),
    }


def ops_center(*, il=None, ilce=None, mahalle=None) -> dict:
    pkg = get_city(il)
    share = _district_share(pkg, ilce, mahalle)
    ozet = dashboard_kpis(il=il, ilce=ilce, mahalle=mahalle)
    cat = kategori_analizi(il=il, ilce=ilce, mahalle=mahalle)
    hist = pkg["monthly_history"][-12:]
    month_labels = [
        _MONTH_LABELS_TR[int(str(row["ay"]).split("-")[1]) - 1] for row in hist
    ]
    cards = deepcopy(pkg["ops_cards"])
    if share < 0.999:
        cards["bugun_acilan"] = _scale_number(cards["bugun_acilan"], share)
        cards["bekleyen_teslimler"] = _scale_number(cards["bekleyen_teslimler"], share)
        cards["son_24_saat"] = {
            "ilan": _scale_number(cards["son_24_saat"]["ilan"], share),
            "teslim": _scale_number(cards["son_24_saat"]["teslim"], share),
        }
        if cards.get("en_yogun_mahalle") and ilce:
            cards["en_yogun_mahalle"] = {
                **cards["en_yogun_mahalle"],
                "bolge": ilce,
                "ilan_sayisi": _scale_number(
                    cards["en_yogun_mahalle"].get("ilan_sayisi") or 10, share
                ),
            }

    charts = {
        "category": {
            "labels": cat["labels"],
            "values": cat["values"],
        },
        "trend": {
            "labels": month_labels,
            "values": [round(float(row["atik_kg"]) * share, 1) for row in hist],
        },
        "teslim_history": {
            "labels": month_labels,
            "values": [float(row["teslim_orani"]) for row in hist],
        },
        "delivery": {
            "labels": ["Teslim", "Aktif", "Bekleyen"],
            "values": [
                ozet["toplam_teslim"],
                ozet["toplam_aktif_ilan"],
                cards["bekleyen_teslimler"],
            ],
            "oran": ozet.get("teslim_orani"),
        },
        "radar": {
            "labels": [c["label"] for c in pkg["sustainability"]["criteria"]],
            "values": [c["score"] for c in pkg["sustainability"]["criteria"]],
        },
        "history": {
            "labels": [
                _MONTH_LABELS_TR[int(a.split("-")[1]) - 1]
                for a in pkg["sustainability_history"]["labels"]
            ],
            "values": pkg["sustainability_history"]["puanlar"],
        },
    }
    # QA alias anahtarları (JS sözleşmesi)
    charts["monthly_trend"] = charts["trend"]
    charts["delivery_history"] = charts["teslim_history"]
    charts["waste_categories"] = charts["category"]

    acts = deepcopy(pkg["activities"][:12])
    if ilce:
        for a in acts:
            meta = dict(a.get("meta") or {})
            meta["ilce"] = ilce
            a["meta"] = meta

    heat = heat_map_points(il=il, ilce=ilce, mahalle=mahalle)
    pred = prediction_report(
        12, il=il, ilce=ilce, mahalle=mahalle, include_all_lookbacks=True
    )

    return {
        "ozet": ozet,
        "cards": cards,
        "aktiviteler": acts,
        "filtre": ozet["filtre"],
        "charts": charts,
        "map_center": deepcopy(pkg["map_center"]),
        "heatmap": heat,
        "heat_points": heat,
        "prediction": pred,
        "source": "demo",
    }


def activities(*, il=None, limit: int = 100) -> list[dict]:
    return deepcopy(get_city(il)["activities"][:limit])


def _metric_block(
    *,
    predicted: float,
    change_pct: float,
    confidence_pct: float,
    trend: str,
    risk: str,
    unit: str,
    ai_yorum: str = "",
    label: str = "",
    metric: str = "",
    horizon_days: int = 30,
) -> dict:
    half = abs(predicted) * 0.08
    return {
        "metric": metric,
        "label": label,
        "unit": unit,
        "horizon_days": horizon_days,
        "horizon_label": HORIZON_LABELS.get(horizon_days, str(horizon_days)),
        "predicted": predicted,
        "monthly_equivalent": predicted,
        "baseline_last_month": round(predicted / (1 + change_pct / 100.0), 2) if change_pct != -100 else predicted,
        "change_pct": change_pct,
        "confidence_pct": confidence_pct,
        "confidence_interval": {
            "low": round(max(0.0, predicted - half), 2),
            "high": round(predicted + half, 2),
            "level_pct": confidence_pct,
        },
        "trend": trend,
        "risk": risk,
        "ai_yorum": ai_yorum,
        "history": [],
    }


def _forecast_from_history(history: list[dict], days: int, trends: dict) -> dict:
    last = history[-1]
    prev = history[-2] if len(history) > 1 else last
    scale = max(0.55, min(1.8, days / 90.0))
    atik_ch = _pct(last["atik_kg"], prev["atik_kg"])
    teslim_ch = _pct(last["teslim_orani"], prev["teslim_orani"])
    kat_ch = _pct(last["katilim"], prev["katilim"])
    co2_ch = _pct(last["co2_kg"], prev["co2_kg"])

    e_trend = trends.get("Elektronik", "artan")
    e_ch = 18.0 if e_trend == "artan" else 6.0

    block = {
        "atik_miktari": _metric_block(
            predicted=round(last["atik_kg"] * (1 + atik_ch / 100.0) * scale, 1),
            change_pct=round(atik_ch, 1),
            confidence_pct=78.0,
            trend="yukselis" if atik_ch >= 0 else "dusus",
            risk="orta",
            unit="kg",
            label="Atık miktarı",
            metric="atik_miktari",
            horizon_days=days,
            ai_yorum=f"Atık miktarı geçmiş trendi izliyor; değişim %{atik_ch:.1f}.",
        ),
        "kategori_artisi": {
            **_metric_block(
                predicted=e_ch,
                change_pct=e_ch,
                confidence_pct=74.0,
                trend="yukselis",
                risk="orta",
                unit="%",
                label="Kategori artışı",
                metric="kategori_artisi",
                horizon_days=days,
                ai_yorum="Elektronik kategorisinde artış geçmiş veriyle uyumlu.",
            ),
            "en_yogun_kategori": "Elektronik",
            "kategori": "Elektronik",
            "monthly_equivalent": round(last.get("elektronik_index", 100) / 5, 1),
            "monthly_volume": round(last.get("elektronik_index", 100) / 5, 1),
            "ranking": [
                {"kategori": "Elektronik", "change_pct": e_ch},
                {"kategori": "Plastik", "change_pct": 1.2},
                {"kategori": "Organik", "change_pct": -6.5},
                {"kategori": "Bitkisel yağ", "change_pct": 14.0},
            ],
        },
        "teslim_orani": _metric_block(
            predicted=round(min(95.0, last["teslim_orani"] + teslim_ch * 0.3), 1),
            change_pct=round(teslim_ch, 1),
            confidence_pct=82.0,
            trend="yukselis" if teslim_ch >= 0 else "dusus",
            risk="dusuk",
            unit="%",
            label="Teslim oranı",
            metric="teslim_orani",
            horizon_days=days,
            ai_yorum="Teslim oranı geçmiş ayları takip ediyor.",
        ),
        "katilim": _metric_block(
            predicted=round(min(95.0, last["katilim"] + kat_ch * 0.25), 1),
            change_pct=round(kat_ch, 1),
            confidence_pct=76.0,
            trend="yukselis" if kat_ch >= 0 else "stabil",
            risk="dusuk",
            unit="%",
            label="Katılım",
            metric="katilim",
            horizon_days=days,
            ai_yorum="Vatandaş katılımı istikrarlı yükselişte.",
        ),
        "co2": _metric_block(
            predicted=round(last["co2_kg"] * (1 + co2_ch / 100.0) * scale, 1),
            change_pct=round(co2_ch, 1),
            confidence_pct=77.0,
            trend="yukselis" if co2_ch >= 0 else "dusus",
            risk="orta",
            unit="kg",
            label="CO₂",
            metric="co2",
            horizon_days=days,
            ai_yorum="CO₂ kazanımı geçmiş trendi izliyor.",
        ),
        "kaynak_paylasimi": _metric_block(
            predicted=round(last["kaynak_adet"] * scale * 1.05, 1),
            change_pct=5.0,
            confidence_pct=70.0,
            trend="stabil",
            risk="dusuk",
            unit="ilan",
            label="Kaynak paylaşımı",
            metric="kaynak_paylasimi",
            horizon_days=days,
            ai_yorum="Kaynak paylaşımı dengeli seyrediyor.",
        ),
        "en_yogun_kategori": None,
    }
    ka = block["kategori_artisi"]
    block["en_yogun_kategori"] = {
        "horizon_days": days,
        "en_yogun_kategori": "Elektronik",
        "predicted": ka["monthly_volume"],
        "change_pct": e_ch,
        "ranking": ka["ranking"],
        "confidence_pct": 74.0,
        "confidence_interval": ka["confidence_interval"],
        "trend": "yukselis",
        "risk": "orta",
        "ai_yorum": ka["ai_yorum"],
    }
    return block


def _pct(curr: float, prev: float) -> float:
    if not prev:
        return 0.0
    return ((curr - prev) / prev) * 100.0


def prediction_payload(
    lookback_months: int = 12,
    *,
    il=None,
    ilce=None,
    mahalle=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    if lookback_months not in LOOKBACK_MONTHS:
        lookback_months = 12
    pkg = get_city(il)
    share = _district_share(pkg, ilce, mahalle)
    history = deepcopy(pkg["monthly_history"][-lookback_months:])
    if share < 0.999:
        for row in history:
            for key in ("atik_kg", "co2_kg", "kaynak_adet", "elektronik_index"):
                if key in row and row[key] is not None:
                    row[key] = _scale_number(row[key], share)
    trends = pkg["trends"]
    forecasts = {
        str(d): _forecast_from_history(history, d, trends) for d in FORECAST_HORIZONS_DAYS
    }
    chart = {
        "labels": [s["ay"] for s in history],
        "atik_kg": [s["atik_kg"] for s in history],
        "co2_kg": [s["co2_kg"] for s in history],
        "kaynak_adet": [s["kaynak_adet"] for s in history],
        "teslim_orani": [s["teslim_orani"] for s in history],
        "katilim": [s["katilim"] for s in history],
        "forecast_atik": {
            str(d): forecasts[str(d)]["atik_miktari"]["predicted"] for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_co2": {
            str(d): forecasts[str(d)]["co2"]["predicted"] for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_teslim": {
            str(d): forecasts[str(d)]["teslim_orani"]["predicted"] for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_katilim": {
            str(d): forecasts[str(d)]["katilim"]["predicted"] for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_kategori": {
            str(d): forecasts[str(d)]["kategori_artisi"]["change_pct"] for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_kaynak": {
            str(d): forecasts[str(d)]["kaynak_paylasimi"]["predicted"] for d in FORECAST_HORIZONS_DAYS
        },
        "horizon_labels": [HORIZON_LABELS[d] for d in FORECAST_HORIZONS_DAYS],
    }
    return {
        "lookback_months": lookback_months,
        "history": history,
        "forecasts": forecasts,
        # QA alias — MASTER monthly_history / forecast blokları
        "prediction_history": history,
        "prediction_forecast": forecasts,
        "metrics": list(METRIC_KEYS),
        "horizons_days": list(FORECAST_HORIZONS_DAYS),
        "horizon_labels": dict(HORIZON_LABELS),
        "chart": chart,
        "filtre": {"il": il or _norm_city(il), "ilce": ilce, "mahalle": mahalle},
        "engine": "demo-master",
        "generated_at": (now or utc_now()).isoformat(),
    }


def prediction_report(
    lookback_months: int = 12,
    *,
    il=None,
    ilce=None,
    mahalle=None,
    include_all_lookbacks: bool = True,
) -> dict:
    filters = {"il": il, "ilce": ilce, "mahalle": mahalle}
    pkg = get_city(il)
    if include_all_lookbacks:
        lookbacks = {str(m): prediction_payload(m, **filters) for m in LOOKBACK_MONTHS}
        primary = lookbacks["12"]
        multi = {
            "lookbacks": lookbacks,
            "primary": primary,
            "horizons_days": list(FORECAST_HORIZONS_DAYS),
            "lookback_options": list(LOOKBACK_MONTHS),
            "metrics": list(METRIC_KEYS),
        }
    else:
        primary = prediction_payload(lookback_months, **filters)
        multi = {
            "lookbacks": {str(lookback_months): primary},
            "primary": primary,
            "horizons_days": list(FORECAST_HORIZONS_DAYS),
            "lookback_options": [lookback_months],
            "metrics": list(METRIC_KEYS),
        }
    return {
        **multi,
        "narratives": list(pkg["ai_summary"]),
        "narrative_source": "demo",
    }


def sustainability_score(*, il=None, ilce=None, mahalle=None) -> dict:
    scored = deepcopy(get_city(il)["sustainability"])
    scored["il"] = il or _norm_city(il)
    scored["ilce"] = ilce
    scored["mahalle"] = mahalle
    return scored


def sustainability_dashboard_overlay(*, il=None, ilce=None) -> dict:
    """sustainability_dashboard şemasına uyumlu demo paket."""
    city = _norm_city(il)
    pkg = get_city(city)
    current = sustainability_score(il=city, ilce=ilce)
    board = national_leaderboard()
    leaders = board[:20]
    my_rank = next((r["sira"] for r in board if r["il"] == city), None)
    radar = {
        "labels": [c["label"] for c in current["criteria"]],
        "values": [c["score"] for c in current["criteria"]],
        "keys": [c["key"] for c in current["criteria"]],
    }
    provinces = [
        {"il": r["il"], "puan": r["puan"], "grade": r["grade"], "sira": r["sira"]}
        for r in board
    ]
    similar = [
        {
            **r,
            "puan_farki": round(r["puan"] - current["puan"], 1),
            "ayni_il": False,
        }
        for r in board
        if r["il"] != city
    ][:5]
    avg = sum(r["puan"] for r in board) / len(board)
    return {
        "current": current,
        "my_rank": my_rank,
        "leaderboard": leaders,
        "turkey_ranking": leaders,
        "province_ranking": provinces,
        "il_ranking": [r for r in leaders if r["il"] == city],
        "focus_il": city,
        "comparison": {
            "turkey_avg": round(avg, 1),
            "delta_pct": round(((current["puan"] - avg) / avg) * 100.0, 1),
            "percentile": round(100.0 * (len(board) - (my_rank or len(board)) + 1) / len(board), 1),
            "peer_count": len(board),
            "message": f"{city} ulusal sıralamada {my_rank}. sırada.",
        },
        "radar": radar,
        "category_scores": current["criteria"],
        "sustainability_categories": {
            "labels": radar["labels"],
            "values": radar["values"],
            "keys": radar["keys"],
        },
        "history": deepcopy(pkg["sustainability_history"]),
        "similar_municipalities": similar,
        "rankings": {
            "turkey": {"sira": my_rank, "toplam": len(board)},
            "il_belediye": {"sira": 1, "toplam": 1, "il": city},
            "il_ortalama": {"sira": my_rank, "toplam": len(board), "il": city},
        },
        "improving": [r for r in board if r["puan"] < 75][:5],
        "at_risk": [r for r in reversed(board) if r["puan"] < 70][:5],
    }


def sustainability_ai_report(scored: dict | None = None) -> dict:
    city = _norm_city((scored or {}).get("il"))
    pkg = get_city(city)
    scored = scored or pkg["sustainability"]
    puan = scored.get("puan")
    grade = scored.get("grade")
    bullets = pkg["ai_summary"]
    suggestions = [
        {
            "title": "Mahalle Bazlı Mobil Toplama",
            "description": bullets[0] if bullets else "Yoğun mahallelerde mobil toplama önerilir.",
            "expected_impact": "Teslim süresi ve katılımda iyileşme",
            "priority": "Yüksek",
            "duration": "Orta",
            "reason": f"{city} skoru {puan}/100 ({grade}).",
            "trigger": "demo",
        },
        {
            "title": "Elektronik Atık Kampanyası",
            "description": next((b for b in bullets if "Elektronik" in b), bullets[1] if len(bullets) > 1 else ""),
            "expected_impact": "Elektronik atık toplama payında artış",
            "priority": "Orta",
            "duration": "Kısa",
            "reason": "MASTER_DATASET elektronik trendi.",
            "trigger": "demo",
        },
        {
            "title": "Bitkisel Yağ Toplama",
            "description": next((b for b in bullets if "yağ" in b.lower() or "Yağ" in b), "Bitkisel yağ kampanyası sürdürülmeli."),
            "expected_impact": "Bitkisel yağ teslimlerinde artış",
            "priority": "Orta",
            "duration": "Kısa",
            "reason": "Kampanya sonrası yükseliş senaryosu.",
            "trigger": "demo",
        },
    ]
    report = {
        "summary": " ".join(bullets[:2]),
        "strengths": bullets[:3],
        "improvements": [
            "Organik atık ayrıştırmasını güçlendirin",
            "Riskli mahallelerde saha takibini artırın",
            "Sanayi bölgelerinde metal lojistiğini sıkılaştırın",
        ],
        "recommendations": [
            "Mobil toplama noktalarını artırın",
            "Elektronik atık günleri planlayın",
            "Bitkisel yağ kampanyasını yaygınlaştırın",
        ],
        "expected_gains": f"CO₂ {pkg['co2_ton']} ton seviyesinin korunması / artırılması",
        "source": "demo",
    }
    return {
        "suggestions": suggestions,
        "report": report,
        "evaluation": report,
        "source": "demo",
        "puan": puan,
        "grade": grade,
    }


# ---------------------------------------------------------------------------
# Kurumsal Kaynak Pazarı — MASTER_DATASET / MARKETPLACE_ORGS kataloğu
# ---------------------------------------------------------------------------

_MP_CATALOG: dict[str, Any] | None = None

_MP_WASTE_TO_LISTING = {
    "Plastik": "Ambalaj",
    "Elektronik": "Elektronik",
    "Cam": "Ambalaj",
    "Metal": "Hammadde",
    "Organik": "Gıda Yan Ürün",
    "Bitkisel yağ": "Gıda Yan Ürün",
    "Diğer": "Diğer",
}
_MP_BIRIMLER = ("kg", "ton", "adet", "palet", "m3")
_MP_TITLE_TMPL = (
    "{kat} stok — {ad}",
    "{miktar} {birim} {kat}",
    "Acil {kat} tedarik ({ad})",
    "{il} {kat} kaynağı",
)


def _mp_slug(name: str) -> str:
    return (
        name.lower()
        .replace(" ", "_")
        .replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace(".", "")
        .replace("ş", "s")[:24]
    )


def _build_marketplace_catalog() -> dict[str, Any]:
    """Deterministik B2B katalog: ≥40 firma, ≥120 ilan, ≥80 teklif, ≥30 rezervasyon, ≥20 teslim."""
    from types import SimpleNamespace

    from constants import (
        MP_EVENT_ANLASMA,
        MP_EVENT_REZERVASYON,
        MP_EVENT_TEKLIF,
        MP_EVENT_TESLIM,
        MP_EVENT_YAYINLA,
        MP_LISTING_ANLASILDI,
        MP_LISTING_REZERVE,
        MP_LISTING_TESLIM,
        MP_LISTING_YAYINDA,
        MP_OFFER_BEKLIYOR,
        MP_OFFER_KABUL,
    )

    now = utc_now()
    firms: list[Any] = []
    firm_by_id: dict[int, Any] = {}
    for i, o in enumerate(MARKETPLACE_ORGS):
        pkg = get_city(o["il"])
        lat = float(pkg["center"][0]) + ((i % 7) - 3) * 0.018
        lng = float(pkg["center"][1]) + ((i % 5) - 2) * 0.02
        firm = SimpleNamespace(
            id=9100000 + i,
            ad=o["ad"],
            soyad="",
            username=_mp_slug(o["ad"]),
            role="company",
            il=o["il"],
            ilce=o["ilce"],
            latitude=lat,
            longitude=lng,
            is_kurum=True,
            waste_kategori=o["kategori"],
            puan_ortalama=round(4.6 - (i % 9) * 0.08, 2),
        )
        firms.append(firm)
        firm_by_id[firm.id] = firm

    listings: list[Any] = []
    listing_by_id: dict[int, Any] = {}
    offers: list[Any] = []
    events: list[Any] = []
    offer_seq = 0

    def _add_offer(listing, offerer, *, durum, miktar, idx):
        nonlocal offer_seq
        offer_seq += 1
        offer = SimpleNamespace(
            id=9300000 + offer_seq,
            listing_id=listing.id,
            listing=listing,
            offerer_id=offerer.id,
            offerer=offerer,
            mesaj=f"{offerer.ad} teklifi — {listing.kategori}",
            miktar=miktar,
            durum=durum,
            created_at=now - timedelta(days=max(1, idx % 20), hours=idx % 12),
            responded_at=now - timedelta(days=max(0, (idx % 10) - 2)) if durum == MP_OFFER_KABUL else None,
        )
        listing.offers.append(offer)
        offers.append(offer)
        return offer

    def _add_event(listing_id, action, detail, *, offer_id=None, days=1, actor_id=None):
        events.append(
            SimpleNamespace(
                listing_id=listing_id,
                offer_id=offer_id,
                action=action,
                detail=detail,
                actor_id=actor_id,
                created_at=now - timedelta(days=days, hours=(abs(listing_id) % 18)),
            )
        )

    # 120 ilan: 50 yayında · 30 rezerve · 20 anlaşılı · 20 teslim
    status_plan = (
        [MP_LISTING_YAYINDA] * 50
        + [MP_LISTING_REZERVE] * 30
        + [MP_LISTING_ANLASILDI] * 20
        + [MP_LISTING_TESLIM] * 20
    )
    for i, durum in enumerate(status_plan):
        publisher = firms[i % len(firms)]
        partner = firms[(i + 7) % len(firms)]
        waste = publisher.waste_kategori
        kat = _MP_WASTE_TO_LISTING.get(waste, "Diğer")
        birim = _MP_BIRIMLER[i % len(_MP_BIRIMLER)]
        miktar = float(20 + (i * 7) % 480)
        tmpl = _MP_TITLE_TMPL[i % len(_MP_TITLE_TMPL)]
        baslik = tmpl.format(
            kat=kat, ad=publisher.ad, miktar=int(miktar), birim=birim, il=publisher.il
        )[:140]
        listing = SimpleNamespace(
            id=9200000 + i,            publisher_id=publisher.id,
            publisher=publisher,
            baslik=baslik,
            aciklama=(
                f"{publisher.ad} ({publisher.il}/{publisher.ilce}) — "
                f"{waste} hattından {kat} kaynağı. MASTER_DATASET senaryosu."
            ),
            kategori=kat,
            miktar=miktar,
            birim=birim,
            latitude=publisher.latitude + ((i % 3) - 1) * 0.004,
            longitude=publisher.longitude + ((i % 4) - 1) * 0.005,
            il=publisher.il,
            ilce=publisher.ilce,
            durum=durum,
            accepted_offer_id=None,
            created_at=now - timedelta(days=1 + (i % 45)),
            updated_at=now - timedelta(days=(i % 10)),
            offers=[],
        )
        listings.append(listing)
        listing_by_id[listing.id] = listing
        _add_event(
            listing.id,
            MP_EVENT_YAYINLA,
            f"İlan yayınlandı: {baslik}",
            days=2 + (i % 40),
            actor_id=publisher.id,
        )

        if durum == MP_LISTING_YAYINDA:
            # Bekleyen teklifler (hedef ≥80 teklif için yayındakilerden bol üret)
            n_pending = 2 if i < 20 else 1
            for j in range(n_pending):
                offerer = firms[(i + 3 + j) % len(firms)]
                if offerer.id == publisher.id:
                    offerer = firms[(i + 11 + j) % len(firms)]
                off = _add_offer(
                    listing, offerer, durum=MP_OFFER_BEKLIYOR, miktar=miktar * 0.9, idx=i + j
                )
                _add_event(
                    listing.id,
                    MP_EVENT_TEKLIF,
                    "Teklif gönderildi",
                    offer_id=off.id,
                    days=1 + (i % 15),
                    actor_id=offerer.id,
                )
        else:
            off = _add_offer(
                listing, partner, durum=MP_OFFER_KABUL, miktar=miktar * 0.95, idx=i
            )
            listing.accepted_offer_id = off.id
            _add_event(
                listing.id,
                MP_EVENT_TEKLIF,
                "Teklif gönderildi",
                offer_id=off.id,
                days=5 + (i % 10),
                actor_id=partner.id,
            )
            _add_event(
                listing.id,
                MP_EVENT_REZERVASYON,
                f"Teklif #{off.id} kabul — rezervasyon",
                offer_id=off.id,
                days=4 + (i % 8),
                actor_id=publisher.id,
            )
            if durum in (MP_LISTING_ANLASILDI, MP_LISTING_TESLIM):
                _add_event(
                    listing.id,
                    MP_EVENT_ANLASMA,
                    "Anlaşma onaylandı",
                    offer_id=off.id,
                    days=3 + (i % 6),
                    actor_id=publisher.id,
                )
            if durum == MP_LISTING_TESLIM:
                _add_event(
                    listing.id,
                    MP_EVENT_TESLIM,
                    "Teslim tamamlandı",
                    offer_id=off.id,
                    days=1 + (i % 5),
                    actor_id=publisher.id,
                )

    # Eksik teklif varsa doldur (garanti ≥80)
    while len(offers) < 80:
        listing = listings[len(offers) % 50]  # yayında bandı
        offerer = firms[(len(offers) + 13) % len(firms)]
        if offerer.id == listing.publisher_id:
            offerer = firms[(len(offers) + 17) % len(firms)]
        off = _add_offer(
            listing,
            offerer,
            durum=MP_OFFER_BEKLIYOR,
            miktar=(listing.miktar or 10) * 0.8,
            idx=len(offers),
        )
        _add_event(
            listing.id,
            MP_EVENT_TEKLIF,
            "Teklif gönderildi",
            offer_id=off.id,
            days=1,
            actor_id=offerer.id,
        )

    events.sort(key=lambda e: e.created_at, reverse=True)

    stats = {
        "firma": len(firms),
        "ilan": len(listings),
        "teklif": len(offers),
        "rezervasyon": sum(1 for l in listings if l.durum == MP_LISTING_REZERVE),
        "teslim": sum(1 for l in listings if l.durum == MP_LISTING_TESLIM),
        "yayinda": sum(1 for l in listings if l.durum == MP_LISTING_YAYINDA),
        "anlasildi": sum(1 for l in listings if l.durum == MP_LISTING_ANLASILDI),
    }
    return {
        "firms": firms,
        "firm_by_id": firm_by_id,
        "listings": listings,
        "listing_by_id": listing_by_id,
        "offers": offers,
        "events": events,
        "stats": stats,
        "source": "demo",
    }


def get_marketplace_catalog() -> dict[str, Any]:
    global _MP_CATALOG
    if _MP_CATALOG is None:
        _MP_CATALOG = _build_marketplace_catalog()
    return _MP_CATALOG


def marketplace_catalog_stats() -> dict[str, int]:
    return dict(get_marketplace_catalog()["stats"])


def marketplace_orgs(*, limit: int = 40) -> list[dict]:
    return deepcopy(MARKETPLACE_ORGS[:limit])


def marketplace_firms(*, limit: int | None = None) -> list[Any]:
    firms = get_marketplace_catalog()["firms"]
    if limit is None:
        return list(firms)
    return list(firms[:limit])


def marketplace_listings(*, durum: str | None = None, exclude_user_id: int | None = None) -> list[Any]:
    rows = get_marketplace_catalog()["listings"]
    out = []
    for listing in rows:
        if durum and listing.durum != durum:
            continue
        if exclude_user_id is not None and listing.publisher_id == exclude_user_id:
            continue
        out.append(listing)
    return out


def marketplace_listing_by_id(listing_id: int) -> Any | None:
    return get_marketplace_catalog()["listing_by_id"].get(listing_id)


def marketplace_offers(*, offerer_id: int | None = None) -> list[Any]:
    rows = get_marketplace_catalog()["offers"]
    if offerer_id is None:
        return list(rows)
    return [o for o in rows if o.offerer_id == offerer_id]


def marketplace_history(*, limit: int = 50) -> list[Any]:
    return list(get_marketplace_catalog()["events"][:limit])


def marketplace_map_points_demo(listings: list[Any] | None = None) -> list[dict]:
    items = listings if listings is not None else marketplace_listings()
    points = []
    for listing in items:
        if listing.durum == "iptal":
            continue
        points.append({
            "id": listing.id,
            "baslik": listing.baslik,
            "durum": listing.durum,
            "lat": listing.latitude,
            "lng": listing.longitude,
            "kategori": listing.kategori,
        })
    return points


def marketplace_suppliers(*, il: str | None = None, limit: int = 100) -> list[dict]:
    cat = get_marketplace_catalog()
    listing_counts: dict[int, int] = {}
    delivery_counts: dict[int, int] = {}
    offer_counts: dict[int, int] = {}
    for listing in cat["listings"]:
        listing_counts[listing.publisher_id] = listing_counts.get(listing.publisher_id, 0) + 1
        if listing.durum == "teslim":
            delivery_counts[listing.publisher_id] = delivery_counts.get(listing.publisher_id, 0) + 1
    for offer in cat["offers"]:
        offer_counts[offer.offerer_id] = offer_counts.get(offer.offerer_id, 0) + 1

    rows = []
    for firm in cat["firms"]:
        if il and firm.il != il:
            continue
        rows.append({
            "id": firm.id,
            "ad": firm.ad,
            "role": firm.role,
            "il": firm.il,
            "ilce": firm.ilce,
            "lat": firm.latitude,
            "lng": firm.longitude,
            "ilan_sayisi": int(listing_counts.get(firm.id) or 0),
            "teslim_sayisi": int(delivery_counts.get(firm.id) or 0),
            "teklif_sayisi": int(offer_counts.get(firm.id) or 0),
            "puan_ortalama": firm.puan_ortalama,
            "puan_adet": 4 + (abs(firm.id) % 8),
        })
    rows.sort(key=lambda r: (-(r["puan_ortalama"] or 0), -r["teslim_sayisi"], -r["ilan_sayisi"]))
    return rows[:limit]


def marketplace_demand_pool(*, kategori: str | None = None, il: str | None = None) -> list[dict]:
    rows = []
    for listing in marketplace_listings(durum="yayinda"):
        if kategori and listing.kategori != kategori:
            continue
        if il and listing.il != il:
            continue
        pending = sum(1 for o in listing.offers if o.durum == "bekliyor")
        rows.append({
            "id": listing.id,
            "baslik": listing.baslik,
            "kategori": listing.kategori,
            "miktar": listing.miktar,
            "birim": listing.birim,
            "il": listing.il,
            "ilce": listing.ilce,
            "publisher": listing.publisher.ad,
            "publisher_id": listing.publisher_id,
            "teklif_bekleyen": pending,
            "created_at": listing.created_at,
            "lat": listing.latitude,
            "lng": listing.longitude,
        })
    return rows[:80]


def marketplace_price_analysis() -> dict:
    from collections import defaultdict
    from statistics import mean

    by_cat: dict[str, dict] = defaultdict(lambda: {
        "ilan_adet": 0,
        "miktarlar": [],
        "teklif_miktarlari": [],
        "teslim_adet": 0,
    })
    for listing in get_marketplace_catalog()["listings"]:
        cat = listing.kategori or "Diğer"
        bucket = by_cat[cat]
        bucket["ilan_adet"] += 1
        if listing.miktar is not None:
            bucket["miktarlar"].append(float(listing.miktar))
        if listing.durum == "teslim":
            bucket["teslim_adet"] += 1
    for offer in get_marketplace_catalog()["offers"]:
        listing = offer.listing
        if listing is None or offer.miktar is None:
            continue
        by_cat[listing.kategori or "Diğer"]["teklif_miktarlari"].append(float(offer.miktar))

    categories = []
    for cat, b in sorted(by_cat.items(), key=lambda x: -x[1]["ilan_adet"]):
        miktarlar = b["miktarlar"]
        teklifler = b["teklif_miktarlari"]
        categories.append({
            "kategori": cat,
            "ilan_adet": b["ilan_adet"],
            "teslim_adet": b["teslim_adet"],
            "ortalama_miktar": round(mean(miktarlar), 2) if miktarlar else None,
            "medyan_miktar": round(sorted(miktarlar)[len(miktarlar) // 2], 2) if miktarlar else None,
            "min_miktar": round(min(miktarlar), 2) if miktarlar else None,
            "max_miktar": round(max(miktarlar), 2) if miktarlar else None,
            "ortalama_teklif_miktar": round(mean(teklifler), 2) if teklifler else None,
            "teklif_adet": len(teklifler),
        })
    return {
        "kategoriler": categories,
        "ozet": {
            "kategori_sayisi": len(categories),
            "toplam_ilan": sum(c["ilan_adet"] for c in categories),
            "toplam_teslim": sum(c["teslim_adet"] for c in categories),
        },
    }


def marketplace_nearest_orgs(
    *,
    lat: float | None = None,
    lng: float | None = None,
    radius_km: float = 50,
    limit: int = 30,
    exclude_id: int | None = None,
) -> list[dict]:
    from utils import mesafe_hesapla

    if lat is None or lng is None:
        center = get_city(DEFAULT_CITY)["center"]
        lat, lng = float(center[0]), float(center[1])

    cat = get_marketplace_catalog()
    listing_counts: dict[int, int] = {}
    for listing in cat["listings"]:
        listing_counts[listing.publisher_id] = listing_counts.get(listing.publisher_id, 0) + 1

    results = []
    for firm in cat["firms"]:
        if exclude_id is not None and firm.id == exclude_id:
            continue
        dist = mesafe_hesapla(lat, lng, firm.latitude, firm.longitude)
        # Demo: MASTER illerini göstermek için yarıçapı esnet — uzak olanları da sırala
        results.append({
            "id": firm.id,
            "ad": firm.ad,
            "role": firm.role,
            "il": firm.il,
            "ilce": firm.ilce,
            "lat": firm.latitude,
            "lng": firm.longitude,
            "mesafe_km": round(dist, 1),
            "puan_ortalama": firm.puan_ortalama,
            "ilan_sayisi": int(listing_counts.get(firm.id) or 0),
        })
    results.sort(key=lambda x: x["mesafe_km"])
    near = [r for r in results if r["mesafe_km"] <= radius_km]
    return (near or results)[:limit]


def marketplace_matches(limit: int = 12, *, il=None, listing=None) -> list[dict]:
    """AI Match — kategori · mesafe · geçmiş başarı (puan) · aktivite."""
    city = _norm_city(il or getattr(listing, "il", None))
    origin = get_city(city)["center"]
    listing_kat = getattr(listing, "kategori", None) if listing is not None else None
    firms = get_marketplace_catalog()["firms"]
    # Önce aynı il, yetmezse tüm MASTER firmalar
    local = [f for f in firms if f.il == city]
    pool = local if len(local) >= 5 else list(firms)

    from utils import mesafe_hesapla

    samples = []
    for i, firm in enumerate(pool[: max(limit, 12)]):
        dist = round(mesafe_hesapla(origin[0], origin[1], firm.latitude, firm.longitude), 1)
        if dist < 1:
            dist = round(3.5 + i * 1.7, 1)
        mesafe_score = max(0.0, round(100.0 * (1.0 - min(dist, 50) / 50.0), 1))
        waste_mp = _MP_WASTE_TO_LISTING.get(firm.waste_kategori, "Diğer")
        kategori_score = 92.0 if listing_kat and waste_mp == listing_kat else (
            78.0 if firm.waste_kategori else 55.0
        )
        kategori_score = round(kategori_score - i * 1.5, 1)
        puan_score = round((firm.puan_ortalama / 5.0) * 100.0 - i * 0.8, 1)
        aktivite_score = round(88.0 - i * 2.2, 1)
        total = round(
            0.40 * mesafe_score
            + 0.25 * kategori_score
            + 0.20 * puan_score
            + 0.15 * aktivite_score,
            1,
        )
        nedenler = [
            f"{dist} km mesafede",
            f"{firm.waste_kategori} / {waste_mp} uyumu",
            f"geçmiş başarı ★{firm.puan_ortalama}",
            "yüksek aktivite",
        ]
        samples.append({
            "id": firm.id,
            "ad": firm.ad,
            "username": firm.username,
            "role": firm.role,
            "il": firm.il,
            "ilce": firm.ilce,
            "lat": firm.latitude,
            "lng": firm.longitude,
            "mesafe_km": dist,
            "eslesme_skoru": total,
            "nedenler": nedenler[:3],
            "skor_detay": {
                "mesafe": mesafe_score,
                "kategori": max(0.0, kategori_score),
                "puan": max(0.0, puan_score),
                "aktivite": max(0.0, aktivite_score),
            },
            "puan_ortalama": firm.puan_ortalama,
        })
    samples.sort(key=lambda x: -x["eslesme_skoru"])
    return samples[:limit]


def municipality_ai_insights(dashboard: dict | None = None, *, il=None) -> dict:
    city = _norm_city(il or (dashboard or {}).get("filtre", {}).get("il"))
    pkg = get_city(city)
    cards = []
    for i, bullet in enumerate(pkg["ai_summary"][:5]):
        cards.append({
            "title": bullet.split(".")[0][:80] or f"{city} özeti",
            "analysis": bullet,
            "expected_impact": "Operasyonel iyileşme · KPI görünürlüğü",
            "priority": ("Yüksek", "Orta", "Orta", "Düşük", "Orta")[i % 5],
            "trigger": "demo",
        })
    return {
        "source": "demo",
        "insights": cards,
        "dashboard": dashboard or dashboard_kpis(il=city),
    }


def decision_support_center() -> dict:
    """Ulusal karar destek — MASTER_DATASET (template/PDF şemasına tam uyumlu)."""
    muni_board = _municipality_board()
    now = utc_now()
    nat = ministry_kpi()
    total_ilan = nat["toplam_ilan"]

    # Kategori payları → dönemsel shift benzeri sayılar
    cat_counts = []
    for k in CATEGORY_KEYS:
        cur = 0
        for city, pkg in MASTER_DATASET.items():
            cur += int(round(pkg["dashboard"]["toplam_aktif_ilan"] * pkg["waste_categories"].get(k, 0) / 100.0))
        prev = max(1, int(cur * 0.88))
        # Elektronik yükseliş, Organik düşüş senaryosu
        if k == "Elektronik":
            prev = max(1, int(cur * 0.82))
        elif k == "Organik":
            prev = int(cur * 1.12)
        elif k == "Bitkisel yağ":
            prev = max(1, int(cur * 0.75))
        delta = cur - prev
        cat_counts.append({
            "kategori": "Bitkisel Yağ" if k == "Bitkisel yağ" else k,
            "current": cur,
            "previous": prev,
            "delta": delta,
            "change_pct": round(((cur - prev) / prev) * 100.0, 1) if prev else 0.0,
        })
    cat_counts.sort(key=lambda x: -abs(x["delta"]))
    rising = [s for s in cat_counts if s["delta"] > 0][:5]
    falling = [s for s in cat_counts if s["delta"] < 0][:5]

    # 8 haftalık katılım
    hist = MASTER_DATASET[DEFAULT_CITY]["monthly_history"][-6:]
    aktif_series = [int(55 + i * 2.5 + (row["katilim"] * 0.15)) for i, row in enumerate(hist)]
    # 8 noktaya tamamla
    while len(aktif_series) < 8:
        aktif_series.append(aktif_series[-1] + 2)
    ilan_series = [int(total_ilan * (0.012 + i * 0.001)) for i in range(8)]
    labels = [f"W{i+1}" for i in range(8)]
    part_change = round(
        ((aktif_series[-1] - aktif_series[0]) / max(aktif_series[0], 1)) * 100.0, 1
    )
    participation = {
        "weeks": 8,
        "series": [
            {"label": labels[i], "aktif_kullanici": aktif_series[i], "ilan": ilan_series[i]}
            for i in range(8)
        ],
        "labels": labels,
        "aktif": aktif_series,
        "ilanlar": ilan_series,
        "change_pct": part_change,
        "trend": "yukselis" if part_change >= 8 else ("dusus" if part_change <= -8 else "stabil"),
    }

    risky_rows = sorted(muni_board, key=lambda r: r["puan"])[:5]
    medium_rows = [r for r in muni_board if r["renk"] == "sari"]
    risk_level = "orta" if len(risky_rows) >= 3 else "dusuk"
    if risky_rows and risky_rows[0]["puan"] < 70:
        risk_level = "orta"
    findings = [
        f"{len(risky_rows)} il düşük sürdürülebilirlik bandında "
        f"(ör. {risky_rows[0]['ad']}).",
        f"Elektronik kategorisinde artış (%{rising[0]['change_pct'] if rising else 12}).",
        "Bitkisel yağ kampanyası birden fazla ilde yükselişte.",
        f"Vatandaş katılımı son dönemde %{part_change} değişti.",
    ]
    risk = {
        "level": risk_level,
        "riskli_belediye_sayisi": len(risky_rows),
        "orta_risk_sayisi": len(medium_rows) or 3,
        "riskli_belediyeler": [
            {
                "belediye_adi": r["ad"],
                "il": r["il"],
                "ilce": r.get("ilce"),
                "puan": r["puan"],
                "renk": r["renk"],
            }
            for r in risky_rows
        ],
        "falling_categories": falling[:3],
        "participation_change_pct": part_change,
        "findings": findings,
    }

    top = [
        {
            "belediye_adi": r["ad"],
            "il": r["il"],
            "ilce": r.get("ilce"),
            "puan": r["puan"],
            "gelisim_yuzde": r["gelisim_yuzde"],
            "renk": r["renk"],
        }
        for r in muni_board[:8]
    ]
    bottom = [
        {
            "belediye_adi": r["ad"],
            "il": r["il"],
            "ilce": r.get("ilce"),
            "puan": r["puan"],
            "gelisim_yuzde": r["gelisim_yuzde"],
            "renk": r["renk"],
        }
        for r in sorted(muni_board, key=lambda x: x["puan"])[:8]
    ]
    comparisons = {
        "top": top,
        "bottom": bottom,
        "provinces_top": province_statistics()[:8],
        "provinces_bottom": list(reversed(province_statistics()[-5:])),
        "chart": {
            "labels": [r["belediye_adi"] for r in top[:6]],
            "puanlar": [r["puan"] for r in top[:6]],
        },
    }

    weekly = {
        "period": "weekly",
        "label": "Haftalık",
        "days": 7,
        "start": (now).isoformat(),
        "end": now.isoformat(),
        "metrics": {
            "ilan": int(total_ilan * 0.02),
            "teslim": int(total_ilan * 0.012),
            "aktif_kullanici": aktif_series[-1],
            "atik_kg": round(nat["toplam_geri_kazanim_kg"] * 0.08, 1),
            "co2e_kg": round(nat["co2_tasarrufu_kg"] * 0.08, 1),
            "su_litre": round(nat["su_tasarrufu_litre"] * 0.08, 1),
            "adet": int(nat["etki_adet"] * 0.08),
        },
        "previous": {
            "ilan": int(total_ilan * 0.018),
            "teslim": int(total_ilan * 0.01),
            "aktif_kullanici": aktif_series[-2],
            "atik_kg": round(nat["toplam_geri_kazanim_kg"] * 0.07, 1),
            "co2e_kg": round(nat["co2_tasarrufu_kg"] * 0.07, 1),
        },
        "change_pct": {
            "ilan": 6.2,
            "teslim": 4.8,
            "aktif_kullanici": 5.1,
            "co2e_kg": 5.5,
            "atik_kg": 4.1,
        },
    }
    monthly = {
        "period": "monthly",
        "label": "Aylık",
        "days": 30,
        "start": now.isoformat(),
        "end": now.isoformat(),
        "metrics": {
            "ilan": int(total_ilan * 0.08),
            "teslim": int(total_ilan * 0.05),
            "aktif_kullanici": int(aktif_series[-1] * 1.4),
            "atik_kg": round(nat["toplam_geri_kazanim_kg"] * 0.25, 1),
            "co2e_kg": round(nat["co2_tasarrufu_kg"] * 0.25, 1),
            "su_litre": round(nat["su_tasarrufu_litre"] * 0.25, 1),
            "adet": int(nat["etki_adet"] * 0.25),
        },
        "previous": {
            "ilan": int(total_ilan * 0.07),
            "teslim": int(total_ilan * 0.045),
            "aktif_kullanici": int(aktif_series[-1] * 1.2),
            "atik_kg": round(nat["toplam_geri_kazanim_kg"] * 0.22, 1),
            "co2e_kg": round(nat["co2_tasarrufu_kg"] * 0.22, 1),
        },
        "change_pct": {
            "ilan": 8.4,
            "teslim": 6.0,
            "aktif_kullanici": 7.2,
            "co2e_kg": 7.1,
            "atik_kg": 5.2,
        },
    }

    campaigns = [
        {
            "title": "Elektronik Atık Haftası",
            "description": (
                "Elektronik kategorisinde ulusal artış gözleniyor. "
                "Toplama günleri ve farkındalık etkinlikleri önerilir."
            ),
            "priority": "Yüksek",
            "horizon": "Kısa",
        },
        {
            "title": "Bitkisel Yağ Toplama Kampanyası",
            "description": (
                "Kampanya sonrası yükseliş birden fazla ilde sürüyor; "
                "yaygınlaştırma önerilir."
            ),
            "priority": "Orta",
            "horizon": "Orta",
        },
        {
            "title": "Organik Kompost Programı",
            "description": (
                "Organik payındaki düşüşü dengelemek için mahalle kompost "
                "programları planlanabilir."
            ),
            "priority": "Orta",
            "horizon": "Orta",
        },
        {
            "title": "Riskli İl Destek Paketi",
            "description": (
                f"{risky_rows[0]['il']} ve benzeri düşük skorlu iller için "
                "operasyonel destek önerilir."
            ),
            "priority": "Yüksek",
            "horizon": "Kısa",
        },
    ]
    actions = [
        {
            "title": f"{bottom[0]['belediye_adi']} için iyileştirme planı",
            "detail": "Düşük performanslı birimlerle hedef odaklı eylem planı paylaşın.",
            "priority": "Yüksek",
        },
        {
            "title": "Elektronik atık lojistiğini güçlendirin",
            "detail": "Ulusal elektronik artışına karşı toplama kapasitesini artırın.",
            "priority": "Yüksek",
        },
        {
            "title": "İller arası iyi uygulama paylaşımı",
            "detail": "İzmir–İstanbul modellerini ulusal bültende yayınlayın.",
            "priority": "Orta",
        },
    ]

    ai = {
        "overview": (
            f"Ulusal özet: {nat['aktif_belediye']} il senaryosu, "
            f"{nat['vatandas_sayisi']} vatandaş, katılım %{nat['vatandas_katilim_orani']}. "
            f"Risk seviyesi: {risk_level}. Elektronik artıyor, organik azalıyor, "
            "bitkisel yağ kampanyası yükseliyor."
        ),
        "weekly_narrative": [
            f"Son 7 günde {weekly['metrics']['ilan']} ilan, "
            f"{weekly['metrics']['teslim']} teslim kaydedildi.",
            f"Haftalık CO₂ tasarrufu {weekly['metrics']['co2e_kg']:.0f} kg.",
            f"Aktif vatandaş {weekly['metrics']['aktif_kullanici']}.",
        ],
        "monthly_narrative": [
            f"Son 30 günde {monthly['metrics']['ilan']} ilan üretildi.",
            f"Aylık geri kazanım {monthly['metrics']['atik_kg']:.0f} kg; "
            f"CO₂ {monthly['metrics']['co2e_kg']:.0f} kg.",
            f"Katılım eğilimi: {participation['trend']} (%{part_change}).",
        ],
        "risk_narrative": findings[:3],
        "source": "demo",
    }

    return {
        "generated_at": now.isoformat(),
        "kpi": dict(nat),
        "weekly_report": weekly,
        "monthly_report": monthly,
        "risk_analysis": risk,
        "campaigns": campaigns,
        "municipality_comparisons": comparisons,
        "category_shifts": {
            "days": 30,
            "all": cat_counts,
            "rising": rising,
            "falling": falling,
            "chart": {
                "labels": [s["kategori"] for s in cat_counts[:8]],
                "current": [s["current"] for s in cat_counts[:8]],
                "previous": [s["previous"] for s in cat_counts[:8]],
            },
        },
        "participation_trends": participation,
        "ministry_actions": actions,
        "reports": {
            "weekly": {"title": "Haftalık Rapor", "key": "weekly"},
            "monthly": {"title": "Aylık Rapor", "key": "monthly"},
            "full": {"title": "Tam Karar Destek Raporu", "key": "full"},
        },
        "ai": ai,
        "ai_source": "demo",
        "source": "demo",
    }


def ministry_kpi(*, il=None, ilce=None, belediye_id=None, kurum_id=None) -> dict:
    """Türkiye özeti — 15 il MASTER agregasyonu."""
    cities = [_norm_city(il)] if il else list(MASTER_DATASET.keys())
    total_ilan = 0
    total_geri = 0.0
    total_co2 = 0.0
    total_energy = 0.0
    total_water_ton = 0.0
    total_pop = 0
    weighted_katilim = 0.0
    etki = 0
    for city in cities:
        if city not in MASTER_DATASET:
            continue
        pkg = MASTER_DATASET[city]
        d = pkg["dashboard"]
        total_ilan += d["toplam_aktif_ilan"]
        total_geri += d["geri_kazanilan_atik_kg"]
        total_co2 += pkg["co2_ton"] * 1000.0
        total_energy += pkg["energy_kwh"]
        total_water_ton += pkg["water_ton"]
        pop = pkg["population"]
        total_pop += pop
        weighted_katilim += pop * d["vatandas_katilim_orani"]
        etki += d["etki_adet"]
    katilim = round(weighted_katilim / total_pop, 1) if total_pop else 0.0
    return {
        "toplam_ilan": total_ilan,
        "toplam_geri_kazanim_kg": round(total_geri, 1),
        "co2_tasarrufu_kg": round(total_co2, 1),
        "enerji_tasarrufu_kwh": round(total_energy, 1),
        "su_tasarrufu_litre": round(total_water_ton * 1000.0, 1),
        "aktif_belediye": len(cities),
        "aktif_kurum": len(MARKETPLACE_ORGS),
        "vatandas_sayisi": int(total_pop * (katilim / 100.0)),
        "vatandas_katilim_orani": katilim,
        "etki_adet": etki,
        "filtre": {
            "il": il,
            "ilce": ilce,
            "belediye_id": belediye_id,
            "kurum_id": kurum_id,
        },
    }


def province_statistics(*, il=None) -> list[dict]:
    """MASTER illerinin puanlı sıralaması."""
    rows = []
    cities = [_norm_city(il)] if il else list_cities()
    for city in cities:
        pkg = MASTER_DATASET[city]
        d = pkg["dashboard"]
        sus = pkg["sustainability"]
        rows.append({
            "il": city,
            "ilan": d["toplam_aktif_ilan"],
            "atik_kg": round(d["geri_kazanilan_atik_kg"], 2),
            "co2e_kg": round(pkg["co2_ton"] * 1000.0, 2),
            "su_litre": round(pkg["water_ton"] * 1000.0, 2),
            "enerji_kwh": float(pkg["energy_kwh"]),
            "kullanici": int(pkg["population"] * d["vatandas_katilim_orani"] / 100 / 50),
            "puan": float(sus["puan"]),
        })
    return sorted(rows, key=lambda r: -r["puan"])


def top_bottom_provinces(limit: int = 10) -> dict:
    rows = province_statistics()
    return {
        "en_basarili": rows[:limit],
        "en_dusuk": list(reversed(rows[-limit:])) if rows else [],
    }


def ministry_map_data(*, il=None, ilce=None) -> dict:
    """
    15 MASTER il renkli; diğer 81-15 JS tarafında gri kalır.
    Heat: tüm MASTER şehir heatmap noktalarının birleşimi.
    """
    cities = [_norm_city(il)] if il else list(MASTER_DATASET.keys())
    heat: list[list[float]] = []
    centers = []
    il_yogunluk = []
    for city in cities:
        pkg = MASTER_DATASET[city]
        puan = float(pkg["sustainability"]["puan"])
        intensity = puan / 100.0
        for p in pkg["heatmap"]:
            heat.append([p[0], p[1], p[2]])
        # İl merkez vurgusu
        lat, lng = pkg["center"]
        heat.append([lat, lng, max(0.35, intensity * 1.4)])
        renk = "yesil" if puan >= 70 else "sari" if puan >= 40 else "kirmizi"
        centers.append({
            "il": city,
            "lat": lat,
            "lng": lng,
            "intensity": intensity,
            "kullanici": int(pkg["population"] * 0.001),
            "puan": puan,
            "renk": renk,
            "performans": (
                "Yüksek" if puan >= 70 else "Orta" if puan >= 40 else "Düşük"
            ),
        })
        il_yogunluk.append({
            "il": city,
            "intensity": intensity,
            "ilan": pkg["dashboard"]["toplam_aktif_ilan"],
            "co2e_kg": round(pkg["co2_ton"] * 1000.0, 2),
        })
    return {
        "heat": heat,
        "il_yogunluk": il_yogunluk,
        "il_merkezleri": centers,
    }


def _municipality_board() -> list[dict]:
    rows = []
    for city in list_cities():
        pkg = MASTER_DATASET[city]
        puan = float(pkg["sustainability"]["puan"])
        gelisim = float(pkg.get("gelisim_yuzde") or pkg["sustainability_history"].get("change_pct") or 0)
        teslim = float(pkg["dashboard"]["teslim_orani"])
        risk = float(pkg.get("risk_skoru") or _risk_score(puan, teslim, gelisim))
        renk = "yesil" if puan >= 70 else "sari" if puan >= 40 else "kirmizi"
        rows.append({
            "id": -2000 - len(rows),
            "ad": f"{city} Belediyesi",
            "il": city,
            "ilce": None,
            "tip": "merkez",
            "ilan": pkg["dashboard"]["toplam_aktif_ilan"],
            "teslim": pkg["dashboard"]["toplam_teslim"],
            "teslim_orani": teslim,
            "puan": puan,
            "gelisim_yuzde": gelisim,
            "risk_skoru": risk,
            "renk": renk,
        })
    return rows


def ministry_ai_summary() -> list[str]:
    board = _municipality_board()
    provinces = province_statistics()
    kpi = ministry_kpi()
    tips = [
        f"Ulusal özet: {kpi['toplam_ilan']} ilan · "
        f"CO₂ {kpi['co2_tasarrufu_kg']/1000:.0f} ton · "
        f"enerji {kpi['enerji_tasarrufu_kwh']/1000:.0f} bin kWh · "
        f"su {kpi['su_tasarrufu_litre']/1000:.0f} ton eşdeğeri.",
        f"Katılım oranı ortalama %{kpi['vatandas_katilim_orani']}; "
        f"{kpi['aktif_belediye']} il senaryosu aktif.",
    ]
    if provinces:
        tips.append(
            f"En başarılı il: {provinces[0]['il']} "
            f"(sürdürülebilirlik {provinces[0]['puan']})."
        )
        low = provinces[-1]
        tips.append(
            f"Öncelikli izleme: {low['il']} "
            f"(skor {low['puan']}) — teslim ve katılım güçlendirilmeli."
        )
    growing = sorted(board, key=lambda r: -r["gelisim_yuzde"])
    if growing:
        tips.append(
            f"{growing[0]['ad']} son 6 ayda "
            f"%{growing[0]['gelisim_yuzde']:.0f} gelişim gösterdi."
        )
    # MASTER AI bullets (ulusal)
    tips.append("Elektronik atık son dönemde ulusal ölçekte artıyor; organik azalıyor.")
    tips.append("Bitkisel yağ kampanyaları birden fazla ilde yükselişte.")
    return tips[:6]


def ministry_national_center(
    *,
    il=None,
    ilce=None,
    belediye_id=None,
    kurum_id=None,
    kategori=None,
    tarih=None,
    belediye_tipi=None,
) -> dict:
    """Ulusal Yönetim Merkezi — MASTER_DATASET paket (mevcut şema)."""
    kpi = ministry_kpi(il=il, ilce=ilce, belediye_id=belediye_id, kurum_id=kurum_id)
    provinces = province_statistics(il=il)
    rankings = top_bottom_provinces(10)
    map_data = ministry_map_data(il=il, ilce=ilce)
    board = _municipality_board()
    if il:
        board = [r for r in board if r["il"] == _norm_city(il)]

    # Üç liste farklı metriklerle — aynı sıralama olmamalı
    en_basarili = sorted(board, key=lambda r: -r["puan"])[:10]
    gelisim = sorted(board, key=lambda r: -r["gelisim_yuzde"])[:10]
    riskli = sorted(board, key=lambda r: -r.get("risk_skoru", 0))[:10]

    return {
        "kpi": kpi,
        "map_data": map_data,
        "province_rankings": rankings,
        "provinces": provinces,
        "en_basarili_belediyeler": en_basarili,
        "gelisim_gosteren": gelisim,
        "riskli_belediyeler": riskli,
        "ai_ozeti": ministry_ai_summary(),
        "charts": chart_demo_bundle(il=il or "İzmir"),
        "filtre": {
            "il": il,
            "ilce": ilce,
            "kategori": kategori,
            "tarih": tarih,
            "belediye_tipi": belediye_tipi,
        },
        "source": "demo",
    }


def ministry_statistics(*, il=None, ilce=None, belediye_id=None, kurum_id=None) -> dict:
    return {
        "kpi": ministry_kpi(il=il, ilce=ilce, belediye_id=belediye_id, kurum_id=kurum_id),
        "drilldown": {
            "iller": list_cities(),
            "ilceler": list(get_city(il)["districts"].keys()) if il else [],
            "belediyeler": [],
            "kurumlar": [o["ad"] for o in MARKETPLACE_ORGS[:20]],
        },
        "rankings": top_bottom_provinces(10),
        "provinces": province_statistics(il=il),
        "source": "demo",
    }


def chart_demo_bundle(*, il=None) -> dict:
    """JS fallback’leri ile uyumlu ortak grafik paketi (Sakarya varsayılan)."""
    pkg = get_city(il)
    cats = pkg["waste_categories"]
    hist = pkg["sustainability_history"]
    monthly = pkg["monthly_history"][-12:]
    board = national_leaderboard()
    month_labels = [
        _MONTH_LABELS_TR[int(str(row["ay"]).split("-")[1]) - 1] for row in monthly
    ]
    return {
        "category": {
            "labels": list(cats.keys()),
            "values": list(cats.values()),
        },
        "trend": {
            "labels": month_labels,
            "values": [float(row["atik_kg"]) for row in monthly],
        },
        "teslim_history": {
            "labels": month_labels,
            "values": [float(row["teslim_orani"]) for row in monthly],
        },
        "delivery": {
            "labels": ["Teslim", "Aktif", "Bekleyen"],
            "values": [
                int(pkg["dashboard"]["teslim_orani"]),
                int(100 - pkg["dashboard"]["teslim_orani"] - 8),
                8,
            ],
        },
        "radar": {
            "labels": [c["label"] for c in pkg["sustainability"]["criteria"]],
            "values": [c["score"] for c in pkg["sustainability"]["criteria"]],
        },
        "sustainability_categories": {
            "labels": [c["label"] for c in pkg["sustainability"]["criteria"]],
            "values": [c["score"] for c in pkg["sustainability"]["criteria"]],
            "keys": [c["key"] for c in pkg["sustainability"]["criteria"]],
        },
        "history": {
            "labels": [
                _MONTH_LABELS_TR[int(a.split("-")[1]) - 1] for a in hist["labels"]
            ],
            "values": hist["puanlar"],
        },
        "bars": {
            "labels": [r["il"] for r in board[:5]],
            "values": [r["puan"] for r in board[:5]],
        },
    }
