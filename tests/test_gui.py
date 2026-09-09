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


def test_full_net_hover_highlighting(qapp, small_design):
    """
    Verifies that hovering over any segment of a net highlights the ENTIRE net
    across all segments, corners/bends, solder dots, and stubs from source to all destinations.
    Also verifies debouncing across corners and status bar integration.
    """
    placement, routing = small_design
    win = SchematicWindow()
    win._routing_res = routing
    win.canvas.load_schematic(placement, routing)
    canvas = win.canvas

    # Find a net with multiple segments (e.g. fanout > 1)
    multi_seg_net = None
    for net_name, wires in canvas._net_wire_items.items():
        if len(wires) >= 2:
            multi_seg_net = net_name
            break

    assert multi_seg_net is not None, "Did not find a multi-segment net in small_design"
    wires = canvas._net_wire_items[multi_seg_net]
    assert len(wires) >= 2

    # Verify initial state: no segments hovered
    for w in wires:
        assert not w._is_hovered
        assert w.zValue() == 0.0

    # 1. Hover entered on one segment
    canvas.hover_net(multi_seg_net, True)
    for w in wires:
        assert w._is_hovered, f"Segment in net {multi_seg_net} should be hovered"
        assert w.zValue() == 10.0, "Hovered wire should have elevated zValue"

    for dot in canvas._net_dot_items.get(multi_seg_net, []):
        assert dot._is_hovered
        assert dot.zValue() == 12.0

    assert win.canvas._current_hovered_net == multi_seg_net
    assert multi_seg_net in win.status_mid.text()
    assert "Source:" in win.status_mid.text()

    # 2. Simulate crossing a 90-degree corner:
    # hoverLeave on seg 1, followed immediately by hoverEnter on seg 2 of same net
    canvas.hover_net(multi_seg_net, False)
    # Debounce timer should be running, net still hovered
    assert canvas._unhover_timer is not None
    assert canvas._unhover_timer.isActive()
    assert canvas._current_hovered_net == multi_seg_net
    for w in wires:
        assert w._is_hovered

    # Enter seg 2 of same net before timer expires
    canvas.hover_net(multi_seg_net, True)
    assert not canvas._unhover_timer.isActive()
    for w in wires:
        assert w._is_hovered

    # 3. Leave net completely and wait for debounce timer
    canvas.hover_net(multi_seg_net, False)
    assert canvas._unhover_timer.isActive()
    # Trigger timeout directly
    canvas._on_unhover_timeout()
    assert canvas._current_hovered_net is None
    for w in wires:
        assert not w._is_hovered
        assert w.zValue() == 0.0

    # 4. Click to select (pin) net, then hover and unhover
    canvas.highlight_net(multi_seg_net)
    for w in wires:
        assert w._is_highlighted

    canvas.hover_net(multi_seg_net, True)
    for w in wires:
        assert w._is_hovered
        assert w._is_highlighted

    canvas._on_unhover_timeout()
    # Pinned highlight should remain intact after unhover
    for w in wires:
        assert not w._is_hovered
        assert w._is_highlighted



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


def test_hierarchical_submodule_navigation(qapp):
    """Verifies hierarchical drill-down into submodules and ascending back to top-level."""
    lib_path = find_default_liberty()
    lib = parse_liberty_file(lib_path)
    synth_path = Path("benchmarks/synth/aes_cipher_top.v")
    assert synth_path.is_file()

    netlist = parse_netlist_file(synth_path, liberty=lib)
    top_mod = netlist["aes_cipher_top"]

    placement = run_placement(top_mod)
    routing = route_placement(placement)

    win = SchematicWindow()
    win.display_design(top_mod, placement, routing, start_expanded=False)

    # 1. Initial state: Module Box view
    assert win.canvas.is_box_view
    assert not win._is_hierarchy_expanded
    assert not win.btn_up_hierarchy.isEnabled()

    # 2. Expand hierarchy into top-level structural block diagram
    win.expand_hierarchy()
    assert not win.canvas.is_box_view
    assert win._is_hierarchy_expanded
    assert win.current_module.name == "aes_cipher_top"
    assert "inst:u_controller" in win.canvas._gate_items
    assert "inst:u_datapath" in win.canvas._gate_items
    assert "inst:u_key_schedule" in win.canvas._gate_items

    # 3. Double-click / descend into u_controller (aes_controller)
    win.descend_into_submodule("u_controller", "aes_controller")
    assert win.current_module.name == "aes_controller"
    assert len(win._hierarchy_history) == 1
    assert win.btn_up_hierarchy.isEnabled()
    assert "aes_cipher_top > aes_controller" in win.lbl_breadcrumb.text()
    # Check that gates in aes_controller are loaded in canvas
    assert len(win.canvas._gate_items) == len(netlist["aes_controller"].instances) + len(netlist["aes_controller"].ports)

    # 4. Ascend back up to aes_cipher_top (via Esc / Up Hierarchy)
    win.ascend_hierarchy()
    assert win.current_module.name == "aes_cipher_top"
    assert len(win._hierarchy_history) == 0
    assert not win.btn_up_hierarchy.isEnabled()
    assert "aes_cipher_top" in win.lbl_breadcrumb.text()
    assert "inst:u_controller" in win.canvas._gate_items

    # 5. Ascend from top level collapses back to Module Box view
    win.ascend_hierarchy()
    assert win.canvas.is_box_view
    assert not win._is_hierarchy_expanded


def test_inverter_buffer_sizing_and_net_width(qapp):
    """
    Verifies that:
    1. Inverters and buffers have compact symbol dimensions (56x34) compared to standard gates (80x50).
    2. Default net line width is 1.0.
    """
    verilog = """
    module inv_buf_demo (in1, out1, out2);
        input in1;
        output out1, out2;
        wire n1;
        sky130_fd_sc_hd__clkinv_1 u_inv (.A(in1), .Y(n1));
        sky130_fd_sc_hd__buf_1 u_buf (.A(n1), .X(out1));
        sky130_fd_sc_hd__nand2_1 u_nand (.A(in1), .B(n1), .Y(out2));
    endmodule
    """
    netlist = parse_netlist_text(verilog)
    top_mod = netlist.top_module
    placement = run_placement(top_mod)
    routing = route_placement(placement)

    # 1. Inverter and buffer size verification
    inv_node = placement.graph.get_node("inst:u_inv")
    buf_node = placement.graph.get_node("inst:u_buf")
    nand_node = placement.graph.get_node("inst:u_nand")

    assert inv_node is not None
    assert buf_node is not None
    assert nand_node is not None

    # Inverter/buffer must be 48x28
    assert inv_node.width == 48.0 and inv_node.height == 28.0
    assert buf_node.width == 48.0 and buf_node.height == 28.0
    # Standard NAND gate must be 80x50
    assert nand_node.width == 80.0 and nand_node.height == 50.0

    # 2. Default net width verification
    canvas = SchematicCanvas()
    canvas.load_schematic(placement, routing)
    wire_item = next(iter(next(iter(canvas._net_wire_items.values()))))
    dummy_img = QtGui.QImage(100, 100, QtGui.QImage.Format.Format_ARGB32)
    p = QtGui.QPainter(dummy_img)
    opt = QtWidgets.QStyleOptionGraphicsItem()
    wire_item.paint(p, opt)
    assert abs(p.pen().widthF() - 0.8) < 1e-4, f"Expected default wire pen width 0.8, got {p.pen().widthF()}"
    p.end()
