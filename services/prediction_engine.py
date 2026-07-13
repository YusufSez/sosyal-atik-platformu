"""AI Prediction Engine — istatistiksel tahmin + güven / trend / risk.

Ağır bağımlılık yok: aylık seriler üzerinde OLS + trend ekstrapolasyonu.
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import datetime
from typing import Any

from models import Atik, CevreselEtki, Kaynak, User
from services.municipality_analytics import normalize_municipality_category
from utils import utc_now

LOOKBACK_MONTHS = (12, 24, 36)
FORECAST_HORIZONS_DAYS = (7, 30, 90, 180, 365)
HORIZON_LABELS = {
    7: "7 gün",
    30: "30 gün",
    90: "90 gün",
    180: "6 ay",
    365: "12 ay",
}

METRIC_KEYS = (
    "atik_miktari",
    "kategori_artisi",
    "teslim_orani",
    "katilim",
    "co2",
)

METRIC_META = {
    "atik_miktari": {"label": "Atık miktarı", "unit": "kg", "kind": "volume"},
    "kategori_artisi": {"label": "Kategori artışı", "unit": "%", "kind": "category"},
    "teslim_orani": {"label": "Teslim oranı", "unit": "%", "kind": "rate"},
    "katilim": {"label": "Katılım", "unit": "%", "kind": "rate"},
    "co2": {"label": "CO₂", "unit": "kg", "kind": "volume"},
    "kaynak_paylasimi": {"label": "Kaynak paylaşımı", "unit": "ilan", "kind": "volume"},
}


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


def _r_squared(ys: list[float], intercept: float, slope: float) -> float:
    n = len(ys)
    if n < 2:
        return 0.0
    mean_y = sum(ys) / n
    ss_tot = sum((y - mean_y) ** 2 for y in ys)
    if ss_tot <= 1e-12:
        return 1.0 if all(abs(y - ys[0]) < 1e-12 for y in ys) else 0.0
    ss_res = sum((y - (intercept + slope * i)) ** 2 for i, y in enumerate(ys))
    return max(0.0, min(1.0, 1.0 - ss_res / ss_tot))


def _residual_std(ys: list[float], intercept: float, slope: float) -> float:
    n = len(ys)
    if n < 3:
        return 0.0
    ss_res = sum((y - (intercept + slope * i)) ** 2 for i, y in enumerate(ys))
    return math.sqrt(ss_res / (n - 2))


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


def _trend_label(change_pct: float) -> str:
    if change_pct >= 8:
        return "yukselis"
    if change_pct <= -8:
        return "dusus"
    return "stabil"


def _confidence_bundle(
    ys: list[float],
    predicted: float,
    steps_ahead: float,
    *,
    clamp_rate: bool = False,
) -> dict:
    """Güven aralığı (%) ve düşük/yüksek bant."""
    n = len(ys)
    intercept, slope = _linear_regression(ys)
    r2 = _r_squared(ys, intercept, slope)
    sigma = _residual_std(ys, intercept, slope)

    # Veri derinliği cezası
    depth = min(1.0, n / 12.0)
    # Uzun ufukta güven düşer
    horizon_penalty = max(0.35, 1.0 - 0.08 * max(0.0, steps_ahead - 1.0))
    confidence_pct = round(100.0 * (0.35 + 0.55 * r2) * depth * horizon_penalty, 1)
    confidence_pct = max(18.0, min(95.0, confidence_pct))

    # ~%95 bant yaklaşıklaması (OLS SE)
    mean_x = (n - 1) / 2.0 if n else 0.0
    ss_x = sum((i - mean_x) ** 2 for i in range(n)) if n else 1.0
    x_future = (n - 1) + steps_ahead if n else steps_ahead
    leverage = 1.0 + (1.0 / max(n, 1)) + ((x_future - mean_x) ** 2) / max(ss_x, 1e-9)
    se = sigma * math.sqrt(leverage) if sigma > 0 else max(abs(predicted) * 0.15, 0.5)
    if n < 3:
        se = max(abs(predicted) * 0.25, 1.0)

    low = predicted - 1.96 * se
    high = predicted + 1.96 * se
    if clamp_rate:
        low = max(0.0, min(100.0, low))
        high = max(0.0, min(100.0, high))
        predicted_c = max(0.0, min(100.0, predicted))
    else:
        low = max(0.0, low)
        predicted_c = max(0.0, predicted)

    return {
        "confidence_pct": confidence_pct,
        "confidence_interval": {
            "low": round(low, 2),
            "high": round(high, 2),
            "level_pct": confidence_pct,
        },
        "r_squared": round(r2, 3),
        "predicted_clamped": round(predicted_c, 2),
    }


def _risk_for_metric(metric_key: str, change_pct: float, confidence_pct: float, predicted: float) -> str:
    """Metrik yönüne göre risk: düşen teslim/katılım/CO₂ kötü; yükselen atık/kategori artış riskli olabilir."""
    low_conf = confidence_pct < 40

    if metric_key in ("teslim_orani", "katilim", "co2"):
        if change_pct <= -15 or (metric_key != "co2" and predicted < 25):
            level = "yuksek"
        elif change_pct <= -5 or (metric_key != "co2" and predicted < 40):
            level = "orta"
        else:
            level = "dusuk"
    elif metric_key == "atik_miktari":
        # Aşırı artış operasyonel yük riski
        if change_pct >= 40:
            level = "yuksek"
        elif change_pct >= 20 or change_pct <= -25:
            level = "orta"
        else:
            level = "dusuk"
    else:  # kategori_artisi
        if change_pct >= 50:
            level = "yuksek"
        elif change_pct >= 25:
            level = "orta"
        else:
            level = "dusuk"

    if low_conf and level == "dusuk":
        return "orta"
    if low_conf and level == "orta":
        return "yuksek"
    return level


def _empty_month_bucket() -> dict:
    return {
        "atik_kg": 0.0,
        "co2_kg": 0.0,
        "kaynak_adet": 0,
        "atik_adet": 0,
        "teslim_adet": 0,
        "toplam_ilan": 0,
        "aktif_kullanicilar": set(),
        "kategoriler": defaultdict(int),
    }


def _count_citizens(il=None, ilce=None, mahalle=None) -> int:
    from constants import ROLE_USER

    q = User.query.filter_by(role=ROLE_USER, is_banned=False)
    for f in _geo_filters(il, ilce, mahalle):
        q = q.filter(f)
    return q.count()


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
    citizen_total = max(_count_citizens(il, ilce, mahalle), 1)

    buckets: dict[str, dict] = {}
    cursor = start
    for _ in range(lookback_months):
        buckets[_month_key(cursor)] = _empty_month_bucket()
        cursor = _add_months(cursor, 1)

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
        if row.user_id:
            b["aktif_kullanicilar"].add(row.user_id)
        cat = normalize_municipality_category(row.kategori)
        b["kategoriler"][cat] += 1

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
        if row.user_id:
            b["aktif_kullanicilar"].add(row.user_id)
        cat = normalize_municipality_category(row.kategori)
        b["kategoriler"][cat] += 1

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
        buckets[key]["co2_kg"] += float(etki.co2e_kg or 0)
        if etki.user_id:
            buckets[key]["aktif_kullanicilar"].add(etki.user_id)

    series = []
    cursor = start
    for _ in range(lookback_months):
        key = _month_key(cursor)
        b = buckets[key]
        toplam = b["toplam_ilan"]
        teslim_orani = round(100.0 * b["teslim_adet"] / toplam, 1) if toplam else 0.0
        aktif = len(b["aktif_kullanicilar"])
        katilim = round(100.0 * aktif / citizen_total, 1)
        cats = dict(b["kategoriler"])
        top_cat = max(cats, key=cats.get) if cats else "Diğer"
        series.append({
            "ay": key,
            "atik_kg": round(b["atik_kg"], 2),
            "co2_kg": round(b["co2_kg"], 2),
            "kaynak_adet": b["kaynak_adet"],
            "atik_adet": b["atik_adet"],
            "teslim_adet": b["teslim_adet"],
            "toplam_ilan": toplam,
            "teslim_orani": teslim_orani,
            "katilim": katilim,
            "aktif_kullanici": aktif,
            "en_yogun_kategori": top_cat,
            "kategoriler": cats,
        })
        cursor = _add_months(cursor, 1)
    return series


def _horizon_steps(days: int) -> float:
    """Aylık seriden kaç ay ileri (kesirli)."""
    return max(days / 30.0, 0.1)


def _enrich_prediction(
    *,
    metric_key: str,
    days: int,
    predicted: float,
    ys: list[float],
    steps: float,
    extra: dict | None = None,
) -> dict:
    meta = METRIC_META[metric_key]
    kind = meta["kind"]
    last = ys[-1] if ys else 0.0
    clamp_rate = kind == "rate"

    if kind == "volume":
        daily = predicted / 30.0
        period_value = round(daily * days, 2)
        monthly_equiv = round(predicted, 2)
        change_pct = _pct_change(monthly_equiv, last)
        conf = _confidence_bundle(ys, period_value, steps, clamp_rate=False)
        value = conf["predicted_clamped"]
        # CI ölçeği dönem toplamına
        ci = conf["confidence_interval"]
    elif kind == "rate":
        monthly_equiv = round(min(100.0, max(0.0, predicted)), 2)
        period_value = monthly_equiv
        change_pct = _pct_change(monthly_equiv, last)
        conf = _confidence_bundle(ys, monthly_equiv, steps, clamp_rate=True)
        value = conf["predicted_clamped"]
        ci = conf["confidence_interval"]
    else:
        # kategori: predicted = change_pct of top growing category volume
        monthly_equiv = round(predicted, 2)
        period_value = monthly_equiv
        if extra is not None and "change_pct" in extra:
            change_pct = float(extra["change_pct"])
        else:
            change_pct = _pct_change(monthly_equiv, last)
        conf = _confidence_bundle(ys, monthly_equiv, steps, clamp_rate=False)
        value = round(change_pct, 1)
        # CI around change %
        spread = max(5.0, abs(change_pct) * (1.0 - conf["r_squared"]))
        ci = {
            "low": round(change_pct - spread, 1),
            "high": round(change_pct + spread, 1),
            "level_pct": conf["confidence_pct"],
        }

    trend = _trend_label(change_pct)
    risk = _risk_for_metric(metric_key, change_pct, conf["confidence_pct"], value)

    out = {
        "metric": metric_key,
        "label": meta["label"],
        "unit": meta["unit"],
        "horizon_days": days,
        "horizon_label": HORIZON_LABELS.get(days, f"{days} gün"),
        "predicted": value,
        "monthly_equivalent": monthly_equiv if kind != "category" else round(float((extra or {}).get("monthly_volume") or 0), 2),
        "baseline_last_month": round(last, 2),
        "change_pct": change_pct,
        "confidence_pct": conf["confidence_pct"],
        "confidence_interval": ci,
        "trend": trend,
        "risk": risk,
        "ai_yorum": "",
        "history": ys,
    }
    if extra:
        out.update(extra)
    return out


def _forecast_volume_or_rate(series: list[dict], field: str, metric_key: str, days: int) -> dict:
    ys = [float(s.get(field) or 0) for s in series]
    steps = _horizon_steps(days)
    predicted = _predict_next_value(ys, steps_ahead=steps)
    return _enrich_prediction(
        metric_key=metric_key,
        days=days,
        predicted=predicted,
        ys=ys,
        steps=steps,
    )


def _forecast_category_growth(series: list[dict], days: int) -> dict:
    """En hızlı büyüyen kategorinin artış tahmini."""
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
            "predicted_volume": round(pred, 2),
            "change_pct": _pct_change(pred, last),
            "baseline_last_month": round(last, 2),
            "ys": ys,
        })
    scored.sort(key=lambda x: -x["change_pct"])
    top = scored[0] if scored else {
        "kategori": "Diğer",
        "predicted_volume": 0.0,
        "change_pct": 0.0,
        "baseline_last_month": 0.0,
        "ys": [0.0],
    }

    # Yoğunluk sıralaması (geriye uyum)
    by_vol = sorted(scored, key=lambda x: -x["predicted_volume"])
    ranking = [
        {
            "kategori": r["kategori"],
            "predicted": r["predicted_volume"],
            "change_pct": r["change_pct"],
            "baseline_last_month": r["baseline_last_month"],
        }
        for r in by_vol[:7]
    ]

    return _enrich_prediction(
        metric_key="kategori_artisi",
        days=days,
        predicted=top["predicted_volume"],
        ys=top["ys"],
        steps=steps,
        extra={
            "kategori": top["kategori"],
            "en_yogun_kategori": by_vol[0]["kategori"] if by_vol else top["kategori"],
            "change_pct": top["change_pct"],
            "monthly_volume": top["predicted_volume"],
            "ranking": ranking,
        },
    )


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
        block = {
            "atik_miktari": _forecast_volume_or_rate(series, "atik_kg", "atik_miktari", days),
            "kategori_artisi": _forecast_category_growth(series, days),
            "teslim_orani": _forecast_volume_or_rate(series, "teslim_orani", "teslim_orani", days),
            "katilim": _forecast_volume_or_rate(series, "katilim", "katilim", days),
            "co2": _forecast_volume_or_rate(series, "co2_kg", "co2", days),
            # Geriye uyumluluk
            "kaynak_paylasimi": _forecast_volume_or_rate(
                series, "kaynak_adet", "kaynak_paylasimi", days
            ),
            "en_yogun_kategori": None,
        }
        # en_yogun_kategori alias
        ka = block["kategori_artisi"]
        block["en_yogun_kategori"] = {
            "horizon_days": days,
            "en_yogun_kategori": ka.get("en_yogun_kategori") or ka.get("kategori"),
            "predicted": ka.get("monthly_equivalent") or ka.get("monthly_volume") or 0,
            "change_pct": ka.get("change_pct") or 0,
            "ranking": ka.get("ranking") or [],
            "confidence_pct": ka.get("confidence_pct"),
            "confidence_interval": ka.get("confidence_interval"),
            "trend": ka.get("trend"),
            "risk": ka.get("risk"),
            "ai_yorum": "",
        }
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
            str(d): forecasts[str(d)]["co2"]["predicted"]
            for d in FORECAST_HORIZONS_DAYS
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
        "horizon_labels": dict(HORIZON_LABELS),
        "metrics": list(METRIC_KEYS),
        "lookback_options": list(LOOKBACK_MONTHS),
    }
