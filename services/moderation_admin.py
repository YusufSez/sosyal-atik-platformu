"""Admin moderasyon paneli — liste, filtre, dashboard."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, case, func, select, union_all
from sqlalchemy.orm import joinedload, load_only, selectinload

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
from services.moderation_list_queries import (
    ModerasyonListeSatir,
    batch_load_ilans,
    sorted_moderation_rows,
)
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


def _row_to_liste_ogesi(row: ModerasyonListeSatir, ilan) -> ModerasyonListeOgesi:
    sahip = getattr(ilan, "sahip", None) if ilan else None
    return ModerasyonListeOgesi(
        tur=row.tur,
        ilan_id=row.ilan_id,
        baslik=row.baslik,
        aciklama_ozet=_aciklama_ilk_satir(row.aciklama),
        kullanici=sahip.username if sahip else "?",
        kullanici_id=row.user_id,
        tarih=row.tarih,
        risk_skoru=row.risk_skoru,
        moderation_status=row.moderation_status,
        category=row.category or row.kategori,
        purpose=row.purpose,
        confidence=row.confidence,
        spam_score=row.spam_score,
        duplicate_score=row.duplicate_score,
        kapak=kapak_resim(ilan) if ilan else (row.resim or "default.jpg"),
        kategori=row.kategori,
        alt_kategori=row.alt_kategori if row.tur == "kaynak" else None,
    )


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
    sorted_rows = sorted_moderation_rows(filters)
    total = len(sorted_rows)

    if page is None:
        slice_rows = sorted_rows
    else:
        per_page = max(1, min(per_page, 100))
        pages = max(1, (total + per_page - 1) // per_page)
        page = max(1, min(page, pages))
        start = (page - 1) * per_page
        slice_rows = sorted_rows[start : start + per_page]

    ilan_map = batch_load_ilans(slice_rows)
    items = [
        _row_to_liste_ogesi(row, ilan_map.get((row.tur, row.ilan_id)))
        for row in slice_rows
    ]

    if page is None:
        return items

    return ModerasyonListeSonuc(
        items=items,
        total=total,
        page=page,
        per_page=per_page,
        pages=pages,
    )


def ilan_detay_paketi(tur: str, ilan_id: int) -> dict[str, Any] | None:
    """Admin detay sayfası veri paketi."""
    if tur == "kaynak":
        ilan = Kaynak.query.options(
            joinedload(Kaynak.sahip),
            selectinload(Kaynak.fotograflar),
        ).get(ilan_id)
    else:
        ilan = Atik.query.options(
            joinedload(Atik.sahip),
            selectinload(Atik.fotograflar),
        ).get(ilan_id)
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
    analiz = IlanModerasyonAnaliz

    toplam, bugun, whitelist_count, false_positive, avg_risk = db.session.execute(
        select(
            func.count(analiz.id),
            func.count().filter(analiz.created_at >= today_start),
            func.count().filter(analiz.whitelist_applied.is_(True)),
            func.count().filter(
                and_(
                    analiz.whitelist_applied.is_(True),
                    analiz.initial_risk >= AI_RISK_REVIEW_MIN,
                )
            ),
            func.avg(analiz.final_risk).filter(analiz.final_risk.isnot(None)),
        )
    ).one()
    avg_risk = round(float(avg_risk), 1) if avg_risk else 0.0

    status_union = union_all(
        select(Kaynak.moderation_status.label("st"), func.count().label("cnt"))
        .group_by(Kaynak.moderation_status),
        select(Atik.moderation_status.label("st"), func.count().label("cnt"))
        .group_by(Atik.moderation_status),
    ).subquery()
    status_counts = Counter(
        {
            row[0]: int(row[1] or 0)
            for row in db.session.execute(
                select(status_union.c.st, func.sum(status_union.c.cnt)).group_by(
                    status_union.c.st
                )
            ).all()
        }
    )

    kategori_rows = (
        db.session.query(analiz.category, func.count(analiz.id))
        .filter(analiz.category.isnot(None), analiz.is_current.is_(True))
        .group_by(analiz.category)
        .order_by(func.count(analiz.id).desc())
        .limit(5)
        .all()
    )
    purpose_rows = (
        db.session.query(analiz.purpose, func.count(analiz.id))
        .filter(analiz.purpose.isnot(None), analiz.is_current.is_(True))
        .group_by(analiz.purpose)
        .order_by(func.count(analiz.id).desc())
        .limit(5)
        .all()
    )

    admin_override = (
        db.session.scalar(
            select(func.count()).select_from(IlanModerasyonTimeline).where(
                IlanModerasyonTimeline.event_type.in_(
                    ("admin_approved", "admin_rejected", "admin_risk_override")
                )
            )
        )
        or 0
    )

    def _gunluk_sayim(days: int) -> dict[str, int]:
        start = now - timedelta(days=days)
        rows = (
            db.session.query(
                func.date(analiz.created_at),
                func.count(analiz.id),
            )
            .filter(analiz.created_at >= start)
            .group_by(func.date(analiz.created_at))
            .all()
        )
        return {str(d): c for d, c in sorted(rows)}

    phase1 = karar_analitigi()
    phase2 = spam_duplicate_analitigi()
    ai_health = ai_health_stats()

    return {
        "toplam_analiz": int(toplam or 0),
        "bugun_analiz": int(bugun or 0),
        "approved": status_counts.get(MODERATION_STATUS_APPROVED, 0),
        "pending_review": status_counts.get(MODERATION_STATUS_PENDING_REVIEW, 0),
        "rejected": status_counts.get(MODERATION_STATUS_REJECTED, 0),
        "whitelist_kullanilan": int(whitelist_count or 0),
        "en_cok_kategori": kategori_rows,
        "ortalama_risk": avg_risk,
        "en_cok_purpose": purpose_rows,
        "yanlis_pozitif": int(false_positive or 0),
        "admin_override": int(admin_override),
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
    """Phase 2 dashboard metrikleri (SQL aggregate)."""
    analiz = IlanModerasyonAnaliz
    current = analiz.is_current.is_(True)
    spam_score = func.coalesce(analiz.spam_score, 0)
    dup_score = func.coalesce(analiz.duplicate_score, 0)

    bucket_0_30, bucket_31_60, bucket_61_100, duplicate_high, total = db.session.execute(
        select(
            func.count().filter(spam_score <= 30),
            func.count().filter(spam_score > 30, spam_score <= 60),
            func.count().filter(spam_score > 60),
            func.count().filter(dup_score >= 50),
            func.count(),
        ).where(current)
    ).one()
    total = int(total or 0) or 1

    spam_buckets = {
        "0-30": int(bucket_0_30 or 0),
        "31-60": int(bucket_31_60 or 0),
        "61-100": int(bucket_61_100 or 0),
    }

    kaynak_spam = db.session.execute(
        select(Kaynak.user_id, func.sum(spam_score))
        .select_from(analiz)
        .join(Kaynak, analiz.kaynak_id == Kaynak.id)
        .where(current, analiz.tur == "kaynak", spam_score >= 40)
        .group_by(Kaynak.user_id)
    ).all()
    atik_spam = db.session.execute(
        select(Atik.user_id, func.sum(spam_score))
        .select_from(analiz)
        .join(Atik, analiz.atik_id == Atik.id)
        .where(current, analiz.tur == "atik", spam_score >= 40)
        .group_by(Atik.user_id)
    ).all()
    user_spam: Counter = Counter()
    for uid, score_sum in kaynak_spam + atik_spam:
        if uid:
            user_spam[int(uid)] += int(score_sum or 0)

    user_map = {
        u.id: u.username
        for u in User.query.filter(User.id.in_(list(user_spam.keys()) or [0]))
        .options(load_only(User.id, User.username))
        .all()
    }
    en_spam = [
        (user_map.get(uid, f"user:{uid}"), score_sum)
        for uid, score_sum in user_spam.most_common(5)
    ]

    dup_rows = db.session.execute(
        select(analiz.tur, func.coalesce(analiz.kaynak_id, analiz.atik_id), dup_score)
        .where(current, dup_score >= 50)
        .order_by(dup_score.desc())
        .limit(5)
    ).all()
    en_tekrar = []
    kaynak_dup_ids = [int(row[1]) for row in dup_rows if row[0] == "kaynak" and row[1]]
    atik_dup_ids = [int(row[1]) for row in dup_rows if row[0] == "atik" and row[1]]
    kaynak_baslik = {
        r.id: r.baslik
        for r in Kaynak.query.filter(Kaynak.id.in_(kaynak_dup_ids or [0]))
        .options(load_only(Kaynak.id, Kaynak.baslik))
        .all()
    }
    atik_baslik = {
        r.id: r.baslik
        for r in Atik.query.filter(Atik.id.in_(atik_dup_ids or [0]))
        .options(load_only(Atik.id, Atik.baslik))
        .all()
    }
    for tur, ilan_id, score in dup_rows:
        if not ilan_id:
            continue
        key = f"{tur}:{ilan_id}"
        baslik = (
            kaynak_baslik.get(int(ilan_id))
            if tur == "kaynak"
            else atik_baslik.get(int(ilan_id))
        )
        en_tekrar.append((baslik or key, int(score or 0), tur, int(ilan_id)))

    return {
        "spam_dagilimi": spam_buckets,
        "duplicate_orani": round((int(duplicate_high or 0) / total) * 100, 1),
        "en_spam_kullanicilar": en_spam,
        "en_tekrar_ilanlar": en_tekrar,
    }


def kategori_secenekleri() -> list[str]:
    return sorted(set(KATEGORILER_KAYNAK + KATEGORILER_ATIK))
