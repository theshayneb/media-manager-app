import time

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from media_manager.settings import MediaSettings
from music_manager.core.settings import Settings as MusicSettings


def _music_folders(tmp_path):
    """Music asks for its folders on first start; give it some so no dialog opens."""
    m = MusicSettings.load()
    for name in ("Review", "Library"):
        (tmp_path / name).mkdir()
    m.review_folder, m.library_folder = str(tmp_path / "Review"), str(tmp_path / "Library")
    m.save()


def _wait(cond, seconds=5.0):
    end = time.time() + seconds
    while time.time() < end:
        QApplication.processEvents()
        if cond():
            return True
        time.sleep(0.02)
    return cond()


def _labels(win):
    return [win.list.item(r).text().strip() for r in range(win.list.count())]


def test_window_lists_every_kind_and_switches(tmp_path):
    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    movies = tmp_path / "Movies"
    tv = tmp_path / "TV"
    movies.mkdir()
    tv.mkdir()
    (movies / "Some.Movie.2019.1080p.mkv").write_bytes(b"x")
    (tv / "Show.Name.S01E02.Episode.Title.mkv").write_bytes(b"x")
    _music_folders(tmp_path)
    s = MediaSettings.load()
    s.movie_folders = [{"path": str(movies), "label": "Movies", "kind": "movies"},
                       {"path": str(tv), "label": "TV Shows", "kind": "tv"}]
    s.save()

    win = build_window()
    win.show()
    labels = _labels(win)
    for heading in ("PHOTOS & VIDEOS", "MUSIC", "MOVIES & TV"):
        assert any(heading in label for label in labels)
    assert "Library" in labels and "Review" in labels
    assert any("Movies" in label for label in labels) and any("TV Shows" in label for label in labels)

    win._clicked(win._item("movies", "movie:" + str(tv)))
    assert win.stack.currentWidget() is win.movies and not win.tags_dock.isVisible()
    assert _wait(lambda: win.movies.table.rowCount() == 1)
    assert win.movies.table.item(0, 3).text() == "Show Name - S01E02 - Episode Title.mkv"

    win._clicked(win._item("music", "library"))
    assert win.stack.currentWidget() is win.music and win.tags_dock.isVisible() and win.selected_dock.isVisible()

    assert win._item("photos", "photo-open") is not None  # no photo folders yet
    win.show_kind("photos")
    assert win.stack.currentWidget() is win.photos and win.details_dock.isVisible()
    assert not win.tags_dock.isVisible()

    win.close()
    again = MediaSettings.load()
    assert again.last_kind == "music" and again.last_key == "library"


def test_movie_folder_shows_add_entry_when_empty(tmp_path):
    QApplication.instance() or QApplication([])
    _music_folders(tmp_path)
    from media_manager.app import build_window

    win = build_window()
    assert win._item("movies", "movie-add") is not None
    _wait(lambda: False, 0.7)  # let the start-up timers run before closing
    win.close()


def _native_children(win):
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QWidget

    return [type(w).__name__ for w in win.findChildren(QWidget)
            if w.testAttribute(Qt.WidgetAttribute.WA_NativeWindow) and not w.isWindow()]


def test_clicks_still_work_after_playing_a_movie(tmp_path):
    """0.1.0's movie player (QVideoWidget) put a native window inside the app; on Windows the
    rest of the window then ignored clicks. Nothing inside the window may be native."""
    import subprocess

    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest

    from music_manager.core.ffmpeg import find_ffmpeg

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    ffmpeg = find_ffmpeg()
    _music_folders(tmp_path)
    for name in ("A - One", "B - Two"):
        (tmp_path / "Review" / f"{name}.mp3").write_bytes(b"")
    movies = tmp_path / "Movies"
    movies.mkdir()
    video = movies / "Some.Movie.2019.mkv"
    if ffmpeg:
        subprocess.run([ffmpeg, "-loglevel", "error", "-f", "lavfi", "-i", "testsrc=d=2:s=160x90", str(video)],
                       check=True)
    else:
        video.write_bytes(b"")
    s = MediaSettings.load()
    s.movie_folders = [{"path": str(movies), "label": "Movies", "kind": "movies"}]
    s.save()

    win = build_window()
    win.resize(1300, 800)
    win.show()
    _wait(lambda: False, 1.0)
    win._clicked(win._item("movies", "movie:" + str(movies)))
    assert _wait(lambda: win.movies.table.rowCount() == 1)
    win.movies.table.selectRow(0)
    win.movies.play_selected()
    _wait(lambda: False, 1.5)
    win._clicked(win._item("music", "review"))
    _wait(lambda: False, 1.5)
    assert _native_children(win) == []

    view = win.music.albums if win.music.albums.isVisible() else win.music.table
    model = view.model()
    rows = [r for r in range(model.rowCount()) if view.visualRect(model.index(r, 0)).height() > 0]
    picked = []
    for row in rows[:3]:
        rect = view.visualRect(model.index(row, 0)).intersected(view.viewport().rect())
        point = view.viewport().mapTo(win, rect.center())
        QTest.mouseClick(win.windowHandle(), Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, point)
        _wait(lambda: False, 0.3)
        picked.append(view.currentIndex().row())
    assert picked == rows[:3]
    win.close()


