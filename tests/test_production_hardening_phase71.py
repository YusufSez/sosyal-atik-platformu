"""Production Hardening Phase 7.1 — read-only filesystem compatibility."""

from unittest.mock import patch

import pytest
from flask import Flask

from app_bootstrap.config import _ensure_backup_dir_at_startup, configure_app
from factory import create_app


def test_ensure_backup_dir_empty_skips_mkdir():
    with patch("app_bootstrap.config.Path") as path_cls:
        _ensure_backup_dir_at_startup("")
        _ensure_backup_dir_at_startup("   ")
        path_cls.assert_not_called()


def test_ensure_backup_dir_success_calls_mkdir():
    with patch("app_bootstrap.config.Path") as path_cls:
        _ensure_backup_dir_at_startup("/app/backups")
        path_cls.return_value.mkdir.assert_called_once_with(parents=True, exist_ok=True)


def test_ensure_backup_dir_readonly_filesystem_logs_warning(caplog):
    with patch("app_bootstrap.config.Path") as path_cls:
        path_cls.return_value.mkdir.side_effect = OSError(30, "Read-only file system")
        with caplog.at_level("WARNING", logger="app_bootstrap.config"):
            _ensure_backup_dir_at_startup("/app/backups")

    assert "Backup directory '/app/backups' is not writable" in caplog.text


def test_configure_app_does_not_raise_on_backup_dir_oserror(monkeypatch, caplog):
    monkeypatch.setenv("SECRET_KEY", "a" * 32)
    app = Flask(__name__)
    app.root_path = "."

    with patch("app_bootstrap.config.Path") as path_cls:
        path_cls.return_value.mkdir.side_effect = OSError(30, "Read-only file system")
        with caplog.at_level("WARNING", logger="app_bootstrap.config"):
            configure_app(app, {"TESTING": True, "BACKUP_DIR": "/app/backups"})

    assert "not writable" in caplog.text


def test_create_app_survives_readonly_backup_dir(monkeypatch, caplog):
    monkeypatch.setenv("SECRET_KEY", "a" * 32)

    with patch("app_bootstrap.config.Path") as path_cls:
        path_cls.return_value.mkdir.side_effect = OSError(30, "Read-only file system")
        with caplog.at_level("WARNING", logger="app_bootstrap.config"):
            app = create_app({
                "TESTING": True,
                "SQLALCHEMY_DATABASE_URI": "sqlite://",
                "WTF_CSRF_ENABLED": False,
                "TURNSTILE_ENABLED": False,
                "BACKUP_DIR": "/app/backups",
            })

    assert app is not None
    assert "not writable" in caplog.text
