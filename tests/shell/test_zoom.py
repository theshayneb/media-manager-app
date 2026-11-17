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
    for _ in range(20):
        z.wheel(-1, at, fitted, area)
    assert not z.zoomed and z.rect(fitted, area) == fitted
    for _ in range(40):
        z.wheel(1, at, fitted, area)
    assert z.zoom == 6.0  # the most it goes in
