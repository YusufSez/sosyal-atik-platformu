"""Belediye yönetim paneli analitik servisleri."""

from __future__ import annotations

from collections import defaultdict
from datetime import timedelta

from sqlalchemy import func, or_

from constants import MUNICIPALITY_CATEGORY_GROUPS
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from services.ilan_moderation import public_ilan_base_filter
from utils import is_varsayilan_konum, utc_now


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    value = value.strip()
    return value or None


def _geo_filters(il=None, ilce=None, mahalle=None):
    filters = []
    il = _norm(il)
    ilce = _norm(ilce)
    mahalle = _norm(mahalle)
    if il:
        filters.append(User.il == il)
    if ilce:
        filters.append(User.ilce == ilce)
    if mahalle:
        filters.append(User.mahalle == mahalle)
    return filters


def _join_user_filter(query, model, geo):
    if not geo:
        return query
    return query.join(User, model.user_id == User.id).filter(*geo)


def _aktif_query(model, geo):
    q = public_ilan_base_filter(model.query, model)
    return _join_user_filter(q, model, geo)


def _teslim_query(model, geo):
    q = model.query.filter_by(ilan_durumu="Teslim Edildi")
    return _join_user_filter(q, model, geo)


def _day_start():
    now = utc_now()
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def normalize_municipality_category(raw: str | None) -> str:
    """Atık/kaynak kategorilerini belediye grafik gruplarına map eder."""
    if not raw:
        return "Diğer"
    key = raw.strip().casefold()
    mapping = {
        "plastik": "Plastik",
        "cam": "Cam",
        "metal": "Metal",
        "elektronik": "Elektronik",
        "elektronik atık": "Elektronik",
        "organik": "Organik",
        "organik atık": "Organik",
        "bitkisel yağ": "Bitkisel Yağ",
        "bitkisel yag": "Bitkisel Yağ",
    }
    return mapping.get(key, "Diğer")


def municipality_dashboard(il=None, ilce=None, mahalle=None) -> dict:
    from sqlalchemy import case

    geo = _geo_filters(il, ilce, mahalle)
    day0 = _day_start()

    bugun_kaynak = _aktif_query(Kaynak, geo).filter(Kaynak.tarih >= day0).count()
    bugun_atik = _aktif_query(Atik, geo).filter(Atik.tarih >= day0).count()
    bugun_kaynak_all = Kaynak.query.filter(Kaynak.tarih >= day0)
    bugun_atik_all = Atik.query.filter(Atik.tarih >= day0)
    if geo:
        bugun_kaynak_all = bugun_kaynak_all.join(User, Kaynak.user_id == User.id).filter(*geo)
        bugun_atik_all = bugun_atik_all.join(User, Atik.user_id == User.id).filter(*geo)

    aktif_kaynak = _aktif_query(Kaynak, geo).count()
    aktif_atik = _aktif_query(Atik, geo).count()
    teslim = _teslim_query(Kaynak, geo).count() + _teslim_query(Atik, geo).count()

    etki_q = db.session.query(
        func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
        func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
        func.coalesce(
            func.sum(case((CevreselEtki.tur == "kaynak", CevreselEtki.dongusel_skor), else_=0)),
            0,
        ),
        func.count(CevreselEtki.id),
    )
    if geo:
        etki_q = etki_q.join(User, CevreselEtki.user_id == User.id).filter(*geo)
    atik_kg, co2e_kg, kaynak_skor, etki_adet = etki_q.one()

    kaynak_teslim = _teslim_query(Kaynak, geo).count()
    atik_teslim = _teslim_query(Atik, geo).count()

    kullanici_q = User.query
    if geo:
        kullanici_q = kullanici_q.filter(*geo)
    gunluk_kullanici = kullanici_q.filter(
        or_(User.last_seen >= day0, User.last_login_at >= day0)
    ).count()

    aktif_kurum_q = User.query.filter(User.is_kurum.is_(True))
    if geo:
        aktif_kurum_q = aktif_kurum_q.filter(*geo)

    ortalama_teslim = _ortalama_teslim_suresi_gun(geo)

    return {
        "bugun_ilan": bugun_kaynak_all.count() + bugun_atik_all.count(),
        "bugun_aktif_ilan": bugun_kaynak + bugun_atik,
        "toplam_aktif_ilan": aktif_kaynak + aktif_atik,
        "aktif_kaynak": aktif_kaynak,
        "aktif_atik": aktif_atik,
        "toplam_teslim": teslim,
        "geri_kazanilan_atik_kg": float(atik_kg or 0),
        "geri_kazanilan_kaynak_adet": kaynak_teslim,
        "geri_kazanilan_kaynak_skor": int(kaynak_skor or 0),
        "atik_teslim": atik_teslim,
        "gunluk_kullanici": gunluk_kullanici,
        "aktif_kurum": aktif_kurum_q.count(),
        "ortalama_teslim_gun": ortalama_teslim,
        "co2e_kg": float(co2e_kg or 0),
        "etki_adet": int(etki_adet or 0),
        "filtre": {"il": _norm(il), "ilce": _norm(ilce), "mahalle": _norm(mahalle)},
    }


