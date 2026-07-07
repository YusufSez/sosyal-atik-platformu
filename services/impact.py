"""Çevresel etki hesaplama ve raporlama servisi."""

from sqlalchemy import case, func

from constants import (
    ETKI_KATSAYILARI_ATIK,
    ETKI_KATSAYILARI_KAYNAK,
    HESAPLAMA_VERSIYONU,
)
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User


def hesapla_etki(tur, kategori):
    kategori = kategori or "Diğer"
    if tur == "kaynak":
        katsayi = ETKI_KATSAYILARI_KAYNAK.get(kategori, ETKI_KATSAYILARI_KAYNAK["Diğer"])
        co2e = katsayi["co2e_kg"]
        su = katsayi["su_litre"]
        atik_kg = 0.0
        dongusel = round(co2e * 10) + 50
    else:
        katsayi = ETKI_KATSAYILARI_ATIK.get(kategori, ETKI_KATSAYILARI_ATIK["Diğer"])
        co2e = katsayi["co2e_kg"]
        su = 0.0
        atik_kg = katsayi["atik_kg"]
        dongusel = round(co2e * 10) + 30

    return {
        "co2e_kg": float(co2e),
        "su_litre": float(su),
        "atik_kg": float(atik_kg),
        "dongusel_skor": int(dongusel),
    }


def _etki_var_mi(ilan, tur):
    if tur == "kaynak":
        return CevreselEtki.query.filter_by(kaynak_id=ilan.id).first() is not None
    return CevreselEtki.query.filter_by(atik_id=ilan.id).first() is not None


def kaydet_etki(ilan, tur):
    if _etki_var_mi(ilan, tur):
        return None

    etki = hesapla_etki(tur, ilan.kategori)
    kayit = CevreselEtki(
        user_id=ilan.user_id,
        kaynak_id=ilan.id if tur == "kaynak" else None,
        atik_id=ilan.id if tur == "atik" else None,
        tur=tur,
        kategori=ilan.kategori or "Diğer",
        co2e_kg=etki["co2e_kg"],
        su_litre=etki["su_litre"],
        atik_kg=etki["atik_kg"],
        dongusel_skor=etki["dongusel_skor"],
        hesaplama_versiyonu=HESAPLAMA_VERSIYONU,
    )
    db.session.add(kayit)
    return kayit


def teslim_sonrasi_islem(ilan, tur):
    """Teslim Edildi geçişinde etki kaydı ve güven puanı artışı."""
    if _etki_var_mi(ilan, tur):
        return None

    sahip = db.session.get(User, ilan.user_id)
    if sahip:
        sahip.guven_puani = (sahip.guven_puani or 0) + 1

    return kaydet_etki(ilan, tur)


def teslim_geri_al(ilan, tur):
    """Teslim Edildi'den çıkıldığında etki kaydını ve güven puanını geri al."""
    if tur == "kaynak":
        kayit = CevreselEtki.query.filter_by(kaynak_id=ilan.id).first()
    else:
        kayit = CevreselEtki.query.filter_by(atik_id=ilan.id).first()

    if not kayit:
        return None

    db.session.delete(kayit)
    sahip = db.session.get(User, ilan.user_id)
    if sahip and (sahip.guven_puani or 0) > 0:
        sahip.guven_puani -= 1
    return kayit


def ilan_durum_etki_sync(ilan, tur, eski_durum, yeni_durum):
    """İlan durumu değişince etkiyi ekle veya geri al. ('eklendi'|'silindi', kayit) veya None."""
    eski = eski_durum or "Aktif"
    if eski != "Teslim Edildi" and yeni_durum == "Teslim Edildi":
        kayit = teslim_sonrasi_islem(ilan, tur)
        return ("eklendi", kayit) if kayit else None
    if eski == "Teslim Edildi" and yeni_durum != "Teslim Edildi":
        kayit = teslim_geri_al(ilan, tur)
        return ("silindi", kayit) if kayit else None
    return None


def _aggregate_ozet(filter_clause=None):
    q = db.session.query(
        func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
        func.coalesce(func.sum(CevreselEtki.su_litre), 0),
        func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
        func.coalesce(func.sum(CevreselEtki.dongusel_skor), 0),
        func.count(CevreselEtki.id),
        func.coalesce(func.sum(case((CevreselEtki.tur == "kaynak", 1), else_=0)), 0),
    )
    if filter_clause is not None:
        q = q.filter(filter_clause)
    return q.one()


def _ozet_dict(row):
    co2e, su, atik_kg, dongusel, teslim, kaynak_adet = row
    return {
        "co2e_kg": float(co2e or 0),
        "su_litre": float(su or 0),
        "atik_kg": float(atik_kg or 0),
        "dongusel_skor": int(dongusel or 0),
        "teslim_sayisi": int(teslim or 0),
        "yeniden_kullanim": int(kaynak_adet or 0),
        "hesaplama_versiyonu": HESAPLAMA_VERSIYONU,
        "tahmini": True,
    }


