from __future__ import annotations

import hashlib
import html
import re
import unicodedata

from utils.misc import sanitize_input

_CITY_DISTRICT_TAIL = re.compile(
    r"(?P<district>[A-ZÇĞİÖŞÜÂÊÎÔÛa-zçğıöşüâêîôû0-9.\s]+)\s*/\s*(?P<city>[A-ZÇĞİÖŞÜÂÊÎÔÛa-zçğıöşüâêîôû\s]+)\s*$"
)


def unescape_html_text(value: str | None) -> str:
    if not value:
        return ""
    text = html.unescape(str(value))
    if "&" in text:
        text = html.unescape(text)
    return text.strip()


def clean_text(value: str | None, *, max_length: int | None = None) -> str:
    return sanitize_input(unescape_html_text(value), max_length=max_length)


def tr_lower(value: str) -> str:
    return (
        value.replace("I", "ı")
        .replace("İ", "i")
        .replace("Ğ", "ğ")
        .replace("Ü", "ü")
        .replace("Ş", "ş")
        .replace("Ö", "ö")
        .replace("Ç", "ç")
        .lower()
    )


def tr_title(value: str) -> str:
    """Türkçe başlık biçimi (kelime başı büyük)."""
    text = clean_text(value)
    if not text:
        return ""
    parts: list[str] = []
    for token in re.split(r"(\s+|/|-)", text):
        if not token or token.isspace() or token in {"/", "-"}:
            parts.append(token)
            continue
        low = tr_lower(token)
        first, rest = low[:1], low[1:]
        if first == "i":
            first = "İ"
        else:
            first = first.upper()
        parts.append(first + rest)
    return "".join(parts)


def normalize_key(value: str) -> str:
    text = tr_lower(clean_text(value))
    # ASCII katman: Türkçe harfleri anahtar eşlemesi için sadeleştir
    text = (
        text.replace("ı", "i")
        .replace("ğ", "g")
        .replace("ü", "u")
        .replace("ş", "s")
        .replace("ö", "o")
        .replace("ç", "c")
        .replace("â", "a")
        .replace("ê", "e")
        .replace("î", "i")
        .replace("ô", "o")
        .replace("û", "u")
    )
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", text).strip()


def make_external_key(source: str, latitude: float, longitude: float) -> str:
    """
    Kararlı tekil anahtar: SHA256(source + lat + lng).

    İsim/adres değişse bile aynı koordinatta aynı kayıt kalır.
    """
    payload = f"{(source or '').strip().lower()}:{latitude:.6f}:{longitude:.6f}"
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# Geriye dönük takma ad
def coord_external_key(latitude: float, longitude: float, *, source: str = "", **_: object) -> str:
    return make_external_key(source, latitude, longitude)


def parse_district_city(address: str, *, default_city: str = "Konya") -> tuple[str | None, str]:
    """'… SELÇUKLU/KONYA' → ('Selçuklu', 'Konya')"""
    addr = clean_text(address)
    if not addr:
        return None, tr_title(default_city)

    match = _CITY_DISTRICT_TAIL.search(addr)
    if match:
        district = tr_title(match.group("district").strip(" ,.-"))
        city = tr_title(match.group("city").strip(" ,.-"))
        return (district or None), (city or tr_title(default_city))

    soft = re.search(
        r"(?P<district>[^,]+),\s*(?P<city>Konya|Ankara|İstanbul|Izmir|İzmir|Bursa|Sakarya|Kocaeli)\s*$",
        addr,
        re.IGNORECASE,
    )
    if soft:
        return tr_title(soft.group("district")), tr_title(soft.group("city"))

    return None, tr_title(default_city)


def parse_title_parts(title: str) -> tuple[str, str, list[str]]:
    """
    Başlıktan (facility_type, name, waste_types) üretir.
    """
    from services.municipal_waste.waste_types import (
        infer_waste_types_from_facility,
        normalize_waste_types,
    )

    raw = clean_text(title)
    if not raw:
        return "Atık Merkezi", "Atık Merkezi", []

    waste: list[str] = []
    work = raw
    paren = re.search(r"\(([^)]*)\)", work)
    if paren:
        waste = normalize_waste_types(paren.group(1))
        work = (work[: paren.start()] + work[paren.end() :]).strip()

    if " - " in work:
        left, right = work.split(" - ", 1)
        facility = left.strip() or work
        name = right.strip() or left.strip() or work
    else:
        facility = work
        name = work

    facility_type = tr_title(facility) or "Atık Merkezi"
    display_name = tr_title(name) or facility_type
    if not waste:
        waste = infer_waste_types_from_facility(facility_type)
    return facility_type, display_name, waste


# Eski import yolu uyumluluğu
def split_waste_types(raw: str | None) -> list[str]:
    from services.municipal_waste.waste_types import normalize_waste_types

    return normalize_waste_types(raw)


def infer_waste_types_from_facility(facility_type: str) -> list[str]:
    from services.municipal_waste.waste_types import (
        infer_waste_types_from_facility as _infer,
    )

    return _infer(facility_type)
