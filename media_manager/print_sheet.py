"""Print sheet: print copies laid out on 8.5 × 11 in paper at 600 DPI, as the user did by hand in Affinity.

- Photos touch edge to edge (no gap) and are placed so every cut can go straight across a piece
  (guillotine packing), turned sideways when that fits more on; as few sheets as possible.
- The whole arrangement is centred on the paper (printers can't print to the very edge), never resized:
  the prints' sizes (and white borders) must stay exactly as Print size made them.
- Light grey crop marks show where to cut, in the white round the photos (never on a photo).
- "Brighter" per photo, its own amount (21 by default, the user's Affinity brightness layer), on the sheet only.
No Qt here except in the window (print_sheet_window.py).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from io import BytesIO
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

DPI = 600
PAPER = (5100, 6600)          # 8.5 × 11 in, portrait, in pixels at 600 DPI
MARGIN = 75                   # 1/8 in kept clear at every edge (no printer prints right to the edge)
MARK = 90                     # crop marks: 0.15 in long
MARK_GAP = 12                 # … starting this far from the photo
MARK_COLOUR = (200, 200, 200)  # light grey
BRIGHTER = 21                 # the user's Affinity brightness layer (21%)


@dataclass
class Piece:
    path: str
    width: int    # its pixels (a print copy: exactly its size at 600 DPI)
    height: int
    brighter: int = 0  # 0: as it is; else this much brighter on the sheet (Edit's Brightness scale)
    turn: bool | None = None  # None: whichever fits better; True/False: turned sideways or not (the user's)

    @property
    def area(self) -> int:
        return self.width * self.height


@dataclass
class Placed:
    piece: Piece
    x: int
    y: int
    turned: bool

    @property
    def w(self) -> int:
        return self.piece.height if self.turned else self.piece.width

    @property
    def h(self) -> int:
        return self.piece.width if self.turned else self.piece.height


@dataclass
class Sheet:
    landscape: bool
    placed: list[Placed] = field(default_factory=list)

    @property
    def size(self) -> tuple[int, int]:
        return (PAPER[1], PAPER[0]) if self.landscape else PAPER

    def used(self) -> float:
        w, h = self.size
        return sum(p.w * p.h for p in self.placed) / (w * h)


def piece_for(path: str) -> Piece:
    from photo_manager.core.crop import upright_size

    w, h = upright_size(path)
    return Piece(path, w, h)


# ------------------------------------------------------------------ arranging
def _pack(pieces: list[Piece], width: int, height: int, fit: str = "short", split: str = "short") -> list[Placed]:
    """Guillotine packing into width × height (every split goes all the way across what's left, so each
    cut is straight): in order, each into the free space it fits best (fit: "short" / "long" leftover side,
    or "area"), turned if that fits better; what's left split along the shorter or longer leftover (split)."""
    free = [(0, 0, width, height)]
    placed: list[Placed] = []
    for piece in pieces:
        best = None
        for i, (_fx, _fy, fw, fh) in enumerate(free):
            for turned in (False, True) if piece.turn is None else (piece.turn,):
                w, h = (piece.height, piece.width) if turned else (piece.width, piece.height)
                if w <= fw and h <= fh:
                    a, b = sorted((fw - w, fh - h))
                    score = {"short": (a, b), "long": (b, a), "area": (fw * fh - w * h, a)}[fit]
                    if best is None or score < best[0]:
                        best = (score, i, turned, w, h)
        if best is None:
            continue
        _score, i, turned, w, h = best
        fx, fy, fw, fh = free.pop(i)
        placed.append(Placed(piece, fx, fy, turned))
        right, below = fw - w, fh - h
        across = (right < below) if split == "short" else (right >= below)
        if across:  # the cut goes across under it: the space beside it is as tall as it is
            parts = [(fx + w, fy, right, h), (fx, fy + h, fw, below)]
        else:       # the cut goes down beside it
            parts = [(fx + w, fy, right, fh), (fx, fy + h, w, below)]
        free.extend(p for p in parts if p[2] > 0 and p[3] > 0)
    return placed


