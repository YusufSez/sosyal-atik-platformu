"""Kurumsal Kaynak Pazarı — iş kuralları (mevcut Kaynak/Atık'tan bağımsız)."""

from __future__ import annotations

from sqlalchemy import or_

from constants import (
    MARKETPLACE_ROLES,
    MP_LISTING_ANLASILDI,
    MP_LISTING_IPTAL,
    MP_LISTING_REZERVE,
    MP_LISTING_TESLIM,
    MP_LISTING_YAYINDA,
    MP_NEARBY_RADIUS_KM,
    MP_OFFER_BEKLIYOR,
    MP_OFFER_IPTAL,
    MP_OFFER_KABUL,
    MP_OFFER_RED,
)
from extensions import db
from models import MarketplaceEvent, MarketplaceListing, MarketplaceOffer, User
from utils import mesafe_hesapla, sanitize_input, utc_now


class MarketplaceError(Exception):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.message = message
        self.status = status


def _log(listing_id: int, actor_id: int | None, action: str, detail: str = "", offer_id: int | None = None):
    db.session.add(
        MarketplaceEvent(
            listing_id=listing_id,
            actor_id=actor_id,
            offer_id=offer_id,
            action=action,
            detail=(detail or "")[:500],
        )
    )


def create_listing(publisher: User, data: dict) -> MarketplaceListing:
    baslik = sanitize_input(data.get("baslik"), max_length=150)
    aciklama = sanitize_input(data.get("aciklama"), max_length=5000)
    if not baslik or not aciklama:
        raise MarketplaceError("Başlık ve açıklama zorunludur.")

    listing = MarketplaceListing(
        publisher_id=publisher.id,
        baslik=baslik,
        aciklama=aciklama,
        kategori=sanitize_input(data.get("kategori"), max_length=50) or "Diğer",
        miktar=data.get("miktar"),
        birim=sanitize_input(data.get("birim"), max_length=30) or "adet",
        latitude=float(data["latitude"]),
        longitude=float(data["longitude"]),
        il=sanitize_input(data.get("il") or publisher.il, max_length=100),
        ilce=sanitize_input(data.get("ilce") or publisher.ilce, max_length=100),
        durum=MP_LISTING_YAYINDA,
    )
    db.session.add(listing)
    db.session.flush()
    _log(listing.id, publisher.id, "yayinla", f"İlan yayınlandı: {listing.baslik}")
    db.session.commit()
    return listing


def list_published(*, exclude_user_id: int | None = None):
    q = MarketplaceListing.query.filter_by(durum=MP_LISTING_YAYINDA).order_by(
        MarketplaceListing.created_at.desc()
    )
    if exclude_user_id:
        q = q.filter(MarketplaceListing.publisher_id != exclude_user_id)
    return q.all()


def my_listings(user_id: int):
    return (
        MarketplaceListing.query.filter_by(publisher_id=user_id)
        .order_by(MarketplaceListing.created_at.desc())
        .all()
    )


def my_offers(user_id: int):
    return (
        MarketplaceOffer.query.filter_by(offerer_id=user_id)
        .order_by(MarketplaceOffer.created_at.desc())
        .all()
    )


def transaction_history(user_id: int, limit: int = 50):
    """Kullanıcının yayıncı veya teklifçi olduğu işlem geçmişi."""
    listing_ids = [
        r[0]
        for r in db.session.query(MarketplaceListing.id)
        .filter(MarketplaceListing.publisher_id == user_id)
        .all()
    ]
    offer_listing_ids = [
        r[0]
        for r in db.session.query(MarketplaceOffer.listing_id)
        .filter(MarketplaceOffer.offerer_id == user_id)
        .distinct()
        .all()
    ]
    ids = set(listing_ids) | set(offer_listing_ids)
    if not ids:
        return []
    return (
        MarketplaceEvent.query.filter(MarketplaceEvent.listing_id.in_(ids))
        .order_by(MarketplaceEvent.created_at.desc())
        .limit(limit)
        .all()
    )


def submit_offer(listing: MarketplaceListing, offerer: User, data: dict) -> MarketplaceOffer:
    if listing.publisher_id == offerer.id:
        raise MarketplaceError("Kendi ilanınıza teklif veremezsiniz.")
    if listing.durum != MP_LISTING_YAYINDA:
        raise MarketplaceError("Bu ilan teklife kapalı.")

    existing = MarketplaceOffer.query.filter_by(
        listing_id=listing.id,
        offerer_id=offerer.id,
        durum=MP_OFFER_BEKLIYOR,
    ).first()
    if existing:
        raise MarketplaceError("Zaten bekleyen bir teklifiniz var.")

    offer = MarketplaceOffer(
        listing_id=listing.id,
        offerer_id=offerer.id,
        mesaj=sanitize_input(data.get("mesaj"), max_length=2000),
        miktar=data.get("miktar"),
        durum=MP_OFFER_BEKLIYOR,
    )
    db.session.add(offer)
    db.session.flush()
    _log(listing.id, offerer.id, "teklif", "Teklif gönderildi", offer_id=offer.id)
    db.session.commit()
    return offer


