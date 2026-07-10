"""Production öncesi güvenlik ve edge-case regression testleri."""

import io
import os

import pytest
from PIL import Image
from sqlalchemy import inspect
from sqlalchemy.pool import StaticPool
from werkzeug.datastructures import FileStorage

from auth_utils import hash_password
from extensions import db
from factory import create_app
from models import DestekTalebi, User
from services.user_moderation import count_active_superadmins, toggle_admin_role


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


def _edit_form(**overrides):
    data = {
        "username": "target",
        "email": "target@test.com",
        "telefon": "",
        "ad": "Ad",
        "soyad": "Soyad",
    }
    data.update(overrides)
    return data


@pytest.fixture
def sec_users(app):
    with app.app_context():
        superadmin = _user(
            username="secsa",
            email="secsa@test.com",
            is_admin=True,
            role="superadmin",
        )
        admin = _user(
            username="secadmin",
            email="secadmin@test.com",
            is_admin=True,
            role="admin",
        )
        target = _user(username="sectarget", email="sectarget@test.com")
        db.session.add_all([superadmin, admin, target])
        db.session.commit()
        ids = {
            "superadmin": superadmin.id,
            "admin": admin.id,
            "target": target.id,
        }
    yield ids


SUPERADMIN_ONLY_GET_ROUTES = [
    "/admin/users",
]

SUPERADMIN_ONLY_ROUTES = [
    lambda uid: f"/admin/users/{uid}",
    lambda uid: f"/admin/users/{uid}/edit",
]


def test_normal_admin_cannot_access_superadmin_user_routes(client, sec_users):
    _login(client, "secadmin@test.com")
    target_id = sec_users["target"]
    for path in SUPERADMIN_ONLY_GET_ROUTES:
        assert client.get(path).status_code == 403
    for route in SUPERADMIN_ONLY_ROUTES:
        assert client.get(route(target_id)).status_code == 403
    assert (
        client.post(
            f"/admin/users/{target_id}/edit",
            data=_edit_form(),
        ).status_code
        == 403
    )


def test_superadmin_cannot_deactivate_self(client, app, sec_users):
    _login(client, "secsa@test.com")
    resp = client.post(
        f"/admin/users/{sec_users['superadmin']}/edit",
        data=_edit_form(
            username="secsa",
            email="secsa@test.com",
            is_deactivated="1",
        ),
        follow_redirects=True,
    )
    text = resp.data.decode("utf-8", errors="ignore")
    assert "pasifleştiremezsiniz" in text.lower()
    with app.app_context():
        sa = db.session.get(User, sec_users["superadmin"])
        assert sa.is_deactivated is False


def test_cannot_deactivate_last_superadmin_via_other_superadmin(client, app, sec_users):
    with app.app_context():
        sa2 = _user(
            username="secsa2",
            email="secsa2@test.com",
            is_admin=True,
            role="superadmin",
        )
        db.session.add(sa2)
        db.session.commit()
        sa2_id = sa2.id

    _login(client, "secsa@test.com")
    resp = client.post(
        f"/admin/users/{sa2_id}/edit",
        data=_edit_form(
            username="secsa2",
            email="secsa2@test.com",
            is_deactivated="1",
        ),
        follow_redirects=True,
    )
    assert resp.status_code == 200
    with app.app_context():
        assert db.session.get(User, sa2_id).is_deactivated is True
        assert db.session.get(User, sec_users["superadmin"]).is_deactivated is False

    resp = client.post(
        f"/admin/users/{sec_users['superadmin']}/edit",
        data=_edit_form(
            username="secsa",
            email="secsa@test.com",
            is_deactivated="1",
        ),
        follow_redirects=True,
    )
    assert "pasifleştiremezsiniz" in resp.data.decode("utf-8", errors="ignore").lower()


def test_last_superadmin_role_cannot_be_toggled(app, sec_users):
    with app.app_context():
        sa = db.session.get(User, sec_users["superadmin"])
        with pytest.raises(ValueError, match="Süper admin rolü"):
            toggle_admin_role(sa)


def test_user_edit_blocks_privilege_escalation(client, app, sec_users):
    _login(client, "secsa@test.com")
    client.post(
        f"/admin/users/{sec_users['target']}/edit",
        data={
            "username": "sectarget",
            "email": "sectarget@test.com",
            "role": "superadmin",
            "is_admin": "1",
        },
        follow_redirects=True,
    )
    with app.app_context():
        target = db.session.get(User, sec_users["target"])
        assert target.role == "user"
        assert target.is_admin is False


def test_user_edit_immutable_fields_unchanged(client, app, sec_users):
    with app.app_context():
        target = db.session.get(User, sec_users["target"])
        before = {
            field: getattr(target, field)
            for field in ("role", "is_admin", "is_banned", "password", "xp")
        }
    _login(client, "secsa@test.com")
    client.post(
        f"/admin/users/{sec_users['target']}/edit",
        data={
            "username": "renameduser",
            "email": "sectarget@test.com",
            "ad": "Yeni",
            "soyad": "Ad",
        },
        follow_redirects=True,
    )
    with app.app_context():
        target = db.session.get(User, sec_users["target"])
        after = {
            field: getattr(target, field)
            for field in ("role", "is_admin", "is_banned", "password", "xp")
        }
        assert before == after
        assert target.username == "renameduser"


