"""İlk admin ataması ve ADMIN_EMAIL yapılandırması."""

import os

from extensions import db
from models import User


def bootstrap_admin_from_env() -> None:
    email = os.getenv("ADMIN_EMAIL", "").strip().lower()
    if not email:
        return

    user = User.query.filter(db.func.lower(User.email) == email).first()
    if user and not user.is_admin:
        user.is_admin = True
        db.session.commit()
