"""Spam Score (0-100) — davranışsal sinyaller."""

from __future__ import annotations

import re
from collections import Counter
from datetime import timedelta
from typing import Any

from constants import (
    SPAM_DEVICE_LOOKBACK_DAYS,
    SPAM_FAST_CREATE_MINUTES,
    SPAM_LOOKBACK_HOURS,
    SPAM_SHORT_DESC_MIN_LEN,
)
from extensions import db
from models import Atik, IlanModerasyonAnaliz, Kaynak
from utils import utc_now


def _normalize_text(text: str | None) -> str:
    if not text:
        return ""
    return re.sub(r"\s+", " ", text.strip().lower())


def _word_repetition_ratio(text: str) -> float:
    words = re.findall(r"\w+", text.lower())
    if len(words) < 4:
        return 0.0
    counts = Counter(words)
    repeated = sum(c - 1 for c in counts.values() if c > 1)
    return repeated / len(words)


def _recent_ilanlar(user_id: int, hours: int = 24) -> list[dict]:
    """Kullanıcının son ilanları (atik + kaynak)."""
    since = utc_now() - timedelta(hours=hours)
    items: list[dict] = []
    for tur, model in (("atik", Atik), ("kaynak", Kaynak)):
        for ilan in model.query.filter(
            model.user_id == user_id,
            model.tarih >= since,
        ).order_by(model.tarih.desc()).limit(20).all():
            items.append({
                "tur": tur,
                "ilan_id": ilan.id,
                "baslik": ilan.baslik,
                "aciklama": ilan.aciklama,
                "tarih": ilan.tarih,
                "kategori": getattr(ilan, "kategori", None),
            })
    items.sort(key=lambda x: x["tarih"] or utc_now(), reverse=True)
    return items


def _find_title_match(baslik: str, exclude_tur: str | None, exclude_id: int | None) -> bool:
    norm = _normalize_text(baslik)
    if not norm:
        return False
    for tur, model in (("atik", Atik), ("kaynak", Kaynak)):
        for ilan in model.query.filter(model.baslik.isnot(None)).order_by(model.id.desc()).limit(200).all():
            if exclude_tur == tur and exclude_id == ilan.id:
                continue
            if _normalize_text(ilan.baslik) == norm:
                return True
    return False


def _find_description_match(aciklama: str, exclude_tur: str | None, exclude_id: int | None) -> bool:
    norm = _normalize_text(aciklama)
    if len(norm) < 10:
        return False
    for tur, model in (("atik", Atik), ("kaynak", Kaynak)):
        for ilan in model.query.filter(model.aciklama.isnot(None)).order_by(model.id.desc()).limit(200).all():
            if exclude_tur == tur and exclude_id == ilan.id:
                continue
            if _normalize_text(ilan.aciklama) == norm:
                return True
    return False


def _same_ip_count(ip: str | None, hours: int = SPAM_LOOKBACK_HOURS) -> int:
    if not ip:
        return 0
    since = utc_now() - timedelta(hours=hours)
    return IlanModerasyonAnaliz.query.filter(
        IlanModerasyonAnaliz.upload_ip == ip,
        IlanModerasyonAnaliz.created_at >= since,
    ).count()


def _same_device_count(fingerprint: str | None, days: int = SPAM_DEVICE_LOOKBACK_DAYS) -> int:
    if not fingerprint:
        return 0
    since = utc_now() - timedelta(days=days)
    return IlanModerasyonAnaliz.query.filter(
        IlanModerasyonAnaliz.device_fingerprint == fingerprint,
        IlanModerasyonAnaliz.created_at >= since,
    ).count()


def _photo_hash_exists(hashes: list[str], exclude_tur: str | None, exclude_id: int | None) -> bool:
    if not hashes:
        return False
    hash_set = set(hashes)
    for analiz in IlanModerasyonAnaliz.query.filter(
        IlanModerasyonAnaliz.photo_hashes_json.isnot(None)
    ).order_by(IlanModerasyonAnaliz.id.desc()).limit(300).all():
        if exclude_tur == analiz.tur:
            ilan_id = analiz.kaynak_id or analiz.atik_id
            if exclude_id and ilan_id == exclude_id:
                continue
        try:
            import json
            stored = json.loads(analiz.photo_hashes_json or "[]")
        except json.JSONDecodeError:
            continue
        if hash_set.intersection(stored):
            return True
    return False


def compute_spam_score(
    *,
    baslik: str,
    aciklama: str,
    user_id: int,
    upload_ip: str | None = None,
    device_fingerprint: str | None = None,
    photo_hashes: list[str] | None = None,
    exclude_tur: str | None = None,
    exclude_ilan_id: int | None = None,
) -> dict[str, Any]:
    """
    Spam Score üretir (0-100).
    Döner: {score, reasons: [{code, label, points}]}
    """
    reasons: list[dict[str, Any]] = []
    score = 0

    norm_baslik = _normalize_text(baslik)
    norm_aciklama = _normalize_text(aciklama)

    if len(norm_aciklama) < SPAM_SHORT_DESC_MIN_LEN:
        reasons.append({"code": "short_description", "label": "Çok kısa açıklama", "points": 10})
        score += 10

    rep_ratio = _word_repetition_ratio(aciklama or "")
    if rep_ratio >= 0.4:
        reasons.append({"code": "repeating_words", "label": "Tekrarlayan kelimeler", "points": 10})
        score += 10

    if _find_title_match(baslik, exclude_tur, exclude_ilan_id):
        reasons.append({"code": "same_title", "label": "Aynı başlık", "points": 18})
        score += 18

    if _find_description_match(aciklama, exclude_tur, exclude_ilan_id):
        reasons.append({"code": "same_description", "label": "Aynı açıklama", "points": 22})
        score += 22

    if _photo_hash_exists(photo_hashes or [], exclude_tur, exclude_ilan_id):
        reasons.append({"code": "same_photo", "label": "Aynı fotoğraf", "points": 25})
        score += 25

    ip_count = _same_ip_count(upload_ip)
    if ip_count >= 1:
        reasons.append({"code": "same_ip", "label": f"Aynı IP ({ip_count + 1} yükleme)", "points": 12})
        score += 12

    device_count = _same_device_count(device_fingerprint)
    if device_count >= 1:
        reasons.append({"code": "same_device", "label": f"Aynı cihaz ({device_count + 1} yükleme)", "points": 10})
        score += 10

    recent = _recent_ilanlar(user_id, hours=1)
    if len(recent) >= 2:
        reasons.append({"code": "same_user_burst", "label": "Aynı kullanıcı — hızlı çoklu ilan", "points": 8})
        score += 8

    user_recent = _recent_ilanlar(user_id, hours=24)
    if user_recent:
        last = user_recent[0]
        if exclude_tur == last["tur"] and exclude_ilan_id == last["ilan_id"]:
            if len(user_recent) > 1:
                last = user_recent[1]
            else:
                last = None
        if last and last.get("tarih"):
            delta = utc_now() - last["tarih"]
            if delta.total_seconds() < SPAM_FAST_CREATE_MINUTES * 60:
                reasons.append({
                    "code": "fast_creation",
                    "label": f"Çok hızlı ilan oluşturma (<{SPAM_FAST_CREATE_MINUTES} dk)",
                    "points": 15,
                })
                score += 15

    if user_id and len(_recent_ilanlar(user_id, hours=24)) >= 5:
        reasons.append({"code": "same_user", "label": "Aynı kullanıcı — yoğun yükleme", "points": 8})
        score += 8

    return {"score": min(100, score), "reasons": reasons}
