from flask import Blueprint, flash, g, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from sqlalchemy.orm import joinedload

from constants import RATE_MESSAGE
from decorators import email_verified_required
from extensions import db, limiter, rate_limit_user_or_ip
from models import Atik, Kaynak, Mesaj, User
from services.content_filter import mesaj_uygun_mu
from services.notifications import bildirim_olustur
from socket_events import (
    canonical_conversation_id,
    emit_after_message_created,
    emit_messages_marked_read,
    is_user_online,
    presence_payload,
    serialize_message,
)
from utils import format_datetime, sanitize_input, utc_now

messages_bp = Blueprint("messages", __name__)


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
    )
    emit_after_message_created(mesaj)
    return mesaj


@messages_bp.before_app_request
def before_request():
    if current_user.is_authenticated:
        g.unread_count = Mesaj.query.filter_by(receiver_id=current_user.id, is_read=False).count()
    else:
        g.unread_count = 0


@messages_bp.route("/mesajlar/<int:user_id>/<int:kaynak_id>/<int:atik_id>", methods=["GET", "POST"])
@login_required
@email_verified_required
@limiter.limit(RATE_MESSAGE, methods=["POST"], key_func=rate_limit_user_or_ip)
def mesajlar(user_id, kaynak_id, atik_id):
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

    mesajlar_list = Mesaj.query.filter(
        ((Mesaj.sender_id == current_user.id) & (Mesaj.receiver_id == alici.id))
        | ((Mesaj.sender_id == alici.id) & (Mesaj.receiver_id == current_user.id)),
        Mesaj.kaynak_id == (kaynak_id if kaynak_id != 0 else None),
        Mesaj.atik_id == (atik_id if atik_id != 0 else None),
    ).options(joinedload(Mesaj.sender)).order_by(Mesaj.timestamp.asc()).all()

    return render_template(
        "mesajlar.html",
        alici=alici,
        mesajlar=mesajlar_list,
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
def mesajlar_getir(alici_id, kaynak_id, atik_id):
    mesajlar_list = Mesaj.query.filter(
        ((Mesaj.sender_id == current_user.id) & (Mesaj.receiver_id == alici_id))
        | ((Mesaj.sender_id == alici_id) & (Mesaj.receiver_id == current_user.id)),
        Mesaj.kaynak_id == (kaynak_id if kaynak_id != 0 else None),
        Mesaj.atik_id == (atik_id if atik_id != 0 else None),
    ).options(joinedload(Mesaj.sender)).order_by(Mesaj.timestamp.asc()).all()

    okunmamis = Mesaj.query.filter_by(
        sender_id=alici_id,
        receiver_id=current_user.id,
        kaynak_id=(kaynak_id if kaynak_id != 0 else None),
        atik_id=(atik_id if atik_id != 0 else None),
        is_read=False,
    ).all()
    now = utc_now()
    for m in okunmamis:
        m.is_read = True
        m.read_at = now
    if okunmamis:
        db.session.commit()
        emit_messages_marked_read(okunmamis, current_user.id)

    return jsonify([{
        "id": m.id,
        "content": m.content,
        "sender_id": m.sender_id,
        "sender_username": m.sender.username,
        "is_read": m.is_read,
        "read_at": m.read_at.isoformat() if m.read_at else None,
        "read_at_local": format_datetime(m.read_at) if m.read_at else None,
        "timestamp": format_datetime(m.timestamp, "%d.%m.%Y %H:%M"),
    } for m in mesajlar_list])


@messages_bp.route("/mesajlarim")
@login_required
def mesajlarim():
    mesajlar_list = Mesaj.query.filter(
        (Mesaj.sender_id == current_user.id) | (Mesaj.receiver_id == current_user.id)
    ).options(joinedload(Mesaj.sender), joinedload(Mesaj.receiver)).order_by(
        Mesaj.timestamp.desc()
    ).all()

    sohbetler = {}
    for m in mesajlar_list:
        other_id = m.receiver_id if m.sender_id == current_user.id else m.sender_id
        key = f"{other_id}-{m.kaynak_id or 0}-{m.atik_id or 0}"
        if key not in sohbetler:
            sohbetler[key] = {
                "msg": m,
                "user_id": other_id,
                "kaynak_id": m.kaynak_id,
                "atik_id": m.atik_id,
                "kaynak": db.session.get(Kaynak, m.kaynak_id) if m.kaynak_id else None,
                "atik": db.session.get(Atik, m.atik_id) if m.atik_id else None,
                "is_new": (not m.is_read) and (m.receiver_id == current_user.id),
            }

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

    uygun, hata = mesaj_uygun_mu(content)
    if not uygun:
        return jsonify({"error": hata}), 400

    mesaj = _persist_message(current_user, alici_id, content, kaynak_id or 0, atik_id or 0)

    return jsonify({
        "success": True,
        "message": serialize_message(mesaj, current_user.id),
    })
