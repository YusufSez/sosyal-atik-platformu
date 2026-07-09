"""İlan moderasyon kararlarını modele uygular ve admin bildirimi gönderir."""

from sqlalchemy import or_

from constants import (
    AI_RISK_REJECT_MIN,
    MODERATION_STATUS_APPROVED,
    MODERATION_STATUS_PENDING_REVIEW,
    MODERATION_STATUS_REJECTED,
)
from extensions import db
from models import User
from services.ai_moderation import moderation_decision
from services.notifications import bildirim_olustur


def ilan_moderasyon_alanlarini_uygula(ilan, ai_sonuc: dict) -> dict:
    """AI sonucunu ilan kaydına yazar; karar özetini döndürür."""
    risk = int(ai_sonuc.get("risk_skoru", 0))
    karar = moderation_decision(risk, uygunsuz=bool(ai_sonuc.get("uygunsuz", False)))

    status = ai_sonuc.get("moderation_status") or karar["moderation_status"]
    ilan.moderation_status = status
    ilan.ai_risk_score = risk
    ilan.moderation_reason = ai_sonuc.get("reason") or ""

    return karar


def moderasyon_reddedildi(ai_sonuc: dict, dosyalar, temizle_fn) -> bool:
    """Yayın engeli: rejected veya yüksek risk (90+) inceleme bekleyen içerik."""
    risk = int(ai_sonuc.get("risk_skoru", 0))
    uygunsuz = bool(ai_sonuc.get("uygunsuz", False))
    karar = moderation_decision(risk, uygunsuz=uygunsuz)
    if karar["publish"]:
        return False
    if dosyalar:
        temizle_fn(dosyalar)
    return True


def admin_moderasyon_bildir(
    ilan,
    tur: str,
    ai_sonuc: dict,
    karar: dict,
    kullanici,
) -> None:
    if not karar.get("notify_admin"):
        return

    baslik = getattr(ilan, "baslik", "İlan")
    risk = ai_sonuc.get("risk_skoru", 0)
    reason = ai_sonuc.get("reason") or "AI moderasyon incelemesi"
    tur_label = "Atık" if tur == "atik" else "Kaynak"

    if karar.get("requires_review"):
        if karar.get("high_risk_review"):
            msg = f"{tur_label} ilanı yüksek risk incelemesi bekliyor (Risk: {risk}/100). {reason}"
        else:
            msg = f"{tur_label} ilanı inceleme bekliyor (Risk: {risk}/100). {reason}"
    else:
        msg = f"{tur_label} ilanı yayınlandı — düşük-orta risk (Risk: {risk}/100). {reason}"

    link = None
    if tur == "atik" and hasattr(ilan, "id") and ilan.id:
        link = f"/atik_detay/{ilan.id}"
    elif tur == "kaynak" and hasattr(ilan, "id") and ilan.id:
        link = f"/kaynak_detay/{ilan.id}"

    admins = User.query.filter(User.is_admin.is_(True), User.is_deactivated.is_(False)).all()
    for admin in admins:
        bildirim_olustur(
            admin.id,
            "AI Moderasyon",
            f"{kullanici.username}: {baslik} — {msg}",
            "moderasyon",
            link,
        )


def public_ilan_base_filter(query, model):
    """Yayında görünen ilanlar — reddedilenler hariç."""
    return query.filter(
        or_(model.ilan_durumu == "Aktif", model.ilan_durumu.is_(None)),
        model.moderation_status != MODERATION_STATUS_REJECTED,
    )


def ilan_metin_moderasyonu(baslik, aciklama, tur="atik"):
    """Görsel olmadan metin moderasyonu (düzenleme akışı)."""
    from helpers import moderasyon_kontrol

    return moderasyon_kontrol(
        {"risk_skoru": 0, "guvenli": True, "moderation_status": MODERATION_STATUS_APPROVED},
        baslik=baslik,
        aciklama=aciklama,
        resim_var=False,
        tur=tur,
    )
