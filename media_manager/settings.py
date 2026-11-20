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
    movie_volume: int = 70
    movie_seen: dict = field(default_factory=dict)  # Movies & TV folder -> the videos seen there (new ones alert)
    # The scrapbook: where Print size saves its copies, and the page layouts (pictures of pockets).
    print_folder: str = r"C:\Users\talkt\Documents\Dashboard\Hobbies\Digital Craft Supplies\Project Life"
    layouts_folder: str = r"C:\Users\talkt\Documents\Dashboard\Hobbies\Digital Craft Supplies\Digital Templates"
    print_grey: str = "D"       # the printer's colour fix (Print sheet's colour check): A cooler … D none … G warmer
    print_brown: str = "D"
    printer_profile: str = "auto"  # the printer + paper ICC profile Print sheet converts for ("" none; "auto": find
                                   # the iP8700 series' Matte Photo Paper one the first time)
    last_print_week: str = ""   # Print size's Week chosen last ("2026-46"): where a card without a date goes
    minimize_to_tray: bool = True  # the minimize button hides the window to the tray
    last_edit: dict = field(default_factory=dict)  # the sliders of the last photo saved ("Same as last edit")
    window_geometry: str = ""
    template_folded: list = field(default_factory=list)  # Photo Templates' size groups folded shut
    folder_order: dict = field(default_factory=dict)      # Folders list: kind -> its entries' keys, in order
    dock_sizes: dict = field(default_factory=dict)        # panel name -> its width (or height)
    photo_collapsed: dict = field(default_factory=dict)   # "<folder>|<group by>" -> collapsed group titles
    window_state: str = ""        # where the Folders, Selected and Tags panels are

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
