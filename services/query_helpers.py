"""Paylaşılan ORM sorgu yardımcıları."""

from __future__ import annotations

from sqlalchemy.orm import load_only


def harita_ilan_load_options(model):
    """Harita için yalnızca gerekli ilan kolonları."""
    return load_only(model.id, model.baslik, model.latitude, model.longitude)
