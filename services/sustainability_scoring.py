"""Sustainability Scoring Engine — belediye 100 puan + harf notu."""

from __future__ import annotations

import math
from collections import defaultdict

from sqlalchemy import func

from constants import (
    ROLE_MUNICIPALITY,
    SUSTAINABILITY_CO2_BENCHMARK_KG,
    SUSTAINABILITY_CRITERION_LABELS,
    SUSTAINABILITY_DELIVERY_IDEAL_DAYS,
    SUSTAINABILITY_DELIVERY_MAX_DAYS,
    SUSTAINABILITY_GRADES,
    SUSTAINABILITY_MISSING_NEUTRAL,
    SUSTAINABILITY_WEIGHTS,
)
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.municipality_analytics import (
    _geo_filters,
    _norm,
    _ortalama_teslim_suresi_gun,
    _teslim_query,
    normalize_municipality_category,
)


def grade_for_score(puan: float) -> str:
    puan = float(puan or 0)
    for threshold, letter in SUSTAINABILITY_GRADES:
        if puan >= threshold:
            return letter
    return "F"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(min(hi, max(lo, float(value))), 1)


def _rate_score(numerator: float, denominator: float, *, missing: float = SUSTAINABILITY_MISSING_NEUTRAL) -> tuple[float, bool]:
    """0–100 oran skoru. Payda 0 ise nötr skor + missing=True (sıfır cezası yok)."""
    if denominator is None or denominator <= 0:
        return _clamp(missing), True
    return _clamp(100.0 * float(numerator) / float(denominator)), False


def _listing_counts(geo) -> dict:
    kaynak_total = Kaynak.query
    atik_total = Atik.query
    if geo:
        kaynak_total = kaynak_total.join(User, Kaynak.user_id == User.id).filter(*geo)
        atik_total = atik_total.join(User, Atik.user_id == User.id).filter(*geo)
    kaynak_n = kaynak_total.count()
    atik_n = atik_total.count()
    kaynak_teslim = _teslim_query(Kaynak, geo).count()
    atik_teslim = _teslim_query(Atik, geo).count()
    return {
        "kaynak_total": kaynak_n,
        "atik_total": atik_n,
        "total": kaynak_n + atik_n,
        "kaynak_teslim": kaynak_teslim,
        "atik_teslim": atik_teslim,
        "teslim": kaynak_teslim + atik_teslim,
    }


def _impact_totals(geo) -> dict:
    q = db.session.query(
        func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
        func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
        func.count(CevreselEtki.id),
    )
    if geo:
        q = q.join(User, CevreselEtki.user_id == User.id).filter(*geo)
    atik_kg, co2e_kg, adet = q.one()
    return {
        "atik_kg": float(atik_kg or 0),
        "co2e_kg": float(co2e_kg or 0),
        "etki_adet": int(adet or 0),
    }


def _participation_rate(geo) -> tuple[float, bool]:
    user_q = User.query
    if geo:
        user_q = user_q.filter(*geo)
    total = user_q.filter(
        User.role.notin_(("admin", "superadmin", "ministry")),
        User.is_deactivated.is_(False),
    ).count()
    if total <= 0:
        return SUSTAINABILITY_MISSING_NEUTRAL, True

    participating = set()
    for model in (Kaynak, Atik):
        q = db.session.query(model.user_id).distinct()
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        participating.update(uid for (uid,) in q.all() if uid)
    return _clamp(100.0 * len(participating) / total), False


def _ai_accuracy_score(geo) -> tuple[float, bool]:
    """AI risk ile moderasyon durumu uyumu (0–100). Veri yoksa nötr."""
    scores = []
    for model in (Kaynak, Atik):
        q = model.query.filter(model.ai_risk_score.isnot(None))
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        for row in q.all():
            risk = int(row.ai_risk_score or 0)
            status = (row.moderation_status or "").lower()
            if status in ("approved", "whitelisted"):
                scores.append(max(0, 100 - risk))
            elif status in ("rejected", "removed", "blocked", "pending_review"):
                scores.append(min(100, risk))
            else:
                scores.append(max(0, 100 - abs(50 - risk)))
    if not scores:
        return SUSTAINABILITY_MISSING_NEUTRAL, True
    return _clamp(sum(scores) / len(scores)), False


