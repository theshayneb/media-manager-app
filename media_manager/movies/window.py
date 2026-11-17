"""Movies & TV: the videos in a Movies or TV Shows folder, a player, and Plex-style renaming,
moving and deleting (subtitles and .nfo files go along)."""

from __future__ import annotations

import os
import subprocess
import sys

from PySide6.QtCore import QRect, Qt, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QDesktopServices, QGuiApplication, QImage, QKeySequence, QPainter
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QToolBar,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from music_manager.ui.model import fmt_time
from music_manager.ui.workers import Background

from ..settings import MediaSettings
from . import files
from .naming import plex_name

try:
    from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer, QVideoSink

    HAVE_VIDEO = True
except ImportError:  # pragma: no cover
    HAVE_VIDEO = False

KINDS = {"movies": "Movies", "tv": "TV Shows"}


def size_text(n: int) -> str:
    return f"{n / 1024 ** 3:.2f} GB" if n >= 1024 ** 3 else f"{n / 1024 ** 2:.0f} MB"


class VideoScreen(QWidget):
    """Draws the video frames itself, as Photo Manager's preview does. (Qt's QVideoWidget puts a separate
    native window inside the app, which on Windows stopped clicks and redraws in the rest of the window.)"""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.image = QImage()
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)

    def set_frame(self, image: QImage) -> None:
        self.image = image
        self.update()

    def clear(self) -> None:
        self.image = QImage()
        self.update()

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("black"))
        if self.image.isNull():
            return
        size = self.image.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        target = QRect(0, 0, size.width(), size.height())
        target.moveCenter(self.rect().center())
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.drawImage(target, self.image)


class PlanDialog(QDialog):
    def __init__(self, rows: list, parent: QWidget | None = None):
        super().__init__(parent)
        self.setWindowTitle("Rename for Plex")
        self.resize(900, 420)
        layout = QVBoxLayout(self)
        intro = QLabel("Movies become “Title (Year)”, episodes “Show - S01E02 - Title”. Subtitles and .nfo files "
                       "named like a video are renamed with it.")
        intro.setWordWrap(True)
        layout.addWidget(intro)
        table = QTableWidget(len(rows), 3)
        table.setHorizontalHeaderLabels(["Now", "Becomes", "Note"])
        table.verticalHeader().setVisible(False)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        for c, mode in enumerate((QHeaderView.ResizeMode.Stretch, QHeaderView.ResizeMode.Stretch,
                                  QHeaderView.ResizeMode.ResizeToContents)):
            table.horizontalHeader().setSectionResizeMode(c, mode)
        changes = 0
        for r, (video, dest, note) in enumerate(rows):
            table.setItem(r, 0, QTableWidgetItem(video.name))
            table.setItem(r, 1, QTableWidgetItem(os.path.basename(dest) if dest else "—"))
            table.setItem(r, 2, QTableWidgetItem(note))
            changes += bool(dest)
        layout.addWidget(table, 1)
        layout.addWidget(QLabel(f"{changes} of {len(rows)} will be renamed."))
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Rename")
        buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(changes > 0)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)


