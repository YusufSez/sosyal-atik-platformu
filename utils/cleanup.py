from .upload import delete_picture


def _delete_comments_for_ilan(*, kaynak_id=None, atik_id=None):
    """Yorum yanıtlarını (parent_id) önce silerek FK ihlalini önler."""
    from models import Comment

    query = Comment.query
    if kaynak_id is not None:
        query = query.filter_by(kaynak_id=kaynak_id)
    if atik_id is not None:
        query = query.filter_by(atik_id=atik_id)
    query.filter(Comment.parent_id.isnot(None)).delete(synchronize_session=False)
    query.delete(synchronize_session=False)


def _collect_mesaj_ids(*, kaynak_id=None, atik_id=None) -> list[int]:
    from models import Mesaj

    query = Mesaj.query
    if kaynak_id is not None:
        query = query.filter_by(kaynak_id=kaynak_id)
    if atik_id is not None:
        query = query.filter_by(atik_id=atik_id)
    return [row[0] for row in query.with_entities(Mesaj.id).all()]


def _delete_sikayet_for_ilan(*, kaynak_id=None, atik_id=None, mesaj_ids=None):
    from sqlalchemy import or_

    from models import Sikayet

    conditions = []
    if kaynak_id is not None:
        conditions.append(Sikayet.kaynak_id == kaynak_id)
    if atik_id is not None:
        conditions.append(Sikayet.atik_id == atik_id)
    if mesaj_ids:
        conditions.append(Sikayet.mesaj_id.in_(mesaj_ids))
    if not conditions:
        return
    Sikayet.query.filter(or_(*conditions)).delete(synchronize_session=False)


def _delete_bildirim_for_mesajlar(mesaj_ids: list[int]) -> None:
    if not mesaj_ids:
        return
    from models import Bildirim

    Bildirim.query.filter(Bildirim.mesaj_id.in_(mesaj_ids)).delete(
        synchronize_session=False
    )


def _delete_mesajlar(*, kaynak_id=None, atik_id=None) -> None:
    from models import Mesaj

    query = Mesaj.query
    if kaynak_id is not None:
        query = query.filter_by(kaynak_id=kaynak_id)
    if atik_id is not None:
        query = query.filter_by(atik_id=atik_id)
    query.delete(synchronize_session=False)


def _delete_moderasyon_for_ilan(*, kaynak_id=None, atik_id=None):
    """Moderasyon tablolarını FK sırasına göre siler (karar/timeline → analiz)."""
    from models import (
        IlanModerasyonActivityLog,
        IlanModerasyonAnaliz,
        IlanModerasyonKarar,
        IlanModerasyonNot,
        IlanModerasyonTimeline,
    )

    def _q(model):
        query = model.query
        if kaynak_id is not None:
            query = query.filter_by(kaynak_id=kaynak_id)
        if atik_id is not None:
            query = query.filter_by(atik_id=atik_id)
        return query

    _q(IlanModerasyonKarar).delete(synchronize_session=False)
    _q(IlanModerasyonTimeline).delete(synchronize_session=False)
    _q(IlanModerasyonAnaliz).delete(synchronize_session=False)
    _q(IlanModerasyonNot).delete(synchronize_session=False)
    _q(IlanModerasyonActivityLog).delete(synchronize_session=False)


def _cleanup_ilan_side(*, kaynak_id=None, atik_id=None):
    """Tek ilan (kaynak veya atık) için tüm bağımlılıkları güvenli sırada temizler."""
    from models import Bildirim, CevreselEtki, Favori, Goruntulenme, IlanResim

    resim_q = IlanResim.query
    if kaynak_id is not None:
        resim_q = resim_q.filter_by(kaynak_id=kaynak_id)
    if atik_id is not None:
        resim_q = resim_q.filter_by(atik_id=atik_id)
    for foto in resim_q.all():
        delete_picture(foto.dosya)
    resim_q.delete(synchronize_session=False)

    mesaj_ids = _collect_mesaj_ids(kaynak_id=kaynak_id, atik_id=atik_id)

    _delete_sikayet_for_ilan(
        kaynak_id=kaynak_id,
        atik_id=atik_id,
        mesaj_ids=mesaj_ids,
    )
    _delete_comments_for_ilan(kaynak_id=kaynak_id, atik_id=atik_id)
    _delete_bildirim_for_mesajlar(mesaj_ids)
    _delete_mesajlar(kaynak_id=kaynak_id, atik_id=atik_id)
    _delete_moderasyon_for_ilan(kaynak_id=kaynak_id, atik_id=atik_id)

    favori_q = Favori.query
    gorunt_q = Goruntulenme.query
    etki_q = CevreselEtki.query
    if kaynak_id is not None:
        favori_q = favori_q.filter_by(kaynak_id=kaynak_id)
        gorunt_q = gorunt_q.filter_by(kaynak_id=kaynak_id)
        etki_q = etki_q.filter_by(kaynak_id=kaynak_id)
    if atik_id is not None:
        favori_q = favori_q.filter_by(atik_id=atik_id)
        gorunt_q = gorunt_q.filter_by(atik_id=atik_id)
        etki_q = etki_q.filter_by(atik_id=atik_id)
    favori_q.delete(synchronize_session=False)
    gorunt_q.delete(synchronize_session=False)
    etki_q.delete(synchronize_session=False)

    if kaynak_id is not None:
        Bildirim.query.filter(Bildirim.link.contains(f"/kaynak/{kaynak_id}")).delete(
            synchronize_session=False
        )
    if atik_id is not None:
        Bildirim.query.filter(Bildirim.link.contains(f"/atik/{atik_id}")).delete(
            synchronize_session=False
        )


def cleanup_ilan_relations(kaynak_id=None, atik_id=None):
    if kaynak_id:
        _cleanup_ilan_side(kaynak_id=kaynak_id)
    if atik_id:
        _cleanup_ilan_side(atik_id=atik_id)


def cleanup_atik_relations(atik_id):
    """Atık ilanı silinmeden önce bağımlılıkları temizler."""
    cleanup_ilan_relations(atik_id=atik_id)


def cleanup_kaynak_relations(kaynak_id):
    """Kaynak ilanı silinmeden önce bağımlılıkları temizler."""
    cleanup_ilan_relations(kaynak_id=kaynak_id)
