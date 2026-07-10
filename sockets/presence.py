from sqlalchemy import select, union

from extensions import db
from models import Mesaj, User
from utils import format_datetime, utc_now

from .rate_limit import _cleanup_user_rate_limit
from .rooms import (
    _leave_room_safe,
    _release_sid,
    conversation_room,
    user_room,
)
from .state import _connection_counts, _sid_users, _user_sids
from .utils import _log_socket


def is_user_online(user_id: int) -> bool:
    return _connection_counts.get(user_id, 0) > 0


def get_online_users() -> set[int]:
    return {uid for uid, count in _connection_counts.items() if count > 0}


def get_conversation_partner_ids(user_id: int) -> set[int]:
    sent = select(Mesaj.receiver_id).where(Mesaj.sender_id == user_id).distinct()
    recv = select(Mesaj.sender_id).where(Mesaj.receiver_id == user_id).distinct()
    rows = db.session.execute(union(sent, recv)).fetchall()
    return {row[0] for row in rows if row[0] != user_id}


def presence_payload(user: User | None, user_id: int) -> dict:
    import socket_events

    last_seen = user.last_seen if user else None
    return {
        "user_id": user_id,
        "is_online": socket_events.is_user_online(user_id),
        "last_seen": last_seen.isoformat() if last_seen else None,
        "last_seen_local": format_datetime(last_seen, "%d.%m.%Y %H:%M") if last_seen else None,
    }


def _set_last_seen(user_id: int) -> None:
    user = db.session.get(User, user_id)
    if not user:
        return
    user.last_seen = utc_now()
    db.session.commit()


def _broadcast_presence(user_id: int, online: bool) -> None:
    import socket_events

    user = db.session.get(User, user_id)
    payload = presence_payload(user, user_id)
    event = "friend_online" if online else "friend_offline"
    _log_socket("PRESENCE", user_id=user_id, online=online)
    for partner_id in get_conversation_partner_ids(user_id):
        if socket_events.is_user_online(partner_id):
            socket_events.socketio.emit(event, payload, room=user_room(partner_id))


def disconnect_user_sockets(user_id: int) -> None:
    """Logout/ban sonrası kullanıcının tüm socket bağlantılarını kapatır."""
    import socket_events

    for sid in list(_user_sids.get(user_id, set())):
        try:
            socket_events.socketio.server.disconnect(sid)
        except Exception:
            pass


def _register_connection(user_id: int) -> bool:
    _connection_counts[user_id] += 1
    return _connection_counts[user_id] == 1


def _unregister_connection(user_id: int) -> bool:
    _connection_counts[user_id] = max(0, _connection_counts[user_id] - 1)
    if _connection_counts[user_id] == 0:
        _connection_counts.pop(user_id, None)
        return True
    return False


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