def test_report_qvideowidget_native(capsys):
    """Informational: does Qt's QVideoWidget make native windows on this platform? (printed in the CI log)"""
    from PySide6.QtWidgets import QMainWindow, QStackedWidget

    try:
        from PySide6.QtMultimediaWidgets import QVideoWidget
    except ImportError:
        return
    QApplication.instance() or QApplication([])
    top = QMainWindow()
    stack = QStackedWidget()
    stack.addWidget(QMainWindow())
    page = QMainWindow()
    page.setCentralWidget(QVideoWidget())
    stack.addWidget(page)
    top.setCentralWidget(stack)
    top.show()
    stack.setCurrentIndex(1)
    _wait(lambda: False, 0.5)
    stack.setCurrentIndex(0)
    _wait(lambda: False, 0.3)
    with capsys.disabled():
        print("\nQVideoWidget native children:", _native_children(top))
    top.close()


def _bar_texts(part):
    from PySide6.QtWidgets import QToolBar

    bar = next(b for b in part.findChildren(QToolBar) if not b.isHidden())
    out = []
    for a in bar.actions():
        w = bar.widgetForAction(a)
        out.append("|" if a.isSeparator() else (w.text() if hasattr(w, "text") and w.text() else a.text()))
    return [t for t in out if t]


def test_top_bars_share_one_layout(tmp_path):
    """Option A order, Option C icons: shared buttons are icons (named on hover), the rest are words."""
    from PySide6.QtWidgets import QToolBar

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    win = build_window()
    names = {"✏️": "Rename", "➡️": "Move to", "🗑": "Delete", "📁": "Show in Explorer", "⟳": "Refresh"}
    for part in (win.music, win.photos, win.movies):
        texts = _bar_texts(part)
        shared = [t for t in texts if t in names]
        assert shared == list(names), texts
        assert texts[-1] == "⚙" and any(t.startswith("📂") for t in texts), texts
        bar = next(b for b in part.findChildren(QToolBar) if not b.isHidden())
        for a in bar.actions():
            w = bar.widgetForAction(a)
            if w is not None and hasattr(w, "text") and w.text() in names:
                assert w.toolTip().startswith(names[w.text()]), (w.text(), w.toolTip())
        # no icons in front of words (Keep, Play, Convert…)
        assert not any(t[0] in "✔▶🗑▦☰" and len(t) > 2 for t in texts), texts
    music = _bar_texts(win.music)
    assert "Convert" in music and "Keep" in music and "Convert to MP3" not in music
    assert music.index("Keep") < music.index("✏️") < music.index("📁") < music.index("⟳")
    assert "Play" in _bar_texts(win.movies)
    assert win.music.delete_action.text() == "🗑 Delete"  # menus keep the full name
    assert win.photos.menuBar().isHidden()
    assert win._item("photos", "browse") is None
    win.close()


