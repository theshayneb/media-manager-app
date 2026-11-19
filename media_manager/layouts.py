"""Scrapbook page layouts (Project Life / pocket pages): pictures of pockets, read from the user's Digital
Templates folder (and the three the user sent, built in). The Layouts panel (a tab with Photos' Details)
shows each with its tall and wide pockets, and whether the week's print copies (the Print size copies in the
Project Life folder, by date taken) fill it.

Not done yet, on purpose (the user's "remember, don't implement now"): dragging photos into the pockets,
and clicking a pocket to start Print size with that pocket's size.
"""

from __future__ import annotations

import os
import re
import struct
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


# ------------------------------------------------------------------ PSD templates
def psd_layers(path: str) -> tuple[int, int, list[tuple[str, int, int, int, int, bool]]]:
    """(width, height, [(name, left, top, right, bottom, is_text)]) of a Photoshop file's layers, read straight
    from the file (no Photoshop library needed)."""
    with open(path, "rb") as f:
        data = f.read()
    if data[:4] != b"8BPS":
        raise ValueError("Not a PSD")
    psb = struct.unpack_from(">H", data, 4)[0] == 2
    height, width = struct.unpack_from(">II", data, 14)
    pos = 26
    pos += 4 + struct.unpack_from(">I", data, pos)[0]  # colour mode data
    pos += 4 + struct.unpack_from(">I", data, pos)[0]  # image resources
    big = ">Q" if psb else ">I"
    step = 8 if psb else 4
    if struct.unpack_from(big, data, pos)[0] == 0:
        return width, height, []
    pos += step
    if struct.unpack_from(big, data, pos)[0] == 0:  # no layer info
        return width, height, []
    pos += step
    count = abs(struct.unpack_from(">h", data, pos)[0])
    pos += 2
    layers = []
    for _ in range(count):
        top, left, bottom, right = struct.unpack_from(">iiii", data, pos)
        channels = struct.unpack_from(">H", data, pos + 16)[0]
        pos += 18 + channels * (10 if psb else 6) + 12  # channel info, blend mode, opacity, clipping, flags…
        extra = struct.unpack_from(">I", data, pos)[0]
        start = pos + 4
        e = start
        e += 4 + struct.unpack_from(">I", data, e)[0]  # layer mask
        e += 4 + struct.unpack_from(">I", data, e)[0]  # blending ranges
        n = data[e]
        name = data[e + 1:e + 1 + n].decode("latin-1")
        e += (1 + n + 3) // 4 * 4
        text = False
        while e + 12 <= start + extra:  # additional layer information
            key = data[e + 4:e + 8]
            length = struct.unpack_from(">I", data, e + 8)[0]
            if key == b"luni":  # the full (Unicode) name
                chars = struct.unpack_from(">I", data, e + 12)[0]
                name = data[e + 16:e + 16 + chars * 2].decode("utf-16-be", "replace").rstrip("\x00")
            elif key in (b"TySh", b"tySh"):
                text = True
            e += 12 + length + (length % 2)
        layers.append((name, left, top, right, bottom, text))
        pos = start + extra
    return width, height, layers


def psd_spots(path: str) -> list[Pocket]:
    """The photo spots of a PSD template: its layers named with "photo" ("photo", "clip photo", "1-PHOTO",
    "PHOTO HERE"…), not text layers, not tiny."""
    width, height, layers = psd_layers(path)
    spots = []
    for name, left, top, right, bottom, text in layers:
        w, h = right - left, bottom - top
        if text or "photo" not in name.casefold() or w * h < 0.005 * width * height:
            continue
        ratio = w / h if h else 1
        shape = "tall" if ratio < 0.92 else "wide" if ratio > 1.08 else "square"
        spots.append(Pocket(left / width, top / height, w / width, h / height, shape))
    spots.sort(key=lambda p: (round(p.y, 1), p.x))
    return spots


def template_image(path: str, size: int) -> Image.Image | None:
    """A thumbnail of a template: a PSD's flattened picture (as Photoshop saved it), or the picture itself."""
    try:
        with Image.open(path) as im:  # (a PSD's frames are its layers: no seek, its own picture is the first)
            im.thumbnail((size, size), Image.Resampling.LANCZOS)
            return im.convert("RGB")
    except Exception:  # noqa: BLE001
        return None


# ------------------------------------------------------------------ which tab
TABS = ["6x8", "3x4 + 6x4", "3x8", "4x4", "Other"]  # ("&" would vanish in a tab's name)
SIZE_TABS = {"6x8": "6x8", "3x4": "3x4 + 6x4", "6x4": "3x4 + 6x4", "4x6": "3x4 + 6x4", "4x3": "3x4 + 6x4",
             "3x8": "3x8", "4x4": "4x4"}


def tab_of(name: str) -> str:
    """By the start of the file name: its size ("3x4 - …", "6x8 …"); "PL …" (the hand-drawn Project Life
    pages) are 6x8; anything else is Other (6x12 too)."""
    if name.strip().upper().startswith("PL"):
        return "6x8"
    m = re.match(r"\s*(\d+)\s*[x×]\s*(\d+)", name, re.IGNORECASE)
    return SIZE_TABS.get(f"{m.group(1)}x{m.group(2)}", "Other") if m else "Other"


@dataclass
class Template:
    name: str
    path: str
    tab: str
    spots: list[Pocket] | None  # a PSD's photo spots (None: not a PSD)

    def summary(self) -> str:
        if self.spots is None:
            return Path(self.path).suffix.lstrip(".").upper()
        n = len(self.spots)
        return f"{n} photo spot{'' if n == 1 else 's'}" if n else "no photo spots found"


