"""Bakanlık (ROLE_MINISTRY) ulusal analitik servisleri."""

from __future__ import annotations

from collections import defaultdict

from sqlalchemy import func, or_

from constants import CO2E_KG_PER_KWH, ROLE_MUNICIPALITY
from extensions import db
from models import Atik, CevreselEtki, Kaynak, User
from utils import is_varsayilan_konum


def _norm(value: str | None) -> str | None:
    if value is None:
        return None
    value = str(value).strip()
    return value or None


def _geo_filters(il=None, ilce=None, belediye_id=None, kurum_id=None):
    """Drill-down filtreleri: Türkiye → İl → İlçe → Belediye → Kurum."""
    filters = []
    il = _norm(il)
    ilce = _norm(ilce)
    if il:
        filters.append(User.il == il)
    if ilce:
        filters.append(User.ilce == ilce)
    if belediye_id:
        try:
            bid = int(belediye_id)
        except (TypeError, ValueError):
            bid = None
        if bid:
            # Belediye kullanıcısının coğrafyasına hizala
            belediye = db.session.get(User, bid)
            if belediye and getattr(belediye, "role", None) == ROLE_MUNICIPALITY:
                if belediye.il:
                    filters.append(User.il == belediye.il)
                if belediye.ilce:
                    filters.append(User.ilce == belediye.ilce)
    if kurum_id:
        try:
            kid = int(kurum_id)
        except (TypeError, ValueError):
            kid = None
        if kid:
            filters.append(User.id == kid)
            filters.append(User.is_kurum.is_(True))
    return filters


def _join_listings(model, geo):
    q = model.query
    if geo:
        q = q.join(User, model.user_id == User.id).filter(*geo)
    return q


def co2e_to_energy_kwh(co2e_kg: float) -> float:
    if not CO2E_KG_PER_KWH:
        return 0.0
    return round(float(co2e_kg or 0) / CO2E_KG_PER_KWH, 2)


def ministry_kpi(il=None, ilce=None, belediye_id=None, kurum_id=None) -> dict:
    geo = _geo_filters(il, ilce, belediye_id, kurum_id)

    toplam_ilan = _join_listings(Kaynak, geo).count() + _join_listings(Atik, geo).count()

    etki_q = db.session.query(
        func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
        func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
        func.coalesce(func.sum(CevreselEtki.su_litre), 0),
        func.count(CevreselEtki.id),
    )
    if geo:
        etki_q = etki_q.join(User, CevreselEtki.user_id == User.id).filter(*geo)
    atik_kg, co2e_kg, su_litre, etki_adet = etki_q.one()
    co2e_kg = float(co2e_kg or 0)
    enerji_kwh = co2e_to_energy_kwh(co2e_kg)

    muni_q = User.query.filter(User.role == ROLE_MUNICIPALITY)
    kurum_q = User.query.filter(User.is_kurum.is_(True))
    if geo:
        muni_q = muni_q.filter(*geo)
        kurum_q = kurum_q.filter(*geo)

    user_q = User.query
    if geo:
        user_q = user_q.filter(*geo)
    toplam_vatandas = user_q.filter(
        User.role.notin_(("admin", "superadmin", "ministry")),
    ).count()
    # Katılım: en az bir ilanı olan kullanıcı / toplam kullanıcı
    participating = set()
    for model in (Kaynak, Atik):
        q = db.session.query(model.user_id).distinct()
        if geo:
            q = q.join(User, model.user_id == User.id).filter(*geo)
        participating.update(r[0] for r in q.all())
    katilim_orani = 0.0
    if toplam_vatandas > 0:
        katilim_orani = round(100.0 * len(participating) / toplam_vatandas, 1)

    return {
        "toplam_ilan": toplam_ilan,
        "toplam_geri_kazanim_kg": float(atik_kg or 0),
        "co2_tasarrufu_kg": co2e_kg,
        "enerji_tasarrufu_kwh": enerji_kwh,
        "su_tasarrufu_litre": float(su_litre or 0),
        "aktif_belediye": muni_q.count(),
        "aktif_kurum": kurum_q.count(),
        "vatandas_katilim_orani": katilim_orani,
        "etki_adet": int(etki_adet or 0),
        "filtre": {
            "il": _norm(il),
            "ilce": _norm(ilce),
            "belediye_id": int(belediye_id) if str(belediye_id or "").isdigit() else None,
            "kurum_id": int(kurum_id) if str(kurum_id or "").isdigit() else None,
        },
    }


