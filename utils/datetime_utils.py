from datetime import datetime, timezone
from zoneinfo import ZoneInfo

APP_TIMEZONE = ZoneInfo("Europe/Istanbul")
UTC = timezone.utc


def utc_now() -> datetime:
    """Veritabanına yazılacak UTC naive zaman damgası."""
    return datetime.now(UTC).replace(tzinfo=None)


def tr_time():
    """Model default değeri — tüm zaman damgaları UTC olarak saklanır."""
    return utc_now()


def to_local(dt: datetime | None) -> datetime | None:
    """UTC naive DB değerini Europe/Istanbul yerel saatine çevirir."""
    if dt is None:
        return None
    if dt.tzinfo is not None:
        utc = dt.astimezone(UTC)
    else:
        utc = dt.replace(tzinfo=UTC)
    return utc.astimezone(APP_TIMEZONE).replace(tzinfo=None)


def to_utc(dt: datetime | None) -> datetime | None:
    """Europe/Istanbul naive/aware değeri UTC naive'e çevirir (sorgu sınırları için)."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        local = dt.replace(tzinfo=APP_TIMEZONE)
    else:
        local = dt.astimezone(APP_TIMEZONE)
    return local.astimezone(UTC).replace(tzinfo=None)


def local_now() -> datetime:
    """Şu anki yerel saat (Europe/Istanbul, naive)."""
    return to_local(utc_now())


def format_datetime(dt: datetime | None, fmt: str = "%d.%m.%Y %H:%M") -> str:
    """DB'deki UTC naive değeri kullanıcıya yerel saat olarak gösterir."""
    if dt is None:
        return "-"
    return to_local(dt).strftime(fmt)
