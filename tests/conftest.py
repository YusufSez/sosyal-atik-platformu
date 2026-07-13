"""Pytest bootstrap — kişisel .env asla test sürecine sızmamalı."""

import os

# factory / extensions import edilmeden ÖNCE test runtime bayrakları
os.environ["TESTING"] = "True"
os.environ["FLASK_ENV"] = "testing"
os.environ["RATELIMIT_STORAGE_URI"] = "memory://"
# Geliştirici shell veya önceki load_dotenv kalıntılarına karşı sabitler
os.environ["DEMO_MODE"] = "False"
os.environ["USE_POSTGRES"] = "False"
os.environ["MAIL_SUPPRESS_SEND"] = "True"

import pytest
from sqlalchemy.pool import StaticPool

from factory import create_app
from extensions import db


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
        "DEMO_MODE": False,
        "SQLALCHEMY_DATABASE_URI": "sqlite://",
        "SQLALCHEMY_ENGINE_OPTIONS": {
            "poolclass": StaticPool,
            "connect_args": {"check_same_thread": False},
        },
        "WTF_CSRF_ENABLED": False,
        "TURNSTILE_ENABLED": False,
    })
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()
