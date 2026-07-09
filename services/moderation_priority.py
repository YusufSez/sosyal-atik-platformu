"""Pending Review öncelik sıralaması."""

from __future__ import annotations

from datetime import datetime

from constants import MODERATION_STATUS_PENDING_REVIEW


def priority_sort_key(item) -> tuple:
    """
    Pending Review sıralaması:
    Risk DESC → Spam DESC → Duplicate DESC → Tarih ASC
  Non-pending: tarih DESC (sonra).
    """
    pending = getattr(item, "moderation_status", None) == MODERATION_STATUS_PENDING_REVIEW
    risk = getattr(item, "risk_skoru", None) or 0
    spam = getattr(item, "spam_score", None) or 0
    dup = getattr(item, "duplicate_score", None) or 0
    tarih = getattr(item, "tarih", None) or datetime.max

    if pending:
        return (0, -risk, -spam, -dup, tarih)
    ts = tarih.timestamp() if tarih and tarih != datetime.max else 0
    return (1, -ts)


def sort_moderation_items(items: list) -> list:
    """Moderasyon listesini öncelik kuyruğuna göre sıralar."""
    return sorted(items, key=priority_sort_key)
