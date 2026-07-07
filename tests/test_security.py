def test_sanitize_input_strips_html(client):
    from utils import sanitize_input

    assert sanitize_input("<script>alert(1)</script>Merhaba") == "alert(1)Merhaba"
    assert "<" not in sanitize_input("<b>kalın</b>")


def test_security_headers(client):
    response = client.get("/anasayfa")
    assert response.headers.get("X-Content-Type-Options") == "nosniff"
    assert response.headers.get("X-Frame-Options") == "SAMEORIGIN"
    assert "Content-Security-Policy" in response.headers
    csp = response.headers.get("Content-Security-Policy", "")
    assert "unsafe-inline" not in csp
    img_src = csp.split("img-src")[1].split(";")[0] if "img-src" in csp else ""
    assert "https:" not in img_src.split()
    assert response.headers.get("Server") is None
    assert "no-store" in response.headers.get("Cache-Control", "")


def test_static_cache_headers(client):
    response = client.get("/static/css/app.css")
    assert response.status_code == 200
    cache_control = response.headers.get("Cache-Control", "")
    assert "max-age" in cache_control


def test_argon2_password_upgrade_on_login(client, app):
    from auth_utils import hash_password, needs_password_update
    from extensions import db
    from models import User
    from werkzeug.security import generate_password_hash

    legacy = generate_password_hash("TestPass1", method="pbkdf2:sha256")
    assert needs_password_update(legacy)

    with app.app_context():
        user = User(
            username="legacyuser",
            email="legacy@test.com",
            password=legacy,
            is_completed=True,
        )
        db.session.add(user)
        db.session.commit()

    response = client.post(
        "/giris",
        data={"email": "legacy@test.com", "password": "TestPass1"},
        follow_redirects=True,
    )
    assert response.status_code == 200

    with app.app_context():
        user = User.query.filter_by(email="legacy@test.com").first()
        assert user.password.startswith("$argon2")
