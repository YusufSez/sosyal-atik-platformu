"""Destek ekleri erişim ve kayıt yardımcıları."""

from __future__ import annotations

import logging
import os

from werkzeug.utils import secure_filename

from services.user_moderation import normalize_role
from utils import resolve_support_attachment_path, save_support_attachment

logger = logging.getLogger(__name__)


def is_support_admin(user) -> bool:
    if not user or not getattr(user, "is_authenticated", False):
        return False
    role = normalize_role(user)
    return bool(getattr(user, "is_admin", False)) or role in ("admin", "superadmin")


def can_access_support_attachment(talep, user) -> bool:
    if not talep or not talep.ek_resim:
        return False
    if not user or not getattr(user, "is_authenticated", False):
        return False
    if talep.user_id == user.id:
        return True
    return is_support_admin(user)


def store_support_image(file_storage) -> tuple[str, str]:
    """
    Görseli güvenli pipeline ile kaydeder.
    Dönüş: (stored_filename, original_filename)
  """
    if not file_storage or not file_storage.filename:
        raise ValueError("Dosya seçilmedi")
    original = secure_filename(file_storage.filename) or "ek.jpg"
    stored = save_support_attachment(file_storage)
    return stored, original


def attachment_file_path(stored_filename: str) -> str:
    return resolve_support_attachment_path(stored_filename)


def attachment_exists(stored_filename: str) -> bool:
    try:
        path = attachment_file_path(stored_filename)
    except ValueError:
        return False
    return os.path.isfile(path)
