"""Kullanıcıya gösterilen moderasyon mesajları (AI detayı içermez)."""

from __future__ import annotations

from constants import (
    MODERATION_STATUS_APPROVED,
    MODERATION_STATUS_PENDING_REVIEW,
    MODERATION_STATUS_REJECTED,
)


def kullanici_moderasyon_mesaji(moderation_status: str | None) -> tuple[str, str]:
    """Kullanıcı flash mesajı ve kategori döndürür."""
    status = moderation_status or MODERATION_STATUS_APPROVED
    if status == MODERATION_STATUS_PENDING_REVIEW:
        return (
            "İlanınız yapay zekâ tarafından incelemeye alınmıştır. "
            "En kısa sürede kontrol edilecektir.",
            "info",
        )
    if status == MODERATION_STATUS_REJECTED:
        return (
            "İlanınız moderasyon nedeniyle yayınlanamadı.",
            "danger",
        )
    return ("İlanınız başarıyla yayınlandı.", "success")
