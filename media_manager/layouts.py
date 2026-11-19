"""Scrapbook page layouts (Project Life / pocket pages): pictures of pockets, read from the user's Digital
Templates folder (and the three the user sent, built in). The Layouts panel (a tab with Photos' Details)
shows each with its tall and wide pockets, and whether the week's print copies (the Print size copies in the
Project Life folder, by date taken) fill it.

Not done yet, on purpose (the user's "remember, don't implement now"): dragging photos into the pockets,
and clicking a pocket to start Print size with that pocket's size.
"""

from __future__ import annotations

import os
from collections import deque
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from PIL import Image, ImageFilter, ImageOps

BUILT_IN = Path(__file__).resolve().parent / "assets" / "layouts"
PICTURES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff", ".bmp", ".psd"}
SCAN = 240  # the picture is looked at this many pixels wide (plenty for boxes)


@dataclass
class Pocket:
    x: float  # fractions of the page
    y: float
    w: float
    h: float
    shape: str  # "tall" | "wide" | "square"


@dataclass
class Layout:
    name: str
    path: str
    pockets: list[Pocket]
    built_in: bool = False

    def count(self, shape: str) -> int:
        return sum(p.shape == shape for p in self.pockets)

    @property
    def signature(self) -> tuple:
        return tuple(sorted((round(p.x, 1), round(p.y, 1), round(p.w, 1), round(p.h, 1)) for p in self.pockets))

    def summary(self) -> str:
        parts = []
        for shape in ("tall", "wide", "square"):
            n = self.count(shape)
            if n:
                parts.append(f"{n} {shape}")
        return " · ".join(parts) or "no pockets found"


def find_pockets(image: Image.Image) -> list[Pocket]:
    """The boxes of a layout picture: the white areas the grey lines divide it into (the writing inside a box
    doesn't split it). A thin margin round the outside isn't a box."""
    grey = ImageOps.grayscale(image.convert("RGB"))
    page_w, page_h = grey.size
    grey = grey.filter(ImageFilter.MinFilter(5))  # thicken the thin lines so they survive shrinking
    scale = SCAN / page_w
    small = grey.resize((SCAN, max(1, round(page_h * scale))), Image.Resampling.BOX)
    w, h = small.size
    px = small.load()
    white = [[px[x, y] >= 235 for x in range(w)] for y in range(h)]
    seen = [[False] * w for _ in range(h)]
    pockets: list[Pocket] = []
    for sy in range(h):
        for sx in range(w):
            if not white[sy][sx] or seen[sy][sx]:
                continue
            seen[sy][sx] = True
            queue, area = deque([(sx, sy)]), 0
            x0, y0, x1, y1 = sx, sy, sx, sy
            while queue:
                x, y = queue.popleft()
                area += 1
                x0, y0, x1, y1 = min(x0, x), min(y0, y), max(x1, x), max(y1, y)
                for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    if 0 <= nx < w and 0 <= ny < h and white[ny][nx] and not seen[ny][nx]:
                        seen[ny][nx] = True
                        queue.append((nx, ny))
            bw, bh = x1 - x0 + 1, y1 - y0 + 1
            if area < 0.02 * w * h or area < 0.6 * bw * bh:  # specks, and the margin round the outside
                continue
            ratio = (bw / bh) * (page_h / h) / (page_w / w) if h and w else 1
            shape = "tall" if ratio < 0.92 else "wide" if ratio > 1.08 else "square"
            pockets.append(Pocket(x0 / w, y0 / h, bw / w, bh / h, shape))
    pockets.sort(key=lambda p: (round(p.y, 1), p.x))
    return pockets


def read_layout(path: Path, built_in: bool = False) -> Layout | None:
    try:
        with Image.open(path) as im:
            im.seek(0)
            pockets = find_pockets(im)
    except Exception:  # noqa: BLE001  (not a picture Pillow can read)
        return None
    return Layout(path.stem, str(path), pockets, built_in) if pockets else None


