from flask import request
from flask_socketio import join_room, leave_room

from models import Mesaj

from .state import _sid_conversations, _sid_users, _user_sids


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
