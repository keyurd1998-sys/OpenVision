"""
Gate graphic items for OpenVision PyQt6 canvas.
Renders standard IEEE Std 91/ANSI Y32 logic gate symbols (AND, NAND, OR, NOR, XOR, XNOR,
INV, BUF, MUX, DFF, MACRO, PORTS) with Level-of-Detail (LOD) optimization, hover states,
and interactive net highlighting.
"""

from typing import Dict, List, Optional, Tuple, Any
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QPainterPath, QColor, QPen, QBrush, QFont

from openvision.placement.cycle_breaker import PlacementNode
from openvision.ingestion.symbol_classifier import GateType, PinRole
from openvision.routing.router_models import PinLocation, PinExitDirection


class Palette:
    """Dark EDA schematic color palette matching commercial reference tools."""
    BG_DARK = QColor("#18191f")
    GATE_BODY = QColor("#22252e")
    GATE_BORDER = QColor("#4fc3f7")          # Crisp light blue
    GATE_BORDER_SELECTED = QColor("#ffeb3b") # Bright yellow
    GATE_BORDER_HOVER = QColor("#00e676")    # Neon green
    GATE_FILL = QColor("#282c37")
    DFF_FILL = QColor("#1e2836")
    PORT_IN_FILL = QColor("#1b382b")
    PORT_IN_BORDER = QColor("#00e676")
    PORT_OUT_FILL = QColor("#3e2723")
    PORT_OUT_BORDER = QColor("#ff7043")
    TEXT_PRIMARY = QColor("#e0e0e0")
    TEXT_MUTED = QColor("#90a4ae")
    PIN_COLOR = QColor("#81d4fa")
    BUBBLE_FILL = QColor("#18191f")
    CLOCK_TRIANGLE = QColor("#ffb74d")


