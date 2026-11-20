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


@pytest.mark.parametrize("names,placed", [
    (["3x4"] * 6, 6), (["3x4"] * 8, 6), (["6x4"] * 3, 2), (["6x4", "3x4", "3x4"], 3),
    (["3x8", "3x4", "3x4", "6x4"], 3), (["3x4"] * 4 + ["6x4"], 4), (["6x8", "3x4", "3x4"], 1),
])
def test_the_first_sheet_is_as_full_as_a_cuttable_grid_allows(names, placed):
    result, too_big = arrange(pieces(*names))
    assert not too_big and len(result[0].placed) == placed
    assert sum(len(s.placed) for s in result) == len(names)
    for sheet in result:
        check(sheet)
        assert not print_sheet.cuts_cross_a_photo(sheet)


def test_every_cut_goes_all_the_way_across_with_marks_at_both_ends():
    [sheet, *_rest], _ = arrange(pieces("6x4", "3x4", "3x4"))
    assert not print_sheet.cuts_cross_a_photo(sheet)
    edges = {(p.x + p.w, p.y) for p in sheet.placed} | {(p.x, p.y + p.h) for p in sheet.placed}
    assert any((q.x, q.y) in edges for q in sheet.placed)  # touching, no gap
    marks = crop_marks(sheet)
    left = min(p.x for p in sheet.placed)
    right = max(p.x + p.w for p in sheet.placed)
    top = min(p.y for p in sheet.placed)
    bottom = max(p.y + p.h for p in sheet.placed)
    for x in {p.x for p in sheet.placed} | {p.x + p.w for p in sheet.placed}:  # each column line: above and below
        assert any(m[0] == m[2] == x and m[3] < top for m in marks)
        assert any(m[0] == m[2] == x and m[1] > bottom for m in marks)
    for y in {p.y for p in sheet.placed} | {p.y + p.h for p in sheet.placed}:  # each row line: left and right
        assert any(m[1] == m[3] == y and m[2] < left for m in marks)
        assert any(m[1] == m[3] == y and m[0] > right for m in marks)
    # The user's example: a tall 6x4 beside two stacked ones isn't allowed (a cut would go through it).
    from media_manager.print_sheet import Placed, Sheet

    bad = Sheet(False, [Placed(Piece("a", 2340, 3520), 0, 500, False),
                        Placed(Piece("b", 3520, 2340), 2340, 0, False),
                        Placed(Piece("c", 3520, 2340), 2340, 2340, False)])
    assert print_sheet.cuts_cross_a_photo(bad)


def test_too_big_for_the_paper():
    _sheets, too_big = arrange([Piece("poster", 6000, 8000)])
    assert [p.path for p in too_big] == ["poster"]


def test_rendered_at_600_dpi_at_its_real_size(tmp_path):
    a = tmp_path / "a - 3x4 Border.jpg"
    Image.new("RGB", SIZES["3x4"], (200, 40, 40)).save(a, quality=95, dpi=(600, 600))
    b = tmp_path / "b - 6x4 No.jpg"
    Image.new("RGB", SIZES["6x4"], (40, 40, 200)).save(b, quality=95, dpi=(600, 600))
    [sheet], _ = arrange([print_sheet.piece_for(str(a)), print_sheet.piece_for(str(b)),
                          print_sheet.piece_for(str(a))])
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
    for n in range(8):  # 6 fit on a sheet: 2 left over
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
    assert len(sheet.sheets) == 1 and len(sheet.sheets[0].placed) == 6  # one full sheet only
    assert len(sheet.leftover) == 2 and "2 left over" in sheet.page_label.text()
    on_sheet = [p.piece.path for p in sheet.sheets[0].placed]
    left = [p.path for p in sheet.leftover]
    # Picking a photo on the sheet colours its name in the list (and a name picks the photo).
    piece = sheet.sheets[0].placed[2].piece
    sheet.select(piece)
    assert sheet.names[id(piece)].styleSheet() and not sheet.names[id(sheet.sheets[0].placed[0].piece)].styleSheet()
    other = sheet.sheets[0].placed[0].piece
    sheet.names[id(other)].mousePressEvent(None)
    assert sheet.view.selected is other and sheet.names[id(other)].styleSheet()
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
            [data] = et.read([on_sheet[0]], ["-XMP-photoshop:Instructions"])
            [unprinted] = et.read([left[0]], ["-XMP-photoshop:Instructions"])
        assert str(data.get("XMP:Instructions", "")).startswith("Printed by Media Manager")
        assert not unprinted.get("XMP:Instructions")  # left over: no 🖨
        assert _wait(lambda: photos.model.item(on_sheet[0]).meta.printed, 10)  # the 🖨 in the grid
        assert not photos.model.item(left[0]).meta.printed
    sheet.close()
    win.close()


