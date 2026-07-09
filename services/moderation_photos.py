"""İlan fotoğrafları için AI görsel analizi."""

from __future__ import annotations

import os
from typing import Any

from flask import current_app

from utils import resolve_item_picture_path


def _confidence_from_risk(risk: int) -> float:
    """Risk skorundan türetilmiş güven skoru (0-1)."""
    return round(max(0.05, min(0.99, (100 - risk) / 100)), 2)


def analyze_photo(
    photo_path: str,
    tur: str,
    baslik: str | None,
    aciklama: str | None,
    index: int,
    analyze_fn=None,
) -> dict[str, Any]:
    """Tek fotoğraf için AI analizi."""
    if analyze_fn is None:
        from helpers import ai_tam_analiz

        analyze_fn = ai_tam_analiz

    sonuc = analyze_fn(
        photo_path,
        tur=tur,
        aciklama=aciklama,
        baslik=baslik,
    )
    risk = int(sonuc.get("risk_skoru", 0))
    confidence = float(sonuc.get("confidence", _confidence_from_risk(risk)))
    return {
        "index": index,
        "filename": os.path.basename(photo_path),
        "label": sonuc.get("kategori") or "Diğer",
        "confidence": confidence,
        "risk_score": risk,
        "purpose": sonuc.get("purpose"),
        "is_recyclable": bool(sonuc.get("is_recyclable")),
        "detected": {
            "hazard_symbol": bool(sonuc.get("uygunsuz")),
            "human": False,
            "vehicle": False,
            "logo": False,
            "label_text": bool(sonuc.get("reason")),
        },
        "raw": sonuc,
    }


def analyze_listing_photos(
    photo_files: list[str],
    tur: str,
    baslik: str | None,
    aciklama: str | None,
    analyze_fn=None,
) -> list[dict[str, Any]]:
    """Tüm ilan fotoğraflarını analiz eder."""
    if not photo_files:
        return []

    upload_folder = current_app.config["UPLOAD_FOLDER"]
    results = []
    for i, dosya in enumerate(photo_files):
        try:
            path = resolve_item_picture_path(dosya)
        except ValueError:
            continue
        if not os.path.isfile(path):
            continue
        results.append(
            analyze_photo(path, tur, baslik, aciklama, i + 1, analyze_fn=analyze_fn)
        )
    return results


def merge_photo_analyses(photo_analyses: list[dict[str, Any]]) -> dict[str, Any]:
    """Fotoğraf analizlerinden birleşik görsel sonuç üretir."""
    if not photo_analyses:
        return {}
    max_risk = max(int(p.get("risk_score", 0)) for p in photo_analyses)
    primary = pick_primary_photo_analysis(photo_analyses)
    return {
        "photo_count": len(photo_analyses),
        "max_risk": max_risk,
        "primary_label": primary.get("label"),
        "primary_confidence": primary.get("confidence"),
        "primary_index": primary.get("index"),
        "photos": photo_analyses,
    }


def _explainability_negativity(raw: dict[str, Any]) -> int:
    """Yüksek değer = moderasyon açısından daha kötü explainability."""
    from services.moderation_explainability import compute_explainability_signals

    _, negative = compute_explainability_signals(raw)
    score = len(negative) * 10
    if raw.get("uygunsuz"):
        score += 5
    if int(raw.get("risk_skoru", 0)) >= 70:
        score += 3
    if raw.get("hata"):
        score += 2
    return score


def pick_primary_photo_analysis(
    photo_analyses: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Moderasyon kararı için birincil fotoğrafı seçer:
    en yüksek risk → en kötü explainability → en yüksek confidence.
    """
    if not photo_analyses:
        return {}

    def sort_key(photo: dict[str, Any]) -> tuple[int, int, float]:
        raw = photo.get("raw") or {}
        risk = int(photo.get("risk_score", raw.get("risk_skoru", 0)))
        negativity = _explainability_negativity(raw)
        confidence = float(photo.get("confidence", raw.get("confidence", 0)))
        return (risk, negativity, confidence)

    return max(photo_analyses, key=sort_key)


def build_merged_ai_sonuc_from_photos(
    photo_analyses: list[dict[str, Any]],
    *,
    kategori_secim: str | None = None,
) -> dict[str, Any]:
    """Tüm fotoğraf analizlerinden upload/re-analyze için birleşik AI sonucu."""
    if not photo_analyses:
        return {
            "kategori": kategori_secim or "Diğer",
            "durum": "Temiz",
            "risk_skoru": 0,
            "guvenli": True,
        }

    primary = pick_primary_photo_analysis(photo_analyses)
    raw = dict(primary.get("raw") or {})
    max_risk = max(int(p.get("risk_score", 0)) for p in photo_analyses)
    max_confidence = max(float(p.get("confidence", 0)) for p in photo_analyses)
    raw["risk_skoru"] = max(int(raw.get("risk_skoru", 0)), max_risk)
    raw["confidence"] = max(float(raw.get("confidence", 0)), max_confidence)
    if kategori_secim and kategori_secim.strip():
        raw.setdefault("kategori", kategori_secim.strip())
    raw["photo_analyses"] = photo_analyses
    raw["vision_analysis"] = merge_photo_analyses(photo_analyses)
    return raw


def analyze_upload_photos(
    photo_files: list[str],
    tur: str,
    baslik: str | None,
    aciklama: str | None,
    *,
    kategori_secim: str | None = None,
    analyze_fn=None,
) -> dict[str, Any]:
    """Upload akışı: tüm fotoğrafları analiz edip birleşik moderasyon sonucu döner."""
    photo_analyses = analyze_listing_photos(
        photo_files, tur, baslik, aciklama, analyze_fn=analyze_fn
    )
    return build_merged_ai_sonuc_from_photos(
        photo_analyses, kategori_secim=kategori_secim
    )
