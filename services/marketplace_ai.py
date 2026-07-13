"""Kurumsal marketplace AI — eşleştirme skoru + açıklama."""

from __future__ import annotations

import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from models import MarketplaceListing
from services.marketplace import nearby_institutions
from services.marketplace_b2b import best_matches

logger = logging.getLogger("atikport.marketplace_ai")


def suggest_nearby_fit(listing: MarketplaceListing, *, radius_km: float = 50) -> dict:
    """
    Yakındaki kurum sayısına göre öneri üretir.
    Örnek: 'Bu kaynak yakınınızdaki 4 kurum için uygundur.'
    """
    from services.demo_manager import is_marketplace_catalog_sufficient, should_use_demo, use_demo_ai
    from services import demo_provider

    if should_use_demo(
        "marketplace",
        real_data_sufficient=is_marketplace_catalog_sufficient(),
    ):
        nearby = demo_provider.marketplace_nearest_orgs(
            lat=getattr(listing, "latitude", None),
            lng=getattr(listing, "longitude", None),
            radius_km=radius_km,
            limit=10,
            exclude_id=getattr(listing, "publisher_id", None),
        )
        count = len(nearby)
        return {
            "suggestion": (
                f"Bu kaynak yakınınızdaki {count} kurum için uygundur."
                if count > 0
                else "Yakın çevrede uygun kurum bulunamadı; yarıçapı genişletmeyi deneyin."
            ),
            "source": "demo",
            "nearby_count": count,
            "nearby": nearby[:10],
            "radius_km": radius_km,
        }

    nearby = nearby_institutions(
        listing, radius_km=radius_km, exclude_user_id=listing.publisher_id
    )
    count = len(nearby)
    rule_text = (
        f"Bu kaynak yakınınızdaki {count} kurum için uygundur."
        if count > 0
        else "Yakın çevrede uygun kurum bulunamadı; yarıçapı genişletmeyi deneyin."
    )

    source = "rules"
    suggestion = rule_text

    if use_demo_ai():
        return {
            "suggestion": suggestion,
            "source": "demo",
            "nearby_count": count,
            "nearby": nearby[:10],
            "radius_km": radius_km,
        }

    client = get_client()
    if client and count > 0:
        names = ", ".join(n["ad"] for n in nearby[:5])
        prompt = (
            "Sen AtıkPort kurumsal pazar asistanısın. Kısa tek Türkçe cümle yaz.\n"
            f"Kaynak: {listing.baslik} ({listing.kategori}). "
            f"Yakında {count} kurum var ({names}).\n"
            "Örnek üslup: 'Bu kaynak yakınınızdaki 4 kurum için uygundur.'\n"
            "Sadece cümleyi döndür."
        )
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = (result.text or "").strip().strip('"')
                if text:
                    suggestion = text.split("\n")[0][:300]
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Marketplace AI önerisi başarısız (%s): %s", model, exc)

    return {
        "suggestion": suggestion,
        "source": source,
        "nearby_count": count,
        "nearby": nearby[:10],
        "radius_km": radius_km,
    }


def _rule_match_explanation(listing: MarketplaceListing, matches: list[dict]) -> str:
    if not matches:
        return (
            f"“{listing.baslik}” için {listing.kategori} kategorisinde "
            "yakın ve uygun eşleşme bulunamadı."
        )
    top = matches[0]
    reasons = ", ".join(top.get("nedenler") or ["konum"])
    return (
        f"“{listing.baslik}” için en uygun eşleşme {top['ad']} "
        f"(skor {top['eslesme_skoru']}/100). Gerekçe: {reasons}."
    )


