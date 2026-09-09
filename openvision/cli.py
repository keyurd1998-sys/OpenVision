"""
Command-line interface for OpenVision.
"""

import sys
import argparse
from pathlib import Path
from rich.console import Console

from openvision import __version__
from openvision.ingestion.liberty_parser import parse_liberty_file, find_default_liberty
from openvision.ingestion.netlist_parser import parse_netlist_file


def main():
    parser = argparse.ArgumentParser(
        prog="openvision",
        description="OpenVision: Universal Schematic Viewer for Technology-Mapped Netlists",
    )
    parser.add_argument(
        "netlist",
        type=str,
        nargs="?",
        help="Path to structural Verilog netlist (.v)",
    )
    parser.add_argument(
        "--liberty", "-l",
        type=str,
        default=None,
        help="Path to PDK Liberty library file (.lib). Defaults to Sky130 PDK if found.",
    )
    parser.add_argument(
        "--summary", "-s",
        action="store_true",
        help="Print text summary of recognized gate types and connectivity statistics.",
    )
    parser.add_argument(
        "--version", "-v",
        action="version",
        version=f"OpenVision v{__version__}",
    )

    args = parser.parse_args()
    console = Console()

    if not args.netlist:
        parser.print_help()
        sys.exit(0)

    netlist_path = Path(args.netlist)
    if not netlist_path.is_file():
        console.print(f"[red]Error: Netlist file not found: {netlist_path}[/red]")
        sys.exit(1)

    lib = None
    if args.liberty:
        lib_path = Path(args.liberty)
        if lib_path.is_file():
            lib = parse_liberty_file(lib_path)
        else:
            console.print(f"[yellow]Warning: Specified Liberty file not found: {lib_path}[/yellow]")
    else:
        try:
            default_lib_path = find_default_liberty()
            lib = parse_liberty_file(default_lib_path)
        except Exception:
            pass

    netlist = parse_netlist_file(netlist_path, liberty=lib)

    top_mod = netlist.top_module
    if not top_mod:
        console.print(f"[red]Error: No modules found in {netlist_path}[/red]")
        sys.exit(1)

    top_mod.print_summary()


if __name__ == "__main__":
    main()
