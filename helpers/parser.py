import re


def apply_vision_text_fallback(text: str, kategoriler, sonuc: dict) -> dict:
    """Fallback: AI yanıt metninden kategori ve risk skoru çıkarır."""
    text_lower = text.lower()

    for k in kategoriler:
        if k.lower() in text_lower:
            sonuc["kategori"] = k
            break

    scores = re.findall(r'\b(\d{1,3})\b', text)
    for s in scores:
        score = int(s)
        if 0 <= score <= 100:
            sonuc["risk_skoru"] = score
            break

    if "uygunsuz" in text_lower or "riskli" in text_lower or "zararlı" in text_lower:
        sonuc["guvenli"] = False
        sonuc["risk_skoru"] = max(sonuc["risk_skoru"], 50)

    return sonuc
