import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from sqlalchemy import or_

from constants import DURUMLAR_KAYNAK, ILAN_DURUMLARI, KATEGORILER_KAYNAK, MAX_ILAN_FOTOSU
from extensions import db, limiter
from models import Comment, Kaynak
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

kaynak_bp = Blueprint("kaynak", __name__)


@kaynak_bp.route("/kaynak_panel")
def kaynak_panel():
    ara = request.args.get("ara", "")
    kategori = request.args.get("kategori", "")
    sirala = request.args.get("sirala", "")
    page = request.args.get("page", 1, type=int)

    query = Kaynak.query.filter(or_(Kaynak.ilan_durumu == "Aktif", Kaynak.ilan_durumu.is_(None)))
    if ara:
        query = query.filter(
            or_(Kaynak.baslik.ilike(f"%{ara}%"), Kaynak.aciklama.ilike(f"%{ara}%"))
        )
    if kategori and kategori not in ("", "Hepsi"):
        query = query.filter(Kaynak.kategori == kategori)
    if sirala == "eski":
        query = query.order_by(Kaynak.id.asc())
    else:
        query = query.order_by(Kaynak.id.desc())

    pagination = query.paginate(page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False)
    harita_kaynaklar = Kaynak.query.filter(
        or_(Kaynak.ilan_durumu == "Aktif", Kaynak.ilan_durumu.is_(None))
    ).all()
    harita_nokta, konumsuz_sayisi = harita_noktalari(harita_kaynaklar)
    oneriler = kullanici_onerileri(current_user, "kaynak", limit=6) if current_user.is_authenticated else []
    return render_template(
        "kaynak_panel.html",
        kaynaklar=pagination.items,
        pagination=pagination,
        kategoriler=KATEGORILER_KAYNAK,
        harita_nokta=harita_nokta,
        konumsuz_sayisi=konumsuz_sayisi,
        max_foto=MAX_ILAN_FOTOSU,
        oneriler=oneriler,
    )


@kaynak_bp.route("/yukle_kaynak", methods=["GET", "POST"])
@login_required
@limiter.limit("30 per hour")
def yukle_kaynak():
    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("kaynak.yukle_kaynak"))

        baslik = sanitize_input(request.form.get("baslik"), max_length=100)
        aciklama = sanitize_input(request.form.get("aciklama"), max_length=2000)
        durum = request.form.get("durum")
        kategori_secim = request.form.get("kategori")
        latitude, longitude, konum_varsayilan = parse_coordinates(
            request.form.get("latitude"),
            request.form.get("longitude"),
            user=current_user,
        )
        if konum_varsayilan:
            flash("Konum belirtilmedi; varsayılan konum (İstanbul) kullanıldı.", "warning")

        if not durum or durum not in DURUMLAR_KAYNAK:
            flash("Lütfen geçerli bir durum seçiniz.", "danger")
            return redirect(url_for("kaynak.yukle_kaynak"))

        try:
            dosyalar = save_ilan_fotograflari(request.files.getlist("resimler"))
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("kaynak.yukle_kaynak"))

        ai_sonuc = ai_analiz_ilk_foto(dosyalar, "kaynak", aciklama)
        ai_sonuc = fotograf_moderasyonu(ai_sonuc, baslik, aciklama, dosyalar)
        if moderasyon_reddedildi(ai_sonuc, dosyalar):
            flash(
                f"AI moderasyonu: İçerik riskli bulundu (Skor: {ai_sonuc.get('risk_skoru', 0)}/100).",
                "danger",
            )
            return redirect(url_for("kaynak.yukle_kaynak"))

        kategori = kategori_secim.strip() if kategori_secim and kategori_secim.strip() else ai_sonuc.get("kategori", "Diğer")
        final_durum = durum if durum in DURUMLAR_KAYNAK else ai_sonuc.get("durum", durum)

        kaynak = Kaynak(
            baslik=baslik,
            aciklama=aciklama,
            durum=final_durum,
            kategori=kategori,
            resim=dosyalar[0] if dosyalar else "default.jpg",
            latitude=latitude,
            longitude=longitude,
            user_id=current_user.id,
        )
        db.session.add(kaynak)
        db.session.flush()
        if dosyalar:
            ilan_fotograflari_ekle(kaynak, "kaynak", dosyalar)
        db.session.commit()
        from services.gamification import ilan_olusturuldu
        ilan_olusturuldu(current_user)
        db.session.commit()

        foto_msg = f" | {len(dosyalar)} fotoğraf" if dosyalar else ""
        flash(
            f"Kaynak eklendi | Kategori: {kategori} | Risk: {ai_sonuc.get('risk_skoru', 0)}/100{foto_msg}",
            "success",
        )
        return redirect(url_for("kaynak.kaynak_panel"))

    return render_template(
        "yukle_kaynak.html",
        kategoriler=KATEGORILER_KAYNAK,
        durumlar=DURUMLAR_KAYNAK,
        max_foto=MAX_ILAN_FOTOSU,
    )


@kaynak_bp.route("/kaynak/<int:id>")
def kaynak_detay(id):
    item = Kaynak.query.get_or_404(id)
    if not ilan_erisilebilir_mi(item, current_user):
        flash("Bu ilan artık aktif değil.", "warning")
        return redirect(url_for("kaynak.kaynak_panel"))
    return render_template("kaynak_detay.html", item=item, ilan_durumlari=ILAN_DURUMLARI)


@kaynak_bp.route("/yorum_ekle/<int:kaynak_id>", methods=["POST"])
@login_required
def yorum_ekle(kaynak_id):
    kaynak = Kaynak.query.get_or_404(kaynak_id)
    content = sanitize_input(request.form.get("yorum"), max_length=1000)
    if not content:
        flash("Yorum boş olamaz!", "danger")
        return redirect(url_for("kaynak.kaynak_detay", id=kaynak_id))

    yorum = Comment(content=content, user_id=current_user.id, kaynak_id=kaynak_id)
    db.session.add(yorum)
    db.session.commit()

    if kaynak.user_id != current_user.id:
        bildirim_olustur(
            kaynak.user_id,
            "Yeni yorum",
            f"{current_user.username} ilanınıza yorum yaptı.",
            "yorum",
            url_for("kaynak.kaynak_detay", id=kaynak_id),
        )

    flash("Yorum başarıyla eklendi!", "success")
    return redirect(url_for("kaynak.kaynak_detay", id=kaynak_id))
