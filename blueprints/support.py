import logging

from flask import (
    Blueprint,
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from flask_login import current_user, login_required

from constants import (
    DESTEK_DURUMLARI,
    DESTEK_KATEGORILERI,
    DESTEK_KATEGORI_BAN_ITIRAZI,
    RATE_BAN_ITIRAZ,
)
from decorators import email_verified_required
from extensions import db, limiter
from models import DestekTalebi, User
from services.admin_notifications import notify_admins
from services.captcha import captcha_hatasi
from services.support_attachments import (
    attachment_exists,
    attachment_file_path,
    can_access_support_attachment,
    store_support_image,
)
from services.user_moderation import expire_temporary_bans, is_user_banned
from utils import sanitize_input

logger = logging.getLogger(__name__)

support_bp = Blueprint("support", __name__)


def _optional_support_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None
    try:
        stored, original = store_support_image(file_storage)
        return stored, original
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


def _find_banned_user_for_appeal(username: str, email: str) -> User | None:
    username = (username or "").strip()
    email = (email or "").strip().lower()
    if not username or not email:
        return None
    expire_temporary_bans()
    user = User.query.filter(
        db.func.lower(User.username) == username.lower(),
        db.func.lower(User.email) == email,
    ).first()
    if not user or not is_user_banned(user):
        return None
    return user


@support_bp.route("/support/attachment/<int:talep_id>")
@login_required
def support_attachment(talep_id: int):
    talep = DestekTalebi.query.get_or_404(talep_id)
    if not can_access_support_attachment(talep, current_user):
        abort(403)
    if not talep.ek_resim or not attachment_exists(talep.ek_resim):
        abort(404)
    try:
        path = attachment_file_path(talep.ek_resim)
    except ValueError:
        abort(404)
    download_name = talep.ek_resim_orijinal or talep.ek_resim
    return send_file(path, conditional=True, download_name=download_name)


@support_bp.route("/ban-itiraz", methods=["GET", "POST"])
@limiter.limit(RATE_BAN_ITIRAZ, methods=["POST"])
def ban_itiraz():
    if request.method == "POST":
        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("support.ban_itiraz"))

        username = sanitize_input(request.form.get("username"), max_length=150)
        email = sanitize_input(request.form.get("email"), max_length=150)
        mesaj = sanitize_input(request.form.get("mesaj"), max_length=5000)

        if not username or not email or not mesaj:
            flash("Kullanıcı adı, e-posta ve mesaj zorunludur.", "danger")
            return redirect(url_for("support.ban_itiraz"))

        user = _find_banned_user_for_appeal(username, email)
        if not user:
            flash(
                "Bilgiler doğrulanamadı. Yalnızca askıya alınmış hesaplar itiraz gönderebilir.",
                "danger",
            )
            return redirect(url_for("support.ban_itiraz"))

        ek_resim = None
        ek_orijinal = None
        file_storage = request.files.get("ek_resim")
        if file_storage and file_storage.filename:
            try:
                ek_resim, ek_orijinal = _optional_support_image(file_storage)
            except ValueError as exc:
                flash(str(exc), "danger")
                return redirect(url_for("support.ban_itiraz"))

        baslik = f"Ban itirazı — {user.username}"
        talep = DestekTalebi(
            user_id=user.id,
            baslik=baslik,
            kategori=DESTEK_KATEGORI_BAN_ITIRAZI,
            mesaj=mesaj,
            ek_resim=ek_resim,
            ek_resim_orijinal=ek_orijinal,
        )
        db.session.add(talep)
        try:
            db.session.commit()
            notify_admins(
                "Ban İtirazı",
                f"{user.username}: {mesaj[:200]}",
                "admin_destek",
                url_for("admin.admin_destek_detail", talep_id=talep.id),
            )
        except Exception:
            db.session.rollback()
            logger.exception("Ban itirazı kaydedilemedi user_id=%s", user.id)
            flash("İtiraz gönderilemedi. Lütfen tekrar deneyin.", "danger")
            return redirect(url_for("support.ban_itiraz"))

        flash("İtirazınız alındı. En kısa sürede incelenecektir.", "success")
        return redirect(url_for("auth.giris"))

    return render_template("ban_itiraz.html")


@support_bp.route("/destek", methods=["GET", "POST"])
@login_required
@email_verified_required
@limiter.limit("10 per hour", methods=["POST"])
def destek():
    if request.method == "POST":
        baslik = sanitize_input(request.form.get("baslik"), max_length=200)
        kategori = sanitize_input(request.form.get("kategori"), max_length=30)
        mesaj = sanitize_input(request.form.get("mesaj"), max_length=5000)
        if not baslik or not mesaj or kategori not in DESTEK_KATEGORILERI:
            flash("Başlık, kategori ve mesaj zorunludur.", "danger")
            return redirect(url_for("support.destek"))

        ek_resim = None
        ek_orijinal = None
        file_storage = request.files.get("ek_resim")
        if file_storage and file_storage.filename:
            try:
                ek_resim, ek_orijinal = _optional_support_image(file_storage)
            except ValueError as exc:
                flash(str(exc), "danger")
                return redirect(url_for("support.destek"))

        talep = DestekTalebi(
            user_id=current_user.id,
            baslik=baslik,
            kategori=kategori,
            mesaj=mesaj,
            ek_resim=ek_resim,
            ek_resim_orijinal=ek_orijinal,
        )
        db.session.add(talep)
        try:
            db.session.commit()
            notify_admins(
                "Yeni Destek Talebi",
                f"{current_user.username}: [{kategori}] {baslik}",
                "admin_destek",
                url_for("admin.admin_destek_detail", talep_id=talep.id),
            )
        except Exception:
            db.session.rollback()
            logger.exception("Destek talebi kaydedilemedi user_id=%s", current_user.id)
            flash("Talep gönderilemedi. Lütfen tekrar deneyin.", "danger")
            return redirect(url_for("support.destek"))

        flash("Destek talebiniz alındı. En kısa sürede incelenecektir.", "success")
        return redirect(url_for("support.destek_taleplerim"))

    return render_template(
        "destek.html",
        kategoriler=DESTEK_KATEGORILERI,
    )


@support_bp.route("/destek/taleplerim")
@login_required
def destek_taleplerim():
    talepler = (
        DestekTalebi.query.filter_by(user_id=current_user.id)
        .order_by(DestekTalebi.id.desc())
        .all()
    )
    return render_template("destek_taleplerim.html", talepler=talepler)
