"""Editing inside the main window (the user's layout): the Edit view takes Photos' photo area, like the big
preview; its sliders take the Folders panel's place; Photos' Details panel stays where it is, for labels,
keywords, dates and renaming while editing. ←/→ go through the folder; Shift+E, Cancel or Save leave."""

from __future__ import annotations

import os
from dataclasses import asdict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

from photo_manager.core.media import kind

from .edit_view import EditView
from .photo_edit import can_edit, save_in_photos


class EditMode:
    def __init__(self, shell) -> None:  # type: ignore[no-untyped-def]
        self.shell, self.photos = shell, shell.photos
        self.view = EditView()
        self.photos.stack.addWidget(self.view)
        self.dock = shell._dock("Edit", "media-edit", self.view.panel)
        self.dock.hide()
        self.active = False
        self.came_from = None
        self.view.finished.connect(self._finished)
        self.view.navigate.connect(self.go)
        self.view.crop_requested.connect(self._crop)
        self.view.print_requested.connect(self._print)
        self.view.fill_weeks = self._fill_weeks
        self.view.crop_settings = self.photos.settings
        self.photos.edit_mode = self
        self._replace_big_preview()
        # Deleted (Delete key) or moved (Move to…) while editing: go on to the photo Photos selects next.
        after_removal = self.photos._after_removal

        def after_removal_then_follow(removed: list[str]) -> None:
            after_removal(removed)
            gone = {os.path.normcase(p) for p in removed}
            if self.active and os.path.normcase(self.view.path) in gone:
                target = self.photos.grid.current_path()
                if target and can_edit(target):
                    self._load(target)
                else:
                    self.leave()

        self.photos._after_removal = after_removal_then_follow
        # Opening another folder while editing: first finish with this photo.
        open_folder = self.photos.open_folder

        def guarded_open_folder(folder: str) -> None:
            if self.active and not self.leave_asking():
                return
            open_folder(folder)

        self.photos.open_folder = guarded_open_folder

    # ---------------------------------------------------------------- in and out
    def toggle(self) -> None:
        if self.active:
            self.view.close_with_shortcut()
            return
        paths = self.photos.action_paths()
        if len(paths) != 1 or not can_edit(paths[0]):
            QMessageBox.information(self.photos, "Edit", "Select one photo (JPG, PNG or HEIC) to edit.")
            return
        self.enter(paths[0])

    def enter(self, path: str) -> None:
        try:
            self.view.load(path)
        except OSError as exc:
            QMessageBox.warning(self.photos, "Edit", f"Couldn't open the photo:\n{exc}")
            return
        photos, shell = self.photos, self.shell
        self.came_from = photos.stack.currentWidget()
        if self.came_from is photos.preview:
            photos.preview.stop_video()
        photos.grid.select_paths([path], current=path)
        photos.refresh_sidebar()
        self.view.set_last(shell.media.last_edit)
        shell._remember_widths()
        area = shell.dockWidgetArea(shell.folders_dock)
        if shell.dockWidgetArea(self.dock) != area or not self.active:
            shell.addDockWidget(area, self.dock)
        shell.folders_dock.hide()
        self.dock.show()
        self._title()
        photos.stack.setCurrentWidget(self.view)
        self.active = True
        QTimer.singleShot(0, lambda: shell.resizeDocks([self.dock], [self.view.panel.minimumWidth() + 10],
                                                       Qt.Orientation.Horizontal))
        self.view.setFocus()

    def leave(self) -> None:
        photos, shell = self.photos, self.shell
        self.active = False
        self.dock.hide()
        shell.folders_dock.show()
        back = photos.grid  # (the big preview is only for videos and comparing now)
        photos.stack.setCurrentWidget(back)
        path = photos.grid.current_path()
        if path:
            photos.grid.scrollTo(photos.model.index(photos.model.row_of(path)))
        photos.grid.setFocus()
        QTimer.singleShot(0, shell._restore_widths)

    def leave_asking(self) -> bool:
        """Leave, saving first if wanted. False if "Keep editing" was chosen."""
        choice = self.view.confirm_leave()
        if choice is None:
            return False
        if choice == "save":
            self._save()
        self.leave()
        return True

    def _finished(self, result: str) -> None:
        if result == "save":
            self._save()
        self.leave()

    def _title(self) -> None:
        self.dock.setWindowTitle(f"Edit · {os.path.basename(self.view.path)}")

    # ---------------------------------------------------------------- the big preview's jobs
    def _replace_big_preview(self) -> None:
        """Double-click / Enter: a photo opens in Edit, a video (or any other file) in the big preview.
        Shift+P still opens and closes the big preview, as before. Right-click → Crop… opens Edit, cropping."""
        from PySide6.QtWidgets import QPushButton

        photos = self.photos

        def one_photo() -> str:
            paths = photos.grid.selected_paths()
            current = photos.grid.current_path()
            if len(paths) <= 1 and current and can_edit(current):
                return current
            return ""

        def open_it() -> None:  # double-click / Enter
            path = one_photo()
            current = photos.grid.current_path()
            if path:
                self.enter(path)
            elif current and kind(current) == "document":  # an Affinity or Photoshop file: open it there
                from PySide6.QtCore import QUrl
                from PySide6.QtGui import QDesktopServices

                QDesktopServices.openUrl(QUrl.fromLocalFile(current))
            elif current:
                photos.open_preview()

        def crop() -> None:  # right-click → Crop…
            path = one_photo()
            if path:
                self.enter(path)
                self.view.start_crop()

        photos.grid.activated.disconnect()
        photos.grid.activated.connect(lambda _index: open_it())
        photos.crop_current = crop
        for button in photos.preview.findChildren(QPushButton):
            if button.text().startswith("Close"):
                button.hide()  # Esc (or Shift+P) still closes it

    def _crop(self, path: str, box: tuple, as_copy: bool) -> None:
        """Crop from the Edit view: Photos crops the file (on its file thread); then the photo is shown again,
        the sliders as they were."""
        self.photos.crop_file(path, box, as_copy)
        if not as_copy:
            self.photos.bg.run(lambda: None, lambda _r, _e: self.view.reload_image() if self.active else None)

    def _taken(self, path: str):  # type: ignore[no-untyped-def]
        item = self.photos.model.item(path)
        return item.meta.date_taken if item is not None and item.meta is not None else None

    def _fill_weeks(self, path: str) -> None:
        """Print size's Week list: the photo's own week chosen (a card without a date: the week chosen last)."""
        from datetime import date, timedelta

        from photo_manager.ui.grid import album_week, album_week_dates

        week_start = getattr(self.photos.settings, "week_start", "sunday")
        taken, last = self._taken(path), self.shell.media.last_print_week
        ref = taken.date() if taken else date.today()
        if not taken and last:
            try:
                year, number = (int(x) for x in last.split("-"))
                ref = (album_week_dates(year, number, week_start) or (ref, ref))[0]
            except ValueError:
                pass
        start = album_week(ref, week_start)[2]
        combo = self.view.print_week
        combo.blockSignals(True)
        combo.clear()
        seen = set()
        for k in range(-10, 11):
            year, number, first, end = album_week(start + timedelta(days=7 * k), week_start)
            if (year, number) in seen:
                continue
            seen.add((year, number))
            label = f"Week {number} · {first:%b} {first.day}–" + (f"{end:%b} " if end.month != first.month else "") \
                + f"{end.day}" + (f", {year}" if year != date.today().year else "")
            if taken and first <= taken.date() <= end:
                label += "  (the photo's week)"
            combo.addItem(label, f"{year}-{number}")
            if first <= ref <= end:
                combo.setCurrentIndex(combo.count() - 1)
        combo.blockSignals(False)

    def _print(self, path: str, box: tuple, size: str, border: bool, week: str = "") -> None:
        """Print size: the print copy (sliders and flip/rotate included) into the Project Life folder."""
        from PySide6.QtWidgets import QFileDialog

        from . import print_size

        media = self.shell.media
        if not os.path.isdir(media.print_folder):
            folder = QFileDialog.getExistingDirectory(self.photos, "Where should print copies go?")
            if not folder:
                return
            media.print_folder = folder
        adjustments, turn, folder, et = self.view.adjustments(), self.view.turn, media.print_folder, self.photos.et
        taken = self._taken(path)
        if week:  # its date taken in the scrapbook week chosen
            from photo_manager.ui.grid import album_week_dates

            year, number = (int(x) for x in week.split("-"))
            days = album_week_dates(year, number, getattr(self.photos.settings, "week_start", "sunday"))
            if days:
                taken = print_size.week_date(taken, *days, getattr(self.photos.settings, "week_start", "sunday"))
                media.last_print_week = week
        self.photos.status.setText("Saving the print copy…")

        def done(dest, error) -> None:  # type: ignore[no-untyped-def]
            if error:
                QMessageBox.warning(self.photos, "Print size", f"The print copy wasn't saved:\n{error}")
                self.photos.status.setText("Print copy not saved.")
                return
            self.photos.status.setText(f"Saved {os.path.basename(dest)} in {os.path.basename(folder)}.")
            layouts = getattr(self.shell, "layouts", None)
            if layouts is not None:
                layouts.refresh(force=True)

        self.photos.bg.run(lambda: print_size.save_print(path, adjustments, turn, box, print_size.BY_NAME[size],
                                                         border, folder, et, taken), done)

    # ---------------------------------------------------------------- saving and moving on
    def _save(self) -> None:
        adjustments, turn = self.view.adjustments(), self.view.turn
        if adjustments.unchanged() and turn.unchanged():
            return
        path = self.view.path
        if not os.path.exists(path):  # renamed from the Details panel while editing
            path = self.photos.grid.current_path() or path
        if not adjustments.unchanged():  # "Same as last edit": the sliders (a rotate/flip is for this photo only)
            self.shell.media.last_edit = asdict(adjustments)
        save_in_photos(self.photos, path, adjustments, turn)

    def renamed(self, old: str, new: str) -> None:
        if os.path.normcase(self.view.path) == os.path.normcase(old):
            self.view.path = new
            self._title()

    def go(self, delta: int) -> None:
        """←/→: the previous/next photo that can be edited, asking to save this one first if it changed."""
        model = self.photos.model
        target = model.neighbour(self.view.path, delta)
        while target is not None and not can_edit(target.path):
            target = model.neighbour(target.path, delta)
        if target is None:
            return
        choice = self.view.confirm_leave()
        if choice is None:
            return
        if choice == "save":
            self._save()
            self.view.set_last(self.shell.media.last_edit)
        self._load(target.path, keep_zoom=True)  # ←/→: the same zoom (reset when Edit closes)

    def _load(self, path: str, keep_zoom: bool = False) -> None:
        self.photos.grid.select_paths([path], current=path)
        self.photos.refresh_sidebar()
        try:
            self.view.load(path, keep_zoom)
        except OSError as exc:
            QMessageBox.warning(self.photos, "Edit", f"Couldn't open the photo:\n{exc}")
            self.leave()
            return
        self.view.set_last(self.shell.media.last_edit)
        self._title()
        self.view.setFocus()
