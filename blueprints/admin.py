import os

from flask import Blueprint, abort, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import MODERATION_STATUS_APPROVED, MODERATION_STATUS_PENDING_REVIEW, MODERATION_STATUS_REJECTED, DESTEK_DURUMLARI
from decorators import admin_required, is_super_admin, super_admin_required
from extensions import db, limiter
from helpers import ai_tam_analiz
from models import AdminAuditLog, Atik, DestekDurumGecmisi, DestekTalebi, Kaynak, Sikayet, User
from sqlalchemy.orm import joinedload
from services.audit import log_admin_action
from services.impact import il_kirilimi, kategori_kirilimi, platform_ozeti
from services.query_options import audit_listesi_options, sikayet_listesi_options
from services.admin_user_detail import build_admin_user_detail
from services.admin_user_edit import (
    UserEditError,
    apply_admin_user_edit,
    can_deactivate_user_in_admin_edit,
    find_registered_user_by_email,
    parse_admin_user_edit_form,
)
from services.support_tickets import kategori_etiketi, record_support_status_change
from services.user_moderation import apply_ban, clear_ban, normalize_ban_reason, parse_ban_duration
from utils import cleanup_ilan_relations, resolve_item_picture_path, sanitize_input, utc_now

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
        inceleme_kaynaklar=Kaynak.query.filter_by(moderation_status=MODERATION_STATUS_PENDING_REVIEW)
        .order_by(Kaynak.id.desc()).limit(20).all(),
        inceleme_atiklar=Atik.query.filter_by(moderation_status=MODERATION_STATUS_PENDING_REVIEW)
        .order_by(Atik.id.desc()).limit(20).all(),
        kullanicilar=User.query.order_by(User.id.desc()).limit(20).all(),
        sikayetler=Sikayet.query.options(*sikayet_listesi_options()).order_by(Sikayet.id.desc()).limit(20).all(),
        audit_kayitlari=AdminAuditLog.query.options(*audit_listesi_options()).order_by(AdminAuditLog.id.desc()).limit(30).all(),
        super_admin=is_super_admin(current_user),
    )


@admin_bp.route("/admin/users")
@login_required
@super_admin_required
def admin_users():
    # Rol/ban işlemleri sadece süper admin tarafında yapılır.
    users = User.query.order_by(User.id.desc()).all()
    return render_template("admin_users.html", users=users)


@admin_bp.route("/admin/users/<int:user_id>")
@login_required
@super_admin_required
def admin_user_detail(user_id: int):
    user = User.query.get_or_404(user_id)
    detail = build_admin_user_detail(user)
    detail["can_edit"] = is_super_admin(current_user)
    return render_template("admin_user_detail.html", **detail)


@admin_bp.route("/admin/users/<int:user_id>/edit", methods=["GET", "POST"])
@login_required
@super_admin_required
def admin_user_edit(user_id: int):
    user = User.query.get_or_404(user_id)

    json_path = os.path.join(
        os.path.dirname(os.path.dirname(__file__)), "static", "data", "il-ilce-list.json"
    )
    with open(json_path, encoding="utf-8") as f:
        import json

        data = json.load(f)
    iller = {il["name"]: [d["name"] for d in il["districts"]] for il in data}

    if request.method == "POST":
        try:
            form_data = parse_admin_user_edit_form(request.form, request.files)
            changes = apply_admin_user_edit(
                user,
                form_data,
                actor_id=current_user.id,
            )
            if changes:
                flash("Kullanıcı bilgileri güncellendi.", "success")
            else:
                flash("Değişiklik yapılmadı.", "info")
            return redirect(url_for("admin.admin_user_detail", user_id=user.id))
        except UserEditError as exc:
            flash(exc.message, "danger")
        except Exception:
            db.session.rollback()
            flash("Güncelleme başarısız oldu.", "danger")

    return render_template(
        "admin_user_edit.html",
        user=user,
        iller=iller,
        can_deactivate=can_deactivate_user_in_admin_edit(
            user,
            actor_id=current_user.id,
        ),
        editing_self=user.id == current_user.id,
    )


