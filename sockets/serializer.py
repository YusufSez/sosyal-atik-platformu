from sqlalchemy import select, union

from sqlalchemy import inspect as sa_inspect

from extensions import db
from models import Mesaj, User
from utils import format_datetime

from .rooms import canonical_conversation_id, conversation_id_for


def _sender_name(mesaj: Mesaj) -> str:
    if "sender" not in sa_inspect(mesaj).unloaded:
        sender = mesaj.sender
        if sender is not None:
            return sender.username or ""
    sender = db.session.get(User, mesaj.sender_id)
    return sender.username if sender else ""


def _partner_name(mesaj: Mesaj, for_user_id: int) -> tuple[int, str]:
    other_id = mesaj.receiver_id if mesaj.sender_id == for_user_id else mesaj.sender_id
    if other_id == mesaj.sender_id and "sender" not in sa_inspect(mesaj).unloaded and mesaj.sender:
        return other_id, mesaj.sender.username or ""
    if other_id == mesaj.receiver_id and "receiver" not in sa_inspect(mesaj).unloaded and mesaj.receiver:
        return other_id, mesaj.receiver.username or ""
    other = db.session.get(User, other_id)
    return other_id, other.username if other else ""


def serialize_message(mesaj: Mesaj, for_user_id: int) -> dict:
    return {
        "message_id": mesaj.id,
        "sender_id": mesaj.sender_id,
        "receiver_id": mesaj.receiver_id,
        "sender_name": _sender_name(mesaj),
        "message": mesaj.content,
        "created_at": mesaj.timestamp.isoformat() if mesaj.timestamp else None,
        "created_at_local": format_datetime(mesaj.timestamp),
        "conversation_id": conversation_id_for(mesaj, for_user_id),
        "canonical_conversation_id": canonical_conversation_id(
            mesaj.sender_id,
            mesaj.receiver_id,
            mesaj.kaynak_id or 0,
            mesaj.atik_id or 0,
        ),
        "is_read": bool(mesaj.is_read),
        "read_at": mesaj.read_at.isoformat() if mesaj.read_at else None,
        "read_at_local": format_datetime(mesaj.read_at) if mesaj.read_at else None,
    }


def _conversation_unread_count(mesaj: Mesaj, viewer_id: int) -> int:
    other_id = mesaj.receiver_id if mesaj.sender_id == viewer_id else mesaj.sender_id
    return Mesaj.query.filter_by(
        sender_id=other_id,
        receiver_id=viewer_id,
        kaynak_id=mesaj.kaynak_id,
        atik_id=mesaj.atik_id,
        is_read=False,
    ).count()


def build_conversation_updated(mesaj: Mesaj, for_user_id: int) -> dict:
    other_id, partner_name = _partner_name(mesaj, for_user_id)
    return {
        "conversation_id": conversation_id_for(mesaj, for_user_id),
        "canonical_conversation_id": canonical_conversation_id(
            mesaj.sender_id,
            mesaj.receiver_id,
            mesaj.kaynak_id or 0,
            mesaj.atik_id or 0,
        ),
        "partner_id": other_id,
        "partner_name": partner_name,
        "last_message": mesaj.content,
        "last_message_at": mesaj.timestamp.isoformat() if mesaj.timestamp else None,
        "last_message_at_local": format_datetime(mesaj.timestamp),
        "unread_count": _conversation_unread_count(mesaj, for_user_id),
        "is_sent_by_me": mesaj.sender_id == for_user_id,
        "kaynak_id": mesaj.kaynak_id or 0,
        "atik_id": mesaj.atik_id or 0,
    }


def unread_counts_for(user_id: int) -> dict:
    from services.message_unread_cache import refresh_unread_cache

    return refresh_unread_cache(user_id)
