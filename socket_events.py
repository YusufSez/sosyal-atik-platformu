"""Flask-SocketIO event handlers — mesajlaşma ve kullanıcı odaları."""

from collections import defaultdict

from flask_login import current_user
from flask_socketio import join_room, leave_room
from socketio.exceptions import ConnectionRefusedError
from sqlalchemy import and_, or_

from extensions import db, socketio
from models import Bildirim, Mesaj, User
from utils import format_datetime

_connection_counts: defaultdict[int, int] = defaultdict(int)


def user_room(user_id: int) -> str:
    return f"user_{user_id}"


def conversation_id_for(mesaj: Mesaj, viewer_id: int) -> str:
    other_id = mesaj.receiver_id if mesaj.sender_id == viewer_id else mesaj.sender_id
    return f"{other_id}-{mesaj.kaynak_id or 0}-{mesaj.atik_id or 0}"


def serialize_message(mesaj: Mesaj, for_user_id: int) -> dict:
    sender = db.session.get(User, mesaj.sender_id)
    return {
        "message_id": mesaj.id,
        "sender_id": mesaj.sender_id,
        "receiver_id": mesaj.receiver_id,
        "sender_name": sender.username if sender else "",
        "message": mesaj.content,
        "created_at": mesaj.timestamp.isoformat() if mesaj.timestamp else None,
        "created_at_local": format_datetime(mesaj.timestamp),
        "conversation_id": conversation_id_for(mesaj, for_user_id),
        "is_read": bool(mesaj.is_read),
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
    other_id = mesaj.receiver_id if mesaj.sender_id == for_user_id else mesaj.sender_id
    other = db.session.get(User, other_id)
    return {
        "conversation_id": conversation_id_for(mesaj, for_user_id),
        "partner_id": other_id,
        "partner_name": other.username if other else "",
        "last_message": mesaj.content,
        "last_message_at": mesaj.timestamp.isoformat() if mesaj.timestamp else None,
        "last_message_at_local": format_datetime(mesaj.timestamp),
        "unread_count": _conversation_unread_count(mesaj, for_user_id),
        "is_sent_by_me": mesaj.sender_id == for_user_id,
        "kaynak_id": mesaj.kaynak_id or 0,
        "atik_id": mesaj.atik_id or 0,
    }


def unread_counts_for(user_id: int) -> dict:
    return {
        "message_unread": Mesaj.query.filter_by(receiver_id=user_id, is_read=False).count(),
        "notification_unread": Bildirim.query.filter_by(user_id=user_id, okundu=False).count(),
    }


def is_user_online(user_id: int) -> bool:
    return _connection_counts.get(user_id, 0) > 0


def _join_user_room(user_id: int) -> None:
    try:
        join_room(user_room(user_id))
    except (AttributeError, RuntimeError):
        pass


def emit_unread_count_updated(user_id: int) -> None:
    if not is_user_online(user_id):
        return
    socketio.emit("unread_count_updated", unread_counts_for(user_id), room=user_room(user_id))


def emit_after_message_created(mesaj: Mesaj) -> None:
    sender_id = mesaj.sender_id
    receiver_id = mesaj.receiver_id

    socketio.emit(
        "message_sent",
        serialize_message(mesaj, sender_id),
        room=user_room(sender_id),
    )
    socketio.emit(
        "conversation_updated",
        build_conversation_updated(mesaj, sender_id),
        room=user_room(sender_id),
    )

    if is_user_online(receiver_id):
        socketio.emit(
            "new_message",
            serialize_message(mesaj, receiver_id),
            room=user_room(receiver_id),
        )
        socketio.emit(
            "conversation_updated",
            build_conversation_updated(mesaj, receiver_id),
            room=user_room(receiver_id),
        )
        emit_unread_count_updated(receiver_id)


def emit_messages_marked_read(messages: list, reader_id: int) -> None:
    if not messages:
        return

    by_sender: dict[int, list[int]] = {}
    for mesaj in messages:
        by_sender.setdefault(mesaj.sender_id, []).append(mesaj.id)

    for sender_id, message_ids in by_sender.items():
        if not is_user_online(sender_id):
            continue
        sample = next(m for m in messages if m.sender_id == sender_id)
        socketio.emit(
            "message_read",
            {
                "reader_id": reader_id,
                "message_ids": message_ids,
                "conversation_id": conversation_id_for(sample, sender_id),
            },
            room=user_room(sender_id),
        )

    emit_unread_count_updated(reader_id)


def _conversation_filter(sender_id: int, receiver_id: int, kaynak_id, atik_id):
    return and_(
        or_(
            and_(Mesaj.sender_id == sender_id, Mesaj.receiver_id == receiver_id),
            and_(Mesaj.sender_id == receiver_id, Mesaj.receiver_id == sender_id),
        ),
        Mesaj.kaynak_id == kaynak_id,
        Mesaj.atik_id == atik_id,
    )


@socketio.on("connect")
def handle_connect():
    """Yalnızca Flask-Login oturumu olan kullanıcılar bağlanabilir."""
    if not current_user.is_authenticated:
        raise ConnectionRefusedError("Giriş gerekli")
    _connection_counts[current_user.id] += 1
    _join_user_room(current_user.id)


@socketio.on("disconnect")
def handle_disconnect():
    if current_user.is_authenticated:
        _connection_counts[current_user.id] = max(0, _connection_counts[current_user.id] - 1)
        if _connection_counts[current_user.id] == 0:
            _connection_counts.pop(current_user.id, None)
        try:
            leave_room(user_room(current_user.id))
        except (AttributeError, RuntimeError):
            pass


@socketio.on("join")
def handle_join():
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    _connection_counts[current_user.id] = max(1, _connection_counts.get(current_user.id, 0))
    room = user_room(current_user.id)
    _join_user_room(current_user.id)
    return {"room": room}


@socketio.on("leave")
def handle_leave():
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    room = user_room(current_user.id)
    try:
        leave_room(room)
    except (AttributeError, RuntimeError):
        pass
    return {"left": room}


@socketio.on("typing")
def handle_typing(data):
    if not current_user.is_authenticated:
        return
    data = data or {}
    receiver_id = data.get("receiver_id")
    conversation_id = data.get("conversation_id")
    if not receiver_id:
        return
    receiver_id = int(receiver_id)
    if receiver_id == current_user.id:
        return
    if not is_user_online(receiver_id):
        return
    socketio.emit(
        "typing",
        {
            "sender_id": current_user.id,
            "sender_name": current_user.username,
            "conversation_id": conversation_id,
        },
        room=user_room(receiver_id),
    )


@socketio.on("stop_typing")
def handle_stop_typing(data):
    if not current_user.is_authenticated:
        return
    data = data or {}
    receiver_id = data.get("receiver_id")
    conversation_id = data.get("conversation_id")
    if not receiver_id:
        return
    receiver_id = int(receiver_id)
    if receiver_id == current_user.id:
        return
    if not is_user_online(receiver_id):
        return
    socketio.emit(
        "stop_typing",
        {
            "sender_id": current_user.id,
            "conversation_id": conversation_id,
        },
        room=user_room(receiver_id),
    )


@socketio.on("message_read")
def handle_message_read(data):
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    data = data or {}
    message_ids = data.get("message_ids") or []
    if not message_ids:
        message_id = data.get("message_id")
        if message_id:
            message_ids = [message_id]

    messages = Mesaj.query.filter(
        Mesaj.id.in_(message_ids),
        Mesaj.receiver_id == current_user.id,
        Mesaj.is_read.is_(False),
    ).all()
    if not messages:
        return {"updated": 0}

    for mesaj in messages:
        mesaj.is_read = True
    db.session.commit()
    emit_messages_marked_read(messages, current_user.id)
    return {"updated": len(messages)}
