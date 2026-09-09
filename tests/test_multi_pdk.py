import os
import pytest
from pathlib import Path
from openvision.ingestion.liberty_parser import parse_liberty_file
from openvision.ingestion.symbol_classifier import classify_cell, GateType

PDK_PATHS = {
    "sky130hd": "/eda/SKY130_PDK/sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib",
    "sky130hs": "/eda/SKY130_PDK/sky130A/libs.ref/sky130_fd_sc_hs/lib/sky130_fd_sc_hs__tt_025C_1v80.lib",
    "nangate45": "/eda/OpenROAD-flow-scripts/flow/platforms/nangate45/lib/NangateOpenCellLibrary_typical.lib",
    "ihp-sg13g2": "/eda/OpenROAD-flow-scripts/flow/platforms/ihp-sg13g2/lib/sg13g2_stdcell_typ_1p20V_25C.lib",
    "gf180": "/eda/OpenROAD-flow-scripts/flow/platforms/gf180/lib/gf180mcu_fd_sc_mcu7t5v0__tt_025C_5v00.lib.gz",
}

AVAILABLE_PDKS = [(name, path) for name, path in PDK_PATHS.items() if os.path.exists(path)]


@pytest.mark.parametrize("pdk_name,pdk_path", AVAILABLE_PDKS)
def test_pdk_liberty_parsing(pdk_name, pdk_path):
    lib = parse_liberty_file(pdk_path)
    assert len(lib.cells) > 0, f"No cells found in {pdk_name}"

    classified_types = set()
    for cell in lib.cells.values():
        sym = classify_cell(cell)
        assert sym is not None
        assert isinstance(sym.gate_type, GateType)
        classified_types.add(sym.gate_type)

    # All standard PDKs must contain basic logic gates and flip-flops
    assert GateType.INV in classified_types
    assert GateType.BUF in classified_types
    assert GateType.NAND in classified_types
    assert GateType.NOR in classified_types
    assert GateType.DFF in classified_types
