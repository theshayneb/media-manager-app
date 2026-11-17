"""Light photo editing: colour balance (blue/yellow, green/red), contrast, shadows and highlights.

All five are curves applied to each colour channel (a lookup table), so the preview updates as you drag
and a full-size photo saves in a moment. Saving works like Photo Manager's crop: the edited photo takes the
original's name (HEIC becomes JPG), every tag is copied over (dates, keywords, labels, GPS) and the original
goes to the Recycle Bin.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from photo_manager.core import thumbs  # noqa: F401  (registers the HEIC opener)
from photo_manager.core.crop import _flatten, _save_params
from photo_manager.core.fileops import unique_path

if TYPE_CHECKING:
    from photo_manager.core.exiftool import ExifTool

EDITABLE = {".jpg", ".jpeg", ".png", ".heic", ".heif"}
SAVED_AS_JPG = {".heic", ".heif"}


@dataclass
class Adjustments:
    """Each from -100 to 100; 0 = unchanged."""

    yellow: int = 0      # Blue (-) <-> Yellow (+)
    red: int = 0         # Green (-) <-> Red (+)
    contrast: int = 0    # Less (-) <-> More (+)
    shadows: int = 0     # Darker (-) <-> Lighter (+)
    highlights: int = 0  # Darker (-) <-> Brighter (+)

    def unchanged(self) -> bool:
        return not any((self.yellow, self.red, self.contrast, self.shadows, self.highlights))


def can_edit(path: str) -> bool:
    return Path(path).suffix.lower() in EDITABLE


# How far each slider's end goes (0.4.1: about twice 0.4.0's, at the user's request).
WARM = (0.20, 0.12, -0.40)    # red, green, blue change at Yellow +100
TINT = (0.30, -0.24, 0.0)     # at Red +100
CONTRAST_UP, CONTRAST_DOWN = 1.2, 0.8
LIFT = 0.7                    # shadows / highlights


def channel_gains(yellow: float, red: float) -> tuple[float, float, float]:
    """The red, green and blue multipliers for the two colour sliders (each -1..1)."""
    return tuple(1 + w * yellow + t * red for w, t in zip(WARM, TINT, strict=True))  # type: ignore[return-value]


def lookup_table(a: Adjustments) -> list[int]:
    """768 values: the R, G and B curves, for Image.point."""
    gains = channel_gains(a.yellow / 100, a.red / 100)
    c = a.contrast / 100
    contrast = 1 + (CONTRAST_UP if c >= 0 else CONTRAST_DOWN) * c
    shadows, highlights = LIFT * a.shadows / 100, LIFT * a.highlights / 100
    table: list[int] = []
    for gain in gains:
        for v in range(256):
            x = min(1.0, v / 255 * gain)
            x += shadows * (1 - x) ** 2 * (1 - (1 - x) ** 6)  # the dark part, not pure black
            x += highlights * x ** 2 * (1 - x ** 6)            # the bright part, not pure white
            x = (x - 0.5) * contrast + 0.5
            table.append(max(0, min(255, round(x * 255))))
    return table


# ------------------------------------------------------------------ auto and white balance
def _slider(value: float) -> int:
    return max(-100, min(100, round(value * 100)))


def neutral(r: float, g: float, b: float) -> tuple[int, int]:
    """The Blue/Yellow and Green/Red values that make a colour (r, g, b) grey."""
    if min(r, g, b) <= 0:
        return 0, 0
    # r*gain_r = g*gain_g = b*gain_b, with gain = 1 + WARM*w + TINT*t: two straight-line equations in w, t.
    (wr, wg, wb), (tr, tg, tb) = WARM, TINT
    a1, b1, c1 = wr * r - wg * g, tr * r - tg * g, g - r
    a2, b2, c2 = wg * g - wb * b, tg * g - tb * b, b - g
    det = a1 * b2 - a2 * b1
    if abs(det) < 1e-9:
        return 0, 0
    w = (c1 * b2 - c2 * b1) / det
    t = (a1 * c2 - a2 * c1) / det
    return _slider(w), _slider(t)


def white_balance_at(image: Image.Image, x: int, y: int, radius: int = 3) -> tuple[int, int]:
    """Blue/Yellow and Green/Red that make the spot around (x, y) white/grey."""
    from PIL import ImageStat

    box = (max(0, x - radius), max(0, y - radius), min(image.width, x + radius + 1), min(image.height, y + radius + 1))
    r, g, b = ImageStat.Stat(image.convert("RGB").crop(box)).mean[:3]
    return neutral(r, g, b)


def _percentile(histogram: list[int], fraction: float) -> int:
    total, running = sum(histogram), 0
    for value, count in enumerate(histogram):
        running += count
        if running >= total * fraction:
            return value
    return 255


def auto(image: Image.Image) -> dict[str, int]:
    """A suggestion for every slider from the photo itself:
    colour: the mid-tones should average out grey (a bit less than fully, so sunsets stay warm);
    contrast: the darkest and brightest 1% should come near black and white;
    shadows: lift the darkest tenth if it's very dark; highlights: tame the brightest tenth if near white
    (or brighten it a little in a dull photo)."""
    from PIL import ImageStat

    small = image.convert("RGB")
    small.thumbnail((400, 400))
    lum = small.convert("L")
    mid = lum.point(lambda v: 255 if 30 <= v <= 225 else 0)
    stat = ImageStat.Stat(small, mid) if mid.getbbox() else ImageStat.Stat(small)
    yellow, red = neutral(*stat.mean[:3])
    out = {"yellow": round(yellow * 0.8), "red": round(red * 0.8)}

    hist = lum.histogram()
    low, high = _percentile(hist, 0.01), _percentile(hist, 0.99)
    spread = high - low
    factor = max(0.7, min(1.5, 235 / spread)) if spread >= 30 else 1.0  # a near-flat picture is left alone
    out["contrast"] = _slider((factor - 1) / (CONTRAST_UP if factor >= 1 else CONTRAST_DOWN))

    x = _percentile(hist, 0.10) / 255
    shape = LIFT * (1 - x) ** 2 * (1 - (1 - x) ** 6)
    out["shadows"] = _slider((0.18 - x) / shape) if x < 0.18 and shape > 0.01 else 0
    out["shadows"] = max(0, out["shadows"])

    x = _percentile(hist, 0.90) / 255
    shape = LIFT * x ** 2 * (1 - x ** 6)
    if x > 0.86 and shape > 0.01:
        out["highlights"] = min(0, _slider((0.82 - x) / shape))
    elif x < 0.62 and shape > 0.01 and spread >= 30:
        out["highlights"] = max(0, min(40, _slider((0.70 - x) / shape)))
    else:
        out["highlights"] = 0
    return out


def apply(image: Image.Image, a: Adjustments) -> Image.Image:
    if a.unchanged():
        return image
    table = lookup_table(a)
    if image.mode == "RGBA":
        rgb = image.convert("RGB").point(table)
        rgb.putalpha(image.getchannel("A"))
        return rgb
    return image.convert("RGB").point(table)


def save_edit(path: str, a: Adjustments, et: "ExifTool | None" = None) -> str:
    """Apply a to the photo; returns where it is now (a HEIC comes back as .jpg)."""
    src_path = Path(path)
    as_jpg = src_path.suffix.lower() in SAVED_AS_JPG
    with Image.open(path) as src:
        src_fmt = src.format or ""
        src.seek(0)
        upright = ImageOps.exif_transpose(src)  # before _save_params resets Orientation
        out_fmt = "JPEG" if as_jpg else {"MPO": "JPEG"}.get(src_fmt, src_fmt) or "PNG"
        params = _save_params(out_fmt, src)
    image = apply(upright, a)
    if out_fmt == "JPEG":
        image = _flatten(image)
    ext = ".jpg" if as_jpg else src_path.suffix
    tmp = src_path.with_name(f"{src_path.stem}.editing{ext}")
    try:
        image.save(tmp, out_fmt, **params)
        if et is not None:
            error = et.write(str(tmp), [
                "-TagsFromFile", path, "-all:all", "-unsafe", "-icc_profile",
                "-FileCreateDate<FileCreateDate", "-FileModifyDate<FileModifyDate",
                "-Orientation#=1", f"-ExifImageWidth={image.width}", f"-ExifImageHeight={image.height}",
                "-ThumbnailImage=", "-PreviewImage=",
            ])
            if error and "Nothing to do" not in error:
                raise OSError(f"Couldn't copy the photo's details (dates, keywords, labels): {error}")
        dest = unique_path(src_path.with_suffix(".jpg")) if as_jpg else src_path
        from send2trash import send2trash

        send2trash(path)
        os.replace(tmp, dest)
        return str(dest)
    finally:
        if tmp.exists():
            tmp.unlink()


# ------------------------------------------------------------------ in Photos
def edit_selected(photos) -> None:  # type: ignore[no-untyped-def]
    """Open the selected photo in the Edit window; on Save, write it (on Photos' file thread)."""
    from PySide6.QtWidgets import QDialog, QMessageBox

    from .edit_dialog import EditDialog

    paths = photos.action_paths()
    if len(paths) != 1 or not can_edit(paths[0]):
        QMessageBox.information(photos, "Edit", "Select one photo (JPG, PNG or HEIC) to edit.")
        return
    path = paths[0]
    try:
        dialog = EditDialog(path, photos)
    except OSError as exc:
        QMessageBox.warning(photos, "Edit", f"Couldn't open the photo:\n{exc}")
        return
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return
    adjustments, et = dialog.adjustments(), photos.et
    photos.status.setText("Saving the edited photo…")

    def done(new_path, error: str | None) -> None:  # type: ignore[no-untyped-def]
        if error:
            QMessageBox.warning(photos, "Edit", f"The edit wasn't saved:\n{error}")
            photos.status.setText("Edit not saved.")
            return
        if os.path.normcase(new_path) == os.path.normcase(path):
            photos.model.refresh_file(new_path)
            photos.model.reload_thumb(new_path)
        else:  # a HEIC is a JPG now
            photos.model.remove_paths([path])
            photos.model.add_path(new_path)
            photos.regroup(select=[new_path], current=new_path)
            photos._show_count()
        photos._load_meta([new_path])
        if photos.previewing:
            photos._preview_show_current()
        photos.refresh_sidebar()
        photos.status.setText("Saved the edit. The original is in the Recycle Bin.")

    photos.bg.run(lambda: save_edit(path, adjustments, et), done)
