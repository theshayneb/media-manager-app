"""The top bars, laid out the same way in every section (the user's "Option A"):

    [section's own buttons] | Rename · Move to · Delete · Show in Explorer | Search [filters]
                                                        ... 📂 folder ▾ [view ▾] ⟳ Refresh ⚙ ▾

Photos and Music keep their own buttons, search boxes and shortcuts: they are only put in this order
(and a few are added). Movies & TV builds its bar this way itself.
"""

from __future__ import annotations

import os
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QAction, QKeySequence
from PySide6.QtWidgets import (
    QFileDialog,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMenu,
    QMessageBox,
    QSizePolicy,
    QSlider,
    QToolBar,
    QToolButton,
    QWidget,
)

GEAR = "⚙"
# The user's "Option C": the buttons every section shares are small icons (their names show on hover);
# each section's own buttons are words without icons.
ICONS = {"Rename": "✏️", "Move to": "➡️", "Delete": "🗑", "Show in Explorer": "📁", "Refresh": "⟳", "Settings": "⚙"}


def label_as(item, name: str, icon: str | None = None) -> None:  # type: ignore[no-untyped-def]
    """Show a toolbar action/button as icon (or plain name), keeping its menu text and a tooltip that names it.
    For an action only its icon text changes, so menus using the same action still show its full name."""
    shown = icon or name
    tip = item.toolTip() or ""
    if not tip.casefold().startswith(name.casefold()):
        tip = f"{name}: {tip}" if tip and tip != item.text() else name
    if isinstance(item, QAction):
        item.setIconText(shown)
    else:
        item.setText(shown)
    item.setToolTip(tip)


def shared_icons(rename, move, delete, explorer, refresh) -> None:  # type: ignore[no-untyped-def]
    for item, name in ((rename, "Rename"), (move, "Move to"), (delete, "Delete"), (explorer, "Show in Explorer"),
                       (refresh, "Refresh")):
        if item is not None:
            label_as(item, name, ICONS[name])


class FolderButton(QToolButton):
    """"📂 <folder> ▾": the folder being shown; its menu opens, adds or shows folders."""

    def __init__(self, menu: QMenu, parent: QWidget | None = None):
        super().__init__(parent)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
        self.setMenu(menu)
        self.path = ""
        self.set_path("")

    def set_path(self, path: str) -> None:
        self.path = path
        name = path or "No folder"
        shown = self.fontMetrics().elidedText(name, Qt.TextElideMode.ElideMiddle, 170)
        self.setText(f"📂 {shown} ▾")
        self.setToolTip(path or "Choose a folder")


def menu_button(text: str, menu: QMenu, tip: str = "") -> QToolButton:
    b = QToolButton()
    b.setText(text)
    b.setToolTip(tip)
    b.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
    b.setStyleSheet("QToolButton::menu-indicator { image: none; width: 0px; }")
    b.setMenu(menu)
    return b


def spacer() -> QWidget:
    w = QWidget()
    w.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return w


# Qt's style draws a light line along a toolbar's top edge, which the panel titles beside it don't have.
FLAT_BAR = "QToolBar { border: none; border-bottom: 1px solid #737476; }"


def flatten(bar: QToolBar) -> None:
    """No line along the bar's top edge (it kept its bottom one), at the height it had before."""
    height = bar.sizeHint().height()
    bar.setStyleSheet(FLAT_BAR)
    bar.setMinimumHeight(height)


def rearrange(window: QMainWindow, bar: QToolBar, items: list) -> None:
    """Put bar's contents in this order. items: QAction (one of the bar's or a new one), QWidget (one of
    the bar's or a new one), or "|" for a separator. Anything of the bar's not listed is taken off it, its
    shortcut still working (it's added to the window)."""
    old = list(bar.actions())
    by_widget = {id(bar.widgetForAction(a)): a for a in old if bar.widgetForAction(a) is not None}
    widget_actions = {id(a) for a in by_widget.values()}
    for a in old:
        bar.removeAction(a)
    used = set()
    for item in items:
        if item == "|":
            bar.addSeparator()
        elif isinstance(item, QAction):
            bar.addAction(item)
            used.add(id(item))
        elif id(item) in by_widget:
            action = by_widget[id(item)]
            bar.addAction(action)
            used.add(id(action))
        else:
            bar.addWidget(item)
    for a in old:
        if id(a) not in used and not a.isSeparator() and id(a) not in widget_actions:
            window.addAction(a)  # keeps its shortcut
    flatten(bar)


