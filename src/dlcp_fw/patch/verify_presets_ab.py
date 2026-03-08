#!/usr/bin/env python3
"""Verify A/B preset patches for DLCP main + control firmware."""

from __future__ import annotations

import argparse
import pathlib
from dataclasses import dataclass
from typing import Dict

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX,
    PATCHED_CONTROL_HEX_V151B,
    PATCHED_CONTROL_HEX_V161B,
    PATCHED_MAIN_HEX,
    STOCK_CONTROL_HEX_V14,
    STOCK_CONTROL_HEX_V15B,
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_HEX,
)


@dataclass(frozen=True)
class ControlProfile:
    name: str
    startup_init: int
    startup_hook: int
    version_literal: int
    version_literal_byte: int
    nav_right: int
    nav_left: int
    setup_index_fix: int
    input_index_fix: int
    dispatch_hook: int
    volume_hook: int
    full_sync_hook: int
    ir_hook: int
    parser_site: int
    parser_expected: tuple[int, int]
    stock_ir_target: int
    version_tuple: tuple[int, int, int]
    volume_header_addr: int
    volume_header_text: str
    usb_guard_addr: int
    setup_fix_required: bool = False


CONTROL_V14 = ControlProfile(
    name="v14",
    startup_init=0x1106,
    startup_hook=0x116E,
    version_literal=0x11A4,
    version_literal_byte=0x29,
    nav_right=0x1264,
    nav_left=0x1288,
    setup_index_fix=0x149A,
    input_index_fix=0x1A08,
    dispatch_hook=0x123E,
    volume_hook=0x13AE,
    full_sync_hook=0x0B52,
    ir_hook=0x0E46,
    parser_site=0x05EC,
    parser_expected=(0x1D, 0x0E),
    stock_ir_target=0x0E4C,
    version_tuple=(0x01, 0x04, 0x31),
    volume_header_addr=0x1062,
    volume_header_text="Volume:         ",
    usb_guard_addr=0x16C0,
)

CONTROL_V15B = ControlProfile(
    name="v15b",
    startup_init=0x10F6,
    startup_hook=0x1160,
    version_literal=0x1196,
    version_literal_byte=0x33,
    nav_right=0x1256,
    nav_left=0x127A,
    setup_index_fix=0x148C,
    input_index_fix=0x19FA,
    dispatch_hook=0x1230,
    volume_hook=0x13A0,
    full_sync_hook=0x0B2C,
    ir_hook=0x0E32,
    parser_site=0x05C6,
    parser_expected=(0x1D, 0x0E),
    stock_ir_target=0x0E38,
    version_tuple=(0x01, 0x05, 0x31),
    volume_header_addr=0x1052,
    volume_header_text="Volume:         ",
    usb_guard_addr=0x16C0,
)

