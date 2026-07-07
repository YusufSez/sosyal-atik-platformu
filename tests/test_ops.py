import os
from pathlib import Path

import pytest

from auth_utils import hash_password
from extensions import db
from factory import create_app
from models import AdminAuditLog, User
from services.backup import backup_database, should_run_daily_backup


@pytest.fixture
def file_db_app(tmp_path):
    db_path = tmp_path / "test.db"
    backup_dir = tmp_path / "backups"
    app = create_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": f"sqlite:///{db_path}",
        "BACKUP_ENABLED": True,
        "BACKUP_DIR": str(backup_dir),
        "BACKUP_RETENTION_DAYS": 7,
        "WTF_CSRF_ENABLED": False,
        "TURNSTILE_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        yield app, db_path, backup_dir
        db.session.remove()


def test_backup_database_creates_file(file_db_app):
    app, db_path, backup_dir = file_db_app
    with app.app_context():
        user = User(username="u1", email="u1@test.com", password=hash_password("TestPass1"))
        db.session.add(user)
        db.session.commit()

        dest = backup_database(f"sqlite:///{db_path}", backup_dir)
        assert dest is not None
        assert dest.is_file()
        assert dest.stat().st_size > 0


def test_should_run_daily_backup(file_db_app):
    _, _, backup_dir = file_db_app
    assert should_run_daily_backup(backup_dir) is True
    backup_dir.mkdir(parents=True, exist_ok=True)
    (backup_dir / ".last_backup").write_text("2099-01-01T00:00:00", encoding="utf-8")
    assert should_run_daily_backup(backup_dir) is False


def test_gizlilik_ve_kullanim_kosullari_redirect(client):
    assert client.get("/gizlilik").status_code == 302
    assert client.get("/kullanim-kosullari").status_code == 302
    assert client.get("/kurumsal/gizlilik-kvkk").status_code == 200
    assert client.get("/kurumsal/kullanim-kosullari").status_code == 200


def test_kayit_requires_terms(client):
    response = client.post("/kayit", data={
        "username": "noterms",
        "email": "noterms@test.com",
        "password": "TestPass1",
    }, follow_redirects=True)
    assert response.status_code == 200
    assert b"kabul" in response.data.lower()


def test_admin_panel_forbidden_for_normal_user(client, app):
    with app.app_context():
        user = User(
            username="normal",
            email="normal@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.commit()

    client.post("/giris", data={"email": "normal@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = client.get("/admin")
    assert response.status_code == 403


def test_super_admin_toggle_required(client, app, monkeypatch):
    monkeypatch.setenv("ADMIN_EMAIL", "super@test.com")

    with app.app_context():
        super_admin = User(
            username="super",
            email="super@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_admin=True,
        )
        normal_admin = User(
            username="mod",
            email="mod@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_admin=True,
        )
        target = User(
            username="target",
            email="target@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add_all([super_admin, normal_admin, target])
        db.session.commit()
        target_id = target.id

    client.post("/giris", data={"email": "mod@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = client.post(f"/admin/kullanici_admin/{target_id}", follow_redirects=True)
    assert response.status_code == 403

    client.get("/cikis", follow_redirects=True)
    client.post("/giris", data={"email": "super@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = client.post(f"/admin/kullanici_admin/{target_id}", follow_redirects=True)
    assert response.status_code == 200

    with app.app_context():
        updated = db.session.get(User, target_id)
        assert updated.is_admin is True
        assert AdminAuditLog.query.filter_by(action="admin_toggle").count() == 1
