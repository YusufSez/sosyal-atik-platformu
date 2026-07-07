"""Belediye ve kurumlar için analiz ve ısı haritası verileri."""

from sqlalchemy import func, or_

from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from utils import is_varsayilan_konum


def _aktif_kaynak_query(il_filtre=None):
    q = Kaynak.query.filter(or_(Kaynak.ilan_durumu == "Aktif", Kaynak.ilan_durumu.is_(None)))
    if il_filtre:
        q = q.join(User, Kaynak.user_id == User.id).filter(User.il == il_filtre)
    return q


def _aktif_atik_query(il_filtre=None):
    q = Atik.query.filter(or_(Atik.ilan_durumu == "Aktif", Atik.ilan_durumu.is_(None)))
    if il_filtre:
        q = q.join(User, Atik.user_id == User.id).filter(User.il == il_filtre)
    return q


def kurum_ozet(il_filtre=None):
    kaynak_q = _aktif_kaynak_query(il_filtre)
    atik_q = _aktif_atik_query(il_filtre)
    teslim_kaynak = Kaynak.query.filter_by(ilan_durumu="Teslim Edildi")
    teslim_atik = Atik.query.filter_by(ilan_durumu="Teslim Edildi")
    if il_filtre:
        teslim_kaynak = teslim_kaynak.join(User).filter(User.il == il_filtre)
        teslim_atik = teslim_atik.join(User).filter(User.il == il_filtre)

    etki_q = db.session.query(
        func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
        func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
        func.count(CevreselEtki.id),
    )
    if il_filtre:
        etki_q = etki_q.join(User, CevreselEtki.user_id == User.id).filter(User.il == il_filtre)
    co2e, atik_kg, teslim_etki = etki_q.one()

    kullanici_q = User.query
    if il_filtre:
        kullanici_q = kullanici_q.filter(User.il == il_filtre)

    return {
        "kullanici": kullanici_q.count(),
        "aktif_kaynak": kaynak_q.count(),
        "aktif_atik": atik_q.count(),
        "teslim": teslim_kaynak.count() + teslim_atik.count(),
        "co2e_kg": float(co2e or 0),
        "atik_kg": float(atik_kg or 0),
        "teslim_etki": int(teslim_etki or 0),
        "il_filtre": il_filtre,
    }


def ilce_kirilimi(il_filtre=None):
    from collections import defaultdict

    counts = defaultdict(int)
    for model in (Kaynak, Atik):
        q = (
            db.session.query(User.ilce, func.count(model.id))
            .join(model, model.user_id == User.id)
            .filter(User.ilce.isnot(None), User.ilce != "")
        )
        if il_filtre:
            q = q.filter(User.il == il_filtre)
        for ilce, cnt in q.group_by(User.ilce).all():
            counts[ilce] += int(cnt or 0)
    return sorted(
        [{"ilce": k, "adet": v} for k, v in counts.items()],
        key=lambda x: -x["adet"],
    )[:15]


def kategori_dagilimi(il_filtre=None, tur="kaynak"):
    if tur == "atik":
        q = db.session.query(Atik.kategori, func.count(Atik.id)).group_by(Atik.kategori)
        if il_filtre:
            q = q.join(User, Atik.user_id == User.id).filter(User.il == il_filtre)
    else:
        q = db.session.query(Kaynak.kategori, func.count(Kaynak.id)).group_by(Kaynak.kategori)
        if il_filtre:
            q = q.join(User, Kaynak.user_id == User.id).filter(User.il == il_filtre)
    return [{"kategori": r[0] or "Diğer", "adet": int(r[1])} for r in q.order_by(func.count().desc()).all()]


def mevcut_iller():
    rows = (
        db.session.query(User.il)
        .filter(User.il.isnot(None), User.il != "")
        .distinct()
        .order_by(User.il)
        .all()
    )
    return [r[0] for r in rows]


def isi_haritasi_noktalari(il_filtre=None, tur=None):
    """Leaflet heat için [lat, lng, yogunluk] listesi."""
    noktalar = []

    def _ekle(ilanlar, agirlik=1.0):
        for ilan in ilanlar:
            if is_varsayilan_konum(ilan.latitude, ilan.longitude):
                continue
            noktalar.append([ilan.latitude, ilan.longitude, agirlik])

    if tur in (None, "kaynak"):
        _ekle(_aktif_kaynak_query(il_filtre).all(), 0.8)
    if tur in (None, "atik"):
        _ekle(_aktif_atik_query(il_filtre).all(), 1.0)

    etki_q = CevreselEtki.query
    if il_filtre:
        etki_q = etki_q.join(User).filter(User.il == il_filtre)
    for etki in etki_q.all():
        ilan = etki.kaynak or etki.atik
        if not ilan or is_varsayilan_konum(ilan.latitude, ilan.longitude):
            continue
        yogunluk = min(2.0, 0.5 + (etki.co2e_kg or 0) / 30)
        noktalar.append([ilan.latitude, ilan.longitude, yogunluk])

    return noktalar
