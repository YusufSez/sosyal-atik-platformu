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


def _build_heatmap(city: str, *, count: int = 36) -> list[list[float]]:
    geo = _CITY_GEO[city]
    hotspots = geo["hotspots"]
    points: list[list[float]] = []
    # sabit ızgara ofsetleri — random yok
    offsets = [
        (0.0, 0.0), (0.004, 0.002), (-0.003, 0.005), (0.006, -0.004),
        (-0.005, -0.003), (0.002, 0.007), (-0.007, 0.001), (0.008, 0.003),
        (-0.002, -0.006), (0.005, 0.005), (-0.004, 0.004), (0.003, -0.007),
    ]
    i = 0
    while len(points) < count:
        name, lat, lng, intensity = hotspots[i % len(hotspots)]
        ox, oy = offsets[i % len(offsets)]
        ring = (i // len(hotspots)) % 3
        points.append([
            round(lat + ox * (1 + ring * 0.4), 5),
            round(lng + oy * (1 + ring * 0.4), 5),
            round(min(1.0, intensity * (1.0 - ring * 0.12)), 3),
        ])
        i += 1
    return points


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
        "heatmap": _build_heatmap(city, count=40 if city in ("İstanbul", "Ankara", "İzmir") else 28),
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


def ops_center(*, il=None, ilce=None, mahalle=None) -> dict:
    pkg = get_city(il)
    ozet = dashboard_kpis(il=il, ilce=ilce, mahalle=mahalle)
    return {
        "ozet": ozet,
        "cards": deepcopy(pkg["ops_cards"]),
        "aktiviteler": deepcopy(pkg["activities"][:12]),
        "filtre": ozet["filtre"],
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
    """Ulusal karar destek — MASTER_DATASET agregasyonu."""
    board = national_leaderboard()
    now = utc_now()
    total_ilan = sum(MASTER_DATASET[c]["dashboard"]["toplam_aktif_ilan"] for c in MASTER_DATASET)
    total_co2 = sum(MASTER_DATASET[c]["co2_ton"] for c in MASTER_DATASET)
    cats = {k: 0.0 for k in CATEGORY_KEYS}
    for city, pkg in MASTER_DATASET.items():
        w = pkg["dashboard"]["toplam_aktif_ilan"]
        for k, pct in pkg["waste_categories"].items():
            cats[k] = cats.get(k, 0) + w * pct
    cat_sum = sum(cats.values()) or 1
    cat_labels = list(CATEGORY_KEYS)
    cat_values = [round(100.0 * cats[k] / cat_sum, 1) for k in cat_labels]

    # 8 haftalık katılım (Sakarya history proxy + national scale)
    sak = MASTER_DATASET[DEFAULT_CITY]["monthly_history"][-6:]
    participation = {
        "labels": [row["ay"] for row in sak] + ["W7", "W8"],
        "aktif": [int(row["katilim"]) for row in sak] + [72, 74],
        "ilanlar": [int(row["kaynak_adet"] * 3) for row in sak] + [40, 44],
    }
    return {
        "generated_at": now.isoformat(),
        "kpi": {
            "aktif_belediye": len(MASTER_DATASET),
            "toplam_ilan": total_ilan,
            "co2_ton": round(total_co2, 1),
            "ortalama_puan": round(sum(r["puan"] for r in board) / len(board), 1),
        },
        "weekly_report": {
            "metrics": {"ilan": int(total_ilan * 0.02), "atik_kg": 12000, "co2e_kg": total_co2 * 20},
            "change_pct": {"ilan": 6.2, "atik_kg": 4.1, "co2e_kg": 5.5},
        },
        "monthly_report": {
            "metrics": {"ilan": int(total_ilan * 0.08), "atik_kg": 52000, "co2e_kg": total_co2 * 80},
            "change_pct": {"ilan": 8.4, "atik_kg": 5.2, "co2e_kg": 7.1},
        },
        "risk_analysis": {
            "high": [r for r in board if r["puan"] < 70],
            "medium": [r for r in board if 70 <= r["puan"] < 78],
            "low": [r for r in board if r["puan"] >= 78],
        },
        "campaigns": [
            {"title": "Elektronik Atık Haftası", "detail": "Ulusal elektronik artışı için ortak kampanya.", "priority": "Yüksek"},
            {"title": "Bitkisel Yağ Toplama", "detail": "Kampanya sonrası yükselişi yaygınlaştırın.", "priority": "Orta"},
            {"title": "Organik Kompost", "detail": "Organik düşüşü dengelemek için kompost programı.", "priority": "Orta"},
        ],
        "municipality_comparisons": {
            "labels": [r["il"] for r in board[:8]],
            "puanlar": [r["puan"] for r in board[:8]],
        },
        "category_shifts": {
            "labels": cat_labels,
            "previous": [max(1, v - 2) for v in cat_values],
            "current": cat_values,
        },
        "participation_trends": participation,
        "ministry_actions": [
            {"title": "Riskli illerde saha desteği", "detail": "Trabzon ve benzeri illerde teslim oranı iyileştirmesi.", "priority": "Yüksek"},
            {"title": "İyi uygulama paylaşımı", "detail": "İzmir–İstanbul modellerini ulusal bültende yayınlayın.", "priority": "Orta"},
        ],
        "reports": {
            "weekly": {"title": "Haftalık Rapor", "key": "weekly"},
            "monthly": {"title": "Aylık Rapor", "key": "monthly"},
            "full": {"title": "Tam Karar Destek Raporu", "key": "full"},
        },
        "ai": {
            "overview": "Ulusal demo senaryosu: elektronik artıyor, organik azalıyor, bitkisel yağ kampanyası yükseliyor.",
            "weekly_narrative": [
                "Elektronik atık son dönemde belirgin arttı.",
                "Teslim oranları genel olarak yükseliyor.",
                "CO₂ kazanımı hedefin üzerinde.",
            ],
            "monthly_narrative": [
                "Son 30 günde ulusal ilan hacmi arttı.",
                "Bitkisel yağ kampanyası başarılı.",
                "Organik atıkta düşüş sürüyor.",
            ],
            "risk_narrative": [
                "Düşük skorlu illerde saha takibi önerilir.",
                "Sanayi hatlarında metal lojistiği kritik.",
            ],
            "source": "demo",
        },
        "ai_source": "demo",
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
