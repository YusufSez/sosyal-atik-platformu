"""Production Hardening Phase 7 regression tests."""

import os
from pathlib import Path
from unittest.mock import patch

import pytest
from flask_login import login_user

from auth_utils import hash_password
from extensions import db
from factory import create_app
from models import Atik, Kaynak, Mesaj, User
from socket_events import user_can_access_conversation


def _make_user(username, email, *, is_admin=False, role="user"):
    user = User(
        username=username,
        email=email,
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
        is_admin=is_admin,
        role=role,
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


def test_http_send_message_rejects_unauthorized_conversation(client, app):
    with app.app_context():
        sender = _make_user("http_a", "http_a@test.com")
        receiver = _make_user("http_b", "http_b@test.com")
        _make_user("http_c", "http_c@test.com")
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="özel")
        )
        db.session.commit()
        sender_id = sender.id

    _login(client, "http_c@test.com")
    response = client.post(
        "/send_message",
        json={
            "alici_id": sender_id,
            "content": "yetkisiz",
            "kaynak_id": 0,
            "atik_id": 0,
        },
    )
    assert response.status_code == 403
    assert response.get_json()["error"] == "Yetkisiz"


def test_http_mesajlar_getir_rejects_unauthorized(client, app):
    with app.app_context():
        sender = _make_user("get_a", "get_a@test.com")
        receiver = _make_user("get_b", "get_b@test.com")
        outsider = _make_user("get_c", "get_c@test.com")
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="gizli")
        )
        db.session.commit()
        sender_id = sender.id

    _login(client, "get_c@test.com")
    response = client.get(f"/mesajlar_getir/{sender_id}/0/0")
    assert response.status_code == 403


def test_http_mesajlar_page_rejects_unauthorized(client, app):
    """HTML /mesajlar URL manipülasyonu — yabancı sohbet 403."""
    with app.app_context():
        sender = _make_user("page_a", "page_a@test.com")
        receiver = _make_user("page_b", "page_b@test.com")
        _make_user("page_c", "page_c@test.com")
        db.session.add(
            Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="özel-ab")
        )
        db.session.commit()
        sender_id = sender.id

    _login(client, "page_c@test.com")
    response = client.get(f"/mesajlar/{sender_id}/0/0")
    assert response.status_code == 403