def _delivery_time_score(avg_days: float | None) -> tuple[float, bool]:
    if avg_days is None:
        return SUSTAINABILITY_MISSING_NEUTRAL, True
    ideal = SUSTAINABILITY_DELIVERY_IDEAL_DAYS
    worst = SUSTAINABILITY_DELIVERY_MAX_DAYS
    if avg_days <= ideal:
        return 100.0, False
    if avg_days >= worst:
        return 0.0, False
    return _clamp(100.0 * (1.0 - (avg_days - ideal) / (worst - ideal))), False


def _carbon_score(co2e_kg: float, *, has_activity: bool) -> tuple[float, bool]:
    """
    CO₂e tasarrufu log ölçeğinde 0–100.
    Küçük hacimli bölgeler lineer 50 kg eşiğinde ezilmesin.
    Faaliyet yoksa nötr; faaliyet var ama 0 tasarruf → düşük puan.
    """
    if not has_activity:
        return SUSTAINABILITY_MISSING_NEUTRAL, True
    if co2e_kg <= 0:
        return 0.0, False
    denom = math.log1p(SUSTAINABILITY_CO2_BENCHMARK_KG)
    if denom <= 0:
        return SUSTAINABILITY_MISSING_NEUTRAL, True
    return _clamp(100.0 * math.log1p(co2e_kg) / denom), False


def _category_shares(geo) -> dict[str, float]:
    """Tüm atık ilanlarının kategori payları (teslim + aktif)."""
    counts = defaultdict(int)
    q = Atik.query
    if geo:
        q = q.join(User, Atik.user_id == User.id).filter(*geo)
    for row in q.all():
        counts[normalize_municipality_category(row.kategori)] += 1
    total = sum(counts.values())
    if total <= 0:
        return {}
    return {k: round(100.0 * v / total, 1) for k, v in counts.items()}


def score_region(il: str | None = None, ilce: str | None = None, mahalle: str | None = None) -> dict:
    """Belirli coğrafya için 7 kriterli sürdürülebilirlik skoru (ağırlıklı 0–100)."""
    geo = _geo_filters(il, ilce, mahalle)
    counts = _listing_counts(geo)
    impact = _impact_totals(geo)
    avg_days = _ortalama_teslim_suresi_gun(geo)

    total = counts["total"]
    atik_total = counts["atik_total"]
    kaynak_total = counts["kaynak_total"]

    geri_donusum, miss_gd = _rate_score(counts["atik_teslim"], atik_total)
    teslim, miss_teslim = _rate_score(counts["teslim"], total)
    katilim, miss_katilim = _participation_rate(geo)
    kaynak_paylasimi, miss_kp = _rate_score(counts["kaynak_teslim"], kaynak_total)
    karbon, miss_karbon = _carbon_score(
        impact["co2e_kg"], has_activity=bool(counts["teslim"] or impact["etki_adet"])
    )
    teslim_suresi, miss_sure = _delivery_time_score(avg_days)
    ai_dogruluk, miss_ai = _ai_accuracy_score(geo)

    raw = {
        "geri_donusum": geri_donusum,
        "teslim": teslim,
        "katilim": katilim,
        "kaynak_paylasimi": kaynak_paylasimi,
        "karbon": karbon,
        "teslim_suresi": teslim_suresi,
        "ai_dogruluk": ai_dogruluk,
    }
    missing = {
        "geri_donusum": miss_gd,
        "teslim": miss_teslim,
        "katilim": miss_katilim,
        "kaynak_paylasimi": miss_kp,
        "karbon": miss_karbon,
        "teslim_suresi": miss_sure,
        "ai_dogruluk": miss_ai,
    }

    # Ağırlıklar SUSTAINABILITY_WEIGHTS toplamı 100 olacak şekilde uygulanır
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
            "missing_data": missing[key],
        })

    puan = _clamp(weighted_sum)
    result = {
        "il": _norm(il),
        "ilce": _norm(ilce),
        "mahalle": _norm(mahalle),
        "puan": puan,
        "grade": grade_for_score(puan),
        "criteria": criteria,
        "raw": raw,
        "missing": missing,
        "metrics": {
            **counts,
            **impact,
            "ortalama_teslim_gun": avg_days,
            "katilim_orani": round(katilim, 1),
            "kategori_paylari": _category_shares(geo),
            "teslim_orani": round(teslim, 1),
            "geri_donusum_orani": round(geri_donusum, 1),
        },
    }
    from services.demo_manager import is_sustainability_data_sufficient, should_use_demo
    from services import demo_provider

    if should_use_demo(
        "sustainability",
        real_data_sufficient=is_sustainability_data_sufficient(result),
    ):
        return demo_provider.sustainability_score(
            il=_norm(il), ilce=_norm(ilce), mahalle=_norm(mahalle)
        )
    return result