def platform_ozeti():
    return _ozet_dict(_aggregate_ozet())


def kullanici_ozeti(user_id):
    return _ozet_dict(_aggregate_ozet(CevreselEtki.user_id == user_id))


def kullanici_son_teslimler(user_id, limit=10):
    return (
        CevreselEtki.query.filter_by(user_id=user_id)
        .order_by(CevreselEtki.timestamp.desc())
        .limit(limit)
        .all()
    )


def kategori_kirilimi():
    rows = (
        db.session.query(
            CevreselEtki.kategori,
            CevreselEtki.tur,
            func.sum(CevreselEtki.co2e_kg),
            func.sum(CevreselEtki.atik_kg),
            func.count(CevreselEtki.id),
        )
        .group_by(CevreselEtki.kategori, CevreselEtki.tur)
        .order_by(func.sum(CevreselEtki.co2e_kg).desc())
        .all()
    )
    return [
        {
            "kategori": r[0],
            "tur": r[1],
            "co2e_kg": float(r[2] or 0),
            "atik_kg": float(r[3] or 0),
            "adet": int(r[4] or 0),
        }
        for r in rows
    ]


def il_kirilimi():
    rows = (
        db.session.query(
            User.il,
            func.sum(CevreselEtki.co2e_kg),
            func.count(CevreselEtki.id),
        )
        .join(User, CevreselEtki.user_id == User.id)
        .group_by(User.il)
        .order_by(func.sum(CevreselEtki.co2e_kg).desc())
        .all()
    )
    return [
        {
            "il": r[0] or "Belirtilmemiş",
            "co2e_kg": float(r[1] or 0),
            "adet": int(r[2] or 0),
        }
        for r in rows
    ]


def aylik_kirilim(user_id=None, ay_sayisi=6):
    from calendar import monthrange
    from datetime import datetime

    from utils import tr_time

    now = tr_time()
    aylar = []
    for offset in range(ay_sayisi - 1, -1, -1):
        month = now.month - offset
        year = now.year
        while month <= 0:
            month += 12
            year -= 1
        while month > 12:
            month -= 12
            year += 1
        ay_bas = datetime(year, month, 1)
        last_day = monthrange(year, month)[1]
        ay_son = datetime(year, month, last_day, 23, 59, 59)
        q = db.session.query(func.coalesce(func.sum(CevreselEtki.co2e_kg), 0)).filter(
            CevreselEtki.timestamp >= ay_bas,
            CevreselEtki.timestamp <= ay_son,
        )
        if user_id is not None:
            q = q.filter(CevreselEtki.user_id == user_id)
        aylar.append({
            "etiket": ay_bas.strftime("%b %Y"),
            "co2e_kg": float(q.scalar() or 0),
        })
    return aylar


def backfill_mevcut_teslimler():
    count = 0
    for kaynak in Kaynak.query.filter_by(ilan_durumu="Teslim Edildi").all():
        if kaydet_etki(kaynak, "kaynak"):
            count += 1
    for atik in Atik.query.filter_by(ilan_durumu="Teslim Edildi").all():
        if kaydet_etki(atik, "atik"):
            count += 1
    db.session.commit()
    return count


def sync_etki_ilan_durumu():
    """Teslim Edildi olmayan ilanlara bağlı etki kayıtlarını temizler."""
    silinen = 0
    for kayit in CevreselEtki.query.filter(CevreselEtki.kaynak_id.isnot(None)).all():
        kaynak = db.session.get(Kaynak, kayit.kaynak_id)
        if not kaynak or kaynak.ilan_durumu != "Teslim Edildi":
            db.session.delete(kayit)
            silinen += 1
    for kayit in CevreselEtki.query.filter(CevreselEtki.atik_id.isnot(None)).all():
        atik = db.session.get(Atik, kayit.atik_id)
        if not atik or atik.ilan_durumu != "Teslim Edildi":
            db.session.delete(kayit)
            silinen += 1
    if silinen:
        db.session.commit()
    return silinen


def format_etki_sayi(value, birim=""):
    """UI için sayı formatlama."""
    value = float(value or 0)
    if value >= 1_000_000:
        text = f"{value / 1_000_000:.1f}M"
    elif value >= 10_000:
        text = f"{value / 1_000:.1f}B"
    elif value >= 1_000:
        text = f"{value / 1_000:.1f}K"
    elif value == int(value):
        text = str(int(value))
    else:
        text = f"{value:.1f}"
    return f"{text} {birim}".strip()
