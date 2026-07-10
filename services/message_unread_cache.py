"""Okunmamış mesaj/bildirim sayacı — HTTP isteklerinde COUNT yerine önbellek."""

from __future__ import annotations

from models import Bildirim, Mesaj

_message_unread_cache: dict[int, int] = {}
_notification_unread_cache: dict[int, int] = {}
_cache_warmed: set[int] = set()


def get_message_unread_count(user_id: int, *, warm_if_missing: bool = False) -> int:
    if warm_if_missing and user_id not in _cache_warmed:
        refresh_unread_cache(user_id)
    return _message_unread_cache.get(user_id, 0)


def get_notification_unread_count(user_id: int) -> int:
    return _notification_unread_cache.get(user_id, 0)


def set_unread_counts(
    user_id: int,
    message_unread: int,
    notification_unread: int | None = None,
) -> None:
    _message_unread_cache[user_id] = message_unread
    _cache_warmed.add(user_id)
    if notification_unread is not None:
        _notification_unread_cache[user_id] = notification_unread


def is_cache_warmed(user_id: int) -> bool:
    return user_id in _cache_warmed


def refresh_unread_cache(user_id: int) -> dict[str, int]:
    message_unread = Mesaj.query.filter_by(receiver_id=user_id, is_read=False).count()
    notification_unread = Bildirim.query.filter_by(user_id=user_id, okundu=False).count()
    set_unread_counts(user_id, message_unread, notification_unread)
    return {
        "message_unread": message_unread,
        "notification_unread": notification_unread,
    }


def clear_unread_cache(user_id: int | None = None) -> None:
    if user_id is None:
        _message_unread_cache.clear()
        _notification_unread_cache.clear()
        _cache_warmed.clear()
        return
    _message_unread_cache.pop(user_id, None)
    _notification_unread_cache.pop(user_id, None)
    _cache_warmed.discard(user_id)
