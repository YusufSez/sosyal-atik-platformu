"""Upload sırasında spam + duplicate sinyallerini birleştirir."""

from __future__ import annotations

from typing import Any

from services.duplicate_detection import detect_duplicates
from services.photo_hash import photo_hashes_for_files
from services.spam_score import compute_spam_score
from services.upload_meta import device_fingerprint, request_ip, request_user_agent


def enrich_upload_signals(
    ai_sonuc: dict,
    *,
    tur: str,
    ilan_id: int | None,
    baslik: str,
    aciklama: str,
    user_id: int,
    kategori: str | None = None,
    latitude: float | None = None,
    longitude: float | None = None,
    photo_files: list[str] | None = None,
    upload_ip: str | None = None,
    user_agent: str | None = None,
) -> dict:
    """ai_sonuc'a spam/duplicate skorlarını ekler."""
    ip = upload_ip if upload_ip is not None else request_ip()
    ua = user_agent if user_agent is not None else request_user_agent()
    fp = device_fingerprint(ua)
    hashes = photo_hashes_for_files(photo_files or [])

    spam = compute_spam_score(
        baslik=baslik,
        aciklama=aciklama,
        user_id=user_id,
        upload_ip=ip,
        device_fingerprint=fp,
        photo_hashes=hashes,
        exclude_tur=tur,
        exclude_ilan_id=ilan_id,
    )
    dup = detect_duplicates(
        baslik=baslik,
        aciklama=aciklama,
        tur=tur,
        user_id=user_id,
        kategori=kategori,
        latitude=latitude,
        longitude=longitude,
        photo_hashes=hashes,
        exclude_ilan_id=ilan_id,
    )

    ai_sonuc["spam_score"] = spam["score"]
    ai_sonuc["spam_reasons"] = spam["reasons"]
    ai_sonuc["duplicate_score"] = dup["score"]
    ai_sonuc["duplicate_reasons"] = dup["reasons"]
    ai_sonuc["duplicate_matches"] = dup["matches"]
    ai_sonuc["upload_ip"] = ip
    ai_sonuc["upload_user_agent"] = ua
    ai_sonuc["device_fingerprint"] = fp
    ai_sonuc["photo_hashes"] = hashes
    return ai_sonuc