def load_layouts(folder: str) -> list[Layout]:
    """The folder's layouts (by name), then the built-in ones that aren't the same as one of them."""
    found: list[Layout] = []
    if folder and os.path.isdir(folder):
        for entry in sorted(Path(folder).iterdir(), key=lambda p: p.name.casefold()):
            if entry.is_file() and entry.suffix.lower() in PICTURES:
                layout = read_layout(entry)
                if layout:
                    found.append(layout)
    have = {layout.signature for layout in found}
    for entry in sorted(BUILT_IN.glob("*.jpg")):
        layout = read_layout(entry, built_in=True)
        if layout and layout.signature not in have:
            found.append(layout)
    return found


# ------------------------------------------------------------------ the week's print copies
def week_of(day: date, week_start: str) -> date:
    """The first day of day's week (as Photos' week groups)."""
    offset = (day.weekday() + 1) % 7 if week_start == "sunday" else day.weekday()
    return day - timedelta(days=offset)


def date_taken(path: str) -> datetime | None:
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            text = exif.get_ifd(0x8769).get(0x9003) or exif.get(0x0132)
    except Exception:  # noqa: BLE001
        return None
    try:
        return datetime.strptime(str(text).strip()[:19], "%Y:%m:%d %H:%M:%S")
    except (TypeError, ValueError):
        return None


@dataclass
class Week:
    start: date | None  # None: a group of the Photos grid (title), not a week
    tall: int = 0
    wide: int = 0
    square: int = 0
    undated: int = 0
    names: tuple[str, ...] = ()
    title: str = ""


def is_inside(folder: str, parent: str) -> bool:
    """folder is parent or one of its subfolders."""
    if not folder or not parent:
        return False
    f, p = (os.path.normcase(os.path.normpath(x)) for x in (folder, parent))
    return f == p or f.startswith(p.rstrip("\\/") + os.sep)


def shape_of(path: str) -> str | None:
    from photo_manager.core.crop import upright_size

    try:
        w, h = upright_size(path)
    except Exception:  # noqa: BLE001
        return None
    return "tall" if w < h * 0.92 else "wide" if w > h * 1.08 else "square"


def group_prints(paths: list[str], title: str) -> Week:
    """A group of the Photos grid (a week, a subfolder, "No date taken"…): dated or not, every picture counts."""
    week = Week(None, title=title)
    for path in paths:
        shape = shape_of(path)
        if shape:
            setattr(week, shape, getattr(week, shape) + 1)
    week.names = tuple(sorted(os.path.basename(p) for p in paths))
    return week


def week_prints(folder: str, start: date) -> Week:
    """The print copies in folder taken in the week starting start: how many tall, wide and square."""
    week = Week(start)
    if not folder or not os.path.isdir(folder):
        return week
    end, names = start + timedelta(days=7), []
    for entry in Path(folder).iterdir():
        if not entry.is_file() or entry.suffix.lower() not in PICTURES:
            continue
        taken = date_taken(str(entry))
        if taken is None:
            week.undated += 1
            continue
        if not start <= taken.date() < end:
            continue
        shape = shape_of(str(entry))
        if shape is None:
            continue
        setattr(week, shape, getattr(week, shape) + 1)
        names.append(entry.name)
    week.names = tuple(sorted(names))
    return week


def fit(layout: Layout, week: Week) -> tuple[bool, str]:
    """(fits, what to say): the week's prints against the layout's pockets."""
    short = []
    for shape in ("tall", "wide", "square"):
        need = layout.count(shape) - getattr(week, shape)
        if need > 0:
            short.append(f"{need} more {shape}")
    if short:
        return False, "✗ needs " + ", ".join(short)
    spare = (week.tall + week.wide + week.square) - len(layout.pockets)
    return True, "✓ fits" + (" this week" if week.start else "") + (f" ({spare} left over)" if spare else "")
