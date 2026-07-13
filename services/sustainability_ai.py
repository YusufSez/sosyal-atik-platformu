"""Sustainability Scoring — AI önerileri."""

from __future__ import annotations

import logging

from helpers.ai import FREE_MODEL, FREE_MODEL_BACKUP, get_client
from services.sustainability_scoring import score_region

logger = logging.getLogger("atikport.sustainability_ai")

_FOCUS_CATEGORIES = ("Elektronik", "Bitkisel Yağ", "Plastik", "Organik", "Cam", "Metal")


def _rule_suggestions(scored: dict) -> list[str]:
    tips: list[str] = []
    criteria = sorted(scored.get("criteria") or [], key=lambda c: c["score"])
    raw = scored.get("raw") or {}
    metrics = scored.get("metrics") or {}
    shares = metrics.get("kategori_paylari") or {}

    for c in criteria[:3]:
        key = c["key"]
        if key == "geri_donusum" and c["score"] < 70:
            tips.append("Puanınızı artırmak için atık teslim (geri dönüşüm) oranını yükseltin.")
        elif key == "teslim" and c["score"] < 70:
            tips.append("Puanınızı artırmak için ilan teslim oranını yükseltin.")
        elif key == "katilim" and c["score"] < 50:
            tips.append("Vatandaş katılımını artırmak için mahalle bazlı bilinçlendirme kampanyaları düzenleyin.")
        elif key == "kaynak_paylasimi" and c["score"] < 60:
            tips.append("Kaynak paylaşımı performansını artırmak için ikinci el ilan teşviklerini güçlendirin.")
        elif key == "karbon" and c["score"] < 60:
            tips.append("Karbon azaltımını yükseltmek için teslim edilen atık ve kaynak hacmini artırın.")
        elif key == "teslim_suresi" and c["score"] < 70:
            tips.append("Ortalama teslim süresini kısaltmak için eşleştirme ve lojistik süreçlerini hızlandırın.")
        elif key == "ai_dogruluk" and c["score"] < 60:
            tips.append("İlan açıklama ve fotoğraf kalitesini artırarak AI moderasyon doğruluğunu iyileştirin.")

    # Kategori odaklı örnekler (kullanıcı isteği)
    elektronik = shares.get("Elektronik", 0)
    yag = shares.get("Bitkisel Yağ", 0)
    if elektronik < 10 and (metrics.get("atik_teslim") or 0) > 0:
        tips.append("Puanınızı artırmak için elektronik atık toplama oranını yükseltin.")
    elif elektronik < 5:
        tips.append("Puanınızı artırmak için elektronik atık toplama oranını yükseltin.")

    if yag < 8:
        tips.append("Bitkisel yağ toplama performansı düşüktür.")

    # En zayıf kategori (payı düşük olan odak grup)
    if shares:
        weakest = min(_FOCUS_CATEGORIES, key=lambda k: shares.get(k, 0))
        if shares.get(weakest, 0) < 12 and weakest not in ("Elektronik", "Bitkisel Yağ"):
            tips.append(f"{weakest} kategorisinde toplama performansı düşük; hedefli kampanya önerilir.")
    elif raw.get("geri_donusum", 0) < 40:
        tips.append("Puanınızı artırmak için elektronik atık toplama oranını yükseltin.")
        tips.append("Bitkisel yağ toplama performansı düşüktür.")

    # Tekrarları temizle, en fazla 5 öneri
    seen = set()
    unique = []
    for t in tips:
        if t not in seen:
            seen.add(t)
            unique.append(t)
    return unique[:5] or [
        "Sürdürülebilirlik puanınızı korumak için mevcut teslim ve geri dönüşüm temposunu sürdürün."
    ]


def generate_sustainability_suggestions(
    *,
    il: str | None = None,
    ilce: str | None = None,
    scored: dict | None = None,
) -> dict:
    scored = scored or score_region(il=il, ilce=ilce)
    rules = _rule_suggestions(scored)
    source = "rules"
    suggestions = list(rules)

    client = get_client()
    if client:
        weak = ", ".join(
            f"{c['label']}={c['score']}"
            for c in sorted(scored.get("criteria") or [], key=lambda x: x["score"])[:3]
        )
        prompt = (
            "Sen AtıkPort sürdürülebilirlik asistanısın. Türkçe, kısa, eyleme dönük 3 öneri yaz.\n"
            f"Belediye puanı: {scored.get('puan')} ({scored.get('grade')}). "
            f"Zayıf kriterler: {weak}.\n"
            "Örnek üslup:\n"
            "- Puanınızı artırmak için elektronik atık toplama oranını yükseltin.\n"
            "- Bitkisel yağ toplama performansı düşüktür.\n"
            "Her satırda bir öneri; numara veya madde işareti kullanma."
        )
        for model in (FREE_MODEL, FREE_MODEL_BACKUP):
            try:
                from google.genai import types

                result = client.models.generate_content(
                    model=model,
                    contents=[types.Content(parts=[types.Part(text=prompt)])],
                )
                text = (result.text or "").strip()
                lines = [ln.strip(" -•\t") for ln in text.splitlines() if ln.strip()]
                lines = [ln for ln in lines if len(ln) > 10][:5]
                if lines:
                    suggestions = lines
                    source = f"gemini:{model}"
                    break
            except Exception as exc:
                logger.warning("Sustainability AI önerisi başarısız (%s): %s", model, exc)

    return {
        "suggestions": suggestions,
        "source": source,
        "puan": scored.get("puan"),
        "grade": scored.get("grade"),
    }
