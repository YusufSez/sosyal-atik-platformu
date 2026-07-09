"""AI vs Admin karar analitiği (Phase 1)."""

from __future__ import annotations

from collections import Counter
from typing import Any

from constants import MODERATION_STATUS_APPROVED, MODERATION_STATUS_PENDING_REVIEW, MODERATION_STATUS_REJECTED
from extensions import db
from models import IlanModerasyonKarar
from services.moderation_analysis import guncel_analiz
from utils import utc_now


def _ai_karar_al(tur: str, ilan_id: int, ilan_status: str | None) -> tuple[str, int | None, str | None, str | None, int | None]:
    """Güncel analizden AI kararını döndürür."""
    analiz = guncel_analiz(tur, ilan_id)
    if analiz:
        return (
            analiz.moderation_status,
            analiz.id,
            analiz.category,
            analiz.purpose,
            analiz.analysis_version,
        )
    return (ilan_status or MODERATION_STATUS_APPROVED, None, None, None, None)


def kaydet_admin_karar(
    tur: str,
    ilan_id: int,
    admin_user_id: int,
    admin_decision: str,
    action_type: str,
    *,
    ai_decision: str | None = None,
    analiz_id: int | None = None,
    decision_version: int | None = None,
    category: str | None = None,
    purpose: str | None = None,
    decision_reason: str | None = None,
    ilan_status_before: str | None = None,
) -> IlanModerasyonKarar:
    """Admin kararını AI kararıyla karşılaştırarak kaydeder."""
    if ai_decision is None:
        ai_decision, analiz_id, category, purpose, decision_version = _ai_karar_al(
            tur, ilan_id, ilan_status_before
        )

    decision_match = ai_decision == admin_decision
    override = not decision_match

    kayit = IlanModerasyonKarar(
        tur=tur,
        kaynak_id=ilan_id if tur == "kaynak" else None,
        atik_id=ilan_id if tur == "atik" else None,
        analiz_id=analiz_id,
        action_type=action_type,
        ai_decision=ai_decision,
        admin_decision=admin_decision,
        decision_match=decision_match,
        override=override,
        decision_version=decision_version,
        decision_reason=(decision_reason[:2000] if decision_reason else None),
        admin_user_id=admin_user_id,
        decision_time=utc_now(),
        category=category,
        purpose=purpose,
    )
    db.session.add(kayit)
    return kayit


def ilan_son_karar(tur: str, ilan_id: int) -> IlanModerasyonKarar | None:
    """İlan için en son admin kararı."""
    q = IlanModerasyonKarar.query.filter_by(tur=tur)
    if tur == "kaynak":
        q = q.filter_by(kaynak_id=ilan_id)
    else:
        q = q.filter_by(atik_id=ilan_id)
    return q.order_by(IlanModerasyonKarar.decision_time.desc()).first()


def ilan_karar_ozeti(tur: str, ilan_id: int, ilan_status: str) -> dict[str, Any]:
    """Detay sayfası: AI Kararı → Admin Kararı → Sonuç."""
    analiz = guncel_analiz(tur, ilan_id)
    ai_decision = analiz.moderation_status if analiz else ilan_status
    son_karar = ilan_son_karar(tur, ilan_id)

    admin_decision = son_karar.admin_decision if son_karar else None
    decision_match = son_karar.decision_match if son_karar else None
    override = son_karar.override if son_karar else None

    if son_karar:
        sonuc = "Eşleşti" if decision_match else "Override (Admin farklı karar verdi)"
    elif ilan_status == ai_decision:
        sonuc = "Henüz admin müdahalesi yok — AI ile uyumlu"
    else:
        sonuc = "Henüz admin müdahalesi yok"

    return {
        "ai_decision": ai_decision,
        "admin_decision": admin_decision or ilan_status,
        "current_status": ilan_status,
        "decision_match": decision_match,
        "override": override,
        "sonuc": sonuc,
        "decision_reason": son_karar.decision_reason if son_karar else None,
        "decision_time": son_karar.decision_time if son_karar else None,
        "decision_version": son_karar.decision_version if son_karar else (analiz.analysis_version if analiz else None),
        "karar_gecmisi": [
            {
                "action_type": k.action_type,
                "ai_decision": k.ai_decision,
                "admin_decision": k.admin_decision,
                "decision_match": k.decision_match,
                "override": k.override,
                "decision_time": k.decision_time,
                "decision_reason": k.decision_reason,
            }
            for k in _ilan_karar_gecmisi(tur, ilan_id)
        ],
    }


def _ilan_karar_gecmisi(tur: str, ilan_id: int) -> list[IlanModerasyonKarar]:
    q = IlanModerasyonKarar.query.filter_by(tur=tur)
    if tur == "kaynak":
        q = q.filter_by(kaynak_id=ilan_id)
    else:
        q = q.filter_by(atik_id=ilan_id)
    return q.order_by(IlanModerasyonKarar.decision_time.desc()).all()


def karar_analitigi() -> dict[str, Any]:
    """Dashboard Phase 1 istatistikleri."""
    kararlar = IlanModerasyonKarar.query.filter(
        IlanModerasyonKarar.action_type.in_(("approve", "reject", "risk_override"))
    ).all()

    total = len(kararlar)
    matches = sum(1 for k in kararlar if k.decision_match)
    overrides = sum(1 for k in kararlar if k.override)

    false_positive = sum(
        1 for k in kararlar
        if k.ai_decision in (MODERATION_STATUS_PENDING_REVIEW, MODERATION_STATUS_REJECTED)
        and k.admin_decision == MODERATION_STATUS_APPROVED
    )
    false_negative = sum(
        1 for k in kararlar
        if k.ai_decision == MODERATION_STATUS_APPROVED
        and k.admin_decision == MODERATION_STATUS_REJECTED
    )
    pending_to_approved = sum(
        1 for k in kararlar
        if k.ai_decision == MODERATION_STATUS_PENDING_REVIEW
        and k.admin_decision == MODERATION_STATUS_APPROVED
    )
    pending_to_rejected = sum(
        1 for k in kararlar
        if k.ai_decision == MODERATION_STATUS_PENDING_REVIEW
        and k.admin_decision == MODERATION_STATUS_REJECTED
    )

    override_kategori: Counter = Counter()
    override_purpose: Counter = Counter()
    for k in kararlar:
        if k.override:
            if k.category:
                override_kategori[k.category] += 1
            if k.purpose:
                override_purpose[k.purpose] += 1

    ai_accuracy = round((matches / total) * 100, 1) if total else 0.0
    override_rate = round((overrides / total) * 100, 1) if total else 0.0

    return {
        "ai_accuracy": ai_accuracy,
        "override_rate": override_rate,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "pending_to_approved": pending_to_approved,
        "pending_to_rejected": pending_to_rejected,
        "en_cok_override_kategori": override_kategori.most_common(5),
        "en_cok_override_purpose": override_purpose.most_common(5),
        "toplam_karar": total,
        "eslesen_karar": matches,
    }