def _ortalama_teslim_suresi_gun(geo) -> float | None:
    """Teslim edilen ilanlar için (etki.timestamp - ilan.tarih) ortalaması (gün)."""
    durations = []
    for model, fk in ((Kaynak, CevreselEtki.kaynak_id), (Atik, CevreselEtki.atik_id)):
        q = (
            db.session.query(model.tarih, CevreselEtki.timestamp)
            .join(CevreselEtki, fk == model.id)
            .filter(model.ilan_durumu == "Teslim Edildi")
        )
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        for created, delivered in q.all():
            if not created or not delivered:
                continue
            delta = delivered - created
            if delta.total_seconds() < 0:
                continue
            durations.append(delta.total_seconds() / 86400.0)
    if not durations:
        return None
    return round(sum(durations) / len(durations), 1)


def geography_options(il=None, ilce=None) -> dict:
    """Basamaklı İl → İlçe → Mahalle seçenekleri."""
    iller = [
        r[0]
        for r in db.session.query(User.il)
        .filter(User.il.isnot(None), User.il != "")
        .distinct()
        .order_by(User.il)
        .all()
    ]
    ilceler = []
    mahalleler = []
    il = _norm(il)
    ilce = _norm(ilce)
    if il:
        ilceler = [
            r[0]
            for r in db.session.query(User.ilce)
            .filter(User.il == il, User.ilce.isnot(None), User.ilce != "")
            .distinct()
            .order_by(User.ilce)
            .all()
        ]
    if il and ilce:
        mahalleler = [
            r[0]
            for r in db.session.query(User.mahalle)
            .filter(
                User.il == il,
                User.ilce == ilce,
                User.mahalle.isnot(None),
                User.mahalle != "",
            )
            .distinct()
            .order_by(User.mahalle)
            .all()
        ]
    return {"iller": iller, "ilceler": ilceler, "mahalleler": mahalleler}


def mahalle_analizi(il=None, ilce=None, mahalle=None) -> list[dict]:
    """Mahalle/ilçe bazında ilan, atık kg, kaynak adet, kullanıcı yoğunluğu."""
    from sqlalchemy import case

    geo = _geo_filters(il, ilce, mahalle)
    group_col = User.mahalle
    if not _norm(ilce):
        group_col = User.ilce
    if not _norm(il):
        group_col = User.il

    user_counts = defaultdict(int)
    uq = db.session.query(group_col, func.count(User.id)).filter(
        group_col.isnot(None), group_col != ""
    )
    if geo:
        uq = uq.filter(*geo)
    for name, cnt in uq.group_by(group_col).all():
        user_counts[name] = int(cnt or 0)

    ilan_counts = defaultdict(int)
    for model in (Kaynak, Atik):
        q = (
            db.session.query(group_col, func.count(model.id))
            .join(model, model.user_id == User.id)
            .filter(group_col.isnot(None), group_col != "")
        )
        if geo:
            q = q.filter(*geo)
        for name, cnt in q.group_by(group_col).all():
            ilan_counts[name] += int(cnt or 0)

    atik_kg = defaultdict(float)
    kaynak_adet = defaultdict(int)
    etki_q = (
        db.session.query(
            group_col,
            func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
            func.sum(case((CevreselEtki.tur == "kaynak", 1), else_=0)),
        )
        .join(CevreselEtki, CevreselEtki.user_id == User.id)
        .filter(group_col.isnot(None), group_col != "")
    )
    if geo:
        etki_q = etki_q.filter(*geo)
    for name, kg, kaynak_n in etki_q.group_by(group_col).all():
        atik_kg[name] = float(kg or 0)
        kaynak_adet[name] = int(kaynak_n or 0)

    names = set(user_counts) | set(ilan_counts) | set(atik_kg) | set(kaynak_adet)
    rows = []
    for name in names:
        rows.append({
            "bolge": name,
            "ilan_sayisi": ilan_counts.get(name, 0),
            "atik_kg": round(atik_kg.get(name, 0.0), 2),
            "kaynak_adet": kaynak_adet.get(name, 0),
            "kullanici_yogunlugu": user_counts.get(name, 0),
        })
    return sorted(rows, key=lambda r: (-r["ilan_sayisi"], r["bolge"]))