def template_files(folder: str) -> list[Path]:
    """Every picture in folder and its subfolders (not hidden ones)."""
    out: list[Path] = []
    if not folder or not os.path.isdir(folder):
        return out
    for root, dirs, files in os.walk(folder):
        dirs[:] = sorted(d for d in dirs if not d.startswith((".", "$", "@", "#")))
        out.extend(Path(root) / f for f in files if Path(f).suffix.lower() in PICTURES)
    return sorted(out, key=lambda p: p.name.casefold())


def load_templates(folder: str) -> dict[str, list[Template]]:
    """The templates for the tabs other than 6x8 (those are layouts: load_layouts)."""
    tabs: dict[str, list[Template]] = {tab: [] for tab in TABS[1:]}
    for entry in template_files(folder):
        tab = tab_of(entry.stem)
        if tab == "6x8":
            continue
        spots = None
        if entry.suffix.lower() == ".psd":
            try:
                spots = psd_spots(str(entry))
            except Exception:  # noqa: BLE001
                spots = []
        tabs[tab].append(Template(entry.stem, str(entry), tab, spots))
    return tabs


def read_layout(path: Path, built_in: bool = False) -> Layout | None:
    """A 6x8 page: a PSD's photo spots, or the boxes of a hand-drawn layout picture."""
    try:
        if path.suffix.lower() == ".psd":
            pockets = psd_spots(str(path))
        else:
            with Image.open(path) as im:
                im.seek(0)
                pockets = find_pockets(im)
    except Exception:  # noqa: BLE001  (not a picture we can read)
        return None
    return Layout(path.stem, str(path), pockets, built_in) if pockets else None


def load_layouts(folder: str) -> list[Layout]:
    """The 6x8 tab: the folder's 6x8 layouts ("6x8 …", "PL …"), then the built-in ones unlike any of them."""
    found: list[Layout] = []
    for entry in template_files(folder):
        if tab_of(entry.stem) == "6x8":
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


def week_prints(folder: str, start: date, last: date | None = None) -> Week:
    """The print copies in folder taken from start to last (a scrapbook week): how many tall, wide, square."""
    week = Week(start)
    if not folder or not os.path.isdir(folder):
        return week
    end, names = (last or start + timedelta(days=6)) + timedelta(days=1), []
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


SHAPES = ("tall", "wide", "square")


def needs(pages: list[Layout]) -> dict[str, int]:
    """How many tall, wide and square pockets the pages have together."""
    return {shape: sum(page.count(shape) for page in pages) for shape in SHAPES}


def describe(need: dict[str, int]) -> str:
    return ", ".join(f"{n} {shape}" for shape, n in need.items() if n) or "nothing"


def fit(layout: Layout | list[Layout], week: Week) -> tuple[bool, str]:
    """(fits, what to say): the week's pictures against the pockets of a layout (or a spread of them)."""
    pages = layout if isinstance(layout, list) else [layout]
    need = needs(pages)
    short = [f"{need[s] - getattr(week, s)} more {s}" for s in SHAPES if need[s] > getattr(week, s)]
    if short:
        return False, "needs " + ", ".join(short)
    spare = (week.tall + week.wide + week.square) - sum(need.values())
    return True, "✓ fits" + (" this week" if week.start else "") + (f" ({spare} left over)" if spare else "")


# ------------------------------------------------------------------ the page plan
PLAN_FILE = "Layout plan.json"


class Plan:
    """Which layout is on which page, saved in the Project Life folder ("Layout plan.json").

    Each week is a spread. You choose its right page; the back of that sheet (the same layout, mirrored) is the
    next week's left page, so that one is fixed ("locked"). Week 1 starts the year's album: both its pages are
    yours to choose (as is a left page whose previous week has no right page yet)."""

    def __init__(self, folder: str):
        self.path = Path(folder) / PLAN_FILE if folder else None
        self.weeks: dict[str, dict[str, str]] = {}
        try:
            import json

            data = json.loads(self.path.read_text(encoding="utf-8")) if self.path else {}
            self.weeks = {k: dict(v) for k, v in data.get("weeks", {}).items() if isinstance(v, dict)}
        except (OSError, ValueError, AttributeError):
            self.weeks = {}

    @staticmethod
    def key(year: int, number: int) -> str:
        return f"{year}-{number:02d}"

    def right(self, year: int, number: int) -> str | None:
        return self.weeks.get(self.key(year, number), {}).get("right")

    def left(self, year: int, number: int) -> tuple[str | None, bool]:
        """(layout name, locked): the back of last week's right page, else the one chosen for this week."""
        if number > 1:
            back = self.right(year, number - 1)
            if back:
                return back, True
        return self.weeks.get(self.key(year, number), {}).get("left"), False

    def choose(self, year: int, number: int, side: str, name: str | None) -> None:
        week = self.weeks.setdefault(self.key(year, number), {})
        if name:
            week[side] = name
        else:
            week.pop(side, None)
        if not week:
            self.weeks.pop(self.key(year, number), None)
        self.save()

    def save(self) -> None:
        import json

        if self.path is None:
            raise OSError("No Project Life folder")
        tmp = self.path.with_name(self.path.name + ".tmp")
        tmp.write_text(json.dumps({"weeks": dict(sorted(self.weeks.items()))}, indent=2, ensure_ascii=False),
                       encoding="utf-8")
        os.replace(tmp, self.path)