def _all_actions(menu: QMenu) -> list[QAction]:
    out = []
    for a in menu.actions():
        out.append(a)
        if a.menu() is not None:
            out += _all_actions(a.menu())
    return out


def _find(actions: list[QAction], text: str) -> QAction | None:
    return next((a for a in actions if a.text() == text), None)


# ------------------------------------------------------------------ Music
def music_bar(music, shell) -> FolderButton:  # type: ignore[no-untyped-def]
    bar = next(b for b in music.findChildren(QToolBar) if b.objectName() == "main")
    acts = list(bar.actions()) + list(music.actions())
    explorer = _find(acts, "Show in Explorer")
    settings = _find(acts, "⚙ Settings")
    refresh = _find(acts, "⟳ Refresh")
    rename = music.rename_action
    rename.setText("Rename")

    move_menu = QMenu(music)
    move_menu.aboutToShow.connect(lambda: _fill_music_move(music, move_menu))
    move_btn = menu_button("Move to", move_menu, "Move the selected songs (and their lyrics files) to another folder")

    folder_menu = QMenu(music)
    folder_menu.addAction("Add a folder to the Folders list…", music.add_folder_view)
    folder_menu.addAction("Save the current search and Show filter…", music.save_search_view)
    folder_menu.addSeparator()
    folder_menu.addAction("Show this folder in Explorer", lambda: _explore(music.folder()))
    folder = FolderButton(folder_menu)
    hint, set_text = music.view_hint, music.view_hint.setText

    def follow(text: str) -> None:
        set_text(text)
        folder.set_path(music.folder() or "")

    hint.setText = follow
    folder.set_path(music.folder() or "")

    gear_menu = QMenu(music)
    if settings is not None:
        settings.setText("Settings…")
        gear_menu.addAction(settings)
    gear = menu_button(GEAR, gear_menu, "Settings")

    label_as(music.keep_action, "Keep")
    label_as(music.convert_action, "Convert")
    shared_icons(rename, move_btn, music.delete_action, explorer, refresh)
    layout_set_text = music.layout_btn.setText
    music.layout_btn.setText = lambda text: layout_set_text(text.lstrip("▦☰ "))  # words only
    music.layout_btn.setText(music.layout_btn.text())

    music.search.setMaximumWidth(220)
    music.show_filter.setMaximumWidth(170)
    show_label = next((bar.widgetForAction(a) for a in bar.actions()
                       if isinstance(bar.widgetForAction(a), QLabel) and "Show" in bar.widgetForAction(a).text()),
                      None)
    rearrange(music, bar, [
        music.keep_action, music.convert_action, music.gain_action, "|",
        rename, move_btn, music.delete_action, *([explorer] if explorer else []), "|",
        music.search, *([show_label] if show_label else []), music.show_filter, spacer(),
        folder, music.layout_btn, *([refresh] if refresh else []), gear,
    ])
    return folder


def _fill_music_move(music, menu: QMenu) -> None:  # type: ignore[no-untyped-def]
    menu.clear()
    here = os.path.normcase(os.path.normpath(music.folder() or ""))
    for d in music.view_defs():
        path = music.folder(d["key"]) if d.get("kind") != "search" else ""
        if path and os.path.normcase(os.path.normpath(path)) != here:
            menu.addAction(d["label"], lambda p=path: move_music(music, p))
    if menu.actions():
        menu.addSeparator()
    menu.addAction("Choose a folder…", lambda: _choose_music_folder(music))


def _choose_music_folder(music) -> None:  # type: ignore[no-untyped-def]
    folder = QFileDialog.getExistingDirectory(music, "Move the songs to", music.folder() or "")
    if folder:
        move_music(music, folder)


