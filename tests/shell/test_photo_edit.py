from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from media_manager.photo_edit import Adjustments, apply, can_edit, lookup_table, save_edit
from photo_manager.core.exiftool import ExifTool, find_exiftool


def test_unchanged_is_unchanged():
    assert lookup_table(Adjustments()) == list(range(256)) * 3
    im = Image.new("RGB", (4, 4), (120, 110, 90))
    assert apply(im, Adjustments()).getpixel((0, 0)) == (120, 110, 90)


def test_each_slider_goes_the_right_way():
    grey = Image.new("RGB", (2, 2), (128, 128, 128))

    def px(**kw):
        return apply(grey, Adjustments(**kw)).getpixel((0, 0))

    r, g, b = px(yellow=60)
    assert b < 128 < r  # yellower: less blue
    r, g, b = px(yellow=-60)
    assert b > 128 > r  # bluer
    r, g, b = px(red=60)
    assert r > 128 > g  # redder
    r, g, b = px(red=-60)
    assert g > 128 > r  # greener
    dark, light = Image.new("RGB", (1, 1), (40, 40, 40)), Image.new("RGB", (1, 1), (215, 215, 215))
    assert apply(dark, Adjustments(contrast=60)).getpixel((0, 0))[0] < 40
    assert apply(light, Adjustments(contrast=60)).getpixel((0, 0))[0] > 215
    assert apply(dark, Adjustments(shadows=80)).getpixel((0, 0))[0] > 50  # shadows lighter
    assert apply(light, Adjustments(shadows=80)).getpixel((0, 0))[0] - 215 < 3  # brights barely move
    assert apply(light, Adjustments(highlights=-80)).getpixel((0, 0))[0] < 205  # highlights darker
    black = Image.new("RGB", (1, 1), (0, 0, 0))
    assert apply(black, Adjustments(shadows=100)).getpixel((0, 0)) == (0, 0, 0)  # black stays black


def test_which_files():
    assert can_edit("a.JPG") and can_edit("b.png") and can_edit("c.heic")
    assert not can_edit("d.mp4") and not can_edit("e.gif")


def test_save_replaces_and_recycles(tmp_path, monkeypatch):
    src = tmp_path / "IMG_1.jpg"
    Image.new("RGB", (64, 48), (128, 128, 128)).save(src, quality=95)
    trashed = []
    monkeypatch.setattr("send2trash.send2trash", lambda p: trashed.append(p) or Path(p).unlink())
    out = save_edit(str(src), Adjustments(yellow=80))
    assert out == str(src) and trashed == [str(src)]
    with Image.open(out) as im:
        r, g, b = im.convert("RGB").getpixel((10, 10))
        assert im.size == (64, 48) and b < r
    assert not list(tmp_path.glob("*.editing*"))


def test_heic_becomes_jpg(tmp_path, monkeypatch):
    pillow_heif = pytest.importorskip("pillow_heif")
    pillow_heif.register_heif_opener()
    src = tmp_path / "phone.heic"
    Image.new("RGB", (64, 32), "orange").save(src, "HEIF")
    monkeypatch.setattr("send2trash.send2trash", lambda p: Path(p).unlink())
    out = save_edit(str(src), Adjustments(contrast=30))
    assert Path(out).name == "phone.jpg" and not src.exists()
    with Image.open(out) as im:
        assert im.format == "JPEG" and im.size == (64, 32)


@pytest.mark.skipif(not find_exiftool(), reason="ExifTool not installed")
def test_keywords_and_date_survive(tmp_path, monkeypatch):
    from photo_manager.core.metadata import READ_TAGS, date_args, keyword_args, label_args, parse_meta

    src = tmp_path / "photo.jpg"
    Image.new("RGB", (32, 24), "green").save(src)
    monkeypatch.setattr("send2trash.send2trash", lambda p: Path(p).unlink())
    with ExifTool(find_exiftool()) as et:
        taken = datetime(2024, 6, 14, 18, 32, 5)
        et.write(str(src), date_args(str(src), taken, False))
        et.write(str(src), keyword_args(str(src), add=["josh", "new york"]))
        et.write(str(src), label_args("Red"))
        out = save_edit(str(src), Adjustments(shadows=40), et)
        [data] = et.read([out], READ_TAGS)
    meta = parse_meta(data)
    assert meta.keywords == ["josh", "new york"] and meta.label == "Red" and meta.taken == taken
