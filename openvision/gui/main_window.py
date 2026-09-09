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

        # 1. Central Canvas Widget
        self.canvas = SchematicCanvas(self)
        self.setCentralWidget(self.canvas)

        # Connect canvas signals
        self.canvas.cursor_moved.connect(self._on_cursor_moved)
        self.canvas.net_selected.connect(self._on_net_selected)
        self.canvas.gate_selected.connect(self._on_gate_selected)

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

        # Populate Canvas
        self.status_left.setText("Populating canvas graphics items...")
        QtWidgets.QApplication.processEvents()
        self.canvas.load_schematic(self._placement_res, self._routing_res)

        # Populate Hierarchy Browser
        self._populate_hierarchy_tree(top_mod)

        # Update Window Title and Status
        self.setWindowTitle(f"OpenVision - [{top_mod.name}] ({len(top_mod.instances):,} gates) - {self._netlist_file.name}")
        self.status_left.setText(
            f"Design: {top_mod.name} | "
            f"Gates: {len(top_mod.instances):,} | "
            f"Nets: {len(self._routing_res.net_routes):,} | "
            f"Columns: {self._placement_res.num_ranks}"
        )
        QtCore.QTimer.singleShot(100, self.canvas.fit_in_view)

    def display_design(
        self,
        module,
        placement_res: PlacementResult,
        routing_res: RoutingResult,
    ) -> None:
        """Displays pre-computed placement and routing results without re-computing."""
        self._placement_res = placement_res
        self._routing_res = routing_res
        self.canvas.load_schematic(placement_res, routing_res)
        self._populate_hierarchy_tree(module)
        self.setWindowTitle(f"OpenVision - [{module.name}] ({len(module.instances):,} gates)")
        self.status_left.setText(
            f"Design: {module.name} | "
            f"Gates: {len(module.instances):,} | "
            f"Nets: {len(routing_res.net_routes):,} | "
            f"Columns: {placement_res.num_ranks}"
        )
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
        self.status_mid.setText(f"Selected Gate: [bold]{gate_name}[/bold]")

    def _on_tree_item_clicked(self, item: QtWidgets.QTreeWidgetItem, column: int):
        name = item.text(0)
        if name and not name.startswith("..."):
            found = self.canvas.find_and_center_node(name)
            if not found:
                self.canvas.find_and_center_net(name)

    def _perform_search(self):
        query = self.edit_search.text().strip()
        if not query:
            return

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