def test_photo_search_filters_by_name(tmp_path):
    from PIL import Image

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    pics = tmp_path / "pics"
    pics.mkdir()
    for name in ("beach.png", "city.png", "beach2.png"):
        Image.new("RGB", (8, 8)).save(pics / name)
    win = build_window()
    win.show()
    win.show_kind("photos")
    _wait(lambda: False, 0.5)  # Photo Manager opens its last folder at start-up
    win.photos.open_folder(str(pics))
    assert _wait(lambda: len(win.photos.model.all_items) == 3)
    win.photo_search.setText("beach")
    assert _wait(lambda: len(win.photos.model.items) == 2)
    assert win.photos.filter_btn.text() == "Filter"
    win.photo_search.setText("")
    assert _wait(lambda: len(win.photos.model.items) == 3)
    assert win.photo_folder.path == str(pics)
    win.close()


def test_music_move_to(tmp_path):
    from media_manager import bars

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    song = tmp_path / "Review" / "A - One.mp3"
    song.write_bytes(b"")
    (tmp_path / "Review" / "A - One.txt").write_text("la la")
    win = build_window()
    win._clicked(win._item("music", "review"))
    assert _wait(lambda: len(win.music.model.tracks) == 1)
    win.music.selected_paths = lambda: [str(song)]
    bars.move_music(win.music, str(tmp_path / "Library"))
    assert _wait(lambda: (tmp_path / "Library" / "A - One.mp3").exists() and not song.exists()
                 and (tmp_path / "Library" / "A - One.txt").exists())  # the lyrics file went along
    win.close()


def test_photo_panel_keeps_photo_manager_styles_and_size(tmp_path):
    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from photo_manager.core.settings import Settings as PhotoSettings
    from photo_manager.ui.main_window import STYLE

    _music_folders(tmp_path)
    alone = __import__("photo_manager.ui.main_window", fromlist=["MainWindow"]).MainWindow(PhotoSettings.load(), None)
    alone_width = alone.sidebar.minimumSizeHint().width()
    alone.close()
    win = build_window()
    assert STYLE.strip() in win.details_dock.styleSheet()
    # The chips and label buttons are as small as in Photo Manager on its own.
    assert win.photos.sidebar.minimumSizeHint().width() <= alone_width + 2
    win.close()


def test_panel_widths_survive_switching_sections(tmp_path):
    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    win = build_window()
    win.resize(1600, 900)
    win.show()
    win.show_kind("music")
    _wait(lambda: False, 0.5)
    win.resizeDocks([win.folders_dock, win.tags_dock], [205, 250], Qt.Orientation.Horizontal)
    _wait(lambda: False, 0.3)
    folders, tags = win.folders_dock.width(), win.tags_dock.width()
    win.show_kind("photos")
    _wait(lambda: False, 0.5)
    win.show_kind("movies")
    _wait(lambda: False, 0.5)
    win.show_kind("music")
    _wait(lambda: False, 0.5)
    assert abs(win.folders_dock.width() - folders) <= 3 and abs(win.tags_dock.width() - tags) <= 3
    win.close()


def test_collapsed_photo_groups_are_remembered(tmp_path):
    from PIL import Image

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    a, b = tmp_path / "a", tmp_path / "b"
    for folder in (a, b):
        folder.mkdir()
        for name in ("one.png", "two.jpg"):
            Image.new("RGB", (8, 8)).save(folder / name)
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    photos = win.photos
    photos.open_folder(str(b))
    photos.set_group("type")  # each folder has its own grouping (0.6.7)
    photos.open_folder(str(a))
    photos.set_group("type")
    titles = photos.model.group_titles()
    assert len(titles) == 2
    photos.grid.toggle_group(titles[0])
    assert photos.model.collapsed == {titles[0]}
    photos.open_folder(str(b))
    assert photos.model.collapsed == set()  # another folder: its own groups
    photos.open_folder(str(a))
    assert photos.model.collapsed == {titles[0]}
    win.close()
    again = MediaSettings.load()
    assert list(again.photo_collapsed.values()) == [[titles[0]]]


def test_timelines_scrub(tmp_path):
    """A click anywhere on a timeline jumps there (and dragging follows the mouse)."""
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QStyle

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from photo_manager.ui.video import VideoView

    _music_folders(tmp_path)
    win = build_window()
    win.show()
    sliders = [win.music.player.slider, win.movies.slider] + [v.slider for v in win.photos.findChildren(VideoView)]
    assert len(sliders) >= 3
    for slider in sliders:
        hint = slider.style().styleHint(QStyle.StyleHint.SH_Slider_AbsoluteSetButtons)
        assert hint == Qt.MouseButton.LeftButton.value
        slider.setRange(0, 100000)
        slider.setValue(0)
        slider.resize(400, 20)
        QTest.mouseClick(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(300, 10))
        assert slider.value() > 50000, slider.value()
    win.close()


