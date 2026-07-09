"""Kullanıcıya özel akıllı ilan önerileri."""

from services.ilan_moderation import public_ilan_base_filter

from models import Atik, Favori, Goruntulenme, Kaynak, User
from utils import is_varsayilan_konum, mesafe_hesapla


def _favori_kategoriler(user_id, tur):
    kategoriler = set()
    for fav in Favori.query.filter_by(user_id=user_id).all():
        if tur == "kaynak" and fav.kaynak:
            kategoriler.add(fav.kaynak.kategori)
        elif tur == "atik" and fav.atik:
            kategoriler.add(fav.atik.kategori or "Diğer")
    return kategoriler


def _goruntulenen_kategoriler(user_id, tur):
    kategoriler = set()
    for g in Goruntulenme.query.filter_by(user_id=user_id).order_by(Goruntulenme.timestamp.desc()).limit(30):
        if tur == "kaynak" and g.kaynak:
            kategoriler.add(g.kaynak.kategori)
        elif tur == "atik" and g.atik:
            kategoriler.add(g.atik.kategori or "Diğer")
    return kategoriler


def _ilan_skoru(ilan, user, favori_kat, goruntu_kat):
    skor = 0
    sahip = getattr(ilan, "sahip", None)
    if user.il and sahip and sahip.il == user.il:
        skor += 30
    if user.ilce and sahip and sahip.ilce == user.ilce:
        skor += 20
    if ilan.kategori in favori_kat:
        skor += 25
    elif ilan.kategori in goruntu_kat:
        skor += 15

    if (
        user.latitude is not None
        and user.longitude is not None
        and not is_varsayilan_konum(ilan.latitude, ilan.longitude)
    ):
        km = mesafe_hesapla(user.latitude, user.longitude, ilan.latitude, ilan.longitude)
        if km < 5:
            skor += 25
        elif km < 15:
            skor += 15
        elif km < 50:
            skor += 8

    if getattr(ilan, "tarih", None):
        skor += 5
    return skor


def kullanici_onerileri(user, tur="kaynak", limit=6):
    if not user or not getattr(user, "is_authenticated", True):
        return []

    favori_kat = _favori_kategoriler(user.id, tur)
    goruntu_kat = _goruntulenen_kategoriler(user.id, tur)

    if tur == "atik":
        ilanlar = (
            public_ilan_base_filter(Atik.query, Atik)
            .filter(Atik.user_id != user.id)
            .order_by(Atik.id.desc())
            .limit(80)
            .all()
        )
    else:
        ilanlar = (
            public_ilan_base_filter(Kaynak.query, Kaynak)
            .filter(Kaynak.user_id != user.id)
            .order_by(Kaynak.id.desc())
            .limit(80)
            .all()
        )

    skorlu = []
    for ilan in ilanlar:
        skor = _ilan_skoru(ilan, user, favori_kat, goruntu_kat)
        if skor <= 0:
            skor = 1
        skorlu.append((skor, ilan))

    skorlu.sort(key=lambda x: (-x[0], -x[1].id))
    return [
        {
            "ilan": ilan,
            "tur": tur,
            "skor": skor,
            "neden": _neden_metni(ilan, user, favori_kat, goruntu_kat),
        }
        for skor, ilan in skorlu[:limit]
    ]


def _neden_metni(ilan, user, favori_kat, goruntu_kat):
    nedenler = []
    sahip = getattr(ilan, "sahip", None)
    if user.il and sahip and sahip.il == user.il:
        nedenler.append("Aynı il")
    if ilan.kategori in favori_kat:
        nedenler.append("Favori kategorin")
    elif ilan.kategori in goruntu_kat:
        nedenler.append("İlgi alanın")
    if (
        user.latitude
        and user.longitude
        and not is_varsayilan_konum(ilan.latitude, ilan.longitude)
    ):
        km = mesafe_hesapla(user.latitude, user.longitude, ilan.latitude, ilan.longitude)
        if km < 15:
            nedenler.append(f"Yakın mesafe (~{km:.0f} km)")
    if not nedenler:
        nedenler.append("Popüler ilan")
    return ", ".join(nedenler)
