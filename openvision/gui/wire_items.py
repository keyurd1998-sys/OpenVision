"""
Wire graphic items for OpenVision PyQt6 canvas.
Renders orthogonal Manhattan wire segments, solder-dot junctions (•), and
High-Fanout Net (HFN) labeled stubs with full interactive net highlighting.
"""

from typing import Dict, List, Optional, Tuple, Any, Callable
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QRectF, QPointF, QLineF
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush, QFont

from openvision.routing.router_models import (
    WireSegment,
    SolderDot,
    HFNStub,
    SegmentOrientation,
    PinExitDirection,
)


class WirePalette:
    """Color palette for wires, junctions, and net highlighting."""
    WIRE_NORMAL = QColor("#26a69a")          # Teal / green wire
    WIRE_HIGHLIGHT = QColor("#ffff00")       # Selected: Pure glowing bright yellow (3.2px)
    WIRE_HOVER = QColor("#ffeb3b")           # Hovered: Radiant glowing yellow (2.6px)
    SOLDER_DOT = QColor("#00e676")           # Bright green solder dot
    SOLDER_DOT_HIGHLIGHT = QColor("#ffff00") # Yellow glowing solder dot
    HFN_STUB_WIRE = QColor("#ff7043")        # Orange/coral stub
    HFN_TAG_BG = QColor("#37474f")           # Slate tag background
    HFN_TAG_BORDER = QColor("#ff7043")       # Orange tag border
    HFN_TAG_TEXT = QColor("#ffffff")         # White text
    HFN_TAG_HIGHLIGHT = QColor("#ffd54f")    # Amber highlight


