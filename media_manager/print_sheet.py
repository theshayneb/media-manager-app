"""Print sheet: print copies laid out on 8.5 × 11 in paper at 600 DPI, as the user did by hand in Affinity.

- Photos touch edge to edge (no gap), in a grid: every cut goes all the way across the sheet, so lined up on
  the crop marks at both ends it never touches a photo, whatever order you cut in; turned sideways when that
  fits more on; as few sheets as possible (Print sheet uses the first, fullest one).
- The whole arrangement is centred on the paper (printers can't print to the very edge), never resized:
  the prints' sizes (and white borders) must stay exactly as Print size made them.
- Light grey crop marks at both ends of every cut, in the white round the photos (never on one).
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
# Every cut goes all the way across the sheet (the user's rule: a rotary cutter lined up on the crop marks at
# both ends, in any order, never touches a photo). So the photos form a grid: columns and rows, every photo in a
# column as wide as the column and every photo in a row as tall as the row (cells may be empty).
MAX_LINES = 4  # columns or rows on a sheet (the smallest print is 2.97 in: no more fit on 8.5 × 11)


def _sizes(pieces: list[Piece]) -> list[int]:
    return sorted({d for p in pieces for d in (p.width, p.height)})


def _splits(values: list[int], room: int) -> list[tuple[int, ...]]:
    """Every way (in order, sizes from values) of splitting room into 1…MAX_LINES columns (or rows)."""
    out: list[tuple[int, ...]] = []

    def grow(prefix: tuple[int, ...], used: int) -> None:
        if prefix:
            out.append(prefix)
        if len(prefix) == MAX_LINES:
            return
        for v in values:
            if prefix and v < prefix[-1]:  # (order doesn't change what fits: smallest first only)
                continue
            if used + v <= room:
                grow(prefix + (v,), used + v)

    grow((), 0)
    return out


def _fill(pieces: list[Piece], cols: tuple[int, ...], rows: tuple[int, ...]) -> list[Placed]:
    """Put pieces into the grid's cells: a cell takes a piece exactly its size (either way round, unless the
    user turned it), the biggest cells first."""
    free = list(pieces)
    placed: list[Placed] = []
    cells = [(c, r) for r in range(len(rows)) for c in range(len(cols))]
    cells.sort(key=lambda cr: -(cols[cr[0]] * rows[cr[1]]))
    for c, r in cells:
        w, h = cols[c], rows[r]
        choice = None
        for piece in free:
            for turned in (False, True) if piece.turn is None else (piece.turn,):
                pw, ph = (piece.height, piece.width) if turned else (piece.width, piece.height)
                if (pw, ph) == (w, h) and (choice is None or (not turned and choice[1])):
                    choice = (piece, turned)
        if choice is not None:
            free.remove(choice[0])
            placed.append(Placed(choice[0], sum(cols[:c]), sum(rows[:r]), choice[1]))
    return placed


def _best_pack(pieces: list[Piece], width: int, height: int) -> list[Placed]:
    """The grid that puts the most on the sheet; then the fewest turned sideways; then the tidiest."""
    values = _sizes(pieces)
    best: list[Placed] = []
    best_key: tuple = (0,)
    import itertools

    for cols in _splits(values, width):
        for rows in _splits(values, height):
            for cols_order in set(itertools.permutations(cols)) if len(cols) <= 3 else [cols]:
                placed = _fill(pieces, cols_order, rows)
                if not placed:
                    continue
                # Columns and rows left empty don't count (they'd only spread the photos out).
                used_cols = {p.x for p in placed}
                used_rows = {p.y for p in placed}
                if len(used_cols) < len(cols_order) or len(used_rows) < len(rows):
                    continue
                area = sum(p.w * p.h for p in placed)
                key = (area, -sum(p.turned for p in placed), -(sum(cols_order) * sum(rows)))
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
    """Short light-grey lines (x0, y0, x1, y1) at both ends of every cut: each column line above and below the
    photos, each row line left and right of them, in the white round the whole arrangement (line a ruler up
    on the two marks and cut straight across)."""
    if not sheet.placed:
        return []
    left = min(p.x for p in sheet.placed)
    top = min(p.y for p in sheet.placed)
    right = max(p.x + p.w for p in sheet.placed)
    bottom = max(p.y + p.h for p in sheet.placed)
    width, height = sheet.size
    xs = sorted({p.x for p in sheet.placed} | {p.x + p.w for p in sheet.placed})
    ys = sorted({p.y for p in sheet.placed} | {p.y + p.h for p in sheet.placed})
    marks = []
    for x in xs:
        marks.append((x, max(0, top - MARK_GAP - MARK), x, max(0, top - MARK_GAP)))
        marks.append((x, min(height - 1, bottom + MARK_GAP), x, min(height - 1, bottom + MARK_GAP + MARK)))
    for y in ys:
        marks.append((max(0, left - MARK_GAP - MARK), y, max(0, left - MARK_GAP), y))
        marks.append((min(width - 1, right + MARK_GAP), y, min(width - 1, right + MARK_GAP + MARK), y))
    return marks


def cuts_cross_a_photo(sheet: Sheet) -> bool:
    """True if a cut (any photo edge, carried all the way across) would go through a photo."""
    xs = {p.x for p in sheet.placed} | {p.x + p.w for p in sheet.placed}
    ys = {p.y for p in sheet.placed} | {p.y + p.h for p in sheet.placed}
    return any(p.x < x < p.x + p.w for p in sheet.placed for x in xs) or \
        any(p.y < y < p.y + p.h for p in sheet.placed for y in ys)


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


def render(sheet: Sheet, images: dict[str, Image.Image] | None = None, grey: str = "D",
           brown: str = "D") -> Image.Image:
    """The sheet at 600 DPI: white paper, the photos at their own size (never scaled), the crop marks; with
    the printer's colour fix (grey, brown: the colour check's letters; "D" = none)."""
    page = Image.new("RGB", sheet.size, "white")
    for p in sheet.placed:
        image = (images or {}).get(p.piece.path) or load(p.piece.path)
        image = colour_fix(brighter(image, p.piece.brighter), grey, brown)
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


def save(sheet: Sheet, folder: str, name: str, grey: str = "D", brown: str = "D") -> str:
    from .print_size import free_path

    os.makedirs(folder, exist_ok=True)
    dest = free_path(Path(folder), name)
    render(sheet, grey=grey, brown=brown).save(dest, "JPEG", quality=95, subsampling=0, dpi=(DPI, DPI))
    return str(dest)


# ------------------------------------------------------------------ the printer's colours (greys and browns)
# A test page prints grey and brown swatches at seven warmths, A (cooler) … D (as they are) … G (warmer). The
# user picks the column that looks right on paper for greys and for browns; the sheets then print with that
# fix, on greys and browns only (other colours, and the print copies themselves, are left alone).
COLOUR_LETTERS = "ABCDEFG"
COLOUR_STEP = 6  # one letter = this much on Edit's Blue ↔ Yellow slider
GREYS = [(200, 200, 200), (150, 150, 150), (100, 100, 100), (60, 60, 60)]
BROWNS = [(196, 160, 120), (150, 105, 70), (110, 75, 50), (70, 50, 35)]


def letter_steps(letter: str) -> int:
    """"A" → -3 (cooler) … "D" → 0 … "G" → +3 (warmer)."""
    return COLOUR_LETTERS.index(letter) - 3 if letter in COLOUR_LETTERS else 0


def _warmth(image: Image.Image, steps: int) -> Image.Image:
    from .photo_edit import Adjustments, apply

    return apply(image, Adjustments(yellow=steps * COLOUR_STEP)) if steps else image


def _masks(image: Image.Image) -> tuple[Image.Image, Image.Image]:
    """(greys, browns): how much each pixel is a grey (little colour) and a brown (orange, not bright)."""
    h, s, v = image.convert("HSV").split()
    grey = s.point(lambda x: max(0, 255 - x * 4))  # full at no colour, none from about a quarter colour
    hue = h.point(lambda x: 255 if 5 <= x <= 32 else (128 if 2 <= x <= 38 else 0))  # orange-ish (≈ 7°–45°)
    some_colour = s.point(lambda x: 0 if x < 40 else (255 if x < 200 else 128))
    not_bright = v.point(lambda x: 255 if x < 210 else 0)
    from PIL import ImageChops

    brown = ImageChops.multiply(ImageChops.multiply(hue, some_colour), not_bright)
    return grey, brown


def colour_fix(image: Image.Image, grey: str = "D", brown: str = "D") -> Image.Image:
    """The printer fix chosen on the colour check: greys and browns warmer or cooler, the rest as it is."""
    g, b = letter_steps(grey), letter_steps(brown)
    if not g and not b:
        return image
    grey_mask, brown_mask = _masks(image)
    out = image
    if g:
        out = Image.composite(_warmth(image, g), out, grey_mask)
    if b:
        out = Image.composite(_warmth(image, b), out, brown_mask)
    return out


def colour_check_page() -> Image.Image:
    """The test page (landscape, 600 DPI): a column per letter, greys above, browns below, each labelled."""
    from PIL import ImageFont

    width, height = PAPER[1], PAPER[0]
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    big, small = ImageFont.load_default(size=150), ImageFont.load_default(size=70)
    draw.text((width // 2, 260), "Colour check: which column looks right? (greys, then browns)", fill=(40, 40, 40),
              font=small, anchor="mm")
    column = (width - 2 * 400) // len(COLOUR_LETTERS)
    swatch = column - 120
    top = 650
    tall = (height - top - 550 - 200) // 2  # each block (greys, browns) as tall as the page allows
    for i, letter in enumerate(COLOUR_LETTERS):
        x = 400 + i * column + 60
        draw.text((x + swatch // 2, top - 120), letter, fill=(30, 30, 30), font=big, anchor="mm")
        y = top
        for colours in (GREYS, BROWNS):
            block = Image.new("RGB", (swatch, tall), "white")
            bd = ImageDraw.Draw(block)
            band = block.height // len(colours)
            for n, colour in enumerate(colours):
                bd.rectangle((0, n * band, swatch, (n + 1) * band), fill=colour)
            page.paste(_warmth(block, letter_steps(letter)), (x, y))
            y += block.height + 200
    draw.text((width // 2, height - 330), "D = as it is now · A, B, C cooler · E, F, G warmer", fill=(90, 90, 90),
              font=small, anchor="mm")
    return page


# ------------------------------------------------------------------ the printer's ICC profile
# Canon's profiles for its own papers come with the printer driver (Windows keeps them in its colour folder);
# the iP8700 series' Matte Photo Paper one has "MP" in its name. With a profile chosen, Media Manager converts
# the sheet's colours for that printer and paper (perceptual), and the driver's own colour correction must be
# off (Canon: Main → Color/Intensity: Manual → Set… → Matching → Color Correction: None).
def colour_folder() -> Path:
    return Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / "spool" / "drivers" / "color"


def printer_profiles(folder: Path | None = None) -> list[Path]:
    folder = folder or colour_folder()
    try:
        return sorted((p for p in folder.iterdir() if p.suffix.lower() in (".icc", ".icm")),
                      key=lambda p: p.name.casefold())
    except OSError:
        return []


def suggested_profile(profiles: list[Path]) -> Path | None:
    """The iP8700 series' (the user's iP8720) Matte Photo Paper profile, if it's there."""
    canon = [p for p in profiles if re.search(r"ip\s*87", p.stem, re.IGNORECASE)]
    matte = [p for p in canon if re.search(r"(^|[^a-z])(mp\d*|matte)([^a-z]|$)", p.stem, re.IGNORECASE)]
    return (matte or [None])[0]


_TRANSFORMS: dict[str, object] = {}


def to_printer(image: Image.Image, profile: str) -> Image.Image:
    """The sheet's colours (sRGB, as on screen) converted for the printer and paper's ICC profile."""
    if not profile:
        return image
    from PIL import ImageCms

    try:
        if profile not in _TRANSFORMS:
            _TRANSFORMS[profile] = ImageCms.buildTransform(
                ImageCms.createProfile("sRGB"), ImageCms.getOpenProfile(profile), "RGB", "RGB",
                renderingIntent=ImageCms.Intent.PERCEPTUAL)
        return ImageCms.applyTransform(image.convert("RGB"), _TRANSFORMS[profile])
    except (ImageCms.PyCMSError, OSError, ValueError) as exc:
        raise OSError(f"Couldn't use the printer profile {os.path.basename(profile)}: {exc}") from exc
