"""Şikayet moderasyonu ve yönetim logları."""

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import ADMIN_LOGS_PER_PAGE, BAN_DURATION_OPTIONS, SIKAYET_DURUMLARI, SIKAYET_TURLERI
from decorators import admin_required, is_super_admin, super_admin_required
from extensions import db
from models import AdminAuditLog, Sikayet
from services.audit import log_admin_action
from services.query_options import audit_listesi_options
from services.report_service import (
    build_report_detail_context,
    build_report_query,
    durum_badge_class,
    normalize_durum,
    paginate_reports,
    report_detail_options,
    sikayet_turu_label,
)
from services.user_moderation import (
    activate_user,
    apply_ban,
    can_superadmin_manage_user,
    clear_ban,
    deactivate_user,
    normalize_role,
    normalize_ban_reason,
    parse_ban_duration,
    soft_delete_user,
    toggle_admin_role,
)
from utils import sanitize_input, utc_now

admin_reports_bp = Blueprint("admin_reports", __name__)


def _report_or_404(report_id: int) -> Sikayet:
    return (
        Sikayet.query.options(*report_detail_options())
        .filter_by(id=report_id)
        .first_or_404()
    )


def _target_user_from_report(sikayet: Sikayet):
    return sikayet.reported_user


def _redirect_detail(report_id: int):
    return redirect(url_for("admin_reports.admin_report_detail", id=report_id))


@admin_reports_bp.route("/admin/reports")
@login_required
@admin_required
def admin_reports_list():
    filter_args = {k: v for k, v in request.args.items() if k != "page"}
    page = request.args.get("page", 1, type=int)
    pagination = paginate_reports(request.args, page)
    return render_template(
        "admin_reports.html",
        pagination=pagination,
        reports=pagination.items,
        durumlar=SIKAYET_DURUMLARI,
        turler=SIKAYET_TURLERI,
        filters=request.args,
        filter_args=filter_args,
        super_admin=is_super_admin(current_user),
        durum_badge_class=durum_badge_class,
        normalize_durum=normalize_durum,
        sikayet_turu_label=sikayet_turu_label,
    )


@admin_reports_bp.route("/admin/reports/search")
@login_required
@admin_required
def admin_reports_search():
    """Canlı arama için JSON sonuç."""
    page = request.args.get("page", 1, type=int)
    pagination = paginate_reports(request.args, page)
    items = []
    for s in pagination.items:
        items.append({
            "id": s.id,
            "reporter": s.user.username if s.user else "-",
            "reported": s.reported_user.username if s.reported_user else "-",
            "tur": sikayet_turu_label(s),
            "durum": normalize_durum(s.durum),
            "tarih": s.timestamp.isoformat() if s.timestamp else None,
            "detail_url": url_for("admin_reports.admin_report_detail", id=s.id),
        })
    return jsonify({
        "items": items,
        "page": pagination.page,
        "pages": pagination.pages,
        "total": pagination.total,
    })


@admin_reports_bp.route("/admin/report/<int:id>")
@login_required
@admin_required
def admin_report_detail(id: int):
    sikayet = _report_or_404(id)
    ctx = build_report_detail_context(sikayet)
    ctx["super_admin"] = is_super_admin(current_user)
    ctx["ban_durations"] = BAN_DURATION_OPTIONS
    ctx["durum_badge_class"] = durum_badge_class
    ctx["normalize_durum"] = normalize_durum
    return render_template("admin_report_detail.html", **ctx)


@admin_reports_bp.route("/admin/report/<int:id>/durum", methods=["POST"])
@login_required
@admin_required
def admin_report_change_status(id: int):
    sikayet = _report_or_404(id)
    new_durum = sanitize_input(request.form.get("durum"), max_length=50)
    if new_durum not in SIKAYET_DURUMLARI:
        flash("Geçersiz durum.", "danger")
        return _redirect_detail(id)

    old_durum = sikayet.durum
    sikayet.durum = new_durum
    db.session.commit()
    log_admin_action(
        "sikayet_durum",
        target=f"sikayet:{id}",
        detail=f"{old_durum} -> {new_durum}",
        old_value=old_durum,
        new_value=new_durum,
    )
    flash("Şikayet durumu güncellendi.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/mark-reviewed", methods=["POST"])
@login_required
@admin_required
def admin_report_mark_reviewed(id: int):
    sikayet = _report_or_404(id)
    sikayet.reviewer_id = current_user.id
    sikayet.reviewed_at = utc_now()
    if normalize_durum(sikayet.durum) == "Bekliyor":
        sikayet.durum = "İşlem Yapıldı"
    db.session.commit()
    log_admin_action(
        "sikayet_incele",
        target=f"sikayet:{id}",
        detail=sikayet.sebep,
        new_value="reviewed",
    )
    flash("Şikayet incelendi olarak işaretlendi.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/unmark-reviewed", methods=["POST"])
@login_required
@admin_required
def admin_report_unmark_reviewed(id: int):
    sikayet = _report_or_404(id)
    old_reviewer = sikayet.reviewer_id
    sikayet.reviewer_id = None
    sikayet.reviewed_at = None
    if normalize_durum(sikayet.durum) == "İşlem Yapıldı":
        sikayet.durum = "Bekliyor"
    db.session.commit()
    log_admin_action(
        "sikayet_incele_geri_al",
        target=f"sikayet:{id}",
        old_value=str(old_reviewer),
        new_value="unreviewed",
    )
    flash("İnceleme işareti kaldırıldı.", "info")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/user/ban", methods=["POST"])
