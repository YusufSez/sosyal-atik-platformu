"""SocketIO mesajlaşma gerçek zamanlı testleri."""

from unittest.mock import patch

import pytest

from auth_utils import hash_password
from extensions import db, socketio
from models import Mesaj, User
from socket_events import (
    canonical_conversation_id,
    conversation_room,
    emit_after_message_created,
    emit_messages_marked_read,
    is_user_online,
    user_room,
)


@pytest.fixture(autouse=True)
def bypass_message_moderation(monkeypatch):
    monkeypatch.setattr(
        "blueprints.messages.mesaj_uygun_mu",
        lambda _content: (True, ""),
    )


@pytest.fixture(autouse=True)
def reset_socket_connection_counts():
    import socket_events

    socket_events._connection_counts.clear()
    socket_events._rate_buckets.clear()
    socket_events._sid_users.clear()
    socket_events._user_sids.clear()
    socket_events._sid_conversations.clear()
    yield
    socket_events._connection_counts.clear()
    socket_events._rate_buckets.clear()
    socket_events._sid_users.clear()
    socket_events._user_sids.clear()
    socket_events._sid_conversations.clear()


def _event_names(events):
    return [event["name"] for event in events]


def _event_payload(events, name):
    for event in events:
        if event["name"] == name:
            args = event.get("args") or []
            return args[0] if args else {}
    return None


def _create_users(app):
    with app.app_context():
        sender = User(
            username="sock_sender",
            email="sock_sender@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        receiver = User(
            username="sock_receiver",
            email="sock_receiver@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        outsider = User(
            username="sock_outsider",
            email="sock_outsider@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sender, receiver, outsider])
        db.session.commit()
        return sender.id, receiver.id, outsider.id


def _login(client, email):
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


def _socket_client(app, flask_client):
    client = socketio.test_client(app, flask_test_client=flask_client)
    client.emit("join", callback=True)
    client.get_received()
    return client


def test_new_message_emitted_to_conversation_room(app):
    with app.app_context():
        sender = User(
            username="sock_sender_live",
            email="sock_sender_live@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        receiver = User(
            username="sock_receiver_live",
            email="sock_receiver_live@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sender, receiver])
        db.session.commit()
        sender_id = sender.id
        receiver_id = receiver.id
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Canlı test")
        db.session.add(mesaj)
        db.session.commit()
        mesaj = db.session.get(Mesaj, mesaj.id)
        canon = canonical_conversation_id(sender_id, receiver_id, 0, 0)

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                emit_after_message_created(mesaj)

        events = [call.args[0] for call in emit_mock.call_args_list]
        assert "new_message" in events
        new_msg_call = next(c for c in emit_mock.call_args_list if c.args[0] == "new_message")
        assert new_msg_call.args[1]["message"] == "Canlı test"
        assert new_msg_call.kwargs["room"] == conversation_room(canon)


def test_sender_gets_message_sent_confirmation(client, app):
    sender_id, receiver_id, _ = _create_users(app)
    with app.app_context():
        db.session.add(
            Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="önceden")
        )
        db.session.commit()
    _login(client, "sock_sender@test.com")
    sender_socket = _socket_client(app, client)
    sender_socket.emit(
        "join_conversation",
        {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0},
        callback=True,
    )
    sender_socket.get_received()

    client.post(
        "/send_message",
        json={"alici_id": receiver_id, "content": "Onay testi", "kaynak_id": 0, "atik_id": 0},
    )

    events = sender_socket.get_received()
    sent = _event_payload(events, "message_sent")
    assert sent["message"] == "Onay testi"
    sender_socket.disconnect()


def test_typing_and_stop_typing_unit(app, client):
    sender_id, receiver_id, _ = _create_users(app)
    with app.app_context():
        db.session.add(
            Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="typing")
        )
        db.session.commit()

    with app.test_request_context():
        import socket_events
        from flask_login import login_user

        sender = db.session.get(User, sender_id)
        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                login_user(sender)
                socket_events.handle_typing_start(
                    {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0}
                )
                socket_events.handle_typing_stop(
                    {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0}
                )

        event_names = [call.args[0] for call in emit_mock.call_args_list]
        assert "typing_start" in event_names
        assert "typing_stop" in event_names
        canon = canonical_conversation_id(sender_id, receiver_id, 0, 0)
        assert emit_mock.call_args_list[0].kwargs["room"] == conversation_room(canon)