def heat_map_points(il=None, ilce=None, mahalle=None, yogunluk="atik") -> list:
    """Leaflet heat: [lat, lng, intensity]. yogunluk: atik|kaynak|teslim."""
    geo = _geo_filters(il, ilce, mahalle)
    mode = (yogunluk or "atik").strip().lower()
    noktalar = []

    def _ekle(query, weight):
        for ilan in query.all():
            if is_varsayilan_konum(ilan.latitude, ilan.longitude):
                continue
            noktalar.append([ilan.latitude, ilan.longitude, weight])

    if mode == "kaynak":
        _ekle(_aktif_query(Kaynak, geo), 0.85)
    elif mode == "teslim":
        _ekle(_teslim_query(Kaynak, geo), 1.0)
        _ekle(_teslim_query(Atik, geo), 1.2)
    else:
        _ekle(_aktif_query(Atik, geo), 1.0)
        # Teslim etkileri atık yoğunluğunu güçlendirir
        etki_q = CevreselEtki.query.filter(CevreselEtki.tur == "atik")
        if geo:
            etki_q = etki_q.join(User, CevreselEtki.user_id == User.id).filter(*geo)
        for etki in etki_q.all():
            ilan = etki.atik
            if not ilan or is_varsayilan_konum(ilan.latitude, ilan.longitude):
                continue
            yog = min(2.0, 0.5 + (etki.atik_kg or 0) / 20)
            noktalar.append([ilan.latitude, ilan.longitude, yog])

    return noktalar


def kategori_analizi(il=None, ilce=None, mahalle=None) -> dict:
    """Belediye kategori gruplarına göre sayım (grafik için)."""
    geo = _geo_filters(il, ilce, mahalle)
    counts = {g: 0 for g in MUNICIPALITY_CATEGORY_GROUPS}

    for model in (Kaynak, Atik):
        q = db.session.query(model.kategori, func.count(model.id)).group_by(model.kategori)
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        for kategori, adet in q.all():
            group = normalize_municipality_category(kategori)
            counts[group] = counts.get(group, 0) + int(adet or 0)

    labels = list(MUNICIPALITY_CATEGORY_GROUPS)
    values = [counts[g] for g in labels]
    return {
        "labels": labels,
        "values": values,
        "adetler": values,
        "rows": [{"kategori": k, "adet": counts[k]} for k in labels],
        "toplam": sum(values),
    }


def ilce_performans(il=None) -> list[dict]:
    """İlçe bazında 100 üzerinden performans puanı (yalnızca analiz, tahmin yok)."""
    il = _norm(il)
    rows = mahalle_analizi(il=il) if not il else mahalle_analizi(il=il)
    # mahalle_analizi without ilce groups by ilce when il is set
    if not rows:
        return []

    max_ilan = max((r["ilan_sayisi"] for r in rows), default=0) or 1
    max_atik = max((r["atik_kg"] for r in rows), default=0) or 1
    max_kaynak = max((r["kaynak_adet"] for r in rows), default=0) or 1
    max_user = max((r["kullanici_yogunlugu"] for r in rows), default=0) or 1

    scored = []
    for r in rows:
        # Ağırlık: teslim/ilan %40, atık %25, kaynak %20, kullanıcı %15
        puan = (
            40.0 * (r["ilan_sayisi"] / max_ilan)
            + 25.0 * (r["atik_kg"] / max_atik)
            + 20.0 * (r["kaynak_adet"] / max_kaynak)
            + 15.0 * (r["kullanici_yogunlugu"] / max_user)
        )
        scored.append({
            **r,
            "puan": round(min(100.0, max(0.0, puan)), 1),
        })
    return sorted(scored, key=lambda x: -x["puan"])


def weekly_category_deltas(il=None) -> list[dict]:
    """Son 7 gün vs önceki 7 gün kategori değişimleri (AI bağlamı)."""
    geo = _geo_filters(il)
    now = utc_now()
    week_ago = now - timedelta(days=7)
    two_weeks = now - timedelta(days=14)

    def _period_counts(start, end):
        counts = defaultdict(int)
        for model in (Kaynak, Atik):
            q = (
                db.session.query(model.kategori, func.count(model.id))
                .filter(model.tarih >= start, model.tarih < end)
                .group_by(model.kategori)
            )
            if geo:
                q = q.join(User, model.user_id == User.id).filter(*geo)
            for kat, adet in q.all():
                counts[normalize_municipality_category(kat)] += int(adet or 0)
        return counts

    current = _period_counts(week_ago, now)
    previous = _period_counts(two_weeks, week_ago)
    deltas = []
    for group in MUNICIPALITY_CATEGORY_GROUPS:
        cur = current.get(group, 0)
        prev = previous.get(group, 0)
        if prev == 0:
            pct = 100.0 if cur > 0 else 0.0
        else:
            pct = round(((cur - prev) / prev) * 100.0, 1)
        deltas.append({
            "kategori": group,
            "bu_hafta": cur,
            "onceki_hafta": prev,
            "degisim_yuzde": pct,
        })
    return deltas


def district_density_summary(il=None) -> list[dict]:
    """İlçe bazlı ilan yoğunluğu (AI bağlamı)."""
    return mahalle_analizi(il=il)[:10]
