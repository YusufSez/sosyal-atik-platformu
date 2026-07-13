"""Belediye Yönetim Modülü — ROLE_MUNICIPALITY paneli."""

from flask import Blueprint, jsonify, render_template, request, send_file
from flask_login import current_user, login_required

from constants import ROLE_MUNICIPALITY
from decorators import municipality_required
from services.municipality_ai import generate_municipality_insights
from services.municipality_analytics import (
    geography_options,
    heat_map_points,
    ilce_performans,
    kategori_analizi,
    mahalle_analizi,
    municipality_dashboard,
    municipality_ops_center,
)
from services.sustainability_ai import generate_sustainability_suggestions
from services.sustainability_pdf import export_sustainability_pdf
from services.sustainability_scoring import sustainability_dashboard


belediye_bp = Blueprint("belediye", __name__, url_prefix="/belediye")


def _filters_from_request():
    """İstek filtreleri; belediye kullanıcısında il boşsa hesap iline kilitlenir."""
    il = request.args.get("il") or None
    if not il and current_user.is_authenticated:
        il = (getattr(current_user, "il", None) or "").strip() or None
    return {
        "il": il,
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
    ops = municipality_ops_center(**filters)
    ozet = ops["ozet"]
    with_ai = generate_municipality_insights(**filters)
    return render_template(
        "belediye/dashboard.html",
        title="Belediye Operasyon Merkezi",
        ozet=ozet,
        ops=ops,
        insights=with_ai.get("insights") or [],
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
    map_center = {"lat": 39.0, "lng": 35.0, "zoom": 6}
    try:
        from services.municipality_analytics import _demo_dashboard_active
        from services import demo_provider

        if _demo_dashboard_active(**filters):
            map_center = demo_provider.get_city(filters["il"])["map_center"]
        elif noktalar:
            map_center = {
                "lat": noktalar[0][0],
                "lng": noktalar[0][1],
                "zoom": 11,
            }
    except Exception:
        if noktalar:
            map_center = {"lat": noktalar[0][0], "lng": noktalar[0][1], "zoom": 11}
    return render_template(
        "belediye/heatmap.html",
        title="Isı Haritası",
        noktalar=noktalar,
        map_center=map_center,
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


@belediye_bp.route("/surdurulebilirlik")
@login_required
@municipality_required
def surdurulebilirlik():
    """Sustainability Scoring Engine dashboard."""
    filters = _filters_from_request()
    belediye_user = current_user if getattr(current_user, "role", None) == ROLE_MUNICIPALITY else None
    dash = sustainability_dashboard(
        il=filters["il"] or (belediye_user.il if belediye_user else None),
        ilce=filters["ilce"] or (belediye_user.ilce if belediye_user else None),
        belediye_user=belediye_user,
    )
    ai = generate_sustainability_suggestions(scored=dash["current"])
    return render_template(
        "belediye/surdurulebilirlik.html",
        title="Sustainability Scoring",
        dash=dash,
        suggestions=ai.get("suggestions") or [],
        suggestion_source=ai.get("source"),
        ai_report=ai.get("report") or {},
        **_geo_context(),
    )


@belediye_bp.route("/api/sustainability")
@login_required
@municipality_required
def api_sustainability():
    filters = _filters_from_request()
    belediye_user = current_user if getattr(current_user, "role", None) == ROLE_MUNICIPALITY else None
    dash = sustainability_dashboard(
        il=filters["il"] or (belediye_user.il if belediye_user else None),
        ilce=filters["ilce"] or (belediye_user.ilce if belediye_user else None),
        belediye_user=belediye_user,
    )
    ai = generate_sustainability_suggestions(scored=dash["current"])
    return jsonify({**dash, "suggestions": ai})


@belediye_bp.route("/surdurulebilirlik/pdf")
@login_required
@municipality_required
def surdurulebilirlik_pdf():
    filters = _filters_from_request()
    belediye_user = current_user if getattr(current_user, "role", None) == ROLE_MUNICIPALITY else None
    dash = sustainability_dashboard(
        il=filters["il"] or (belediye_user.il if belediye_user else None),
        ilce=filters["ilce"] or (belediye_user.ilce if belediye_user else None),
        belediye_user=belediye_user,
    )
    ai = generate_sustainability_suggestions(scored=dash["current"])
    data, filename = export_sustainability_pdf(
        dash,
        ai.get("suggestions") or [],
        report=ai.get("report") or {},
    )
    import io

    mimetype = "application/pdf" if filename.endswith(".pdf") else "text/plain"
    return send_file(
        io.BytesIO(data),
        mimetype=mimetype,
        as_attachment=True,
        download_name=filename,
    )
