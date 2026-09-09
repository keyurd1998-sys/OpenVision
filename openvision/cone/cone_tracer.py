"""
Incremental logic cone tracing engine for OpenVision.
Traverses structural Verilog netlists to extract forward fanout cones,
backward fanin cones, and critical logic paths bounded by sequential registers
or primary I/O ports.
"""

from collections import deque
from typing import Dict, List, Optional, Set, Tuple, Any

from openvision.ingestion.netlist_parser import NetlistModule, NetlistInstance, NetlistPort
from openvision.cone.cone_models import LogicCone


class ConeTracer:
    """
    High-performance logic cone tracer for VLSI netlists.
    Extracts fanin and fanout cones with optional depth constraints and register boundary stops.
    """

    def __init__(self, module: NetlistModule):
        self.module = module
        if not self.module._connectivity_built:
            self.module.build_connectivity()

    def trace_fanin(
        self,
        target: str,
        depth: Optional[int] = None,
        stop_at_dff: bool = True,
    ) -> LogicCone:
        """
        Traces the backward fanin logic cone driving the target instance, port, or net.
        Stops at sequential register boundaries (flip-flop Q outputs) or primary inputs.
        """
        clean_target = target.replace("inst:", "").replace("port_out:", "").replace("port_in:", "")

        cone = LogicCone(
            root_name=clean_target,
            direction="FANIN",
            depth_limit=depth,
        )

        initial_nets: List[str] = []

        # 1. Resolve starting nets
        if clean_target in self.module.instances:
            inst = self.module.instances[clean_target]
            cone.instances.add(clean_target)
            initial_nets.extend(inst.get_input_nets())
        elif clean_target in self.module.ports:
            # Output port driven by internal net
            initial_nets.append(clean_target)
        elif clean_target in self.module._drivers or clean_target in self.module._loads:
            initial_nets.append(clean_target)
        else:
            # Check if port bit or bus
            drivers = self.module.get_drivers(clean_target)
            if drivers:
                initial_nets.append(clean_target)

        # 2. BFS Traversal
        queue: deque[Tuple[str, int]] = deque([(net, 0) for net in initial_nets])
        visited_nets: Set[str] = set()

        while queue:
            net_name, curr_depth = queue.popleft()
            if net_name in visited_nets:
                continue
            visited_nets.add(net_name)
            cone.nets.add(net_name)
            cone.max_depth_reached = max(cone.max_depth_reached, curr_depth)

            drivers = self.module.get_drivers(net_name)
            if not drivers:
                cone.boundary_endpoints.add(f"PORT:{net_name}")
                continue

            for drv_src, drv_pin in drivers:
                if drv_src == "PORT":
                    cone.boundary_endpoints.add(f"PORT:{drv_pin}")
                elif drv_src in self.module.instances:
                    drv_inst = self.module.instances[drv_src]
                    cone.instances.add(drv_src)

                    # Check sequential register boundary
                    is_dff = any(k in drv_inst.cell_type.lower() for k in ("dfx", "dff", "latch", "flop"))
                    if drv_inst.classification:
                        is_dff = is_dff or ("DFF" in drv_inst.gate_type.name or "LATCH" in drv_inst.gate_type.name)

                    if is_dff and stop_at_dff:
                        cone.boundary_endpoints.add(f"DFF:{drv_src}")
                        # Stop backward propagation at DFF boundary
                    else:
                        # Continue expanding if depth permits
                        if depth is None or curr_depth + 1 < depth:
                            for inp_net in drv_inst.get_input_nets():
                                if inp_net not in visited_nets:
                                    queue.append((inp_net, curr_depth + 1))
                        else:
                            # Depth limit reached; register inputs as boundaries
                            for inp_net in drv_inst.get_input_nets():
                                cone.boundary_endpoints.add(f"NET:{inp_net}")

        return cone

    def trace_fanout(
        self,
        target: str,
        depth: Optional[int] = None,
        stop_at_dff: bool = True,
    ) -> LogicCone:
        """
        Traces the forward fanout logic cone driven by the target instance, port, or net.
        Stops at sequential register boundaries (flip-flop D inputs) or primary outputs.
        """
        clean_target = target.replace("inst:", "").replace("port_in:", "").replace("port_out:", "")

        cone = LogicCone(
            root_name=clean_target,
            direction="FANOUT",
            depth_limit=depth,
        )

        initial_nets: List[str] = []

        # 1. Resolve starting nets
        if clean_target in self.module.instances:
            inst = self.module.instances[clean_target]
            cone.instances.add(clean_target)
            initial_nets.extend(inst.get_output_nets())
        elif clean_target in self.module.ports:
            # Input port driving internal nets
            port = self.module.ports[clean_target]
            initial_nets.extend(port.bit_names)
        elif clean_target in self.module._loads or clean_target in self.module._drivers:
            initial_nets.append(clean_target)
        else:
            loads = self.module.get_loads(clean_target)
            if loads:
                initial_nets.append(clean_target)

        # 2. BFS Traversal
        queue: deque[Tuple[str, int]] = deque([(net, 0) for net in initial_nets])
        visited_nets: Set[str] = set()

        while queue:
            net_name, curr_depth = queue.popleft()
            if net_name in visited_nets:
                continue
            visited_nets.add(net_name)
            cone.nets.add(net_name)
            cone.max_depth_reached = max(cone.max_depth_reached, curr_depth)

            loads = self.module.get_loads(net_name)
            if not loads:
                cone.boundary_endpoints.add(f"PORT:{net_name}")
                continue

            for load_dst, load_pin in loads:
                if load_dst == "PORT":
                    cone.boundary_endpoints.add(f"PORT:{load_pin}")
                elif load_dst in self.module.instances:
                    load_inst = self.module.instances[load_dst]
                    cone.instances.add(load_dst)

                    # Check sequential register boundary
                    is_dff = any(k in load_inst.cell_type.lower() for k in ("dfx", "dff", "latch", "flop"))
                    if load_inst.classification:
                        is_dff = is_dff or ("DFF" in load_inst.gate_type.name or "LATCH" in load_inst.gate_type.name)

                    if is_dff and stop_at_dff:
                        cone.boundary_endpoints.add(f"DFF:{load_dst}")
                        # Stop forward propagation at DFF boundary
                    else:
                        # Continue expanding if depth permits
                        if depth is None or curr_depth + 1 < depth:
                            for out_net in load_inst.get_output_nets():
                                if out_net not in visited_nets:
                                    queue.append((out_net, curr_depth + 1))
                        else:
                            for out_net in load_inst.get_output_nets():
                                cone.boundary_endpoints.add(f"NET:{out_net}")

        return cone

    def trace_logic_path(self, start: str, end: str) -> Optional[List[str]]:
        """
        Finds the shortest directed logic path from start instance to end instance.
        Returns the ordered list of instance names along the path, or None if unconnected.
        """
        clean_start = start.replace("inst:", "")
        clean_end = end.replace("inst:", "")

        if clean_start not in self.module.instances or clean_end not in self.module.instances:
            return None

        queue: deque[Tuple[str, List[str]]] = deque([(clean_start, [clean_start])])
        visited: Set[str] = {clean_start}

        while queue:
            curr_inst_name, path = queue.popleft()
            if curr_inst_name == clean_end:
                return path

            inst = self.module.instances[curr_inst_name]
            for out_net in inst.get_output_nets():
                for load_dst, _ in self.module.get_loads(out_net):
                    if load_dst in self.module.instances and load_dst not in visited:
                        visited.add(load_dst)
                        queue.append((load_dst, path + [load_dst]))

        return None
