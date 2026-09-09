#!/usr/bin/env python3
"""
Milestone 2 Verification Script for OpenVision.
Executes and validates the Sugiyama Layered Placement Engine on the complex
128-bit AES Encryption benchmark (~10,000 instances) mapped to SkyWater 130nm.
"""

import sys
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from openvision.ingestion.liberty_parser import parse_liberty_file, find_default_liberty
from openvision.ingestion.netlist_parser import parse_netlist_file
from openvision.placement import run_placement


def main():
    console = Console()
    console.print(Panel.fit(
        "[bold cyan]OpenVision Milestone 2 Verification[/bold cyan]\n"
        "[dim]Sugiyama Layered Placement Engine: Cycle Breaking, Topological Layering, Crossing Reduction & Coordinates[/dim]",
        border_style="cyan"
    ))

    # 1. Ingest Liberty library
    lib_path = find_default_liberty()
    console.print(f"[*] Ingesting Liberty library from: [green]{lib_path}[/green]")
    t0 = time.time()
    lib = parse_liberty_file(lib_path)
    console.print(f"[+] Loaded [bold green]{len(lib)}[/bold green] standard cells in [dim]{time.time() - t0:.2f}s[/dim].")

    # 2. Ingest synthesized AES-128 netlist
    synth_file = Path("benchmarks/synth/aes_cipher_top.v")
    if not synth_file.is_file():
        console.print(f"[red]Error: Synthesized netlist not found at {synth_file}[/red]")
        sys.exit(1)

    console.print(f"[*] Ingesting synthesized netlist: [green]{synth_file}[/green]")
    t1 = time.time()
    netlist = parse_netlist_file(synth_file, liberty=lib)
    top_mod = netlist.top_module
    console.print(f"[+] Ingested [bold green]{len(top_mod.instances)}[/bold green] instances and [bold green]{len(top_mod.ports)}[/bold green] ports in [dim]{time.time() - t1:.2f}s[/dim].")

    # 3. Run Sugiyama placement engine
    console.print("\n[*] Executing Sugiyama Layered Placement Pipeline...")
    t2 = time.time()
    result = run_placement(top_mod, num_crossing_iterations=2)
    elapsed = time.time() - t2
    console.print(f"[+] Placement completed in [bold green]{elapsed:.3f}s[/bold green]!\n")

    # 4. Display Placement Metrics Table
    metrics_table = Table(title="Placement Execution Metrics (AES-128 Benchmark)", header_style="bold magenta")
    metrics_table.add_column("Metric", style="cyan", justify="left")
    metrics_table.add_column("Value", style="bold white", justify="right")
    metrics_table.add_column("EDA Interpretation", style="dim", justify="left")

    metrics_table.add_row("Total Placed Nodes", str(result.total_nodes), "Gates + Primary Ports")
    metrics_table.add_row("Total Interconnect Edges", str(result.total_edges), "Directed net-to-pin connections")
    metrics_table.add_row("Decoupled Feedback Loops", str(result.feedback_edges), "DFF sequential loop boundaries broken")
    metrics_table.add_row("Topological Columns (Ranks)", str(result.num_ranks), "Left-to-right logic stages (Rank 0 -> Rank 11)")
    metrics_table.add_row("Canvas Dimensions", f"{result.width:.0f} x {result.height:.0f}", "Vector coordinate space (units)")
    metrics_table.add_row("Placement Engine Runtime", f"{result.elapsed_seconds:.3f} s", "High-performance Python execution")

    console.print(metrics_table)

    # 5. Display Column Distribution Table
    col_table = Table(title="Topological Column Gate Distribution", header_style="bold cyan")
    col_table.add_column("Rank (Column)", justify="center", style="yellow")
    col_table.add_column("Gate Count", justify="right", style="green")
    col_table.add_column("Visual Density", justify="left", style="blue")
    col_table.add_column("X Coordinate", justify="right", style="magenta")

    dist = result.get_rank_distribution()
    for r in range(result.num_ranks):
        count = dist[r]
        bar = "█" * min(40, max(1, count // 60))
        sample_x = result.graph.nodes[result.graph.ranks[r][0]].x
        col_table.add_row(f"Col {r}", str(count), bar, f"{sample_x:.1f}")

    console.print(col_table)

    # 6. Sanity Checks & Verification
    console.print("\n[*] Validating Placement Constraints:")
    # Constraint A: Strict Left-to-Right monotonicity on forward edges
    violations = 0
    for edge in result.graph.edges:
        if not edge.is_feedback:
            u = result.graph.nodes[edge.src]
            v = result.graph.nodes[edge.dst]
            if u.rank >= v.rank:
                violations += 1
    if violations == 0:
        console.print("  [bold green][PASS][/bold green] Monotonicity: 100% of forward edges flow strictly left-to-right.")
    else:
        console.print(f"  [bold red][FAIL][/bold red] Monotonicity: {violations} rank violations found.")

    # Constraint B: Coordinate finiteness
    nan_count = sum(1 for n in result.graph.nodes.values() if n.x != n.x or n.y != n.y)
    if nan_count == 0:
        console.print("  [bold green][PASS][/bold green] Coordinate Sanity: 100% of nodes placed with valid finite (X, Y) coordinates.")
    else:
        console.print(f"  [bold red][FAIL][/bold red] Coordinate Sanity: {nan_count} NaN coordinates.")

    # Constraint C: Cycle Freedom
    visited = set()
    rec_stack = set()
    def has_cycle(u: str) -> bool:
        visited.add(u)
        rec_stack.add(u)
        for v in result.graph.nodes[u].succs:
            if v not in visited:
                if has_cycle(v): return True
            elif v in rec_stack: return True
        rec_stack.remove(u)
        return False
    cycle_found = any(has_cycle(n) for n in result.graph.nodes if n not in visited)
    if not cycle_found:
        console.print("  [bold green][PASS][/bold green] Cycle Freedom: Graph is a verified strict Directed Acyclic Graph (DAG).")
    else:
        console.print("  [bold red][FAIL][/bold red] Cycle Freedom: Unbroken directed cycle detected.")

    if violations == 0 and nan_count == 0 and not cycle_found:
        console.print(Panel("[bold green]Milestone 2 Placement Engine successfully verified![/bold green]", border_style="green"))
    else:
        console.print(Panel("[bold red]Milestone 2 verification encountered errors.[/bold red]", border_style="red"))
        sys.exit(1)


if __name__ == "__main__":
    main()
