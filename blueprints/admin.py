import os

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from extensions import db
from helpers import ai_tam_analiz
from models import Atik, Kaynak, Sikayet, User
from services.impact import il_kirilimi, kategori_kirilimi, platform_ozeti
from utils import cleanup_ilan_relations

admin_bp = Blueprint("admin", __name__)


def admin_required():
    if not current_user.is_authenticated or not current_user.is_admin:
        return False
    return True


@admin_bp.route("/admin")
@login_required
def admin_panel():
    if not admin_required():
        abort(404)

    return render_template(
        "admin.html",
        user_count=User.query.count(),
        kaynak_count=Kaynak.query.count(),
        atik_count=Atik.query.count(),
        etki_ozet=platform_ozeti(),
        etki_kategoriler=kategori_kirilimi(),
        etki_iller=il_kirilimi(),
        son_kaynaklar=Kaynak.query.order_by(Kaynak.id.desc()).limit(10).all(),
        son_atiklar=Atik.query.order_by(Atik.id.desc()).limit(10).all(),
        kullanicilar=User.query.order_by(User.id.desc()).limit(20).all(),
        sikayetler=Sikayet.query.order_by(Sikayet.id.desc()).limit(20).all(),
    )


@admin_bp.route("/admin/ilan_sil/<tur>/<int:id>", methods=["POST"])
@login_required
def admin_ilan_sil(tur, id):
    if not admin_required():
        abort(404)

    if tur == "kaynak":
        ilan = Kaynak.query.get_or_404(id)
        cleanup_ilan_relations(kaynak_id=ilan.id)
        db.session.delete(ilan)
        flash("Kaynak ilanı admin tarafından silindi.", "success")
    else:
        ilan = Atik.query.get_or_404(id)
        cleanup_ilan_relations(atik_id=ilan.id)
        db.session.delete(ilan)
        flash("Atık ilanı admin tarafından silindi.", "success")
    db.session.commit()
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/kullanici_admin/<int:user_id>", methods=["POST"])
@login_required
def admin_toggle_admin(user_id):
    if not admin_required():
        abort(404)

    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Kendi admin durumunuzu değiştiremezsiniz.", "warning")
        return redirect(url_for("admin.admin_panel"))

    user.is_admin = not user.is_admin
    db.session.commit()
    flash(f"{user.username} admin durumu güncellendi.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/sikayet_incele/<int:id>", methods=["POST"])
@login_required
def admin_sikayet_incele(id):
    if not admin_required():
        abort(404)

    sikayet = Sikayet.query.get_or_404(id)
    sikayet.durum = "İncelendi"
    db.session.commit()
    flash("Şikayet incelendi olarak işaretlendi.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/ai_test/<tur>")
@login_required
def ai_test(tur):
    if not admin_required():
        abort(404)

    test_resim = None
    if tur == "kaynak":
        kaynak = Kaynak.query.filter(Kaynak.resim != "default.jpg").first()
        if kaynak:
            test_resim = os.path.join(current_app.config["UPLOAD_FOLDER"], kaynak.resim)
    else:
        atik = Atik.query.filter(Atik.resim.isnot(None), Atik.resim != "default.jpg").first()
        if atik:
            test_resim = os.path.join(current_app.config["UPLOAD_FOLDER"], atik.resim)

    if not test_resim or not os.path.exists(test_resim):
        return jsonify({"hata": "Test için resim bulunamadı."})

    return jsonify(ai_tam_analiz(test_resim, tur=tur, aciklama="Test açıklama"))
