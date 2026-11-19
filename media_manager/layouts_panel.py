"""The Layouts panel: a tab with Photos' Details (click Layouts, it covers Details; click Details, it's back).
Each layout's picture, its pockets, and whether they're filled by:
- in the Project Life folder (or a folder in it): the group of the Photos grid that the selected picture is in
  (a subfolder like Week 1, a week, "No date taken"…), dated or not;
- anywhere else: the print copies in the Project Life folder from the selected photo's week (else this week)."""

from __future__ import annotations

import os
import time
from datetime import date

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from music_manager.ui.workers import Background

from . import layouts

FIT_COLOUR, SHORT_COLOUR = "#7cc47c", "#d8a050"


class LayoutsPanel(QWidget):
    def __init__(self, media, photos, parent: QWidget | None = None):  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.media, self.photos = media, photos
        self.bg = Background(1)
        self.layouts: list[layouts.Layout] = []
        self.week: layouts.Week | None = None
        self._loaded_from: str | None = None
        self._scanned: tuple[object, float] | None = None
        self._busy = False

        self.heading = QLabel("")
        self.heading.setWordWrap(True)
        self.only_fit = QCheckBox("Only layouts that fit")
        self.only_fit.toggled.connect(lambda _on: self._fill())
        self.list = QListWidget()
        self.list.setIconSize(QSize(72, 96))
        self.list.setSpacing(3)
        self.list.setWordWrap(True)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        folder_btn = QPushButton("📂 Layouts folder")
        folder_btn.setToolTip("Open the Digital Templates folder (add a picture of a layout there)")
        folder_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.media.layouts_folder)))
        prints_btn = QPushButton("📂 Print copies")
        prints_btn.setToolTip("Open the Project Life folder (where Print size saves)")
        prints_btn.clicked.connect(lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(self.media.print_folder)))
        again = QPushButton("↻")
        again.setToolTip("Look again (layouts and print copies)")
        again.setFixedWidth(34)
        again.clicked.connect(lambda: self.refresh(force=True, layouts_too=True))

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.heading)
        layout.addWidget(self.only_fit)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.note)
        buttons = QHBoxLayout()
        buttons.addWidget(folder_btn)
        buttons.addWidget(prints_btn)
        buttons.addWidget(again)
        layout.addLayout(buttons)

    # ---------------------------------------------------------------- which week
    def week_start_day(self) -> date:
        day = date.today()
        path = self.photos.grid.current_path()
        item = self.photos.model.item(path) if path else None
        meta = getattr(item, "meta", None)
        if meta is not None and meta.date_taken is not None:
            day = meta.date_taken.date()
        return layouts.week_of(day, getattr(self.photos.settings, "week_start", "sunday"))

    def selected_group(self) -> tuple[str, list[str]] | None:
        """In the Project Life folder: (title, pictures) of the grid group the selected picture is in (the whole
        folder when it isn't grouped). Elsewhere None (the week's print copies count instead)."""
        model = self.photos.model
        folder = getattr(model, "folder", "")
        if not layouts.is_inside(folder, self.media.print_folder):
            return None
        pictures = [i for i in model.items if i.kind == "image"]
        path = self.photos.grid.current_path()
        item = model.item(path) if path else None
        title = item.extra.get("group") if item is not None and model.grouped else None
        if title is None:
            return os.path.basename(folder), [i.path for i in pictures]
        return title, [i.path for i in pictures if i.extra.get("group") == title]

    def refresh(self, force: bool = False, layouts_too: bool = False) -> None:
        """Look at the week's print copies (and read the layouts the first time, or when asked)."""
        if self._busy:
            return
        group = self.selected_group()
        start = self.week_start_day() if group is None else None
        what: object = start if group is None else (group[0], tuple(group[1]))
        recent = self._scanned and self._scanned[0] == what and time.time() - self._scanned[1] < 15
        reload_layouts = layouts_too or self._loaded_from != self.media.layouts_folder
        if recent and not force and not reload_layouts:
            return
        self._busy = True
        prints, templates = self.media.print_folder, self.media.layouts_folder

        def work():  # type: ignore[no-untyped-def]
            found = layouts.load_layouts(templates) if reload_layouts else None
            if group is not None:
                return found, layouts.group_prints(group[1], group[0])
            return found, layouts.week_prints(prints, start)

        def done(result, error) -> None:  # type: ignore[no-untyped-def]
            self._busy = False
            if error or result is None:
                self.note.setText(f"Couldn't read: {error}")
                return
            found, week = result
            if found is not None:
                self.layouts, self._loaded_from = found, templates
            self.week, self._scanned = week, (what, time.time())
            self._fill()

        self.bg.run(work, done)

    # ---------------------------------------------------------------- showing it
    def _fill(self) -> None:
        week = self.week
        if week is None:
            return
        total = week.tall + week.wide + week.square
        counts = f"{week.tall} tall, {week.wide} wide" + (f", {week.square} square" if week.square else "")
        if week.start is None:  # a group of the grid, in the Project Life folder
            self.heading.setText(f"<b>{week.title}</b><br>{total} picture{'' if total == 1 else 's'}: {counts}")
        else:
            last = date.fromordinal(week.start.toordinal() + 6)
            self.heading.setText(f"<b>Week of {week.start:%a, %b} {week.start.day}</b> – {last:%b} {last.day}<br>"
                                 f"{total} print cop{'y' if total == 1 else 'ies'}: {counts}")
        self.heading.setToolTip("\n".join(week.names) or "No print copies from this week yet")
        self.list.clear()
        for layout in self.layouts:
            fits, verdict = layouts.fit(layout, week)
            if self.only_fit.isChecked() and not fits:
                continue
            item = QListWidgetItem(f"{layout.name}\n{layout.summary()}\n{verdict}")
            pixmap = QPixmap(layout.path)
            if not pixmap.isNull():
                item.setIcon(QIcon(pixmap.scaled(144, 192, Qt.AspectRatioMode.KeepAspectRatio,
                                                 Qt.TransformationMode.SmoothTransformation)))
            item.setForeground(QColor(FIT_COLOUR if fits else SHORT_COLOUR))
            item.setToolTip(layout.path + ("  (built in)" if layout.built_in else ""))
            self.list.addItem(item)
        notes = []
        if not os.path.isdir(self.media.layouts_folder):
            notes.append(f"Layouts folder not found: {self.media.layouts_folder}")
        if not os.path.isdir(self.media.print_folder):
            notes.append(f"Print copies folder not found: {self.media.print_folder}")
        elif week.undated and week.start is not None:
            notes.append(f"{week.undated} print cop{'y has' if week.undated == 1 else 'ies have'} no date taken "
                         "(not counted)")
        self.note.setText("\n".join(notes))
        self.note.setVisible(bool(notes))
