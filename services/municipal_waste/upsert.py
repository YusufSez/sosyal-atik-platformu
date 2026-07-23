from __future__ import annotations

import json
import logging
from datetime import timedelta
from typing import Iterable

from extensions import db
from models import MunicipalWasteCenter
from services.municipal_waste.base import STALE_DAYS_DEFAULT
from services.municipal_waste.types import NormalizedCenter, SyncStats
from utils import tr_time

logger = logging.getLogger(__name__)

# UPSERT sırasında karşılaştırılan alanlar (external_key / coords ayrı)
_UPDATABLE_FIELDS = (
    "name",
    "facility_type",
    "address",
    "district",
    "city",
    "image_url",
    "description",
    "waste_types",
    "source_name",
)


def _waste_types_json(values: list[str]) -> str:
    return json.dumps(values, ensure_ascii=False)


def _values_equal(key: str, old, new) -> bool:
    if key in {"latitude", "longitude"}:
        try:
            return abs(float(old) - float(new)) < 1e-8
        except (TypeError, ValueError):
            return old == new
    return old == new


def _payload_from_center(center: NormalizedCenter) -> dict:
    district = (center.district[:100] if center.district else None)
    return {
        "name": center.name[:200],
        "facility_type": (center.facility_type or "")[:120] or None,
        "address": (center.address or "")[:255] or None,
        "district": district,
        "city": (center.city or "")[:100],
        "latitude": float(center.latitude),
        "longitude": float(center.longitude),
        "image_url": ((center.image_url or "")[:500] or None),
        "waste_types": _waste_types_json(center.waste_types),
        "description": center.description,
        "source": center.source[:40],
        "source_name": center.source_name[:150],
        "external_key": center.external_key[:120],
        "is_active": True,
    }


def _apply_fields(row: MunicipalWasteCenter, center: NormalizedCenter, *, now) -> bool:
    """
    Alanları günceller.
    last_seen_at her zaman yenilenir.
    İçerik alanlarından biri değişirse updated_at da yenilenir ve True döner.
    """
    payload = _payload_from_center(center)
    content_changed = False
    for key in _UPDATABLE_FIELDS:
        value = payload[key]
        if not _values_equal(key, getattr(row, key), value):
            setattr(row, key, value)
            content_changed = True

    # Koordinat / anahtar her zaman hizalanır (legacy key migrasyonu)
    for key in ("latitude", "longitude", "external_key", "source", "is_active"):
        value = payload[key]
        if not _values_equal(key, getattr(row, key), value):
            setattr(row, key, value)
            if key != "is_active":
                content_changed = True

    row.last_seen_at = now
    if content_changed:
        row.updated_at = now
    return content_changed


def _legacy_coord_lookup(
    rows: list[MunicipalWasteCenter],
    *,
    latitude: float,
    longitude: float,
) -> MunicipalWasteCenter | None:
    """Eski (isim tabanlı) external_key kayıtlarını koordinattan bul."""
    for row in rows:
        try:
            if abs(float(row.latitude) - latitude) < 1e-6 and abs(float(row.longitude) - longitude) < 1e-6:
                return row
        except (TypeError, ValueError):
            continue
    return None


def _inactivate_stale(*, source: str, stale_days: int, now) -> int:
    if stale_days <= 0:
        return 0
    cutoff = now - timedelta(days=stale_days)
    q = MunicipalWasteCenter.query.filter(
        MunicipalWasteCenter.source == source,
        MunicipalWasteCenter.is_active.is_(True),
        MunicipalWasteCenter.last_seen_at.isnot(None),
        MunicipalWasteCenter.last_seen_at < cutoff,
    )
    count = 0
    for row in q.all():
        row.is_active = False
        row.updated_at = now
        count += 1
    return count


def upsert_centers(
    centers: Iterable[NormalizedCenter],
    *,
    source: str,
    source_name: str = "",
    stale_days: int = STALE_DAYS_DEFAULT,
) -> SyncStats:
    """
    Tekilleştirme: (source, external_key) where external_key = SHA256(source+lat+lng).

    Görülen kayıtların last_seen_at değeri güncellenir.
    stale_days boyunca görülmeyen aktif kayıtlar soft-delete (is_active=False) edilir.
    """
    stats = SyncStats(source=source, source_name=source_name)
    now = tr_time()
    existing_rows = MunicipalWasteCenter.query.filter_by(source=source).all()
    by_external = {row.external_key: row for row in existing_rows if row.external_key}
    legacy_pool = list(existing_rows)
    seen_keys: set[str] = set()

    for center in centers:
        stats.found += 1
        if not center.external_key:
            stats.errors += 1
            continue
        dedupe = f"{center.source}:{center.external_key}"
        if dedupe in seen_keys:
            stats.skipped += 1
            continue
        seen_keys.add(dedupe)

        try:
            existing = by_external.get(center.external_key)
            if existing is None:
                existing = _legacy_coord_lookup(
                    legacy_pool, latitude=center.latitude, longitude=center.longitude
                )
                if existing is not None:
                    # Eski anahtarı yeni SHA256'ya taşı
                    by_external.pop(existing.external_key, None)
                    existing.external_key = center.external_key
                    by_external[center.external_key] = existing

            if existing is None:
                row = MunicipalWasteCenter(created_at=now, updated_at=now, last_seen_at=now)
                _apply_fields(row, center, now=now)
                db.session.add(row)
                by_external[center.external_key] = row
                legacy_pool.append(row)
                stats.created += 1
            else:
                if _apply_fields(existing, center, now=now):
                    stats.updated += 1
                else:
                    stats.skipped += 1
        except Exception:
            logger.exception(
                "UPSERT hatası source=%s key=%s name=%s",
                center.source,
                center.external_key,
                center.name,
            )
            stats.errors += 1
            db.session.rollback()
            existing_rows = MunicipalWasteCenter.query.filter_by(source=source).all()
            by_external = {row.external_key: row for row in existing_rows if row.external_key}
            legacy_pool = list(existing_rows)
            continue

    try:
        stats.inactivated = _inactivate_stale(source=source, stale_days=stale_days, now=now)
        db.session.commit()
    except Exception:
        logger.exception("municipal_waste_centers commit başarısız (source=%s)", source)
        db.session.rollback()
        raise

    logger.info(
        "municipal_sync source=%s found=%s created=%s updated=%s skipped=%s "
        "inactivated=%s errors=%s",
        source,
        stats.found,
        stats.created,
        stats.updated,
        stats.skipped,
        stats.inactivated,
        stats.errors,
    )
    return stats


# Geriye uyumluluk: harita payload sorgusu query modülünde
from services.municipal_waste.query import centers_as_map_payload  # noqa: E402
