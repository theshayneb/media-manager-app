"""Finding, renaming, moving and deleting movie / episode files (with their subtitles)."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from send2trash import send2trash

from music_manager.core.fileops import friendly_error, move_file, same_path, unique_path

from .naming import companion_target, companions, is_video, plex_name

SKIP_DIRS = {"@eadir", "#recycle", "$recycle.bin", "system volume information", ".thumbnails", "sample", "samples"}


@dataclass
class Video:
    path: str
    size: int

    @property
    def name(self) -> str:
        return os.path.basename(self.path)

    @property
    def folder(self) -> str:
        return os.path.dirname(self.path)


def list_videos(folder: str) -> list[Video]:
    """Every video in folder and its subfolders (TV seasons), by name."""
    out: list[Video] = []
    if not folder or not os.path.isdir(folder):
        return out
    for root, dirs, files in os.walk(folder, onerror=lambda _e: None):
        dirs[:] = [d for d in dirs if not d.startswith(".") and d.lower() not in SKIP_DIRS]
        for f in files:
            if is_video(f):
                p = os.path.join(root, f)
                try:
                    out.append(Video(p, os.path.getsize(p)))
                except OSError:
                    pass
    return sorted(out, key=lambda v: v.path.casefold())


def rename_plan(videos: list[Video], kind: str) -> list[tuple[Video, str | None, str]]:
    """[(video, new path or None, note)]: Plex-style names, never clashing with other files."""
    out = []
    taken: set[str] = set()
    for v in videos:
        new = plex_name(v.name, kind)
        if not new or new == v.name:
            out.append((v, None, "already named well" if new == v.name else "no year or episode number found"))
            continue
        target = unique_path(Path(v.folder) / new, taken, ignore=v.path)
        taken.add(os.path.normcase(str(target)))
        if same_path(target, v.path) and target.name == v.name:
            out.append((v, None, "already named well"))
        else:
            out.append((v, str(target), ""))
    return out


def move_video(src: str, dest: str) -> str:
    """Move or rename a video and its subtitles/.nfo; returns where it went."""
    extras = companions(src)
    move_file(src, dest)
    for extra in extras:
        target = companion_target(extra, src, dest)
        if not os.path.exists(target):
            try:
                move_file(extra, target)
            except OSError:
                pass
    return dest


def rename(plan: dict[str, str]) -> tuple[dict[str, str], list[tuple[str, str]]]:
    done, failures = {}, []
    for src, dest in plan.items():
        try:
            if os.path.exists(dest) and not same_path(src, dest):
                raise FileExistsError(f"{os.path.basename(dest)} already exists")
            done[src] = move_video(src, dest)
        except OSError as exc:
            failures.append((src, friendly_error(exc)))
    return done, failures


def move(paths: list[str], folder: str) -> tuple[dict[str, str], list[tuple[str, str]]]:
    done, failures = {}, []
    for p in paths:
        try:
            dest = unique_path(Path(folder) / os.path.basename(p))
            done[p] = move_video(p, str(dest))
        except OSError as exc:
            failures.append((p, friendly_error(exc)))
    return done, failures


def recycle(paths: list[str]) -> list[tuple[str, str]]:
    failures = []
    for p in paths:
        extras = companions(p)
        try:
            send2trash(p)
        except OSError as exc:
            failures.append((p, friendly_error(exc)))
            continue
        for extra in extras:
            try:
                send2trash(extra)
            except OSError:
                pass
    return failures
