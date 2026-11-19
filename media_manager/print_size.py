"""Print copies for the scrapbook (Project Life pockets), the user's Affinity crop presets and macros in one:
crop to the right shape, resize to exact pixels at 600 DPI, add an even white border if wanted, and save a
JPG copy (the original stays as it is). Bordered or not, a size always ends up the same number of pixels,
so every print is the same size in the album.

The finished sizes are the user's Affinity macros' canvas sizes; the border is the same width all round
(BORDER px), taken off the photo part, never added to the finished size.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from pathlib import Path
from typing import TYPE_CHECKING

from PIL import Image, ImageOps

from photo_manager.core import thumbs  # noqa: F401  (registers the HEIC opener)
from photo_manager.core.crop import _flatten

if TYPE_CHECKING:
    from photo_manager.core.exiftool import ExifTool

    from .photo_edit import Adjustments, Turn

DPI = 600
BORDER = 63  # px at 600 DPI (0.105 in), on every side


@dataclass(frozen=True)
class PrintSize:
    name: str     # "3x4"
    width: int    # finished pixels at DPI
    height: int
    shape: str    # "tall" | "wide" (how it goes in the album)

    def photo_part(self, border: bool) -> tuple[int, int]:
        """The photo inside the border (or all of it)."""
        b = 2 * BORDER if border else 0
        return self.width - b, self.height - b

    def ratio(self, border: bool) -> float:
        w, h = self.photo_part(border)
        return w / h

    def inches(self) -> str:
        return f"{self.width / DPI:.2f} × {self.height / DPI:.2f} in"


SIZES = [
    PrintSize("3x4", 1782, 2340, "tall"),
    PrintSize("6x4", 3520, 2340, "wide"),
    PrintSize("3x8", 1782, 4680, "tall"),
    PrintSize("6x8", 3520, 4723, "tall"),
]
BY_NAME = {s.name: s for s in SIZES}


def copy_name(path: str, size: PrintSize, border: bool) -> str:
    """"IMG_2041 - 3x4 Border.jpg" / "IMG_2041 - 3x4 No.jpg" (Affinity's preset names)."""
    return f"{Path(path).stem} - {size.name} {'Border' if border else 'No'}.jpg"


def free_path(folder: Path, name: str) -> Path:
    """name, or "name (2).jpg", "name (3).jpg"… if it's taken."""
    target = folder / name
    n = 2
    while target.exists():
        target = folder / f"{Path(name).stem} ({n}){Path(name).suffix}"
        n += 1
    return target


def make_print(image: Image.Image, box: tuple, size: PrintSize, border: bool) -> Image.Image:
    """image (edited, turned) cropped to box, resized to the exact pixels, with the white border."""
    w, h = size.photo_part(border)
    out = _flatten(image.crop(tuple(int(round(v)) for v in box))).resize((w, h), Image.Resampling.LANCZOS)
    if border:
        out = ImageOps.expand(out, BORDER, fill="white")
    return out


def week_date(taken: datetime | None, start: date, end: date, week_start: str = "sunday") -> datetime:
    """The print copy's date taken for the scrapbook week start…end: the photo's own date when it's in that
    week; moved by whole weeks into it when the user chose another week; noon on its first day for a card
    without a date."""
    if taken is None:
        return datetime.combine(start, time(12, 0))
    if start <= taken.date() <= end:
        return taken
    from photo_manager.ui.grid import album_week

    moved = taken + timedelta(days=(start - album_week(taken.date(), week_start)[2]).days)
    low, high = datetime.combine(start, time(0, 0)), datetime.combine(end, time(23, 59, 59))
    return min(max(moved, low), high)


def save_print(path: str, a: "Adjustments", turn: "Turn", box: tuple, size: PrintSize, border: bool,
               folder: str, et: "ExifTool | None" = None, taken: datetime | None = None) -> str:
    """Write the print copy into folder; returns its path. box: on the photo as shown (edited and turned),
    in its full-size pixels. taken: its date taken (the scrapbook week it's for)."""
    from .photo_edit import apply

    with Image.open(path) as src:
        src.seek(0)
        upright = ImageOps.exif_transpose(src)
    image = make_print(turn.image(apply(upright, a)), box, size, border)
    os.makedirs(folder, exist_ok=True)
    dest = free_path(Path(folder), copy_name(path, size, border))
    exif = Image.Exif()
    if taken is not None:
        stamp = taken.strftime("%Y:%m:%d %H:%M:%S")
        exif[0x0132] = stamp
        exif.get_ifd(0x8769).update({0x9003: stamp, 0x9004: stamp})
    image.save(dest, "JPEG", quality=100, subsampling=0, dpi=(DPI, DPI), exif=exif.tobytes())
    if et is not None:  # its dates (for the week it belongs to), keywords and labels
        error = et.write(str(dest), [
            "-TagsFromFile", path, "-all:all", "-unsafe",
            "-Orientation#=1", f"-ExifImageWidth={image.width}", f"-ExifImageHeight={image.height}",
            f"-XResolution={DPI}", f"-YResolution={DPI}", "-ResolutionUnit=inches",
            "-ThumbnailImage=", "-PreviewImage=",
        ] + ([f"-AllDates={taken:%Y:%m:%d %H:%M:%S}"] if taken is not None else []))
        if error and "Nothing to do" not in error:
            raise OSError(f"Couldn't copy the photo's details (dates, keywords): {error}")
    return str(dest)
