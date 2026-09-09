"""
Unified Sugiyama placement engine orchestrator for OpenVision.
Executes cycle breaking, topological layering, crossing minimization,
and coordinate assignment to generate production-grade schematic placements.
"""

import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple, Any
from openvision.ingestion.netlist_parser import NetlistModule
from openvision.placement.cycle_breaker import build_placement_graph, PlacementGraph, PlacementNode, PlacementEdge
from openvision.placement.layerer import assign_topological_ranks
from openvision.placement.crossing_minimizer import minimize_crossings
from openvision.placement.coord_assigner import assign_coordinates


@dataclass
class PlacementResult:
    """Holds the complete result of placing a netlist module."""
    module_name: str
    graph: PlacementGraph
    num_ranks: int
    total_nodes: int
    total_edges: int
    feedback_edges: int
    bbox: Tuple[float, float, float, float]  # (min_x, min_y, max_x, max_y)
    elapsed_seconds: float = 0.0

    @property
    def width(self) -> float:
        return self.bbox[2] - self.bbox[0]

    @property
    def height(self) -> float:
        return self.bbox[3] - self.bbox[1]

    def get_rank_distribution(self) -> Dict[int, int]:
        """Returns the number of gates placed in each column rank."""
        return {r: len(nodes) for r, nodes in enumerate(self.graph.ranks)}

    def get_node_position(self, node_id: str) -> Optional[Tuple[float, float]]:
        """Looks up the (X, Y) coordinate of a placed gate or port."""
        node = self.graph.get_node(node_id)
        if node:
            return (node.x, node.y)
        return None

    def print_summary(self) -> None:
        """Prints a formatted summary of placement metrics."""
        print("=" * 60)
        print(f" Placement Summary: {self.module_name}")
        print("=" * 60)
        print(f" Total Placed Nodes: {self.total_nodes}")
        print(f" Total Edges:        {self.total_edges} ({self.feedback_edges} broken feedback loops)")
        print(f" Topological Ranks:  {self.num_ranks} columns")
        print(f" Schematic Canvas:   {self.width:.1f} x {self.height:.1f} units")
        print(f" Placement Runtime:  {self.elapsed_seconds:.3f} s")
        print("-" * 60)
        print(" Rank Distribution (First 15 Columns):")
        dist = self.get_rank_distribution()
        for r in range(min(15, len(dist))):
            bar = "#" * min(40, (dist[r] // 50) + 1)
            print(f"   Col {r:2d}: {dist[r]:4d} gates  {bar}")
        if len(dist) > 15:
            print(f"   ... ({len(dist) - 15} additional columns)")
        print("=" * 60)


def run_placement(
    module: NetlistModule,
    num_crossing_iterations: int = 4,
    col_spacing: float = 120.0,
    row_spacing: float = 45.0,
    center_align_ranks: bool = True,
    decouple_dff: bool = True,
) -> PlacementResult:
    """
    Executes the full 4-stage Sugiyama placement pipeline on a NetlistModule:
      1. Cycle Breaking & DAG Construction
      2. Topological Layering (ASAP Longest-Path Ranking)
      3. Crossing Minimization (Barycentric Sweep)
      4. Coordinate & Channel Assignment
    """
    t0 = time.time()

    # Step 1: Build graph and break feedback loops
    graph = build_placement_graph(module, decouple_dff=decouple_dff)

    # Step 2: Assign topological ranks
    max_rank = assign_topological_ranks(graph)
    num_ranks = max_rank + 1

    # Step 3: Barycentric crossing minimization
    minimize_crossings(graph, num_iterations=num_crossing_iterations)

    # Step 4: Coordinate and channel assignment
    bbox = assign_coordinates(
        graph,
        col_spacing=col_spacing,
        row_spacing=row_spacing,
        center_align_ranks=center_align_ranks,
    )

    t1 = time.time()

    feedback_count = sum(1 for e in graph.edges if e.is_feedback)

    return PlacementResult(
        module_name=module.name,
        graph=graph,
        num_ranks=num_ranks,
        total_nodes=len(graph.nodes),
        total_edges=len(graph.edges),
        feedback_edges=feedback_count,
        bbox=bbox,
        elapsed_seconds=t1 - t0,
    )