CONTROL_V16B = ControlProfile(
    name="v16b",
    startup_init=0x10B2,
    startup_hook=0x111C,
    version_literal=0x1152,
    version_literal_byte=0x3D,
    nav_right=0x1216,
    nav_left=0x123A,
    setup_index_fix=0x1406,
    input_index_fix=0x191A,
    dispatch_hook=0x11F0,
    volume_hook=0x137A,
    full_sync_hook=0x0B36,
    ir_hook=0x0DE6,
    parser_site=0x05D0,
    parser_expected=(0x1D, 0x0E),
    stock_ir_target=0x0DEC,
    version_tuple=(0x01, 0x06, 0x31),
    volume_header_addr=0x100C,
    volume_header_text="Volume:         ",
    usb_guard_addr=0x1000,
    setup_fix_required=True,
)


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0
    for lineno, line in enumerate(path.read_text(encoding="ascii").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        if not line.startswith(":"):
            raise RuntimeError(f"{path}:{lineno}: bad HEX")
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
            upper = (data[0] << 8) | data[1]
    return mem


def _decode_goto_target(mem: Dict[int, int], addr: int, *, label: str) -> int:
    w1_lo = mem.get(addr, 0xFF)
    w1_hi = mem.get(addr + 1, 0xFF)
    w2_lo = mem.get(addr + 2, 0xFF)
    w2_hi = mem.get(addr + 3, 0xFF)
    if w1_hi != 0xEF or w2_hi != 0xF0:
        raise RuntimeError(f"{label} at 0x{addr:04X} is not a goto instruction")
    return ((((w2_hi & 0x0F) << 8) | w2_lo) << 8 | w1_lo) * 2


def _decode_call_target(mem: Dict[int, int], addr: int, *, label: str) -> int:
    w1_lo = mem.get(addr, 0xFF)
    w1_hi = mem.get(addr + 1, 0xFF)
    w2_lo = mem.get(addr + 2, 0xFF)
    w2_hi = mem.get(addr + 3, 0xFF)
    if w1_hi != 0xEC or w2_hi != 0xF0:
        raise RuntimeError(f"{label} at 0x{addr:04X} is not a call instruction")
    return ((((w2_hi & 0x0F) << 8) | w2_lo) << 8 | w1_lo) * 2


def _find_seq(mem: Dict[int, int], seq: list[int], *, lo: int, hi: int) -> int | None:
    n = len(seq)
    for addr in range(lo, hi - n + 1):
        if all(mem.get(addr + i, 0xFF) == seq[i] for i in range(n)):
            return addr
    return None


def _count_seq(mem: Dict[int, int], seq: list[int], *, lo: int, hi: int) -> int:
    n = len(seq)
    count = 0
    for addr in range(lo, hi - n + 1):
        if all(mem.get(addr + i, 0xFF) == seq[i] for i in range(n)):
            count += 1
    return count


def _expect_bytes(mem: Dict[int, int], expected: Dict[int, int], *, label: str) -> None:
    for addr, want in expected.items():
        got = mem.get(addr, 0xFF)
        if got != want:
            raise RuntimeError(f"{label} mismatch at 0x{addr:04X}: got 0x{got:02X}, want 0x{want:02X}")


def _read_ascii16(mem: Dict[int, int], addr: int) -> str:
    return bytes(mem.get(addr + i, 0x20) for i in range(16)).decode("ascii", "replace")


def check_main(main_orig: Dict[int, int], main_new: Dict[int, int]) -> None:
    for i in range(0xA00):
        a = main_orig.get(0x5600 + i, 0xFF)
        b = main_new.get(0x4A00 + i, 0xFF)
        if a != b:
            raise RuntimeError(f"main table copy mismatch at +0x{i:03X}: A=0x{a:02X} B=0x{b:02X}")

    main_hooks = {
        0x1E64: 0x5500,
        0x2E6E: 0x5440,
        0x3DAC: 0x54C0,
        0x4028: 0x5400,
    }
    for addr, want in main_hooks.items():
        got = _decode_goto_target(main_new, addr, label="main hook")
        if got != want:
            raise RuntimeError(
                f"main hook target mismatch at 0x{addr:04X}: got 0x{got:04X}, want 0x{want:04X}"
            )

    for addr in (0x20BE, 0x27C0):
        orig = [main_orig.get(addr + i, 0xFF) for i in range(4)]
        new = [main_new.get(addr + i, 0xFF) for i in range(4)]
        if new != orig:
            raise RuntimeError(f"main stock cmd03 path unexpectedly changed at 0x{addr:04X}")

    for literal in (0x1D, 0x1E, 0x20):
        if _find_seq(main_new, [literal, 0x0A], lo=0x5500, hi=0x5560) is None:
            raise RuntimeError(f"main cmd-tail missing xorlw 0x{literal:02X}")
    for literal in (0x21, 0x22):
        if _find_seq(main_new, [literal, 0x0A], lo=0x5500, hi=0x5560) is not None:
            raise RuntimeError(f"main cmd-tail still contains removed xorlw 0x{literal:02X}")

    if _count_seq(main_new, [0xBA, 0xEC, 0x22, 0xF0], lo=0x5500, hi=0x5560) < 2:
        raise RuntimeError("main cmd-tail missing dual apply calls for cmd=0x20")

    main_ver = [main_new.get(a, 0xFF) for a in (0xF00080, 0xF00081, 0xF00082)]
    if main_ver != [0x02, 0x03, 0x30]:
        raise RuntimeError(
            f"main EEPROM version tuple mismatch: got {[hex(x) for x in main_ver]}, want [0x2,0x3,0x30]"
        )
    orig_ver = [main_orig.get(a, 0xFF) for a in (0xF00080, 0xF00081, 0xF00082)]
    if main_ver != orig_ver:
        raise RuntimeError(
            f"main EEPROM version tuple drift vs stock: new={[hex(x) for x in main_ver]} orig={[hex(x) for x in orig_ver]}"
        )

    _expect_bytes(
        main_new,
        {0x240C: 0x03, 0x2412: 0x02, 0x2416: 0x04},
        label="main USB version literal",
    )


def _check_control_profile(
    control_orig: Dict[int, int],
    control_new: Dict[int, int],
    profile: ControlProfile,
) -> None:
    _expect_bytes(
        control_new,
        {
            profile.startup_init: 0x1F,
            profile.startup_init + 1: 0x96,
            profile.startup_init + 2: 0x1F,
            profile.startup_init + 3: 0x98,
            profile.version_literal: profile.version_literal_byte,
            profile.version_literal + 1: 0x0E,
            profile.nav_right: 0x03,
            profile.nav_right + 1: 0x0E,
            profile.nav_left: 0x03,
            profile.nav_left + 1: 0x0E,
            profile.setup_index_fix: 0x02,
            profile.setup_index_fix + 1: 0x0E,
            profile.setup_index_fix + 3: 0x6E,
            profile.input_index_fix: 0x01,
            profile.input_index_fix + 1: 0x0E,
            profile.input_index_fix + 3: 0x6E,
        },
        label=f"control {profile.name}",
    )

    boot_target = _decode_call_target(control_new, profile.startup_hook, label="control startup hook")
    if not (0x7000 <= boot_target < 0x7300):
        raise RuntimeError(f"control startup hook target out of stub range: 0x{boot_target:04X}")

    dispatch_target = _decode_goto_target(control_new, profile.dispatch_hook, label="control dispatch hook")
    if not (0x7000 <= dispatch_target < 0x7300):
        raise RuntimeError(f"control dispatch hook target out of stub range: 0x{dispatch_target:04X}")

    volume_target = _decode_goto_target(control_new, profile.volume_hook, label="control volume hook")
    if not (0x7000 <= volume_target < 0x7300):
        raise RuntimeError(f"control volume hook target out of stub range: 0x{volume_target:04X}")

    full_sync_target = _decode_goto_target(control_new, profile.full_sync_hook, label="control full-sync hook")
    if not (0x7000 <= full_sync_target < 0x7300):
        raise RuntimeError(f"control full-sync hook target out of stub range: 0x{full_sync_target:04X}")

    ir_target = _decode_goto_target(control_new, profile.ir_hook, label="control IR dispatch hook")
    if ir_target == profile.stock_ir_target:
        raise RuntimeError(
            f"control IR dispatch hook target drifted to stock target (0x{profile.stock_ir_target:04X})"
        )
    if not (0x7000 <= ir_target < 0x7300):
        raise RuntimeError(f"control IR dispatch hook target out of stub range: 0x{ir_target:04X}")

    parser_bytes = [control_new.get(profile.parser_site + i, 0xFF) for i in range(2)]
    if tuple(parser_bytes) != profile.parser_expected:
        raise RuntimeError(
            f"control parser site drift at 0x{profile.parser_site:04X}: got {parser_bytes}, want {list(profile.parser_expected)}"
        )

    if _find_seq(control_new, [0x74, 0x0E, 0xA9, 0x6E], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control stub missing EEPROM[0x74] preset persistence")
    if _find_seq(control_new, [0x73, 0x0E, 0xA9, 0x6E], lo=0x7000, hi=0x7300) is not None:
        raise RuntimeError("control stub still writes preset persistence to EEPROM[0x73]")
    if _find_seq(control_new, [0x72, 0x0E, 0xA9, 0x6E], lo=0x7000, hi=0x7300) is not None:
        raise RuntimeError("control stub still writes preset persistence to EEPROM[0x72]")

    if _find_seq(control_new, [0xB0, 0x0E], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control stub missing route=0xB0 sender")
    if _find_seq(control_new, [0x20, 0x0E], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control stub missing cmd=0x20 sender")
    if _find_seq(control_new, [0x02, 0x0E, 0x01, 0x01, 0x70, 0x6F], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control stub missing 2-retry budget seed after explicit preset change")
    if _count_seq(control_new, [0x01, 0x01, 0x03, 0x0E, 0x70, 0x6F], lo=0x7000, hi=0x7300) < 1:
        raise RuntimeError("control stub missing 3-retry seed signature")
    if _find_seq(control_new, [0x71, 0x6B], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control stub missing reconnect shadow clear (0x171)")
    if _find_seq(control_new, [0x71, 0x6F], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control stub missing reconnect shadow set (0x171)")

    if _find_seq(control_new, [0x38, 0x0A], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control IR preset shortcut missing xorlw 0x38 (F1->preset A)")
    if _find_seq(control_new, [0x39, 0x0A], lo=0x7000, hi=0x7300) is None:
        raise RuntimeError("control IR preset shortcut missing xorlw 0x39 (F2->preset B)")

    if _find_seq(control_new, [0x21, 0x0E], lo=0x7000, hi=0x7300) is not None:
        raise RuntimeError("control stub still contains removed filename cmd literal 0x21")
    if _find_seq(control_new, [0x22, 0x0E], lo=0x7000, hi=0x7300) is not None:
        raise RuntimeError("control stub still contains removed filename cmd literal 0x22")
    if _find_seq(control_new, [0x2F, 0x0E], lo=0x7000, hi=0x7300) is not None:
        raise RuntimeError("control stub still contains removed filename context literal 0x2F")

    version = [control_new.get(a, 0xFF) for a in (0xF00070, 0xF00071, 0xF00072)]
    if version != list(profile.version_tuple):
        raise RuntimeError(
            f"control version tuple mismatch: got {[hex(x) for x in version]}, want {[hex(x) for x in profile.version_tuple]}"
        )

    vol_hdr = _read_ascii16(control_new, profile.volume_header_addr)
    if vol_hdr != profile.volume_header_text:
        raise RuntimeError(f"control Volume header changed: {vol_hdr!r}")
    app_window = bytes(control_new.get(a, 0x20) for a in range(profile.usb_guard_addr, 0x1B00))
    if b"USB" not in app_window:
        raise RuntimeError("control USBaudio label missing from app text window")

    if profile.setup_fix_required:
        seq = [0xBA, 0x51, 0x06, 0xE0, 0xBA, 0x6B, 0x01, 0x0E, 0xA9, 0x6E]
        if _find_seq(control_new, seq, lo=0x7000, hi=0x7300) is None:
            raise RuntimeError("control stale setup-index clamp signature missing")

    if control_orig.get(profile.nav_right, 0xFF) != 0x02:
        raise RuntimeError(f"control original mismatch at 0x{profile.nav_right:04X} (expected movlw 0x02)")
    if control_orig.get(profile.dispatch_hook, 0xFF) != 0xBF:
        raise RuntimeError(
            f"control original mismatch at 0x{profile.dispatch_hook:04X} (expected decfsz 0xBF)"
        )
    if tuple(control_orig.get(profile.parser_site + i, 0xFF) for i in range(2)) != profile.parser_expected:
        raise RuntimeError(
            f"control original parser-site mismatch at 0x{profile.parser_site:04X}"
        )


def check_control(control_orig: Dict[int, int], control_new: Dict[int, int]) -> None:
    _check_control_profile(control_orig, control_new, CONTROL_V14)


def check_control_v15b(control_orig: Dict[int, int], control_new: Dict[int, int]) -> None:
    _check_control_profile(control_orig, control_new, CONTROL_V15B)


def check_control_v16b(control_orig: Dict[int, int], control_new: Dict[int, int]) -> None:
    _check_control_profile(control_orig, control_new, CONTROL_V16B)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--main-orig", type=pathlib.Path, default=STOCK_MAIN_HEX)
    ap.add_argument("--main-new", type=pathlib.Path, default=PATCHED_MAIN_HEX)
    ap.add_argument("--control-orig", type=pathlib.Path, default=STOCK_CONTROL_HEX_V14)
    ap.add_argument("--control-new", type=pathlib.Path, default=PATCHED_CONTROL_HEX)
    ap.add_argument(
        "--control-profile",
        choices=("auto", "v14", "v15b", "v16b"),
        default="auto",
        help="control firmware profile for verification (default: auto)",
    )
    ap.add_argument(
        "--control-new-v151b",
        action="store_true",
        help="shortcut: set --control-orig to stock V1.5b and --control-new to patched V1.51b",
    )
    ap.add_argument(
        "--control-new-v161b",
        action="store_true",
        help="shortcut: set --control-orig to stock V1.6b and --control-new to patched V1.61b",
    )
    args = ap.parse_args()

    if args.control_new_v151b:
        args.control_orig = STOCK_CONTROL_HEX_V15B
        args.control_new = PATCHED_CONTROL_HEX_V151B
    if args.control_new_v161b:
        args.control_orig = STOCK_CONTROL_HEX_V16B
        args.control_new = PATCHED_CONTROL_HEX_V161B

    main_orig = parse_intel_hex(args.main_orig.resolve())
    main_new = parse_intel_hex(args.main_new.resolve())
    control_orig = parse_intel_hex(args.control_orig.resolve())
    control_new = parse_intel_hex(args.control_new.resolve())

    check_main(main_orig, main_new)

    profile = args.control_profile
    if profile == "auto":
        if control_orig.get(0x10B2, 0xFF) == 0x1F and control_orig.get(0x111C, 0xFF) == 0x23:
            profile = "v16b"
        elif control_orig.get(0x10F6, 0xFF) == 0x1F and control_orig.get(0x1160, 0xFF) == 0x1E:
            profile = "v15b"
        else:
            profile = "v14"

    if profile == "v14":
        check_control(control_orig, control_new)
    elif profile == "v15b":
        check_control_v15b(control_orig, control_new)
    else:
        check_control_v16b(control_orig, control_new)

    print("OK: main + control preset A/B patches validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
