"""
Main application window for OpenVision schematic viewer.
Provides a modern dark EDA desktop interface with hierarchical instance browser,
interactive net searching, menu/toolbars, status bar, and image exporter.
"""

from pathlib import Path
from typing import Dict, List, Optional
from PyQt6 import QtCore, QtGui, QtWidgets
from PyQt6.QtCore import Qt, QSize
from PyQt6.QtGui import QAction, QIcon, QKeySequence, QFont

from openvision import __version__
from openvision.ingestion.liberty_parser import parse_liberty_file, find_default_liberty, LibertyLibrary
from openvision.ingestion.netlist_parser import parse_netlist_file, Netlist
from openvision.placement.placement_engine import run_placement, PlacementResult
from openvision.routing import route_placement, RoutingResult
from openvision.gui.canvas import SchematicCanvas
from openvision.gui.exporter import export_scene_to_image


DARK_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #18191f;
    color: #e0e0e0;
    font-family: 'Segoe UI', 'Ubuntu', sans-serif;
    font-size: 12px;
}
QMenuBar {
    background-color: #21222b;
    color: #cfd8dc;
    border-bottom: 1px solid #37474f;
}
QMenuBar::item:selected {
    background-color: #2c3240;
    color: #4fc3f7;
}
QMenu {
    background-color: #21222b;
    color: #e0e0e0;
    border: 1px solid #37474f;
}
QMenu::item:selected {
    background-color: #2c3240;
    color: #4fc3f7;
}
QToolBar {
    background-color: #21222b;
    border-bottom: 1px solid #37474f;
    spacing: 6px;
    padding: 3px;
}
QToolButton {
    background-color: #282c37;
    color: #e0e0e0;
    border: 1px solid #37474f;
    border-radius: 3px;
    padding: 4px 8px;
}
QToolButton:hover {
    background-color: #37474f;
    border-color: #4fc3f7;
    color: #ffffff;
}
QToolButton:pressed {
    background-color: #1e2836;
}
QLineEdit {
    background-color: #282c37;
    color: #ffffff;
    border: 1px solid #37474f;
    border-radius: 3px;
    padding: 3px 6px;
    selection-background-color: #0288d1;
}
QLineEdit:focus {
    border: 1px solid #4fc3f7;
}
QComboBox {
    background-color: #282c37;
    color: #ffffff;
    border: 1px solid #37474f;
    border-radius: 3px;
    padding: 2px 6px;
}
QDockWidget {
    color: #cfd8dc;
    titlebar-close-icon: url(none);
    titlebar-normal-icon: url(none);
}
QDockWidget::title {
    background-color: #21222b;
    border-bottom: 1px solid #37474f;
    padding: 6px;
    font-weight: bold;
}
QTreeWidget, QListWidget {
    background-color: #1e2028;
    color: #e0e0e0;
    border: 1px solid #37474f;
}
QTreeWidget::item:selected, QListWidget::item:selected {
    background-color: #0277bd;
    color: #ffffff;
}
QTreeWidget::item:hover, QListWidget::item:hover {
    background-color: #2c3240;
}
QStatusBar {
    background-color: #21222b;
    color: #90a4ae;
    border-top: 1px solid #37474f;
}
"""


class SchematicWindow(QtWidgets.QMainWindow):
    """
    Top-level application window containing the canvas, menus, toolbars,
    hierarchy browser dock, search bar, and status indicators.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(parent)
        self.setWindowTitle(f"OpenVision - Universal VLSI Schematic Viewer v{__version__}")
        self.resize(1440, 900)
        self.setStyleSheet(DARK_STYLESHEET)

        self._netlist_file: Optional[Path] = None
        self._liberty_file: Optional[Path] = None
        self._placement_res: Optional[PlacementResult] = None
        self._routing_res: Optional[RoutingResult] = None
        self._full_module = None
        self._full_placement_res: Optional[PlacementResult] = None
        self._full_routing_res: Optional[RoutingResult] = None
        self._current_cone = None
        self._selected_node_name: Optional[str] = None
        self._is_hierarchy_expanded: bool = False

        # 1. Central Canvas Widget
        self.canvas = SchematicCanvas(self)
        self.setCentralWidget(self.canvas)

        # Connect canvas signals
        self.canvas.cursor_moved.connect(self._on_cursor_moved)
        self.canvas.net_selected.connect(self._on_net_selected)
        self.canvas.gate_selected.connect(self._on_gate_selected)
        self.canvas.module_expanded.connect(self.expand_hierarchy)

        # 2. UI Components
        self._create_actions()
        self._create_menus()
        self._create_toolbar()
        self._create_hierarchy_dock()
        self._create_status_bar()

    def load_design(
        self,
        netlist_path: Path,
        liberty_path: Optional[Path] = None,
        hfn_threshold: int = 20,
    ) -> None:
        """Loads a structural Verilog netlist, performs placement & routing, and displays it."""
        self._netlist_file = Path(netlist_path)
        self.status_left.setText(f"Loading netlist: {self._netlist_file.name}...")
        QtWidgets.QApplication.processEvents()

        lib = None
        if liberty_path and Path(liberty_path).is_file():
            self._liberty_file = Path(liberty_path)
            lib = parse_liberty_file(self._liberty_file)
        else:
            try:
                def_lib = find_default_liberty()
                self._liberty_file = Path(def_lib)
                lib = parse_liberty_file(self._liberty_file)
            except Exception:
                pass

        netlist = parse_netlist_file(self._netlist_file, liberty=lib)
        top_mod = netlist.top_module
        if not top_mod:
            raise ValueError(f"No module found in {netlist_path}")

        # Run Placement
        self.status_left.setText("Running Sugiyama layered placement...")
        QtWidgets.QApplication.processEvents()
        self._placement_res = run_placement(top_mod)

        # Run Routing
        self.status_left.setText("Running Manhattan orthogonal auto-router...")
        QtWidgets.QApplication.processEvents()
        self._routing_res = route_placement(self._placement_res, hfn_threshold=hfn_threshold)

        # Save full references for cone restoration
        self._full_module = top_mod
        self._full_placement_res = self._placement_res
        self._full_routing_res = self._routing_res

        # Populate Hierarchy Browser
        self._populate_hierarchy_tree(top_mod)

        # Update Window Title and Status
        self.setWindowTitle(f"OpenVision - [{top_mod.name}] ({len(top_mod.instances):,} gates) - {self._netlist_file.name}")
        self.show_module_box()

    def display_design(
        self,
        module,
        placement_res: PlacementResult,
        routing_res: RoutingResult,
        start_expanded: bool = False,
    ) -> None:
        """Displays pre-computed placement and routing results. Opens in module box by default."""
        self._placement_res = placement_res
        self._routing_res = routing_res
        self._full_module = module
        self._full_placement_res = placement_res
        self._full_routing_res = routing_res

        self._populate_hierarchy_tree(module)
        self.setWindowTitle(f"OpenVision - [{module.name}] ({len(module.instances):,} gates)")

        if start_expanded:
            self.expand_hierarchy()
        else:
            self.show_module_box()

    def show_module_box(self) -> None:
        """Displays the design as an architectural top-level module box with primary IO pins."""
        if not self._full_module:
            return

        self._is_hierarchy_expanded = False
        self.canvas.load_module_box(self._full_module, on_expand=self.expand_hierarchy)

        if hasattr(self, "btn_box_view"):
            self.btn_box_view.setVisible(False)
        if hasattr(self, "btn_expand_hierarchy"):
            self.btn_expand_hierarchy.setVisible(True)

        self.status_left.setText(
            f"Design: {self._full_module.name} | "
            f"Gates: {len(self._full_module.instances):,} | "
            f"Ports: {len(self._full_module.ports)} | "
            f"Top-Level Block View"
        )
        self.status_mid.setText("Double-click the module box to expand hierarchy")
        QtCore.QTimer.singleShot(100, self.canvas.fit_in_view)

    def expand_hierarchy(self, module=None) -> None:
        """Expands the module box into the full gate-level placed and routed schematic."""
        if not self._full_placement_res or not self._full_routing_res or not self._full_module:
            return

        self._is_hierarchy_expanded = True
        self.canvas.load_schematic(self._full_placement_res, self._full_routing_res)

        if hasattr(self, "btn_box_view"):
            self.btn_box_view.setVisible(True)
        if hasattr(self, "btn_expand_hierarchy"):
            self.btn_expand_hierarchy.setVisible(False)

        self.status_left.setText(
            f"Design: {self._full_module.name} | "
            f"Gates: {len(self._full_module.instances):,} | "
            f"Nets: {len(self._full_routing_res.net_routes):,} | "
            f"Columns: {self._full_placement_res.num_ranks}"
        )
        self.status_mid.setText("Expanded internal gate-level schematic (press Esc or click 'Module Box' to collapse)")
        QtCore.QTimer.singleShot(100, self.canvas.fit_in_view)

    def showEvent(self, event: QtGui.QShowEvent):
        super().showEvent(event)
        QtCore.QTimer.singleShot(100, self.canvas.fit_in_view)

    # -------------------------------------------------------------------------
    # UI Setup Helpers
    # -------------------------------------------------------------------------

    def _create_actions(self):
        """Creates standard QActions."""
        self.act_open = QAction("&Open Netlist...", self)
        self.act_open.setShortcut(QKeySequence.StandardKey.Open)
        self.act_open.triggered.connect(self._open_netlist_dialog)

        self.act_export_png = QAction("&Export Image (PNG)...", self)
        self.act_export_png.setShortcut(QKeySequence("Ctrl+E"))
        self.act_export_png.triggered.connect(self._export_image_dialog)

        self.act_exit = QAction("E&xit", self)
        self.act_exit.setShortcut(QKeySequence("Ctrl+Q"))
        self.act_exit.triggered.connect(self.close)

        self.act_fit_view = QAction("&Fit in View", self)
        self.act_fit_view.setShortcut(QKeySequence("F"))
        self.act_fit_view.triggered.connect(self.canvas.fit_in_view)

        self.act_zoom_in = QAction("Zoom &In", self)
        self.act_zoom_in.setShortcut(QKeySequence.StandardKey.ZoomIn)
        self.act_zoom_in.triggered.connect(self.canvas.zoom_in)

        self.act_zoom_out = QAction("Zoom &Out", self)
        self.act_zoom_out.setShortcut(QKeySequence.StandardKey.ZoomOut)
        self.act_zoom_out.triggered.connect(self.canvas.zoom_out)

        self.act_reset_zoom = QAction("&1:1 Actual Size", self)
        self.act_reset_zoom.setShortcut(QKeySequence("Ctrl+0"))
        self.act_reset_zoom.triggered.connect(self.canvas.reset_zoom)

    def _create_menus(self):
        """Creates application menu bar."""
        mb = self.menuBar()

        # File Menu
        menu_file = mb.addMenu("&File")
        menu_file.addAction(self.act_open)
        menu_file.addAction(self.act_export_png)
        menu_file.addSeparator()
        menu_file.addAction(self.act_exit)

        # View Menu
        menu_view = mb.addMenu("&View")
        menu_view.addAction(self.act_fit_view)
        menu_view.addAction(self.act_zoom_in)
        menu_view.addAction(self.act_zoom_out)
        menu_view.addAction(self.act_reset_zoom)

        # Help Menu
        menu_help = mb.addMenu("&Help")
        act_about = QAction("&About OpenVision", self)
        act_about.triggered.connect(self._show_about_dialog)
        menu_help.addAction(act_about)

    def _create_toolbar(self):
        """Creates top tool bar with quick navigation & search tools."""
        tb = self.addToolBar("Main Navigation")
        tb.setIconSize(QSize(18, 18))
        tb.setMovable(False)

        tb.addAction(self.act_open)
        tb.addSeparator()
        tb.addAction(self.act_fit_view)
        tb.addAction(self.act_zoom_in)
        tb.addAction(self.act_zoom_out)
        tb.addSeparator()

        # Search Widget
        lbl_search = QtWidgets.QLabel(" Search: ")
        lbl_search.setStyleSheet("color: #cfd8dc; font-weight: bold;")
        tb.addWidget(lbl_search)

        self.combo_search_type = QtWidgets.QComboBox()
        self.combo_search_type.addItems(["Gate / Port", "Net"])
        tb.addWidget(self.combo_search_type)

        self.edit_search = QtWidgets.QLineEdit()
        self.edit_search.setPlaceholderText("Enter instance or net name...")
        self.edit_search.setFixedWidth(200)
        self.edit_search.returnPressed.connect(self._perform_search)
        tb.addWidget(self.edit_search)

        btn_find = QtWidgets.QPushButton("Find")
        btn_find.setStyleSheet("background-color: #0277bd; color: white; padding: 3px 10px; border-radius: 3px;")
        btn_find.clicked.connect(self._perform_search)
        tb.addWidget(btn_find)

        btn_clear = QtWidgets.QPushButton("Clear")
        btn_clear.setStyleSheet("background-color: #37474f; color: white; padding: 3px 8px; border-radius: 3px;")
        btn_clear.clicked.connect(self._clear_search)
        tb.addWidget(btn_clear)

        # Cone Tracing Toolbar Section
        tb.addSeparator()
        lbl_cone = QtWidgets.QLabel(" Cone: ")
        lbl_cone.setStyleSheet("color: #cfd8dc; font-weight: bold;")
        tb.addWidget(lbl_cone)

        self.spin_cone_depth = QtWidgets.QSpinBox()
        self.spin_cone_depth.setRange(0, 50)
        self.spin_cone_depth.setValue(1)
        self.spin_cone_depth.setSpecialValueText("Full")
        self.spin_cone_depth.setToolTip("Cone logic depth (0 for full cone to register boundary)")
        tb.addWidget(self.spin_cone_depth)

        btn_fanin = QtWidgets.QPushButton("Fanin")
        btn_fanin.setStyleSheet("background-color: #00838f; color: white; padding: 3px 8px; border-radius: 3px;")
        btn_fanin.setToolTip("Trace Fanin cone driving the currently selected gate")
        btn_fanin.clicked.connect(self._on_toolbar_fanin)
        tb.addWidget(btn_fanin)

        btn_fanout = QtWidgets.QPushButton("Fanout")
        btn_fanout.setStyleSheet("background-color: #00838f; color: white; padding: 3px 8px; border-radius: 3px;")
        btn_fanout.setToolTip("Trace Fanout cone driven by the currently selected gate")
        btn_fanout.clicked.connect(self._on_toolbar_fanout)
        tb.addWidget(btn_fanout)

        btn_isolate = QtWidgets.QPushButton("Isolate")
        btn_isolate.setStyleSheet("background-color: #4527a0; color: white; padding: 3px 8px; border-radius: 3px;")
        btn_isolate.setToolTip("Place and route strictly the extracted logic cone into an isolated sub-schematic")
        btn_isolate.clicked.connect(self.isolate_current_cone)
        tb.addWidget(btn_isolate)

        self.btn_full_design = QtWidgets.QPushButton("Full Design")
        self.btn_full_design.setStyleSheet("background-color: #2e7d32; color: white; padding: 3px 8px; border-radius: 3px;")
        self.btn_full_design.setToolTip("Return to the full top-level design schematic")
        self.btn_full_design.clicked.connect(self.restore_full_design)
        self.btn_full_design.setVisible(False)
        tb.addWidget(self.btn_full_design)

        # Hierarchy View Navigation
        tb.addSeparator()
        self.btn_expand_hierarchy = QtWidgets.QPushButton("Expand Hierarchy")
        self.btn_expand_hierarchy.setStyleSheet("background-color: #0284c7; color: white; padding: 3px 8px; border-radius: 3px; font-weight: bold;")
        self.btn_expand_hierarchy.setToolTip("Expand the module box into internal gate-level schematic (or double-click the box)")
        self.btn_expand_hierarchy.clicked.connect(self.expand_hierarchy)
        tb.addWidget(self.btn_expand_hierarchy)

        self.btn_box_view = QtWidgets.QPushButton("Module Box")
        self.btn_box_view.setStyleSheet("background-color: #334155; color: white; padding: 3px 8px; border-radius: 3px;")
        self.btn_box_view.setToolTip("Return to the top-level module block view (or press Esc)")
        self.btn_box_view.clicked.connect(self.show_module_box)
        self.btn_box_view.setVisible(False)
        tb.addWidget(self.btn_box_view)

        tb.addSeparator()
        tb.addAction(self.act_export_png)

    def _create_hierarchy_dock(self):
        """Creates left sidebar dock widget with design hierarchy tree."""
        self.dock_tree = QtWidgets.QDockWidget("Design Hierarchy", self)
        self.dock_tree.setAllowedAreas(Qt.DockWidgetArea.LeftDockWidgetArea | Qt.DockWidgetArea.RightDockWidgetArea)

        container = QtWidgets.QWidget()
        layout = QtWidgets.QVBoxLayout(container)
        layout.setContentsMargins(4, 4, 4, 4)

        # Filter box
        self.tree_filter = QtWidgets.QLineEdit()
        self.tree_filter.setPlaceholderText("Filter instances...")
        self.tree_filter.textChanged.connect(self._filter_tree)
        layout.addWidget(self.tree_filter)

        # Tree widget
        self.tree_widget = QtWidgets.QTreeWidget()
        self.tree_widget.setHeaderLabels(["Element", "Type / Bits"])
        self.tree_widget.itemClicked.connect(self._on_tree_item_clicked)
        self.tree_widget.itemDoubleClicked.connect(self._on_tree_item_double_clicked)
        layout.addWidget(self.tree_widget)

        self.dock_tree.setWidget(container)
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.dock_tree)

    def _create_status_bar(self):
        """Creates bottom status bar."""
        sb = self.statusBar()

        self.status_left = QtWidgets.QLabel("Ready")
        self.status_mid = QtWidgets.QLabel("No selection")
        self.status_coords = QtWidgets.QLabel("X: 0.0, Y: 0.0")

        self.status_left.setStyleSheet("padding-left: 8px; font-weight: bold;")
        self.status_mid.setStyleSheet("color: #ffeb3b; padding-left: 15px;")
        self.status_coords.setStyleSheet("padding-right: 15px; font-family: monospace;")

        sb.addWidget(self.status_left, 1)
        sb.addWidget(self.status_mid, 1)
        sb.addPermanentWidget(self.status_coords)

    def _populate_hierarchy_tree(self, module):
        """Populates the hierarchy tree with ports, sequential, and combinational gates."""
        self.tree_widget.clear()

        # Primary Ports
        item_ports = QtWidgets.QTreeWidgetItem(self.tree_widget, ["Primary Ports", f"{len(module.ports)} ports"])
        for p in module.ports.values():
            QtWidgets.QTreeWidgetItem(item_ports, [p.name, f"{p.direction} [{p.width}b]"])

        # Sequential Registers
        dffs = [inst for inst in module.instances.values() if "DFF" in getattr(inst, "gate_type", "").name]
        item_dff = QtWidgets.QTreeWidgetItem(self.tree_widget, ["Registers (DFF)", f"{len(dffs)} gates"])
        for inst in dffs[:500]:  # Cap initial tree view for fast UI response
            QtWidgets.QTreeWidgetItem(item_dff, [inst.name, inst.cell_type])
        if len(dffs) > 500:
            QtWidgets.QTreeWidgetItem(item_dff, [f"... ({len(dffs) - 500} more registers)", ""])

        # Combinational Gates
        comb = [inst for inst in module.instances.values() if "DFF" not in getattr(inst, "gate_type", "").name]
        item_comb = QtWidgets.QTreeWidgetItem(self.tree_widget, ["Combinational Logic", f"{len(comb)} gates"])
        for inst in comb[:500]:
            gt = getattr(inst, "gate_type", None)
            gt_str = gt.value if gt else "GATE"
            QtWidgets.QTreeWidgetItem(item_comb, [inst.name, f"{gt_str} ({inst.cell_type})"])
        if len(comb) > 500:
            QtWidgets.QTreeWidgetItem(item_comb, [f"... ({len(comb) - 500} more gates)", ""])

        item_ports.setExpanded(True)
        item_dff.setExpanded(False)
        item_comb.setExpanded(False)

    # -------------------------------------------------------------------------
    # Event Handlers & Callbacks
    # -------------------------------------------------------------------------

    def _on_cursor_moved(self, x: float, y: float):
        self.status_coords.setText(f"X: {x:8.1f}, Y: {y:8.1f}")

    def _on_net_selected(self, net_name: str):
        fo = self._routing_res.net_routes[net_name].fanout if self._routing_res and net_name in self._routing_res.net_routes else 0
        self.status_mid.setText(f"Selected Net: [bold]{net_name}[/bold] (fanout={fo})")

    def _on_gate_selected(self, gate_name: str):
        self._selected_node_name = gate_name
        self.status_mid.setText(f"Selected Gate: [bold]{gate_name}[/bold]")

    def _on_toolbar_fanin(self):
        target = self._selected_node_name or self.edit_search.text().strip()
        if not target:
            self.status_mid.setText("Select a gate on the canvas or type its name in Search to trace Fanin")
            return
        depth = self.spin_cone_depth.value()
        self.trace_node_fanin(target, depth=None if depth == 0 else depth)

    def _on_toolbar_fanout(self):
        target = self._selected_node_name or self.edit_search.text().strip()
        if not target:
            self.status_mid.setText("Select a gate on the canvas or type its name in Search to trace Fanout")
            return
        depth = self.spin_cone_depth.value()
        self.trace_node_fanout(target, depth=None if depth == 0 else depth)

    def trace_node_fanin(self, node_name: str, depth: Optional[int] = None):
        """Extracts and highlights the fanin logic cone for a gate/port."""
        if not self._full_module:
            return
        from openvision.cone import ConeTracer
        tracer = ConeTracer(self._full_module)
        cone = tracer.trace_fanin(node_name, depth=depth)
        self._current_cone = cone
        self.canvas.highlight_cone(cone)
        depth_str = f"depth={cone.max_depth_reached}"
        self.status_mid.setText(f"Fanin Cone: {node_name} ({len(cone.instances)} gates, {len(cone.boundary_endpoints)} boundaries, {depth_str})")

    def trace_node_fanout(self, node_name: str, depth: Optional[int] = None):
        """Extracts and highlights the fanout logic cone for a gate/port."""
        if not self._full_module:
            return
        from openvision.cone import ConeTracer
        tracer = ConeTracer(self._full_module)
        cone = tracer.trace_fanout(node_name, depth=depth)
        self._current_cone = cone
        self.canvas.highlight_cone(cone)
        depth_str = f"depth={cone.max_depth_reached}"
        self.status_mid.setText(f"Fanout Cone: {node_name} ({len(cone.instances)} gates, {len(cone.boundary_endpoints)} boundaries, {depth_str})")

    def isolate_current_cone(self):
        """Places, routes, and displays strictly the extracted logic cone."""
        if not self._current_cone or not self._full_module:
            self.status_mid.setText("No active logic cone to isolate! Trace a fanin/fanout cone first.")
            return

        submod = self._current_cone.extract_submodule(self._full_module)
        cone_placement = run_placement(submod)
        cone_routing = route_placement(cone_placement)

        self.canvas.load_schematic(cone_placement, cone_routing)
        self._populate_hierarchy_tree(submod)
        self.btn_full_design.setVisible(True)
        self.status_left.setText(f"Isolated Cone: {self._current_cone.root_name} | {len(submod.instances)} gates | {len(cone_routing.net_routes)} nets")
        self.status_mid.setText(f"Displaying isolated sub-schematic ({cone_placement.num_ranks} columns)")
        QtCore.QTimer.singleShot(100, self.canvas.fit_in_view)

    def restore_full_design(self):
        """Restores the full top-level design view."""
        if self._full_placement_res and self._full_routing_res and self._full_module:
            self.canvas.load_schematic(self._full_placement_res, self._full_routing_res)
            self._populate_hierarchy_tree(self._full_module)
            self.btn_full_design.setVisible(False)
            self.status_left.setText(
                f"Design: {self._full_module.name} | "
                f"Gates: {len(self._full_module.instances):,} | "
                f"Nets: {len(self._full_routing_res.net_routes):,} | "
                f"Columns: {self._full_placement_res.num_ranks}"
            )
            self.status_mid.setText("Restored full design view")
            QtCore.QTimer.singleShot(100, self.canvas.fit_in_view)

    def keyPressEvent(self, event: QtGui.QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            if getattr(self, "_is_hierarchy_expanded", False):
                self.show_module_box()
                event.accept()
                return
        super().keyPressEvent(event)

    def _on_tree_item_double_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int) -> None:
        if item == self.tree_widget.topLevelItem(0):
            if self._is_hierarchy_expanded:
                self.show_module_box()
            else:
                self.expand_hierarchy()

    def _on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        name = item.text(0)
        if name and not name.startswith("..."):
            if item == self.tree_widget.topLevelItem(0):
                if not self._is_hierarchy_expanded:
                    self.show_module_box()
                return
            if not self._is_hierarchy_expanded:
                self.expand_hierarchy()
            found = self.canvas.find_and_center_node(name)
            if not found:
                self.canvas.find_and_center_net(name)

    def _perform_search(self):
        query = self.edit_search.text().strip()
        if not query:
            return

        if not self._is_hierarchy_expanded:
            self.expand_hierarchy()

        search_type = self.combo_search_type.currentText()
        if search_type == "Gate / Port":
            success = self.canvas.find_and_center_node(query)
            if success:
                self.status_mid.setText(f"Found gate '{query}'")
            else:
                self.status_mid.setText(f"Gate '{query}' not found")
        else:
            success = self.canvas.find_and_center_net(query)
            if success:
                self.status_mid.setText(f"Found and highlighted net '{query}'")
            else:
                self.status_mid.setText(f"Net '{query}' not found")

    def _clear_search(self):
        self.edit_search.clear()
        self.canvas.highlight_net(None)
        self.canvas._scene.clearSelection()
        self.status_mid.setText("Selection cleared")

    def _filter_tree(self, text: str):
        text = text.lower()
        root = self.tree_widget.invisibleRootItem()
        for i in range(root.childCount()):
            group = root.child(i)
            has_match = False
            for j in range(group.childCount()):
                child = group.child(j)
                match = text in child.text(0).lower() or text in child.text(1).lower()
                child.setHidden(not match and text != "")
                if match:
                    has_match = True
            group.setHidden(not has_match and text != "")

    def _open_netlist_dialog(self):
        file_path, _ = QtWidgets.QFileDialog.getOpenFileName(
            self,
            "Open Structural Verilog Netlist",
            str(Path.cwd()),
            "Verilog Files (*.v *.sv);;All Files (*)",
        )
        if file_path:
            self.load_design(Path(file_path))

    def _export_image_dialog(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            self,
            "Export Schematic Image",
            "schematic.png",
            "PNG Images (*.png);;All Files (*)",
        )
        if file_path:
            out_file = export_scene_to_image(self.canvas._scene, file_path)
            self.status_mid.setText(f"Exported schematic to: {out_file}")

    def _show_about_dialog(self):
        QtWidgets.QMessageBox.information(
            self,
            "About OpenVision",
            f"<h3>OpenVision v{__version__}</h3>"
            "<p>Universal Schematic Viewer for Technology-Mapped Netlists.</p>"
            "<p>Features:"
            "<ul>"
            "<li>Direct structural Verilog & Liberty ingestion</li>"
            "<li>Dynamic truth-table IEEE symbol classification</li>"
            "<li>Sugiyama layered DAG placement</li>"
            "<li>Manhattan orthogonal auto-routing with solder dots</li>"
            "<li>Hardware-accelerated interactive 2D canvas</li>"
            "</ul></p>",
        )
