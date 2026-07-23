"""Municipal waste center harita / API sorguları (bbox, nearby, filtreler)."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy import func

from models import MunicipalWasteCenter
from utils import mesafe_hesapla

DEFAULT_NEARBY_LIMIT = 20
DEFAULT_BBOX_LIMIT = 2500
MAX_LIMIT = 5000


def _row_payload(row: MunicipalWasteCenter, *, mesafe: float | None = None) -> dict[str, Any]:
    payload = {
        "id": row.id,
        "ad": row.name,
        "lat": row.latitude,
        "lng": row.longitude,
        "adres": row.address or "",
        "source": row.source,
        "source_name": row.source_name,
        "facility_type": row.facility_type,
        "district": row.district,
        "city": row.city,
        "waste_types": row.waste_types_list,
        "image_url": row.image_url,
        "is_active": row.is_active,
    }
    if mesafe is not None:
        payload["mesafe"] = round(mesafe, 2)
    return payload


def _parse_bbox(args: dict[str, Any]) -> tuple[float, float, float, float] | None:
    try:
        north = float(args.get("north"))
        south = float(args.get("south"))
        east = float(args.get("east"))
        west = float(args.get("west"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= south <= north <= 90):
        return None
    if not (-180 <= west <= 180 and -180 <= east <= 180):
        return None
    return north, south, east, west


def _clamp_limit(raw: Any, *, default: int) -> int:
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    return max(1, min(value, MAX_LIMIT))


def query_centers(
    *,
    source: str | None = None,
    city: str | None = None,
    district: str | None = None,
    facility_type: str | None = None,
    waste_type: str | None = None,
    include_inactive: bool = False,
    north: float | None = None,
    south: float | None = None,
    east: float | None = None,
    west: float | None = None,
    lat: float | None = None,
    lng: float | None = None,
    nearby: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """
    Filtre + bbox veya nearby sorgusu.

    nearby=True ise lat/lng zorunlu; mesafe sıralı top-N döner.
    bbox verilmişse yalnızca görünür alan içindeki kayıtlar (limit ile).
    """
    query = MunicipalWasteCenter.query
    if not include_inactive:
        query = query.filter_by(is_active=True)
    if source:
        query = query.filter(MunicipalWasteCenter.source == source.strip().lower())
    if city:
        query = query.filter(func.lower(MunicipalWasteCenter.city) == city.strip().lower())
    if district:
        query = query.filter(func.lower(MunicipalWasteCenter.district) == district.strip().lower())
    if facility_type:
        query = query.filter(
            func.lower(MunicipalWasteCenter.facility_type) == facility_type.strip().lower()
        )
    if waste_type:
        # waste_types JSON text — kanonik ad parçası araması
        needle = waste_type.strip()
        query = query.filter(MunicipalWasteCenter.waste_types.ilike(f"%{needle}%"))

    if nearby:
        if lat is None or lng is None:
            return []
        rows = query.all()
        ranked: list[tuple[float, MunicipalWasteCenter]] = []
        for row in rows:
            dist = mesafe_hesapla(lat, lng, row.latitude, row.longitude)
            ranked.append((dist, row))
        ranked.sort(key=lambda item: item[0])
        cap = limit if limit is not None else DEFAULT_NEARBY_LIMIT
        return [_row_payload(row, mesafe=dist) for dist, row in ranked[:cap]]

    if None not in (north, south, east, west):
        # Antimeridian (west > east) basit destek: OR iki dilim
        if west <= east:
            query = query.filter(
                MunicipalWasteCenter.latitude <= north,
                MunicipalWasteCenter.latitude >= south,
                MunicipalWasteCenter.longitude <= east,
                MunicipalWasteCenter.longitude >= west,
            )
        else:
            query = query.filter(
                MunicipalWasteCenter.latitude <= north,
                MunicipalWasteCenter.latitude >= south,
                db_or_longitude_wrap(west, east),
            )
        cap = limit if limit is not None else DEFAULT_BBOX_LIMIT
        rows = query.order_by(MunicipalWasteCenter.name.asc()).limit(cap).all()
        return [_row_payload(row) for row in rows]

    cap = limit if limit is not None else DEFAULT_BBOX_LIMIT
    rows = query.order_by(MunicipalWasteCenter.name.asc()).limit(cap).all()
    return [_row_payload(row) for row in rows]


def db_or_longitude_wrap(west: float, east: float):
    from sqlalchemy import or_

    return or_(
        MunicipalWasteCenter.longitude >= west,
        MunicipalWasteCenter.longitude <= east,
    )


def centers_as_map_payload(
    *,
    source: str | None = None,
    city: str | None = None,
    district: str | None = None,
    facility_type: str | None = None,
    waste_type: str | None = None,
    include_inactive: bool = False,
    bbox: tuple[float, float, float, float] | None = None,
    lat: float | None = None,
    lng: float | None = None,
    nearby: bool = False,
    limit: int | None = None,
) -> list[dict]:
    """Geriye uyumlu sarmalayıcı + genişletilmiş filtreler."""
    north = south = east = west = None
    if bbox:
        north, south, east, west = bbox
    return query_centers(
        source=source,
        city=city,
        district=district,
        facility_type=facility_type,
        waste_type=waste_type,
        include_inactive=include_inactive,
        north=north,
        south=south,
        east=east,
        west=west,
        lat=lat,
        lng=lng,
        nearby=nearby,
        limit=limit,
    )


def filter_meta(*, source: str | None = None) -> dict[str, Any]:
    """
    Harita filtre paneli meta.

    İl/ilçe listeleri DB'den üretilmez — resmi Türkiye sözlüğü için
    /api/turkey/provinces ve /api/turkey/districts kullanılır.
    Burada yalnızca kayıt bağımlı filtreler (tesis tipi, atık türü) döner.
    """
    query = MunicipalWasteCenter.query.filter_by(is_active=True)
    if source:
        query = query.filter(MunicipalWasteCenter.source == source.strip().lower())

    facility_types = sorted(
        {
            (f or "").strip()
            for (f,) in query.with_entities(MunicipalWasteCenter.facility_type).distinct().all()
            if f
        },
        key=str.casefold,
    )

    waste_types: set[str] = set()
    for (raw,) in query.with_entities(MunicipalWasteCenter.waste_types).all():
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except (TypeError, ValueError):
            continue
        if isinstance(data, list):
            for item in data:
                if isinstance(item, str) and item.strip():
                    waste_types.add(item.strip())

    return {
        "facility_types": facility_types,
        "waste_types": sorted(waste_types, key=str.casefold),
        "geography": {
            "provinces_url": "/api/turkey/provinces",
            "districts_url": "/api/turkey/districts",
        },
    }


def parse_request_args(args) -> dict[str, Any]:
    """Flask request.args → query_centers kwargs."""
    source = (args.get("source") or "").strip().lower() or None
    city = (args.get("city") or "").strip() or None
    district = (args.get("district") or args.get("ilce") or "").strip() or None
    facility_type = (args.get("facility_type") or "").strip() or None
    waste_type = (args.get("waste_type") or args.get("waste_types") or "").strip() or None
    include_inactive = (args.get("include_inactive") or "").strip().lower() in {
        "1",
        "true",
        "yes",
    }
    nearby = (args.get("nearby") or "").strip().lower() in {"1", "true", "yes"}
    lat = lng = None
    try:
        if args.get("lat") is not None and args.get("lng") is not None:
            lat = float(args.get("lat"))
            lng = float(args.get("lng"))
    except (TypeError, ValueError):
        lat = lng = None

    bbox = _parse_bbox(
        {
            "north": args.get("north"),
            "south": args.get("south"),
            "east": args.get("east"),
            "west": args.get("west"),
        }
    )
    north = south = east = west = None
    if bbox:
        north, south, east, west = bbox

    default_limit = DEFAULT_NEARBY_LIMIT if nearby else DEFAULT_BBOX_LIMIT
    limit = _clamp_limit(args.get("limit"), default=default_limit)

    return {
        "source": source,
        "city": city,
        "district": district,
        "facility_type": facility_type,
        "waste_type": waste_type,
        "include_inactive": include_inactive,
        "north": north,
        "south": south,
        "east": east,
        "west": west,
        "lat": lat,
        "lng": lng,
        "nearby": nearby,
        "limit": limit,
    }
