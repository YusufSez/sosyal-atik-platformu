"""Production Hardening Phase 4 regression tests."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from flask import url_for
from flask_login import login_user

from auth_utils import hash_password
from extensions import db, socketio
from factory import create_app
from models import Atik, Bildirim, Kaynak, Mesaj, User
from services.notifications import bildirim_olustur
from socket_events import user_can_access_conversation
from utils import safe_notification_link, safe_redirect_url


def _make_user(username, email):
    user = User(
        username=username,
        email=email,
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
    )
    db.session.add(user)
    db.session.commit()
    return user


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


# --- 1) Search endpoints ---


def test_kaynak_panel_search_does_not_500(client, app):
    with app.app_context():
        owner = _make_user("search_owner_k", "search_owner_k@test.com")
        kaynak = Kaynak(
            user_id=owner.id,
            baslik="Aranabilir Kaynak",
            aciklama="Test açıklama",
            durum="İkinci El",
            kategori="Elektronik",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add(kaynak)
        db.session.commit()

    response = client.get("/kaynak_panel?ara=Aranabilir")
    assert response.status_code == 200
    assert b"Aranabilir Kaynak" in response.data


def test_atik_panel_search_does_not_500(client, app):
    with app.app_context():
        owner = _make_user("search_owner_a", "search_owner_a@test.com")
        atik = Atik(
            user_id=owner.id,
            baslik="Aranabilir Atik",
            aciklama="Test açıklama",
            kategori="Plastik",
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add(atik)
        db.session.commit()

    response = client.get("/atik_panel?ara=Aranabilir")
    assert response.status_code == 200
    assert b"Aranabilir Atik" in response.data


def test_admin_reports_search_does_not_500(client, app):
    with app.app_context():
        admin = User(
            username="search_admin",
            email="search_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            is_admin=True,
            role="admin",
        )
        db.session.add(admin)
        db.session.commit()

    _login(client, "search_admin@test.com")
    response = client.get("/admin/reports/search?q=test")
    assert response.status_code == 200
    assert response.is_json


# --- 4) Safe redirect ---


def test_safe_redirect_url_rejects_external(app):
    with app.test_request_context("/", base_url="http://localhost/"):
        target = safe_redirect_url("https://evil.example/phish")
        assert "evil.example" not in target
        assert target.endswith("/anasayfa") or target == "/anasayfa"


def test_admin_ban_redirect_rejects_external_referrer(client, app):
    with app.app_context():
        admin = User(
            username="ban_admin",
            email="ban_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            is_admin=True,
            role="superadmin",
        )
        target = _make_user("ban_target", "ban_target@test.com")
        db.session.add(admin)
        db.session.commit()
        target_id = target.id

    _login(client, "ban_admin@test.com")
    response = client.post(
        f"/admin/users/ban/{target_id}",
        data={"ban_reason": ""},
        headers={"Referer": "https://evil.example/steal"},
        follow_redirects=False,
    )
    assert response.status_code == 302
    assert "evil.example" not in (response.location or "")


# --- 5) load_user hardening ---


@pytest.mark.parametrize(
    "session_user_id",
    ["", "abc", None, "-1", "0"],
)
def test_load_user_malformed_session_returns_none(app, client, session_user_id):
    with client.session_transaction() as sess:
        sess["_user_id"] = session_user_id
        sess["_fresh"] = True
    response = client.get("/profil", follow_redirects=False)
    assert response.status_code in (302, 401, 403, 404)


# --- 6) Notification link sanitization ---


def test_safe_notification_link_rejects_javascript():
    assert safe_notification_link("javascript:alert(1)") is None
    assert safe_notification_link("data:text/html,<script>") is None


def test_safe_notification_link_allows_relative():
    assert safe_notification_link("/mesajlar/1/0/0") == "/mesajlar/1/0/0"


def test_bildirim_olustur_sanitizes_link(app):
    with app.app_context():
        user = _make_user("notif_user", "notif_user@test.com")
        bildirim = bildirim_olustur(
            user.id,
            "Test",
            "İçerik",
            "test",
            "javascript:alert(1)",
        )
        assert bildirim.link is None


def test_bildirimleri_getir_sanitizes_malicious_link(client, app):
    with app.app_context():
        user = _make_user("notif_api", "notif_api@test.com")
        row = Bildirim(
            user_id=user.id,
            baslik="XSS",
            icerik="test",
            tur="test",
            link="javascript:alert(1)",
        )
        db.session.add(row)
        db.session.commit()

    _login(client, "notif_api@test.com")
    response = client.get("/bildirimleri_getir")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload[0]["link"] is None


# --- 3) Socket conversation authorization ---


def test_socket_join_rejects_unauthorized_stranger(app, client):
    with app.app_context():
        sender = _make_user("sock_a", "sock_a@test.com")
        receiver = _make_user("sock_b", "sock_b@test.com")
        stranger = _make_user("sock_c", "sock_c@test.com")
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="gizli")
        )
        db.session.commit()
        stranger_id = stranger.id
        sender_id = sender.id

    stranger_client = app.test_client()
    _login(stranger_client, "sock_c@test.com")
    socket_client = _socket_client(app, stranger_client)
    result = socket_client.emit(
        "join_conversation",
        {"partner_id": sender_id, "kaynak_id": 0, "atik_id": 0},
        callback=True,
    )
    assert result.get("error") == "Yetkisiz"
    socket_client.disconnect()


def test_socket_join_allows_ilan_owner_without_prior_message(app, client):
    with app.app_context():
        owner = _make_user("ilan_owner", "ilan_owner@test.com")
        buyer = _make_user("ilan_buyer", "ilan_buyer@test.com")
        kaynak = Kaynak(
            user_id=owner.id,
            baslik="Satılık",
            aciklama="Açıklama",
            durum="İkinci El",
            kategori="Elektronik",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add(kaynak)
        db.session.commit()
        owner_id = owner.id
        kaynak_id = kaynak.id

    buyer_client = app.test_client()
    _login(buyer_client, "ilan_buyer@test.com")
    socket_client = _socket_client(app, buyer_client)
    result = socket_client.emit(
        "join_conversation",
        {
            "partner_id": owner_id,
            "kaynak_id": kaynak_id,
            "atik_id": 0,
        },
        callback=True,
    )
    assert "room" in result
    socket_client.disconnect()


def test_socket_sync_state_rejects_unauthorized(app, client):
    with app.app_context():
        sender = _make_user("sync_a", "sync_a@test.com")
        receiver = _make_user("sync_b", "sync_b@test.com")
        outsider = _make_user("sync_c", "sync_c@test.com")
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="özel")
        )
        db.session.commit()
        sender_id = sender.id

    outsider_client = app.test_client()
    _login(outsider_client, "sync_c@test.com")
    socket_client = _socket_client(app, outsider_client)
    result = socket_client.emit(
        "sync_state",
        {"partner_id": sender_id, "kaynak_id": 0, "atik_id": 0},
        callback=True,
    )
    assert result.get("error") == "Yetkisiz"
    socket_client.disconnect()


def test_socket_typing_rejects_unauthorized(app):
    from socket_events import handle_typing_start

    with app.app_context():
        sender = _make_user("type_a", "type_a@test.com")
        receiver = _make_user("type_b", "type_b@test.com")
        outsider = _make_user("type_c", "type_c@test.com")
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="msg")
        )
        db.session.commit()
        outsider_user = outsider
        sender_id = sender.id

        with app.test_request_context():
            login_user(outsider_user)
            with patch("socket_events.socketio.emit") as emit_mock:
                handle_typing_start(
                    {"partner_id": sender_id, "kaynak_id": 0, "atik_id": 0}
                )
            emit_mock.assert_not_called()


def test_user_can_access_conversation_admin_bypass(app):
    with app.app_context():
        admin = User(
            username="sock_admin",
            email="sock_admin@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
            is_admin=True,
            role="admin",
        )
        other = _make_user("sock_other", "sock_other@test.com")
        db.session.add(admin)
        db.session.commit()
        assert user_can_access_conversation(admin.id, other.id, 0, 0) is True


# --- 7) Rate limit production warning ---


def test_rate_limit_memory_logs_production_warning(monkeypatch, caplog):
    import logging

    from production_config import resolve_rate_limit_storage_uri

    monkeypatch.delenv("RATELIMIT_STORAGE_URI", raising=False)
    monkeypatch.setenv("RATELIMIT_BACKEND", "memory")
    monkeypatch.setenv("DEBUG", "False")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)

    with caplog.at_level(logging.WARNING, logger="atikport.config"):
        uri = resolve_rate_limit_storage_uri()

    assert uri == "memory://"
    assert any("PRODUCTION UYARISI" in record.message for record in caplog.records)


# --- 8) Migration integration ---


def test_flask_db_upgrade_on_empty_postgres():
    postgres_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not postgres_url:
        pytest.skip("TEST_DATABASE_URL tanımlı değil")

    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import NullPool

    engine = create_engine(postgres_url, poolclass=NullPool)
    with engine.connect() as conn:
        conn.execute(text("DROP SCHEMA IF EXISTS public CASCADE"))
        conn.execute(text("CREATE SCHEMA public"))
        conn.commit()

    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": postgres_url,
            "WTF_CSRF_ENABLED": False,
            "TURNSTILE_ENABLED": False,
        }
    )

    with app.app_context():
        from flask_migrate import upgrade

        upgrade()
        tables = db.session.execute(
            text(
                "SELECT tablename FROM pg_tables WHERE schemaname = 'public' AND tablename = 'user'"
            )
        ).fetchone()
        assert tables is not None

    client = app.test_client()
    health = client.get("/health")
    assert health.status_code == 200
    assert health.get_json().get("status") == "ok"


# --- 9) Backup scripts ---


def test_backup_scripts_read_credentials_from_env():
    deploy_scripts = Path(__file__).resolve().parents[1] / "deploy" / "scripts"
    for name in ("backup-db.sh", "pg-dump-local.sh", "pg-restore.sh", "smoke-test.sh"):
        content = (deploy_scripts / name).read_text(encoding="utf-8")
        assert "POSTGRES_USER" in content
        assert "POSTGRES_DB" in content
        assert "pg_dump -U postgres atikport" not in content
        assert 'pg_isready -U postgres -d atikport' not in content

    backup = (deploy_scripts / "backup-db.sh").read_text(encoding="utf-8")
    assert "support_attachments" in backup


def test_docker_compose_support_attachments_volume():
    compose = (
        Path(__file__).resolve().parents[1] / "deploy" / "docker-compose.prod.yml"
    ).read_text(encoding="utf-8")
    assert "data/support_attachments:/app/data/support_attachments" in compose
