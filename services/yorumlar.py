"""Yorum ve cevap işlemleri."""

from flask import has_request_context, url_for

from extensions import db
from models import Comment
from services.notifications import bildirim_olustur
from services.query_options import yorum_agaci_options


def _yorum_bildirim_link(parent: Comment) -> str:
    anchor = f"yorum-{parent.id}"
    if has_request_context():
        if parent.kaynak_id:
            return url_for("kaynak.kaynak_detay", id=parent.kaynak_id, _anchor=anchor)
        return url_for("atik.atik_detay", id=parent.atik_id, _anchor=anchor)
    if parent.kaynak_id:
        return f"/kaynak/{parent.kaynak_id}#{anchor}"
    return f"/atik/{parent.atik_id}#{anchor}"


def kok_yorumlari_getir(*, kaynak_id=None, atik_id=None):
    q = Comment.query.filter_by(parent_id=None)
    if kaynak_id is not None:
        q = q.filter_by(kaynak_id=kaynak_id)
    elif atik_id is not None:
        q = q.filter_by(atik_id=atik_id)
    else:
        return []
    return q.options(*yorum_agaci_options()).order_by(Comment.timestamp.asc()).all()


def yorum_cevapla(user, parent_id: int, content: str) -> Comment:
    parent = Comment.query.get_or_404(parent_id)

    if parent.parent_id is not None:
        raise ValueError("Yalnızca ana yorumlara cevap verilebilir.")

    ilan = parent.kaynak or parent.atik
    if not ilan or ilan.user_id != user.id:
        raise PermissionError("Yalnızca ilan sahibi yorumlara cevap verebilir.")

    cevap = Comment(
        content=content,
        user_id=user.id,
        kaynak_id=parent.kaynak_id,
        atik_id=parent.atik_id,
        parent_id=parent.id,
    )
    db.session.add(cevap)
    db.session.commit()

    if parent.user_id != user.id:
        bildirim_olustur(
            parent.user_id,
            "Yorumunuza cevap",
            f"{user.username} yorumunuza cevap verdi.",
            "yorum",
            _yorum_bildirim_link(parent),
        )

    return cevap
