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
    DESTEK_KATEGORILERI,
    DESTEK_KATEGORI_BAN_ITIRAZI_LABEL,
    EMAIL_VERIFY_REQUIRED_MSG,
    RATE_DESTEK_AUTH,
    RATE_DESTEK_GUEST,
)
from decorators import _verification_required
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
from services.support_tickets import (
    create_authenticated_support_ticket,
    create_guest_support_ticket,
    notify_new_support_ticket,
)
from services.user_moderation import is_user_banned
from utils import sanitize_input

logger = logging.getLogger(__name__)

support_bp = Blueprint("support", __name__)


def _destek_rate_limit():
    if current_user.is_authenticated:
        return RATE_DESTEK_AUTH
    return RATE_DESTEK_GUEST


def _optional_support_image(file_storage):
    if not file_storage or not file_storage.filename:
        return None, None
    try:
        stored, original = store_support_image(file_storage)
        return stored, original
    except ValueError as exc:
        raise ValueError(str(exc)) from exc


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
def ban_itiraz():
    """Eski ban itiraz URL'si — destek sayfasına yönlendirilir."""
    if request.method == "POST":
        flash("Ban itirazları artık destek formu üzerinden gönderilir.", "info")
    return redirect(url_for("support.destek", kategori=DESTEK_KATEGORI_BAN_ITIRAZI_LABEL))


@support_bp.route("/destek", methods=["GET", "POST"])
@limiter.limit(_destek_rate_limit, methods=["POST"])
def destek():
    is_auth = current_user.is_authenticated
    selected_kategori = sanitize_input(request.args.get("kategori"), max_length=30)

    if request.method == "POST":
        if is_auth:
            if _verification_required():
                flash(EMAIL_VERIFY_REQUIRED_MSG, "warning")
                return redirect(url_for("auth.eposta_dogrula_bekle"))
            return _handle_authenticated_destek_post()

        captcha_err = captcha_hatasi()
        if captcha_err:
            flash(captcha_err, "danger")
            return redirect(url_for("support.destek"))

        return _handle_guest_destek_post()

    return render_template(
        "destek.html",
        kategoriler=DESTEK_KATEGORILERI,
        is_guest=not is_auth,
        selected_kategori=selected_kategori if selected_kategori in DESTEK_KATEGORILERI else "",
        user=current_user if is_auth else None,
    )


def _handle_guest_destek_post():
    ad = request.form.get("ad")
    soyad = request.form.get("soyad")
    email = request.form.get("email")
    telefon = request.form.get("telefon")
    kategori = request.form.get("kategori")
    baslik = request.form.get("baslik")
    mesaj = request.form.get("mesaj")

    ek_resim = None
    ek_orijinal = None
    file_storage = request.files.get("ek_resim")
    if file_storage and file_storage.filename:
        try:
            ek_resim, ek_orijinal = _optional_support_image(file_storage)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("support.destek"))

    try:
        talep = create_guest_support_ticket(
            ad=ad,
            soyad=soyad,
            email=email,
            telefon=telefon,
            kategori=kategori,
            baslik=baslik,
            mesaj=mesaj,
            ek_resim=ek_resim,
            ek_resim_orijinal=ek_orijinal,
        )
        notify_new_support_ticket(
            talep,
            admin_detail_url=url_for("admin.admin_destek_detail", talep_id=talep.id),
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("support.destek"))
    except Exception:
        db.session.rollback()
        logger.exception("Misafir destek talebi kaydedilemedi")
        flash("Talep gönderilemedi. Lütfen tekrar deneyin.", "danger")
        return redirect(url_for("support.destek"))

    flash("Destek talebiniz alındı. En kısa sürede incelenecektir.", "success")
    return redirect(url_for("support.destek"))


def _handle_authenticated_destek_post():
    baslik = request.form.get("baslik")
    kategori = request.form.get("kategori")
    mesaj = request.form.get("mesaj")

    ek_resim = None
    ek_orijinal = None
    file_storage = request.files.get("ek_resim")
    if file_storage and file_storage.filename:
        try:
            ek_resim, ek_orijinal = _optional_support_image(file_storage)
        except ValueError as exc:
            flash(str(exc), "danger")
            return redirect(url_for("support.destek"))

    try:
        talep = create_authenticated_support_ticket(
            current_user,
            kategori=kategori,
            baslik=baslik,
            mesaj=mesaj,
            ek_resim=ek_resim,
            ek_resim_orijinal=ek_orijinal,
        )
        notify_new_support_ticket(
            talep,
            admin_detail_url=url_for("admin.admin_destek_detail", talep_id=talep.id),
        )
    except ValueError as exc:
        flash(str(exc), "danger")
        return redirect(url_for("support.destek"))
    except Exception:
        db.session.rollback()
        logger.exception("Destek talebi kaydedilemedi user_id=%s", current_user.id)
        flash("Talep gönderilemedi. Lütfen tekrar deneyin.", "danger")
        return redirect(url_for("support.destek"))

    flash("Destek talebiniz alındı. En kısa sürede incelenecektir.", "success")
    user = db.session.get(User, int(current_user.get_id()))
    if user and is_user_banned(user):
        return redirect(url_for("support.destek"))
    return redirect(url_for("support.destek_taleplerim"))


@support_bp.route("/destek/taleplerim")
@login_required
def destek_taleplerim():
    talepler = (
        DestekTalebi.query.filter_by(user_id=current_user.id)
        .order_by(DestekTalebi.id.desc())
        .all()
    )
    return render_template("destek_taleplerim.html", talepler=talepler)
