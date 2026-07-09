"""Production Security Phase 2 — upload güvenliği ve socket stabilitesi."""

import io
import os

import pytest
from PIL import Image
from werkzeug.datastructures import FileStorage

from utils import (
    _save_image_to_folder,
    _strip_exif,
    canonical_upload_basename,
    delete_picture,
    resolve_item_picture_path,
    resolve_safe_path_in_folder,
)


def test_canonical_basename_rejects_invalid_names():
    with pytest.raises(ValueError):
        canonical_upload_basename("default.jpg")
    with pytest.raises(ValueError):
        canonical_upload_basename("noextension")


def test_resolve_safe_path_stays_inside_folder(tmp_path):
    folder = tmp_path / "uploads"
    folder.mkdir()
    safe = resolve_safe_path_in_folder(str(folder), "../../photo.jpg")
    assert safe.startswith(str(folder.resolve()))


def test_delete_picture_ignores_traversal(app, tmp_path):
    outside = tmp_path / "outside.jpg"
    outside.write_bytes(b"x")
    with app.app_context():
        app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
        os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)
        delete_picture("../../outside.jpg")
    assert outside.exists()


def test_strip_exif_removes_gps_metadata():
    buf = io.BytesIO()
    img = Image.new("RGB", (16, 16), color="red")
    exif = img.getexif()
    exif[0x0110] = "TestCamera"
    exif[0x8825] = {1: "N"}
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    loaded = Image.open(buf)
    assert loaded.getexif()
    cleaned = _strip_exif(loaded)
    assert not cleaned.getexif()


def test_validate_rejects_oversized_pixels(app):
    from utils import _validate_image_bytes

    huge = Image.new("RGB", (6000, 6000), color="blue")
    buf = io.BytesIO()
    huge.save(buf, format="JPEG", quality=50)
    file_storage = FileStorage(
        stream=io.BytesIO(buf.getvalue()),
        filename="big.jpg",
        content_type="image/jpeg",
    )
    ok, err, _ = _validate_image_bytes(file_storage)
    assert not ok
    assert "çözünürlük" in (err or "").lower() or "yüksek" in (err or "").lower()


def test_save_image_strips_exif_on_disk(app, tmp_path):
    folder = tmp_path / "pics"
    folder.mkdir()
    buf = io.BytesIO()
    img = Image.new("RGB", (32, 32), color="green")
    exif = img.getexif()
    exif[0x0110] = "TestPhone"
    img.save(buf, format="JPEG", exif=exif)
    buf.seek(0)
    storage = FileStorage(stream=buf, filename="cam.jpg", content_type="image/jpeg")

    with app.app_context():
        app.config["UPLOAD_FOLDER"] = str(folder)
        name = _save_image_to_folder(storage, str(folder), (32, 32))
        path = resolve_item_picture_path(name)
        with Image.open(path) as saved:
            assert not saved.getexif()


def test_socket_sid_cleanup_on_disconnect(app):
    import socket_events

    socket_events._sid_users["sid-1"] = 42
    socket_events._user_sids[42].add("sid-1")
    socket_events._sid_conversations["sid-1"] = ["1-2-0-0"]
    socket_events._connection_counts[42] = 1
    socket_events._rate_buckets[42]["typing"] = [1.0]

    went = socket_events._finalize_disconnect(42, "sid-1", ["1-2-0-0"])

    assert went is True
    assert "sid-1" not in socket_events._sid_users
    assert 42 not in socket_events._user_sids
    assert 42 not in socket_events._rate_buckets
