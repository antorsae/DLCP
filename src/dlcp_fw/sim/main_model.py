"""Stateful main-unit simulation model for preset banking tests."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .hexio import parse_intel_hex
from .protocol import SerialFrame


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class FlashWriteEvent:
    logical_addr: int
    physical_addr: int
    value: int


@dataclass(frozen=True)
class DspIngestEvent:
    preset_idx: int
    table_base: int
    table_sha256: str


@dataclass
class MainUnitModel:
    name: str
    link_addr: int
    flash: bytearray
    preset_idx: int = 0
    apply_count: int = 0
    rx_count: int = 0
    handled_count: int = 0
    flash_writes: List[FlashWriteEvent] = field(default_factory=list)
    dsp_ingest: List[DspIngestEvent] = field(default_factory=list)

    @staticmethod
    def from_hex(name: str, link_addr: int, hex_path: Path) -> "MainUnitModel":
        mem: Dict[int, int] = parse_intel_hex(hex_path)
        flash = bytearray([0xFF] * 0x6000)
        for addr, b in mem.items():
            if 0 <= addr < len(flash):
                flash[addr] = b
        return MainUnitModel(name=name, link_addr=link_addr, flash=flash)

    def _accepts_route(self, route: int) -> bool:
        if (route & 0xF0) != 0xB0:
            return False
        rid = route & 0x0F
        return rid == 0 or rid == self.link_addr

    def _map_addr_for_table(self, logical_addr: int) -> int:
        if self.preset_idx != 1:
            return logical_addr
        upper = (logical_addr >> 16) & 0xFF
        high = (logical_addr >> 8) & 0xFF
        if upper != 0:
            return logical_addr
        if 0x56 <= high <= 0x5F:
            return logical_addr - 0x0C00
        return logical_addr

    def process_frame(self, frame: SerialFrame) -> bool:
        frame = frame.normalized()
        self.rx_count += 1
        if not self._accepts_route(frame.route):
            return False
        if frame.cmd == 0x20:
            self.set_preset(frame.data & 0x01)
            self.handled_count += 1
            return True
        return False

    def set_preset(self, idx: int) -> None:
        normalized = 1 if idx else 0
        if normalized == self.preset_idx:
            return
        self.preset_idx = normalized
        self.apply_table()

    def table_bytes(self, base: int = 0x5600) -> bytes:
        return bytes(self.flash[base : base + 0xA00])

    def table_digest(self, base: int = 0x5600) -> str:
        return sha256_hex(self.table_bytes(base))

    def apply_table(self) -> None:
        self.apply_count += 1
        base = 0x4A00 if self.preset_idx else 0x5600
        self.dsp_ingest.append(
            DspIngestEvent(
                preset_idx=self.preset_idx,
                table_base=base,
                table_sha256=self.table_digest(base),
            )
        )

    def upload_hfd_table(self, payload_0xA00: bytes) -> None:
        if len(payload_0xA00) != 0xA00:
            raise ValueError("payload must be exactly 0xA00 bytes")
        for i, b in enumerate(payload_0xA00):
            logical = 0x5600 + i
            physical = self._map_addr_for_table(logical)
            if not (0 <= physical < len(self.flash)):
                raise RuntimeError(f"{self.name}: mapped address out of range 0x{physical:04X}")
            self.flash[physical] = b
            self.flash_writes.append(
                FlashWriteEvent(logical_addr=logical, physical_addr=physical, value=b)
            )
