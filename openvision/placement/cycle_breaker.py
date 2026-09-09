"""
Cycle breaking and feedback loop decoupling engine for OpenVision.
Decouples sequential feedback loops at flip-flop boundaries and detects/reverses
any combinational cycles to produce a strict Directed Acyclic Graph (DAG).
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any
from openvision.ingestion.netlist_parser import NetlistModule, NetlistInstance, NetlistPort
from openvision.ingestion.symbol_classifier import GateType, PinRole


@dataclass
class PlacementEdge:
    """Represents a directed net connection from source pin to sink pin."""
    src: str        # Source node ID
    dst: str        # Destination node ID
    net_name: str   # Net identifier
    src_pin: str = ""
    dst_pin: str = ""
    is_feedback: bool = False


@dataclass
class PlacementNode:
    """Represents a gate, port, or routing node in the placement graph."""
    id: str
    kind: str       # "PRIMARY_INPUT", "PRIMARY_OUTPUT", "DFF", "INSTANCE", "DUMMY"
    name: str
    ref: Optional[Any] = None  # NetlistInstance or NetlistPort
    width: float = 80.0
    height: float = 60.0
    rank: int = 0
    order: int = 0
    x: float = 0.0
    y: float = 0.0
    preds: List[str] = field(default_factory=list)
    succs: List[str] = field(default_factory=list)

    @property
    def is_sequential(self) -> bool:
        return self.kind == "DFF"

    @property
    def is_port(self) -> bool:
        return self.kind in ("PRIMARY_INPUT", "PRIMARY_OUTPUT")


class PlacementGraph:
    """Directed graph of placement nodes and interconnect edges."""

    def __init__(self):
        self.nodes: Dict[str, PlacementNode] = {}
        self.edges: List[PlacementEdge] = []
        self.ranks: List[List[str]] = []

    def add_node(self, node: PlacementNode) -> None:
        self.nodes[node.id] = node

    def add_edge(self, edge: PlacementEdge) -> None:
        self.edges.append(edge)
        if not edge.is_feedback:
            if edge.dst not in self.nodes[edge.src].succs:
                self.nodes[edge.src].succs.append(edge.dst)
            if edge.src not in self.nodes[edge.dst].preds:
                self.nodes[edge.dst].preds.append(edge.src)

    def get_node(self, node_id: str) -> Optional[PlacementNode]:
        return self.nodes.get(node_id)


def build_placement_graph(module: NetlistModule, decouple_dff: bool = True) -> PlacementGraph:
    """
    Builds a PlacementGraph from a NetlistModule, breaking feedback cycles
    at sequential flip-flop boundaries.
    """
    graph = PlacementGraph()

    # 1. Create primary input nodes
    for port in module.ports.values():
        if port.direction in ("input", "inout"):
            for bit in port.bit_names:
                node_id = f"port_in:{bit}"
                graph.add_node(
                    PlacementNode(
                        id=node_id,
                        kind="PRIMARY_INPUT",
                        name=bit,
                        ref=port,
                        width=50.0,
                        height=24.0,
                    )
                )
        if port.direction in ("output", "inout"):
            for bit in port.bit_names:
                node_id = f"port_out:{bit}"
                graph.add_node(
                    PlacementNode(
                        id=node_id,
                        kind="PRIMARY_OUTPUT",
                        name=bit,
                        ref=port,
                        width=50.0,
                        height=24.0,
                    )
                )

    # 2. Create instance nodes
    for inst in module.instances.values():
        is_dff = (inst.gate_type in (GateType.DFF, GateType.LATCH))
        node_id = f"inst:{inst.name}"
        graph.add_node(
            PlacementNode(
                id=node_id,
                kind="DFF" if is_dff else "INSTANCE",
                name=inst.name,
                ref=inst,
                width=100.0 if is_dff else 80.0,
                height=70.0 if is_dff else 50.0,
            )
        )

    # 3. Create edges from net connectivity
    # Ensure module connectivity is indexed
    module.build_connectivity()

    for inst in module.instances.values():
        dst_node_id = f"inst:{inst.name}"
        is_dst_dff = (inst.gate_type in (GateType.DFF, GateType.LATCH))

        for pin_name, net_expr in inst.connections.items():
            if not net_expr or net_expr in ("1'b0", "1'b1", "1'bx", "1'bz"):
                continue

            # Determine if this pin is an input
            is_input_pin = True
            if inst.classification:
                role = inst.classification.pin_roles.get(pin_name)
                if role in (PinRole.OUTPUT, PinRole.Q, PinRole.QN, PinRole.SUM, PinRole.COUT):
                    is_input_pin = False

            if not is_input_pin:
                continue

            # Find all drivers of this net
            drivers = module.get_drivers(net_expr)
            for drv_src, drv_pin in drivers:
                if drv_src == "PORT":
                    src_node_id = f"port_in:{drv_pin}"
                elif drv_src == "ASSIGN":
                    # RHS net driven
                    continue
                else:
                    src_node_id = f"inst:{drv_src}"

                if src_node_id in graph.nodes and dst_node_id in graph.nodes:
                    src_node = graph.nodes[src_node_id]
                    # Cycle breaking: If decoupling DFFs and source is DFF,
                    # treat DFF -> Logic as forward, but Logic -> DFF as boundary
                    is_feedback = False
                    if decouple_dff and is_dst_dff:
                        # Logic feeding into DFF D input is a sequential endpoint
                        # In the Sugiyama DAG, we break at DFF inputs so loops don't cause cycles
                        is_feedback = True

                    edge = PlacementEdge(
                        src=src_node_id,
                        dst=dst_node_id,
                        net_name=net_expr,
                        src_pin=drv_pin,
                        dst_pin=pin_name,
                        is_feedback=is_feedback,
                    )
                    graph.add_edge(edge)

    # 4. Connect Primary Outputs
    for port in module.ports.values():
        if port.direction in ("output", "inout"):
            for bit in port.bit_names:
                dst_node_id = f"port_out:{bit}"
                drivers = module.get_drivers(bit)
                for drv_src, drv_pin in drivers:
                    if drv_src == "PORT":
                        src_node_id = f"port_in:{drv_pin}"
                    elif drv_src == "ASSIGN":
                        continue
                    else:
                        src_node_id = f"inst:{drv_src}"

                    if src_node_id in graph.nodes:
                        edge = PlacementEdge(
                            src=src_node_id,
                            dst=dst_node_id,
                            net_name=bit,
                            src_pin=drv_pin,
                            dst_pin="IN",
                            is_feedback=False,
                        )
                        graph.add_edge(edge)

    # 5. DFS cycle detection for any remaining combinational feedback loops
    _break_remaining_cycles(graph)

    return graph


def _break_remaining_cycles(graph: PlacementGraph) -> None:
    """
    Detects any remaining directed cycles using Tarjan/DFS back-edge detection
    and breaks them to guarantee a strict Directed Acyclic Graph (DAG).
    """
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {nid: WHITE for nid in graph.nodes}
    edges_to_remove: List[Tuple[str, str]] = []

    def dfs(u: str):
        color[u] = GRAY
        for v in list(graph.nodes[u].succs):
            if color[v] == GRAY:
                # Back-edge detected: u -> v forms a cycle!
                edges_to_remove.append((u, v))
            elif color[v] == WHITE:
                dfs(v)
        color[u] = BLACK

    for nid in graph.nodes:
        if color[nid] == WHITE:
            dfs(nid)

    # Mark back-edges as feedback and remove from DAG adjacency
    if edges_to_remove:
        remove_set = set(edges_to_remove)
        for edge in graph.edges:
            if (edge.src, edge.dst) in remove_set and not edge.is_feedback:
                edge.is_feedback = True
                if edge.dst in graph.nodes[edge.src].succs:
                    graph.nodes[edge.src].succs.remove(edge.dst)
                if edge.src in graph.nodes[edge.dst].preds:
                    graph.nodes[edge.dst].preds.remove(edge.src)
