"""
Crossing reduction engine using the Barycentric heuristic for OpenVision.
Applies alternating forward and backward sweeps across topological ranks
to order gates vertically, minimizing wire crossings.
"""

from typing import Dict, List
from openvision.placement.cycle_breaker import PlacementGraph


def minimize_crossings(graph: PlacementGraph, num_iterations: int = 4) -> None:
    """
    Minimizes edge crossings across adjacent ranks using the Barycentric heuristic
    with alternating forward and backward passes.
    """
    if not graph.ranks:
        return

    # 1. Initial ordering: assign initial order indices
    for rank_idx, rank_nodes in enumerate(graph.ranks):
        for order_idx, nid in enumerate(rank_nodes):
            graph.nodes[nid].order = order_idx

    # Position map: nid -> float vertical index
    pos_map: Dict[str, float] = {nid: float(node.order) for nid, node in graph.nodes.items()}

    # 2. Alternating sweeps
    for iteration in range(num_iterations):
        # Forward sweep: from rank 1 up to max_rank
        for r in range(1, len(graph.ranks)):
            rank_nodes = graph.ranks[r]
            barycenters = []
            for nid in rank_nodes:
                node = graph.nodes[nid]
                preds = [p for p in node.preds if p in pos_map]
                if preds:
                    bc = sum(pos_map[p] for p in preds) / len(preds)
                else:
                    bc = pos_map[nid]
                barycenters.append((bc, pos_map[nid], nid))

            # Sort nodes in this rank by barycenter (stable tie-breaking on old pos)
            barycenters.sort(key=lambda x: (x[0], x[1]))
            graph.ranks[r] = [item[2] for item in barycenters]
            for order_idx, nid in enumerate(graph.ranks[r]):
                graph.nodes[nid].order = order_idx
                pos_map[nid] = float(order_idx)

        # Backward sweep: from max_rank - 1 down to 0
        for r in range(len(graph.ranks) - 2, -1, -1):
            rank_nodes = graph.ranks[r]
            barycenters = []
            for nid in rank_nodes:
                node = graph.nodes[nid]
                succs = [s for s in node.succs if s in pos_map]
                if succs:
                    bc = sum(pos_map[s] for s in succs) / len(succs)
                else:
                    bc = pos_map[nid]
                barycenters.append((bc, pos_map[nid], nid))

            barycenters.sort(key=lambda x: (x[0], x[1]))
            graph.ranks[r] = [item[2] for item in barycenters]
            for order_idx, nid in enumerate(graph.ranks[r]):
                graph.nodes[nid].order = order_idx
                pos_map[nid] = float(order_idx)
