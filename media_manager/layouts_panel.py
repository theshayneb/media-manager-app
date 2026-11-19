"""The Layouts panel: a tab with Photos' Details (click Layouts, it covers Details; click Details, it's back).
Each layout's picture, its pockets, and whether they're filled by:
- in the Project Life folder (or a folder in it): the group of the Photos grid that the selected picture is in
  (a subfolder like Week 1, a week, "No date taken"…), dated or not;
- anywhere else: the print copies in the Project Life folder from the selected photo's week (else this week).
Weeks are the scrapbook's (photo_manager.ui.grid.album_week). Above the list: the week's spread (layouts.Plan):
the left page (the back of last week's right page, locked) and the right page you choose (double-click a
layout, or right-click it)."""

from __future__ import annotations

import os
import time
from datetime import date

from PySide6.QtCore import QRectF, QSize, Qt, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from music_manager.ui.workers import Background
from photo_manager.ui.grid import album_week

from . import layouts

FIT_COLOUR, SHORT_COLOUR = "#7cc47c", "#d8a050"


_ICONS: dict[tuple[str, float], QIcon] = {}


def layout_icon(path: str) -> QIcon | None:
    """A layout's picture for the list (PSDs too), made once per version of the file."""
    try:
        key = (path, os.path.getmtime(path))
    except OSError:
        return None
    if key not in _ICONS:
        image = layouts.template_image(path, 192)
        if image is None:
            return None
        from photo_manager.ui.grid import pil_to_qimage

        _ICONS[key] = QIcon(QPixmap.fromImage(pil_to_qimage(image)))
    return _ICONS[key]