def ministry_drilldown_options(il=None, ilce=None, belediye_id=None) -> dict:
    """Basamaklı seçenekler: iller / ilçeler / belediyeler / kurumlar."""
    iller = [
        r[0]
        for r in db.session.query(User.il)
        .filter(User.il.isnot(None), User.il != "")
        .distinct()
        .order_by(User.il)
        .all()
    ]
    il = _norm(il)
    ilce = _norm(ilce)
    ilceler = []
    belediyeler = []
    kurumlar = []

    if il:
        ilceler = [
            r[0]
            for r in db.session.query(User.ilce)
            .filter(User.il == il, User.ilce.isnot(None), User.ilce != "")
            .distinct()
            .order_by(User.ilce)
            .all()
        ]

    muni_q = User.query.filter(User.role == ROLE_MUNICIPALITY)
    if il:
        muni_q = muni_q.filter(User.il == il)
    if ilce:
        muni_q = muni_q.filter(User.ilce == ilce)
    belediyeler = [
        {
            "id": u.id,
            "ad": u.display_name or u.username,
            "il": u.il,
            "ilce": u.ilce,
        }
        for u in muni_q.order_by(User.username).all()
    ]

    kurum_q = User.query.filter(User.is_kurum.is_(True))
    if il:
        kurum_q = kurum_q.filter(User.il == il)
    if ilce:
        kurum_q = kurum_q.filter(User.ilce == ilce)
    if belediye_id and str(belediye_id).isdigit():
        belediye = db.session.get(User, int(belediye_id))
        if belediye and belediye.ilce:
            kurum_q = kurum_q.filter(User.ilce == belediye.ilce)
    kurumlar = [
        {"id": u.id, "ad": u.display_name or u.username, "il": u.il, "ilce": u.ilce}
        for u in kurum_q.order_by(User.username).all()
    ]

    return {
        "iller": iller,
        "ilceler": ilceler,
        "belediyeler": belediyeler,
        "kurumlar": kurumlar,
    }


def province_statistics(il=None) -> list[dict]:
    """İl bazlı skor ve metrikler (sıralama / grafik)."""
    geo = _geo_filters(il=il) if il else []
    group_col = User.il

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

    etki = defaultdict(lambda: {"atik_kg": 0.0, "co2e_kg": 0.0, "su_litre": 0.0})
    etki_q = (
        db.session.query(
            group_col,
            func.coalesce(func.sum(CevreselEtki.atik_kg), 0),
            func.coalesce(func.sum(CevreselEtki.co2e_kg), 0),
            func.coalesce(func.sum(CevreselEtki.su_litre), 0),
        )
        .join(CevreselEtki, CevreselEtki.user_id == User.id)
        .filter(group_col.isnot(None), group_col != "")
    )
    if geo:
        etki_q = etki_q.filter(*geo)
    for name, atik_kg, co2e, su in etki_q.group_by(group_col).all():
        etki[name] = {
            "atik_kg": float(atik_kg or 0),
            "co2e_kg": float(co2e or 0),
            "su_litre": float(su or 0),
        }

    user_counts = defaultdict(int)
    uq = db.session.query(group_col, func.count(User.id)).filter(
        group_col.isnot(None), group_col != ""
    )
    if geo:
        uq = uq.filter(*geo)
    for name, cnt in uq.group_by(group_col).all():
        user_counts[name] = int(cnt or 0)

    names = set(ilan_counts) | set(etki) | set(user_counts)
    if not names:
        return []

    max_ilan = max((ilan_counts[n] for n in names), default=0) or 1
    max_co2 = max((etki[n]["co2e_kg"] for n in names), default=0) or 1
    max_atik = max((etki[n]["atik_kg"] for n in names), default=0) or 1
    max_user = max((user_counts[n] for n in names), default=0) or 1

    rows = []
    for name in names:
        e = etki[name]
        puan = (
            35.0 * (ilan_counts[name] / max_ilan)
            + 30.0 * (e["co2e_kg"] / max_co2)
            + 20.0 * (e["atik_kg"] / max_atik)
            + 15.0 * (user_counts[name] / max_user)
        )
        rows.append({
            "il": name,
            "ilan": ilan_counts[name],
            "atik_kg": round(e["atik_kg"], 2),
            "co2e_kg": round(e["co2e_kg"], 2),
            "su_litre": round(e["su_litre"], 2),
            "enerji_kwh": co2e_to_energy_kwh(e["co2e_kg"]),
            "kullanici": user_counts[name],
            "puan": round(min(100.0, max(0.0, puan)), 1),
        })
    return sorted(rows, key=lambda r: -r["puan"])


