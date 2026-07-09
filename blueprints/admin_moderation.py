"""Admin AI moderasyon paneli — liste, detay, dashboard, aksiyonlar."""

from __future__ import annotations

import json
from datetime import datetime

from flask import Blueprint, abort, flash, jsonify, make_response, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import (
    MODERATION_STATUS_APPROVED,
    MODERATION_STATUS_PENDING_REVIEW,
    MODERATION_STATUS_REJECTED,
)
from decorators import admin_required
from extensions import db, limiter
from models import Atik, IlanModerasyonNot, Kaynak
from services.audit import log_admin_action
from services.ilan_moderation import ilan_moderasyon_alanlarini_uygula
from services.moderation_activity import activity_dict, activity_listesi
from services.moderation_admin import (
    dashboard_istatistikleri,
    ilan_detay_paketi,
    kategori_secenekleri,
    moderasyon_listesi,
)
from services.moderation_admin_actions import kaydet_moderasyon_aksiyonu
from services.moderation_analysis import analiz_gecmisi, guncel_analiz, yeniden_ai_analizi
from services.moderation_export import EXPORT_SCOPES, export_csv, export_excel, export_pdf
from services.moderation_timeline import timeline_ekle
from utils import sanitize_input

admin_moderation_bp = Blueprint("admin_moderation", __name__, url_prefix="/admin/moderasyon")


def _ilan_getir(tur: str, ilan_id: int):
    if tur == "kaynak":
        return Kaynak.query.get_or_404(ilan_id)
    if tur == "atik":
        return Atik.query.get_or_404(ilan_id)
    abort(400)


def _parse_filters() -> dict:
    filters = {
        "q": sanitize_input(request.args.get("q"), max_length=100) or "",
        "status": request.args.get("status") or "",
        "tur": request.args.get("tur") or "",
        "username": sanitize_input(request.args.get("username"), max_length=80) or "",
        "kategori": request.args.get("kategori") or "",
        "date_from": None,
        "date_to": None,
        "risk_min": None,
    }
    if request.args.get("risk_90"):
        filters["risk_min"] = 90
    elif request.args.get("risk_70"):
        filters["risk_min"] = 70
    for key in ("date_from", "date_to"):
        raw = request.args.get(key)
        if raw:
            try:
                filters[key] = datetime.strptime(raw, "%Y-%m-%d")
            except ValueError:
                pass
    return filters


@admin_moderation_bp.route("")
@admin_moderation_bp.route("/")
@login_required
@admin_required
def dashboard():
    return render_template(
        "admin_moderation/dashboard.html",
        stats=dashboard_istatistikleri(),
        title="AI Moderasyon Dashboard",
    )


@admin_moderation_bp.route("/activity")
@login_required
@admin_required
def activity_log():
    action = request.args.get("action") or None
    admin_id = request.args.get("admin_id", type=int)
    tur = request.args.get("tur") or None
    logs = [activity_dict(log) for log in activity_listesi(action=action, admin_id=admin_id, tur=tur)]
    return render_template(
        "admin_moderation/activity.html",
        logs=logs,
        filters={"action": action or "", "admin_id": admin_id, "tur": tur or ""},
        title="Moderasyon Activity Log",
    )


@admin_moderation_bp.route("/ilanlar")
@login_required
@admin_required
def ilan_listesi():
    filters = _parse_filters()
    page = request.args.get("page", 1, type=int)
    result = moderasyon_listesi(filters, page=page)
    return render_template(
        "admin_moderation/list.html",
        items=result.items,
        pagination=result,
        filters=filters,
        kategoriler=kategori_secenekleri(),
        statuses=[
            MODERATION_STATUS_PENDING_REVIEW,
            MODERATION_STATUS_APPROVED,
            MODERATION_STATUS_REJECTED,
        ],
        title="Moderasyon İlanları",
    )


@admin_moderation_bp.route("/ilan/<tur>/<int:ilan_id>")
@login_required
@admin_required
def ilan_detay(tur, ilan_id):
    paket = ilan_detay_paketi(tur, ilan_id)
    if not paket:
        abort(404)
    return render_template(
        "admin_moderation/detail.html",
        **paket,
        title=f"Moderasyon — {paket['ilan'].baslik}",
    )


