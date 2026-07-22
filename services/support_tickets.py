"""Destek talebi oluşturma ve yönetim yardımcıları."""

from __future__ import annotations

import re

from flask import request

from constants import DESTEK_KATEGORILERI, DESTEK_KATEGORI_BAN_ITIRAZI_LABEL
from extensions import db
from models import DestekDurumGecmisi, DestekTalebi, User
from services.admin_notifications import notify_admins
from utils import sanitize_input, tr_time


def _request_meta() -> tuple[str | None, str | None]:
    from services.client_ip import client_ip

    ip = client_ip()
    user_agent = (request.headers.get("User-Agent") or "")[:500]
    return ip, user_agent or None


def _validate_guest_name(value: str, label: str) -> str:
    cleaned = sanitize_input(value, max_length=100)
    if len(cleaned) < 2:
        raise ValueError(f"{label} en az 2 karakter olmalıdır.")
    if not re.match(r"^[\w\sçğıöşüÇĞİÖŞÜ]+$", cleaned):
        raise ValueError(f"{label} yalnızca harf ve boşluk içerebilir.")
    return cleaned


def _validate_guest_email(email: str) -> str:
    cleaned = sanitize_input(email, max_length=150).lower().strip()
    if not re.match(r"^[\w.+-]+@[\w-]+\.[\w.-]+$", cleaned):
        raise ValueError("Geçerli bir e-posta adresi giriniz.")
    return cleaned


def _validate_kategori(kategori: str) -> str:
    cleaned = sanitize_input(kategori, max_length=30)
    if cleaned not in DESTEK_KATEGORILERI:
        raise ValueError("Geçersiz kategori seçimi.")
    return cleaned


def _record_initial_status(talep: DestekTalebi) -> None:
    db.session.add(
        DestekDurumGecmisi(
            talep=talep,
            eski_durum=None,
            yeni_durum=talep.durum,
            admin_id=None,
            not_metni="Talep oluşturuldu",
        )
    )


def create_guest_support_ticket(
    *,
    ad: str,
    soyad: str,
    email: str,
    telefon: str,
    kategori: str,
    baslik: str,
    mesaj: str,
    ek_resim: str | None = None,
    ek_resim_orijinal: str | None = None,
) -> DestekTalebi:
    guest_name = _validate_guest_name(ad, "Ad")
    guest_surname = _validate_guest_name(soyad, "Soyad")
    guest_email = _validate_guest_email(email)
    guest_phone = sanitize_input(telefon, max_length=20)
    if not guest_phone:
        raise ValueError("Telefon zorunludur.")
    kategori = _validate_kategori(kategori)
    baslik = sanitize_input(baslik, max_length=200)
    mesaj = sanitize_input(mesaj, max_length=5000)
    if not baslik or not mesaj:
        raise ValueError("Konu ve mesaj zorunludur.")

    ip_address, user_agent = _request_meta()
    talep = DestekTalebi(
        user_id=None,
        guest_name=guest_name,
        guest_surname=guest_surname,
        guest_email=guest_email,
        guest_phone=guest_phone,
        baslik=baslik,
        kategori=kategori,
        mesaj=mesaj,
        ek_resim=ek_resim,
        ek_resim_orijinal=ek_resim_orijinal,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.session.add(talep)
    db.session.flush()
    _record_initial_status(talep)
    db.session.commit()
    return talep


def create_authenticated_support_ticket(
    user: User,
    *,
    kategori: str,
    baslik: str,
    mesaj: str,
    ek_resim: str | None = None,
    ek_resim_orijinal: str | None = None,
) -> DestekTalebi:
    kategori = _validate_kategori(kategori)
    baslik = sanitize_input(baslik, max_length=200)
    mesaj = sanitize_input(mesaj, max_length=5000)
    if not baslik or not mesaj:
        raise ValueError("Başlık ve mesaj zorunludur.")

    ip_address, user_agent = _request_meta()
    talep = DestekTalebi(
        user_id=user.id,
        baslik=baslik,
        kategori=kategori,
        mesaj=mesaj,
        ek_resim=ek_resim,
        ek_resim_orijinal=ek_resim_orijinal,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    db.session.add(talep)
    db.session.flush()
    _record_initial_status(talep)
    db.session.commit()
    return talep


def notify_new_support_ticket(talep: DestekTalebi, *, admin_detail_url: str) -> None:
    if talep.user:
        sender = talep.user.username
    else:
        sender = f"{talep.guest_name} {talep.guest_surname}".strip()
    notify_admins(
        "Yeni Destek Talebi",
        f"{sender}: [{talep.kategori}] {talep.baslik}",
        "admin_destek",
        admin_detail_url,
    )


def record_support_status_change(
    talep: DestekTalebi,
    *,
    eski_durum: str,
    yeni_durum: str,
    admin_id: int | None,
    not_metni: str | None = None,
) -> None:
    if eski_durum == yeni_durum:
        return
    db.session.add(
        DestekDurumGecmisi(
            talep_id=talep.id,
            eski_durum=eski_durum,
            yeni_durum=yeni_durum,
            admin_id=admin_id,
            not_metni=not_metni,
            created_at=tr_time(),
        )
    )


def kategori_etiketi(kategori: str) -> str:
    if kategori == "BAN_ITIRAZI":
        return DESTEK_KATEGORI_BAN_ITIRAZI_LABEL
    return kategori
