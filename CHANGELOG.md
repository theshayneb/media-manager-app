# Changelog

## 0.5.0

- Edit now opens inside the main window, like the big preview: the photo (with Hold for Before · Reset ·
  Cancel · Save under it) in the photo area, the sliders in the Folders panel's place, and Photos' Details
  panel where you keep it, so you can label, add keywords, set dates and rename while editing. Leaving Edit
  brings the Folders panel back.
- ←/→ go to the previous/next photo while editing (asking "Save the edit?" first if you changed something).
- "Auto all" is gone. "Pick white" and a new "Same as last edit" (sets every slider the way you saved the
  previous photo) sit between the adjustments and the colour sliders.
- The mouse wheel also zooms out, below fit-to-screen (down to a quarter), in the Edit view and the big preview.

## 0.4.5

- Photos saved from the Edit window show ✨ in a dark circle in the bottom-right corner of their thumbnail
  (and in the big preview). The mark is kept in the photo itself (EXIF ProcessingSoftware "Media Manager
  edit"), so it stays when the photo is renamed, moved or copied. Photos edited before 0.4.5 don't have it.

## 0.4.4

- Edit window: a Brightness slider (darker ← → brighter mid-tones; black and white stay put), with its
  checkbox, ↺ and A (Auto all includes it).
- Mouse-wheel zoom, towards the pointer, in the Edit window and in Photos' big preview. While zoomed in, drag
  to look around (in the Edit window, drag near the line to move the line).
- Shift+E also closes the Edit window (it asks "Save the edit?" if you changed anything).

## 0.4.3

- Edit window: a DETAIL section with Sharpness (none → more) and Clarity (softer ← → more punch: contrast in
  the mid-tones over larger areas, for texture, clouds and fabric). Each has its checkbox, ↺ and A; Auto all
  sets a gentle, print-friendly amount of both. Their size follows the photo's, so the preview matches the
  saved full-size photo; dragging them stays quick.

## 0.4.2

- Edit window: a checkbox on the left of every slider. Untick it to see the photo as if that slider had never
  been moved (it's left out when saving too); its value is kept, so ticking it again brings it back.
- Saturation sliders: All colours, then Red, Orange, Yellow, Green, Aqua, Blue, Purple and Pink
  (less colour ← → more colour), each with its ↺ and checkbox.
- The sliders sit in one column you can scroll: LIGHT & COLOUR, then SATURATION.

## 0.4.1

- Edit window: opens maximized (it has Minimize / Maximize buttons now); the before/after line starts at the
  left, so you see the whole edit first.
- Each slider: click a spot to jump there; a ↺ arrow puts it back to 0; an "A" sets it from the photo.
  "Auto all" sets all five.
- White balance: "Pick white", then click something in the photo that should be white or grey; the two colour
  sliders move to make it neutral.
- The sliders are about twice as strong at their ends.

## 0.4.0

- Photos: Edit (button after Convert, Shift+E, or right-click → Edit…). Five sliders: Blue ↔ Yellow,
  Green ↔ Red, Contrast, Shadows, Highlights. The photo shows the original left of a line and the edit right
  of it (drag the line); hold "Hold for Before" or the space bar to see the whole original. Save replaces the
  photo, keeping its date taken, keywords, labels and other details; the original goes to the Recycle Bin.
  HEIC photos are saved as JPG.
- Minimize to the tray: the minimize button hides Media Manager to the tray; click the icon to bring it back.
  Right-click the icon for Show, a "Minimize to the tray" tick (to turn it off) and Quit.
- No pop-up after a Steam import (the status bar says how many were imported).

## 0.3.2

- Music: the check-up no longer shows "Kept this week".
- Photos: a Steam import button in the top bar, between Convert and Open (still also under ⚙).
- Fixed: a light line along the top of every top bar made it look out of step with the panel titles beside
  it. The bars keep their height and their bottom line.

## 0.3.1

- Fixed: the Obsidian tag chips were gone. 0.3.0 reset Music's tag cache, so it knew no tags until the Library
  was opened again. The cache is kept now, and when it has nothing from the Library, the Library is read in the
  background at start-up (chips, drop-downs and the check-up know its songs straight away).
- Obsidian notes is one line now, above Obsidian tags (the chips stay right under the tags).

## 0.3.0

- Scrubbing: every playback timeline (Music, Photos videos, Movies & TV) jumps to where you click and
  follows the mouse while you drag, playing from there (Music used to jump only when you let go).
- Music: new "Obsidian notes" box on the Tags panel's Extra tab. Saved in the file as TXXX:Obsidian Notes (MP3) /
  OBSIDIAN NOTES (FLAC), one value; also in the Keep review.
  For the Obsidian Media Manager plugin to add to a note's Notes property.

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
