"""Phase-2 AppSec: PoC-only validation of previously reported findings."""

from __future__ import annotations

import io
from unittest.mock import patch

from flask_login import login_user
from PIL import Image
from werkzeug.datastructures import FileStorage

from auth_utils import hash_password
from blueprints.belediye import _filters_from_request
from constants import MODERATION_STATUS_REJECTED
from extensions import db
from models import Kaynak, Mesaj, User
from services.ai_moderation import (
    apply_recyclable_adjustment,
    qualifies_for_risk_adjustment,
    resolve_moderation_status,
)
from services.client_ip import client_ip
from services.content_filter import mesaj_uygun_mu
from services.email_tokens import create_reset_token, peek_token, verify_reset_token
from services.session_security import password_session_stamp, session_matches_password, stamp_login_session
from utils import _validate_image_bytes, allowed_file, safe_redirect_url


def _user(**kwargs):
    defaults = dict(
        password=hash_password("TestPass1"),
        is_completed=True,
        email_verified=True,
        role="user",
    )
    defaults.update(kwargs)
    u = User(**defaults)
    db.session.add(u)
    db.session.commit()
    return u


def _login(client, email):
    return client.post(
        "/giris",
        data={"email": email, "password": "TestPass1"},
        follow_redirects=True,
    )


# ---------- AI ----------


def test_poc_ai_uygunsuz_whitelist_bypass_fixed():
    out = apply_recyclable_adjustment(
        {
            "risk_skoru": 98,
            "uygunsuz": True,
            "is_recyclable": True,
            "purpose": "recycling",
        },
        baslik="Silah geri dönüşüm için ücretsiz ver",
        aciklama="bertaraf",
        tur="atik",
    )
    assert out["risk_skoru"] == 98
    assert resolve_moderation_status(98, True) == MODERATION_STATUS_REJECTED


def test_poc_ai_flag_only_bypass_fixed():
    assert not qualifies_for_risk_adjustment(
        {
            "risk_skoru": 95,
            "is_recyclable": True,
            "purpose": "recycling",
            "uygunsuz": False,
        },
        baslik="Normal esya",
        aciklama="temiz urun",
        tur="atik",
    )


def test_poc_ai_unicode_zw_rtl_with_uygunsuz_not_exploitable():
    payloads = [
        "geri\u200bdönüşüm için ücretsiz ver",
        "geri dön\u202eüşüm ücretsiz",
        "ｇｅｒｉ dönüşüm ücretsiz ver",
        "♻️ geri dönüşüm için pil",
        "```geri dönüşüm``` ücretsiz ver",
        "GERİ DÖNÜŞÜM İÇİN ÜCRETSİZ VER",
        "Z2VyaSBkw7Zuw7zFn8O8bQ==",
    ]
    for text in payloads:
        out = apply_recyclable_adjustment(
            {"risk_skoru": 98, "uygunsuz": True},
            baslik=text,
            aciklama=text,
            tur="atik",
        )
        assert out["risk_skoru"] >= 90, text


# ---------- Messages ----------


def test_poc_message_ai_keyword_bypass_fixed(app):
    def ai_ok(_m):
        return {
            "uygun": True,
            "risk_skoru": 1,
            "kaynak": "ai",
            "mesaj": "",
            "hata": None,
            "kategori": "temiz",
        }

    with patch("services.content_filter.ai_mesaj_moderasyon", ai_ok):
        with app.app_context():
            ok, _ = mesaj_uygun_mu("Ürün mevcut mu?")
            bad, _ = mesaj_uygun_mu("amk ne diyorsun")
    assert ok is True
    assert bad is False


def test_poc_message_idor_fixed(client, app):
    with app.app_context():
        a = _user(username="idora", email="idora@t.com")
        b = _user(username="idorb", email="idorb@t.com")
        _user(username="idorc", email="idorc@t.com")
        db.session.add(Mesaj(sender_id=a.id, receiver_id=b.id, content="gizli"))
        db.session.commit()
        aid = a.id

    _login(client, "idorc@t.com")
    assert client.get(f"/mesajlar/{aid}/0/0").status_code == 403
    assert client.get(f"/mesajlar_getir/{aid}/0/0").status_code == 403


