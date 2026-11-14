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
    assert win.stack.currentWidget() is win.movies and not win.music_extras.isVisible()
    assert _wait(lambda: win.movies.table.rowCount() == 1)
    assert win.movies.table.item(0, 3).text() == "Show Name - S01E02 - Episode Title.mkv"

    win._clicked(win._item("music", "library"))
    assert win.stack.currentWidget() is win.music and win.music_extras.isVisible()

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
    win.close()
