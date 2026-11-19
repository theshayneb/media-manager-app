"""Media Manager's window: one Folders list for every kind of media, and the matching part of the
app next to it. Photos & Videos is Photo Manager, Music is Music Manager (both exactly as they
are, with their own settings), Movies & TV is new.
"""

from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import QByteArray, QEvent, QMimeData, QPoint, Qt, QTimer
from PySide6.QtGui import QBrush, QColor, QDrag, QFont, QIcon, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDockWidget,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QPushButton,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from music_manager.ui.main_window import MainWindow as MusicWindow
from photo_manager.ui.folders import dropped_files, wants_copy
from photo_manager.ui.main_window import MainWindow as PhotoWindow

from . import __version__, bars, scrub
from .movies import watch
from .movies.window import KINDS, MoviesWindow
from .settings import MediaSettings

GROUPS = [("photos", "📷  PHOTOS & VIDEOS"), ("music", "🎵  MUSIC"), ("movies", "🎬  MOVIES & TV")]
KIND_ROLE = Qt.ItemDataRole.UserRole
FIXED = {"photo-open", "movie-add"}  # the "＋ Add…" entries stay where they are
NEW_COLOUR = "#f0a830"   # a Movies & TV folder with new videos in it
WATCH_EVERY_MS = 60_000  # how often the Movies & TV folders are checked for new videos
KEY_ROLE = Qt.ItemDataRole.UserRole + 1


ORDER_MIME = "application/x-media-manager-folder"
DROP_COLOUR = QColor(59, 111, 196, 150)  # the folder a photo will be dropped in