def test_colour_fix_changes_only_greys_and_browns():
    im = Image.new("RGB", (4, 1))
    grey, brown, blue, red = (128, 128, 128), (150, 105, 70), (40, 90, 200), (230, 40, 40)
    for x, colour in enumerate((grey, brown, blue, red)):
        im.putpixel((x, 0), colour)
    cooler = print_sheet.colour_fix(im, grey="B", brown="D")
    g = cooler.getpixel((0, 0))
    assert g[2] > g[0]  # grey: bluer (less warm)
    assert cooler.getpixel((1, 0)) == brown  # browns left as they are (D)
    assert cooler.getpixel((2, 0)) == blue and cooler.getpixel((3, 0)) == red  # other colours untouched
    warmer = print_sheet.colour_fix(im, grey="D", brown="F").getpixel((1, 0))
    assert warmer[2] < brown[2]  # brown: warmer
    assert print_sheet.colour_fix(im) is im  # D, D: nothing done


def test_colour_check_page():
    page = print_sheet.colour_check_page()
    assert page.size == (6600, 5100)  # landscape 11 × 8.5 in at 600 DPI
    column = (6600 - 800) // 7
    a = page.getpixel((400 + 60 + 100, 900))
    d = page.getpixel((400 + 3 * column + 60 + 100, 900))
    assert a[2] > a[0] and d[0] == d[1] == d[2]  # A cooler, D a true grey


def test_printer_profile(tmp_path):
    from PIL import ImageCms

    names = ["Canon iP8700 series PR1.icc", "Canon iP8700 series MP1.icc", "Canon iP8700 series GL1.icc",
             "sRGB Color Space Profile.icm", "Canon MG5700 series MP1.icc"]
    for name in names:
        (tmp_path / name).write_bytes(b"x")
    (tmp_path / "notes.txt").write_text("not a profile")
    profiles = print_sheet.printer_profiles(tmp_path)
    assert len(profiles) == 5
    assert print_sheet.suggested_profile(profiles).name == "Canon iP8700 series MP1.icc"  # the matte one
    assert print_sheet.suggested_profile([tmp_path / "Canon iP8700 series GL1.icc"]) is None
    # A real profile: the colours converted (here sRGB to sRGB: nearly the same).
    srgb = tmp_path / "test-srgb.icc"
    srgb.write_bytes(ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes())
    im = Image.new("RGB", (4, 4), (120, 100, 80))
    out = print_sheet.to_printer(im, str(srgb))
    assert all(abs(a - b) <= 3 for a, b in zip(out.getpixel((1, 1)), (120, 100, 80), strict=True))
    assert print_sheet.to_printer(im, "") is im
    with pytest.raises(OSError):
        print_sheet.to_printer(im, str(tmp_path / "Canon iP8700 series PR1.icc"))  # not a real profile



def test_ctrl_p_opens_print_sheet(tmp_path, monkeypatch):
    from PySide6.QtGui import QAction
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    win = build_window()
    win.show()
    _wait(lambda: False, 0.3)
    action = next(a for a in win.photos.findChildren(QAction) if a.text() == "Print sheet")
    assert [k.toString() for k in action.shortcuts()] == ["Ctrl+P", "Shift+S"]
    opened = []
    win.photos.open_print_sheet = lambda: opened.append(True)
    action.trigger()
    assert opened
    win.close()
