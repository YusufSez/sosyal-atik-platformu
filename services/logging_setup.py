"""Uygulama günlüğü ve hata izleme yapılandırması."""

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path

from flask import Flask, jsonify, render_template, request
from werkzeug.exceptions import HTTPException


def _resolve_log_level(app: Flask) -> int:
    raw = (os.getenv("LOG_LEVEL") or "").strip().upper()
    if raw:
        return getattr(logging, raw, logging.INFO)
    return logging.DEBUG if app.config.get("DEBUG") else logging.INFO


def init_logging(app: Flask) -> None:
    if app.config.get("TESTING"):
        return

    log_level = _resolve_log_level(app)
    log_dir = Path(app.root_path) / app.config.get("LOG_DIR", "logs")
    log_dir.mkdir(parents=True, exist_ok=True)

    formatter = logging.Formatter(
        "[%(asctime)s] %(levelname)s in %(module)s: %(message)s"
    )

    app_handler = RotatingFileHandler(
        log_dir / "app.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=5,
        encoding="utf-8",
    )
    error_handler = RotatingFileHandler(
        log_dir / "errors.log",
        maxBytes=10 * 1024 * 1024,
        backupCount=10,
        encoding="utf-8",
    )
    error_handler.setLevel(logging.ERROR)

    for handler in (app_handler, error_handler):
        handler.setFormatter(formatter)
        app.logger.addHandler(handler)

    app.logger.setLevel(log_level)
    app.logger.propagate = True

    ai_logger = logging.getLogger("atikport.ai")
    ai_logger.setLevel(log_level)
    ai_logger.addHandler(app_handler)
    ai_logger.propagate = False

    socket_logger = logging.getLogger("atikport.socket")
    socket_logger.setLevel(log_level)

    werkzeug_logger = logging.getLogger("werkzeug")
    if not app.config.get("DEBUG"):
        werkzeug_logger.setLevel(logging.WARNING)


def register_error_handlers(app: Flask) -> None:
    @app.errorhandler(404)
    def handle_not_found(error):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Kaynak bulunamadı."}), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(403)
    def handle_forbidden(error):
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Bu işlem için yetkiniz yok."}), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(500)
    def handle_server_error(error):
        app.logger.exception("Beklenmeyen sunucu hatası: %s", error)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Sunucu hatası oluştu."}), 500
        return render_template("errors/500.html"), 500

    @app.errorhandler(Exception)
    def handle_unexpected_error(error):
        if isinstance(error, HTTPException):
            return error
        app.logger.exception("İşlenmeyen istisna: %s", error)
        if request.path.startswith("/api/") or request.is_json:
            return jsonify({"error": "Sunucu hatası oluştu."}), 500
        return render_template("errors/500.html"), 500
