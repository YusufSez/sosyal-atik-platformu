"""Mesajlaşma pro özellikleri — presence, typing, read receipt, rooms."""

from unittest.mock import patch

import pytest
from flask_login import login_user

from auth_utils import hash_password
from extensions import db, socketio
from models import Mesaj, User
from socket_events import (
    canonical_conversation_id,
    conversation_room,
    emit_notification_sync,
    get_online_users,
    is_user_online,
)


@pytest.fixture(autouse=True)
def bypass_message_moderation(monkeypatch):
    monkeypatch.setattr(
        "blueprints.messages.mesaj_uygun_mu",
        lambda _content: (True, ""),
    )


@pytest.fixture(autouse=True)
def reset_socket_state():
    import socket_events

    socket_events._connection_counts.clear()
    socket_events._rate_buckets.clear()
    yield
    socket_events._connection_counts.clear()
    socket_events._rate_buckets.clear()


def _create_pair(app):
    with app.app_context():
        sender = User(
            username="pro_sender",
            email="pro_sender@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        receiver = User(
            username="pro_receiver",
            email="pro_receiver@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sender, receiver])
        db.session.commit()
        return sender.id, receiver.id


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


def test_typing_start_stop_uses_conversation_room(app):
    from socket_events import handle_typing_start, handle_typing_stop, user_room
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        sender = db.session.get(User, sender_id)
        canon = canonical_conversation_id(sender_id, receiver_id, 0, 0)

        with app.test_request_context():
            with patch("socket_events.socketio.emit") as emit_mock:
                login_user(sender)
                handle_typing_start(
                    {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0}
                )
                handle_typing_stop(
                    {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0}
                )

        names = [call.args[0] for call in emit_mock.call_args_list]
        assert "typing_start" in names
        assert "typing_stop" in names
        assert emit_mock.call_args_list[0].kwargs["room"] == conversation_room(canon)


def test_message_emit_uses_conversation_room(app):
    from socket_events import emit_after_message_created, user_room
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Room test")
        db.session.add(mesaj)
        db.session.commit()
        mesaj = db.session.get(Mesaj, mesaj.id)
        canon = canonical_conversation_id(sender_id, receiver_id, 0, 0)

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                emit_after_message_created(mesaj)

        rooms = [call.kwargs.get("room") for call in emit_mock.call_args_list]
        events = [call.args[0] for call in emit_mock.call_args_list]
        assert conversation_room(canon) in rooms
        assert "message_sent" in events
        assert "new_message" in events
        assert user_room(sender_id) in rooms
        assert user_room(receiver_id) in rooms


def test_join_conversation_requires_valid_partner(app, client):
    _, receiver_id = _create_pair(app)
    _login(client, "pro_sender@test.com")
    socket_client = _socket_client(app, client)

    result = socket_client.emit(
        "join_conversation",
        {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0},
        callback=True,
    )
    assert "room" in result
    assert result["room"].startswith("conversation_")
    socket_client.disconnect()


def test_join_conversation_rejects_self(app, client):
    sender_id, _ = _create_pair(app)
    _login(client, "pro_sender@test.com")
    socket_client = _socket_client(app, client)

    result = socket_client.emit(
        "join_conversation",
        {"partner_id": sender_id, "kaynak_id": 0, "atik_id": 0},
        callback=True,
    )
    assert result.get("error") == "Yetkisiz"
    socket_client.disconnect()


def test_message_read_sets_read_at(app, client):
    sender_id, receiver_id = _create_pair(app)
    with app.app_context():
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Oku")
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id

    receiver_client = app.test_client()
    _login(receiver_client, "pro_receiver@test.com")
    receiver_socket = _socket_client(app, receiver_client)

    result = receiver_socket.emit("message_read", {"message_ids": [mesaj_id]}, callback=True)
    assert result["updated"] == 1

    with app.app_context():
        saved = db.session.get(Mesaj, mesaj_id)
        assert saved.is_read is True
        assert saved.read_at is not None

    receiver_socket.disconnect()


def test_presence_friend_online_offline(app):
    from socket_events import user_room
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        mesaj = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="Merhaba")
        db.session.add(mesaj)
        db.session.commit()

        import socket_events

        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                socket_events._connection_counts[sender_id] = 1
                socket_events._broadcast_presence(sender_id, online=True)

        online_events = [c for c in emit_mock.call_args_list if c.args[0] == "friend_online"]
        assert online_events
        assert online_events[0].kwargs["room"] == user_room(receiver_id)

        with patch("socket_events.socketio.emit") as emit_mock2:
            with patch("socket_events.is_user_online", return_value=True):
                socket_events._set_last_seen(sender_id)
                socket_events._broadcast_presence(sender_id, online=False)

        offline_events = [c for c in emit_mock2.call_args_list if c.args[0] == "friend_offline"]
        assert offline_events

        user = db.session.get(User, sender_id)
        assert user.last_seen is not None


