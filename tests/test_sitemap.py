"""SEO: sitemap.xml ve robots.txt."""

from __future__ import annotations

import xml.etree.ElementTree as ET

from models import Atik, Kaynak


NS = {"sm": "http://www.sitemaps.org/schemas/sitemap/0.9"}


def _set_site_url(app):
    app.config["SITE_URL"] = "https://atikport.com"


def test_sitemap_xml_ok(client, app):
    with app.app_context():
        _set_site_url(app)
    response = client.get("/sitemap.xml")
    assert response.status_code == 200
    assert "xml" in (response.mimetype or "").lower()
    body = response.data.decode("utf-8")
    assert '<?xml version="1.0"' in body
    assert "<urlset" in body
    assert "https://atikport.com/" in body
    assert "https://atikport.com/giris" in body
    assert "https://atikport.com/kayit" in body
    assert "/admin/" not in body
    assert "/belediye/" not in body
    assert "/api/" not in body
    assert "/minister/" not in body
    assert "/marketplace/" not in body

    root = ET.fromstring(response.data)
    locs = [el.text for el in root.findall("sm:url/sm:loc", NS)]
    assert locs
    assert any(u.rstrip("/").endswith("atikport.com") or u.endswith("atikport.com/") for u in locs)
    assert all("/admin" not in (u or "") for u in locs)
    assert all("/belediye" not in (u or "") for u in locs)
    assert all("/api/" not in (u or "") for u in locs)


def test_robots_txt_ok(client, app):
    with app.app_context():
        _set_site_url(app)
    response = client.get("/robots.txt")
    assert response.status_code == 200
    assert "text/plain" in (response.mimetype or "")
    text = response.data.decode("utf-8")
    assert "User-agent: *" in text
    assert "Allow: /" in text
    assert "Disallow: /admin/" in text
    assert "Disallow: /belediye/" in text
    assert "Disallow: /api/" in text
    assert "Sitemap: https://atikport.com/sitemap.xml" in text


def test_sitemap_includes_public_listings(client, app):
    with app.app_context():
        _set_site_url(app)
        from auth_utils import hash_password
        from extensions import db
        from models import User

        user = User(
            username="seo_owner",
            email="seo_owner@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
            email_verified=True,
        )
        db.session.add(user)
        db.session.flush()
        kaynak = Kaynak(
            baslik="SEO Kaynak",
            aciklama="Açıklama",
            durum="Temiz",
            kategori="Mobilya",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
            user_id=user.id,
        )
        atik = Atik(
            baslik="SEO Atik",
            aciklama="Açıklama",
            kategori="Plastik",
            latitude=41.0,
            longitude=29.0,
            ilan_durumu="Aktif",
            moderation_status="approved",
            user_id=user.id,
        )
        db.session.add_all([kaynak, atik])
        db.session.commit()
        kid, aid = kaynak.id, atik.id

    response = client.get("/sitemap.xml")
    body = response.data.decode("utf-8")
    assert f"https://atikport.com/kaynak/{kid}" in body
    assert f"https://atikport.com/atik/{aid}" in body
    assert "kategori=Mobilya" in body or "kategori=Mobilya" in body.replace("+", " ")


def test_layout_has_canonical_and_meta(client, app):
    with app.app_context():
        _set_site_url(app)
    response = client.get("/")
    html = response.data.decode("utf-8")
    assert 'rel="canonical"' in html
    assert 'name="description"' in html
    assert 'property="og:title"' in html
    assert 'property="og:description"' in html
    assert 'property="og:type"' in html
    assert 'property="og:url"' in html
    assert 'name="twitter:card"' in html
