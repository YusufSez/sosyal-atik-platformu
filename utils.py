import html
import io
import os
import re
import secrets

import bleach
from urllib.parse import urlparse

from flask import current_app, has_request_context, request
from flask_login import current_user
from PIL import Image
from werkzeug.utils import secure_filename

from constants import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIMES,
    BLOCKED_UPLOAD_EXTENSIONS,
    DEFAULT_LAT,
    DEFAULT_LNG,
    EXTENSION_TO_PIL_FORMAT,
    MAX_IMAGE_PIXELS,
    MAX_SINGLE_IMAGE_BYTES,
    PIL_FORMAT_TO_EXT,
    PIL_FORMAT_TO_MIME,
)
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from extensions import db

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS

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


def env_to_bool(value, default=False):
    if value is None:
        return default
    return str(value).strip().lower() in ("1", "true", "yes", "on")


def sanitize_input(text, max_length=None):
    """Metni temizler; HTML etiketlerini kaldırır (XSS önlemi)."""
    if not text:
        return ""
    text = bleach.clean(str(text), tags=[], attributes={}, strip=True)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = " ".join(text.split()).strip()
    if max_length and len(text) > max_length:
        text = text[:max_length]
    return text


def safe_redirect_url(target, default_endpoint="main.anasayfa"):
    """Harici open-redirect riskini önler; yalnızca aynı host veya göreli yollar."""
    if not target:
        from flask import url_for
        return url_for(default_endpoint)
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc:
        host = (request.host or "").split(":")[0].lower()
        ref_host = (parsed.netloc or "").split(":")[0].lower()
        if not ref_host or ref_host != host:
            from flask import url_for
            return url_for(default_endpoint)
    return target


def safe_notification_link(link, *, site_url=None):
    """Bildirim href: göreli yol veya aynı origin; javascript:/data: reddedilir."""
    if not link:
        return None
    link = str(link).strip()
    if not link:
        return None
    if link.startswith("//"):
        return None
    lower = link.lower()
    if lower.startswith(("javascript:", "data:", "vbscript:")):
        return None
    parsed = urlparse(link)
    if not parsed.scheme and not parsed.netloc:
        return link if link.startswith("/") else f"/{link}"
    scheme = (parsed.scheme or "").lower()
    if scheme in ("http", "https"):
        ref_host = (parsed.netloc or "").split(":")[0].lower()
        if site_url:
            site_host = urlparse(site_url).netloc.split(":")[0].lower()
            if ref_host and ref_host == site_host:
                return link
        if has_request_context():
            req_host = (request.host or "").split(":")[0].lower()
            if ref_host and ref_host == req_host:
                return link
        return None
    return None


def unescape_stored_text(text):
    """Eski kayıtlardaki HTML-escape edilmiş metinleri gösterim için düzeltir."""
    if not text:
        return ""
    if "&lt;" in text or "&gt;" in text or "&amp;" in text:
        return html.unescape(text)
    return text


def validate_password(password):
    if len(password) < 8:
        return False, "Şifre en az 8 karakter olmalıdır"
    if not any(c.isupper() for c in password):
        return False, "Şifre en az 1 büyük harf içermelidir"
    if not any(c.islower() for c in password):
        return False, "Şifre en az 1 küçük harf içermelidir"
    if not any(c.isdigit() for c in password):
        return False, "Şifre en az 1 rakam içermelidir"
    return True, "Şifre güvenli"


def allowed_file(filename):
    if not filename or "." not in filename:
        return False
    safe_name = secure_filename(filename).lower()
    if not safe_name:
        return False
    for part in safe_name.split(".")[1:]:
        if part in BLOCKED_UPLOAD_EXTENSIONS:
            return False
    ext = safe_name.rsplit(".", 1)[1]
    return ext in ALLOWED_IMAGE_EXTENSIONS


def canonical_upload_basename(filename: str) -> str:
    """Dosya adını basename + secure_filename ile normalize eder."""
    if not filename or filename == "default.jpg":
        raise ValueError("Geçersiz dosya adı")
    safe = os.path.basename(str(filename).replace("\\", "/"))
    if not safe or safe in (".", ".."):
        raise ValueError("Geçersiz dosya adı")
    safe = secure_filename(safe)
    if not safe or not allowed_file(safe):
        raise ValueError("Geçersiz dosya adı")
    return safe


def resolve_safe_path_in_folder(folder: str, filename: str) -> str:
    """Klasör içinde canonical path; dışına çıkış reddedilir."""
    safe = canonical_upload_basename(filename)
    base = os.path.realpath(os.path.abspath(folder))
    candidate = os.path.realpath(os.path.join(base, safe))
    if candidate != base and not candidate.startswith(base + os.sep):
        raise ValueError("Geçersiz dosya yolu")
    return candidate


