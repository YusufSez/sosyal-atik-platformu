"""Cloudflare Turnstile doğrulama."""

import requests
from flask import current_app, request

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"


def turnstile_is_enabled():
    return bool(
        current_app.config.get("TURNSTILE_ENABLED")
        and current_app.config.get("TURNSTILE_SECRET_KEY")
    )


def verify_turnstile(token: str) -> tuple[bool, str | None]:
    if not turnstile_is_enabled():
        return True, None
    if not token:
        return False, "Lütfen güvenlik doğrulamasını tamamlayın."
    try:
        resp = requests.post(
            TURNSTILE_VERIFY_URL,
            data={
                "secret": current_app.config["TURNSTILE_SECRET_KEY"],
                "response": token,
                "remoteip": request.remote_addr,
            },
            timeout=5,
        )
        data = resp.json()
        if data.get("success"):
            return True, None
        return False, "Güvenlik doğrulaması başarısız. Lütfen tekrar deneyin."
    except requests.RequestException:
        return False, "Güvenlik doğrulama servisine ulaşılamadı. Lütfen daha sonra tekrar deneyin."


def captcha_hatasi():
    """Form gönderiminde Turnstile token doğrulaması. Hata varsa mesaj döner."""
    token = request.form.get("cf-turnstile-response", "")
    ok, err = verify_turnstile(token)
    return None if ok else err
