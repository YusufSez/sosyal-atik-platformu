from flask import Blueprint, abort, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from app_bootstrap.health import database_health_response
from services.ilan_moderation import public_ilan_base_filter
from sqlalchemy.orm import selectinload

from content.kurumsal import KURUMSAL_SAYFALAR, SITE_HARITASI_GRUPLARI
from models import Atik, Kaynak
from services.impact import platform_ozeti
from services.recommendations import kullanici_onerileri
from services.stats_queries import homepage_stats

main_bp = Blueprint("main", __name__)


@main_bp.route("/")
@main_bp.route("/anasayfa")
def anasayfa():
    kaynaklar = public_ilan_base_filter(
        Kaynak.query.options(selectinload(Kaynak.fotograflar)), Kaynak
    ).order_by(Kaynak.id.desc()).limit(8).all()
    stats = homepage_stats()
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


@main_bp.route("/socket-test")
@login_required
def socket_test():
    return render_template("socket_test.html", title="SocketIO Test")


@main_bp.route("/favicon.ico")
def favicon():
    return redirect(url_for("static", filename="vendor/leaflet/1.9.4/images/marker-icon.png"), code=302)


@main_bp.route("/health")
def health():
    return database_health_response()


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


@main_bp.route("/sitemap.xml")
def sitemap_xml():
    from flask import Response

    from services.sitemap import render_sitemap_xml

    xml = render_sitemap_xml()
    return Response(xml, mimetype="application/xml")


@main_bp.route("/robots.txt")
def robots_txt():
    from flask import Response

    from services.sitemap import render_robots_txt

    return Response(render_robots_txt(), mimetype="text/plain")
