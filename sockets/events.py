"""Flask-SocketIO event handler kaydı."""

import socket_events
from extensions import socketio
from socketio.exceptions import ConnectionRefusedError

from constants import (
    RATE_SOCKET_MESSAGE_PER_SEC,
    RATE_SOCKET_SYNC_STATE_PER_SEC,
)
from extensions import db
from models import Mesaj, User
from utils import utc_now

from .emitters import (
    emit_messages_marked_read,
    emit_unread_count_updated,
)
from .permissions import _conversation_filter, user_can_access_conversation
from .presence import (
    _broadcast_presence,
    _finalize_disconnect,
    _register_connection,
    presence_payload,
)
from .rate_limit import _check_rate_limit
from .rooms import (
    _bind_sid,
    _join_room_safe,
    _leave_room_safe,
    _release_sid,
    _track_conversation_join,
    _untrack_conversation_leave,
    canonical_conversation_id,
    conversation_room,
    user_room,
)
from .serializer import serialize_message, unread_counts_for
from .state import _connection_counts, _sid_conversations, _sid_users
from .typing import handle_typing_start, handle_typing_stop
from .utils import _log_socket


@socketio.on("connect")
def handle_connect():
    if not socket_events.current_user.is_authenticated:
        raise ConnectionRefusedError("Giriş gerekli")
    from services.user_moderation import is_account_suspended

    user = db.session.get(User, int(socket_events.current_user.get_id()))
    if not user or is_account_suspended(user):
        raise ConnectionRefusedError("Hesap askıya alındı")
    became_online = _register_connection(socket_events.current_user.id)
    _bind_sid(socket_events.current_user.id)
    room = user_room(socket_events.current_user.id)
    _join_room_safe(room)
    _log_socket(
        "JOIN",
        user_id=socket_events.current_user.id,
        room=room,
        became_online=became_online,
    )
    if became_online:
        _broadcast_presence(socket_events.current_user.id, online=True)


@socketio.on("disconnect")
def handle_disconnect():
    sid = socket_events.request.sid
    convos = list(_sid_conversations.get(sid, []))
    user_id = _sid_users.get(sid)
    if user_id is None and socket_events.current_user.is_authenticated:
        user_id = socket_events.current_user.id
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
    if not socket_events.current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    _connection_counts[socket_events.current_user.id] = max(
        1, _connection_counts.get(socket_events.current_user.id, 0)
    )
    room = user_room(socket_events.current_user.id)
    _join_room_safe(room)
    _log_socket(
        "JOIN",
        user_id=socket_events.current_user.id,
        room=room,
        via="join_event",
    )
    emit_unread_count_updated(socket_events.current_user.id)
    return {
        "room": room,
        "user_id": socket_events.current_user.id,
        "presence": presence_payload(socket_events.current_user, socket_events.current_user.id),
    }


@socketio.on("leave")
def handle_leave():
    if not socket_events.current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    room = user_room(socket_events.current_user.id)
    _leave_room_safe(room)
    _log_socket(
        "LEAVE",
        user_id=socket_events.current_user.id,
        room=room,
        via="leave_event",
    )
    return {"left": room}


@socketio.on("join_conversation")
def handle_join_conversation(data):
    if not socket_events.current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    data = data or {}
    partner_id = int(data.get("partner_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if not user_can_access_conversation(
        socket_events.current_user.id, partner_id, kaynak_id, atik_id
    ):
        return {"error": "Yetkisiz"}
    canon = canonical_conversation_id(
        socket_events.current_user.id, partner_id, kaynak_id, atik_id
    )
    room = conversation_room(canon)
    _join_room_safe(room)
    _track_conversation_join(socket_events.request.sid, canon)
    _log_socket(
        "JOIN_CONVERSATION",
        user_id=socket_events.current_user.id,
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
    if not socket_events.current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    data = data or {}
    partner_id = int(data.get("partner_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if partner_id:
        if not user_can_access_conversation(
            socket_events.current_user.id, partner_id, kaynak_id, atik_id
        ):
            return {"error": "Yetkisiz"}
        canon = canonical_conversation_id(
            socket_events.current_user.id, partner_id, kaynak_id, atik_id
        )
        room = conversation_room(canon)
        _leave_room_safe(room)
        _untrack_conversation_leave(socket_events.request.sid, canon)
        _log_socket("LEAVE_CONVERSATION", user_id=socket_events.current_user.id, room=room)
    return {"left": True}


@socketio.on("typing_start")
def handle_typing_start_event(data):
    handle_typing_start(data)


@socketio.on("typing_stop")
def handle_typing_stop_event(data):
    handle_typing_stop(data)


@socketio.on("typing")
def handle_typing_legacy(data):
    handle_typing_start(data)


@socketio.on("stop_typing")
def handle_stop_typing_legacy(data):
    handle_typing_stop(data)


@socketio.on("message_read")
def handle_message_read(data):
    if not socket_events.current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    if not _check_rate_limit(
        socket_events.current_user.id, "message_read", RATE_SOCKET_MESSAGE_PER_SEC
    ):
        return {"error": "Çok fazla istek"}
    data = data or {}
    message_ids = data.get("message_ids") or []
    if not message_ids:
        message_id = data.get("message_id")
        if message_id:
            message_ids = [message_id]

    messages = Mesaj.query.filter(
        Mesaj.id.in_(message_ids),
        Mesaj.receiver_id == socket_events.current_user.id,
        Mesaj.is_read.is_(False),
    ).all()
    messages = [
        mesaj
        for mesaj in messages
        if user_can_access_conversation(
            socket_events.current_user.id,
            mesaj.sender_id,
            mesaj.kaynak_id or 0,
            mesaj.atik_id or 0,
        )
    ]
    if not messages:
        return {"updated": 0}

    now = utc_now()
    for mesaj in messages:
        mesaj.is_read = True
        mesaj.read_at = now
    db.session.commit()
    _log_socket("MESSAGE_READ", reader=socket_events.current_user.id, count=len(messages))
    emit_messages_marked_read(messages, socket_events.current_user.id)
    return {"updated": len(messages)}


@socketio.on("sync_state")
def handle_sync_state(data):
    if not socket_events.current_user.is_authenticated:
        return {"error": "Giriş gerekli"}
    if not _check_rate_limit(
        socket_events.current_user.id, "sync_state", RATE_SOCKET_SYNC_STATE_PER_SEC
    ):
        return {"error": "Çok fazla istek"}
    data = data or {}
    partner_id = int(data.get("partner_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    after_id = int(data.get("after_message_id") or 0)
    if not partner_id:
        return {"error": "Eksik veri"}
    if not user_can_access_conversation(
        socket_events.current_user.id, partner_id, kaynak_id, atik_id
    ):
        return {"error": "Yetkisiz"}
    k_id = kaynak_id if kaynak_id != 0 else None
    a_id = atik_id if atik_id != 0 else None
    query = Mesaj.query.filter(
        _conversation_filter(socket_events.current_user.id, partner_id, k_id, a_id),
    )
    if after_id:
        query = query.filter(Mesaj.id > after_id)
    rows = query.order_by(Mesaj.id.asc()).limit(100).all()
    _log_socket(
        "SYNC",
        user_id=socket_events.current_user.id,
        partner_id=partner_id,
        after_id=after_id,
        count=len(rows),
    )
    return {
        "messages": [serialize_message(m, socket_events.current_user.id) for m in rows],
        "unread": unread_counts_for(socket_events.current_user.id),
    }
