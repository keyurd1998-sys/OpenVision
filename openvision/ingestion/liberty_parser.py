"""
Liberty (.lib) technology file parser for OpenVision.
Extracts cells, pin definitions, directions, clocks, sequential ff/latch blocks,
and Boolean logic functions from Synopsys Liberty files.
"""

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Union, Iterator


@dataclass
class LibertyPin:
    """Represents a pin on a Liberty standard cell."""
    name: str
    direction: str = "input"  # "input", "output", "inout", "internal"
    function: Optional[str] = None
    clock: bool = False

    @property
    def is_input(self) -> bool:
        return self.direction in ("input", "inout")

    @property
    def is_output(self) -> bool:
        return self.direction in ("output", "inout")


@dataclass
class LibertyFF:
    """Represents sequential flip-flop storage semantics from an 'ff' block."""
    clocked_on: Optional[str] = None
    next_state: Optional[str] = None
    clear: Optional[str] = None
    preset: Optional[str] = None
    clear_preset_var1: Optional[str] = None
    clear_preset_var2: Optional[str] = None


@dataclass
class LibertyLatch:
    """Represents sequential latch storage semantics from a 'latch' block."""
    data_in: Optional[str] = None
    enable: Optional[str] = None
    clear: Optional[str] = None
    preset: Optional[str] = None


@dataclass
class LibertyCell:
    """Represents a technology library standard cell."""
    name: str
    cell_footprint: Optional[str] = None
    area: float = 0.0
    pins: Dict[str, LibertyPin] = field(default_factory=dict)
    pg_pins: List[str] = field(default_factory=list)
    ff: Optional[LibertyFF] = None
    latch: Optional[LibertyLatch] = None

    @property
    def is_sequential(self) -> bool:
        return (self.ff is not None) or (self.latch is not None)

    @property
    def input_pins(self) -> List[str]:
        return [p.name for p in self.pins.values() if p.is_input]

    @property
    def output_pins(self) -> List[str]:
        return [p.name for p in self.pins.values() if p.is_output]

    @property
    def clock_pin(self) -> Optional[str]:
        if self.ff and self.ff.clocked_on:
            clk_clean = self.ff.clocked_on.lstrip("!~ ")
            if clk_clean in self.pins:
                return clk_clean
        for p in self.pins.values():
            if p.clock:
                return p.name
        return None

    def get_pin_function(self, pin_name: str) -> Optional[str]:
        pin = self.pins.get(pin_name)
        return pin.function if pin else None


class LibertyLibrary:
    """Represents an ingested Liberty (.lib) library."""

    def __init__(self, name: str = "", filepath: Optional[Path] = None):
        self.name = name
        self.filepath = filepath
        self.cells: Dict[str, LibertyCell] = {}

    def add_cell(self, cell: LibertyCell) -> None:
        self.cells[cell.name] = cell

    def get_cell(self, name: str) -> Optional[LibertyCell]:
        return self.cells.get(name)

    def __contains__(self, name: str) -> bool:
        return name in self.cells

    def __getitem__(self, name: str) -> LibertyCell:
        return self.cells[name]

    def __len__(self) -> int:
        return len(self.cells)

    def __iter__(self) -> Iterator[str]:
        return iter(self.cells)

    def __repr__(self) -> str:
        return f"<LibertyLibrary '{self.name}' cells={len(self.cells)}>"


# Precompiled regexes for high-performance parsing
RE_LIBRARY = re.compile(r"(?<!\w)library\s*\(\s*\"?([^\")]+)\"?\s*\)")
RE_CELL = re.compile(r"(?<!\w)cell\s*\(\s*\"?([^\")]+)\"?\s*\)")
RE_PG_PIN = re.compile(r"(?<!\w)pg_pin\s*\(\s*\"?([^\")]+)\"?\s*\)")
RE_PIN = re.compile(r"(?<!\w)pin\s*\(\s*\"?([^\")]+)\"?\s*\)")
RE_FF = re.compile(r"(?<!\w)ff\s*\(")
RE_LATCH = re.compile(r"(?<!\w)latch\s*\(")