@login_required
@super_admin_required
def admin_report_ban_user(id: int):
    sikayet = _report_or_404(id)
    target = _target_user_from_report(sikayet)
    if not target:
        flash("Şikayet edilen kullanıcı bulunamadı.", "warning")
        return _redirect_detail(id)

    if not can_superadmin_manage_user(current_user, target):
        abort(403)

    reason = normalize_ban_reason(sanitize_input(request.form.get("ban_reason"), max_length=500))
    if not reason:
        flash("Ban sebebi zorunludur.", "danger")
        return _redirect_detail(id)

    duration_key = sanitize_input(request.form.get("ban_duration"), max_length=20)
    duration_days = parse_ban_duration(duration_key)

    old = f"banned={target.is_banned}"
    apply_ban(target, reason, duration_days, banned_by_id=current_user.id)
    db.session.commit()

    log_admin_action(
        "user_ban",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"report:{id}",
        reason=reason,
        old_value=old,
        new_value=f"banned=True expires={duration_days}",
    )
    flash(f"{target.username} banlandı.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/user/unban", methods=["POST"])
@login_required
@super_admin_required
def admin_report_unban_user(id: int):
    sikayet = _report_or_404(id)
    target = _target_user_from_report(sikayet)
    if not target:
        flash("Şikayet edilen kullanıcı bulunamadı.", "warning")
        return _redirect_detail(id)

    if not can_superadmin_manage_user(current_user, target):
        abort(403)

    old = f"banned={target.is_banned}"
    clear_ban(target)
    db.session.commit()
    log_admin_action(
        "user_unban",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"report:{id}",
        old_value=old,
        new_value="banned=False",
    )
    flash(f"{target.username} banı kaldırıldı.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/user/toggle-admin", methods=["POST"])
@login_required
@super_admin_required
def admin_report_toggle_admin(id: int):
    sikayet = _report_or_404(id)
    target = _target_user_from_report(sikayet)
    if not target:
        flash("Şikayet edilen kullanıcı bulunamadı.", "warning")
        return _redirect_detail(id)

    if not can_superadmin_manage_user(current_user, target):
        abort(403)

    old_role, new_role = toggle_admin_role(target)
    db.session.commit()
    action = "admin_ver" if new_role == "admin" else "admin_kaldir"
    log_admin_action(
        action,
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"report:{id}",
        old_value=old_role,
        new_value=new_role,
    )
    flash(f"{target.username} rolü güncellendi: {new_role}", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/user/deactivate", methods=["POST"])
@login_required
@super_admin_required
def admin_report_deactivate_user(id: int):
    sikayet = _report_or_404(id)
    target = _target_user_from_report(sikayet)
    if not target:
        flash("Şikayet edilen kullanıcı bulunamadı.", "warning")
        return _redirect_detail(id)

    if not can_superadmin_manage_user(current_user, target):
        abort(403)

    old = str(target.is_deactivated)
    deactivate_user(target, actor_id=current_user.id)
    db.session.commit()
    log_admin_action(
        "user_deactivate",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"report:{id}",
        old_value=old,
        new_value="deactivated=True",
    )
    flash(f"{target.username} pasifleştirildi.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/user/activate", methods=["POST"])
@login_required
@super_admin_required
def admin_report_activate_user(id: int):
    sikayet = _report_or_404(id)
    target = _target_user_from_report(sikayet)
    if not target:
        flash("Şikayet edilen kullanıcı bulunamadı.", "warning")
        return _redirect_detail(id)

    if not can_superadmin_manage_user(current_user, target):
        abort(403)

    activate_user(target)
    db.session.commit()
    log_admin_action(
        "user_activate",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"report:{id}",
        new_value="deactivated=False",
    )
    flash(f"{target.username} tekrar aktifleştirildi.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/report/<int:id>/user/soft-delete", methods=["POST"])
@login_required
@super_admin_required
def admin_report_soft_delete_user(id: int):
    sikayet = _report_or_404(id)
    target = _target_user_from_report(sikayet)
    if not target:
        flash("Şikayet edilen kullanıcı bulunamadı.", "warning")
        return _redirect_detail(id)

    if not can_superadmin_manage_user(current_user, target):
        abort(403)

    reason = normalize_ban_reason(
        sanitize_input(request.form.get("ban_reason"), max_length=500) if request.form else None
    )
    if not reason:
        flash("Ban sebebi zorunludur.", "danger")
        return _redirect_detail(id)

    soft_delete_user(target, reason, banned_by_id=current_user.id)
    db.session.commit()
    log_admin_action(
        "user_soft_delete",
        target=f"user:{target.id}",
        target_user_id=target.id,
        detail=f"report:{id}",
        reason=reason,
        new_value="soft_deleted",
    )
    flash(f"{target.username} soft-delete uygulandı.", "success")
    return _redirect_detail(id)


@admin_reports_bp.route("/admin/logs")
@login_required
@admin_required
def admin_logs():
    page = request.args.get("page", 1, type=int)
    query = AdminAuditLog.query.options(*audit_listesi_options()).order_by(
        AdminAuditLog.id.desc()
    )
    action = (request.args.get("action") or "").strip()
    if action:
        query = query.filter(AdminAuditLog.action.ilike(f"%{action}%"))

    pagination = query.paginate(page=page, per_page=ADMIN_LOGS_PER_PAGE, error_out=False)
    return render_template(
        "admin_logs.html",
        pagination=pagination,
        logs=pagination.items,
        filters=request.args,
    )