def test_read_receipt_unit(app):
    with app.app_context():
        sender_id, receiver_id, _ = _create_users(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Okundu mu?")
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                emit_messages_marked_read([db.session.get(Mesaj, mesaj_id)], receiver_id)

        assert any(call.args[0] == "message_read" for call in emit_mock.call_args_list)


def test_unread_count_updated_for_receiver(client, app):
    _, receiver_id, _ = _create_users(app)

    receiver_client = app.test_client()
    _login(receiver_client, "sock_receiver@test.com")
    receiver_socket = _socket_client(app, receiver_client)

    _login(client, "sock_sender@test.com")
    client.post(
        "/send_message",
        json={"alici_id": receiver_id, "content": "Badge test", "kaynak_id": 0, "atik_id": 0},
    )

    events = receiver_socket.get_received()
    assert "unread_count_updated" in _event_names(events)
    unread = _event_payload(events, "unread_count_updated")
    assert unread["message_unread"] >= 1

    receiver_socket.disconnect()


def test_room_isolation_unit(app):
    with app.app_context():
        sender_id, receiver_id, _ = _create_users(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Gizli")
        db.session.add(mesaj)
        db.session.commit()
        mesaj = db.session.get(Mesaj, mesaj.id)
        canon = canonical_conversation_id(sender_id, receiver_id, 0, 0)

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                emit_after_message_created(mesaj)

        rooms = [call.kwargs.get("room") for call in emit_mock.call_args_list]
        event_names = [call.args[0] for call in emit_mock.call_args_list]

        assert conversation_room(canon) in rooms
        assert user_room(sender_id) in rooms
        assert user_room(receiver_id) in rooms
        assert "new_message" in event_names
        assert "message_sent" in event_names


def test_unauthorized_room_join_rejected(client, app):
    _, _, outsider_id = _create_users(app)
    _login(client, "sock_outsider@test.com")
    outsider_socket = _socket_client(app, client)

    result = outsider_socket.emit("join", callback=True)
    assert result["room"] == user_room(outsider_id)
    assert result["room"] != user_room(outsider_id + 999)
    outsider_socket.disconnect()


def test_offline_user_still_emits_to_conversation_room(app):
    """Oda üyeleri bağlıyken mesaj her zaman conversation odasına gider."""
    with app.app_context():
        sender_id, receiver_id, _ = _create_users(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Offline")
        db.session.add(mesaj)
        db.session.commit()
        mesaj = db.session.get(Mesaj, mesaj.id)
        canon = canonical_conversation_id(sender_id, receiver_id, 0, 0)

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=False):
                emit_after_message_created(mesaj)

        event_names = [call.args[0] for call in emit_mock.call_args_list]
        assert "message_sent" in event_names
        assert "new_message" in event_names
        new_msg_call = next(c for c in emit_mock.call_args_list if c.args[0] == "new_message")
        assert new_msg_call.kwargs["room"] == conversation_room(canon)


def test_mesajlar_getir_emits_read_receipt(app):
    with app.app_context():
        sender_id, receiver_id, _ = _create_users(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Fetch okundu")
        db.session.add(mesaj)
        db.session.commit()

        from blueprints.messages import mesajlar_getir
        from flask_login import login_user

        receiver = db.session.get(User, receiver_id)
        with app.test_request_context(f"/mesajlar_getir/{sender_id}/0/0"):
            with patch("socket_events.socketio.emit") as emit_mock:
                with patch("socket_events.is_user_online", return_value=True):
                    login_user(receiver)
                    mesajlar_getir(sender_id, 0, 0)

                assert any(call.args[0] == "message_read" for call in emit_mock.call_args_list)


def test_emit_messages_marked_read_always_emits(app):
    with app.app_context():
        sender_id, receiver_id, _ = _create_users(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="x", is_read=True)
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=False):
                emit_messages_marked_read(
                    [db.session.get(Mesaj, mesaj_id)],
                    receiver_id,
                )

        assert any(call.args[0] == "message_read" for call in emit_mock.call_args_list)


def test_is_user_online_tracks_join(app, client):
    _, _, outsider_id = _create_users(app)
    assert is_user_online(outsider_id) is False
    _login(client, "sock_outsider@test.com")
    socket_client = _socket_client(app, client)
    assert is_user_online(outsider_id) is True
    socket_client.disconnect()
