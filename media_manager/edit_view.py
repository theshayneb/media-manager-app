"""The Edit view (the user's "Option A and C"): the photo with a line down it (original on the left,
the edit on the right; drag the line) and "Hold for Before" (or the space bar) to see the whole original.
Shown in Photos' photo area like the big preview, with its sliders in a side panel (see edit_mode)."""

from __future__ import annotations

import os

from PIL import Image
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMenu,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSlider,
    QStackedWidget,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from photo_manager.core.crop import ASPECT_RATIOS, can_crop, upright_size
from photo_manager.core.thumbs import open_image
from photo_manager.ui.preview import CropCanvas

from . import print_size
from .photo_edit import SATURATION, SAVED_AS_JPG, Adjustments, Turn, apply, auto, white_balance_at
from .scrub import make_scrubbable
from .zoom import Zoom, notches

PREVIEW_PIXELS = 2400  # sharp enough for a maximized window
# (attribute, name, left end, right end, groove colours left -> right)
SLIDERS = [
    ("yellow", "Blue ↔ Yellow", "Bluer", "Yellower", ("#3b78d8", "#777777", "#d8b83b")),
    ("red", "Green ↔ Red", "Greener", "Redder", ("#3bb85a", "#777777", "#d84a3b")),
    ("brightness", "Brightness", "Darker", "Brighter", ("#222222", "#dddddd")),
    ("contrast", "Contrast", "Less", "More", ("#555555", "#999999")),
    ("shadows", "Shadows", "Darker", "Lighter", ("#111111", "#888888")),
    ("highlights", "Highlights", "Darker", "Brighter", ("#666666", "#eeeeee")),
]
DETAIL = [
    ("sharpness", "Sharpness", "None", "More", ("#555555", "#bbbbbb")),
    ("clarity", "Clarity", "Softer", "More punch", ("#666666", "#cccccc")),
]


def to_qimage(image: Image.Image) -> QImage:
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    return QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()


SAT_COLOURS = ["#e04040", "#f08a30", "#e8d040", "#40b050", "#30c0c0", "#3b78d8", "#9050d0", "#e050a0"]


def _heading(text: str, note: str = "") -> QLabel:
    label = QLabel(f"<b>{text}</b>" + (f" <span style='font-weight:normal'>{note}</span>" if note else ""))
    label.setStyleSheet("color: #9aa0a8; font-size: 11px; letter-spacing: 0.5px; padding-top: 8px;")
    return label


