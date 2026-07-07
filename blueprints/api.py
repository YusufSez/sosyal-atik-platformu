import re

import requests
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import RATE_PUBLIC_API
from extensions import db, limiter
from models import AtikMerkezi, Atik, Bildirim, Favori, Goruntulenme, Kaynak, Mesaj, Sikayet
from services.notifications import bildirim_olustur
from utils import mesafe_hesapla, sanitize_input

api_bp = Blueprint("api", __name__)

IBB_ATIK_RESOURCE_ID = "0124b01f-cfe7-4af8-ac80-88cb44ab5d64"


def get_ibb_merkezleri(limit=200):
    """İBB açık veri API'sinden atık toplama merkezlerini çeker."""
    url = (
        "https://data.ibb.gov.tr/api/3/action/datastore_search"
        f"?resource_id={IBB_ATIK_RESOURCE_ID}&limit={limit}"
    )
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
    except requests.RequestException:
        return []

    results = data.get("result", {}).get("records", [])
    merkezler = []
    for i, item in enumerate(results):
        try:
            shape = item.get("shape")
            lat, lng = None, None
            if shape:
                match = re.search(r"POINT\s*\(([^ ]+)\s+([^)]+)\)", shape)
                if match:
                    lng = float(match.group(1))
                    lat = float(match.group(2))
            if lat is None or lng is None:
                continue
            merkezler.append({
                "id": i,
                "ad": item.get("facility_name") or "Atık Merkezi",
                "lat": lat,
                "lng": lng,
                "adres": item.get("address", ""),
            })
        except (TypeError, ValueError):
            continue
    return merkezler


def get_yerel_merkezler():
    return [
        {
            "id": m.id,
            "ad": m.ad,
            "lat": m.latitude,
            "lng": m.longitude,
            "adres": m.adres,
        }
        for m in AtikMerkezi.query.all()
    ]


@api_bp.route("/api/ibb_atik_merkezleri")
@limiter.limit(RATE_PUBLIC_API)
def ibb_atik_merkezleri():
    return jsonify(get_ibb_merkezleri())


@api_bp.route("/api/atik_merkezleri")
@limiter.limit(RATE_PUBLIC_API)
def api_atik_merkezleri():
    merkezler = AtikMerkezi.query.all()
    return jsonify([
        {"id": m.id, "ad": m.ad, "lat": m.latitude, "lng": m.longitude, "adres": m.adres}
        for m in merkezler
    ])


@api_bp.route("/api/en_yakin_merkezler/<float:lat>/<float:lng>")
@limiter.limit(RATE_PUBLIC_API)
def en_yakin_merkezler(lat, lng):
    merkezler = get_ibb_merkezleri()
    if not merkezler:
        merkezler = get_yerel_merkezler()

    liste = []
    for m in merkezler:
        liste.append({
            "ad": m["ad"],
            "lat": m["lat"],
            "lng": m["lng"],
            "adres": m.get("adres", ""),
            "mesafe": round(mesafe_hesapla(lat, lng, m["lat"], m["lng"]), 2),
        })
    liste.sort(key=lambda x: x["mesafe"])
    return jsonify(liste[:10])


@api_bp.route("/seed")
def seed():
    if not current_app.config.get("ALLOW_SEED_ROUTE", False):
        return jsonify({"error": "Seed endpoint devre dışı."}), 403
    if AtikMerkezi.query.count() == 0:
        db.session.add_all([
            AtikMerkezi(ad="Kadıköy Merkez", latitude=40.99, longitude=29.03, adres="Kadıköy"),
            AtikMerkezi(ad="Beşiktaş Merkez", latitude=41.04, longitude=29.00, adres="Beşiktaş"),
            AtikMerkezi(ad="Üsküdar Merkez", latitude=41.02, longitude=29.02, adres="Üsküdar"),
        ])
        db.session.commit()
    return "OK"


