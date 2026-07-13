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

    data = {
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
    from services.demo_manager import is_dashboard_data_sufficient, should_use_demo
    from services import demo_provider

    if should_use_demo(
        "dashboard",
        real_data_sufficient=is_dashboard_data_sufficient(data),
    ):
        demo = demo_provider.dashboard_kpis(
            il=_norm(il), ilce=_norm(ilce), mahalle=_norm(mahalle)
        )
        return demo
    return data


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


def period_listing_counts(il=None, ilce=None, mahalle=None, *, days: int = 30) -> dict:
    """Son N gün vs önceki N gün ilan / teslim sayıları."""
    geo = _geo_filters(il, ilce, mahalle)
    now = utc_now()
    cur_start = now - timedelta(days=days)
    prev_start = now - timedelta(days=days * 2)

    def _count(model, start, end, *, teslim_only=False):
        q = model.query.filter(model.tarih >= start, model.tarih < end)
        if teslim_only:
            q = q.filter(model.ilan_durumu == "Teslim Edildi")
        return _join_user_filter(q, model, geo).count()

    cur_ilan = _count(Kaynak, cur_start, now) + _count(Atik, cur_start, now)
    prev_ilan = _count(Kaynak, prev_start, cur_start) + _count(Atik, prev_start, cur_start)
    cur_teslim = (
        _count(Kaynak, cur_start, now, teslim_only=True)
        + _count(Atik, cur_start, now, teslim_only=True)
    )
    prev_teslim = (
        _count(Kaynak, prev_start, cur_start, teslim_only=True)
        + _count(Atik, prev_start, cur_start, teslim_only=True)
    )

    def _pct(cur, prev):
        if prev <= 0:
            return 100.0 if cur > 0 else 0.0
        return round(((cur - prev) / prev) * 100.0, 1)

    return {
        "days": days,
        "ilan_son": cur_ilan,
        "ilan_onceki": prev_ilan,
        "ilan_degisim_yuzde": _pct(cur_ilan, prev_ilan),
        "teslim_son": cur_teslim,
        "teslim_onceki": prev_teslim,
        "teslim_degisim_yuzde": _pct(cur_teslim, prev_teslim),
    }


def seasonal_category_shift(il=None, ilce=None, mahalle=None) -> list[dict]:
    """Son 90 günü 3×30 günlük dilimlere bölerek mevsimsel / dönemsel kayma."""
    geo = _geo_filters(il, ilce, mahalle)
    now = utc_now()
    windows = []
    for i in range(3):
        end = now - timedelta(days=30 * i)
        start = now - timedelta(days=30 * (i + 1))
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
        windows.append({"label": f"son_{30*(i+1)}_gun", "counts": dict(counts)})

    # En yeni vs en eski dilim
    latest = windows[0]["counts"]
    oldest = windows[2]["counts"]
    shifts = []
    cats = set(latest) | set(oldest)
    for cat in cats:
        a = latest.get(cat, 0)
        b = oldest.get(cat, 0)
        if a + b == 0:
            continue
        if b == 0:
            pct = 100.0 if a else 0.0
        else:
            pct = round(((a - b) / b) * 100.0, 1)
        shifts.append({
            "kategori": cat,
            "son_dilim": a,
            "eski_dilim": b,
            "degisim_yuzde": pct,
        })
    return sorted(shifts, key=lambda x: -abs(x["degisim_yuzde"]))


def municipality_analysis_context(il=None, ilce=None, mahalle=None) -> dict:
    """AI / rule engine için birleşik analiz bağlamı."""
    geo = _geo_filters(il, ilce, mahalle)
    dashboard = municipality_dashboard(il=il, ilce=ilce, mahalle=mahalle)
    total = (dashboard.get("toplam_aktif_ilan") or 0) + (dashboard.get("toplam_teslim") or 0)
    teslim = dashboard.get("toplam_teslim") or 0
    teslim_orani = round(100.0 * teslim / total, 1) if total else 0.0

    user_q = User.query.filter(
        User.role.notin_(("admin", "superadmin", "ministry")),
        User.is_deactivated.is_(False),
    )
    if geo:
        user_q = user_q.filter(*geo)
    toplam_vatandas = user_q.count()
    katilim = (
        round(100.0 * (dashboard.get("gunluk_kullanici") or 0) / toplam_vatandas, 1)
        if toplam_vatandas
        else 0.0
    )

    return {
        "dashboard": dashboard,
        "kategori_artisi": weekly_category_deltas(il=il),
        "mahalle_yogunlugu": district_density_summary(il=il),
        "teslim_orani": teslim_orani,
        "vatandas_katilimi": {
            "oran": katilim,
            "gunluk": dashboard.get("gunluk_kullanici") or 0,
            "toplam": toplam_vatandas,
        },
        "trend_30_gun": period_listing_counts(il=il, ilce=ilce, mahalle=mahalle, days=30),
        "mevsimsel": seasonal_category_shift(il=il, ilce=ilce, mahalle=mahalle)[:6],
    }


def _count_since(model, geo, since, *, durum=None):
    q = model.query.filter(model.tarih >= since)
    if durum:
        q = q.filter(model.ilan_durumu == durum)
    return _join_user_filter(q, model, geo).count()


def _rezerve_query(model, geo):
    q = model.query.filter_by(ilan_durumu="Rezerve")
    return _join_user_filter(q, model, geo)


def _high_risk_query(model, geo, threshold: int = 60):
    q = model.query.filter(
        model.ai_risk_score.isnot(None),
        model.ai_risk_score >= threshold,
    )
    return _join_user_filter(q, model, geo)


def municipality_ops_center(il=None, ilce=None, mahalle=None) -> dict:
    """
    Belediye Operasyon Merkezi — kartlar, aktiviteler, risk özeti.
    municipality_dashboard alanlarını bozmadan genişletir.
    """
    geo = _geo_filters(il, ilce, mahalle)
    ozet = municipality_dashboard(il=il, ilce=ilce, mahalle=mahalle)
    now = utc_now()
    day0 = _day_start()
    since_24h = now - timedelta(hours=24)

    bugun_acilan = ozet["bugun_ilan"]
    bekleyen = _rezerve_query(Kaynak, geo).count() + _rezerve_query(Atik, geo).count()
    son_24_ilan = (
        _count_since(Kaynak, geo, since_24h) + _count_since(Atik, geo, since_24h)
    )
    son_24_teslim = (
        _count_since(Kaynak, geo, since_24h, durum="Teslim Edildi")
        + _count_since(Atik, geo, since_24h, durum="Teslim Edildi")
    )

    bolgeler = mahalle_analizi(il=il, ilce=ilce, mahalle=mahalle)
    en_yogun = bolgeler[0] if bolgeler else None

    # Riskli bölgeler: yüksek ilan yoğunluğu veya riskli ilan içeren üst dilimler
    riskli = []
    for row in bolgeler[:5]:
        if row["ilan_sayisi"] >= 3 or (en_yogun and row["bolge"] == en_yogun["bolge"]):
            riskli.append({
                "bolge": row["bolge"],
                "ilan_sayisi": row["ilan_sayisi"],
                "seviye": "yüksek" if row["ilan_sayisi"] >= max(5, (en_yogun or {}).get("ilan_sayisi", 0)) else "orta",
            })
    if not riskli and en_yogun:
        riskli = [{"bolge": en_yogun["bolge"], "ilan_sayisi": en_yogun["ilan_sayisi"], "seviye": "orta"}]

    # Kritik kategori: haftalık en yüksek artış veya en yüksek hacim
    deltas = weekly_category_deltas(il=il)
    kritik = None
    if deltas:
        by_growth = sorted(deltas, key=lambda d: -(d.get("degisim_yuzde") or 0))
        candidate = by_growth[0]
        if (candidate.get("degisim_yuzde") or 0) > 0 and (
            (candidate.get("bu_hafta") or 0) + (candidate.get("onceki_hafta") or 0) > 0
        ):
            kritik = {
                "kategori": candidate["kategori"],
                "degisim_yuzde": candidate["degisim_yuzde"],
                "bu_hafta": candidate["bu_hafta"],
            }
        else:
            by_vol = sorted(deltas, key=lambda d: -(d.get("bu_hafta") or 0))
            if by_vol[0].get("bu_hafta"):
                kritik = {
                    "kategori": by_vol[0]["kategori"],
                    "degisim_yuzde": by_vol[0]["degisim_yuzde"],
                    "bu_hafta": by_vol[0]["bu_hafta"],
                }

    high_risk = _high_risk_query(Kaynak, geo).count() + _high_risk_query(Atik, geo).count()
    ai_uyari = high_risk
    if kritik and (kritik.get("degisim_yuzde") or 0) >= 20:
        ai_uyari += 1
    if en_yogun and en_yogun.get("ilan_sayisi", 0) >= 5:
        ai_uyari += 1

    # Vatandaş katılımı: günlük aktif / bölge kullanıcıları
    user_q = User.query.filter(
        User.role.notin_(("admin", "superadmin", "ministry")),
        User.is_deactivated.is_(False),
    )
    if geo:
        user_q = user_q.filter(*geo)
    toplam_vatandas = user_q.count()
    katilim_pct = (
        round(100.0 * ozet["gunluk_kullanici"] / toplam_vatandas, 1)
        if toplam_vatandas
        else 0.0
    )

    cards = {
        "bugun_acilan": bugun_acilan,
        "bekleyen_teslimler": bekleyen,
        "son_24_saat": {"ilan": son_24_ilan, "teslim": son_24_teslim},
        "en_yogun_mahalle": en_yogun,
        "riskli_bolgeler": riskli[:3],
        "kritik_kategori": kritik,
        "vatandas_katilimi": {
            "gunluk": ozet["gunluk_kullanici"],
            "toplam": toplam_vatandas,
            "oran": katilim_pct,
        },
        "ai_uyarilari": ai_uyari,
        "yuksek_risk_ilan": high_risk,
    }

    aktiviteler = _recent_activities(geo, bolgeler, kritik, limit=12)

    return {
        "ozet": ozet,
        "cards": cards,
        "aktiviteler": aktiviteler,
        "filtre": ozet.get("filtre") or {},
    }


def _recent_activities(geo, bolgeler, kritik, limit: int = 12) -> list[dict]:
    """Son aktiviteler: yeni ilan, teslim, yüksek risk, yoğunluk artışı."""
    items = []
    now = utc_now()

    for model, tur in ((Kaynak, "kaynak"), (Atik, "atik")):
        q = model.query
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        q = q.order_by(model.tarih.desc()).limit(8)
        for row in q.all():
            if row.ilan_durumu == "Teslim Edildi":
                tip = "teslim"
                baslik = f"Teslim: {row.baslik}"
            else:
                tip = "yeni_ilan"
                baslik = f"Yeni ilan: {row.baslik}"
            items.append({
                "tip": tip,
                "baslik": baslik,
                "kategori": row.kategori,
                "tur": tur,
                "zaman": row.tarih,
                "meta": row.ilan_durumu,
            })
            if row.ai_risk_score is not None and row.ai_risk_score >= 60:
                items.append({
                    "tip": "yuksek_risk",
                    "baslik": f"Yüksek risk ({row.ai_risk_score}): {row.baslik}",
                    "kategori": row.kategori,
                    "tur": tur,
                    "zaman": row.tarih,
                    "meta": f"risk={row.ai_risk_score}",
                })

    if bolgeler:
        top = bolgeler[0]
        items.append({
            "tip": "yogunluk",
            "baslik": f"Yoğunluk artışı: {top['bolge']}",
            "kategori": None,
            "tur": "bolge",
            "zaman": now,
            "meta": f"{top['ilan_sayisi']} ilan",
        })
    if kritik and (kritik.get("degisim_yuzde") or 0) >= 15:
        items.append({
            "tip": "yogunluk",
            "baslik": f"Kritik kategori: {kritik['kategori']} (%{kritik['degisim_yuzde']:.0f})",
            "kategori": kritik["kategori"],
            "tur": "kategori",
            "zaman": now,
            "meta": f"bu hafta {kritik.get('bu_hafta', 0)}",
        })

    # Zamanına göre sırala (None en sona)
    def _key(a):
        z = a.get("zaman")
        return z or now.replace(year=1970)

    items.sort(key=_key, reverse=True)
    # Aynı başlığı tekrarsız tut
    seen = set()
    unique = []
    for a in items:
        key = (a["tip"], a["baslik"])
        if key in seen:
            continue
        seen.add(key)
        unique.append(a)
    return unique[:limit]
