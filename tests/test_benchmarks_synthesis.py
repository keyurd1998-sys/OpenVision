"""
Integration tests for the 10 RTL benchmark designs and their Sky130 synthesized netlists.
"""

import pytest
from pathlib import Path
from openvision.ingestion.liberty_parser import parse_liberty_file
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
    assert len(mod.instances) > 0, f"Module {top} has no instances"
    assert len(mod.ports) > 0, f"Module {top} has no ports"

    summary = mod.get_summary()
    assert summary["total_instances"] == len(mod.instances)
    assert summary["total_nets"] > 0
