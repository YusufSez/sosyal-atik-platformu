"""Kurumsal Kaynak Pazarı — ROLE_COMPANY / ROLE_INSTITUTION."""

from flask import Blueprint, abort, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import MP_KATEGORILER, MP_NEARBY_RADIUS_KM
from decorators import marketplace_required
from extensions import db
from models import MarketplaceListing, MarketplaceOffer
from services.marketplace import (
    MarketplaceError,
    accept_offer,
    cancel_listing,
    cancel_offer,
    confirm_agreement,
    create_listing,
    list_published,
    mark_delivered,
    marketplace_map_points,
    my_listings,
    my_offers,
    nearby_institutions,
    submit_offer,
    transaction_history,
)
from services.marketplace_ai import suggest_nearby_fit
from utils import parse_coordinates

marketplace_bp = Blueprint("marketplace", __name__, url_prefix="/marketplace")


def _err(exc: MarketplaceError):
    if request.is_json or request.path.startswith("/marketplace/api/"):
        return jsonify({"error": exc.message}), exc.status
    flash(exc.message, "danger")
    return redirect(request.referrer or url_for("marketplace.panel"))


@marketplace_bp.route("/")
@marketplace_bp.route("/panel")
@login_required
@marketplace_required
def panel():
    published = list_published(exclude_user_id=current_user.id)
    mine = my_listings(current_user.id)
    offers = my_offers(current_user.id)
    history = transaction_history(current_user.id)
    points = marketplace_map_points(published + [l for l in mine if l.durum == "yayinda"])
    return render_template(
        "marketplace/panel.html",
        title="Kurumsal Marketplace",
        published=published,
        mine=mine,
        offers=offers,
        history=history,
        map_points=points,
        kategoriler=MP_KATEGORILER,
    )


@marketplace_bp.route("/ilan/<int:listing_id>")
@login_required
@marketplace_required
def detail(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id)
    if not listing:
        abort(404)
    nearby = nearby_institutions(
        listing, radius_km=MP_NEARBY_RADIUS_KM, exclude_user_id=listing.publisher_id
    )
    ai = suggest_nearby_fit(listing)
    is_owner = listing.publisher_id == current_user.id
    my_pending = None
    if not is_owner:
        my_pending = MarketplaceOffer.query.filter_by(
            listing_id=listing.id,
            offerer_id=current_user.id,
            durum="bekliyor",
        ).first()
    return render_template(
        "marketplace/detail.html",
        title=listing.baslik,
        listing=listing,
        nearby=nearby,
        ai_suggestion=ai,
        is_owner=is_owner,
        my_pending=my_pending,
    )


@marketplace_bp.route("/ilan/yeni", methods=["GET", "POST"])
@login_required
@marketplace_required
def create():
    if request.method == "GET":
        return render_template(
            "marketplace/create.html",
            title="Kaynak Yayınla",
            kategoriler=MP_KATEGORILER,
        )

    lat, lng, _ = parse_coordinates(
        request.form.get("latitude"),
        request.form.get("longitude"),
        user=current_user,
    )
    miktar_raw = request.form.get("miktar")
    try:
        miktar = float(miktar_raw) if miktar_raw not in (None, "") else None
    except ValueError:
        miktar = None

    try:
        listing = create_listing(
            current_user,
            {
                "baslik": request.form.get("baslik"),
                "aciklama": request.form.get("aciklama"),
                "kategori": request.form.get("kategori"),
                "miktar": miktar,
                "birim": request.form.get("birim") or "adet",
                "latitude": lat,
                "longitude": lng,
                "il": request.form.get("il") or current_user.il,
                "ilce": request.form.get("ilce") or current_user.ilce,
            },
        )
    except MarketplaceError as exc:
        return _err(exc)

    flash("Kurumsal kaynak yayınlandı.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id))


@marketplace_bp.route("/ilan/<int:listing_id>/teklif", methods=["POST"])
@login_required
@marketplace_required
def offer(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    miktar_raw = request.form.get("miktar")
    try:
        miktar = float(miktar_raw) if miktar_raw not in (None, "") else None
    except ValueError:
        miktar = None
    try:
        submit_offer(
            listing,
            current_user,
            {"mesaj": request.form.get("mesaj"), "miktar": miktar},
        )
    except MarketplaceError as exc:
        return _err(exc)
    flash("Teklifiniz gönderildi.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id))


@marketplace_bp.route("/teklif/<int:offer_id>/kabul", methods=["POST"])
@login_required
@marketplace_required
def offer_accept(offer_id: int):
    offer_obj = db.session.get(MarketplaceOffer, offer_id) or abort(404)
    listing = offer_obj.listing
    try:
        accept_offer(listing, offer_obj, current_user)
    except MarketplaceError as exc:
        return _err(exc)
    flash("Teklif kabul edildi — rezervasyon oluşturuldu.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id))


@marketplace_bp.route("/ilan/<int:listing_id>/anlasma", methods=["POST"])
@login_required
@marketplace_required
def agreement(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    try:
        confirm_agreement(listing, current_user)
    except MarketplaceError as exc:
        return _err(exc)
    flash("Anlaşma onaylandı.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id))


@marketplace_bp.route("/ilan/<int:listing_id>/teslim", methods=["POST"])
@login_required
@marketplace_required
def deliver(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    try:
        mark_delivered(listing, current_user)
    except MarketplaceError as exc:
        return _err(exc)
    flash("Teslim tamamlandı.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id))


@marketplace_bp.route("/ilan/<int:listing_id>/iptal", methods=["POST"])
@login_required
@marketplace_required
def listing_cancel(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    try:
        cancel_listing(listing, current_user, reason=request.form.get("reason") or "")
    except MarketplaceError as exc:
        return _err(exc)
    flash("İlan iptal edildi.", "info")
    return redirect(url_for("marketplace.panel"))


@marketplace_bp.route("/teklif/<int:offer_id>/iptal", methods=["POST"])
@login_required
@marketplace_required
def offer_cancel(offer_id: int):
    offer_obj = db.session.get(MarketplaceOffer, offer_id) or abort(404)
    try:
        cancel_offer(offer_obj, current_user)
    except MarketplaceError as exc:
        return _err(exc)
    flash("Teklif iptal edildi.", "info")
    return redirect(url_for("marketplace.detail", listing_id=offer_obj.listing_id))


@marketplace_bp.route("/api/nearby/<int:listing_id>")
@login_required
@marketplace_required
def api_nearby(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    return jsonify(suggest_nearby_fit(listing))


@marketplace_bp.route("/api/map")
@login_required
@marketplace_required
def api_map():
    return jsonify(marketplace_map_points())
