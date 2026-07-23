from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Any

from bs4 import BeautifulSoup

from services.municipal_waste.base import MunicipalSourceProvider, resolve_path
from services.municipal_waste.text_utils import (
    clean_text,
    parse_district_city,
    parse_title_parts,
    unescape_html_text,
)
from services.municipal_waste.types import NormalizedCenter

logger = logging.getLogger(__name__)

DEFAULT_KONYA_SOURCE = (
    Path(__file__).resolve().parents[3] / "data" / "municipal_sources" / "konya_sifiratik.html"
)

_JS_ARRAY_START = re.compile(r"var\s+konumlar\s*=\s*\[", re.IGNORECASE)


def extract_konumlar_array(raw_text: str) -> list[dict[str, Any]]:
    """
    Sayfa HTML/JS içeriğinden `var konumlar = [...]` dizisini güvenli ayıklar.
    eval / exec kullanılmaz.
    """
    match = _JS_ARRAY_START.search(raw_text)
    if not match:
        raise ValueError("Kaynak dosyasında 'var konumlar = [' bulunamadı.")

    start = raw_text.find("[", match.start())
    if start < 0:
        raise ValueError("konumlar dizisi başlangıcı okunamadı.")

    depth = 0
    in_string = False
    escape = False
    end: int | None = None
    for idx in range(start, len(raw_text)):
        ch = raw_text[idx]
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                end = idx + 1
                break

    if end is None:
        raise ValueError("konumlar dizisi kapanışı bulunamadı (bozuk JS).")

    try:
        data = json.loads(raw_text[start:end])
    except json.JSONDecodeError as exc:
        raise ValueError(f"konumlar dizisi JSON olarak ayrıştırılamadı: {exc}") from exc

    if not isinstance(data, list):
        raise ValueError("konumlar beklenen dizi tipinde değil.")
    return data


def _first_text(nodes) -> str:
    for node in nodes:
        text = clean_text(node.get_text(" ", strip=True))
        if text:
            return text
    return ""


def parse_aciklama_html(aciklama: str) -> tuple[str, str, str | None]:
    """
    aciklama HTML → (başlık, adres, görsel_url).

    BeautifulSoup DOM ile defensive parse: span/div değişimine dayanıklı.
    """
    html = unescape_html_text(aciklama).replace("\\/", "/")
    if not html.strip():
        return "", "", None

    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        logger.exception("BeautifulSoup aciklama parse başarısız")
        return "", "", None

    image_url: str | None = None
    img = soup.find("img", src=True)
    if img and img.get("src"):
        image_url = str(img["src"]).replace("\\/", "/")

    address = ""
    loc = soup.select_one(".icon-location, [class*='icon-location'], .location")
    if loc:
        address = clean_text(loc.get_text(" ", strip=True))
    if not address:
        # Konum benzeri metin: İlçe/İL kalıbı
        for el in soup.find_all(["span", "div", "p", "li"]):
            text = clean_text(el.get_text(" ", strip=True))
            if text and "/" in text and len(text) < 200:
                address = text
                break

    title = ""
    content = soup.select_one(".mapContent, [class*='mapContent']")
    scope = content or soup
    # Konum ikonu dışındaki ilk anlamlı metin bloğu = başlık
    for el in scope.find_all(["span", "div", "strong", "h1", "h2", "h3", "h4", "p"]):
        classes = " ".join(el.get("class") or [])
        if "icon-location" in classes or "infoBtn" in classes:
            continue
        if el.find(class_=lambda c: c and "icon-location" in " ".join(c if isinstance(c, list) else [c])):
            continue
        text = clean_text(el.get_text(" ", strip=True))
        if not text or text == address:
            continue
        # Çocukların birleşik metni adresle aynıysa atla
        if address and text == address:
            continue
        title = text
        break

    if not title:
        title = _first_text(scope.find_all(string=True))

    return title, address, image_url


def record_to_center(
    item: dict[str, Any],
    *,
    provider: "KonyaMunicipalProvider | None" = None,
) -> NormalizedCenter | None:
    kor = item.get("kor") or {}
    try:
        lat = float(kor.get("lat"))
        lng = float(kor.get("lng"))
    except (TypeError, ValueError):
        return None
    if not (-90 <= lat <= 90 and -180 <= lng <= 180):
        return None

    title, address, image_url = parse_aciklama_html(str(item.get("aciklama") or ""))
    if not title and not address:
        return None

    prov = provider or KonyaMunicipalProvider()
    facility_type, name, waste_types = parse_title_parts(title)
    district, city = parse_district_city(address, default_city=prov.default_city)
    description = clean_text(title) or None

    center = NormalizedCenter(
        name=name,
        facility_type=facility_type,
        address=address or f"{district or ''}/{city}".strip("/"),
        district=district,
        city=city or prov.default_city,
        latitude=lat,
        longitude=lng,
        image_url=image_url,
        waste_types=waste_types,
        description=description,
    )
    return prov.attach_metadata(center)


class KonyaMunicipalProvider(MunicipalSourceProvider):
    source = "konya"
    source_name = "Konya Büyükşehir Belediyesi"
    default_city = "Konya"

    def load_centers(self, *, file_path: str | Path | None = None, **_: Any) -> list[NormalizedCenter]:
        path = resolve_path(file_path, default=DEFAULT_KONYA_SOURCE)
        logger.info(
            "municipal_load source=%s path=%s",
            self.source,
            path,
        )
        raw = path.read_text(encoding="utf-8", errors="replace")
        records = extract_konumlar_array(raw)
        centers: list[NormalizedCenter] = []
        errors = 0
        for idx, item in enumerate(records):
            if not isinstance(item, dict):
                errors += 1
                continue
            try:
                center = record_to_center(item, provider=self)
            except Exception:
                logger.exception("Konya kaydı ayrıştırılamadı (index=%s)", idx)
                errors += 1
                continue
            if center is None:
                errors += 1
                continue
            centers.append(center)
        logger.info(
            "municipal_parse source=%s raw=%s valid=%s errors=%s",
            self.source,
            len(records),
            len(centers),
            errors,
        )
        return centers
