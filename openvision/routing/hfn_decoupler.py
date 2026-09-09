"""
High-Fanout Net (HFN) Decoupler for OpenVision.
Decouples global high-fanout signals (clocks, resets, enables) into localized
pin stubs with net labels and directional indicators, preventing unreadable
global spaghetti lines across the schematic canvas.
"""

import re
from typing import Dict, List, Optional, Set, Tuple
from openvision.routing.router_models import (
    Point,
    WireSegment,
    SegmentOrientation,
    PinLocation,
    PinExitDirection,
    HFNStub,
    NetRoute,
)

# Standard regexes for global clock, reset, and test signals
DEFAULT_GLOBAL_PATTERNS = [
    re.compile(r"(clk|clock|gclk)", re.IGNORECASE),
    re.compile(r"(rst|reset)", re.IGNORECASE),
    re.compile(r"(scan_enable|scan_en|test_mode|test_en|se)", re.IGNORECASE),
]


class HighFanoutDecoupler:
    """
    Detects and decouples High-Fanout Nets (HFNs).
    Replaces long-distance interconnect wires with local pin stubs and tags.
    """

    def __init__(
        self,
        hfn_threshold: int = 20,
        stub_length: float = 16.0,
        decouple_globals: bool = True,
        custom_patterns: Optional[List[re.Pattern]] = None,
    ):
        self.hfn_threshold = hfn_threshold
        self.stub_length = stub_length
        self.decouple_globals = decouple_globals
        self.patterns = custom_patterns or DEFAULT_GLOBAL_PATTERNS

    def is_hfn(self, net_name: str, fanout: int) -> bool:
        """Determines if a net qualifies as a high-fanout net to be decoupled."""
        if fanout >= self.hfn_threshold:
            return True
        if self.decouple_globals:
            for pat in self.patterns:
                if pat.search(net_name):
                    return True
        return False

    def decouple_net(
        self,
        net_name: str,
        driver_pin: Optional[PinLocation],
        sink_pins: List[PinLocation],
    ) -> NetRoute:
        """
        Creates an HFN NetRoute consisting of short localized stubs and label tags
        at the driver and each sink pin.
        """
        stubs: List[HFNStub] = []
        segments: List[WireSegment] = []

        # 1. Driver pin stub
        if driver_pin:
            if driver_pin.direction == PinExitDirection.EAST:
                p_start = Point(driver_pin.x, driver_pin.y)
                p_end = Point(driver_pin.x + self.stub_length, driver_pin.y)
                orientation = SegmentOrientation.HORIZONTAL
                arrow = "RIGHT"
            elif driver_pin.direction == PinExitDirection.SOUTH:
                p_start = Point(driver_pin.x, driver_pin.y)
                p_end = Point(driver_pin.x, driver_pin.y + self.stub_length)
                orientation = SegmentOrientation.VERTICAL
                arrow = "DOWN"
            elif driver_pin.direction == PinExitDirection.WEST:
                p_start = Point(driver_pin.x, driver_pin.y)
                p_end = Point(driver_pin.x - self.stub_length, driver_pin.y)
                orientation = SegmentOrientation.HORIZONTAL
                arrow = "LEFT"
            else:
                p_start = Point(driver_pin.x, driver_pin.y)
                p_end = Point(driver_pin.x, driver_pin.y - self.stub_length)
                orientation = SegmentOrientation.VERTICAL
                arrow = "UP"

            seg = WireSegment(
                p1=p_start,
                p2=p_end,
                net_name=net_name,
                orientation=orientation,
                is_stub=True,
            )
            segments.append(seg)
            stubs.append(
                HFNStub(
                    net_name=net_name,
                    pin_loc=driver_pin,
                    start=p_start,
                    end=p_end,
                    label=net_name,
                    is_driver=True,
                    arrow_direction=arrow,
                )
            )

        # 2. Sink pin stubs
        for sink in sink_pins:
            if sink.direction == PinExitDirection.WEST:
                # Enters into pin from the left
                p_start = Point(sink.x - self.stub_length, sink.y)
                p_end = Point(sink.x, sink.y)
                orientation = SegmentOrientation.HORIZONTAL
                arrow = "RIGHT"
            elif sink.direction == PinExitDirection.SOUTH:
                # Enters into pin from below
                p_start = Point(sink.x, sink.y + self.stub_length)
                p_end = Point(sink.x, sink.y)
                orientation = SegmentOrientation.VERTICAL
                arrow = "UP"
            elif sink.direction == PinExitDirection.EAST:
                p_start = Point(sink.x + self.stub_length, sink.y)
                p_end = Point(sink.x, sink.y)
                orientation = SegmentOrientation.HORIZONTAL
                arrow = "LEFT"
            else:
                p_start = Point(sink.x, sink.y - self.stub_length)
                p_end = Point(sink.x, sink.y)
                orientation = SegmentOrientation.VERTICAL
                arrow = "DOWN"

            seg = WireSegment(
                p1=p_start,
                p2=p_end,
                net_name=net_name,
                orientation=orientation,
                is_stub=True,
            )
            segments.append(seg)
            stubs.append(
                HFNStub(
                    net_name=net_name,
                    pin_loc=sink,
                    start=p_start,
                    end=p_end,
                    label=net_name,
                    is_driver=False,
                    arrow_direction=arrow,
                )
            )

        return NetRoute(
            net_name=net_name,
            segments=segments,
            solder_dots=[],  # HFN stubs are independent; no cross-channel solder dots
            is_decoupled_hfn=True,
            hfn_stubs=stubs,
            driver_pin=driver_pin,
            sink_pins=sink_pins,
        )
