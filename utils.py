import html
import os
import re
from time import time

import bleach
from flask import current_app
from flask_login import current_user
from PIL import Image
from werkzeug.utils import secure_filename

from constants import ALLOWED_IMAGE_EXTENSIONS, DEFAULT_LAT, DEFAULT_LNG, MAX_SINGLE_IMAGE_BYTES
from extensions import db


def tr_time():
    import pytz
    from datetime import datetime
    return datetime.now(pytz.timezone("Europe/Istanbul"))


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
    return (
        "." in filename
        and filename.rsplit(".", 1)[1].lower() in ALLOWED_IMAGE_EXTENSIONS
    )


def _validate_image_bytes(file_storage):
    """Dosya uzantısı, boyutu ve gerçek görsel içeriğini doğrula."""
    if not file_storage or not file_storage.filename:
        return False, "Dosya seçilmedi"
    if not allowed_file(file_storage.filename):
        return False, "Sadece PNG, JPG, JPEG veya WEBP yüklenebilir"
    file_storage.seek(0, os.SEEK_END)
    size = file_storage.tell()
    file_storage.seek(0)
    if size > MAX_SINGLE_IMAGE_BYTES:
        max_mb = MAX_SINGLE_IMAGE_BYTES // (1024 * 1024)
        return False, f"Dosya boyutu {max_mb} MB sınırını aşıyor"
    try:
        img = Image.open(file_storage)
        img.verify()
        file_storage.seek(0)
        img = Image.open(file_storage)
        if img.format and img.format.upper() not in ("JPEG", "PNG", "WEBP"):
            file_storage.seek(0)
            return False, "Geçersiz görsel dosyası"
        file_storage.seek(0)
    except Exception:
        file_storage.seek(0)
        return False, "Geçersiz görsel dosyası"
    return True, None


def save_picture(form_picture):
    ok, err = _validate_image_bytes(form_picture)
    if not ok:
        raise ValueError(err)

    random_hex = str(time()).replace(".", "")
    f_ext = os.path.splitext(secure_filename(form_picture.filename))[1].lower()
    if f_ext == ".jpeg":
        f_ext = ".jpg"
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(current_app.config["UPLOAD_FOLDER"], picture_fn)

    img = Image.open(form_picture)
    img.thumbnail((600, 400))
    save_format = "JPEG" if f_ext in (".jpg", ".jpeg") else img.format or "PNG"
    if save_format == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(picture_path, format=save_format, optimize=True, quality=85)
    return picture_fn


def delete_picture(filename):
    if not filename or filename == "default.jpg":
        return
    path = os.path.join(current_app.config["UPLOAD_FOLDER"], filename)
    if os.path.isfile(path):
        os.remove(path)


def save_profile_picture(form_picture):
    ok, err = _validate_image_bytes(form_picture)
    if not ok:
        raise ValueError(err)

    folder = os.path.join(current_app.root_path, "static", "profile_pics")
    os.makedirs(folder, exist_ok=True)
    random_hex = str(time()).replace(".", "")
    f_ext = os.path.splitext(secure_filename(form_picture.filename))[1].lower()
    if f_ext == ".jpeg":
        f_ext = ".jpg"
    picture_fn = random_hex + f_ext
    picture_path = os.path.join(folder, picture_fn)

    img = Image.open(form_picture)
    img.thumbnail((300, 300))
    save_format = "JPEG" if f_ext in (".jpg", ".jpeg") else img.format or "PNG"
    if save_format == "JPEG" and img.mode in ("RGBA", "P"):
        img = img.convert("RGB")
    img.save(picture_path, format=save_format, optimize=True, quality=85)
    return picture_fn


def delete_profile_picture(filename):
    if not filename or filename == "default.jpg":
        return
    path = os.path.join(current_app.root_path, "static", "profile_pics", filename)
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
    durum = getattr(ilan, "ilan_durumu", None) or "Aktif"
    if durum == "Aktif":
        return True
    if user and getattr(user, "is_authenticated", False):
        if ilan.user_id == user.id or getattr(user, "is_admin", False):
            return True
    return False


def cleanup_ilan_relations(kaynak_id=None, atik_id=None):
    from models import Bildirim, Comment, CevreselEtki, Favori, Goruntulenme, IlanResim, Mesaj, Sikayet

    if kaynak_id:
        for foto in IlanResim.query.filter_by(kaynak_id=kaynak_id).all():
            delete_picture(foto.dosya)
        IlanResim.query.filter_by(kaynak_id=kaynak_id).delete()
        Comment.query.filter_by(kaynak_id=kaynak_id).delete()
        Mesaj.query.filter_by(kaynak_id=kaynak_id).delete()
        Favori.query.filter_by(kaynak_id=kaynak_id).delete()
        Goruntulenme.query.filter_by(kaynak_id=kaynak_id).delete()
        Sikayet.query.filter_by(kaynak_id=kaynak_id).delete()
        CevreselEtki.query.filter_by(kaynak_id=kaynak_id).delete()
        Bildirim.query.filter(Bildirim.link.contains(f"/kaynak/{kaynak_id}")).delete(synchronize_session=False)
    if atik_id:
        for foto in IlanResim.query.filter_by(atik_id=atik_id).all():
            delete_picture(foto.dosya)
        IlanResim.query.filter_by(atik_id=atik_id).delete()
        Comment.query.filter_by(atik_id=atik_id).delete()
        Mesaj.query.filter_by(atik_id=atik_id).delete()
        Favori.query.filter_by(atik_id=atik_id).delete()
        Goruntulenme.query.filter_by(atik_id=atik_id).delete()
        Sikayet.query.filter_by(atik_id=atik_id).delete()
        CevreselEtki.query.filter_by(atik_id=atik_id).delete()
        Bildirim.query.filter(Bildirim.link.contains(f"/atik/{atik_id}")).delete(synchronize_session=False)


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

    if "comment" in inspector.get_table_names():
        comment_cols = {c["name"] for c in inspector.get_columns("comment")}
        with db.engine.begin() as conn:
            if "atik_id" not in comment_cols:
                conn.execute(text("ALTER TABLE comment ADD COLUMN atik_id INTEGER"))

    for table in ("kaynak", "atik"):
        if table not in inspector.get_table_names():
            continue
        cols = {c["name"] for c in inspector.get_columns(table)}
        with db.engine.begin() as conn:
            if "ilan_durumu" not in cols:
                conn.execute(text(f"ALTER TABLE {table} ADD COLUMN ilan_durumu VARCHAR(50) DEFAULT 'Aktif'"))
            conn.execute(text(f"UPDATE {table} SET ilan_durumu = 'Aktif' WHERE ilan_durumu IS NULL"))