@api_bp.route("/api/favori_ekle", methods=["POST"])
@login_required
def favori_ekle():
    data = request.get_json() or {}
    kaynak_id = data.get("kaynak_id")
    atik_id = data.get("atik_id")
    if not kaynak_id and not atik_id:
        return jsonify({"error": "Geçersiz istek"}), 400

    if kaynak_id:
        if not db.session.get(Kaynak, kaynak_id):
            return jsonify({"error": "İlan bulunamadı"}), 404
    elif atik_id:
        if not db.session.get(Atik, atik_id):
            return jsonify({"error": "İlan bulunamadı"}), 404

    existing = Favori.query.filter_by(
        user_id=current_user.id,
        kaynak_id=kaynak_id if kaynak_id else None,
        atik_id=atik_id if atik_id else None,
    ).first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        return jsonify({"status": "removed"})

    favori = Favori(
        user_id=current_user.id,
        kaynak_id=kaynak_id if kaynak_id else None,
        atik_id=atik_id if atik_id else None,
    )
    db.session.add(favori)
    db.session.commit()
    from services.gamification import favori_eklendi
    favori_eklendi(current_user)
    db.session.commit()

    owner_id = None
    link = None
    if kaynak_id:
        kaynak = db.session.get(Kaynak, kaynak_id)
        if kaynak:
            owner_id = kaynak.user_id
            link = url_for("kaynak.kaynak_detay", id=kaynak_id)
    elif atik_id:
        atik = db.session.get(Atik, atik_id)
        if atik:
            owner_id = atik.user_id
            link = url_for("atik.atik_detay", id=atik_id)

    if owner_id and owner_id != current_user.id:
        bildirim_olustur(
            owner_id,
            "Yeni favori",
            f"{current_user.username} ilanınızı favorilere ekledi.",
            "favori",
            link,
        )

    return jsonify({"status": "added"})


@api_bp.route("/api/favori_kontrol")
@login_required
def favori_kontrol():
    kaynak_id = request.args.get("kaynak_id", type=int)
    atik_id = request.args.get("atik_id", type=int)
    favorilenmis = Favori.query.filter_by(
        user_id=current_user.id,
        kaynak_id=kaynak_id if kaynak_id else None,
        atik_id=atik_id if atik_id else None,
    ).first()
    return jsonify({"is_favori": favorilenmis is not None})


@api_bp.route("/favorilerim")
@login_required
def favorilerim():
    favoriler = Favori.query.filter_by(user_id=current_user.id).order_by(Favori.timestamp.desc()).all()
    return render_template("favorilerim.html", favoriler=favoriler, title="Favorilerim")


@api_bp.route("/bildirimleri_getir")
@login_required
def bildirimleri_getir():
    bildirimler = Bildirim.query.filter_by(user_id=current_user.id).order_by(Bildirim.timestamp.desc()).limit(20).all()
    return jsonify([{
        "id": b.id,
        "baslik": b.baslik,
        "icerik": b.icerik,
        "tur": b.tur,
        "okundu": b.okundu,
        "link": b.link,
        "timestamp": b.timestamp.strftime("%d.%m.%Y %H:%M"),
    } for b in bildirimler])


@api_bp.route("/bildirim_okundu_isaretle/<int:id>", methods=["POST"])
@login_required
def bildirim_okundu_isaretle(id):
    bildirim = Bildirim.query.filter_by(id=id, user_id=current_user.id).first()
    if bildirim:
        bildirim.okundu = True
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"error": "Bulunamadı"}), 404


@api_bp.route("/bildirimleri_okundu_isaretle", methods=["POST"])
@login_required
def bildirimleri_okundu_isaretle():
    Bildirim.query.filter_by(user_id=current_user.id, okundu=False).update({"okundu": True})
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/bildirimleri_temizle", methods=["POST"])
@login_required
def bildirimleri_temizle():
    Bildirim.query.filter_by(user_id=current_user.id, okundu=True).delete()
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/api/goruntulenme_ekle", methods=["POST"])
@login_required
def goruntulenme_ekle():
    data = request.get_json() or {}
    kaynak_id = data.get("kaynak_id")
    atik_id = data.get("atik_id")
    if not kaynak_id and not atik_id:
        return jsonify({"error": "Geçersiz istek"}), 400

    if kaynak_id:
        if not db.session.get(Kaynak, kaynak_id):
            return jsonify({"error": "İlan bulunamadı"}), 404
    elif atik_id:
        if not db.session.get(Atik, atik_id):
            return jsonify({"error": "İlan bulunamadı"}), 404

    db.session.add(Goruntulenme(
        kaynak_id=kaynak_id if kaynak_id else None,
        atik_id=atik_id if atik_id else None,
        user_id=current_user.id,
    ))
    db.session.commit()

    if kaynak_id:
        count = Goruntulenme.query.filter_by(kaynak_id=kaynak_id).count()
    else:
        count = Goruntulenme.query.filter_by(atik_id=atik_id).count()
    return jsonify({"count": count})