class GateGraphicsItem(QtWidgets.QGraphicsItem):
    """
    QGraphicsItem representing a placed logic gate, flip-flop, or primary port.
    Draws authentic IEEE Std 91 gate shapes with Level-of-Detail (LOD) acceleration.
    """

    def __init__(
        self,
        node: PlacementNode,
        pins: List[PinLocation],
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.node = node
        self.pins = pins

        self.setPos(node.x, node.y)
        self.setFlags(
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable |
            QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptHoverEvents(True)

        self._width = node.width
        self._height = node.height
        self._is_hovered = False

        # Precompute IEEE path
        self._gate_path = self._build_gate_path()
        self._bubble_paths = self._build_bubble_paths()

        # Tooltip
        inst_type = getattr(node.ref, "cell_type", node.kind)
        gate_type = getattr(node.ref, "gate_type", None)
        gt_name = gate_type.value if gate_type else node.kind
        self.setToolTip(
            f"<b>Instance:</b> {node.name}<br>"
            f"<b>Cell Type:</b> {inst_type}<br>"
            f"<b>Symbol:</b> {gt_name}<br>"
            f"<b>Rank:</b> {node.rank}<br>"
            f"<b>Coords:</b> ({node.x:.1f}, {node.y:.1f})"
        )

    def boundingRect(self) -> QRectF:
        # Include small margin for pin stubs and hover glow
        return QRectF(-10.0, -10.0, self._width + 20.0, self._height + 20.0)

    def hoverEnterEvent(self, event):
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def paint(self, painter: QPainter, option, widget=None):
        lod = option.levelOfDetailFromTransform(painter.worldTransform())

        w = self._width
        h = self._height

        # Pen & Brush selection
        if self.isSelected():
            pen = QPen(Palette.GATE_BORDER_SELECTED, 2.5)
        elif self._is_hovered:
            pen = QPen(Palette.GATE_BORDER_HOVER, 2.0)
        else:
            if self.node.kind == "PRIMARY_INPUT":
                pen = QPen(Palette.PORT_IN_BORDER, 1.5)
            elif self.node.kind == "PRIMARY_OUTPUT":
                pen = QPen(Palette.PORT_OUT_BORDER, 1.5)
            else:
                pen = QPen(Palette.GATE_BORDER, 1.5)

        painter.setPen(pen)

        # LOD Optimization: When zoomed far out, draw simplified fast bounding box
        if lod < 0.12:
            painter.setBrush(QBrush(Palette.GATE_FILL))
            painter.drawRect(QRectF(0, 0, w, h))
            return

        # Choose fill brush
        if self.node.kind == "PRIMARY_INPUT":
            brush = QBrush(Palette.PORT_IN_FILL)
        elif self.node.kind == "PRIMARY_OUTPUT":
            brush = QBrush(Palette.PORT_OUT_FILL)
        elif self.node.kind == "DFF":
            brush = QBrush(Palette.DFF_FILL)
        else:
            brush = QBrush(Palette.GATE_FILL)

        painter.setBrush(brush)

        # Draw main IEEE shape
        if not self._gate_path.isEmpty():
            painter.drawPath(self._gate_path)
        else:
            # Fallback rectangle
            painter.drawRoundedRect(QRectF(0, 0, w, h), 4.0, 4.0)

        # Draw inverting bubble circles if present
        if self._bubble_paths:
            painter.setBrush(QBrush(Palette.BUBBLE_FILL))
            for bpath in self._bubble_paths:
                painter.drawPath(bpath)

        # Draw DFF internal clock triangle (>) on South/bottom edge
        if self.node.kind == "DFF" and lod >= 0.25:
            clk_pin = next((p for p in self.pins if p.direction == PinExitDirection.SOUTH and "CLK" in p.pin_name.upper()), None)
            if clk_pin:
                local_clk_x = clk_pin.x - self.node.x
                clk_tri = QPainterPath()
                clk_tri.moveTo(local_clk_x - 5.0, h)
                clk_tri.lineTo(local_clk_x, h - 8.0)
                clk_tri.lineTo(local_clk_x + 5.0, h)
                painter.setPen(QPen(Palette.CLOCK_TRIANGLE, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(clk_tri)

        # Draw Labels when sufficiently zoomed in
        if lod >= 0.25:
            self._paint_labels(painter, w, h, lod)

    def _paint_labels(self, painter: QPainter, w: float, h: float, lod: float):
        """Draws instance name, cell type, and pin names."""
        painter.setPen(QPen(Palette.TEXT_PRIMARY))
        font = QFont("monospace", 8)
        painter.setFont(font)

        # Main label (Instance Name or Port Name)
        text_rect = QRectF(2.0, 2.0, w - 4.0, h - 4.0)
        label_text = self.node.name
        # Shorten very long instance names if needed
        if len(label_text) > 12 and not self.node.is_port:
            label_text = label_text[:11] + "…"

        painter.drawText(text_rect, Qt.AlignmentFlag.AlignCenter, label_text)

        # Cell type sub-label below center
        if lod >= 0.45 and not self.node.is_port:
            cell_type = getattr(self.node.ref, "cell_type", "")
            if cell_type:
                # Truncate prefix like sky130_fd_sc_hd__
                short_cell = cell_type.split("__")[-1] if "__" in cell_type else cell_type
                painter.setPen(QPen(Palette.TEXT_MUTED))
                sub_font = QFont("monospace", 6)
                painter.setFont(sub_font)
                painter.drawText(
                    QRectF(2.0, h - 14.0, w - 4.0, 12.0),
                    Qt.AlignmentFlag.AlignCenter,
                    short_cell,
                )

    def _build_gate_path(self) -> QPainterPath:
        """Constructs the IEEE Std 91 graphic path for this gate type."""
        w = self._width
        h = self._height
        path = QPainterPath()

        gate_type = None
        if self.node.ref:
            gate_type = getattr(self.node.ref, "gate_type", None)

        # Inverter or Buffer (Triangle)
        if gate_type in (GateType.INV, GateType.BUF):
            r_b = 4.0 if gate_type == GateType.INV else 0.0
            tip_x = w - r_b * 2.0
            path.moveTo(0, 0)
            path.lineTo(tip_x, h / 2.0)
            path.lineTo(0, h)
            path.closeSubpath()
            return path

        # AND or NAND Gate
        if gate_type in (GateType.AND, GateType.NAND):
            r_b = 4.0 if gate_type == GateType.NAND else 0.0
            front_x = w - r_b * 2.0
            mid_x = front_x * 0.5
            path.moveTo(0, 0)
            path.lineTo(mid_x, 0)
            # Semicircular front
            path.arcTo(mid_x - front_x * 0.5, 0, front_x, h, 90.0, -180.0)
            path.lineTo(0, h)
            path.closeSubpath()
            return path

        # OR or NOR Gate
        if gate_type in (GateType.OR, GateType.NOR):
            r_b = 4.0 if gate_type == GateType.NOR else 0.0
            tip_x = w - r_b * 2.0
            # Curved back (inward)
            path.moveTo(0, 0)
            path.quadTo(w * 0.22, h / 2.0, 0, h)
            # Curved bottom to tip
            path.quadTo(w * 0.6, h * 0.95, tip_x, h / 2.0)
            # Curved top back to (0, 0)
            path.quadTo(w * 0.6, h * 0.05, 0, 0)
            path.closeSubpath()
            return path

        # XOR or XNOR Gate
        if gate_type in (GateType.XOR, GateType.XNOR):
            r_b = 4.0 if gate_type == GateType.XNOR else 0.0
            tip_x = w - r_b * 2.0
            # Main body
            path.moveTo(w * 0.1, 0)
            path.quadTo(w * 0.32, h / 2.0, w * 0.1, h)
            path.quadTo(w * 0.65, h * 0.95, tip_x, h / 2.0)
            path.quadTo(w * 0.65, h * 0.05, w * 0.1, 0)
            path.closeSubpath()
            # Second back arc
            path.moveTo(0, 0)
            path.quadTo(w * 0.22, h / 2.0, 0, h)
            return path

        # MUX 2:1 (Trapezoid)
        if gate_type == GateType.MUX2:
            path.moveTo(0, 0)
            path.lineTo(w, h * 0.2)
            path.lineTo(w, h * 0.8)
            path.lineTo(0, h)
            path.closeSubpath()
            return path

        # Primary Ports (Arrow badges)
        if self.node.kind == "PRIMARY_INPUT":
            # Points right towards the circuit: [ ▶ ]
            path.moveTo(0, 0)
            path.lineTo(w - 8.0, 0)
            path.lineTo(w, h / 2.0)
            path.lineTo(w - 8.0, h)
            path.lineTo(0, h)
            path.closeSubpath()
            return path

        if self.node.kind == "PRIMARY_OUTPUT":
            # Signals enter from the left: [ ▶ ]
            path.moveTo(0, h / 2.0)
            path.lineTo(8.0, 0)
            path.lineTo(w, 0)
            path.lineTo(w, h)
            path.lineTo(8.0, h)
            path.closeSubpath()
            return path

        # Standard rounded box for DFF, Adders, AOI, OAI, Macros
        path.addRoundedRect(QRectF(0, 0, w, h), 4.0, 4.0)
        return path

    def _build_bubble_paths(self) -> List[QPainterPath]:
        """Constructs circle paths for inverting bubble pins."""
        bubbles = []
        w = self._width
        h = self._height
        r_b = 3.5

        gate_type = getattr(self.node.ref, "gate_type", None) if self.node.ref else None

        if gate_type in (GateType.INV, GateType.NAND, GateType.NOR, GateType.XNOR):
            # Output bubble at (w - r_b, h / 2)
            bp = QPainterPath()
            bp.addEllipse(QPointF(w - r_b, h / 2.0), r_b, r_b)
            bubbles.append(bp)

        # Check instance bubble pins
        classification = getattr(self.node.ref, "classification", None)
        if classification and classification.bubble_pins:
            for b_pin in classification.bubble_pins:
                pin_loc = next((p for p in self.pins if p.pin_name == b_pin), None)
                if pin_loc:
                    lx = pin_loc.x - self.node.x
                    ly = pin_loc.y - self.node.y
                    bp = QPainterPath()
                    bp.addEllipse(QPointF(lx, ly), r_b, r_b)
                    bubbles.append(bp)

        return bubbles
