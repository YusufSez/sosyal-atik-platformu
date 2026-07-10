from constants import RATE_SOCKET_TYPING_PER_SEC
from extensions import socketio

from .permissions import user_can_access_conversation
from .rate_limit import _check_rate_limit
from .rooms import canonical_conversation_id, conversation_room
from .utils import _log_emit


def handle_typing_start(data):
    import socket_events

    current_user = socket_events.current_user
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
    if not user_can_access_conversation(current_user.id, partner_id, kaynak_id, atik_id):
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


def handle_typing_stop(data):
    import socket_events

    current_user = socket_events.current_user
    if not current_user.is_authenticated:
        return
    data = data or {}
    partner_id = int(data.get("partner_id") or data.get("receiver_id") or 0)
    kaynak_id = int(data.get("kaynak_id") or 0)
    atik_id = int(data.get("atik_id") or 0)
    if not partner_id or partner_id == current_user.id:
        return
    if not user_can_access_conversation(current_user.id, partner_id, kaynak_id, atik_id):
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
