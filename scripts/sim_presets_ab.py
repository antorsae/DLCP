#!/usr/bin/env python3
"""
Protocol-level simulator for DLCP A/B preset behavior.

This is intentionally not a full PIC emulator. It models:
- one Control unit sending current-loop command 0x20 (set preset)
- two Main units receiving broadcast, selecting preset A/B
- HFD-style table uploads targeting 0x5600..0x5FFF, transparently mapped to
  A or B bank by the patched firmware logic
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
from dataclasses import dataclass
from typing import Dict, Iterable

import _bootstrap

from dlcp_fw.paths import STOCK_MAIN_HEX

ROOT = _bootstrap.REPO_ROOT


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0
    with path.open("r", encoding="ascii", errors="strict") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise RuntimeError(f"{path}:{lineno}: bad HEX line")
            ll = int(line[1:3], 16)
            aaaa = int(line[3:7], 16)
            rtype = int(line[7:9], 16)
            data = bytes.fromhex(line[9 : 9 + ll * 2])
            if rtype == 0x00:
                base = (upper << 16) | aaaa
                for i, b in enumerate(data):
                    mem[base + i] = b
            elif rtype == 0x01:
                break
            elif rtype == 0x04:
                if ll != 2:
                    raise RuntimeError(f"{path}:{lineno}: bad type 04 length")
                upper = (data[0] << 8) | data[1]
    return mem


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@dataclass
class MainUnitSim:
    name: str
    flash: bytearray
    preset_idx: int = 0
    apply_count: int = 0

    @staticmethod
    def from_hex(name: str, hex_path: pathlib.Path) -> "MainUnitSim":
        mem = parse_intel_hex(hex_path)
        # model only program space 0x0000..0x5FFF
        flash = bytearray([0xFF] * 0x6000)
        for a, b in mem.items():
            if 0 <= a < 0x6000:
                flash[a] = b
        return MainUnitSim(name=name, flash=flash)

    def _map_addr_for_table(self, addr: int) -> int:
        """Mirror patched firmware remap for table accesses."""
        if self.preset_idx != 1:
            return addr
        hi = (addr >> 8) & 0xFF
        lo_hi = (addr >> 16) & 0xFF
        if lo_hi != 0:
            return addr
        if 0x56 <= hi <= 0x5F:
            return addr - 0x0C00
        return addr

    def set_preset(self, idx: int) -> None:
        self.preset_idx = 1 if idx else 0
        self.apply_table()

    def apply_table(self) -> None:
        # In hardware this pushes flash table entries to TAS3108 via I2C.
        self.apply_count += 1

    def upload_hfd_table(self, payload_0xA00: bytes) -> None:
        """Simulate HFD writing full table to logical A range 0x5600..0x5FFF."""
        if len(payload_0xA00) != 0xA00:
            raise ValueError("payload must be exactly 0xA00 bytes")
        for i, b in enumerate(payload_0xA00):
            logical = 0x5600 + i
            phys = self._map_addr_for_table(logical)
            if not (0 <= phys < len(self.flash)):
                raise RuntimeError(f"mapped address out of range: 0x{phys:04X}")
            self.flash[phys] = b

    def table_digest(self, base: int) -> str:
        return sha256_hex(bytes(self.flash[base : base + 0xA00]))


@dataclass
class ControlUnitSim:
    preset_idx: int = 0

    def broadcast_set_preset(self, mains: Iterable[MainUnitSim], idx: int) -> None:
        self.preset_idx = 1 if idx else 0
        # Current-loop frame: route=0xBF, cmd=0x20, data=idx
        for m in mains:
            m.set_preset(self.preset_idx)


def build_payload(seed: int) -> bytes:
    # Deterministic pseudo-data for simulation runs.
    out = bytearray(0xA00)
    x = seed & 0xFF
    for i in range(len(out)):
        x = ((x * 109) + 19) & 0xFF
        out[i] = x
    return bytes(out)


def run_demo(main_hex: pathlib.Path) -> int:
    left = MainUnitSim.from_hex("main_left", main_hex)
    right = MainUnitSim.from_hex("main_right", main_hex)
    ctl = ControlUnitSim()
    mains = [left, right]

    print("initial preset:", ctl.preset_idx)
    print("A digest left :", left.table_digest(0x5600))
    print("B digest left :", left.table_digest(0x4A00))

    payload_a = build_payload(0x11)
    ctl.broadcast_set_preset(mains, 0)
    for m in mains:
        m.upload_hfd_table(payload_a)
    print("\nafter upload in preset A:")
    print("A digest left :", left.table_digest(0x5600))
    print("B digest left :", left.table_digest(0x4A00))
    print("apply counts  :", left.apply_count, right.apply_count)

    payload_b = build_payload(0x7C)
    ctl.broadcast_set_preset(mains, 1)
    for m in mains:
        m.upload_hfd_table(payload_b)
    print("\nafter upload in preset B:")
    print("A digest left :", left.table_digest(0x5600))
    print("B digest left :", left.table_digest(0x4A00))
    print("apply counts  :", left.apply_count, right.apply_count)

    # Sanity assertions:
    assert left.table_digest(0x5600) == right.table_digest(0x5600)
    assert left.table_digest(0x4A00) == right.table_digest(0x4A00)
    assert left.table_digest(0x5600) != left.table_digest(0x4A00)
    print("\nOK: two-main preset sync + banked upload behavior validated.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--main-hex",
        type=pathlib.Path,
        default=STOCK_MAIN_HEX,
        help="main firmware HEX used as simulation flash seed",
    )
    args = ap.parse_args()
    return run_demo(args.main_hex.resolve())


if __name__ == "__main__":
    raise SystemExit(main())
