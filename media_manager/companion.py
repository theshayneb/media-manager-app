"""Settings the Android companion app needs, shared through OneDrive: the keyword sets (the phone shows
their buttons but doesn't edit them), the rename pattern, the "date from file name" templates and the last
edit. Written to <OneDrive>\\Documents\\Phone\\Media Manager\\companion.json when Media Manager starts and closes."""

from __future__ import annotations

import json
import os
from pathlib import Path

FILE = Path("Documents") / "Phone" / "Media Manager" / "companion.json"
OLD_FILE = Path("Media Manager") / "companion.json"  # where 0.6.0 put it (moved, at the user's request)


def onedrive_folder() -> Path | None:
    """The PC's OneDrive folder (Windows sets %OneDrive%), or None."""
    for name in ("OneDriveConsumer", "OneDrive"):
        value = os.environ.get(name)
        if value and os.path.isdir(value):
            return Path(value)
    return None


def companion_data(photo_settings, media_settings) -> dict:  # type: ignore[no-untyped-def]
    return {
        "version": 1,
        "keyword_sets": photo_settings.keyword_sets,
        "current_keyword_set": photo_settings.current_keyword_set,
        "rename_pattern": photo_settings.rename_pattern,
        "templates": [t.to_dict() for t in photo_settings.templates],
        "week_start": getattr(photo_settings, "week_start", "sunday"),
        "last_edit": media_settings.last_edit,
    }


def write(photo_settings, media_settings, folder: Path | None = None) -> Path | None:  # type: ignore[no-untyped-def]
    """Write companion.json if it changed; returns its path (None without OneDrive)."""
    root = folder or onedrive_folder()
    if root is None:
        return None
    path = root / FILE
    text = json.dumps(companion_data(photo_settings, media_settings), indent=2, ensure_ascii=False)
    try:
        if path.exists() and path.read_text(encoding="utf-8") == text:
            _remove_old(root)
            return path  # unchanged: don't make OneDrive upload it again
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(text, encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        return None
    _remove_old(root)
    return path


def _remove_old(root: Path) -> None:
    old = root / OLD_FILE
    try:
        if old.exists():
            old.unlink()
        if old.parent.exists() and not any(old.parent.iterdir()):
            old.parent.rmdir()
    except OSError:
        pass
