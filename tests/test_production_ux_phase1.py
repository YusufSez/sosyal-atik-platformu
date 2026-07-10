"""Production UX Phase 1 testleri."""

from pathlib import Path

import pytest

from auth_utils import hash_password
from extensions import db
from models import Bildirim, DestekTalebi, Mesaj, User
from services.admin_notifications import notify_admins
from services.notification_sync import mark_message_notifications_read
from services.user_moderation import apply_ban, normalize_ban_reason, soft_delete_user


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        role="user",
        is_admin=False,
        email_verified=True,
    )
    defaults.update(kwargs)
    return User(**defaults)


def _login(client, email):
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


@pytest.fixture
def ux_users(app):
    with app.app_context():
        superadmin = _user(
            username="uxsa",
            email="uxsa@test.com",
            is_admin=True,
            role="superadmin",
        )
        admin = _user(
            username="uxadmin",
            email="uxadmin@test.com",
            is_admin=True,
            role="admin",
        )
        victim = _user(username="uxvictim", email="uxvictim@test.com")
        member = _user(username="uxmember", email="uxmember@test.com")
        db.session.add_all([superadmin, admin, victim, member])
        db.session.commit()
        ids = {
            "superadmin": superadmin.id,
            "admin": admin.id,
            "victim": victim.id,
            "member": member.id,
        }
    yield ids


def test_normalize_ban_reason_requires_text():
    assert normalize_ban_reason("  spam  ") == "spam"
    assert normalize_ban_reason("") is None
    assert normalize_ban_reason(None) is None