def test_steam_import_kept_this_week_and_flat_bars(tmp_path):
    from PySide6.QtWidgets import QLabel, QToolBar

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    win = build_window()
    photos = _bar_texts(win.photos)
    assert photos.index("Convert") < photos.index("Steam import") < photos.index("Open")
    texts = [w.text() for w in win.music.checkup.findChildren(QLabel)]
    assert not any("KEPT THIS WEEK" in t or "Songs kept" in t for t in texts)
    for part in (win.music, win.photos, win.movies):
        bar = next(b for b in part.findChildren(QToolBar) if not b.isHidden())
        assert "border: none" in bar.styleSheet()  # no line along the top edge
    win.close()


def test_edit_button_window_tray_and_quiet_steam(tmp_path, monkeypatch):
    from PIL import Image
    from PySide6.QtGui import QWindowStateChangeEvent

    from media_manager.edit_view import EditView

    def EditDialog(path):  # noqa: N802  (the Edit view, loaded with a photo)
        view = EditView()
        view.load(path)
        return view

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    win = build_window()
    photos = _bar_texts(win.photos)
    assert photos.index("Convert") < photos.index("Edit") < photos.index("Steam import")
    from PySide6.QtGui import QAction

    edit = next(a for a in win.photos.findChildren(QAction) if a.iconText() == "Edit")
    assert edit.shortcut().toString() == "Shift+E"
    assert win.photos.quiet_steam_import is True
    menu = win.photos.extra_menu_items([str(tmp_path / "a.jpg")])
    assert menu[0][0] == "Edit…" and menu[0][3]

    # The Edit window: sliders change the right-hand side; Hold for Before shows the original.
    pic = tmp_path / "a.jpg"
    Image.new("RGB", (80, 60), (128, 128, 128)).save(pic)
    dlg = EditDialog(str(pic))
    assert not dlg.save_btn.isEnabled()
    assert dlg.view.split == 0.0  # the line starts at the left: all After
    dlg.values["yellow"].setValue(50)
    dlg._render()
    assert dlg.save_btn.isEnabled() and dlg.numbers["yellow"].text() == "+50"
    after = dlg.view.after.pixelColor(10, 10)
    assert after.blue() < after.red()
    dlg.before_btn.pressed.emit()
    assert dlg.view.whole_before
    dlg.before_btn.released.emit()
    assert not dlg.view.whole_before

    # ↻ and ⇋: shown at once (Before too), saved with Save, undone by Reset.
    dlg.rotate_btn.click()
    assert dlg.view.after.width() == 60 and dlg.view.before.width() == 60 and dlg.changed()
    dlg.flip_btn.menu().actions()[1].trigger()  # Flip vertical
    assert dlg.turn.mirror and dlg.view.after.height() == 80
    dlg.reset()
    assert dlg.turn.unchanged() and dlg.view.after.width() == 80 and not dlg.save_btn.isEnabled()
    dlg.view.resize(400, 300)
    dlg.view._move_line(dlg.view.picture_rect().left() + dlg.view.picture_rect().width() * 0.25)
    assert abs(dlg.view.split - 0.25) < 0.02
    dlg.reset()
    assert dlg.adjustments().unchanged() and not dlg.save_btn.isEnabled()

    # Each slider: a click jumps there; ↺ puts it back to 0; A sets it from the photo.
    from PySide6.QtCore import QPoint
    from PySide6.QtTest import QTest

    slider = dlg.values["contrast"]
    slider.resize(200, 20)
    QTest.mouseClick(slider, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.NoModifier, QPoint(190, 10))
    assert slider.value() > 70 and dlg.resets["contrast"].isEnabled()
    dlg.resets["contrast"].click()
    assert slider.value() == 0 and not dlg.resets["contrast"].isEnabled()

    warm = tmp_path / "warm.jpg"
    Image.new("RGB", (80, 60), (170, 140, 100)).save(warm)
    dlg2 = EditDialog(str(warm))
    dlg2.set_auto("yellow")
    assert dlg2.values["yellow"].value() < 0 and dlg2.values["contrast"].value() == 0  # only that one
    dlg2.set_auto(None)
    dlg2.reset()
    dlg2.pick_btn.setChecked(True)
    assert dlg2.view.picking
    dlg2.view.picked.emit(0.5, 0.5)  # clicked the (orange) middle: make it grey
    assert not dlg2.pick_btn.isChecked() and dlg2.values["yellow"].value() < -30
    dlg2._render()
    c = dlg2.view.after.pixelColor(40, 30)
    assert max(c.red(), c.green(), c.blue()) - min(c.red(), c.green(), c.blue()) < 12
    # A checkbox leaves a slider out (on screen and when saving), keeping its value.
    dlg2.reset()
    dlg2.values["contrast"].setValue(40)
    dlg2.values["sat_orange"].setValue(50)
    dlg2.checks["contrast"].setChecked(False)
    a = dlg2.adjustments()
    assert a.contrast == 0 and a.sat_orange == 50 and dlg2.values["contrast"].value() == 40
    assert not dlg2.values["contrast"].isEnabled() and dlg2.save_btn.isEnabled()
    dlg2.checks["sat_orange"].setChecked(False)
    assert dlg2.adjustments().unchanged() and not dlg2.save_btn.isEnabled()
    dlg2.checks["contrast"].setChecked(True)
    assert dlg2.adjustments().contrast == 40
    dlg2.reset()
    assert all(c.isChecked() for c in dlg2.checks.values()) and len(dlg2.checks) == 17
    assert dlg2.values["sharpness"].minimum() == 0 and dlg2.values["clarity"].minimum() == -100
    dlg2.set_auto(None)
    assert dlg2.values["sharpness"].value() == dlg2._auto["sharpness"]  # (a flat picture: 0)
    # The mouse wheel zooms; Shift+E closes (asking first when there are changes).
    from PySide6.QtCore import QPointF
    from PySide6.QtGui import QWheelEvent

    view = dlg2.view
    view.resize(400, 300)
    wheel = QWheelEvent(QPointF(200, 150), QPointF(200, 150), QPoint(0, 0), QPoint(0, 360),
                        Qt.MouseButton.NoButton, Qt.KeyboardModifier.NoModifier, Qt.ScrollPhase.NoScrollPhase, False)
    view.wheelEvent(wheel)
    assert view.zoom.zoomed and view.picture_rect().width() > view.fitted_rect().width()
    dlg2.reset()
    dlg2.close_with_shortcut()
    assert dlg2.result() == 0  # nothing changed: just closed
    dlg2.values["brightness"].setValue(30)
    from PySide6.QtWidgets import QMessageBox

    answers = []
    monkeypatch.setattr(QMessageBox, "exec", lambda box: answers.append(box.text()))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box.buttons()[0])  # "Save"
    dlg2.close_with_shortcut()
    assert answers and "Save the edit?" in answers[0] and dlg2.result() == 1
    dlg2.close()
    dlg.close()

    # The big preview zooms with the wheel too (patched in at start-up).
    from photo_manager.ui.preview import CropCanvas

    canvas = CropCanvas()
    canvas.resize(400, 300)
    from PySide6.QtGui import QPixmap

    pix = QPixmap(800, 600)
    canvas.set_image(pix, (800, 600))
    fitted = canvas._target().width()
    canvas.wheelEvent(wheel)
    assert canvas._target().width() > fitted
    canvas.set_image(pix, (800, 600))  # another photo (←/→): the same zoom (the user's request)
    assert canvas._target().width() > fitted

    # The tray: minimizing hides the window when the tray is there; the menu's tick turns it off.
    hidden = []
    monkeypatch.setattr(win.tray, "isVisible", lambda: True)
    monkeypatch.setattr(win, "hide", lambda: hidden.append(True))
    monkeypatch.setattr(win, "isMinimized", lambda: True)
    win.changeEvent(QWindowStateChangeEvent(Qt.WindowState.WindowNoState))
    _wait(lambda: bool(hidden), 1.0)
    assert hidden
    win.tray_toggle.setChecked(False)
    assert win.media.minimize_to_tray is False
    hidden.clear()
    win.changeEvent(QWindowStateChangeEvent(Qt.WindowState.WindowNoState))
    _wait(lambda: False, 0.2)
    assert not hidden
    win.close()


