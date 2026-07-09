import os

from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import DURUMLAR_KAYNAK, ILAN_DURUMLARI, KATEGORILER_ATIK, KATEGORILER_KAYNAK, MAX_ILAN_FOTOSU
from extensions import ai_analiz_limit, db
from models import Atik, Kaynak, User
from services.ilan_moderation import (
    admin_moderasyon_bildir,
    ilan_metin_moderasyonu,
    ilan_moderasyon_alanlarini_uygula,
)
from services.ilan_images import (
    ai_analiz_ilk_foto,
    ensure_ilan_fotograflari,
    fotograf_moderasyonu,
    ilan_fotograf_listesi,
    ilan_fotograflari_ekle,
    ilan_fotograflari_sil,
    moderasyon_reddedildi,
    save_ilan_fotograflari,
)
from services.impact import format_etki_sayi, ilan_durum_etki_sync
from services.notifications import bildirim_olustur
from utils import cleanup_ilan_relations, parse_coordinates, sanitize_input

ilan_bp = Blueprint("ilan", __name__)


def _teslim_gamification(ilan):
    if not ilan:
        return
    from services.gamification import teslim_tamamlandi
    user = db.session.get(User, ilan.user_id)
    if user:
        teslim_tamamlandi(user)
        db.session.commit()


def _etki_durum_mesajlari(ilan, tur, sonuc):
    if not sonuc:
        flash("İlan durumu güncellendi.", "success")
        return
    islem, etki_kayit = sonuc
    if islem == "eklendi" and etki_kayit:
        co2e_text = format_etki_sayi(etki_kayit.co2e_kg, "kg CO₂e")
        flash(
            f"Tebrikler! Bu paylaşımınla yaklaşık {co2e_text} tasarrufu sağlandı.",
            "success",
        )
        bildirim_olustur(
            ilan.user_id,
            "Çevresel etki kaydedildi",
            f"{ilan.kategori} kategorisindeki paylaşımınız {co2e_text} tahmini tasarruf sağladı.",
            "etki",
            link=url_for("impact.etki_panelim"),
        )
    elif islem == "silindi":
        flash("İlan durumu güncellendi. Çevresel etki kaydı geri alındı.", "info")


def _ilan_metin_moderasyonu_uygula(ilan, tur):
    """Başlık/açıklama değişikliklerinde metin moderasyonu."""
    ai_sonuc = ilan_metin_moderasyonu(ilan.baslik, ilan.aciklama, tur=tur)
    if moderasyon_reddedildi(ai_sonuc, []):
        return ai_sonuc, None
    karar = ilan_moderasyon_alanlarini_uygula(ilan, ai_sonuc)
    admin_moderasyon_bildir(ilan, tur, ai_sonuc, karar, current_user)
    return ai_sonuc, karar


def _ilan_foto_guncelle(ilan, tur):
    ensure_ilan_fotograflari(ilan, tur)
    silinecek = [int(x) for x in request.form.getlist("silinecek_resim") if str(x).isdigit()]
    ilan_fotograflari_sil(ilan, silinecek)
    mevcut = len(ilan_fotograf_listesi(ilan))
    try:
        yeni_dosyalar = save_ilan_fotograflari(request.files.getlist("resimler"), mevcut_adet=mevcut)
    except ValueError as exc:
        return str(exc)
    if yeni_dosyalar:
        ai_sonuc = ai_analiz_ilk_foto(
            yeni_dosyalar,
            tur,
            ilan.aciklama,
            baslik=ilan.baslik,
            kategori_secim=ilan.kategori if tur == "atik" else None,
        )
        ai_sonuc = fotograf_moderasyonu(ai_sonuc, ilan.baslik, ilan.aciklama, yeni_dosyalar, tur=tur)
        if moderasyon_reddedildi(ai_sonuc, yeni_dosyalar):
            return "Yeni görseller moderasyon kontrolünden geçemedi."
        ilan_fotograflari_ekle(ilan, tur, yeni_dosyalar)
    return None


