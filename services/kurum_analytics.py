"""Belediye ve kurumlar için analiz ve ısı haritası verileri."""

from sqlalchemy import func

from services.ilan_moderation import public_ilan_base_filter

from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from utils import is_varsayilan_konum


def _use_kurum_demo(il_filtre=None) -> bool:
    from services.demo_manager import is_demo_mode, should_use_demo

    if is_demo_mode():
        return True
    probe = Kaynak.query.count() + Atik.query.count()
    return should_use_demo("dashboard", real_data_sufficient=probe > 0)


def _aktif_kaynak_query(il_filtre=None):
    q = public_ilan_base_filter(Kaynak.query, Kaynak)
    if il_filtre:
        q = q.join(User, Kaynak.user_id == User.id).filter(User.il == il_filtre)
    return q


def _aktif_atik_query(il_filtre=None):
    q = public_ilan_base_filter(Atik.query, Atik)
    if il_filtre:
        q = q.join(User, Atik.user_id == User.id).filter(User.il == il_filtre)
    return q


def kurum_ozet(il_filtre=None):
    if _use_kurum_demo(il_filtre):
        from services import demo_provider

        if il_filtre:
            pkg = demo_provider.get_city(il_filtre)
            d = pkg["dashboard"]
            return {
                "kullanici": int(pkg["population"] * d["vatandas_katilim_orani"] / 100 / 40),
                "aktif_kaynak": d["aktif_kaynak"],
                "aktif_atik": d["aktif_atik"],
                "teslim": d["toplam_teslim"],
                "co2e_kg": float(d["co2e_kg"]),
                "atik_kg": float(d["geri_kazanilan_atik_kg"]),
                "teslim_etki": int(d["etki_adet"]),
                "il_filtre": il_filtre,
                "teslim_orani": d["teslim_orani"],
                "katilim": d["vatandas_katilim_orani"],
                "ai_ozeti": list(pkg["ai_summary"][:4]),
                "charts": demo_provider.chart_demo_bundle(il=il_filtre),
                "source": "demo",
            }
        kpi = demo_provider.ministry_kpi()
        return {
            "kullanici": kpi["vatandas_sayisi"],
            "aktif_kaynak": int(kpi["toplam_ilan"] * 0.45),
            "aktif_atik": int(kpi["toplam_ilan"] * 0.55),
            "teslim": int(kpi["etki_adet"]),
            "co2e_kg": float(kpi["co2_tasarrufu_kg"]),
            "atik_kg": float(kpi["toplam_geri_kazanim_kg"]),
            "teslim_etki": int(kpi["etki_adet"]),
            "il_filtre": None,
            "teslim_orani": round(kpi["vatandas_katilim_orani"], 1),
            "katilim": kpi["vatandas_katilim_orani"],
            "ai_ozeti": demo_provider.ministry_ai_summary()[:4],
            "charts": demo_provider.chart_demo_bundle(il="Sakarya"),
            "source": "demo",
        }

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
        "source": "live",
    }


def ilce_kirilimi(il_filtre=None):
    if _use_kurum_demo(il_filtre):
        from services import demo_provider

        city = il_filtre or "Sakarya"
        rows = demo_provider.mahalle_rows(il=city)
        return [{"ilce": r["bolge"], "adet": r["ilan_sayisi"]} for r in rows][:15]

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
    if _use_kurum_demo(il_filtre):
        from services import demo_provider

        cat = demo_provider.kategori_analizi(il=il_filtre or "Sakarya")
        rows = [{"kategori": r["kategori"], "adet": r["adet"]} for r in cat["rows"]]
        if tur == "atik":
            return [{"kategori": r["kategori"], "adet": max(1, int(r["adet"] * 0.55))} for r in rows]
        return [{"kategori": r["kategori"], "adet": max(1, int(r["adet"] * 0.45))} for r in rows]

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
    if _use_kurum_demo():
        from services import demo_provider

        return demo_provider.list_cities()

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
    if _use_kurum_demo(il_filtre):
        from services import demo_provider

        if il_filtre:
            return demo_provider.heat_map_points(il=il_filtre, yogunluk=tur or "atik")
        mmap = demo_provider.ministry_map_data()
        return mmap.get("heat") or []

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
    for etki in etki_q.limit(200).all():
        ilan = etki.atik or etki.kaynak
        if not ilan or is_varsayilan_konum(ilan.latitude, ilan.longitude):
            continue
        yog = min(2.0, 0.5 + (etki.atik_kg or 0) / 20)
        noktalar.append([ilan.latitude, ilan.longitude, yog])

    return noktalar


def kurum_eslesme_onerileri(il_filtre=None, limit: int = 8) -> list[dict]:
    """Kurumsal eşleştirme özeti — marketplace MASTER skorları."""
    if not _use_kurum_demo(il_filtre):
        return []
    from services import demo_provider

    return demo_provider.marketplace_matches(limit=limit, il=il_filtre)
