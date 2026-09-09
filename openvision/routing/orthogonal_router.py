"""
Manhattan Orthogonal Auto-Router for OpenVision.
Generates 100% horizontal and vertical wire segments (90° bends only),
assigns non-overlapping channel tracks using the Left-Edge algorithm,
inserts standard IEEE solder dots (•) at multi-fanout junctions,
and supports multi-rank bridges and feedback perimeter routing.
"""

import heapq
import time
from collections import defaultdict
from typing import Dict, List, Optional, Set, Tuple

from openvision.placement.placement_engine import PlacementResult
from openvision.placement.cycle_breaker import PlacementGraph, PlacementNode
from openvision.routing.router_models import (
    Point,
    WireSegment,
    SegmentOrientation,
    PinLocation,
    PinExitDirection,
    SolderDot,
    NetRoute,
    RoutingResult,
)
from openvision.routing.pin_resolver import PinResolver
from openvision.routing.hfn_decoupler import HighFanoutDecoupler
from openvision.routing.solder_dots import SolderDotManager


class OrthogonalRouter:
    """
    High-performance Manhattan Orthogonal Router for technology-mapped schematics.
    Routes nets using strictly 90-degree horizontal and vertical wire segments.
    """

    def __init__(
        self,
        placement: PlacementResult,
        hfn_threshold: int = 20,
        decouple_globals: bool = True,
        track_pitch: float = 8.0,
        channel_margin: float = 12.0,
        top_corridor_y: float = 25.0,
    ):
        self.placement = placement
        self.graph = placement.graph
        self.hfn_threshold = hfn_threshold
        self.decouple_globals = decouple_globals
        self.track_pitch = track_pitch
        self.channel_margin = channel_margin
        self.top_corridor_y = top_corridor_y

        self.pin_resolver = PinResolver(self.graph)
        self.decoupler = HighFanoutDecoupler(
            hfn_threshold=hfn_threshold,
            decouple_globals=decouple_globals,
        )
        self.solder_manager = SolderDotManager(radius=3.0)

        self._channel_x_bounds: Dict[int, Tuple[float, float]] = {}
        self._channel_track_alloc: Dict[int, Dict[str, int]] = defaultdict(dict)
        self._channel_track_count: Dict[int, int] = defaultdict(int)

        self._compute_channel_bounds()

    def _compute_channel_bounds(self) -> None:
        """Calculates the physical X boundaries for each vertical routing channel and perimeter corridors."""
        num_ranks = len(self.graph.ranks)
        for r in range(num_ranks - 1):
            curr_nodes = [self.graph.nodes[nid] for nid in self.graph.ranks[r]]
            next_nodes = [self.graph.nodes[nid] for nid in self.graph.ranks[r + 1]]

            x_right_curr = max(n.x + n.width for n in curr_nodes) if curr_nodes else 50.0
            x_left_next = min(n.x for n in next_nodes) if next_nodes else x_right_curr + 120.0

            self._channel_x_bounds[r] = (x_right_curr, x_left_next)

        # Circuit bounding box & perimeter routing corridors
        if self.graph.nodes:
            self._min_x = min(n.x for n in self.graph.nodes.values())
            self._max_x = max(n.x + n.width for n in self.graph.nodes.values())
            self._min_y = min(n.y for n in self.graph.nodes.values())
            self._max_y = max(n.y + n.height for n in self.graph.nodes.values())
        else:
            self._min_x, self._max_x, self._min_y, self._max_y = 50.0, 500.0, 50.0, 500.0

        self._left_perimeter_x = self._min_x - 30.0
        self._right_perimeter_x = self._max_x + 30.0
        self._top_corridor_base = min(self.top_corridor_y, self._min_y - 30.0)
        self._bottom_corridor_base = self._max_y + 30.0
        self._corridor_offset = 0.0

    def _check_horizontal_collision(self, x1: float, x2: float, y: float, margin: float = 4.0) -> bool:
        """Checks if a horizontal wire segment between x1 and x2 at y intersects any placed node."""
        xa, xb = min(x1, x2), max(x1, x2)
        for node in self.graph.nodes.values():
            if node.y - margin <= y <= node.y + node.height + margin:
                if max(xa, node.x) < min(xb, node.x + node.width) - 1.0:
                    return True
        return False

    def _get_channel_track_x(self, channel_idx: int, track_id: int) -> float:
        """Computes the exact X coordinate for a track index within a channel."""
        num_ranks = len(self.graph.ranks)
        c = max(0, min(channel_idx, num_ranks - 2))

        x_start, x_end = self._channel_x_bounds[c]
        trunk_start = x_start + self.channel_margin
        trunk_end = x_end - self.channel_margin
        avail_width = max(10.0, trunk_end - trunk_start)

        total_tracks = max(1, self._channel_track_count.get(c, 1))
        if total_tracks <= 1:
            return (trunk_start + trunk_end) / 2.0

        pitch = min(self.track_pitch, avail_width / max(1, total_tracks - 1))
        return trunk_start + (track_id % total_tracks) * pitch

    def route_all_nets(self) -> RoutingResult:
        """
        Executes the complete orthogonal routing pipeline across all nets:
          1. Groups connections into nets with drivers and sinks.
          2. Decouples High-Fanout Nets (clocks, resets, enables).
          3. Allocates non-overlapping tracks per channel using Left-Edge heuristic.
          4. Generates strictly Manhattan 90° wire segments.
          5. Detects 3-way/4-way junctions and inserts solder dots (•).
        """
        t0 = time.time()

        # Step 1: Group placement edges into distinct nets
        net_drivers: Dict[str, Tuple[str, str]] = {}
        net_sinks: Dict[str, List[Tuple[str, str, bool]]] = defaultdict(list)

        for edge in self.graph.edges:
            if edge.net_name not in net_drivers:
                net_drivers[edge.net_name] = (edge.src, edge.src_pin)
            net_sinks[edge.net_name].append((edge.dst, edge.dst_pin, edge.is_feedback))

        # Step 2: Identify HFNs and collect non-HFN intervals per channel for track allocation
        net_routes: Dict[str, NetRoute] = {}
        decoupled_count = 0
        regular_nets: Dict[str, Tuple[Optional[PinLocation], List[PinLocation]]] = {}
        channel_intervals: Dict[int, List[Tuple[float, float, str]]] = defaultdict(list)

        num_ranks = len(self.graph.ranks)

        for net_name, (src_node, src_pin) in net_drivers.items():
            sinks = net_sinks[net_name]
            p_src = self.pin_resolver.get_pin(src_node, src_pin)
            p_dsts = [self.pin_resolver.get_pin(dst, pin) for dst, pin, _ in sinks]
            p_dsts = [p for p in p_dsts if p is not None]

            fanout = len(p_dsts)

            if self.decoupler.is_hfn(net_name, fanout):
                route = self.decoupler.decouple_net(net_name, p_src, p_dsts)
                net_routes[net_name] = route
                decoupled_count += 1
            else:
                regular_nets[net_name] = (p_src, p_dsts)
                if p_src and p_dsts and num_ranks > 1:
                    r_src = self.graph.nodes[src_node].rank
                    c_idx = max(0, min(r_src, num_ranks - 2))
                    y_all = [p_src.y] + [pd.y for pd in p_dsts]
                    channel_intervals[c_idx].append((min(y_all), max(y_all), net_name))

        # Step 3: Run Left-Edge track assignment for each channel
        for c_idx, intervals in channel_intervals.items():
            intervals.sort(key=lambda x: x[0])
            heap: List[Tuple[float, int]] = []  # (end_y, track_id)
            track_count = 0

            for ymin, ymax, nname in intervals:
                # If earliest track finishes before this interval starts (with 10 unit gap)
                if heap and heap[0][0] + 10.0 <= ymin:
                    end_y, track_id = heapq.heappop(heap)
                else:
                    track_id = track_count
                    track_count += 1

                heapq.heappush(heap, (ymax, track_id))
                self._channel_track_alloc[c_idx][nname] = track_id

            self._channel_track_count[c_idx] = max(1, track_count)

        # Step 4: Route regular nets
        for net_name, (p_src, p_dsts) in regular_nets.items():
            if not p_src or not p_dsts:
                # Unconnected or single-node stub
                continue

            route = self._route_single_net(net_name, p_src, p_dsts)
            net_routes[net_name] = route

        t1 = time.time()

        # Compute summary metrics
        total_segs = sum(len(r.segments) for r in net_routes.values())
        total_dots = sum(len(r.solder_dots) for r in net_routes.values())
        total_bends = sum(r.num_bends for r in net_routes.values())

        # Verify strict orthogonality
        is_strictly_orthogonal = True
        for r in net_routes.values():
            for s in r.segments:
                dx = abs(s.p1.x - s.p2.x)
                dy = abs(s.p1.y - s.p2.y)
                if dx > 1e-4 and dy > 1e-4:
                    is_strictly_orthogonal = False
                    break
            if not is_strictly_orthogonal:
                break

        # Compute bounding box including perimeter corridor routes
        all_xs = [self._min_x, self._max_x, self._left_perimeter_x, self._right_perimeter_x]
        all_ys = [self._min_y, self._max_y, self._top_corridor_base, self._bottom_corridor_base]
        for r in net_routes.values():
            for s in r.segments:
                all_xs.append(s.p1.x)
                all_xs.append(s.p2.x)
                all_ys.append(s.p1.y)
                all_ys.append(s.p2.y)
        routing_bbox = (min(all_xs) - 20.0, min(all_ys) - 20.0, max(all_xs) + 20.0, max(all_ys) + 20.0)

        return RoutingResult(
            module_name=self.placement.module_name,
            net_routes=net_routes,
            total_segments=total_segs,
            total_solder_dots=total_dots,
            total_bends=total_bends,
            decoupled_hfn_count=decoupled_count,
            regular_routed_count=len(regular_nets),
            is_strictly_orthogonal=is_strictly_orthogonal,
            bbox=routing_bbox,
            elapsed_seconds=t1 - t0,
        )

    def _route_single_net(
        self,
        net_name: str,
        p_src: PinLocation,
        p_dsts: List[PinLocation],
    ) -> NetRoute:
        """Routes a single non-HFN net using orthogonal Manhattan channels."""
        segments: List[WireSegment] = []
        num_ranks = len(self.graph.ranks)

        src_node = self.graph.nodes[p_src.node_id]
        r_src = src_node.rank

        # Main vertical channel for the driver
        if r_src >= num_ranks - 1:
            # Driver is in the last rank: trunk must be in the right perimeter channel!
            x_trunk = self._right_perimeter_x + self._corridor_offset
            track_id = 0
        else:
            c_main = max(0, min(r_src, num_ranks - 2)) if num_ranks > 1 else 0
            track_id = self._channel_track_alloc[c_main].get(net_name, 0)
            x_trunk = self._get_channel_track_x(c_main, track_id)

        # Optimization: Fanout = 1, single horizontal straight line without collisions
        if len(p_dsts) == 1 and abs(p_src.y - p_dsts[0].y) < 1e-3 and p_dsts[0].x > p_src.x:
            dst_pin = p_dsts[0]
            if dst_pin.direction == PinExitDirection.WEST:
                if not self._check_horizontal_collision(p_src.x, dst_pin.x, p_src.y):
                    seg = WireSegment(
                        p1=Point(p_src.x, p_src.y),
                        p2=Point(dst_pin.x, dst_pin.y),
                        net_name=net_name,
                        orientation=SegmentOrientation.HORIZONTAL,
                    )
                    return NetRoute(
                        net_name=net_name,
                        segments=[seg],
                        solder_dots=[],
                        is_decoupled_hfn=False,
                        driver_pin=p_src,
                        sink_pins=p_dsts,
                    )

        # 1. Driver pin exit lead: must emerge horizontally to the East (or perpendicularly)
        if abs(p_src.x - x_trunk) > 1e-3:
            segments.append(
                WireSegment(
                    p1=Point(p_src.x, p_src.y),
                    p2=Point(x_trunk, p_src.y),
                    net_name=net_name,
                    orientation=SegmentOrientation.HORIZONTAL,
                )
            )

        # Group sinks into forward, skip-rank, and feedback
        trunk_y_points: List[float] = [p_src.y]
        corridor_offset = self._corridor_offset
        self._corridor_offset = (self._corridor_offset + 6.0) % 40.0

        for pd in p_dsts:
            dst_node = self.graph.nodes[pd.node_id]
            r_dst = dst_node.rank

            if r_dst <= r_src or pd.x <= x_trunk:
                # FEEDBACK / SAME-COLUMN ROUTE via Top Corridor
                y_feed = self._top_corridor_base - corridor_offset
                trunk_y_points.append(y_feed)

                # Up in c_main to top corridor
                segments.append(
                    WireSegment(
                        p1=Point(x_trunk, p_src.y),
                        p2=Point(x_trunk, y_feed),
                        net_name=net_name,
                        orientation=SegmentOrientation.VERTICAL,
                    )
                )

                # Drop channel
                if r_dst == 0:
                    x_drop = self._left_perimeter_x - corridor_offset
                else:
                    c_drop = max(0, min(r_dst - 1, num_ranks - 2))
                    drop_track = self._channel_track_alloc[c_drop].get(net_name, 0)
                    x_drop = self._get_channel_track_x(c_drop, drop_track)

                # Horizontal along top corridor
                segments.append(
                    WireSegment(
                        p1=Point(x_trunk, y_feed),
                        p2=Point(x_drop, y_feed),
                        net_name=net_name,
                        orientation=SegmentOrientation.HORIZONTAL,
                    )
                )

                # Drop down in drop channel
                if pd.direction == PinExitDirection.SOUTH:
                    y_dogleg = pd.y + 16.0
                    segments.append(
                        WireSegment(
                            p1=Point(x_drop, y_feed),
                            p2=Point(x_drop, y_dogleg),
                            net_name=net_name,
                            orientation=SegmentOrientation.VERTICAL,
                        )
                    )
                    segments.append(
                        WireSegment(
                            p1=Point(x_drop, y_dogleg),
                            p2=Point(pd.x, y_dogleg),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )
                    segments.append(
                        WireSegment(
                            p1=Point(pd.x, y_dogleg),
                            p2=Point(pd.x, pd.y),
                            net_name=net_name,
                            orientation=SegmentOrientation.VERTICAL,
                        )
                    )
                else:
                    segments.append(
                        WireSegment(
                            p1=Point(x_drop, y_feed),
                            p2=Point(x_drop, pd.y),
                            net_name=net_name,
                            orientation=SegmentOrientation.VERTICAL,
                        )
                    )
                    segments.append(
                        WireSegment(
                            p1=Point(x_drop, pd.y),
                            p2=Point(pd.x, pd.y),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )

            elif r_dst == r_src + 1:
                # DIRECT ADJACENT COLUMN ROUTE
                trunk_y_points.append(pd.y)
                if pd.direction == PinExitDirection.SOUTH:
                    y_dogleg = pd.y + 16.0
                    trunk_y_points.append(y_dogleg)
                    segments.append(
                        WireSegment(
                            p1=Point(x_trunk, y_dogleg),
                            p2=Point(pd.x, y_dogleg),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )
                    segments.append(
                        WireSegment(
                            p1=Point(pd.x, y_dogleg),
                            p2=Point(pd.x, pd.y),
                            net_name=net_name,
                            orientation=SegmentOrientation.VERTICAL,
                        )
                    )
                else:
                    segments.append(
                        WireSegment(
                            p1=Point(x_trunk, pd.y),
                            p2=Point(pd.x, pd.y),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )

            else:
                # SKIP-RANK FORWARD ROUTE (r_dst > r_src + 1)
                c_dest = max(0, min(r_dst - 1, num_ranks - 2))
                dest_track = self._channel_track_alloc[c_dest].get(net_name, 0)
                x_dest_trunk = self._get_channel_track_x(c_dest, dest_track)

                # Check collision for straight bridge at p_src.y or target y
                dst_target_y = pd.y + 16.0 if pd.direction == PinExitDirection.SOUTH else pd.y
                has_coll_src = self._check_horizontal_collision(x_trunk, x_dest_trunk, p_src.y)
                has_coll_dst = self._check_horizontal_collision(x_trunk, x_dest_trunk, dst_target_y)

                if not has_coll_src:
                    y_bridge = p_src.y
                    trunk_y_points.append(y_bridge)
                    segments.append(
                        WireSegment(
                            p1=Point(x_trunk, y_bridge),
                            p2=Point(x_dest_trunk, y_bridge),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )
                    # Down/up to target y in c_dest
                    if pd.direction == PinExitDirection.SOUTH:
                        y_dogleg = pd.y + 16.0
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_bridge),
                                p2=Point(x_dest_trunk, y_dogleg),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_dogleg),
                                p2=Point(pd.x, y_dogleg),
                                net_name=net_name,
                                orientation=SegmentOrientation.HORIZONTAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(pd.x, y_dogleg),
                                p2=Point(pd.x, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                    else:
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_bridge),
                                p2=Point(x_dest_trunk, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, pd.y),
                                p2=Point(pd.x, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.HORIZONTAL,
                            )
                        )

                elif not has_coll_dst:
                    y_bridge = dst_target_y
                    trunk_y_points.append(y_bridge)
                    segments.append(
                        WireSegment(
                            p1=Point(x_trunk, y_bridge),
                            p2=Point(x_dest_trunk, y_bridge),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )
                    if pd.direction == PinExitDirection.SOUTH:
                        y_dogleg = pd.y + 16.0
                        if abs(y_bridge - y_dogleg) > 1e-3:
                            segments.append(
                                WireSegment(
                                    p1=Point(x_dest_trunk, y_bridge),
                                    p2=Point(x_dest_trunk, y_dogleg),
                                    net_name=net_name,
                                    orientation=SegmentOrientation.VERTICAL,
                                )
                            )
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_dogleg),
                                p2=Point(pd.x, y_dogleg),
                                net_name=net_name,
                                orientation=SegmentOrientation.HORIZONTAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(pd.x, y_dogleg),
                                p2=Point(pd.x, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                    else:
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, pd.y),
                                p2=Point(pd.x, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.HORIZONTAL,
                            )
                        )

                else:
                    # BOTH OBSTRUCTED: Route via Perimeter Corridor!
                    mid_y = (self._min_y + self._max_y) / 2.0
                    if p_src.y < mid_y:
                        y_corr = self._top_corridor_base - corridor_offset
                    else:
                        y_corr = self._bottom_corridor_base + corridor_offset

                    trunk_y_points.append(y_corr)
                    # Up/down in c_main to corridor
                    segments.append(
                        WireSegment(
                            p1=Point(x_trunk, p_src.y),
                            p2=Point(x_trunk, y_corr),
                            net_name=net_name,
                            orientation=SegmentOrientation.VERTICAL,
                        )
                    )
                    # Horizontal along corridor across intermediate ranks
                    segments.append(
                        WireSegment(
                            p1=Point(x_trunk, y_corr),
                            p2=Point(x_dest_trunk, y_corr),
                            net_name=net_name,
                            orientation=SegmentOrientation.HORIZONTAL,
                        )
                    )
                    # Down/up in c_dest from corridor to sink
                    if pd.direction == PinExitDirection.SOUTH:
                        y_dogleg = pd.y + 16.0
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_corr),
                                p2=Point(x_dest_trunk, y_dogleg),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_dogleg),
                                p2=Point(pd.x, y_dogleg),
                                net_name=net_name,
                                orientation=SegmentOrientation.HORIZONTAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(pd.x, y_dogleg),
                                p2=Point(pd.x, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                    else:
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, y_corr),
                                p2=Point(x_dest_trunk, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.VERTICAL,
                            )
                        )
                        segments.append(
                            WireSegment(
                                p1=Point(x_dest_trunk, pd.y),
                                p2=Point(pd.x, pd.y),
                                net_name=net_name,
                                orientation=SegmentOrientation.HORIZONTAL,
                            )
                        )

        # 2. Main vertical trunk segment
        y_min = min(trunk_y_points)
        y_max = max(trunk_y_points)
        if y_max - y_min > 1e-3:
            segments.append(
                WireSegment(
                    p1=Point(x_trunk, y_min),
                    p2=Point(x_trunk, y_max),
                    net_name=net_name,
                    orientation=SegmentOrientation.VERTICAL,
                    track_id=track_id if r_src < num_ranks - 1 else 0,
                )
            )

        # 3. Detect 3-way/4-way junctions and insert solder dots
        solder_dots = self.solder_manager.detect_junctions(segments, net_name) if len(p_dsts) > 1 else []

        return NetRoute(
            net_name=net_name,
            segments=segments,
            solder_dots=solder_dots,
            is_decoupled_hfn=False,
            driver_pin=p_src,
            sink_pins=p_dsts,
        )
