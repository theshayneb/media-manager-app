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
           brown: str = "D", picks: list | tuple = ()) -> Image.Image:
    """The sheet at 600 DPI: white paper, the photos at their own size (never scaled), the crop marks; with
    the printer's colour fix (grey, brown: the colour check's letters; "D" = none)."""
    page = Image.new("RGB", sheet.size, "white")
    for p in sheet.placed:
        image = (images or {}).get(p.piece.path) or load(p.piece.path)
        image = apply_fixes(brighter(image, p.piece.brighter), grey, brown, picks)
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


def save(sheet: Sheet, folder: str, name: str, grey: str = "D", brown: str = "D", picks: list | tuple = ()) -> str:
    from .print_size import free_path

    os.makedirs(folder, exist_ok=True)
    dest = free_path(Path(folder), name)
    render(sheet, grey=grey, brown=brown, picks=picks).save(dest, "JPEG", quality=95, subsampling=0, dpi=(DPI, DPI))
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


# ------------------------------------------------------------------ the colour check from the sheet's own photos
CHECK_PHOTOS = 3  # pieces of up to this many photos (each their greyest, then their brownest part)


def _best_window(mask: Image.Image, size: int) -> tuple[int, int, float]:
    """(x, y, how much: 0–255 on average) of the size × size square of mask with the most in it (coarse)."""
    w, h = mask.size
    size = min(size, w, h)
    step = max(1, size // 4)
    best, at = -1.0, (0, 0)
    for y in range(0, h - size + 1, step):
        for x in range(0, w - size + 1, step):
            total = mask.crop((x, y, x + size, y + size)).resize((1, 1), Image.Resampling.BOX).getpixel((0, 0))
            if total > best:
                best, at = total, (x, y)
    return at[0], at[1], float(best)


MIN_SHARE = 60  # a part counts as grey (brown) when this much of it is (0–255 on average)


def check_pieces(path: str, side: int) -> tuple[Image.Image | None, Image.Image | None]:
    """(its greyest part, its brownest part) of a photo, each side × side pixels (a square a third its size);
    None where it has hardly any grey (brown)."""
    image = load(path)
    small = image.copy()
    small.thumbnail((240, 240))
    grey, brown = _masks(small)
    scale = image.width / small.width
    window = max(8, min(small.size) // 3)
    out: list[Image.Image | None] = []
    for mask in (grey, brown):
        x, y, share = _best_window(mask, window)
        if share < MIN_SHARE:
            out.append(None)
            continue
        box = (round(x * scale), round(y * scale), round((x + window) * scale), round((y + window) * scale))
        out.append(image.crop(box).resize((side, side), Image.Resampling.LANCZOS))
    return out[0], out[1]


def colour_check_photos(paths: list[str]) -> Image.Image:
    """The colour check with pieces of the photos about to be printed: in each column A–G, their greyest parts
    with that column's grey fix (above) and their brownest parts with its brown fix (below)."""
    from PIL import ImageFont

    width, height = PAPER[1], PAPER[0]
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    big, small = ImageFont.load_default(size=150), ImageFont.load_default(size=70)
    column = (width - 2 * 400) // len(COLOUR_LETTERS)
    top = 650
    side = min(column - 120, (height - top - 550 - 200) // (2 * CHECK_PHOTOS))
    greys: list[Image.Image] = []
    browns: list[Image.Image] = []
    for path in paths:  # the photos with the most grey / brown in them, up to CHECK_PHOTOS of each
        if len(greys) >= CHECK_PHOTOS and len(browns) >= CHECK_PHOTOS:
            break
        try:
            grey, brown = check_pieces(path, side)
        except Exception:  # noqa: BLE001
            continue
        if grey is not None and len(greys) < CHECK_PHOTOS:
            greys.append(grey)
        if brown is not None and len(browns) < CHECK_PHOTOS:
            browns.append(brown)
    # A kind none of the photos has: the plain swatches for it.
    for found, colours in ((greys, GREYS), (browns, BROWNS)):
        if not found:
            swatch = Image.new("RGB", (side, side), "white")
            sd = ImageDraw.Draw(swatch)
            band = side // len(colours)
            for n, colour in enumerate(colours):
                sd.rectangle((0, n * band, side, (n + 1) * band), fill=colour)
            found.append(swatch)
    draw.text((width // 2, 260), "Colour check (your photos): which column looks right? greys above, browns below",
              fill=(40, 40, 40), font=small, anchor="mm")
    for i, letter in enumerate(COLOUR_LETTERS):
        x = 400 + i * column + (column - side) // 2
        draw.text((x + side // 2, top - 120), letter, fill=(30, 30, 30), font=big, anchor="mm")
        y = top
        for grey in greys:
            page.paste(colour_fix(grey, grey=letter, brown="D"), (x, y))
            y += side
        y = top + CHECK_PHOTOS * side + 200
        for brown in browns:
            page.paste(colour_fix(brown, grey="D", brown=letter), (x, y))
            y += side
    draw.text((width // 2, height - 330), "D = as it is now · A, B, C cooler · E, F, G warmer", fill=(90, 90, 90),
              font=small, anchor="mm")
    return page


# ------------------------------------------------------------------ colours picked with the eyedropper
# Any colour the printer gets wrong (the user: yellows, purples), picked from a photo on the sheet. Each gets two
# letters from the colour check: Shade (its hue towards one neighbour or the other: a purple bluer or pinker) and
# Strength (duller or brighter). They change only colours like it: the same hue, about as strong (any lightness).
HUE_NAMES = [(8, "red"), (25, "orange"), (45, "yellow"), (100, "green"), (130, "teal"), (180, "blue"),
             (205, "purple"), (240, "pink"), (256, "red")]  # (up to this hue, 0–255), name
SHADE_STEP = 3       # one letter: about 4° round the colour wheel
STRENGTH_STEP = 0.1  # one letter: 10% more (or less) colour, and 4% lighter (darker)
MAX_PICKS = 4


@dataclass
class Pick:
    rgb: tuple[int, int, int]
    name: str = ""
    source: str = ""     # the photo it was picked from (its name)
    path: str = ""       # … and where: fractions across and down the photo
    fx: float = 0.5
    fy: float = 0.5
    shade: str = "D"
    strength: str = "D"

    def to_dict(self) -> dict:
        return {"rgb": list(self.rgb), "name": self.name, "source": self.source, "path": self.path,
                "fx": self.fx, "fy": self.fy, "shade": self.shade, "strength": self.strength}

    @classmethod
    def from_dict(cls, d: dict) -> "Pick":
        return cls(tuple(d.get("rgb", (128, 128, 128)))[:3], d.get("name", ""), d.get("source", ""),  # type: ignore[arg-type]
                   d.get("path", ""), float(d.get("fx", 0.5)), float(d.get("fy", 0.5)), d.get("shade", "D"),
                   d.get("strength", "D"))

    def hsv(self) -> tuple[int, int, int]:
        return Image.new("RGB", (1, 1), tuple(self.rgb)).convert("HSV").getpixel((0, 0))  # type: ignore[return-value]

    def sides(self) -> tuple[str, str]:
        """What its Shade letters move it towards: (A side, G side), e.g. ("blue", "pink") for a purple."""
        h = self.hsv()[0]
        names = [n for _top, n in HUE_NAMES]
        i = next(n for n, (top, _name) in enumerate(HUE_NAMES) if h < top)
        return names[(i - 1) % len(names)], names[(i + 1) % len(names)]


def colour_name(rgb: tuple[int, int, int]) -> str:
    h, s, v = Image.new("RGB", (1, 1), tuple(rgb)).convert("HSV").getpixel((0, 0))  # type: ignore[misc]
    if s < 40:
        return "Grey"
    if 5 <= h <= 32 and v < 210 and s < 200:
        return "Brown"
    return next(name for top, name in HUE_NAMES if h < top).capitalize()


def _pick_mask(image: Image.Image, pick: Pick) -> Image.Image:
    """How much each pixel is "that colour": its hue close (full within ≈14°, none past ≈31°) and its strength
    (saturation) similar, any lightness."""
    ph, ps, _pv = pick.hsv()
    h, s, _v = image.convert("HSV").split()

    def hue_weight(x: int) -> int:
        d = min(abs(x - ph), 256 - abs(x - ph))
        return 255 if d <= 10 else max(0, 255 - (d - 10) * 21)

    low, high = max(35, ps * 0.5), min(255, ps * 1.7 + 20)

    def strength_weight(x: int) -> int:
        if low <= x <= high:
            return 255
        gap = low - x if x < low else x - high
        return max(0, 255 - int(gap * 17))

    from PIL import ImageChops

    return ImageChops.multiply(h.point(hue_weight), s.point(strength_weight))


def pick_fix(image: Image.Image, pick: Pick, shade: str | None = None, strength: str | None = None) -> Image.Image:
    """That colour (only) moved by its letters: Shade round the colour wheel, Strength duller/brighter."""
    k = letter_steps(pick.shade if shade is None else shade)
    j = letter_steps(pick.strength if strength is None else strength)
    if not k and not j:
        return image
    rgb = image.convert("RGB")
    h, s, v = rgb.convert("HSV").split()
    if k:
        h = h.point(lambda x: (x + k * SHADE_STEP) % 256)
    if j:
        s = s.point(lambda x: max(0, min(255, round(x * (1 + j * STRENGTH_STEP)))))
        v = v.point(lambda x: max(0, min(255, round(x * (1 + j * STRENGTH_STEP * 0.4)))))
    moved = Image.merge("HSV", (h, s, v)).convert("RGB")
    return Image.composite(moved, rgb, _pick_mask(rgb, pick))


def apply_fixes(image: Image.Image, grey: str = "D", brown: str = "D", picks: list[Pick] | tuple = ()) -> Image.Image:
    """All the printer fixes chosen on the colour check: greys, browns and the picked colours."""
    out = colour_fix(image, grey, brown)
    for pick in picks:
        out = pick_fix(out, pick)
    return out


def _around(path: str, fx: float, fy: float, side: int) -> Image.Image | None:
    """A square piece of a photo round a spot (a fifth of its smaller side), side × side pixels."""
    try:
        image = load(path)
    except Exception:  # noqa: BLE001
        return None
    size = max(16, min(image.size) // 5)
    x = min(max(0, round(fx * image.width) - size // 2), image.width - size)
    y = min(max(0, round(fy * image.height) - size // 2), image.height - size)
    return image.crop((x, y, x + size, y + size)).resize((side, side), Image.Resampling.LANCZOS)


def colour_check(paths: list[str], picks: list[Pick] | tuple = ()) -> Image.Image:
    """The colour check page (landscape, 600 DPI, its own page): a row per thing to check, each in seven
    versions A–G: greys and browns (cooler ↔ warmer, a piece of the sheet's photos or a swatch), then each
    picked colour twice (its Shade, then its Strength), a piece of the photo round where it was picked."""
    from PIL import ImageFont

    width, height = PAPER[1], PAPER[0]
    page = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(page)
    big, small, tiny = (ImageFont.load_default(size=n) for n in (130, 64, 50))
    picks = list(picks)[:MAX_PICKS]
    label_w, left, top, bottom = 1100, 250, 560, 420
    column = (width - left - label_w - 250) // len(COLOUR_LETTERS)
    n_rows = 2 + 2 * len(picks)
    gap = 40
    side = min(column - 60, (height - top - bottom - gap * (n_rows - 1)) // n_rows)

    def swatch(colours: list[tuple[int, int, int]]) -> Image.Image:
        im = Image.new("RGB", (side, side), "white")
        d = ImageDraw.Draw(im)
        band = side // len(colours)
        for n, colour in enumerate(colours):
            d.rectangle((0, n * band, side, (n + 1) * band), fill=colour)
        return im

    grey_piece = brown_piece = None
    for path in paths:  # the sheet's greyest and brownest parts
        if grey_piece is not None and brown_piece is not None:
            break
        try:
            g, b = check_pieces(path, side)
        except Exception:  # noqa: BLE001
            continue
        grey_piece = grey_piece or g
        brown_piece = brown_piece or b
    rows = [("Greys", "A cooler · G warmer", grey_piece or swatch(GREYS), lambda im, L: colour_fix(im, grey=L)),
            ("Browns", "A cooler · G warmer", brown_piece or swatch(BROWNS), lambda im, L: colour_fix(im, brown=L))]
    for pick in picks:
        piece = (_around(pick.path, pick.fx, pick.fy, side) if pick.path else None) or \
            Image.new("RGB", (side, side), tuple(pick.rgb))
        a, g = pick.sides()
        name = pick.name or colour_name(pick.rgb)
        rows.append((f"{name}: shade", f"A more {a} · G more {g}",
                     piece, lambda im, L, p=pick: pick_fix(im, p, shade=L, strength="D")))
        rows.append((f"{name}: strength", "A duller · G brighter",
                     piece, lambda im, L, p=pick: pick_fix(im, p, shade="D", strength=L)))
    draw.text((width // 2, 200), "Colour check: for each row, which column looks right on paper?", fill=(40, 40, 40),
              font=small, anchor="mm")
    x0 = left + label_w
    for i, letter in enumerate(COLOUR_LETTERS):
        draw.text((x0 + i * column + side // 2, top - 110), letter, fill=(30, 30, 30), font=big, anchor="mm")
    y = top
    for title, sides, piece, fix in rows:
        draw.text((left, y + side // 2 - 40), title, fill=(30, 30, 30), font=small, anchor="lm")
        draw.text((left, y + side // 2 + 40), sides, fill=(110, 110, 110), font=tiny, anchor="lm")
        for i, letter in enumerate(COLOUR_LETTERS):
            page.paste(fix(piece, letter), (x0 + i * column, y))
        y += side + gap
    draw.text((width // 2, height - 250), "D = as it is now", fill=(90, 90, 90), font=small, anchor="mm")
    return page
