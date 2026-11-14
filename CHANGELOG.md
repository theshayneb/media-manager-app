# Changelog

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
