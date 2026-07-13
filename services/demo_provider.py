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
    sus_series = []
    for i, row in enumerate(hist6):
        p = round(puan - 6 + i * 1.1, 1)
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
            "change_pct": round(
                ((sus_series[-1]["puan"] - sus_series[0]["puan"]) / max(sus_series[0]["puan"], 1))
                * 100.0,
                1,
            ),
            "trend": "yukselis",
        },
        "heatmap": _build_heatmap(
            city, count=48 if city in ("İstanbul", "Ankara", "İzmir") else 36
        ),
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


def dashboard_kpis(*, il=None, ilce=None, mahalle=None) -> dict:
    city = _norm_city(il)
    data = deepcopy(get_city(city)["dashboard"])
    data["filtre"] = {"il": il or city, "ilce": ilce, "mahalle": mahalle}
    return data


def heat_map_points(*, il=None, ilce=None, mahalle=None, yogunluk="atik") -> list:
    pts = deepcopy(get_city(il)["heatmap"])
    # yogunluk yalnızca intensity ölçeği (şema aynı)
    scale = {"kaynak": 0.85, "teslim": 1.1}.get((yogunluk or "atik").lower(), 1.0)
    return [[p[0], p[1], round(min(1.0, p[2] * scale), 3)] for p in pts]


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


def kategori_analizi(*, il=None) -> dict:
    """Belediye kategori grafik şeması — MASTER waste_categories."""
    from constants import MUNICIPALITY_CATEGORY_GROUPS

    pkg = get_city(il)
    raw = pkg["waste_categories"]
    # MASTER "Bitkisel yağ" → UI grubu "Bitkisel Yağ"
    alias = {"Bitkisel yağ": "Bitkisel Yağ", "Elektronik": "Elektronik"}
    counts = {g: 0 for g in MUNICIPALITY_CATEGORY_GROUPS}
    total_listings = pkg["dashboard"]["toplam_aktif_ilan"]
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
    ozet = dashboard_kpis(il=il, ilce=ilce, mahalle=mahalle)
    charts = chart_demo_bundle(il=il)
    # Trend serisini ops metrikleriyle hizala
    cards = deepcopy(pkg["ops_cards"])
    charts["trend"] = {
        "labels": ["Bugün", "Son 24s ilan", "Son 24s teslim", "Aktif", "Teslim", "Bekleyen"],
        "values": [
            cards["bugun_acilan"],
            cards["son_24_saat"]["ilan"],
            cards["son_24_saat"]["teslim"],
            ozet["toplam_aktif_ilan"],
            ozet["toplam_teslim"],
            cards["bekleyen_teslimler"],
        ],
    }
    charts["delivery"] = {
        "labels": ["Teslim", "Aktif", "Bekleyen"],
        "values": [
            ozet["toplam_teslim"],
            ozet["toplam_aktif_ilan"],
            cards["bekleyen_teslimler"],
        ],
    }
    return {
        "ozet": ozet,
        "cards": cards,
        "aktiviteler": deepcopy(pkg["activities"][:12]),
        "filtre": ozet["filtre"],
        "charts": charts,
        "map_center": deepcopy(pkg["map_center"]),
        "heatmap": heat_map_points(il=il, ilce=ilce, mahalle=mahalle),
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
    history = deepcopy(pkg["monthly_history"][-lookback_months:])
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


def marketplace_matches(limit: int = 12, *, il=None) -> list[dict]:
    city = _norm_city(il)
    orgs = [o for o in MARKETPLACE_ORGS if o["il"] == city]
    if len(orgs) < 5:
        orgs = list(MARKETPLACE_ORGS)
    samples = []
    for i, o in enumerate(orgs[:limit]):
        skor = round(88.5 - i * 2.3, 1)
        dist = round(3.5 + i * 1.7, 1)
        samples.append({
            "id": -200 - i,
            "ad": o["ad"],
            "username": o["ad"].lower().replace(" ", "_")[:24],
            "role": "company",
            "il": o["il"],
            "ilce": o["ilce"],
            "lat": get_city(o["il"])["center"][0],
            "lng": get_city(o["il"])["center"][1],
            "mesafe_km": dist,
            "eslesme_skoru": skor,
            "nedenler": [f"{dist} km mesafede", f"{o['kategori']} kategorisinde deneyim"],
            "skor_detay": {
                "mesafe": round(90 - i * 3, 1),
                "kategori": round(80 - i * 2, 1),
                "puan": round(78 - i, 1),
                "aktivite": round(70 - i * 1.5, 1),
            },
            "puan_ortalama": round(4.5 - i * 0.05, 2),
        })
    return samples


def marketplace_orgs(*, limit: int = 40) -> list[dict]:
    return deepcopy(MARKETPLACE_ORGS[:limit])


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
        gelisim = float(pkg["sustainability_history"].get("change_pct") or 0)
        teslim = float(pkg["dashboard"]["teslim_orani"])
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

    en_basarili = board[:10]
    gelisim = sorted(
        [r for r in board if r["gelisim_yuzde"] > 0],
        key=lambda r: -r["gelisim_yuzde"],
    )[:10]
    # Risk = en düşük sürdürülebilirlik skorları (jüri senaryosu)
    riskli = sorted(board, key=lambda r: r["puan"])[:10]

    return {
        "kpi": kpi,
        "map_data": map_data,
        "province_rankings": rankings,
        "provinces": provinces,
        "en_basarili_belediyeler": en_basarili,
        "gelisim_gosteren": gelisim,
        "riskli_belediyeler": riskli,
        "ai_ozeti": ministry_ai_summary(),
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
    board = national_leaderboard()
    return {
        "category": {
            "labels": list(cats.keys()),
            "values": list(cats.values()),
        },
        "trend": {
            "labels": ["Pzt", "Sal", "Çar", "Per", "Cum", "Cmt", "Paz"],
            "values": [12, 15, 14, 18, 17, 11, 16],
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
