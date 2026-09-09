"""
Topological layering and rank assignment engine for OpenVision.
Assigns gates and ports to vertical columns (ranks) using longest-path leveling
and topological sorting from Primary Inputs/Registers (Rank 0) to Primary Outputs (Final Rank).
"""

from collections import deque
from typing import Dict, List, Set, Tuple
from openvision.placement.cycle_breaker import PlacementGraph, PlacementNode, PlacementEdge


def assign_topological_ranks(graph: PlacementGraph) -> int:
    """
    Computes topological rank (column level) for every node in the PlacementGraph.
    Returns the maximum rank (total number of columns - 1).
    """
    # 1. Compute in-degree in the DAG
    in_degree = {nid: len(node.preds) for nid, node in graph.nodes.items()}

    # 2. Queue all source nodes (in-degree 0, including primary inputs and DFFs)
    queue = deque([nid for nid, deg in in_degree.items() if deg == 0])

    # Default rank = 0
    for nid in queue:
        graph.nodes[nid].rank = 0

    visited_count = 0
    max_rank = 0

    # 3. Process nodes in topological order (Longest-Path / ASAP leveling)
    while queue:
        u_id = queue.popleft()
        visited_count += 1
        u_node = graph.nodes[u_id]
        u_rank = u_node.rank

        for v_id in u_node.succs:
            v_node = graph.nodes[v_id]
            # Longest path: v must be to the right of all its predecessors
            if u_rank + 1 > v_node.rank:
                v_node.rank = u_rank + 1
                if v_node.rank > max_rank:
                    max_rank = v_node.rank

            in_degree[v_id] -= 1
            if in_degree[v_id] == 0:
                queue.append(v_id)

    # 4. Handle any unvisited nodes (e.g. disconnected components)
    for nid, deg in in_degree.items():
        if deg > 0 and graph.nodes[nid].rank == 0:
            graph.nodes[nid].rank = 0

    # 5. Place Primary Outputs on the rightmost rank or just beyond their drivers
    for nid, node in graph.nodes.items():
        if node.kind == "PRIMARY_OUTPUT":
            if node.preds:
                highest_pred_rank = max(graph.nodes[p].rank for p in node.preds)
                node.rank = highest_pred_rank + 1
                if node.rank > max_rank:
                    max_rank = node.rank
            else:
                node.rank = max_rank

    # 6. Group nodes into ranks list
    ranks: List[List[str]] = [[] for _ in range(max_rank + 1)]
    for nid, node in graph.nodes.items():
        ranks[node.rank].append(nid)

    graph.ranks = ranks
    return max_rank
