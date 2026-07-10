import html
import re

import bleach


def sanitize_input(text, max_length=None):
    """Metni temizler; HTML etiketlerini kaldırır (XSS önlemi)."""
    if not text:
        return ""
    text = bleach.clean(str(text), tags=[], attributes={}, strip=True)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = " ".join(text.split()).strip()
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return text


def unescape_stored_text(text):
    """Eski kayıtlardaki HTML-escape edilmiş metinleri gösterim için düzeltir."""
    if not text:
        return ""
    if "&lt;" in text or "&gt;" in text or "&amp;" in text:
        return html.unescape(text)
    return text


def validate_password(password):
    if len(password) < 8:
        return False, "Şifre en az 8 karakter olmalıdır"
    if not any(c.isupper() for c in password):
        return False, "Şifre en az 1 büyük harf içermelidir"
    if not any(c.islower() for c in password):
        return False, "Şifre en az 1 küçük harf içermelidir"
    if not any(c.isdigit() for c in password):
        return False, "Şifre en az 1 rakam içermelidir"
    return True, "Şifre güvenli"


def ilan_erisilebilir_mi(ilan, user=None):
    mod_status = getattr(ilan, "moderation_status", None) or "approved"
    if mod_status == "rejected":
        if user and getattr(user, "is_authenticated", False):
            if ilan.user_id == user.id or getattr(user, "is_admin", False):
                return True
        return False
    durum = getattr(ilan, "ilan_durumu", None) or "Aktif"
    if durum == "Aktif":
        return True
    if user and getattr(user, "is_authenticated", False):
        if ilan.user_id == user.id or getattr(user, "is_admin", False):
            return True
    return False
