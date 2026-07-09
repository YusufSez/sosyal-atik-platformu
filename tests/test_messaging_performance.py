"""Production Performance Phase — mesajlaşma performans testleri."""

from unittest.mock import patch

import pytest
from flask_login import login_user

from auth_utils import hash_password
from constants import MESSAGE_PAGE_SIZE
from extensions import db
from models import Atik, Kaynak, Mesaj, User
from services.message_unread_cache import clear_unread_cache, get_message_unread_count, refresh_unread_cache
from services.messaging_queries import fetch_inbox_threads, fetch_message_page


@pytest.fixture(autouse=True)
def reset_unread_cache():
    clear_unread_cache()
    yield
    clear_unread_cache()


def _create_pair(app):
    with app.app_context():
        sender = User(
            username="perf_sender",
            email="perf_sender@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        receiver = User(
            username="perf_receiver",
            email="perf_receiver@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([sender, receiver])
        db.session.commit()
        return sender.id, receiver.id


def _add_messages(sender_id, receiver_id, count, *, kaynak_id=None, atik_id=None):
    for i in range(count):
        db.session.add(
            Mesaj(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content=f"msg-{i}",
                kaynak_id=kaynak_id,
                atik_id=atik_id,
                is_read=True,
            )
        )
    db.session.commit()


def test_fetch_message_page_initial_limit(app):
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        _add_messages(sender_id, receiver_id, MESSAGE_PAGE_SIZE + 10)

        rows, has_more, oldest_id = fetch_message_page(receiver_id, sender_id, 0, 0)
        assert len(rows) == MESSAGE_PAGE_SIZE
        assert has_more is True
        assert oldest_id == rows[0].id
        assert rows[-1].content == f"msg-{MESSAGE_PAGE_SIZE + 9}"


def test_fetch_message_page_before_id(app):
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        _add_messages(sender_id, receiver_id, MESSAGE_PAGE_SIZE + 5)

        first_page, has_more, oldest = fetch_message_page(receiver_id, sender_id, 0, 0)
        assert has_more is True

        older, has_more_2, _ = fetch_message_page(
            receiver_id, sender_id, 0, 0, before_id=oldest
        )
        assert len(older) == 5
        assert has_more_2 is False
        assert older[0].content == "msg-0"


def test_fetch_inbox_threads_sql_latest_per_conversation(app):
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        kaynak = Kaynak(
            baslik="K",
            aciklama="a",
            durum="Temiz",
            kategori="Diğer",
            latitude=41.0,
            longitude=29.0,
            user_id=sender_id,
        )
        db.session.add(kaynak)
        db.session.commit()

        db.session.add(
            Mesaj(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content="eski",
                kaynak_id=kaynak.id,
                is_read=True,
            )
        )
        db.session.add(
            Mesaj(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content="yeni",
                kaynak_id=kaynak.id,
                is_read=False,
            )
        )
        db.session.commit()

        sohbetler = fetch_inbox_threads(receiver_id)
        assert len(sohbetler) == 1
        thread = next(iter(sohbetler.values()))
        assert thread["msg"].content == "yeni"
        assert thread["is_new"] is True
        assert thread["kaynak"].id == kaynak.id


def test_mesajlar_getir_paginated_json(client, app):
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        _add_messages(sender_id, receiver_id, 3)
        receiver = db.session.get(User, receiver_id)

    client.post(
        "/giris",
        data={"email": receiver.email, "password": "TestPass1"},
        follow_redirects=True,
    )
    response = client.get(f"/mesajlar_getir/{sender_id}/0/0")
    assert response.status_code == 200
    data = response.get_json()
    assert "messages" in data
    assert data["has_more"] is False
    assert len(data["messages"]) == 3


def test_unread_cache_avoids_per_request_count(app, client):
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        db.session.add(
            Mesaj(
                sender_id=sender_id,
                receiver_id=receiver_id,
                content="okunmadi",
                is_read=False,
            )
        )
        db.session.commit()
        refresh_unread_cache(receiver_id)
        assert get_message_unread_count(receiver_id) == 1

        receiver = db.session.get(User, receiver_id)

    with patch.object(Mesaj.query, "filter_by", wraps=Mesaj.query.filter_by) as filter_mock:
        with app.test_request_context("/"):
            login_user(receiver)
            from blueprints.messages import inject_unread_from_cache

            inject_unread_from_cache()
            inject_unread_from_cache()
        filter_mock.assert_not_called()


def test_sync_state_rate_limit(app):
    import socket_events
    from socket_events import handle_sync_state

    socket_events._rate_buckets.clear()
    with app.app_context():
        sender_id, receiver_id = _create_pair(app)
        receiver = db.session.get(User, receiver_id)

        with app.test_request_context():
            login_user(receiver)
            payload = {"partner_id": sender_id, "kaynak_id": 0, "atik_id": 0}
            for i in range(8):
                result = handle_sync_state(payload)
                if i < 5:
                    assert "error" not in result
                else:
                    assert result.get("error") == "Çok fazla istek"


def test_mesajlar_getir_rate_limit(client, app):
    from extensions import limiter

    limiter.enabled = True
    try:
        with app.app_context():
            sender_id, receiver_id = _create_pair(app)
            receiver = db.session.get(User, receiver_id)

        client.post(
            "/giris",
            data={"email": receiver.email, "password": "TestPass1"},
            follow_redirects=True,
        )

        for i in range(61):
            response = client.get(f"/mesajlar_getir/{sender_id}/0/0")
            if i < 60:
                assert response.status_code == 200
            else:
                assert response.status_code == 429
    finally:
        limiter.enabled = False
