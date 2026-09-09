"""
Solder-dot (•) junction detector and manager for OpenVision.
Identifies all multi-fanout branching points and T-junctions in routed nets,
inserting standard circular solder-dot junction markers (•) while suppressing
them at simple 2-way corner bends and dead-ends.
"""

from typing import Dict, List, Set, Tuple
from openvision.routing.router_models import Point, WireSegment, SolderDot, SegmentOrientation


class SolderDotManager:
    """
    Analyzes wire segments for a net and detects true 3-way and 4-way T-junctions
    to place solder dots according to IEEE schematic standards.
    """

    def __init__(self, radius: float = 3.0):
        self.radius = radius

    def detect_junctions(self, segments: List[WireSegment], net_name: str) -> List[SolderDot]:
        """
        Detects all branch points where:
          1. 3 or more segments share the exact same endpoint (degree >= 3).
          2. A horizontal segment's endpoint lies strictly inside the vertical span
             of a vertical segment (T-junction on a trunk).
          3. A vertical segment's endpoint lies strictly inside the horizontal span
             of a horizontal segment.
        """
        if len(segments) < 2:
            return []

        junction_coords: Set[Tuple[float, float]] = set()

        # 1. Endpoint degree counting
        endpoint_count: Dict[Tuple[float, float], int] = {}
        for seg in segments:
            p1_key = (round(seg.p1.x, 2), round(seg.p1.y, 2))
            p2_key = (round(seg.p2.x, 2), round(seg.p2.y, 2))
            endpoint_count[p1_key] = endpoint_count.get(p1_key, 0) + 1
            endpoint_count[p2_key] = endpoint_count.get(p2_key, 0) + 1

        for coord, count in endpoint_count.items():
            if count >= 3:
                junction_coords.add(coord)

        # 2. T-junction detection: An endpoint of segment A lies on the interior of segment B
        v_segs = [s for s in segments if s.is_vertical]
        h_segs = [s for s in segments if s.is_horizontal]

        for h in h_segs:
            for p in (h.p1, h.p2):
                px, py = round(p.x, 2), round(p.y, 2)
                for v in v_segs:
                    vx = round(v.p1.x, 2)
                    if abs(px - vx) < 1e-2:
                        vy_min = round(min(v.p1.y, v.p2.y), 2)
                        vy_max = round(max(v.p1.y, v.p2.y), 2)
                        # Check if py is within or at the trunk
                        if vy_min <= py <= vy_max:
                            # If it's not a simple corner (count == 2 with endpoints matching)
                            # Check if the point divides the vertical segment or meets others
                            if vy_min < py < vy_max:
                                junction_coords.add((px, py))

        for v in v_segs:
            for p in (v.p1, v.p2):
                px, py = round(p.x, 2), round(p.y, 2)
                for h in h_segs:
                    hy = round(h.p1.y, 2)
                    if abs(py - hy) < 1e-2:
                        hx_min = round(min(h.p1.x, h.p2.x), 2)
                        hx_max = round(max(h.p1.x, h.p2.x), 2)
                        if hx_min < px < hx_max:
                            junction_coords.add((px, py))

        # Return unique sorted solder dots
        dots = [
            SolderDot(x=coord[0], y=coord[1], net_name=net_name, radius=self.radius)
            for coord in sorted(junction_coords)
        ]
        return dots