def test_guest_ticket_admin_list_and_detail_no_none_errors(client, app, sec_users):
    with app.app_context():
        talep = DestekTalebi(
            user_id=None,
            guest_name="Misafir",
            guest_surname="Test",
            guest_email="guest-sec@test.com",
            guest_phone="5550001122",
            baslik="Guest ticket",
            kategori="Öneri",
            mesaj="Mesaj",
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    _login(client, "secadmin@test.com")
    list_resp = client.get("/admin/destek")
    detail_resp = client.get(f"/admin/destek/{talep_id}")
    list_text = list_resp.data.decode("utf-8", errors="ignore")
    detail_text = detail_resp.data.decode("utf-8", errors="ignore")
    assert list_resp.status_code == 200
    assert detail_resp.status_code == 200
    assert "Misafir" in list_text
    assert "Misafir" in detail_text
    assert "guest-sec@test.com" in detail_text
    assert "None" not in detail_text


def test_guest_support_attachment_only_admin(client, app, sec_users, tmp_path):
    with app.app_context():
        app.config["SUPPORT_UPLOAD_FOLDER"] = str(tmp_path)
        from utils import save_support_attachment

        buf = io.BytesIO()
        Image.new("RGB", (16, 16), color="red").save(buf, format="JPEG")
        buf.seek(0)
        stored = save_support_attachment(
            FileStorage(stream=buf, filename="ek.jpg", content_type="image/jpeg")
        )
        talep = DestekTalebi(
            user_id=None,
            guest_name="Misafir",
            guest_surname="Ek",
            guest_email="guest-attach@test.com",
            guest_phone="5550003344",
            baslik="Ek",
            kategori="Öneri",
            mesaj="Mesaj",
            ek_resim=stored,
        )
        db.session.add(talep)
        db.session.commit()
        talep_id = talep.id

    assert client.get(f"/support/attachment/{talep_id}").status_code in (302, 401, 403)
    _login(client, "secadmin@test.com")
    assert client.get(f"/support/attachment/{talep_id}").status_code == 200


def test_destek_talebi_user_id_nullable_model():
    column = DestekTalebi.__table__.c.user_id
    assert column.nullable is True


def test_user_edit_field_lengths_match_migration():
    assert User.__table__.c.adres.type.length == 255
    assert User.__table__.c.ad.type.length == 100
    assert User.__table__.c.soyad.type.length == 100
    assert User.__table__.c.telefon.type.length == 20
    assert DestekTalebi.__table__.c.guest_email.type.length == 150
    assert DestekTalebi.__table__.c.guest_phone.type.length == 20


@pytest.mark.parametrize(
    "db_uri,engine_options",
    [
        (
            "sqlite://",
            {
                "poolclass": StaticPool,
                "connect_args": {"check_same_thread": False},
            },
        ),
    ],
)
def test_guest_ticket_persists_across_db_backends(db_uri, engine_options):
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": db_uri,
            "SQLALCHEMY_ENGINE_OPTIONS": engine_options,
            "WTF_CSRF_ENABLED": False,
            "TURNSTILE_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        talep = DestekTalebi(
            user_id=None,
            guest_name="DB",
            guest_surname="Test",
            guest_email="db-guest@test.com",
            guest_phone="5551110000",
            baslik="Başlık",
            kategori="Öneri",
            mesaj="Mesaj",
        )
        db.session.add(talep)
        db.session.commit()
        saved = DestekTalebi.query.filter_by(guest_email="db-guest@test.com").first()
        assert saved is not None
        assert saved.user_id is None
        assert saved.is_guest is True
        with db.engine.connect() as conn:
            insp = inspect(conn)
            cols = {c["name"]: c for c in insp.get_columns("destek_talebi")}
            assert cols["user_id"]["nullable"] is True
        db.session.remove()
        db.drop_all()


def test_guest_ticket_persists_on_postgres_when_configured():
    postgres_url = os.environ.get("TEST_DATABASE_URL", "").strip()
    if not postgres_url:
        pytest.skip("TEST_DATABASE_URL tanımlı değil")
    app = create_app(
        {
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": postgres_url,
            "WTF_CSRF_ENABLED": False,
            "TURNSTILE_ENABLED": False,
        }
    )
    with app.app_context():
        db.create_all()
        talep = DestekTalebi(
            user_id=None,
            guest_name="PG",
            guest_surname="Guest",
            guest_email="pg-guest@test.com",
            guest_phone="5552220000",
            baslik="PG",
            kategori="Öneri",
            mesaj="Mesaj",
        )
        db.session.add(talep)
        db.session.commit()
        assert DestekTalebi.query.filter_by(guest_email="pg-guest@test.com").count() == 1
        db.session.remove()
        db.drop_all()


def test_count_active_superadmins_excludes_deactivated(app, sec_users):
    with app.app_context():
        assert count_active_superadmins() == 1
        sa = db.session.get(User, sec_users["superadmin"])
        sa.is_deactivated = True
        db.session.commit()
        assert count_active_superadmins() == 0
