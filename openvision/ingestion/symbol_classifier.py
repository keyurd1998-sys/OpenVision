"""
Dynamic Boolean function classifier and IEEE logic symbol assigner for OpenVision.
Parses Boolean logic expressions and truth tables from Liberty cells to dynamically
categorize gates into IEEE standard symbols (AND, NAND, OR, NOR, XOR, XNOR, INV, BUF,
MUX, DFF, LATCH, FA, HA, AOI, etc.) without relying on hardcoded cell names.
"""

import re
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Set
from openvision.ingestion.liberty_parser import LibertyCell, LibertyPin


class GateType(Enum):
    """IEEE / standard schematic symbol types."""
    INV     = "INV"       # Inverter (triangle with bubble)
    BUF     = "BUF"       # Buffer (triangle without bubble)
    AND     = "AND"       # AND gate
    NAND    = "NAND"      # NAND gate (bubble at output)
    OR      = "OR"        # OR gate
    NOR     = "NOR"       # NOR gate (bubble at output)
    XOR     = "XOR"       # XOR gate
    XNOR    = "XNOR"      # XNOR gate (bubble at output)
    MUX2    = "MUX2"      # 2:1 Multiplexer
    MUX4    = "MUX4"      # 4:1 Multiplexer
    DFF     = "DFF"       # D Flip-Flop
    LATCH   = "LATCH"     # D Latch
    TIEHI   = "TIEHI"     # Tie High (Logic 1)
    TIELO   = "TIELO"     # Tie Low (Logic 0)
    FA      = "FA"        # Full Adder
    HA      = "HA"        # Half Adder
    MAJ     = "MAJ"       # Majority gate
    AOI     = "AOI"       # AND-OR-Invert compound gate
    OAI     = "OAI"       # OR-AND-Invert compound gate
    AO      = "AO"        # AND-OR compound gate
    OA      = "OA"        # OR-AND compound gate
    ISOBUF  = "ISOBUF"    # Isolation buffer / gated buffer
    MACRO   = "MACRO"     # Generic structured rectangular block


class PinRole(Enum):
    """Semantic role of a pin within a gate symbol."""
    INPUT   = "INPUT"     # Generic logic input
    OUTPUT  = "OUTPUT"    # Generic logic output
    CLOCK   = "CLOCK"     # Clock input (dynamic triangle)
    RESET   = "RESET"     # Reset input
    PRESET  = "PRESET"    # Preset / set input
    ENABLE  = "ENABLE"    # Clock / latch enable
    SELECT  = "SELECT"    # Multiplexer select line
    DATA0   = "DATA0"     # Mux data input 0
    DATA1   = "DATA1"     # Mux data input 1
    DATA    = "DATA"      # Register D input
    Q       = "Q"         # Register non-inverting output
    QN      = "QN"        # Register inverting output
    SUM     = "SUM"       # Adder sum output
    COUT    = "COUT"      # Adder carry output
    CIN     = "CIN"       # Adder carry input
    SUPPLY  = "SUPPLY"    # Power or ground rail


class SymbolClassification:
    """Holds the classified symbol details for a standard cell."""

    def __init__(
        self,
        cell_name: str,
        gate_type: GateType,
        num_inputs: int = 0,
        num_outputs: int = 1,
        pin_roles: Optional[Dict[str, PinRole]] = None,
        bubble_pins: Optional[List[str]] = None,
        description: str = "",
    ):
        self.cell_name = cell_name
        self.gate_type = gate_type
        self.num_inputs = num_inputs
        self.num_outputs = num_outputs
        self.pin_roles: Dict[str, PinRole] = pin_roles or {}
        self.bubble_pins: List[str] = bubble_pins or []
        self.description = description

    def __repr__(self) -> str:
        return (
            f"<SymbolClassification {self.cell_name}: type={self.gate_type.value} "
            f"inputs={self.num_inputs} outputs={self.num_outputs} "
            f"bubbles={self.bubble_pins}>"
        )


def _lib_to_python_expr(expr: str) -> str:
    """Translates Liberty Boolean expression syntax to a valid Python logical expression."""
    # Handle single quote postfix inversion: A' -> (not A)
    expr = re.sub(r"([a-zA-Z0-9_]+)\x27", r"(not \1)", expr)
    # Handle ! prefix inversion: !A or !(...) -> (not A)
    expr = re.sub(r"!(?=[a-zA-Z0-9_\(])", " not ", expr)
    # Handle & and * (AND)
    expr = expr.replace("&", " and ").replace("*", " and ")
    # Handle | and + (OR)
    expr = expr.replace("|", " or ").replace("+", " or ")
    # Handle ^ (XOR)
    expr = expr.replace("^", " ^ ")
    return expr


