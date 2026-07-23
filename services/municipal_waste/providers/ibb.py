from __future__ import annotations

import logging
import re
from typing import Any

import requests

from services.municipal_waste.base import MunicipalSourceProvider
from services.municipal_waste.text_utils import clean_text, tr_lower, tr_title
from services.municipal_waste.types import NormalizedCenter
from utils import mesafe_hesapla

logger = logging.getLogger(__name__)

IBB_ATIK_RESOURCE_ID = "0124b01f-cfe7-4af8-ac80-88cb44ab5d64"
IBB_DATASTORE_URL = "https://data.ibb.gov.tr/api/3/action/datastore_search"
DEFAULT_TIMEOUT_SEC = 10
IBB_CITY = "İstanbul"
IBB_FACILITY_TYPE = "Atık Toplama Merkezi"


def fetch_ibb_merkezleri_live(*, limit: int = 200, timeout: int = DEFAULT_TIMEOUT_SEC) -> list[dict[str, Any]]:
    """
    İBB açık veri API'sinden atık toplama merkezlerini çeker.

    Dönüş şekli mevcut harita/API sözleşmesiyle uyumludur; city her zaman İstanbul:
    [{id, ad, lat, lng, adres, city, source, facility_type, ...}, ...]
    """
    url = f"{IBB_DATASTORE_URL}?resource_id={IBB_ATIK_RESOURCE_ID}&limit={limit}"
    try:
        response = requests.get(url, timeout=timeout)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("İBB açık veri isteği başarısız: %s", exc)
        return []

    results = data.get("result", {}).get("records", []) if isinstance(data, dict) else []
    merkezler: list[dict[str, Any]] = []
    for i, item in enumerate(results):
        try:
            shape = item.get("shape")
            lat, lng = None, None
            if shape:
                match = re.search(r"POINT\s*\(([^ ]+)\s+([^)]+)\)", str(shape))
                if match:
                    lng = float(match.group(1))
                    lat = float(match.group(2))
            if lat is None or lng is None:
                continue
            name = item.get("facility_name") or "Atık Merkezi"
            merkezler.append(
                {
                    "id": i,
                    "ad": name,
                    "lat": lat,
                    "lng": lng,
                    "adres": item.get("address", "") or "",
                    "city": IBB_CITY,
                    "district": None,
                    "source": "ibb",
                    "source_name": "İstanbul Büyükşehir Belediyesi",
                    "facility_type": IBB_FACILITY_TYPE,
                    "waste_types": [],
                }
            )
        except (TypeError, ValueError):
            continue
    return merkezler


def filter_ibb_live_centers(
    centers: list[dict[str, Any]],
    *,
    city: str | None = None,
    district: str | None = None,
    facility_type: str | None = None,
    waste_type: str | None = None,
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
    Canlı İBB listesine harita filtrelerini uygular.

    city başka bir il ise boş döner; İstanbul / boş city → kayıtlar kalır.
    facility_type / waste_type İBB canlı katmanını sıfırlamaz (eşleşmezse atlanır).
    """
    if city and tr_lower(city.strip()) != tr_lower(IBB_CITY):
        return []

    # İlçe seçimi İBB canlı kayıtlarında yok; city=İstanbul iken ilçe İBB'yi gizlemez.
    _ = district

    rows = list(centers)
    if facility_type:
        needle = tr_lower(facility_type.strip())
        matched = [
            r
            for r in rows
            if tr_lower(str(r.get("facility_type") or "")) == needle
        ]
        # Eşleşme yoksa İBB katmanını yanlışlıkla sıfırlama — filtreyi atla
        if matched:
            rows = matched

    if waste_type:
        needle = waste_type.strip()
        matched = []
        for r in rows:
            types = r.get("waste_types") or []
            if isinstance(types, list) and any(
                isinstance(t, str) and needle.casefold() in t.casefold() for t in types
            ):
                matched.append(r)
        if matched:
            rows = matched

    if nearby:
        if lat is None or lng is None:
            return []
        ranked: list[tuple[float, dict[str, Any]]] = []
        for row in rows:
            try:
                dist = mesafe_hesapla(lat, lng, float(row["lat"]), float(row["lng"]))
            except (KeyError, TypeError, ValueError):
                continue
            item = dict(row)
            item["mesafe"] = round(dist, 2)
            ranked.append((dist, item))
        ranked.sort(key=lambda pair: pair[0])
        cap = limit if limit is not None else 20
        return [item for _, item in ranked[:cap]]

    if None not in (north, south, east, west):
        filtered: list[dict[str, Any]] = []
        for row in rows:
            try:
                rlat = float(row["lat"])
                rlng = float(row["lng"])
            except (KeyError, TypeError, ValueError):
                continue
            if not (south <= rlat <= north):
                continue
            if west <= east:
                if not (west <= rlng <= east):
                    continue
            else:
                if not (rlng >= west or rlng <= east):
                    continue
            filtered.append(row)
        rows = filtered

    if limit is not None:
        rows = rows[: max(1, int(limit))]
    return rows


class IbbMunicipalProvider(MunicipalSourceProvider):
    """
    İBB açık veri (CKAN) sağlayıcısı.

    Canlı harita yolu `fetch_ibb_merkezleri_live` ile aynı kaynaktan beslenir;
    bu sınıf isteğe bağlı DB senkronu için normalize eder.
    """

    source = "ibb"
    source_name = "İstanbul Büyükşehir Belediyesi"
    default_city = "İstanbul"

    def load_centers(
        self,
        *,
        limit: int = 500,
        timeout: int = DEFAULT_TIMEOUT_SEC,
        **_: Any,
    ) -> list[NormalizedCenter]:
        raw = fetch_ibb_merkezleri_live(limit=limit, timeout=timeout)
        centers: list[NormalizedCenter] = []
        for item in raw:
            try:
                lat = float(item["lat"])
                lng = float(item["lng"])
                name = clean_text(item.get("ad") or "Atık Merkezi", max_length=200) or "Atık Merkezi"
                address = clean_text(item.get("adres") or "", max_length=255)
                center = NormalizedCenter(
                    name=tr_title(name),
                    facility_type="Atık Toplama Merkezi",
                    address=address,
                    district=None,
                    city=self.default_city,
                    latitude=lat,
                    longitude=lng,
                    image_url=None,
                    waste_types=[],
                    description=tr_title(name),
                )
                centers.append(self.attach_metadata(center))
            except (KeyError, TypeError, ValueError):
                logger.exception("İBB kaydı normalize edilemedi: %s", item)
                continue
        logger.info("municipal_parse source=%s valid=%s", self.source, len(centers))
        return centers
