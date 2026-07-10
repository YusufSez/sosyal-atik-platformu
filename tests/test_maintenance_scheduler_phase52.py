"""Phase 5.2 — bakım görevlerinin request yolundan scheduler'a taşınması."""

from datetime import timedelta
from unittest.mock import patch

import pytest

from auth_utils import hash_password
from extensions import db
from models import User
from services.maintenance import run_scheduled_maintenance
from services.user_moderation import (
    apply_ban,
    expire_temporary_bans,
    is_user_banned,
)
from utils import utc_now


def _before_request_names(app):
    return [getattr(f, "__name__", repr(f)) for f in app.before_request_funcs.get(None, [])]


def test_before_request_does_not_expire_temporary_bans(app):
    assert "_expire_temporary_bans" not in _before_request_names(app)


def test_before_request_still_enforces_active_account(app):
    assert "_enforce_active_account" in _before_request_names(app)


def test_is_user_banned_expired_does_not_commit(app):
    with app.app_context():
        user = User(
            username="expiredban",
            email="expiredban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_banned=True,
            ban_expires_at=utc_now() - timedelta(minutes=1),
        )
        db.session.add(user)
        db.session.commit()

        with patch.object(db.session, "commit", wraps=db.session.commit) as commit_mock:
            assert is_user_banned(user) is False
            commit_mock.assert_not_called()


def test_is_user_banned_active_temporary_ban(app):
    with app.app_context():
        user = User(
            username="activeban",
            email="activeban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        apply_ban(user, "test", duration_days=1)
        db.session.add(user)
        db.session.commit()

        assert is_user_banned(user) is True


def test_expire_temporary_bans_clears_expired_user(app):
    with app.app_context():
        user = User(
            username="schedban",
            email="schedban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        apply_ban(user, "süre doldu", duration_days=1)
        user.ban_expires_at = utc_now() - timedelta(minutes=5)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        count = expire_temporary_bans()
        assert count == 1

        refreshed = db.session.get(User, user_id)
        assert refreshed.is_banned is False
        assert refreshed.ban_expires_at is None


def test_expire_temporary_bans_is_idempotent(app):
    with app.app_context():
        user = User(
            username="idempotentban",
            email="idempotentban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        apply_ban(user, "tekrar", duration_days=1)
        user.ban_expires_at = utc_now() - timedelta(minutes=1)
        db.session.add(user)
        db.session.commit()

        assert expire_temporary_bans() == 1
        assert expire_temporary_bans() == 0


def test_run_scheduled_maintenance_expires_bans(app):
    with app.app_context():
        user = User(
            username="maintban",
            email="maintban@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        apply_ban(user, "bakım", duration_days=1)
        user.ban_expires_at = utc_now() - timedelta(minutes=2)
        db.session.add(user)
        db.session.commit()
        user_id = user.id

        results = run_scheduled_maintenance(app)
        assert results.get("expire_temporary_bans") == 1

        refreshed = db.session.get(User, user_id)
        assert refreshed.is_banned is False


def test_run_scheduled_maintenance_skips_when_lock_held(app, tmp_path, monkeypatch):
    with app.app_context():
        lock_path = tmp_path / ".maintenance.lock"
        lock_path.write_text("held", encoding="utf-8")
        monkeypatch.setattr(
            "services.maintenance._maintenance_lock_path",
            lambda _app: lock_path,
        )

        results = run_scheduled_maintenance(app)
        assert results == {}


def test_background_scheduler_not_started_in_testing(app):
    from app_bootstrap import scheduler as scheduler_module

    scheduler_module._scheduler_started = False
    with patch.object(scheduler_module.threading, "Thread") as thread_mock:
        scheduler_module.start_background_scheduler(app)
        thread_mock.assert_not_called()


def test_background_scheduler_starts_outside_testing(app):
    from app_bootstrap import scheduler as scheduler_module

    scheduler_module._scheduler_started = False
    app.config["TESTING"] = False
    try:
        with patch.object(scheduler_module.threading, "Thread") as thread_mock:
            scheduler_module.start_background_scheduler(app)
            thread_mock.assert_called_once()
            kwargs = thread_mock.call_args.kwargs
            assert kwargs.get("daemon") is True
            assert kwargs.get("name") == "atikport-maintenance"
    finally:
        scheduler_module._scheduler_started = False
        app.config["TESTING"] = True