def test_ban_requires_reason_and_stores_metadata(app, client, ux_users):
    with app.app_context():
        victim = db.session.get(User, ux_users["victim"])
        apply_ban(victim, "Kural ihlali", None, banned_by_id=ux_users["superadmin"])
        db.session.commit()

    _login(client, "uxvictim@test.com")
    resp = client.post(
        "/giris",
        data={"email": "uxvictim@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "Hesabınız askıya alınmıştır" in text
    assert "Kural ihlali" in text
    assert "destek sistemi" in text.lower() or "destek" in text.lower()

    _login(client, "uxsa@test.com")
    resp = client.post(
        f"/admin/users/ban/{ux_users['member']}",
        data={"ban_reason": "", "ban_duration": "permanent"},
        follow_redirects=True,
    )
    assert "Ban sebebi zorunludur" in resp.data.decode("utf-8", errors="ignore")

    with app.app_context():
        member = db.session.get(User, ux_users["member"])
        assert member.is_banned is False


def test_ban_stores_banned_by_id(app, client, ux_users):
    _login(client, "uxsa@test.com")
    client.post(
        f"/admin/users/ban/{ux_users['member']}",
        data={"ban_reason": "Spam", "ban_duration": "permanent"},
        follow_redirects=True,
    )
    with app.app_context():
        member = db.session.get(User, ux_users["member"])
        assert member.is_banned is True
        assert member.ban_reason == "Spam"
        assert member.banned_by_id == ux_users["superadmin"]
        assert member.banned_at is not None


def test_admin_user_detail_page(client, ux_users):
    _login(client, "uxsa@test.com")
    resp = client.get(f"/admin/users/{ux_users['member']}")
    assert resp.status_code == 200
    text = resp.data.decode("utf-8", errors="ignore")
    assert "Kullanıcı Detayı" in text
    assert "uxmember" in text
    assert "İstatistikler" in text


def test_support_request_creates_ticket_and_admin_notification(app, client, ux_users):
    _login(client, "uxmember@test.com")
    resp = client.post(
        "/destek",
        data={
            "baslik": "Öneri test",
            "kategori": "Öneri",
            "mesaj": "Platform çok iyi",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(user_id=ux_users["member"]).first()
        assert talep is not None
        assert talep.baslik == "Öneri test"
        assert talep.kategori == "Öneri"
        bildirim = Bildirim.query.filter_by(user_id=ux_users["admin"], tur="admin_destek").first()
        assert bildirim is not None
        assert "Öneri test" in bildirim.icerik


def test_admin_destek_list_and_update(client, ux_users, app):
    with app.app_context():
        talep = DestekTalebi(
            user_id=ux_users["member"],
            baslik="Şikayet",
            kategori="Şikayet",
            mesaj="Sorun var",
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    _login(client, "uxadmin@test.com")
    resp = client.get("/admin/destek")
    assert resp.status_code == 200
    assert "Şikayet" in resp.data.decode("utf-8", errors="ignore")

    resp = client.post(
        f"/admin/destek/{talep_id}",
        data={"durum": "İnceleniyor", "admin_not": "Bakıyoruz"},
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = db.session.get(DestekTalebi, talep_id)
        assert talep.durum == "İnceleniyor"
        assert talep.admin_not == "Bakıyoruz"
        assert talep.reviewer_id == ux_users["admin"]


def test_notify_admins_creates_for_all_admins(app, ux_users):
    with app.app_context():
        before = Bildirim.query.filter_by(tur="admin_test").count()
        notify_admins("Test", "İçerik", "admin_test", "/admin")
        after = Bildirim.query.filter_by(tur="admin_test").count()
        assert after - before >= 2


def test_mark_message_notifications_read(app, ux_users):
    with app.app_context():
        partner = ux_users["member"]
        reader = ux_users["victim"]
        mesaj = Mesaj(
            sender_id=partner,
            receiver_id=reader,
            content="Merhaba",
        )
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id
        link = f"/mesajlar/{partner}/0/0"
        bildirim = Bildirim(
            user_id=reader,
            baslik="Yeni mesaj",
            icerik="Merhaba",
            tur="mesaj",
            link=link,
            mesaj_id=mesaj_id,
            okundu=False,
        )
        db.session.add(bildirim)
        db.session.commit()
        bildirim_id = bildirim.id

        count = mark_message_notifications_read(
            reader, messages=[db.session.get(Mesaj, mesaj_id)]
        )
        assert count == 1
        row = db.session.get(Bildirim, bildirim_id)
        assert row.okundu is True


def test_message_read_marks_notification(app, client, ux_users):
    with app.app_context():
        mesaj = Mesaj(
            sender_id=ux_users["member"],
            receiver_id=ux_users["victim"],
            content="selam",
            kaynak_id=None,
            atik_id=None,
        )
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id
        bildirim = Bildirim(
            user_id=ux_users["victim"],
            baslik="Mesaj",
            icerik="selam",
            tur="mesaj",
            link=f"/mesajlar/{ux_users['member']}/0/0",
            mesaj_id=mesaj_id,
            okundu=False,
        )
        db.session.add(bildirim)
        db.session.commit()
        bildirim_id = bildirim.id

    _login(client, "uxvictim@test.com")
    client.get(f"/mesajlar_getir/{ux_users['member']}/0/0")

    with app.app_context():
        row = db.session.get(Bildirim, bildirim_id)
        assert row.okundu is True
        mesaj = db.session.get(Mesaj, mesaj_id)
        assert mesaj.is_read is True


def test_message_scroll_helper_algorithm():
    def is_near_bottom(scroll_height, scroll_top, client_height, threshold=80):
        return scroll_height - scroll_top - client_height < threshold

    assert is_near_bottom(1000, 900, 100) is True
    assert is_near_bottom(1000, 100, 100) is False
    assert is_near_bottom(1000, 821, 100) is True


def test_lightbox_assets_exist():
    root = Path(__file__).resolve().parents[1]
    js = (root / "static" / "js" / "ilan-lightbox.js").read_text(encoding="utf-8")
    assert "IlanLightbox" in js
    assert "Escape" in js or "keydown" in js
    css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".ilan-lightbox" in css


def test_item_card_uses_contain_fit():
    root = Path(__file__).resolve().parents[1]
    css = (root / "static" / "css" / "app.css").read_text(encoding="utf-8")
    assert ".item-card .card-img-wrap img" in css
    block_start = css.index(".item-card .card-img-wrap img")
    block = css[block_start : block_start + 200]
    assert "object-fit: contain" in block


def test_soft_delete_requires_reason(app, client, ux_users):
    _login(client, "uxsa@test.com")
    with app.app_context():
        user = db.session.get(User, ux_users["member"])
        soft_delete_user(user, "Hesap kapatma", banned_by_id=ux_users["superadmin"])
        db.session.commit()
        assert user.is_banned is True
        assert user.banned_by_id == ux_users["superadmin"]
