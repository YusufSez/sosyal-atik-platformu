"""Rozetler, seviyeler ve liderlik tablosu."""

from sqlalchemy import func

from constants import (
    ROZET_TANIMLARI,
    SEVIYE_ADLARI,
    SEVIYE_ESIKLERI,
    XP_FAVORI,
    XP_ILAN_OLUSTUR,
    XP_TESLIM,
)
from extensions import db
from models import Atik, CevreselEtki, Favori, Kaynak, KullaniciRozet, User
from services.notifications import bildirim_olustur


def seviye_hesapla(xp):
    xp = xp or 0
    seviye = 1
    for i, esik in enumerate(SEVIYE_ESIKLERI):
        if xp >= esik:
            seviye = i + 1
    seviye = min(seviye, len(SEVIYE_ADLARI))
    sonraki_esik = SEVIYE_ESIKLERI[seviye] if seviye < len(SEVIYE_ESIKLERI) else None
    onceki_esik = SEVIYE_ESIKLERI[seviye - 1] if seviye > 0 else 0
    return {
        "seviye": seviye,
        "ad": SEVIYE_ADLARI[seviye - 1],
        "xp": xp,
        "sonraki_esik": sonraki_esik,
        "onceki_esik": onceki_esik,
        "ilerleme_yuzde": _ilerleme_yuzde(xp, onceki_esik, sonraki_esik),
    }


def _ilerleme_yuzde(xp, onceki, sonraki):
    if sonraki is None:
        return 100
    aralik = sonraki - onceki
    if aralik <= 0:
        return 100
    return min(100, int(((xp - onceki) / aralik) * 100))


def xp_ekle(user, miktar):
    user.xp = (user.xp or 0) + miktar
    return seviye_hesapla(user.xp)


def _rozet_var_mi(user_id, kod):
    return KullaniciRozet.query.filter_by(user_id=user_id, rozet_kod=kod).first() is not None


def _rozet_ver(user, kod):
    if kod not in ROZET_TANIMLARI or _rozet_var_mi(user.id, kod):
        return None
    db.session.add(KullaniciRozet(user_id=user.id, rozet_kod=kod))
    tanim = ROZET_TANIMLARI[kod]
    bildirim_olustur(
        user.id,
        f"Yeni rozet: {tanim['ad']}",
        tanim["aciklama"],
        "rozet",
        link="/rozetlerim",
    )
    return tanim


def _teslim_sayisi(user_id):
    k = Kaynak.query.filter_by(user_id=user_id, ilan_durumu="Teslim Edildi").count()
    a = Atik.query.filter_by(user_id=user_id, ilan_durumu="Teslim Edildi").count()
    return k + a


def _toplam_co2e(user_id):
    return float(
        db.session.query(func.coalesce(func.sum(CevreselEtki.co2e_kg), 0))
        .filter_by(user_id=user_id)
        .scalar()
        or 0
    )


def rozetleri_kontrol_et(user):
    yeni = []
    toplam_ilan = Kaynak.query.filter_by(user_id=user.id).count() + Atik.query.filter_by(user_id=user.id).count()
    teslim = _teslim_sayisi(user.id)
    favori = Favori.query.filter_by(user_id=user.id).count()
    co2e = _toplam_co2e(user.id)

    kontroller = [
        ("ilk_ilan", toplam_ilan >= 1),
        ("ilk_teslim", teslim >= 1),
        ("teslim_3", teslim >= 3),
        ("teslim_10", teslim >= 10),
        ("guven_5", (user.guven_puani or 0) >= 5),
        ("cevresel_sampiyon", co2e >= 50),
        ("favori_meraklisi", favori >= 5),
    ]
    for kod, kosul in kontroller:
        if kosul and _rozet_ver(user, kod):
            yeni.append(kod)
    return yeni


def kullanici_rozet_listesi(user):
    kodlar = {r.rozet_kod for r in (user.rozetler or [])}
    sonuc = []
    for kod, tanim in ROZET_TANIMLARI.items():
        sonuc.append({
            "kod": kod,
            "kazanildi": kod in kodlar,
            **tanim,
        })
    return sonuc


def ilan_olusturuldu(user):
    xp_ekle(user, XP_ILAN_OLUSTUR)
    return rozetleri_kontrol_et(user)


def teslim_tamamlandi(user):
    xp_ekle(user, XP_TESLIM)
    return rozetleri_kontrol_et(user)


def favori_eklendi(user):
    xp_ekle(user, XP_FAVORI)
    return rozetleri_kontrol_et(user)


def liderlik_tablosu(limit=20):
    rows = (
        db.session.query(
            User.id,
            User.username,
            User.xp,
            User.guven_puani,
            User.il,
            func.coalesce(func.sum(CevreselEtki.co2e_kg), 0).label("co2e"),
        )
        .outerjoin(CevreselEtki, CevreselEtki.user_id == User.id)
        .group_by(User.id)
        .order_by(User.xp.desc(), func.coalesce(func.sum(CevreselEtki.co2e_kg), 0).desc())
        .limit(limit)
        .all()
    )
    sonuc = []
    for i, r in enumerate(rows, start=1):
        seviye = seviye_hesapla(r.xp or 0)
        sonuc.append({
            "sira": i,
            "user_id": r.id,
            "username": r.username,
            "xp": r.xp or 0,
            "guven_puani": r.guven_puani or 0,
            "il": r.il or "—",
            "co2e_kg": float(r.co2e or 0),
            "seviye_ad": seviye["ad"],
            "seviye": seviye["seviye"],
        })
    return sonuc


def kullanici_siralama(user_id):
    tablo = liderlik_tablosu(limit=500)
    for row in tablo:
        if row["user_id"] == user_id:
            return row["sira"]
    return None
