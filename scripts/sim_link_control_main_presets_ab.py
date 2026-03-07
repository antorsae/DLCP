#!/usr/bin/env python3
"""
End-to-end DLCP A/B preset link simulation.

This is a protocol-level simulation (not PIC instruction emulation). It models:
- patched CONTROL firmware sending current-loop frames
- two patched MAIN units receiving/handling route+cmd+data frames
- transparent HFD uploads into logical table range 0x5600..0x5FFF
"""

from __future__ import annotations

import argparse
import hashlib
import pathlib
from dataclasses import dataclass, field
from typing import Dict, Iterable, List

import _bootstrap

from dlcp_fw.paths import PATCHED_CONTROL_HEX, PATCHED_MAIN_HEX

ROOT = _bootstrap.REPO_ROOT


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0
    for lineno, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise RuntimeError(f"{path}:{lineno}: invalid HEX record")
        ll = int(line[1:3], 16)
        addr16 = int(line[3:7], 16)
        rtype = int(line[7:9], 16)
        data = bytes.fromhex(line[9 : 9 + ll * 2])
        if rtype == 0x00:
            base = (upper << 16) | addr16
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


def build_payload(seed: int) -> bytes:
    out = bytearray(0xA00)
    x = seed & 0xFF
    for i in range(len(out)):
        x = ((x * 109) + 19) & 0xFF
        out[i] = x
    return bytes(out)


@dataclass(frozen=True)
class SerialFrame:
    route: int
    cmd: int
    data: int

    def __str__(self) -> str:
        return f"[route=0x{self.route:02X} cmd=0x{self.cmd:02X} data=0x{self.data:02X}]"


@dataclass
class MainUnitSim:
    name: str
    link_addr: int
    flash: bytearray
    preset_idx: int = 0
    apply_count: int = 0
    rx_count: int = 0
    handled_count: int = 0

    @staticmethod
    def from_hex(name: str, link_addr: int, hex_path: pathlib.Path) -> "MainUnitSim":
        mem = parse_intel_hex(hex_path)
        flash = bytearray([0xFF] * 0x6000)
        for a, b in mem.items():
            if 0 <= a < 0x6000:
                flash[a] = b
        return MainUnitSim(name=name, link_addr=link_addr, flash=flash)

    def _accepts_route(self, route: int) -> bool:
        if (route & 0xF0) != 0xB0:
            return False
        route_id = route & 0x0F
        return route_id == 0 or route_id == self.link_addr

    def _map_addr_for_table(self, addr: int) -> int:
        if self.preset_idx != 1:
            return addr
        hi = (addr >> 8) & 0xFF
        upper = (addr >> 16) & 0xFF
        if upper != 0:
            return addr
        if 0x56 <= hi <= 0x5F:
            return addr - 0x0C00
        return addr

    def process_frame(self, frame: SerialFrame) -> bool:
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

    def apply_table(self) -> None:
        self.apply_count += 1

    def upload_hfd_table(self, payload_0xA00: bytes) -> None:
        if len(payload_0xA00) != 0xA00:
            raise ValueError("payload must be exactly 0xA00 bytes")
        for i, b in enumerate(payload_0xA00):
            logical = 0x5600 + i
            phys = self._map_addr_for_table(logical)
            if not (0 <= phys < len(self.flash)):
                raise RuntimeError(f"{self.name}: mapped address out of range 0x{phys:04X}")
            self.flash[phys] = b

    def table_digest(self, base: int) -> str:
        return sha256_hex(bytes(self.flash[base : base + 0xA00]))


@dataclass
class ControlUnitSim:
    preset_idx: int = 0
    preset_vals: List[int] = field(default_factory=lambda: [0] * 6)
    tx_frames: List[SerialFrame] = field(default_factory=list)

    def set_preset(self, idx: int) -> SerialFrame:
        normalized = 1 if idx else 0
        self.preset_idx = normalized
        for i in range(6):
            self.preset_vals[i] = normalized
        frame = SerialFrame(route=0xB0, cmd=0x20, data=normalized)
        self.tx_frames.append(frame)
        return frame


@dataclass
class CurrentLoopBusSim:
    mains: List[MainUnitSim]

    def deliver(self, frame: SerialFrame) -> List[str]:
        handled_by: List[str] = []
        for m in self.mains:
            if m.process_frame(frame):
                handled_by.append(m.name)
        return handled_by