def generate_match_report(
    listing: MarketplaceListing,
    *,
    radius_km: float = 50,
    limit: int = 12,
) -> dict:
    """En uygun eşleşmeler + AI/kural açıklaması."""
    from services.demo_manager import (
        is_marketplace_data_sufficient,
        should_use_demo,
        use_demo_ai,
    )
    from services import demo_provider

    matches = best_matches(listing, radius_km=radius_km, limit=limit)
    if should_use_demo(
        "marketplace",
        real_data_sufficient=is_marketplace_data_sufficient(matches),
    ):
        matches = demo_provider.marketplace_matches(
            limit=limit, il=getattr(listing, "il", None), listing=listing
        )
        explanation = (
            f"“{listing.baslik}” için demo kurum eşleşmeleri gösteriliyor "
            f"(en uygun: {matches[0]['ad']}, skor {matches[0]['eslesme_skoru']}/100)."
        )
        return {
            "listing_id": listing.id,
            "listing_baslik": listing.baslik,
            "kategori": listing.kategori,
            "matches": matches,
            "explanation": explanation,
            "explanation_source": "demo",
            "nearby_suggestion": explanation,
            "nearby_source": "demo",
            "nearby_count": len(matches),
            "radius_km": radius_km,
            "source": "demo",
        }

    explanation = _rule_match_explanation(listing, matches)
    source = "rules"

    if use_demo_ai():
        nearby_fit = suggest_nearby_fit(listing, radius_km=radius_km)
        return {
            "listing_id": listing.id,
            "listing_baslik": listing.baslik,
            "kategori": listing.kategori,
            "matches": matches,
            "explanation": explanation,
            "explanation_source": "demo",
            "nearby_suggestion": nearby_fit.get("suggestion"),
            "nearby_source": "demo",
            "nearby_count": nearby_fit.get("nearby_count"),
            "radius_km": radius_km,
            "source": "demo",
        }

    client = get_client()
    if client and matches:
        compact = [
            {
                "ad": m["ad"],
                "skor": m["eslesme_skoru"],
                "mesafe_km": m.get("mesafe_km"),
                "nedenler": m.get("nedenler"),
            }
            for m in matches[:5]
        ]
        prompt = (
            "Sen AtıkPort B2B eşleştirme asistanısın. Verilen skorları değiştirme.\n"
            f"İlan: {listing.baslik} | Kategori: {listing.kategori} | "
            f"Miktar: {listing.miktar or '—'} {listing.birim or ''}\n"
            f"Eşleşmeler: {compact}\n"
            "2-3 kısa Türkçe cümleyle neden bu kurumların uygun olduğunu açıkla. "
            "Sadece metin döndür."
        )
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = (result.text or "").strip()
                if text:
                    explanation = text[:800]
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Marketplace eşleşme AI başarısız (%s): %s", model, exc)

    nearby_fit = suggest_nearby_fit(listing, radius_km=radius_km)
    return {
        "listing_id": listing.id,
        "listing_baslik": listing.baslik,
        "kategori": listing.kategori,
        "matches": matches,
        "explanation": explanation,
        "explanation_source": source,
        "nearby_suggestion": nearby_fit.get("suggestion"),
        "nearby_source": nearby_fit.get("source"),
        "nearby_count": nearby_fit.get("nearby_count"),
        "radius_km": radius_km,
    }


def platform_ai_overview(*, sample_listings: list[MarketplaceListing] | None = None) -> dict:
    """Platform genel AI açıklaması (sayfa için)."""
    from extensions import db
    from services.demo_manager import is_demo_mode, use_demo_ai
    from services.marketplace_b2b import demand_pool, list_suppliers, price_analysis

    pool = demand_pool()
    suppliers = list_suppliers(limit=20)
    prices = price_analysis()
    listings = list(sample_listings or [])
    if not listings and pool:
        from services.marketplace import resolve_listing

        first = resolve_listing(pool[0]["id"])
        if first:
            listings = [first]

    bullets = [
        f"Talep havuzunda {len(pool)} açık ilan bulunuyor.",
        f"Kayıtlı {len(suppliers)} tedarikçi / kurum listeleniyor.",
        f"{prices['ozet']['kategori_sayisi']} kategoride miktar analizi mevcut.",
    ]
    if listings:
        top = generate_match_report(listings[0])
        bullets.append(top["explanation"])

    source = "rules"
    explanation = " ".join(bullets)

    if is_demo_mode() or use_demo_ai():
        return {
            "explanation": explanation,
            "source": "demo",
            "bullets": bullets,
            "pool_count": len(pool),
            "supplier_count": len(suppliers),
            "price_summary": prices["ozet"],
        }

    client = get_client()
    if client:
        prompt = (
            "Sen AtıkPort B2B platform asistanısın. Aşağıdaki özeti 3 kısa Türkçe maddede "
            "yeniden yaz; sayı uydurma.\n"
            f"VERİ: {bullets}\n"
            "Her madde tek satır. Madde işareti kullan."
        )
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = (result.text or "").strip()
                if text:
                    explanation = text[:1000]
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Platform AI özeti başarısız (%s): %s", model, exc)

    return {
        "explanation": explanation,
        "source": source,
        "bullets": bullets,
        "pool_count": len(pool),
        "supplier_count": len(suppliers),
        "price_summary": prices["ozet"],
    }
