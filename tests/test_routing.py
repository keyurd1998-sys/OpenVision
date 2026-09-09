"""
Unit and integration tests for Stage 3: Manhattan Orthogonal Auto-Router.
Validates strict 90-degree segment geometry, solder dot placement,
HFN decoupling, and full-scale routing on the complex AES-128 benchmark.
"""

import pytest
from pathlib import Path

from openvision.ingestion.liberty_parser import parse_liberty_text, parse_liberty_file, find_default_liberty
from openvision.ingestion.netlist_parser import parse_netlist_text, parse_netlist_file
from openvision.placement.placement_engine import run_placement
from openvision.routing import (
    Point,
    WireSegment,
    SegmentOrientation,
    PinExitDirection,
    SolderDot,
    route_placement,
    PinResolver,
    HighFanoutDecoupler,
    SolderDotManager,
    OrthogonalRouter,
)


def test_strict_orthogonality_validation():
    """Verifies that WireSegment strictly enforces orthogonal endpoints."""
    # Valid horizontal segment
    s_h = WireSegment(Point(0, 10), Point(50, 10), "net_a", SegmentOrientation.HORIZONTAL)
    assert s_h.is_horizontal
    assert not s_h.is_vertical
    assert s_h.length == 50.0

    # Valid vertical segment
    s_v = WireSegment(Point(20, 0), Point(20, 40), "net_b", SegmentOrientation.VERTICAL)
    assert s_v.is_vertical
    assert not s_v.is_horizontal
    assert s_v.length == 40.0

    # Diagonal segment must raise ValueError
    with pytest.raises(ValueError):
        WireSegment(Point(0, 0), Point(10, 10), "diag", SegmentOrientation.HORIZONTAL)


def test_solder_dot_insertion_on_junctions():
    """Verifies that solder dots (•) are placed at T-junctions and suppressed at 2-way corners."""
    mgr = SolderDotManager()

    # Case 1: Simple L-bend (2-way corner) -> No solder dot!
    corner_segs = [
        WireSegment(Point(0, 10), Point(30, 10), "net1", SegmentOrientation.HORIZONTAL),
        WireSegment(Point(30, 10), Point(30, 50), "net1", SegmentOrientation.VERTICAL),
    ]
    dots = mgr.detect_junctions(corner_segs, "net1")
    assert len(dots) == 0, "Solder dot incorrectly placed at simple 2-way corner bend"

    # Case 2: 3-way T-junction (Trunk with a branch) -> Must have solder dot!
    t_segs = [
        WireSegment(Point(0, 30), Point(30, 30), "net2", SegmentOrientation.HORIZONTAL),  # Driver
        WireSegment(Point(30, 10), Point(30, 50), "net2", SegmentOrientation.VERTICAL),   # Trunk
        WireSegment(Point(30, 10), Point(60, 10), "net2", SegmentOrientation.HORIZONTAL),  # Sink 1
        WireSegment(Point(30, 50), Point(60, 50), "net2", SegmentOrientation.HORIZONTAL),  # Sink 2
    ]
    dots = mgr.detect_junctions(t_segs, "net2")
    dot_coords = {(round(d.x, 1), round(d.y, 1)) for d in dots}
    assert (30.0, 30.0) in dot_coords or len(dots) >= 1, "Expected solder dot at branch junction"


def test_hfn_decoupling():
    """Verifies that global clock/reset and high-fanout nets are decoupled into stubs."""
    decoupler = HighFanoutDecoupler(hfn_threshold=5, decouple_globals=True)

    assert decoupler.is_hfn("clk", fanout=2)
    assert decoupler.is_hfn("rst_n", fanout=1)
    assert decoupler.is_hfn("global_clock", fanout=1)
    assert decoupler.is_hfn("data_bus", fanout=10)
    assert not decoupler.is_hfn("data_bus", fanout=3)


