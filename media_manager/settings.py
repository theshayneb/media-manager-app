"""Media Manager's own settings (%APPDATA%\\MediaManager\\settings.json): the Movies & TV folders and
where you were. Photos and Music keep using their own settings files, so nothing had to move."""

from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from pathlib import Path

APP_NAME = "MediaManager"


def config_dir() -> Path:
    base = os.environ.get("APPDATA") or os.path.join(Path.home(), ".config")
    return Path(base) / APP_NAME


def cache_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA") or os.path.join(Path.home(), ".cache")
    return Path(base) / APP_NAME


@dataclass
class MediaSettings:
    movie_folders: list[dict] = field(default_factory=list)  # [{"path", "label", "kind": "movies" | "tv"}]
    last_kind: str = "music"      # photos | music | movies
    last_key: str = ""            # the entry of the Folders list that was open
    photo_tree: bool = False      # Photo Manager's own folder tree shown
    movie_volume: int = 70
    window_geometry: str = ""
    splitter_state: str = ""

    path: Path = field(default_factory=lambda: config_dir() / "settings.json", repr=False)

    @classmethod
    def load(cls, path: Path | None = None) -> "MediaSettings":
        s = cls()
        if path:
            s.path = path
        try:
            data = json.loads(s.path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return s
        for key, value in data.items():
            if key != "path" and hasattr(s, key) and type(getattr(s, key)) is type(value):
                setattr(s, key, value)
        return s

    def save(self) -> None:
        data = asdict(self)
        data.pop("path", None)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, self.path)
