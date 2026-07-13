"""Belediye Yönetim Modülü — ROLE_MUNICIPALITY paneli."""

from flask import Blueprint, jsonify, render_template, request
from flask_login import login_required

from decorators import municipality_required
from services.municipality_ai import generate_municipality_insights
from services.municipality_analytics import (
    geography_options,
    heat_map_points,
    ilce_performans,
    kategori_analizi,
    mahalle_analizi,
    municipality_dashboard,
)

belediye_bp = Blueprint("belediye", __name__, url_prefix="/belediye")


def _filters_from_request():
    return {
        "il": request.args.get("il") or None,
        "ilce": request.args.get("ilce") or None,
        "mahalle": request.args.get("mahalle") or None,
    }


def _geo_context(**extra):
    filters = _filters_from_request()
    opts = geography_options(il=filters["il"], ilce=filters["ilce"])
    ctx = {
        **filters,
        "iller": opts["iller"],
        "ilceler": opts["ilceler"],
        "mahalleler": opts["mahalleler"],
        "secili_il": filters["il"],
        "secili_ilce": filters["ilce"],
        "secili_mahalle": filters["mahalle"],
    }
    ctx.update(extra)
    return ctx


@belediye_bp.route("/")
@belediye_bp.route("/dashboard")
@login_required
@municipality_required
def dashboard():
    filters = _filters_from_request()
    ozet = municipality_dashboard(**filters)
    return render_template(
        "belediye/dashboard.html",
        title="Belediye Dashboard",
        ozet=ozet,
        **_geo_context(),
    )


@belediye_bp.route("/mahalle")
@login_required
@municipality_required
def mahalle():
    filters = _filters_from_request()
    rows = mahalle_analizi(**filters)
    return render_template(
        "belediye/mahalle.html",
        title="Mahalle / İlçe Analizi",
        rows=rows,
        **_geo_context(),
    )


@belediye_bp.route("/heatmap")
@login_required
@municipality_required
def heatmap():
    filters = _filters_from_request()
    yogunluk = request.args.get("yogunluk") or "atik"
    noktalar = heat_map_points(**filters, yogunluk=yogunluk)
    return render_template(
        "belediye/heatmap.html",
        title="Isı Haritası",
        noktalar=noktalar,
        secili_yogunluk=yogunluk,
        **_geo_context(),
    )


@belediye_bp.route("/api/heatmap")
@login_required
@municipality_required
def api_heatmap():
    filters = _filters_from_request()
    yogunluk = request.args.get("yogunluk") or "atik"
    return jsonify(heat_map_points(**filters, yogunluk=yogunluk))


@belediye_bp.route("/kategori")
@login_required
@municipality_required
def kategori():
    filters = _filters_from_request()
    data = kategori_analizi(**filters)
    return render_template(
        "belediye/kategori.html",
        title="Kategori Analizi",
        kategori_data=data,
        **_geo_context(),
    )


@belediye_bp.route("/ai-asistan")
@login_required
@municipality_required
def ai_asistan():
    filters = _filters_from_request()
    result = generate_municipality_insights(**filters)
    return render_template(
        "belediye/ai_asistan.html",
        title="AI Belediye Asistanı",
        insights=result.get("insights") or [],
        insight_source=result.get("source"),
        ozet=result.get("dashboard") or {},
        **_geo_context(),
    )


@belediye_bp.route("/api/ai-insights")
@login_required
@municipality_required
def api_ai_insights():
    filters = _filters_from_request()
    result = generate_municipality_insights(**filters)
    return jsonify({
        "source": result.get("source"),
        "insights": result.get("insights") or [],
    })


@belediye_bp.route("/performans")
@login_required
@municipality_required
def performans():
    filters = _filters_from_request()
    rows = ilce_performans(il=filters["il"])
    return render_template(
        "belediye/performans.html",
        title="İlçe Performans",
        rows=rows,
        **_geo_context(),
    )


@belediye_bp.route("/api/geography")
@login_required
@municipality_required
def api_geography():
    """Basamaklı filtre seçenekleri JSON."""
    return jsonify(geography_options(
        il=request.args.get("il") or None,
        ilce=request.args.get("ilce") or None,
    ))


@belediye_bp.route("/api/predictions")
@login_required
@municipality_required
def api_predictions():
    """AI Prediction Engine — istatistiksel tahmin + AI yorum."""
    from services.prediction_ai import generate_prediction_report

    filters = _filters_from_request()
    lookback = request.args.get("lookback", type=int) or 12
    report = generate_prediction_report(
        lookback_months=lookback,
        il=filters["il"],
        ilce=filters["ilce"],
        mahalle=filters["mahalle"],
        include_all_lookbacks=True,
    )
    # Seçili lookback'i primary yap
    if str(lookback) in (report.get("lookbacks") or {}):
        report["primary"] = report["lookbacks"][str(lookback)]
    return jsonify(report)
