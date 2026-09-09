"""
Unit and integration tests for Milestone 5: Incremental Logic Cone Tracing & CLI.
Tests backward fanin, forward fanout, depth limits, sequential register boundary stopping,
shortest logic path traversal, and isolated sub-module schematic extraction.
"""

import pytest
from pathlib import Path

from openvision.ingestion.liberty_parser import parse_liberty_file, find_default_liberty
from openvision.ingestion.netlist_parser import parse_netlist_text, parse_netlist_file
from openvision.cone import ConeTracer, LogicCone
from openvision.placement import run_placement
from openvision.routing import route_placement


@pytest.fixture
def sequential_netlist():
    """
    Fixture with a sequential pipeline:
    in_a, in_b -> g1 (nand) -> ff1 (dff) -> g2 (xor) -> g3 (inv) -> ff2 (dff) -> g4 (buf) -> out_z
    """
    verilog = """
    module seq_pipe (clk, rst, in_a, in_b, out_z);
        input clk, rst, in_a, in_b;
        output out_z;
        wire n_g1, q_ff1, n_xor, n_inv, q_ff2;

        sky130_fd_sc_hd__nand2_1 g1 (.A(in_a), .B(in_b), .Y(n_g1));
        sky130_fd_sc_hd__dfxtp_1 ff1 (.CLK(clk), .D(n_g1), .Q(q_ff1));
        sky130_fd_sc_hd__xor2_1  g2 (.A(q_ff1), .B(in_b), .Y(n_xor));
        sky130_fd_sc_hd__clkinv_1 g3 (.A(n_xor), .Y(n_inv));
        sky130_fd_sc_hd__dfxtp_1 ff2 (.CLK(clk), .D(n_inv), .Q(q_ff2));
        sky130_fd_sc_hd__buf_1   g4 (.A(q_ff2), .X(out_z));
    endmodule
    """
    return parse_netlist_text(verilog).top_module


def test_fanin_unbounded_stops_at_dff(sequential_netlist):
    """Verifies that backward fanin tracing stops cleanly at DFF boundaries."""
    tracer = ConeTracer(sequential_netlist)

    # Trace backward from g3 (inverter)
    cone = tracer.trace_fanin("g3", stop_at_dff=True)

    assert cone.direction == "FANIN"
    assert "g3" in cone.instances
    assert "g2" in cone.instances
    # ff1 drives g2, so ff1 should be a boundary endpoint and not traversed through
    assert any("ff1" in ep for ep in cone.boundary_endpoints)
    # g1 is before ff1, so g1 should NOT be in the cone when stopping at DFF
    assert "g1" not in cone.instances
    # in_b directly feeds g2, so in_b is also a boundary endpoint
    assert any("in_b" in ep for ep in cone.boundary_endpoints)


def test_fanin_depth_limit(sequential_netlist):
    """Verifies depth-limited fanin expansion."""
    tracer = ConeTracer(sequential_netlist)

    # Depth 1 from g3 should only inspect g3's direct driver (g2)
    cone_d1 = tracer.trace_fanin("g3", depth=1)
    assert "g3" in cone_d1.instances
    assert "g2" in cone_d1.instances
    assert cone_d1.max_depth_reached <= 1


def test_fanout_unbounded_stops_at_dff(sequential_netlist):
    """Verifies that forward fanout tracing stops at DFF input boundaries."""
    tracer = ConeTracer(sequential_netlist)

    # Trace forward from g2 (xor)
    cone = tracer.trace_fanout("g2", stop_at_dff=True)

    assert cone.direction == "FANOUT"
    assert "g2" in cone.instances
    assert "g3" in cone.instances
    # ff2 receives output of g3, so ff2 should be a boundary endpoint
    assert any("ff2" in ep for ep in cone.boundary_endpoints)
    # g4 is after ff2, so g4 should NOT be in the fanout cone
    assert "g4" not in cone.instances


