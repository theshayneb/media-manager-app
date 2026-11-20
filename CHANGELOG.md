# Changelog

## 0.7.0

- Photos: 🖨 Print sheet (Shift+S, also right-click). The selected print copies laid out on 8.5 × 11 paper to
  waste as little as possible (as few sheets as it can, portrait or landscape, photos turned sideways when that
  fits more on; upright when it fits just as well), touching edge to edge, cuttable in straight passes, and
  centred on the paper at their real size (never resized; 1/8 in kept clear at the edges).
  - Light grey crop marks in the white round the photos (never on one).
  - ☀ Brighter per photo, each its own amount (21% to start, your Affinity brightness layer), on the sheet only.
  - Turn selected, Auto-arrange, and drag a photo onto another the same size to swap them.
  - Print… prints straight from Media Manager; Save sheets writes "Week 46 - Sheet 1.jpg" (600 DPI) in
    Project Life (the Layouts panel doesn't count saved sheets as print copies).
  - Printed print copies get a 🖨 in a dark circle, bottom-right (next to ✨).

## 0.6.15

- Fixed: closing 0.6.14 showed "AttributeError: 'NoneType' object has no attribute 'flush'" (and could leave it
  running). The installed app has no console window to flush.

## 0.6.14

- Fixed: after closing, Media Manager could stay running with its title bar frozen on the screen. It waited for
  the template tabs to finish reading Digital Templates (every PSD, start to end, in OneDrive: a download for
  online-only files). Now closing doesn't wait for anything that only reads, and the program always ends.
- The template tabs read only a PSD's layer list (a few KB), and its thumbnail once (kept with Photos'
  thumbnails), instead of the whole file every time something in the folder changed.

## 0.6.13

- Photos shows Photoshop files (.psd) with their picture, at any thumbnail size; double-click opens one in its
  program. (Like .af files, nothing is written to them.)
- Group by → Template size: the files' names' sizes, as the Photo Templates tab: Layouts (PL) first, then 3x4,
  6x4, 3x8, 4x4, 6x8, 6x12, any other size, and "No size in the name". Remembered for that folder only.

## 0.6.12

- Two tabs behind Details instead of five:
  - Layouts (as before 0.6.11): only your page-protector layouts, the "PL …" JPGs (and the three built in),
    with the week's spread, the plan and "fits".
  - Photo Templates: every other template in Digital Templates (the cards and pages that go inside a pocket),
    grouped by the size their names start with: 3x4, 6x4, 3x8, 4x4, 6x8, 6x12 (any other size gets its own
    group too), then Other. Click a heading to fold it; double-click a template to open it in Affinity.
  Both update by themselves when you add or rename a file.

## 0.6.11

- The Layouts tab is now "6x8": your hand-drawn PL pages and the 6x8 PSDs ("6x8 - …"). A PSD's photo spots are
  its layers named with "photo" (photo, clip photo, 1-PHOTO, PHOTO HERE…), counted tall/wide like pockets.
- New tabs behind Details for the other templates in Digital Templates, by the size their names start with:
  3x4 + 6x4, 3x8, 4x4, and Other (6x12, and anything without a size). Each shows the thumbnail, the name and
  how many photo spots it has; double-click opens it (in Affinity).
- All the tabs update by themselves when you add, rename or delete a template (a renamed one moves to its new
  tab). Subfolders of Digital Templates count too.

## 0.6.10

- Crop and Print size: the cut-off area is darker; the arrow keys nudge the box (Shift: 10× as far); green
  lines show when the box is in the middle left-right or top-bottom, and dragging or nudging it stops there.
- Print size: a button for each size (3x4, 6x4, 3x8, 6x8), then White border, then Week.
- Open (Ctrl+O, and now Shift+X) opens every selected file, not just one (an open Affinity gets them all).
- Folders panel: drag a folder up or down within its section to put them in your order. While you drag photos
  over a photo folder, that folder lights up.
- Layouts: the "Next…" and "Double-click…" lines are gone, and so is the ✗ before "needs…".

## 0.6.9

- Print size: the bar no longer shows the pixel size, DPI and inches (only Size, White border and Week).

## 0.6.8

- Weeks are your scrapbook's weeks everywhere (Group by Week taken, Print size, Layouts): each year's Week 1
  starts on January 1, and a short first week is part of Week 1 (2026: Jan 1–10, 2027: Jan 1–9); the last
  week ends on December 31. Today is Week 46.
