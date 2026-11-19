import os
from datetime import date
from pathlib import Path

import pytest
from PIL import Image

from media_manager import layouts, print_size
from media_manager.photo_edit import Adjustments, Turn
from photo_manager.core.exiftool import ExifTool, find_exiftool


def test_sizes_are_the_affinity_macros_and_the_border_is_even():
    assert [(s.name, s.width, s.height) for s in print_size.SIZES] == [
        ("3x4", 1782, 2340), ("6x4", 3520, 2340), ("3x8", 1782, 4680), ("6x8", 3520, 4723)]
    for size in print_size.SIZES:
        w, h = size.photo_part(border=True)
        assert (size.width - w) == (size.height - h) == 2 * print_size.BORDER  # the same all round
        assert size.photo_part(border=False) == (size.width, size.height)  # never bigger with or without


def test_print_copy(tmp_path):
    src = tmp_path / "IMG_2041.jpg"
    Image.new("RGB", (4000, 3000), (40, 90, 160)).save(src, quality=95)
    out = tmp_path / "Project Life"
    size = print_size.BY_NAME["3x4"]
    w, h = size.photo_part(True)
    box = (100, 0, 100 + 3000 * w / h, 3000)
    first = print_size.save_print(str(src), Adjustments(), Turn(), box, size, True, str(out))
    assert Path(first).name == "IMG_2041 - 3x4 Border.jpg"
    with Image.open(first) as im:
        assert im.size == (1782, 2340) and round(im.info["dpi"][0]) == 600
        assert min(im.getpixel((10, 10))) > 245  # the white border
        assert im.getpixel((891, 1170))[2] > 120  # the photo inside
    second = print_size.save_print(str(src), Adjustments(), Turn(), box, size, True, str(out))
    assert Path(second).name == "IMG_2041 - 3x4 Border (2).jpg"
    plain = print_size.save_print(str(src), Adjustments(), Turn().rotated(), (0, 0, 3000, 4000),
                                  print_size.BY_NAME["6x8"], False, str(out))
    with Image.open(plain) as im:
        assert Path(plain).name == "IMG_2041 - 6x8 No.jpg" and im.size == (3520, 4723)
        assert im.getpixel((5, 5))[2] > 120  # no border


def test_print_copy_keeps_the_date_and_600_dpi(tmp_path):
    if not find_exiftool():
        pytest.skip("needs ExifTool")
    src = tmp_path / "IMG_1.jpg"
    Image.new("RGB", (800, 600), (128, 128, 128)).save(src, dpi=(72, 72))
    with ExifTool(find_exiftool()) as et:
        et.write(str(src), ["-AllDates=2026:11:17 10:00:00"])
        out = print_size.save_print(str(src), Adjustments(), Turn(), (0, 0, 600, 600),
                                    print_size.BY_NAME["6x4"], True, str(tmp_path / "out"), et)
        [data] = et.read([out], ["-EXIF:DateTimeOriginal", "-EXIF:XResolution"])
    assert str(data.get("EXIF:DateTimeOriginal")).startswith("2026:11:17")
    assert float(data.get("EXIF:XResolution")) == 600
    assert layouts.date_taken(out).date() == date(2026, 11, 17)


def test_the_three_layouts_are_read_from_their_pictures():
    found = {lay.name: lay for lay in layouts.load_layouts("")}
    assert found["Two 3x4 and a 6x4"].summary() == "2 tall · 1 wide"
    assert found["Four 3x4"].summary() == "4 tall"
    assert found["Two 6x4"].summary() == "2 wide"


def test_a_layout_in_the_folder_replaces_the_same_built_in_one(tmp_path):
    (tmp_path / "PL My four.jpg").write_bytes((layouts.BUILT_IN / "Four 3x4.jpg").read_bytes())
    (tmp_path / "notes.txt").write_text("not a picture")
    names = [lay.name for lay in layouts.load_layouts(str(tmp_path))]
    assert names[0] == "PL My four" and "Four 3x4" not in names and len(names) == 3


