"""Noticing new videos in the Movies & TV folders, so the Folders list can show "● 2 new" until you look.

Media Manager remembers, per folder, the videos you've seen there (settings.movie_seen). Anything else that
turns up is new. The first look at a folder only learns what's there (nothing is new then), and opening a
folder in Movies & TV counts as seeing everything in it.
"""

from __future__ import annotations

import os

from . import files


def _key(path: str) -> str:
    return os.path.normcase(os.path.normpath(path))


def scan(folders: list[str]) -> dict[str, list[str]]:
    """{folder: its video paths} for the folders that can be read now (a disconnected drive is left out,
    so its videos aren't forgotten or reported again)."""
    return {f: [v.path for v in files.list_videos(f)] for f in folders if f and os.path.isdir(f)}


class Watch:
    def __init__(self, seen: dict[str, list[str]]):
        self.seen = seen  # the settings' dict, changed in place

    def new(self, folder: str, current: list[str]) -> list[str]:
        """The videos in folder that weren't there before (learning the folder the first time)."""
        if folder not in self.seen:
            self.seen[folder] = list(current)
            return []
        known = {_key(p) for p in self.seen[folder]}
        return [p for p in current if _key(p) not in known]

    def mark_seen(self, folder: str, current: list[str]) -> None:
        self.seen[folder] = list(current)

    def add_seen(self, paths: list[str]) -> None:
        """Videos Media Manager put somewhere itself (Move to): not new in a watched folder they landed in."""
        for folder, known in self.seen.items():
            base = _key(folder).rstrip("\\/") + os.sep
            known.extend(p for p in paths if _key(p).startswith(base))

    def forget(self, keep: list[str]) -> None:
        """Drop folders no longer in the list."""
        for folder in [f for f in self.seen if f not in keep]:
            del self.seen[folder]
