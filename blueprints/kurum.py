from flask import Blueprint, abort, jsonify, render_template, request
from flask_login import current_user, login_required

from services.kurum_analytics import (
    ilce_kirilimi,
    isi_haritasi_noktalari,
    kategori_dagilimi,
    kurum_eslesme_onerileri,
    kurum_ozet,
    mevcut_iller,
)

kurum_bp = Blueprint("kurum", __name__)


def kurum_erisimi():
    if not current_user.is_authenticated:
        return False
    if getattr(current_user, "is_kurum", False) or getattr(current_user, "is_admin", False):
        return True
    role = getattr(current_user, "role", None)
    return role == "institution"


@kurum_bp.route("/kurum/analiz")
@login_required
def analiz_paneli():
    if not kurum_erisimi():
        abort(404)

    il_filtre = request.args.get("il") or None
    if il_filtre == "":
        il_filtre = None
    tur = request.args.get("tur") or None

    return render_template(
        "kurum/analiz.html",
        ozet=kurum_ozet(il_filtre),
        ilceler=ilce_kirilimi(il_filtre),
        kaynak_kategoriler=kategori_dagilimi(il_filtre, "kaynak"),
        atik_kategoriler=kategori_dagilimi(il_filtre, "atik"),
        iller=mevcut_iller(),
        secili_il=il_filtre,
        secili_tur=tur,
        isi_noktalari=isi_haritasi_noktalari(il_filtre, tur),
        eslesmeler=kurum_eslesme_onerileri(il_filtre),
        title="Kurum Analiz Paneli",
    )


@kurum_bp.route("/api/kurum/isi-haritasi")
@login_required
def api_isi_haritasi():
    if not kurum_erisimi():
        return jsonify({"error": "Yetkisiz"}), 403
    il_filtre = request.args.get("il") or None
    tur = request.args.get("tur") or None
    return jsonify(isi_haritasi_noktalari(il_filtre, tur))