@ilan_bp.route("/ilanlarim")
@login_required
def ilanlarim():
    kaynaklarim = Kaynak.query.filter_by(user_id=current_user.id).order_by(Kaynak.id.desc()).all()
    atiklarim = Atik.query.filter_by(user_id=current_user.id).order_by(Atik.id.desc()).all()
    return render_template("ilanlarim.html", kaynaklarim=kaynaklarim, atiklarim=atiklarim, ilan_durumlari=ILAN_DURUMLARI)


@ilan_bp.route("/ilan_sil/<tur>/<int:id>", methods=["POST"])
@login_required
def ilan_sil(tur, id):
    if tur == "kaynak":
        ilan = Kaynak.query.get_or_404(id)
        if ilan.user_id != current_user.id:
            flash("Bu ilanı silme yetkiniz yok.", "danger")
            return redirect(url_for("ilan.ilanlarim"))
        cleanup_ilan_relations(kaynak_id=ilan.id)
        db.session.delete(ilan)
        flash("Kaynak ilanı silindi.", "success")
    else:
        ilan = Atik.query.get_or_404(id)
        if ilan.user_id != current_user.id:
            flash("Bu ilanı silme yetkiniz yok.", "danger")
            return redirect(url_for("ilan.ilanlarim"))
        cleanup_ilan_relations(atik_id=ilan.id)
        db.session.delete(ilan)
        flash("Atık ilanı silindi.", "success")
    db.session.commit()
    return redirect(url_for("ilan.ilanlarim"))


@ilan_bp.route("/ilan_durum_guncelle/<tur>/<int:id>", methods=["POST"])
@login_required
def ilan_durum_guncelle(tur, id):
    yeni_durum = request.form.get("ilan_durumu")
    if yeni_durum not in ILAN_DURUMLARI:
        flash("Geçersiz ilan durumu.", "danger")
        return redirect(url_for("ilan.ilanlarim"))

    if tur == "kaynak":
        ilan = Kaynak.query.get_or_404(id)
    else:
        ilan = Atik.query.get_or_404(id)

    if ilan.user_id != current_user.id:
        flash("Bu ilanı güncelleme yetkiniz yok.", "danger")
        return redirect(url_for("ilan.ilanlarim"))

    eski_durum = ilan.ilan_durumu
    ilan.ilan_durumu = yeni_durum
    sonuc = ilan_durum_etki_sync(ilan, tur, eski_durum, yeni_durum)
    db.session.commit()
    if sonuc and sonuc[0] == "eklendi":
        _teslim_gamification(ilan)
    _etki_durum_mesajlari(ilan, tur, sonuc)
    return redirect(url_for("ilan.ilanlarim"))


@ilan_bp.route("/ilan_duzenle/kaynak/<int:id>", methods=["GET", "POST"])
@login_required
@ai_analiz_limit
def ilan_duzenle_kaynak(id):
    ilan = Kaynak.query.get_or_404(id)
    if ilan.user_id != current_user.id:
        flash("Bu ilanı düzenleme yetkiniz yok.", "danger")
        return redirect(url_for("ilan.ilanlarim"))

    if request.method == "POST":
        eski_durum = ilan.ilan_durumu
        ilan.baslik = sanitize_input(request.form.get("baslik"), max_length=100)
        ilan.aciklama = sanitize_input(request.form.get("aciklama"), max_length=2000)
        ilan.durum = request.form.get("durum")
        ilan.kategori = request.form.get("kategori")
        ilan_durumu = request.form.get("ilan_durumu")
        if ilan_durumu in ILAN_DURUMLARI:
            ilan.ilan_durumu = ilan_durumu

        lat, lng, _ = parse_coordinates(
            request.form.get("latitude"), request.form.get("longitude"), user=current_user
        )
        ilan.latitude = lat
        ilan.longitude = lng

        foto_hata = _ilan_foto_guncelle(ilan, "kaynak")
        if foto_hata:
            flash(foto_hata, "danger")
            return redirect(url_for("ilan.ilan_duzenle_kaynak", id=id))

        ai_sonuc, karar = _ilan_metin_moderasyonu_uygula(ilan, "kaynak")
        if karar is None:
            flash(
                f"Metin moderasyonu: İçerik yayınlanamadı (Skor: {ai_sonuc.get('risk_skoru', 0)}/100). "
                f"{ai_sonuc.get('reason') or 'Admin onayı gerekiyor.'}",
                "danger",
            )
            db.session.rollback()
            return redirect(url_for("ilan.ilan_duzenle_kaynak", id=id))

        sonuc = ilan_durum_etki_sync(ilan, "kaynak", eski_durum, ilan.ilan_durumu)
        db.session.commit()
        if sonuc and sonuc[0] == "eklendi":
            _teslim_gamification(ilan)
            _etki_durum_mesajlari(ilan, "kaynak", sonuc)
        elif sonuc and sonuc[0] == "silindi":
            flash("Kaynak ilanı güncellendi. Çevresel etki kaydı geri alındı.", "info")
        else:
            flash("Kaynak ilanı güncellendi.", "success")
        return redirect(url_for("ilan.ilanlarim"))

    ensure_ilan_fotograflari(ilan, "kaynak")
    db.session.commit()
    return render_template(
        "ilan_duzenle.html",
        ilan=ilan,
        tur="kaynak",
        kategoriler=KATEGORILER_KAYNAK,
        durumlar=DURUMLAR_KAYNAK,
        ilan_durumlari=ILAN_DURUMLARI,
        max_foto=MAX_ILAN_FOTOSU,
    )


