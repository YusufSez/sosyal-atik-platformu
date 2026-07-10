"""Production UX Phase 3 testleri."""

import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from auth_utils import hash_password
from constants import DESTEK_KATEGORI_BAN_ITIRAZI_LABEL
from extensions import db
from models import AdminAuditLog, DestekDurumGecmisi, DestekTalebi, User
from services.user_moderation import apply_ban


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


def _guest_destek_form(**overrides):
    data = {
        "ad": "Misafir",
        "soyad": "Kullanıcı",
        "email": "guest@test.com",
        "telefon": "5551112233",
        "kategori": "Öneri",
        "baslik": "Konu başlığı",
        "mesaj": "Destek mesajı içeriği",
    }
    data.update(overrides)
    return data


@pytest.fixture
def phase3_users(app):
    with app.app_context():
        superadmin = _user(
            username="p3sa",
            email="p3sa@test.com",
            is_admin=True,
            role="superadmin",
            ad="Süper",
            soyad="Admin",
        )
        admin = _user(
            username="p3admin",
            email="p3admin@test.com",
            is_admin=True,
            role="admin",
        )
        victim = _user(
            username="p3victim",
            email="p3victim@test.com",
            ad="Kurban",
            soyad="Kullanıcı",
            telefon="5559998877",
        )
        other = _user(
            username="p3other",
            email="p3other@test.com",
            telefon="5554443322",
        )
        banned = _user(
            username="p3banned",
            email="p3banned@test.com",
            is_banned=True,
            ban_reason="Test ban",
            ad="Banlı",
            soyad="Kullanıcı",
            telefon="5556667788",
        )
        db.session.add_all([superadmin, admin, victim, other, banned])
        db.session.commit()
        ids = {
            "superadmin": superadmin.id,
            "admin": admin.id,
            "victim": victim.id,
            "other": other.id,
            "banned": banned.id,
        }
    yield ids


