"""Flask-SocketIO altyapı testleri."""

from unittest.mock import MagicMock

import pytest
from socketio.exceptions import ConnectionRefusedError

import socket_events
from extensions import socketio


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
        monkeypatch.setattr(socket_events, "current_user", MagicMock(is_authenticated=False))
        with pytest.raises(ConnectionRefusedError):
            socket_events.handle_connect()


def test_connect_handler_allows_authenticated(app, monkeypatch):
    with app.test_request_context():
        monkeypatch.setattr(socket_events, "current_user", MagicMock(is_authenticated=True))
        assert socket_events.handle_connect() is None


def test_authenticated_socket_connection_allowed(client, app):
    _register_and_login(client)
    socket_client = socketio.test_client(app, flask_test_client=client)
    assert socket_client.is_connected()
    socket_client.disconnect()


def test_socket_test_page_requires_login(client):
    response = client.get("/socket-test", follow_redirects=False)
    assert response.status_code == 302


def test_socket_test_page_csp_safe_assets(client):
    _register_and_login(client)
    response = client.get("/socket-test")
    assert response.status_code == 200
    body = response.data.decode("utf-8")
    assert "vendor/socket.io.min.js" in body
    assert "js/socket-test.js" in body
    assert "cdn.socket.io" not in body
    assert "<script>" not in body


def test_vendored_socket_asset_served(client):
    response = client.get("/static/vendor/socket.io.min.js")
    assert response.status_code == 200
    assert b"Socket.IO v4.8.1" in response.data