def test_fanout_from_primary_input(sequential_netlist):
    """Verifies fanout cone initiated from primary input port."""
    tracer = ConeTracer(sequential_netlist)

    # Trace forward from port 'in_a'
    cone = tracer.trace_fanout("in_a")
    assert "g1" in cone.instances
    # g1 drives ff1, so ff1 is a boundary
    assert any("ff1" in ep for ep in cone.boundary_endpoints)


def test_extract_submodule_and_layout(sequential_netlist):
    """Verifies that an extracted logic cone submodule can be placed and routed cleanly."""
    tracer = ConeTracer(sequential_netlist)
    cone = tracer.trace_fanin("g3", depth=None, stop_at_dff=True)

    submod = cone.extract_submodule(sequential_netlist, submodule_name="test_cone")
    assert submod.name == "test_cone"
    assert "g3" in submod.instances
    assert "g2" in submod.instances
    assert len(submod.ports) > 0

    # Place and route the isolated cone submodule
    placement = run_placement(submod)
    assert placement.num_ranks >= 1
    assert placement.total_nodes >= len(submod.instances)

    routing = route_placement(placement)
    assert routing.total_segments > 0
    assert routing.is_strictly_orthogonal is True


def test_trace_shortest_path(sequential_netlist):
    """Verifies finding the shortest directed logic path between two gates."""
    tracer = ConeTracer(sequential_netlist)

    # Path from g2 to g3
    path = tracer.trace_logic_path("g2", "g3")
    assert path == ["g2", "g3"]

    # Path from g1 to ff1
    path_dff = tracer.trace_logic_path("g1", "ff1")
    assert path_dff == ["g1", "ff1"]

    # Path in reverse should be None
    path_rev = tracer.trace_logic_path("g3", "g2")
    assert path_rev is None


def test_cone_tracing_on_aes_benchmark():
    """Verifies cone tracing on top-level hierarchy and standard-cell submodules of AES benchmark."""
    netlist_path = Path("benchmarks/synth/aes_cipher_top.v")
    assert netlist_path.is_file()

    lib_path = find_default_liberty()
    lib = parse_liberty_file(lib_path)
    netlist = parse_netlist_file(netlist_path, liberty=lib)
    top_mod = netlist.top_module
    assert top_mod is not None

    # 1. Test cone tracing on hierarchical top module (target u_datapath)
    tracer = ConeTracer(top_mod)
    target = "u_datapath"
    assert target in top_mod.instances

    cone_fanin_1 = tracer.trace_fanin(target, depth=1)
    assert cone_fanin_1.total_gates >= 1
    assert cone_fanin_1.max_depth_reached <= 1

    cone_fanin_2 = tracer.trace_fanin(target, depth=2)
    assert cone_fanin_2.total_gates >= cone_fanin_1.total_gates

    cone_fanout = tracer.trace_fanout("u_controller", depth=2)
    assert cone_fanout.total_gates >= 1

    # Test submodule extraction & placement/routing of isolated cone
    submod = cone_fanin_2.extract_submodule(top_mod)
    assert len(submod.instances) == cone_fanin_2.total_gates

    sub_placement = run_placement(submod)
    assert sub_placement.num_ranks >= 1
    sub_routing = route_placement(sub_placement)
    assert sub_routing.total_segments > 0
    assert sub_routing.is_strictly_orthogonal

    # 2. Test cone tracing on standard-cell submodule (aes_sbox_lut)
    sbox_mod = netlist["aes_sbox_lut"]
    sbox_tracer = ConeTracer(sbox_mod)
    sbox_target = list(sbox_mod.instances.keys())[-1]

    cone_sbox_1 = sbox_tracer.trace_fanin(sbox_target, depth=1)
    assert cone_sbox_1.total_gates >= 1

    cone_sbox_3 = sbox_tracer.trace_fanin(sbox_target, depth=3)
    assert cone_sbox_3.total_gates >= cone_sbox_1.total_gates

    sbox_submod = cone_sbox_3.extract_submodule(sbox_mod)
    assert len(sbox_submod.instances) == cone_sbox_3.total_gates
    sbox_place = run_placement(sbox_submod)
    assert sbox_place.num_ranks >= 1
    sbox_route = route_placement(sbox_place)
    assert sbox_route.is_strictly_orthogonal
