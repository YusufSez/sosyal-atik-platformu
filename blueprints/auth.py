import json
import os
import re

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from auth_utils import hash_password, needs_password_update, verify_password
from extensions import db, limiter
from models import User
from services.captcha import captcha_hatasi
from utils import (
    delete_profile_picture,
    parse_coordinates,
    sanitize_input,
    save_profile_picture,
    validate_password,
)

auth_bp = Blueprint("auth", __name__)


@auth_bp.route("/kayit", methods=["GET", "POST"])
@limiter.limit("10 per hour")
def kayit():
    if current_user.is_authenticated:
        return redirect(url_for("main.anasayfa"))

    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("auth.kayit"))

        username = sanitize_input(request.form.get("username"), max_length=30)
        email = sanitize_input(request.form.get("email"), max_length=150).lower().strip()
        password = request.form.get("password")

        if len(username) < 3:
            flash("Kullanıcı adı en az 3 karakter olmalıdır.", "danger")
            return redirect(url_for("auth.kayit"))
        if not re.match(r"^[\w\s]+$", username):
            flash("Kullanıcı adı sadece harf, rakam ve boşluk içerebilir.", "danger")
            return redirect(url_for("auth.kayit"))
        if not re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", email):
            flash("Geçerli bir e-posta adresi giriniz.", "danger")
            return redirect(url_for("auth.kayit"))

        valid, msg = validate_password(password)
        if not valid:
            flash(msg, "danger")
            return redirect(url_for("auth.kayit"))

        if User.query.filter_by(email=email).first():
            flash("Bu e-posta zaten kayıtlı!", "danger")
            return redirect(url_for("auth.kayit"))
        if User.query.filter_by(username=username).first():
            flash("Bu kullanıcı adı zaten alınmış!", "danger")
            return redirect(url_for("auth.kayit"))

        new_user = User(username=username, email=email, password=hash_password(password))
        db.session.add(new_user)
        db.session.commit()
        session["temp_user_id"] = new_user.id
        flash("Kayıt başarılı! Şimdi profilinizi tamamlayın.", "success")
        return redirect(url_for("auth.profil_tamamla"))

    return render_template("register.html", title="Kayıt Ol")


@auth_bp.route("/profil_tamamla", methods=["GET", "POST"])
def profil_tamamla():
    temp_id = session.get("temp_user_id")
    if temp_id:
        user = db.session.get(User, temp_id)
    elif current_user.is_authenticated:
        user = current_user
    else:
        flash("Lütfen önce temel kayıt formunu doldurun.", "warning")
        return redirect(url_for("auth.kayit"))

    if not user:
        flash("Kullanıcı bulunamadı.", "warning")
        return redirect(url_for("auth.kayit"))

    json_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "static", "data", "il-ilce-list.json")
    with open(json_path, encoding="utf-8") as f:
        data = json.load(f)
    iller = {il["name"]: [d["name"] for d in il["districts"]] for il in data}

    if request.method == "POST":
        user.dogum_tarihi = sanitize_input(request.form.get("dogum_tarihi"), max_length=20)
        user.il = sanitize_input(request.form.get("il"), max_length=100)
        user.ilce = sanitize_input(request.form.get("ilce"), max_length=100)
        user.telefon = sanitize_input(request.form.get("telefon"), max_length=20)
        lat, lng, _ = parse_coordinates(request.form.get("latitude"), request.form.get("longitude"))
        if lat is not None and lng is not None:
            user.latitude = lat
            user.longitude = lng
        user.is_completed = True
        db.session.commit()
        session.pop("temp_user_id", None)
        login_user(user)
        flash("Profil başarıyla tamamlandı!", "success")
        return redirect(url_for("main.anasayfa"))

    return render_template("profil_tamamla.html", user=user, iller=iller, title="Profil Tamamla")


