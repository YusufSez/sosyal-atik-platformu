"""Ulusal Karar Destek Merkezi — ülke geneli analitik paketleri.

Mevcut ministry API sözleşmesini değiştirmez; yeni dashboard/PDF için veri üretir.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func

from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.ministry_analytics import (
    ministry_kpi,
    municipality_performance_rows,
    province_statistics,
)
from services.municipality_analytics import normalize_municipality_category
from utils import utc_now


def _period_bounds(period: str, *, now=None):
    now = now or utc_now()
    period = (period or "weekly").lower()
    if period in ("monthly", "aylik", "aylık", "30"):
        days = 30
        label = "Aylık"
        key = "monthly"
    else:
        days = 7
        label = "Haftalık"
        key = "weekly"
    start = now - timedelta(days=days)
    prev_start = start - timedelta(days=days)
    return {
        "key": key,
        "label": label,
        "days": days,
        "start": start,
        "end": now,
        "prev_start": prev_start,
        "prev_end": start,
    }


def _count_listings(model, *, since=None, until=None) -> int:
    q = model.query
    if since is not None:
        q = q.filter(model.tarih >= since)
    if until is not None:
        q = q.filter(model.tarih < until)
    return q.count()


def _count_teslim(model, *, since=None, until=None) -> int:
    q = model.query.filter(model.ilan_durumu == "Teslim Edildi")
    if since is not None:
        q = q.filter(model.tarih >= since)
    if until is not None:
        q = q.filter(model.tarih < until)
    return q.count()


def _impact_between(since, until) -> dict:
    q = db.session.query(
        func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
        func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
        func.coalesce(func.sum(CevreselEtki.su_litre), 0),
        func.count(CevreselEtki.id),
    ).filter(CevreselEtki.timestamp >= since, CevreselEtki.timestamp < until)
    atik, co2, su, adet = q.one()
    return {
        "atik_kg": float(atik or 0),
        "co2e_kg": float(co2 or 0),
        "su_litre": float(su or 0),
        "adet": int(adet or 0),
    }


def _active_users(since, until) -> int:
    users = set()
    for model in (Kaynak, Atik):
        q = db.session.query(model.user_id).filter(
            model.tarih >= since, model.tarih < until
        ).distinct()
        users.update(uid for (uid,) in q.all() if uid)
    return len(users)


def _pct(cur: float, prev: float) -> float:
    if prev == 0:
        return 100.0 if cur > 0 else 0.0
    return round(((cur - prev) / prev) * 100.0, 1)


def period_snapshot(period: str = "weekly", *, now=None) -> dict:
    """Haftalık / aylık özet + önceki dönem karşılaştırması."""
    bounds = _period_bounds(period, now=now)
    start, end = bounds["start"], bounds["end"]
    ps, pe = bounds["prev_start"], bounds["prev_end"]

    cur_ilan = _count_listings(Kaynak, since=start, until=end) + _count_listings(
        Atik, since=start, until=end
    )
    prev_ilan = _count_listings(Kaynak, since=ps, until=pe) + _count_listings(
        Atik, since=ps, until=pe
    )
    cur_teslim = _count_teslim(Kaynak, since=start, until=end) + _count_teslim(
        Atik, since=start, until=end
    )
    prev_teslim = _count_teslim(Kaynak, since=ps, until=pe) + _count_teslim(
        Atik, since=ps, until=pe
    )
    cur_impact = _impact_between(start, end)
    prev_impact = _impact_between(ps, pe)
    cur_users = _active_users(start, end)
    prev_users = _active_users(ps, pe)

    return {
        "period": bounds["key"],
        "label": bounds["label"],
        "days": bounds["days"],
        "start": start.isoformat(),
        "end": end.isoformat(),
        "metrics": {
            "ilan": cur_ilan,
            "teslim": cur_teslim,
            "aktif_kullanici": cur_users,
            **cur_impact,
        },
        "previous": {
            "ilan": prev_ilan,
            "teslim": prev_teslim,
            "aktif_kullanici": prev_users,
            **prev_impact,
        },
        "change_pct": {
            "ilan": _pct(cur_ilan, prev_ilan),
            "teslim": _pct(cur_teslim, prev_teslim),
            "aktif_kullanici": _pct(cur_users, prev_users),
            "co2e_kg": _pct(cur_impact["co2e_kg"], prev_impact["co2e_kg"]),
            "atik_kg": _pct(cur_impact["atik_kg"], prev_impact["atik_kg"]),
        },
    }


def category_shifts(*, days: int = 30, now=None) -> dict:
    """Kategori değişimleri: son dönem vs önceki dönem."""
    now = now or utc_now()
    cur_start = now - timedelta(days=days)
    prev_start = cur_start - timedelta(days=days)

    def _counts(since, until):
        tallies = defaultdict(int)
        for model in (Kaynak, Atik):
            for row in model.query.filter(model.tarih >= since, model.tarih < until).all():
                tallies[normalize_municipality_category(row.kategori)] += 1
        return dict(tallies)

    cur = _counts(cur_start, now)
    prev = _counts(prev_start, cur_start)
    cats = sorted(set(cur) | set(prev))
    shifts = []
    for cat in cats:
        c = cur.get(cat, 0)
        p = prev.get(cat, 0)
        shifts.append({
            "kategori": cat,
            "current": c,
            "previous": p,
            "delta": c - p,
            "change_pct": _pct(c, p),
        })
    shifts.sort(key=lambda x: -abs(x["delta"]))
    rising = [s for s in shifts if s["delta"] > 0][:5]
    falling = [s for s in shifts if s["delta"] < 0][:5]
    return {
        "days": days,
        "all": shifts,
        "rising": rising,
        "falling": falling,
        "chart": {
            "labels": [s["kategori"] for s in shifts[:8]],
            "current": [s["current"] for s in shifts[:8]],
            "previous": [s["previous"] for s in shifts[:8]],
        },
    }


def participation_trends(*, weeks: int = 8, now=None) -> dict:
    """Vatandaş katılım eğilimleri — haftalık aktif kullanıcı."""
    now = now or utc_now()
    weeks = max(4, min(16, int(weeks or 8)))
    series = []
    for i in range(weeks - 1, -1, -1):
        end = now - timedelta(days=7 * i)
        start = end - timedelta(days=7)
        active = _active_users(start, end)
        ilan = _count_listings(Kaynak, since=start, until=end) + _count_listings(
            Atik, since=start, until=end
        )
        series.append({
            "label": start.strftime("%d.%m"),
            "start": start.isoformat(),
            "aktif_kullanici": active,
            "ilan": ilan,
        })
    change = None
    if len(series) >= 2 and series[0]["aktif_kullanici"] >= 0:
        change = _pct(series[-1]["aktif_kullanici"], series[0]["aktif_kullanici"])
    return {
        "weeks": weeks,
        "series": series,
        "labels": [s["label"] for s in series],
        "aktif": [s["aktif_kullanici"] for s in series],
        "ilanlar": [s["ilan"] for s in series],
        "change_pct": change,
        "trend": (
            "yukselis" if (change or 0) >= 8
            else ("dusus" if (change or 0) <= -8 else "stabil")
        ),
    }


def risk_analysis() -> dict:
    """Ulusal risk analizi — belediye performans + kategori baskısı."""
    board = municipality_performance_rows()
    risky = [r for r in board if r.get("renk") == "kirmizi"]
    medium = [r for r in board if r.get("renk") == "sari"]
    shifts = category_shifts(days=30)
    falling_cats = shifts["falling"][:3]
    part = participation_trends(weeks=6)
    risk_level = "dusuk"
    if len(risky) >= 3 or (part.get("change_pct") or 0) <= -20:
        risk_level = "yuksek"
    elif len(risky) >= 1 or len(medium) >= 3 or (part.get("change_pct") or 0) <= -8:
        risk_level = "orta"

    findings = []
    if risky:
        findings.append(
            f"{len(risky)} belediye yüksek risk bandında "
            f"(ör. {risky[0].get('ad') or risky[0].get('il')})."
        )
    if falling_cats:
        findings.append(
            f"Kategori düşüşü: {falling_cats[0]['kategori']} "
            f"(%{falling_cats[0]['change_pct']})."
        )
    if (part.get("change_pct") or 0) < 0:
        findings.append(
            f"Vatandaş katılımı son haftalarda %{abs(part['change_pct']):.0f} geriledi."
        )
    if not findings:
        findings.append("Ulusal göstergelerde kritik risk sinyali saptanmadı.")

    return {
        "level": risk_level,
        "riskli_belediye_sayisi": len(risky),
        "orta_risk_sayisi": len(medium),
        "riskli_belediyeler": [
            {
                "belediye_adi": r.get("ad"),
                "il": r.get("il"),
                "ilce": r.get("ilce"),
                "puan": r.get("puan"),
                "renk": r.get("renk"),
            }
            for r in risky[:10]
        ],
        "falling_categories": falling_cats,
        "participation_change_pct": part.get("change_pct"),
        "findings": findings,
    }


def municipality_comparisons(*, limit: int = 8) -> dict:
    board = municipality_performance_rows()
    top = [
        {
            "belediye_adi": r.get("ad"),
            "il": r.get("il"),
            "ilce": r.get("ilce"),
            "puan": r.get("puan"),
            "gelisim_yuzde": r.get("gelisim_yuzde"),
            "renk": r.get("renk"),
        }
        for r in board[:limit]
    ]
    raw_bottom = list(reversed(board[-limit:])) if len(board) > limit else list(reversed(board))
    bottom = [
        {
            "belediye_adi": r.get("ad"),
            "il": r.get("il"),
            "ilce": r.get("ilce"),
            "puan": r.get("puan"),
            "gelisim_yuzde": r.get("gelisim_yuzde"),
            "renk": r.get("renk"),
        }
        for r in raw_bottom
    ]
    provinces = province_statistics()
    provinces_sorted = sorted(provinces, key=lambda p: -float(p.get("puan") or 0))
    return {
        "top": top,
        "bottom": bottom,
        "provinces_top": provinces_sorted[:8],
        "provinces_bottom": list(reversed(provinces_sorted[-5:])) if provinces_sorted else [],
        "chart": {
            "labels": [r.get("belediye_adi") or r.get("il") for r in top[:6]],
            "puanlar": [r.get("puan") for r in top[:6]],
        },
    }


def campaign_suggestions(risk: dict, shifts: dict, participation: dict) -> list[dict]:
    """Yeni kampanya önerileri (kural tabanlı iskelet; AI zenginleştirir)."""
    tips = []
    rising = (shifts.get("rising") or [])[:1]
    falling = (shifts.get("falling") or [])[:1]
    if rising:
        tips.append({
            "title": f"{rising[0]['kategori']} Yoğunluk Kampanyası",
            "description": (
                f"{rising[0]['kategori']} kategorisinde artış gözleniyor "
                f"(%{rising[0]['change_pct']}). Toplama günleri ve farkındalık "
                "etkinlikleri önerilir."
            ),
            "priority": "Yüksek",
            "horizon": "Kısa",
        })
    if falling:
        tips.append({
            "title": f"{falling[0]['kategori']} Canlandırma Programı",
            "description": (
                f"{falling[0]['kategori']} payında düşüş var. Mahalle bazlı "
                "bilgilendirme ve teşvik kampanyası planlanabilir."
            ),
            "priority": "Orta",
            "horizon": "Orta",
        })
    if (participation.get("change_pct") or 0) < 0:
        tips.append({
            "title": "Vatandaş Katılımı Canlandırma",
            "description": (
                "Katılım eğilimi geriliyor. Rozet/puan tanıtımı, okul ziyaretleri "
                "ve yerel basın duyuruları önerilir."
            ),
            "priority": "Yüksek",
            "horizon": "Kısa",
        })
    if risk.get("level") in ("orta", "yuksek"):
        tips.append({
            "title": "Riskli Belediye Destek Paketi",
            "description": (
                f"{risk.get('riskli_belediye_sayisi', 0)} yüksek riskli belediye "
                "için operasyonel destek ve ortak toplama takvimi önerilir."
            ),
            "priority": "Kritik" if risk.get("level") == "yuksek" else "Yüksek",
            "horizon": "Kısa",
        })
    if len(tips) < 3:
        tips.append({
            "title": "Ulusal Sıfır Atık Haftası",
            "description": (
                "Tüm illerde eşzamanlı bilinçlendirme ve kurumsal kaynak paylaşımı "
                "günleri düzenlenebilir."
            ),
            "priority": "Orta",
            "horizon": "Orta",
        })
    return tips[:5]


def ministry_action_items(risk: dict, comparisons: dict, weekly: dict, monthly: dict) -> list[dict]:
    actions = []
    if risk.get("level") == "yuksek":
        actions.append({
            "title": "Acil risk izleme masası kurun",
            "detail": "Yüksek riskli belediyeler için haftalık durum brifingi alın.",
            "priority": "Kritik",
        })
    bottom = comparisons.get("bottom") or []
    if bottom:
        actions.append({
            "title": f"{bottom[0].get('belediye_adi') or bottom[0].get('il')} için iyileştirme planı",
            "detail": "Düşük performanslı birimlerle hedef odaklı eylem planı paylaşın.",
            "priority": "Yüksek",
        })
    if (weekly.get("change_pct") or {}).get("teslim", 0) < 0:
        actions.append({
            "title": "Teslim lojistiğini güçlendirin",
            "detail": "Haftalık teslim düşüşüne karşı mobil toplama kapasitesini artırın.",
            "priority": "Yüksek",
        })
    if (monthly.get("change_pct") or {}).get("co2e_kg", 0) < 0:
        actions.append({
            "title": "Karbon etkisi görünürlüğünü artırın",
            "detail": "Teslim sonrası etki kaydı ve vatandaş bilgilendirmesini yaygınlaştırın.",
            "priority": "Orta",
        })
    actions.append({
        "title": "İller arası iyi uygulama paylaşımı",
        "detail": "Üst sıralardaki belediyelerin modellerini ulusal bültende yayınlayın.",
        "priority": "Orta",
    })
    return actions[:6]


def build_decision_support_center(*, now=None) -> dict:
    """Ulusal Karar Destek Merkezi dashboard paketi."""
    from services.demo_manager import should_use_demo
    from services import demo_provider

    now = now or utc_now()
    kpi = ministry_kpi()
    kpi_ok = bool((kpi or {}).get("toplam_ilan") or (kpi or {}).get("etki_adet"))
    if should_use_demo("dashboard", real_data_sufficient=kpi_ok):
        return demo_provider.decision_support_center()

    weekly = period_snapshot("weekly", now=now)
    monthly = period_snapshot("monthly", now=now)
    shifts = category_shifts(days=30, now=now)
    participation = participation_trends(weeks=8, now=now)
    risk = risk_analysis()
    comparisons = municipality_comparisons()
    campaigns = campaign_suggestions(risk, shifts, participation)
    actions = ministry_action_items(risk, comparisons, weekly, monthly)

    return {
        "generated_at": now.isoformat(),
        "kpi": kpi,
        "weekly_report": weekly,
        "monthly_report": monthly,
        "risk_analysis": risk,
        "campaigns": campaigns,
        "municipality_comparisons": comparisons,
        "category_shifts": shifts,
        "participation_trends": participation,
        "ministry_actions": actions,
        "reports": {
            "weekly": {"title": "Haftalık Rapor", "key": "weekly"},
            "monthly": {"title": "Aylık Rapor", "key": "monthly"},
            "full": {"title": "Tam Karar Destek Raporu", "key": "full"},
        },
    }
