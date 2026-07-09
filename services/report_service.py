"""Şikayet listeleme, filtreleme ve detay verisi."""

import re
from datetime import datetime

from sqlalchemy import and_, or_
from sqlalchemy.orm import joinedload

from constants import ADMIN_REPORTS_PER_PAGE, SIKAYET_DURUM_LEGACY_MAP, SIKAYET_DURUMLARI, SIKAYET_TURLERI
from extensions import db
from models import Mesaj, Sikayet, User
from services.user_moderation import kullanici_istatistikleri


def normalize_durum(durum: str | None) -> str:
    if not durum:
        return "Bekliyor"
    return SIKAYET_DURUM_LEGACY_MAP.get(durum, durum)


def durum_badge_class(durum: str) -> str:
    durum = normalize_durum(durum)
    mapping = {
        "Bekliyor": "warning",
        "İnceleniyor": "info",
        "İşlem Yapıldı": "success",
        "Reddedildi": "danger",
        "Kapatıldı": "secondary",
    }
    return mapping.get(durum, "secondary")


def role_badge_class(role: str) -> str:
    mapping = {
        "user": "secondary",
        "admin": "primary",
        "superadmin": "danger",
    }
    return mapping.get(role, "secondary")


def sikayet_turu_label(sikayet: Sikayet) -> str:
    tur = sikayet.tur
    if tur == "mesaj":
        return "Mesaj şikayeti"
    if tur == "kaynak":
        return "Kaynak ilanı şikayeti"
    if tur == "atik":
        return "Atık ilanı şikayeti"
    if sikayet.mesaj_id:
        return "Mesaj şikayeti"
    if sikayet.kaynak_id:
        return "Kaynak ilanı şikayeti"
    if sikayet.atik_id:
        return "Atık ilanı şikayeti"
    return "Şikayet"


def parse_aciklama(sikayet: Sikayet) -> str:
    if sikayet.aciklama:
        return sikayet.aciklama
    sebep = sikayet.sebep or ""
    if "| Açıklama:" in sebep:
        return sebep.split("| Açıklama:", 1)[1].strip()
    match = re.search(r"Mesaj şikayeti \(#\d+\):\s*(.+)$", sebep)
    if match and "|" not in match.group(1):
        return ""
    return ""


def report_detail_options():
    return [
        joinedload(Sikayet.user),
        joinedload(Sikayet.reported_user),
        joinedload(Sikayet.reviewer),
        joinedload(Sikayet.mesaj).joinedload(Mesaj.sender),
        joinedload(Sikayet.mesaj).joinedload(Mesaj.receiver),
        joinedload(Sikayet.kaynak),
        joinedload(Sikayet.atik),
    ]


def report_list_options():
    return [
        joinedload(Sikayet.user),
        joinedload(Sikayet.reported_user),
    ]


def build_report_query(args):
    Reporter = db.aliased(User)
    Reported = db.aliased(User)

    query = (
        Sikayet.query.options(*report_list_options())
        .outerjoin(Reporter, Sikayet.user_id == Reporter.id)
        .outerjoin(Reported, Sikayet.reported_user_id == Reported.id)
    )

    durum = (args.get("durum") or "").strip()
    if durum:
        if durum == "Bekliyor":
            query = query.filter(Sikayet.durum.in_(["Bekliyor", "Beklemede"]))
        else:
            query = query.filter(Sikayet.durum == durum)

    tur = (args.get("tur") or "").strip()
    if tur in SIKAYET_TURLERI:
        query = query.filter(Sikayet.tur == tur)

    if args.get("sadece_bekleyen") in ("1", "true", "on"):
        query = query.filter(Sikayet.durum.in_(["Bekliyor", "Beklemede", "İnceleniyor"]))

    username = (args.get("username") or "").strip()
    if username:
        query = query.filter(Reporter.username.ilike(f"%{username}%"))

    email = (args.get("email") or "").strip()
    if email:
        query = query.filter(Reporter.email.ilike(f"%{email}%"))

    reported = (args.get("reported_user") or "").strip()
    if reported:
        query = query.filter(Reported.username.ilike(f"%{reported}%"))

    if args.get("banli") in ("1", "true", "on"):
        query = query.filter(Reported.is_banned.is_(True))

    date_from = (args.get("date_from") or "").strip()
    if date_from:
        try:
            start = datetime.strptime(date_from, "%Y-%m-%d")
            query = query.filter(Sikayet.timestamp >= start)
        except ValueError:
            pass

    date_to = (args.get("date_to") or "").strip()
    if date_to:
        try:
            end = datetime.strptime(date_to, "%Y-%m-%d").replace(hour=23, minute=59, second=59)
            query = query.filter(Sikayet.timestamp <= end)
        except ValueError:
            pass

    q = (args.get("q") or "").strip()
    if q:
        like = f"%{q}%"
        query = query.outerjoin(Mesaj, Sikayet.mesaj_id == Mesaj.id).filter(
            or_(
                Reporter.username.ilike(like),
                Reporter.email.ilike(like),
                Reported.username.ilike(like),
                Reported.email.ilike(like),
                Sikayet.sebep.ilike(like),
                Sikayet.aciklama.ilike(like),
                Mesaj.content.ilike(like),
            )
        )

    return query.order_by(Sikayet.id.desc())


def paginate_reports(args, page: int):
    return build_report_query(args).paginate(
        page=page,
        per_page=ADMIN_REPORTS_PER_PAGE,
        error_out=False,
    )


def get_conversation_messages(mesaj: Mesaj) -> list:
    if not mesaj:
        return []
    pair_filter = or_(
        and_(Mesaj.sender_id == mesaj.sender_id, Mesaj.receiver_id == mesaj.receiver_id),
        and_(Mesaj.sender_id == mesaj.receiver_id, Mesaj.receiver_id == mesaj.sender_id),
    )
    context_filter = []
    if mesaj.kaynak_id:
        context_filter.append(Mesaj.kaynak_id == mesaj.kaynak_id)
    else:
        context_filter.append(Mesaj.kaynak_id.is_(None))
    if mesaj.atik_id:
        context_filter.append(Mesaj.atik_id == mesaj.atik_id)
    else:
        context_filter.append(Mesaj.atik_id.is_(None))

    return (
        Mesaj.query.filter(pair_filter, *context_filter)
        .options(joinedload(Mesaj.sender), joinedload(Mesaj.receiver))
        .order_by(Mesaj.timestamp.asc())
        .all()
    )


def build_report_detail_context(sikayet: Sikayet) -> dict:
    conversation = []
    if sikayet.mesaj:
        conversation = get_conversation_messages(sikayet.mesaj)

    reporter_stats = kullanici_istatistikleri(sikayet.user_id) if sikayet.user else {}
    reported_stats = {}
    if sikayet.reported_user_id:
        reported_stats = kullanici_istatistikleri(sikayet.reported_user_id)

    return {
        "sikayet": sikayet,
        "turu_label": sikayet_turu_label(sikayet),
        "aciklama": parse_aciklama(sikayet),
        "incelendi_mi": sikayet.reviewer_id is not None,
        "conversation": conversation,
        "highlight_mesaj_id": sikayet.mesaj_id,
        "reporter_stats": reporter_stats,
        "reported_stats": reported_stats,
        "durumlar": SIKAYET_DURUMLARI,
    }
