"""Kurumsal marketplace AI önerileri."""

from __future__ import annotations

import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from models import MarketplaceListing
from services.marketplace import nearby_institutions

logger = logging.getLogger("atikport.marketplace_ai")


def suggest_nearby_fit(listing: MarketplaceListing, *, radius_km: float = 50) -> dict:
    """
    Yakındaki kurum sayısına göre öneri üretir.
    Örnek: 'Bu kaynak yakınınızdaki 4 kurum için uygundur.'
    """
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
