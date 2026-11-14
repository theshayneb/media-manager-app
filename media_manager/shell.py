"""Media Manager's window: one Folders list for every kind of media, and the matching part of the
app next to it. Photos & Videos is Photo Manager, Music is Music Manager (both exactly as they
are, with their own settings), Movies & TV is new.
"""

from __future__ import annotations

import os

from PySide6.QtCore import QByteArray, Qt, QTimer
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import (
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from music_manager.ui.main_window import MainWindow as MusicWindow
from photo_manager.ui.folders import dropped_files, wants_copy
from photo_manager.ui.main_window import MainWindow as PhotoWindow

from . import __version__, bars, scrub
from .movies.window import KINDS, MoviesWindow
from .settings import MediaSettings

GROUPS = [("photos", "📷  PHOTOS & VIDEOS"), ("music", "🎵  MUSIC"), ("movies", "🎬  MOVIES & TV")]
KIND_ROLE = Qt.ItemDataRole.UserRole
KEY_ROLE = Qt.ItemDataRole.UserRole + 1


class FolderList(QListWidget):
    """The Folders list. Photos can be dropped on a photo folder to move them there (Ctrl to copy),
    as on Photo Manager's favorites."""

    def __init__(self, shell: "MediaWindow"):
        super().__init__()
        self.shell = shell
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)

    def _photo_folder_at(self, pos) -> str:  # type: ignore[no-untyped-def]
        item = self.itemAt(pos)
        if item is None or item.data(KIND_ROLE) != "photos":
            return ""
        key = str(item.data(KEY_ROLE) or "")
        return key[4:] if key.startswith("fav:") and os.path.isdir(key[4:]) else ""

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if dropped_files(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self._photo_folder_at(event.position().toPoint()):
            event.setDropAction(Qt.DropAction.CopyAction if wants_copy(event) else Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        folder = self._photo_folder_at(event.position().toPoint())
        paths = dropped_files(event)
        if folder and paths:
            self.shell.photos.move_paths(paths, folder, copy=wants_copy(event))
            event.acceptProposedAction()
        else:
            event.ignore()


class MediaWindow(QMainWindow):
    def __init__(self, media: MediaSettings, photos: PhotoWindow, music: MusicWindow):
        super().__init__()
        self.media = media
        self.setWindowTitle(f"Media Manager {__version__}")
        self.resize(1500, 920)
        self.photos, self.music = photos, music
        self.movies = MoviesWindow(media)
        self.kind = ""
        self._filling = False

        # The three parts sit inside this window (each keeps its own toolbar, panels and status bar).
        self.stack = QStackedWidget()
        for part in (self.photos, self.music, self.movies):
            part.setWindowFlags(Qt.WindowType.Widget)
            self.stack.addWidget(part)

        # Music's own Folders panel is replaced by this one; its album art and check-up move here.
        self.music.folders_dock.hide()
        self.music.folders_dock.toggleViewAction().setVisible(False)
        self.photo_tree = next((d for d in self.photos.findChildren(QDockWidget) if d.windowTitle() == "Folders"),
                               None)
        if self.photo_tree is not None:  # folders are opened from the 📂 folder button instead
            self.photo_tree.hide()
            self.photo_tree.toggleViewAction().setVisible(False)

        scrub.install(self.music, self.movies)  # drag along any timeline to scrub
        # The same top-bar layout in every section.
        self.music_folder = bars.music_bar(self.music, self)
        self.photo_folder, self.photo_search = bars.photo_bar(self.photos)

        # The panels: Folders and Selected (album art + check-up) here, and Music's Tags panel moved out
        # of Music so all three can be dragged by their titles to any edge of the window.
        self.list = FolderList(self)
        self.list.setStyleSheet("QListWidget { font-size: 14px; } QListWidget::item { padding: 4px 6px; }")
        self.list.itemClicked.connect(self._clicked)
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
        self.list.setMinimumWidth(190)
        self.folders_dock = self._dock("Folders", "media-folders", self.list)

        self.music_extras = QWidget()
        mv = QVBoxLayout(self.music_extras)
        mv.setContentsMargins(0, 0, 0, 0)
        self.music.now_card.heading.hide()  # the panel's title says it
        mv.addWidget(self.music.now_card)
        mv.addWidget(self.music.checkup)
        mv.addStretch(1)
        self.selected_dock = self._dock("Selected", "media-selected", self.music_extras)
        card, show_track = self.music.now_card, self.music.now_card.show_track

        def titled_show_track(track, playing):  # type: ignore[no-untyped-def]
            show_track(track, playing)
            self.selected_dock.setWindowTitle(card.heading.text().title())  # "Selected" / "Now Playing"

        card.show_track = titled_show_track

        self.tags_dock = self.music.editor_dock
        self.music.removeDockWidget(self.tags_dock)
        self.details_dock = self.photos.details_dock  # Photo Manager's panel, unchanged, now movable here
        self.photos.removeDockWidget(self.details_dock)
        self.details_dock.setTitleBarWidget(None)  # a title to drag it by
        # Photo Manager styles its chips and label buttons on its window; the panel keeps those styles here.
        self.details_dock.setStyleSheet(self.photos.styleSheet())
        self._remember_collapsed()

        self.setCentralWidget(self.stack)
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowNestedDocks)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.folders_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.selected_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.tags_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.details_dock)
        self.tags_dock.show()
        self.details_dock.show()
        self.resizeDocks([self.folders_dock, self.tags_dock], [240, 270], Qt.Orientation.Horizontal)
        if media.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(media.window_geometry.encode()))
        if media.window_state:
            self.restoreState(QByteArray.fromBase64(media.window_state.encode()))

        # Keep the list up to date when folders are added, renamed or removed in any part.
        self._wrap(self.music, "_fill_views")
        self._wrap(self.photos, "_fill_favorites")
        self.movies.folders_changed.connect(self.fill)
        self.fill()
        QTimer.singleShot(50, self._restore)

    def _dock(self, title: str, name: str, widget: QWidget) -> QDockWidget:
        dock = QDockWidget(title, self)
        dock.setObjectName(name)
        dock.setWidget(widget)
        dock.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetMovable)
        dock.setToolTip("Drag this panel by its title to move it to another edge of the window")
        return dock

    def _wrap(self, part, name: str) -> None:  # type: ignore[no-untyped-def]
        original = getattr(part, name)

        def wrapped(*args, **kwargs):  # type: ignore[no-untyped-def]
            result = original(*args, **kwargs)
            QTimer.singleShot(0, self.fill)
            return result

        setattr(part, name, wrapped)

    # ------------------------------------------------------------ the Folders list
    def entries(self) -> dict[str, list[tuple[str, str, str]]]:
        """{kind: [(key, label, tooltip)]}."""
        photos = [("fav:" + f, os.path.basename(os.path.normpath(f)) or f, f) for f in self.photos.settings.favorites]
        if not photos:
            photos = [("photo-open", "＋ Open a folder…", "Open a photo folder (📂 in the top bar adds it here)")]
        music = [(d["key"], d["label"], self.music.folder(d["key"])) for d in self.music.view_defs()]
        movies = [("movie:" + f["path"], f"{'📺' if f.get('kind') == 'tv' else '🎞'} {f.get('label') or f['path']}",
                   f"{KINDS.get(f.get('kind', 'movies'))}: {f['path']}") for f in self.media.movie_folders]
        if not movies:
            movies = [("movie-add", "＋ Add a folder…", "Add a Movies or TV Shows folder")]
        return {"photos": photos, "music": music, "movies": movies}

    def fill(self) -> None:
        current = self.list.currentItem()
        keep = (current.data(KIND_ROLE), current.data(KEY_ROLE)) if current else (self.kind, self.media.last_key)
        self._filling = True
        self.list.clear()
        for kind, heading in GROUPS:
            head = QListWidgetItem(heading)
            head.setFlags(Qt.ItemFlag.NoItemFlags)
            font = QFont()
            font.setBold(True)
            font.setPointSizeF(font.pointSizeF() * 0.85)
            head.setFont(font)
            head.setForeground(QColor("#9aa0a8"))
            self.list.addItem(head)
            for key, label, tip in self.entries()[kind]:
                item = QListWidgetItem("   " + label)
                item.setData(KIND_ROLE, kind)
                item.setData(KEY_ROLE, key)
                item.setToolTip(tip)
                self.list.addItem(item)
                if (kind, key) == keep:
                    self.list.setCurrentItem(item)
        self._filling = False

    def _item(self, kind: str, key: str) -> QListWidgetItem | None:
        for row in range(self.list.count()):
            item = self.list.item(row)
            if item.data(KIND_ROLE) == kind and item.data(KEY_ROLE) == key:
                return item
        return None

    def _restore(self) -> None:
        item = self._item(self.media.last_kind, self.media.last_key)
        if item is None:  # the Music Library, else the first entry there is
            item = self._item("music", "library") or next(
                (self.list.item(r) for r in range(self.list.count()) if self.list.item(r).data(KIND_ROLE)), None)
        if item is not None:
            self.list.setCurrentItem(item)
            self._clicked(item)

    def _clicked(self, item: QListWidgetItem) -> None:
        kind, key = item.data(KIND_ROLE), str(item.data(KEY_ROLE) or "")
        if not kind:
            return
        if key == "photo-open":
            self.show_kind("photos")
            bars._open_photo_folder(self.photos)
            return
        if key == "movie-add":
            self.show_kind("movies")
            self.movies.add_folder("movies")
            return
        self.show_kind(kind)
        self.media.last_kind, self.media.last_key = kind, key
        if kind == "photos" and key.startswith("fav:"):
            self.photos.open_folder(key[4:])
        elif kind == "music":
            if self.music.view != key or not self.music.model.tracks:
                self.music._select_view_item(key)
        elif kind == "movies" and key.startswith("movie:"):
            path = key[6:]
            entry = next((f for f in self.media.movie_folders if f["path"] == path), {"path": path})
            self.movies.open_entry(entry)

    def show_kind(self, kind: str) -> None:
        if kind == self.kind:
            return
        # Only one thing plays at a time.
        if self.kind == "music" and self.music.player.is_playing():
            self.music.player.toggle()
        if self.kind == "movies":
            self.movies.stop()
        self.kind = kind
        part = {"photos": self.photos, "music": self.music, "movies": self.movies}[kind]
        self._remember_widths()
        self.stack.setCurrentWidget(part)
        self.selected_dock.setVisible(kind == "music")
        self.tags_dock.setVisible(kind == "music")
        self.details_dock.setVisible(kind == "photos")
        QTimer.singleShot(0, self._restore_widths)

    # ------------------------------------------------------------ panel widths
    def _docks(self) -> list[QDockWidget]:
        return [self.folders_dock, self.selected_dock, self.tags_dock, self.details_dock]

    def _side(self, dock: QDockWidget) -> bool:
        return self.dockWidgetArea(dock) in (Qt.DockWidgetArea.LeftDockWidgetArea,
                                             Qt.DockWidgetArea.RightDockWidgetArea)

    def _remember_widths(self) -> None:
        """Showing or hiding a panel makes Qt re-size the others; note each one's size to put it back."""
        for d in self._docks():
            if d.isVisible():
                self.media.dock_sizes[d.objectName()] = d.width() if self._side(d) else d.height()

    def _restore_widths(self) -> None:
        shown = [d for d in self._docks() if d.isVisible() and d.objectName() in self.media.dock_sizes]
        for orientation, docks in ((Qt.Orientation.Horizontal, [d for d in shown if self._side(d)]),
                                   (Qt.Orientation.Vertical, [d for d in shown if not self._side(d)])):
            if docks:
                self.resizeDocks(docks, [self.media.dock_sizes[d.objectName()] for d in docks], orientation)
        self._fit_details()

    # ------------------------------------------------------------ photo groups
    def _remember_collapsed(self) -> None:
        """Collapsed photo groups are remembered for each folder and grouping (also after a restart)."""
        photos, model = self.photos, self.photos.model
        saved = self.media.photo_collapsed  # {"<folder>|<group by>": [titles]}

        def key(folder: str, group: str) -> str:
            return f"{os.path.normcase(os.path.normpath(folder))}|{group}"

        set_collapsed, load_folder, set_group = model.set_collapsed, model.load_folder, photos.set_group

        def set_collapsed_saved(title: str, collapsed: bool) -> None:
            set_collapsed(title, collapsed)
            if model.folder:
                k = key(model.folder, model.group_by)
                if model.collapsed:
                    saved[k] = sorted(model.collapsed)
                else:
                    saved.pop(k, None)

        def load_folder_saved(folder: str) -> None:
            model.collapsed = set(saved.get(key(folder, model.group_by), []))
            load_folder(folder)

        def set_group_saved(group: str) -> None:
            if model.folder:
                model.collapsed = set(saved.get(key(model.folder, group), []))
            set_group(group)

        model.set_collapsed, model.load_folder, photos.set_group = set_collapsed_saved, load_folder_saved, \
            set_group_saved

    def _fit_details(self) -> None:
        """Photo Manager's panel never narrower than its contents (they'd be cut off)."""
        need = self.photos.sidebar.minimumSizeHint().width() + 24  # + its scroll bar
        if self.details_dock.isVisible() and self.details_dock.width() < need:
            self.resizeDocks([self.details_dock], [need], Qt.Orientation.Horizontal)

    def _menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        item = self.list.itemAt(pos)
        menu = QMenu(self)
        kind = item.data(KIND_ROLE) if item else None
        key = str(item.data(KEY_ROLE) or "") if item else ""
        if kind == "music":
            d = self.music.view_def(key)
            if d and d["kind"] in ("folder", "search"):
                menu.addAction("Rename…", lambda: self.music._rename_view(d))
                menu.addAction("Remove from the list", lambda: self.music._remove_view(d))
                menu.addSeparator()
            menu.addAction("Add a music folder…", self.music.add_folder_view)
            menu.addAction("Save the current music search…", self.music.save_search_view)
        elif kind == "photos":
            if key.startswith("fav:"):
                menu.addAction("Remove from Favorites", lambda: self.photos.toggle_favorite(key[4:]))
                menu.addSeparator()
            menu.addAction("Open a folder…", lambda: bars._open_photo_folder(self.photos))
        elif kind == "movies":
            if key.startswith("movie:"):
                menu.addAction("Remove from the list", lambda: self.movies.remove_folder(key[6:]))
                menu.addSeparator()
            menu.addAction("Add a Movies folder…", lambda: self.movies.add_folder("movies"))
            menu.addAction("Add a TV Shows folder…", lambda: self.movies.add_folder("tv"))
        if not menu.isEmpty():
            menu.exec(self.list.mapToGlobal(pos))

    # ------------------------------------------------------------ closing
    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.media.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.media.window_state = bytes(self.saveState().toBase64()).decode()
        self._remember_widths()
        for part in (self.movies, self.music, self.photos):
            part.close()  # each saves its own settings and stops its work
        try:
            self.media.save()
        except OSError:
            pass
        super().closeEvent(event)