class WireGraphicsItem(QtWidgets.QGraphicsItem):
    """
    QGraphicsItem representing an orthogonal Manhattan wire segment.
    Supports hover and clicking to highlight the entire net from source to every destination.
    """

    def __init__(
        self,
        segment: WireSegment,
        on_net_selected: Optional[Callable[[str], None]] = None,
        on_net_hovered: Optional[Callable[[str, bool], None]] = None,
        tooltip: Optional[str] = None,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.segment = segment
        self.net_name = segment.net_name
        self.on_net_selected = on_net_selected
        self.on_net_hovered = on_net_hovered

        self._is_highlighted = False
        self._is_hovered = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip if tooltip else f"<b>Net:</b> {self.net_name}")

        # Segment bounds
        x1, y1 = segment.p1.x, segment.p1.y
        x2, y2 = segment.p2.x, segment.p2.y
        self._min_x = min(x1, x2)
        self._max_x = max(x1, x2)
        self._min_y = min(y1, y2)
        self._max_y = max(y1, y2)

    def boundingRect(self) -> QRectF:
        # Generous hit-box margin around the line for easy cursor detection
        w = max(6.0, self._max_x - self._min_x)
        h = max(6.0, self._max_y - self._min_y)
        return QRectF(self._min_x - 4.0, self._min_y - 4.0, w + 8.0, h + 8.0)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        path.moveTo(self.segment.p1.x, self.segment.p1.y)
        path.lineTo(self.segment.p2.x, self.segment.p2.y)
        stroker = QtGui.QPainterPathStroker()
        stroker.setWidth(8.0)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        return stroker.createStroke(path)

    def set_highlighted(self, state: bool):
        if self._is_highlighted != state:
            self._is_highlighted = state
            self.setZValue(10.0 if (self._is_highlighted or self._is_hovered) else 0.0)
            self.update()

    def set_hovered(self, state: bool):
        if self._is_hovered != state:
            self._is_hovered = state
            self.setZValue(10.0 if (self._is_highlighted or self._is_hovered) else 0.0)
            self.update()

    def hoverEnterEvent(self, event):
        if self.on_net_hovered:
            self.on_net_hovered(self.net_name, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.on_net_hovered:
            self.on_net_hovered(self.net_name, False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.on_net_selected:
                self.on_net_selected(self.net_name)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        if self._is_highlighted:
            pen = QPen(WirePalette.WIRE_HIGHLIGHT, 3.2)
        elif self._is_hovered:
            pen = QPen(WirePalette.WIRE_HOVER, 2.6)
        else:
            pen = QPen(WirePalette.WIRE_NORMAL, 1.5)

        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        painter.setPen(pen)

        p1 = QPointF(self.segment.p1.x, self.segment.p1.y)
        p2 = QPointF(self.segment.p2.x, self.segment.p2.y)
        painter.drawLine(p1, p2)


class SolderDotGraphicsItem(QtWidgets.QGraphicsItem):
    """
    QGraphicsItem representing a circular solder dot (•) at wire branch junctions.
    """

    def __init__(
        self,
        dot: SolderDot,
        on_net_selected: Optional[Callable[[str], None]] = None,
        on_net_hovered: Optional[Callable[[str, bool], None]] = None,
        tooltip: Optional[str] = None,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.dot = dot
        self.net_name = dot.net_name
        self.on_net_selected = on_net_selected
        self.on_net_hovered = on_net_hovered
        self.radius = dot.radius

        self._is_highlighted = False
        self._is_hovered = False

        self.setPos(dot.x, dot.y)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip if tooltip else f"<b>Branch Junction (•):</b> {self.net_name}")
        self.setZValue(5.0)

    def boundingRect(self) -> QRectF:
        r = self.radius + 3.0
        return QRectF(-r, -r, 2 * r, 2 * r)

    def shape(self) -> QPainterPath:
        path = QPainterPath()
        r = self.radius + 4.0
        path.addEllipse(QPointF(0, 0), r, r)
        return path

    def set_highlighted(self, state: bool):
        if self._is_highlighted != state:
            self._is_highlighted = state
            self.setZValue(12.0 if (self._is_highlighted or self._is_hovered) else 5.0)
            self.update()

    def set_hovered(self, state: bool):
        if self._is_hovered != state:
            self._is_hovered = state
            self.setZValue(12.0 if (self._is_highlighted or self._is_hovered) else 5.0)
            self.update()

    def hoverEnterEvent(self, event):
        if self.on_net_hovered:
            self.on_net_hovered(self.net_name, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.on_net_hovered:
            self.on_net_hovered(self.net_name, False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.on_net_selected:
                self.on_net_selected(self.net_name)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        r = self.radius
        if self._is_highlighted or self._is_hovered:
            painter.setBrush(QBrush(WirePalette.SOLDER_DOT_HIGHLIGHT))
            painter.setPen(QPen(Qt.GlobalColor.black, 1.0))
            r += 1.5
        else:
            painter.setBrush(QBrush(WirePalette.SOLDER_DOT))
            painter.setPen(Qt.PenStyle.NoPen)

        painter.drawEllipse(QPointF(0, 0), r, r)


class HFNStubGraphicsItem(QtWidgets.QGraphicsItem):
    """
    QGraphicsItem representing a decoupled High-Fanout Net (HFN) local pin stub
    with a directional badge and net label.
    """

    def __init__(
        self,
        stub: HFNStub,
        on_net_selected: Optional[Callable[[str], None]] = None,
        on_net_hovered: Optional[Callable[[str, bool], None]] = None,
        tooltip: Optional[str] = None,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.stub = stub
        self.net_name = stub.net_name
        self.on_net_selected = on_net_selected
        self.on_net_hovered = on_net_hovered

        self._is_highlighted = False
        self._is_hovered = False

        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(tooltip if tooltip else f"<b>Decoupled Global Signal:</b> {self.net_name}")
        self.setZValue(2.0)

        # Compute bounding rectangle including tag
        x1, y1 = stub.start.x, stub.start.y
        x2, y2 = stub.end.x, stub.end.y
        min_x = min(x1, x2) - 35.0
        max_x = max(x1, x2) + 35.0
        min_y = min(y1, y2) - 18.0
        max_y = max(y1, y2) + 18.0
        self._bbox = QRectF(min_x, min_y, max_x - min_x, max_y - min_y)

    def boundingRect(self) -> QRectF:
        return self._bbox

    def set_highlighted(self, state: bool):
        if self._is_highlighted != state:
            self._is_highlighted = state
            self.setZValue(11.0 if (self._is_highlighted or self._is_hovered) else 2.0)
            self.update()

    def set_hovered(self, state: bool):
        if self._is_hovered != state:
            self._is_hovered = state
            self.setZValue(11.0 if (self._is_highlighted or self._is_hovered) else 2.0)
            self.update()

    def hoverEnterEvent(self, event):
        if self.on_net_hovered:
            self.on_net_hovered(self.net_name, True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        if self.on_net_hovered:
            self.on_net_hovered(self.net_name, False)
        super().hoverLeaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self.on_net_selected:
                self.on_net_selected(self.net_name)
            event.accept()
        else:
            super().mousePressEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        # Draw stub wire segment
        if self._is_highlighted:
            pen = QPen(WirePalette.WIRE_HIGHLIGHT, 3.0)
        elif self._is_hovered:
            pen = QPen(WirePalette.WIRE_HOVER, 2.5)
        else:
            pen = QPen(WirePalette.HFN_STUB_WIRE, 1.5)

        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(pen)
        p1 = QPointF(self.stub.start.x, self.stub.start.y)
        p2 = QPointF(self.stub.end.x, self.stub.end.y)
        painter.drawLine(p1, p2)

        # Draw tag badge if zoomed in sufficiently
        if lod >= 0.2:
            tag_pos = p1 if not self.stub.is_driver else p2
            tag_w = max(24.0, len(self.stub.label) * 6.0 + 8.0)
            tag_h = 12.0

            if self.stub.arrow_direction == "RIGHT":
                tag_rect = QRectF(tag_pos.x() - tag_w, tag_pos.y() - tag_h / 2.0, tag_w, tag_h)
            elif self.stub.arrow_direction == "LEFT":
                tag_rect = QRectF(tag_pos.x(), tag_pos.y() - tag_h / 2.0, tag_w, tag_h)
            elif self.stub.arrow_direction == "UP":
                tag_rect = QRectF(tag_pos.x() - tag_w / 2.0, tag_pos.y(), tag_w, tag_h)
            else:
                tag_rect = QRectF(tag_pos.x() - tag_w / 2.0, tag_pos.y() - tag_h, tag_w, tag_h)

            is_lit = self._is_highlighted or self._is_hovered
            painter.setBrush(QBrush(WirePalette.HFN_TAG_BG))
            painter.setPen(QPen(WirePalette.HFN_TAG_HIGHLIGHT if is_lit else WirePalette.HFN_TAG_BORDER, 1.5 if is_lit else 1.0))
            painter.drawRoundedRect(tag_rect, 2.0, 2.0)

            # Draw tag text
            painter.setPen(QPen(WirePalette.HFN_TAG_HIGHLIGHT if is_lit else WirePalette.HFN_TAG_TEXT))
            font = QFont("monospace", 6, QFont.Weight.Bold if is_lit else QFont.Weight.Normal)
            painter.setFont(font)
            painter.drawText(tag_rect, Qt.AlignmentFlag.AlignCenter, self.stub.label)
