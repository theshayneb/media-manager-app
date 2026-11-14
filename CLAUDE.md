# Media Manager — notes for agents

Windows 11 desktop app, Python 3.12 + PySide6. Combines two existing apps plus a new part:

- `photo_manager/` — Photo Manager (theshayneb/photo-manager), copied as it is. Developed in its own repo;
  copy later versions in rather than changing it here. Its right-hand panel must NOT be changed (user's request).
- `music_manager/` — Music Manager (theshayneb/music-manger), copied as it is; same rule.
- `media_manager/` — the shell: `app.py` (start-up, `--self-test`), `shell.py` (`MediaWindow`: one grouped
  Folders list + a QStackedWidget with the three parts), `settings.py` (`%APPDATA%\MediaManager`),
  `movies/` (Movies & TV: `naming.py`, `files.py`, `window.py`).
- Each part keeps its own settings file, so the user's existing Photo/Music settings carry over.
- Tests: `python -m pytest` (`tests/photo`, `tests/music`, `tests/shell`); GUI tests run offscreen.
  ffmpeg in `vendor/ffmpeg` or on PATH, ExifTool in `vendor/exiftool`.
- Ruff covers everything except the copied `photo_manager` (and its tests).
- Release: bump `media_manager/__init__.py` and `pyproject.toml`, add a CHANGELOG entry, push to main;
  CI builds, self-tests the exe and publishes the release.

The user's requirements (keep them):
- Everything must work with Plex, Plexamp and Symfonium. Show mock-ups before visual changes;
  never make visual changes that weren't asked for.
- Music: flat library in OneDrive; lyrics embedded AND `<song>.txt`; no cover.jpg; ratings in files; MP3 V0;
  never re-encode MP3s.
- Keep it simple and reliable.
