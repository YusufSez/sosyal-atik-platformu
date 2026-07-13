"""Demo Provider — sunum amaçlı örnek veri (mevcut response şemalarına uyumlu)."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
from typing import Any

from services.prediction_engine import (
    FORECAST_HORIZONS_DAYS,
    HORIZON_LABELS,
    LOOKBACK_MONTHS,
    METRIC_KEYS,
)
from utils import utc_now


def dashboard_kpis(*, il=None, ilce=None, mahalle=None) -> dict:
    return {
        "bugun_ilan": 12,
        "bugun_aktif_ilan": 9,
        "toplam_aktif_ilan": 48,
        "aktif_kaynak": 22,
        "aktif_atik": 26,
        "toplam_teslim": 31,
        "geri_kazanilan_atik_kg": 1840.0,
        "geri_kazanilan_kaynak_adet": 14,
        "geri_kazanilan_kaynak_skor": 1260,
        "atik_teslim": 17,
        "gunluk_kullanici": 86,
        "aktif_kurum": 7,
        "ortalama_teslim_gun": 2.4,
        "co2e_kg": 412.5,
        "etki_adet": 31,
        "filtre": {"il": il, "ilce": ilce, "mahalle": mahalle},
    }


def _metric_block(
    *,
    predicted: float,
    change_pct: float,
    confidence_pct: float,
    trend: str,
    risk: str,
    unit: str,
    ai_yorum: str = "",
) -> dict:
    half = predicted * 0.08
    return {
        "predicted": predicted,
        "change_pct": change_pct,
        "confidence_pct": confidence_pct,
        "confidence_interval": {
            "low": round(max(0.0, predicted - half), 2),
            "high": round(predicted + half, 2),
            "level_pct": confidence_pct,
        },
        "trend": trend,
        "risk": risk,
        "unit": unit,
        "ai_yorum": ai_yorum,
    }


def _forecast_block(scale: float = 1.0) -> dict:
    block = {
        "atik_miktari": _metric_block(
            predicted=round(420 * scale, 1),
            change_pct=8.4,
            confidence_pct=78.0,
            trend="yukselis",
            risk="orta",
            unit="kg",
            ai_yorum="Atık miktarında ılımlı artış bekleniyor; güven %78.",
        ),
        "kategori_artisi": {
            **_metric_block(
                predicted=12.5,
                change_pct=12.5,
                confidence_pct=71.0,
                trend="yukselis",
                risk="orta",
                unit="%",
                ai_yorum="Elektronik kategorisinde göreli artış öne çıkıyor.",
            ),
            "en_yogun_kategori": "Elektronik",
            "kategori": "Elektronik",
            "monthly_equivalent": 18.0,
            "monthly_volume": 18.0,
            "ranking": [
                {"kategori": "Elektronik", "change_pct": 12.5},
                {"kategori": "Plastik", "change_pct": 6.2},
                {"kategori": "Kağıt", "change_pct": 3.1},
            ],
        },
        "teslim_orani": _metric_block(
            predicted=round(68.0 * min(scale, 1.1), 1),
            change_pct=4.2,
            confidence_pct=82.0,
            trend="yukselis",
            risk="dusuk",
            unit="%",
            ai_yorum="Teslim oranı istikrarlı yükselişte; güven yüksek.",
        ),
        "katilim": _metric_block(
            predicted=round(54.0 * scale, 1),
            change_pct=5.8,
            confidence_pct=74.0,
            trend="yukselis",
            risk="dusuk",
            unit="%",
            ai_yorum="Vatandaş katılımında olumlu seyir devam ediyor.",
        ),
        "co2": _metric_block(
            predicted=round(95.0 * scale, 1),
            change_pct=7.1,
            confidence_pct=76.0,
            trend="yukselis",
            risk="orta",
            unit="kg",
            ai_yorum="CO₂ azaltım etkisi artma eğiliminde.",
        ),
        "kaynak_paylasimi": _metric_block(
            predicted=round(28 * scale, 1),
            change_pct=6.0,
            confidence_pct=70.0,
            trend="stabil",
            risk="dusuk",
            unit="ilan",
            ai_yorum="Kaynak paylaşımı dengeli seyrediyor.",
        ),
        "en_yogun_kategori": None,
    }
    ka = block["kategori_artisi"]
    block["en_yogun_kategori"] = {
        "horizon_days": 30,
        "en_yogun_kategori": "Elektronik",
        "predicted": 18.0,
        "change_pct": 12.5,
        "ranking": ka["ranking"],
        "confidence_pct": 71.0,
        "confidence_interval": ka["confidence_interval"],
        "trend": "yukselis",
        "risk": "orta",
        "ai_yorum": ka["ai_yorum"],
    }
    return block


def _history(months: int = 12, now: datetime | None = None) -> list[dict]:
    now = now or utc_now()
    rows = []
    for i in range(months - 1, -1, -1):
        year = now.year
        month = now.month - i
        while month <= 0:
            month += 12
            year -= 1
        factor = 0.7 + (months - i) * 0.03
        rows.append({
            "ay": f"{year:04d}-{month:02d}",
            "atik_kg": round(280 * factor, 1),
            "co2_kg": round(62 * factor, 1),
            "kaynak_adet": int(18 * factor),
            "teslim_orani": round(55 + i * 0.8, 1),
            "katilim": round(42 + i * 0.9, 1),
        })
    return rows


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
    now = now or utc_now()
    series = _history(lookback_months, now)
    forecasts = {}
    for days in FORECAST_HORIZONS_DAYS:
        scale = max(0.5, days / 90.0)
        block = _forecast_block(scale)
        block["en_yogun_kategori"]["horizon_days"] = days
        forecasts[str(days)] = block

    chart = {
        "labels": [s["ay"] for s in series],
        "atik_kg": [s["atik_kg"] for s in series],
        "co2_kg": [s["co2_kg"] for s in series],
        "kaynak_adet": [s["kaynak_adet"] for s in series],
        "teslim_orani": [s["teslim_orani"] for s in series],
        "katilim": [s["katilim"] for s in series],
        "forecast_atik": {
            str(d): forecasts[str(d)]["atik_miktari"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_co2": {
            str(d): forecasts[str(d)]["co2"]["predicted"] for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_teslim": {
            str(d): forecasts[str(d)]["teslim_orani"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_katilim": {
            str(d): forecasts[str(d)]["katilim"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_kategori": {
            str(d): forecasts[str(d)]["kategori_artisi"]["change_pct"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_kaynak": {
            str(d): forecasts[str(d)]["kaynak_paylasimi"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "horizon_labels": [HORIZON_LABELS[d] for d in FORECAST_HORIZONS_DAYS],
    }
    return {
        "lookback_months": lookback_months,
        "history": series,
        "forecasts": forecasts,
        "metrics": list(METRIC_KEYS),
        "horizons_days": list(FORECAST_HORIZONS_DAYS),
        "horizon_labels": dict(HORIZON_LABELS),
        "chart": chart,
        "filtre": {"il": il, "ilce": ilce, "mahalle": mahalle},
        "engine": "demo",
        "generated_at": now.isoformat(),
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
    if include_all_lookbacks:
        lookbacks = {
            str(m): prediction_payload(m, **filters) for m in LOOKBACK_MONTHS
        }
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

    narratives = [
        "Demo tahmin: atık hacminde ılımlı artış bekleniyor.",
        "Demo tahmin: teslim oranı ve katılım birlikte yükseliyor.",
        "Demo tahmin: elektronik kategorisi göreli olarak öne çıkıyor.",
    ]
    return {
        **multi,
        "narratives": narratives,
        "narrative_source": "demo",
    }


def sustainability_score(*, il=None, ilce=None, mahalle=None) -> dict:
    from constants import SUSTAINABILITY_CRITERION_LABELS, SUSTAINABILITY_WEIGHTS
    from services.sustainability_scoring import grade_for_score

    raw = {
        "geri_donusum": 74.0,
        "teslim": 81.0,
        "katilim": 68.0,
        "kaynak_paylasimi": 72.0,
        "karbon": 65.0,
        "teslim_suresi": 78.0,
        "ai_dogruluk": 70.0,
    }
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
    puan = round(weighted_sum, 1)
    return {
        "il": il,
        "ilce": ilce,
        "mahalle": mahalle,
        "puan": puan,
        "grade": grade_for_score(puan),
        "criteria": criteria,
        "raw": raw,
        "missing": {k: False for k in raw},
        "metrics": {
            "total": 96,
            "atik_total": 52,
            "kaynak_total": 44,
            "teslim": 61,
            "atik_teslim": 34,
            "kaynak_teslim": 27,
            "co2e_kg": 412.5,
            "atik_kg": 1840.0,
            "etki_adet": 61,
            "ortalama_teslim_gun": 2.4,
            "katilim_orani": 68.0,
            "kategori_paylari": {
                "Elektronik": 28.0,
                "Plastik": 22.0,
                "Kağıt": 18.0,
                "Diğer": 32.0,
            },
            "teslim_orani": 81.0,
            "geri_donusum_orani": 74.0,
        },
    }


def sustainability_ai_report(scored: dict | None = None) -> dict:
    scored = scored or sustainability_score()
    puan = scored.get("puan")
    grade = scored.get("grade")
    suggestions = [
        {
            "title": "Mahalle Bazlı Mobil Toplama",
            "description": (
                "Yoğun mahallelerde dönemsel mobil toplama noktaları ile "
                "teslim süresinin kısaltılması önerilir."
            ),
            "expected_impact": "Teslim süresi ve katılımda iyileşme",
            "priority": "Yüksek",
            "duration": "Orta",
            "reason": f"Demo sürdürülebilirlik skoru {puan}/100 ({grade}).",
            "trigger": "demo",
        },
        {
            "title": "Elektronik Atık Kampanyası",
            "description": (
                "Okul ve kamu kurumlarında e-atık günleri düzenlenerek "
                "elektronik kategori payı güçlendirilebilir."
            ),
            "expected_impact": "Elektronik atık toplama payında artış",
            "priority": "Orta",
            "duration": "Kısa",
            "reason": "Demo veri: elektronik kategori öne çıkıyor.",
            "trigger": "demo",
        },
    ]
    report = {
        "summary": (
            f"Demo değerlendirme: bölge skoru {puan}/100 ({grade}). "
            "Sunum amaçlı örnek sürdürülebilirlik raporu."
        ),
        "strengths": [
            "Teslim oranı yüksek seviyede",
            "Vatandaş katılımı istikrarlı",
            "Kaynak paylaşımı dengeli",
        ],
        "improvements": [
            "Karbon azaltımını artırmak",
            "E-atık toplama sıklığını yükseltmek",
            "Mahalle bazlı lojistiği sıkılaştırmak",
        ],
        "recommendations": [
            "Mobil toplama noktalarını artırın",
            "Kurumsal e-atık günleri planlayın",
            "Teslim hatırlatma bildirimlerini etkinleştirin",
        ],
        "expected_gains": "Katılım ve CO₂ etkisinde ölçülebilir iyileşme",
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


def marketplace_matches(limit: int = 12) -> list[dict]:
    samples = [
        {
            "id": -101,
            "ad": "Demo Geri Dönüşüm A.Ş.",
            "username": "demo_gd",
            "il": "İstanbul",
            "ilce": "Kadıköy",
            "mesafe_km": 4.2,
            "eslesme_skoru": 88.5,
            "nedenler": ["4.2 km mesafede", "Elektronik kategorisinde deneyim"],
            "skor_detay": {"mesafe": 91.0, "kategori": 85.0, "puan": 80.0, "aktivite": 70.0},
        },
        {
            "id": -102,
            "ad": "Demo Belediye Atölyesi",
            "username": "demo_bld",
            "il": "İstanbul",
            "ilce": "Üsküdar",
            "mesafe_km": 9.8,
            "eslesme_skoru": 76.2,
            "nedenler": ["9.8 km içinde erişilebilir", "ortalama puan 4.2"],
            "skor_detay": {"mesafe": 72.0, "kategori": 60.0, "puan": 84.0, "aktivite": 55.0},
        },
        {
            "id": -103,
            "ad": "Demo Sosyal Kooperatif",
            "username": "demo_koop",
            "il": "İstanbul",
            "ilce": "Ataşehir",
            "mesafe_km": 14.5,
            "eslesme_skoru": 69.0,
            "nedenler": ["14.5 km içinde erişilebilir", "3 tamamlanan işlem"],
            "skor_detay": {"mesafe": 60.0, "kategori": 50.0, "puan": 70.0, "aktivite": 60.0},
        },
    ]
    return deepcopy(samples[:limit])


def municipality_ai_insights(dashboard: dict | None = None) -> dict:
    cards = [
        {
            "title": "Geri dönüşüm ivmesi",
            "analysis": (
                "Demo veriye göre geri dönüşüm oranı son dönemde istikrarlı yükselmektedir."
            ),
            "expected_impact": "Teslim ve CO₂ metriklerinde olumlu seyir",
            "priority": "Orta",
            "trigger": "demo",
        },
        {
            "title": "Elektronik atık artışı",
            "analysis": (
                "Elektronik atıklarda dikkat çekici artış gözlenmiştir; "
                "kampanya planlaması önerilir."
            ),
            "expected_impact": "E-atık toplama payında artış",
            "priority": "Yüksek",
            "trigger": "demo",
        },
        {
            "title": "Mobil toplama önerisi",
            "analysis": (
                "Yoğun mahallelerde mobil toplama noktalarının artırılması önerilmektedir."
            ),
            "expected_impact": "Ortalama teslim süresinde azalma",
            "priority": "Orta",
            "trigger": "demo",
        },
    ]
    return {
        "source": "demo",
        "insights": cards,
        "dashboard": dashboard or dashboard_kpis(),
    }
