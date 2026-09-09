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
        "--place", "-p",
        action="store_true",
        help="Execute Sugiyama layered placement and report placement layout statistics.",
    )
    parser.add_argument(
        "--route", "-r",
        action="store_true",
        help="Execute Manhattan orthogonal auto-routing with solder dots and HFN decoupling.",
    )
    parser.add_argument(
        "--gui", "-g",
        action="store_true",
        help="Launch interactive PyQt6 vector schematic viewer window.",
    )
    parser.add_argument(
        "--export-image", "-o",
        type=str,
        default=None,
        help="Export rendered schematic to high-resolution PNG image on disk.",
    )
    parser.add_argument(
        "--hfn-threshold",
        type=int,
        default=20,
        help="Fanout threshold for decoupling high-fanout nets (default: 20).",
    )
    parser.add_argument(
        "--fanin",
        type=str,
        default=None,
        help="Trace backward fanin logic cone driving the specified instance, port, or net.",
    )
    parser.add_argument(
        "--fanout",
        type=str,
        default=None,
        help="Trace forward fanout logic cone driven by the specified instance, port, or net.",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=None,
        help="Maximum logic depth for cone tracing (default: unbounded, stops at registers/ports).",
    )
    parser.add_argument(
        "--export-cone",
        type=str,
        default=None,
        help="Export isolated logic cone sub-schematic to PNG image.",
    )
    parser.add_argument(
        "--export-box",
        type=str,
        default=None,
        help="Export top-level module box with IO pins to high-resolution PNG image on disk.",
    )
    parser.add_argument(
        "--expanded",
        action="store_true",
        help="Start GUI viewer with hierarchy already expanded into gate-level schematic.",
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

    placement_res = None
    routing_res = None

    if args.place or args.route or args.export_image or args.gui:
        from openvision.placement import run_placement
        console.print("\n[bold cyan]Running Sugiyama Placement Engine...[/bold cyan]")
        placement_res = run_placement(top_mod)
        placement_res.print_summary()

    if args.route or args.export_image or args.gui:
        from openvision.routing import route_placement
        console.print("\n[bold cyan]Running Manhattan Orthogonal Auto-Router...[/bold cyan]")
        routing_res = route_placement(placement_res, hfn_threshold=args.hfn_threshold)
        routing_res.print_summary()

    if args.export_image:
        import os
        from PyQt6 import QtWidgets
        from openvision.gui import SchematicCanvas, export_scene_to_image

        if "DISPLAY" not in os.environ and "QT_QPA_PLATFORM" not in os.environ:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        canvas = SchematicCanvas()
        canvas.load_schematic(placement_res, routing_res)
        out_path = export_scene_to_image(canvas._scene, args.export_image)
        console.print(f"\n[bold green][SUCCESS] Exported schematic image to:[/bold green] {out_path}")

    active_cone = None
    if args.fanin or args.fanout:
        from openvision.cone import ConeTracer
        tracer = ConeTracer(top_mod)
        if args.fanin:
            console.print(f"\n[bold cyan]Tracing Fanin Cone for: {args.fanin}...[/bold cyan]")
            active_cone = tracer.trace_fanin(args.fanin, depth=args.depth)
            active_cone.print_summary()
        elif args.fanout:
            console.print(f"\n[bold cyan]Tracing Fanout Cone for: {args.fanout}...[/bold cyan]")
            active_cone = tracer.trace_fanout(args.fanout, depth=args.depth)
            active_cone.print_summary()

    if args.export_cone:
        if not active_cone:
            console.print("[red]Error: --export-cone requires either --fanin or --fanout to be specified.[/red]")
            sys.exit(1)
        import os
        from PyQt6 import QtWidgets
        from openvision.placement import run_placement
        from openvision.routing import route_placement
        from openvision.gui import SchematicCanvas, export_scene_to_image

        if "DISPLAY" not in os.environ and "QT_QPA_PLATFORM" not in os.environ:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

        console.print(f"\n[bold cyan]Extracting isolated cone sub-module ({len(active_cone.instances)} gates)...[/bold cyan]")
        cone_mod = active_cone.extract_submodule(top_mod)
        cone_place = run_placement(cone_mod)
        cone_route = route_placement(cone_place)

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        canvas = SchematicCanvas()
        canvas.load_schematic(cone_place, cone_route)
        out_path = export_scene_to_image(canvas._scene, args.export_cone)
        console.print(f"\n[bold green][SUCCESS] Exported isolated cone schematic to:[/bold green] {out_path}")

    if args.export_box:
        import os
        from PyQt6 import QtWidgets
        from openvision.gui import SchematicCanvas, export_scene_to_image

        if "DISPLAY" not in os.environ and "QT_QPA_PLATFORM" not in os.environ:
            os.environ["QT_QPA_PLATFORM"] = "offscreen"

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
        canvas = SchematicCanvas()
        canvas.load_module_box(top_mod)
        out_path = export_scene_to_image(canvas._scene, args.export_box)
        console.print(f"\n[bold green][SUCCESS] Exported module box image to:[/bold green] {out_path}")

    if args.gui:
        from PyQt6 import QtWidgets
        from openvision.gui import SchematicWindow

        app = QtWidgets.QApplication.instance() or QtWidgets.QApplication(sys.argv)
        win = SchematicWindow()
        win.display_design(top_mod, placement_res, routing_res, start_expanded=args.expanded)
        if args.fanin:
            win.expand_hierarchy()
            win.trace_node_fanin(args.fanin, depth=args.depth)
        elif args.fanout:
            win.expand_hierarchy()
            win.trace_node_fanout(args.fanout, depth=args.depth)
        win.show()
        sys.exit(app.exec())


if __name__ == "__main__":
    main()
