"""Bakanlık paneli — ROLE_MINISTRY (tüm belediyeleri görür)."""

from flask import Blueprint, jsonify, render_template, request, send_file
from flask_login import login_required

from decorators import ministry_required
from services.ministry_analytics import (
    ministry_drilldown_options,
    ministry_kpi,
    ministry_map_data,
    ministry_national_center,
    ministry_statistics,
)
from constants import MUNICIPALITY_CATEGORY_GROUPS
from services.sustainability_ai import generate_sustainability_suggestions
from services.sustainability_pdf import export_sustainability_pdf
from services.sustainability_scoring import sustainability_dashboard


admin_ministry_bp = Blueprint("admin_ministry", __name__, url_prefix="/minister")


def _filters():
    return {
        "il": request.args.get("il") or None,
        "ilce": request.args.get("ilce") or None,
        "belediye_id": request.args.get("belediye_id") or None,
        "kurum_id": request.args.get("kurum_id") or None,
        "kategori": request.args.get("kategori") or None,
        "tarih": request.args.get("tarih") or None,
        "belediye_tipi": request.args.get("belediye_tipi") or None,
    }


def _geo_only(filters=None):
    """Mevcut API'ler için yalnızca coğrafi filtreler (geriye uyum)."""
    filters = filters or _filters()
    return {
        "il": filters.get("il"),
        "ilce": filters.get("ilce"),
        "belediye_id": filters.get("belediye_id"),
        "kurum_id": filters.get("kurum_id"),
    }


def _wants_json() -> bool:
    if request.args.get("format") == "json":
        return True
    best = request.accept_mimetypes.best_match(["application/json", "text/html"])
    return best == "application/json" and (
        request.accept_mimetypes[best] > request.accept_mimetypes["text/html"]
    )


def _page_context(**extra):
    filters = _filters()
    opts = ministry_drilldown_options(
        il=filters["il"],
        ilce=filters["ilce"],
        belediye_id=filters["belediye_id"],
    )
    ctx = {
        **filters,
        "iller": opts["iller"],
        "ilceler": opts["ilceler"],
        "belediyeler": opts["belediyeler"],
        "kurumlar": opts["kurumlar"],
        "kategoriler": MUNICIPALITY_CATEGORY_GROUPS,
        "secili_il": filters["il"],
        "secili_ilce": filters["ilce"],
        "secili_belediye_id": str(filters["belediye_id"] or ""),
        "secili_kurum_id": str(filters["kurum_id"] or ""),
        "secili_kategori": filters["kategori"],
        "secili_tarih": filters["tarih"],
        "secili_belediye_tipi": filters["belediye_tipi"],
    }
    ctx.update(extra)
    return ctx


@admin_ministry_bp.route("/")
@admin_ministry_bp.route("/dashboard")
@login_required
@ministry_required
def dashboard():
    filters = _filters()
    if _wants_json():
        return jsonify(ministry_statistics(
            il=filters["il"],
            ilce=filters["ilce"],
            belediye_id=filters["belediye_id"],
            kurum_id=filters["kurum_id"],
        ))

    center = ministry_national_center(
        il=filters["il"],
        ilce=filters["ilce"],
        belediye_id=filters["belediye_id"],
        kurum_id=filters["kurum_id"],
        kategori=filters["kategori"],
        tarih=filters["tarih"],
        belediye_tipi=filters["belediye_tipi"],
    )
    prediction = None
    if center.get("source") == "demo":
        from services.prediction_ai import generate_prediction_report

        prediction = generate_prediction_report(
            lookback_months=12,
            il=filters["il"],
            ilce=filters["ilce"],
            include_all_lookbacks=True,
        )
    return render_template(
        "ministry/dashboard.html",
        title="Ulusal Yönetim Merkezi",
        kpi=center["kpi"],
        rankings=center["province_rankings"],
        map_data=center["map_data"],
        center=center,
        prediction=prediction,
        **_page_context(),
    )


@admin_ministry_bp.route("/map")
@login_required
@ministry_required
def api_map():
    return jsonify(ministry_map_data(**{k: v for k, v in _geo_only().items() if k in ("il", "ilce")}))


@admin_ministry_bp.route("/kpi")
@login_required
@ministry_required
def api_kpi():
    return jsonify(ministry_kpi(**_geo_only()))


@admin_ministry_bp.route("/statistics")
@login_required
@ministry_required
def api_statistics():
    return jsonify(ministry_statistics(**_geo_only()))


@admin_ministry_bp.route("/api/drilldown")
@login_required
@ministry_required
def api_drilldown():
    filters = _filters()
    return jsonify(ministry_drilldown_options(
        il=filters["il"],
        ilce=filters["ilce"],
        belediye_id=filters["belediye_id"],
    ))


@admin_ministry_bp.route("/predictions")
@login_required
@ministry_required
def api_predictions():
    """AI Prediction Engine API (ulusal / filtrelenmiş)."""
    from services.prediction_ai import generate_prediction_report

    filters = _filters()
    lookback = request.args.get("lookback", type=int) or 12
    report = generate_prediction_report(
        lookback_months=lookback,
        il=filters["il"],
        ilce=filters["ilce"],
        include_all_lookbacks=True,
    )
    if str(lookback) in (report.get("lookbacks") or {}):
        report["primary"] = report["lookbacks"][str(lookback)]
    return jsonify(report)


@admin_ministry_bp.route("/surdurulebilirlik")
@login_required
@ministry_required
def surdurulebilirlik():
    filters = _filters()
    dash = sustainability_dashboard(il=filters["il"], ilce=filters["ilce"])
    ai = generate_sustainability_suggestions(scored=dash["current"])
    return render_template(
        "ministry/surdurulebilirlik.html",
        title="Sustainability Scoring",
        dash=dash,
        suggestions=ai.get("suggestions") or [],
        suggestion_source=ai.get("source"),
        ai_report=ai.get("report") or {},
        **_page_context(),
    )


@admin_ministry_bp.route("/surdurulebilirlik/pdf")
@login_required
@ministry_required
def surdurulebilirlik_pdf():
    import io

    filters = _filters()
    dash = sustainability_dashboard(il=filters["il"], ilce=filters["ilce"])
    ai = generate_sustainability_suggestions(scored=dash["current"])
    data, filename = export_sustainability_pdf(
        dash,
        ai.get("suggestions") or [],
        report=ai.get("report") or {},
    )
    mimetype = "application/pdf" if filename.endswith(".pdf") else "text/plain"
    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )


@admin_ministry_bp.route("/karar-destek")
@login_required
@ministry_required
def karar_destek():
    """Ulusal Karar Destek Merkezi — AI ulusal analiz dashboard."""
    from services.decision_support_ai import enrich_decision_support

    center = enrich_decision_support()
    return render_template(
        "ministry/karar_destek.html",
        title="Ulusal Karar Destek Merkezi",
        center=center,
        **_page_context(),
    )


@admin_ministry_bp.route("/karar-destek/pdf")
@login_required
@ministry_required
def karar_destek_pdf():
    """Haftalık / aylık / tam karar destek PDF."""
    import io

    from services.decision_support_ai import enrich_decision_support
    from services.decision_support_pdf import export_decision_support_pdf

    report_type = (request.args.get("type") or "full").lower()
    center = enrich_decision_support()
    data, filename = export_decision_support_pdf(center, report_type=report_type)
    mimetype = "application/pdf" if filename.endswith(".pdf") else "text/plain"
    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )
