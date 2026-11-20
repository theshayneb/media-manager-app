from datetime import datetime
from pathlib import Path

import pytest
from PIL import Image

from media_manager import print_sheet
from media_manager.print_sheet import MARGIN, Piece, arrange, crop_marks, render
from photo_manager.core.exiftool import ExifTool, find_exiftool

SIZES = {"3x4": (1782, 2340), "6x4": (3520, 2340), "3x8": (1782, 4680), "6x8": (3520, 4723)}


def pieces(*names):
    return [Piece(f"{n}-{i}", *SIZES[n]) for i, n in enumerate(names)]


def check(sheet):
    """Inside the paper with the margin, centred, nothing overlapping, sizes unchanged."""
    w, h = sheet.size
    xs = [p.x for p in sheet.placed] + [p.x + p.w for p in sheet.placed]
    ys = [p.y for p in sheet.placed] + [p.y + p.h for p in sheet.placed]
    assert min(xs) >= MARGIN and min(ys) >= MARGIN and max(xs) <= w - MARGIN and max(ys) <= h - MARGIN
    assert abs(min(xs) - (w - max(xs))) <= 1 and abs(min(ys) - (h - max(ys))) <= 1  # centred
    for a in sheet.placed:
        assert sorted((a.w, a.h)) == sorted((a.piece.width, a.piece.height))  # never resized
        for b in sheet.placed:
            if a is not b:
                assert a.x + a.w <= b.x or b.x + b.w <= a.x or a.y + a.h <= b.y or b.y + b.h <= a.y


@pytest.mark.parametrize("names,sheets", [
    (["3x4"] * 6, 1), (["3x4"] * 4 + ["6x4"], 1), (["6x4"] * 3, 1), (["6x8", "3x4", "3x4"], 1),
    (["3x8", "3x4", "3x4", "6x4"], 1), (["3x4"] * 12, 2), (["3x4"] * 7, 2),
])
def test_arranged_on_as_few_sheets_as_possible(names, sheets):
    result, too_big = arrange(pieces(*names))
    assert len(result) == sheets and not too_big
    assert sum(len(s.placed) for s in result) == len(names)
    for sheet in result:
        check(sheet)


def test_photos_touch_and_crop_marks_stay_off_the_photos():
    [sheet], _ = arrange(pieces("3x4", "3x4", "3x4", "3x4", "6x4"))
    edges = {(p.x + p.w, p.y) for p in sheet.placed}
    assert any((q.x, q.y) in edges for q in sheet.placed)  # side by side, no gap
    marks = crop_marks(sheet)
    assert marks
    for x0, y0, x1, y1 in marks:
        for p in sheet.placed:  # no mark on a photo
            inside_x = p.x < x0 < p.x + p.w - 1 or p.x < x1 < p.x + p.w - 1
            inside_y = p.y < y0 < p.y + p.h - 1 or p.y < y1 < p.y + p.h - 1
            assert not (inside_x and inside_y and (x0 == x1 or y0 == y1) and
                        p.x < (x0 + x1) / 2 < p.x + p.w and p.y < (y0 + y1) / 2 < p.y + p.h)


def test_too_big_for_the_paper():
    _sheets, too_big = arrange([Piece("poster", 6000, 8000)])
    assert [p.path for p in too_big] == ["poster"]


def test_rendered_at_600_dpi_at_its_real_size(tmp_path):
    a = tmp_path / "a - 3x4 Border.jpg"
    Image.new("RGB", SIZES["3x4"], (200, 40, 40)).save(a, quality=95, dpi=(600, 600))
    b = tmp_path / "b - 6x4 No.jpg"
    Image.new("RGB", SIZES["6x4"], (40, 40, 200)).save(b, quality=95, dpi=(600, 600))
    [sheet], _ = arrange([print_sheet.piece_for(str(a)), print_sheet.piece_for(str(b))])
    page = render(sheet)
    assert page.size in ((5100, 6600), (6600, 5100))  # 8.5 × 11 in at 600 DPI
    for p in sheet.placed:
        r, _g, bl = page.getpixel((p.x + p.w // 2, p.y + p.h // 2))
        assert (r > 150) == ("a - " in p.piece.path) and (bl > 150) == ("b - " in p.piece.path)

    left = min(p.x for p in sheet.placed)
    assert page.getpixel((left - 40, sheet.placed[0].y + 200)) == (255, 255, 255)  # white round them
    # Brighter: on the sheet only, each photo its own amount.
    sheet.placed[0].piece.brighter = 21
    p = sheet.placed[0]
    lighter = render(sheet).getpixel((p.x + p.w // 2, p.y + p.h // 2))
    assert sum(lighter) > sum(page.getpixel((p.x + p.w // 2, p.y + p.h // 2)))
    with Image.open(p.piece.path) as original:  # the print copy itself is unchanged
        assert abs(original.getpixel((5, 5))[0] - (200 if "a - " in p.piece.path else 40)) < 4
    out = print_sheet.save(sheet, str(tmp_path), print_sheet.sheet_name("Week 46", 1))
    assert Path(out).name == "Week 46 - Sheet 1.jpg" and print_sheet.is_sheet(out)
    assert not print_sheet.is_sheet(str(a))
    with Image.open(out) as im:
        assert round(im.info["dpi"][0]) == 600


def test_print_sheet_window_prints_and_marks(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from PySide6.QtPrintSupport import QPrinter

    from media_manager.app import build_window
    from media_manager.print_sheet_window import PrintSheetWindow
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    pl = tmp_path / "Project Life"
    pl.mkdir()
    paths = []
    for n in range(5):
        path = pl / f"IMG_{n} - 3x4 Border.jpg"
        im = Image.new("RGB", SIZES["3x4"], (100 + n * 20, 120, 140))
        exif = im.getexif()
        exif.get_ifd(0x8769)[0x9003] = datetime(2026, 11, 17, 10).strftime("%Y:%m:%d %H:%M:%S")
        im.save(path, quality=90, exif=exif, dpi=(600, 600))
        paths.append(str(path))
    win = build_window()
    win.media.print_folder = str(pl)
    win.show()
    _wait(lambda: False, 0.5)
    win.show_kind("photos")
    photos = win.photos
    photos.open_folder(str(pl))
    assert _wait(lambda: all(i.meta is not None for i in photos.model.items), 10)
    sheet = PrintSheetWindow(photos, win.media, paths)
    assert len(sheet.sheets) == 1 and len(sheet.sheets[0].placed) == 5
    assert "Sheet 1 of 1" in sheet.page_label.text()
    saved = sheet.save_sheets()
    assert [Path(p).name for p in saved] == ["Week 46 - Sheet 1.jpg"]
    printer = QPrinter(QPrinter.PrinterMode.HighResolution)
    printer.setOutputFormat(QPrinter.OutputFormat.PdfFormat)
    printer.setOutputFileName(str(tmp_path / "out.pdf"))
    printer.setResolution(600)
    printer.setFullPage(True)
    assert sheet.print_to(printer)
    assert (tmp_path / "out.pdf").stat().st_size > 1000
    if find_exiftool():
        photos.bg.wait(20000)
        _wait(lambda: False, 0.5)
        with ExifTool(find_exiftool()) as et:
            [data] = et.read([paths[0]], ["-XMP-photoshop:Instructions"])
        assert str(data.get("XMP:Instructions", "")).startswith("Printed by Media Manager")
        assert _wait(lambda: photos.model.item(paths[0]).meta.printed, 10)  # the 🖨 in the grid
    sheet.close()
    win.close()
