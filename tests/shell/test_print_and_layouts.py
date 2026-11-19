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
    (tmp_path / "My four.jpg").write_bytes((layouts.BUILT_IN / "Four 3x4.jpg").read_bytes())
    (tmp_path / "notes.txt").write_text("not a picture")
    names = [lay.name for lay in layouts.load_layouts(str(tmp_path))]
    assert names[0] == "My four" and "Four 3x4" not in names and len(names) == 3


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
    assert layouts.fit(found["Four 3x4"], week) == (False, "✗ needs 2 more tall")
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
    view.print_size.setCurrentIndex(1)  # 6x4 (wide)
    view.print_border.setChecked(False)
    box = view.cropper.box
    assert abs(box.width() / box.height() - 3520 / 2340) < 0.01
    assert "3520 × 2340 px" in view.print_info.text()
    view.apply_print()
    assert asked and asked[0][2:] == ("6x4", False) and not view.printing


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
    assert win.layouts_dock in win.tabifiedDockWidgets(win.details_dock)  # behind it, not a panel of its own
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