def pocket_picture(layout: layouts.Layout | None, mirrored: bool = False, w: int = 45, h: int = 60) -> QPixmap:
    """A small drawing of the layout's pockets (mirrored: the back of the sheet, as the next left page)."""
    pix = QPixmap(w, h)
    pix.fill(QColor("#f4f4f4"))
    p = QPainter(pix)
    p.setPen(QPen(QColor("#9aa0a8"), 1))
    p.drawRect(0, 0, w - 1, h - 1)
    if layout is None:
        p.drawText(QRectF(0, 0, w, h), Qt.AlignmentFlag.AlignCenter, "?")
    else:
        for pocket in layout.pockets:
            x = (1 - pocket.x - pocket.w) if mirrored else pocket.x
            r = QRectF(2 + x * (w - 4), 2 + pocket.y * (h - 4), pocket.w * (w - 4) - 2, pocket.h * (h - 4) - 2)
            p.fillRect(r, QColor("#ffffff"))
            p.drawRect(r)
            p.drawText(r, Qt.AlignmentFlag.AlignCenter, {"tall": "▯", "wide": "▭"}.get(pocket.shape, "□"))
    p.end()
    return pix


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
        self.album: tuple[int, int, date, date] | None = None  # the scrapbook week shown (year, number, …)

        # This week's spread: the left page (locked: the back of last week's right page) and the right page.
        self.spread = QFrame()
        self.spread.setFrameShape(QFrame.Shape.StyledPanel)
        grid = QGridLayout(self.spread)
        grid.setContentsMargins(6, 4, 6, 4)
        self.spread_title = QLabel("")
        grid.addWidget(self.spread_title, 0, 0, 1, 3)
        self.left_pic, self.left_text = QLabel(), QLabel("")
        self.right_pic, self.right_text = QLabel(), QLabel("")
        self.left_clear, self.right_clear = QToolButton(text="✕"), QToolButton(text="✕")
        for row, (pic, text, clear, side) in enumerate(((self.left_pic, self.left_text, self.left_clear, "left"),
                                                        (self.right_pic, self.right_text, self.right_clear,
                                                         "right")), start=1):
            text.setWordWrap(True)
            clear.setAutoRaise(True)
            clear.setToolTip(f"Clear this week's {side} page")
            clear.clicked.connect(lambda _c=False, s=side: self.choose(s, None))
            grid.addWidget(pic, row, 0)
            grid.addWidget(text, row, 1)
            grid.addWidget(clear, row, 2, Qt.AlignmentFlag.AlignTop)
        grid.setColumnStretch(1, 1)
        self.spread_verdict = QLabel("")
        self.spread_verdict.setWordWrap(True)
        grid.addWidget(self.spread_verdict, 3, 0, 1, 3)

        self.heading = QLabel("")
        self.heading.setWordWrap(True)
        self.only_fit = QCheckBox("Only layouts that fit")
        self.only_fit.toggled.connect(lambda _on: self._fill())
        self.list = QListWidget()
        self.list.setIconSize(QSize(72, 96))
        self.list.setSpacing(3)
        self.list.setWordWrap(True)
        self.list.itemDoubleClicked.connect(lambda item: self.choose("right", item.data(Qt.ItemDataRole.UserRole)))
        self.list.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list.customContextMenuRequested.connect(self._menu)
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
        layout.addWidget(self.spread)  # (no "Next…"/"Double-click…" wording: it took room, the user said)
        layout.addWidget(self.only_fit)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.note)
        buttons = QHBoxLayout()
        buttons.addWidget(folder_btn)
        buttons.addWidget(prints_btn)
        buttons.addWidget(again)
        layout.addLayout(buttons)

    # ---------------------------------------------------------------- which week
    def week_start(self) -> str:
        return getattr(self.photos.settings, "week_start", "sunday")

    def album_week(self, inside: bool) -> tuple[int, int, date, date] | None:
        """The scrapbook week of the selected picture (elsewhere than Project Life, else this week)."""
        path = self.photos.grid.current_path()
        item = self.photos.model.item(path) if path else None
        meta = getattr(item, "meta", None)
        if meta is not None and meta.date_taken is not None:
            return album_week(meta.date_taken.date(), self.week_start())
        return None if inside else album_week(date.today(), self.week_start())

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
        self.album = self.album_week(inside=group is not None)
        start, last = (self.album[2], self.album[3]) if self.album else (date.today(), date.today())
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
            return found, layouts.week_prints(prints, start, last)

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
            year, number, first, last = self.album or album_week(week.start, self.week_start())
            self.heading.setText(f"<b>Week {number}</b> · {first:%a, %b} {first.day} – {last:%b} {last.day}<br>"
                                 f"{total} print cop{'y' if total == 1 else 'ies'}: {counts}")
        left, right = self._spread()
        self.heading.setToolTip("\n".join(week.names) or "No print copies from this week yet")
        self.list.clear()
        for layout in self.layouts:
            fits, verdict = layouts.fit([left, layout] if left else layout, week)
            if left:
                verdict = "with the left page: " + verdict
            if self.only_fit.isChecked() and not fits:
                continue
            item = QListWidgetItem(f"{layout.name}\n{layout.summary()}\n{verdict}")
            icon = layout_icon(layout.path)
            if icon is not None:
                item.setIcon(icon)
            item.setForeground(QColor(FIT_COLOUR if fits else SHORT_COLOUR))
            item.setToolTip(layout.path + ("  (built in)" if layout.built_in else ""))
            item.setData(Qt.ItemDataRole.UserRole, layout.name)
            if layout is right:
                item.setText("✓ this week's right page\n" + item.text())
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

    # ---------------------------------------------------------------- the spread (page plan)
    def plan(self) -> layouts.Plan:
        return layouts.Plan(self.media.print_folder if os.path.isdir(self.media.print_folder) else "")

    def by_name(self, name: str | None) -> layouts.Layout | None:
        return next((lay for lay in self.layouts if lay.name == name), None) if name else None

    def _spread(self) -> tuple[layouts.Layout | None, layouts.Layout | None]:
        """Show this week's spread; returns its (left, right) layouts."""
        self.spread.setVisible(self.album is not None)
        if self.album is None:
            return None, None
        year, number, _first, _last = self.album
        plan = self.plan()
        left_name, locked = plan.left(year, number)
        right_name = plan.right(year, number)
        left, right = self.by_name(left_name), self.by_name(right_name)
        self.spread_title.setText(f"<b>Week {number}'s spread</b>" + ("  (the start of the album)" if number == 1
                                                                       else ""))
        self.left_pic.setPixmap(pocket_picture(left, mirrored=locked))
        if locked:
            self.left_text.setText(f"Left page 🔒 {left_name}\n(the back of Week {number - 1}'s right page)\n"
                                   + (left.summary() if left else "not in your layouts"))
        else:
            self.left_text.setText("Left page: " + (f"{left_name}\n{left.summary()}" if left else
                                                    "not chosen (right-click a layout)"))
        self.left_clear.setVisible(bool(left_name) and not locked)
        self.right_pic.setPixmap(pocket_picture(right))
        self.right_text.setText("Right page: " + (f"{right_name}\n{right.summary()}" if right else
                                                  "not chosen (double-click a layout)"))
        self.right_clear.setVisible(bool(right_name))
        pages = [p for p in (left, right) if p]
        if pages and self.week is not None:
            fits, verdict = layouts.fit(pages, self.week)
            have = self.week.tall + self.week.wide + self.week.square
            self.spread_verdict.setText(f"Spread needs {layouts.describe(layouts.needs(pages))} · "
                                        f"{verdict if have or fits else 'nothing yet'}")
            self.spread_verdict.setStyleSheet(f"color: {FIT_COLOUR if fits else SHORT_COLOUR};")
        else:
            self.spread_verdict.setText("")
        return left, right

    def choose(self, side: str, name: str | None) -> None:
        """Put a layout on this week's left or right page (None: clear it)."""
        if self.album is None:
            return
        try:
            self.plan().choose(self.album[0], self.album[1], side, name)
        except OSError as exc:
            QMessageBox.warning(self, "Layouts", f"Couldn't save the plan in the Project Life folder:\n{exc}")
            return
        self._fill()

    def _menu(self, pos) -> None:  # type: ignore[no-untyped-def]
        item = self.list.itemAt(pos)
        if item is None or self.album is None:
            return
        name, number = item.data(Qt.ItemDataRole.UserRole), self.album[1]
        _left, locked = self.plan().left(self.album[0], number)
        menu = QMenu(self)
        menu.addAction(f"Use for Week {number}'s right page", lambda: self.choose("right", name))
        if not locked:
            menu.addAction(f"Use for Week {number}'s left page", lambda: self.choose("left", name))
        menu.exec(self.list.viewport().mapToGlobal(pos))


