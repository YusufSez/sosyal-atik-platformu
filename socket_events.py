"""Flask-SocketIO event handlers — mesajlaşma, presence ve conversation odaları."""

import logging
import time
from collections import defaultdict

from flask import request
from flask_login import current_user
from flask_socketio import join_room, leave_room
from socketio.exceptions import ConnectionRefusedError
from sqlalchemy import and_, or_, select, union

from constants import (
    RATE_SOCKET_MESSAGE_PER_SEC,
    RATE_SOCKET_SYNC_STATE_PER_SEC,
    RATE_SOCKET_TYPING_PER_SEC,
)
from extensions import db, socketio
from models import Bildirim, Mesaj, User
from utils import format_datetime, utc_now

logger = logging.getLogger("atikport.socket")

_connection_counts: defaultdict[int, int] = defaultdict(int)
_rate_buckets: defaultdict[int, defaultdict[str, list]] = defaultdict(lambda: defaultdict(list))
_sid_users: dict[str, int] = {}
_user_sids: defaultdict[int, set] = defaultdict(set)
_sid_conversations: defaultdict[str, list] = defaultdict(list)


def user_room(user_id: int) -> str:
    return f"user_{user_id}"


def canonical_conversation_id(user_a: int, user_b: int, kaynak_id=0, atik_id=0) -> str:
    low, high = sorted([user_a, user_b])
    return f"{low}-{high}-{kaynak_id or 0}-{atik_id or 0}"


def conversation_room(canonical_id: str) -> str:
    return f"conversation_{canonical_id}"


def conversation_id_for(mesaj: Mesaj, viewer_id: int) -> str:
    other_id = mesaj.receiver_id if mesaj.sender_id == viewer_id else mesaj.sender_id
    return f"{other_id}-{mesaj.kaynak_id or 0}-{mesaj.atik_id or 0}"


def parse_conversation_parts(conversation_id: str) -> tuple[int, int, int] | None:
    parts = str(conversation_id or "").split("-")
    if len(parts) != 3:
        return None
    try:
        return int(parts[0]), int(parts[1]), int(parts[2])
    except (TypeError, ValueError):
        return None


def is_user_online(user_id: int) -> bool:
    return _connection_counts.get(user_id, 0) > 0


def _log_emit(event: str, room: str, **extra) -> None:
    logger.info("SOCKET EMIT %s room=%s %s", event, room, extra or "")


def _log_socket(event: str, **extra) -> None:
    logger.info("SOCKET %s %s", event, extra or "")


def get_online_users() -> set[int]:
    return {uid for uid, count in _connection_counts.items() if count > 0}


def _check_rate_limit(user_id: int, event: str, max_per_second: int) -> bool:
    now = time.time()
    bucket = _rate_buckets[user_id][event]
    bucket[:] = [stamp for stamp in bucket if now - stamp < 1]
    if len(bucket) >= max_per_second:
        return False
    bucket.append(now)
    return True


def _cleanup_user_rate_limit(user_id: int) -> None:
    if _connection_counts.get(user_id, 0) == 0:
        _rate_buckets.pop(user_id, None)


def _bind_sid(user_id: int) -> None:
    sid = request.sid
    _sid_users[sid] = user_id
    _user_sids[user_id].add(sid)


def _release_sid(sid: str) -> int | None:
    user_id = _sid_users.pop(sid, None)
    if user_id is not None:
        _user_sids[user_id].discard(sid)
        if not _user_sids[user_id]:
            _user_sids.pop(user_id, None)
    _sid_conversations.pop(sid, None)
    return user_id


def _track_conversation_join(sid: str, canon: str) -> None:
    rooms = _sid_conversations[sid]
    if canon not in rooms:
        rooms.append(canon)


def _untrack_conversation_leave(sid: str, canon: str) -> None:
    rooms = _sid_conversations.get(sid)
    if not rooms:
        return
    try:
        rooms.remove(canon)
    except ValueError:
        pass
    if not rooms:
        _sid_conversations.pop(sid, None)


