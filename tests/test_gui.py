"""
Unit and integration tests for Milestone 4: Interactive PyQt6 GUI Canvas.
Tests canvas creation, gate/wire graphics items, net highlighting,
search navigation, image export, and main window lifecycle in offscreen mode.
"""

import os
import pytest
from pathlib import Path

# Ensure offscreen Qt platform for headless test execution
os.environ["QT_QPA_PLATFORM"] = "offscreen"

from PyQt6 import QtWidgets, QtCore, QtGui
from openvision.ingestion.liberty_parser import parse_liberty_text, parse_liberty_file, find_default_liberty
from openvision.ingestion.netlist_parser import parse_netlist_text, parse_netlist_file
from openvision.placement import run_placement
from openvision.routing import route_placement
from openvision.gui import (
    SchematicCanvas,
    SchematicWindow,
    GateGraphicsItem,
    WireGraphicsItem,
    SolderDotGraphicsItem,
    HFNStubGraphicsItem,
    export_scene_to_image,
)


@pytest.fixture(scope="session")
def qapp():
    """Initializes a shared offscreen QApplication for tests."""
    app = QtWidgets.QApplication.instance()
    if app is None:
        app = QtWidgets.QApplication([])
    return app


@pytest.fixture
def small_design():
    """Creates a small placed and routed design fixture."""
    verilog = """
    module simple_demo (clk, rst, in1, in2, out1, out2);
        input clk, rst, in1, in2;
        output out1, out2;
        wire n1, n2;
        sky130_fd_sc_hd__nand2_1 g1 (.A(in1), .B(in2), .Y(n1));
        sky130_fd_sc_hd__dfxtp_1 ff1 (.CLK(clk), .D(n1), .Q(out1));
        sky130_fd_sc_hd__clkinv_1 inv1 (.A(n1), .Y(out2));
    endmodule
    """
    netlist = parse_netlist_text(verilog)
    placement = run_placement(netlist.top_module)
    routing = route_placement(placement, hfn_threshold=10)
    return placement, routing


def test_canvas_creation_and_loading(qapp, small_design):
    """Verifies that SchematicCanvas populates all items correctly."""
    placement, routing = small_design
    canvas = SchematicCanvas()
    canvas.load_schematic(placement, routing)

    # Verify gates
    assert len(canvas._gate_items) == len(placement.graph.nodes)
    for node_id in placement.graph.nodes:
        assert node_id in canvas._gate_items
        item = canvas._gate_items[node_id]
        assert isinstance(item, GateGraphicsItem)

    # Verify scene items
    assert len(canvas._scene.items()) > 0
    assert not canvas._scene.sceneRect().isEmpty()


def test_net_highlighting_interaction(qapp, small_design):
    """Verifies selecting a net highlights all its wire segments and solder dots."""
    placement, routing = small_design
    canvas = SchematicCanvas()
    canvas.load_schematic(placement, routing)

    # Find a net with wire segments
    target_net = None
    for net_name, wires in canvas._net_wire_items.items():
        if len(wires) > 0:
            target_net = net_name
            break

    assert target_net is not None, "No wired net found"

    # Select net
    canvas.highlight_net(target_net)
    for w in canvas._net_wire_items[target_net]:
        assert w._is_highlighted, f"Wire in net {target_net} was not highlighted"

    # Deselect net
    canvas.highlight_net(None)
    for w in canvas._net_wire_items[target_net]:
        assert not w._is_highlighted, "Wire was not un-highlighted"


def test_search_and_center_navigation(qapp, small_design):
    """Verifies search navigation can locate gates and nets."""
    placement, routing = small_design
    canvas = SchematicCanvas()
    canvas.load_schematic(placement, routing)

    # Search for gate
    found_gate = canvas.find_and_center_node("g1")
    assert found_gate, "Failed to find gate 'g1'"

    # Search for port
    found_port = canvas.find_and_center_node("in1")
    assert found_port, "Failed to find port 'in1'"

    # Search for non-existent node
    not_found = canvas.find_and_center_node("non_existent_gate_xyz")
    assert not not_found


def test_export_scene_to_image(qapp, small_design, tmp_path):
    """Verifies exporting the schematic to a PNG image file."""
    placement, routing = small_design
    canvas = SchematicCanvas()
    canvas.load_schematic(placement, routing)

    out_png = tmp_path / "test_schematic.png"
    result_path = export_scene_to_image(canvas._scene, str(out_png), max_dimension=1024)

    assert Path(result_path).is_file()
    assert Path(result_path).stat().st_size > 0


def test_main_window_lifecycle(qapp, small_design, tmp_path):
    """Verifies SchematicWindow initialization, toolbar, dock, and design loading."""
    placement, routing = small_design
    win = SchematicWindow()
    assert win.canvas is not None
    assert win.tree_widget is not None

    # Load design into window
    win.canvas.load_schematic(placement, routing)
    win.canvas.fit_in_view()
    assert not win.canvas._scene.sceneRect().isEmpty()


def test_module_box_rendering_and_expansion(qapp, small_design):
    """Verifies that the module box displays by default and expands on demand."""
    placement, routing = small_design

    verilog = """
    module simple_demo (clk, rst, in1, in2, out1, out2);
        input clk, rst, in1, in2;
        output out1, out2;
        wire n1, n2;
        sky130_fd_sc_hd__nand2_1 g1 (.A(in1), .B(in2), .Y(n1));
        sky130_fd_sc_hd__dfxtp_1 ff1 (.CLK(clk), .D(n1), .Q(out1));
        sky130_fd_sc_hd__clkinv_1 inv1 (.A(n1), .Y(out2));
    endmodule
    """
    mod = parse_netlist_text(verilog).top_module

    win = SchematicWindow()
    win.display_design(mod, placement, routing, start_expanded=False)

    # Initial state must be the top module box view
    assert not win._is_hierarchy_expanded
    assert win.canvas.is_box_view
    assert win.canvas._module_box_item is not None
    assert len(win.canvas._gate_items) == 0

    # Expand hierarchy to show gates
    win.expand_hierarchy()
    assert win._is_hierarchy_expanded
    assert not win.canvas.is_box_view
    assert len(win.canvas._gate_items) == len(placement.graph.nodes)

    # Collapse back to box view
    win.show_module_box()
    assert not win._is_hierarchy_expanded
    assert win.canvas.is_box_view
    assert win.canvas._module_box_item is not None
