"""Flask-SocketIO altyapı testleri."""

from unittest.mock import MagicMock

import pytest
from socketio.exceptions import ConnectionRefusedError

from auth_utils import hash_password
from extensions import db, socketio
from models import User
import socket_events


def _register_and_login(client, email="socket@test.com", username="socketuser"):
    client.post(
        "/kayit",
        data={
            "username": username,
            "email": email,
            "password": "TestPass1",
            "password_tekrar": "TestPass1",
            "kullanim_kosullari": "on",
        },
        follow_redirects=True,
    )
    client.post(
        "/profil_tamamla",
        data={
            "dogum_tarihi": "1990-01-01",
            "il": "İstanbul",
            "ilce": "Kadıköy",
            "telefon": "5551234567",
        },
        follow_redirects=True,
    )


def test_connect_handler_rejects_unauthenticated(app, monkeypatch):
    with app.test_request_context():
        monkeypatch.setattr(
            socket_events,
            "current_user",
            MagicMock(is_authenticated=False),
        )
        with pytest.raises(ConnectionRefusedError):
            socket_events.handle_connect()


def test_connect_handler_allows_authenticated(app, monkeypatch):
    with app.test_request_context():
        monkeypatch.setattr(
            socket_events,
            "current_user",
            MagicMock(is_authenticated=True),
        )
        assert socket_events.handle_connect() is None


def test_authenticated_socket_connection_allowed(client, app):
    _register_and_login(client)
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()
    socket_client.disconnect()


def test_socket_test_page_requires_login(client):
    response = client.get("/socket-test", follow_redirects=False)
    assert response.status_code == 302


def test_socket_test_page_renders_for_logged_in_user(client):
    _register_and_login(client)
    response = client.get("/socket-test")
    assert response.status_code == 200
    assert b"SocketIO Test" in response.data
    assert b"socket.io" in response.data


def test_socket_connect_disconnect_events(client, app):
    _register_and_login(client, email="sock2@test.com", username="sock2")
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()
    received = socket_client.get_received()
    socket_client.disconnect()
    assert not socket_client.is_connected()
    # connect/disconnect handler'ları hata fırlatmamalı
    assert isinstance(received, list)