def test_poc_owner_arbitrary_partner_fixed(client, app):
    with app.app_context():
        own = _user(username="ownp", email="ownp@t.com")
        stranger = _user(username="strp", email="strp@t.com")
        k = Kaynak(
            user_id=own.id,
            baslik="OWN-POC",
            aciklama="x",
            durum="Temiz",
            kategori="Diğer",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
        )
        db.session.add(k)
        db.session.commit()
        sid, kid = stranger.id, k.id

    _login(client, "ownp@t.com")
    assert client.get(f"/mesajlar/{sid}/{kid}/0").status_code == 403


# ---------- Auth ----------


def test_poc_reset_token_not_consumed_before_success(app):
    with app.app_context():
        u = _user(username="resu", email="resu@t.com")
        token = create_reset_token(u)
        a, e1 = peek_token(token, "reset")
        b, e2 = peek_token(token, "reset")
        assert a and b and not e1 and not e2
        c, e3 = verify_reset_token(token)
        d, e4 = peek_token(token, "reset")
        assert c and not e3
        assert d is None


def test_poc_session_stamp_invalidates_after_password_change(app):
    with app.app_context():
        u = _user(username="stmp", email="stmp@t.com")
        old = password_session_stamp(u.password)
        u.password = hash_password("TestPass9!")
        db.session.commit()
        new = password_session_stamp(u.password)
        assert old != new

    with app.test_request_context("/"):
        from flask import session

        session["pwd_stamp"] = old
        with app.app_context():
            u = User.query.filter_by(email="stmp@t.com").first()
            assert session_matches_password(u) is False


def test_poc_logout_get_does_not_destroy_session(client, app):
    with app.app_context():
        _user(username="lgout", email="lgout@t.com")
    _login(client, "lgout@t.com")
    assert client.get("/profil").status_code == 200
    r = client.get("/cikis")
    assert r.status_code == 200  # confirmation page
    assert client.get("/profil").status_code == 200  # still logged in
    client.post("/cikis")
    assert client.get("/profil").status_code in (302, 401)


# ---------- AuthZ geo / IP / redirect ----------


def test_poc_municipality_geo_bypass_fixed(app):
    with app.app_context():
        muni = _user(
            username="muni2",
            email="muni2@t.com",
            role="municipality",
            il="İstanbul",
            ilce="Kadıköy",
        )
    with app.test_request_context("/belediye/dashboard?il=Ankara&ilce=Çankaya"):
        with app.app_context():
            muni = User.query.filter_by(email="muni2@t.com").first()
            login_user(muni)
            stamp_login_session(muni)
            f = _filters_from_request()
            assert f["il"] == "İstanbul"
            assert f["ilce"] == "Kadıköy"


def test_poc_xff_leftmost_spoof_fixed(app):
    with app.test_request_context(
        "/",
        environ_base={"REMOTE_ADDR": "203.0.113.10"},
        headers={"X-Forwarded-For": "1.2.3.4, 203.0.113.10"},
    ):
        assert client_ip() == "203.0.113.10"


def test_poc_open_redirect_helper_fixed(app):
    with app.test_request_context("/", base_url="https://atikport.test/"):
        url = safe_redirect_url("https://evil.example/phish", "marketplace.panel")
        assert "evil" not in url
        assert url.startswith("/")


# ---------- Upload ----------


def test_poc_upload_svg_php_polyglot_rejected():
    assert not allowed_file("x.svg")
    assert not allowed_file("x.php")
    assert not allowed_file("x.php.jpg")
    assert not allowed_file("x.html")
    assert not allowed_file("x.exe")

    php_as_jpg = FileStorage(
        stream=io.BytesIO(b"<?php system($_GET['c']); ?>"),
        filename="shell.jpg",
        content_type="image/jpeg",
    )
    ok, err, _ = _validate_image_bytes(php_as_jpg)
    assert not ok

    svg = b"""<?xml version='1.0'?><svg xmlns='http://www.w3.org/2000/svg' onload='alert(1)'/>"""
    svg_as_jpg = FileStorage(
        stream=io.BytesIO(svg),
        filename="xss.jpg",
        content_type="image/jpeg",
    )
    ok2, _, _ = _validate_image_bytes(svg_as_jpg)
    assert not ok2

    buf = io.BytesIO()
    Image.new("RGB", (8, 8), color="blue").save(buf, format="JPEG")
    good = FileStorage(
        stream=io.BytesIO(buf.getvalue()),
        filename="ok.jpg",
        content_type="image/jpeg",
    )
    ok3, err3, fmt = _validate_image_bytes(good)
    assert ok3 and fmt == "JPEG"
