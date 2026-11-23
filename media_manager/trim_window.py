"""Music › Trim… window: the song's waveform with a start and an end handle, fade in / fade out, a preview to
listen to, and Trim (the work itself is media_manager.trim)."""

from __future__ import annotations

import os
import threading

from PySide6.QtCore import QObject, QPointF, QRectF, Qt, QTimer, QUrl, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QDoubleSpinBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from . import trim

FADE = QColor("#e2b04a")
WAVE = QColor("#5d8fd8")


def clock(seconds: float) -> str:
    """5:28.0"""
    seconds = max(0.0, seconds)
    m = int(seconds // 60)
    return f"{m}:{seconds - m * 60:04.1f}"


def parse_clock(text: str) -> float | None:
    """'5:28.0', '5:28' or '328.0' → seconds."""
    text = text.strip()
    try:
        if ":" in text:
            m, s = text.split(":", 1)
            return int(m or 0) * 60 + float(s or 0)
        return float(text)
    except ValueError:
        return None


class WaveView(QWidget):
    """The waveform: drag the white handles (start, end); the parts outside them are darkened."""

    changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setMinimumHeight(150)
        self.setMouseTracking(True)
        self.peaks: list[float] = []
        self.length = 0.0
        self.start = 0.0
        self.end = 0.0
        self.fade_in = 0.0
        self.fade_out = 0.0
        self.position: float | None = None  # where the preview is playing (song time)
        self.message = "Reading the song…"
        self._drag: str | None = None

    def set_song(self, peaks: list[float], length: float) -> None:
        top = max(peaks) if peaks else 0
        self.peaks = [p / top for p in peaks] if top > 0 else peaks
        self.length, self.start, self.end = length, 0.0, length
        self.message = ""
        self.update()

    def _x(self, t: float) -> float:
        return 0 if self.length <= 0 else t / self.length * self.width()

    def _t(self, x: float) -> float:
        return max(0.0, min(self.length, x / max(1, self.width()) * self.length))

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor("#1b1c20"))
        if self.message:
            p.setPen(QColor("#9a9ea6"))
            p.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self.message)
            return
        mid = h / 2
        if self.peaks:
            bar = w / len(self.peaks)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(WAVE)
            for i, v in enumerate(self.peaks):
                half = max(0.5, v * (h / 2 - 6))
                p.drawRect(QRectF(i * bar, mid - half, max(1.0, bar - 0.4), half * 2))
        xs, xe = self._x(self.start), self._x(self.end)
        p.setBrush(QColor(10, 10, 12, 185))
        p.drawRect(QRectF(0, 0, xs, h))
        p.drawRect(QRectF(xe, 0, w - xe, h))
        pen = QPen(FADE, 2)
        p.setPen(pen)
        if self.fade_in > 0:
            p.drawLine(QPointF(xs, h - 2), QPointF(self._x(min(self.end, self.start + self.fade_in)), 2))
        if self.fade_out > 0:
            p.drawLine(QPointF(self._x(max(self.start, self.end - self.fade_out)), 2), QPointF(xe, h - 2))
        if self.position is not None:
            p.setPen(QPen(QColor("#7fb0ff"), 1.5))
            x = self._x(self.position)
            p.drawLine(QPointF(x, 0), QPointF(x, h))
        for x in (xs, xe):
            p.setPen(QPen(QColor("white"), 2))
            p.drawLine(QPointF(x, 0), QPointF(x, h))
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(x, 7), 7, 7)

    def _handle_at(self, x: float) -> str:
        """The handle to move: the one under the pointer, else the nearer one."""
        ds, de = abs(x - self._x(self.start)), abs(x - self._x(self.end))
        return "start" if ds <= de else "end"

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        if self.length <= 0:
            return
        self._drag = self._handle_at(event.position().x())
        self._move(event.position().x())

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        x = event.position().x()
        if self._drag:
            self._move(x)
        elif self.length > 0:
            near = min(abs(x - self._x(self.start)), abs(x - self._x(self.end))) < 9
            self.setCursor(Qt.CursorShape.SizeHorCursor if near else Qt.CursorShape.ArrowCursor)

    def mouseReleaseEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        self._drag = None

    def _move(self, x: float) -> None:
        t = self._t(x)
        if self._drag == "start":
            self.start = min(t, self.end - 1.0)
        else:
            self.end = max(t, self.start + 1.0)
        self.start, self.end = max(0.0, self.start), min(self.length, self.end)
        self.update()
        self.changed.emit()


