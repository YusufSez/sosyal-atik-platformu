import os

from flask import current_app

from constants import MAX_ILAN_FOTOSU
from extensions import db
from helpers import ai_tam_analiz, moderasyon_kontrol
from models import IlanResim
from utils import delete_picture, save_picture


def ilan_fotograf_listesi(ilan):
    fotolar = list(getattr(ilan, "fotograflar", None) or [])
    if fotolar:
        return [f.dosya for f in fotolar]
    resim = getattr(ilan, "resim", None)
    if resim and resim != "default.jpg":
        return [resim]
    return []


def kapak_resim(ilan):
    fotolar = ilan_fotograf_listesi(ilan)
    if fotolar:
        return fotolar[0]
    return getattr(ilan, "resim", None) or "default.jpg"


def sync_ilan_kapak(ilan):
    fotolar = ilan_fotograf_listesi(ilan)
    ilan.resim = fotolar[0] if fotolar else "default.jpg"


def save_ilan_fotograflari(file_list, mevcut_adet=0):
    """Formdan gelen dosyaları kaydeder. Mevcut + yeni toplam MAX_ILAN_FOTOSU'yu aşamaz."""
    files = [f for f in file_list if f and getattr(f, "filename", None)]
    if not files:
        return []
    if mevcut_adet + len(files) > MAX_ILAN_FOTOSU:
        raise ValueError(f"En fazla {MAX_ILAN_FOTOSU} fotoğraf yükleyebilirsiniz.")
    saved = []
    for f in files:
        saved.append(save_picture(f))
    return saved


def fotograflari_temizle(dosyalar):
    for dosya in dosyalar:
        delete_picture(dosya)


def ilan_fotograflari_ekle(ilan, tur, dosyalar):
    baslangic = len(ilan_fotograf_listesi(ilan))
    for i, dosya in enumerate(dosyalar):
        db.session.add(IlanResim(
            kaynak_id=ilan.id if tur == "kaynak" else None,
            atik_id=ilan.id if tur == "atik" else None,
            dosya=dosya,
            sira=baslangic + i,
        ))
    sync_ilan_kapak(ilan)


def ilan_fotograflari_sil(ilan, resim_idleri):
    if not resim_idleri:
        return
    for resim_id in resim_idleri:
        kayit = db.session.get(IlanResim, resim_id)
        if not kayit:
            continue
        if ilan.id != (kayit.kaynak_id or kayit.atik_id):
            continue
        delete_picture(kayit.dosya)
        db.session.delete(kayit)
    db.session.flush()
    db.session.expire(ilan, ["fotograflar"])
    _yeniden_sirala(ilan)
    sync_ilan_kapak(ilan)


def ensure_ilan_fotograflari(ilan, tur):
    """Eski ilanlarda yalnızca resim alanı doluysa IlanResim kaydı oluşturur."""
    if list(getattr(ilan, "fotograflar", None) or []):
        return False
    resim = getattr(ilan, "resim", None)
    if not resim or resim == "default.jpg":
        return False
    db.session.add(IlanResim(
        kaynak_id=ilan.id if tur == "kaynak" else None,
        atik_id=ilan.id if tur == "atik" else None,
        dosya=resim,
        sira=0,
    ))
    db.session.flush()
    db.session.expire(ilan, ["fotograflar"])
    return True


def _yeniden_sirala(ilan):
    fotolar = list(getattr(ilan, "fotograflar", None) or [])
    for i, foto in enumerate(sorted(fotolar, key=lambda x: x.sira)):
        foto.sira = i


def ai_analiz_ilk_foto(dosyalar, tur, aciklama, baslik=None, kategori_secim=None):
    if not dosyalar:
        return {"kategori": "Diğer", "durum": "Temiz", "risk_skoru": 0, "guvenli": True}
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], dosyalar[0])
    return ai_tam_analiz(
        path,
        tur=tur,
        aciklama=aciklama,
        baslik=baslik,
        kategori_secim=kategori_secim,
    )


def fotograf_moderasyonu(ai_sonuc, baslik, aciklama, dosyalar, tur="atik"):
    return moderasyon_kontrol(
        ai_sonuc,
        baslik=baslik,
        aciklama=aciklama,
        resim_var=bool(dosyalar),
        tur=tur,
    )


def moderasyon_reddedildi(ai_sonuc, dosyalar):
    from services.ilan_moderation import moderasyon_reddedildi as _reddedildi

    return _reddedildi(ai_sonuc, dosyalar, fotograflari_temizle)


def backfill_ilan_resimleri():
    from models import Atik, Kaynak

    eklenen = 0
    for kaynak in Kaynak.query.all():
        if kaynak.resim and kaynak.resim != "default.jpg" and not kaynak.fotograflar:
            db.session.add(IlanResim(kaynak_id=kaynak.id, dosya=kaynak.resim, sira=0))
            eklenen += 1
    for atik in Atik.query.all():
        if atik.resim and atik.resim != "default.jpg" and not atik.fotograflar:
            db.session.add(IlanResim(atik_id=atik.id, dosya=atik.resim, sira=0))
            eklenen += 1
    if eklenen:
        db.session.commit()
    return eklenen
