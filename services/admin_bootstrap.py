"""İlk admin ataması ve ADMIN_EMAIL yapılandırması."""

import os

from extensions import db
from models import User


def bootstrap_admin_from_env() -> None:
    super_email = os.getenv("SUPERADMIN_EMAIL", "").strip().lower()
    if not super_email:
        # Geriye uyumluluk: SUPERADMIN_EMAIL tanımlı değilse ADMIN_EMAIL'i
        # superadmin kabul et.
        super_email = os.getenv("ADMIN_EMAIL", "").strip().lower()

    if not super_email:
        return

    user = User.query.filter(db.func.lower(User.email) == super_email).first()
    if not user:
        return

    # Role + is_admin senkronu
    user.role = "superadmin"
    user.is_admin = True
    db.session.commit()
