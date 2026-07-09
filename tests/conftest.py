import os

os.environ["RATELIMIT_STORAGE_URI"] = "memory://"

import pytest
from sqlalchemy.pool import StaticPool

from factory import create_app
from extensions import db


@pytest.fixture
def app():
    app = create_app({
        "TESTING": True,
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