class TemplatesPanel(QWidget):
    """Photo Templates: the cards and pages that go inside a pocket (the PSDs in Digital Templates that aren't
    Layouts), grouped by the size their names start with (3x4, 6x4, 3x8, 4x4, 6x8, 6x12…, Other). Click a
    heading to fold it; double-click (or Enter) opens a template in its program (Affinity). The shell fills it."""

    HEADING = Qt.ItemDataRole.UserRole + 1

    def __init__(self, media, parent: QWidget | None = None):  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self.media = media
        self.cache_dir = None  # the shell sets Photos' thumbnail cache folder
        self.bg = Background(2)
        self.groups: dict[str, list[layouts.Template]] = {}
        self._icons: dict[tuple[str, float], QIcon] = {}
        self.list = QListWidget()
        self.list.setIconSize(QSize(72, 96))
        self.list.setSpacing(3)
        self.list.setWordWrap(True)
        self.list.itemActivated.connect(self._open)
        self.list.itemClicked.connect(self._fold)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.addWidget(self.list, 1)
        layout.addWidget(self.note)

    def set_templates(self, groups: dict[str, list[layouts.Template]]) -> None:
        self.groups = groups
        self._fill()

    def _fill(self) -> None:
        top = self.list.verticalScrollBar().value()
        self.list.clear()
        folded = set(self.media.template_folded)
        for group, templates in self.groups.items():
            shut = group in folded
            head = QListWidgetItem(f"{'▸' if shut else '▾'}  {group} · {len(templates)}")
            head.setData(self.HEADING, group)
            head.setFlags(Qt.ItemFlag.ItemIsEnabled)
            font = head.font()
            font.setBold(True)
            head.setFont(font)
            head.setForeground(QColor("#9aa0a8"))
            self.list.addItem(head)
            if shut:
                continue
            for t in templates:
                item = QListWidgetItem(f"{t.name}\n{t.summary()}")
                item.setData(Qt.ItemDataRole.UserRole, t.path)
                item.setToolTip(t.path)
                self.list.addItem(item)
                self._icon(item, t.path)
        self.list.verticalScrollBar().setValue(top)
        self.note.setText("" if self.groups else "No templates in the Digital Templates folder yet (their names "
                          "start with the size, e.g. \"3x4 - …\").")
        self.note.setVisible(not self.groups)

    def _fold(self, item: QListWidgetItem) -> None:
        group = item.data(self.HEADING)
        if not group:
            return
        folded = list(self.media.template_folded)
        if group in folded:
            folded.remove(group)
        else:
            folded.append(group)
        self.media.template_folded = folded
        self._fill()

    def _icon(self, item: QListWidgetItem, path: str) -> None:
        try:
            key = (path, os.path.getmtime(path))
        except OSError:
            return
        if key in self._icons:
            item.setIcon(self._icons[key])
            return

        def make():  # type: ignore[no-untyped-def]
            from photo_manager.core.thumbs import thumbnail

            # Photos' thumbnail cache on disk: a template is read (and, online-only, downloaded) once.
            return thumbnail(path, 192, self.cache_dir) or layouts.template_image(path, 192)

        def done(image, _error) -> None:  # type: ignore[no-untyped-def]
            if image is None:
                return
            from photo_manager.ui.grid import pil_to_qimage

            icon = QIcon(QPixmap.fromImage(pil_to_qimage(image)))
            self._icons[key] = icon
            for row in range(self.list.count()):  # (the list may have been filled again meanwhile)
                if self.list.item(row).data(Qt.ItemDataRole.UserRole) == path:
                    self.list.item(row).setIcon(icon)

        self.bg.run(make, done)

    def _open(self, item: QListWidgetItem) -> None:
        if not item.data(Qt.ItemDataRole.UserRole):
            return
        QDesktopServices.openUrl(QUrl.fromLocalFile(item.data(Qt.ItemDataRole.UserRole)))