RE_DIRECTION = re.compile(r"(?<!\w)direction\s*:\s*\"?([^\";]+)\"?\s*;")
RE_FUNCTION = re.compile(r"(?<!\w)function\s*:\s*\"([^\"]+)\"")
RE_CLOCK = re.compile(r"(?<!\w)clock\s*:\s*\"?([^\";]+)\"?\s*;")
RE_AREA = re.compile(r"(?<!\w)area\s*:\s*([0-9.]+)\s*;")
RE_FOOTPRINT = re.compile(r"(?<!\w)cell_footprint\s*:\s*\"?([^\";]+)\"?\s*;")

RE_CLOCKED_ON = re.compile(r"(?<!\w)clocked_on\s*:\s*\"([^\"]+)\"")
RE_NEXT_STATE = re.compile(r"(?<!\w)next_state\s*:\s*\"([^\"]+)\"")
RE_CLEAR = re.compile(r"(?<!\w)clear\s*:\s*\"([^\"]+)\"")
RE_PRESET = re.compile(r"(?<!\w)preset\s*:\s*\"([^\"]+)\"")
RE_DATA_IN = re.compile(r"(?<!\w)data_in\s*:\s*\"([^\"]+)\"")
RE_ENABLE = re.compile(r"(?<!\w)enable\s*:\s*\"([^\"]+)\"")


