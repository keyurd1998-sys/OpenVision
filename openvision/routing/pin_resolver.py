"""
Pin resolver for OpenVision.
Calculates exact geometric (X, Y) canvas coordinates and perpendicular exit directions
for every input, output, clock, and reset pin of placed gates and ports.
"""

from typing import Dict, List, Optional, Tuple, Any
from openvision.placement.cycle_breaker import PlacementGraph, PlacementNode
from openvision.ingestion.symbol_classifier import GateType, PinRole, SymbolClassification
from openvision.routing.router_models import PinLocation, PinExitDirection, Point


class PinResolver:
    """
    Computes and caches pin positions for every node in a PlacementGraph.
    Adheres strictly to IEEE schematic drawing standards:
      - Logic inputs enter perpendicularly from the West.
      - Logic outputs emerge perpendicularly to the East.
      - Clocks, resets, and enables enter from the South (or bottom edge).
    """

    def __init__(self, graph: PlacementGraph):
        self.graph = graph
        # Map: (node_id, pin_name) -> PinLocation
        self._pin_map: Dict[Tuple[str, str], PinLocation] = {}
        # Map: node_id -> List[PinLocation]
        self._node_pins: Dict[str, List[PinLocation]] = {}
        self._resolve_all_pins()

    def get_pin(self, node_id: str, pin_name: str) -> Optional[PinLocation]:
        """Looks up the PinLocation for a specific pin on a node."""
        loc = self._pin_map.get((node_id, pin_name))
        if loc:
            return loc
        # Fallback: if node exists, try matching case-insensitively or return first matching role
        if node_id in self._node_pins:
            for p in self._node_pins[node_id]:
                if p.pin_name.upper() == pin_name.upper():
                    return p
            # If primary input/output with single pin
            node = self.graph.get_node(node_id)
            if node and node.is_port and self._node_pins[node_id]:
                return self._node_pins[node_id][0]
        return None

    def get_node_pins(self, node_id: str) -> List[PinLocation]:
        """Returns all resolved pins for a node."""
        return self._node_pins.get(node_id, [])

    def _resolve_all_pins(self) -> None:
        """Iterates over all nodes in the graph and assigns pin coordinates."""
        for node_id, node in self.graph.nodes.items():
            pins: List[PinLocation] = []

            if node.kind == "PRIMARY_INPUT":
                # Signal flows OUT to the East towards the circuit
                loc = PinLocation(
                    node_id=node_id,
                    pin_name=node.name,
                    x=node.x + node.width,
                    y=node.y + node.height / 2.0,
                    direction=PinExitDirection.EAST,
                    role=PinRole.OUTPUT,
                )
                pins.append(loc)
                self._pin_map[(node_id, node.name)] = loc
                self._pin_map[(node_id, "OUT")] = loc
                self._pin_map[(node_id, "Y")] = loc

            elif node.kind == "PRIMARY_OUTPUT":
                # Signal flows IN from the West from the circuit
                loc = PinLocation(
                    node_id=node_id,
                    pin_name="IN",
                    x=node.x,
                    y=node.y + node.height / 2.0,
                    direction=PinExitDirection.WEST,
                    role=PinRole.INPUT,
                )
                pins.append(loc)
                self._pin_map[(node_id, "IN")] = loc
                self._pin_map[(node_id, node.name)] = loc
                self._pin_map[(node_id, "A")] = loc

            elif node.kind == "DFF":
                pins = self._resolve_dff_pins(node)

            else:
                # Combinational instance or macro
                pins = self._resolve_combinational_pins(node)

            self._node_pins[node_id] = pins
            for p in pins:
                self._pin_map[(node_id, p.pin_name)] = p

    def _resolve_dff_pins(self, node: PlacementNode) -> List[PinLocation]:
        """Resolves pins for sequential flip-flops and latches."""
        pins: List[PinLocation] = []
        inst = node.ref
        classification: Optional[SymbolClassification] = getattr(inst, "classification", None) if inst else None
        roles = classification.pin_roles if classification else {}
        bubble_pins = set(classification.bubble_pins) if classification else set()

        connections = getattr(inst, "connections", {}) if inst else {}
        all_pins = list(connections.keys()) if connections else ["CLK", "D", "RESET_B", "Q", "QN"]

        # Categorize pins
        clk_pin = None
        rst_pin = None
        set_pin = None
        data_pins = []
        en_pins = []
        q_pins = []
        qn_pins = []
        other_inputs = []

        for p in all_pins:
            role = roles.get(p)
            p_upper = p.upper()

            if role == PinRole.CLOCK or "CLK" in p_upper or p_upper in ("C", "CP"):
                clk_pin = p
            elif role == PinRole.RESET or any(k in p_upper for k in ("RESET", "RST", "CLR", "CLEAR")):
                rst_pin = p
            elif role == PinRole.PRESET or any(k in p_upper for k in ("SET", "PRE", "PRESET")):
                set_pin = p
            elif role == PinRole.DATA or p_upper in ("D", "DATA"):
                data_pins.append(p)
            elif role == PinRole.ENABLE or "EN" in p_upper:
                en_pins.append(p)
            elif role == PinRole.QN or p_upper in ("QN", "Q_N", "IQ_N"):
                qn_pins.append(p)
            elif role == PinRole.Q or p_upper in ("Q", "IQ"):
                q_pins.append(p)
            else:
                if role == PinRole.OUTPUT:
                    q_pins.append(p)
                else:
                    other_inputs.append(p)

        # 1. South pins: CLK, RESET, PRESET
        if clk_pin:
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=clk_pin,
                    x=node.x + 25.0,
                    y=node.y + node.height,
                    direction=PinExitDirection.SOUTH,
                    is_inverted=(clk_pin in bubble_pins),
                    role=PinRole.CLOCK,
                )
            )

        if rst_pin:
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=rst_pin,
                    x=node.x + 65.0,
                    y=node.y + node.height,
                    direction=PinExitDirection.SOUTH,
                    is_inverted=(rst_pin in bubble_pins),
                    role=PinRole.RESET,
                )
            )

        if set_pin:
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=set_pin,
                    x=node.x + 85.0,
                    y=node.y + node.height,
                    direction=PinExitDirection.SOUTH,
                    is_inverted=(set_pin in bubble_pins),
                    role=PinRole.PRESET,
                )
            )

        # 2. West pins: D, EN, other inputs
        west_inputs = data_pins + en_pins + other_inputs
        if not west_inputs and not data_pins:
            west_inputs = ["D"]

        num_west = len(west_inputs)
        for idx, p in enumerate(west_inputs):
            y_pos = node.y + (node.height * (idx + 1.0)) / (num_west + 1.0)
            role = roles.get(p, PinRole.DATA if idx == 0 else PinRole.INPUT)
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=p,
                    x=node.x,
                    y=y_pos,
                    direction=PinExitDirection.WEST,
                    is_inverted=(p in bubble_pins),
                    role=role,
                )
            )

        # 3. East pins: Q, QN
        east_outputs = q_pins + qn_pins
        if not east_outputs:
            east_outputs = ["Q"]
        num_east = len(east_outputs)
        for idx, p in enumerate(east_outputs):
            y_pos = node.y + (node.height * (idx + 1.0)) / (num_east + 1.0)
            role = roles.get(p, PinRole.QN if "N" in p.upper() else PinRole.Q)
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=p,
                    x=node.x + node.width,
                    y=y_pos,
                    direction=PinExitDirection.EAST,
                    is_inverted=(p in bubble_pins),
                    role=role,
                )
            )

        return pins

    def _resolve_combinational_pins(self, node: PlacementNode) -> List[PinLocation]:
        """Resolves pins for combinational logic gates, adders, and macros."""
        pins: List[PinLocation] = []
        inst = node.ref
        classification: Optional[SymbolClassification] = getattr(inst, "classification", None) if inst else None
        roles = classification.pin_roles if classification else {}
        bubble_pins = set(classification.bubble_pins) if classification else set()

        connections = getattr(inst, "connections", {}) if inst else {}
        all_pins = list(connections.keys()) if connections else []

        inputs: List[str] = []
        outputs: List[str] = []
        south_pins: List[str] = []

        for p in all_pins:
            role = roles.get(p)
            p_upper = p.upper()

            if role in (PinRole.OUTPUT, PinRole.SUM, PinRole.COUT) or p_upper in ("Y", "X", "OUT", "SUM", "COUT"):
                outputs.append(p)
            elif role == PinRole.SELECT and classification and classification.gate_type == GateType.MUX2:
                # MUX select line enters from the South
                south_pins.append(p)
            elif role == PinRole.CLOCK or p_upper in ("CLK", "CLOCK", "C", "CP"):
                south_pins.append(p)
            elif role in (PinRole.RESET, PinRole.PRESET) or any(k in p_upper for k in ("RESET", "RST", "CLR", "CLEAR")):
                south_pins.append(p)
            else:
                inputs.append(p)

        # Fallback if no pins detected
        if not outputs and not inputs and not south_pins:
            outputs = ["Y"]
            inputs = ["A", "B"]

        # 1. South pins (e.g. MUX select, clocks, resets)
        num_south = len(south_pins)
        for idx, p in enumerate(south_pins):
            x_pos = node.x + (node.width * (idx + 1.0)) / (num_south + 1.0)
            role = roles.get(p, PinRole.CLOCK if "CLK" in p.upper() else PinRole.SELECT)
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=p,
                    x=x_pos,
                    y=node.y + node.height,
                    direction=PinExitDirection.SOUTH,
                    is_inverted=(p in bubble_pins),
                    role=role,
                )
            )

        # 2. West pins (Inputs)
        num_inputs = len(inputs)
        for idx, p in enumerate(inputs):
            y_pos = node.y + (node.height * (idx + 1.0)) / (num_inputs + 1.0)
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=p,
                    x=node.x,
                    y=y_pos,
                    direction=PinExitDirection.WEST,
                    is_inverted=(p in bubble_pins),
                    role=roles.get(p, PinRole.INPUT),
                )
            )

        # 3. East pins (Outputs)
        num_outputs = len(outputs)
        for idx, p in enumerate(outputs):
            y_pos = node.y + (node.height * (idx + 1.0)) / (num_outputs + 1.0)
            pins.append(
                PinLocation(
                    node_id=node.id,
                    pin_name=p,
                    x=node.x + node.width,
                    y=y_pos,
                    direction=PinExitDirection.EAST,
                    is_inverted=(p in bubble_pins),
                    role=roles.get(p, PinRole.OUTPUT),
                )
            )

        return pins
