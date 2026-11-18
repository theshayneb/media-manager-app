from PySide6.QtCore import QPointF, QRectF

from media_manager.zoom import Zoom


def test_zoom_keeps_the_spot_under_the_pointer_and_the_edges_in():
    fitted, area = QRectF(100, 0, 800, 600), QRectF(0, 0, 1000, 600)
    z = Zoom()
    assert z.rect(fitted, area) == fitted
    at = QPointF(300, 150)  # a quarter across, a quarter down the picture
    assert z.wheel(4, at, fitted, area)
    rect = z.rect(fitted, area)
    assert abs((at.x() - rect.left()) / rect.width() - 0.25) < 0.01
    assert abs((at.y() - rect.top()) / rect.height() - 0.25) < 0.01
    assert rect.width() > 1900
    z.start_pan(QPointF(500, 300))
    z.pan(QPointF(5000, 3000), fitted, area)  # dragged far: stops at the picture's corner
    rect = z.rect(fitted, area)
    assert rect.left() == 0 and rect.top() == 0
    z.end_pan()
    for _ in range(4):  # four notches in, four out
        z.wheel(-1, at, fitted, area)
    assert not z.changed and z.rect(fitted, area) == fitted  # back at fitted on the way out
    for _ in range(20):
        z.wheel(-1, at, fitted, area)
    small = z.rect(fitted, area)
    assert z.zoom == 0.25 and small.width() == 200 and small.center() == area.center()  # smaller, centred
    z.start_pan(QPointF(500, 300))
    z.pan(QPointF(900, 300), fitted, area)  # nothing to look around: stays centred
    assert z.rect(fitted, area).center() == area.center()
    z.end_pan()
    for _ in range(20):
        z.wheel(1, at, fitted, area)
    for _ in range(20):
        z.wheel(1, at, fitted, area)
    assert z.zoom == 6.0  # the most it goes in


def test_zoom_stays_from_photo_to_photo_until_closed(tmp_path):
    from PIL import Image
    from PySide6.QtGui import QPixmap
    from PySide6.QtWidgets import QApplication, QStackedWidget, QWidget

    QApplication.instance() or QApplication([])
    from media_manager.zoom import patch_preview

    patch_preview()
    from photo_manager.ui.preview import CropCanvas

    # The big preview: ←/→ give the canvas the next photo; the zoom stays until the preview is closed.
    stack = QStackedWidget()
    canvas, grid = CropCanvas(), QWidget()
    stack.addWidget(grid)
    stack.addWidget(canvas)
    stack.resize(400, 300)
    stack.show()
    stack.setCurrentWidget(canvas)
    pix = QPixmap(200, 100)
    canvas.set_image(pix, (200, 100))
    canvas._zoom.wheel(-3, QPointF(200, 150), canvas._target(), QRectF(canvas.rect()))
    smaller = canvas._zoom.zoom
    assert smaller < 1
    canvas.set_image(QPixmap(150, 100), (150, 100))  # the next photo
    assert canvas._zoom.zoom == smaller
    stack.setCurrentWidget(grid)  # closed
    assert canvas._zoom.zoom == 1

    # Edit: ←/→ keep the zoom; opening a photo afresh resets it.
    from media_manager.edit_view import EditView

    a, b = tmp_path / "a.jpg", tmp_path / "b.jpg"
    Image.new("RGB", (80, 60)).save(a)
    Image.new("RGB", (60, 80)).save(b)
    view = EditView()
    view.load(str(a))
    view.view.zoom.zoom = 0.5
    view.load(str(b), keep_zoom=True)
    assert view.view.zoom.zoom == 0.5
    view.load(str(a))
    assert view.view.zoom.zoom == 1
