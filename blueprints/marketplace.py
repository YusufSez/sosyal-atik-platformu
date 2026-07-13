"""Kurumsal Kaynak Pazarı — B2B platform (ROLE_COMPANY / ROLE_INSTITUTION)."""

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
    post_message,
    resolve_listing,
    submit_offer,
    submit_rating,
    transaction_history,
)
from services.marketplace_ai import generate_match_report, platform_ai_overview, suggest_nearby_fit
from services.marketplace_b2b import (
    demand_pool,
    listing_messages,
    listing_ratings,
    list_suppliers,
    nearest_orgs_for_user,
    price_analysis,
)
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
    suppliers_preview = list_suppliers(limit=6)
    pool_preview = demand_pool()[:6]
    prices = price_analysis()
    return render_template(
        "marketplace/panel.html",
        title="B2B Kaynak Platformu",
        published=published,
        mine=mine,
        offers=offers,
        history=history,
        map_points=points,
        kategoriler=MP_KATEGORILER,
        suppliers_preview=suppliers_preview,
        pool_preview=pool_preview,
        price_ozet=prices["ozet"],
    )


@marketplace_bp.route("/tedarikciler")
@login_required
@marketplace_required
def tedarikciler():
    il = (request.args.get("il") or "").strip() or None
    return render_template(
        "marketplace/tedarikciler.html",
        title="Tedarikçiler",
        suppliers=list_suppliers(il=il),
        secili_il=il or "",
    )


@marketplace_bp.route("/talep-havuzu")
@login_required
@marketplace_required
def talep_havuzu():
    kategori = (request.args.get("kategori") or "").strip() or None
    il = (request.args.get("il") or "").strip() or None
    return render_template(
        "marketplace/talep_havuzu.html",
        title="Talep Havuzu",
        pool=demand_pool(kategori=kategori, il=il),
        kategoriler=MP_KATEGORILER,
        secili_kategori=kategori or "",
        secili_il=il or "",
    )


@marketplace_bp.route("/eslesmeler")
@login_required
@marketplace_required
def eslesmeler():
    listing_id = request.args.get("listing_id", type=int)
    listings = my_listings(current_user.id)
    open_listings = [l for l in listings if l.durum == "yayinda"]
    all_open = list_published()
    candidates = open_listings or all_open[:20]
    listing = None
    report = None
    if listing_id:
        listing = resolve_listing(listing_id)
    elif candidates:
        listing = candidates[0]
    if listing:
        report = generate_match_report(listing)
    return render_template(
        "marketplace/eslesmeler.html",
        title="En Uygun Eşleşmeler",
        candidates=candidates,
        listing=listing,
        report=report,
    )


@marketplace_bp.route("/fiyat-analizi")
@login_required
@marketplace_required
def fiyat_analizi():
    return render_template(
        "marketplace/fiyat_analizi.html",
        title="Fiyat Analizi",
        analysis=price_analysis(),
    )


@marketplace_bp.route("/yakin-kurumlar")
@login_required
@marketplace_required
def yakin_kurumlar():
    orgs = nearest_orgs_for_user(current_user, radius_km=MP_NEARBY_RADIUS_KM)
    return render_template(
        "marketplace/yakin_kurumlar.html",
        title="En Yakın Kurumlar",
        orgs=orgs,
        radius_km=MP_NEARBY_RADIUS_KM,
    )


@marketplace_bp.route("/ai-aciklama")
@login_required
@marketplace_required
def ai_aciklama():
    overview = platform_ai_overview()
    listing_id = request.args.get("listing_id", type=int)
    match_report = None
    if listing_id:
        listing = resolve_listing(listing_id)
        if listing:
            match_report = generate_match_report(listing)
    return render_template(
        "marketplace/ai_aciklama.html",
        title="AI Açıklaması",
        overview=overview,
        match_report=match_report,
    )


@marketplace_bp.route("/gecmis")
@login_required
@marketplace_required
def gecmis():
    return render_template(
        "marketplace/gecmis.html",
        title="İşlem Geçmişi",
        history=transaction_history(current_user.id, limit=100),
    )


@marketplace_bp.route("/ilan/<int:listing_id>")
@login_required
@marketplace_required
def detail(listing_id: int):
    listing = resolve_listing(listing_id)
    if not listing:
        abort(404)
    nearby = nearby_institutions(
        listing, radius_km=MP_NEARBY_RADIUS_KM, exclude_user_id=listing.publisher_id
    )
    ai = suggest_nearby_fit(listing)
    match_report = generate_match_report(listing, limit=5)
    is_owner = listing.publisher_id == current_user.id
    my_pending = None
    if not is_owner:
        my_pending = MarketplaceOffer.query.filter_by(
            listing_id=listing.id,
            offerer_id=current_user.id,
            durum="bekliyor",
        ).first()
    messages = listing_messages(listing.id)
    ratings = listing_ratings(listing.id)
    counterparty_id = None
    if listing.accepted_offer_id:
        acc = db.session.get(MarketplaceOffer, listing.accepted_offer_id)
        if acc:
            if current_user.id == listing.publisher_id:
                counterparty_id = acc.offerer_id
            elif current_user.id == acc.offerer_id:
                counterparty_id = listing.publisher_id
    can_message = is_owner or any(o.offerer_id == current_user.id for o in listing.offers)
    return render_template(
        "marketplace/detail.html",
        title=listing.baslik,
        listing=listing,
        nearby=nearby,
        ai_suggestion=ai,
        match_report=match_report,
        is_owner=is_owner,
        my_pending=my_pending,
        messages=messages,
        ratings=ratings,
        counterparty_id=counterparty_id,
        can_message=can_message,
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


@marketplace_bp.route("/ilan/<int:listing_id>/mesaj", methods=["POST"])
@login_required
@marketplace_required
def message(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    try:
        post_message(listing, current_user, request.form.get("mesaj") or "")
    except MarketplaceError as exc:
        return _err(exc)
    flash("Mesaj gönderildi.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id) + "#mesajlar")


@marketplace_bp.route("/ilan/<int:listing_id>/puan", methods=["POST"])
@login_required
@marketplace_required
def rate(listing_id: int):
    listing = db.session.get(MarketplaceListing, listing_id) or abort(404)
    try:
        submit_rating(
            listing,
            current_user,
            puan=request.form.get("puan"),
            hedef_id=int(request.form.get("hedef_id") or 0),
            yorum=request.form.get("yorum") or "",
        )
    except (MarketplaceError, ValueError) as exc:
        if isinstance(exc, MarketplaceError):
            return _err(exc)
        flash("Geçersiz puan formu.", "danger")
        return redirect(url_for("marketplace.detail", listing_id=listing.id))
    flash("Puanınız kaydedildi.", "success")
    return redirect(url_for("marketplace.detail", listing_id=listing.id) + "#puanlama")


@marketplace_bp.route("/api/nearby/<int:listing_id>")
@login_required
@marketplace_required
def api_nearby(listing_id: int):
    listing = resolve_listing(listing_id) or abort(404)
    return jsonify(suggest_nearby_fit(listing))


@marketplace_bp.route("/api/matches/<int:listing_id>")
@login_required
@marketplace_required
def api_matches(listing_id: int):
    listing = resolve_listing(listing_id) or abort(404)
    return jsonify(generate_match_report(listing))


@marketplace_bp.route("/api/map")
@login_required
@marketplace_required
def api_map():
    return jsonify(marketplace_map_points())
