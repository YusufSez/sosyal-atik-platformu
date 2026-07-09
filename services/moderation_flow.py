"""AI Moderation Flow — detay ekranı akış diyagramı."""

from __future__ import annotations

from typing import Any


FLOW_STEPS = (
    ("ilan", "İlan", "İlan oluşturuldu / yüklendi"),
    ("vision", "Vision Analysis", "Görsel AI analizi"),
    ("text", "Text Analysis", "Metin moderasyonu"),
    ("purpose", "Purpose Detection", "Amaç tespiti"),
    ("spam", "Spam Detection", "Spam skoru"),
    ("duplicate", "Duplicate Detection", "Duplicate skoru"),
    ("whitelist", "Whitelist", "Geri dönüşüm whitelist"),
    ("risk", "Risk Calculation", "Risk hesaplama"),
    ("explainability", "Explainability", "Sinyal ve kural açıklaması"),
    ("decision", "Decision", "Moderasyon kararı"),
)


def build_moderation_flow(analiz: dict | None, timeline: list[dict] | None = None) -> list[dict[str, Any]]:
    """Moderasyon akış adımlarını timeline ile zenginleştirir."""
    analiz = analiz or {}
    timeline = timeline or []
    event_map = {e.get("event_type", ""): e for e in timeline}

    steps: list[dict[str, Any]] = []
    for step_id, title, default_desc in FLOW_STEPS:
        status = "pending"
        detail = default_desc
        ts = None

        if step_id == "ilan":
            ev = event_map.get("ilan_created")
            status = "done" if ev else "active"
            if ev:
                ts = ev.get("created_at")
                detail = ev.get("title", default_desc)
        elif step_id == "vision":
            status = "done" if analiz.get("vision_analysis") or analiz.get("photo_analyses") else "skip"
            ev = event_map.get("risk_scored")
            if ev:
                ts = ev.get("created_at")
        elif step_id == "text":
            status = "done" if analiz.get("text_analysis") else "skip"
        elif step_id == "purpose":
            status = "done" if analiz.get("purpose") else "skip"
            detail = analiz.get("purpose") or default_desc
        elif step_id == "spam":
            spam = analiz.get("spam_score")
            status = "done" if spam is not None else "skip"
            detail = f"Spam Score: {spam}" if spam is not None else default_desc
        elif step_id == "duplicate":
            dup = analiz.get("duplicate_score")
            status = "done" if dup is not None else "skip"
            detail = f"Duplicate Score: {dup}" if dup is not None else default_desc
        elif step_id == "whitelist":
            status = "done" if analiz.get("whitelist_applied") is not None else "skip"
            detail = "Uygulandı" if analiz.get("whitelist_applied") else "Uygulanmadı"
        elif step_id == "risk":
            status = "done" if analiz.get("final_risk") is not None else "pending"
            detail = f"Final Risk: {analiz.get('final_risk')}/100"
        elif step_id == "explainability":
            status = "done" if analiz.get("matched_rules") else "skip"
        elif step_id == "decision":
            status = "done" if analiz.get("moderation_status") else "pending"
            detail = analiz.get("moderation_status") or default_desc
            ev = event_map.get("admin_approved") or event_map.get("admin_rejected")
            if ev:
                ts = ev.get("created_at")

        steps.append({
            "id": step_id,
            "title": title,
            "detail": detail,
            "status": status,
            "created_at": ts,
        })
    return steps
