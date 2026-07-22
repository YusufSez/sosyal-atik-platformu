from sqlalchemy import and_, or_

from extensions import db
from models import Atik, Kaynak, Mesaj, User
from utils import ilan_erisilebilir_mi


def _conversation_filter(user_id: int, partner_id: int, kaynak_id, atik_id):
    return and_(
        or_(
            and_(Mesaj.sender_id == user_id, Mesaj.receiver_id == partner_id),
            and_(Mesaj.sender_id == partner_id, Mesaj.receiver_id == user_id),
        ),
        Mesaj.kaynak_id == kaynak_id,
        Mesaj.atik_id == atik_id,
    )


def _user_is_admin(user: User | None) -> bool:
    if not user:
        return False
    role = getattr(user, "role", None)
    if role in ("admin", "superadmin"):
        return True
    return bool(getattr(user, "is_admin", False))


def user_can_access_conversation(user_id: int, partner_id: int, kaynak_id: int, atik_id: int) -> bool:
    if partner_id == user_id:
        return False
    k_id = int(kaynak_id or 0)
    a_id = int(atik_id or 0)
    # Geçersiz anahtar: aynı anda iki ilan türü
    if k_id and a_id:
        return False
    partner = db.session.get(User, partner_id)
    if not partner:
        return False
    user = db.session.get(User, user_id)
    if not user:
        return False
    if _user_is_admin(user):
        return True

    k_id_db = k_id if k_id != 0 else None
    a_id_db = a_id if a_id != 0 else None
    exists = db.session.query(Mesaj.id).filter(
        _conversation_filter(user_id, partner_id, k_id_db, a_id_db)
    ).first()
    if exists is not None:
        return True

    # Yeni sohbet (önceki mesaj yok): yalnızca ilan sahibiyle iletişime izin ver.
    # İlan sahibi rastgele user_id ile sohbet açamaz (URL manipülasyonu / IDOR yüzeyi).
    # Sahip yanıtı, alıcının ilk mesajından sonra `exists` dalıyla zaten açılır.
    if k_id_db:
        kaynak = db.session.get(Kaynak, k_id_db)
        if (
            kaynak
            and ilan_erisilebilir_mi(kaynak, user)
            and partner_id == kaynak.user_id
        ):
            return True
    if a_id_db:
        atik = db.session.get(Atik, a_id_db)
        if (
            atik
            and ilan_erisilebilir_mi(atik, user)
            and partner_id == atik.user_id
        ):
            return True

    return False


def user_can_join_conversation(user_id: int, partner_id: int, kaynak_id: int, atik_id: int) -> bool:
    return user_can_access_conversation(user_id, partner_id, kaynak_id, atik_id)
