import json
import os
import re
from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from flask_login import current_user, login_required, login_user, logout_user

from auth_utils import hash_password, needs_password_update, verify_password
from constants import (
    RATE_EMAIL_RESEND,
    RATE_LOGIN,
    RATE_PASSWORD_RESET,
    RATE_REGISTER,
)
from extensions import db, limiter, rate_limit_user_or_ip
from models import User
from services.captcha import captcha_hatasi
from services.email import dogrulama_epostasi_gonder, sifre_sifirlama_epostasi_gonder
from services.email_tokens import (
    create_reset_token,
    create_verify_token,
    peek_token,
    verify_email_token,
    verify_reset_token,
)
from services.user_moderation import expire_temporary_bans, is_user_banned
from utils import (
    delete_profile_picture,
    parse_coordinates,
    sanitize_input,
    save_profile_picture,
    utc_now,
    validate_password,
)

auth_bp = Blueprint("auth", __name__)


def _find_user_by_login(identifier: str):
    """Girilen değer e-posta (@ içeriyorsa) veya kullanıcı adı olarak aranır."""
    identifier = (identifier or "").strip()
    if not identifier:
        return None
    if "@" in identifier:
        email = identifier.lower()
        return User.query.filter(db.func.lower(User.email) == email).first()
    return User.query.filter(db.func.lower(User.username) == identifier.lower()).first()


@auth_bp.route("/kayit", methods=["GET", "POST"])
@limiter.limit(RATE_REGISTER, methods=["POST"])
def kayit():
    if current_user.is_authenticated:
        return redirect(url_for("main.anasayfa"))

    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("auth.kayit"))

        ad = sanitize_input(request.form.get("ad"), max_length=100)
        soyad = sanitize_input(request.form.get("soyad"), max_length=100)
        username = sanitize_input(request.form.get("username"), max_length=30)
        email = sanitize_input(request.form.get("email"), max_length=150).lower().strip()
        password = request.form.get("password")
        password_tekrar = request.form.get("password_tekrar")

        if len(ad) < 2:
            flash("Ad en az 2 karakter olmalıdır.", "danger")
            return redirect(url_for("auth.kayit"))
        if len(soyad) < 2:
            flash("Soyad en az 2 karakter olmalıdır.", "danger")
            return redirect(url_for("auth.kayit"))
        if not re.match(r"^[\w\sçğıöşüÇĞİÖŞÜ]+$", ad):
            flash("Ad yalnızca harf ve boşluk içerebilir.", "danger")
            return redirect(url_for("auth.kayit"))
        if not re.match(r"^[\w\sçğıöşüÇĞİÖŞÜ]+$", soyad):
            flash("Soyad yalnızca harf ve boşluk içerebilir.", "danger")
            return redirect(url_for("auth.kayit"))

        if len(username) < 3:
            flash("Kullanıcı adı en az 3 karakter olmalıdır.", "danger")
            return redirect(url_for("auth.kayit"))
        if not re.match(r"^[\w]+$", username):
            flash(
                "Kullanıcı adı yalnızca harf, rakam ve alt çizgi içerebilir (boşluk kullanmayın).",
                "danger",
            )
            return redirect(url_for("auth.kayit"))
        if not re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", email):
            flash("Geçerli bir e-posta adresi giriniz.", "danger")
            return redirect(url_for("auth.kayit"))

        valid, msg = validate_password(password)
        if not valid:
            flash(msg, "danger")
            return redirect(url_for("auth.kayit"))

        if password != password_tekrar:
            flash("Parolalar eşleşmiyor.", "danger")
            return redirect(url_for("auth.kayit"))

        if not request.form.get("kullanim_kosullari"):
            flash("Kayıt için Kullanım Koşulları ve Gizlilik Politikası'nı kabul etmelisiniz.", "danger")
            return redirect(url_for("auth.kayit"))

        if User.query.filter_by(email=email).first():
            flash("Bu e-posta zaten kayıtlı!", "danger")
            return redirect(url_for("auth.kayit"))
        if User.query.filter_by(username=username).first():
            flash("Bu kullanıcı adı zaten alınmış!", "danger")
            return redirect(url_for("auth.kayit"))

        new_user = User(
            username=username,
            ad=ad,
            soyad=soyad,
            email=email,
            password=hash_password(password),
            terms_accepted_at=utc_now(),
        )
        db.session.add(new_user)
        db.session.commit()

        if not new_user.email_verified:
            token = create_verify_token(new_user)
            if dogrulama_epostasi_gonder(new_user, token):
                flash(
                    "Kayıt başarılı! E-posta adresinize doğrulama bağlantısı gönderildi.",
                    "success",
                )
            else:
                flash(
                    "Kayıt başarılı! Doğrulama e-postası gönderilemedi. "
                    "Giriş yaptıktan sonra E-posta Doğrulama sayfasından tekrar deneyebilirsiniz.",
                    "warning",
                )
        else:
            flash("Kayıt başarılı! Şimdi profilinizi tamamlayın.", "success")
        session["temp_user_id"] = new_user.id
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
        from services.message_unread_cache import refresh_unread_cache

        refresh_unread_cache(user.id)
        flash("Profil başarıyla tamamlandı!", "success")
        return redirect(url_for("main.anasayfa"))

    return render_template("profil_tamamla.html", user=user, iller=iller, title="Profil Tamamla")


