from flask import Blueprint, render_template
from flask_login import current_user, login_required

from constants import ETKI_KATSAYILARI_ATIK, ETKI_KATSAYILARI_KAYNAK, HESAPLAMA_VERSIYONU
from services.impact import aylik_kirilim, kullanici_ozeti, kullanici_son_teslimler, platform_ozeti

impact_bp = Blueprint("impact", __name__)


@impact_bp.route("/etki-panelim")
@login_required
def etki_panelim():
    ozet = kullanici_ozeti(current_user.id)
    son_teslimler = kullanici_son_teslimler(current_user.id, limit=10)
    aylik = aylik_kirilim(user_id=current_user.id)
    return render_template(
        "etki_panelim.html",
        ozet=ozet,
        son_teslimler=son_teslimler,
        aylik=aylik,
        title="Çevresel Etki Panelim",
    )


@impact_bp.route("/cevresel-etki-metodolojisi")
def metodoloji():
    return render_template(
        "etki_metodoloji.html",
        kaynak_katsayilari=ETKI_KATSAYILARI_KAYNAK,
        atik_katsayilari=ETKI_KATSAYILARI_ATIK,
        versiyon=HESAPLAMA_VERSIYONU,
        platform_ozet=platform_ozeti(),
        title="Çevresel Etki Metodolojisi",
    )