def top_bottom_provinces(limit: int = 10) -> dict:
    rows = province_statistics()
    return {
        "en_basarili": rows[:limit],
        "en_dusuk": list(reversed(rows[-limit:])) if rows else [],
    }


def ministry_map_data(il=None, ilce=None) -> dict:
    """Türkiye ısı haritası noktaları + il bazlı yoğunluk."""
    geo = _geo_filters(il=il, ilce=ilce)
    noktalar = []

    def _ekle(query, weight):
        for ilan in query.all():
            if is_varsayilan_konum(ilan.latitude, ilan.longitude):
                continue
            noktalar.append({
                "lat": ilan.latitude,
                "lng": ilan.longitude,
                "intensity": weight,
            })

    kay_q = Kaynak.query
    atik_q = Atik.query
    if geo:
        kay_q = kay_q.join(User, Kaynak.user_id == User.id).filter(*geo)
        atik_q = atik_q.join(User, Atik.user_id == User.id).filter(*geo)
    _ekle(kay_q, 0.8)
    _ekle(atik_q, 1.0)

    # İl yoğunluk özeti (renk skalası için)
    provinces = province_statistics(il=il)
    il_yogunluk = [
        {
            "il": r["il"],
            "intensity": r["puan"] / 100.0,
            "ilan": r["ilan"],
            "co2e_kg": r["co2e_kg"],
        }
        for r in provinces
    ]

    # İl merkez proxy: kullanıcı ortalama lat/lng
    centers = []
    cq = (
        db.session.query(
            User.il,
            func.avg(User.latitude),
            func.avg(User.longitude),
            func.count(User.id),
        )
        .filter(
            User.il.isnot(None),
            User.il != "",
            User.latitude.isnot(None),
            User.longitude.isnot(None),
        )
        .group_by(User.il)
    )
    if il:
        cq = cq.filter(User.il == il)
    intensity_by_il = {r["il"]: r["intensity"] for r in il_yogunluk}
    for name, lat, lng, cnt in cq.all():
        if lat is None or lng is None:
            continue
        centers.append({
            "il": name,
            "lat": float(lat),
            "lng": float(lng),
            "intensity": intensity_by_il.get(name, 0.1),
            "kullanici": int(cnt or 0),
        })

    heat = [[p["lat"], p["lng"], p["intensity"]] for p in noktalar]
    # İl merkezlerini de heat'e ekle (il bazlı yoğunluk vurgusu)
    for c in centers:
        heat.append([c["lat"], c["lng"], max(0.3, c["intensity"] * 1.5)])

    return {
        "heat": heat,
        "il_yogunluk": il_yogunluk,
        "il_merkezleri": centers,
    }


def ministry_statistics(il=None, ilce=None, belediye_id=None, kurum_id=None) -> dict:
    return {
        "kpi": ministry_kpi(il, ilce, belediye_id, kurum_id),
        "drilldown": ministry_drilldown_options(il, ilce, belediye_id),
        "rankings": top_bottom_provinces(10),
        "provinces": province_statistics(il=il),
    }