def test_edit_mode_in_the_main_window(tmp_path, monkeypatch):
    """Edit takes Photos' photo area; its sliders take the Folders panel's place; Details stays put.
    ←/→ go to the next photo; Save writes it, remembers it for "Same as last edit" and leaves."""
    from pathlib import Path

    from PIL import Image

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    pics = tmp_path / "pics"
    pics.mkdir()
    for name, colour in (("a.jpg", (120, 120, 120)), ("b.jpg", (90, 90, 90)), ("c.mp4", None)):
        if colour:
            Image.new("RGB", (40, 30), colour).save(pics / name)
        else:
            (pics / name).write_bytes(b"")
    monkeypatch.setattr("send2trash.send2trash", lambda p: Path(p).unlink())
    win = build_window()
    win.resize(1400, 900)
    win.show()
    _wait(lambda: False, 0.5)
    win.show_kind("photos")
    photos = win.photos
    photos.open_folder(str(pics))
    photos.grid.select_paths([str(pics / "a.jpg")], current=str(pics / "a.jpg"))
    details_area = win.dockWidgetArea(win.details_dock)
    folders_area = win.dockWidgetArea(win.folders_dock)

    photos.edit_mode.toggle()  # the Edit button / Shift+E
    edit = win.edit
    assert edit.active and photos.stack.currentWidget() is edit.view
    assert edit.dock.isVisible() and not win.folders_dock.isVisible()
    assert win.dockWidgetArea(edit.dock) == folders_area
    assert win.details_dock.isVisible() and win.dockWidgetArea(win.details_dock) == details_area
    assert not edit.view.same_btn.isEnabled()  # nothing saved yet

    edit.view.values["brightness"].setValue(40)
    answers = []
    from PySide6.QtWidgets import QMessageBox

    monkeypatch.setattr(QMessageBox, "exec", lambda box: answers.append(box.text()))
    monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: box.buttons()[0])  # "Save"
    edit.view.navigate.emit(1)  # →: asks, saves a.jpg, moves on to b.jpg
    assert answers == ["Save the edit?"]
    assert edit.view.path == str(pics / "b.jpg") and photos.grid.current_path() == str(pics / "b.jpg")
    assert edit.view.adjustments().unchanged() and win.media.last_edit["brightness"] == 40
    assert _wait(lambda: not photos.bg.pending, 5)
    with Image.open(pics / "a.jpg") as im:
        assert im.getpixel((5, 5))[0] > 125  # brighter
    edit.view.navigate.emit(1)  # → again: c.mp4 can't be edited, so nothing to go to
    assert edit.view.path == str(pics / "b.jpg")

    assert edit.view.same_btn.isEnabled()
    edit.view.same_btn.click()
    assert edit.view.values["brightness"].value() == 40
    edit.view.save_btn.click()  # Save: leaves Edit
    assert not edit.active and photos.stack.currentWidget() is photos.grid
    assert win.folders_dock.isVisible() and not edit.dock.isVisible()
    assert _wait(lambda: not photos.bg.pending, 5)
    with Image.open(pics / "b.jpg") as im:
        assert im.getpixel((5, 5))[0] > 95

    photos.edit_mode.toggle()
    assert edit.active
    edit.view.close_with_shortcut()  # Shift+E with nothing changed: just leaves
    assert not edit.active
    win.close()


