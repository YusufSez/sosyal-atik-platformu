def test_error_page_404(client):
    response = client.get("/bu-sayfa-yok-xyz")
    assert response.status_code == 404
    html = response.data.decode("utf-8")
    assert "Sayfa Bulunamadı" in html
    assert "404" in html
    assert "AtıkPort" in html


def test_error_page_403(client, app):
    from auth_utils import hash_password
    from extensions import db
    from models import User

    with app.app_context():
        user = User(
            username="guest403",
            email="guest403@test.com",
            password=hash_password("TestPass1"),
            is_completed=True,
        )
        db.session.add(user)
        db.session.commit()

    client.post("/giris", data={"email": "guest403@test.com", "password": "TestPass1"}, follow_redirects=True)
    response = client.get("/admin")
    assert response.status_code == 403
    html = response.data.decode("utf-8")
    assert "Erişim Reddedildi" in html
    assert "403" in html


def test_error_page_429_template(app):
    with app.test_request_context():
        from flask import render_template

        html = render_template("errors/429.html")
        assert "Çok Fazla İstek" in html
        assert "429" in html
