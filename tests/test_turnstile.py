import pytest

from services.captcha import captcha_hatasi, verify_turnstile


def test_turnstile_kapali_iken_gecer(app):
    with app.app_context():
        ok, err = verify_turnstile("")
        assert ok is True
        assert err is None


def test_turnstile_token_zorunlu(app):
    app.config["TURNSTILE_ENABLED"] = True
    app.config["TURNSTILE_SECRET_KEY"] = "test-secret"
    with app.app_context():
        ok, err = verify_turnstile("")
        assert ok is False
        assert "güvenlik doğrulamasını" in err.lower()


def test_turnstile_dogrulama_basari(app, monkeypatch):
    app.config["TURNSTILE_ENABLED"] = True
    app.config["TURNSTILE_SECRET_KEY"] = "test-secret"

    class FakeResp:
        def json(self):
            return {"success": True}

    monkeypatch.setattr(
        "services.captcha.requests.post",
        lambda *a, **k: FakeResp(),
    )

    with app.test_request_context():
        ok, err = verify_turnstile("token-abc")
        assert ok is True
        assert err is None


def test_captcha_hatasi_form_token(client, app, monkeypatch):
    app.config["TURNSTILE_ENABLED"] = True
    app.config["TURNSTILE_SECRET_KEY"] = "test-secret"

    class FakeResp:
        def json(self):
            return {"success": True}

    monkeypatch.setattr(
        "services.captcha.requests.post",
        lambda *a, **k: FakeResp(),
    )

    with app.test_request_context(
        method="POST",
        data={"cf-turnstile-response": "valid-token"},
    ):
        assert captcha_hatasi() is None
