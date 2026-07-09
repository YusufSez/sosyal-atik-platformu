"""İlk superadmin ataması — yalnızca startup/CLI bootstrap ile."""

import os

from extensions import db
from models import User


def superadmin_target_email() -> str | None:
    """SUPERADMIN_EMAIL; yoksa geriye uyumluluk için ADMIN_EMAIL."""
    super_email = os.getenv("SUPERADMIN_EMAIL", "").strip().lower()
    if not super_email:
        super_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    return super_email or None


def bootstrap_admin_from_env() -> bool:
    """
    Env'deki e-posta ile eşleşen doğrulanmış mevcut kullanıcıyı superadmin yapar.

    - Kullanıcı kayıtlı ve email_verified olmalı
    - Zaten superadmin ise idempotent (değişiklik yok)
    - Başka bir superadmin varken ikinci superadmin oluşturmaz
  """
    super_email = superadmin_target_email()
    if not super_email:
        return False

    user = User.query.filter(db.func.lower(User.email) == super_email).first()
    if not user:
        return False

    if not getattr(user, "email_verified", False):
        return False

    if user.role == "superadmin" and user.is_admin:
        return True

    other_superadmin = (
        User.query.filter(User.role == "superadmin", User.id != user.id).first()
    )
    if other_superadmin:
        return False

    user.role = "superadmin"
    user.is_admin = True
    db.session.commit()
    return True
