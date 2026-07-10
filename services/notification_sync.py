"""Mesaj bildirimleri ile okundu senkronu."""

from __future__ import annotations

import logging

from sqlalchemy import or_

from extensions import db
from models import Bildirim, Mesaj

logger = logging.getLogger(__name__)


def message_notification_link(partner_id: int, kaynak_id: int = 0, atik_id: int = 0) -> str:
    return f"/mesajlar/{partner_id}/{kaynak_id or 0}/{atik_id or 0}"


def _conversation_link_filters(messages: list[Mesaj], reader_id: int) -> list:
    links = set()
    for mesaj in messages:
        partner_id = (
            mesaj.sender_id if mesaj.receiver_id == reader_id else mesaj.receiver_id
        )
        links.add(message_notification_link(partner_id, mesaj.kaynak_id or 0, mesaj.atik_id or 0))
    return [Bildirim.link == link for link in links]


def mark_message_notifications_read(
    user_id: int,
    messages: list[Mesaj] | None = None,
    *,
    partner_id: int | None = None,
    kaynak_id: int = 0,
    atik_id: int = 0,
) -> int:
    if messages:
        message_ids = [m.id for m in messages if m.id]
        filters = []
        if message_ids:
            filters.append(Bildirim.mesaj_id.in_(message_ids))
        link_filters = _conversation_link_filters(messages, user_id)
        if link_filters:
            filters.append(or_(*link_filters))
        if not filters:
            return 0
        rows = (
            Bildirim.query.filter_by(user_id=user_id, tur="mesaj", okundu=False)
            .filter(or_(*filters))
            .all()
        )
    else:
        if partner_id is None:
            return 0
        link = message_notification_link(partner_id, kaynak_id, atik_id)
        rows = Bildirim.query.filter_by(
            user_id=user_id,
            tur="mesaj",
            okundu=False,
        ).filter(Bildirim.link == link).all()

    if not rows:
        return 0
    for row in rows:
        row.okundu = True
    db.session.commit()
    try:
        from socket_events import emit_notification_sync, emit_unread_count_updated

        emit_unread_count_updated(user_id)
        emit_notification_sync(user_id)
    except Exception:
        logger.exception(
            "Mesaj bildirimi socket senkronu başarısız user_id=%s", user_id
        )
    return len(rows)
