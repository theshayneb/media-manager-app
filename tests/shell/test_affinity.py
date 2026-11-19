from io import BytesIO

from PIL import Image
from PySide6.QtWidgets import QApplication

from photo_manager.core.media import kind
from photo_manager.core.thumbs import thumbnail
from tests.shell.test_window import _music_folders, _wait


def fake_af(path, colour=(200, 40, 40)):
    """An Affinity .af as far as the preview goes: compressed parts, then "Thmb" + a PNG, then "Meta"."""
    png = BytesIO()
    Image.new("RGB", (512, 395), colour).save(png, "PNG")
    data = (b"\x00\xffKA\x0c\x00\x04\x02nsrP#Inf" + bytes(5000)
            + b"Thmb\x01\x00\x00\x00" + bytes(16) + b"\x01" + png.getvalue()
            + b"\xff\xff\xff\xffMeta\x01" + b'{"document":{"title":"t"}}')
    path.write_bytes(data)


def test_af_thumbnail(tmp_path):
    af = tmp_path / "8.5x11 - Borderless - Photos.af"
    fake_af(af)
    assert kind(str(af)) == "document" and kind("x.afphoto") is None  # only .af (and .psd)
    assert kind("3x4 - Card.psd") == "document"
    im = thumbnail(str(af), 256)
    assert im.size == (256, 198) and im.getpixel((10, 10))[0] > 150
    (tmp_path / "broken.af").write_bytes(b"no preview here")
    assert thumbnail(str(tmp_path / "broken.af"), 256) is None


def test_af_in_photos_opens_in_affinity(tmp_path, monkeypatch):
    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    folder = tmp_path / "Templates"
    folder.mkdir()
    af = folder / "template.af"
    fake_af(af)
    Image.new("RGB", (80, 60)).save(folder / "a.jpg")
    opened = []
    monkeypatch.setattr("PySide6.QtGui.QDesktopServices.openUrl", lambda url: opened.append(url.toLocalFile()))
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    win.show_kind("photos")
    photos = win.photos
    photos.open_folder(str(folder))
    assert _wait(lambda: photos.model.item(str(af)) is not None)
    photos.grid.select_paths([str(af)], current=str(af))
    photos.grid.activated.emit(photos.model.index(photos.model.row_of(str(af))))  # double-click
    assert opened and opened[0].endswith("template.af")
    assert not win.edit.active and not photos.previewing
    win.close()