def test_no_big_preview_for_photos_crop_delete_and_move_in_edit(tmp_path, monkeypatch):
    from pathlib import Path

    from PIL import Image
    from PySide6.QtCore import QRectF
    from PySide6.QtWidgets import QPushButton

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    _music_folders(tmp_path)
    pics = tmp_path / "pics"
    pics.mkdir()
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        Image.new("RGB", (80, 60), (120, 120, 120)).save(pics / name)
    (pics / "d.mp4").write_bytes(b"")
    trashed = []
    monkeypatch.setattr("send2trash.send2trash", lambda p: trashed.append(p) or Path(p).unlink())
    win = build_window()
    win.resize(1400, 900)
    win.show()
    _wait(lambda: False, 0.5)
    win.show_kind("photos")
    photos, edit = win.photos, win.edit
    photos.settings.confirm_delete = False
    photos.open_folder(str(pics))
    a = str(pics / "a.jpg")
    photos.grid.select_paths([a], current=a)
    assert win.folders_dock.isVisible()

    # Double-click (activated) and Shift+P open Edit, not the big preview; Folders hides.
    photos.grid.activated.emit(photos.model.index(photos.model.row_of(a)))
    assert edit.active and photos.stack.currentWidget() is edit.view and not win.folders_dock.isVisible()
    assert not any(b.isVisible() and b.text().startswith("Close") for b in edit.view.findChildren(QPushButton))
    edit.view.reject()
    assert win.folders_dock.isVisible() and photos.stack.currentWidget() is photos.grid
    from PySide6.QtCore import Qt as _Qt
    from PySide6.QtTest import QTest

    photos.grid.setFocus()
    QTest.keyClick(photos.grid, _Qt.Key.Key_P, _Qt.KeyboardModifier.ShiftModifier)  # Shift+P: the big preview
    assert photos.previewing and not edit.active and not win.folders_dock.isVisible()
    QTest.keyClick(photos.preview, _Qt.Key.Key_P, _Qt.KeyboardModifier.ShiftModifier)  # and Shift+P closes it
    assert not photos.previewing and win.folders_dock.isVisible()
    # The big preview (still there for videos and comparing) hides Folders and has no Close button.
    photos.grid.select_paths([a, str(pics / "b.jpg")], current=a)
    photos.open_preview()
    assert photos.previewing and not win.folders_dock.isVisible()
    assert not any(b.isVisible() and b.text().startswith("Close") for b in photos.preview.findChildren(QPushButton))
    photos.close_preview()
    assert win.folders_dock.isVisible()

    # Double-clicking a video opens the big preview.
    video = str(pics / "d.mp4")
    photos.grid.select_paths([video], current=video)
    photos.grid.activated.emit(photos.model.index(photos.model.row_of(video)))
    assert photos.previewing and not edit.active
    photos.close_preview()

    # Crop in the Edit view: Crop (C), a box, Save crop: the file is cropped, the sliders kept.
    photos.grid.select_paths([a], current=a)
    photos.edit_mode.toggle()
    edit.view.values["brightness"].setValue(20)
    edit.view.start_crop()
    assert edit.view.cropping and edit.view.crop_bar.isVisible()
    edit.view.cropper.box = QRectF(10, 10, 40, 30)
    edit.view.as_copy.setChecked(False)
    edit.view.apply_crop()
    assert _wait(lambda: not photos.bg.pending, 5)
    _wait(lambda: False, 0.3)
    with Image.open(a) as im:
        assert im.size == (40, 30)
    assert edit.view.original.size == (40, 30) and edit.view.values["brightness"].value() == 20

    # Delete while editing: to the Recycle Bin, and on to the next photo.
    edit.view.reset()
    photos.delete_selected()  # what the Delete key does
    assert _wait(lambda: not photos.bg.pending and a in trashed, 5)
    _wait(lambda: False, 0.3)
    assert edit.active and edit.view.path != a and Path(edit.view.path).exists()

    # Move to… under Rename in the Details panel.
    assert win.move_btn.text() == "Move to…"
    layout = photos.sidebar.layout()
    assert layout.indexOf(win.move_btn) > layout.indexOf(photos.sidebar.sections["rename"])
    assert 'section="true"' in win.details_dock.styleSheet() and "11pt" in win.details_dock.styleSheet()
    win.close()


