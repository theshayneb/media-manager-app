"""Editing inside the main window (the user's layout): the Edit view takes Photos' photo area, like the big
preview; its sliders take the Folders panel's place; Photos' Details panel stays where it is, for labels,
keywords, dates and renaming while editing. ←/→ go through the folder; Shift+E, Cancel or Save leave."""

from __future__ import annotations

import os
from dataclasses import asdict

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import QMessageBox

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
        self.photos.edit_mode = self
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
        back = self.came_from if self.came_from in (photos.preview, photos.grid) else photos.grid
        photos.stack.setCurrentWidget(back)
        if back is photos.preview:
            photos._preview_show_current()
            photos.preview.setFocus()
        else:
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

    # ---------------------------------------------------------------- saving and moving on
    def _save(self) -> None:
        adjustments = self.view.adjustments()
        if adjustments.unchanged():
            return
        path = self.view.path
        if not os.path.exists(path):  # renamed from the Details panel while editing
            path = self.photos.grid.current_path() or path
        self.shell.media.last_edit = asdict(adjustments)
        save_in_photos(self.photos, path, adjustments)

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
        self.photos.grid.select_paths([target.path], current=target.path)
        self.photos.refresh_sidebar()
        try:
            self.view.load(target.path)
        except OSError as exc:
            QMessageBox.warning(self.photos, "Edit", f"Couldn't open the photo:\n{exc}")
            self.leave()
            return
        self._title()
        self.view.setFocus()
