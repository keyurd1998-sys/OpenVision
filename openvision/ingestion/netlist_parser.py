"""
Structural Verilog netlist parser and connectivity graph builder for OpenVision.
Parses technology-mapped Verilog netlists into an internal representation of modules,
ports, wires, cell instantiations, and interconnect nets, with fanin/fanout cone tracing.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union, Any

from openvision.ingestion.liberty_parser import LibertyLibrary
from openvision.ingestion.symbol_classifier import classify_cell, GateType, PinRole, SymbolClassification


@dataclass
class NetlistPort:
    """Represents a primary module port."""
    name: str
    direction: str  # "input", "output", "inout"
    msb: Optional[int] = None
    lsb: Optional[int] = None

    @property
    def is_bus(self) -> bool:
        return self.msb is not None and self.lsb is not None

    @property
    def width(self) -> int:
        if not self.is_bus:
            return 1
        return abs(self.msb - self.lsb) + 1

    @property
    def bit_names(self) -> List[str]:
        if not self.is_bus:
            return [self.name]
        step = 1 if self.msb >= self.lsb else -1
        return [f"{self.name}[{i}]" for i in range(self.msb, self.lsb - step, -step)]


@dataclass
class NetlistWire:
    """Represents a wire or bus declaration within a module."""
    name: str
    msb: Optional[int] = None
    lsb: Optional[int] = None

    @property
    def is_bus(self) -> bool:
        return self.msb is not None and self.lsb is not None

    @property
    def width(self) -> int:
        if not self.is_bus:
            return 1
        return abs(self.msb - self.lsb) + 1

    @property
    def bit_names(self) -> List[str]:
        if not self.is_bus:
            return [self.name]
        step = 1 if self.msb >= self.lsb else -1
        return [f"{self.name}[{i}]" for i in range(self.msb, self.lsb - step, -step)]


@dataclass
class NetlistInstance:
    """Represents an instantiated standard cell or sub-block."""
    name: str
    cell_type: str
    connections: Dict[str, str] = field(default_factory=dict)  # pin_name -> net_name/expression
    parameters: Dict[str, Any] = field(default_factory=dict)
    classification: Optional[SymbolClassification] = None

    @property
    def gate_type(self) -> GateType:
        if self.classification:
            return self.classification.gate_type
        return GateType.MACRO

    def get_input_nets(self) -> List[str]:
        """Returns the list of net names driving the inputs of this instance."""
        if self.classification:
            input_pins = [
                pin for pin, role in self.classification.pin_roles.items()
                if role not in (PinRole.OUTPUT, PinRole.Q, PinRole.QN, PinRole.SUM, PinRole.COUT, PinRole.SUPPLY)
            ]
            return [self.connections[pin] for pin in input_pins if pin in self.connections and self.connections[pin]]
        return [
            net for pin, net in self.connections.items()
            if pin.upper() not in ("Y", "X", "Q", "QN", "SUM", "COUT", "OUT", "VDD", "VSS", "VPWR", "VGND") and net
        ]

    def get_output_nets(self) -> List[str]:
        """Returns the list of net names driven by the outputs of this instance."""
        if self.classification:
            output_pins = [
                pin for pin, role in self.classification.pin_roles.items()
                if role in (PinRole.OUTPUT, PinRole.Q, PinRole.QN, PinRole.SUM, PinRole.COUT)
            ]
            return [self.connections[pin] for pin in output_pins if pin in self.connections and self.connections[pin]]
        return [
            net for pin, net in self.connections.items()
            if pin.upper() in ("Y", "X", "Q", "QN", "SUM", "COUT", "OUT") and net
        ]


@dataclass
class NetlistAssign:
    """Represents a continuous assignment: assign lhs = rhs;"""
    lhs: str
    rhs: str


class NetlistModule:
    """Represents a parsed structural Verilog module."""

    def __init__(self, name: str):
        self.name = name
        self.ports: Dict[str, NetlistPort] = {}
        self.wires: Dict[str, NetlistWire] = {}
        self.instances: Dict[str, NetlistInstance] = {}
        self.assigns: List[NetlistAssign] = []

        # Connectivity indices: net -> drivers, net -> loads
        self._drivers: Dict[str, List[Tuple[str, str]]] = {}  # net -> [(inst_name, pin_name) or ("PORT", port_name)]
        self._loads: Dict[str, List[Tuple[str, str]]] = {}    # net -> [(inst_name, pin_name) or ("PORT", port_name)]
        self._connectivity_built = False

    def add_port(self, port: NetlistPort) -> None:
        self.ports[port.name] = port
        self._connectivity_built = False

    def add_wire(self, wire: NetlistWire) -> None:
        self.wires[wire.name] = wire
        self._connectivity_built = False

    def add_instance(self, instance: NetlistInstance) -> None:
        self.instances[instance.name] = instance
        self._connectivity_built = False

    def add_assign(self, assign: NetlistAssign) -> None:
        self.assigns.append(assign)
        self._connectivity_built = False

    def link_library(self, lib: LibertyLibrary) -> None:
        """Annotates each instance in the module with its Liberty symbol classification."""
        for inst in self.instances.values():
            cell = lib.get_cell(inst.cell_type)
            if cell:
                inst.classification = classify_cell(cell)
            else:
                inst.classification = SymbolClassification(
                    cell_name=inst.cell_type,
                    gate_type=GateType.MACRO,
                    description=f"Unrecognized cell: {inst.cell_type}",
                )
        self.build_connectivity()

    def build_connectivity(self) -> None:
        """Constructs driver and load connectivity maps for fast netlist traversal."""
        self._drivers.clear()
        self._loads.clear()

        # Primary input ports drive nets
        for port in self.ports.values():
            if port.direction in ("input", "inout"):
                for bit in port.bit_names:
                    self._drivers.setdefault(bit, []).append(("PORT", bit))
            if port.direction in ("output", "inout"):
                for bit in port.bit_names:
                    self._loads.setdefault(bit, []).append(("PORT", bit))

        # Assign statements: rhs drives lhs
        for asn in self.assigns:
            self._drivers.setdefault(asn.lhs, []).append(("ASSIGN", asn.rhs))
            self._loads.setdefault(asn.rhs, []).append(("ASSIGN", asn.lhs))

        # Instances: pin roles determine whether pin is driver or load
        for inst in self.instances.values():
            for pin_name, net_expr in inst.connections.items():
                if not net_expr or net_expr in ("1'b0", "1'b1", "1'bx", "1'bz"):
                    continue

                is_driver = False
                if inst.classification:
                    role = inst.classification.pin_roles.get(pin_name)
                    if role in (PinRole.OUTPUT, PinRole.Q, PinRole.QN, PinRole.SUM, PinRole.COUT):
                        is_driver = True
                else:
                    # Heuristic if unclassified: pin name starting with Y, X, Q, OUT
                    if pin_name.upper() in ("Y", "X", "Q", "QN", "SUM", "COUT", "OUT"):
                        is_driver = True

                if is_driver:
                    self._drivers.setdefault(net_expr, []).append((inst.name, pin_name))
                else:
                    self._loads.setdefault(net_expr, []).append((inst.name, pin_name))

        self._connectivity_built = True

    def get_drivers(self, net_name: str) -> List[Tuple[str, str]]:
        """Returns all drivers for a given net: [(source, pin_name), ...]"""
        if not self._connectivity_built:
            self.build_connectivity()
        return self._drivers.get(net_name, [])

    def get_loads(self, net_name: str) -> List[Tuple[str, str]]:
        """Returns all sinks/loads for a given net: [(sink, pin_name), ...]"""
        if not self._connectivity_built:
            self.build_connectivity()
        return self._loads.get(net_name, [])

    def get_summary(self) -> Dict[str, Any]:
        """Generates a summary of module statistics, gates, and netlist connectivity."""
        if not self._connectivity_built:
            self.build_connectivity()

        gate_type_counts: Dict[str, int] = {}
        cell_name_counts: Dict[str, int] = {}
        sequential_count = 0
        combinational_count = 0

        for inst in self.instances.values():
            gtype = inst.gate_type.value
            gate_type_counts[gtype] = gate_type_counts.get(gtype, 0) + 1
            cell_name_counts[inst.cell_type] = cell_name_counts.get(inst.cell_type, 0) + 1
            if inst.gate_type in (GateType.DFF, GateType.LATCH):
                sequential_count += 1
            else:
                combinational_count += 1

        all_nets = set(self._drivers.keys()).union(set(self._loads.keys()))

        return {
            "module_name": self.name,
            "total_instances": len(self.instances),
            "sequential_instances": sequential_count,
            "combinational_instances": combinational_count,
            "total_ports": len(self.ports),
            "input_ports": sum(1 for p in self.ports.values() if p.direction == "input"),
            "output_ports": sum(1 for p in self.ports.values() if p.direction == "output"),
            "total_wires": len(self.wires),
            "total_nets": len(all_nets),
            "gate_types": gate_type_counts,
            "cell_types": cell_name_counts,
        }

    def print_summary(self) -> None:
        """Prints a human-readable gate and connectivity summary."""
        summary = self.get_summary()
        print(f"============================================================")
        print(f" Module: {summary['module_name']}")
        print(f"============================================================")
        print(f" Instances:       {summary['total_instances']} total ({summary['combinational_instances']} combinational, {summary['sequential_instances']} sequential)")
        print(f" Ports:           {summary['total_ports']} ({summary['input_ports']} in, {summary['output_ports']} out)")
        print(f" Declared Wires:  {summary['total_wires']}")
        print(f" Connected Nets:  {summary['total_nets']}")
        print(f"------------------------------------------------------------")
        print(f" Recognized Gate Symbols:")
        for gtype, count in sorted(summary["gate_types"].items(), key=lambda x: -x[1]):
            print(f"   {gtype:12s}: {count:3d}")
        print(f"------------------------------------------------------------")
        print(f" Technology Cell Breakdown:")
        for cname, count in sorted(summary["cell_types"].items(), key=lambda x: -x[1]):
            print(f"   {cname:35s}: {count:3d}")
        print(f"============================================================")


class Netlist:
    """Represents a complete parsed structural Verilog netlist containing one or more modules."""

    def __init__(self, filepath: Optional[Path] = None):
        self.filepath = filepath
        self.modules: Dict[str, NetlistModule] = {}
        self.top_module_name: Optional[str] = None

    def add_module(self, module: NetlistModule) -> None:
        self.modules[module.name] = module
        if self.top_module_name is None:
            self.top_module_name = module.name

    @property
    def top_module(self) -> Optional[NetlistModule]:
        if self.top_module_name:
            return self.modules.get(self.top_module_name)
        return next(iter(self.modules.values())) if self.modules else None

    def link_library(self, lib: LibertyLibrary) -> None:
        """Links standard cell library to all modules in the netlist."""
        for mod in self.modules.values():
            mod.link_library(lib)

    def __getitem__(self, module_name: str) -> NetlistModule:
        return self.modules[module_name]

    def __contains__(self, module_name: str) -> bool:
        return module_name in self.modules

    def __len__(self) -> int:
        return len(self.modules)


def _tokenize_verilog(code: str) -> List[str]:
    """Tokenizes structural Verilog, handling comments, strings, identifiers, and symbols."""
    token_spec = [
        ("COMMENT_BLOCK", r"/\*.*?\*/"),
        ("COMMENT_LINE",  r"//.*$"),
        ("STRING",        r"\"[^\"]*\""),
        ("ESCAPED_ID",    r"\\\S+"),
        ("NUMBER",        r"([0-9]+\x27[bB][01xzXZ_]+|[0-9]+\x27[hH][0-9a-fA-F_]+|[0-9]+\x27[dD][0-9_]+|[0-9]+)"),
        ("IDENTIFIER",    r"[a-zA-Z_][a-zA-Z0-9_$]*"),
        ("PUNCT",         r"[;,\(\)\[\]\{\}\.:#=]"),
        ("SKIP",          r"\s+"),
        ("MISMATCH",      r"."),
    ]
    tok_regex = "|".join(f"(?P<{pair[0]}>{pair[1]})" for pair in token_spec)
    tokens: List[str] = []
    for mo in re.finditer(tok_regex, code, flags=re.MULTILINE | re.DOTALL):
        kind = mo.lastgroup
        val = mo.group()
        if kind in ("COMMENT_BLOCK", "COMMENT_LINE", "SKIP", "MISMATCH"):
            continue
        tokens.append(val.strip())
    return tokens


def parse_netlist_text(text: str, filepath: Optional[Path] = None) -> Netlist:
    """Parses structural Verilog source text into a Netlist object."""
    tokens = _tokenize_verilog(text)
    netlist = Netlist(filepath=filepath)

    i = 0
    n = len(tokens)

    while i < n:
        if tokens[i] != "module":
            i += 1
            continue

        i += 1
        if i >= n:
            break
        mod_name = tokens[i]
        i += 1

        module = NetlistModule(name=mod_name)
        netlist.add_module(module)

        # Parse module port list (e.g. `(a, b, c);` or ANSI `(input a, ...);`)
        if i < n and tokens[i] == "(":
            i += 1
            # Check if ANSI port style
            paren_depth = 1
            port_tokens: List[str] = []
            while i < n and paren_depth > 0:
                if tokens[i] == "(":
                    paren_depth += 1
                elif tokens[i] == ")":
                    paren_depth -= 1
                    if paren_depth == 0:
                        i += 1
                        break
                port_tokens.append(tokens[i])
                i += 1

            # If ANSI style, port_tokens will contain 'input' or 'output'
            if any(t in ("input", "output", "inout") for t in port_tokens):
                _parse_ansi_ports(port_tokens, module)

        if i < n and tokens[i] == ";":
            i += 1

        # Parse module body
        while i < n and tokens[i] != "endmodule":
            tok = tokens[i]

            # Port declarations (non-ANSI style)
            if tok in ("input", "output", "inout"):
                direction = tok
                i += 1
                if i < n and tokens[i] in ("wire", "reg"):
                    i += 1
                if i < n and tokens[i] == "signed":
                    i += 1

                msb, lsb = None, None
                if i < n and tokens[i] == "[":
                    i += 1  # consume [
                    msb = int(tokens[i])
                    i += 1  # consume msb
                    if i < n and tokens[i] == ":":
                        i += 1  # consume :
                    lsb = int(tokens[i])
                    i += 1  # consume lsb
                    if i < n and tokens[i] == "]":
                        i += 1  # consume ]

                while i < n and tokens[i] != ";":
                    pname = tokens[i]
                    module.add_port(NetlistPort(name=pname, direction=direction, msb=msb, lsb=lsb))
                    i += 1
                    if i < n and tokens[i] == ",":
                        i += 1
                if i < n and tokens[i] == ";":
                    i += 1

            # Wire declarations
            elif tok == "wire":
                i += 1
                if i < n and tokens[i] == "signed":
                    i += 1
                msb, lsb = None, None
                if i < n and tokens[i] == "[":
                    i += 1  # consume [
                    msb = int(tokens[i])
                    i += 1  # consume msb
                    if i < n and tokens[i] == ":":
                        i += 1  # consume :
                    lsb = int(tokens[i])
                    i += 1  # consume lsb
                    if i < n and tokens[i] == "]":
                        i += 1  # consume ]

                while i < n and tokens[i] != ";":
                    wname = tokens[i]
                    module.add_wire(NetlistWire(name=wname, msb=msb, lsb=lsb))
                    i += 1
                    if i < n and tokens[i] == ",":
                        i += 1
                if i < n and tokens[i] == ";":
                    i += 1

            # Continuous assignments
            elif tok == "assign":
                i += 1
                lhs_parts: List[str] = []
                while i < n and tokens[i] != "=":
                    lhs_parts.append(tokens[i])
                    i += 1
                if i < n and tokens[i] == "=":
                    i += 1
                rhs_parts: List[str] = []
                while i < n and tokens[i] != ";":
                    rhs_parts.append(tokens[i])
                    i += 1
                if i < n and tokens[i] == ";":
                    i += 1
                module.add_assign(NetlistAssign(lhs="".join(lhs_parts), rhs="".join(rhs_parts)))

            # Cell / sub-module instantiation
            else:
                cell_type = tok
                i += 1

                # Optional parameter assignments: #(.PARAM(val), ...)
                params: Dict[str, Any] = {}
                if i < n and tokens[i] == "#":
                    i += 1
                    if i < n and tokens[i] == "(":
                        pdepth = 1
                        i += 1
                        while i < n and pdepth > 0:
                            if tokens[i] == "(":
                                pdepth += 1
                            elif tokens[i] == ")":
                                pdepth -= 1
                            i += 1

                # Instance name and port connections
                inst_name = tokens[i]
                i += 1

                if i < n and tokens[i] == "(":
                    i += 1
                    connections: Dict[str, str] = {}
                    while i < n and tokens[i] != ")":
                        if tokens[i] == ".":
                            i += 1
                            pin_name = tokens[i]
                            i += 1  # pin name
                            if i < n and tokens[i] == "(":
                                i += 1  # (
                                pdepth = 1
                                net_tokens: List[str] = []
                                while i < n and pdepth > 0:
                                    if tokens[i] == "(":
                                        pdepth += 1
                                        net_tokens.append(tokens[i])
                                    elif tokens[i] == ")":
                                        pdepth -= 1
                                        if pdepth > 0:
                                            net_tokens.append(tokens[i])
                                    else:
                                        net_tokens.append(tokens[i])
                                    i += 1
                                connections[pin_name] = "".join(net_tokens)
                            if i < n and tokens[i] == ",":
                                i += 1
                        else:
                            i += 1

                    if i < n and tokens[i] == ")":
                        i += 1
                    if i < n and tokens[i] == ";":
                        i += 1

                    module.add_instance(
                        NetlistInstance(
                            name=inst_name,
                            cell_type=cell_type,
                            connections=connections,
                            parameters=params,
                        )
                    )
                else:
                    i += 1

        if i < n and tokens[i] == "endmodule":
            i += 1

    return netlist


def _parse_ansi_ports(tokens: List[str], module: NetlistModule) -> None:
    """Helper to parse ANSI-style port declarations in module headers."""
    i = 0
    n = len(tokens)
    current_dir = "input"

    while i < n:
        if tokens[i] in ("input", "output", "inout"):
            current_dir = tokens[i]
            i += 1
        if i < n and tokens[i] in ("wire", "reg"):
            i += 1
        if i < n and tokens[i] == "signed":
            i += 1

        msb, lsb = None, None
        if i < n and tokens[i] == "[":
            i += 1  # consume [
            msb = int(tokens[i])
            i += 1  # consume msb
            if i < n and tokens[i] == ":":
                i += 1  # consume :
            lsb = int(tokens[i])
            i += 1  # consume lsb
            if i < n and tokens[i] == "]":
                i += 1  # consume ]

        if i < n and tokens[i] not in (",", ")"):
            pname = tokens[i]
            module.add_port(NetlistPort(name=pname, direction=current_dir, msb=msb, lsb=lsb))
            i += 1

        if i < n and tokens[i] == ",":
            i += 1


def parse_netlist_file(file_path: Union[str, Path], liberty: Optional[LibertyLibrary] = None) -> Netlist:
    """Parses a structural Verilog netlist file from disk, optionally linking a Liberty library."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Netlist file not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    netlist = parse_netlist_text(text, filepath=path)
    if liberty is not None:
        netlist.link_library(liberty)
    return netlist
