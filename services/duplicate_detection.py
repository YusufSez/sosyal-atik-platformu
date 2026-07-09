"""Duplicate Detection — benzer ilan karşılaştırması."""

from __future__ import annotations

import json
import re
from datetime import timedelta
from difflib import SequenceMatcher
from typing import Any

from constants import (
    DUPLICATE_LOCATION_EPSILON,
    DUPLICATE_LOOKBACK_DAYS,
    DUPLICATE_MATCH_THRESHOLD,
    DUPLICATE_MAX_CANDIDATES,
)
from models import Atik, Kaynak, User
from services.photo_hash import photo_file_hash
from utils import utc_now


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def _text_similarity(a: str, b: str) -> float:
    if not a or not b:
        return 0.0
    return SequenceMatcher(None, a, b).ratio()


def _location_match(lat1: float | None, lon1: float | None, lat2: float | None, lon2: float | None) -> bool:
    if lat1 is None or lon1 is None or lat2 is None or lon2 is None:
        return False
    return abs(lat1 - lat2) <= DUPLICATE_LOCATION_EPSILON and abs(lon1 - lon2) <= DUPLICATE_LOCATION_EPSILON


def _candidate_ilanlar(exclude_tur: str | None, exclude_id: int | None) -> list[dict]:
    """Son ilanlar (atik + kaynak birleşik)."""
    since = utc_now() - timedelta(days=DUPLICATE_LOOKBACK_DAYS)
    items: list[dict] = []
    for tur, model in (("atik", Atik), ("kaynak", Kaynak)):
        q = model.query.filter(model.tarih >= since).order_by(model.id.desc()).limit(DUPLICATE_MAX_CANDIDATES)
        for ilan in q.all():
            if exclude_tur == tur and exclude_id == ilan.id:
                continue
            photo_hash = photo_file_hash(getattr(ilan, "resim", None))
            items.append({
                "tur": tur,
                "ilan_id": ilan.id,
                "baslik": ilan.baslik,
                "aciklama": ilan.aciklama,
                "kategori": getattr(ilan, "kategori", None),
                "latitude": ilan.latitude,
                "longitude": ilan.longitude,
                "user_id": ilan.user_id,
                "tarih": ilan.tarih,
                "photo_hash": photo_hash,
            })
    return items


def _compare_ilan(
    *,
    baslik: str,
    aciklama: str,
    kategori: str | None,
    latitude: float | None,
    longitude: float | None,
    user_id: int,
    photo_hashes: list[str],
    candidate: dict,
) -> tuple[int, list[str]]:
    """Tek aday ile duplicate skoru ve nedenleri."""
    score = 0
    reasons: list[str] = []
    norm_baslik = _normalize_text(baslik)
    norm_aciklama = _normalize_text(aciklama)
    cand_baslik = _normalize_text(candidate.get("baslik"))
    cand_aciklama = _normalize_text(candidate.get("aciklama"))

    if norm_baslik and cand_baslik:
        if norm_baslik == cand_baslik:
            score += 25
            reasons.append("Aynı başlık")
        elif _text_similarity(norm_baslik, cand_baslik) >= 0.85:
            score += 15
            reasons.append("Benzer başlık")

    if norm_aciklama and cand_aciklama:
        if norm_aciklama == cand_aciklama:
            score += 30
            reasons.append("Aynı açıklama")
        elif _text_similarity(norm_aciklama, cand_aciklama) >= 0.8:
            score += 20
            reasons.append("Benzer açıklama")

    cand_hash = candidate.get("photo_hash")
    if photo_hashes and cand_hash and cand_hash in photo_hashes:
        score += 30
        reasons.append("Aynı fotoğraf hash")

    if kategori and candidate.get("kategori") and kategori == candidate["kategori"]:
        score += 5
        reasons.append("Aynı kategori")

    if _location_match(latitude, longitude, candidate.get("latitude"), candidate.get("longitude")):
        score += 10
        reasons.append("Aynı konum")

    if user_id and candidate.get("user_id") == user_id:
        score += 10
        reasons.append("Aynı kullanıcı")

    return min(100, score), reasons


def detect_duplicates(
    *,
    baslik: str,
    aciklama: str,
    tur: str,
    user_id: int,
    kategori: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    photo_hashes: list[str] | None = None,
    exclude_ilan_id: int | None = None,
) -> dict[str, Any]:
    """
    Duplicate Score ve benzer ilan listesi.
    Döner: {score, reasons, matches: [{tur, ilan_id, baslik, score, reasons}]}
    """
    hashes = photo_hashes or []
    candidates = _candidate_ilanlar(tur, exclude_ilan_id)
    matches: list[dict[str, Any]] = []
    all_reasons: list[str] = []
    best_score = 0

    for cand in candidates:
        cand_score, cand_reasons = _compare_ilan(
            baslik=baslik,
            aciklama=aciklama,
            kategori=kategori,
            latitude=latitude,
            longitude=longitude,
            user_id=user_id,
            photo_hashes=hashes,
            candidate=cand,
        )
        if cand_score >= DUPLICATE_MATCH_THRESHOLD:
            matches.append({
                "tur": cand["tur"],
                "ilan_id": cand["ilan_id"],
                "baslik": cand["baslik"],
                "score": cand_score,
                "reasons": cand_reasons,
                "kategori": cand.get("kategori"),
            })
        if cand_score > best_score:
            best_score = cand_score
            all_reasons = cand_reasons

    matches.sort(key=lambda m: m["score"], reverse=True)
    return {
        "score": best_score,
        "reasons": all_reasons,
        "matches": matches[:10],
    }


def duplicate_matches_from_json(raw: str | None) -> list[dict]:
    try:
        return json.loads(raw or "[]")
    except json.JSONDecodeError:
        return []