def test_week_prints_and_fit(tmp_path):
    def shot(name, size, taken):
        im = Image.new("RGB", size, "white")
        exif = im.getexif()
        if taken:
            exif.get_ifd(0x8769)[0x9003] = taken
        im.save(tmp_path / name, exif=exif)

    shot("a - 3x4 Border.jpg", (30, 40), "2026:11:16 09:00:00")   # Monday
    shot("b - 3x4 No.jpg", (30, 40), "2026:11:21 20:00:00")       # Saturday
    shot("c - 6x4 No.jpg", (60, 40), "2026:11:18 12:00:00")
    shot("d - 3x4 No.jpg", (30, 40), "2026:11:24 12:00:00")       # next week
    shot("e - 3x4 No.jpg", (30, 40), None)
    start = layouts.week_of(date(2026, 11, 18), "sunday")
    assert start == date(2026, 11, 15)
    week = layouts.week_prints(str(tmp_path), start)
    assert (week.tall, week.wide, week.undated) == (2, 1, 1)
    found = {lay.name: lay for lay in layouts.load_layouts("")}
    assert layouts.fit(found["Two 3x4 and a 6x4"], week) == (True, "✓ fits this week")
    assert layouts.fit(found["Four 3x4"], week) == (False, "needs 2 more tall")
    assert layouts.fit(found["Two 6x4"], week)[0] is False


def test_print_size_in_the_edit_view(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.edit_view import EditView

    pic = tmp_path / "a.jpg"
    Image.new("RGB", (400, 300), (120, 120, 120)).save(pic)
    view = EditView()
    view.resize(900, 700)
    view.load(str(pic))
    asked = []
    view.print_requested.connect(lambda *a: asked.append(a))
    view.start_print()
    assert view.printing and view.print_bar.isVisibleTo(view) and not view.crop_bar.isVisibleTo(view)
    box = view.cropper.box
    assert abs(box.width() / box.height() - print_size.BY_NAME["3x4"].ratio(True)) < 0.01
    assert [b.text() for b in view.size_buttons.values()] == ["3x4 (tall)", "6x4 (wide)", "3x8 (tall)", "6x8 (tall)"]
    view.size_buttons["6x4"].click()  # 6x4 (wide)
    view.print_border.setChecked(False)
    box = view.cropper.box
    assert abs(box.width() / box.height() - 3520 / 2340) < 0.01
    assert "3520 × 2340 px" in view.print_info.text()
    view.apply_print()
    assert asked and asked[0][2:] == ("6x4", False, "") and not view.printing


def test_layouts_stays_behind_details_wherever_it_is(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from media_manager.settings import MediaSettings
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    win = build_window()
    win.show()
    win.show_kind("photos")
    assert win.layouts_dock in win.tabifiedDockWidgets(win.details_dock)
    # The user's layout from before Layouts existed: Details on the left, under Folders.
    win.removeDockWidget(win.layouts_dock)
    win.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, win.details_dock)
    old_state = bytes(win.saveState().toBase64()).decode()
    win.close()
    s = MediaSettings.load()
    s.window_state, s.last_kind = old_state, "photos"
    s.save()
    win = build_window()
    win.show()
    _wait(lambda: False, 0.6)  # start-up done (with no photo folder it opens Music)
    win.show_kind("photos")
    _wait(lambda: False, 0.2)
    assert win.dockWidgetArea(win.details_dock) == Qt.DockWidgetArea.LeftDockWidgetArea
    behind = win.tabifiedDockWidgets(win.details_dock)
    assert win.layouts_dock in behind  # behind it, not a panel of its own
    assert win.templates_dock in behind  # and Photo Templates
    # Details dragged to the other side: Layouts goes with it.
    win.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, win.details_dock)
    _wait(lambda: win.layouts_dock in win.tabifiedDockWidgets(win.details_dock), 2)
    assert win.dockWidgetArea(win.layouts_dock) == Qt.DockWidgetArea.RightDockWidgetArea
    win.close()


