import io
import os
import secrets

from PIL import Image
from werkzeug.utils import secure_filename

from constants import (
    ALLOWED_IMAGE_EXTENSIONS,
    ALLOWED_IMAGE_MIMES,
    BLOCKED_UPLOAD_EXTENSIONS,
    EXTENSION_TO_PIL_FORMAT,
    MAX_IMAGE_PIXELS,
    MAX_SINGLE_IMAGE_BYTES,
    PIL_FORMAT_TO_EXT,
    PIL_FORMAT_TO_MIME,
)

Image.MAX_IMAGE_PIXELS = MAX_IMAGE_PIXELS


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