def verify_patch_compat(main_mem: Dict[int, int], control_mem: Dict[int, int]) -> None:
    main_checks = {
        0x1E64: 0x90,  # goto 0x5520 hook
        0x2E6E: 0x20,  # goto 0x5440 hook
        0x3DAC: 0x60,  # goto 0x54C0 hook
        0x4028: 0x00,  # goto 0x5400 hook
        0x5536: 0x20,  # xorlw 0x20 in cmd_tail_patch
    }
    for addr, want in main_checks.items():
        got = main_mem.get(addr, 0xFF)
        if got != want:
            raise RuntimeError(
                f"main hex compatibility check failed at 0x{addr:04X}: got 0x{got:02X}, want 0x{want:02X}"
            )

    control_checks = {
        0x0B53: 0xEF,  # goto full_sync_entry_stub (periodic preset resync hook)
        0x123F: 0xEF,  # goto new_dispatch_stub (dispatch hook present)
        0x13AF: 0xEF,  # goto volume_indicator_stub (indicator hook present)
        0x1264: 0x03,  # nav wrap RIGHT = 3 (4-screen)
        0x1288: 0x03,  # nav wrap LEFT = 3 (4-screen)
    }
    for addr, want in control_checks.items():
        got = control_mem.get(addr, 0xFF)
        if got != want:
            raise RuntimeError(
                f"control hex compatibility check failed at 0x{addr:04X}: got 0x{got:02X}, want 0x{want:02X}"
            )


def print_bank_state(tag: str, mains: Iterable[MainUnitSim]) -> None:
    print(tag)
    for m in mains:
        print(
            f"  {m.name}: preset={'B' if m.preset_idx else 'A'} "
            f"A={m.table_digest(0x5600)[:12]} B={m.table_digest(0x4A00)[:12]} "
            f"apply={m.apply_count}"
        )


def run_demo(
    main_hex: pathlib.Path,
    control_hex: pathlib.Path,
    left_addr: int,
    right_addr: int,
    seed_a: int,
    seed_b: int,
) -> int:
    main_mem = parse_intel_hex(main_hex)
    control_mem = parse_intel_hex(control_hex)
    verify_patch_compat(main_mem, control_mem)

    left = MainUnitSim.from_hex("main_left", left_addr, main_hex)
    right = MainUnitSim.from_hex("main_right", right_addr, main_hex)
    mains = [left, right]
    bus = CurrentLoopBusSim(mains=mains)
    ctl = ControlUnitSim()

    print("Patch-compat: OK")
    print(f"Main addresses: left={left_addr} right={right_addr}")
    print_bank_state("Initial bank state:", mains)

    payload_a = build_payload(seed_a)
    payload_b = build_payload(seed_b)

    frame = ctl.set_preset(0)
    handled = bus.deliver(frame)
    print(f"\nCONTROL TX {frame} -> handled by {handled}")
    for m in mains:
        m.upload_hfd_table(payload_a)
    print_bank_state("After HFD upload in preset A:", mains)

    frame = ctl.set_preset(1)
    handled = bus.deliver(frame)
    print(f"\nCONTROL TX {frame} -> handled by {handled}")
    for m in mains:
        m.upload_hfd_table(payload_b)
    print_bank_state("After HFD upload in preset B:", mains)

    frame = ctl.set_preset(0)
    handled = bus.deliver(frame)
    print(f"\nCONTROL TX {frame} -> handled by {handled}")
    print_bank_state("Final state after switch back to A:", mains)

    # Assertions for the specific two-main synchronized preset requirement.
    assert left.preset_idx == 0 and right.preset_idx == 0
    assert left.table_digest(0x5600) == right.table_digest(0x5600)
    assert left.table_digest(0x4A00) == right.table_digest(0x4A00)
    assert left.table_digest(0x5600) != left.table_digest(0x4A00)
    assert left.apply_count >= 3 and right.apply_count >= 3
    assert len(ctl.tx_frames) == 3

    print("\nOK: CONTROL<->MAIN serial comms are compatible and two-main preset sync is validated.")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--main-hex",
        type=pathlib.Path,
        default=PATCHED_MAIN_HEX,
        help="patched main firmware HEX",
    )
    ap.add_argument(
        "--control-hex",
        type=pathlib.Path,
        default=PATCHED_CONTROL_HEX,
        help="patched control firmware HEX",
    )
    ap.add_argument("--left-addr", type=int, default=1, help="left main link address (1..15)")
    ap.add_argument("--right-addr", type=int, default=2, help="right main link address (1..15)")
    ap.add_argument("--seed-a", type=int, default=0x11, help="deterministic payload seed for preset A")
    ap.add_argument("--seed-b", type=int, default=0x7C, help="deterministic payload seed for preset B")
    args = ap.parse_args()

    for v, n in ((args.left_addr, "left-addr"), (args.right_addr, "right-addr")):
        if not (1 <= v <= 15):
            raise SystemExit(f"{n} must be in 1..15")

    return run_demo(
        main_hex=args.main_hex.resolve(),
        control_hex=args.control_hex.resolve(),
        left_addr=args.left_addr,
        right_addr=args.right_addr,
        seed_a=args.seed_a,
        seed_b=args.seed_b,
    )


if __name__ == "__main__":
    raise SystemExit(main())
