from flask import Blueprint, abort, jsonify, redirect, render_template, url_for
from flask_login import current_user

from sqlalchemy import or_, text
from sqlalchemy.orm import selectinload

from content.kurumsal import KURUMSAL_SAYFALAR, SITE_HARITASI_GRUPLARI
from extensions import db
from models import Atik, Kaynak, User
from services.impact import platform_ozeti
from services.recommendations import kullanici_onerileri

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@main_bp.route("/anasayfa")
def anasayfa():
    kaynaklar = Kaynak.query.options(selectinload(Kaynak.fotograflar)).filter(
        or_(Kaynak.ilan_durumu == "Aktif", Kaynak.ilan_durumu.is_(None))
    ).order_by(Kaynak.id.desc()).limit(8).all()
    stats = {
        "kullanici": User.query.count(),
        "kaynak": Kaynak.query.count(),
        "atik": Atik.query.count(),
        "teslim": (
            Kaynak.query.filter_by(ilan_durumu="Teslim Edildi").count()
            + Atik.query.filter_by(ilan_durumu="Teslim Edildi").count()
        ),
    }
    etki = platform_ozeti()
    oneriler_kaynak = []
    oneriler_atik = []
    if current_user.is_authenticated:
        oneriler_kaynak = kullanici_onerileri(current_user, "kaynak", limit=4)
        oneriler_atik = kullanici_onerileri(current_user, "atik", limit=4)
    return render_template(
        "home.html",
        kaynaklar=kaynaklar,
        stats=stats,
        etki=etki,
        oneriler_kaynak=oneriler_kaynak,
        oneriler_atik=oneriler_atik,
        title="Anasayfa",
    )


@main_bp.route("/health")
def health():
    try:
        db.session.execute(text("SELECT 1"))
        return {"status": "ok", "database": "up"}, 200
    except Exception:
        return {"status": "degraded", "database": "down"}, 503


@main_bp.route("/kurumsal/<slug>")
def kurumsal_sayfa(slug):
    sayfa = KURUMSAL_SAYFALAR.get(slug)
    if not sayfa:
        abort(404)
    return render_template(
        "kurumsal/sayfa.html",
        sayfa=sayfa,
        slug=slug,
        title=sayfa["title"],
    )


@main_bp.route("/kurumsal/site-haritasi")
def site_haritasi():
    return render_template(
        "kurumsal/site_haritasi.html",
        gruplar=SITE_HARITASI_GRUPLARI,
        title="Site Haritası",
    )


@main_bp.route("/kurumsal/iletisim")
def iletisim():
    return render_template("kurumsal/iletisim.html", title="İletişim")


@main_bp.route("/gizlilik")
def gizlilik():
    return redirect(url_for("main.kurumsal_sayfa", slug="gizlilik-kvkk"))


@main_bp.route("/kullanim-kosullari")
def kullanim_kosullari():
    return redirect(url_for("main.kurumsal_sayfa", slug="kullanim-kosullari"))
