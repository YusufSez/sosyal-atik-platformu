import os

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, url_for
from flask_login import current_user, login_required

from decorators import admin_required, is_super_admin, super_admin_required
from extensions import db, limiter
from helpers import ai_tam_analiz
from models import AdminAuditLog, Atik, Kaynak, Sikayet, User
from services.audit import log_admin_action
from services.impact import il_kirilimi, kategori_kirilimi, platform_ozeti
from services.query_options import audit_listesi_options, sikayet_listesi_options
from utils import cleanup_ilan_relations

admin_bp = Blueprint("admin", __name__)


@admin_bp.route("/admin")
@login_required
@admin_required
def admin_panel():
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
        sikayetler=Sikayet.query.options(*sikayet_listesi_options()).order_by(Sikayet.id.desc()).limit(20).all(),
        audit_kayitlari=AdminAuditLog.query.options(*audit_listesi_options()).order_by(AdminAuditLog.id.desc()).limit(30).all(),
        super_admin=is_super_admin(current_user),
    )


@admin_bp.route("/admin/ilan_sil/<tur>/<int:id>", methods=["POST"])
@login_required
@admin_required
def admin_ilan_sil(tur, id):
    if tur == "kaynak":
        ilan = Kaynak.query.get_or_404(id)
        baslik = ilan.baslik
        cleanup_ilan_relations(kaynak_id=ilan.id)
        db.session.delete(ilan)
        db.session.commit()
        log_admin_action("ilan_sil", target=f"kaynak:{id}", detail=baslik)
        flash("Kaynak ilanı admin tarafından silindi.", "success")
    elif tur == "atik":
        ilan = Atik.query.get_or_404(id)
        baslik = ilan.baslik
        cleanup_ilan_relations(atik_id=ilan.id)
        db.session.delete(ilan)
        db.session.commit()
        log_admin_action("ilan_sil", target=f"atik:{id}", detail=baslik)
        flash("Atık ilanı admin tarafından silindi.", "success")
    else:
        abort(400)
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/kullanici_admin/<int:user_id>", methods=["POST"])
@login_required
@super_admin_required
def admin_toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Kendi admin durumunuzu değiştiremezsiniz.", "warning")
        return redirect(url_for("admin.admin_panel"))

    user.is_admin = not user.is_admin
    db.session.commit()
    log_admin_action(
        "admin_toggle",
        target=f"user:{user.id}",
        detail=f"{user.email} -> is_admin={user.is_admin}",
    )
    flash(f"{user.username} admin durumu güncellendi.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/sikayet_incele/<int:id>", methods=["POST"])
@login_required
@admin_required
def admin_sikayet_incele(id):
    sikayet = Sikayet.query.get_or_404(id)
    sikayet.durum = "İncelendi"
    db.session.commit()
    log_admin_action("sikayet_incele", target=f"sikayet:{id}", detail=sikayet.sebep)
    flash("Şikayet incelendi olarak işaretlendi.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/ai_test/<tur>", methods=["GET"])
@login_required
@admin_required
@limiter.limit("5 per hour")
def ai_test(tur):
    if tur not in ("kaynak", "atik"):
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
