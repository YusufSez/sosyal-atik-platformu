"""Sustainability Scoring Engine — belediye 100 puan + harf notu."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func

from constants import (
    ROLE_MUNICIPALITY,
    SUSTAINABILITY_CO2_BENCHMARK_KG,
    SUSTAINABILITY_CRITERION_LABELS,
    SUSTAINABILITY_DELIVERY_IDEAL_DAYS,
    SUSTAINABILITY_DELIVERY_MAX_DAYS,
    SUSTAINABILITY_GRADES,
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
    return "D"


def _clamp(value: float, lo: float = 0.0, hi: float = 100.0) -> float:
    return round(min(hi, max(lo, value)), 1)


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


def _participation_rate(geo) -> float:
    user_q = User.query
    if geo:
        user_q = user_q.filter(*geo)
    total = user_q.filter(
        User.role.notin_(("admin", "superadmin", "ministry")),
        User.is_deactivated.is_(False),
    ).count()
    if total <= 0:
        return 0.0

    participating = set()
    for model in (Kaynak, Atik):
        q = db.session.query(model.user_id).distinct()
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        participating.update(uid for (uid,) in q.all() if uid)
    return 100.0 * len(participating) / total


def _ai_accuracy_score(geo) -> float:
    """AI risk ile moderasyon durumu uyumu (0–100). Veri yoksa nötr 50."""
    scores = []
    for model in (Kaynak, Atik):
        q = model.query.filter(model.ai_risk_score.isnot(None))
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        for row in q.all():
            risk = int(row.ai_risk_score or 0)
            status = (row.moderation_status or "").lower()
            if status in ("approved", "whitelisted"):
                # Düşük risk + onay = yüksek doğruluk
                scores.append(max(0, 100 - risk))
            elif status in ("rejected", "removed", "blocked", "pending_review"):
                # Yüksek risk + engel = yüksek doğruluk
                scores.append(min(100, risk))
            else:
                scores.append(max(0, 100 - abs(50 - risk)))
    if not scores:
        return 50.0
    return _clamp(sum(scores) / len(scores))


def _delivery_time_score(avg_days: float | None) -> float:
    if avg_days is None:
        return 50.0  # veri yok — nötr
    ideal = SUSTAINABILITY_DELIVERY_IDEAL_DAYS
    worst = SUSTAINABILITY_DELIVERY_MAX_DAYS
    if avg_days <= ideal:
        return 100.0
    if avg_days >= worst:
        return 0.0
    return _clamp(100.0 * (1.0 - (avg_days - ideal) / (worst - ideal)))


def _category_shares(geo) -> dict[str, float]:
    """Atık kategorilerinin teslim payları (AI önerileri için)."""
    counts = defaultdict(int)
    q = _teslim_query(Atik, geo)
    for row in q.all():
        counts[normalize_municipality_category(row.kategori)] += 1
    total = sum(counts.values()) or 1
    return {k: round(100.0 * v / total, 1) for k, v in counts.items()}


def score_region(il: str | None = None, ilce: str | None = None, mahalle: str | None = None) -> dict:
    """Belirli coğrafya için 7 kriterli sürdürülebilirlik skoru."""
    geo = _geo_filters(il, ilce, mahalle)
    counts = _listing_counts(geo)
    impact = _impact_totals(geo)
    avg_days = _ortalama_teslim_suresi_gun(geo)

    total = counts["total"]
    atik_total = counts["atik_total"] or 0
    kaynak_total = counts["kaynak_total"] or 0

    geri_donusum = (
        100.0 * counts["atik_teslim"] / atik_total if atik_total else 0.0
    )
    teslim = 100.0 * counts["teslim"] / total if total else 0.0
    katilim = _participation_rate(geo)
    kaynak_paylasimi = (
        100.0 * counts["kaynak_teslim"] / kaynak_total if kaynak_total else 0.0
    )
    karbon = _clamp(100.0 * impact["co2e_kg"] / SUSTAINABILITY_CO2_BENCHMARK_KG)
    teslim_suresi = _delivery_time_score(avg_days)
    ai_dogruluk = _ai_accuracy_score(geo)

    raw = {
        "geri_donusum": _clamp(geri_donusum),
        "teslim": _clamp(teslim),
        "katilim": _clamp(katilim),
        "kaynak_paylasimi": _clamp(kaynak_paylasimi),
        "karbon": karbon,
        "teslim_suresi": teslim_suresi,
        "ai_dogruluk": ai_dogruluk,
    }

    criteria = []
    weighted_sum = 0.0
    for key, weight in SUSTAINABILITY_WEIGHTS.items():
        part = raw[key] * weight / 100.0
        weighted_sum += part
        criteria.append({
            "key": key,
            "label": SUSTAINABILITY_CRITERION_LABELS[key],
            "score": raw[key],
            "weight": weight,
            "weighted": round(part, 2),
        })

    puan = _clamp(weighted_sum)
    return {
        "il": _norm(il),
        "ilce": _norm(ilce),
        "mahalle": _norm(mahalle),
        "puan": puan,
        "grade": grade_for_score(puan),
        "criteria": criteria,
        "raw": raw,
        "metrics": {
            **counts,
            **impact,
            "ortalama_teslim_gun": avg_days,
            "katilim_orani": round(katilim, 1),
            "kategori_paylari": _category_shares(geo),
        },
    }


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

    # Belediyesi olmayan iller: doğrudan il skoru
    if not by_il:
        # Fallback: tüm User.il değerleri üzerinden region score
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


def sustainability_dashboard(
    *,
    il: str | None = None,
    ilce: str | None = None,
    belediye_user: User | None = None,
) -> dict:
    """Dashboard paketi: skor + lider tablosu + Türkiye/il sıralaması."""
    if belediye_user and getattr(belediye_user, "role", None) == ROLE_MUNICIPALITY:
        current = score_municipality(belediye_user)
        focus_il = belediye_user.il
    else:
        current = score_region(il=il, ilce=ilce)
        current["scope"] = "bolge"
        focus_il = il or current.get("il")

    leaders = turkey_ranking(limit=20)
    provinces = province_ranking()
    il_board = municipality_leaderboard(il=focus_il) if focus_il else []

    my_rank = None
    if current.get("belediye_id"):
        for row in leaders:
            if row.get("belediye_id") == current["belediye_id"]:
                my_rank = row["sira"]
                break

    return {
        "current": current,
        "my_rank": my_rank,
        "leaderboard": leaders,
        "turkey_ranking": leaders,
        "province_ranking": provinces,
        "il_ranking": il_board,
        "focus_il": focus_il,
    }