def resolve_item_picture_path(filename: str) -> str:
    """UPLOAD_FOLDER altında güvenli ilan fotoğraf yolu."""
    return resolve_safe_path_in_folder(current_app.config["UPLOAD_FOLDER"], filename)


def resolve_profile_picture_path(filename: str) -> str:
    """profile_pics altında güvenli profil fotoğraf yolu."""
    folder = os.path.join(current_app.root_path, "static", "profile_pics")
    return resolve_safe_path_in_folder(folder, filename)


def resolve_item_picture_path_from_ref(path_or_name: str) -> str:
    """Dosya adı veya upload klasörü altındaki tam yol."""
    folder = current_app.config["UPLOAD_FOLDER"]
    base = os.path.realpath(os.path.abspath(folder))
    if os.path.isabs(path_or_name) or "/" in str(path_or_name).replace("\\", "/"):
        candidate = os.path.realpath(os.path.abspath(path_or_name))
        if candidate != base and not candidate.startswith(base + os.sep):
            raise ValueError("Geçersiz dosya yolu")
        return candidate
    return resolve_item_picture_path(path_or_name)


def _check_image_dimensions(img: Image.Image) -> None:
    width, height = img.size
    if width <= 0 or height <= 0:
        raise ValueError("Geçersiz görsel boyutu")
    if width * height > MAX_IMAGE_PIXELS:
        raise ValueError("Görsel çözünürlüğü çok yüksek")


