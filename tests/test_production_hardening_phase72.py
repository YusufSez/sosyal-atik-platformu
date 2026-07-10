"""Production Hardening Phase 7.2 — scheduler read-only filesystem compatibility."""

import tempfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from auth_utils import hash_password
from extensions import db
from models import User
from services.maintenance import (
    _acquire_lock,
    _maintenance_lock_path,
    _release_lock,
    run_scheduled_maintenance,
)
from services.user_moderation import apply_ban
from utils import utc_now


def test_maintenance_lock_path_uses_temp_dir(app):
    lock_path = _maintenance_lock_path(app)
    assert str(lock_path).startswith(tempfile.gettempdir())
    assert not str(lock_path).startswith(str(Path(app.root_path) / "data"))


def test_maintenance_lock_path_respects_tmpdir_env(app, monkeypatch, tmp_path):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    with patch("services.maintenance.tempfile.gettempdir", return_value=str(tmp_path)):
        lock_path = _maintenance_lock_path(app)
    assert lock_path.parent == tmp_path


def test_maintenance_lock_path_does_not_mkdir_under_app(app):
    with patch("pathlib.Path.mkdir") as mkdir_mock:
        _maintenance_lock_path(app)
    mkdir_mock.assert_not_called()


def test_run_scheduled_maintenance_uses_temp_lock(app, tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    with patch("services.maintenance.tempfile.gettempdir", return_value=str(tmp_path)):
        with app.app_context():
            user = User(
                username="ro_maint",
                email="ro_maint@test.com",
                password=hash_password("TestPass1"),
                is_completed=True,
            )
            apply_ban(user, "bakım", duration_days=1)
            user.ban_expires_at = utc_now() - timedelta(minutes=1)
            db.session.add(user)
            db.session.commit()

            results = run_scheduled_maintenance(app)

    assert results.get("expire_temporary_bans") == 1
    assert not (Path(app.root_path) / "data" / ".maintenance.lock").exists()
    assert not any((Path(app.root_path) / "data").rglob(".maintenance.lock"))


def test_maintenance_lock_released_after_run(app, tmp_path, monkeypatch):
    lock_path = tmp_path / "test.maintenance.lock"
    monkeypatch.setattr(
        "services.maintenance._maintenance_lock_path",
        lambda _app: lock_path,
    )

    with app.app_context():
        run_scheduled_maintenance(app)

    assert not lock_path.exists()


def test_concurrent_maintenance_only_one_acquires_lock(app, tmp_path, monkeypatch):
    lock_path = tmp_path / "concurrent.maintenance.lock"
    monkeypatch.setattr(
        "services.maintenance._maintenance_lock_path",
        lambda _app: lock_path,
    )

    with app.app_context():
        user = User(
            username="conc_maint",
            email="conc_maint@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        apply_ban(user, "bakım", duration_days=1)
        user.ban_expires_at = utc_now() - timedelta(minutes=1)
        db.session.add(user)
        db.session.commit()

        first = run_scheduled_maintenance(app)
        lock_path.write_text("held", encoding="utf-8")
        second = run_scheduled_maintenance(app)

    assert first.get("expire_temporary_bans") == 1
    assert second == {}


def test_acquire_lock_returns_false_on_readonly_filesystem(tmp_path):
    lock_path = tmp_path / "readonly.lock"

    with patch("services.maintenance.os.open", side_effect=OSError(30, "Read-only file system")):
        assert _acquire_lock(lock_path) is False


def test_release_lock_is_idempotent(tmp_path):
    lock_path = tmp_path / "cleanup.lock"
    lock_path.write_text("x", encoding="utf-8")
    _release_lock(lock_path)
    _release_lock(lock_path)
    assert not lock_path.exists()


def test_background_scheduler_starts_without_app_data_lock(app):
    from app_bootstrap import scheduler as scheduler_module

    scheduler_module._scheduler_started = False
    app.config["TESTING"] = False
    try:
        with patch.object(scheduler_module.threading, "Thread") as thread_mock:
            scheduler_module.start_background_scheduler(app)
            thread_mock.assert_called_once()
            assert thread_mock.call_args.kwargs["name"] == "atikport-maintenance"
    finally:
        scheduler_module._scheduler_started = False
        app.config["TESTING"] = True

    lock_path = _maintenance_lock_path(app)
    assert app.root_path not in str(lock_path)
