"""Mesaj içerik denetimi — öncelikli yapay zeka, yedek kelime listesi."""

import re

from helpers import ai_mesaj_moderasyon

# API kullanılamadığında hızlı yedek filtre
ARGO_KELIMELER = (
    "amk",
    "aq",
    "orospu",
    "piç",
    "pic",
    "sik",
    "sikeyim",
    "siktir",
    "göt",
    "got",
    "yarrak",
    "yarrrak",
    "kahpe",
    "pezevenk",
    "oc",
    "oç",
    "salak",
    "aptal",
)

_ARGO_PATTERNS = [
    re.compile(r"(?<![\w])" + re.escape(kelime) + r"(?![\w])", re.IGNORECASE)
    for kelime in ARGO_KELIMELER
]

_UYGUNSUZ_MESAJ = (
    "Mesajınız uygunsuz ifadeler içeriyor. Lütfen saygılı bir dil kullanın."
)
_AI_UYGUNSUZ_MESAJ = (
    "Mesajınız yapay zeka içerik denetimi tarafından uygunsuz bulundu. "
    "Lütfen saygılı bir dil kullanın."
)


def argo_iceriyor(metin: str) -> bool:
    if not metin:
        return False
    for pattern in _ARGO_PATTERNS:
        if pattern.search(metin):
            return True
    return False


def _liste_ile_kontrol(metin: str) -> tuple[bool, str]:
    if argo_iceriyor(metin):
        return False, _UYGUNSUZ_MESAJ
    return True, ""


def mesaj_uygun_mu(metin: str) -> tuple[bool, str]:
    """
    Mesaj gönderim öncesi denetim.
    1) Gemini AI moderasyonu (GEMINI_API_KEY varsa)
    2) API yoksa veya hata olursa kelime listesi yedeği
    """
    metin = (metin or "").strip()
    if not metin:
        return True, ""

    ai_sonuc = ai_mesaj_moderasyon(metin)

    # Kelime listesi her zaman uygulanır (AI onaylasa bile) — prompt injection bypass önlemi.
    liste_ok, liste_msg = _liste_ile_kontrol(metin)
    if not liste_ok:
        return False, liste_msg

    if ai_sonuc.get("kaynak") == "ai":
        if not ai_sonuc.get("uygun", True):
            return False, ai_sonuc.get("mesaj") or _AI_UYGUNSUZ_MESAJ
        return True, ""

    return True, ""


def yorum_uygun_mu(metin: str) -> tuple[bool, str]:
    """Yorumlar için mesaj moderasyonu ile aynı denetim."""
    return mesaj_uygun_mu(metin)