def test_in_the_project_life_folder_the_selected_group_counts(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    pl = tmp_path / "Project Life"
    for sub in ("Week 1", "Week 2"):
        (pl / sub).mkdir(parents=True)
    for n in range(4):  # journaling cards and photos without a date
        Image.new("RGB", (30, 40)).save(pl / "Week 1" / f"card{n}.png")
    Image.new("RGB", (60, 40)).save(pl / "Week 2" / "wide.jpg")
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    win.media.print_folder = str(pl)
    win.show_kind("photos")
    photos = win.photos
    photos.open_folder(str(pl))
    photos.set_group("folder")
    card = str(pl / "Week 1" / "card0.png")
    photos.grid.select_paths([card], current=card)
    panel = win.layouts
    panel.refresh(force=True)
    assert _wait(lambda: panel.week is not None and panel.week.title == "Week 1")
    assert (panel.week.tall, panel.week.wide) == (4, 0)
    assert "Week 1" in panel.heading.text() and "4 tall" in panel.heading.text()
    four = next(lay for lay in panel.layouts if lay.name == "Four 3x4")
    assert layouts.fit(four, panel.week) == (True, "✓ fits")
    wide = str(pl / "Week 2" / "wide.jpg")
    photos.grid.select_paths([wide], current=wide)
    panel.refresh(force=True)
    assert _wait(lambda: panel.week.title == "Week 2" and panel.week.wide == 1)
    win.close()


def test_print_copy_goes_in_the_chosen_scrapbook_week(tmp_path):
    from datetime import datetime

    from photo_manager.ui.grid import album_week_dates

    week46 = album_week_dates(2026, 46)  # Sun Nov 15 - Sat Nov 21
    taken = datetime(2026, 11, 17, 9, 30)
    assert print_size.week_date(taken, *week46) == taken  # its own week: unchanged
    assert print_size.week_date(datetime(2026, 11, 10, 9, 30), *week46) == datetime(2026, 11, 17, 9, 30)  # +1 wk
    assert print_size.week_date(None, *week46) == datetime(2026, 11, 15, 12, 0)  # a card: noon, first day
    week1 = album_week_dates(2027, 1)  # Fri Jan 1 - Sat Jan 9
    assert print_size.week_date(datetime(2026, 12, 29, 8, 0), *week1) == datetime(2027, 1, 3, 8, 0)  # in Week 1
    # Without ExifTool too, the copy has the date (so the week groups find it).
    card = tmp_path / "card.png"
    Image.new("RGB", (300, 400), "white").save(card)
    out = print_size.save_print(str(card), Adjustments(), Turn(), (0, 0, 300, 394), print_size.BY_NAME["3x4"],
                                False, str(tmp_path / "pl"), None, print_size.week_date(None, *week46))
    assert layouts.date_taken(out) == datetime(2026, 11, 15, 12, 0)
    if find_exiftool():
        with ExifTool(find_exiftool()) as et:
            out = print_size.save_print(str(card), Adjustments(), Turn(), (0, 0, 300, 394),
                                        print_size.BY_NAME["3x4"], False, str(tmp_path / "pl"), et,
                                        datetime(2026, 11, 18, 12, 0))
        assert layouts.date_taken(out) == datetime(2026, 11, 18, 12, 0)


def test_print_size_week_list(tmp_path):
    from datetime import date

    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    pics = tmp_path / "pics"
    pics.mkdir()
    Image.new("RGB", (300, 400), "white").save(pics / "card.png")
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    win.show_kind("photos")
    win.photos.open_folder(str(pics))
    card = str(pics / "card.png")
    win.media.last_print_week = "2026-40"
    win.media.print_folder = str(tmp_path / "Project Life")  # (missing, it would ask where)
    (tmp_path / "Project Life").mkdir()
    win.edit.enter(card)
    win.edit.view.start_print()
    combo = win.edit.view.print_week
    assert combo.currentData() == "2026-40"  # a card: the week chosen last
    assert combo.count() >= 20 and combo.currentText().startswith("Week 40 · ")
    asked = []
    win.edit.view.print_requested.connect(lambda *a: asked.append(a))
    combo.setCurrentIndex(combo.currentIndex() + 1)
    win.edit.view.apply_print()
    assert asked[0][4] == "2026-41"
    win.photos.bg.wait(10000)
    _wait(lambda: False, 0.3)
    [out] = list((tmp_path / "Project Life").glob("*.jpg"))
    assert out.name == "card - 3x4 Border.jpg"
    assert layouts.date_taken(str(out)).date() == date(2026, 10, 11)  # Week 41: Sun Oct 11, noon
    assert win.media.last_print_week == "2026-41"
    win.close()


def test_the_page_plan(tmp_path):
    plan = layouts.Plan(str(tmp_path))
    assert plan.left(2026, 1) == (None, False)
    plan.choose(2026, 1, "left", "Two 6x4")         # Week 1 starts the album: its left page is free
    plan.choose(2026, 46, "right", "Four 3x4")
    again = layouts.Plan(str(tmp_path))              # saved in the Project Life folder
    assert (tmp_path / "Layout plan.json").exists()
    assert again.left(2026, 1) == ("Two 6x4", False)
    assert again.left(2026, 47) == ("Four 3x4", True)  # the back of Week 46's right page: locked
    assert again.left(2027, 1) == (None, False)
    again.choose(2026, 46, "right", None)
    assert layouts.Plan(str(tmp_path)).left(2026, 47) == (None, False)


def test_spread_in_the_layouts_panel(tmp_path):
    from datetime import datetime

    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    pl = tmp_path / "Project Life"
    pl.mkdir()

    def card(name, size, when):
        im = Image.new("RGB", size, "white")
        exif = im.getexif()
        exif.get_ifd(0x8769)[0x9003] = when.strftime("%Y:%m:%d %H:%M:%S")
        im.save(pl / name, exif=exif)

    for n in range(4):
        card(f"w46-{n}.jpg", (30, 40), datetime(2026, 11, 16, 10))   # Week 46: 4 tall
    for n in range(6):
        card(f"w47-{n}.jpg", (30, 40), datetime(2026, 11, 23, 10))   # Week 47: 6 tall
    card("w47-wide.jpg", (60, 40), datetime(2026, 11, 24, 10))
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    win.media.print_folder = str(pl)
    win.show_kind("photos")
    photos, panel = win.photos, win.layouts
    photos.open_folder(str(pl))
    photos.set_group("week")
    assert _wait(lambda: all(i.meta is not None for i in photos.model.items), 10)
    photos.set_group("week")

    def select(name):
        path = str(pl / name)
        photos.grid.select_paths([path], current=path)
        panel.refresh(force=True)
        _wait(lambda: not panel._busy and panel.week is not None and panel.week.names
              and name in panel.week.names, 5)

    select("w46-0.jpg")
    assert panel.album[1] == 46 and "Week 46" in panel.heading.text()
    four = next(i for i in range(panel.list.count())
                if panel.list.item(i).data(Qt.ItemDataRole.UserRole) == "Four 3x4")
    panel.list.itemDoubleClicked.emit(panel.list.item(four))       # this week's right page
    assert layouts.Plan(str(pl)).right(2026, 46) == "Four 3x4"
    assert "Four 3x4" in panel.right_text.text()

    select("w47-0.jpg")
    assert panel.album[1] == 47
    assert "🔒 Four 3x4" in panel.left_text.text() and not panel.left_clear.isVisible()
    assert "✓ fits" in panel.spread_verdict.text()        # left page alone: 4 tall of the 6 tall + 1 wide
    texts = {panel.list.item(i).data(Qt.ItemDataRole.UserRole): panel.list.item(i).text()
             for i in range(panel.list.count())}
    assert "with the left page: needs 2 more tall" in texts["Four 3x4"]   # 8 tall needed, 6 there
    assert "with the left page: ✓ fits" in texts["Two 3x4 and a 6x4"]      # 6 tall + 1 wide
    win.close()


def test_crop_box_nudges_and_finds_the_middle(tmp_path):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.edit_view import EditView

    pic = tmp_path / "a.jpg"
    Image.new("RGB", (400, 300), (120, 120, 120)).save(pic)
    view = EditView()
    view.resize(900, 700)
    view.show()
    view.load(str(pic))
    view.start_print()
    cropper = view.cropper
    assert cropper.centred() == (True, True)  # starts in the middle
    left = cropper.box.left()
    QTest.keyClick(view, Qt.Key.Key_Right, Qt.KeyboardModifier.ShiftModifier)
    assert cropper.box.left() > left and cropper.centred() == (False, True)
    for _ in range(3):
        QTest.keyClick(view, Qt.Key.Key_Left, Qt.KeyboardModifier.ShiftModifier)
    assert cropper.centred()[0] or cropper.box.left() < left  # it stopped at the middle on the way
    while cropper.box.center().x() < 200 - 0.75 and cropper.box.left() > 0:  # past it: back to the middle
        QTest.keyClick(view, Qt.Key.Key_Right)
        if cropper.centred()[0]:
            break
    assert cropper.centred()[0]
    assert view.printing  # the arrows didn't go to the next photo
    view.close()


def test_open_sends_every_selected_file(tmp_path, monkeypatch):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    pics = tmp_path / "pics"
    pics.mkdir()
    for n in range(3):
        Image.new("RGB", (8, 8)).save(pics / f"{n}.jpg")
    opened = []
    monkeypatch.setattr("PySide6.QtGui.QDesktopServices.openUrl", lambda url: opened.append(url.toLocalFile()))
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    photos = win.photos
    photos.open_folder(str(pics))
    photos.grid.select_paths([str(pics / "0.jpg"), str(pics / "2.jpg")], current=str(pics / "2.jpg"))
    from PySide6.QtGui import QAction

    action = next(a for a in photos.findChildren(QAction) if a.text() == "Open" and a.shortcuts())
    assert [s.toString() for s in action.shortcuts()] == ["Ctrl+O", "Shift+X"]
    action.trigger()
    assert sorted(os.path.normpath(p) for p in opened) == [str(pics / "0.jpg"), str(pics / "2.jpg")]
    win.close()


def make_psd(path, width, height, layers):
    """A bare Photoshop file with named layers (left, top, right, bottom): enough for the layer reader."""
    import struct

    records = b""
    for name, (left, top, right, bottom), text in layers:
        raw = name.encode("latin-1", "replace")[:255]
        pascal = bytes([len(raw)]) + raw
        pascal += b"\0" * (-len(pascal) % 4)
        luni_text = name.encode("utf-16-be")
        luni = struct.pack(">I", len(name)) + luni_text
        luni += b"\0" * (len(luni) % 2)
        extra = struct.pack(">I", 0) + struct.pack(">I", 0) + pascal
        extra += b"8BIMluni" + struct.pack(">I", len(luni)) + luni
        if text:
            extra += b"8BIMTySh" + struct.pack(">I", 2) + b"\0\0"
        records += struct.pack(">iiiiH", top, left, bottom, right, 0) + b"8BIMnorm" + bytes([255, 0, 0, 0])
        records += struct.pack(">I", len(extra)) + extra
    info = struct.pack(">h", len(layers)) + records
    info = struct.pack(">I", len(info)) + info
    header = b"8BPS" + struct.pack(">H", 1) + b"\0" * 6 + struct.pack(">HIIHH", 3, height, width, 8, 3)
    data = header + struct.pack(">I", 0) + struct.pack(">I", 0) + struct.pack(">I", len(info)) + info
    path.write_bytes(data)


def test_psd_photo_spots_and_the_two_tabs(tmp_path):
    assert [layouts.size_group(n) for n in ("3x4 - ESD - Day of Thanks 1", "6x4 - PP - Photo Templates 21",
                                           "3x8 - IACB - Comfort & Joy 2", "4x4 - FDD DD 1", "6x8 - PP - Dec Faves",
                                           "6x12 - Big", "Brooklyn")] == [
        "3x4", "6x4", "3x8", "4x4", "6x8", "6x12", "Other"]
    assert layouts.is_layout(Path("PL 3x4.jpg")) and not layouts.is_layout(Path("PL 3x4.psd"))
    assert not layouts.is_layout(Path("3x4 - Card.jpg"))
    card = tmp_path / "3x4 - Card.psd"
    make_psd(card, 900, 1200, [("Background", (0, 0, 900, 1200), False), ("clip photo", (192, 169, 708, 721), False),
                               ("Photo caption", (100, 800, 800, 900), True), ("tiny photo", (0, 0, 10, 10), False)])
    page = tmp_path / "6x8 - Page.psd"
    make_psd(page, 1800, 2400, [("Background", (0, 0, 1800, 2400), False), ("1-PHOTO", (100, 100, 800, 1100), False),
                                ("2-PHOTO", (900, 100, 1700, 700), False)])
    (tmp_path / "PL Mine.jpg").write_bytes((layouts.BUILT_IN / "Two 6x4.jpg").read_bytes())
    (tmp_path / "Brooklyn.png").write_bytes((layouts.BUILT_IN / "Two 6x4.jpg").read_bytes())
    assert [s.shape for s in layouts.psd_spots(str(card))] == ["square"]  # not the text layer, not the tiny one
    groups = layouts.load_templates(str(tmp_path))
    assert list(groups) == ["3x4", "6x8", "Other"]  # in the size order; Other last; no Layouts among them
    assert groups["3x4"][0].summary() == "1 photo spot" and groups["6x8"][0].summary() == "2 photo spots"
    names = [lay.name for lay in layouts.load_layouts(str(tmp_path))]
    assert names[0] == "PL Mine" and "6x8 - Page" not in names  # Layouts: only the PL JPGs (and built-ins)


def test_photo_templates_follow_the_folder(tmp_path):
    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    templates = tmp_path / "Digital Templates"
    templates.mkdir()
    Image.new("RGB", (90, 120), "white").save(templates / "3x4 - Card.png")
    win = build_window()
    win.media.layouts_folder = str(templates)
    win.show()
    _wait(lambda: False, 0.5)
    win.show_kind("photos")
    assert [d.windowTitle() for d in win._behind_details()] == ["Layouts", "Photo Templates"]
    win.load_templates()
    panel = win.templates

    def texts():
        return [panel.list.item(i).text() for i in range(panel.list.count())]

    assert _wait(lambda: texts() == ["▾  3x4 · 1", "3x4 - Card\nPNG"], 5)
    panel.bg.wait(5000)  # its thumbnail made
    _wait(lambda: False, 0.2)
    (templates / "3x4 - Card.png").rename(templates / "4x4 - Card.png")  # renamed: it moves groups by itself
    assert _wait(lambda: texts() == ["▾  4x4 · 1", "4x4 - Card\nPNG"], 10)
    panel.list.itemClicked.emit(panel.list.item(0))  # fold the group
    assert texts() == ["▸  4x4 · 1"] and win.media.template_folded == ["4x4"]
    win.close()


def test_closing_doesnt_wait_for_slow_reading(tmp_path):
    """0.6.12 stayed open (frozen on the screen) while a template in OneDrive was still being read."""
    import threading
    import time

    from PySide6.QtWidgets import QApplication

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from tests.shell.test_window import _music_folders, _wait

    _music_folders(tmp_path)
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    release = threading.Event()
    for bg in (win.templates_bg, win.templates.bg, win.layouts.bg, win.watch_bg):
        bg.run(lambda: release.wait(30))  # a file that takes "forever" to read
    started = time.time()
    win.close()
    assert time.time() - started < 5
    release.set()


def test_psd_layers_reads_only_the_layer_list(tmp_path, monkeypatch):
    psd = tmp_path / "3x4 - Card.psd"
    make_psd(psd, 900, 1200, [("clip photo", (192, 169, 708, 721), False)])
    with open(psd, "ab") as f:
        f.write(b"\0" * 5_000_000)  # the pictures (never read)
    read = []
    real_open = open

    def counting_open(path, mode="r", *a, **k):  # type: ignore[no-untyped-def]
        f = real_open(path, mode, *a, **k)
        if str(path) == str(psd):
            original = f.read
            f.read = lambda n=-1: (read.append(n), original(n))[1]
        return f

    monkeypatch.setattr("builtins.open", counting_open)
    assert [s.shape for s in layouts.psd_spots(str(psd))] == ["square"]
    assert -1 not in read and sum(read) < 10_000
