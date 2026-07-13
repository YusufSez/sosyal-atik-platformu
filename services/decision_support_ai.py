"""Ulusal Karar Destek Merkezi — AI değerlendirme katmanı."""

from __future__ import annotations

import json
import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.decision_support import build_decision_support_center

logger = logging.getLogger("atikport.decision_support_ai")


def _rule_narratives(center: dict) -> dict:
    weekly = center.get("weekly_report") or {}
    monthly = center.get("monthly_report") or {}
    risk = center.get("risk_analysis") or {}
    part = center.get("participation_trends") or {}
    kpi = center.get("kpi") or {}

    wchg = weekly.get("change_pct") or {}
    mchg = monthly.get("change_pct") or {}

    weekly_text = [
        f"Son 7 günde {weekly.get('metrics', {}).get('ilan', 0)} ilan, "
        f"{weekly.get('metrics', {}).get('teslim', 0)} teslim kaydedildi "
        f"(ilan değişim %{wchg.get('ilan', 0)}).",
        f"Haftalık CO₂ tasarrufu {weekly.get('metrics', {}).get('co2e_kg', 0):.1f} kg.",
        f"Aktif vatandaş {weekly.get('metrics', {}).get('aktif_kullanici', 0)} "
        f"(değişim %{wchg.get('aktif_kullanici', 0)}).",
    ]
    monthly_text = [
        f"Son 30 günde {monthly.get('metrics', {}).get('ilan', 0)} ilan üretildi "
        f"(değişim %{mchg.get('ilan', 0)}).",
        f"Aylık geri kazanım {monthly.get('metrics', {}).get('atik_kg', 0):.1f} kg; "
        f"CO₂ {monthly.get('metrics', {}).get('co2e_kg', 0):.1f} kg.",
        f"Katılım eğilimi: {part.get('trend', 'stabil')} "
        f"(%{part.get('change_pct', 0)}).",
    ]

    overview = (
        f"Ulusal özet: {kpi.get('aktif_belediye', 0)} belediye, "
        f"{kpi.get('vatandas_sayisi', 0)} vatandaş, "
        f"katılım %{kpi.get('vatandas_katilim_orani', 0)}. "
        f"Risk seviyesi: {risk.get('level', 'dusuk')}."
    )

    return {
        "overview": overview,
        "weekly_narrative": weekly_text,
        "monthly_narrative": monthly_text,
        "risk_narrative": risk.get("findings") or [],
        "source": "rules",
    }


def enrich_decision_support(center: dict | None = None) -> dict:
    """Analitik paket + AI/kural anlatım."""
    center = center or build_decision_support_center()
    narratives = _rule_narratives(center)
    source = "rules"

    client = get_client()
    if client:
        compact = {
            "kpi": {
                k: center.get("kpi", {}).get(k)
                for k in (
                    "aktif_belediye",
                    "vatandas_sayisi",
                    "vatandas_katilim_orani",
                    "co2_tasarrufu_kg",
                    "toplam_geri_kazanim_kg",
                )
            },
            "weekly_change": (center.get("weekly_report") or {}).get("change_pct"),
            "monthly_change": (center.get("monthly_report") or {}).get("change_pct"),
            "risk": {
                "level": (center.get("risk_analysis") or {}).get("level"),
                "findings": (center.get("risk_analysis") or {}).get("findings"),
            },
            "campaigns": [
                c.get("title") for c in (center.get("campaigns") or [])[:4]
            ],
            "actions": [
                a.get("title") for a in (center.get("ministry_actions") or [])[:4]
            ],
            "rising_categories": [
                s.get("kategori")
                for s in ((center.get("category_shifts") or {}).get("rising") or [])[:3]
            ],
            "participation_trend": (center.get("participation_trends") or {}).get("trend"),
        }
        prompt = (
            "Sen AtıkPort Ulusal Karar Destek asistanısın. Verilen istatistikleri yorumla; "
            "yeni sayı uydurma.\n"
            "JSON döndür:\n"
            '{"overview":"...","weekly_narrative":["...","...","..."],'
            '"monthly_narrative":["...","...","..."],"risk_narrative":["...","..."]}\n'
            f"VERİ:\n{json.dumps(compact, ensure_ascii=False, default=str)}"
        )
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types
                from helpers.json_utils import json_cikar

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                parsed = json_cikar((result.text or "").strip())
                if isinstance(parsed, dict) and parsed.get("overview"):
                    narratives = {
                        "overview": str(parsed.get("overview") or narratives["overview"]),
                        "weekly_narrative": [
                            str(x) for x in (parsed.get("weekly_narrative") or narratives["weekly_narrative"])
                        ][:5],
                        "monthly_narrative": [
                            str(x) for x in (parsed.get("monthly_narrative") or narratives["monthly_narrative"])
                        ][:5],
                        "risk_narrative": [
                            str(x) for x in (parsed.get("risk_narrative") or narratives["risk_narrative"])
                        ][:5],
                        "source": f"gemini:{model}",
                    }
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Karar destek AI başarısız (%s): %s", model, exc)

    center["ai"] = narratives
    center["ai_source"] = source
    return center
