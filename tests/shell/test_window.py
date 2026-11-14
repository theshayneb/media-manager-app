import time

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

    win._clicked(win._item("photos", "browse"))
    assert win.stack.currentWidget() is win.photos and win.media.photo_tree

    win.close()
    again = MediaSettings.load()
    assert again.last_kind == "music" and again.last_key == "library" and again.photo_tree


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
