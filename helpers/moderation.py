import os

from constants import AI_RISK_AUTO_APPROVE_MAX, AI_RISK_REJECT_MIN
from utils import env_to_bool

from .ai import ai_metin_moderasyon, ai_tam_analiz

_ATIK_ANAHTAR_KELIMELER = ()  # services.ai_moderation.RECYCLABLE_WHITELIST_TERMS kullanılır


def _atik_baglami_var(baslik=None, aciklama=None, kategori_secim=None, ai_kategori=None):
    from services.ai_moderation import detect_recyclable_context
    return detect_recyclable_context(baslik, aciklama, kategori_secim, ai_kategori, tur="atik")


def _atik_moderasyon_duzelt(sonuc, baslik=None, aciklama=None, kategori_secim=None):
    from services.ai_moderation import apply_recyclable_adjustment
    return apply_recyclable_adjustment(
        sonuc, baslik=baslik, aciklama=aciklama, kategori_secim=kategori_secim, tur="atik"
    )


def moderasyon_kontrol(ai_sonuc, baslik=None, aciklama=None, resim_var=False, tur="atik"):
    """Görsel + metin moderasyonunu birleştirir."""
    from services.ai_moderation import apply_recyclable_adjustment, resolve_moderation_status
    from constants import MODERATION_STATUS_REJECTED

    from .ai import logger

    fail_open = env_to_bool(os.getenv("AI_UPLOAD_FAIL_OPEN"), default=False)
    if resim_var and ai_sonuc.get("hata"):
        if fail_open:
            logger.warning("Görsel moderasyon fail-open: %s", ai_sonuc["hata"])
            ai_sonuc["guvenli"] = True
            ai_sonuc["risk_skoru"] = min(ai_sonuc.get("risk_skoru", 0), 40)
        else:
            ai_sonuc["guvenli"] = False
            ai_sonuc["risk_skoru"] = max(ai_sonuc.get("risk_skoru", 0), 80)
    if baslik or aciklama:
        metin_sonuc = ai_metin_moderasyon(baslik, aciklama, tur=tur)
        ai_sonuc["risk_skoru"] = max(ai_sonuc.get("risk_skoru", 0), metin_sonuc["risk_skoru"])
        if metin_sonuc.get("reason"):
            ai_sonuc["reason"] = metin_sonuc["reason"]
        if metin_sonuc.get("is_recyclable"):
            ai_sonuc["is_recyclable"] = True
        if metin_sonuc.get("purpose"):
            ai_sonuc["purpose"] = metin_sonuc["purpose"]
        if metin_sonuc.get("uygunsuz"):
            ai_sonuc["uygunsuz"] = True
        if metin_sonuc.get("hata"):
            ai_sonuc["hata"] = metin_sonuc["hata"]
    if "initial_risk" not in ai_sonuc:
        ai_sonuc["initial_risk"] = int(ai_sonuc.get("risk_skoru", 0))
    ai_sonuc = apply_recyclable_adjustment(
        ai_sonuc, baslik=baslik, aciklama=aciklama, tur=tur
    )
    uygunsuz = bool(ai_sonuc.get("uygunsuz", False))
    ai_sonuc["moderation_status"] = resolve_moderation_status(
        int(ai_sonuc.get("risk_skoru", 0)), uygunsuz=uygunsuz
    )
    ai_sonuc["guvenli"] = ai_sonuc["moderation_status"] != MODERATION_STATUS_REJECTED
    from services.ai_moderation import enrich_explainability
    ai_sonuc = enrich_explainability(
        ai_sonuc,
        baslik=baslik,
        aciklama=aciklama,
        tur=tur,
        initial_risk=int(ai_sonuc.get("initial_risk", ai_sonuc.get("risk_skoru", 0))),
    )
    return ai_sonuc


def gelismis_moderasyon(resim_yolu, aciklama=None):
    """
    Kapsamlı moderasyon kontrolü yapar.
    (status): guvenli, şüpheli, riskli
    """
    sonuc = ai_tam_analiz(resim_yolu, "kaynak", aciklama)

    if sonuc["risk_skoru"] < AI_RISK_AUTO_APPROVE_MAX:
        return {
            "status": "guvenli",
            "skor": sonuc["risk_skoru"],
            "mesaj": "İçerik güvenli görünüyor."
        }
    elif sonuc["risk_skoru"] < AI_RISK_REJECT_MIN:
        return {
            "status": "suspicious",
            "skor": sonuc["risk_skoru"],
            "mesaj": "İçerik şüpheli görünüyor, manuel inceleme önerilir."
        }
    else:
        return {
            "status": "riskli",
            "skor": sonuc["risk_skoru"],
            "mesaj": "İçerik riskli bulundu, paylaşım engellendi."
        }
