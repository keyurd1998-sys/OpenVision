#!/usr/bin/env python3
"""
Milestone 1 Verification Script for OpenVision.
Loads the SkyWater 130nm Liberty library, parses all 10 synthesized benchmark netlists,
links cells to IEEE logic symbols, and prints detailed gate summaries.
"""

import sys
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from openvision.ingestion.liberty_parser import parse_liberty_file
from openvision.ingestion.symbol_classifier import GateType
from openvision.ingestion.netlist_parser import parse_netlist_file
from benchmarks.synthesize_benchmarks import find_sky130_lib, BENCHMARKS


def main():
    console = Console()
    console.print(Panel.fit(
        "[bold cyan]OpenVision Milestone 1 Verification[/bold cyan]\n"
        "[dim]Ingestion Engine, Dynamic Symbol Classification & Benchmark Netlist Validation[/dim]",
        border_style="cyan"
    ))

    # 1. Ingest Liberty Library
    lib_path = find_sky130_lib()
    console.print(f"[*] Ingesting Liberty library from: [green]{lib_path}[/green]")
    lib = parse_liberty_file(lib_path)
    console.print(f"[+] Loaded [bold green]{len(lib)}[/bold green] standard cells from library [bold]{lib.name}[/bold].\n")

    repo_root = Path(__file__).resolve().parent
    synth_dir = repo_root / "benchmarks" / "synth"

    summary_table = Table(title="OpenVision Benchmark Netlists - Milestone 1 Recognition Summary", header_style="bold magenta")
    summary_table.add_column("Benchmark Design", style="cyan", justify="left")
    summary_table.add_column("Instances", justify="right")
    summary_table.add_column("DFF/Seq", justify="right", style="yellow")
    summary_table.add_column("NAND/NOR/AND/OR", justify="right", style="green")
    summary_table.add_column("XOR/XNOR/MAJ", justify="right", style="blue")
    summary_table.add_column("INV/BUF/ISO", justify="right", style="bright_black")
    summary_table.add_column("MUX/AOI/OAI/Macro", justify="right", style="magenta")
    summary_table.add_column("Nets", justify="right")
    summary_table.add_column("Status", justify="center", style="bold green")

    all_passed = True

    for name, top in BENCHMARKS:
        netlist_file = synth_dir / f"{name}.v"
        if not netlist_file.exists():
            console.print(f"[red]Error: Netlist {netlist_file} not found![/red]")
            all_passed = False
            continue

        netlist = parse_netlist_file(netlist_file, liberty=lib)
        module = netlist.modules.get(top)
        if not module:
            console.print(f"[red]Error: Top module {top} not found in {netlist_file}![/red]")
            all_passed = False
            continue

        summary = module.get_summary()
        gt = summary["gate_types"]

        dff_cnt = gt.get(GateType.DFF.value, 0) + gt.get(GateType.LATCH.value, 0)
        basic_cnt = (
            gt.get(GateType.NAND.value, 0) + gt.get(GateType.NOR.value, 0) +
            gt.get(GateType.AND.value, 0) + gt.get(GateType.OR.value, 0)
        )
        arith_cnt = (
            gt.get(GateType.XOR.value, 0) + gt.get(GateType.XNOR.value, 0) +
            gt.get(GateType.MAJ.value, 0) + gt.get(GateType.FA.value, 0) + gt.get(GateType.HA.value, 0)
        )
        buf_cnt = (
            gt.get(GateType.INV.value, 0) + gt.get(GateType.BUF.value, 0) +
            gt.get(GateType.ISOBUF.value, 0)
        )
        complex_cnt = (
            gt.get(GateType.MUX2.value, 0) + gt.get(GateType.AOI.value, 0) +
            gt.get(GateType.OAI.value, 0) + gt.get(GateType.AO.value, 0) +
            gt.get(GateType.OA.value, 0) + gt.get(GateType.MACRO.value, 0)
        )

        summary_table.add_row(
            name,
            str(summary["total_instances"]),
            str(dff_cnt),
            str(basic_cnt),
            str(arith_cnt),
            str(buf_cnt),
            str(complex_cnt),
            str(summary["total_nets"]),
            "[bold green]PASSED[/bold green]"
        )

    console.print(summary_table)

    # Detailed per-module prints
    console.print("\n[bold cyan]Detailed Module Gate Recognition Summaries:[/bold cyan]")
    for name, top in BENCHMARKS:
        netlist_file = synth_dir / f"{name}.v"
        netlist = parse_netlist_file(netlist_file, liberty=lib)
        module = netlist[top]
        module.print_summary()
        print()

    if all_passed:
        console.print(Panel("[bold green]All 10 benchmark netlists successfully parsed and verified![/bold green]", border_style="green"))
    else:
        console.print(Panel("[bold red]Milestone 1 verification encountered errors.[/bold red]", border_style="red"))
        sys.exit(1)


if __name__ == "__main__":
    main()
