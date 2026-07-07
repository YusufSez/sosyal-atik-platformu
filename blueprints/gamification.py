from flask import Blueprint, render_template
from flask_login import current_user, login_required

from services.gamification import (
    kullanici_rozet_listesi,
    kullanici_siralama,
    liderlik_tablosu,
    seviye_hesapla,
)

gamification_bp = Blueprint("gamification", __name__)


@gamification_bp.route("/liderlik-tablosu")
def liderlik():
    tablo = liderlik_tablosu(limit=50)
    benim_sira = None
    benim_seviye = None
    if current_user.is_authenticated:
        benim_sira = kullanici_siralama(current_user.id)
        benim_seviye = seviye_hesapla(current_user.xp)
    return render_template(
        "gamification/liderlik.html",
        tablo=tablo,
        benim_sira=benim_sira,
        benim_seviye=benim_seviye,
        title="Liderlik Tablosu",
    )


@gamification_bp.route("/rozetlerim")
@login_required
def rozetlerim():
    return render_template(
        "gamification/rozetler.html",
        rozetler=kullanici_rozet_listesi(current_user),
        seviye=seviye_hesapla(current_user.xp),
        title="Rozetlerim",
    )
