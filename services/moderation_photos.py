"""İlan fotoğrafları için AI görsel analizi."""

from __future__ import annotations

import os
from typing import Any

from flask import current_app


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
        path = os.path.join(upload_folder, dosya)
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
    primary = max(photo_analyses, key=lambda p: p.get("confidence", 0))
    return {
        "photo_count": len(photo_analyses),
        "max_risk": max_risk,
        "primary_label": primary.get("label"),
        "primary_confidence": primary.get("confidence"),
        "photos": photo_analyses,
    }
