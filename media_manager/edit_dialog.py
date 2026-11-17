"""The Edit window (the user's "Option A and C"): the photo with a line down it (original on the left,
the edit on the right; drag the line), five sliders on the right, and "Hold for Before" (or the space bar)
to see the whole original for a moment."""

from __future__ import annotations

import os

from PIL import Image
from PySide6.QtCore import QPointF, QRect, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QFont, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QDialog,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from photo_manager.core.thumbs import open_image

from .photo_edit import SAVED_AS_JPG, Adjustments, apply

PREVIEW_PIXELS = 1600
# (attribute, name, left end, right end, groove colours left -> right)
SLIDERS = [
    ("yellow", "Blue ↔ Yellow", "Bluer", "Yellower", ("#3b78d8", "#777777", "#d8b83b")),
    ("red", "Green ↔ Red", "Greener", "Redder", ("#3bb85a", "#777777", "#d84a3b")),
    ("contrast", "Contrast", "Less", "More", ("#555555", "#999999")),
    ("shadows", "Shadows", "Darker", "Lighter", ("#111111", "#888888")),
    ("highlights", "Highlights", "Darker", "Brighter", ("#666666", "#eeeeee")),
]


def to_qimage(image: Image.Image) -> QImage:
    image = image.convert("RGBA")
    data = image.tobytes("raw", "RGBA")
    return QImage(data, image.width, image.height, image.width * 4, QImage.Format.Format_RGBA8888).copy()


class CompareView(QWidget):
    """The original left of the line, the edit right of it. Press anywhere and drag to move the line."""

    def __init__(self, before: QImage, parent: QWidget | None = None):
        super().__init__(parent)
        self.before, self.after = before, before
        self.split = 0.5          # where the line is, across the picture
        self.whole_before = False  # "Hold for Before"
        self.setMinimumSize(360, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setCursor(Qt.CursorShape.SplitHCursor)

    def set_after(self, image: QImage) -> None:
        self.after = image
        self.update()

    def picture_rect(self) -> QRectF:
        size = self.before.size().scaled(self.size(), Qt.AspectRatioMode.KeepAspectRatio)
        rect = QRectF(0, 0, size.width(), size.height())
        rect.moveCenter(QRectF(self.rect()).center())
        return rect

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        p = QPainter(self)
        p.fillRect(self.rect(), QColor("#1b1c1f"))
        rect = self.picture_rect()
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        if self.whole_before:
            p.drawImage(rect, self.before)
            self._caption(p, rect, "Before", left=True)
            return
        p.drawImage(rect, self.after)
        x = rect.left() + rect.width() * self.split
        if self.split > 0:
            p.save()
            p.setClipRect(QRectF(rect.left(), rect.top(), x - rect.left(), rect.height()))
            p.drawImage(rect, self.before)
            p.restore()
            self._caption(p, rect, "Before", left=True)
        if self.split < 1:
            self._caption(p, rect, "After", left=False)
        if 0 < self.split < 1:
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))
            p.setBrush(QColor("white"))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawEllipse(QPointF(x, rect.center().y()), 13, 13)
            p.setPen(QColor("#222222"))
            p.drawText(QRectF(x - 13, rect.center().y() - 13, 26, 26), Qt.AlignmentFlag.AlignCenter, "⇔")

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

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.button() == Qt.MouseButton.LeftButton:
            self._move_line(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.buttons() & Qt.MouseButton.LeftButton:
            self._move_line(event.position().x())


class EditDialog(QDialog):
    hold = Signal(bool)

    def __init__(self, path: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.path = path
        self.setWindowTitle(f"Edit photo: {os.path.basename(path)}")
        self.resize(1180, 760)
        self.original = open_image(path, PREVIEW_PIXELS)  # upright, screen-sized
        self.view = CompareView(to_qimage(self.original))
        self.values: dict[str, QSlider] = {}
        self.numbers: dict[str, QLabel] = {}

        sliders = QWidget()
        sliders.setFixedWidth(260)
        sv = QVBoxLayout(sliders)
        sv.setContentsMargins(0, 0, 0, 0)
        for key, name, left, right, colours in SLIDERS:
            grid = QGridLayout()
            grid.setVerticalSpacing(2)
            title, number = QLabel(name), QLabel("0")
            number.setAlignment(Qt.AlignmentFlag.AlignRight)
            number.setStyleSheet("color: palette(placeholder-text);")
            slider = QSlider(Qt.Orientation.Horizontal)
            slider.setRange(-100, 100)
            slider.setValue(0)
            slider.setToolTip(f"{name}: drag, or click a spot. Double-click the name to put it back to 0.")
            stops = ", ".join(f"stop:{i / (len(colours) - 1):.2f} {c}" for i, c in enumerate(colours))
            slider.setStyleSheet(
                "QSlider::groove:horizontal { height: 6px; border-radius: 3px; "
                f"background: qlineargradient(x1:0, y1:0, x2:1, y2:0, {stops}); }}"
                "QSlider::handle:horizontal { width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; "
                "background: #e6e6e6; border: 1px solid #888888; }")
            slider.valueChanged.connect(lambda v, key=key: self._changed(key, v))
            ends = QHBoxLayout()
            for text, align in ((left, Qt.AlignmentFlag.AlignLeft), (right, Qt.AlignmentFlag.AlignRight)):
                label = QLabel(text)
                label.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
                label.setAlignment(align)
                ends.addWidget(label)
            title.mouseDoubleClickEvent = lambda _e, s=slider: s.setValue(0)  # type: ignore[method-assign]
            grid.addWidget(title, 0, 0)
            grid.addWidget(number, 0, 1)
            grid.addWidget(slider, 1, 0, 1, 2)
            grid.addLayout(ends, 2, 0, 1, 2)
            sv.addLayout(grid)
            sv.addSpacing(10)
            self.values[key], self.numbers[key] = slider, number
        sv.addStretch(1)

        body = QHBoxLayout()
        body.addWidget(self.view, 1)
        body.addWidget(sliders)

        foot = QHBoxLayout()
        note = "the original goes to the Recycle Bin"
        if os.path.splitext(path)[1].lower() in SAVED_AS_JPG:
            note += " · saved as JPG"
        info = QLabel(f"{os.path.basename(path)} · {note}")
        info.setStyleSheet("color: palette(placeholder-text);")
        foot.addWidget(info, 1)
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
        cancel.clicked.connect(self.reject)
        self.save_btn = QPushButton("Save")
        self.save_btn.setDefault(True)
        self.save_btn.setEnabled(False)
        self.save_btn.clicked.connect(self.accept)
        for b in (self.before_btn, reset, cancel, self.save_btn):
            foot.addWidget(b)

        layout = QVBoxLayout(self)
        layout.addLayout(body, 1)
        layout.addLayout(foot)

        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(25)
        self._timer.timeout.connect(self._render)

    def adjustments(self) -> Adjustments:
        return Adjustments(**{key: s.value() for key, s in self.values.items()})

    def _changed(self, key: str, value: int) -> None:
        self.numbers[key].setText(f"{value:+d}" if value else "0")
        self.save_btn.setEnabled(not self.adjustments().unchanged())
        self._timer.start()

    def _render(self) -> None:
        self.view.set_after(to_qimage(apply(self.original, self.adjustments())))

    def reset(self) -> None:
        for slider in self.values.values():
            slider.setValue(0)

    def _show_before(self, on: bool) -> None:
        self.view.whole_before = on
        self.view.update()

    def keyPressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.key() == Qt.Key.Key_Space:
            if not event.isAutoRepeat():
                self._show_before(True)
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._show_before(False)
            return
        super().keyReleaseEvent(event)
