import os

from flask import Blueprint, current_app, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from services.ilan_moderation import public_ilan_base_filter

from constants import DURUMLAR_KAYNAK, ILAN_DURUMLARI, KATEGORILER_KAYNAK, MAX_ILAN_FOTOSU, RATE_COMMENT, RATE_ILAN_CREATE
from decorators import email_verified_required
from extensions import db, ai_analiz_limit, limiter, rate_limit_user_or_ip
from models import Comment, Kaynak
from services.captcha import captcha_hatasi
from services.ilan_moderation import admin_moderasyon_bildir, ilan_moderasyon_alanlarini_uygula
from services.moderation_analysis import kaydet_ilk_analiz
from services.moderation_messages import kullanici_moderasyon_mesaji
from services.ilan_images import (
    ai_analiz_ilk_foto,
    fotograf_moderasyonu,
    ilan_fotograflari_ekle,
    moderasyon_reddedildi,
    save_ilan_fotograflari,
)
from services.notifications import bildirim_olustur
from services.yorumlar import kok_yorumlari_getir, yorum_cevapla as yorum_cevabi_kaydet
from services.recommendations import kullanici_onerileri
from services.query_options import ilan_detay_options, ilan_listesi_options
from services.content_filter import yorum_uygun_mu
from utils import ilan_erisilebilir_mi, parse_coordinates, sanitize_input, harita_noktalari

kaynak_bp = Blueprint("kaynak", __name__)


@kaynak_bp.route("/kaynak_panel")
def kaynak_panel():
    ara = request.args.get("ara", "")
    kategori = request.args.get("kategori", "")
    sirala = request.args.get("sirala", "")
    page = request.args.get("page", 1, type=int)

    query = public_ilan_base_filter(Kaynak.query, Kaynak)
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

    pagination = query.options(*ilan_listesi_options(Kaynak)).paginate(
        page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False
    )
    harita_kaynaklar = public_ilan_base_filter(Kaynak.query, Kaynak).all()
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
@email_verified_required
@limiter.limit(RATE_ILAN_CREATE, methods=["POST"], key_func=rate_limit_user_or_ip)
@ai_analiz_limit
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

        ai_sonuc = ai_analiz_ilk_foto(
            dosyalar, "kaynak", aciklama, baslik=baslik, kategori_secim=kategori_secim
        )
        ai_sonuc = fotograf_moderasyonu(ai_sonuc, baslik, aciklama, dosyalar, tur="kaynak")
        if moderasyon_reddedildi(ai_sonuc, dosyalar):
            flash(
                f"AI moderasyonu: İçerik yayınlanamadı (Skor: {ai_sonuc.get('risk_skoru', 0)}/100). "
                f"{ai_sonuc.get('reason') or 'Admin onayı gerekiyor.'}",
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
        karar = ilan_moderasyon_alanlarini_uygula(kaynak, ai_sonuc)
        db.session.add(kaynak)
        db.session.flush()
        if dosyalar:
            ilan_fotograflari_ekle(kaynak, "kaynak", dosyalar)
        from services.moderation_signals import enrich_upload_signals
        enrich_upload_signals(
            ai_sonuc,
            tur="kaynak",
            ilan_id=kaynak.id,
            baslik=baslik,
            aciklama=aciklama,
            user_id=current_user.id,
            kategori=kategori,
            latitude=latitude,
            longitude=longitude,
            photo_files=dosyalar,
        )
        kaydet_ilk_analiz(kaynak, "kaynak", ai_sonuc, dosyalar, triggered_by="upload")
        db.session.commit()
        admin_moderasyon_bildir(kaynak, "kaynak", ai_sonuc, karar, current_user)
        db.session.commit()
        from services.gamification import ilan_olusturuldu
        ilan_olusturuldu(current_user)
        db.session.commit()

        kullanici_msg, kullanici_cat = kullanici_moderasyon_mesaji(ai_sonuc.get("moderation_status"))
        flash(kullanici_msg, kullanici_cat)
        return redirect(url_for("kaynak.kaynak_panel"))

    return render_template(
        "yukle_kaynak.html",
        kategoriler=KATEGORILER_KAYNAK,
        durumlar=DURUMLAR_KAYNAK,
        max_foto=MAX_ILAN_FOTOSU,
    )


@kaynak_bp.route("/kaynak/<int:id>")
def kaynak_detay(id):
    item = Kaynak.query.options(*ilan_detay_options(Kaynak)).filter_by(id=id).first_or_404()
    if not ilan_erisilebilir_mi(item, current_user):
        flash("Bu ilan artık aktif değil.", "warning")
        return redirect(url_for("kaynak.kaynak_panel"))
    return render_template(
        "kaynak_detay.html",
        item=item,
        ilan_durumlari=ILAN_DURUMLARI,
        kok_yorumlar=kok_yorumlari_getir(kaynak_id=item.id),
    )


@kaynak_bp.route("/yorum_ekle/<int:kaynak_id>", methods=["POST"])
@login_required
@email_verified_required
@limiter.limit(RATE_COMMENT, methods=["POST"], key_func=rate_limit_user_or_ip)
def yorum_ekle(kaynak_id):
    kaynak = Kaynak.query.get_or_404(kaynak_id)
    content = sanitize_input(request.form.get("yorum"), max_length=1000)
    if not content:
        flash("Yorum boş olamaz!", "danger")
        return redirect(url_for("kaynak.kaynak_detay", id=kaynak_id))

    uygun, hata = yorum_uygun_mu(content)
    if not uygun:
        flash(hata, "danger")
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


@kaynak_bp.route("/yorum_cevapla/<int:kaynak_id>/<int:parent_id>", methods=["POST"])
@login_required
@email_verified_required
@limiter.limit(RATE_COMMENT, methods=["POST"], key_func=rate_limit_user_or_ip)
def yorum_cevapla(kaynak_id, parent_id):
    Kaynak.query.get_or_404(kaynak_id)
    content = sanitize_input(request.form.get("yorum"), max_length=1000)
    if not content:
        flash("Cevap boş olamaz!", "danger")
        return redirect(url_for("kaynak.kaynak_detay", id=kaynak_id, _anchor=f"yorum-{parent_id}"))

    try:
        yorum_cevabi_kaydet(current_user, parent_id, content)
        flash("Cevabınız eklendi!", "success")
    except PermissionError:
        flash("Yalnızca ilan sahibi yorumlara cevap verebilir.", "danger")
    except ValueError as exc:
        flash(str(exc), "danger")

    return redirect(url_for("kaynak.kaynak_detay", id=kaynak_id, _anchor=f"yorum-{parent_id}"))