@auth_bp.route("/giris", methods=["GET", "POST"])
@limiter.limit("20 per hour")
def giris():
    if current_user.is_authenticated:
        return redirect(url_for("main.anasayfa"))

    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("auth.giris"))

        email = sanitize_input(request.form.get("email"), max_length=150).lower().strip()
        password = request.form.get("password")

        if not re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", email):
            flash("Geçerli bir e-posta adresi giriniz.", "danger")
            return redirect(url_for("auth.giris"))

        user = User.query.filter_by(email=email).first()
        if not user:
            flash("Bu e-posta ile kayıtlı bir kullanıcı bulunamadı. Lütfen kayıt olun.", "warning")
            return redirect(url_for("auth.kayit"))
        if not verify_password(password, user.password):
            flash("Hatalı e-posta veya şifre!", "danger")
            return redirect(url_for("auth.giris"))

        if needs_password_update(user.password):
            user.password = hash_password(password)
            db.session.commit()

        if not user.is_completed:
            session["temp_user_id"] = user.id
            flash("Lütfen önce profilinizi tamamlayın.", "warning")
            return redirect(url_for("auth.profil_tamamla"))

        login_user(user)
        flash("Giriş başarılı! Hoş geldiniz, " + user.username + "!", "success")
        return redirect(url_for("main.anasayfa"))

    return render_template("login.html", title="Giriş Yap")


@auth_bp.route("/cikis")
@login_required
def cikis():
    logout_user()
    flash("Çıkış yapıldı.", "success")
    return redirect(url_for("main.anasayfa"))


@auth_bp.route("/profil")
@login_required
def profil():
    from services.gamification import kullanici_rozet_listesi, kullanici_siralama, seviye_hesapla
    from services.impact import kullanici_ozeti

    rozetler = kullanici_rozet_listesi(current_user)
    kazanilan = sum(1 for r in rozetler if r["kazanildi"])
    return render_template(
        "profil.html",
        user=current_user,
        etki_ozet=kullanici_ozeti(current_user.id),
        seviye=seviye_hesapla(current_user.xp),
        siralama=kullanici_siralama(current_user.id),
        rozet_sayisi=kazanilan,
        rozet_toplam=len(rozetler),
    )


@auth_bp.route("/profil_foto", methods=["POST"])
@login_required
@limiter.limit("20 per hour")
def profil_foto():
    if "profil_resmi" not in request.files or not request.files["profil_resmi"].filename:
        flash("Lütfen bir görsel seçin.", "warning")
        return redirect(url_for("auth.profil"))
    try:
        new_image = save_profile_picture(request.files["profil_resmi"])
        delete_profile_picture(current_user.profile_image)
        current_user.profile_image = new_image
        db.session.commit()
        flash("Profil fotoğrafı güncellendi.", "success")
    except ValueError as exc:
        flash(str(exc), "danger")
    return redirect(url_for("auth.profil"))


@auth_bp.route("/sifre_degistir", methods=["GET", "POST"])
@login_required
def sifre_degistir():
    if request.method == "POST":
        mevcut = request.form.get("mevcut_sifre", "")
        yeni = request.form.get("yeni_sifre", "")
        yeni_tekrar = request.form.get("yeni_sifre_tekrar", "")

        if not verify_password(mevcut, current_user.password):
            flash("Mevcut şifre hatalı.", "danger")
            return redirect(url_for("auth.sifre_degistir"))
        if yeni != yeni_tekrar:
            flash("Yeni şifreler eşleşmiyor.", "danger")
            return redirect(url_for("auth.sifre_degistir"))
        valid, msg = validate_password(yeni)
        if not valid:
            flash(msg, "danger")
            return redirect(url_for("auth.sifre_degistir"))

        current_user.password = hash_password(yeni)
        db.session.commit()
        flash("Şifreniz güncellendi.", "success")
        return redirect(url_for("auth.profil"))

    return render_template("sifre_degistir.html", title="Şifre Değiştir")
