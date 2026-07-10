"""UX Phase 1 güvenlik / hardening testleri."""

import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from auth_utils import hash_password
from extensions import db
from models import Bildirim, DestekTalebi, Mesaj, User
from services.admin_notifications import notify_admins
from services.notification_sync import mark_message_notifications_read
from services.user_moderation import apply_ban, soft_delete_user


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        role="user",
        is_admin=False,
        email_verified=True,
    )
    defaults.update(kwargs)
    return User(**kwargs)


def _login(client, email):
    client.get("/cikis", follow_redirects=True)
    client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


def _make_image_file(ext="jpg", fmt="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", (32, 32), color="blue").save(buf, format=fmt)
    buf.seek(0)
    return FileStorage(
        stream=buf,
        filename=f"ek.{ext}",
        content_type="image/jpeg" if fmt == "JPEG" else f"image/{ext}",
    )


@pytest.fixture
def hardening_users(app):
    pwd = hash_password("TestPass1")
    with app.app_context():
        admin = User(
            username="hadmin",
            email="hadmin@test.com",
            password=pwd,
            is_completed=True,
            is_admin=True,
            role="admin",
            email_verified=True,
        )
        member = User(
            username="hmember",
            email="hmember@test.com",
            password=pwd,
            is_completed=True,
            email_verified=True,
        )
        banned = User(
            username="hbanned",
            email="hbanned@test.com",
            password=pwd,
            is_completed=True,
            is_banned=True,
            email_verified=True,
        )
        other = User(
            username="hother",
            email="hother@test.com",
            password=pwd,
            is_completed=True,
            email_verified=True,
        )
        db.session.add_all([admin, member, banned, other])
        db.session.commit()
        ids = {
            "admin": admin.id,
            "member": member.id,
            "banned": banned.id,
            "other": other.id,
        }
    yield ids


