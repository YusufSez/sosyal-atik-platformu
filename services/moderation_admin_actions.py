"""Moderasyon admin aksiyonlarını merkezi kayıt noktası."""

from __future__ import annotations

from services.moderation_activity import log_moderasyon_activity
from services.moderation_decisions import kaydet_admin_karar


def kaydet_moderasyon_aksiyonu(
    action_type: str,
    tur: str,
    ilan_id: int,
    admin_user_id: int,
    *,
    admin_decision: str | None = None,
    decision_reason: str | None = None,
    ilan_status_before: str | None = None,
    activity_note: str | None = None,
    kaydet_karar: bool = True,
) -> None:
    """
    Activity log + (opsiyonel) karar analitiği kaydı.
    approve/reject/risk_override için karar kaydı oluşturur.
    """
    log_moderasyon_activity(
        action=action_type,
        tur=tur,
        ilan_id=ilan_id,
        note=activity_note or decision_reason,
        admin_user_id=admin_user_id,
    )

    if kaydet_karar and admin_decision and action_type in ("approve", "reject", "risk_override"):
        kaydet_admin_karar(
            tur,
            ilan_id,
            admin_user_id,
            admin_decision,
            action_type,
            decision_reason=decision_reason,
            ilan_status_before=ilan_status_before,
        )