@admin_moderation_bp.route("/onayla/<tur>/<int:ilan_id>", methods=["POST"])
@login_required
@admin_required
def onayla(tur, ilan_id):
    ilan = _ilan_getir(tur, ilan_id)
    onceki = ilan.moderation_status
    ilan.moderation_status = MODERATION_STATUS_APPROVED
    timeline_ekle(
        tur, ilan_id, "admin_approved", "Admin onayladı", admin_user_id=current_user.id
    )
    kaydet_moderasyon_aksiyonu(
        "approve",
        tur,
        ilan_id,
        current_user.id,
        admin_decision=MODERATION_STATUS_APPROVED,
        ilan_status_before=onceki,
        activity_note=ilan.baslik,
    )
    db.session.commit()
    log_admin_action("moderasyon_onay", target=f"{tur}:{ilan_id}", detail=ilan.baslik)
    flash("İlan onaylandı.", "success")
    return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))


@admin_moderation_bp.route("/reddet/<tur>/<int:ilan_id>", methods=["POST"])
@login_required
@admin_required
def reddet(tur, ilan_id):
    ilan = _ilan_getir(tur, ilan_id)
    onceki = ilan.moderation_status
    ilan.moderation_status = MODERATION_STATUS_REJECTED
    timeline_ekle(
        tur, ilan_id, "admin_rejected", "Admin reddetti", admin_user_id=current_user.id
    )
    kaydet_moderasyon_aksiyonu(
        "reject",
        tur,
        ilan_id,
        current_user.id,
        admin_decision=MODERATION_STATUS_REJECTED,
        ilan_status_before=onceki,
        activity_note=ilan.baslik,
    )
    db.session.commit()
    log_admin_action("moderasyon_red", target=f"{tur}:{ilan_id}", detail=ilan.baslik)
    flash("İlan reddedildi.", "warning")
    return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))


@admin_moderation_bp.route("/yeniden-analiz/<tur>/<int:ilan_id>", methods=["POST"])
@login_required
@admin_required
@limiter.limit("10 per hour")
def yeniden_analiz(tur, ilan_id):
    _ilan_getir(tur, ilan_id)
    try:
        ai_sonuc, kayit = yeniden_ai_analizi(tur, ilan_id, current_user.id)
        kaydet_moderasyon_aksiyonu(
            "reanalyze",
            tur,
            ilan_id,
            current_user.id,
            kaydet_karar=False,
            activity_note=f"v{kayit.analysis_version} risk={ai_sonuc.get('risk_skoru')}",
        )
        db.session.commit()
        log_admin_action(
            "moderasyon_reanalyze",
            target=f"{tur}:{ilan_id}",
            detail=f"v{kayit.analysis_version} risk={ai_sonuc.get('risk_skoru')}",
        )
        flash(
            f"Yeniden analiz tamamlandı (v{kayit.analysis_version}, "
            f"Risk: {ai_sonuc.get('risk_skoru')}/100).",
            "success",
        )
    except Exception as exc:
        db.session.rollback()
        flash(f"Yeniden analiz başarısız: {exc}", "danger")
    return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))


