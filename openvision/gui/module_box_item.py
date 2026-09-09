"""
Top-level hierarchical module box vector graphics item for OpenVision.
Renders the design as a clean rectangular block with West input pins,
East output pins, module metadata, and double-click hierarchy expansion.
"""

from typing import Callable, Dict, List, Optional, Tuple
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QRectF, QPointF
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QPainterPath

from openvision.ingestion.netlist_parser import NetlistModule, NetlistPort
from openvision.gui.gate_items import Palette


class ModuleBoxPalette:
    """Color palette for top-level hierarchical module boxes."""
    BOX_FILL = QColor("#141923")          # Deep navy/slate background
    BOX_BORDER = QColor("#38bdf8")        # Bright cyan border
    BOX_BORDER_HOVER = QColor("#facc15")  # Vibrant gold on hover
    BOX_HEADER_FILL = QColor("#1e293b")   # Slate header bar
    HEADER_TEXT = QColor("#ffffff")       # White title
    SUBTITLE_TEXT = QColor("#94a3b8")     # Muted slate subtitle
    BADGE_FILL = QColor("#0369a1")        # Cyan badge fill
    BADGE_TEXT = QColor("#e0f2fe")        # Light cyan badge text
    PIN_LINE = QColor("#38bdf8")          # Pin stub color
    PIN_DOT = QColor("#0284c7")           # Terminal pin dot
    PIN_TEXT = QColor("#e2e8f0")          # Crisp white/slate pin label
    PIN_BUS_TEXT = QColor("#7dd3fc")      # Accent color for bus dimensions
    HINT_BOX_FILL = QColor("#1e293b")     # Expansion call-to-action box
    HINT_BOX_BORDER = QColor("#0284c7")   # Border for call-to-action
    HINT_TEXT = QColor("#38bdf8")         # Expansion text prompt


