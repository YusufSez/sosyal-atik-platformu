from extensions import db
from models import Bildirim, User
from services.email import eposta_gonder


def bildirim_olustur(user_id, baslik, icerik, tur, link=None):
    if not user_id:
        return
    bildirim = Bildirim(
        user_id=user_id,
        baslik=baslik,
        icerik=icerik,
        tur=tur,
        link=link,
    )
    db.session.add(bildirim)
    db.session.commit()

    user = db.session.get(User, user_id)
    if user and user.email:
        eposta_gonder(user.email, baslik, icerik)
