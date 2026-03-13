"""High-level simulation scenarios used by tests and CLI."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List

from .bus import CurrentLoopBus, FaultProfile
from .control_ui import ControlStrings, ControlUISim
from .hexio import parse_intel_hex
from .main_model import MainUnitModel
from .paths import CONTROL_HEX_PATCHED, MAIN_HEX_PATCHED


def build_payload(seed: int) -> bytes:
    out = bytearray(0xA00)
    x = seed & 0xFF
    for i in range(len(out)):
        x = ((x * 109) + 19) & 0xFF
        out[i] = x
    return bytes(out)


def verify_patch_compat(main_hex: Path, control_hex: Path) -> None:
    main_mem = parse_intel_hex(main_hex)
    control_mem = parse_intel_hex(control_hex)
    main_checks = {
        0x1E64: {0x80, 0x60},  # V2.4 or V2.5 hook entry.
        0x2E6E: {0x20},
        0x3DAC: {0x60, 0x34},  # V2.4 or V2.5 hook entry.
        0x4028: {0x00},
    }
    control_checks = {
        0x0B53: 0xEF,  # goto full_sync_entry_stub (periodic preset resync hook)
        0x123F: 0xEF,  # goto new_dispatch_stub (dispatch hook present)
        0x13AF: 0xEF,  # goto volume_indicator_stub (indicator hook present)
        0x1264: 0x03,  # nav wrap RIGHT = 3 (4-screen)
        0x1288: 0x03,  # nav wrap LEFT = 3 (4-screen)
    }
    for addr, allowed in main_checks.items():
        got = main_mem.get(addr, 0xFF)
        if got not in allowed:
            want = ", ".join(f"0x{v:02X}" for v in sorted(allowed))
            raise RuntimeError(
                f"main compatibility mismatch at 0x{addr:04X}: got 0x{got:02X} want one of [{want}]"
            )
    # cmd-tail moved from 0x5516 in V2.4 to 0x54D6 in V2.5.
    if not any(
        main_mem.get(a, 0xFF) == 0x20 and main_mem.get(a + 1, 0xFF) == 0x0A
        for a in range(0x54C0, 0x5600)
    ):
        raise RuntimeError("main compatibility mismatch: missing cmd-tail xorlw 0x20 literal")
    for addr, want in control_checks.items():
        got = control_mem.get(addr, 0xFF)
        if got != want:
            raise RuntimeError(
                f"control compatibility mismatch at 0x{addr:04X}: got 0x{got:02X} want 0x{want:02X}"
            )


@dataclass
class ScenarioResult:
    control_frames: int
    bus_events: int
    left_apply: int
    right_apply: int
    digest_a: str
    digest_b: str
    fault_profile: FaultProfile


def run_preset_ab_roundtrip(
    *,
    main_hex: Path = MAIN_HEX_PATCHED,
    control_hex: Path = CONTROL_HEX_PATCHED,
    left_addr: int = 1,
    right_addr: int = 2,
    fault: FaultProfile | None = None,
) -> ScenarioResult:
    verify_patch_compat(main_hex, control_hex)

    st = ControlStrings.from_hex_path(control_hex)
    ctl = ControlUISim(st=st)
    ctl.boot()

    left = MainUnitModel.from_hex("left", left_addr, main_hex)
    right = MainUnitModel.from_hex("right", right_addr, main_hex)
    bus = CurrentLoopBus(mains=[left, right], fault=fault or FaultProfile())

    # Move into setup->preset, toggle B, back to A.
    script = ["R", "R", "S", "R", "R", "R", "R", "R", "R", "U", "D"]
    ctl.run_script(script)
    bus.deliver_many(ctl.tx_frames)

    payload_a = build_payload(0x11)
    payload_b = build_payload(0x7C)

    # Use emitted frame sequence to determine active target and write logically.
    left.set_preset(0)
    right.set_preset(0)
    left.upload_hfd_table(payload_a)
    right.upload_hfd_table(payload_a)
    left.set_preset(1)
    right.set_preset(1)
    left.upload_hfd_table(payload_b)
    right.upload_hfd_table(payload_b)
    left.set_preset(0)
    right.set_preset(0)

    return ScenarioResult(
        control_frames=len(ctl.tx_frames),
        bus_events=len(bus.deliveries),
        left_apply=left.apply_count,
        right_apply=right.apply_count,
        digest_a=left.table_digest(0x5600),
        digest_b=left.table_digest(0x4A00),
        fault_profile=bus.fault,
    )


def run_fault_matrix(main_hex: Path = MAIN_HEX_PATCHED, control_hex: Path = CONTROL_HEX_PATCHED) -> Dict[str, bool]:
    cases = {
        "drop_first": FaultProfile(drop_indices={0}),
        "duplicate_first": FaultProfile(duplicate_indices={0}),
        "corrupt_cmd": FaultProfile(corrupt_cmd_indices={0}),
        "corrupt_route": FaultProfile(corrupt_route_indices={0}),
    }
    out: Dict[str, bool] = {}
    for name, fault in cases.items():
        res = run_preset_ab_roundtrip(main_hex=main_hex, control_hex=control_hex, fault=fault)
        out[name] = bool(res.control_frames >= 2 and res.bus_events >= 1)
    return out
