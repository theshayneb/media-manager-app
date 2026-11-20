"""The Print sheet window (Photos → 🖨 Print sheet, Shift+S): the selected print copies laid out on 8.5 × 11 in
sheets (print_sheet.arrange), shown as they'll print; per photo ☀ Brighter (its own amount); Print… (straight to
the printer, at the photos' exact size, centred) and Save sheets ("Week 46 - Sheet 1.jpg" in Project Life).
Printing marks the print copies with 🖨 (XMP-photoshop:Instructions, metadata.PRINTED_MARK)."""

from __future__ import annotations

import os
from datetime import date

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QImage, QPainter, QPen
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from . import print_sheet
from .print_sheet import Piece, Placed, Sheet

SELECTED_NAME = "background: #3b6fc4; color: white; font-weight: bold; border-radius: 3px; padding: 1px 4px;"
PREVIEW = 8  # the preview is drawn at 1/8 of the real size (75 DPI)


def _qimage(image: Image.Image) -> QImage:
    from photo_manager.ui.grid import pil_to_qimage

    return pil_to_qimage(image)


class SheetView(QWidget):
    """One sheet as it'll print: the paper, the photos (small copies), the crop marks; click a photo to select it,
    drag it onto another the same size to swap them."""

    picked = Signal(object)    # the Piece clicked
    swapped = Signal(object, object)

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self.sheet: Sheet | None = None
        self.small: dict[str, QImage] = {}
        self.selected: Piece | None = None
        self._drag: Placed | None = None
        self.setMinimumSize(400, 320)

    def show_sheet(self, sheet: Sheet | None) -> None:
        self.sheet = sheet
        self.update()

    def _frame(self) -> tuple[QRectF, float]:
        """Where the paper is drawn, and the scale (screen px per sheet px)."""
        if self.sheet is None:
            return QRectF(), 1.0
        w, h = self.sheet.size
        s = min((self.width() - 24) / w, (self.height() - 24) / h)
        return QRectF((self.width() - w * s) / 2, (self.height() - h * s) / 2, w * s, h * s), s

    def _rect(self, p: Placed) -> QRectF:
        frame, s = self._frame()
        return QRectF(frame.left() + p.x * s, frame.top() + p.y * s, p.w * s, p.h * s)

    def paintEvent(self, _event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        painter = QPainter(self)
        painter.fillRect(self.rect(), QColor("#2a2b30"))
        if self.sheet is None:
            return
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        frame, s = self._frame()
        painter.fillRect(frame.translated(3, 4), QColor(0, 0, 0, 90))
        painter.fillRect(frame, QColor("white"))
        for p in self.sheet.placed:
            r = self._rect(p)
            image = self.small.get(self._key(p))
            if image is not None:
                painter.drawImage(r, image)
            else:
                painter.fillRect(r, QColor("#cccccc"))
            if p.piece.brighter:
                painter.setPen(QColor("white"))
                painter.drawText(r.adjusted(4, 2, -4, -2), Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
                                 f"☀ {p.piece.brighter}")
            if p.piece is self.selected:
                painter.setPen(QPen(QColor("#4c8dff"), 3))
                painter.drawRect(r.adjusted(1, 1, -1, -1))
        painter.setPen(QPen(QColor(150, 150, 150), 1))
        for x0, y0, x1, y1 in print_sheet.crop_marks(self.sheet):
            painter.drawLine(QPointF(frame.left() + x0 * s, frame.top() + y0 * s),
                             QPointF(frame.left() + x1 * s, frame.top() + y1 * s))

    @staticmethod
    def _key(p: Placed) -> str:
        return f"{p.piece.path}|{p.turned}|{p.piece.brighter}"

    def _at(self, pos) -> Placed | None:  # type: ignore[no-untyped-def]
        if self.sheet is None:
            return None
        return next((p for p in self.sheet.placed if self._rect(p).contains(pos)), None)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        hit = self._at(event.position())
        self._drag = hit
        self.picked.emit(hit.piece if hit else None)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]  # noqa: N802
        target = self._at(event.position())
        if self._drag is not None and target is not None and target is not self._drag:
            self.swapped.emit(self._drag, target)
        self._drag = None


