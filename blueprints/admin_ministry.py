"""Bakanlık paneli — ROLE_MINISTRY (tüm belediyeleri görür)."""

from flask import Blueprint, jsonify, render_template, request, send_file
from flask_login import login_required

from decorators import ministry_required
from services.ministry_analytics import (
    ministry_drilldown_options,
    ministry_kpi,
    ministry_map_data,
    ministry_statistics,
    top_bottom_provinces,
)
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
        "secili_il": filters["il"],
        "secili_ilce": filters["ilce"],
        "secili_belediye_id": str(filters["belediye_id"] or ""),
        "secili_kurum_id": str(filters["kurum_id"] or ""),
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
        return jsonify(ministry_statistics(**filters))

    kpi = ministry_kpi(**filters)
    rankings = top_bottom_provinces(10)
    map_data = ministry_map_data(il=filters["il"], ilce=filters["ilce"])
    return render_template(
        "ministry/dashboard.html",
        title="Bakanlık Dashboard",
        kpi=kpi,
        rankings=rankings,
        map_data=map_data,
        **_page_context(),
    )


@admin_ministry_bp.route("/map")
@login_required
@ministry_required
def api_map():
    filters = _filters()
    return jsonify(ministry_map_data(il=filters["il"], ilce=filters["ilce"]))


@admin_ministry_bp.route("/kpi")
@login_required
@ministry_required
def api_kpi():
    return jsonify(ministry_kpi(**_filters()))


@admin_ministry_bp.route("/statistics")
@login_required
@ministry_required
def api_statistics():
    return jsonify(ministry_statistics(**_filters()))


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
    data, filename = export_sustainability_pdf(dash, ai.get("suggestions") or [])
    mimetype = "application/pdf" if filename.endswith(".pdf") else "text/plain"
    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )
