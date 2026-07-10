from collections import defaultdict

from extensions import socketio
from models import Mesaj
from utils import format_datetime

from .rooms import canonical_conversation_id, conversation_id_for, conversation_room, user_room
from .serializer import build_conversation_updated, serialize_message, unread_counts_for
from .utils import _log_emit, logger


def emit_unread_count_updated(user_id: int) -> None:
    room = user_room(user_id)
    payload = unread_counts_for(user_id)
    _log_emit("unread_count_updated", room, user_id=user_id)
    socketio.emit("unread_count_updated", payload, room=room)


def emit_notification_sync(user_id: int) -> None:
    room = user_room(user_id)
    _log_emit("notification_sync", room, user_id=user_id)
    socketio.emit("notification_sync", unread_counts_for(user_id), room=room)


def emit_after_message_created(mesaj: Mesaj) -> None:
    sender_id = mesaj.sender_id
    receiver_id = mesaj.receiver_id
    canon = canonical_conversation_id(
        sender_id,
        receiver_id,
        mesaj.kaynak_id or 0,
        mesaj.atik_id or 0,
    )
    conv = conversation_room(canon)

    sent_payload = serialize_message(mesaj, sender_id)
    recv_payload = serialize_message(mesaj, receiver_id)

    _log_emit("message_sent", conv, message_id=mesaj.id, sender=sender_id)
    socketio.emit("message_sent", sent_payload, room=conv)

    _log_emit("new_message", conv, message_id=mesaj.id, receiver=receiver_id)
    socketio.emit("new_message", recv_payload, room=conv)

    _log_emit("conversation_updated", user_room(sender_id), user_id=sender_id)
    socketio.emit(
        "conversation_updated",
        build_conversation_updated(mesaj, sender_id),
        room=user_room(sender_id),
    )
    _log_emit("conversation_updated", user_room(receiver_id), user_id=receiver_id)
    socketio.emit(
        "conversation_updated",
        build_conversation_updated(mesaj, receiver_id),
        room=user_room(receiver_id),
    )
    emit_unread_count_updated(receiver_id)


def emit_messages_marked_read(messages: list, reader_id: int) -> None:
    if not messages:
        return

    by_sender: dict[int, list[dict]] = defaultdict(list)
    for mesaj in messages:
        by_sender[mesaj.sender_id].append({
            "message_id": mesaj.id,
            "read_at": mesaj.read_at.isoformat() if mesaj.read_at else None,
            "read_at_local": format_datetime(mesaj.read_at) if mesaj.read_at else None,
        })

    for sender_id, items in by_sender.items():
        sample = next(m for m in messages if m.sender_id == sender_id)
        canon = canonical_conversation_id(
            sample.sender_id,
            sample.receiver_id,
            sample.kaynak_id or 0,
            sample.atik_id or 0,
        )
        payload = {
            "reader_id": reader_id,
            "message_ids": [item["message_id"] for item in items],
            "messages": items,
            "conversation_id": conversation_id_for(sample, sender_id),
            "canonical_conversation_id": canon,
        }
        sender_room = user_room(sender_id)
        _log_emit("message_read", sender_room, reader=reader_id, count=len(items))
        socketio.emit("message_read", payload, room=sender_room)
        _log_emit("message_read", conversation_room(canon), reader=reader_id, count=len(items))
        socketio.emit("message_read", payload, room=conversation_room(canon))

    emit_unread_count_updated(reader_id)

    try:
        from services.notification_sync import mark_message_notifications_read

        mark_message_notifications_read(reader_id, messages=messages)
    except Exception:
        logger.exception(
            "Mesaj okundu bildirim senkronu başarısız reader_id=%s", reader_id
        )
