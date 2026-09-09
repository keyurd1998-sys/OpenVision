#!/usr/bin/env python3
"""
Automated Yosys synthesis script for OpenVision benchmark suite.
Synthesizes 10 RTL benchmark designs and technology-maps them to SkyWater 130nm standard cells.
Outputs synthesized structural Verilog netlists to benchmarks/synth/*.v.
"""

import os
import sys
import subprocess
from pathlib import Path

BENCHMARKS = [
    ("full_adder", "full_adder"),
    ("priority_encoder_8to3", "priority_encoder_8to3"),
    ("mux4to1", "mux4to1"),
    ("alu_4bit", "alu_4bit"),
    ("dff_sync_reset", "dff_sync_reset"),
    ("up_down_counter_4bit", "up_down_counter_4bit"),
    ("shift_register_8bit", "shift_register_8bit"),
    ("fsm_traffic_light", "fsm_traffic_light"),
    ("barrel_shifter_8bit", "barrel_shifter_8bit"),
    ("fibonacci_generator", "fibonacci_generator"),
]

def find_sky130_lib() -> Path:
    """Locate the SkyWater 130nm HD Liberty file."""
    pdk_root = os.environ.get("PDK_ROOT", "/eda/SKY130_PDK")
    candidate_paths = [
        Path(pdk_root) / "sky130A/libs.ref/sky130_fd_sc_hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib",
        Path("/eda/OpenROAD-flow-scripts/flow/platforms/sky130hd/lib/sky130_fd_sc_hd__tt_025C_1v80.lib"),
    ]
    for p in candidate_paths:
        if p.is_file():
            return p
    raise FileNotFoundError(f"SkyWater 130nm Liberty file not found in candidates: {candidate_paths}")

def synthesize_design(design_name: str, top_module: str, rtl_dir: Path, synth_dir: Path, lib_path: Path) -> Path:
    """Synthesizes a single RTL benchmark into a structural Verilog netlist using Yosys."""
    rtl_file = rtl_dir / f"{design_name}.v"
    out_file = synth_dir / f"{design_name}.v"

    if not rtl_file.exists():
        raise FileNotFoundError(f"RTL file not found: {rtl_file}")

    synth_dir.mkdir(parents=True, exist_ok=True)

    yosys_script = f"""
read_verilog "{rtl_file.resolve()}"
hierarchy -check -top {top_module}
proc; opt; fsm; opt; memory; opt
techmap; opt
dfflibmap -liberty "{lib_path.resolve()}"
abc -liberty "{lib_path.resolve()}"
opt_clean -purge
clean
stat -liberty "{lib_path.resolve()}"
write_verilog -noattr "{out_file.resolve()}"
"""

    cmd = ["yosys", "-q", "-p", yosys_script]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error synthesizing {design_name}:", file=sys.stderr)
        print(result.stderr, file=sys.stderr)
        raise RuntimeError(f"Yosys synthesis failed for {design_name} (code {result.returncode})")

    if not out_file.exists() or out_file.stat().st_size == 0:
        raise RuntimeError(f"Output netlist was not generated or is empty: {out_file}")

    return out_file

def main():
    repo_root = Path(__file__).resolve().parent.parent
    rtl_dir = repo_root / "benchmarks" / "rtl"
    synth_dir = repo_root / "benchmarks" / "synth"
    lib_path = find_sky130_lib()

    print(f"[*] Sky130 Liberty: {lib_path}")
    print(f"[*] RTL Directory:  {rtl_dir}")
    print(f"[*] Synth Directory:{synth_dir}")
    print("=" * 60)

    success_count = 0
    for name, top in BENCHMARKS:
        print(f"[*] Synthesizing benchmark: {name} (top: {top})...", end=" ", flush=True)
        try:
            out_file = synthesize_design(name, top, rtl_dir, synth_dir, lib_path)
            size = out_file.stat().st_size
            print(f"SUCCESS ({size} bytes)")
            success_count += 1
        except Exception as e:
            print(f"FAILED: {e}")

    print("=" * 60)
    print(f"[*] Synthesis Complete: {success_count}/{len(BENCHMARKS)} benchmarks synthesized.")
    if success_count != len(BENCHMARKS):
        sys.exit(1)

if __name__ == "__main__":
    main()