def parse_liberty_text(text: str, lib_name: str = "", filepath: Optional[Path] = None) -> LibertyLibrary:
    """
    Parses Liberty text stream and extracts standard cells, pins, and attributes.
    Optimized for high speed on multi-megabyte Liberty files by selectively indexing
    cell and pin groups while bypassing dense timing and power tables.
    """
    lib = LibertyLibrary(name=lib_name, filepath=filepath)

    current_cell: Optional[LibertyCell] = None
    current_pin: Optional[LibertyPin] = None
    current_ff: Optional[LibertyFF] = None
    current_latch: Optional[LibertyLatch] = None

    depth = 0
    cell_depth: Optional[int] = None
    pin_depth: Optional[int] = None
    ff_depth: Optional[int] = None
    latch_depth: Optional[int] = None

    in_block_comment = False

    for line in text.splitlines():
        sline = line.strip()
        if not sline:
            continue

        # Handle multi-line comments
        if in_block_comment:
            end_comment_idx = sline.find("*/")
            if end_comment_idx != -1:
                in_block_comment = False
                sline = sline[end_comment_idx + 2:].strip()
                if not sline:
                    continue
            else:
                continue

        if sline.startswith("/*"):
            end_comment_idx = sline.find("*/", 2)
            if end_comment_idx != -1:
                sline = sline[end_comment_idx + 2:].strip()
                if not sline:
                    continue
            else:
                in_block_comment = True
                continue

        if sline.startswith("//"):
            continue

        # Check library name if not provided
        if not lib.name and depth == 0:
            m_lib = RE_LIBRARY.search(sline)
            if m_lib:
                lib.name = m_lib.group(1)

        # Check cell start
        m_cell = RE_CELL.search(sline)
        if m_cell:
            cell_name = m_cell.group(1)
            current_cell = LibertyCell(name=cell_name)
            lib.add_cell(current_cell)
            cell_depth = depth
            current_pin = None
            current_ff = None
            current_latch = None
            pin_depth = None
            ff_depth = None
            latch_depth = None

        elif current_cell is not None:
            # Check for pg_pin
            m_pg = RE_PG_PIN.search(sline)
            if m_pg:
                current_cell.pg_pins.append(m_pg.group(1))
            else:
                # Check for pin
                m_pin = RE_PIN.search(sline)
                if m_pin:
                    pin_name = m_pin.group(1)
                    current_pin = LibertyPin(name=pin_name)
                    current_cell.pins[pin_name] = current_pin
                    pin_depth = depth
                elif RE_FF.search(sline):
                    current_ff = LibertyFF()
                    current_cell.ff = current_ff
                    ff_depth = depth
                elif RE_LATCH.search(sline):
                    current_latch = LibertyLatch()
                    current_cell.latch = current_latch
                    latch_depth = depth

            # Extract pin attributes
            if current_pin is not None:
                m_dir = RE_DIRECTION.search(sline)
                if m_dir:
                    current_pin.direction = m_dir.group(1).strip().lower()
                m_fn = RE_FUNCTION.search(sline)
                if m_fn:
                    current_pin.function = m_fn.group(1).strip()
                m_clk = RE_CLOCK.search(sline)
                if m_clk:
                    current_pin.clock = (m_clk.group(1).strip().lower() == "true")

            # Extract FF attributes
            elif current_ff is not None:
                m_clk = RE_CLOCKED_ON.search(sline)
                if m_clk:
                    current_ff.clocked_on = m_clk.group(1).strip()
                m_ns = RE_NEXT_STATE.search(sline)
                if m_ns:
                    current_ff.next_state = m_ns.group(1).strip()
                m_clr = RE_CLEAR.search(sline)
                if m_clr:
                    current_ff.clear = m_clr.group(1).strip()
                m_pre = RE_PRESET.search(sline)
                if m_pre:
                    current_ff.preset = m_pre.group(1).strip()

            # Extract Latch attributes
            elif current_latch is not None:
                m_din = RE_DATA_IN.search(sline)
                if m_din:
                    current_latch.data_in = m_din.group(1).strip()
                m_en = RE_ENABLE.search(sline)
                if m_en:
                    current_latch.enable = m_en.group(1).strip()
                m_clr = RE_CLEAR.search(sline)
                if m_clr:
                    current_latch.clear = m_clr.group(1).strip()
                m_pre = RE_PRESET.search(sline)
                if m_pre:
                    current_latch.preset = m_pre.group(1).strip()

            # Extract top-level cell attributes
            elif current_cell is not None and current_pin is None and current_ff is None and current_latch is None:
                m_area = RE_AREA.search(sline)
                if m_area:
                    try:
                        current_cell.area = float(m_area.group(1))
                    except ValueError:
                        pass
                m_foot = RE_FOOTPRINT.search(sline)
                if m_foot:
                    current_cell.cell_footprint = m_foot.group(1).strip()

        # Update block nesting depth
        open_braces = sline.count("{")
        close_braces = sline.count("}")
        depth += open_braces - close_braces

        # Reset active blocks upon leaving their scopes
        if pin_depth is not None and depth <= pin_depth:
            current_pin = None
            pin_depth = None
        if ff_depth is not None and depth <= ff_depth:
            current_ff = None
            ff_depth = None
        if latch_depth is not None and depth <= latch_depth:
            current_latch = None
            latch_depth = None
        if cell_depth is not None and depth <= cell_depth:
            current_cell = None
            cell_depth = None

    return lib


def parse_liberty_file(file_path: Union[str, Path]) -> LibertyLibrary:
    """Parses a Liberty (.lib) file from disk."""
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Liberty file not found: {path}")

    with open(path, "r", encoding="utf-8", errors="replace") as f:
        text = f.read()

    return parse_liberty_text(text, filepath=path)


def find_default_liberty() -> Path:
    """Locates the default standard cell PDK Liberty file (Sky130)."""
    pdk_root = os.environ.get("PDK_ROOT", "/eda/SKY130_PDK")
    candidate_paths = [
        Path(pdk_root) / "sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib",
        Path("/eda/OpenROAD-flow-scripts/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"),
    ]
    for p in candidate_paths:
        if p.is_file():
            return p
    raise FileNotFoundError(f"Default Liberty file not found in candidates: {candidate_paths}")