class PrintSheetWindow(QDialog):
    def __init__(self, photos, media, paths: list[str]):  # type: ignore[no-untyped-def]
        super().__init__(photos)
        self.setWindowTitle("Print sheet")
        self.photos, self.media = photos, media
        self.pieces: list[Piece] = []
        problems = []
        for path in paths:
            try:
                self.pieces.append(print_sheet.piece_for(path))
            except Exception as exc:  # noqa: BLE001
                problems.append(f"{os.path.basename(path)}: {exc}")
        self.sheets: list[Sheet] = []
        self.leftover: list[Piece] = []
        self.names: dict[int, QLabel] = {}
        self.current = 0
        self.thumbs: dict[str, Image.Image] = {}  # a small copy of each photo (for the preview)

        bar = QHBoxLayout()
        self.arrange_btn = QPushButton("⟳ Auto-arrange")
        self.arrange_btn.clicked.connect(lambda: self.arrange(reset_turns=True))
        self.turn_btn = QPushButton("↻ Turn selected")
        self.turn_btn.setToolTip("Turn the selected photo sideways on the paper (or back), then arrange again")
        self.turn_btn.clicked.connect(self.turn_selected)
        self.prev_btn, self.next_btn = QPushButton("◀"), QPushButton("▶")
        self.prev_btn.clicked.connect(lambda: self.go(-1))
        self.next_btn.clicked.connect(lambda: self.go(1))
        self.page_label = QLabel("")
        self.used_label = QLabel("")
        self.save_btn = QPushButton("💾 Save sheet")
        self.save_btn.setToolTip("The sheet as an 8.5 × 11 in picture at 600 DPI, in the Project Life folder")
        self.save_btn.clicked.connect(self.save_sheets)
        self.print_btn = QPushButton("🖨 Print…")
        self.print_btn.setDefault(True)
        self.print_btn.clicked.connect(self.print_sheets)
        # The printer's colour fix: print the colour check, then pick the column that looked right.
        self.check_btn = QPushButton("🎨 Colour check")
        self.check_btn.setToolTip("Print a test page (its own page, not the sheet): the greyest and brownest parts "
                                  "of the photos on this sheet (or plain swatches, with none) in columns A–G, to see "
                                  "which looks right on your paper")
        self.check_btn.clicked.connect(self.print_colour_check)
        self.grey_box, self.brown_box = QComboBox(), QComboBox()
        for box, value, tip in ((self.grey_box, media.print_grey, "Greys"),
                                (self.brown_box, media.print_brown, "Browns")):
            for letter in print_sheet.COLOUR_LETTERS:
                box.addItem(letter + ("  (as it is)" if letter == "D" else ""), letter)
            box.setCurrentIndex(max(0, box.findData(value)))
            box.setToolTip(f"{tip}: the colour check's column that looked right (D = as it is). Used when printing "
                           "and saving sheets; the screen shows them as they are.")
        self.grey_box.currentIndexChanged.connect(lambda _i: setattr(media, "print_grey", self.grey_box.currentData()))
        self.brown_box.currentIndexChanged.connect(
            lambda _i: setattr(media, "print_brown", self.brown_box.currentData()))
        # The printer + paper's ICC profile (Canon's Matte Photo Paper one for the iP8720, found by itself).
        self.profile_box = QComboBox()
        self.profile_box.setMinimumContentsLength(22)
        self.profile_box.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.profile_box.addItem("None (as Affinity prints now)", "")
        profiles = print_sheet.printer_profiles()
        for path in profiles:
            self.profile_box.addItem(path.stem, str(path))
        if media.printer_profile == "auto":
            found = print_sheet.suggested_profile(profiles)
            media.printer_profile = str(found) if found else ""
        self.profile_box.setCurrentIndex(max(0, self.profile_box.findData(media.printer_profile)))
        self.profile_box.setToolTip("Your printer and paper's colour profile: Media Manager makes the colours right "
                                    "for them. In the Canon print dialog, turn its own colour correction off then "
                                    "(Main → Color/Intensity: Manual → Set… → Matching → Color Correction: None).")
        self.profile_box.currentIndexChanged.connect(self._profile_chosen)
        close = QPushButton("Close")
        close.clicked.connect(self.reject)
        for w in (self.arrange_btn, self.turn_btn, self.prev_btn, self.page_label, self.next_btn, self.used_label):
            bar.addWidget(w)
        bar.addStretch(1)
        for w in (QLabel("Printer profile:"), self.profile_box, self.check_btn, QLabel("Greys:"), self.grey_box,
                  QLabel("Browns:"), self.brown_box):
            bar.addWidget(w)
        bar.addSpacing(12)
        for w in (self.save_btn, self.print_btn, close):
            bar.addWidget(w)

        self.view = SheetView()
        self.view.picked.connect(self.select)
        self.view.swapped.connect(self.swap)

        self.side = QWidget()
        self.side_layout = QVBoxLayout(self.side)
        self.side_layout.setContentsMargins(6, 6, 6, 6)
        scroll = QScrollArea()
        scroll.setWidget(self.side)
        scroll.setWidgetResizable(True)
        scroll.setFixedWidth(330)

        main = QHBoxLayout()
        main.addWidget(self.view, 1)
        main.addWidget(scroll)
        layout = QVBoxLayout(self)
        layout.addLayout(bar)
        layout.addLayout(main, 1)
        self.note = QLabel("")
        self.note.setWordWrap(True)
        self.note.setStyleSheet("color: palette(placeholder-text);")
        layout.addWidget(self.note)
        if problems:
            self.note.setText("Not added: " + "; ".join(problems))
        self._make_thumbs()
        self.arrange()
        if not problems:
            self._profile_note()
        if not self.pieces:
            self.note.setText("No photos selected: the sheet is empty. 🎨 Colour check prints its own test page; to "
                              "print photos, close this, select the print copies and open Print sheet again.")

    # ---------------------------------------------------------------- arranging
    def _make_thumbs(self) -> None:
        for piece in self.pieces:
            try:
                image = print_sheet.load(piece.path)
                image.thumbnail((max(1, piece.width // PREVIEW), max(1, piece.height // PREVIEW)))
                self.thumbs[piece.path] = image
            except Exception:  # noqa: BLE001
                pass

    def arrange(self, reset_turns: bool = False) -> None:
        if reset_turns:
            for piece in self.pieces:
                piece.turn = None
        # One sheet, filled as well as it can be (the user never prints a page that isn't full); the photos that
        # don't fit are left over, not printed (and not marked), for the next sheet.
        sheets, too_big = print_sheet.arrange(self.pieces)
        self.sheets = sheets[:1]
        self.leftover = [p.piece for sheet in sheets[1:] for p in sheet.placed]
        if too_big:
            self.note.setText("Too big for 8.5 × 11 paper: " + ", ".join(os.path.basename(p.path) for p in too_big))
        self.current = 0
        self._previews()
        self._show()

    def _previews(self) -> None:
        for sheet in self.sheets:
            for p in sheet.placed:
                key = SheetView._key(p)
                if key in self.view.small or p.piece.path not in self.thumbs:
                    continue
                image = print_sheet.brighter(self.thumbs[p.piece.path], p.piece.brighter)
                if p.turned:
                    image = image.transpose(Image.Transpose.ROTATE_90)
                self.view.small[key] = _qimage(image)

    def _show(self) -> None:
        sheet = self.sheets[self.current] if self.sheets else None
        self.view.show_sheet(sheet)
        n = len(self.sheets)
        left = len(self.leftover)
        self.page_label.setText(("One sheet" + (f" · {left} left over for the next one" if left else ""))
                                if n else "Nothing to print")
        self.prev_btn.hide()
        self.next_btn.hide()
        self.used_label.setText(f"   Paper used: {round(sheet.used() * 100)}%" if sheet else "")
        self.print_btn.setEnabled(bool(n))
        self.save_btn.setEnabled(bool(n))
        self._fill_side()

    def go(self, delta: int) -> None:
        self.current = max(0, min(len(self.sheets) - 1, self.current + delta))
        self._show()

    def select(self, piece: Piece | None) -> None:
        """A photo picked on the sheet (or its name in the list): outlined there, its name coloured here."""
        self.view.selected = piece
        self.view.update()
        for key, label in self.names.items():
            label.setStyleSheet(SELECTED_NAME if piece is not None and key == id(piece) else "")

    def turn_selected(self) -> None:
        piece = self.view.selected
        if piece is None:
            return
        placed = next((p for s in self.sheets for p in s.placed if p.piece is piece), None)
        piece.turn = not (placed.turned if placed else False)
        self.arrange()

    def swap(self, a: Placed, b: Placed) -> None:
        """Two photos the same size (either way round) change places."""
        slots = [(p, (p.w, p.h)) for p in (a, b)]
        if sorted(slots[0][1]) != sorted(slots[1][1]):
            self.note.setText("Only photos the same size can swap places (Auto-arrange or Turn for the rest).")
            return
        a.piece, b.piece = b.piece, a.piece
        for p, (w, h) in slots:  # each stood the way its new place needs
            p.turned = (p.piece.width, p.piece.height) != (w, h)
        self._previews()
        self.view.update()

    # ---------------------------------------------------------------- the list beside it (☀ Brighter)
    def _fill_side(self) -> None:
        while self.side_layout.count():
            item = self.side_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        self.names: dict[int, QLabel] = {}
        for sheet in self.sheets:
            self.side_layout.addWidget(QLabel(f"<b>On this sheet</b> ({len(sheet.placed)})"))
            for p in sheet.placed:
                self.side_layout.addWidget(self._row(p.piece))
        if self.leftover:
            title = QLabel(f"<b>Left over</b> ({len(self.leftover)}): not printed, for the next sheet")
            title.setWordWrap(True)
            self.side_layout.addWidget(title)
            for piece in self.leftover:
                name = QLabel(os.path.basename(piece.path))
                name.setWordWrap(True)
                name.setStyleSheet("color: palette(placeholder-text);")
                self.side_layout.addWidget(name)
        self.select(self.view.selected)
        hint = QLabel("☀ Brighter: on the sheet only (the print copy isn't changed), each photo its own amount "
                      f"(Edit's Brightness; {print_sheet.BRIGHTER} is your Affinity brightness layer).")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: palette(placeholder-text); font-size: 11px;")
        self.side_layout.addWidget(hint)
        self.side_layout.addStretch(1)

    def _row(self, piece: Piece) -> QWidget:
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 0, 0, 0)
        name = QLabel(os.path.basename(piece.path))
        name.setWordWrap(True)
        name.setToolTip(piece.path + "\n(click to pick it on the sheet)")
        name.setCursor(Qt.CursorShape.PointingHandCursor)
        name.mousePressEvent = lambda _e: self.select(piece)  # type: ignore[method-assign]
        self.names[id(piece)] = name
        check = QCheckBox("☀")
        check.setToolTip("Brighter on the sheet")
        check.setChecked(bool(piece.brighter))
        amount = QSpinBox()
        amount.setRange(1, 100)
        amount.setSuffix("%")
        amount.setValue(piece.brighter or print_sheet.BRIGHTER)
        amount.setEnabled(bool(piece.brighter))

        def changed(_v=None) -> None:  # type: ignore[no-untyped-def]
            amount.setEnabled(check.isChecked())
            piece.brighter = amount.value() if check.isChecked() else 0
            self._previews()
            self.view.update()

        check.toggled.connect(changed)
        amount.valueChanged.connect(changed)
        h.addWidget(name, 1)
        h.addWidget(check)
        h.addWidget(amount)
        return row

    # ---------------------------------------------------------------- out
    def _week(self) -> str:
        """"Week 46" (the scrapbook week of the first photo with a date taken)."""
        from photo_manager.ui.grid import album_week

        for piece in self.pieces:
            item = self.photos.model.item(piece.path)
            meta = getattr(item, "meta", None)
            if meta is not None and meta.date_taken is not None:
                return f"Week {album_week(meta.date_taken.date(), self.photos.settings.week_start)[1]}"
        return ""

    def save_sheets(self) -> list[str]:
        folder = self.media.print_folder
        if not os.path.isdir(folder):
            QMessageBox.warning(self, "Print sheet", f"The Project Life folder isn't there:\n{folder}")
            return []
        week = self._week()
        saved = []
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            for n, sheet in enumerate(self.sheets, start=1):
                saved.append(print_sheet.save(sheet, folder, print_sheet.sheet_name(week, n),
                                              self.media.print_grey, self.media.print_brown))
        finally:
            self.unsetCursor()
        self.note.setText("Saved " + ", ".join(os.path.basename(p) for p in saved) + f" in {folder}")
        return saved

    def print_sheets(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog

        printer = self._printer("Print sheet")  # the whole paper: the arrangement centred on it, real size
        dialog = QPrintDialog(printer, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        self.print_to(printer)

    def print_to(self, printer) -> bool:  # type: ignore[no-untyped-def]
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QPrinter

        painter = QPainter()
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            for n, sheet in enumerate(self.sheets):
                printer.setPageOrientation(QPageLayout.Orientation.Landscape if sheet.landscape
                                           else QPageLayout.Orientation.Portrait)
                if n == 0:
                    if not painter.begin(printer):
                        raise OSError("The printer couldn't start")
                elif not printer.newPage():
                    raise OSError("The printer couldn't start a new page")
                image = _qimage(print_sheet.to_printer(
                    print_sheet.render(sheet, grey=self.media.print_grey, brown=self.media.print_brown),
                    self.media.printer_profile))
                # The whole paper, in the printer's own pixels: the sheet (8.5 × 11 in) fills it exactly, so every
                # photo prints at its real size.
                painter.drawImage(printer.paperRect(QPrinter.Unit.DevicePixel), image)
        except OSError as exc:
            QMessageBox.warning(self, "Print sheet", f"Not printed: {exc}")
            return False
        finally:
            if painter.isActive():
                painter.end()
            self.unsetCursor()
        self.mark_printed([p.piece.path for s in self.sheets for p in s.placed])
        self.note.setText(f"Sent {len(self.sheets)} sheet{'s' if len(self.sheets) != 1 else ''} to the printer; "
                          "the print copies have a 🖨 now.")
        return True

    def _printer(self, name: str):  # type: ignore[no-untyped-def]
        """The printer as Media Manager prints: the whole page, 600 DPI, letter (choose the matte paper and
        borderless settings in the print dialog, as for Affinity)."""
        from PySide6.QtGui import QPageSize
        from PySide6.QtPrintSupport import QPrinter

        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        printer.setResolution(print_sheet.DPI)
        printer.setFullPage(True)
        printer.setPageSize(QPageSize(QPageSize.PageSizeId.Letter))
        printer.setDocName(name)
        return printer

    def _profile_chosen(self, _index: int) -> None:
        self.media.printer_profile = self.profile_box.currentData() or ""
        self._profile_note()

    def _profile_note(self) -> None:
        if self.media.printer_profile:
            self.note.setText(f"Printing with {os.path.basename(self.media.printer_profile)}: in the Canon print "
                              "dialog turn its colour correction off (Main → Color/Intensity: Manual → Set… → "
                              "Matching → Color Correction: None), and choose Matte Photo Paper.")

    def print_colour_check(self) -> None:
        from PySide6.QtPrintSupport import QPrintDialog

        printer = self._printer("Colour check")
        if QPrintDialog(printer, self).exec() != QDialog.DialogCode.Accepted:
            return
        # With photos on the sheet: pieces of them (their greyest and brownest parts); else the plain swatches.
        on_sheet = [p.piece.path for sheet in self.sheets for p in sheet.placed]
        self.setCursor(Qt.CursorShape.WaitCursor)
        try:
            check = print_sheet.colour_check_photos(on_sheet) if on_sheet else print_sheet.colour_check_page()
        finally:
            self.unsetCursor()
        page = print_sheet.to_printer(check, self.media.printer_profile)
        if self.print_page(printer, page, landscape=True):
            self.note.setText("Colour check sent. On the paper, find the column whose greys look most like true "
                              "greys, and the one whose browns look right, and choose those letters here.")

    def print_page(self, printer, image: Image.Image, landscape: bool) -> bool:  # type: ignore[no-untyped-def]
        from PySide6.QtGui import QPageLayout
        from PySide6.QtPrintSupport import QPrinter

        printer.setPageOrientation(QPageLayout.Orientation.Landscape if landscape
                                   else QPageLayout.Orientation.Portrait)
        painter = QPainter()
        if not painter.begin(printer):
            QMessageBox.warning(self, "Print sheet", "The printer couldn't start.")
            return False
        try:
            painter.drawImage(printer.paperRect(QPrinter.Unit.DevicePixel), _qimage(image))
        finally:
            painter.end()
        return True

    def mark_printed(self, paths: list[str]) -> None:
        """🖨 on the print copies (written by ExifTool on Photos' file thread, the files' dates kept)."""
        from photo_manager.core.metadata import PRINTED_MARK

        et = getattr(self.photos, "et", None)
        if et is None or not paths:
            return
        value = f"{PRINTED_MARK} {date.today():%Y-%m-%d}"

        def work() -> None:
            for path in paths:
                et.write(path, ["-P", f"-XMP-photoshop:Instructions={value}"])

        self.photos.bg.run(work, lambda _r, _e: self.photos._load_meta(paths))


def open_print_sheet(photos, media) -> None:  # type: ignore[no-untyped-def]
    """Photos' 🖨 Print sheet (Ctrl+P): the selected pictures (print copies). With none selected it opens all the
    same (for the colour check and the printer settings), with nothing on the sheet."""
    paths = [p for p in photos.grid.selected_paths() if photos.model.item(p) and photos.model.item(p).kind == "image"]
    window = PrintSheetWindow(photos, media, paths)
    window.setWindowState(Qt.WindowState.WindowMaximized)
    window.exec()
