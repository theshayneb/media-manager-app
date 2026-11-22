"""The phone's "Import now" for Steam screenshots (no Qt). The Android app can't see Steam's folder, so it leaves a
request in OneDrive (Documents\\Phone\\Media Manager\\steam-request.json); Media Manager on this PC sees it,
runs the same import as Photos' Steam import (its settings: Steam folder, account, extra folders, where to,
date and keyword), and writes what happened to steam-result.json for the phone to show."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

FOLDER = Path("Documents") / "Phone" / "Media Manager"
REQUEST = FOLDER / "steam-request.json"
RESULT = FOLDER / "steam-result.json"


def pending_request(root: Path) -> str | None:
    """The id of a request not answered yet, or None."""
    try:
        asked = json.loads((root / REQUEST).read_text(encoding="utf-8")).get("id")
    except (OSError, ValueError, AttributeError):
        return None
    if not asked:
        return None
    try:
        done = json.loads((root / RESULT).read_text(encoding="utf-8"))
        if done.get("id") == asked and done.get("state") != "running":
            return None
    except (OSError, ValueError, AttributeError):
        pass
    return str(asked)


def write_result(root: Path, request_id: str, state: str, **extra) -> None:  # type: ignore[no-untyped-def]
    data = {"id": request_id, "state": state, "time": datetime.now().isoformat(timespec="seconds"), **extra}
    path = root / RESULT
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        pass


def plan(settings):  # type: ignore[no-untyped-def]
    """What the Steam import dialog would offer, without the dialog: (plan, log path, seen in dest).
    Names games that aren't installed here (played on the Steam Deck) from the Steam store first."""
    from photo_manager.core import steam
    from photo_manager.core.templates import match_any

    dest = settings.steam_dest
    if not dest:
        raise ValueError("Choose where Steam screenshots go first (Photos › Steam import on the PC)")
    path = settings.steam_path or steam.find_steam() or ""
    account = settings.steam_account or None
    shots = steam.find_screenshots(path, account, settings.steam_extra_folders, settings.steam_game_names)
    missing = [a for a in steam.unnamed_app_ids(shots) if a not in settings.steam_game_names]
    if missing:
        names = steam.fetch_store_names(missing[:50])
        if names:
            settings.steam_game_names.update(names)
            settings.save()
            shots = steam.find_screenshots(path, account, settings.steam_extra_folders, settings.steam_game_names)

    def date_of_name(name: str):  # type: ignore[no-untyped-def]
        found = match_any(settings.templates, name)
        return found[1] if found else None

    log = settings.path.parent / "steam_imported.txt"
    seen = steam.found_in_dest(shots, dest, date_of_name)
    return steam.plan_import(shots, dest, steam.load_log(log) | seen), log, seen


def run(settings, et):  # type: ignore[no-untyped-def]
    """The import itself (as Photos' Steam import does it). Returns (done, failures)."""
    from photo_manager.core import steam
    from photo_manager.core.metadata import date_args, keyword_args

    todo, log, seen = plan(settings)
    done, failures = steam.import_shots(todo)
    steam.add_to_log(log, seen | {steam.shot_key(shot) for shot, _ in done})
    if et is not None:
        for shot, target in done:
            if settings.steam_set_date and shot.taken:
                et.write(target, date_args(target, shot.taken, True))
            if settings.steam_keyword:
                et.write(target, keyword_args(target, add=[shot.game]))
    return done, failures


def summary(done, failures) -> dict:  # type: ignore[no-untyped-def]
    games: dict[str, int] = {}
    for shot, _ in done:
        games[shot.game] = games.get(shot.game, 0) + 1
    return {"imported": len(done), "failed": len(failures), "games": games,
            "problem": failures[0][1] if failures else ""}