def test_support_attachment_not_public_static(client, app, hardening_users):
    with app.app_context():
        talep = DestekTalebi(
            user_id=hardening_users["member"],
            baslik="Test",
            kategori="Öneri",
            mesaj="Mesaj",
            ek_resim="secret.jpg",
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    resp = client.get("/static/support_attachments/secret.jpg")
    assert resp.status_code == 404

    _login(client, "hother@test.com")
    assert client.get(f"/support/attachment/{talep_id}").status_code == 403

    client.post("/cikis", follow_redirects=True)
    _login(client, "hmember@test.com")
    # dosya yok — auth geçer ama 404
    assert client.get(f"/support/attachment/{talep_id}").status_code == 404


def test_support_attachment_admin_access_with_file(client, app, hardening_users, tmp_path):
    with app.app_context():
        app.config["SUPPORT_UPLOAD_FOLDER"] = str(tmp_path)
        from utils import save_support_attachment

        img = _make_image_file()
        stored = save_support_attachment(img)
        talep = DestekTalebi(
            user_id=hardening_users["member"],
            baslik="Ekli",
            kategori="Öneri",
            mesaj="Mesaj",
            ek_resim=stored,
            ek_resim_orijinal="ek.jpg",
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    _login(client, "hadmin@test.com")
    resp = client.get(f"/support/attachment/{talep_id}")
    assert resp.status_code == 200
    assert resp.mimetype.startswith("image/")


def test_destek_rejects_invalid_image(client, hardening_users):
    _login(client, "hmember@test.com")
    resp = client.post(
        "/destek",
        data={
            "baslik": "Test",
            "kategori": "Öneri",
            "mesaj": "İçerik",
            "ek_resim": FileStorage(
                stream=io.BytesIO(b"not-image"),
                filename="bad.jpg",
                content_type="image/jpeg",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "Geçersiz" in text or "görsel" in text.lower()


def test_destek_accepts_valid_image(client, app, hardening_users, tmp_path):
    with app.app_context():
        app.config["SUPPORT_UPLOAD_FOLDER"] = str(tmp_path)

    _login(client, "hmember@test.com")
    resp = client.post(
        "/destek",
        data={
            "baslik": "Görsel",
            "kategori": "Öneri",
            "mesaj": "İçerik",
            "ek_resim": _make_image_file(),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(user_id=hardening_users["member"]).first()
        assert talep is not None
        assert talep.ek_resim is not None
        assert talep.ek_resim_orijinal == "ek.jpg"


def test_ban_itiraz_without_login(client, app, hardening_users):
    resp = client.post(
        "/destek",
        data={
            "ad": "Banlı",
            "soyad": "Kullanıcı",
            "email": "hbanned@test.com",
            "telefon": "5551234567",
            "kategori": "Ban İtirazı",
            "baslik": "Ban itirazı",
            "mesaj": "Hatalı ban",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(guest_email="hbanned@test.com").first()
        assert talep is not None
        assert talep.kategori == "Ban İtirazı"


def test_ban_itiraz_legacy_redirect(client):
    resp = client.get("/ban-itiraz", follow_redirects=False)
    assert resp.status_code == 302
    assert "/destek" in resp.headers.get("Location", "")


def test_notify_admins_atomic_all_admins(app, hardening_users):
    with app.app_context():
        pwd = hash_password("TestPass1")
        superadmin = User(
            username="hsa",
            email="hsa@test.com",
            password=pwd,
            is_completed=True,
            is_admin=True,
            role="superadmin",
            email_verified=True,
        )
        db.session.add(superadmin)
        db.session.commit()
        admin_count = User.query.filter(
            User.is_deactivated.is_(False),
            db.or_(User.is_admin.is_(True), User.role.in_(("admin", "superadmin"))),
        ).count()
        before = Bildirim.query.filter_by(tur="admin_atomic_test").count()
        notify_admins("T", "İçerik", "admin_atomic_test", "/admin")
        after = Bildirim.query.filter_by(tur="admin_atomic_test").count()
        assert after - before == admin_count


def test_mark_notification_by_mesaj_id(app, hardening_users):
    with app.app_context():
        mesaj = Mesaj(
            sender_id=hardening_users["member"],
            receiver_id=hardening_users["other"],
            content="selam",
        )
        db.session.add(mesaj)
        db.session.commit()
        mesaj_id = mesaj.id
        bildirim = Bildirim(
            user_id=hardening_users["other"],
            baslik="Mesaj",
            icerik="x",
            tur="mesaj",
            link="/mesajlar/yanlis/0/0",
            mesaj_id=mesaj_id,
            okundu=False,
        )
        db.session.add(bildirim)
        db.session.commit()
        bid = bildirim.id

        count = mark_message_notifications_read(
            hardening_users["other"],
            messages=[mesaj],
        )
        assert count == 1
        row = db.session.get(Bildirim, bid)
        assert row.okundu is True


def test_mark_notifications_multi_conversation_batch(app, hardening_users):
    with app.app_context():
        m1 = Mesaj(
            sender_id=hardening_users["member"],
            receiver_id=hardening_users["other"],
            content="a",
        )
        m2 = Mesaj(
            sender_id=hardening_users["admin"],
            receiver_id=hardening_users["other"],
            content="b",
        )
        db.session.add_all([m1, m2])
        db.session.commit()
        b1 = Bildirim(
            user_id=hardening_users["other"],
            baslik="1",
            icerik="1",
            tur="mesaj",
            link=f"/mesajlar/{hardening_users['member']}/0/0",
            mesaj_id=m1.id,
            okundu=False,
        )
        b2 = Bildirim(
            user_id=hardening_users["other"],
            baslik="2",
            icerik="2",
            tur="mesaj",
            link=f"/mesajlar/{hardening_users['admin']}/0/0",
            mesaj_id=m2.id,
            okundu=False,
        )
        db.session.add_all([b1, b2])
        db.session.commit()

        count = mark_message_notifications_read(
            hardening_users["other"],
            messages=[m1, m2],
        )
        assert count == 2


def test_soft_delete_requires_reason_service_level(app, hardening_users):
    with app.app_context():
        user = db.session.get(User, hardening_users["member"])
        with pytest.raises(ValueError, match="Ban sebebi"):
            soft_delete_user(user, "")
        with pytest.raises(ValueError, match="Ban sebebi"):
            soft_delete_user(user, None)


def test_soft_delete_with_reason(app, hardening_users):
    with app.app_context():
        user = db.session.get(User, hardening_users["member"])
        soft_delete_user(user, "Kural ihlali", banned_by_id=hardening_users["admin"])
        db.session.commit()
        assert user.is_banned is True
        assert user.ban_reason == "Kural ihlali"


def test_login_ban_notice_links_destek(client, app, hardening_users):
    with app.app_context():
        user = db.session.get(User, hardening_users["banned"])
        user.ban_reason = "Test sebep"
        db.session.commit()

    resp = client.post(
        "/giris",
        data={"email": "hbanned@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "/destek" in text