def test_multi_tab_single_online_user(app, client):
    sender_id, _ = _create_pair(app)
    _login(client, "pro_sender@test.com")

    socket_a = _socket_client(app, client)
    socket_b = _socket_client(app, client)

    import socket_events

    assert socket_events._connection_counts[sender_id] == 2
    assert is_user_online(sender_id) is True

    socket_a.disconnect()
    assert is_user_online(sender_id) is True

    socket_b.disconnect()
    assert is_user_online(sender_id) is False
    assert sender_id not in get_online_users()


def test_sync_state_returns_missing_messages(app, client):
    sender_id, receiver_id = _create_pair(app)
    with app.app_context():
        first = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="1")
        second = Mesaj(sender_id=sender_id, receiver_id=receiver_id, content="2")
        db.session.add_all([first, second])
        db.session.commit()
        first_id = first.id

    _login(client, "pro_receiver@test.com")
    socket_client = _socket_client(app, client)

    result = socket_client.emit(
        "sync_state",
        {
            "partner_id": sender_id,
            "kaynak_id": 0,
            "atik_id": 0,
            "after_message_id": first_id,
        },
        callback=True,
    )
    assert len(result["messages"]) == 1
    assert result["messages"][0]["message"] == "2"
    socket_client.disconnect()


def test_typing_rate_limit(app):
    from socket_events import handle_typing_start
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        sender = db.session.get(User, sender_id)

        with app.test_request_context():
            login_user(sender)
            with patch("socket_events.socketio.emit") as emit_mock:
                for _ in range(12):
                    handle_typing_start(
                        {"partner_id": receiver_id, "kaynak_id": 0, "atik_id": 0}
                    )
        assert emit_mock.call_count <= 10


def test_notification_sync_emit_unit(app):
    with app.app_context():
        _, receiver_id = _create_pair(app)
        with patch("socket_events.socketio.emit") as emit_mock:
            with patch("socket_events.is_user_online", return_value=True):
                emit_notification_sync(receiver_id)
        assert emit_mock.call_args.args[0] == "notification_sync"


def test_stranger_gets_own_conversation_room(app, client):
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        stranger = User(
            username="stranger",
            email="stranger@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add(stranger)
        db.session.commit()
        stranger_id = stranger.id

    stranger_client = app.test_client()
    _login(stranger_client, "stranger@test.com")
    socket_client = _socket_client(app, stranger_client)

    result = socket_client.emit(
        "join_conversation",
        {"partner_id": sender_id, "kaynak_id": 0, "atik_id": 0},
        callback=True,
    )
    sender_receiver_room = conversation_room(
        canonical_conversation_id(sender_id, receiver_id, 0, 0)
    )
    assert result["room"] != sender_receiver_room
    assert result["room"] == conversation_room(
        canonical_conversation_id(stranger_id, sender_id, 0, 0)
    )
    socket_client.disconnect()