def move_music(music, folder: str) -> None:  # type: ignore[no-untyped-def]
    """Move the selected songs (with their lyrics .txt) to folder, like Delete takes them out of the list."""
    from music_manager.core import fileops

    if music._busy:
        return
    paths = music.selected_paths()
    if not paths:
        return
    music.editor.changed = {}
    playing = music.player.is_playing() and any(fileops.same_path(music.player.path, p) for p in paths)
    next_row = music._row_after(paths)
    if music._release(paths) is None and music.player.is_playing():
        playing = False

    def done(result, error) -> None:  # type: ignore[no-untyped-def]
        moved, failures = result or ({}, [])
        for p in moved:
            music.cache.forget(p)
        music.model.remove(list(moved))
        music._mark_others_stale()
        music._update_checkup()
        music._report("Moved", len(moved), failures, error)
        music._after_removal(next_row, playing)

    music.bg.run(lambda: fileops.move(paths, folder), done)


def _explore(path: str) -> None:
    if path and os.path.isdir(path) and os.name == "nt":
        os.startfile(path)  # type: ignore[attr-defined]


# ------------------------------------------------------------------ Photos
def photo_bar(photos) -> tuple[FolderButton, QLineEdit]:  # type: ignore[no-untyped-def]
    bar = next(b for b in photos.findChildren(QToolBar) if b.objectName() == "main-toolbar")
    acts = list(bar.actions())
    texts = {a.text(): a for a in acts}
    widgets = {a: bar.widgetForAction(a) for a in acts}

    def label(text: str):  # type: ignore[no-untyped-def]
        return next((w for w in widgets.values() if isinstance(w, QLabel) and w.text().strip() == text), None)

    slider = next((w for w in widgets.values() if isinstance(w, QSlider)), None)
    if slider is not None:
        slider.setFixedWidth(80)
    up, refresh = texts.get("⬆ Up"), texts.get("⟳")
    for old, new in (("Move to…", "Move to"), ("Convert…", "Convert")):
        if old in texts:
            texts[old].setText(new)
            texts[new] = texts[old]
    if refresh is not None:
        refresh.setText("⟳ Refresh")
    rename = QAction("Rename", photos)
    rename.setToolTip("Rename the selected file (F2). The Rename panel renames many at once.")
    rename.triggered.connect(photos.rename_current)

    # The menu row (Tools, View) goes: View ▾ and ⚙ ▾ hold its menus.
    menus = {a.text().replace("&", ""): a.menu() for a in photos.menuBar().actions() if a.menu() is not None}
    for m in menus.values():
        for a in _all_actions(m):
            photos.addAction(a)  # shortcuts keep working with the menu row hidden
    photos.menuBar().hide()
    view_btn = menu_button("▦ View ▾", menus["View"], "Thumbnails, grouping, panels and theme") \
        if "View" in menus else None
    gear = menu_button(GEAR, menus["Tools"], "Settings: Steam and video imports") if "Tools" in menus else None
    if view_btn is not None:
        view_btn.setText("View ▾")

    folder_menu = QMenu(photos)
    folder_menu.aboutToShow.connect(lambda: _fill_photo_folder_menu(photos, folder_menu, up))
    folder = FolderButton(folder_menu)
    photos.address.textChanged.connect(folder.set_path)
    folder.set_path(photos.address.text())

    from .photo_edit import can_edit, edit_selected

    edit = QAction("Edit", photos)
    edit.setShortcut(QKeySequence("Shift+E"))
    edit.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
    edit.setToolTip("Edit: colour balance, contrast, shadows and highlights (Shift+E)")
    edit.triggered.connect(lambda: edit_selected(photos))
    sheet = QAction("Print sheet", photos)  # print copies on 8.5 × 11 paper (the shell sets open_print_sheet)
    sheet.setShortcut(QKeySequence("Shift+S"))
    sheet.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
    sheet.setToolTip("Print the selected print copies on 8.5 × 11 paper, laid out to waste the least (Shift+S)")
    sheet.triggered.connect(lambda: getattr(photos, "open_print_sheet", lambda: None)())
    photos.extra_menu_items = lambda paths: [
        ("Edit…", lambda: edit_selected(photos), "Shift+E", len(paths) == 1 and can_edit(paths[0])),
        ("Print sheet…", lambda: getattr(photos, "open_print_sheet", lambda: None)(), "Shift+S", bool(paths))]

    search = QLineEdit()
    search.setPlaceholderText("Search names…")
    search.setClearButtonEnabled(True)
    search.setMaximumWidth(170)
    search.setMinimumWidth(120)
    _add_photo_search(photos, search)

    shared_icons(rename, texts.get("Move to"), texts.get("Delete"), texts.get("Show in Explorer"), refresh)
    steam = texts.get("Steam import…")
    if steam is not None:
        label_as(steam, "Steam import")  # its button, between Convert and Open (the user's request)
    items = [texts.get("View"), texts.get("Convert"), edit, sheet, steam, texts.get("Open"), "|",
             rename, texts.get("Move to"), texts.get("Delete"), texts.get("Show in Explorer"), "|",
             search, label("Sort:"), photos.sort_combo, label("Group:"), photos.group_combo, photos.filter_btn,
             label("Size:"), slider, spacer(), folder, photos.fav_action, view_btn, refresh, gear]
    rearrange(photos, bar, [i for i in items if i is not None])
    return folder, search