@auth_bp.route("/giris", methods=["GET", "POST"])
@limiter.limit(RATE_LOGIN, methods=["POST"])
def giris():
    if current_user.is_authenticated:
        return redirect(url_for("main.anasayfa"))

    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("auth.giris"))

        login_id = sanitize_input(request.form.get("email"), max_length=150).strip()
        password = request.form.get("password")

        if not login_id:
            flash("Kullanıcı adı veya e-posta gerekli.", "danger")
            return redirect(url_for("auth.giris"))

        user = _find_user_by_login(login_id)
        expire_temporary_bans()
        if user and getattr(user, "is_deactivated", False):
            flash("Hesabınız pasifleştirildi. Giriş yapamazsınız.", "danger")
            return redirect(url_for("auth.giris"))
        if user and is_user_banned(user):
            session["ban_notice"] = {
                "reason": user.ban_reason or "Belirtilmedi",
            }
            flash("Hesabınız askıya alınmıştır.", "danger")
            return redirect(url_for("auth.giris"))

        if not user or not verify_password(password, user.password):
            flash("Hatalı kullanıcı adı/e-posta veya şifre!", "danger")
            return redirect(url_for("auth.giris"))

        if needs_password_update(user.password):
            user.password = hash_password(password)
            db.session.commit()

        if not user.is_completed:
            session["temp_user_id"] = user.id
            flash("Lütfen önce profilinizi tamamlayın.", "warning")
            return redirect(url_for("auth.profil_tamamla"))

        login_user(user)
        from services.message_unread_cache import refresh_unread_cache

        refresh_unread_cache(user.id)
        user.last_login_at = utc_now()
        db.session.commit()
        flash("Giriş başarılı! Hoş geldiniz, " + user.username + "!", "success")
        return redirect(url_for("main.anasayfa"))

    return render_template("login.html", title="Giriş Yap", ban_notice=session.pop("ban_notice", None))


@auth_bp.route("/cikis")
@login_required
def cikis():
    from services.message_unread_cache import clear_unread_cache

    user_id = current_user.id
    logout_user()
    clear_unread_cache(user_id)
    flash("Çıkış yapıldı.", "success")
    return redirect(url_for("main.anasayfa"))


@auth_bp.route("/profil")
@login_required
def profil():
    from services.gamification import kullanici_rozet_listesi, kullanici_siralama, seviye_hesapla
    from services.impact import kullanici_ozeti
    from socket_events import is_user_online, presence_payload

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
        presence=presence_payload(current_user, current_user.id),
        is_online=is_user_online(current_user.id),
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
@limiter.limit(RATE_PASSWORD_RESET, methods=["POST"], key_func=rate_limit_user_or_ip)
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


def _send_verification_to_user(user):
    token = create_verify_token(user)
    return dogrulama_epostasi_gonder(user, token)


@auth_bp.route("/eposta-dogrula")
@login_required
def eposta_dogrula_bekle():
    return render_template("eposta_dogrula.html", title="E-posta Doğrulama")


