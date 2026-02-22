"""Current-loop bus model with deterministic fault injection."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Sequence, Set

from .main_model import MainUnitModel
from .protocol import SerialFrame


@dataclass
class FaultProfile:
    """
    Deterministic fault injection profile.

    Indexing is 0-based by emitted frame order.
    """

    drop_indices: Set[int] = field(default_factory=set)
    duplicate_indices: Set[int] = field(default_factory=set)
    corrupt_cmd_indices: Set[int] = field(default_factory=set)
    corrupt_route_indices: Set[int] = field(default_factory=set)


@dataclass
class BusDelivery:
    index: int
    frame: SerialFrame
    delivered: bool
    handled_by: List[str]


@dataclass
class CurrentLoopBus:
    mains: List[MainUnitModel]
    fault: FaultProfile = field(default_factory=FaultProfile)
    deliveries: List[BusDelivery] = field(default_factory=list)

    def _deliver_once(self, idx: int, frame: SerialFrame) -> List[str]:
        handled: List[str] = []
        for m in self.mains:
            if m.process_frame(frame):
                handled.append(m.name)
        self.deliveries.append(BusDelivery(index=idx, frame=frame, delivered=True, handled_by=handled))
        return handled

    def deliver(self, idx: int, frame: SerialFrame) -> List[str]:
        frame = frame.normalized()
        if idx in self.fault.corrupt_cmd_indices:
            frame = SerialFrame(route=frame.route, cmd=0x2F, data=frame.data)
        if idx in self.fault.corrupt_route_indices:
            frame = SerialFrame(route=0xAF, cmd=frame.cmd, data=frame.data)

        if idx in self.fault.drop_indices:
            self.deliveries.append(BusDelivery(index=idx, frame=frame, delivered=False, handled_by=[]))
            return []

        handled = self._deliver_once(idx, frame)
        if idx in self.fault.duplicate_indices:
            handled2 = self._deliver_once(idx, frame)
            handled = handled + handled2
        return handled

    def deliver_many(self, frames: Sequence[SerialFrame]) -> List[List[str]]:
        out: List[List[str]] = []
        for i, frame in enumerate(frames):
            out.append(self.deliver(i, frame))
        return out
