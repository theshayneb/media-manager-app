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
    assert _wait(lambda: (tmp_path / "Library" / "A - One.mp3").exists() and not song.exists())
    assert (tmp_path / "Library" / "A - One.txt").exists()  # the lyrics file went along
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
    photos.set_group("type")
    photos.open_folder(str(a))
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

    from media_manager.edit_dialog import EditDialog

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
    dlg.values["yellow"].setValue(50)
    dlg._render()
    assert dlg.save_btn.isEnabled() and dlg.numbers["yellow"].text() == "+50"
    after = dlg.view.after.pixelColor(10, 10)
    assert after.blue() < after.red()
    dlg.before_btn.pressed.emit()
    assert dlg.view.whole_before
    dlg.before_btn.released.emit()
    assert not dlg.view.whole_before
    dlg.view.resize(400, 300)
    dlg.view._move_line(dlg.view.picture_rect().left() + dlg.view.picture_rect().width() * 0.25)
    assert abs(dlg.view.split - 0.25) < 0.02
    dlg.reset()
    assert dlg.adjustments().unchanged() and not dlg.save_btn.isEnabled()
    dlg.close()

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
