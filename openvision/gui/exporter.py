"""
Image and vector export utilities for OpenVision schematic canvas.
Exports publication-quality high-resolution PNG images from the QGraphicsScene.
"""

from pathlib import Path
from typing import Optional
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import QRectF
from PyQt6.QtGui import QImage, QPainter, QColor

from openvision.gui.gate_items import Palette


def export_scene_to_image(
    scene: QtWidgets.QGraphicsScene,
    output_path: str,
    max_dimension: int = 4096,
    bg_color: QColor = Palette.BG_DARK,
) -> str:
    """
    Renders the complete QGraphicsScene to a high-resolution PNG image on disk.
    Preserves aspect ratio and scales up to max_dimension.
    """
    source_rect = scene.sceneRect()
    if source_rect.isEmpty():
        raise ValueError("Cannot export an empty scene.")

    w = source_rect.width()
    h = source_rect.height()

    # Calculate target dimensions respecting max_dimension
    if w >= h:
        target_w = max_dimension
        target_h = int(max_dimension * (h / w))
    else:
        target_h = max_dimension
        target_w = int(max_dimension * (w / h))

    target_w = max(640, min(8192, target_w))
    target_h = max(480, min(8192, target_h))

    image = QImage(target_w, target_h, QImage.Format.Format_ARGB32_Premultiplied)
    image.fill(bg_color)

    painter = QPainter(image)
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing |
        QPainter.RenderHint.TextAntialiasing |
        QPainter.RenderHint.SmoothPixmapTransform
    )

    target_rect = QRectF(0, 0, target_w, target_h)
    scene.render(painter, target_rect, source_rect)
    painter.end()

    out_file = Path(output_path)
    out_file.parent.mkdir(parents=True, exist_ok=True)
    success = image.save(str(out_file), "PNG")
    if not success:
        raise IOError(f"Failed to save image to {out_file}")

    return str(out_file.resolve())