@api_bp.route("/api/goruntulenme_sayisi")
def goruntulenme_sayisi():
    kaynak_id = request.args.get("kaynak_id", type=int)
    atik_id = request.args.get("atik_id", type=int)
    if kaynak_id:
        count = Goruntulenme.query.filter_by(kaynak_id=kaynak_id).count()
    elif atik_id:
        count = Goruntulenme.query.filter_by(atik_id=atik_id).count()
    else:
        count = 0
    return jsonify({"count": count})


@api_bp.route("/api/sikayet", methods=["POST"])
@login_required
@limiter.limit("10 per hour")
def sikayet_olustur():
    data = request.get_json() or {}
    kaynak_id = data.get("kaynak_id")
    atik_id = data.get("atik_id")
    sebep = (data.get("sebep") or "").strip()
    if not sebep or (not kaynak_id and not atik_id):
        return jsonify({"error": "Geçersiz istek"}), 400

    db.session.add(Sikayet(
        user_id=current_user.id,
        kaynak_id=kaynak_id if kaynak_id else None,
        atik_id=atik_id if atik_id else None,
        sebep=sanitize_input(sebep, max_length=500),
    ))
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/api/mesaj_sikayet", methods=["POST"])
@login_required
@limiter.limit("15 per hour")
def mesaj_sikayet():
    data = request.get_json() or {}
    mesaj_id = data.get("mesaj_id")
    ek_sebep = sanitize_input(data.get("sebep", ""), max_length=400)

    if not mesaj_id:
        return jsonify({"error": "Mesaj seçilmedi."}), 400

    mesaj = Mesaj.query.get_or_404(int(mesaj_id))
    if current_user.id not in (mesaj.sender_id, mesaj.receiver_id):
        return jsonify({"error": "Bu mesajı şikayet etme yetkiniz yok."}), 403

    mevcut = Sikayet.query.filter_by(user_id=current_user.id, mesaj_id=mesaj.id).first()
    if mevcut:
        return jsonify({"error": "Bu mesajı zaten şikayet ettiniz."}), 400

    ozet = sanitize_input(mesaj.content, max_length=200)
    sebep = f"Mesaj şikayeti (#{mesaj.id}): {ozet}"
    if ek_sebep:
        sebep += f" | Açıklama: {ek_sebep}"

    db.session.add(Sikayet(
        user_id=current_user.id,
        kaynak_id=mesaj.kaynak_id,
        atik_id=mesaj.atik_id,
        mesaj_id=mesaj.id,
        sebep=sebep[:500],
    ))
    db.session.commit()
    return jsonify({"success": True})


@api_bp.route("/api/etki/ozet")
def etki_ozet():
    from services.impact import platform_ozeti

    return jsonify(platform_ozeti())


@api_bp.route("/api/etki/benim")
@login_required
def etki_benim():
    from services.impact import kullanici_ozeti

    return jsonify(kullanici_ozeti(current_user.id))


@api_bp.route("/api/oneriler")
@login_required
def api_oneriler():
    from services.recommendations import kullanici_onerileri

    tur = request.args.get("tur", "kaynak")
    if tur not in ("kaynak", "atik"):
        return jsonify({"error": "Geçersiz tür"}), 400
    oneriler = kullanici_onerileri(current_user, tur, limit=8)
    return jsonify([
        {
            "id": o["ilan"].id,
            "baslik": o["ilan"].baslik,
            "kategori": o["ilan"].kategori,
            "tur": tur,
            "neden": o["neden"],
            "skor": o["skor"],
        }
        for o in oneriler
    ])