def score_municipality(user: User) -> dict:
    """Tek belediye kullanıcısı için skor (il/ilçe coğrafyası)."""
    result = score_region(il=user.il, ilce=user.ilce)
    result["belediye_id"] = user.id
    result["belediye_adi"] = user.display_name or user.username
    result["scope"] = "belediye"
    return result


def municipality_leaderboard(*, il: str | None = None, limit: int | None = None) -> list[dict]:
    """Türkiye / il belediye lider tablosu."""
    q = User.query.filter(User.role == ROLE_MUNICIPALITY)
    il = _norm(il)
    if il:
        q = q.filter(User.il == il)
    rows = []
    for user in q.all():
        if not user.il:
            continue
        scored = score_municipality(user)
        rows.append(scored)
    rows.sort(key=lambda r: (-r["puan"], r.get("belediye_adi") or ""))
    for idx, row in enumerate(rows, start=1):
        row["sira"] = idx
    if limit:
        return rows[:limit]
    return rows


def turkey_ranking(limit: int | None = None) -> list[dict]:
    return municipality_leaderboard(limit=limit)


def province_ranking(il: str | None = None) -> list[dict]:
    """İl bazlı ortalama sürdürülebilirlik sıralaması."""
    board = municipality_leaderboard(il=il)
    by_il: dict[str, list[float]] = defaultdict(list)
    for row in board:
        if row.get("il"):
            by_il[row["il"]].append(row["puan"])

    if not by_il:
        iller = [
            r[0]
            for r in db.session.query(User.il)
            .filter(User.il.isnot(None), User.il != "")
            .distinct()
            .all()
        ]
        if il:
            iller = [i for i in iller if i == il]
        rows = []
        for name in iller:
            scored = score_region(il=name)
            rows.append({
                "il": name,
                "puan": scored["puan"],
                "grade": scored["grade"],
                "belediye_sayisi": 0,
                "criteria": scored["criteria"],
            })
        rows.sort(key=lambda r: -r["puan"])
        for idx, row in enumerate(rows, start=1):
            row["sira"] = idx
        return rows

    rows = []
    for name, puanlar in by_il.items():
        avg = sum(puanlar) / len(puanlar)
        rows.append({
            "il": name,
            "puan": _clamp(avg),
            "grade": grade_for_score(avg),
            "belediye_sayisi": len(puanlar),
        })
    rows.sort(key=lambda r: -r["puan"])
    for idx, row in enumerate(rows, start=1):
        row["sira"] = idx
    return rows


def build_turkey_comparison(current_puan: float, board: list[dict] | None = None) -> dict:
    """Türkiye ortalaması ve benzer belediyelere göre kısa karşılaştırma."""
    board = board if board is not None else municipality_leaderboard()
    puanlar = [float(r.get("puan") or 0) for r in board]
    if not puanlar:
        return {
            "turkey_avg": None,
            "delta_pct": None,
            "percentile": None,
            "message": "Karşılaştırma için yeterli belediye verisi bulunamadı.",
        }

    avg = sum(puanlar) / len(puanlar)
    current = float(current_puan or 0)
    if avg > 0:
        delta_pct = round(((current - avg) / avg) * 100.0, 1)
    else:
        delta_pct = 0.0

    below_or_eq = sum(1 for p in puanlar if p <= current)
    percentile = round(100.0 * below_or_eq / len(puanlar), 1)

    if delta_pct >= 5:
        message = f"Türkiye ortalamasının %{abs(delta_pct):.0f} üzerindesiniz."
    elif delta_pct <= -5:
        message = (
            f"Türkiye ortalamasının %{abs(delta_pct):.0f} gerisindesiniz. "
            "Benzer belediyelerin gerisinde kalmamak için öncelikli aksiyonlar önerilir."
        )
    else:
        message = "Türkiye ortalamasına yakın bir sürdürülebilirlik performansındasınız."

    return {
        "turkey_avg": round(avg, 1),
        "delta_pct": delta_pct,
        "percentile": percentile,
        "peer_count": len(puanlar),
        "message": message,
    }