class Ticks(QWidget):
    """The minutes under the waveform, each under its place."""

    def __init__(self, wave: WaveView, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.wave = wave
        self.setFixedHeight(16)

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        length = self.wave.length
        if length <= 0:
            return
        p = QPainter(self)
        p.setPen(QColor("#9a9ea6"))
        f = p.font()
        f.setPointSizeF(8.5)
        p.setFont(f)
        w = self.width()
        step = 60 if length > 150 else 30 if length > 60 else 10
        marks = list(range(0, int(length), step))
        if length - marks[-1] < step * 0.4:
            marks.pop()  # too close to the end's own label
        for t in marks:
            p.drawText(QRectF(t / length * w, 0, 60, 16), Qt.AlignmentFlag.AlignLeft, clock(t).split(".")[0])
        p.drawText(QRectF(w - 60, 0, 60, 16), Qt.AlignmentFlag.AlignRight, clock(length).split(".")[0])


class _Relay(QObject):
    loaded = Signal(object, float)
    failed = Signal(str)


class TrimWindow(QDialog):
    """Choose where the song starts and ends, and its fades; values() once accepted."""

    def __init__(self, ffmpeg: str, path: str, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ffmpeg, self.path = ffmpeg, path
        self.setWindowTitle("Trim")
        self.resize(860, 430)
        self._previews: list[str] = []
        self.player = None
        lay = QVBoxLayout(self)
        name = QLabel(os.path.basename(path))
        name.setStyleSheet("font-size: 15px; font-weight: 600;")
        lay.addWidget(name)
        self.meta = QLabel("")
        self.meta.setStyleSheet("color: #9a9ea6;")
        lay.addWidget(self.meta)
        self.wave = WaveView(self)
        lay.addWidget(self.wave, 1)
        self.ticks = Ticks(self.wave, self)
        lay.addWidget(self.ticks)

        grid = QGridLayout()
        self.start_box, self.end_box = QLineEdit(), QLineEdit()
        for box in (self.start_box, self.end_box):
            box.setFixedWidth(90)
            box.editingFinished.connect(self._typed)
        self.play_start = QPushButton("▶ Play from here")
        self.play_end = QPushButton("▶ Play the last 5 s")
        self.play_start.clicked.connect(lambda: self._play("start"))
        self.play_end.clicked.connect(lambda: self._play("end"))
        self.fade_in_box, self.fade_out_box = QDoubleSpinBox(), QDoubleSpinBox()
        for box in (self.fade_in_box, self.fade_out_box):
            box.setRange(0, 30)
            box.setSingleStep(0.5)
            box.setDecimals(1)
            box.setSuffix(" s")
            box.setFixedWidth(90)
            box.valueChanged.connect(self._faded)
        grid.addWidget(QLabel("Start at"), 0, 0)
        grid.addWidget(self.start_box, 1, 0)
        grid.addWidget(self.play_start, 1, 1, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(QLabel("End at"), 0, 2)
        grid.addWidget(self.end_box, 1, 2)
        grid.addWidget(self.play_end, 1, 3, Qt.AlignmentFlag.AlignLeft)
        grid.addWidget(QLabel("Fade in"), 2, 0)
        fin = QHBoxLayout()
        fin.addWidget(self.fade_in_box)
        zero = QLabel("0 = no fade")
        zero.setStyleSheet("color: #9a9ea6;")
        fin.addWidget(zero)
        fin.addStretch(1)
        grid.addLayout(fin, 3, 0, 1, 2)
        grid.addWidget(QLabel("Fade out"), 2, 2)
        grid.addWidget(self.fade_out_box, 3, 2)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(3, 1)
        lay.addLayout(grid)

        foot = QHBoxLayout()
        lossless = ("The MP3 isn't re-encoded: the cut is made between its frames (every 1/40 s), and the fades "
                    "are done by turning down each frame's volume. " if path.lower().endswith(".mp3") else "")
        note = QLabel(lossless + "The original goes to the Recycle Bin; tags, lyrics and the .txt are kept, and "
                      "ReplayGain is measured again.")
        note.setWordWrap(True)
        note.setStyleSheet("color: #9a9ea6; font-size: 12px;")
        foot.addWidget(note, 1)
        cancel, self.ok = QPushButton("Cancel"), QPushButton("Trim")
        self.ok.setDefault(True)
        self.ok.setEnabled(False)
        cancel.clicked.connect(self.reject)
        self.ok.clicked.connect(self.accept)
        foot.addWidget(cancel)
        foot.addWidget(self.ok)
        lay.addLayout(foot)

        self.wave.changed.connect(self._dragged)
        self._relay = _Relay()
        self._relay.loaded.connect(self._loaded)
        self._relay.failed.connect(self._failed)
        relay = self._relay

        def work() -> None:
            try:
                peaks, length = trim.peaks(ffmpeg, path, 900)
                relay.loaded.emit(peaks, length)
            except Exception as exc:  # noqa: BLE001
                try:
                    relay.failed.emit(str(exc))
                except RuntimeError:  # closed meanwhile
                    pass

        threading.Thread(target=work, daemon=True).start()
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._tick)

    # ------------------------------------------------------------ values
    def values(self) -> tuple[float, float | None, float, float]:
        """(start, end — None if not cut, fade in, fade out), in seconds."""
        w = self.wave
        end = None if w.end >= w.length - 0.01 else w.end
        return w.start, end, self.fade_in_box.value(), self.fade_out_box.value()

    def _loaded(self, peaks: list[float], length: float) -> None:
        self.wave.set_song(peaks, length)
        self.ticks.update()
        self._show()

    def _failed(self, text: str) -> None:
        self.wave.message = f"Couldn't read the song: {text}"
        self.wave.update()

    def _show(self) -> None:
        w = self.wave
        self.start_box.setText(clock(w.start))
        self.end_box.setText(clock(w.end))
        self.meta.setText(f"{clock(w.length).split('.')[0]} now, {clock(w.end - w.start).split('.')[0]} after the trim")
        start, end, fin, fout = self.values()
        self.ok.setEnabled(w.length > 0 and (start > 0.01 or end is not None or fin > 0 or fout > 0))

    def _dragged(self) -> None:
        self._show()

    def _typed(self) -> None:
        w = self.wave
        s, e = parse_clock(self.start_box.text()), parse_clock(self.end_box.text())
        if s is not None and e is not None and w.length > 0:
            e = min(w.length, e)
            s = max(0.0, min(s, e - 1.0))
            w.start, w.end = s, e
            w.update()
        self._show()

    def _faded(self) -> None:
        self.wave.fade_in, self.wave.fade_out = self.fade_in_box.value(), self.fade_out_box.value()
        self.wave.update()
        self._show()

    # ------------------------------------------------------------ listening first
    def _play(self, where: str) -> None:
        from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer

        if self.player and self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._stop()
            return
        start, end, fin, fout = self.values()
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            copy = trim.preview_copy(self.ffmpeg, self.path, start, end, fin, fout)  # exactly what Trim makes
        except Exception as exc:  # noqa: BLE001
            self.meta.setText(f"Couldn't make the preview: {exc}")
            return
        finally:
            QApplication.restoreOverrideCursor()
        self._previews.append(copy)
        if self.player is None:
            self.player = QMediaPlayer(self)
            self.audio = QAudioOutput(self)
            self.player.setAudioOutput(self.audio)
            self.player.playbackStateChanged.connect(self._state)
        self.player.setSource(QUrl.fromLocalFile(copy))
        length = self.wave.end - self.wave.start
        self._offset = 0.0 if where == "start" else max(0.0, length - 5.0)
        self.player.setPosition(int(self._offset * 1000))
        self.player.play()
        self._timer.start(50)
        (self.play_start if where == "start" else self.play_end).setText("■ Stop")

    def _state(self, state) -> None:  # type: ignore[no-untyped-def]
        from PySide6.QtMultimedia import QMediaPlayer

        if state != QMediaPlayer.PlaybackState.PlayingState:
            self._timer.stop()
            self.wave.position = None
            self.wave.update()
            self.play_start.setText("▶ Play from here")
            self.play_end.setText("▶ Play the last 5 s")

    def _tick(self) -> None:
        if self.player:
            self.wave.position = self.wave.start + self.player.position() / 1000
            self.wave.update()

    def _stop(self) -> None:
        if self.player:
            self.player.stop()
            self.player.setSource(QUrl())

    def done(self, result: int) -> None:  # noqa: D102 - closing: stop and remove the preview copies
        self._stop()
        for path in self._previews:
            try:
                os.remove(path)
            except OSError:
                pass
        super().done(result)
