"""Türkiye'nin resmi 81 il ve ilçe sözlüğü (statik JSON).

Kaynak: static/data/il-ilce-list.json
Belediye atık merkezi kayıtlarından bağımsızdır; yeni belediyeler
eklendiğinde bu modül değişmeden çalışır.
"""

from __future__ import annotations

import json
import logging
import re
import threading
from functools import lru_cache
from pathlib import Path

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_JSON_RELATIVE = Path("static") / "data" / "il-ilce-list.json"


def _candidate_json_paths() -> list[Path]:
    """Sabit relatif path yok — root_path / paket kökü adayları."""
    candidates: list[Path] = []

    try:
        from flask import current_app, has_app_context

        if has_app_context() and current_app:
            root = Path(current_app.root_path)
            candidates.append(root / _JSON_RELATIVE)
            # Bazı kurulumlarda static_folder ayrıdır
            static_folder = current_app.static_folder
            if static_folder:
                candidates.append(Path(static_folder) / "data" / "il-ilce-list.json")
    except Exception:
        logger.exception("turkey_geo: current_app.root_path okunamadı")

    # services/turkey_geo.py → repo kökü
    package_root = Path(__file__).resolve().parent.parent
    candidates.append(package_root / _JSON_RELATIVE)
    candidates.append(package_root / "static" / "data" / "il-ilce-list.json")

    # Yinelenenleri koru, sırayı bozma
    seen: set[str] = set()
    unique: list[Path] = []
    for path in candidates:
        key = str(path.resolve()) if path.exists() else str(path)
        if key in seen:
            continue
        seen.add(key)
        unique.append(path)
    return unique


def resolve_il_ilce_json_path() -> Path:
    """İlk bulunan il-ilçe JSON dosyasını döndürür."""
    tried: list[str] = []
    for path in _candidate_json_paths():
        tried.append(str(path))
        if path.is_file():
            return path
    raise FileNotFoundError(
        "Türkiye il-ilçe JSON bulunamadı. Denenen yollar: " + " | ".join(tried)
    )


def _tr_lower(value: str) -> str:
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


def _tr_title(value: str) -> str:
    text = (value or "").strip()
    if not text:
        return ""
    parts: list[str] = []
    for token in re.split(r"(\s+|/|-)", text):
        if not token or token.isspace() or token in {"/", "-"}:
            parts.append(token)
            continue
        low = _tr_lower(token)
        first, rest = low[:1], low[1:]
        if first == "i":
            first = "İ"
        else:
            first = first.upper()
        parts.append(first + rest)
    return "".join(parts)


@lru_cache(maxsize=1)
def _load_raw(resolved_path: str) -> tuple[dict[str, list[str]], tuple[str, ...]]:
    """
    Returns (provinces_by_key, display_order).

    Cache anahtarı çözümlenmiş dosya yoludur (root_path değişirse yenilenir).
    """
    path = Path(resolved_path)
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)

    if not isinstance(data, list):
        raise ValueError(f"il-ilce JSON liste olmalı: {path}")

    by_key: dict[str, list[str]] = {}
    order: list[str] = []
    for entry in data:
        if not isinstance(entry, dict):
            continue
        city = _tr_title(entry.get("name") or "")
        if not city:
            continue
        districts = sorted(
            {
                _tr_title(d.get("name") or "")
                for d in (entry.get("districts") or [])
                if isinstance(d, dict) and d.get("name")
            },
            key=_tr_lower,
        )
        by_key[_tr_lower(city)] = districts
        order.append(city)

    if len(order) < 81:
        logger.warning(
            "turkey_geo: beklenen 81 il, bulunan=%s path=%s",
            len(order),
            path,
        )
    return by_key, tuple(order)


def _cached_bundle() -> tuple[dict[str, list[str]], tuple[str, ...]]:
    path = resolve_il_ilce_json_path()
    return _load_raw(str(path.resolve()))


def list_provinces() -> list[str]:
    """81 il (görünen ad, plaka sırası)."""
    _, order = _cached_bundle()
    return list(order)


def list_districts(city: str | None) -> list[str]:
    """Seçilen ile ait resmi ilçeler. İl yoksa veya bilinmiyorsa []."""
    if not city or not str(city).strip():
        return []
    by_key, _ = _cached_bundle()
    return list(by_key.get(_tr_lower(city.strip()), []))


def province_exists(city: str | None) -> bool:
    if not city or not str(city).strip():
        return False
    by_key, _ = _cached_bundle()
    return _tr_lower(city.strip()) in by_key


def reload_cache() -> None:
    """Test / hot-reload için."""
    with _lock:
        _load_raw.cache_clear()