def radar_chart_data(scored: dict) -> dict:
    """Chart.js radar için etiket / değer paketleri."""
    criteria = scored.get("criteria") or []
    labels = [c.get("label") or c.get("key") for c in criteria]
    values = [float(c.get("score") or 0) for c in criteria]
    return {
        "labels": labels,
        "values": values,
        "keys": [c.get("key") for c in criteria],
    }


def category_scores(scored: dict) -> list[dict]:
    """Kategori (kriter) puanları — UI / PDF için sade liste."""
    return [
        {
            "key": c.get("key"),
            "label": c.get("label"),
            "score": c.get("score"),
            "weight": c.get("weight"),
            "weighted": c.get("weighted"),
            "missing_data": c.get("missing_data"),
        }
        for c in (scored.get("criteria") or [])
    ]


def _month_bounds(now, months_back: int) -> list[tuple[str, object, object]]:
    """Son N ay için (label, start, end) — end exclusive."""
    from calendar import monthrange
    from datetime import datetime

    from utils import utc_now

    now = now or utc_now()
    year, month = now.year, now.month
    windows = []
    for i in range(months_back - 1, -1, -1):
        m = month - i
        y = year
        while m <= 0:
            m += 12
            y -= 1
        start = datetime(y, m, 1)
        last = monthrange(y, m)[1]
        end = datetime(y, m, last, 23, 59, 59)
        windows.append((f"{y:04d}-{m:02d}", start, end))
    return windows


def _count_in_window(model, geo, start, end, *, teslim_only: bool = False) -> int:
    q = model.query.filter(model.tarih >= start, model.tarih <= end)
    if teslim_only:
        q = q.filter(model.ilan_durumu == "Teslim Edildi")
    if geo:
        q = q.join(User, model.user_id == User.id).filter(*geo)
    return q.count()


def score_history(
    il: str | None = None,
    ilce: str | None = None,
    mahalle: str | None = None,
    *,
    months: int = 6,
    now=None,
) -> dict:
    """
    Aylık geçmiş değişim (şema değiştirmeden).
    Her ay için o ayın aktivitesinden türetilmiş proxy puan.
    """
    months = max(3, min(12, int(months or 6)))
    geo = _geo_filters(il, ilce, mahalle)
    series = []
    for label, start, end in _month_bounds(now, months):
        kaynak_n = _count_in_window(Kaynak, geo, start, end)
        atik_n = _count_in_window(Atik, geo, start, end)
        kaynak_t = _count_in_window(Kaynak, geo, start, end, teslim_only=True)
        atik_t = _count_in_window(Atik, geo, start, end, teslim_only=True)
        total = kaynak_n + atik_n
        teslim = kaynak_t + atik_t

        etki_q = db.session.query(func.coalesce(func.sum(CevreselEtki.co2e_kg), 0)).filter(
            CevreselEtki.timestamp >= start,
            CevreselEtki.timestamp <= end,
        )
        if geo:
            etki_q = etki_q.join(User, CevreselEtki.user_id == User.id).filter(*geo)
        co2 = float(etki_q.scalar() or 0)

        teslim_score, _ = _rate_score(teslim, total)
        gd_score, _ = _rate_score(atik_t, atik_n)
        karbon_score, _ = _carbon_score(co2, has_activity=bool(teslim or co2 > 0))
        # Basit aylık bileşik: teslim %40 + geri dönüşüm %35 + karbon %25
        puan = _clamp(0.40 * teslim_score + 0.35 * gd_score + 0.25 * karbon_score)
        series.append({
            "ay": label,
            "puan": puan,
            "teslim_orani": teslim_score,
            "geri_donusum": gd_score,
            "karbon": karbon_score,
            "ilan": total,
            "teslim": teslim,
            "co2e_kg": round(co2, 2),
        })

    change = None
    if len(series) >= 2:
        first = series[0]["puan"]
        last = series[-1]["puan"]
        if first > 0:
            change = round(((last - first) / first) * 100.0, 1)
        else:
            change = 100.0 if last > 0 else 0.0

    return {
        "months": months,
        "series": series,
        "labels": [s["ay"] for s in series],
        "puanlar": [s["puan"] for s in series],
        "change_pct": change,
        "trend": (
            "yukselis" if (change or 0) >= 5
            else ("dusus" if (change or 0) <= -5 else "stabil")
        ),
    }


