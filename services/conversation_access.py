"""Yetkili sohbet bağlamı — URL parametreleri yalnızca anahtar; ilan/kullanıcı DB'den."""

from __future__ import annotations

from dataclasses import dataclass

from extensions import db
from models import Atik, Kaynak, User
from sockets.permissions import user_can_access_conversation
from sockets.rooms import canonical_conversation_id


@dataclass(frozen=True)
class ConversationContext:
    partner: User
    kaynak_id: int
    atik_id: int
    urun: Kaynak | Atik | None
    conversation_id: str
    canonical_conversation_id: str


def normalize_listing_ids(kaynak_id, atik_id) -> tuple[int, int]:
    return int(kaynak_id or 0), int(atik_id or 0)


def resolve_authorized_conversation(
    viewer_id: int,
    partner_id: int,
    kaynak_id=0,
    atik_id=0,
) -> ConversationContext | None:
    """
    URL'deki (partner_id, kaynak_id, atik_id) yalnızca sohbet anahtarıdır.

    - Yetki yoksa None (çağıran 403 döner).
    - Partner ve ilan, erişim onayından sonra veritabanından yüklenir.
    - Aynı anda hem kaynak hem atık kimliği geçersizdir.
    """
    partner_id = int(partner_id or 0)
    k_id, a_id = normalize_listing_ids(kaynak_id, atik_id)

    if partner_id <= 0:
        return None
    if k_id and a_id:
        return None
    if not user_can_access_conversation(viewer_id, partner_id, k_id, a_id):
        return None

    partner = db.session.get(User, partner_id)
    if not partner:
        return None

    urun: Kaynak | Atik | None = None
    if k_id:
        urun = db.session.get(Kaynak, k_id)
    elif a_id:
        urun = db.session.get(Atik, a_id)

    return ConversationContext(
        partner=partner,
        kaynak_id=k_id,
        atik_id=a_id,
        urun=urun,
        conversation_id=f"{partner.id}-{k_id}-{a_id}",
        canonical_conversation_id=canonical_conversation_id(
            viewer_id, partner.id, k_id, a_id
        ),
    )
