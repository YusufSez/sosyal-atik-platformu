"""B2B marketplace analitik katmanı — mevcut tabloları kullanır (şema değişmez)."""

from __future__ import annotations

from collections import defaultdict
from statistics import mean

from sqlalchemy import or_

from constants import (
    MARKETPLACE_ROLES,
    MP_EVENT_PUAN,
    MP_LISTING_TESLIM,
    MP_LISTING_YAYINDA,
    MP_NEARBY_RADIUS_KM,
    MP_OFFER_KABUL,
)
from extensions import db
from models import MarketplaceEvent, MarketplaceListing, MarketplaceOffer, User
from services.marketplace import nearby_institutions
from utils import mesafe_hesapla


def _parse_puan_detail(detail: str | None) -> dict | None:
    """detail formatı: puan:4|hedef:12|yorum metni"""
    if not detail or not detail.startswith("puan:"):
        return None
    parts = detail.split("|", 2)
    try:
        score = int(parts[0].split(":", 1)[1])
    except (IndexError, ValueError):
        return None
    hedef_id = None
    yorum = ""
    if len(parts) > 1 and parts[1].startswith("hedef:"):
        try:
            hedef_id = int(parts[1].split(":", 1)[1])
        except ValueError:
            hedef_id = None
    if len(parts) > 2:
        yorum = parts[2]
    return {"puan": max(1, min(5, score)), "hedef_id": hedef_id, "yorum": yorum}


def ratings_for_user(user_id: int) -> dict:
    events = MarketplaceEvent.query.filter_by(action=MP_EVENT_PUAN).all()
    scores = []
    comments = []
    for e in events:
        parsed = _parse_puan_detail(e.detail)
        if not parsed or parsed.get("hedef_id") != user_id:
            continue
        scores.append(parsed["puan"])
        comments.append({
            "puan": parsed["puan"],
            "yorum": parsed["yorum"],
            "actor_id": e.actor_id,
            "listing_id": e.listing_id,
            "created_at": e.created_at,
        })
    return {
        "ortalama": round(mean(scores), 2) if scores else None,
        "adet": len(scores),
        "yorumlar": comments[:20],
    }


def list_suppliers(*, il: str | None = None, limit: int = 100) -> list[dict]:
    """Tedarikçi / kurum dizini — company, institution, is_kurum."""
    q = User.query.filter(
        or_(
            User.role.in_(MARKETPLACE_ROLES),
            User.is_kurum.is_(True),
        )
    )
    if il:
        q = q.filter(User.il == il)
    users = q.order_by(User.username.asc()).limit(limit).all()

    listing_counts = dict(
        db.session.query(
            MarketplaceListing.publisher_id,
            db.func.count(MarketplaceListing.id),
        )
        .group_by(MarketplaceListing.publisher_id)
        .all()
    )
    delivery_counts = dict(
        db.session.query(
            MarketplaceListing.publisher_id,
            db.func.count(MarketplaceListing.id),
        )
        .filter(MarketplaceListing.durum == MP_LISTING_TESLIM)
        .group_by(MarketplaceListing.publisher_id)
        .all()
    )
    offer_counts = dict(
        db.session.query(
            MarketplaceOffer.offerer_id,
            db.func.count(MarketplaceOffer.id),
        )
        .group_by(MarketplaceOffer.offerer_id)
        .all()
    )

    rows = []
    for u in users:
        rating = ratings_for_user(u.id)
        rows.append({
            "id": u.id,
            "ad": u.display_name or u.username,
            "role": u.role,
            "il": u.il,
            "ilce": u.ilce,
            "lat": u.latitude,
            "lng": u.longitude,
            "ilan_sayisi": int(listing_counts.get(u.id) or 0),
            "teslim_sayisi": int(delivery_counts.get(u.id) or 0),
            "teklif_sayisi": int(offer_counts.get(u.id) or 0),
            "puan_ortalama": rating["ortalama"],
            "puan_adet": rating["adet"],
        })
    rows.sort(
        key=lambda r: (
            -(r["puan_ortalama"] or 0),
            -r["teslim_sayisi"],
            -r["ilan_sayisi"],
        )
    )
    return rows