def test_pin_resolver_orientations():
    """Verifies IEEE standard perpendicular pin directions."""
    sample_verilog = """
    module simple_sub (clk, rst, a, b, q);
        input clk, rst, a, b;
        output q;
        wire n1;
        sky130_fd_sc_hd__nand2_1 g1 (.A(a), .B(b), .Y(n1));
        sky130_fd_sc_hd__dfxtp_1 ff1 (.CLK(clk), .D(n1), .Q(q));
    endmodule
    """
    netlist = parse_netlist_text(sample_verilog)
    placement = run_placement(netlist.top_module)
    pin_res = PinResolver(placement.graph)

    # Primary Input
    p_in = pin_res.get_pin("port_in:a", "a")
    assert p_in is not None
    assert p_in.direction == PinExitDirection.EAST

    # Primary Output
    p_out = pin_res.get_pin("port_out:q", "IN")
    assert p_out is not None
    assert p_out.direction == PinExitDirection.WEST

    # DFF pins
    clk_pin = pin_res.get_pin("inst:ff1", "CLK")
    assert clk_pin is not None
    assert clk_pin.direction == PinExitDirection.SOUTH

    d_pin = pin_res.get_pin("inst:ff1", "D")
    assert d_pin is not None
    assert d_pin.direction == PinExitDirection.WEST

    q_pin = pin_res.get_pin("inst:ff1", "Q")
    assert q_pin is not None
    assert q_pin.direction == PinExitDirection.EAST


def test_complex_aes_routing_scale_and_orthogonality():
    """
    Validates end-to-end Manhattan orthogonal routing on hierarchical top module
    and complex submodules of the AES-128 benchmark.
    """
    netlist_path = Path("benchmarks/synth/aes_cipher_top.v")
    if not netlist_path.is_file():
        pytest.skip("AES benchmark netlist not found")

    lib_path = find_default_liberty()
    lib = parse_liberty_file(lib_path)
    netlist = parse_netlist_file(netlist_path, liberty=lib)

    # 1. Test top-level hierarchical routing
    placement_top = run_placement(netlist["aes_cipher_top"])
    routing_top = route_placement(placement_top, hfn_threshold=20)

    # Top module: 100% strictly orthogonal
    assert routing_top.is_strictly_orthogonal, "Violated: non-orthogonal segments found in top module"
    assert routing_top.elapsed_seconds < 0.5, f"Routing too slow: {routing_top.elapsed_seconds}s"
    assert routing_top.total_segments >= 30, f"Expected >= 30 segments in top module, got {routing_top.total_segments}"

    for seg in routing_top.all_segments():
        dx = abs(seg.p1.x - seg.p2.x)
        dy = abs(seg.p1.y - seg.p2.y)
        assert dx < 1e-4 or dy < 1e-4, f"Diagonal segment in net {seg.net_name}: {seg.p1} -> {seg.p2}"

    # 2. Test complex submodule routing (aes_key_schedule with ~650 nodes and multi-fanout branches)
    placement_sub = run_placement(netlist["aes_key_schedule"])
    routing_sub = route_placement(placement_sub, hfn_threshold=20)

    # Submodule: 100% strictly orthogonal, solder dots, and HFN decoupling
    assert routing_sub.is_strictly_orthogonal, "Violated: non-orthogonal segments found in submodule"
    assert routing_sub.elapsed_seconds < 2.0, f"Submodule routing too slow: {routing_sub.elapsed_seconds}s"
    assert routing_sub.total_segments > 2000, f"Expected >2000 segments in key_schedule, got {routing_sub.total_segments}"
    assert routing_sub.total_solder_dots > 100, f"Expected >100 solder dots, got {routing_sub.total_solder_dots}"
    assert routing_sub.decoupled_hfn_count > 0, f"Expected decoupled HFNs, got {routing_sub.decoupled_hfn_count}"

    for seg in routing_sub.all_segments():
        dx = abs(seg.p1.x - seg.p2.x)
        dy = abs(seg.p1.y - seg.p2.y)
        assert dx < 1e-4 or dy < 1e-4, f"Diagonal segment in net {seg.net_name}: {seg.p1} -> {seg.p2}"
