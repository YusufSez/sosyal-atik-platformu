import logging

from extensions import db
from models import Bildirim, User
from services.email import eposta_gonder

logger = logging.getLogger(__name__)


def _emit_bildirim_realtime(user_id: int) -> None:
    try:
        from socket_events import emit_notification_sync, emit_unread_count_updated

        emit_unread_count_updated(user_id)
        emit_notification_sync(user_id)
    except Exception:
        logger.exception("Bildirim socket senkronu başarısız user_id=%s", user_id)


def _send_bildirim_email(user_id: int, baslik: str, icerik: str) -> None:
    user = db.session.get(User, user_id)
    if user and user.email:
        try:
            eposta_gonder(user.email, baslik, icerik)
        except Exception:
            logger.exception("Bildirim e-postası gönderilemedi user_id=%s", user_id)


def bildirim_olustur(
    user_id,
    baslik,
    icerik,
    tur,
    link=None,
    *,
    mesaj_id=None,
    commit=True,
):
    if not user_id:
        return None
    bildirim = Bildirim(
        user_id=user_id,
        baslik=baslik,
        icerik=icerik,
        tur=tur,
        link=link,
        mesaj_id=mesaj_id,
    )
    db.session.add(bildirim)
    if commit:
        db.session.commit()
        _send_bildirim_email(user_id, baslik, icerik)
        _emit_bildirim_realtime(user_id)
    return bildirim


def bildirim_olustur_coklu(kayitlar: list[dict]) -> list[Bildirim]:
    """Tüm bildirimleri tek transaction ile oluşturur."""
    if not kayitlar:
        return []
    created = []
    for item in kayitlar:
        user_id = item.get("user_id")
        if not user_id:
            continue
        row = Bildirim(
            user_id=user_id,
            baslik=item["baslik"],
            icerik=item["icerik"],
            tur=item["tur"],
            link=item.get("link"),
            mesaj_id=item.get("mesaj_id"),
        )
        db.session.add(row)
        created.append(row)
    if not created:
        return []
    try:
        db.session.commit()
    except Exception:
        db.session.rollback()
        logger.exception("Toplu bildirim kaydı başarısız")
        raise
    for row in created:
        _send_bildirim_email(row.user_id, row.baslik, row.icerik)
        _emit_bildirim_realtime(row.user_id)
    return created