def test_new_videos_are_flagged_until_the_folder_is_opened(tmp_path):
    QApplication.instance() or QApplication([])
    from media_manager.app import build_window

    movies, tv = tmp_path / "Movies", tmp_path / "TV"
    movies.mkdir()
    tv.mkdir()
    (movies / "Old.Movie.2001.mkv").write_bytes(b"x")
    _music_folders(tmp_path)
    s = MediaSettings.load()
    s.movie_folders = [{"path": str(movies), "label": "Movies", "kind": "movies"},
                       {"path": str(tv), "label": "TV Shows", "kind": "tv"}]
    s.save()

    win = build_window()
    win.show()
    win.check_new_videos()  # the first look only learns what's there
    assert _wait(lambda: str(movies) in win.media.movie_seen and not win._watching)
    assert not win.new_videos

    (movies / "New.Movie.2024.mkv").write_bytes(b"x")
    (movies / "Another.2023.mp4").write_bytes(b"x")
    win.check_new_videos()
    assert _wait(lambda: str(movies) in win.new_videos)
    item = win._item("movies", "movie:" + str(movies))
    assert item.text().strip().endswith("● 2 new") and item.font().bold()
    assert "New.Movie.2024.mkv" in item.toolTip()
    assert "new" not in win._item("movies", "movie:" + str(tv)).text()

    # Moving a video with Move to… into another watched folder doesn't make it new there.
    win.watch.add_seen([str(tv / "Moved.S01E01.mkv")])
    (tv / "Moved.S01E01.mkv").write_bytes(b"x")

    win._clicked(item)  # opening the folder sees them
    assert _wait(lambda: str(movies) not in win.new_videos)
    assert "new" not in win._item("movies", "movie:" + str(movies)).text()
    win.check_new_videos()
    assert _wait(lambda: not win._watching)
    assert not win.new_videos
    win.close()


