"""Current-loop serial protocol structures."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SerialFrame:
    route: int
    cmd: int
    data: int

    def normalized(self) -> "SerialFrame":
        return SerialFrame(route=self.route & 0xFF, cmd=self.cmd & 0xFF, data=self.data & 0xFF)

    def is_current_loop(self) -> bool:
        return (self.route & 0xF0) == 0xB0

    def __str__(self) -> str:
        return f"[route=0x{self.route:02X} cmd=0x{self.cmd:02X} data=0x{self.data:02X}]"