@auth_bp.route("/eposta-dogrula/onay/<token>")
def eposta_dogrula_onay(token):
    user, error = verify_email_token(token)
    if error == "expired":
        flash("Doğrulama bağlantısının süresi dolmuş. Yeni bağlantı isteyin.", "warning")
        return redirect(url_for("auth.eposta_dogrula_bekle") if current_user.is_authenticated else url_for("auth.giris"))
    if not user:
        flash("Geçersiz veya kullanılmış doğrulama bağlantısı.", "danger")
        return redirect(url_for("auth.giris"))

    user.email_verified = True
    user.email_verified_at = utc_now()
    db.session.commit()
    flash("E-posta adresiniz başarıyla doğrulandı!", "success")
    if current_user.is_authenticated and current_user.id == user.id:
        return redirect(url_for("main.anasayfa"))
    return redirect(url_for("auth.giris"))


@auth_bp.route("/eposta-dogrula/tekrar-gonder", methods=["POST"])
@login_required
@limiter.limit(RATE_EMAIL_RESEND, methods=["POST"], key_func=rate_limit_user_or_ip)
def eposta_dogrula_tekrar():
    if current_user.email_verified:
        flash("E-posta adresiniz zaten doğrulanmış.", "info")
        return redirect(url_for("auth.profil"))

    if _send_verification_to_user(current_user):
        flash("Doğrulama e-postası tekrar gönderildi.", "success")
    else:
        flash("E-posta gönderilemedi. SMTP ayarlarını kontrol edin.", "danger")
    return redirect(url_for("auth.eposta_dogrula_bekle"))


@auth_bp.route("/sifremi-unuttum", methods=["GET", "POST"])
@limiter.limit(RATE_PASSWORD_RESET, methods=["POST"])
def sifremi_unuttum():
    if current_user.is_authenticated:
        return redirect(url_for("main.anasayfa"))

    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("auth.sifremi_unuttum"))

        email = sanitize_input(request.form.get("email"), max_length=150).lower().strip()
        user = User.query.filter_by(email=email).first()
        if user:
            token = create_reset_token(user)
            sifre_sifirlama_epostasi_gonder(user, token)

        flash(
            "E-posta adresiniz kayıtlıysa şifre sıfırlama bağlantısı gönderildi.",
            "info",
        )
        return redirect(url_for("auth.giris"))

    return render_template("sifremi_unuttum.html", title="Şifremi Unuttum")


@auth_bp.route("/sifre-sifirla/<token>", methods=["GET", "POST"])
@limiter.limit(RATE_PASSWORD_RESET, methods=["POST"])
def sifre_sifirla(token):
    if request.method == "GET":
        _, error = peek_token(token, "reset")
        if error == "expired":
            flash("Şifre sıfırlama bağlantısının süresi dolmuş.", "warning")
            return redirect(url_for("auth.sifremi_unuttum"))
        if error:
            flash("Geçersiz veya kullanılmış şifre sıfırlama bağlantısı.", "danger")
            return redirect(url_for("auth.sifremi_unuttum"))
        return render_template("sifre_sifirla.html", title="Şifre Sıfırla", token=token)

    user, error = verify_reset_token(token)
    if error == "expired":
        flash("Şifre sıfırlama bağlantısının süresi dolmuş.", "warning")
        return redirect(url_for("auth.sifremi_unuttum"))
    if not user:
        flash("Geçersiz veya kullanılmış şifre sıfırlama bağlantısı.", "danger")
        return redirect(url_for("auth.sifremi_unuttum"))

    yeni = request.form.get("yeni_sifre", "")
    yeni_tekrar = request.form.get("yeni_sifre_tekrar", "")
    if yeni != yeni_tekrar:
        flash("Şifreler eşleşmiyor.", "danger")
        return render_template("sifre_sifirla.html", title="Şifre Sıfırla", token=token)
    valid, msg = validate_password(yeni)
    if not valid:
        flash(msg, "danger")
        return render_template("sifre_sifirla.html", title="Şifre Sıfırla", token=token)

    user.password = hash_password(yeni)
    db.session.commit()
    flash("Şifreniz güncellendi. Giriş yapabilirsiniz.", "success")
    return redirect(url_for("auth.giris"))