def disconnect_user_sockets(user_id: int) -> None:
    """Logout/ban sonrası kullanıcının tüm socket bağlantılarını kapatır."""
    for sid in list(_user_sids.get(user_id, set())):
        try:
            socketio.server.disconnect(sid)
        except Exception:
            pass


def _finalize_disconnect(user_id: int, sid: str, convos: list[str]) -> bool:
    """Oda ayrılma, presence ve rate-limit temizliği. went_offline döner."""
    for canon in convos:
        _leave_room_safe(conversation_room(canon))
    _release_sid(sid)
    went_offline = _unregister_connection(user_id)
    room = user_room(user_id)
    _leave_room_safe(room)
    _cleanup_user_rate_limit(user_id)
    if went_offline:
        _set_last_seen(user_id)
        _broadcast_presence(user_id, online=False)
    return went_offline


def _join_room_safe(room: str) -> None:
    try:
        join_room(room)
    except (AttributeError, RuntimeError):
        pass


def _leave_room_safe(room: str) -> None:
    try:
        leave_room(room)
    except (AttributeError, RuntimeError):
        pass


def _conversation_filter(user_id: int, partner_id: int, kaynak_id, atik_id):
    return and_(
        or_(
            and_(Mesaj.sender_id == user_id, Mesaj.receiver_id == partner_id),
            and_(Mesaj.sender_id == partner_id, Mesaj.receiver_id == user_id),
        ),
        Mesaj.kaynak_id == kaynak_id,
        Mesaj.atik_id == atik_id,
    )


def user_can_access_conversation(user_id: int, partner_id: int, kaynak_id: int, atik_id: int) -> bool:
    if partner_id == user_id:
        return False
    if not db.session.get(User, partner_id):
        return False
    k_id = kaynak_id if kaynak_id != 0 else None
    a_id = atik_id if atik_id != 0 else None
    exists = db.session.query(Mesaj.id).filter(
        _conversation_filter(user_id, partner_id, k_id, a_id)
    ).first()
    return exists is not None


def user_can_join_conversation(user_id: int, partner_id: int, kaynak_id: int, atik_id: int) -> bool:
    if partner_id == user_id:
        return False
    return db.session.get(User, partner_id) is not None


def get_conversation_partner_ids(user_id: int) -> set[int]:
    sent = select(Mesaj.receiver_id).where(Mesaj.sender_id == user_id).distinct()
    recv = select(Mesaj.sender_id).where(Mesaj.receiver_id == user_id).distinct()
    rows = db.session.execute(union(sent, recv)).fetchall()
    return {row[0] for row in rows if row[0] != user_id}


