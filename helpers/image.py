import os

from PIL import Image

from utils import resolve_item_picture_path_from_ref

MIME_MAP = {
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".webp": "image/webp",
}


def resim_mime_tipi(resim_yolu):
    ext = os.path.splitext(resim_yolu)[1].lower()
    return MIME_MAP.get(ext, "image/jpeg")


def resmi_bytes_oku(resim_yolu):
    path = resolve_item_picture_path_from_ref(resim_yolu)
    with open(path, "rb") as f:
        return f.read()


def resim_kontrol(resim_yolu):
    try:
        path = resolve_item_picture_path_from_ref(resim_yolu)
    except ValueError:
        return False
    try:
        with Image.open(path) as img:
            img.verify()
        with Image.open(path) as img:
            return img.format in ("JPEG", "PNG", "WEBP")
    except Exception:
        return False