class CompareView(QWidget):
    """The original left of the line, the edit right of it. Press anywhere and drag to move the line.
    While picking white, a click reports the spot instead (picked)."""

    picked = Signal(float, float)  # where, as fractions of the picture's width and height

    def __init__(self, before: QImage, parent: QWidget | None = None):
        super().__init__(parent)
        self.before, self.after = before, before
        self.split = 0.0          # where the line is, across the picture: starts at the left (all After)
        self.picking = False
        self.zoom = Zoom()        # mouse wheel; while zoomed in, drag (away from the line) to look around
        self._moving_line = False
        self.whole_before = False  # "Hold for Before"
        self.setMinimumSize(360, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def set_after(self, image: QImage) -> None:
        self.after = image
        self.update()

    def fitted_rect(self) -> QRectF:
        size = self.before.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRectF(0, 0, size.width(), size.height())
        rect.moveCenter(QRectF(self.rect()).center())
        return rect

    def picture_rect(self) -> QRectF:
        return self.zoom.rect(self.fitted_rect(), QRectF(self.rect()))

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self.zoom.wheel(notches(event), event.position(), self.fitted_rect(), QRectF(self.rect())):
            self.update()
        event.accept()

    def _line_x(self) -> float:
        rect = self.picture_rect()
        return max(rect.left() + 1, rect.left() + rect.width() * self.split)

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1b1c1f"))
        rect = self.picture_rect()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        seen = rect.intersected(QRectF(self.rect()))  # the part on screen (all of it unless zoomed in)
        if self.whole_before:
            p.drawImage(rect, self.before)
            self._caption(p, seen, "Before", left=True)
            return
        p.drawImage(rect, self.after)
        x = rect.left() + rect.width() * self.split
        if self.split > 0:
            p.save()
            p.setClipRect(QRectF(rect.left(), rect.top(), x - rect.left(), rect.height()))
            p.drawImage(rect, self.before)
            p.restore()
            if x > seen.left() + 60:
                self._caption(p, seen, "Before", left=True)
        if self.split < 1:
            self._caption(p, seen, "After", left=False)
        if self.split < 1 and seen.left() - 1 <= x <= seen.right() + 1:  # the line, also at the very left
            x = max(x, rect.left() + 1)
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(QPointF(x, seen.top()), QPointF(x, seen.bottom()))
            p.setBrush(QColor("white"))
            p.setPen(Qt.PenStyle.NoPen)
            hx = min(max(x, seen.left() + 14), seen.right() - 14)  # the handle stays whole at the edges
            p.drawEllipse(QPointF(hx, seen.center().y()), 13, 13)
            p.setPen(QColor("#222222"))
            p.drawText(QRectF(hx - 13, seen.center().y() - 13, 26, 26), Qt.AlignmentFlag.AlignCenter, "⇔")

    def _caption(self, p: QPainter, rect: QRectF, text: str, left: bool) -> None:
        font = QFont(self.font())
        font.setPointSizeF(font.pointSizeF() * 0.9)
        p.setFont(font)
        width = p.fontMetrics().horizontalAdvance(text) + 12
        box = QRect(int(rect.left() + 8) if left else int(rect.right() - 8 - width), int(rect.top() + 8), width, 20)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 160))
        p.drawRoundedRect(box, 3, 3)
        p.setPen(QColor("white"))
        p.drawText(box, Qt.AlignmentFlag.AlignCenter, text)

    def _move_line(self, x: float) -> None:
        rect = self.picture_rect()
        if rect.width() > 0:
            self.split = max(0.0, min(1.0, (x - rect.left()) / rect.width()))
            self.update()

    def set_picking(self, on: bool) -> None:
        self.picking = on
        self.setCursor(Qt.CursorShape.CrossCursor if on else Qt.CursorShape.SplitHCursor)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self.picking:
            rect = self.picture_rect()
            pos = event.position()
            if rect.contains(pos):
                self.picked.emit((pos.x() - rect.left()) / rect.width(), (pos.y() - rect.top()) / rect.height())
            return
        x = event.position().x()
        if self.zoom.zoomed and abs(x - self._line_x()) > 14:  # zoomed in, away from the line: look around
            self.zoom.start_pan(event.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            return
        self._moving_line = True
        self._move_line(x)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if not event.buttons() & Qt.MouseButton.LeftButton or self.picking:
            return
        if self.zoom.panning:
            self.zoom.pan(event.position(), self.fitted_rect(), QRectF(self.rect()))
            self.update()
        elif self._moving_line:
            self._move_line(event.position().x())

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self.zoom.panning:
            self.zoom.end_pan()
            self.set_picking(self.picking)  # back to its usual pointer
        self._moving_line = False


class EditView(QWidget):
    """The photo being edited, with Hold for Before · Reset · Cancel · Save under it. Shown in Photos'
    photo area; its sliders (self.panel) go in a side panel in the Folders panel's place (see edit_mode)."""

    finished = Signal(str)   # "save" or "cancel"
    navigate = Signal(int)   # ← / →: the previous / next photo
    crop_requested = Signal(str, tuple, bool)  # path, box (upright pixels of the full photo), as a copy
    print_requested = Signal(str, tuple, str, bool, str)  # path, box (as shown, full size), size, border, week

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.path = ""
        self.original = Image.new("RGB", (1, 1))
        self.view = CompareView(to_qimage(self.original))
        self.values: dict[str, QSlider] = {}
        self.numbers: dict[str, QLabel] = {}
        self.resets: dict[str, QToolButton] = {}
        self.checks: dict[str, QCheckBox] = {}
        self.parts: dict[str, list[QWidget]] = {}  # each slider's widgets, greyed out when it's unticked
        self._last: dict | None = None
        self._result = 0

        sliders = QWidget()
        sv = QVBoxLayout(sliders)
        sv.setContentsMargins(0, 0, 8, 0)
        self.pick_btn = QPushButton("Pick white")
        self.pick_btn.setCheckable(True)
        self.pick_btn.setAutoDefault(False)
        self.pick_btn.setToolTip("White balance: then click something in the photo that should be white or grey "
                                 "(a wall, a shirt, clouds). Sets Blue ↔ Yellow and Green ↔ Red.")
        self.pick_btn.toggled.connect(self._picking)
        self.same_btn = QPushButton("Same as last edit")
        self.same_btn.setAutoDefault(False)
        self.same_btn.setToolTip("Set every slider the way you saved the previous photo")
        self.same_btn.clicked.connect(self.same_as_last)
        self.same_btn.setEnabled(False)
        self.view.picked.connect(self._picked)

        for heading, rows in (("LIGHT & COLOUR", SLIDERS), ("DETAIL", DETAIL)):
            sv.addWidget(_heading(heading))
            self._big_rows(sv, rows)
        buttons = QHBoxLayout()  # between the adjustments and the colours (the user's layout)
        buttons.addWidget(self.pick_btn)
        buttons.addWidget(self.same_btn)
        sv.addLayout(buttons)
        self.pick_hint = QLabel("Click something white or grey in the photo")
        self.pick_hint.setStyleSheet("color: #e0a040; font-size: 11px;")
        self.pick_hint.setVisible(False)
        sv.addWidget(self.pick_hint)

        sv.addWidget(_heading("SATURATION", "(less colour ← → more colour)"))
        rows = [("sat_all", "All colours", "#c8c8c8")] + [
            (key, name, colour) for (key, name, _h, _r), colour in zip(SATURATION, SAT_COLOURS, strict=True)]
        grid = QGridLayout()
        grid.setHorizontalSpacing(4)
        grid.setVerticalSpacing(6)
        for row, (key, name, colour) in enumerate(rows):
            check = self._check(key, f"{name} saturation")
            title, number = QLabel(name), self._number()
            title.setMinimumWidth(70)
            slider = self._slider(key, f"{name} saturation", ("#777777", colour))
            reset = self._reset(key, f"{name} saturation", slider)
            for col, w in enumerate((check, title, slider, number, reset)):
                grid.addWidget(w, row, col)
            self.values[key], self.numbers[key], self.resets[key] = slider, number, reset
            self.parts[key] = [title, number, slider, reset]
        grid.setColumnStretch(2, 1)
        sv.addLayout(grid)
        sv.addStretch(1)

        self.panel = QScrollArea()  # the sliders: edit_mode puts them in a side panel
        self.panel.setWidget(sliders)
        self.panel.setWidgetResizable(True)
        self.panel.setFrameShape(QFrame.Shape.NoFrame)
        self.panel.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.panel.setMinimumWidth(330)

        foot = QHBoxLayout()
        self.info = QLabel("")
        self.info.setStyleSheet("color: palette(placeholder-text);")
        foot.addWidget(self.info, 1)
        self.before_btn = QPushButton("Hold for Before")
        self.before_btn.setToolTip("Hold to see the whole original (or hold the space bar)")
        self.before_btn.setAutoDefault(False)
        self.before_btn.pressed.connect(lambda: self._show_before(True))
        self.before_btn.released.connect(lambda: self._show_before(False))
        reset = QPushButton("Reset")
        reset.setAutoDefault(False)
        reset.clicked.connect(self.reset)
        cancel = QPushButton("Cancel")
        cancel.setAutoDefault(False)
        cancel.setToolTip("Leave without saving (Shift+E asks first if you changed anything)")
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Save")
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.accept)
        for b in (self.before_btn, reset, cancel, self.save_btn):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # the keys (space, ←/→) stay with the photo
            foot.addWidget(b)

        # Crop, as it was in the big preview: a Crop (C) button over the photo, and its bar while cropping.
        top = QHBoxLayout()
        self.caption = QLabel("")
        top.addWidget(self.caption, 1)
        self.crop_btn = QPushButton("Crop (C)")
        self.crop_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.crop_btn.clicked.connect(self.start_crop)
        top.addWidget(self.crop_btn)
        # Flip and rotate, right of Crop: part of the edit (shown now, saved with Save).
        self.turn = Turn()
        self.flip_btn = QPushButton("⇋ Flip ▾")
        self.flip_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        flip_menu = QMenu(self.flip_btn)
        flip_menu.addAction("Flip horizontal (H)", lambda: self.flip(False))
        flip_menu.addAction("Flip vertical (V)", lambda: self.flip(True))
        self.flip_btn.setMenu(flip_menu)
        self.flip_btn.setStyleSheet("QPushButton::menu-indicator { width: 0; }")
        top.addWidget(self.flip_btn)
        self.rotate_btn = QPushButton("↻ Rotate (R)")
        self.rotate_btn.setToolTip("Turn the photo 90° clockwise")
        self.rotate_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.rotate_btn.clicked.connect(self.rotate)
        top.addWidget(self.rotate_btn)
        # Print size: a scrapbook print copy (the user's Affinity presets + border macros).
        self.print_btn = QPushButton("🖨 Print size (P)")
        self.print_btn.setToolTip("Save a print copy at an exact size (600 DPI), with or without a white border")
        self.print_btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.print_btn.clicked.connect(self.start_print)
        top.addWidget(self.print_btn)
        self.crop_bar = QWidget()
        bar = QHBoxLayout(self.crop_bar)
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(QLabel("Aspect ratio:"))
        self.ratio = QComboBox()
        self.ratio.addItems(list(ASPECT_RATIOS))
        self.ratio.currentTextChanged.connect(lambda _t: self.cropper.set_ratio(self._ratio_value()))
        bar.addWidget(self.ratio)
        self.as_copy = QCheckBox("Save as a copy")
        self.as_copy.setToolTip("Unticked: the cropped photo replaces the original, "
                                "and the original goes to the Recycle Bin.")
        self.as_copy.toggled.connect(lambda on: setattr(self.crop_settings, "crop_as_copy", on)
                                     if self.crop_settings is not None else None)
        bar.addWidget(self.as_copy)
        bar.addStretch(1)
        bar.addWidget(QLabel("Drag to draw · drag edges/corners to adjust"))
        apply_btn = QPushButton("Save crop (Enter)")
        apply_btn.clicked.connect(self.apply_crop)
        cancel_crop = QPushButton("Cancel")
        cancel_crop.clicked.connect(self.cancel_crop)
        for b in (apply_btn, cancel_crop):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            bar.addWidget(b)
        self.crop_bar.setVisible(False)
        self.print_bar = QWidget()
        pbar = QHBoxLayout(self.print_bar)
        pbar.setContentsMargins(0, 0, 0, 0)
        self.print_size = QComboBox()
        for size in print_size.SIZES:
            self.print_size.addItem(f"{size.name} ({size.shape})", size.name)
        self.print_size.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.print_border = QCheckBox("White border")
        self.print_border.setChecked(True)
        self.print_border.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.print_info = QLabel("")
        self.print_info.setStyleSheet("color: palette(placeholder-text);")
        self.print_week = QComboBox()  # the scrapbook week it's for ("2026-46"); edit_mode fills it
        self.print_week.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.print_week.setMinimumContentsLength(34)  # "Week 46 · Nov 15–21  (the photo's week)"
        self.print_week.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.print_week.setToolTip("The week of the scrapbook this print is for: the print copy gets a date taken "
                                   "in that week (cards without a date too)")
        for w in (QLabel("Size:"), self.print_size, self.print_border, QLabel("  Week:"), self.print_week,
                  self.print_info):
            pbar.addWidget(w)
        self.fill_weeks = None  # edit_mode: fills print_week for this photo
        pbar.addStretch(1)
        save_print = QPushButton("Save print copy (Enter)")
        save_print.clicked.connect(self.apply_print)
        cancel_print = QPushButton("Cancel")
        cancel_print.clicked.connect(self.cancel_crop)
        for b in (save_print, cancel_print):
            b.setFocusPolicy(Qt.FocusPolicy.NoFocus)
            pbar.addWidget(b)
        self.print_bar.setVisible(False)
        self.print_size.currentIndexChanged.connect(lambda _i: self._print_shape())
        self.print_border.toggled.connect(lambda _on: self._print_shape())
        self.printing = False
        self.crop_settings = None  # Photo Manager's settings (remembers "Save as a copy"); set by edit_mode
        self.cropper = CropCanvas()
        self.pages = QStackedWidget()
        self.pages.addWidget(self.view)
        self.pages.addWidget(self.cropper)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 4, 6, 6)
        layout.addLayout(top)
        layout.addWidget(self.crop_bar)
        layout.addWidget(self.print_bar)
        layout.addWidget(self.pages, 1)
        layout.addLayout(foot)

        self._auto: dict[str, int] | None = None
        self._cache: dict = {}  # the preview's work before Clarity/Sharpness (see photo_edit.apply)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._render)

    def adjustments(self) -> Adjustments:
        """What's applied (shown and saved): an unticked slider counts as 0."""
        return Adjustments(**{key: s.value() if self.checks[key].isChecked() else 0 for key, s in self.values.items()})

    def changed(self) -> bool:
        return not (self.adjustments().unchanged() and self.turn.unchanged())

    def _update(self) -> None:
        self.save_btn.setEnabled(self.changed())
        self._timer.start()

    # ---------------------------------------------------------------- flip and rotate
    def rotate(self) -> None:
        self._set_turn(self.turn.rotated())

    def flip(self, vertical: bool) -> None:
        self._set_turn(self.turn.flipped(vertical))

    def _set_turn(self, turn: Turn) -> None:
        if self.cropping:
            return
        self.turn = turn
        self.view.before = to_qimage(turn.image(self.original))
        self.view.zoom.reset()
        self._render()
        self._update()

    # ---------------------------------------------------------------- building
    def _big_rows(self, sv: QVBoxLayout, rows: list) -> None:
        """Light & colour and Detail: checkbox, name, value; slider with ↺ and A; its two ends below."""
        for key, name, left, right, colours in rows:
            grid = QGridLayout()
            grid.setVerticalSpacing(2)
            grid.setHorizontalSpacing(4)
            check = self._check(key, name)
            title, number = QLabel(name), self._number()
            slider = self._slider(key, name, colours)
            if key == "sharpness":
                slider.setRange(0, 100)  # no "less sharp" end
            reset = self._reset(key, name, slider)
            auto_btn = QToolButton(text="A")
            auto_btn.setAutoRaise(True)
            auto_btn.setToolTip(f"Auto: set {name} from the photo")
            auto_btn.clicked.connect(lambda _c=False, key=key: self.set_auto(key))
            ends = QHBoxLayout()
            labels = []
            for text, align in ((left, Qt.AlignmentFlag.AlignLeft), (right, Qt.AlignmentFlag.AlignRight)):
                label = QLabel(text)
                label.setStyleSheet("QLabel { color: palette(placeholder-text); font-size: 11px; }"
                                    "QLabel:disabled { color: #55585e; }")
                label.setAlignment(align)
                ends.addWidget(label)
                labels.append(label)
            grid.addWidget(check, 0, 0)
            grid.addWidget(title, 0, 1)
            grid.addWidget(number, 0, 2)
            grid.addWidget(slider, 1, 1, 1, 2)
            grid.addWidget(reset, 1, 3)
            grid.addWidget(auto_btn, 1, 4)
            grid.addLayout(ends, 2, 1, 1, 2)
            grid.setColumnStretch(1, 1)
            sv.addLayout(grid)
            sv.addSpacing(8)
            self.values[key], self.numbers[key], self.resets[key] = slider, number, reset
            self.parts[key] = [title, number, slider, reset, auto_btn, *labels]

    def _check(self, key: str, name: str) -> QCheckBox:
        check = QCheckBox()
        check.setChecked(True)
        check.setToolTip(f"Untick to see the photo without {name} (also when saving); tick to bring it back")
        check.toggled.connect(lambda on, key=key: self._ticked(key, on))
        self.checks[key] = check
        return check

    def _number(self) -> QLabel:
        number = QLabel("0")
        number.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        number.setMinimumWidth(30)
        number.setStyleSheet("QLabel { color: palette(placeholder-text); } QLabel:disabled { color: #55585e; }")
        return number

    def _slider(self, key: str, name: str, colours: tuple[str, ...]) -> QSlider:
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(-100, 100)
        slider.setValue(0)
        slider.setToolTip(f"{name}: click a spot to jump there, or drag")
        stops = ", ".join(f"stop:{i / (len(colours) - 1):.2f} {c}" for i, c in enumerate(colours))
        slider.setStyleSheet(
            "QSlider::groove:horizontal { height: 6px; border-radius: 3px; "
            f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops}); }}"
            "QSlider::groove:horizontal:disabled { background: #44474d; }"
            "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; "
            "background: #e6e6e6; border: 1px solid #888888; }"
            "QSlider::handle:horizontal:disabled { background: #6a6d73; border-color: #55585e; }")
        make_scrubbable(slider)  # a click jumps there
        slider.valueChanged.connect(lambda v, key=key: self._changed(key, v))
        return slider

    def _reset(self, key: str, name: str, slider: QSlider) -> QToolButton:
        reset = QToolButton(text="↺")
        reset.setAutoRaise(True)
        reset.setToolTip(f"Put {name} back to 0")
        reset.setEnabled(False)
        reset.clicked.connect(lambda _c=False, s=slider: s.setValue(0))
        return reset

    def _ticked(self, key: str, on: bool) -> None:
        for w in self.parts.get(key, []):
            w.setEnabled(on)
        if on:
            self.resets[key].setEnabled(self.values[key].value() != 0)
        self._update()

    def set_auto(self, key: str | None) -> None:
        """Auto for one slider (key) or all of them (None)."""
        if self._auto is None:
            self._auto = auto(self.original)
        for k, value in self._auto.items():
            if key is None or k == key:
                self.values[k].setValue(value)

    def _picking(self, on: bool) -> None:
        self.view.set_picking(on)
        self.pick_hint.setVisible(on)

    def _picked(self, fx: float, fy: float) -> None:
        shown = self.turn.image(self.original)  # the click is on the photo as it's shown (turned)
        x, y = int(fx * shown.width), int(fy * shown.height)
        yellow, red = white_balance_at(shown, x, y, radius=max(2, shown.width // 300))
        self.values["yellow"].setValue(yellow)
        self.values["red"].setValue(red)
        self.pick_btn.setChecked(False)

    def _changed(self, key: str, value: int) -> None:
        self.numbers[key].setText(f"{value:+d}" if value else "0")
        self.resets[key].setEnabled(value != 0 and self.checks[key].isChecked())
        self._update()

    def _render(self) -> None:
        self.view.set_after(to_qimage(self.turn.image(apply(self.original, self.adjustments(), self._cache))))

    def reset(self) -> None:
        for key, slider in self.values.items():
            slider.setValue(0)
            self.checks[key].setChecked(True)
        if not self.turn.unchanged():
            self._set_turn(Turn())

    def _show_before(self, on: bool) -> None:
        self.view.whole_before = on
        self.view.update()

    # ---------------------------------------------------------------- a photo in, a result out
    def load(self, path: str, keep_zoom: bool = False) -> None:
        """Start editing path: every slider at 0 and ticked, the line at the left, fitted (or, going on with
        ←/→, zoomed as the photo before was, the user's request)."""
        self.path = path
        self.original = open_image(path, PREVIEW_PIXELS)  # upright, screen-sized
        self._auto, self._cache, self._result = None, {}, 0
        self.turn = Turn()
        self.view.before = self.view.after = to_qimage(self.original)
        self.view.split = 0.0
        if not keep_zoom:
            self.view.zoom.reset()
        self.pick_btn.setChecked(False)
        self.reset()
        self._timer.stop()
        note = "the original goes to the Recycle Bin"
        if os.path.splitext(path)[1].lower() in SAVED_AS_JPG:
            note += " · saved as JPG"
        self.info.setText(f"{os.path.basename(path)} · {note}")
        self.caption.setText(os.path.basename(path))
        self.cancel_crop()
        self.crop_btn.setEnabled(can_crop(path))
        self.view.update()

    def reload_image(self) -> None:
        """The photo changed on disk (cropped): show it again, keeping the sliders as they are."""
        self.original = open_image(self.path, PREVIEW_PIXELS)
        self._auto, self._cache = None, {}
        self.view.before = to_qimage(self.turn.image(self.original))
        self.view.zoom.reset()
        self._render()

    # ---------------------------------------------------------------- crop
    @property
    def cropping(self) -> bool:
        return self.pages.currentWidget() is self.cropper

    def _ratio_value(self) -> float | None:
        value = ASPECT_RATIOS.get(self.ratio.currentText())
        if value == "original":
            w, h = self.cropper.full_size
            return w / h if h else None
        return value  # type: ignore[return-value]

    def start_crop(self) -> None:
        if not self.crop_btn.isEnabled() or self.cropping:
            return
        from PySide6.QtGui import QPixmap

        try:
            self._full = upright_size(self.path)
        except Exception:  # noqa: BLE001
            self._full = (self.original.width, self.original.height)
        full = self.turn.size(*self._full)  # the box is drawn on the photo as it's shown (turned)
        self.as_copy.setChecked(bool(getattr(self.crop_settings, "crop_as_copy", False)))
        self.cropper.set_image(QPixmap.fromImage(self.view.after), full)  # what you see, edits and all
        self.pages.setCurrentWidget(self.cropper)
        self.crop_bar.setVisible(True)
        self.cropper.start_crop(self._ratio_value())
        self.setFocus()

    # ---------------------------------------------------------------- print size
    def chosen_print(self) -> print_size.PrintSize:
        return print_size.BY_NAME[self.print_size.currentData()]

    def _print_shape(self) -> None:
        size, border = self.chosen_print(), self.print_border.isChecked()
        w, h = size.photo_part(border)
        self.print_info.setText(f"→ {size.width} × {size.height} px · {print_size.DPI} DPI · prints {size.inches()}"
                                + (f" (photo {w} × {h} + border)" if border else ""))
        if self.printing:
            self.cropper.set_ratio(size.ratio(border))

    def start_print(self) -> None:
        if not self.crop_btn.isEnabled() or self.cropping:
            return
        self.start_crop()
        self.crop_bar.setVisible(False)
        if self.fill_weeks is not None:
            self.fill_weeks(self.path)
        self.print_bar.setVisible(True)
        self.printing = True
        self._print_shape()

    def apply_print(self) -> None:
        if not self.printing:
            return
        box = self.cropper.crop_box()  # on the photo as shown (edits, flip/rotate), full-size pixels
        size, border = self.chosen_print().name, self.print_border.isChecked()
        week = self.print_week.currentData() or ""
        self.cancel_crop()
        self.print_requested.emit(self.path, box, size, border, week)

    def cancel_crop(self) -> None:
        self.printing = False
        self.print_bar.setVisible(False)
        self.crop_bar.setVisible(False)
        self.cropper.stop_crop()
        self.pages.setCurrentWidget(self.view)

    def apply_crop(self) -> None:
        if not self.cropping or self.printing:
            return
        box = self.turn.box_back(self.cropper.crop_box(), *self._full)  # the file isn't turned until Save
        self.cancel_crop()
        self.crop_requested.emit(self.path, box, self.as_copy.isChecked())

    def set_last(self, values: dict | None) -> None:
        """The sliders of the last photo saved, for "Same as last edit"."""
        self._last = values or None
        self.same_btn.setEnabled(bool(self._last))

    def same_as_last(self) -> None:
        if not self._last:
            return
        for key, slider in self.values.items():
            slider.setValue(int(self._last.get(key, 0)))
            self.checks[key].setChecked(True)

    def accept(self) -> None:
        self._result = 1
        self.finished.emit("save")

    def reject(self) -> None:
        self._result = 0
        self.finished.emit("cancel")

    def result(self) -> int:
        return self._result

    def confirm_leave(self) -> str | None:
        """Before leaving this photo: "save", "discard", or None (keep editing). Asks only if something changed."""
        from PySide6.QtWidgets import QMessageBox

        if not self.changed():
            return "discard"
        box = QMessageBox(QMessageBox.Icon.Question, "Edit photo", "Save the edit?", parent=self)
        save = box.addButton("Save", QMessageBox.ButtonRole.AcceptRole)
        discard = box.addButton("Don't save", QMessageBox.ButtonRole.DestructiveRole)
        box.addButton("Keep editing", QMessageBox.ButtonRole.RejectRole)
        box.setDefaultButton(save)
        box.exec()
        if box.clickedButton() is save:
            return "save"
        if box.clickedButton() is discard:
            return "discard"
        return None

    def close_with_shortcut(self) -> None:
        """Shift+E (the key that opened it) closes it; with changes, it asks first."""
        choice = self.confirm_leave()
        if choice == "save":
            self.accept()
        elif choice == "discard":
            self.reject()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        key = event.key()
        if self.cropping:
            if key == Qt.Key.Key_Escape:
                self.cancel_crop()
            elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                self.apply_print() if self.printing else self.apply_crop()
            return
        if key == Qt.Key.Key_P and not event.modifiers():
            self.start_print()
            return
        if key == Qt.Key.Key_C and not event.modifiers():
            self.start_crop()
            return
        if key in (Qt.Key.Key_R, Qt.Key.Key_H, Qt.Key.Key_V) and not event.modifiers():
            self.rotate() if key == Qt.Key.Key_R else self.flip(key == Qt.Key.Key_V)
            return
        if key == Qt.Key.Key_E and event.modifiers() == Qt.KeyboardModifier.ShiftModifier:
            self.close_with_shortcut()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            self.navigate.emit(-1 if key == Qt.Key.Key_Left else 1)
            return
        if key == Qt.Key.Key_Escape:
            self.close_with_shortcut()
            return
        if key == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self._show_before(True)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._show_before(False)
            return
        super().keyReleaseEvent(event)
