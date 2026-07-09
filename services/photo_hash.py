"""Fotoğraf hash hesaplama (duplicate tespiti)."""

from __future__ import annotations

import hashlib
import os

from utils import resolve_item_picture_path


def photo_file_hash(filename: str) -> str | None:
    """Kayıtlı ilan fotoğrafının SHA-256 hash'i."""
    if not filename or filename == "default.jpg":
        return None
    try:
        path = resolve_item_picture_path(filename)
        if not os.path.isfile(path):
            return None
        h = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()
    except (OSError, RuntimeError):
        return None


def photo_hashes_for_files(filenames: list[str] | None) -> list[str]:
    """Dosya adları listesinden hash listesi."""
    if not filenames:
        return []
    return [h for f in filenames if (h := photo_file_hash(f))]
