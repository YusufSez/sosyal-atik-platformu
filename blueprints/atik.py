from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from sqlalchemy import or_

from constants import ILAN_DURUMLARI, KATEGORILER_ATIK, MAX_ILAN_FOTOSU
from extensions import db, limiter
from models import Atik, Comment
from services.captcha import captcha_hatasi
from services.ilan_images import (
    ai_analiz_ilk_foto,
    fotograf_moderasyonu,
    ilan_fotograflari_ekle,
    moderasyon_reddedildi,
    save_ilan_fotograflari,
)
from services.notifications import bildirim_olustur
from services.recommendations import kullanici_onerileri
from utils import ilan_erisilebilir_mi, parse_coordinates, sanitize_input, harita_noktalari

atik_bp = Blueprint("atik", __name__)


@atik_bp.route("/atik_panel")
def atik_panel():
    ara = request.args.get("ara", "")
    kategori = request.args.get("kategori", "")
    sirala = request.args.get("sirala", "")
    page = request.args.get("page", 1, type=int)

    query = Atik.query.filter(or_(Atik.ilan_durumu == "Aktif", Atik.ilan_durumu.is_(None)))
    if ara:
        query = query.filter(
            or_(Atik.baslik.ilike(f"%{ara}%"), Atik.aciklama.ilike(f"%{ara}%"))
        )
    if kategori and kategori not in ("", "Hepsi"):
        query = query.filter(Atik.kategori == kategori)
    if sirala == "eski":
        query = query.order_by(Atik.id.asc())
    else:
        query = query.order_by(Atik.id.desc())

    pagination = query.paginate(page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False)
    harita_atiklar = Atik.query.filter(
        or_(Atik.ilan_durumu == "Aktif", Atik.ilan_durumu.is_(None))
    ).all()
    harita_nokta, konumsuz_sayisi = harita_noktalari(harita_atiklar)
    oneriler = kullanici_onerileri(current_user, "atik", limit=6) if current_user.is_authenticated else []
    return render_template(
        "atik_panel.html",
        atiklar=pagination.items,
        pagination=pagination,
        kategoriler=KATEGORILER_ATIK,
        harita_nokta=harita_nokta,
        konumsuz_sayisi=konumsuz_sayisi,
        max_foto=MAX_ILAN_FOTOSU,
        oneriler=oneriler,
    )


@atik_bp.route("/yukle_atik", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def yukle_atik():
    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("atik.yukle_atik"))

        baslik = sanitize_input(request.form.get("baslik"), max_length=100)
        aciklama = sanitize_input(request.form.get("aciklama"), max_length=2000)
        kategori_secim = request.form.get("kategori")
        latitude, longitude, konum_varsayilan = parse_coordinates(
            request.form.get("latitude"),
            request.form.get("longitude"),
            user=current_user,
        )
        if konum_varsayilan:
            flash("Konum belirtilmedi; varsayılan konum (İstanbul) kullanıldı.", "warning")

        try:
            dosyalar = save_ilan_fotograflari(request.files.getlist("resimler"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("atik.yukle_atik"))

        ai_sonuc = ai_analiz_ilk_foto(
            dosyalar, "atik", aciklama, baslik=baslik, kategori_secim=kategori_secim
        )
        ai_sonuc = fotograf_moderasyonu(ai_sonuc, baslik, aciklama, dosyalar)
        if moderasyon_reddedildi(ai_sonuc, dosyalar):
            flash(
                f"AI moderasyonu: İçerik riskli bulundu (Skor: {ai_sonuc.get('risk_skoru', 0)}/100).",
                "danger",
            )
            return redirect(url_for("atik.yukle_atik"))

        kategori = kategori_secim.strip() if kategori_secim and kategori_secim.strip() else ai_sonuc.get("kategori", "Diğer")

        atik = Atik(
            baslik=baslik,
            aciklama=aciklama,
            resim=dosyalar[0] if dosyalar else "default.jpg",
            latitude=latitude,
            longitude=longitude,
            user_id=current_user.id,
            kategori=kategori,
        )
        db.session.add(atik)
        db.session.flush()
        if dosyalar:
            ilan_fotograflari_ekle(atik, "atik", dosyalar)
        db.session.commit()
        from services.gamification import ilan_olusturuldu
        ilan_olusturuldu(current_user)
        db.session.commit()

        foto_msg = f" | {len(dosyalar)} fotoğraf" if dosyalar else ""
        flash(
            f"Atık eklendi | Kategori: {kategori} | Risk: {ai_sonuc.get('risk_skoru', 0)}/100{foto_msg}",
            "success",
        )
        return redirect(url_for("atik.atik_panel"))

    return render_template(
        "yukle_atik.html",
        kategoriler=KATEGORILER_ATIK,
        max_foto=MAX_ILAN_FOTOSU,
        varsayilan_lat=current_user.latitude,
        varsayilan_lng=current_user.longitude,
    )


@atik_bp.route("/atik/<int:id>")
def atik_detay(id):
    item = Atik.query.get_or_404(id)
    if not ilan_erisilebilir_mi(item, current_user):
        flash("Bu ilan artık aktif değil.", "warning")
        return redirect(url_for("atik.atik_panel"))
    return render_template("atik_detay.html", item=item, ilan_durumlari=ILAN_DURUMLARI)


@atik_bp.route("/yorum_ekle_atik/<int:atik_id>", methods=["POST"])
@login_required
def yorum_ekle_atik(atik_id):
    atik = Atik.query.get_or_404(atik_id)
    content = sanitize_input(request.form.get("yorum"), max_length=1000)
    if not content:
        flash("Yorum boş olamaz!", "danger")
        return redirect(url_for("atik.atik_detay", id=atik_id))

    yorum = Comment(content=content, user_id=current_user.id, atik_id=atik_id)
    db.session.add(yorum)
    db.session.commit()

    if atik.user_id != current_user.id:
        bildirim_olustur(
            atik.user_id,
            "Yeni yorum",
            f"{current_user.username} ilanınıza yorum yaptı.",
            "yorum",
            url_for("atik.atik_detay", id=atik_id),
        )

    flash("Yorum başarıyla eklendi!", "success")
    return redirect(url_for("atik.atik_detay", id=atik_id))
