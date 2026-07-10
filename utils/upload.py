import os

from flask import current_app
from PIL import Image
from werkzeug.utils import secure_filename

from .image import (
    _check_image_dimensions,
    _random_image_filename,
    _strip_exif,
    _validate_image_bytes,
    allowed_file,
)


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