def _extract_variables(py_expr: str) -> List[str]:
    """Finds all variable identifiers used in the expression."""
    tokens = re.findall(r"[a-zA-Z_][a-zA-Z0-9_]*", py_expr)
    keywords = {"not", "and", "or", "True", "False"}
    vars_found = [t for t in tokens if t not in keywords]
    # Return unique sorted variables
    return sorted(list(dict.fromkeys(vars_found)))


def _evaluate_truth_table(py_expr: str, var_names: List[str]) -> Tuple[int, ...]:
    """Evaluates the Boolean expression over all 2^N input combinations."""
    n = len(var_names)
    tt: List[int] = []
    for i in range(1 << n):
        env = {var_names[j]: (1 if (i & (1 << (n - 1 - j))) else 0) for j in range(n)}
        val = bool(eval(py_expr, {"__builtins__": {}}, env))
        tt.append(1 if val else 0)
    return tuple(tt)


def classify_cell(cell: LibertyCell) -> SymbolClassification:
    """
    Dynamically classifies a LibertyCell into an IEEE standard gate symbol
    using its Boolean function, pin attributes, and sequential storage definitions.
    """
    # 1. Check for Sequential Flip-Flop
    if cell.ff is not None:
        return _classify_flip_flop(cell)

    # 2. Check for Sequential Latch
    if cell.latch is not None:
        return _classify_latch(cell)

    # Check if pins explicitly indicate a clock and output Q
    if any(p.clock for p in cell.pins.values()):
        return _classify_flip_flop(cell)

    outputs = cell.output_pins
    inputs = cell.input_pins

    # 3. Multi-output cells (Full Adder, Half Adder, or Macro)
    if len(outputs) > 1:
        return _classify_multi_output(cell)

    # 4. Zero outputs (Tie cells or special physical cells)
    if len(outputs) == 0:
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.MACRO,
            num_inputs=len(inputs),
            num_outputs=0,
            description="Special / Physical cell",
        )

    # 5. Single-output combinational cells
    out_pin_name = outputs[0]
    out_pin = cell.pins[out_pin_name]
    func_str = out_pin.function

    if not func_str:
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.MACRO,
            num_inputs=len(inputs),
            num_outputs=1,
            description="Combinational macro block",
        )

    func_clean = func_str.strip()

    # Constants
    if func_clean == "1":
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.TIEHI,
            num_inputs=0,
            num_outputs=1,
            pin_roles={out_pin_name: PinRole.OUTPUT},
            description="Tie-High (Logic 1)",
        )
    if func_clean == "0":
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.TIELO,
            num_inputs=0,
            num_outputs=1,
            pin_roles={out_pin_name: PinRole.OUTPUT},
            description="Tie-Low (Logic 0)",
        )

    # Parse function into Python expression
    py_expr = _lib_to_python_expr(func_clean)
    all_vars = _extract_variables(py_expr)
    # Match variables to input pins
    relevant_vars = [v for v in all_vars if v in cell.pins and cell.pins[v].is_input]
    if not relevant_vars:
        relevant_vars = all_vars

    num_vars = len(relevant_vars)
    try:
        tt = _evaluate_truth_table(py_expr, relevant_vars)
    except Exception:
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.MACRO,
            num_inputs=len(inputs),
            num_outputs=1,
            description=f"Complex logic: {func_str}",
        )

    pin_roles = {out_pin_name: PinRole.OUTPUT}
    for inp in inputs:
        pin_roles[inp] = PinRole.INPUT
    bubble_pins: List[str] = []

    # 1-input gates: INV or BUF
    if num_vars == 1:
        inp_var = relevant_vars[0]
        if tt == (1, 0):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.INV,
                num_inputs=1,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="IEEE Inverter",
            )
        if tt == (0, 1):
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.BUF,
                num_inputs=1,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="IEEE Buffer",
            )

    # 2-input gates: AND, NAND, OR, NOR, XOR, XNOR, ISOBUF
    if num_vars == 2:
        if tt == (0, 0, 0, 1):
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.AND,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                description="2-input IEEE AND Gate",
            )
        if tt == (1, 1, 1, 0):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.NAND,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="2-input IEEE NAND Gate",
            )
        if tt == (0, 1, 1, 1):
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.OR,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                description="2-input IEEE OR Gate",
            )
        if tt == (1, 0, 0, 0):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.NOR,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="2-input IEEE NOR Gate",
            )
        if tt == (0, 1, 1, 0):
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.XOR,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                description="2-input IEEE XOR Gate",
            )
        if tt == (1, 0, 0, 1):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.XNOR,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="2-input IEEE XNOR Gate",
            )
        # AND with one inverted input (e.g. A & !SLEEP): Isolation buffer / Gated cell
        if sum(tt) == 1:
            # Detect which input is inverted
            inverted_input = relevant_vars[1] if tt == (0, 1, 0, 0) else relevant_vars[0]
            bubble_pins.append(inverted_input)
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.ISOBUF,
                num_inputs=2,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="Isolation Buffer / Gated Logic",
            )

    # 3-input gates: MUX2, AND3, NAND3, OR3, NOR3, XOR3, XNOR3, MAJ3, AOI/OAI
    if num_vars == 3:
        if tt == (0, 0, 0, 0, 0, 0, 0, 1):
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.AND, num_inputs=3,
                num_outputs=1, pin_roles=pin_roles, description="3-input IEEE AND Gate"
            )
        if tt == (1, 1, 1, 1, 1, 1, 1, 0):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.NAND, num_inputs=3,
                num_outputs=1, pin_roles=pin_roles, bubble_pins=bubble_pins,
                description="3-input IEEE NAND Gate"
            )
        if tt == (0, 1, 1, 1, 1, 1, 1, 1):
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.OR, num_inputs=3,
                num_outputs=1, pin_roles=pin_roles, description="3-input IEEE OR Gate"
            )
        if tt == (1, 0, 0, 0, 0, 0, 0, 0):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.NOR, num_inputs=3,
                num_outputs=1, pin_roles=pin_roles, bubble_pins=bubble_pins,
                description="3-input IEEE NOR Gate"
            )
        if tt == (0, 1, 1, 0, 1, 0, 0, 1):
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.XOR, num_inputs=3,
                num_outputs=1, pin_roles=pin_roles, description="3-input IEEE XOR Gate"
            )
        if tt == (1, 0, 0, 1, 0, 1, 1, 0):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.XNOR, num_inputs=3,
                num_outputs=1, pin_roles=pin_roles, bubble_pins=bubble_pins,
                description="3-input IEEE XNOR Gate"
            )

        # Dynamic Multiplexer check: (S ? D1 : D0) or (D0 & !S) | (D1 & S)
        mux_result = _detect_mux2(py_expr, relevant_vars)
        if mux_result:
            s_pin, d0_pin, d1_pin, is_inverted = mux_result
            pin_roles[s_pin] = PinRole.SELECT
            pin_roles[d0_pin] = PinRole.DATA0
            pin_roles[d1_pin] = PinRole.DATA1
            if is_inverted:
                bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.MUX2,
                num_inputs=3,
                num_outputs=1,
                pin_roles=pin_roles,
                bubble_pins=bubble_pins,
                description="2:1 Multiplexer" + (" (Inverting)" if is_inverted else ""),
            )

        # Majority check: SUM of minterms with at least two 1s
        if sum(tt) == 4 and _is_majority(py_expr, relevant_vars):
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.MAJ,
                num_inputs=3,
                num_outputs=1,
                pin_roles=pin_roles,
                description="3-input Majority Gate",
            )

    # 4-input gates: AND4, NAND4, OR4, NOR4, XOR4, etc.
    if num_vars == 4:
        if tt == (0,) * 15 + (1,):
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.AND, num_inputs=4,
                num_outputs=1, pin_roles=pin_roles, description="4-input IEEE AND Gate"
            )
        if tt == (1,) * 15 + (0,):
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.NAND, num_inputs=4,
                num_outputs=1, pin_roles=pin_roles, bubble_pins=bubble_pins,
                description="4-input IEEE NAND Gate"
            )
        if tt == (0,) + (1,) * 15:
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.OR, num_inputs=4,
                num_outputs=1, pin_roles=pin_roles, description="4-input IEEE OR Gate"
            )
        if tt == (1,) + (0,) * 15:
            bubble_pins.append(out_pin_name)
            return SymbolClassification(
                cell_name=cell.name, gate_type=GateType.NOR, num_inputs=4,
                num_outputs=1, pin_roles=pin_roles, bubble_pins=bubble_pins,
                description="4-input IEEE NOR Gate"
            )

    # Compound gates check (AOI, OAI, AO, OA)
    cname_lower = cell.name.lower()
    footprint_lower = (cell.cell_footprint or "").lower()
    tag = cname_lower + " " + footprint_lower
    if "aoi" in tag or ("a" in tag and "oi" in tag):
        bubble_pins.append(out_pin_name)
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.AOI,
            num_inputs=len(inputs),
            num_outputs=1,
            pin_roles=pin_roles,
            bubble_pins=bubble_pins,
            description="AND-OR-Invert Compound Gate",
        )
    if "oai" in tag or ("o" in tag and "ai" in tag):
        bubble_pins.append(out_pin_name)
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.OAI,
            num_inputs=len(inputs),
            num_outputs=1,
            pin_roles=pin_roles,
            bubble_pins=bubble_pins,
            description="OR-AND-Invert Compound Gate",
        )
    if "ao" in tag or ("a" in tag and "o" in tag):
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.AO,
            num_inputs=len(inputs),
            num_outputs=1,
            pin_roles=pin_roles,
            description="AND-OR Compound Gate",
        )
    if "oa" in tag or ("o" in tag and "a" in tag):
        return SymbolClassification(
            cell_name=cell.name,
            gate_type=GateType.OA,
            num_inputs=len(inputs),
            num_outputs=1,
            pin_roles=pin_roles,
            description="OR-AND Compound Gate",
        )

    # Default fallback: structured rectangular macro
    return SymbolClassification(
        cell_name=cell.name,
        gate_type=GateType.MACRO,
        num_inputs=len(inputs),
        num_outputs=1,
        pin_roles=pin_roles,
        description=f"Standard Cell: {cell.name}",
    )


