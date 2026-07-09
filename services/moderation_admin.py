"""Admin moderasyon paneli — liste, filtre, dashboard."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload

from constants import (
    AI_RISK_REVIEW_MIN,
    KATEGORILER_ATIK,
    KATEGORILER_KAYNAK,
    MODERATION_STATUS_APPROVED,
    MODERATION_STATUS_PENDING_REVIEW,
    MODERATION_STATUS_REJECTED,
)
from extensions import db
from models import Atik, IlanModerasyonAnaliz, IlanModerasyonNot, IlanModerasyonTimeline, Kaynak, User
from services.ai_health import ai_health_stats
from services.ilan_images import kapak_resim
from services.moderation_analysis import analiz_dict, analiz_gecmisi, guncel_analiz
from services.moderation_compare import latest_reanalyze_comparison
from services.moderation_decisions import ilan_karar_ozeti, karar_analitigi
from services.moderation_flow import build_moderation_flow
from services.moderation_priority import sort_moderation_items
from services.moderation_timeline import timeline_detay, timeline_listele
from utils import utc_now

MODERATION_LISTE_PER_PAGE = 50


@dataclass
class ModerasyonListeOgesi:
    tur: str
    ilan_id: int
    baslik: str
    aciklama_ozet: str
    kullanici: str
    kullanici_id: int
    tarih: datetime | None
    risk_skoru: int | None
    moderation_status: str
    category: str | None
    purpose: str | None
    confidence: float | None
    spam_score: int | None
    duplicate_score: int | None
    kapak: str
    kategori: str | None
    alt_kategori: str | None


@dataclass
class ModerasyonListeSonuc:
    items: list[ModerasyonListeOgesi]
    total: int
    page: int
    per_page: int
    pages: int


def _aciklama_ilk_satir(aciklama: str | None) -> str:
    if not aciklama:
        return ""
    return aciklama.strip().split("\n", 1)[0][:120]


def _bulk_guncel_analiz_map() -> dict[tuple[str, int], IlanModerasyonAnaliz]:
    """Tüm güncel analizleri tek sorguda yükler (N+1 önleme)."""
    analizler = IlanModerasyonAnaliz.query.filter_by(is_current=True).all()
    return {(a.tur, (a.kaynak_id or a.atik_id)): a for a in analizler if (a.kaynak_id or a.atik_id)}


def _ilan_to_liste_ogesi(
    tur: str,
    ilan,
    analiz: IlanModerasyonAnaliz | None,
) -> ModerasyonListeOgesi:
    sahip = getattr(ilan, "sahip", None)
    return ModerasyonListeOgesi(
        tur=tur,
        ilan_id=ilan.id,
        baslik=ilan.baslik,
        aciklama_ozet=_aciklama_ilk_satir(ilan.aciklama),
        kullanici=sahip.username if sahip else "?",
        kullanici_id=ilan.user_id,
        tarih=ilan.tarih,
        risk_skoru=analiz.final_risk if analiz else ilan.ai_risk_score,
        moderation_status=ilan.moderation_status,
        category=(analiz.category if analiz else None) or getattr(ilan, "kategori", None),
        purpose=analiz.purpose if analiz else None,
        confidence=analiz.confidence if analiz else None,
        spam_score=analiz.spam_score if analiz else None,
        duplicate_score=analiz.duplicate_score if analiz else None,
        kapak=kapak_resim(ilan),
        kategori=getattr(ilan, "kategori", None),
        alt_kategori=getattr(ilan, "durum", None) if tur == "kaynak" else None,
    )


def _filtre_uygula_ilan(query, model, filters: dict):
    status = filters.get("status")
    if status:
        query = query.filter(model.moderation_status == status)
    risk_min = filters.get("risk_min")
    if risk_min:
        query = query.filter(model.ai_risk_score >= int(risk_min))
    kategori = filters.get("kategori")
    if kategori:
        query = query.filter(model.kategori == kategori)
    username = filters.get("username")
    if username:
        query = query.join(User, model.user_id == User.id).filter(
            User.username.ilike(f"%{username}%")
        )
    date_from = filters.get("date_from")
    if date_from:
        query = query.filter(model.tarih >= date_from)
    date_to = filters.get("date_to")
    if date_to:
        query = query.filter(model.tarih <= date_to)
    q = filters.get("q")
    if q:
        query = query.filter(
            or_(model.baslik.ilike(f"%{q}%"), model.aciklama.ilike(f"%{q}%"))
        )
    return query


def _collect_filtered_items(filters: dict, analiz_map: dict) -> list[ModerasyonListeOgesi]:
    items: list[ModerasyonListeOgesi] = []
    tur_filtre = filters.get("tur")

    if tur_filtre in (None, "", "kaynak"):
        q = _filtre_uygula_ilan(
            Kaynak.query.options(joinedload(Kaynak.sahip)), Kaynak, filters
        )
        for ilan in q.order_by(Kaynak.id.desc()).limit(500).all():
            analiz = analiz_map.get(("kaynak", ilan.id))
            items.append(_ilan_to_liste_ogesi("kaynak", ilan, analiz))

    if tur_filtre in (None, "", "atik"):
        q = _filtre_uygula_ilan(
            Atik.query.options(joinedload(Atik.sahip)), Atik, filters
        )
        for ilan in q.order_by(Atik.id.desc()).limit(500).all():
            analiz = analiz_map.get(("atik", ilan.id))
            items.append(_ilan_to_liste_ogesi("atik", ilan, analiz))

    return sort_moderation_items(items)


def moderasyon_listesi(
    filters: dict | None = None,
    *,
    page: int | None = None,
    per_page: int = MODERATION_LISTE_PER_PAGE,
) -> ModerasyonListeSonuc | list[ModerasyonListeOgesi]:
    """
    Filtrelenmiş moderasyon listesi.
    page/per_page verilirse sayfalanmış sonuç; aksi halde geriye uyumlu liste.
    """
    filters = filters or {}
    analiz_map = _bulk_guncel_analiz_map()
    items = _collect_filtered_items(filters, analiz_map)
    total = len(items)

    if page is None:
        return items

    per_page = max(1, min(per_page, 100))
    pages = max(1, (total + per_page - 1) // per_page)
    page = max(1, min(page, pages))
    start = (page - 1) * per_page
    page_items = items[start:start + per_page]

    return ModerasyonListeSonuc(
        items=page_items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


def ilan_detay_paketi(tur: str, ilan_id: int) -> dict[str, Any] | None:
    """Admin detay sayfası veri paketi."""
    if tur == "kaynak":
        ilan = Kaynak.query.options(joinedload(Kaynak.sahip)).get(ilan_id)
    else:
        ilan = Atik.query.options(joinedload(Atik.sahip)).get(ilan_id)
    if not ilan:
        return None

    sahip = ilan.sahip
    guncel = guncel_analiz(tur, ilan_id)
    gecmis = [analiz_dict(a) for a in analiz_gecmisi(tur, ilan_id)]
    guncel_dict = analiz_dict(guncel)

    not_filt = {"tur": tur}
    if tur == "kaynak":
        not_filt["kaynak_id"] = ilan_id
    else:
        not_filt["atik_id"] = ilan_id
    notlar = (
        IlanModerasyonNot.query.options(joinedload(IlanModerasyonNot.admin))
        .filter_by(**not_filt)
        .order_by(IlanModerasyonNot.created_at.desc())
        .all()
    )
    timeline = [timeline_detay(e) for e in timeline_listele(tur, ilan_id)]

    return {
        "ilan": ilan,
        "tur": tur,
        "sahip": sahip,
        "guncel_analiz": guncel_dict,
        "analiz_gecmisi": gecmis,
        "prompt_karsilastirma": latest_reanalyze_comparison(gecmis),
        "moderation_flow": build_moderation_flow(guncel_dict, timeline),
        "timeline": timeline,
        "notlar": notlar,
        "karar_ozeti": ilan_karar_ozeti(tur, ilan_id, ilan.moderation_status),
        "fotograflar": __import__(
            "services.ilan_images", fromlist=["ilan_fotograf_listesi"]
        ).ilan_fotograf_listesi(ilan),
    }


def dashboard_istatistikleri() -> dict[str, Any]:
    """Moderasyon dashboard özet verileri (optimize aggregate sorgular)."""
    now = utc_now()
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    toplam = db.session.query(func.count(IlanModerasyonAnaliz.id)).scalar() or 0
    bugun = (
        db.session.query(func.count(IlanModerasyonAnaliz.id))
        .filter(IlanModerasyonAnaliz.created_at >= today_start)
        .scalar()
        or 0
    )

    status_counts = Counter()
    for model in (Kaynak, Atik):
        rows = (
            db.session.query(model.moderation_status, func.count(model.id))
            .group_by(model.moderation_status)
            .all()
        )
        for status, cnt in rows:
            status_counts[status] += cnt

    whitelist_count = (
        db.session.query(func.count(IlanModerasyonAnaliz.id))
        .filter(IlanModerasyonAnaliz.whitelist_applied.is_(True))
        .scalar()
        or 0
    )

    kategori_rows = (
        db.session.query(IlanModerasyonAnaliz.category, func.count(IlanModerasyonAnaliz.id))
        .filter(IlanModerasyonAnaliz.category.isnot(None), IlanModerasyonAnaliz.is_current.is_(True))
        .group_by(IlanModerasyonAnaliz.category)
        .order_by(func.count(IlanModerasyonAnaliz.id).desc())
        .limit(5)
        .all()
    )
    purpose_rows = (
        db.session.query(IlanModerasyonAnaliz.purpose, func.count(IlanModerasyonAnaliz.id))
        .filter(IlanModerasyonAnaliz.purpose.isnot(None), IlanModerasyonAnaliz.is_current.is_(True))
        .group_by(IlanModerasyonAnaliz.purpose)
        .order_by(func.count(IlanModerasyonAnaliz.id).desc())
        .limit(5)
        .all()
    )

    avg_risk = (
        db.session.query(func.avg(IlanModerasyonAnaliz.final_risk))
        .filter(IlanModerasyonAnaliz.final_risk.isnot(None))
        .scalar()
    )
    avg_risk = round(float(avg_risk), 1) if avg_risk else 0.0

    false_positive = (
        db.session.query(func.count(IlanModerasyonAnaliz.id))
        .filter(
            IlanModerasyonAnaliz.whitelist_applied.is_(True),
            IlanModerasyonAnaliz.initial_risk >= AI_RISK_REVIEW_MIN,
        )
        .scalar()
        or 0
    )

    admin_override = (
        db.session.query(func.count(IlanModerasyonTimeline.id))
        .filter(
            IlanModerasyonTimeline.event_type.in_(
                ("admin_approved", "admin_rejected", "admin_risk_override")
            )
        )
        .scalar()
        or 0
    )

    def _gunluk_sayim(days: int) -> dict[str, int]:
        start = now - timedelta(days=days)
        rows = (
            db.session.query(
                func.date(IlanModerasyonAnaliz.created_at),
                func.count(IlanModerasyonAnaliz.id),
            )
            .filter(IlanModerasyonAnaliz.created_at >= start)
            .group_by(func.date(IlanModerasyonAnaliz.created_at))
            .all()
        )
        return {str(d): c for d, c in sorted(rows)}

    phase1 = karar_analitigi()
    phase2 = spam_duplicate_analitigi()
    ai_health = ai_health_stats()

    return {
        "toplam_analiz": toplam,
        "bugun_analiz": bugun,
        "approved": status_counts.get(MODERATION_STATUS_APPROVED, 0),
        "pending_review": status_counts.get(MODERATION_STATUS_PENDING_REVIEW, 0),
        "rejected": status_counts.get(MODERATION_STATUS_REJECTED, 0),
        "whitelist_kullanilan": whitelist_count,
        "en_cok_kategori": kategori_rows,
        "ortalama_risk": avg_risk,
        "en_cok_purpose": purpose_rows,
        "yanlis_pozitif": false_positive,
        "admin_override": admin_override,
        "grafik_7_gun": _gunluk_sayim(7),
        "grafik_30_gun": _gunluk_sayim(30),
        "ai_accuracy": phase1["ai_accuracy"],
        "override_rate": phase1["override_rate"],
        "false_positive": phase1["false_positive"],
        "false_negative": phase1["false_negative"],
        "pending_to_approved": phase1["pending_to_approved"],
        "pending_to_rejected": phase1["pending_to_rejected"],
        "en_cok_override_kategori": phase1["en_cok_override_kategori"],
        "en_cok_override_purpose": phase1["en_cok_override_purpose"],
        "spam_dagilimi": phase2["spam_dagilimi"],
        "duplicate_orani": phase2["duplicate_orani"],
        "en_spam_kullanicilar": phase2["en_spam_kullanicilar"],
        "en_tekrar_ilanlar": phase2["en_tekrar_ilanlar"],
        "ai_health": ai_health,
    }


def spam_duplicate_analitigi() -> dict[str, Any]:
    """Phase 2 dashboard metrikleri (optimize)."""
    analizler = IlanModerasyonAnaliz.query.filter_by(is_current=True).all()
    spam_buckets = {"0-30": 0, "31-60": 0, "61-100": 0}
    duplicate_high = 0
    user_spam: Counter = Counter()
    ilan_dup: Counter = Counter()

    user_ids = set()
    ilan_refs: list[tuple[str, int, int]] = []

    for a in analizler:
        spam = a.spam_score or 0
        if spam <= 30:
            spam_buckets["0-30"] += 1
        elif spam <= 60:
            spam_buckets["31-60"] += 1
        else:
            spam_buckets["61-100"] += 1

        dup = a.duplicate_score or 0
        if dup >= 50:
            duplicate_high += 1

        if spam >= 40:
            ilan_id = a.kaynak_id or a.atik_id
            if ilan_id:
                ilan_refs.append((a.tur, ilan_id, spam))

        if dup >= 50:
            ilan_id = a.kaynak_id or a.atik_id
            if ilan_id:
                ilan_dup[f"{a.tur}:{ilan_id}"] = dup

    for tur, ilan_id, spam in ilan_refs:
        model = Kaynak if tur == "kaynak" else Atik
        uid = db.session.query(model.user_id).filter_by(id=ilan_id).scalar()
        if uid:
            user_spam[uid] += spam

    total = len(analizler) or 1
    user_map = {
        u.id: u.username
        for u in User.query.filter(User.id.in_(list(user_spam.keys()) or [0])).all()
    }
    en_spam = [
        (user_map.get(uid, f"user:{uid}"), score_sum)
        for uid, score_sum in user_spam.most_common(5)
    ]

    en_tekrar = []
    for key, score in ilan_dup.most_common(5):
        tur, ilan_id = key.split(":", 1)
        model = Kaynak if tur == "kaynak" else Atik
        baslik = db.session.query(model.baslik).filter_by(id=int(ilan_id)).scalar()
        en_tekrar.append((baslik or key, score, tur, int(ilan_id)))

    return {
        "spam_dagilimi": spam_buckets,
        "duplicate_orani": round((duplicate_high / total) * 100, 1),
        "en_spam_kullanicilar": en_spam,
        "en_tekrar_ilanlar": en_tekrar,
    }


def kategori_secenekleri() -> list[str]:
    return sorted(set(KATEGORILER_KAYNAK + KATEGORILER_ATIK))