def _fill_photo_folder_menu(photos, menu: QMenu, up: QAction | None) -> None:  # type: ignore[no-untyped-def]
    menu.clear()
    folder = photos.model.folder or ""
    menu.addAction("Open a folder…", lambda: _open_photo_folder(photos))
    menu.addAction("Type a folder path…", lambda: _type_photo_folder(photos))
    if up is not None:
        menu.addAction(up)
    recent = [f for f in getattr(photos.settings, "recent_move_folders", []) if os.path.isdir(f)][:8]
    if recent:
        sub = menu.addMenu("Recent folders")
        for f in recent:
            sub.addAction(f, lambda f=f: photos.open_folder(f))
    if folder:
        menu.addSeparator()
        fav = photos.is_favorite(folder)
        menu.addAction("Remove from the Folders list" if fav else "Add to the Folders list",
                       lambda: photos.toggle_favorite(folder))
        menu.addAction("Show this folder in Explorer", lambda: _explore(folder))


def _open_photo_folder(photos) -> None:  # type: ignore[no-untyped-def]
    folder = QFileDialog.getExistingDirectory(photos, "Open a folder", photos.model.folder or "")
    if folder:
        photos.open_folder(os.path.normpath(folder))


def _type_photo_folder(photos) -> None:  # type: ignore[no-untyped-def]
    text, ok = QInputDialog.getText(photos, "Open a folder", "Folder path:", text=photos.model.folder or "")
    text = text.strip().strip('"')
    if not ok or not text:
        return
    if os.path.isdir(text):
        photos.open_folder(os.path.normpath(text))
    else:
        QMessageBox.information(photos, "Open a folder", f"Can't find the folder\n{text}")


def _add_photo_search(photos, search: QLineEdit) -> None:  # type: ignore[no-untyped-def]
    """Search by name, on top of Photo Manager's own filters."""
    passes, active, apply = photos._passes_filter, photos._filter_active, photos.apply_filter

    def words() -> list[str]:
        return search.text().casefold().split()

    def passes_with_search(item) -> bool:  # type: ignore[no-untyped-def]
        name = item.name.casefold()
        return all(w in name for w in words()) and (not active() or passes(item))

    def apply_with_search() -> None:
        photos._filter_active = lambda: active() or bool(words())
        photos._passes_filter = passes_with_search
        try:
            apply()
        finally:
            photos._filter_active = active
        if not active():  # the Filter button counts only its own filters
            photos.filter_btn.setText("Filter")
            photos.filter_btn.setStyleSheet("")

    photos.apply_filter = apply_with_search
    search.textChanged.connect(lambda _t: apply_with_search())


def add_actions(menu: QMenu, entries: list[tuple[str, Callable]]) -> None:
    for text, slot in entries:
        menu.addAction(text, slot)