class MoviesWindow(QMainWindow):
    folders_changed = Signal()

    def __init__(self, settings: MediaSettings):
        super().__init__()
        self.settings = settings
        self.entry: dict = {}
        self.videos: list[files.Video] = []
        self.bg = Background(1)
        self._gen = 0
        self.playing = ""

        self.table = QTableWidget(0, 4)
        self.table.setHorizontalHeaderLabels(["Name", "Folder", "Size", "Plex name"])
        self.table.verticalHeader().setVisible(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setSortingEnabled(True)
        self.table.setAlternatingRowColors(True)
        self.table.setWordWrap(False)
        header = self.table.horizontalHeader()
        header.setSectionsMovable(True)
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        for col in (1, 2, 3):
            header.setSectionResizeMode(col, QHeaderView.ResizeMode.Interactive)
        header.resizeSection(1, 160)
        header.resizeSection(2, 80)
        header.resizeSection(3, 260)
        self.table.verticalHeader().setDefaultSectionSize(24)
        self.table.doubleClicked.connect(lambda _i: self.play_selected())
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._menu)

        right = QWidget()
        rv = QVBoxLayout(right)
        rv.setContentsMargins(0, 0, 0, 0)
        self.screen = VideoScreen() if HAVE_VIDEO else QLabel("Video playback isn't available")
        self.screen.setMinimumSize(320, 180)
        self.screen.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        rv.addWidget(self.screen, 1)
        controls = QHBoxLayout()
        self.play_btn = QToolButton(text="▶")
        self.play_btn.setAutoRaise(True)
        font = self.play_btn.font()
        font.setPointSizeF(font.pointSizeF() * 2)
        self.play_btn.setFont(font)
        self.play_btn.clicked.connect(self.toggle)
        self.pos = QLabel("0:00")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.sliderMoved.connect(lambda v: self.player.setPosition(v) if HAVE_VIDEO else None)
        self.length = QLabel("0:00")
        self.volume = QSlider(Qt.Orientation.Horizontal)
        self.volume.setRange(0, 100)
        self.volume.setValue(settings.movie_volume)
        self.volume.setFixedWidth(90)
        for w in (self.play_btn, self.pos):
            controls.addWidget(w)
        controls.addWidget(self.slider, 1)
        controls.addWidget(self.length)
        controls.addWidget(QLabel("🔊"))
        controls.addWidget(self.volume)
        rv.addLayout(controls)
        self.now = QLabel("")
        self.now.setStyleSheet("color: palette(placeholder-text);")
        rv.addWidget(self.now)

        split = QSplitter()
        split.addWidget(self.table)
        split.addWidget(right)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        self.setCentralWidget(split)
        self.status = QLabel("")
        self.statusBar().addWidget(self.status, 1)

        if HAVE_VIDEO:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.sink = QVideoSink(self)
            self.sink.videoFrameChanged.connect(self._frame)
            self.player.setVideoSink(self.sink)
            self.audio.setVolume((self.volume.value() / 100) ** 3)
            self.volume.valueChanged.connect(lambda v: self.audio.setVolume((v / 100) ** 3))
            self.player.positionChanged.connect(self._position)
            self.player.durationChanged.connect(lambda ms: (self.slider.setRange(0, ms),
                                                            self.length.setText(fmt_time(ms / 1000))))
            self.player.playbackStateChanged.connect(
                lambda s: self.play_btn.setText("⏸" if s == QMediaPlayer.PlaybackState.PlayingState else "▶"))
        self._build_toolbar()

    # ------------------------------------------------------------ toolbar
    def _build_toolbar(self) -> None:
        bar = QToolBar("Movies")
        bar.setMovable(False)
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
        self.addToolBar(bar)

        def act(text: str, slot, keys: str | None = None, tip: str = "") -> QAction:  # type: ignore[no-untyped-def]
            a = QAction(text, self)
            a.triggered.connect(lambda _=False: slot())
            if keys:
                a.setShortcut(QKeySequence(keys))
                a.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
            a.setToolTip(f"{tip or text}{f' ({keys})' if keys else ''}")
            self.addAction(a)
            bar.addAction(a)
            return a

        from ..bars import GEAR, FolderButton, flatten, label_as, menu_button, shared_icons

        play = act("Play", self.play_selected, "Return")
        act("Rename for Plex", self.rename_plex, None,
            "“Title (Year)” for movies, “Show - S01E02 - Title” for episodes")
        bar.addSeparator()
        rename = act("Rename", self.rename_one, "F2", "Rename one video")
        move = act("Move to", self.move_selected, "Ctrl+M")
        delete = act("Delete", self.delete_selected, "Delete", "Send to the Recycle Bin (with its subtitles)")
        explorer = act("Show in Explorer", self.show_in_explorer, "Ctrl+E")
        bar.addSeparator()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search…")
        self.search.setClearButtonEnabled(True)
        self.search.setMaximumWidth(260)
        self.search.textChanged.connect(self._filter)
        bar.addWidget(self.search)
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        menu = QMenu(self)
        menu.addAction("Add a Movies folder to the Folders list…", lambda: self.add_folder("movies"))
        menu.addAction("Add a TV Shows folder to the Folders list…", lambda: self.add_folder("tv"))
        menu.addSeparator()
        menu.addAction("Show this folder in Explorer", self.show_folder_in_explorer)
        self.where = FolderButton(menu)
        bar.addWidget(self.where)
        refresh = act("Refresh", self.reload, "F5")
        shared_icons(rename, move, delete, explorer, refresh)
        label_as(play, "Play")
        gear_menu = QMenu(self)
        gear_menu.addAction("Remove this folder from the Folders list",
                            lambda: self.remove_folder(self.entry.get("path", "")) if self.entry else None)
        bar.addWidget(menu_button(GEAR, gear_menu, "Settings: folder options"))
        flatten(bar)

    # ------------------------------------------------------------ folders
    def add_folder(self, kind: str) -> None:
        folder = QFileDialog.getExistingDirectory(self, f"Add a {KINDS[kind]} folder")
        if not folder:
            return
        folder = os.path.normpath(folder)
        if not any(os.path.normcase(f["path"]) == os.path.normcase(folder) for f in self.settings.movie_folders):
            label = os.path.basename(folder) or folder
            self.settings.movie_folders.append({"path": folder, "label": label, "kind": kind})
            self.settings.save()
        self.folders_changed.emit()

    def remove_folder(self, path: str) -> None:
        self.settings.movie_folders = [f for f in self.settings.movie_folders
                                       if os.path.normcase(f["path"]) != os.path.normcase(path)]
        self.settings.save()
        self.folders_changed.emit()

    def open_entry(self, entry: dict) -> None:
        self.entry = entry
        self.where.set_path(entry.get("path", ""))
        self.reload()

    def reload(self) -> None:
        folder = self.entry.get("path", "")
        self._gen += 1
        gen = self._gen
        self.table.setRowCount(0)
        if not folder:
            self.status.setText("Add a Movies or TV Shows folder with 📁 Add Folder.")
            return
        if not os.path.isdir(folder):
            self.status.setText(f"Can't open {folder} (is the drive connected?)")
            return
        self.status.setText(f"Reading {folder}…")

        def done(videos, error) -> None:  # type: ignore[no-untyped-def]
            if gen != self._gen:
                return
            self.videos = videos or []
            self._fill()
            self.status.setText(error or f"{len(self.videos)} videos")

        self.bg.run(lambda: files.list_videos(folder), done)

    def _fill(self) -> None:
        kind = self.entry.get("kind", "movies")
        base = self.entry.get("path", "")
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(self.videos))
        for r, v in enumerate(self.videos):
            name = QTableWidgetItem(v.name)
            name.setData(Qt.ItemDataRole.UserRole, v.path)
            name.setToolTip(v.path)
            rel = os.path.relpath(v.folder, base) if base else v.folder
            size = QTableWidgetItem(size_text(v.size))
            size.setData(Qt.ItemDataRole.UserRole + 1, v.size)
            size.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            plex = plex_name(v.name, kind)
            plex_item = QTableWidgetItem("✓ already" if plex == v.name else (plex or "—"))
            for c, item in enumerate((name, QTableWidgetItem("" if rel == "." else rel), size, plex_item)):
                self.table.setItem(r, c, item)
        self.table.setSortingEnabled(True)
        self._filter(self.search.text())

    def _filter(self, text: str) -> None:
        words = text.casefold().split()
        for r in range(self.table.rowCount()):
            name = self.table.item(r, 0).text().casefold() + " " + self.table.item(r, 1).text().casefold()
            self.table.setRowHidden(r, not all(w in name for w in words))

    def selected_paths(self) -> list[str]:
        rows = sorted({i.row() for i in self.table.selectionModel().selectedRows()})
        return [self.table.item(r, 0).data(Qt.ItemDataRole.UserRole) for r in rows]

    # ------------------------------------------------------------ playing
    def play_selected(self) -> None:
        paths = self.selected_paths()
        if paths and HAVE_VIDEO:
            self.playing = paths[0]
            self.now.setText(os.path.basename(paths[0]))
            self.player.setSource(QUrl.fromLocalFile(paths[0]))
            self.player.play()

    def _frame(self, frame) -> None:  # type: ignore[no-untyped-def]
        if self.playing and frame.isValid():
            self.screen.set_frame(frame.toImage())

    def toggle(self) -> None:
        if not HAVE_VIDEO:
            return
        if not self.playing:
            self.play_selected()
        elif self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def _position(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)
        self.pos.setText(fmt_time(ms / 1000))

    def _release(self, paths: list[str]) -> None:
        if HAVE_VIDEO and self.playing and any(os.path.normcase(p) == os.path.normcase(self.playing) for p in paths):
            self.player.stop()
            self.player.setSource(QUrl())
            self.playing = ""
            self.now.setText("")
            self.screen.clear()

    def stop(self) -> None:
        if HAVE_VIDEO:
            self.player.stop()

    # ------------------------------------------------------------ files
    def _report(self, verb: str, count: int, failures) -> None:  # type: ignore[no-untyped-def]
        if failures:
            QMessageBox.warning(self, "Some videos couldn't be changed",
                                "\n".join(f"• {os.path.basename(p)}: {e}" for p, e in failures[:12]))
        self.status.setText(f"{verb} {count} video{'s' if count != 1 else ''}.")
        self.reload()

    def rename_plex(self) -> None:
        paths = set(self.selected_paths())
        videos = [v for v in self.videos if v.path in paths] or self.videos
        rows = files.rename_plan(videos, self.entry.get("kind", "movies"))
        if PlanDialog(rows, self).exec() != QDialog.DialogCode.Accepted:
            return
        plan = {v.path: dest for v, dest, _n in rows if dest}
        self._release(list(plan))
        self.bg.run(lambda: files.rename(plan), lambda res, err: self._report("Renamed", len((res or ({}, []))[0]),
                                                                          (res or ({}, []))[1]))

    def rename_one(self) -> None:
        paths = self.selected_paths()
        if len(paths) != 1:
            return
        from music_manager.core.fileops import check_new_name
        from music_manager.ui.dialogs import ask_text

        old = os.path.basename(paths[0])
        name = ask_text(self, "Rename", "New name:", old)
        if not name or name == old:
            return
        problem = check_new_name(paths[0], name)
        if problem:
            QMessageBox.warning(self, "Rename", problem)
            return
        plan = {paths[0]: os.path.join(os.path.dirname(paths[0]), name.strip())}
        self._release(list(plan))
        self.bg.run(lambda: files.rename(plan), lambda res, err: self._report("Renamed", len((res or ({}, []))[0]),
                                                                          (res or ({}, []))[1]))

    def move_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        folder = QFileDialog.getExistingDirectory(self, "Move to", self.entry.get("path", ""))
        if not folder:
            return
        self._release(paths)
        self.bg.run(lambda: files.move(paths, folder),
                    lambda res, err: self._report("Moved", len((res or ({}, []))[0]), (res or ({}, []))[1]))

    def delete_selected(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        what = os.path.basename(paths[0]) if len(paths) == 1 else f"these {len(paths)} videos"
        if QMessageBox.question(self, "Delete", f"Send {what} (and its subtitles) to the Recycle Bin?") \
                != QMessageBox.StandardButton.Yes:
            return
        self._release(paths)
        self.bg.run(lambda: files.recycle(paths),
                    lambda res, err: self._report("Deleted", len(paths) - len(res or []), res or []))

    def show_folder_in_explorer(self) -> None:
        folder = self.entry.get("path", "")
        if folder and os.path.isdir(folder) and sys.platform == "win32":
            os.startfile(folder)  # type: ignore[attr-defined]

    def show_in_explorer(self) -> None:
        paths = self.selected_paths()
        if not paths:
            return
        if sys.platform == "win32":
            subprocess.Popen(["explorer", "/select,", os.path.normpath(paths[0])])
        else:
            QDesktopServices.openUrl(QUrl.fromLocalFile(os.path.dirname(paths[0])))

    def _menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        paths = self.selected_paths()
        if not paths:
            return
        menu = QMenu(self)
        menu.addAction("▶ Play", self.play_selected)
        menu.addAction("Rename for Plex…", self.rename_plex)
        if len(paths) == 1:
            menu.addAction("Rename… (F2)", self.rename_one)
        menu.addAction("Move to…", self.move_selected)
        menu.addAction("🗑 Delete", self.delete_selected)
        menu.addSeparator()
        menu.addAction("Show in Explorer", self.show_in_explorer)
        menu.addAction("Copy path", lambda: QGuiApplication.clipboard().setText("\n".join(paths)))
        menu.exec(self.table.viewport().mapToGlobal(pos))

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.stop()
        self.settings.movie_volume = self.volume.value()
        self.bg.shutdown()
        super().closeEvent(event)