def demand_pool(*, kategori: str | None = None, il: str | None = None) -> list[dict]:
    """Talep havuzu — yayındaki kurumsal ilanlar."""
    q = MarketplaceListing.query.filter_by(durum=MP_LISTING_YAYINDA).order_by(
        MarketplaceListing.created_at.desc()
    )
    if kategori:
        q = q.filter(MarketplaceListing.kategori == kategori)
    if il:
        q = q.filter(MarketplaceListing.il == il)

    rows = []
    for listing in q.limit(80).all():
        pending = sum(1 for o in listing.offers if o.durum == "bekliyor")
        rows.append({
            "id": listing.id,
            "baslik": listing.baslik,
            "kategori": listing.kategori,
            "miktar": listing.miktar,
            "birim": listing.birim,
            "il": listing.il,
            "ilce": listing.ilce,
            "publisher": listing.publisher.display_name or listing.publisher.username,
            "publisher_id": listing.publisher_id,
            "teklif_bekleyen": pending,
            "created_at": listing.created_at,
            "lat": listing.latitude,
            "lng": listing.longitude,
        })
    return rows


def price_analysis() -> dict:
    """Kategori bazlı miktar / teklif analizi (fiyat vekili: miktar dağılımı)."""
    by_cat: dict[str, dict] = defaultdict(lambda: {
        "ilan_adet": 0,
        "miktarlar": [],
        "teklif_miktarlari": [],
        "teslim_adet": 0,
    })

    for listing in MarketplaceListing.query.all():
        cat = listing.kategori or "Diğer"
        bucket = by_cat[cat]
        bucket["ilan_adet"] += 1
        if listing.miktar is not None:
            bucket["miktarlar"].append(float(listing.miktar))
        if listing.durum == MP_LISTING_TESLIM:
            bucket["teslim_adet"] += 1

    for offer in MarketplaceOffer.query.all():
        listing = offer.listing
        if not listing:
            continue
        cat = listing.kategori or "Diğer"
        if offer.miktar is not None:
            by_cat[cat]["teklif_miktarlari"].append(float(offer.miktar))

    categories = []
    for cat, b in sorted(by_cat.items(), key=lambda x: -x[1]["ilan_adet"]):
        miktarlar = b["miktarlar"]
        teklifler = b["teklif_miktarlari"]
        categories.append({
            "kategori": cat,
            "ilan_adet": b["ilan_adet"],
            "teslim_adet": b["teslim_adet"],
            "ortalama_miktar": round(mean(miktarlar), 2) if miktarlar else None,
            "medyan_miktar": round(sorted(miktarlar)[len(miktarlar) // 2], 2) if miktarlar else None,
            "min_miktar": round(min(miktarlar), 2) if miktarlar else None,
            "max_miktar": round(max(miktarlar), 2) if miktarlar else None,
            "ortalama_teklif_miktar": round(mean(teklifler), 2) if teklifler else None,
            "teklif_adet": len(teklifler),
        })

    return {
        "kategoriler": categories,
        "ozet": {
            "kategori_sayisi": len(categories),
            "toplam_ilan": sum(c["ilan_adet"] for c in categories),
            "toplam_teslim": sum(c["teslim_adet"] for c in categories),
        },
    }


def category_affinity(user_id: int) -> dict[str, int]:
    """Kullanıcının yayınladığı / teklif verdiği kategoriler."""
    counts: dict[str, int] = defaultdict(int)
    for listing in MarketplaceListing.query.filter_by(publisher_id=user_id).all():
        counts[listing.kategori or "Diğer"] += 2
    for offer in MarketplaceOffer.query.filter_by(offerer_id=user_id).all():
        if offer.listing:
            counts[offer.listing.kategori or "Diğer"] += 1
    return dict(counts)


def score_match(
    listing: MarketplaceListing,
    org: dict,
    *,
    radius_km: float = MP_NEARBY_RADIUS_KM,
) -> dict:
    """Mesafe + kategori uyumu + puan + teslim geçmişi skoru (0–100)."""
    dist = float(org.get("mesafe_km") or radius_km)
    distance_score = max(0.0, 100.0 * (1.0 - dist / max(radius_km, 1.0)))

    affinity = category_affinity(org["id"])
    cat = listing.kategori or "Diğer"
    cat_hits = affinity.get(cat, 0)
    category_score = min(100.0, cat_hits * 25.0)

    rating = ratings_for_user(org["id"])
    rating_score = (rating["ortalama"] or 3.0) / 5.0 * 100.0

    deliveries = MarketplaceListing.query.filter_by(
        publisher_id=org["id"], durum=MP_LISTING_TESLIM
    ).count()
    accepted_as_offerer = MarketplaceOffer.query.filter_by(
        offerer_id=org["id"], durum=MP_OFFER_KABUL
    ).count()
    activity_score = min(100.0, (deliveries + accepted_as_offerer) * 20.0)

    total = round(
        0.40 * distance_score
        + 0.25 * category_score
        + 0.20 * rating_score
        + 0.15 * activity_score,
        1,
    )
    reasons = []
    if dist <= 15:
        reasons.append(f"{dist} km mesafede")
    elif dist <= radius_km:
        reasons.append(f"{dist} km içinde erişilebilir")
    if cat_hits:
        reasons.append(f"{cat} kategorisinde deneyim")
    if rating["ortalama"]:
        reasons.append(f"ortalama puan {rating['ortalama']}")
    if deliveries or accepted_as_offerer:
        reasons.append(f"{deliveries + accepted_as_offerer} tamamlanan işlem")

    return {
        **org,
        "eslesme_skoru": total,
        "skor_detay": {
            "mesafe": round(distance_score, 1),
            "kategori": round(category_score, 1),
            "puan": round(rating_score, 1),
            "aktivite": round(activity_score, 1),
        },
        "nedenler": reasons or ["Konum yakınlığı"],
        "puan_ortalama": rating["ortalama"],
    }


def best_matches(
    listing: MarketplaceListing,
    *,
    radius_km: float = MP_NEARBY_RADIUS_KM,
    limit: int = 12,
) -> list[dict]:
    nearby = nearby_institutions(
        listing, radius_km=radius_km, exclude_user_id=listing.publisher_id
    )
    scored = [score_match(listing, org, radius_km=radius_km) for org in nearby]
    scored.sort(key=lambda x: -x["eslesme_skoru"])
    return scored[:limit]


def nearest_orgs_for_user(
    user: User,
    *,
    radius_km: float = MP_NEARBY_RADIUS_KM,
    limit: int = 30,
) -> list[dict]:
    """Kullanıcı konumuna göre en yakın kurumlar."""
    if user.latitude is None or user.longitude is None:
        return []
    q = User.query.filter(
        or_(
            User.role.in_(MARKETPLACE_ROLES),
            User.is_kurum.is_(True),
        ),
        User.latitude.isnot(None),
        User.longitude.isnot(None),
        User.id != user.id,
    )
    results = []
    for other in q.all():
        dist = mesafe_hesapla(
            user.latitude, user.longitude, other.latitude, other.longitude
        )
        if dist > radius_km:
            continue
        rating = ratings_for_user(other.id)
        results.append({
            "id": other.id,
            "ad": other.display_name or other.username,
            "role": other.role,
            "il": other.il,
            "ilce": other.ilce,
            "lat": other.latitude,
            "lng": other.longitude,
            "mesafe_km": round(dist, 1),
            "puan_ortalama": rating["ortalama"],
            "ilan_sayisi": MarketplaceListing.query.filter_by(publisher_id=other.id).count(),
        })
    results.sort(key=lambda x: x["mesafe_km"])
    return results[:limit]


def listing_messages(listing_id: int) -> list[MarketplaceEvent]:
    from constants import MP_EVENT_MESAJ

    return (
        MarketplaceEvent.query.filter_by(listing_id=listing_id, action=MP_EVENT_MESAJ)
        .order_by(MarketplaceEvent.created_at.asc())
        .all()
    )


def listing_ratings(listing_id: int) -> list[dict]:
    events = (
        MarketplaceEvent.query.filter_by(listing_id=listing_id, action=MP_EVENT_PUAN)
        .order_by(MarketplaceEvent.created_at.desc())
        .all()
    )
    out = []
    for e in events:
        parsed = _parse_puan_detail(e.detail)
        if not parsed:
            continue
        out.append({
            "actor_id": e.actor_id,
            "puan": parsed["puan"],
            "hedef_id": parsed["hedef_id"],
            "yorum": parsed["yorum"],
            "created_at": e.created_at,
        })
    return out