def test_owner_cannot_open_chat_with_arbitrary_user_via_url(client, app):
    """İlan sahibi, mesaj geçmişi olmadan rastgele user_id ile sohbet açamaz."""
    with app.app_context():
        owner = _make_user("own_url", "own_url@test.com")
        stranger = _make_user("str_url", "str_url@test.com")
        kaynak = Kaynak(
            user_id=owner.id,
            baslik="URL-IDOR",
            aciklama="Test",
            durum="Temiz",
            kategori="Diğer",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add(kaynak)
        db.session.commit()
        stranger_id = stranger.id
        kaynak_id = kaynak.id

    _login(client, "own_url@test.com")
    assert client.get(f"/mesajlar/{stranger_id}/{kaynak_id}/0").status_code == 403
    assert client.get(f"/mesajlar_getir/{stranger_id}/{kaynak_id}/0").status_code == 403


def test_dual_listing_ids_rejected(client, app):
    with app.app_context():
        owner = _make_user("dual_o", "dual_o@test.com")
        buyer = _make_user("dual_b", "dual_b@test.com")
        kaynak = Kaynak(
            user_id=owner.id,
            baslik="Dual",
            aciklama="Test",
            durum="Temiz",
            kategori="Diğer",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        atik = Atik(
            user_id=owner.id,
            baslik="DualAtik",
            aciklama="Test",
            latitude=41.0,
            longitude=29.0,
            kategori="Plastik",
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add_all([kaynak, atik])
        db.session.commit()
        owner_id = owner.id
        kid, aid = kaynak.id, atik.id

    _login(client, "dual_b@test.com")
    assert client.get(f"/mesajlar/{owner_id}/{kid}/{aid}").status_code == 403


def test_http_send_message_allows_ilan_context(client, app):
    with app.app_context():
        owner = _make_user("ilan_owner", "ilan_owner@test.com")
        buyer = _make_user("ilan_buyer", "ilan_buyer@test.com")
        kaynak = Kaynak(
            user_id=owner.id,
            baslik="Satılık",
            aciklama="Test",
            durum="Temiz",
            kategori="Diğer",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add(kaynak)
        db.session.commit()
        kaynak_id = kaynak.id
        owner_id = owner.id

    with patch("blueprints.messages.mesaj_uygun_mu", return_value=(True, "")):
        _login(client, "ilan_buyer@test.com")
        response = client.post(
            "/send_message",
            json={
                "alici_id": owner_id,
                "content": "İlan hakkında",
                "kaynak_id": kaynak_id,
                "atik_id": 0,
            },
        )
    assert response.status_code == 200
    assert response.get_json()["success"] is True


def test_production_fail_fast_missing_site_url(monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("FORCE_HTTPS", "true")
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    monkeypatch.setenv("SOCKETIO_CORS_ORIGINS", "https://example.com")
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.delenv("SKIP_DOTENV", raising=False)

    with pytest.raises(RuntimeError, match="SITE_URL"):
        create_app()


def test_production_fail_fast_skipped_when_app_env_development(monkeypatch):
    """Local APP_ENV=development: FORCE_HTTPS/CORS zorunluluğu uygulanmaz."""
    from flask import Flask

    from app_bootstrap.config import configure_app

    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    monkeypatch.setenv("DEBUG", "false")
    monkeypatch.setenv("APP_ENV", "development")
    monkeypatch.delenv("FLASK_ENV", raising=False)
    monkeypatch.setenv("FORCE_HTTPS", "false")
    monkeypatch.delenv("SOCKETIO_CORS_ORIGINS", raising=False)
    monkeypatch.delenv("SITE_URL", raising=False)
    monkeypatch.delenv("TESTING", raising=False)
    monkeypatch.setenv("SKIP_DOTENV", "1")

    app = Flask(__name__)
    configure_app(app, {"SQLALCHEMY_DATABASE_URI": "sqlite://"})
    assert app.config["DEBUG"] is False
    assert app.config["FORCE_HTTPS"] is False


def test_production_fail_fast_skipped_in_testing(app):
  # conftest TESTING=True — app fixture should start without production checks failing
    assert app.config["TESTING"] is True


def test_health_endpoint_extended_fields(client):
    response = client.get("/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"
    assert "version" in data
    assert "uptime_seconds" in data
    assert "worker" in data
    assert "redis_enabled" in data
    assert "scheduler" in data
    assert "maintenance_running" in data["scheduler"]


def test_health_degraded_when_redis_unreachable(monkeypatch, client):
    monkeypatch.setenv("REDIS_URL", "redis://127.0.0.1:59999/0")
    from services.redis_manager import reset_redis_client

    reset_redis_client()
    response = client.get("/health")
    reset_redis_client()
    data = response.get_json()
    assert data["redis"] == "degraded"
    assert data["status"] == "degraded"
    assert response.status_code == 200


def test_scheduler_status_reported(app):
    from app_bootstrap.scheduler import scheduler_status

    with app.app_context():
        status = scheduler_status()
    assert "maintenance_running" in status
    assert status["backup_scheduler_running"] is False


def test_log_level_env(monkeypatch, app):
    monkeypatch.setenv("LOG_LEVEL", "WARNING")
    from services.logging_setup import _resolve_log_level

    import logging

    assert _resolve_log_level(app) == logging.WARNING


def test_admin_conversation_access_audit_log(app):
    from models import AdminAuditLog
    from sockets.events import handle_join_conversation
    import socket_events

    with app.app_context():
        admin = _make_user(
            "audit_admin",
            "audit_admin@test.com",
            is_admin=True,
            role="admin",
        )
        other = _make_user("audit_other", "audit_other@test.com")
        db.session.commit()

        with app.test_request_context():
            login_user(admin)
            with patch.object(socket_events, "current_user", admin):
                with patch("socket_events.request") as req_mock:
                    req_mock.sid = "test-sid"
                    handle_join_conversation(
                        {"partner_id": other.id, "kaynak_id": 0, "atik_id": 0}
                    )

        log = AdminAuditLog.query.filter_by(action="admin_conversation_access").first()
        assert log is not None
        assert log.target_user_id == other.id


def test_backup_scripts_include_manifest_and_uploads():
    deploy_scripts = Path(__file__).resolve().parents[1] / "deploy" / "scripts"
    backup = (deploy_scripts / "backup-db.sh").read_text(encoding="utf-8")
    assert "manifest_" in backup
    assert "item_pics" in backup
    assert "profile_pics" in backup

    restore = (deploy_scripts / "pg-restore.sh").read_text(encoding="utf-8")
    assert "|| true" not in restore
    assert "Geri yükleme doğrulaması" in restore


def test_docker_compose_hardening_flags():
    compose = (
        Path(__file__).resolve().parents[1] / "deploy" / "docker-compose.prod.yml"
    ).read_text(encoding="utf-8")
    assert "read_only: true" in compose
    assert "no-new-privileges:true" in compose
    assert "max-size:" in compose
    assert "deploy:" in compose


def test_permission_parity_helper_matches_socket(app):
    with app.app_context():
        a = _make_user("parity_a", "parity_a@test.com")
        b = _make_user("parity_b", "parity_b@test.com")
        assert user_can_access_conversation(a.id, b.id, 0, 0) is False
        db.session.add(Mesaj(sender_id=a.id, receiver_id=b.id, content="x"))
        db.session.commit()
        assert user_can_access_conversation(a.id, b.id, 0, 0) is True