def test_superadmin_can_edit_user(client, app, phase3_users):
    _login(client, "p3sa@test.com")
    resp = client.get(f"/admin/users/{phase3_users['victim']}/edit")
    assert resp.status_code == 200

    resp = client.post(
        f"/admin/users/{phase3_users['victim']}/edit",
        data={
            "ad": "Yeni",
            "soyad": "İsim",
            "username": "p3victim",
            "email": "p3victim@test.com",
            "telefon": "5559998877",
            "il": "İstanbul",
            "ilce": "Kadıköy",
            "adres": "Test adres 1",
            "profil_aciklama": "Açıklama metni",
            "email_verified": "1",
            "telefon_verified": "1",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        user = db.session.get(User, phase3_users["victim"])
        assert user.ad == "Yeni"
        assert user.soyad == "İsim"
        assert user.adres == "Test adres 1"
        assert user.profil_aciklama == "Açıklama metni"
        assert user.telefon_verified is True
        logs = AdminAuditLog.query.filter_by(action="user_edit", target_user_id=user.id).all()
        assert len(logs) >= 4
        assert any(log.detail == "ad" and log.old_value == "Kurban" for log in logs)


def test_admin_cannot_edit_user(client, phase3_users):
    _login(client, "p3admin@test.com")
    assert client.get(f"/admin/users/{phase3_users['victim']}/edit").status_code == 403
    assert (
        client.post(
            f"/admin/users/{phase3_users['victim']}/edit",
            data={"username": "hack"},
        ).status_code
        == 403
    )


def test_edit_rejects_duplicate_username(client, phase3_users):
    _login(client, "p3sa@test.com")
    resp = client.post(
        f"/admin/users/{phase3_users['victim']}/edit",
        data={
            "username": "p3other",
            "email": "p3victim@test.com",
            "telefon": "5559998877",
        },
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "kullanıcı adı" in text.lower()


def test_edit_rejects_duplicate_email(client, phase3_users):
    _login(client, "p3sa@test.com")
    resp = client.post(
        f"/admin/users/{phase3_users['victim']}/edit",
        data={
            "username": "p3victim",
            "email": "p3other@test.com",
            "telefon": "5559998877",
        },
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "e-posta" in text.lower()


def test_edit_rejects_duplicate_phone(client, phase3_users):
    _login(client, "p3sa@test.com")
    resp = client.post(
        f"/admin/users/{phase3_users['victim']}/edit",
        data={
            "username": "p3victim",
            "email": "p3victim@test.com",
            "telefon": "5554443322",
        },
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "telefon" in text.lower()


def test_guest_support_request(client, app):
    resp = client.post(
        "/destek",
        data=_guest_destek_form(),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(guest_email="guest@test.com").first()
        assert talep is not None
        assert talep.is_guest is True
        assert talep.user_id is None
        assert talep.guest_name == "Misafir"
        assert DestekDurumGecmisi.query.filter_by(talep_id=talep.id).count() == 1


def test_authenticated_support_request(client, app, phase3_users):
    _login(client, "p3other@test.com")
    resp = client.post(
        "/destek",
        data={
            "baslik": "Üye talebi",
            "kategori": "İstek",
            "mesaj": "Üye destek mesajı",
        },
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(user_id=phase3_users["other"]).first()
        assert talep is not None
        assert talep.is_guest is False
        assert talep.baslik == "Üye talebi"


def test_guest_support_upload(client, app, tmp_path):
    with app.app_context():
        app.config["SUPPORT_UPLOAD_FOLDER"] = str(tmp_path)

    resp = client.post(
        "/destek",
        data={
            **_guest_destek_form(email="uploadguest@test.com"),
            "ek_resim": _make_image_file(),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(guest_email="uploadguest@test.com").first()
        assert talep is not None
        assert talep.ek_resim is not None


def test_guest_support_rejects_invalid_image(client, app):
    client.post(
        "/destek",
        data={
            **_guest_destek_form(email="badimg@test.com"),
            "ek_resim": FileStorage(
                stream=io.BytesIO(b"not-image"),
                filename="bad.jpg",
                content_type="image/jpeg",
            ),
        },
        content_type="multipart/form-data",
        follow_redirects=True,
    )
    with app.app_context():
        assert DestekTalebi.query.filter_by(guest_email="badimg@test.com").first() is None


def test_banned_user_guest_ban_appeal(client, app, phase3_users):
    resp = client.post(
        "/destek",
        data=_guest_destek_form(
            ad="Banlı",
            soyad="Kullanıcı",
            email="p3banned@test.com",
            telefon="5556667788",
            kategori=DESTEK_KATEGORI_BAN_ITIRAZI_LABEL,
            baslik="Ban itirazım",
            mesaj="Hatalı ban kararı",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        talep = DestekTalebi.query.filter_by(guest_email="p3banned@test.com").first()
        assert talep is not None
        assert talep.kategori == DESTEK_KATEGORI_BAN_ITIRAZI_LABEL
        assert talep.is_guest is True


def test_admin_views_guest_ticket(client, app, phase3_users):
    with app.app_context():
        talep = DestekTalebi(
            user_id=None,
            guest_name="Misafir",
            guest_surname="Test",
            guest_email="p3banned@test.com",
            guest_phone="5556667788",
            baslik="Ban itiraz",
            kategori=DESTEK_KATEGORI_BAN_ITIRAZI_LABEL,
            mesaj="İtiraz metni",
            ip_address="127.0.0.1",
            user_agent="pytest",
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    _login(client, "p3admin@test.com")
    resp = client.get(f"/admin/destek/{talep_id}")
    text = resp.data.decode("utf-8", errors="ignore")
    assert resp.status_code == 200
    assert "Misafir" in text
    assert "p3banned@test.com" in text
    assert "Kayıtlı kullanıcı" in text or "p3banned" in text


def test_admin_views_registered_user_ticket(client, app, phase3_users):
    with app.app_context():
        talep = DestekTalebi(
            user_id=phase3_users["other"],
            baslik="Üye talep",
            kategori="Öneri",
            mesaj="Mesaj",
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    _login(client, "p3admin@test.com")
    resp = client.get(f"/admin/destek/{talep_id}")
    text = resp.data.decode("utf-8", errors="ignore")
    assert resp.status_code == 200
    assert "Kullanıcı" in text
    assert "p3other" in text


def test_support_attachment_access_control(client, app, phase3_users, tmp_path):
    with app.app_context():
        app.config["SUPPORT_UPLOAD_FOLDER"] = str(tmp_path)
        from utils import save_support_attachment

        stored = save_support_attachment(_make_image_file())
        talep = DestekTalebi(
            user_id=phase3_users["other"],
            baslik="Ekli",
            kategori="Öneri",
            mesaj="Mesaj",
            ek_resim=stored,
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    assert client.get(f"/support/attachment/{talep_id}").status_code in (302, 401, 403)

    _login(client, "p3victim@test.com")
    assert client.get(f"/support/attachment/{talep_id}").status_code == 403

    _login(client, "p3other@test.com")
    assert client.get(f"/support/attachment/{talep_id}").status_code == 200

    _login(client, "p3admin@test.com")
    assert client.get(f"/support/attachment/{talep_id}").status_code == 200


def test_banned_logged_in_user_can_submit_support(client, app, phase3_users):
    _login(client, "p3other@test.com")
    with app.app_context():
        user = db.session.get(User, phase3_users["other"])
        apply_ban(user, "Geçici ban", None, banned_by_id=phase3_users["superadmin"])
        db.session.commit()

    resp = client.post(
        "/destek",
        data={
            "baslik": "Banlı oturum",
            "kategori": DESTEK_KATEGORI_BAN_ITIRAZI_LABEL,
            "mesaj": "Oturum açıkken itiraz",
        },
        follow_redirects=False,
    )
    assert resp.status_code in (302, 303)
    with app.app_context():
        talep = (
            DestekTalebi.query.filter_by(user_id=phase3_users["other"])
            .order_by(DestekTalebi.id.desc())
            .first()
        )
        assert talep is not None
        assert talep.kategori == DESTEK_KATEGORI_BAN_ITIRAZI_LABEL


def test_login_ban_notice_links_destek(client, phase3_users):
    resp = client.post(
        "/giris",
        data={"email": "p3banned@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "/destek" in text
