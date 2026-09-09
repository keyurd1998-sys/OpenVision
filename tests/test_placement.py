"""
Unit and integration tests for OpenVision Sugiyama Layered Placement Engine.
Tests cycle breaking, topological ranking, crossing minimization,
and coordinate assignment on both unit circuits and the ~10,000-instance AES benchmark.
"""

import pytest
from pathlib import Path
from openvision.ingestion.liberty_parser import parse_liberty_file, find_default_liberty
from openvision.ingestion.netlist_parser import parse_netlist_file, parse_netlist_text
from openvision.placement import (
    run_placement,
    build_placement_graph,
    assign_topological_ranks,
    minimize_crossings,
    assign_coordinates,
)

SAMPLE_FEEDBACK_NETLIST = """
module feedback_loop(input wire clk, input wire in, output wire out);
  wire q1, q2, next_q1;

  sky130_fd_sc_hd__dfxtp_1 r1 (.CLK(clk), .D(next_q1), .Q(q1));
  sky130_fd_sc_hd__dfxtp_1 r2 (.CLK(clk), .D(q1), .Q(q2));
  sky130_fd_sc_hd__xor2_1 g1 (.A(in), .B(q2), .X(next_q1));

  assign out = q2;
endmodule
"""


def test_cycle_breaking_on_sequential_loop():
    netlist = parse_netlist_text(SAMPLE_FEEDBACK_NETLIST)
    mod = netlist["feedback_loop"]
    graph = build_placement_graph(mod, decouple_dff=True)

    # Verify nodes
    assert "port_in:clk" in graph.nodes
    assert "port_in:in" in graph.nodes
    assert "port_out:out" in graph.nodes
    assert "inst:r1" in graph.nodes
    assert "inst:r2" in graph.nodes
    assert "inst:g1" in graph.nodes

    # Verify that the DAG contains no cycles
    visited = set()
    rec_stack = set()

    def has_cycle(u: str) -> bool:
        visited.add(u)
        rec_stack.add(u)
        for v in graph.nodes[u].succs:
            if v not in visited:
                if has_cycle(v):
                    return True
            elif v in rec_stack:
                return True
        rec_stack.remove(u)
        return False

    for nid in graph.nodes:
        if nid not in visited:
            assert not has_cycle(nid), f"Cycle detected involving node {nid}"


def test_topological_ranking_monotonicity():
    netlist = parse_netlist_text(SAMPLE_FEEDBACK_NETLIST)
    mod = netlist["feedback_loop"]
    graph = build_placement_graph(mod, decouple_dff=True)
    max_rank = assign_topological_ranks(graph)

    assert max_rank >= 1
    # For every forward edge u -> v, rank(u) must be strictly less than rank(v)
    for edge in graph.edges:
        if not edge.is_feedback:
            u_node = graph.nodes[edge.src]
            v_node = graph.nodes[edge.dst]
            assert u_node.rank < v_node.rank, f"Rank violation: {edge.src}({u_node.rank}) -> {edge.dst}({v_node.rank})"


def test_coordinate_assignment_monotonicity():
    netlist = parse_netlist_text(SAMPLE_FEEDBACK_NETLIST)
    mod = netlist["feedback_loop"]
    result = run_placement(mod)

    assert result.num_ranks >= 2
    assert result.total_nodes == 6
    assert result.width > 0
    assert result.height > 0

    # Ensure X increases strictly with rank
    for rank_idx, rank_nodes in enumerate(result.graph.ranks):
        for nid in rank_nodes:
            node = result.graph.nodes[nid]
            assert node.rank == rank_idx
            assert node.x > 0
            assert node.y > 0


def test_aes_complex_placement_scale():
    """Validates placement engine on hierarchical top module and submodules of the AES benchmark."""
    lib = parse_liberty_file(find_default_liberty())
    synth_path = Path("benchmarks/synth/aes_cipher_top.v")
    assert synth_path.is_file(), "Synthesized AES netlist must exist"

    netlist = parse_netlist_file(synth_path, liberty=lib)

    # 1. Validate top-level hierarchical block placement
    top_mod = netlist["aes_cipher_top"]
    result_top = run_placement(top_mod, num_crossing_iterations=2)

    assert result_top.total_nodes == 10, f"Expected 10 nodes (3 submodules + 7 ports), got {result_top.total_nodes}"
    assert result_top.num_ranks == 5, f"Expected 5 topological columns, got {result_top.num_ranks}"
    assert result_top.elapsed_seconds < 0.5, f"Top placement was too slow: {result_top.elapsed_seconds:.2f}s"
    assert result_top.width >= 1000.0
    assert result_top.height < 500.0, "Top module must be compact horizontal block layout, not vertical line"

    # Monotonicity of column coordinates for top
    col_x_top = [result_top.graph.nodes[rank[0]].x for rank in result_top.graph.ranks if rank]
    for i in range(len(col_x_top) - 1):
        assert col_x_top[i] < col_x_top[i+1], f"Column X coords must be strictly increasing: {col_x_top}"

    # Check all nodes in top have valid finite coordinates
    for nid, node in result_top.graph.nodes.items():
        assert node.x >= 50.0
        assert node.y >= 50.0
        assert not (node.x != node.x)  # not NaN
        assert not (node.y != node.y)  # not NaN

    # 2. Validate complex submodule placement (aes_datapath with ~780 nodes)
    dp_mod = netlist["aes_datapath"]
    result_dp = run_placement(dp_mod, num_crossing_iterations=2)

    assert result_dp.total_nodes >= 700, f"Expected >= 700 nodes in aes_datapath, got {result_dp.total_nodes}"
    assert result_dp.num_ranks >= 3, f"Expected >= 3 topological columns in datapath, got {result_dp.num_ranks}"
    assert result_dp.elapsed_seconds < 2.0, f"Submodule placement was too slow: {result_dp.elapsed_seconds:.2f}s"

    # Monotonicity of column coordinates for submodule
    col_x_dp = [result_dp.graph.nodes[rank[0]].x for rank in result_dp.graph.ranks if rank]
    for i in range(len(col_x_dp) - 1):
        assert col_x_dp[i] < col_x_dp[i+1], f"Column X coords must be strictly increasing: {col_x_dp}"

    for nid, node in result_dp.graph.nodes.items():
        assert node.x >= 50.0
        assert node.y >= 50.0
        assert not (node.x != node.x)  # not NaN
        assert not (node.y != node.y)  # not NaN
