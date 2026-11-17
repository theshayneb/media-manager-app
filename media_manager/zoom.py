"""Zooming with the mouse wheel (towards the pointer), and dragging to look around while zoomed in.
Used by the Edit window and, patched in from here, by Photo Manager's big preview (its CropCanvas)."""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt

MAX_ZOOM = 6.0
STEP = 1.25  # per wheel notch


class Zoom:
    """How far in (1 = fitted) and which part of the picture is in the middle (as fractions)."""

    def __init__(self) -> None:
        self.reset()

    def reset(self) -> None:
        self.zoom = 1.0
        self.cx = self.cy = 0.5
        self._pan_from: QPointF | None = None
        self._x0 = self._y0 = 0.0

    @property
    def zoomed(self) -> bool:
        return self.zoom > 1.0001

    def rect(self, fitted: QRectF, area: QRectF) -> QRectF:
        """Where the picture goes: fitted (the zoom-1 rectangle) scaled up around (cx, cy), never leaving a gap
        at an edge while it's bigger than the area."""
        if not self.zoomed or fitted.isEmpty():
            return fitted
        w, h = fitted.width() * self.zoom, fitted.height() * self.zoom

        def place(size: float, extent: float, start: float, centre: float) -> float:
            if size <= extent:
                return start + (extent - size) / 2
            return min(start, max(start + extent - size, start + extent / 2 - centre * size))

        x = place(w, area.width(), area.left(), self.cx)
        y = place(h, area.height(), area.top(), self.cy)
        return QRectF(x, y, w, h)

    def _centre_from(self, rect: QRectF, area: QRectF) -> None:
        self.cx = (area.center().x() - rect.left()) / rect.width()
        self.cy = (area.center().y() - rect.top()) / rect.height()

    def wheel(self, notches: float, at: QPointF, fitted: QRectF, area: QRectF) -> bool:
        """Zoom by notches (+ in, - out) keeping the spot under the pointer where it is. True if it changed."""
        if fitted.isEmpty():
            return False
        before = self.rect(fitted, area)
        fx = (at.x() - before.left()) / before.width()
        fy = (at.y() - before.top()) / before.height()
        new = max(1.0, min(MAX_ZOOM, self.zoom * STEP ** notches))
        if abs(new - self.zoom) < 1e-6:
            return False
        self.zoom = new
        if not self.zoomed:
            self.reset()
            return True
        w, h = fitted.width() * new, fitted.height() * new
        rect = QRectF(at.x() - fx * w, at.y() - fy * h, w, h)
        self._centre_from(rect, area)
        self._centre_from(self.rect(fitted, area), area)  # after keeping the edges in
        return True

    def start_pan(self, at: QPointF) -> None:
        self._pan_from = QPointF(at)

    @property
    def panning(self) -> bool:
        return self._pan_from is not None

    def pan(self, at: QPointF, fitted: QRectF, area: QRectF) -> None:
        if self._pan_from is None:
            return
        rect = self.rect(fitted, area).translated(at - self._pan_from)
        self._pan_from = QPointF(at)
        self._centre_from(rect, area)
        self._centre_from(self.rect(fitted, area), area)

    def end_pan(self) -> None:
        self._pan_from = None


def notches(event) -> float:  # type: ignore[no-untyped-def]
    return event.angleDelta().y() / 120


# ------------------------------------------------------------------ Photo Manager's big preview
def patch_preview() -> None:
    """Wheel zoom and drag-to-look-around for the big preview (call before Photo Manager's window is built)."""
    from photo_manager.ui import preview

    canvas = preview.CropCanvas
    if getattr(canvas, "_zoom_patched", False):
        return
    fitted_target = canvas._target
    set_image, press, move, release = (canvas.set_image, canvas.mousePressEvent, canvas.mouseMoveEvent,
                                       canvas.mouseReleaseEvent)

    def zoom_of(self) -> Zoom:  # type: ignore[no-untyped-def]
        if not hasattr(self, "_zoom"):
            self._zoom = Zoom()
        return self._zoom

    def _target(self) -> QRectF:  # type: ignore[no-untyped-def]
        return zoom_of(self).rect(fitted_target(self), QRectF(self.rect()))

    def _set_image(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        zoom_of(self).reset()
        return set_image(self, *args, **kwargs)

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self.pixmap and zoom_of(self).wheel(notches(event), event.position(), fitted_target(self),
                                               QRectF(self.rect())):
            self.update()
        event.accept()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        z = zoom_of(self)
        if z.zoomed and not self.cropping and event.button() == Qt.MouseButton.LeftButton:
            z.start_pan(event.position())
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
        return press(self, event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        z = zoom_of(self)
        if z.panning:
            z.pan(event.position(), fitted_target(self), QRectF(self.rect()))
            self.update()
            return None
        return move(self, event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        z = zoom_of(self)
        if z.panning:
            z.end_pan()
            self.unsetCursor()
        return release(self, event)

    canvas._target = _target
    canvas.set_image = _set_image
    canvas.wheelEvent = wheelEvent
    canvas.mousePressEvent = mousePressEvent
    canvas.mouseMoveEvent = mouseMoveEvent
    canvas.mouseReleaseEvent = mouseReleaseEvent
    canvas._zoom_patched = True
