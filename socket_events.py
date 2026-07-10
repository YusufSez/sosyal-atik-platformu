"""Flask-SocketIO — mesajlaşma, presence ve conversation odaları (uyumluluk katmanı)."""

from flask import request
from flask_login import current_user

from extensions import db, socketio

from sockets.emitters import (
    emit_after_message_created,
    emit_messages_marked_read,
    emit_notification_sync,
    emit_unread_count_updated,
)
from sockets.events import (
    handle_connect,
    handle_disconnect,
    handle_join,
    handle_join_conversation,
    handle_leave,
    handle_leave_conversation,
    handle_message_read,
    handle_stop_typing_legacy,
    handle_sync_state,
    handle_typing_legacy,
    handle_typing_start_event,
    handle_typing_stop_event,
)
from sockets.permissions import (
    user_can_access_conversation,
    user_can_join_conversation,
)
from sockets.presence import (
    _broadcast_presence,
    _finalize_disconnect,
    _register_connection,
    _set_last_seen,
    _unregister_connection,
    disconnect_user_sockets,
    get_online_users,
    is_user_online,
    presence_payload,
)
from sockets.rate_limit import _check_rate_limit, _cleanup_user_rate_limit
from sockets.rooms import (
    _bind_sid,
    _join_room_safe,
    _leave_room_safe,
    _release_sid,
    _track_conversation_join,
    _untrack_conversation_leave,
    canonical_conversation_id,
    conversation_id_for,
    conversation_room,
    parse_conversation_parts,
    user_room,
)
from sockets.serializer import (
    build_conversation_updated,
    serialize_message,
    unread_counts_for,
)
from sockets.state import (
    _connection_counts,
    _rate_buckets,
    _sid_conversations,
    _sid_users,
    _user_sids,
)
from sockets.typing import handle_typing_start, handle_typing_stop
from sockets.utils import _log_emit, _log_socket, logger

__all__ = [
    "canonical_conversation_id",
    "conversation_id_for",
    "conversation_room",
    "current_user",
    "db",
    "disconnect_user_sockets",
    "emit_after_message_created",
    "emit_messages_marked_read",
    "emit_notification_sync",
    "emit_unread_count_updated",
    "get_online_users",
    "handle_connect",
    "handle_disconnect",
    "handle_join",
    "handle_join_conversation",
    "handle_leave",
    "handle_leave_conversation",
    "handle_message_read",
    "handle_sync_state",
    "handle_typing_start",
    "handle_typing_stop",
    "is_user_online",
    "logger",
    "parse_conversation_parts",
    "presence_payload",
    "request",
    "serialize_message",
    "socketio",
    "unread_counts_for",
    "user_can_access_conversation",
    "user_can_join_conversation",
    "user_room",
    "_broadcast_presence",
    "_bind_sid",
    "_check_rate_limit",
    "_cleanup_user_rate_limit",
    "_connection_counts",
    "_finalize_disconnect",
    "_join_room_safe",
    "_leave_room_safe",
    "_log_emit",
    "_log_socket",
    "_rate_buckets",
    "_register_connection",
    "_release_sid",
    "_set_last_seen",
    "_sid_conversations",
    "_sid_users",
    "_track_conversation_join",
    "_untrack_conversation_leave",
    "_unregister_connection",
    "_user_sids",
    "build_conversation_updated",
]
