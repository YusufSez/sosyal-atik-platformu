"""Phase 5.4 — sorgu ve pagination performans regression testleri."""

from unittest.mock import patch

import pytest
from sqlalchemy import event
from sqlalchemy.orm import joinedload

from auth_utils import hash_password
from extensions import db
from models import Mesaj, User
from services.stats_queries import homepage_stats
from sockets.serializer import serialize_message


def _count_queries(app, fn):
    counter = {"n": 0}

    def _before(conn, cursor, statement, parameters, context, executemany):
        counter["n"] += 1

    with app.app_context():
        event.listen(db.engine, "before_cursor_execute", _before)
        try:
            fn()
        finally:
            event.remove(db.engine, "before_cursor_execute", _before)
    return counter["n"]


def test_homepage_stats_returns_expected_keys(app):
    with app.app_context():
        stats = homepage_stats()
    assert set(stats.keys()) == {"kullanici", "kaynak", "atik", "teslim"}
    assert all(isinstance(v, int) for v in stats.values())


def test_homepage_stats_fewer_queries_than_five_separate_counts(app):
    from models import Atik, Kaynak, User

    def _five_counts():
        User.query.count()
        Kaynak.query.count()
        Atik.query.count()
        Kaynak.query.filter_by(ilan_durumu="Teslim Edildi").count()
        Atik.query.filter_by(ilan_durumu="Teslim Edildi").count()

    with app.app_context():
        optimized = _count_queries(app, homepage_stats)
        naive = _count_queries(app, _five_counts)
    assert optimized == 3
    assert naive == 5
    assert optimized < naive


def test_serialize_message_avoids_user_query_when_sender_loaded(app):
    with app.app_context():
        sender = User(
            username="perf_sender",
            email="perf_sender@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        receiver = User(
            username="perf_recv",
            email="perf_recv@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add_all([sender, receiver])
        db.session.commit()
        mesaj = Mesaj(sender_id=sender.id, receiver_id=receiver.id, content="Merhaba")
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id
        receiver_id = receiver.id

        def _loaded():
            row = (
                db.session.query(Mesaj)
                .options(joinedload(Mesaj.sender))
                .filter(Mesaj.id == mesaj_id)
                .one()
            )
            serialize_message(row, receiver_id)

        def _unloaded():
            row = db.session.get(Mesaj, mesaj_id)
            serialize_message(row, receiver_id)

        loaded_queries = _count_queries(app, _loaded)
        unloaded_queries = _count_queries(app, _unloaded)
        loaded = (
            db.session.query(Mesaj)
            .options(joinedload(Mesaj.sender))
            .filter(Mesaj.id == mesaj_id)
            .one()
        )
        assert loaded_queries < unloaded_queries
        assert serialize_message(loaded, receiver_id)["sender_name"] == "perf_sender"


def test_admin_users_paginated(monkeypatch, client, app):
    monkeypatch.setenv("SUPERADMIN_EMAIL", "superpage@test.com")

    with app.app_context():
        for i in range(3):
            db.session.add(
                User(
                    username=f"pageuser{i}",
                    email=f"pageuser{i}@test.com",
                    password=hash_password("TestPass1"),
                    is_completed=True,
                    role="user",
                )
            )
        sa = User(
            username="superpage",
            email="superpage@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            is_admin=True,
            role="superadmin",
        )
        db.session.add(sa)
        db.session.commit()

    client.post(
        "/giris",
        data={"email": "superpage@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    response = client.get("/admin/users?page=1")
    assert response.status_code == 200
    assert b"pageuser" in response.data


def test_emit_bildirim_realtime_single_unread_query(app):
    from services.notifications import _emit_bildirim_realtime

    with app.app_context():
        with patch("sockets.serializer.unread_counts_for") as unread_mock:
            unread_mock.return_value = {"message_unread": 1, "notification_unread": 2}
            with patch("socket_events.emit_unread_count_updated") as emit_unread:
                with patch("socket_events.emit_notification_sync") as emit_sync:
                    _emit_bildirim_realtime(99)
                    unread_mock.assert_called_once_with(99)
                    emit_unread.assert_called_once()
                    emit_sync.assert_called_once()
                    assert emit_unread.call_args.kwargs.get("payload") == emit_sync.call_args.kwargs.get("payload")


def test_sync_state_query_uses_joinedload(app):
    from sockets import events as socket_events_module

    source = open(socket_events_module.__file__, encoding="utf-8").read()
    assert "joinedload(Mesaj.sender)" in source