def presence_payload(user: User | None, user_id: int) -> dict:
    last_seen = user.last_seen if user else None
    return {
        "user_id": user_id,
        "is_online": is_user_online(user_id),
        "last_seen": last_seen.isoformat() if last_seen else None,
        "last_seen_local": format_datetime(last_seen, "%d.%m.%Y %H:%M") if last_seen else None,
    }


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
    other_id = mesaj.receiver_id if mesaj.sender_id == for_user_id else mesaj.sender_id
    other = db.session.get(User, other_id)
    return {
        "conversation_id": conversation_id_for(mesaj, for_user_id),
        "canonical_conversation_id": canonical_conversation_id(
            mesaj.sender_id,
            mesaj.receiver_id,
            mesaj.kaynak_id or 0,
            mesaj.atik_id or 0,
        ),
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
    from services.message_unread_cache import set_unread_counts

    payload = {
        "message_unread": Mesaj.query.filter_by(receiver_id=user_id, is_read=False).count(),
        "notification_unread": Bildirim.query.filter_by(user_id=user_id, okundu=False).count(),
    }
    set_unread_counts(user_id, payload["message_unread"], payload["notification_unread"])
    return payload


def _set_last_seen(user_id: int) -> None:
    user = db.session.get(User, user_id)
    if not user:
        return
    user.last_seen = utc_now()
    db.session.commit()


def _broadcast_presence(user_id: int, online: bool) -> None:
    user = db.session.get(User, user_id)
    payload = presence_payload(user, user_id)
    event = "friend_online" if online else "friend_offline"
    _log_socket("PRESENCE", user_id=user_id, online=online)
    for partner_id in get_conversation_partner_ids(user_id):
        if is_user_online(partner_id):
            socketio.emit(event, payload, room=user_room(partner_id))


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


def _register_connection(user_id: int) -> bool:
    _connection_counts[user_id] += 1
    return _connection_counts[user_id] == 1


def _unregister_connection(user_id: int) -> bool:
    _connection_counts[user_id] = max(0, _connection_counts[user_id] - 1)
    if _connection_counts[user_id] == 0:
        _connection_counts.pop(user_id, None)
        return True
    return False


@socketio.on("connect")
def handle_connect():
    if not current_user.is_authenticated:
        raise ConnectionRefusedError("Giriş gerekli")
    from services.user_moderation import is_account_suspended

    user = db.session.get(User, int(current_user.get_id()))
    if not user or is_account_suspended(user):
        raise ConnectionRefusedError("Hesap askıya alındı")
    became_online = _register_connection(current_user.id)
    _bind_sid(current_user.id)
    room = user_room(current_user.id)
    _join_room_safe(room)
    _log_socket("JOIN", user_id=current_user.id, room=room, became_online=became_online)
    if became_online:
        _broadcast_presence(current_user.id, online=True)


@socketio.on("disconnect")
def handle_disconnect():
    sid = request.sid
    convos = list(_sid_conversations.get(sid, []))
    user_id = _sid_users.get(sid)
    if user_id is None and current_user.is_authenticated:
        user_id = current_user.id
    if user_id is None:
        _release_sid(sid)
        return
    went_offline = _finalize_disconnect(user_id, sid, convos)
    _log_socket(
        "LEAVE",
        user_id=user_id,
        room=user_room(user_id),
        went_offline=went_offline,
        sid=sid,
    )


@socketio.on("join")
def handle_join():
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    _connection_counts[current_user.id] = max(1, _connection_counts.get(current_user.id, 0))
    room = user_room(current_user.id)
    _join_room_safe(room)
    _log_socket("JOIN", user_id=current_user.id, room=room, via="join_event")
    emit_unread_count_updated(current_user.id)
    return {
        "room": room,
        "user_id": current_user.id,
        "presence": presence_payload(current_user, current_user.id),
    }


@socketio.on("leave")
def handle_leave():
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    room = user_room(current_user.id)
    _leave_room_safe(room)
    _log_socket("LEAVE", user_id=current_user.id, room=room, via="leave_event")
    return {"left": room}


@socketio.on("join_conversation")
def handle_join_conversation(data):
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    data = data or {}
    partner_id = int(data.get("partner_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if not user_can_join_conversation(current_user.id, partner_id, kaynak_id, atik_id):
        return {"error": "Yetkisiz"}
    canon = canonical_conversation_id(current_user.id, partner_id, kaynak_id, atik_id)
    room = conversation_room(canon)
    _join_room_safe(room)
    _track_conversation_join(request.sid, canon)
    _log_socket(
        "JOIN_CONVERSATION",
        user_id=current_user.id,
        room=room,
        partner_id=partner_id,
        canonical=canon,
    )
    partner = db.session.get(User, partner_id)
    return {
        "room": room,
        "canonical_conversation_id": canon,
        "conversation_id": f"{partner_id}-{kaynak_id}-{atik_id}",
        "partner": presence_payload(partner, partner_id),
    }


@socketio.on("leave_conversation")
def handle_leave_conversation(data):
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    data = data or {}
    partner_id = int(data.get("partner_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if partner_id:
        canon = canonical_conversation_id(current_user.id, partner_id, kaynak_id, atik_id)
        room = conversation_room(canon)
        _leave_room_safe(room)
        _untrack_conversation_leave(request.sid, canon)
        _log_socket("LEAVE_CONVERSATION", user_id=current_user.id, room=room)
    return {"left": True}


@socketio.on("typing_start")
def handle_typing_start(data):
    if not current_user.is_authenticated:
        return
    if not _check_rate_limit(current_user.id, "typing", RATE_SOCKET_TYPING_PER_SEC):
        return
    data = data or {}
    partner_id = int(data.get("partner_id") or data.get("receiver_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if not partner_id or partner_id == current_user.id:
        return
    if not user_can_join_conversation(current_user.id, partner_id, kaynak_id, atik_id):
        return
    canon = canonical_conversation_id(current_user.id, partner_id, kaynak_id, atik_id)
    conv = conversation_room(canon)
    payload = {
        "sender_id": current_user.id,
        "sender_name": current_user.username,
        "conversation_id": f"{partner_id}-{kaynak_id}-{atik_id}",
        "canonical_conversation_id": canon,
    }
    _log_emit("typing_start", conv, sender=current_user.id)
    socketio.emit("typing_start", payload, room=conv, include_self=False)


@socketio.on("typing_stop")
def handle_typing_stop(data):
    if not current_user.is_authenticated:
        return
    data = data or {}
    partner_id = int(data.get("partner_id") or data.get("receiver_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if not partner_id or partner_id == current_user.id:
        return
    if not user_can_join_conversation(current_user.id, partner_id, kaynak_id, atik_id):
        return
    canon = canonical_conversation_id(current_user.id, partner_id, kaynak_id, atik_id)
    conv = conversation_room(canon)
    payload = {
        "sender_id": current_user.id,
        "conversation_id": f"{partner_id}-{kaynak_id}-{atik_id}",
        "canonical_conversation_id": canon,
    }
    _log_emit("typing_stop", conv, sender=current_user.id)
    socketio.emit("typing_stop", payload, room=conv, include_self=False)


@socketio.on("typing")
def handle_typing_legacy(data):
    handle_typing_start(data)


@socketio.on("stop_typing")
def handle_stop_typing_legacy(data):
    handle_typing_stop(data)


@socketio.on("message_read")
def handle_message_read(data):
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    if not _check_rate_limit(current_user.id, "message_read", RATE_SOCKET_MESSAGE_PER_SEC):
        return {"error": "Çok fazla istek"}
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

    now = utc_now()
    for mesaj in messages:
        mesaj.is_read = True
        mesaj.read_at = now
    db.session.commit()
    _log_socket("MESSAGE_READ", reader=current_user.id, count=len(messages))
    emit_messages_marked_read(messages, current_user.id)
    return {"updated": len(messages)}


@socketio.on("sync_state")
def handle_sync_state(data):
    if not current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    if not _check_rate_limit(current_user.id, "sync_state", RATE_SOCKET_SYNC_STATE_PER_SEC):
        return {"error": "Çok fazla istek"}
    data = data or {}
    partner_id = int(data.get("partner_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    after_id = int(data.get("after_message_id") or 0)
    if not partner_id:
        return {"error": "Eksik veri"}
    if not user_can_join_conversation(current_user.id, partner_id, kaynak_id, atik_id):
        return {"error": "Yetkisiz"}
    k_id = kaynak_id if kaynak_id != 0 else None
    a_id = atik_id if atik_id != 0 else None
    query = Mesaj.query.filter(
        _conversation_filter(current_user.id, partner_id, k_id, a_id),
    )
    if after_id:
        query = query.filter(Mesaj.id > after_id)
    rows = query.order_by(Mesaj.id.asc()).limit(100).all()
    _log_socket(
        "SYNC",
        user_id=current_user.id,
        partner_id=partner_id,
        after_id=after_id,
        count=len(rows),
    )
    return {
        "messages": [serialize_message(m, current_user.id) for m in rows],
        "unread": unread_counts_for(current_user.id),
    }
