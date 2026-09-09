"""
Data models and sub-module extraction utilities for logic cone analysis.
Defines LogicCone, metrics collection, and dynamic extraction of isolated sub-schematics.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple, Any

from openvision.ingestion.netlist_parser import (
    NetlistModule,
    NetlistInstance,
    NetlistPort,
    NetlistWire,
)


@dataclass
class LogicCone:
    """
    Represents an extracted combinational or sequential logic cone.
    Contains the set of instances, nets, boundary ports, and depth statistics.
    """
    root_name: str
    direction: str  # "FANIN" or "FANOUT"
    depth_limit: Optional[int]
    instances: Set[str] = field(default_factory=set)
    nets: Set[str] = field(default_factory=set)
    boundary_endpoints: Set[str] = field(default_factory=set)  # Registers or primary ports
    max_depth_reached: int = 0

    @property
    def total_gates(self) -> int:
        return len(self.instances)

    @property
    def total_nets(self) -> int:
        return len(self.nets)

    @property
    def total_boundaries(self) -> int:
        return len(self.boundary_endpoints)

    def print_summary(self) -> None:
        """Prints a formatted console summary of the logic cone."""
        print("=" * 60)
        print(f" Logic Cone Analysis: {self.root_name} ({self.direction})")
        print("=" * 60)
        depth_str = f"{self.max_depth_reached} (limit: {self.depth_limit})" if self.depth_limit else f"{self.max_depth_reached} (unbounded)"
        print(f" Logic Depth:            {depth_str}")
        print(f" Total Visited Gates:    {self.total_gates}")
        print(f" Total Internal Nets:    {self.total_nets}")
        print(f" Boundary Endpoints:     {self.total_boundaries} (registers/ports)")
        print("=" * 60)

    def extract_submodule(
        self,
        parent_module: NetlistModule,
        submodule_name: Optional[str] = None,
    ) -> NetlistModule:
        """
        Creates a standalone, fully self-contained NetlistModule representing
        strictly this logic cone. Boundary endpoints become module primary ports,
        and all internal instances and wires are cloned.
        This sub-module can be placed and routed independently to view an isolated cone!
        """
        name = submodule_name or f"cone_{self.direction.lower()}_{self.root_name.replace(':', '_').replace('[', '_').replace(']', '')}"
        sub = NetlistModule(name=name)

        # 1. Clone instances within cone
        for inst_name in self.instances:
            if inst_name in parent_module.instances:
                orig = parent_module.instances[inst_name]
                cloned = NetlistInstance(
                    name=orig.name,
                    cell_type=orig.cell_type,
                    connections=dict(orig.connections),
                    parameters=dict(orig.parameters),
                    classification=orig.classification,
                )
                sub.add_instance(cloned)

        # 2. Add boundary primary ports
        # For fanin cone: boundary inputs feed the cone, root is output
        if self.direction == "FANIN":
            for b in self.boundary_endpoints:
                clean_b = b.split(":")[-1]
                sub.add_port(NetlistPort(name=clean_b, direction="input"))

            root_clean = self.root_name.split(":")[-1]
            sub.add_port(NetlistPort(name=root_clean, direction="output"))

        # For fanout cone: root is input, boundary outputs terminate the cone
        else:
            root_clean = self.root_name.split(":")[-1]
            sub.add_port(NetlistPort(name=root_clean, direction="input"))

            for b in self.boundary_endpoints:
                clean_b = b.split(":")[-1]
                sub.add_port(NetlistPort(name=clean_b, direction="output"))

        # 3. Add internal wires
        for net_name in self.nets:
            sub.add_wire(NetlistWire(name=net_name))

        sub.build_connectivity()
        return sub
