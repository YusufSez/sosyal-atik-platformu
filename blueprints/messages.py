from flask import Blueprint, abort, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required

from constants import RATE_MESSAGE, RATE_MESSAGE_FETCH
from decorators import email_verified_required
from extensions import db, limiter, rate_limit_user_or_ip
from models import Atik, Kaynak, Mesaj, User
from services.content_filter import mesaj_uygun_mu
from services.message_unread_cache import get_message_unread_count
from services.messaging_queries import (
    fetch_inbox_threads,
    fetch_message_page,
    serialize_fetched_message,
)
from services.notifications import bildirim_olustur
from socket_events import (
    canonical_conversation_id,
    emit_after_message_created,
    emit_messages_marked_read,
    presence_payload,
    serialize_message,
    user_can_access_conversation,
)
from utils import sanitize_input, utc_now

messages_bp = Blueprint("messages", __name__)


def _norm_conversation_ids(kaynak_id, atik_id) -> tuple[int, int]:
    return int(kaynak_id or 0), int(atik_id or 0)


def _require_conversation_access(partner_id: int, kaynak_id, atik_id):
    """Socket ile aynı yetki kontrolü; yetkisizse yanıt döner."""
    k_id, a_id = _norm_conversation_ids(kaynak_id, atik_id)
    if user_can_access_conversation(current_user.id, int(partner_id), k_id, a_id):
        return None
    if request.is_json or request.path.endswith("/send_message") or "/mesajlar_getir/" in request.path:
        return jsonify({"error": "Yetkisiz"}), 403
    abort(403)


def _persist_message(sender, receiver_id, content, kaynak_id, atik_id):
    mesaj = Mesaj(
        sender_id=sender.id,
        receiver_id=receiver_id,
        content=content,
        kaynak_id=kaynak_id if kaynak_id != 0 else None,
        atik_id=atik_id if atik_id != 0 else None,
    )
    db.session.add(mesaj)
    db.session.commit()
    mesaj = db.session.get(Mesaj, mesaj.id)
    bildirim_olustur(
        receiver_id,
        "Yeni mesaj",
        f"{sender.username} size mesaj gönderdi.",
        "mesaj",
        url_for(
            "messages.mesajlar",
            user_id=sender.id,
            kaynak_id=kaynak_id or 0,
            atik_id=atik_id or 0,
        ),
        mesaj_id=mesaj.id,
    )
    emit_after_message_created(mesaj)
    return mesaj


def _mark_conversation_read(alici_id, kaynak_id, atik_id):
    okunmamis = Mesaj.query.filter_by(
        sender_id=alici_id,
        receiver_id=current_user.id,
        kaynak_id=(kaynak_id if kaynak_id != 0 else None),
        atik_id=(atik_id if atik_id != 0 else None),
        is_read=False,
    ).all()
    if not okunmamis:
        return
    now = utc_now()
    for mesaj in okunmamis:
        mesaj.is_read = True
        mesaj.read_at = now
    db.session.commit()
    emit_messages_marked_read(okunmamis, current_user.id)


@messages_bp.before_app_request
def inject_unread_from_cache():
    if current_user.is_authenticated:
        g.unread_count = get_message_unread_count(
            current_user.id,
            warm_if_missing=True,
        )
    else:
        g.unread_count = 0


@messages_bp.route("/mesajlar/<int:user_id>/<int:kaynak_id>/<int:atik_id>", methods=["GET", "POST"])
@login_required
@email_verified_required
@limiter.limit(RATE_MESSAGE, methods=["POST"], key_func=rate_limit_user_or_ip)
@limiter.limit(RATE_MESSAGE_FETCH, methods=["GET"], key_func=rate_limit_user_or_ip)
def mesajlar(user_id, kaynak_id, atik_id):
    denied = _require_conversation_access(user_id, kaynak_id, atik_id)
    if denied:
        return denied

    alici = User.query.get_or_404(user_id)
    urun = None

    if kaynak_id != 0:
        urun = Kaynak.query.get_or_404(kaynak_id)
    if atik_id != 0:
        urun = Atik.query.get_or_404(atik_id)

    if request.method == "POST":
        icerik = sanitize_input(request.form.get("icerik"), max_length=2000)
        uygun, hata = mesaj_uygun_mu(icerik)
        if icerik and not uygun:
            flash(hata, "danger")
            return redirect(url_for("messages.mesajlar", user_id=alici.id, kaynak_id=kaynak_id, atik_id=atik_id))
        if icerik:
            _persist_message(current_user, alici.id, icerik, kaynak_id, atik_id)
        return redirect(url_for("messages.mesajlar", user_id=alici.id, kaynak_id=kaynak_id, atik_id=atik_id))

    return render_template(
        "mesajlar.html",
        alici=alici,
        kaynak_id=kaynak_id,
        atik_id=atik_id,
        urun=urun,
        conversation_id=f"{alici.id}-{kaynak_id}-{atik_id}",
        canonical_conversation_id=canonical_conversation_id(
            current_user.id, alici.id, kaynak_id, atik_id
        ),
        partner_presence=presence_payload(alici, alici.id),
    )


@messages_bp.route("/mesajlar_getir/<int:alici_id>/<int:kaynak_id>/<int:atik_id>")
@login_required
@limiter.limit(RATE_MESSAGE_FETCH, key_func=rate_limit_user_or_ip)
def mesajlar_getir(alici_id, kaynak_id, atik_id):
    denied = _require_conversation_access(alici_id, kaynak_id, atik_id)
    if denied:
        return denied

    before_id = request.args.get("before_id", type=int)
    mesajlar_list, has_more, oldest_id = fetch_message_page(
        current_user.id,
        alici_id,
        kaynak_id,
        atik_id,
        before_id=before_id,
    )

    if before_id is None:
        _mark_conversation_read(alici_id, kaynak_id, atik_id)

    return jsonify({
        "messages": [serialize_fetched_message(m) for m in mesajlar_list],
        "has_more": has_more,
        "oldest_id": oldest_id,
    })


@messages_bp.route("/mesajlarim")
@login_required
def mesajlarim():
    sohbetler = fetch_inbox_threads(current_user.id)
    return render_template("mesajlarim.html", sohbetler=sohbetler)


@messages_bp.route("/send_message", methods=["POST"])
@login_required
@email_verified_required
@limiter.limit(RATE_MESSAGE, methods=["POST"], key_func=rate_limit_user_or_ip)
def send_message():
    data = request.get_json() or {}
    alici_id = data.get("alici_id")
    content = sanitize_input(data.get("content"), max_length=2000)
    kaynak_id = data.get("kaynak_id")
    atik_id = data.get("atik_id")

    if not alici_id or not content:
        return jsonify({"error": "Eksik veri"}), 400

    denied = _require_conversation_access(int(alici_id), kaynak_id or 0, atik_id or 0)
    if denied:
        return denied

    uygun, hata = mesaj_uygun_mu(content)
    if not uygun:
        return jsonify({"error": hata}), 400

    mesaj = _persist_message(current_user, alici_id, content, kaynak_id or 0, atik_id or 0)

    return jsonify({
        "success": True,
        "message": serialize_message(mesaj, current_user.id),
    })
