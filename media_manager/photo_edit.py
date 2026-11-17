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


def lookup_table(a: Adjustments) -> list[int]:
    """768 values: the R, G and B curves, for Image.point."""
    warm, tint = a.yellow / 100, a.red / 100
    gains = (1 + 0.10 * warm + 0.15 * tint,   # red
             1 + 0.06 * warm - 0.12 * tint,   # green
             1 - 0.20 * warm)                 # blue
    contrast = 1 + 0.6 * a.contrast / 100
    shadows, highlights = 0.35 * a.shadows / 100, 0.35 * a.highlights / 100
    table: list[int] = []
    for gain in gains:
        for v in range(256):
            x = min(1.0, v / 255 * gain)
            x += shadows * (1 - x) ** 2 * (1 - (1 - x) ** 6)  # the dark part, not pure black
            x += highlights * x ** 2 * (1 - x ** 6)            # the bright part, not pure white
            x = (x - 0.5) * contrast + 0.5
            table.append(max(0, min(255, round(x * 255))))
    return table


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