def _detect_mux2(py_expr: str, vars_3: List[str]) -> Optional[Tuple[str, str, str, bool]]:
    """
    Dynamically tests if a 3-variable expression is a 2:1 MUX.
    Returns (select_pin, data0_pin, data1_pin, is_inverted) or None.
    """
    for s_var in vars_3:
        others = [v for v in vars_3 if v != s_var]
        d0_candidate, d1_candidate = others[0], others[1]

        for inv in (False, True):
            for d0_pin, d1_pin in ((d0_candidate, d1_candidate), (d1_candidate, d0_candidate)):
                is_match = True
                for s_val in (0, 1):
                    for d0_val in (0, 1):
                        for d1_val in (0, 1):
                            env = {s_var: s_val, d0_pin: d0_val, d1_pin: d1_val}
                            expected = d1_val if s_val else d0_val
                            if inv:
                                expected = 1 - expected
                            res = 1 if eval(py_expr, {"__builtins__": {}}, env) else 0
                            if res != expected:
                                is_match = False
                                break
                        if not is_match:
                            break
                    if not is_match:
                        break
                if is_match:
                    return (s_var, d0_pin, d1_pin, inv)
    return None


def _is_majority(py_expr: str, vars_3: List[str]) -> bool:
    """Checks if the expression matches the majority function (at least two 1s)."""
    for a in (0, 1):
        for b in (0, 1):
            for c in (0, 1):
                env = {vars_3[0]: a, vars_3[1]: b, vars_3[2]: c}
                expected = 1 if (a + b + c >= 2) else 0
                res = 1 if eval(py_expr, {"__builtins__": {}}, env) else 0
                if res != expected:
                    return False
    return True