- Print size: Week ▾. The print copy gets a date taken in that week, so cards without a date go in their week
  too. A photo starts with its own week, a card with the week you chose last. A photo printed for another week
  is moved into it by whole weeks (the original isn't touched).
- Layouts: the week's spread. Double-click a layout (or right-click → Use for the right page) to put it on
  this week's right page; the back of that sheet is next week's left page, shown 🔒 and mirrored. "Fits" is
  for the whole spread, and the panel says what next week's locked page will need, so you can crop ahead.
  Week 1 starts the album: both its pages are yours to choose. The plan is saved in Project Life as
  "Layout plan.json".

## 0.6.7

- Photos: Group by → Subfolder. The open folder's subfolders (Week 1, Week 2… in number order) each become a
  group, with the files that aren't in a subfolder under "In this folder".
- Each folder keeps its own grouping: change it in one folder and the others stay as they were. Folders you
  haven't set use the grouping you had before.
- Layouts: in the Project Life folder (or a folder in it), the panel counts the group you've selected in the grid
  (a subfolder, a week, "No date taken"…), whether the pictures have a date or not. Elsewhere it counts the
  print copies from the selected photo's week, as before.

## 0.6.6

- Photos shows Affinity documents (.af) with a thumbnail (the preview Affinity keeps inside the file); double-click
  or Enter opens one in Affinity (whatever Windows opens .af files with). Nothing is written to them.

## 0.6.5

- Fixed: Layouts showed as a panel of its own (next to Details, taking room) instead of behind Details. It's a
  tab of Details again, wherever your Details panel is (also if you move it): click Layouts at the bottom of
  the panel to bring it over Details, Details to go back.

## 0.6.4

- Edit: 🖨 Print size (P), for the scrapbook. Pick 3x4 (tall), 6x4 (wide), 3x8 or 6x8 and tick White border or
  not; the crop box takes the right shape. Save print copy makes "IMG_2041 - 3x4 Border.jpg" in the Project Life
  folder: cropped, resized to your Affinity sizes at 600 DPI (3x4 = 1782 × 2340 px, 6x4 = 3520 × 2340 px…),
  with an even white border (63 px, 0.105 in) inside that size, JPG at top quality, its date and keywords kept,
  your sliders and flip/rotate included. The original isn't touched; a name that's taken gets (2), (3)…
- Layouts: a tab next to Details (Photos). Your page layouts from Digital Templates (any picture of the boxes;
  the three you sent are built in), each with its tall and wide pockets, and whether the print copies from the
  selected photo's week fill it.
## 0.6.3

- Edit and the big preview keep your zoom when you go to the previous/next photo (←/→); it goes back to
  fitted when you close Edit or the big preview.

## 0.6.2

- Edit: ⇋ Flip ▾ (Flip horizontal H, Flip vertical V) and ↻ Rotate (R, 90° clockwise), right of Crop. Shown at
  once (Before too), saved with Save like the sliders (✨, original to the Recycle Bin), undone by Reset/Cancel.
  A crop drawn after turning follows the photo as you see it. "Same as last edit" keeps to the sliders.
- The Android app (0.1.8) has the same ⇋ Flip and ↻ buttons; a turn made on the phone is done to the OneDrive
  copy too.

## 0.6.1

- Movies & TV: when a video is dropped into one of your folders, the folder turns orange in the Folders list with
  "● N new" (hover for the names), and a note pops up by the clock (click it to open the folder). Opening the
  folder clears it. Folders are checked every minute; videos you move there with Move to… don't count as new.
- companion.json (for the Android app) moved to OneDrive › Documents › Phone › Media Manager; the old
  OneDrive › Media Manager folder is removed.

## 0.6.0

- For the Android companion app: Media Manager keeps OneDrive › Media Manager › companion.json up to date (your
  keyword sets, rename pattern, "date from file name" templates and last edit), so the phone uses the same ones.
- Photos edited on the phone show ✨ too (the phone marks them in XMP photoshop:History, as it can't write the
  EXIF tag the PC uses).

## 0.5.2

- Shift+P opens and closes the big preview again, for photos too (Shift+E is Edit).
- Double-clicking (or Enter on) a photo opens Edit; a video opens the big preview.

## 0.5.1

- Fixed: Sharpness hardly did anything (about 0.3/255 on a phone photo, invisible). It now sharpens about 4 px
  on a 4032 px photo, up to 4×; the preview matches the saved photo.
- Photos open in Edit instead of the big preview: double-click, Enter, Shift+P and right-click → Preview.
  The big preview is left for videos and for comparing several photos; it has no Close button (Esc closes).
- Crop is in the Edit view, as it was in the big preview: Crop (C) above the photo, then Aspect ratio · Save as
  a copy · Save crop (Enter) · Cancel. The sliders are kept; right-click → Crop… opens Edit and starts cropping.
- The Folders panel shows only with the photo list (not in Edit or the big preview).
- A "Move to…" button at the bottom of the Details panel, under Rename (same as right-click → Move to…).
- Delete while editing sends the photo to the Recycle Bin and goes on to the next one (Move to… does too).
- The Details panel's section headings are a little bigger.

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