@ilan_bp.route("/ilan_duzenle/atik/<int:id>", methods=["GET", "POST"])
@login_required
@ai_analiz_limit
def ilan_duzenle_atik(id):
    ilan = Atik.query.get_or_404(id)
    if ilan.user_id != current_user.id:
        flash("Bu ilanı düzenleme yetkiniz yok.", "danger")
        return redirect(url_for("ilan.ilanlarim"))

    if request.method == "POST":
        eski_durum = ilan.ilan_durumu
        ilan.baslik = sanitize_input(request.form.get("baslik"), max_length=100)
        ilan.aciklama = sanitize_input(request.form.get("aciklama"), max_length=2000)
        ilan.kategori = request.form.get("kategori")
        ilan_durumu = request.form.get("ilan_durumu")
        if ilan_durumu in ILAN_DURUMLARI:
            ilan.ilan_durumu = ilan_durumu

        lat, lng, _ = parse_coordinates(
            request.form.get("latitude"), request.form.get("longitude"), user=current_user
        )
        ilan.latitude = lat
        ilan.longitude = lng

        foto_hata = _ilan_foto_guncelle(ilan, "atik")
        if foto_hata:
            flash(foto_hata, "danger")
            return redirect(url_for("ilan.ilan_duzenle_atik", id=id))

        ai_sonuc, karar = _ilan_metin_moderasyonu_uygula(ilan, "atik")
        if karar is None:
            flash(
                f"Metin moderasyonu: İçerik yayınlanamadı (Skor: {ai_sonuc.get('risk_skoru', 0)}/100). "
                f"{ai_sonuc.get('reason') or 'Admin onayı gerekiyor.'}",
                "danger",
            )
            db.session.rollback()
            return redirect(url_for("ilan.ilan_duzenle_atik", id=id))

        sonuc = ilan_durum_etki_sync(ilan, "atik", eski_durum, ilan.ilan_durumu)
        db.session.commit()
        if sonuc and sonuc[0] == "eklendi":
            _teslim_gamification(ilan)
            _etki_durum_mesajlari(ilan, "atik", sonuc)
        elif sonuc and sonuc[0] == "silindi":
            flash("Atık ilanı güncellendi. Çevresel etki kaydı geri alındı.", "info")
        else:
            flash("Atık ilanı güncellendi.", "success")
        return redirect(url_for("ilan.ilanlarim"))

    ensure_ilan_fotograflari(ilan, "atik")
    db.session.commit()
    return render_template(
        "ilan_duzenle.html",
        ilan=ilan,
        tur="atik",
        kategoriler=KATEGORILER_ATIK,
        ilan_durumlari=ILAN_DURUMLARI,
        max_foto=MAX_ILAN_FOTOSU,
    )