@admin_bp.route("/admin/users/ban/<int:user_id>", methods=["POST"])
@login_required
@super_admin_required
def admin_ban_user(user_id: int):
    target = User.query.get_or_404(user_id)

    if target.id == current_user.id:
        flash("Kendi hesabınızı banlayamazsınız.", "warning")
        return redirect(url_for("admin.admin_users"))

    if is_super_admin(target):
        abort(403)

    reason = normalize_ban_reason(
        sanitize_input(request.form.get("ban_reason"), max_length=500) if request.form else None
    )
    if not reason:
        flash("Ban sebebi zorunludur.", "danger")
        from utils import safe_redirect_url

        return redirect(safe_redirect_url(request.referrer, "admin.admin_users"))

    duration_days = parse_ban_duration(
        sanitize_input(request.form.get("ban_duration"), max_length=20) if request.form else None
    )

    apply_ban(target, reason, duration_days, banned_by_id=current_user.id)
    db.session.commit()

    log_admin_action(
        "user_ban",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"{target.email} reason={reason or ''}",
        reason=reason,
        new_value=f"expires={duration_days}",
    )
    flash(f"{target.username} banlandı.", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/unban/<int:user_id>", methods=["POST"])
@login_required
@super_admin_required
def admin_unban_user(user_id: int):
    target = User.query.get_or_404(user_id)

    if target.id == current_user.id:
        flash("Kendi hesabınızı unbanlayamazsınız.", "warning")
        return redirect(url_for("admin.admin_users"))

    if is_super_admin(target):
        abort(403)

    clear_ban(target)
    db.session.commit()

    log_admin_action(
        "user_unban",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"{target.email}",
    )
    flash(f"{target.username} ban kaldırıldı.", "success")
    return redirect(url_for("admin.admin_users"))


@admin_bp.route("/admin/users/soft-delete/<int:user_id>", methods=["POST"])
@login_required
@super_admin_required
def admin_soft_delete_user(user_id: int):
    # "Sil" işlemi hard-delete yerine soft-ban olarak uygulanır.
    target = User.query.get_or_404(user_id)

    if target.id == current_user.id:
        flash("Kendi hesabınızı silemezsiniz.", "warning")
        return redirect(url_for("admin.admin_users"))

    if is_super_admin(target):
        abort(403)

    reason = normalize_ban_reason(
        sanitize_input(request.form.get("ban_reason"), max_length=500) if request.form else None
    )
    if not reason:
        flash("Silme (soft-ban) için sebep zorunludur.", "danger")
        from utils import safe_redirect_url

        return redirect(safe_redirect_url(request.referrer, "admin.admin_users"))

    apply_ban(target, reason, None, banned_by_id=current_user.id)
    db.session.commit()

    log_admin_action(
        "user_soft_delete",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"{target.email} reason={reason or ''}",
        reason=reason,
    )
    flash(f"{target.username} silindi (soft-ban).", "success")
    return redirect(url_for("admin.admin_users"))


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


@admin_bp.route("/admin/moderasyon_onayla/<tur>/<int:id>", methods=["POST"])
@login_required
@admin_required
def admin_moderasyon_onayla(tur, id):
    if tur == "kaynak":
        ilan = Kaynak.query.get_or_404(id)
    elif tur == "atik":
        ilan = Atik.query.get_or_404(id)
    else:
        abort(400)

    ilan.moderation_status = MODERATION_STATUS_APPROVED
    db.session.commit()
    log_admin_action("moderasyon_onay", target=f"{tur}:{id}", detail=ilan.baslik)
    flash("İlan moderasyonu onaylandı.", "success")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/moderasyon_reddet/<tur>/<int:id>", methods=["POST"])
@login_required
@admin_required
def admin_moderasyon_reddet(tur, id):
    if tur == "kaynak":
        ilan = Kaynak.query.get_or_404(id)
    elif tur == "atik":
        ilan = Atik.query.get_or_404(id)
    else:
        abort(400)

    ilan.moderation_status = MODERATION_STATUS_REJECTED
    db.session.commit()
    log_admin_action("moderasyon_red", target=f"{tur}:{id}", detail=ilan.baslik)
    flash("İlan moderasyonu reddedildi ve yayından kaldırıldı.", "warning")
    return redirect(url_for("admin.admin_panel"))


@admin_bp.route("/admin/kullanici_admin/<int:user_id>", methods=["POST"])
@login_required
@super_admin_required
def admin_toggle_admin(user_id):
    user = User.query.get_or_404(user_id)
    if user.id == current_user.id:
        flash("Kendi admin durumunuzu değiştiremezsiniz.", "warning")
        return redirect(url_for("admin.admin_panel"))

    # Süper admin başka süper admin'i yönetemez.
    if is_super_admin(user):
        abort(403)

    # role + is_admin senkronu
    if user.is_admin:
        user.is_admin = False
        user.role = "user"
    else:
        user.is_admin = True
        user.role = "admin"
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
    """Geriye uyumluluk: eski admin panel butonu."""
    sikayet = Sikayet.query.get_or_404(id)
    sikayet.reviewer_id = current_user.id
    sikayet.reviewed_at = utc_now()
    if sikayet.durum in ("Beklemede", "Bekliyor"):
        sikayet.durum = "İşlem Yapıldı"
    db.session.commit()
    log_admin_action("sikayet_incele", target=f"sikayet:{id}", detail=sikayet.sebep, new_value="reviewed")
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
            try:
                test_resim = resolve_item_picture_path(kaynak.resim)
            except ValueError:
                test_resim = None
    else:
        atik = Atik.query.filter(Atik.resim.isnot(None), Atik.resim != "default.jpg").first()
        if atik:
            try:
                test_resim = resolve_item_picture_path(atik.resim)
            except ValueError:
                test_resim = None

    if not test_resim or not os.path.exists(test_resim):
        return jsonify({"hata": "Test için resim bulunamadı."})

    return jsonify(ai_tam_analiz(test_resim, tur=tur, aciklama="Test açıklama"))


@admin_bp.route("/admin/destek")
@login_required
@admin_required
def admin_destek_list():
    talepler = (
        DestekTalebi.query.options(joinedload(DestekTalebi.user))
        .order_by(DestekTalebi.id.desc())
        .limit(100)
        .all()
    )
    return render_template(
        "admin_destek.html",
        talepler=talepler,
        durumlar=DESTEK_DURUMLARI,
        kategori_etiketi=kategori_etiketi,
    )


@admin_bp.route("/admin/destek/<int:talep_id>", methods=["GET", "POST"])
@login_required
@admin_required
def admin_destek_detail(talep_id: int):
    talep = (
        DestekTalebi.query.options(
            joinedload(DestekTalebi.user),
            joinedload(DestekTalebi.reviewer),
            joinedload(DestekTalebi.durum_gecmisi).joinedload(DestekDurumGecmisi.admin),
        )
        .get_or_404(talep_id)
    )
    matched_user = None
    if talep.is_guest and talep.guest_email:
        matched_user = find_registered_user_by_email(talep.guest_email)

    if request.method == "POST":
        durum = sanitize_input(request.form.get("durum"), max_length=30)
        admin_not = sanitize_input(request.form.get("admin_not"), max_length=5000)
        eski_durum = talep.durum
        if durum in DESTEK_DURUMLARI:
            talep.durum = durum
        if admin_not is not None:
            talep.admin_not = admin_not
        talep.reviewer_id = current_user.id
        talep.updated_at = utc_now()
        record_support_status_change(
            talep,
            eski_durum=eski_durum,
            yeni_durum=talep.durum,
            admin_id=current_user.id,
            not_metni=admin_not,
        )
        db.session.commit()
        log_admin_action(
            "destek_guncelle",
            target=f"destek:{talep.id}",
            target_user_id=talep.user_id,
            detail=f"durum={talep.durum}",
            old_value=eski_durum,
            new_value=talep.durum,
        )
        flash("Destek talebi güncellendi.", "success")
        return redirect(url_for("admin.admin_destek_detail", talep_id=talep.id))

    return render_template(
        "admin_destek_detail.html",
        talep=talep,
        durumlar=DESTEK_DURUMLARI,
        matched_user=matched_user,
        kategori_etiketi=kategori_etiketi,
    )
