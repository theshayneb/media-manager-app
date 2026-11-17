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
    assert apply(light, Adjustments(shadows=80)).getpixel((0, 0))[0] - 215 < 6  # brights barely move
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
    assert meta.keywords == ["josh", "new york"] and meta.label == "Red" and meta.date_taken == taken


def test_auto_and_white_balance():
    from media_manager.photo_edit import auto, channel_gains, neutral, white_balance_at

    for rgb in [(150, 140, 110), (110, 130, 160), (140, 120, 130)]:
        y, r = neutral(*rgb)
        out = [c * k for c, k in zip(rgb, channel_gains(y / 100, r / 100), strict=True)]
        assert max(out) - min(out) < 3  # grey after
    assert neutral(128, 128, 128) == (0, 0)
    spot = Image.new("RGB", (40, 40), (90, 90, 90))
    spot.paste((200, 170, 120), (10, 10, 20, 20))
    assert white_balance_at(spot, 15, 15)[0] < 0  # the yellowish patch -> bluer
    dull = Image.linear_gradient("L").resize((64, 64)).point(lambda v: 90 + v // 4).convert("RGB")
    suggested = auto(dull)
    assert suggested["contrast"] > 20  # a flat, grey-ish picture gets more contrast
    dark = Image.linear_gradient("L").resize((64, 64)).point(lambda v: v // 3).convert("RGB")
    assert auto(dark)["shadows"] > 0
    assert auto(Image.new("RGB", (32, 32), (128, 128, 128))) == {
        "yellow": 0, "red": 0, "contrast": 0, "shadows": 0, "highlights": 0, "sharpness": 0, "clarity": 0,
        "brightness": 0}


def test_sliders_are_stronger():
    grey = Image.new("RGB", (1, 1), (128, 128, 128))
    r, g, b = apply(grey, Adjustments(yellow=100)).getpixel((0, 0))
    assert r - b > 70  # 0.4.0 gave about 38


def test_saturation_per_colour():
    import colorsys

    def sat(px):
        return colorsys.rgb_to_hsv(*[c / 255 for c in px])[1]

    red, orange, blue = (200, 60, 50), (220, 130, 40), (50, 90, 200)
    pic = Image.new("RGB", (3, 1))
    for x, c in enumerate((red, orange, blue)):
        pic.putpixel((x, 0), c)
    out = apply(pic, Adjustments(sat_blue=-80))
    assert sat(out.getpixel((2, 0))) < sat(blue) - 0.4  # blue loses its colour...
    assert abs(sat(out.getpixel((0, 0))) - sat(red)) < 0.02  # ...red and orange don't change
    assert abs(sat(out.getpixel((1, 0))) - sat(orange)) < 0.02
    out = apply(pic, Adjustments(sat_all=-100))
    assert all(sat(out.getpixel((x, 0))) < 0.02 for x in range(3))  # all colours gone: grey
    grey = Image.new("RGB", (1, 1), (128, 128, 128))
    assert apply(grey, Adjustments(sat_all=100)).getpixel((0, 0)) == (128, 128, 128)
    assert not Adjustments(sat_pink=5).unchanged()


def test_sharpness_and_clarity():
    from PIL import ImageFilter, ImageStat

    from media_manager.photo_edit import auto

    edge = Image.new("L", (3000, 100), 60)  # about a phone photo's width (the sharpening follows the size)
    edge.paste(190, (100, 0, 3000, 100))
    soft = edge.filter(ImageFilter.GaussianBlur(2)).convert("RGB")

    def contrast_at_edge(im):  # how steep the edge is
        return im.getpixel((101, 50))[0] - im.getpixel((98, 50))[0]

    sharp = apply(soft, Adjustments(sharpness=80))
    assert contrast_at_edge(sharp) > contrast_at_edge(soft)
    assert sharp.getpixel((20, 50)) == soft.getpixel((20, 50))  # flat areas untouched
    punch = apply(soft, Adjustments(clarity=80))
    softer = apply(soft, Adjustments(clarity=-80))
    spread = [ImageStat.Stat(im.crop((80, 40, 120, 60)).convert("L")).stddev[0] for im in (softer, soft, punch)]
    assert spread[0] < spread[1] < spread[2]
    # A cache (the Edit window's) gives the same picture.
    cache: dict = {}
    a = Adjustments(contrast=20, clarity=40, sharpness=30)
    first = apply(soft, a, cache)
    again = apply(soft, Adjustments(contrast=20, clarity=-20, sharpness=10), cache)
    assert again.tobytes() == apply(soft, Adjustments(contrast=20, clarity=-20, sharpness=10)).tobytes()
    assert first.tobytes() == apply(soft, a).tobytes()
    suggested = auto(soft.resize((400, 200)))
    assert 10 <= suggested["sharpness"] <= 40 and suggested["clarity"] in (12, 25)


def test_brightness():
    from media_manager.photo_edit import auto

    grey = Image.new("RGB", (1, 1), (100, 100, 100))
    values = [apply(grey, Adjustments(brightness=b)).getpixel((0, 0))[0] for b in (-60, 0, 60)]
    assert values[0] < 100 < values[2]
    assert apply(Image.new("RGB", (1, 1), (0, 0, 0)), Adjustments(brightness=100)).getpixel((0, 0)) == (0, 0, 0)
    dark = Image.linear_gradient("L").resize((64, 64)).point(lambda v: v // 3).convert("RGB")
    assert auto(dark)["brightness"] > 0