def test_folders_in_your_order_and_the_drop_folder_lights_up(tmp_path):
    from PySide6.QtCore import QMimeData, QUrl
    from PySide6.QtGui import QDragMoveEvent

    QApplication.instance() or QApplication([])
    from media_manager.app import build_window
    from media_manager.shell import FolderList

    _music_folders(tmp_path)
    folders = []
    for name in ("Alpha", "Beta", "Gamma"):
        (tmp_path / name).mkdir()
        folders.append(str(tmp_path / name))
    win = build_window()
    win.show()
    _wait(lambda: False, 0.5)
    win.photos.settings.favorites = list(folders)
    win.photos._fill_favorites()
    keys = lambda: [k for k, _l, _t in win.entries()["photos"]]  # noqa: E731
    assert keys() == ["fav:" + f for f in folders]
    win.move_entry("photos", "fav:" + folders[2], "fav:" + folders[0], before=True)  # Gamma to the top
    assert keys() == ["fav:" + folders[2], "fav:" + folders[0], "fav:" + folders[1]]
    win.move_entry("music", "library", "review", before=True)
    assert [k for k, _l, _t in win.entries()["music"]][:2] == ["library", "review"]
    win.close()
    win = build_window()  # remembered
    assert [k for k, _l, _t in win.entries()["photos"]][0] == "fav:" + folders[2]

    # Photos held over a photo folder: it lights up.
    pic = tmp_path / "x.jpg"
    from PIL import Image

    Image.new("RGB", (8, 8)).save(pic)
    item = win._item("photos", "fav:" + folders[0])
    lst: FolderList = win.list
    mime = QMimeData()
    mime.setUrls([QUrl.fromLocalFile(str(pic))])
    pos = lst.visualItemRect(item).center()
    lst._dragging = None
    event = QDragMoveEvent(pos, Qt.DropAction.MoveAction, mime, Qt.MouseButton.LeftButton,
                           Qt.KeyboardModifier.NoModifier)
    lst.dragMoveEvent(event)
    assert lst._lit is item and item.background().color().alpha() > 0
    lst._light(None)
    assert item.background().style() == Qt.BrushStyle.NoBrush
    win.close()


def test_the_app_ends_without_a_console(monkeypatch):
    """0.6.14: the installed app has no console (sys.stdout is None): ending it showed an error."""
    import sys

    from media_manager import app as app_module

    ended = []
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    monkeypatch.setattr(app_module.os, "_exit", lambda code: ended.append(code))

    class FakeApp:
        def __init__(self, *_a):
            pass

        def exec(self):
            return 0

        def __getattr__(self, _name):
            return lambda *a, **k: None

    class FakeWindow:
        def __getattr__(self, _name):
            return lambda *a, **k: None

    monkeypatch.setattr(app_module, "QApplication", FakeApp)
    monkeypatch.setattr(app_module, "build_window", lambda: FakeWindow())
    monkeypatch.setattr(app_module, "install_error_handler", lambda: None)
    monkeypatch.setattr(app_module, "ICON", app_module.Path("no-icon-here.png"))
    app_module.main(["MediaManager"])
    assert ended == [0]