def accept_offer(listing: MarketplaceListing, offer: MarketplaceOffer, actor: User) -> MarketplaceListing:
    if listing.publisher_id != actor.id:
        raise MarketplaceError("Yalnızca yayıncı teklif kabul edebilir.", 403)
    if listing.durum != MP_LISTING_YAYINDA:
        raise MarketplaceError("İlan teklif kabulüne uygun değil.")
    if offer.listing_id != listing.id or offer.durum != MP_OFFER_BEKLIYOR:
        raise MarketplaceError("Geçersiz teklif.")

    now = utc_now()
    offer.durum = MP_OFFER_KABUL
    offer.responded_at = now
    listing.durum = MP_LISTING_REZERVE
    listing.accepted_offer_id = offer.id

    # Diğer bekleyen teklifleri reddet
    others = MarketplaceOffer.query.filter(
        MarketplaceOffer.listing_id == listing.id,
        MarketplaceOffer.id != offer.id,
        MarketplaceOffer.durum == MP_OFFER_BEKLIYOR,
    ).all()
    for o in others:
        o.durum = MP_OFFER_RED
        o.responded_at = now

    _log(listing.id, actor.id, "rezervasyon", f"Teklif #{offer.id} kabul — rezervasyon", offer_id=offer.id)
    db.session.commit()
    return listing


def confirm_agreement(listing: MarketplaceListing, actor: User) -> MarketplaceListing:
    """Rezerve → Anlaşma (yayıncı veya kabul edilen teklif sahibi)."""
    if listing.durum != MP_LISTING_REZERVE:
        raise MarketplaceError("Anlaşma yalnızca rezervasyon sonrası yapılabilir.")
    offer = db.session.get(MarketplaceOffer, listing.accepted_offer_id) if listing.accepted_offer_id else None
    allowed = {listing.publisher_id}
    if offer:
        allowed.add(offer.offerer_id)
    if actor.id not in allowed:
        raise MarketplaceError("Bu işlem için yetkiniz yok.", 403)

    listing.durum = MP_LISTING_ANLASILDI
    _log(listing.id, actor.id, "anlasma", "Anlaşma onaylandı", offer_id=listing.accepted_offer_id)
    db.session.commit()
    return listing


def mark_delivered(listing: MarketplaceListing, actor: User) -> MarketplaceListing:
    if listing.durum != MP_LISTING_ANLASILDI:
        raise MarketplaceError("Teslim yalnızca anlaşma sonrası işaretlenebilir.")
    offer = db.session.get(MarketplaceOffer, listing.accepted_offer_id) if listing.accepted_offer_id else None
    allowed = {listing.publisher_id}
    if offer:
        allowed.add(offer.offerer_id)
    if actor.id not in allowed:
        raise MarketplaceError("Bu işlem için yetkiniz yok.", 403)

    listing.durum = MP_LISTING_TESLIM
    _log(listing.id, actor.id, "teslim", "Teslim tamamlandı", offer_id=listing.accepted_offer_id)
    db.session.commit()
    return listing


def cancel_listing(listing: MarketplaceListing, actor: User, reason: str = "") -> MarketplaceListing:
    if listing.publisher_id != actor.id and not getattr(actor, "is_admin", False):
        raise MarketplaceError("Yalnızca yayıncı iptal edebilir.", 403)
    if listing.durum in (MP_LISTING_TESLIM, MP_LISTING_IPTAL):
        raise MarketplaceError("Bu ilan iptal edilemez.")

    listing.durum = MP_LISTING_IPTAL
    pending = MarketplaceOffer.query.filter_by(
        listing_id=listing.id, durum=MP_OFFER_BEKLIYOR
    ).all()
    now = utc_now()
    for o in pending:
        o.durum = MP_OFFER_IPTAL
        o.responded_at = now
    _log(listing.id, actor.id, "iptal", reason or "İlan iptal edildi")
    db.session.commit()
    return listing


def cancel_offer(offer: MarketplaceOffer, actor: User) -> MarketplaceOffer:
    if offer.offerer_id != actor.id:
        raise MarketplaceError("Yalnızca teklif sahibi iptal edebilir.", 403)
    if offer.durum != MP_OFFER_BEKLIYOR:
        raise MarketplaceError("Yalnızca bekleyen teklif iptal edilebilir.")
    offer.durum = MP_OFFER_IPTAL
    offer.responded_at = utc_now()
    _log(offer.listing_id, actor.id, "teklif_iptal", "Teklif geri çekildi", offer_id=offer.id)
    db.session.commit()
    return offer


def nearby_institutions(
    listing: MarketplaceListing,
    *,
    radius_km: float = MP_NEARBY_RADIUS_KM,
    exclude_user_id: int | None = None,
) -> list[dict]:
    """Yakındaki company/institution/kurum kullanıcıları."""
    q = User.query.filter(
        or_(
            User.role.in_(MARKETPLACE_ROLES),
            User.is_kurum.is_(True),
        ),
        User.latitude.isnot(None),
        User.longitude.isnot(None),
    )
    if exclude_user_id:
        q = q.filter(User.id != exclude_user_id)

    results = []
    for user in q.all():
        dist = mesafe_hesapla(
            listing.latitude, listing.longitude, user.latitude, user.longitude
        )
        if dist <= radius_km:
            results.append({
                "id": user.id,
                "ad": user.display_name or user.username,
                "role": user.role,
                "il": user.il,
                "ilce": user.ilce,
                "lat": user.latitude,
                "lng": user.longitude,
                "mesafe_km": round(dist, 1),
            })
    results.sort(key=lambda x: x["mesafe_km"])
    return results


def marketplace_map_points(listings: list[MarketplaceListing] | None = None) -> list:
    items = listings
    if items is None:
        items = MarketplaceListing.query.filter(
            MarketplaceListing.durum.in_(
                [MP_LISTING_YAYINDA, MP_LISTING_REZERVE, MP_LISTING_ANLASILDI]
            )
        ).all()
    points = []
    for listing in items:
        points.append({
            "id": listing.id,
            "baslik": listing.baslik,
            "durum": listing.durum,
            "lat": listing.latitude,
            "lng": listing.longitude,
            "kategori": listing.kategori,
        })
    return points
