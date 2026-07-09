"""İlan moderasyon timeline olayları."""

from __future__ import annotations

import json
from typing import Any

from extensions import db
from models import IlanModerasyonTimeline
from utils import utc_now


def _ilan_keys(tur: str, ilan_id: int) -> dict:
    if tur == "kaynak":
        return {"tur": tur, "kaynak_id": ilan_id, "atik_id": None}
    return {"tur": tur, "kaynak_id": None, "atik_id": ilan_id}


def timeline_ekle(
    tur: str,
    ilan_id: int,
    event_type: str,
    title: str,
    detail: dict | None = None,
    analiz_id: int | None = None,
    admin_user_id: int | None = None,
) -> IlanModerasyonTimeline:
    """Yeni timeline olayı kaydeder."""
    event = IlanModerasyonTimeline(
        **_ilan_keys(tur, ilan_id),
        analiz_id=analiz_id,
        event_type=event_type,
        title=title,
        detail_json=json.dumps(detail or {}, ensure_ascii=False),
        admin_user_id=admin_user_id,
        created_at=utc_now(),
    )
    db.session.add(event)
    return event


def timeline_listele(tur: str, ilan_id: int) -> list[IlanModerasyonTimeline]:
    """İlan için kronolojik timeline."""
    q = IlanModerasyonTimeline.query.filter_by(**_ilan_keys(tur, ilan_id))
    return q.order_by(IlanModerasyonTimeline.created_at.asc(), IlanModerasyonTimeline.id.asc()).all()


def timeline_detay(event: IlanModerasyonTimeline) -> dict[str, Any]:
    """Timeline olay detayını dict olarak döndürür."""
    try:
        detail = json.loads(event.detail_json or "{}")
    except json.JSONDecodeError:
        detail = {}
    return {
        "id": event.id,
        "event_type": event.event_type,
        "title": event.title,
        "detail": detail,
        "analiz_id": event.analiz_id,
        "admin_user_id": event.admin_user_id,
        "created_at": event.created_at,
    }


def analiz_timeline_olaylari_ekle(
    tur: str,
    ilan_id: int,
    ai_sonuc: dict,
    analiz_id: int,
    triggered_by: str,
    model_name: str,
    prompt_version: str,
) -> None:
    """AI analiz sonucundan standart timeline zinciri oluşturur."""
    if triggered_by == "upload":
        timeline_ekle(tur, ilan_id, "ilan_created", "İlan oluşturuldu", analiz_id=analiz_id)
    elif triggered_by == "admin_reanalyze":
        timeline_ekle(
            tur,
            ilan_id,
            "reanalyze_started",
            "Yeniden AI analizi başlatıldı",
            detail={"model": model_name, "prompt_version": prompt_version},
            analiz_id=analiz_id,
        )
    else:
        timeline_ekle(tur, ilan_id, "analysis_started", "AI analizi başladı", analiz_id=analiz_id)

    timeline_ekle(
        tur,
        ilan_id,
        "ai_model",
        f"Gemini analiz — {model_name}",
        detail={"model": model_name, "prompt_version": prompt_version},
        analiz_id=analiz_id,
    )

    initial = ai_sonuc.get("initial_risk", ai_sonuc.get("risk_skoru"))
    timeline_ekle(
        tur,
        ilan_id,
        "risk_scored",
        f"Risk {initial}/100",
        detail={"risk": initial, "phase": "initial"},
        analiz_id=analiz_id,
    )

    purpose = ai_sonuc.get("purpose")
    if purpose and purpose != "unknown":
        timeline_ekle(
            tur,
            ilan_id,
            "purpose_detected",
            f"Purpose = {purpose}",
            detail={"purpose": purpose},
            analiz_id=analiz_id,
        )

    if ai_sonuc.get("whitelist_applied") or ai_sonuc.get("risk_adjustment", 0) > 0:
        timeline_ekle(
            tur,
            ilan_id,
            "whitelist_matched",
            "Whitelist / bağlam eşleşmesi",
            detail={
                "matched_rules": ai_sonuc.get("matched_rules", []),
                "adjustment": ai_sonuc.get("risk_adjustment", 0),
            },
            analiz_id=analiz_id,
        )
        final = ai_sonuc.get("final_risk", ai_sonuc.get("risk_skoru"))
        timeline_ekle(
            tur,
            ilan_id,
            "risk_adjusted",
            f"Risk {final}/100",
            detail={
                "initial_risk": initial,
                "final_risk": final,
                "reason": ai_sonuc.get("risk_adjustment_reason"),
            },
            analiz_id=analiz_id,
        )

    status = ai_sonuc.get("moderation_status", "approved")
    status_labels = {
        "approved": "Onaylandı",
        "pending_review": "İnceleme Bekliyor",
        "rejected": "Reddedildi",
    }
    timeline_ekle(
        tur,
        ilan_id,
        "status_set",
        status_labels.get(status, status),
        detail={"moderation_status": status, "confidence": ai_sonuc.get("confidence")},
        analiz_id=analiz_id,
    )
