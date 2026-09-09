"""
Integration tests for the complex RTL benchmark design (~10,000 instances) and Sky130 synthesis.
"""

import pytest
from pathlib import Path
from openvision.ingestion.liberty_parser import parse_liberty_file
from openvision.ingestion.symbol_classifier import GateType
from openvision.ingestion.netlist_parser import parse_netlist_file
from benchmarks.synthesize_benchmarks import find_sky130_lib, BENCHMARKS


@pytest.fixture(scope="module")
def sky130_lib():
    lib_path = find_sky130_lib()
    return parse_liberty_file(lib_path)


@pytest.mark.parametrize("name,top", BENCHMARKS)
def test_benchmark_rtl_exists(name, top):
    rtl_path = Path("benchmarks/rtl") / f"{name}.v"
    assert rtl_path.is_file(), f"RTL benchmark missing: {rtl_path}"
    assert rtl_path.stat().st_size > 0


@pytest.mark.parametrize("name,top", BENCHMARKS)
def test_benchmark_synth_netlist_valid(sky130_lib, name, top):
    synth_path = Path("benchmarks/synth") / f"{name}.v"
    assert synth_path.is_file(), f"Synthesized netlist missing: {synth_path}"
    assert synth_path.stat().st_size > 0

    netlist = parse_netlist_file(synth_path, liberty=sky130_lib)
    assert top in netlist.modules, f"Module {top} not found in {synth_path}"

    mod = netlist[top]
    inst_count = len(mod.instances)
    assert inst_count > 0, f"Module {top} has no instances"
    assert len(mod.ports) > 0, f"Module {top} has no ports"

    # Verify hierarchical structure is preserved (unflattened netlist)
    assert len(netlist.modules) > 1, f"Expected hierarchical netlist with multiple modules, got {len(netlist.modules)}"
    assert inst_count == 3, f"Expected 3 hierarchical submodules in {top}, got {inst_count}"

    # Verify submodules exist and total instance count across hierarchy
    total_insts = sum(len(m.instances) for m in netlist.modules.values())
    assert total_insts > 2000, f"Expected >2000 instances across hierarchy, got {total_insts}"

    # Verify submodules are mapped to Sky130 standard cells
    sbox = netlist["aes_sbox_lut"]
    assert len(sbox.instances) > 300
    sbox_summary = sbox.get_summary()
    assert sbox_summary["combinational_instances"] > 300

    # Verify controller has DFFs
    ctrl = netlist["aes_controller"]
    ctrl_summary = ctrl.get_summary()
    assert GateType.DFF.value in ctrl_summary["gate_types"]

    # Collect gate types across all modules
    all_gate_types = set()
    for m in netlist.modules.values():
        all_gate_types.update(m.get_summary()["gate_types"].keys())

    assert GateType.DFF.value in all_gate_types
    assert GateType.NAND.value in all_gate_types
    assert GateType.NOR.value in all_gate_types
    assert GateType.XOR.value in all_gate_types
    assert GateType.XNOR.value in all_gate_types
    assert GateType.OAI.value in all_gate_types
    assert GateType.AOI.value in all_gate_types