class FolderList(QListWidget):
    """The Folders list. Photos can be dropped on a photo folder to move them there (Ctrl to copy),
    as on Photo Manager's favorites; that folder lights up while you hold them over it. A folder can be
    dragged up or down within its own section to put the list in your order (settings.folder_order)."""

    def __init__(self, shell: "MediaWindow"):
        super().__init__()
        self.shell = shell
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self._press: tuple[QPoint, QListWidgetItem] | None = None
        self._lit: QListWidgetItem | None = None
        self._line_y: int | None = None  # where a dragged folder will go
        self._dragging: tuple[str, str] | None = None  # (kind, key) of a folder being dragged

    # -- dragging a folder to another place in its section
    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        item = self.itemAt(event.position().toPoint())
        movable = item is not None and item.data(KIND_ROLE) and str(item.data(KEY_ROLE)) not in FIXED
        self._press = (event.position().toPoint(), item) if movable and \
            event.button() == Qt.MouseButton.LeftButton else None
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self._press and event.buttons() & Qt.MouseButton.LeftButton and \
                (event.position().toPoint() - self._press[0]).manhattanLength() >= QApplication.startDragDistance():
            item = self._press[1]
            self._press = None
            mime = QMimeData()
            mime.setData(ORDER_MIME, f"{item.data(KIND_ROLE)}\n{item.data(KEY_ROLE)}".encode())
            drag = QDrag(self)
            drag.setMimeData(mime)
            drag.exec(Qt.DropAction.MoveAction)
            return
        super().mouseMoveEvent(event)

    def _order_target(self, pos) -> tuple[QListWidgetItem, bool] | None:  # type: ignore[no-untyped-def]
        """(the entry it goes next to, before it?) for a dragged folder: only within its own section."""
        item = self.itemAt(pos)
        source = self._dragging
        if item is None or source is None or item.data(KIND_ROLE) != source[0] or str(item.data(KEY_ROLE)) in FIXED:
            return None
        rect = self.visualItemRect(item)
        return item, pos.y() < rect.center().y()

    def _light(self, item: QListWidgetItem | None, line_y: int | None = None) -> None:
        if self._lit is not None and self._lit is not item:
            self._lit.setBackground(QBrush())
        self._lit = item
        if item is not None:
            item.setBackground(QBrush(DROP_COLOUR))
        if line_y != self._line_y:
            self._line_y = line_y
            self.viewport().update()

    def dragLeaveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._light(None)
        self._dragging = None
        super().dragLeaveEvent(event)

    def paintEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().paintEvent(event)
        if self._line_y is not None:
            p = QPainter(self.viewport())
            p.setPen(QPen(QColor("#4c8dff"), 3))
            p.drawLine(4, self._line_y, self.viewport().width() - 4, self._line_y)
            p.end()

    def _photo_folder_at(self, pos) -> str:  # type: ignore[no-untyped-def]
        item = self.itemAt(pos)
        if item is None or item.data(KIND_ROLE) != "photos":
            return ""
        key = str(item.data(KEY_ROLE) or "")
        return key[4:] if key.startswith("fav:") and os.path.isdir(key[4:]) else ""

    def dragEnterEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._dragging = None
        if event.mimeData().hasFormat(ORDER_MIME):
            kind, key = bytes(event.mimeData().data(ORDER_MIME)).decode().split("\n", 1)
            self._dragging = (kind, key)
            event.acceptProposedAction()
        elif dropped_files(event):
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        pos = event.position().toPoint()
        if self._dragging is not None:
            target = self._order_target(pos)
            if target:
                rect = self.visualItemRect(target[0])
                self._light(None, rect.top() if target[1] else rect.bottom())
                event.setDropAction(Qt.DropAction.MoveAction)
                event.accept()
            else:
                self._light(None)
                event.ignore()
            return
        if self._photo_folder_at(pos):
            self._light(self.itemAt(pos))  # this folder lights up: the photos go here
            event.setDropAction(Qt.DropAction.CopyAction if wants_copy(event) else Qt.DropAction.MoveAction)
            event.accept()
        else:
            self._light(None)
            event.ignore()

    def dropEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        pos = event.position().toPoint()
        self._light(None)
        if self._dragging is not None:
            target = self._order_target(pos)
            kind, key = self._dragging
            self._dragging = None
            if target:
                self.shell.move_entry(kind, key, str(target[0].data(KEY_ROLE)), before=target[1])
                event.acceptProposedAction()
            else:
                event.ignore()
            return
        folder = self._photo_folder_at(pos)
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
        self.photos.quiet_steam_import = True  # no pop-up after a Steam import (the status bar says it)
        self._build_tray()
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
        self.details_dock.setStyleSheet(
            self.photos.styleSheet()
            # The section headings (Labels, Keywords, Date taken, Rename…) a little bigger (the user's request).
            + '\nQToolButton[section="true"] { font-size: 11pt; padding: 6px 4px; }')
        # A "Move to…" button at the bottom of the panel, under Rename: the same as right-click → Move to….
        move = QPushButton("Move to…")
        move.setToolTip("Move the selected photos to another folder (Ctrl+M)")
        move.clicked.connect(lambda: self.photos.move_selected())
        sidebar = self.photos.sidebar.layout()
        sidebar.insertSpacing(sidebar.count() - 1, 8)
        sidebar.insertWidget(sidebar.count() - 1, move)
        self.move_btn = move
        self._remember_collapsed()
        # Layouts (scrapbook pages): a tab with Details, so it slides over it and back.
        from .layouts_panel import LayoutsPanel

        self.layouts = LayoutsPanel(media, self.photos)
        self.layouts_dock = self._dock("Layouts", "media-layouts", self.layouts)  # the page protectors
        # Photo Templates: the cards that go inside a pocket, grouped by size (one tab).
        from .layouts_panel import TemplatesPanel

        self.templates = TemplatesPanel(media)
        self.templates.cache_dir = getattr(self.photos.model, "cache_dir", None)  # thumbnails kept on disk
        self.templates_dock = self._dock("Photo Templates", "media-photo-templates", self.templates)
        self._watch_templates()
        self.layouts_dock.visibilityChanged.connect(lambda shown: self.layouts.refresh() if shown else None)
        self._layouts_timer = QTimer(self)  # another photo selected: perhaps another week
        self._layouts_timer.setSingleShot(True)
        self._layouts_timer.setInterval(300)
        self._layouts_timer.timeout.connect(self._refresh_layouts)
        self.photos.grid.selectionModel().currentChanged.connect(lambda *_a: self._layouts_timer.start())

        from .edit_mode import EditMode

        self.edit = EditMode(self)  # Photos' Edit view: its sliders go where the Folders panel is
        self.photos.stack.currentChanged.connect(lambda _i: self._photo_page())
        self.setCentralWidget(self.stack)
        self.setDockOptions(QMainWindow.DockOption.AnimatedDocks | QMainWindow.DockOption.AllowNestedDocks)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.folders_dock)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.selected_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.tags_dock)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.details_dock)
        for dock in self._behind_details():
            self.tabifyDockWidget(self.details_dock, dock)
        self.details_dock.raise_()
        self.tags_dock.show()
        self.details_dock.show()
        self.resizeDocks([self.folders_dock, self.tags_dock], [240, 270], Qt.Orientation.Horizontal)
        if media.window_geometry:
            self.restoreGeometry(QByteArray.fromBase64(media.window_geometry.encode()))
        if media.window_state:
            self.restoreState(QByteArray.fromBase64(media.window_state.encode()))
        # Layouts lives behind Details (a tab of it), wherever Details is: also after a saved layout from before
        # it existed, and when Details is dragged somewhere else.
        self._layouts_behind_details()
        self.details_dock.dockLocationChanged.connect(lambda _area: QTimer.singleShot(0, self._layouts_behind_details))

        # Keep the list up to date when folders are added, renamed or removed in any part.
        self._wrap(self.music, "_fill_views")
        self._wrap(self.photos, "_fill_favorites")
        self.movies.folders_changed.connect(self.fill)
        self._watch_new_videos()
        self.fill()
        QTimer.singleShot(50, self._restore)
        QTimer.singleShot(2000, self._write_companion)  # for the Android app, through OneDrive

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
        movies = []
        for f in self.media.movie_folders:
            label = f"{'📺' if f.get('kind') == 'tv' else '🎞'} {f.get('label') or f['path']}"
            tip = f"{KINDS.get(f.get('kind', 'movies'))}: {f['path']}"
            new = self.new_videos.get(f["path"], [])
            if new:  # dropped in since you last looked (cleared when the folder is opened)
                label += f"   ● {len(new)} new"
                tip += "\n\nNew:\n" + "\n".join(os.path.basename(p) for p in new[:15]) + \
                       (f"\n…and {len(new) - 15} more" if len(new) > 15 else "")
            movies.append(("movie:" + f["path"], label, tip))
        if not movies:
            movies = [("movie-add", "＋ Add a folder…", "Add a Movies or TV Shows folder")]
        out = {"photos": photos, "music": music, "movies": movies}
        for kind, entries in out.items():  # in the user's order (dragged), the rest after as they come
            order = self.media.folder_order.get(kind, [])
            entries.sort(key=lambda e: order.index(e[0]) if e[0] in order else len(order))
        return out

    def move_entry(self, kind: str, key: str, target: str, before: bool) -> None:
        """A folder dragged within its section: remember the new order."""
        keys = [k for k, _label, _tip in self.entries()[kind] if k not in FIXED]
        if key not in keys or target not in keys or key == target:
            return
        keys.remove(key)
        keys.insert(keys.index(target) + (0 if before else 1), key)
        self.media.folder_order[kind] = keys
        self.fill()

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
                if kind == "movies" and self.new_videos.get(key[6:]):
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
                    item.setForeground(QColor(NEW_COLOUR))
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
        for dock in self._behind_details():
            dock.setVisible(kind == "photos")
        if kind == "photos":
            self._layouts_behind_details()
            QTimer.singleShot(0, self._layouts_behind_details)
        if self.edit.active:  # editing a photo: its sliders show with Photos only, in the Folders panel's place
            self.edit.dock.setVisible(kind == "photos")
        self._photo_page()
        QTimer.singleShot(0, self._restore_widths)

    def _photo_page(self) -> None:
        """The Folders panel shows only with Photos' list (not in Edit or the big preview)."""
        if self.kind == "photos":
            self.folders_dock.setVisible(self.photos.stack.currentWidget() is self.photos.grid)
        elif not self.folders_dock.isVisible():
            self.folders_dock.show()

    def showEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().showEvent(event)
        # Qt puts a saved layout back once more when the window first shows (a layout from before Layouts
        # existed would leave it on its own): behind Details again, after that.
        QTimer.singleShot(0, self._layouts_behind_details)
        QTimer.singleShot(200, self._layouts_behind_details)

    def _behind_details(self) -> list[QDockWidget]:
        """The tabs that live behind Details: Layouts, then Photo Templates."""
        return [self.layouts_dock, self.templates_dock]

    def _layouts_behind_details(self) -> None:
        if self.details_dock.isHidden() or self.details_dock.isFloating():
            return  # (Qt only knows hidden panels' tabs once they show: done again then, by show_kind)
        tabbed = self.tabifiedDockWidgets(self.details_dock)
        moved = False
        for dock in self._behind_details():
            if dock.isHidden() or dock in tabbed:
                continue
            # (Qt won't move a panel that's in another tab group by tabifying alone: out and back in first.)
            self.removeDockWidget(dock)
            self.addDockWidget(self.dockWidgetArea(self.details_dock), dock)
            dock.show()
            self.tabifyDockWidget(self.details_dock, dock)
            moved = True
        if moved:
            self.details_dock.raise_()

    # ------------------------------------------------------------ Digital Templates (all the tabs)
    def _watch_templates(self) -> None:
        """Fill the template tabs, and again when a file in Digital Templates is added, renamed or deleted."""
        from PySide6.QtCore import QFileSystemWatcher

        from music_manager.ui.workers import Background

        self.templates_bg = Background(1)
        self.templates_watcher = QFileSystemWatcher(self)
        self._templates_timer = QTimer(self)
        self._templates_timer.setSingleShot(True)
        self._templates_timer.setInterval(1000)  # a burst of changes (copying several files): look once
        self._templates_timer.timeout.connect(self.load_templates)
        self.templates_watcher.directoryChanged.connect(lambda _d: self._templates_timer.start())
        QTimer.singleShot(1500, self.load_templates)

    def load_templates(self) -> None:
        from . import layouts

        folder = self.media.layouts_folder
        watched = self.templates_watcher.directories()
        if watched:
            self.templates_watcher.removePaths(watched)
        if os.path.isdir(folder):
            dirs = [folder] + [os.path.join(r, d) for r, ds, _f in os.walk(folder) for d in ds
                               if not d.startswith((".", "$", "@", "#"))]
            self.templates_watcher.addPaths(dirs)

        def done(found, error) -> None:  # type: ignore[no-untyped-def]
            if error or found is None:
                return
            self.templates.set_templates(found)
            self.layouts.refresh(force=True, layouts_too=True)  # the 6x8 tab too (a file renamed into it…)

        self.templates_bg.run(lambda: layouts.load_templates(folder), done)

    def _refresh_layouts(self) -> None:
        if self.layouts_dock.isVisible() and not self.layouts.visibleRegion().isEmpty():  # its tab is in front
            self.layouts.refresh()

    # ------------------------------------------------------------ panel widths
    def _docks(self) -> list[QDockWidget]:
        return [self.folders_dock, self.selected_dock, self.tags_dock, self.details_dock, *self._behind_details(),
                self.edit.dock]

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

    # ------------------------------------------------------------ new videos in Movies & TV
    def _watch_new_videos(self) -> None:
        """Every minute, look for videos dropped into the Movies & TV folders: the folder shows "● N new"
        in the Folders list (and a note pops up by the clock) until it's opened."""
        from music_manager.ui.workers import Background

        self.new_videos: dict[str, list[str]] = {}
        self.watch = watch.Watch(self.media.movie_seen)
        self.watch_bg = Background(1)
        self._watching = False
        self.movies.seen.connect(self._videos_seen)
        self.movies.placed.connect(self.watch.add_seen)
        self.movies.folders_changed.connect(lambda: QTimer.singleShot(0, self.check_new_videos))
        self.tray.messageClicked.connect(self._open_new_videos)
        self.watch_timer = QTimer(self)
        self.watch_timer.timeout.connect(self.check_new_videos)
        self.watch_timer.start(WATCH_EVERY_MS)
        QTimer.singleShot(3000, self.check_new_videos)

    def check_new_videos(self) -> None:
        if self._watching:
            return
        folders = [f["path"] for f in self.media.movie_folders]
        self.watch.forget(folders)
        self._watching = True
        self.watch_bg.run(lambda: watch.scan(folders), self._scanned)

    def _scanned(self, found, error) -> None:  # type: ignore[no-untyped-def]
        self._watching = False
        if not found:
            return
        names = {f["path"]: f.get("label") or os.path.basename(f["path"]) for f in self.media.movie_folders}
        before = {k: len(v) for k, v in self.new_videos.items()}
        news: list[str] = []
        for folder, current in found.items():
            new = self.watch.new(folder, current)
            if new:
                self.new_videos[folder] = new
            else:
                self.new_videos.pop(folder, None)
            if len(new) > before.get(folder, 0):
                news.append(f"{names.get(folder, folder)}: {len(new)} new video{'s' if len(new) != 1 else ''}")
        if {k: len(v) for k, v in self.new_videos.items()} != before:
            self.fill()
        if news and self.tray.isVisible():
            self.tray.showMessage("New videos", "\n".join(news), QSystemTrayIcon.MessageIcon.Information, 10_000)

    def _videos_seen(self, folder: str, current: list) -> None:
        """A folder was opened in Movies & TV: everything in it has been seen."""
        self.watch.mark_seen(folder, current)
        if self.new_videos.pop(folder, None):
            self.fill()

    def _open_new_videos(self) -> None:
        """The "New videos" note was clicked: show the (first) folder with new videos."""
        self.show_from_tray()
        folder = next(iter(self.new_videos), None)
        item = self._item("movies", "movie:" + folder) if folder else None
        if item is not None:
            self.list.setCurrentItem(item)
            self._clicked(item)

    # ------------------------------------------------------------ the tray
    def _build_tray(self) -> None:
        """The icon by the clock: minimizing hides the window there (click the icon to bring it back)."""
        icon = QIcon(str(Path(__file__).resolve().parent / "assets" / "icon.png"))
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip("Media Manager")
        menu = QMenu(self)
        show = menu.addAction("Show Media Manager", self.show_from_tray)
        font = show.font()
        font.setBold(True)
        show.setFont(font)
        menu.addSeparator()
        self.tray_toggle = menu.addAction("Minimize to the tray")
        self.tray_toggle.setCheckable(True)
        self.tray_toggle.setChecked(self.media.minimize_to_tray)
        self.tray_toggle.toggled.connect(lambda on: setattr(self.media, "minimize_to_tray", on))
        menu.addSeparator()
        menu.addAction("Quit", self.quit_app)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._tray_clicked)
        self._was_maximized = False
        if QSystemTrayIcon.isSystemTrayAvailable():
            self.tray.show()

    def quit_app(self) -> None:
        """Quit, also while hidden in the tray (closing a hidden window doesn't end the app by itself)."""
        from PySide6.QtWidgets import QApplication

        if self.close():
            QApplication.instance().quit()

    def _tray_clicked(self, reason) -> None:  # type: ignore[no-untyped-def]
        if reason in (QSystemTrayIcon.ActivationReason.Trigger, QSystemTrayIcon.ActivationReason.DoubleClick):
            self.show_from_tray()

    def show_from_tray(self) -> None:
        if self._was_maximized:
            self.showMaximized()
        else:
            self.showNormal()
        self.raise_()
        self.activateWindow()

    def changeEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        super().changeEvent(event)
        if event.type() == QEvent.Type.WindowStateChange and self.isMinimized():
            self._was_maximized = bool(event.oldState() & Qt.WindowState.WindowMaximized)
            if self.media.minimize_to_tray and self.tray.isVisible():
                QTimer.singleShot(0, self.hide)  # off the taskbar; the tray icon brings it back

    def _write_companion(self) -> None:
        from . import companion

        companion.write(self.photos.settings, self.media)

    # ------------------------------------------------------------ closing
    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.media.window_geometry = bytes(self.saveGeometry().toBase64()).decode()
        self.media.window_state = bytes(self.saveState().toBase64()).decode()
        self._remember_widths()
        self._write_companion()
        self.watch_timer.stop()
        # Only reading (new videos, layouts, templates): don't wait for it to close (a template in OneDrive that
        # is still downloading kept 0.6.12 open, frozen, after its window was closed).
        for bg in (self.watch_bg, self.layouts.bg, self.templates_bg, self.templates.bg):
            bg.pool.clear()
            bg.shutdown(300)
        for part in (self.movies, self.music, self.photos):
            part.close()  # each saves its own settings and stops its work
        try:
            self.media.save()
        except OSError:
            pass
        self.tray.hide()
        super().closeEvent(event)