def similar_municipalities(
    current: dict,
    board: list[dict] | None = None,
    *,
    limit: int = 5,
    band: float = 12.0,
) -> list[dict]:
    """Benzer puan bandındaki belediyeler (aynı il öncelikli)."""
    board = board if board is not None else municipality_leaderboard()
    current_id = current.get("belediye_id")
    current_puan = float(current.get("puan") or 0)
    current_il = current.get("il")

    peers = []
    for row in board:
        if current_id and row.get("belediye_id") == current_id:
            continue
        delta = abs(float(row.get("puan") or 0) - current_puan)
        if delta > band:
            continue
        peers.append({
            "belediye_id": row.get("belediye_id"),
            "belediye_adi": row.get("belediye_adi"),
            "il": row.get("il"),
            "ilce": row.get("ilce"),
            "puan": row.get("puan"),
            "grade": row.get("grade"),
            "sira": row.get("sira"),
            "puan_farki": round(float(row.get("puan") or 0) - current_puan, 1),
            "ayni_il": bool(current_il and row.get("il") == current_il),
            "raw": row.get("raw"),
        })

    peers.sort(key=lambda p: (0 if p["ayni_il"] else 1, abs(p["puan_farki"]), p.get("sira") or 999))
    return peers[:limit]


def ranking_context(current: dict, full_board: list[dict], il_board: list[dict], provinces: list[dict]) -> dict:
    """Türkiye / il sıralama özeti."""
    turkey_sira = None
    turkey_total = len(full_board)
    if current.get("belediye_id"):
        for row in full_board:
            if row.get("belediye_id") == current["belediye_id"]:
                turkey_sira = row.get("sira")
                break
    elif current.get("il") and not current.get("ilce"):
        for row in provinces:
            if row.get("il") == current.get("il"):
                turkey_sira = row.get("sira")
                break

    il_sira = None
    il_total = len(il_board)
    if current.get("belediye_id"):
        for idx, row in enumerate(il_board, start=1):
            if row.get("belediye_id") == current["belediye_id"]:
                il_sira = idx
                break

    province_sira = None
    focus_il = current.get("il")
    if focus_il:
        for row in provinces:
            if row.get("il") == focus_il:
                province_sira = row.get("sira")
                break

    return {
        "turkey": {"sira": turkey_sira, "toplam": turkey_total},
        "il_belediye": {"sira": il_sira, "toplam": il_total, "il": focus_il},
        "il_ortalama": {"sira": province_sira, "toplam": len(provinces), "il": focus_il},
    }


def sustainability_dashboard(
    *,
    il: str | None = None,
    ilce: str | None = None,
    belediye_user: User | None = None,
) -> dict:
    """Dashboard paketi: skor + radar + geçmiş + sıralamalar + benzer belediyeler."""
    if belediye_user and getattr(belediye_user, "role", None) == ROLE_MUNICIPALITY:
        current = score_municipality(belediye_user)
        focus_il = belediye_user.il
    else:
        current = score_region(il=il, ilce=ilce)
        current["scope"] = "bolge"
        focus_il = il or current.get("il")

    full_board = municipality_leaderboard()
    leaders = full_board[:20]
    provinces = province_ranking()
    il_board = municipality_leaderboard(il=focus_il) if focus_il else []

    my_rank = None
    if current.get("belediye_id"):
        for row in full_board:
            if row.get("belediye_id") == current["belediye_id"]:
                my_rank = row["sira"]
                break

    comparison = build_turkey_comparison(current.get("puan") or 0, full_board)
    history = score_history(
        il=current.get("il") or il,
        ilce=current.get("ilce") or ilce,
        mahalle=current.get("mahalle"),
        months=6,
    )
    similar = similar_municipalities(current, full_board, limit=5)
    ranks = ranking_context(current, full_board, il_board, provinces)
    radar = radar_chart_data(current)
    cats = category_scores(current)

    return {
        "current": current,
        "my_rank": my_rank,
        "leaderboard": leaders,
        "turkey_ranking": leaders,
        "province_ranking": provinces,
        "il_ranking": il_board,
        "focus_il": focus_il,
        "comparison": comparison,
        # Yeni alanlar (mevcut endpoint sözleşmesine additive)
        "radar": radar,
        "category_scores": cats,
        "history": history,
        "similar_municipalities": similar,
        "rankings": ranks,
    }