def _rows(pieces: list[Piece], width: int, height: int, policy: str) -> list[Placed]:
    """Row by row (each row is one straight cut across the sheet): pieces stood the way policy says
    ("as is", "wide", "tall"), tallest first, each into the first row it fits in (turned to fit, if allowed)."""
    def stood(p: Piece) -> bool:  # turned?
        if p.turn is not None:
            return p.turn
        if policy == "wide":
            return p.height > p.width
        if policy == "tall":
            return p.width > p.height
        return False

    order = sorted(pieces, key=lambda p: (-(p.width if stood(p) else p.height), -p.area))
    rows: list[list] = []  # [top, height, used width]
    placed: list[Placed] = []
    for piece in order:
        options = [stood(piece)] + ([not stood(piece)] if piece.turn is None else [])
        done = False
        for row in rows:
            for turned in options:
                w, h = (piece.height, piece.width) if turned else (piece.width, piece.height)
                if h <= row[1] and row[2] + w <= width:
                    placed.append(Placed(piece, row[2], row[0], turned))
                    row[2] += w
                    done = True
                    break
            if done:
                break
        if done:
            continue
        top = sum(r[1] for r in rows)
        turned = options[0]
        w, h = (piece.height, piece.width) if turned else (piece.width, piece.height)
        if w <= width and top + h <= height:
            rows.append([top, h, w])
            placed.append(Placed(piece, 0, top, turned))
    return placed


def _best_pack(pieces: list[Piece], width: int, height: int) -> list[Placed]:
    """The packing (of several ways of doing it) that puts the most on the sheet."""
    orders = [
        sorted(pieces, key=lambda p: (-p.area, -max(p.width, p.height))),
        sorted(pieces, key=lambda p: (-max(p.width, p.height), -p.area)),
        sorted(pieces, key=lambda p: (-min(p.width, p.height), -p.area)),
    ]
    best: list[Placed] = []
    best_key: tuple = (-1, 0, 0)
    for order in orders:
        for fit in ("short", "long", "area"):
            for split in ("short", "long"):
                placed = _pack(order, width, height, fit, split)
                area = sum(p.w * p.h for p in placed)
                # Most on the sheet; then the tidiest block (the smallest box round it: fewer cuts).
                box = (max((p.x + p.w for p in placed), default=0) * max((p.y + p.h for p in placed), default=0))
                key = (area, -box, -sum(p.turned for p in placed))  # (then: the fewest turned sideways)
                if key > best_key:
                    best, best_key = placed, key
    for policy in ("as is", "wide", "tall"):
        for w, h, swap in ((width, height, False), (height, width, True)):  # rows, or columns (rows turned)
            placed = _rows(pieces, w, h, policy)
            if swap:  # columns: the same, with x and y swapped (and each piece turned the other way)
                placed = [Placed(p.piece, p.y, p.x, not p.turned) for p in placed]
                if any(p.piece.turn is not None and p.turned != p.piece.turn for p in placed):
                    continue
            area = sum(p.w * p.h for p in placed)
            box = (max((p.x + p.w for p in placed), default=0) * max((p.y + p.h for p in placed), default=0))
            key = (area, -box, -sum(p.turned for p in placed))
            if key > best_key:
                best, best_key = placed, key
    return best


def _centre(placed: list[Placed], width: int, height: int) -> None:
    """Move the arrangement to the middle of the paper (the space round it is shared out evenly)."""
    if not placed:
        return
    left = min(p.x for p in placed)
    top = min(p.y for p in placed)
    right = max(p.x + p.w for p in placed)
    bottom = max(p.y + p.h for p in placed)
    dx = (width - (right - left)) // 2 - left
    dy = (height - (bottom - top)) // 2 - top
    for p in placed:
        p.x += dx
        p.y += dy


def arrange(pieces: list[Piece]) -> tuple[list[Sheet], list[Piece]]:
    """As few sheets as possible, each portrait or landscape (whichever takes more); returns (sheets, the
    pieces too big for the paper)."""
    usable = (PAPER[0] - 2 * MARGIN, PAPER[1] - 2 * MARGIN)
    too_big = [p for p in pieces if not ((p.width <= usable[0] and p.height <= usable[1])
                                         or (p.height <= usable[0] and p.width <= usable[1]))]
    left = sorted((p for p in pieces if p not in too_big), key=lambda p: (-p.area, -max(p.width, p.height)))
    sheets: list[Sheet] = []
    while left:
        options = []
        for landscape in (False, True):
            w, h = (usable[1], usable[0]) if landscape else usable
            placed = _best_pack(left, w, h)
            turned = sum(p.turned for p in placed)
            options.append((sum(p.w * p.h for p in placed), -turned, not landscape, landscape, placed))
        *_keys, landscape, placed = max(options, key=lambda o: (o[0], o[1], o[2]))
        if not placed:  # (can't happen: anything that fits alone was placed)
            break
        sheet = Sheet(landscape, placed)
        _centre(sheet.placed, *sheet.size)
        sheets.append(sheet)
        done = {id(p.piece) for p in placed}
        left = [p for p in left if id(p) not in done]
    return sheets, too_big


