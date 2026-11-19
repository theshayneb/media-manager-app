# Media Manager — notes for agents

Windows 11 desktop app, Python 3.12 + PySide6. Combines two existing apps plus a new part:

- `photo_manager/` — Photo Manager (theshayneb/photo-manager), copied as it is. Developed in its own repo;
  copy later versions in rather than changing it here. Its right-hand panel must NOT be changed (user's request).
- `music_manager/` — Music Manager (theshayneb/music-manger), copied as it is; same rule.
- `media_manager/` — the shell: `app.py` (start-up, `--self-test`), `shell.py` (`MediaWindow`: one grouped
  Folders list + a QStackedWidget with the three parts), `settings.py` (`%APPDATA%\MediaManager`),
  `movies/` (Movies & TV: `naming.py`, `files.py`, `window.py`, `watch.py` = the "● N new" alert).
- `bars.py` lays out every section's top bar the same way (user's "Option A"): it re-orders Photo/Music's
  own toolbar actions and widgets (shortcuts kept) and adds the 📂 folder button, ⚙ ▾, Photos' search and
  Music's Move to. Photos' menu row is hidden. Music's Tags and Photos' Details docks live in `MediaWindow`.
- Changed inside `music_manager/` on the user's request: the Tags panel's Rating row is on its own line;
  "Obsidian notes" (TXXX:Obsidian Notes / Vorbis OBSIDIAN NOTES, one line of text) on the Extra tab, above
  Obsidian tags; the tag cache accepts versions 9 and 10, and Music reads the Library at start when the cache
  has none of it (`_fill_cache`).
- `scrub.py`: every timeline slider jumps to a click and follows a drag (a QProxyStyle per slider; Photos'
  VideoView is patched before Photo Manager's window is built).
- `photo_edit.py` (curves per channel, saved like Photo Manager's crop: tags copied with ExifTool, original
  to the Recycle Bin, HEIC → JPG), `edit_view.py` (EditView: split-line compare + Hold for Before; its sliders
  in `.panel`) and `photo_edit.Turn` = rotate/flip (also `android/core` Turn.kt), `edit_mode.py` (EditMode: the view as a page of Photos' stack, the sliders dock in the
  Folders dock's place, Details untouched; ←/→, Save/Cancel/Shift+E; "Same as last edit" = settings.last_edit).
  Photo Manager's right-click menu has one hook for it: `extra_menu_items`. Tray: `MediaWindow._build_tray`.
- Changed inside `photo_manager/` for the ✨ edited mark: `metadata.READ_TAGS`/`Meta.edited`/`EDITED_MARK`
  (EXIF ProcessingSoftware) and `grid.paint_flags` (draws ✨ bottom-right).
  And for .af (Affinity) files: `media.AFFINITY_EXTS`/kind "affinity", `thumbs.affinity_preview` (its "Thmb" PNG);
  double-click opens it in Windows' app for .af (edit_mode `open_it`).
  And Group by "Subfolder" (`grid.scan_media`, GROUPS["folder"]) and each folder's own grouping
  (`settings.folder_groups`, `MainWindow.set_group`/`_show_group`/`open_folder`).
  And the week groups are the user's scrapbook weeks (`grid.album_week`/`album_week_dates`: Week 1 starts Jan 1,
  a first week under 4 days joins the next full week, the last ends Dec 31).
  And `preview.CropCanvas`: darker shade, green centre lines, snap to the middle, `nudge`/`centred`; and
  `open_external_selected` opens every selected file, the Open action also on Shift+X.
- `print_size.py` (Edit's 🖨 Print size: the user's Affinity crop presets + border macros as one tool; finished
  sizes at 600 DPI, an even 63 px border taken off the photo part, copies to settings.print_folder) and
  `layouts.py`/`layouts_panel.py` (the Layouts tab with Details: pockets read from layout pictures in
  settings.layouts_folder + assets/layouts; fit against the week's print copies, or, inside the print
  folder, the grid group of the selected picture; the spread = `layouts.Plan`, "Layout plan.json" in the print
  folder: right page chosen, next week's left page = its back, locked). Print size's Week sets the copy's date
  (`print_size.week_date`). Not built yet, on purpose: the half-width insert,
  dragging photos into pockets, and a pocket starting Print size with its size.
- `zoom.py`: mouse-wheel zoom/pan, used by the Edit window and patched into Photo Manager's preview CropCanvas.
- `android/`: the Android companion app (Kotlin; user's choice). `core/` is plain Kotlin and tested here
  (`gradle -p android :core:test`): Photo Manager's tag places (XMP dc:subject + IPTC keywords; PNG: XMP iTXt only, `Png.kt`; xmp:Label,
  xmp:Rating 5 = Star, xmpDM:good = Bookmark), templates/rename pattern, the edit maths (port of photo_edit.py),
  the ✨ mark as XMP photoshop:History. `app/` (Compose) is built by .github/workflows/android.yml (no Android
  SDK here); releases are `android-<android/version.txt>`. Sync: every change is done to the phone's photo and
  queued (SyncQueue) to be done to the same photo in OneDrive's Camera Roll (Microsoft Graph, device-code
  sign-in, the user's own Azure app ID). `media_manager/companion.py` writes OneDrive\Documents\Phone\Media Manager\companion.json.
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
