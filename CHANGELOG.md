# Changelog

## 0.2.2

- Top-bar icons follow one rule in every section: the shared buttons are small icons (✏️ Rename, ➡️ Move to,
  🗑 Delete, 📁 Show in Explorer, ⟳ Refresh, ⚙ Settings; point at one to see its name), and each section's
  own buttons are words without icons (Keep, Convert, Play, Song list ▾, View ▾…).
- Music's "Convert to MP3" button now says "Convert". Right-click menus keep the full names.

## 0.2.1

- Fixed: Photos' keyword chips and label buttons were giant again (and the panel cut off). Moving the panel
  out of Photo Manager's window had lost Photo Manager's own button styles; the panel keeps them now.
- Fixed: panels jumped to a very wide size when switching between sections. Each panel's size is
  remembered and put back.
- Collapsed photo groups are remembered for each folder and grouping, also after closing the app.

## 0.2.0

- Top bars laid out the same way in every section: the section's own buttons, then Rename · Move to ·
  Delete · Show in Explorer, then Search; on the right the 📂 folder button, ⟳ Refresh and ⚙ ▾.
  - Photos: the Tools / View menu row is gone (its menus are under ⚙ ▾ and ▦ View ▾); new Rename button and a
    search box (by name); the folder button opens, types or adds folders, so "Browse folders…" is gone
    from the Folders list.
  - Music: new Move to (with the lyrics .txt); the folder button holds Add Folder and the saved search.
  - Movies & TV: the folder button holds Add a Movies / TV Shows folder.
- Tags panel: Rating sits on its own line under the word Rating, so the panel can be about 80 px narrower.
- Photos' side panel (Preview, Labels, Keywords, Date taken, Rename) can be dragged to any edge like the others.
  It looks the same; it never opens narrower than its contents.

## 0.1.1

- Fixed: clicks were ignored all over the window (songs couldn't be picked one after another, photo group
  headings did nothing and had no right-click menu). The Movies player used Qt's video widget, which puts a
  separate native window inside the app; on Windows that stopped clicks and redraws elsewhere. Movies now
  draw their frames themselves, as Photo Manager's preview does.
- The Folders, Selected (album art + check-up) and Tags panels can each be dragged by their title to any
  edge of the window; where you put them is remembered. Selected and Tags show while Music is open.
- Movies & TV: a long folder path in the toolbar no longer pushes the player off the window.

## 0.1.0

- First version: Photo Manager 0.13.0 and Music Manager 0.8.2 in one window, plus Movies & TV.
- One Folders list grouped by kind (Photos & Videos, Music, Movies & TV). Photo favorites, Photo Manager's
  folder tree (📂 Browse folders…), music views and saved searches, and Movies / TV Shows folders.
- Photos can still be dropped on a photo folder in the list to move them there (Ctrl to copy).
- Music's album art card and library check-up sit under the Folders list while Music is open.
- Movies & TV: list and play videos; Rename for Plex with a preview; Rename (F2); Move to; Delete; Show in Explorer.
  Subtitles and .nfo files follow their video.
- Only one thing plays at a time: switching kinds pauses what was playing.