def _classify_flip_flop(cell: LibertyCell) -> SymbolClassification:
    """Classifies a sequential flip-flop cell and assigns pin roles."""
    pin_roles: Dict[str, PinRole] = {}
    bubble_pins: List[str] = []

    # Assign clock
    clk_name = cell.clock_pin
    if clk_name and clk_name in cell.pins:
        pin_roles[clk_name] = PinRole.CLOCK
        if cell.ff and cell.ff.clocked_on and cell.ff.clocked_on.startswith("!"):
            bubble_pins.append(clk_name)

    # Assign data D
    d_name = None
    if cell.ff and cell.ff.next_state:
        clean_d = cell.ff.next_state.lstrip("!~ ")
        if clean_d in cell.pins:
            d_name = clean_d
    if not d_name:
        for p in cell.pins.values():
            if p.is_input and p.name in ("D", "DATA", "d"):
                d_name = p.name
                break
    if d_name:
        pin_roles[d_name] = PinRole.DATA

    # Assign reset
    if cell.ff and cell.ff.clear:
        clr_name = cell.ff.clear.lstrip("!~ ")
        if clr_name in cell.pins:
            pin_roles[clr_name] = PinRole.RESET
            if cell.ff.clear.startswith("!"):
                bubble_pins.append(clr_name)

    # Assign preset
    if cell.ff and cell.ff.preset:
        pre_name = cell.ff.preset.lstrip("!~ ")
        if pre_name in cell.pins:
            pin_roles[pre_name] = PinRole.PRESET
            if cell.ff.preset.startswith("!"):
                bubble_pins.append(pre_name)

    # Assign enable
    for p in cell.pins.values():
        if p.is_input and p.name not in pin_roles:
            if any(k in p.name.upper() for k in ("EN", "GATE", "DE")):
                pin_roles[p.name] = PinRole.ENABLE
            else:
                pin_roles[p.name] = PinRole.INPUT

    # Assign outputs Q and QN
    for p in cell.pins.values():
        if p.is_output:
            if p.function == "IQ_N" or "N" in p.name:
                pin_roles[p.name] = PinRole.QN
                bubble_pins.append(p.name)
            else:
                pin_roles[p.name] = PinRole.Q

    return SymbolClassification(
        cell_name=cell.name,
        gate_type=GateType.DFF,
        num_inputs=len(cell.input_pins),
        num_outputs=len(cell.output_pins),
        pin_roles=pin_roles,
        bubble_pins=bubble_pins,
        description="IEEE D-Flip-Flop",
    )


