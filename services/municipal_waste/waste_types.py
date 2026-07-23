"""Merkezi atık türü normalizasyon sözlüğü (tüm belediyeler)."""

from __future__ import annotations

import re

from services.municipal_waste.text_utils import clean_text, normalize_key, tr_title

# Ham ifade (normalize_key sonrası) → kanonik görünen ad
WASTE_TYPE_ALIASES: dict[str, str] = {
    # Kağıt
    "kagit": "Kağıt",
    "kagit karton": "Kağıt",
    "kagit-karton": "Kağıt",
    "atik kagit": "Kağıt",
    "kagit atik": "Kağıt",
    # Plastik
    "plastik": "Plastik",
    "atik plastik": "Plastik",
    "plastik atik": "Plastik",
    # Cam
    "cam": "Cam",
    "atik cam": "Cam",
    "cam atik": "Cam",
    # Metal
    "metal": "Metal",
    "metal ambalaj": "Metal",
    "atik metal": "Metal",
    "metal atik": "Metal",
    # Pil
    "pil": "Pil",
    "atik pil": "Pil",
    "atik piller": "Pil",
    "piller": "Pil",
    # Elektronik / AEEE
    "elektronik": "Elektronik Atık",
    "elektronik atik": "Elektronik Atık",
    "elektrikli elektronik atik": "Elektronik Atık",
    "aeee": "Elektronik Atık",
    "e-atik": "Elektronik Atık",
    "e atik": "Elektronik Atık",
    # Bitkisel yağ
    "bitkisel atik yagi": "Bitkisel Atık Yağı",
    "bitkisel atik yag": "Bitkisel Atık Yağı",
    "atik yag": "Bitkisel Atık Yağı",
    "atik yagi": "Bitkisel Atık Yağı",
    "yag": "Bitkisel Atık Yağı",
    "yagi": "Bitkisel Atık Yağı",
    # Tekstil
    "tekstil": "Tekstil",
    "tekstil atik": "Tekstil",
    "atik tekstil": "Tekstil",
    # İlaç
    "ilac": "İlaç",
    "atik ilac": "İlaç",
    # Diğer
    "inert": "İnert Atık",
    "inert atik": "İnert Atık",
    "hafriyat": "Hafriyat",
    "karisik": "Karışık Atık",
    "karisik atik": "Karışık Atık",
}

# Tesis adı içinde geçen anahtarlar → kanonik tür
_FACILITY_HINTS: tuple[tuple[str, str], ...] = (
    ("tekstil", "Tekstil"),
    ("aeee", "Elektronik Atık"),
    ("elektronik", "Elektronik Atık"),
    ("bitkisel", "Bitkisel Atık Yağı"),
    (" yag", "Bitkisel Atık Yağı"),
    ("yağ", "Bitkisel Atık Yağı"),
    ("ilac", "İlaç"),
    ("ilaç", "İlaç"),
    ("hafriyat", "Hafriyat"),
    ("inert", "İnert Atık"),
    ("karisik", "Karışık Atık"),
    ("karışık", "Karışık Atık"),
    ("cam", "Cam"),
    ("kagit", "Kağıt"),
    ("plastik", "Plastik"),
    ("metal", "Metal"),
    ("pil", "Pil"),
)

_NON_WASTE_PAREN = re.compile(
    r"^(azra\s*\d+|bidon|curuf|cüruf|trafik\s*parki|trafik\s*parkı|metal\s*kumbara)$",
    re.IGNORECASE,
)


def normalize_waste_type(raw: str | None) -> str | None:
    """Tek bir ham ifadeyi kanonik türe çevirir; bilinmiyorsa title-case döner."""
    piece = clean_text(raw)
    if not piece:
        return None
    key = normalize_key(piece)
    if len(key) < 2 or key in {"vb", "ve"}:
        return None
    if key in WASTE_TYPE_ALIASES:
        return WASTE_TYPE_ALIASES[key]
    # En uzun alias eşleşmesini tercih et
    best: str | None = None
    best_len = 0
    for alias, canon in WASTE_TYPE_ALIASES.items():
        if alias in key or key in alias:
            if len(alias) > best_len:
                best = canon
                best_len = len(alias)
    if best:
        return best
    return tr_title(piece)


def normalize_waste_types(raw: str | None) -> list[str]:
    """Virgül/ayraçlı listeyi kanonik tür listesine çevirir."""
    if not raw:
        return []
    text = clean_text(raw).strip("()[] ")
    if not text or _NON_WASTE_PAREN.match(text):
        return []
    text = re.sub(r"\bvb\.?\s*atiklar?\b", "", text, flags=re.IGNORECASE)
    out: list[str] = []
    seen: set[str] = set()
    for part in re.split(r"[,;/|]+", text):
        canon = normalize_waste_type(part)
        if canon and canon not in seen:
            seen.add(canon)
            out.append(canon)
    return out


def infer_waste_types_from_facility(facility_type: str) -> list[str]:
    key = normalize_key(facility_type)
    inferred: list[str] = []
    for needle, label in _FACILITY_HINTS:
        if needle in key and label not in inferred:
            inferred.append(label)
    return inferred
