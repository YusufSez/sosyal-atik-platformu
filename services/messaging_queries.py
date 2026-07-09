"""Mesajlaşma sorguları — sayfalama ve inbox SQL toplama."""

from __future__ import annotations

from sqlalchemy import case, func, or_
from sqlalchemy.orm import joinedload

from constants import MESSAGE_PAGE_SIZE
from extensions import db
from models import Atik, Kaynak, Mesaj
from utils import format_datetime


def _normalize_listing_ids(kaynak_id: int, atik_id: int) -> tuple[int | None, int | None]:
    return (kaynak_id if kaynak_id != 0 else None, atik_id if atik_id != 0 else None)


def conversation_query(user_id: int, partner_id: int, kaynak_id: int, atik_id: int):
    k_id, a_id = _normalize_listing_ids(kaynak_id, atik_id)
    return Mesaj.query.filter(
        ((Mesaj.sender_id == user_id) & (Mesaj.receiver_id == partner_id))
        | ((Mesaj.sender_id == partner_id) & (Mesaj.receiver_id == user_id)),
        Mesaj.kaynak_id == k_id,
        Mesaj.atik_id == a_id,
    )


def fetch_message_page(
    user_id: int,
    partner_id: int,
    kaynak_id: int,
    atik_id: int,
    *,
    before_id: int | None = None,
    limit: int = MESSAGE_PAGE_SIZE,
) -> tuple[list[Mesaj], bool, int | None]:
    """Cursor sayfalama: son `limit` mesaj veya `before_id` öncesi daha eski mesajlar."""
    query = conversation_query(user_id, partner_id, kaynak_id, atik_id).options(
        joinedload(Mesaj.sender)
    )
    if before_id:
        query = query.filter(Mesaj.id < before_id)
    rows = query.order_by(Mesaj.id.desc()).limit(limit + 1).all()
    has_more = len(rows) > limit
    if has_more:
        rows = rows[:limit]
    rows.reverse()
    oldest_id = rows[0].id if rows else None
    return rows, has_more, oldest_id


def serialize_fetched_message(mesaj: Mesaj) -> dict:
    return {
        "id": mesaj.id,
        "content": mesaj.content,
        "sender_id": mesaj.sender_id,
        "sender_username": mesaj.sender.username if mesaj.sender else "",
        "is_read": mesaj.is_read,
        "read_at": mesaj.read_at.isoformat() if mesaj.read_at else None,
        "read_at_local": format_datetime(mesaj.read_at) if mesaj.read_at else None,
        "timestamp": format_datetime(mesaj.timestamp, "%d.%m.%Y %H:%M"),
    }


def fetch_inbox_threads(user_id: int) -> dict:
    """Her sohbet için SQL ile son mesajı döndürür (Python döngüsü yerine)."""
    other_id_expr = case(
        (Mesaj.sender_id == user_id, Mesaj.receiver_id),
        else_=Mesaj.sender_id,
    )
    latest_subq = (
        db.session.query(
            func.max(Mesaj.id).label("max_id"),
        )
        .filter(or_(Mesaj.sender_id == user_id, Mesaj.receiver_id == user_id))
        .group_by(other_id_expr, Mesaj.kaynak_id, Mesaj.atik_id)
        .subquery()
    )
    messages = (
        Mesaj.query.join(latest_subq, Mesaj.id == latest_subq.c.max_id)
        .options(joinedload(Mesaj.sender), joinedload(Mesaj.receiver))
        .order_by(Mesaj.timestamp.desc())
        .all()
    )

    kaynak_ids = {m.kaynak_id for m in messages if m.kaynak_id}
    atik_ids = {m.atik_id for m in messages if m.atik_id}
    kaynaklar = (
        {k.id: k for k in Kaynak.query.filter(Kaynak.id.in_(kaynak_ids)).all()}
        if kaynak_ids
        else {}
    )
    atiklar = (
        {a.id: a for a in Atik.query.filter(Atik.id.in_(atik_ids)).all()} if atik_ids else {}
    )

    sohbetler = {}
    for mesaj in messages:
        other_id = mesaj.receiver_id if mesaj.sender_id == user_id else mesaj.sender_id
        key = f"{other_id}-{mesaj.kaynak_id or 0}-{mesaj.atik_id or 0}"
        sohbetler[key] = {
            "msg": mesaj,
            "user_id": other_id,
            "kaynak_id": mesaj.kaynak_id,
            "atik_id": mesaj.atik_id,
            "kaynak": kaynaklar.get(mesaj.kaynak_id) if mesaj.kaynak_id else None,
            "atik": atiklar.get(mesaj.atik_id) if mesaj.atik_id else None,
            "is_new": (not mesaj.is_read) and (mesaj.receiver_id == user_id),
        }
    return sohbetler
