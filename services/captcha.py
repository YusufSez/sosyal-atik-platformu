"""Google reCAPTCHA v2 doğrulama."""

import requests
from flask import current_app, request


def captcha_is_enabled():
    return bool(
        current_app.config.get("RECAPTCHA_ENABLED")
        and current_app.config.get("RECAPTCHA_SECRET_KEY")
    )


def verify_recaptcha(token):
    if not captcha_is_enabled():
        return True, None
    if not token:
        return False, "Lütfen CAPTCHA doğrulamasını tamamlayın."
    try:
        resp = requests.post(
            "https://www.google.com/recaptcha/api/siteverify",
            data={
                "secret": current_app.config["RECAPTCHA_SECRET_KEY"],
                "response": token,
                "remoteip": request.remote_addr,
            },
            timeout=5,
        )
        data = resp.json()
        if data.get("success"):
            return True, None
        return False, "CAPTCHA doğrulaması başarısız. Lütfen tekrar deneyin."
    except requests.RequestException:
        return False, "CAPTCHA servisine ulaşılamadı. Lütfen daha sonra tekrar deneyin."


def captcha_hatasi():
    token = request.form.get("g-recaptcha-response", "")
    ok, err = verify_recaptcha(token)
    return None if ok else err