# ------------------------------------------------------------------ crop marks
def crop_marks(sheet: Sheet) -> list[tuple[int, int, int, int]]:
    """Short light-grey lines (x0, y0, x1, y1) carrying each photo edge out into the white round it, where it
    meets no other photo: where to put the ruler and cut."""
    rects = [(p.x, p.y, p.x + p.w, p.y + p.h) for p in sheet.placed]

    def covered(x: int, y: int) -> bool:
        return any(r[0] <= x < r[2] and r[1] <= y < r[3] for r in rects)

    width, height = sheet.size
    marks: set[tuple[int, int, int, int]] = set()
    for x0, y0, x1, y1 in rects:
        for x in (x0, x1):  # vertical edges: out past the top and bottom
            for y, direction in ((y0, -1), (y1, 1)):
                probe = y + direction * (MARK_GAP + 1)
                if 0 <= probe < height and not any(covered(x + dx, probe) for dx in (-1, 0)):
                    start = y + direction * MARK_GAP
                    end = max(0, min(height - 1, y + direction * (MARK_GAP + MARK)))
                    if not any(covered(x + dx, end) for dx in (-1, 0)):
                        marks.add((x, min(start, end), x, max(start, end)))
        for y in (y0, y1):  # horizontal edges: out past the left and right
            for x, direction in ((x0, -1), (x1, 1)):
                probe = x + direction * (MARK_GAP + 1)
                if 0 <= probe < width and not any(covered(probe, y + dy) for dy in (-1, 0)):
                    start = x + direction * MARK_GAP
                    end = max(0, min(width - 1, x + direction * (MARK_GAP + MARK)))
                    if not any(covered(end, y + dy) for dy in (-1, 0)):
                        marks.add((min(start, end), y, max(start, end), y))
    return sorted(marks)


# ------------------------------------------------------------------ the picture
def load(path: str) -> Image.Image:
    with Image.open(BytesIO(Path(path).read_bytes())) as im:
        return ImageOps.exif_transpose(im).convert("RGB")


def brighter(image: Image.Image, amount: int) -> Image.Image:
    """Edit's Brightness slider (the mid-tones up; black and white stay)."""
    if not amount:
        return image
    from .photo_edit import Adjustments, apply

    return apply(image, Adjustments(brightness=max(-100, min(100, amount))))


def render(sheet: Sheet, images: dict[str, Image.Image] | None = None) -> Image.Image:
    """The sheet at 600 DPI: white paper, the photos at their own size (never scaled), the crop marks."""
    page = Image.new("RGB", sheet.size, "white")
    for p in sheet.placed:
        image = (images or {}).get(p.piece.path) or load(p.piece.path)
        image = brighter(image, p.piece.brighter)
        if p.turned:
            image = image.transpose(Image.Transpose.ROTATE_90)
        if image.size != (p.w, p.h):  # (not a print copy at its exact size: fitted, never cropped)
            image = image.resize((p.w, p.h), Image.Resampling.LANCZOS)
        page.paste(image, (p.x, p.y))
    draw = ImageDraw.Draw(page)
    for x0, y0, x1, y1 in crop_marks(sheet):
        draw.line((x0, y0, x1, y1), fill=MARK_COLOUR, width=3)
    return page


def sheet_name(week: str, number: int) -> str:
    """"Week 46 - Sheet 1.jpg" (the scrapbook week of its photos)."""
    return f"{week} - Sheet {number}.jpg" if week else f"Sheet {number}.jpg"


SHEET_FILE = re.compile(r"(^|.* - )Sheet \d+( \(\d+\))?\.jpg$", re.IGNORECASE)


def is_sheet(path: str) -> bool:
    """A saved sheet (not a print copy: the Layouts panel doesn't count it)."""
    return bool(SHEET_FILE.match(os.path.basename(path)))


def save(sheet: Sheet, folder: str, name: str) -> str:
    from .print_size import free_path

    os.makedirs(folder, exist_ok=True)
    dest = free_path(Path(folder), name)
    render(sheet).save(dest, "JPEG", quality=95, subsampling=0, dpi=(DPI, DPI))
    return str(dest)
