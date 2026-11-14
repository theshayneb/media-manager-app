# Media Manager

One Windows app for all your media: reviewing, tagging, renaming, moving and playing it.

- **Photos & Videos**: Photo Manager, exactly as it is (labels, keywords, dates, rename, convert, crop, imports).
- **Music**: Music Manager, exactly as it is (Review → Keep, tags, lyrics, album art, Plex ratings and play counts).
- **Movies & TV**: browse and play your movie and TV files, rename them the way Plex wants
  (`Title (Year).mkv`, `Show - S01E02 - Episode Title.mkv`) with a preview first, move them,
  delete them (to the Recycle Bin) and show them in Explorer. Subtitles (`.srt`) and `.nfo` files go with their video.

The Folders list on the left holds all three kinds; the rest of the window follows what you pick.

## Download

Get `MediaManager-windows.zip` from the [latest release](../../releases/latest), unzip it anywhere,
and run `MediaManager.exe`. ExifTool and ffmpeg are included.

Your Photo Manager and Music Manager settings (favorites, folders, templates, saved searches, Plex)
are used as they are: Media Manager reads the same settings files, so nothing needs setting up again.
Media Manager's own settings (Movies & TV folders, window layout) are in `%APPDATA%\MediaManager`.

## Run from source

`run.bat` (needs Python 3.11+), or:

```
python -m venv .venv
.venv\Scripts\pip install -r requirements-dev.txt
powershell -File scripts\get-exiftool.ps1
powershell -File scripts\get-ffmpeg.ps1
.venv\Scripts\python -m media_manager
```

Tests: `python -m pytest`. Build: `scripts\build.ps1`.
