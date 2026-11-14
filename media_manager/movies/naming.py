"""Movie and TV file names the way Plex wants them.

Movies:  "Title.of.Movie.2019.1080p.BluRay.x264-GRP.mkv" -> "Title of Movie (2019).mkv"
         (Photo Manager's video import does the same, and its rules are used as they are.)
Episodes: "Show.Name.S01E02.Episode.Title.720p.WEB.mkv" -> "Show Name - S01E02 - Episode Title.mkv"
          "Show Name 1x02.mkv"                          -> "Show Name - S01E02.mkv"

A subtitle or other file named like the video ("Movie.en.srt", "Movie.nfo") follows it.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

from photo_manager.core.folder_import import movie_name

VIDEO_EXTENSIONS = {".mkv", ".mp4", ".m4v", ".avi", ".mov", ".wmv", ".webm", ".ts", ".m2ts", ".mts", ".mpg",
                    ".mpeg", ".flv", ".3gp"}
COMPANION_EXTENSIONS = {".srt", ".ass", ".ssa", ".sub", ".idx", ".vtt", ".nfo", ".txt", ".jpg", ".png"}

# Where the useful part of a downloaded name ends: quality, source, codec, group tags.
_JUNK = re.compile(
    r"\b(2160p|1080p|1080i|720p|576p|480p|4k|uhd|hdr|hdr10|dv|web[- ]?dl|webrip|web|bluray|blu[- ]?ray|brrip|"
    r"bdrip|dvdrip|hdtv|hdrip|x264|x265|h ?264|h ?265|hevc|avc|aac|ac3|dd5 ?1|ddp5 ?1|atmos|10bit|proper|repack|"
    r"internal|amzn|nf|dsnp|hmax|atvp|hulu|extended|multi)\b.*$", re.IGNORECASE)
_EPISODE = re.compile(r"^(?P<show>.*?)[\s._-]*(?:[Ss](?P<s>\d{1,2})[\s._-]*[Ee](?P<e>\d{1,3})"
                      r"(?:[\s._-]*-?[Ee]\d{1,3})*|(?P<s2>\d{1,2})[xX](?P<e2>\d{2,3}))(?P<rest>.*)$")


def is_video(path: str | Path) -> bool:
    return Path(path).suffix.lower() in VIDEO_EXTENSIONS


def _words(text: str) -> str:
    text = re.sub(r"^\s*(\[[^\]]*\]\s*)+", "", text)  # "[group] ..." in front
    text = re.sub(r"[._]+", " ", text)
    text = _JUNK.sub("", text)
    text = re.sub(r"\s*-\s*[A-Za-z0-9]+$", "", text) if re.search(r"-[A-Za-z0-9]+$", text.strip()) and \
        not re.search(r"\s-\s", text) else text  # "-GROUP" at the very end
    return " ".join(text.replace("[", " ").replace("]", " ").split()).strip(" -")


def episode_name(filename: str) -> str | None:
    """"Show.S01E02.Title.720p.mkv" -> "Show - S01E02 - Title.mkv"; None if there's no SxxEyy / 1x02."""
    stem, ext = os.path.splitext(filename)
    if ext.lower() not in VIDEO_EXTENSIONS:
        stem, ext = filename, ""
    m = _EPISODE.match(stem)
    if not m:
        return None
    season = int(m.group("s") or m.group("s2"))
    episode = int(m.group("e") or m.group("e2"))
    show = _words(m.group("show") or "")
    show = re.sub(r"\s*\(?\b(19|20)\d{2}\b\)?$", lambda y: f" ({y.group(0).strip(' ()')})", show).strip()
    if not show:
        return None
    title = _words(m.group("rest") or "")
    title = re.sub(r"^\s*-\s*", "", title)
    name = f"{show} - S{season:02d}E{episode:02d}"
    return f"{name} - {title}{ext}" if title else f"{name}{ext}"


def plex_name(filename: str, kind: str) -> str | None:
    """The Plex-style name for a file in a Movies ("movies") or TV ("tv") folder; None = keep the name."""
    if kind == "tv":
        return episode_name(filename)
    return movie_name(filename) if not episode_name(filename) else None


def companions(path: str) -> list[str]:
    """Files that belong to a video: same name, then ".srt", ".en.srt", ".nfo"... in the same folder."""
    p = Path(path)
    out = []
    try:
        for other in p.parent.iterdir():
            if other == p or not other.is_file():
                continue
            name = other.name
            if name.lower().startswith(p.stem.lower() + ".") and other.suffix.lower() in COMPANION_EXTENSIONS:
                out.append(str(other))
    except OSError:
        pass
    return out


def companion_target(companion: str, video: str, new_video: str) -> str:
    """"Old.en.srt" for "Old.mkv" -> "New.en.srt" for "New.mkv"."""
    old_stem, new_stem = Path(video).stem, Path(new_video).stem
    name = Path(companion).name
    return str(Path(new_video).with_name(new_stem + name[len(old_stem):]))
