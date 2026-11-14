"""Scrubbing: every playback timeline follows the mouse. Click anywhere on it to jump there, and keep the
button down to drag back and forth while the song or video plays from where you are."""

from __future__ import annotations

from PySide6.QtWidgets import QProxyStyle, QSlider, QStyle

_styles: list[QProxyStyle] = []  # kept alive while their sliders are


class ScrubStyle(QProxyStyle):
    """The app's own style, except a left click on a slider jumps to that spot (and starts dragging)."""

    def styleHint(self, hint, option=None, widget=None, data=None):  # type: ignore[no-untyped-def]  # noqa: N802
        if hint == QStyle.StyleHint.SH_Slider_AbsoluteSetButtons:
            from PySide6.QtCore import Qt

            return Qt.MouseButton.LeftButton.value
        return super().styleHint(hint, option, widget, data)


def make_scrubbable(slider: QSlider) -> None:
    if getattr(slider, "_scrub", False):
        return
    style = ScrubStyle()  # no base style given: it follows the app's style, also when the theme changes
    _styles.append(style)
    slider.setStyle(style)
    slider._scrub = True  # type: ignore[attr-defined]


def patch_photo_videos() -> None:
    """Every Photos video player made from now on (call before Photo Manager's window is built)."""
    from photo_manager.ui import video

    init = video.VideoView.__init__
    if getattr(init, "_scrub", False):
        return

    def scrubbable_init(self, *args, **kwargs):  # type: ignore[no-untyped-def]
        init(self, *args, **kwargs)
        make_scrubbable(self.slider)
        # A click without dragging moves the handle; play from there too.
        self.slider.sliderReleased.connect(lambda: self._seek(self.slider.value()))

    scrubbable_init._scrub = True  # type: ignore[attr-defined]
    video.VideoView.__init__ = scrubbable_init


def install(music, movies) -> None:  # type: ignore[no-untyped-def]
    """Music's and Movies' timelines."""
    make_scrubbable(movies.slider)
    if getattr(movies, "player", None) is not None:
        movies.slider.sliderReleased.connect(lambda: movies.player.setPosition(movies.slider.value()))
    player = music.player
    make_scrubbable(player.slider)
    if player.player is not None:
        # Music jumped only when the mouse was let go; now it plays from wherever you drag.
        player.slider.sliderMoved.connect(lambda ms: player.player.setPosition(ms))