@admin_moderation_bp.route("/risk/<tur>/<int:ilan_id>", methods=["POST"])
@login_required
@admin_required
def risk_duzenle(tur, ilan_id):
    ilan = _ilan_getir(tur, ilan_id)
    try:
        yeni_risk = int(request.form.get("risk_skoru", ""))
        yeni_risk = max(0, min(100, yeni_risk))
    except (TypeError, ValueError):
        flash("Geçersiz risk skoru.", "danger")
        return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))

    eski = ilan.ai_risk_score
    onceki_status = ilan.moderation_status
    reason = sanitize_input(request.form.get("reason"), max_length=500) or "Admin manuel düzenleme"
    ilan.ai_risk_score = yeni_risk
    ai_sonuc = {
        "risk_skoru": yeni_risk,
        "final_risk": yeni_risk,
        "initial_risk": eski,
        "uygunsuz": False,
        "reason": reason,
    }
    ilan_moderasyon_alanlarini_uygula(ilan, ai_sonuc)
    timeline_ekle(
        tur,
        ilan_id,
        "admin_risk_override",
        f"Risk manuel düzenlendi: {eski} → {yeni_risk}",
        detail={"old": eski, "new": yeni_risk},
        admin_user_id=current_user.id,
    )
    kaydet_moderasyon_aksiyonu(
        "risk_override",
        tur,
        ilan_id,
        current_user.id,
        admin_decision=ilan.moderation_status,
        decision_reason=reason,
        ilan_status_before=onceki_status,
        activity_note=f"Risk {eski} → {yeni_risk}",
    )
    db.session.commit()
    log_admin_action(
        "moderasyon_risk_override",
        target=f"{tur}:{ilan_id}",
        old_value=str(eski),
        new_value=str(yeni_risk),
    )
    flash("Risk skoru güncellendi.", "success")
    return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))


@admin_moderation_bp.route("/not/<tur>/<int:ilan_id>", methods=["POST"])
@login_required
@admin_required
def not_ekle(tur, ilan_id):
    _ilan_getir(tur, ilan_id)
    note = sanitize_input(request.form.get("note"), max_length=2000)
    if not note:
        flash("Not boş olamaz.", "warning")
        return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))

    kayit = IlanModerasyonNot(
        tur=tur,
        kaynak_id=ilan_id if tur == "kaynak" else None,
        atik_id=ilan_id if tur == "atik" else None,
        admin_user_id=current_user.id,
        note=note,
    )
    db.session.add(kayit)
    timeline_ekle(
        tur, ilan_id, "admin_note", "Admin notu eklendi",
        detail={"note": note[:200]}, admin_user_id=current_user.id,
    )
    kaydet_moderasyon_aksiyonu(
        "note",
        tur,
        ilan_id,
        current_user.id,
        kaydet_karar=False,
        activity_note=note[:200],
    )
    db.session.commit()
    flash("Admin notu kaydedildi.", "success")
    return redirect(url_for("admin_moderation.ilan_detay", tur=tur, ilan_id=ilan_id))


@admin_moderation_bp.route("/json/<tur>/<int:ilan_id>")
@admin_moderation_bp.route("/json/<tur>/<int:ilan_id>/<int:version>")
@login_required
@admin_required
def ham_json(tur, ilan_id, version=None):
    """Admin-only ham AI JSON."""
    if version:
        analiz = next((a for a in analiz_gecmisi(tur, ilan_id) if a.analysis_version == version), None)
    else:
        analiz = guncel_analiz(tur, ilan_id)
    if not analiz:
        abort(404)
    try:
        data = json.loads(analiz.raw_json or "{}")
    except json.JSONDecodeError:
        data = {"raw": analiz.raw_json}
    return jsonify(data)


_MIME_TYPES = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "pdf": "application/pdf",
}


@admin_moderation_bp.route("/export/<scope>/<fmt>")
@login_required
@admin_required
@limiter.limit("20 per hour")
def export_veri(scope, fmt):
    """Moderasyon verilerini CSV / Excel / PDF olarak dışa aktarır."""
    if scope not in EXPORT_SCOPES:
        abort(400)
    if fmt == "csv":
        data, filename = export_csv(scope)
        mime = _MIME_TYPES["csv"]
    elif fmt in ("xlsx", "excel"):
        data, filename = export_excel(scope)
        mime = _MIME_TYPES["xlsx"]
    elif fmt == "pdf":
        data, filename = export_pdf(scope)
        mime = _MIME_TYPES["pdf"] if filename.endswith(".pdf") else "text/plain; charset=utf-8"
    else:
        abort(400)

    log_admin_action("moderasyon_export", target=f"{scope}:{fmt}", detail=filename)
    resp = make_response(data)
    resp.headers["Content-Type"] = mime
    resp.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
    return resp
