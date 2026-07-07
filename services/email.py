"""Brevo SMTP veya REST API ile HTML e-posta gönderimi."""

import re
import smtplib

import requests
from flask import current_app, render_template
from flask_mail import Message

from extensions import mail
from services.email_links import absolute_url_for


def mail_configured() -> bool:
    return bool(
        current_app.config.get("MAIL_SERVER")
        and current_app.config.get("MAIL_USERNAME")
        and current_app.config.get("MAIL_PASSWORD")
    )


def _parse_sender(sender: str) -> dict:
    match = re.match(r"^(.+?)\s*<([^>]+)>$", (sender or "").strip())
    if match:
        return {"name": match.group(1).strip(), "email": match.group(2).strip()}
    return {"name": current_app.config.get("SITE_NAME", "AtıkPort"), "email": sender}


def _brevo_api_gonder(alici: str, konu: str, html_icerik: str, metin_icerik: str) -> bool:
    api_key = current_app.config.get("BREVO_API_KEY", "").strip()
    if not api_key:
        return False

    sender_raw = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config.get("MAIL_USERNAME", "")
    payload = {
        "sender": _parse_sender(sender_raw),
        "to": [{"email": alici}],
        "subject": konu,
        "htmlContent": html_icerik,
        "textContent": metin_icerik,
    }
    try:
        response = requests.post(
            "https://api.brevo.com/v3/smtp/email",
            json=payload,
            headers={"api-key": api_key, "accept": "application/json"},
            timeout=15,
        )
        if response.status_code in (200, 201):
            return True
        current_app.logger.error(
            "Brevo API hatası: status=%s body=%s",
            response.status_code,
            response.text[:300],
        )
        return False
    except requests.RequestException as exc:
        current_app.logger.error("Brevo API bağlantı hatası: %s", exc)
        return False


def eposta_gonder(alici: str, konu: str, html_icerik: str, metin_icerik: str | None = None) -> bool:
    if current_app.config.get("MAIL_SUPPRESS_SEND"):
        current_app.logger.info("E-posta (test modu): alici=%s konu=%s", alici, konu)
        return True

    plain = metin_icerik or _html_to_plain(html_icerik)

    if current_app.config.get("BREVO_API_KEY", "").strip():
        if _brevo_api_gonder(alici, konu, html_icerik, plain):
            return True
        if not mail_configured():
            return False

    if not mail_configured():
        current_app.logger.warning(
            "E-posta gönderilemedi (yapılandırma yok): alici=%s konu=%s",
            alici,
            konu,
        )
        return False

    sender = current_app.config.get("MAIL_DEFAULT_SENDER") or current_app.config["MAIL_USERNAME"]
    msg = Message(
        subject=konu,
        recipients=[alici],
        html=html_icerik,
        body=plain,
        sender=sender,
    )
    try:
        mail.send(msg)
        return True
    except smtplib.SMTPException as exc:
        current_app.logger.error(
            "E-posta gönderilemedi (SMTP): alici=%s konu=%s hata=%s",
            alici,
            konu,
            exc,
        )
        return False
    except Exception:
        current_app.logger.exception("E-posta gönderilemedi: alici=%s konu=%s", alici, konu)
        return False


def _html_to_plain(html: str) -> str:
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def dogrulama_epostasi_gonder(user, token: str) -> bool:
    link = absolute_url_for("auth.eposta_dogrula_onay", token=token)
    site_adi = current_app.config.get("SITE_NAME", "AI Tabanlı Atık ve Kaynak Paylaşım Platformu")
    saat = current_app.config.get("EMAIL_TOKEN_MAX_AGE", 86400) // 3600
    html = render_template(
        "email/dogrulama.html",
        user=user,
        link=link,
        site_adi=site_adi,
        gecerlilik_saat=saat,
    )
    return eposta_gonder(
        user.email,
        f"{site_adi} — E-posta Doğrulama",
        html,
        (
            f"Merhaba {user.username},\n\n"
            f"{site_adi}'na hoş geldiniz.\n\n"
            f"Hesabınızı doğrulamak için bağlantıya tıklayın:\n{link}\n\n"
            f"Bu bağlantı {saat} saat boyunca geçerlidir."
        ),
    )


def sifre_sifirlama_epostasi_gonder(user, token: str) -> bool:
    link = absolute_url_for("auth.sifre_sifirla", token=token)
    site_adi = current_app.config.get("SITE_NAME", "AI Tabanlı Atık ve Paylaşım Platformu")
    saat = current_app.config.get("EMAIL_TOKEN_MAX_AGE", 86400) // 3600
    html = render_template(
        "email/sifre_sifirla.html",
        user=user,
        link=link,
        site_adi=site_adi,
        gecerlilik_saat=saat,
    )
    return eposta_gonder(
        user.email,
        f"{site_adi} — Şifre Sıfırlama",
        html,
        (
            f"Merhaba {user.username},\n\n"
            f"Şifrenizi sıfırlamak için bağlantıya tıklayın:\n{link}\n\n"
            f"Bu bağlantı {saat} saat boyunca geçerlidir.\n"
            "Bu talebi siz yapmadıysanız bu e-postayı yok sayın."
        ),
    )
