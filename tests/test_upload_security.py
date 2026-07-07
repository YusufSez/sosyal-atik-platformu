import io

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from utils import _validate_image_bytes, allowed_file


def _make_image_file(ext="jpg", fmt="JPEG", content=b"not-an-image", content_type=None):
    if content == b"not-an-image":
        buf = io.BytesIO()
        Image.new("RGB", (8, 8), color="red").save(buf, format=fmt)
        content = buf.getvalue()
    return FileStorage(
        stream=io.BytesIO(content),
        filename=f"test.{ext}",
        content_type=content_type,
    )


def test_allowed_file_rejects_dangerous_extensions():
    assert not allowed_file("virus.exe")
    assert not allowed_file("shell.php")
    assert not allowed_file("xss.svg")
    assert not allowed_file("hack.js")
    assert not allowed_file("image.php.jpg")


def test_allowed_file_accepts_safe_extensions():
    assert allowed_file("photo.jpg")
    assert allowed_file("photo.jpeg")
    assert allowed_file("photo.png")
    assert allowed_file("photo.webp")


def test_validate_rejects_fake_jpeg_content():
    file_storage = FileStorage(
        stream=io.BytesIO(b"<?php echo 'x'; ?>"),
        filename="fake.jpg",
        content_type="image/jpeg",
    )
    ok, err, _ = _validate_image_bytes(file_storage)
    assert not ok
    assert "Geçersiz" in err


def test_validate_accepts_real_jpeg():
    file_storage = _make_image_file("jpg", "JPEG", content_type="image/jpeg")
    ok, err, fmt = _validate_image_bytes(file_storage)
    assert ok
    assert err is None
    assert fmt == "JPEG"


def test_validate_rejects_extension_content_mismatch():
    file_storage = _make_image_file("png", "JPEG", content_type="image/png")
    ok, err, _ = _validate_image_bytes(file_storage)
    assert not ok
    assert "uyuşmuyor" in err


def test_validate_rejects_wrong_mime_header():
    file_storage = _make_image_file("jpg", "JPEG", content_type="image/png")
    ok, err, _ = _validate_image_bytes(file_storage)
    assert not ok
    assert "MIME" in err
