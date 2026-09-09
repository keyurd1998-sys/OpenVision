"""
Coordinate assignment and channel allocation engine for OpenVision.
Assigns 2D canvas coordinates (X, Y) to each placed gate and port,
allocating routing channels between columns and rows.
"""

from typing import Dict, List, Tuple
from openvision.placement.cycle_breaker import PlacementGraph


def assign_coordinates(
    graph: PlacementGraph,
    col_spacing: float = 120.0,
    row_spacing: float = 45.0,
    center_align_ranks: bool = True,
) -> Tuple[float, float, float, float]:
    """
    Assigns (x, y) coordinates to every node in the PlacementGraph based on
    its rank column and vertical ordering.

    Returns the bounding box: (min_x, min_y, max_x, max_y).
    """
    if not graph.ranks:
        return (0.0, 0.0, 0.0, 0.0)

    # 1. Determine column widths and maximum column height
    col_widths: List[float] = []
    col_heights: List[float] = []

    for rank_nodes in graph.ranks:
        max_w = 60.0
        total_h = 0.0
        for nid in rank_nodes:
            node = graph.nodes[nid]
            if node.width > max_w:
                max_w = node.width
            total_h += node.height + row_spacing
        col_widths.append(max_w)
        col_heights.append(max(total_h, 60.0))

    max_overall_height = max(col_heights) if col_heights else 0.0

    # 2. Assign X coordinates monotonically by rank
    col_x_offsets: List[float] = []
    curr_x = 50.0
    for r, width in enumerate(col_widths):
        col_x_offsets.append(curr_x)
        curr_x += width + col_spacing

    # 3. Assign (x, y) to each node
    for r, rank_nodes in enumerate(graph.ranks):
        rank_x = col_x_offsets[r]
        rank_h = col_heights[r]

        # Vertical start offset (centered or top-aligned)
        if center_align_ranks and rank_h < max_overall_height:
            start_y = 50.0 + (max_overall_height - rank_h) / 2.0
        else:
            start_y = 50.0

        curr_y = start_y
        for nid in rank_nodes:
            node = graph.nodes[nid]
            node.x = rank_x
            node.y = curr_y
            curr_y += node.height + row_spacing

    # 4. Calculate total bounding box
    min_x = 50.0
    min_y = 50.0
    max_x = curr_x
    max_y = max_overall_height + 50.0

    return (min_x, min_y, max_x, max_y)
