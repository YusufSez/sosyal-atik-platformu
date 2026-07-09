"""Şikayet moderasyonu, ban, filtreleme ve log testleri."""

from datetime import timedelta

import pytest

from auth_utils import hash_password
from extensions import db
from models import AdminAuditLog, Mesaj, Sikayet, User
from services.user_moderation import apply_ban, expire_temporary_bans
from utils import utc_now


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        role="user",
        is_admin=False,
    )
    defaults.update(kwargs)
    return User(**defaults)


@pytest.fixture
def moderation_users(app):
    with app.app_context():
        admin = _user(username="modadmin", email="mod@test.com", is_admin=True, role="admin")
        superadmin = _user(
            username="supermod",
            email="supermod@test.com",
            is_admin=True,
            role="superadmin",
        )
        reporter = _user(username="reporter", email="reporter@test.com")
        reported = _user(username="reported", email="reported@test.com")
        db.session.add_all([admin, superadmin, reporter, reported])
        db.session.commit()
        ids = {
            "admin": admin.id,
            "superadmin": superadmin.id,
            "reporter": reporter.id,
            "reported": reported.id,
        }
    yield ids


@pytest.fixture
def message_report(app, moderation_users):
    with app.app_context():
        mesaj = Mesaj(
            sender_id=moderation_users["reported"],
            receiver_id=moderation_users["reporter"],
            content="hakaret ediyor",
            kaynak_id=None,
            atik_id=None,
        )
        db.session.add(mesaj)
        db.session.commit()
        sikayet = Sikayet(
            user_id=moderation_users["reporter"],
            reported_user_id=moderation_users["reported"],
            mesaj_id=mesaj.id,
            tur="mesaj",
            sebep=f"Mesaj şikayeti (#{mesaj.id}): hakaret",
            aciklama="hakaret ediyor",
            durum="Bekliyor",
        )
        db.session.add(sikayet)
        db.session.commit()
        report_id = sikayet.id
        mesaj_id = mesaj.id
    return {"report_id": report_id, "mesaj_id": mesaj_id}


def _login(client, email):
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


def test_report_detail_page(client, moderation_users, message_report):
    _login(client, "mod@test.com")
    resp = client.get(f"/admin/report/{message_report['report_id']}")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8", errors="ignore")
    assert "Şikayet Detayı" in text
    assert "hakaret ediyor" in text
    assert "Mesajın Bulunduğu Konuşma" in text
    assert "reported" in text


def test_conversation_loaded(client, moderation_users, message_report, app):
    with app.app_context():
        mesaj2 = Mesaj(
            sender_id=moderation_users["reporter"],
            receiver_id=moderation_users["reported"],
            content="merhaba",
            kaynak_id=None,
            atik_id=None,
        )
        db.session.add(mesaj2)
        db.session.commit()

    _login(client, "mod@test.com")
    resp = client.get(f"/admin/report/{message_report['report_id']}")
    text = resp.data.decode("utf-8", errors="ignore")
    assert "merhaba" in text
    assert "hakaret ediyor" in text


def test_admin_can_mark_reviewed(client, moderation_users, message_report, app):
    _login(client, "mod@test.com")
    resp = client.post(
        f"/admin/report/{message_report['report_id']}/mark-reviewed",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        s = db.session.get(Sikayet, message_report["report_id"])
        assert s.reviewer_id == moderation_users["admin"]
        assert s.durum == "İşlem Yapıldı"
        log = AdminAuditLog.query.filter_by(action="sikayet_incele").first()
        assert log is not None


def test_admin_cannot_ban(client, moderation_users, message_report):
    _login(client, "mod@test.com")
    resp = client.post(
        f"/admin/report/{message_report['report_id']}/user/ban",
        data={"ban_reason": "test", "ban_duration": "permanent"},
    )
    assert resp.status_code == 403


def test_superadmin_can_ban(client, moderation_users, message_report, app):
    _login(client, "supermod@test.com")
    resp = client.post(
        f"/admin/report/{message_report['report_id']}/user/ban",
        data={"ban_reason": "Kural ihlali", "ban_duration": "7"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, moderation_users["reported"])
        assert user.is_banned is True
        assert user.ban_reason == "Kural ihlali"
        assert user.ban_expires_at is not None
        log = AdminAuditLog.query.filter_by(action="user_ban").first()
        assert log is not None
        assert log.reason == "Kural ihlali"


def test_superadmin_can_unban(client, moderation_users, message_report, app):
    with app.app_context():
        user = db.session.get(User, moderation_users["reported"])
        apply_ban(user, "test", 7)
        db.session.commit()

    _login(client, "supermod@test.com")
    resp = client.post(
        f"/admin/report/{message_report['report_id']}/user/unban",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, moderation_users["reported"])
        assert user.is_banned is False


def test_timed_ban_expires(client, app, moderation_users):
    with app.app_context():
        user = db.session.get(User, moderation_users["reported"])
        user.ban_expires_at = utc_now() - timedelta(minutes=1)
        user.is_banned = True
        user.ban_reason = "süreli"
        db.session.commit()
        count = expire_temporary_bans()
        assert count == 1
        user = db.session.get(User, moderation_users["reported"])
        assert user.is_banned is False


def test_soft_delete_from_report(client, moderation_users, message_report, app):
    _login(client, "supermod@test.com")
    resp = client.post(
        f"/admin/report/{message_report['report_id']}/user/soft-delete",
        data={"ban_reason": "Silindi"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, moderation_users["reported"])
        assert user.is_banned is True
        assert "Silindi" in (user.ban_reason or "")


def test_report_filter_by_status(client, moderation_users, message_report):
    _login(client, "mod@test.com")
    resp = client.get("/admin/reports?durum=Bekliyor")
    assert resp.status_code == 200
    assert str(message_report["report_id"]).encode() in resp.data or b"Bekliyor" in resp.data


def test_report_search(client, moderation_users, message_report):
    _login(client, "mod@test.com")
    resp = client.get("/admin/reports?q=hakaret")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8", errors="ignore")
    assert "reporter" in text


def test_admin_logs_page(client, moderation_users, message_report):
    _login(client, "mod@test.com")
    client.post(
        f"/admin/report/{message_report['report_id']}/mark-reviewed",
        follow_redirects=True,
    )
    resp = client.get("/admin/logs")
    assert resp.status_code == 200
    assert b"sikayet_incele" in resp.data


def test_report_mark_reviewed_requires_post(client, moderation_users, message_report):
    _login(client, "mod@test.com")
    resp = client.get(f"/admin/report/{message_report['report_id']}/mark-reviewed")
    assert resp.status_code == 405


def test_normal_user_cannot_access_reports(client, moderation_users):
    _login(client, "reporter@test.com")
    resp = client.get("/admin/reports")
    assert resp.status_code == 403


def test_superadmin_cannot_ban_self(client, moderation_users, message_report):
    with client.application.app_context():
        s = db.session.get(Sikayet, message_report["report_id"])
        s.reported_user_id = moderation_users["superadmin"]
        db.session.commit()

    _login(client, "supermod@test.com")
    resp = client.post(
        f"/admin/report/{message_report['report_id']}/user/ban",
        data={"ban_reason": "x", "ban_duration": "permanent"},
    )
    assert resp.status_code == 403
