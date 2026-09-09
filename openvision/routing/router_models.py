"""
Data models and geometric primitives for the OpenVision Manhattan Orthogonal Router.
Defines points, strictly horizontal/vertical wire segments, solder-dot junctions,
pin locations, high-fanout net (HFN) stubs, and net routing collections.
"""

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Dict, List, Optional, Tuple, Any, Set


class SegmentOrientation(Enum):
    """Orientation of a Manhattan orthogonal wire segment."""
    HORIZONTAL = "HORIZONTAL"
    VERTICAL = "VERTICAL"


class PinExitDirection(Enum):
    """Exit or entry direction for gate and port pins."""
    EAST = "EAST"    # Standard outputs emerge heading East (+X)
    WEST = "WEST"    # Standard inputs enter from the West (-X)
    SOUTH = "SOUTH"  # Clocks / Resets enter from the South (+Y in screen coords)
    NORTH = "NORTH"  # Presets or top inputs enter from the North (-Y in screen coords)


@dataclass(frozen=True)
class Point:
    """2D coordinate point on the schematic canvas."""
    x: float
    y: float

    def __repr__(self) -> str:
        return f"({self.x:.1f}, {self.y:.1f})"

    @property
    def tuple(self) -> Tuple[float, float]:
        return (self.x, self.y)


@dataclass
class WireSegment:
    """
    Represents a strictly orthogonal (90°) wire segment on the schematic canvas.
    Must be either purely HORIZONTAL (y1 == y2) or purely VERTICAL (x1 == x2).
    """
    p1: Point
    p2: Point
    net_name: str
    orientation: SegmentOrientation
    is_stub: bool = False
    track_id: Optional[int] = None

    def __post_init__(self):
        # Guarantee strict orthogonality
        dx = abs(self.p1.x - self.p2.x)
        dy = abs(self.p1.y - self.p2.y)
        if dx > 1e-4 and dy > 1e-4:
            raise ValueError(
                f"Non-orthogonal wire segment created for net '{self.net_name}': "
                f"p1=({self.p1.x}, {self.p1.y}) to p2=({self.p2.x}, {self.p2.y})"
            )

    @property
    def length(self) -> float:
        return abs(self.p2.x - self.p1.x) + abs(self.p2.y - self.p1.y)

    @property
    def is_horizontal(self) -> bool:
        return self.orientation == SegmentOrientation.HORIZONTAL

    @property
    def is_vertical(self) -> bool:
        return self.orientation == SegmentOrientation.VERTICAL

    @property
    def min_x(self) -> float:
        return min(self.p1.x, self.p2.x)

    @property
    def max_x(self) -> float:
        return max(self.p1.x, self.p2.x)

    @property
    def min_y(self) -> float:
        return min(self.p1.y, self.p2.y)

    @property
    def max_y(self) -> float:
        return max(self.p1.y, self.p2.y)


@dataclass
class SolderDot:
    """
    Represents a circular solder dot (•) placed at a 3-way or 4-way wire junction
    where a multi-fanout branch tees into a trunk line.
    """
    x: float
    y: float
    net_name: str
    radius: float = 3.0

    @property
    def point(self) -> Point:
        return Point(self.x, self.y)

    @property
    def coord(self) -> Tuple[float, float]:
        return (round(self.x, 2), round(self.y, 2))


@dataclass
class PinLocation:
    """
    Exact geometric location and orientation of a pin on a placed schematic node.
    """
    node_id: str
    pin_name: str
    x: float
    y: float
    direction: PinExitDirection
    is_inverted: bool = False
    role: Optional[Any] = None

    @property
    def point(self) -> Point:
        return Point(self.x, self.y)


@dataclass
class HFNStub:
    """
    Represents a decoupled High-Fanout Net (HFN) local stub at a pin,
    displaying a net label and directional indicator instead of a global wire.
    """
    net_name: str
    pin_loc: PinLocation
    start: Point
    end: Point
    label: str
    is_driver: bool
    arrow_direction: str  # "RIGHT", "LEFT", "UP", "DOWN"