def _strip_exif(img: Image.Image) -> Image.Image:
    """EXIF/GPS/kamera metadata kaldırır."""
    if img.mode in ("RGBA", "LA"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    if img.mode == "P":
        img = img.convert("RGBA")
        background = Image.new("RGB", img.size, (255, 255, 255))
        background.paste(img, mask=img.split()[-1])
        return background
    if img.mode != "RGB":
        img = img.convert("RGB")
    clean = Image.new("RGB", img.size)
    clean.paste(img)
    return clean


def _normalize_mime(mime_type):
    if not mime_type:
        return ""
    return mime_type.split(";")[0].strip().lower()


def _validate_image_bytes(file_storage):
    """Uzantı, MIME, boyut ve Pillow ile gerçek görsel içeriğini doğrula."""
    if not file_storage or not file_storage.filename:
        return False, "Dosya seçilmedi", None
    if not allowed_file(file_storage.filename):
        return False, "Sadece JPG, JPEG, PNG veya WEBP yüklenebilir", None

    safe_name = secure_filename(file_storage.filename).lower()
    claimed_ext = safe_name.rsplit(".", 1)[1]
    expected_format = EXTENSION_TO_PIL_FORMAT.get(claimed_ext)
    if not expected_format:
        return False, "Geçersiz dosya uzantısı", None

    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size == 0:
        return False, "Boş dosya yüklenemez", None
    if size > MAX_SINGLE_IMAGE_BYTES:
        max_mb = MAX_SINGLE_IMAGE_BYTES // (1024 * 1024)
        return False, f"Dosya boyutu {max_mb} MB sınırını aşıyor", None

    claimed_mime = _normalize_mime(getattr(file_storage, "content_type", None))
    if claimed_mime and claimed_mime not in ALLOWED_IMAGE_MIMES:
        return False, "Geçersiz dosya MIME türü", None

    try:
        raw = file_storage.read()
        file_storage.seek(0)
        with Image.open(io.BytesIO(raw)) as img:
            img.verify()
        with Image.open(io.BytesIO(raw)) as img:
            _check_image_dimensions(img)
            img.load()
            detected_format = (img.format or "").upper()
            if detected_format not in PIL_FORMAT_TO_EXT:
                return False, "Geçersiz görsel dosyası", None
            if detected_format != expected_format:
                return False, "Dosya uzantısı ile içerik uyuşmuyor", None
            if claimed_mime:
                expected_mime = PIL_FORMAT_TO_MIME.get(detected_format)
                if expected_mime and claimed_mime != expected_mime:
                    return False, "Dosya MIME türü ile içerik uyuşmuyor", None
        file_storage.seek(0)
    except ValueError as exc:
        file_storage.seek(0)
        return False, str(exc), None
    except Exception:
        file_storage.seek(0)
        return False, "Geçersiz görsel dosyası", None

    return True, None, expected_format


def _random_image_filename(pil_format):
    ext = PIL_FORMAT_TO_EXT.get(pil_format, ".jpg")
    return secrets.token_hex(16) + ext


def _save_image_to_folder(form_picture, folder, thumbnail_size):
    ok, err, pil_format = _validate_image_bytes(form_picture)
    if not ok:
        raise ValueError(err)

    os.makedirs(folder, exist_ok=True)
    picture_fn = _random_image_filename(pil_format)

    img = Image.open(form_picture)
    img.load()
    _check_image_dimensions(img)
    img.thumbnail(thumbnail_size)
    save_format = pil_format
    img = _strip_exif(img)
    picture_path = resolve_safe_path_in_folder(folder, picture_fn)
    img.save(picture_path, format=save_format, optimize=True, quality=85)
    form_picture.seek(0)
    return picture_fn


def resolve_support_attachment_path(filename: str) -> str:
    """Private destek ekleri klasöründe güvenli dosya yolu."""
    folder = current_app.config["SUPPORT_UPLOAD_FOLDER"]
    return resolve_safe_path_in_folder(folder, filename)


def save_support_attachment(form_picture):
    """İlan yükleme ile aynı güvenlik pipeline'ı (doğrulama + re-encode)."""
    folder = current_app.config["SUPPORT_UPLOAD_FOLDER"]
    return _save_image_to_folder(form_picture, folder, (600, 400))


def save_picture(form_picture):
    folder = current_app.config["UPLOAD_FOLDER"]
    return _save_image_to_folder(form_picture, folder, (600, 400))


def delete_picture(filename):
    if not filename or filename == "default.jpg":
        return
    try:
        path = resolve_item_picture_path(filename)
    except ValueError:
        return
    if os.path.isfile(path):
        os.remove(path)


def save_profile_picture(form_picture):
    folder = os.path.join(current_app.root_path, "static", "profile_pics")
    return _save_image_to_folder(form_picture, folder, (300, 300))


def delete_profile_picture(filename):
    if not filename or filename == "default.jpg":
        return
    try:
        path = resolve_profile_picture_path(filename)
    except ValueError:
        return
    if os.path.isfile(path):
        os.remove(path)


def parse_coordinates(lat_raw, lng_raw, user=None):
    try:
        lat = float(lat_raw) if lat_raw not in (None, "") else None
        lng = float(lng_raw) if lng_raw not in (None, "") else None
    except (TypeError, ValueError):
        lat, lng = None, None

    if lat is not None and lng is not None and -90 <= lat <= 90 and -180 <= lng <= 180:
        return lat, lng, False

    if user and getattr(user, "latitude", None) is not None and getattr(user, "longitude", None) is not None:
        return user.latitude, user.longitude, False

    return DEFAULT_LAT, DEFAULT_LNG, True


def is_varsayilan_konum(lat, lng, epsilon=0.001):
    """Koordinatların varsayılan İstanbul merkezine denk gelip gelmediğini kontrol eder."""
    if lat is None or lng is None:
        return True
    return abs(lat - DEFAULT_LAT) < epsilon and abs(lng - DEFAULT_LNG) < epsilon


def harita_noktalari(ilanlar):
    """Haritada gösterilecek ilanları gruplar; varsayılan konumdakileri hariç tutar."""
    gruplar = {}
    konumsuz = 0
    for ilan in ilanlar:
        if is_varsayilan_konum(ilan.latitude, ilan.longitude):
            konumsuz += 1
            continue
        anahtar = f"{round(ilan.latitude, 5)}:{round(ilan.longitude, 5)}"
        gruplar.setdefault(anahtar, []).append({
            "id": ilan.id,
            "baslik": ilan.baslik,
            "lat": ilan.latitude,
            "lng": ilan.longitude,
        })

    noktalar = []
    for grup in gruplar.values():
        noktalar.append({
            "lat": grup[0]["lat"],
            "lng": grup[0]["lng"],
            "ilanlar": grup,
        })
    return noktalar, konumsuz


def ilan_erisilebilir_mi(ilan, user=None):
    mod_status = getattr(ilan, "moderation_status", None) or "approved"
    if mod_status == "rejected":
        if user and getattr(user, "is_authenticated", False):
            if ilan.user_id == user.id or getattr(user, "is_admin", False):
                return True
        return False
    durum = getattr(ilan, "ilan_durumu", None) or "Aktif"
    if durum == "Aktif":
        return True
    if user and getattr(user, "is_authenticated", False):
        if ilan.user_id == user.id or getattr(user, "is_admin", False):
            return True
    return False


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


def mesafe_hesapla(lat1, lon1, lat2, lon2):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c


def ensure_schema():
    """Mevcut SQLite veritabanına yeni sütunları güvenli şekilde ekler."""
    from sqlalchemy import inspect, text

    if db.engine.dialect.name != "sqlite":
        return
    inspector = inspect(db.engine)
    if "user" in inspector.get_table_names():
        user_cols = {c["name"] for c in inspector.get_columns("user")}
        with db.engine.begin() as conn:
            if "latitude" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN latitude FLOAT"))
            if "longitude" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN longitude FLOAT"))
            if "is_admin" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_admin BOOLEAN DEFAULT 0"))
            if "guven_puani" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN guven_puani INTEGER DEFAULT 0"))
            if "is_kurum" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_kurum BOOLEAN DEFAULT 0"))
            if "xp" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN xp INTEGER DEFAULT 0"))
            # Production role + ban fields (SQLite only) for local compatibility
            if "role" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN role VARCHAR(20) DEFAULT 'user'"))
            if "is_banned" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_banned BOOLEAN DEFAULT 0"))
            if "banned_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN banned_at DATETIME"))
            if "ban_reason" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN ban_reason TEXT"))
            if "ban_expires_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN ban_expires_at DATETIME"))
            if "is_deactivated" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN is_deactivated BOOLEAN DEFAULT 0"))
            if "last_login_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_login_at DATETIME"))
            if "last_seen" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN last_seen DATETIME"))
            if "terms_accepted_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN terms_accepted_at DATETIME"))
            if "email_verified" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verified BOOLEAN DEFAULT 0"))
                conn.execute(text("UPDATE user SET email_verified = 1"))
            if "email_verified_at" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN email_verified_at DATETIME"))
            if "ad" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN ad VARCHAR(100)"))
            if "soyad" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN soyad VARCHAR(100)"))
            if "adres" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN adres VARCHAR(255)"))
            if "profil_aciklama" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN profil_aciklama TEXT"))
            if "telefon_verified" not in user_cols:
                conn.execute(text("ALTER TABLE user ADD COLUMN telefon_verified BOOLEAN DEFAULT 0"))

    if "destek_talebi" in inspector.get_table_names():
        destek_cols = {c["name"] for c in inspector.get_columns("destek_talebi")}
        with db.engine.begin() as conn:
            for col, ddl in (
                ("guest_name", "VARCHAR(100)"),
                ("guest_surname", "VARCHAR(100)"),
                ("guest_email", "VARCHAR(150)"),
                ("guest_phone", "VARCHAR(20)"),
                ("ip_address", "VARCHAR(45)"),
                ("user_agent", "VARCHAR(500)"),
            ):
                if col not in destek_cols:
                    conn.execute(text(f"ALTER TABLE destek_talebi ADD COLUMN {col} {ddl}"))

    if "comment" in inspector.get_table_names():
        comment_cols = {c["name"] for c in inspector.get_columns("comment")}
        with db.engine.begin() as conn:
            if "atik_id" not in comment_cols:
                conn.execute(text("ALTER TABLE comment ADD COLUMN atik_id INTEGER"))
            if "parent_id" not in comment_cols:
                conn.execute(text("ALTER TABLE comment ADD COLUMN parent_id INTEGER"))

    for table in ("kaynak", "atik"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        with db.engine.begin() as conn:
            if "ilan_durumu" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN ilan_durumu VARCHAR(50) DEFAULT 'Aktif'"))
            conn.execute(text(f"UPDATE {table} SET ilan_durumu = 'Aktif' WHERE ilan_durumu IS NULL"))
            if "moderation_status" not in cols:
                conn.execute(
                    text(f"ALTER TABLE {table} ADD COLUMN moderation_status VARCHAR(30) DEFAULT 'approved'")
                )
            if "moderation_reason" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN moderation_reason TEXT"))
            if "ai_risk_score" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN ai_risk_score INTEGER"))
            conn.execute(
                text(f"UPDATE {table} SET moderation_status = 'approved' WHERE moderation_status IS NULL")
            )

    if "sikayet" in inspector.get_table_names():
        sikayet_cols = {c["name"] for c in inspector.get_columns("sikayet")}
        with db.engine.begin() as conn:
            if "mesaj_id" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN mesaj_id INTEGER"))
            if "reported_user_id" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN reported_user_id INTEGER"))
            if "tur" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN tur VARCHAR(20)"))
            if "aciklama" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN aciklama TEXT"))
            if "reviewer_id" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN reviewer_id INTEGER"))
            if "reviewed_at" not in sikayet_cols:
                conn.execute(text("ALTER TABLE sikayet ADD COLUMN reviewed_at DATETIME"))

    if "admin_audit_log" in inspector.get_table_names():
        audit_cols = {c["name"] for c in inspector.get_columns("admin_audit_log")}
        with db.engine.begin() as conn:
            if "target_user_id" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN target_user_id INTEGER"))
            if "reason" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN reason TEXT"))
            if "old_value" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN old_value TEXT"))
            if "new_value" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN new_value TEXT"))
            if "user_agent" not in audit_cols:
                conn.execute(text("ALTER TABLE admin_audit_log ADD COLUMN user_agent VARCHAR(500)"))
