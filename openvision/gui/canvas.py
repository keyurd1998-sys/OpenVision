"""
Hardware-accelerated 2D vector canvas for OpenVision.
Provides QGraphicsView with cursor-centered zoom, infinite panning,
fast spatial indexing, net highlighting, and level-of-detail rendering.
"""

from typing import Dict, List, Optional, Set, Tuple
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QRectF, QPointF, pyqtSignal
from PyQt6.QtGui import QPainter, QColor, QPen, QBrush

from openvision.placement.placement_engine import PlacementResult
from openvision.routing.router_models import RoutingResult
from openvision.gui.gate_items import GateGraphicsItem, Palette
from openvision.gui.wire_items import (
    WireGraphicsItem,
    SolderDotGraphicsItem,
    HFNStubGraphicsItem,
    WirePalette,
)
from openvision.routing.pin_resolver import PinResolver


class SchematicCanvas(QtWidgets.QGraphicsView):
    """
    High-performance 2D schematic graphics view.
    Supports cursor-centered zoom, middle-mouse and space-drag panning,
    instantaneous net selection highlighting, and full schematic rendering.
    """

    # Signals
    net_selected = pyqtSignal(str)     # Emits net name when selected
    gate_selected = pyqtSignal(str)    # Emits node/instance name when selected
    cursor_moved = pyqtSignal(float, float)  # Emits (canvas_x, canvas_y)

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)

        self._scene = QtWidgets.QGraphicsScene(self)
        self._scene.setItemIndexMethod(QtWidgets.QGraphicsScene.ItemIndexMethod.BspTreeIndex)
        self.setScene(self._scene)

        # Rendering and performance flags
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing |
            QPainter.RenderHint.TextAntialiasing |
            QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setViewportUpdateMode(QtWidgets.QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setResizeAnchor(QtWidgets.QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setDragMode(QtWidgets.QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.setBackgroundBrush(QBrush(Palette.BG_DARK))

        # Pan and interaction states
        self._is_panning = False
        self._pan_start_pos = QtCore.QPoint()
        self._space_pressed = False
        self._zoom_factor_in = 1.20
        self._zoom_factor_out = 1.0 / 1.20

        # Indices for instantaneous net and gate lookup
        self._gate_items: Dict[str, GateGraphicsItem] = {}
        self._net_wire_items: Dict[str, List[WireGraphicsItem]] = {}
        self._net_dot_items: Dict[str, List[SolderDotGraphicsItem]] = {}
        self._net_stub_items: Dict[str, List[HFNStubGraphicsItem]] = {}

        self._current_highlighted_net: Optional[str] = None
        self._placement_res: Optional[PlacementResult] = None
        self._routing_res: Optional[RoutingResult] = None

    def load_schematic(
        self,
        placement: PlacementResult,
        routing: RoutingResult,
    ) -> None:
        """
        Clears and populates the canvas with gates, wires, solder dots, and HFN stubs.
        """
        self._scene.clear()
        self._gate_items.clear()
        self._net_wire_items.clear()
        self._net_dot_items.clear()
        self._net_stub_items.clear()
        self._current_highlighted_net = None

        self._placement_res = placement
        self._routing_res = routing

        pin_res = PinResolver(placement.graph)

        # 1. Add Gate Items
        for node_id, node in placement.graph.nodes.items():
            pins = pin_res.get_node_pins(node_id)
            gate_item = GateGraphicsItem(node=node, pins=pins)
            self._scene.addItem(gate_item)
            self._gate_items[node_id] = gate_item

        # 2. Add Wires, Solder Dots, and HFN Stubs
        for net_name, route in routing.net_routes.items():
            wire_list: List[WireGraphicsItem] = []
            dot_list: List[SolderDotGraphicsItem] = []
            stub_list: List[HFNStubGraphicsItem] = []

            # Wires
            for seg in route.segments:
                w_item = WireGraphicsItem(
                    segment=seg,
                    on_net_selected=self.highlight_net,
                )
                self._scene.addItem(w_item)
                wire_list.append(w_item)

            # Solder dots
            for dot in route.solder_dots:
                d_item = SolderDotGraphicsItem(
                    dot=dot,
                    on_net_selected=self.highlight_net,
                )
                self._scene.addItem(d_item)
                dot_list.append(d_item)

            # HFN Stubs
            for stub in route.hfn_stubs:
                s_item = HFNStubGraphicsItem(
                    stub=stub,
                    on_net_selected=self.highlight_net,
                )
                self._scene.addItem(s_item)
                stub_list.append(s_item)

            self._net_wire_items[net_name] = wire_list
            self._net_dot_items[net_name] = dot_list
            self._net_stub_items[net_name] = stub_list

        # Set scene bounding box with comfortable margin
        min_x, min_y, max_x, max_y = placement.bbox
        margin = 100.0
        self._scene.setSceneRect(
            min_x - margin,
            min_y - margin,
            (max_x - min_x) + 2 * margin,
            (max_y - min_y) + 2 * margin,
        )

        self.fit_in_view()

    def fit_in_view(self) -> None:
        """Fits the entire schematic within the current canvas viewport."""
        rect = self._scene.sceneRect()
        if not rect.isEmpty():
            self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)

    def zoom_in(self) -> None:
        """Zooms in by the default zoom factor."""
        self.scale(self._zoom_factor_in, self._zoom_factor_in)

    def zoom_out(self) -> None:
        """Zooms out by the default zoom factor."""
        self.scale(self._zoom_factor_out, self._zoom_factor_out)

    def reset_zoom(self) -> None:
        """Resets canvas scale to 1:1."""
        self.resetTransform()

    def highlight_net(self, net_name: Optional[str]) -> None:
        """
        Highlights all wire segments, solder dots, and stubs for the given net,
        and un-highlights previously selected nets.
        """
        # Deselect old net
        if self._current_highlighted_net and self._current_highlighted_net in self._net_wire_items:
            old = self._current_highlighted_net
            for w in self._net_wire_items.get(old, []):
                w.set_highlighted(False)
            for d in self._net_dot_items.get(old, []):
                d.set_highlighted(False)
            for s in self._net_stub_items.get(old, []):
                s.set_highlighted(False)

        self._current_highlighted_net = net_name

        # Highlight new net
        if net_name:
            for w in self._net_wire_items.get(net_name, []):
                w.set_highlighted(True)
            for d in self._net_dot_items.get(net_name, []):
                d.set_highlighted(True)
            for s in self._net_stub_items.get(net_name, []):
                s.set_highlighted(True)

            self.net_selected.emit(net_name)

    def find_and_center_node(self, node_name: str) -> bool:
        """Searches for a gate or port by name, highlights it, and centers the view."""
        # Check exact ID or match instance/port name
        target_item = self._gate_items.get(node_name)
        if not target_item:
            target_item = self._gate_items.get(f"inst:{node_name}")
        if not target_item:
            target_item = self._gate_items.get(f"port_in:{node_name}")
        if not target_item:
            target_item = self._gate_items.get(f"port_out:{node_name}")

        if not target_item:
            # Case-insensitive search
            for item in self._gate_items.values():
                if item.node.name.lower() == node_name.lower():
                    target_item = item
                    break

        if target_item:
            self._scene.clearSelection()
            target_item.setSelected(True)
            self.centerOn(target_item)
            self.gate_selected.emit(target_item.node.name)
            return True

        return False

    def find_and_center_net(self, net_name: str) -> bool:
        """Searches for a net by name, highlights it, and centers the view on its driver."""
        if net_name in self._net_wire_items or net_name in self._net_stub_items:
            self.highlight_net(net_name)
            # Center on first segment or stub
            wire_list = self._net_wire_items.get(net_name, [])
            if wire_list:
                self.centerOn(wire_list[0])
            else:
                stub_list = self._net_stub_items.get(net_name, [])
                if stub_list:
                    self.centerOn(stub_list[0])
            return True
        return False

    def highlight_cone(self, cone) -> None:
        """Highlights all gates and nets belonging to an extracted logic cone."""
        self._scene.clearSelection()

        # Highlight all gates in cone
        first_item = None
        for inst_name in cone.instances:
            item = self._gate_items.get(f"inst:{inst_name}") or self._gate_items.get(inst_name)
            if item:
                item.setSelected(True)
                if not first_item:
                    first_item = item

        # Highlight all nets in cone
        for net_name in cone.nets:
            for w in self._net_wire_items.get(net_name, []):
                w.set_highlighted(True)
            for d in self._net_dot_items.get(net_name, []):
                d.set_highlighted(True)
            for s in self._net_stub_items.get(net_name, []):
                s.set_highlighted(True)

        if first_item:
            self.centerOn(first_item)

    def clear_cone_highlight(self) -> None:
        """Clears all gate selections and net highlights."""
        self._scene.clearSelection()
        self.highlight_net(None)

    # -------------------------------------------------------------------------
    # Mouse & Keyboard Event Handlers
    # -------------------------------------------------------------------------

    def wheelEvent(self, event: QtGui.QWheelEvent):
        """Cursor-centered zooming using mouse wheel."""
        if event.angleDelta().y() > 0:
            factor = self._zoom_factor_in
        else:
            factor = self._zoom_factor_out

        self.scale(factor, factor)
        event.accept()

    def mousePressEvent(self, event: QtGui.QMouseEvent):
        """Middle-click drag or space+left-click to pan."""
        if event.button() == Qt.MouseButton.MiddleButton or (event.button() == Qt.MouseButton.LeftButton and self._space_pressed):
            self._is_panning = True
            self._pan_start_pos = event.pos()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        super().mousePressEvent(event)

        # If clicking empty canvas area, deselect current net
        item = self.itemAt(event.pos())
        if item is None and event.button() == Qt.MouseButton.LeftButton:
            self.highlight_net(None)

    def mouseMoveEvent(self, event: QtGui.QMouseEvent):
        """Handles active panning and updates cursor canvas coordinate."""
        if self._is_panning:
            delta = event.pos() - self._pan_start_pos
            self._pan_start_pos = event.pos()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return

        scene_pos = self.mapToScene(event.pos())
        self.cursor_moved.emit(scene_pos.x(), scene_pos.y())
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QtGui.QMouseEvent):
        """Stops panning."""
        if event.button() in (Qt.MouseButton.MiddleButton, Qt.MouseButton.LeftButton) and self._is_panning:
            self._is_panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QtGui.QKeyEvent):
        """Keyboard navigation shortcuts."""
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = True
            self.setCursor(Qt.CursorShape.OpenHandCursor)
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_F, Qt.Key.Key_Home):
            self.fit_in_view()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
            self.zoom_in()
            event.accept()
            return
        elif event.key() in (Qt.Key.Key_Minus, Qt.Key.Key_Underscore):
            self.zoom_out()
            event.accept()
            return
        elif event.key() == Qt.Key.Key_Escape:
            self.highlight_net(None)
            self._scene.clearSelection()
            event.accept()
            return

        super().keyPressEvent(event)

    def keyReleaseEvent(self, event: QtGui.QKeyEvent):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self._space_pressed = False
            if not self._is_panning:
                self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        super().keyReleaseEvent(event)
