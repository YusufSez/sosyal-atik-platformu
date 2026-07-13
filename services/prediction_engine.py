"""AI Prediction Engine — istatistiksel tahmin + AI yorum katmanı.

Ağır bağımlılık yok: aylık seriler üzerinde basit OLS + trend ekstrapolasyonu.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func

from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.municipality_analytics import normalize_municipality_category
from utils import utc_now

LOOKBACK_MONTHS = (12, 24, 36)
FORECAST_HORIZONS_DAYS = (7, 30, 90)


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _geo_filters(il=None, ilce=None, mahalle=None):
    filters = []
    if _norm(il):
        filters.append(User.il == _norm(il))
    if _norm(ilce):
        filters.append(User.ilce == _norm(ilce))
    if _norm(mahalle):
        filters.append(User.mahalle == _norm(mahalle))
    return filters


def _month_key(dt: datetime) -> str:
    return f"{dt.year:04d}-{dt.month:02d}"


def _month_start(dt: datetime) -> datetime:
    return dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _add_months(dt: datetime, months: int) -> datetime:
    year = dt.year + (dt.month - 1 + months) // 12
    month = (dt.month - 1 + months) % 12 + 1
    return dt.replace(year=year, month=month, day=1)


def _linear_regression(ys: list[float]) -> tuple[float, float]:
    """y = a + b*x, x = 0..n-1. Dönüş: (intercept, slope)."""
    n = len(ys)
    if n == 0:
        return 0.0, 0.0
    if n == 1:
        return float(ys[0]), 0.0
    xs = list(range(n))
    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    denom = sum((x - mean_x) ** 2 for x in xs)
    if denom == 0:
        return mean_y, 0.0
    slope = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys)) / denom
    intercept = mean_y - slope * mean_x
    return intercept, slope


def _predict_next_value(ys: list[float], steps_ahead: float = 1.0) -> float:
    intercept, slope = _linear_regression(ys)
    n = len(ys)
    if n == 0:
        return 0.0
    pred = intercept + slope * (n - 1 + steps_ahead)
    return max(0.0, float(pred))


def _pct_change(current: float, previous: float) -> float:
    if previous == 0:
        return 100.0 if current > 0 else 0.0
    return round(((current - previous) / previous) * 100.0, 1)


def _empty_month_bucket() -> dict:
    return {
        "atik_kg": 0.0,
        "kaynak_adet": 0,
        "atik_adet": 0,
        "teslim_adet": 0,
        "toplam_ilan": 0,
        "kategoriler": defaultdict(int),
    }


def _collect_monthly_series(
    lookback_months: int,
    *,
    il=None,
    ilce=None,
    mahalle=None,
    now: datetime | None = None,
) -> list[dict]:
    """Son N ay için aylık metrik serisi (kronolojik)."""
    now = now or utc_now()
    end = _month_start(now)
    start = _add_months(end, -(lookback_months - 1))
    geo = _geo_filters(il, ilce, mahalle)

    buckets: dict[str, dict] = {}
    cursor = start
    for _ in range(lookback_months):
        buckets[_month_key(cursor)] = _empty_month_bucket()
        cursor = _add_months(cursor, 1)

    # Kaynak ilanları
    kay_q = Kaynak.query.filter(Kaynak.tarih >= start)
    if geo:
        kay_q = kay_q.join(User, Kaynak.user_id == User.id).filter(*geo)
    for row in kay_q.all():
        if not row.tarih:
            continue
        key = _month_key(row.tarih)
        if key not in buckets:
            continue
        b = buckets[key]
        b["kaynak_adet"] += 1
        b["toplam_ilan"] += 1
        if row.ilan_durumu == "Teslim Edildi":
            b["teslim_adet"] += 1
        cat = normalize_municipality_category(row.kategori)
        b["kategoriler"][cat] += 1

    # Atık ilanları
    atik_q = Atik.query.filter(Atik.tarih >= start)
    if geo:
        atik_q = atik_q.join(User, Atik.user_id == User.id).filter(*geo)
    for row in atik_q.all():
        if not row.tarih:
            continue
        key = _month_key(row.tarih)
        if key not in buckets:
            continue
        b = buckets[key]
        b["atik_adet"] += 1
        b["toplam_ilan"] += 1
        if row.ilan_durumu == "Teslim Edildi":
            b["teslim_adet"] += 1
        cat = normalize_municipality_category(row.kategori)
        b["kategoriler"][cat] += 1

    # Atık kg (etki)
    etki_q = CevreselEtki.query.filter(CevreselEtki.timestamp >= start)
    if geo:
        etki_q = etki_q.join(User, CevreselEtki.user_id == User.id).filter(*geo)
    for etki in etki_q.all():
        ts = etki.timestamp
        if not ts:
            continue
        key = _month_key(ts)
        if key not in buckets:
            continue
        buckets[key]["atik_kg"] += float(etki.atik_kg or 0)

    series = []
    cursor = start
    for _ in range(lookback_months):
        key = _month_key(cursor)
        b = buckets[key]
        toplam = b["toplam_ilan"]
        teslim_orani = round(100.0 * b["teslim_adet"] / toplam, 1) if toplam else 0.0
        cats = dict(b["kategoriler"])
        top_cat = max(cats, key=cats.get) if cats else "Diğer"
        series.append({
            "ay": key,
            "atik_kg": round(b["atik_kg"], 2),
            "kaynak_adet": b["kaynak_adet"],
            "atik_adet": b["atik_adet"],
            "teslim_adet": b["teslim_adet"],
            "toplam_ilan": toplam,
            "teslim_orani": teslim_orani,
            "en_yogun_kategori": top_cat,
            "kategoriler": cats,
        })
        cursor = _add_months(cursor, 1)
    return series


def _horizon_steps(days: int) -> float:
    """Aylık seriden kaç ay ileri (kesirli)."""
    return max(days / 30.0, 0.1)


def _forecast_metric(series: list[dict], field: str, days: int) -> dict:
    ys = [float(s.get(field) or 0) for s in series]
    steps = _horizon_steps(days)
    predicted = _predict_next_value(ys, steps_ahead=steps)
    # Günlük ölçek: aylık tahmini → dönem toplamı (steps * monthly ≈ already steps ahead monthly value)
    # Daha sezgisel: son ay ortalaması + trend ile dönem değeri
    last = ys[-1] if ys else 0.0
    # Dönem tahmini: günlük hız × gün
    daily = predicted / 30.0
    period_total = round(daily * days, 2)
    # Aylık eşdeğer tahmin (grafik için)
    monthly_equiv = round(predicted, 2)
    change_pct = _pct_change(monthly_equiv, last)
    return {
        "horizon_days": days,
        "predicted": period_total,
        "monthly_equivalent": monthly_equiv,
        "baseline_last_month": round(last, 2),
        "change_pct": change_pct,
        "history": ys,
    }


def _forecast_top_category(series: list[dict], days: int) -> dict:
    """Kategori trendlerinden en yoğun beklenen kategori."""
    cat_series: dict[str, list[float]] = defaultdict(list)
    all_cats = set()
    for s in series:
        all_cats.update((s.get("kategoriler") or {}).keys())
    if not all_cats:
        all_cats = {"Diğer"}
    for s in series:
        cats = s.get("kategoriler") or {}
        for cat in all_cats:
            cat_series[cat].append(float(cats.get(cat, 0)))

    steps = _horizon_steps(days)
    scored = []
    for cat, ys in cat_series.items():
        pred = _predict_next_value(ys, steps_ahead=steps)
        last = ys[-1] if ys else 0.0
        scored.append({
            "kategori": cat,
            "predicted": round(pred, 2),
            "change_pct": _pct_change(pred, last),
            "baseline_last_month": round(last, 2),
        })
    scored.sort(key=lambda x: -x["predicted"])
    top = scored[0] if scored else {
        "kategori": "Diğer",
        "predicted": 0.0,
        "change_pct": 0.0,
        "baseline_last_month": 0.0,
    }
    return {
        "horizon_days": days,
        "en_yogun_kategori": top["kategori"],
        "predicted": top["predicted"],
        "change_pct": top["change_pct"],
        "ranking": scored[:7],
    }


def run_statistical_forecast(
    lookback_months: int = 12,
    *,
    il=None,
    ilce=None,
    mahalle=None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """İstatistiksel tahmin motoru (Gemini yok)."""
    if lookback_months not in LOOKBACK_MONTHS:
        lookback_months = 12

    series = _collect_monthly_series(
        lookback_months, il=il, ilce=ilce, mahalle=mahalle, now=now
    )

    forecasts = {}
    for days in FORECAST_HORIZONS_DAYS:
        forecasts[str(days)] = {
            "atik_miktari": _forecast_metric(series, "atik_kg", days),
            "kaynak_paylasimi": _forecast_metric(series, "kaynak_adet", days),
            "teslim_orani": _forecast_metric(series, "teslim_orani", days),
            "en_yogun_kategori": _forecast_top_category(series, days),
        }
        # teslim_orani predicted should stay 0-100
        tr = forecasts[str(days)]["teslim_orani"]
        tr["predicted"] = round(min(100.0, max(0.0, tr["monthly_equivalent"])), 1)
        tr["monthly_equivalent"] = tr["predicted"]

    chart = {
        "labels": [s["ay"] for s in series],
        "atik_kg": [s["atik_kg"] for s in series],
        "kaynak_adet": [s["kaynak_adet"] for s in series],
        "teslim_orani": [s["teslim_orani"] for s in series],
        "forecast_atik": {
            str(d): forecasts[str(d)]["atik_miktari"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_kaynak": {
            str(d): forecasts[str(d)]["kaynak_paylasimi"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
        "forecast_teslim": {
            str(d): forecasts[str(d)]["teslim_orani"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
        },
    }

    return {
        "lookback_months": lookback_months,
        "history": series,
        "forecasts": forecasts,
        "chart": chart,
        "filtre": {
            "il": _norm(il),
            "ilce": _norm(ilce),
            "mahalle": _norm(mahalle),
        },
        "engine": "ols-trend",
        "generated_at": (now or utc_now()).isoformat(),
    }


def run_multi_lookback_forecast(**filters) -> dict:
    """12 / 24 / 36 ay analizlerini birlikte üretir."""
    results = {}
    for months in LOOKBACK_MONTHS:
        results[str(months)] = run_statistical_forecast(months, **filters)
    return {
        "lookbacks": results,
        "primary": results["12"],
        "horizons_days": list(FORECAST_HORIZONS_DAYS),
        "lookback_options": list(LOOKBACK_MONTHS),
    }
