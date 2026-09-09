"""
Routing engine orchestrator for OpenVision.
Provides the top-level API to route a placed netlist using the Manhattan Orthogonal Auto-Router.
"""

from openvision.placement.placement_engine import PlacementResult
from openvision.routing.router_models import RoutingResult, WireSegment, SolderDot, HFNStub, NetRoute
from openvision.routing.orthogonal_router import OrthogonalRouter


def route_placement(
    placement: PlacementResult,
    hfn_threshold: int = 20,
    decouple_globals: bool = True,
    track_pitch: float = 8.0,
    channel_margin: float = 12.0,
    top_corridor_y: float = 25.0,
) -> RoutingResult:
    """
    Executes the full Stage 3 Manhattan Orthogonal Routing pipeline:
      1. Pin coordinate and perpendicular orientation resolution
      2. High-Fanout Net (HFN) detection and local stub decoupling
      3. Channel track allocation via Left-Edge interval packing
      4. 100% strictly orthogonal (90° bends only) segment generation
      5. Solder-dot (•) junction insertion for fanout > 1
    """
    router = OrthogonalRouter(
        placement=placement,
        hfn_threshold=hfn_threshold,
        decouple_globals=decouple_globals,
        track_pitch=track_pitch,
        channel_margin=channel_margin,
        top_corridor_y=top_corridor_y,
    )

    return router.route_all_nets()