def _classify_latch(cell: LibertyCell) -> SymbolClassification:
    """Classifies a sequential latch cell and assigns pin roles."""
    pin_roles: Dict[str, PinRole] = {}
    bubble_pins: List[str] = []

    if cell.latch and cell.latch.enable:
        en_name = cell.latch.enable.lstrip("!~ ")
        if en_name in cell.pins:
            pin_roles[en_name] = PinRole.ENABLE
            if cell.latch.enable.startswith("!"):
                bubble_pins.append(en_name)

    if cell.latch and cell.latch.data_in:
        d_name = cell.latch.data_in.lstrip("!~ ")
        if d_name in cell.pins:
            pin_roles[d_name] = PinRole.DATA

    if cell.latch and cell.latch.clear:
        clr_name = cell.latch.clear.lstrip("!~ ")
        if clr_name in cell.pins:
            pin_roles[clr_name] = PinRole.RESET
            if cell.latch.clear.startswith("!"):
                bubble_pins.append(clr_name)

    for p in cell.pins.values():
        if p.is_input and p.name not in pin_roles:
            pin_roles[p.name] = PinRole.INPUT
        elif p.is_output:
            if p.function == "IQ_N" or "N" in p.name:
                pin_roles[p.name] = PinRole.QN
                bubble_pins.append(p.name)
            else:
                pin_roles[p.name] = PinRole.Q

    return SymbolClassification(
        cell_name=cell.name,
        gate_type=GateType.LATCH,
        num_inputs=len(cell.input_pins),
        num_outputs=len(cell.output_pins),
        pin_roles=pin_roles,
        bubble_pins=bubble_pins,
        description="D Latch",
    )


def _classify_multi_output(cell: LibertyCell) -> SymbolClassification:
    """Classifies multi-output cells like Full Adder (FA) or Half Adder (HA)."""
    pin_roles: Dict[str, PinRole] = {}
    inputs = cell.input_pins
    outputs = cell.output_pins

    sum_pin = None
    cout_pin = None
    for p in outputs:
        p_upper = p.upper()
        if "SUM" in p_upper or p_upper == "S":
            sum_pin = p
            pin_roles[p] = PinRole.SUM
        elif "COUT" in p_upper or "CARRY" in p_upper or p_upper == "CO":
            cout_pin = p
            pin_roles[p] = PinRole.COUT
        else:
            pin_roles[p] = PinRole.OUTPUT

    for p in inputs:
        p_upper = p.upper()
        if "CIN" in p_upper or p_upper == "CI":
            pin_roles[p] = PinRole.CIN
        else:
            pin_roles[p] = PinRole.INPUT

    if sum_pin and cout_pin:
        if len(inputs) == 3 or any(pin_roles.get(p) == PinRole.CIN for p in inputs):
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.FA,
                num_inputs=len(inputs),
                num_outputs=len(outputs),
                pin_roles=pin_roles,
                description="Full Adder",
            )
        elif len(inputs) == 2:
            return SymbolClassification(
                cell_name=cell.name,
                gate_type=GateType.HA,
                num_inputs=2,
                num_outputs=len(outputs),
                pin_roles=pin_roles,
                description="Half Adder",
            )

    return SymbolClassification(
        cell_name=cell.name,
        gate_type=GateType.MACRO,
        num_inputs=len(inputs),
        num_outputs=len(outputs),
        pin_roles=pin_roles,
        description=f"Multi-output Macro ({len(inputs)} in, {len(outputs)} out)",
    )