@dataclass
class NetRoute:
    """Complete routed geometry for a single net."""
    net_name: str
    segments: List[WireSegment] = field(default_factory=list)
    solder_dots: List[SolderDot] = field(default_factory=list)
    is_decoupled_hfn: bool = False
    hfn_stubs: List[HFNStub] = field(default_factory=list)
    driver_pin: Optional[PinLocation] = None
    sink_pins: List[PinLocation] = field(default_factory=list)

    @property
    def total_wire_length(self) -> float:
        return sum(seg.length for seg in self.segments)

    @property
    def fanout(self) -> int:
        return len(self.sink_pins)

    @property
    def num_bends(self) -> int:
        """Counts the number of 90-degree bends in this net's route."""
        bends = 0
        for i in range(len(self.segments)):
            for j in range(i + 1, len(self.segments)):
                s1 = self.segments[i]
                s2 = self.segments[j]
                if s1.orientation != s2.orientation:
                    # Check if they share an endpoint
                    pts1 = {(round(s1.p1.x, 2), round(s1.p1.y, 2)), (round(s1.p2.x, 2), round(s1.p2.y, 2))}
                    pts2 = {(round(s2.p1.x, 2), round(s2.p1.y, 2)), (round(s2.p2.x, 2), round(s2.p2.y, 2))}
                    if pts1 & pts2:
                        bends += 1
        return bends


@dataclass
class RoutingResult:
    """Summary of all routed nets and routing metrics."""
    module_name: str
    net_routes: Dict[str, NetRoute]
    total_segments: int
    total_solder_dots: int
    total_bends: int
    decoupled_hfn_count: int
    regular_routed_count: int
    is_strictly_orthogonal: bool
    bbox: Tuple[float, float, float, float]
    elapsed_seconds: float = 0.0

    def all_segments(self) -> List[WireSegment]:
        """Returns a flat list of all wire segments across all routes."""
        segs: List[WireSegment] = []
        for r in self.net_routes.values():
            segs.extend(r.segments)
        return segs

    def all_solder_dots(self) -> List[SolderDot]:
        """Returns a flat list of all solder dots across all routes."""
        dots: List[SolderDot] = []
        for r in self.net_routes.values():
            dots.extend(r.solder_dots)
        return dots

    def all_stubs(self) -> List[HFNStub]:
        """Returns a flat list of all HFN stubs across all routes."""
        stubs: List[HFNStub] = []
        for r in self.net_routes.values():
            stubs.extend(r.hfn_stubs)
        return stubs

    def verify_orthogonality(self) -> bool:
        """Verifies that 100% of all wire segments are strictly horizontal or vertical."""
        for seg in self.all_segments():
            dx = abs(seg.p1.x - seg.p2.x)
            dy = abs(seg.p1.y - seg.p2.y)
            if dx > 1e-4 and dy > 1e-4:
                return False
        return True

    def print_summary(self) -> None:
        """Prints a clean, formatted routing report."""
        print("=" * 65)
        print(f" Orthogonal Routing Summary: {self.module_name}")
        print("=" * 65)
        print(f" Total Routed Nets:        {len(self.net_routes):,}")
        print(f"   Decoupled HFNs:         {self.decoupled_hfn_count:,} nets")
        print(f"   Regular Channel Nets:   {self.regular_routed_count:,} nets")
        print(f" Total Wire Segments:      {self.total_segments:,}")
        print(f" Total Solder Dots (•):    {self.total_solder_dots:,}")
        print(f" Total 90° Wire Bends:     {self.total_bends:,}")
        ortho_str = "100% STRICTLY ORTHOGONAL (Zero Diagonal Wires)" if self.is_strictly_orthogonal else "WARNING: Non-orthogonal wires detected!"
        print(f" Orthogonality Check:      {ortho_str}")
        print(f" Routing Runtime:          {self.elapsed_seconds:.3f} s")
        print("=" * 65)
