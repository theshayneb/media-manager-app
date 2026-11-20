"""Start-up: the settings of each part, ExifTool (photos), ffmpeg (music), and the window."""

from __future__ import annotations

import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication

from . import __version__

ICON = Path(__file__).resolve().parent / "assets" / "icon.png"


def build_window():  # type: ignore[no-untyped-def]
    from music_manager.core.settings import Settings as MusicSettings
    from music_manager.ui.main_window import MainWindow as MusicWindow
    from music_manager.ui.theme import apply_theme
    from photo_manager.app import start_exiftool
    from photo_manager.core.settings import Settings as PhotoSettings
    from photo_manager.ui.main_window import MainWindow as PhotoWindow

    from .settings import MediaSettings
    from .shell import MediaWindow

    photo_settings = PhotoSettings.load()
    music_settings = MusicSettings.load()
    apply_theme(music_settings.theme)
    from .scrub import patch_photo_videos
    from .zoom import patch_preview

    patch_photo_videos()  # before Photo Manager's video player is made
    patch_preview()  # mouse-wheel zoom in the big preview
    photos = PhotoWindow(photo_settings, start_exiftool(photo_settings))
    music = MusicWindow(music_settings)
    return MediaWindow(MediaSettings.load(), photos, music)


def self_test(out_path: str) -> int:
    """Used by CI on the built exe: ExifTool, ffmpeg, audio/video playback and the window load, and a
    FLAC really converts to a tagged MP3."""
    import json
    import tempfile

    result: dict[str, object] = {}
    try:
        from music_manager.core import convert, tags
        from music_manager.core.ffmpeg import find_ffmpeg, run
        from photo_manager.app import start_exiftool
        from photo_manager.core.settings import Settings as PhotoSettings

        ffmpeg = find_ffmpeg()
        result["ffmpeg"] = ffmpeg
        et = start_exiftool(PhotoSettings())
        result["exiftool"] = et.execute("-ver")[0].strip() if et else None
        if et:
            et.close()
        with tempfile.TemporaryDirectory() as tmp:
            flac = str(Path(tmp) / "test.flac")
            run(ffmpeg or "ffmpeg", ["-f", "lavfi", "-i", "sine=frequency=440:duration=2", flac])
            tags.write(flac, {"title": "Test", "rating": 5})
            mp3 = convert.to_mp3(ffmpeg, flac, "V0")
            result["convert_ok"] = tags.read_track(mp3).title == "Test"
        from PIL import Image

        from photo_manager.core import thumbs  # noqa: F401  (registers the HEIC opener)

        result["heic"] = ".heic" in Image.registered_extensions()
        from PySide6.QtMultimedia import QMediaPlayer

        result["media"] = QMediaPlayer().isAvailable()
        from PySide6.QtPrintSupport import QPrinter  # Print sheet

        result["print"] = QPrinter().resolution() > 0
        from PIL import ImageCms  # Print sheet's printer profile

        result["icc"] = bool(ImageCms.createProfile("sRGB"))
        window = build_window()
        window.close()
        result["icon"] = ICON.exists()
        result["ok"] = bool(ffmpeg and result["exiftool"] and result["convert_ok"] and result["heic"]
                            and result["media"] and result["icon"] and result["print"]
                            and result["icc"])
    except Exception as exc:  # noqa: BLE001
        result["error"] = repr(exc)
        result["ok"] = False
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f)
    return 0 if result["ok"] else 1


def install_error_handler() -> None:
    """Show unexpected errors instead of failing silently (the exe has no console)."""
    import traceback
    from datetime import datetime

    from PySide6.QtWidgets import QMessageBox

    from .settings import cache_dir

    log = cache_dir() / "errors.log"
    showing = False

    def hook(exc_type, exc, tb) -> None:  # type: ignore[no-untyped-def]
        nonlocal showing
        text = "".join(traceback.format_exception(exc_type, exc, tb))
        try:
            log.parent.mkdir(parents=True, exist_ok=True)
            with open(log, "a", encoding="utf-8") as f:
                f.write(f"--- {datetime.now():%Y-%m-%d %H:%M:%S} (v{__version__})\n{text}\n")
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)
        if showing or QApplication.instance() is None:
            return
        showing = True
        try:
            QMessageBox.warning(None, "Media Manager — something went wrong",
                                f"{exc_type.__name__}: {exc}\n\nDetails were saved to:\n{log}")
        finally:
            showing = False

    sys.excepthook = hook


def main(argv: list[str] | None = None) -> int:
    argv = list(argv if argv is not None else sys.argv)
    app = QApplication(argv)
    if sys.platform == "win32":
        import ctypes

        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("MediaManager.MediaManager")
        except (AttributeError, OSError):
            pass
    if ICON.exists():
        app.setWindowIcon(QIcon(str(ICON)))
    if "--self-test" in argv:
        return self_test(argv[argv.index("--self-test") + 1])
    app.setApplicationName("Media Manager")
    app.setApplicationVersion(__version__)
    app.setOrganizationName("MediaManager")
    install_error_handler()
    window = build_window()
    window.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
    window.show()
    code = app.exec()
    # Everything that writes was finished and saved when the window closed (each part's closeEvent); any
    # reading still going on in the background (a slow network or OneDrive file) mustn't keep the program
    # running, with its window frozen on the screen, so it ends here.
    for stream in (sys.stdout, sys.stderr):  # (None in the installed app: it has no console)
        if stream is not None:
            try:
                stream.flush()
            except (OSError, ValueError):
                pass
    os._exit(code)