class ModuleBoxGraphicsItem(QtWidgets.QGraphicsItem):
    """
    Renders a structural Verilog module as an architectural black-box symbol
    with rectangular boundary, labeled IO pin stubs, and double-click interaction.
    """

    def __init__(
        self,
        module: NetlistModule,
        on_double_click: Optional[Callable[[NetlistModule], None]] = None,
        parent: Optional[QtWidgets.QGraphicsItem] = None,
    ):
        super().__init__(parent)
        self.module = module
        self.on_double_click = on_double_click

        # Interaction flags
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFlag(QtWidgets.QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setToolTip(
            f"Module: {module.name}\n"
            f"Instances: {len(module.instances):,} gates\n"
            f"Ports: {len(module.ports)} primary I/O pins\n"
            f"Action: Double-click to expand hierarchy"
        )

        self._is_hovered = False

        # Classify and order ports
        self.input_ports: List[NetlistPort] = []
        self.output_ports: List[NetlistPort] = []

        for port in module.ports.values():
            if port.direction in ("input", "inout"):
                self.input_ports.append(port)
            else:
                self.output_ports.append(port)

        # Sort ports cleanly: clock/reset first, then alphanumeric
        def port_sort_key(p: NetlistPort):
            n = p.name.lower()
            if "clk" in n or "clock" in n:
                return (0, n)
            if "rst" in n or "reset" in n:
                return (1, n)
            return (2, n)

        self.input_ports.sort(key=port_sort_key)
        self.output_ports.sort(key=lambda p: p.name.lower())

        # Layout geometry calculations
        self.pin_pitch = 30.0
        self.stub_length = 45.0
        self.header_height = 85.0
        self.footer_height = 65.0

        max_pins = max(len(self.input_ports), len(self.output_ports), 1)
        self.pins_height = max_pins * self.pin_pitch
        self.box_height = max(260.0, self.header_height + self.pins_height + self.footer_height)

        # Determine width based on text lengths
        max_in_len = max([len(self._format_port_name(p)) for p in self.input_ports], default=6)
        max_out_len = max([len(self._format_port_name(p)) for p in self.output_ports], default=6)
        name_len = len(self.module.name)

        min_w = max(420.0, (max_in_len + max_out_len) * 9.0 + 160.0, name_len * 14.0 + 120.0)
        self.box_width = min_w

        # Pin coordinate maps: port_name -> (terminal_point, connection_point)
        self._input_pin_coords: Dict[str, Tuple[QPointF, QPointF]] = {}
        self._output_pin_coords: Dict[str, Tuple[QPointF, QPointF]] = {}
        self._compute_pin_locations()

    def _format_port_name(self, port: NetlistPort) -> str:
        """Formats port name with bus dimensions if applicable."""
        if port.is_bus:
            return f"{port.name} [{port.msb}:{port.lsb}]"
        return port.name

    def _compute_pin_locations(self) -> None:
        """Calculates (X, Y) positions for input and output pin stubs."""
        # Calculate vertical centering for pins
        in_start_y = self.header_height + (self.pins_height - len(self.input_ports) * self.pin_pitch) / 2.0 + self.pin_pitch / 2.0
        out_start_y = self.header_height + (self.pins_height - len(self.output_ports) * self.pin_pitch) / 2.0 + self.pin_pitch / 2.0

        for i, port in enumerate(self.input_ports):
            y = in_start_y + i * self.pin_pitch
            term_pt = QPointF(-self.stub_length, y)
            box_pt = QPointF(0.0, y)
            self._input_pin_coords[port.name] = (term_pt, box_pt)

        for i, port in enumerate(self.output_ports):
            y = out_start_y + i * self.pin_pitch
            box_pt = QPointF(self.box_width, y)
            term_pt = QPointF(self.box_width + self.stub_length, y)
            self._output_pin_coords[port.name] = (term_pt, box_pt)

    def boundingRect(self) -> QRectF:
        """Enclosing bounding rectangle including all external pin stubs."""
        margin = 15.0
        return QRectF(
            -self.stub_length - margin,
            -margin,
            self.box_width + 2.0 * (self.stub_length + margin),
            self.box_height + 2.0 * margin,
        )

    def paint(
        self,
        painter: QPainter,
        option: QtWidgets.QStyleOptionGraphicsItem,
        widget: Optional[QtWidgets.QWidget] = None,
    ) -> None:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)

        # 1. Outer Box Shadow
        shadow_rect = QRectF(4.0, 4.0, self.box_width, self.box_height)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(0, 0, 0, 90))
        painter.drawRoundedRect(shadow_rect, 10.0, 10.0)

        # 2. Main Box Body
        box_rect = QRectF(0.0, 0.0, self.box_width, self.box_height)
        border_col = ModuleBoxPalette.BOX_BORDER_HOVER if self._is_hovered else ModuleBoxPalette.BOX_BORDER
        pen_width = 3.0 if self._is_hovered else 2.0

        painter.setPen(QPen(border_col, pen_width))
        painter.setBrush(QBrush(ModuleBoxPalette.BOX_FILL))
        painter.drawRoundedRect(box_rect, 8.0, 8.0)

        # 3. Header Bar Background
        header_path = QPainterPath()
        header_path.moveTo(0.0, 8.0)
        header_path.arcTo(0.0, 0.0, 16.0, 16.0, 180.0, -90.0)
        header_path.lineTo(self.box_width - 8.0, 0.0)
        header_path.arcTo(self.box_width - 16.0, 0.0, 16.0, 16.0, 90.0, -90.0)
        header_path.lineTo(self.box_width, self.header_height)
        header_path.lineTo(0.0, self.header_height)
        header_path.closeSubpath()

        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QBrush(ModuleBoxPalette.BOX_HEADER_FILL))
        painter.drawPath(header_path)

        # Header dividing line
        painter.setPen(QPen(border_col.darker(130), 1.5))
        painter.drawLine(QPointF(0.0, self.header_height), QPointF(self.box_width, self.header_height))

        # 4. Header Text (Module Name & Statistics)
        painter.setPen(ModuleBoxPalette.HEADER_TEXT)
        font_title = QFont("Monospace", 15, QFont.Weight.Bold)
        font_title.setStyleHint(QFont.StyleHint.TypeWriter)
        painter.setFont(font_title)
        painter.drawText(
            QRectF(15.0, 10.0, self.box_width - 30.0, 32.0),
            Qt.AlignmentFlag.AlignCenter,
            self.module.name,
        )

        font_sub = QFont("SansSerif", 9, QFont.Weight.Normal)
        painter.setFont(font_sub)
        painter.setPen(ModuleBoxPalette.SUBTITLE_TEXT)
        inst_count = len(self.module.instances)
        net_count = len(self.module.wires)
        painter.drawText(
            QRectF(15.0, 42.0, self.box_width - 30.0, 20.0),
            Qt.AlignmentFlag.AlignCenter,
            f"Structural Verilog Netlist | {inst_count:,} Cells | {net_count:,} Wires",
        )

        # Small hierarchical block badge
        badge_rect = QRectF(self.box_width / 2.0 - 65.0, 62.0, 130.0, 16.0)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(ModuleBoxPalette.BADGE_FILL)
        painter.drawRoundedRect(badge_rect, 4.0, 4.0)

        font_badge = QFont("Monospace", 8, QFont.Weight.Bold)
        painter.setFont(font_badge)
        painter.setPen(ModuleBoxPalette.BADGE_TEXT)
        painter.drawText(badge_rect, Qt.AlignmentFlag.AlignCenter, "TOP MODULE BLOCK")

        # 5. Render Input Pins (West Side)
        font_pin = QFont("Monospace", 9, QFont.Weight.Normal)
        font_pin.setStyleHint(QFont.StyleHint.TypeWriter)
        painter.setFont(font_pin)

        for port in self.input_ports:
            term_pt, box_pt = self._input_pin_coords[port.name]
            y = term_pt.y()

            # Wire stub
            is_clk = any(k in port.name.lower() for k in ("clk", "clock"))
            pen_stub = QPen(ModuleBoxPalette.PIN_LINE, 2.5 if port.is_bus else 1.5)
            painter.setPen(pen_stub)
            painter.drawLine(term_pt, box_pt)

            # Terminal indicator dot
            painter.setBrush(QBrush(ModuleBoxPalette.PIN_DOT))
            painter.drawEllipse(term_pt, 3.5, 3.5)

            # Direction triangle entering into the box
            tri = QPainterPath()
            tri.moveTo(box_pt.x() - 6.0, y - 3.5)
            tri.lineTo(box_pt.x() - 1.0, y)
            tri.lineTo(box_pt.x() - 6.0, y + 3.5)
            tri.closeSubpath()
            painter.setBrush(QBrush(ModuleBoxPalette.PIN_LINE))
            painter.drawPath(tri)

            # Clock internal triangle if applicable
            if is_clk:
                clk_tri = QPainterPath()
                clk_tri.moveTo(0.0, y - 6.0)
                clk_tri.lineTo(8.0, y)
                clk_tri.lineTo(0.0, y + 6.0)
                painter.setPen(QPen(ModuleBoxPalette.PIN_LINE, 1.5))
                painter.setBrush(Qt.BrushStyle.NoBrush)
                painter.drawPath(clk_tri)

            # Port label inside box
            label_text = self._format_port_name(port)
            label_x = 14.0 if is_clk else 8.0
            painter.setPen(ModuleBoxPalette.PIN_BUS_TEXT if port.is_bus else ModuleBoxPalette.PIN_TEXT)
            painter.drawText(
                QRectF(label_x, y - 10.0, (self.box_width / 2.0) - label_x - 10.0, 20.0),
                Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
                label_text,
            )

        # 6. Render Output Pins (East Side)
        for port in self.output_ports:
            term_pt, box_pt = self._output_pin_coords[port.name]
            y = term_pt.y()

            # Wire stub
            pen_stub = QPen(ModuleBoxPalette.PIN_LINE, 2.5 if port.is_bus else 1.5)
            painter.setPen(pen_stub)
            painter.drawLine(box_pt, term_pt)

            # Terminal indicator dot
            painter.setBrush(QBrush(ModuleBoxPalette.PIN_DOT))
            painter.drawEllipse(term_pt, 3.5, 3.5)

            # Direction triangle emerging out of the box
            tri = QPainterPath()
            tri.moveTo(term_pt.x() - 6.0, y - 3.5)
            tri.lineTo(term_pt.x() - 1.0, y)
            tri.lineTo(term_pt.x() - 6.0, y + 3.5)
            tri.closeSubpath()
            painter.setBrush(QBrush(ModuleBoxPalette.PIN_LINE))
            painter.drawPath(tri)

            # Port label inside box
            label_text = self._format_port_name(port)
            painter.setPen(ModuleBoxPalette.PIN_BUS_TEXT if port.is_bus else ModuleBoxPalette.PIN_TEXT)
            painter.drawText(
                QRectF(self.box_width / 2.0 + 10.0, y - 10.0, (self.box_width / 2.0) - 18.0, 20.0),
                Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter,
                label_text,
            )

        # 7. Call-to-action prompt at the bottom
        prompt_w = min(280.0, self.box_width - 40.0)
        prompt_rect = QRectF(
            (self.box_width - prompt_w) / 2.0,
            self.box_height - 48.0,
            prompt_w,
            32.0,
        )

        p_border = ModuleBoxPalette.BOX_BORDER_HOVER if self._is_hovered else ModuleBoxPalette.HINT_BOX_BORDER
        p_text = ModuleBoxPalette.BOX_BORDER_HOVER if self._is_hovered else ModuleBoxPalette.HINT_TEXT

        painter.setPen(QPen(p_border, 1.5))
        painter.setBrush(QBrush(ModuleBoxPalette.HINT_BOX_FILL))
        painter.drawRoundedRect(prompt_rect, 6.0, 6.0)

        font_prompt = QFont("Monospace", 9, QFont.Weight.Bold)
        painter.setFont(font_prompt)
        painter.setPen(p_text)
        painter.drawText(
            prompt_rect,
            Qt.AlignmentFlag.AlignCenter,
            "[ Double-Click to Expand Hierarchy ]",
        )

    # -------------------------------------------------------------------------
    # Event Handlers
    # -------------------------------------------------------------------------

    def hoverEnterEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._is_hovered = True
        self.update()
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event: QtWidgets.QGraphicsSceneHoverEvent) -> None:
        self._is_hovered = False
        self.update()
        super().hoverLeaveEvent(event)

    def mouseDoubleClickEvent(self, event: QtWidgets.QGraphicsSceneMouseEvent) -> None:
        if event.button() == Qt.MouseButton.LeftButton:
            event.accept()
            if self.on_double_click:
                self.on_double_click(self.module)
        else:
            super().mouseDoubleClickEvent(event)
