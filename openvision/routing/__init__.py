"""
OpenVision Orthogonal Routing Subsystem.
Implements Stage 3 Manhattan Orthogonal Auto-Routing with solder-dot junctions
and High-Fanout Net (HFN) decoupling.
"""

from openvision.routing.router_models import (
    Point,
    SegmentOrientation,
    PinExitDirection,
    WireSegment,
    SolderDot,
    PinLocation,
    HFNStub,
    NetRoute,
    RoutingResult,
)
from openvision.routing.pin_resolver import PinResolver
from openvision.routing.hfn_decoupler import HighFanoutDecoupler
from openvision.routing.solder_dots import SolderDotManager
from openvision.routing.orthogonal_router import OrthogonalRouter
from openvision.routing.routing_engine import route_placement

__all__ = [
    "Point",
    "SegmentOrientation",
    "PinExitDirection",
    "WireSegment",
    "SolderDot",
    "PinLocation",
    "HFNStub",
    "NetRoute",
    "RoutingResult",
    "PinResolver",
    "HighFanoutDecoupler",
    "SolderDotManager",
    "OrthogonalRouter",
    "route_placement",
]
