#!/usr/bin/env python3
"""
Verify A/B preset patches for DLCP main + control firmware.
"""

from __future__ import annotations

import argparse
import pathlib
from typing import Dict

from dlcp_fw.paths import PATCHED_CONTROL_HEX, PATCHED_MAIN_HEX, STOCK_CONTROL_HEX_V14, STOCK_MAIN_HEX


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


def check_main(main_orig: Dict[int, int], main_new: Dict[int, int]) -> None:
    # A->B table copy check
    for i in range(0xA00):
        a = main_orig.get(0x5600 + i, 0xFF)
        b = main_new.get(0x4A00 + i, 0xFF)
        if a != b:
            raise RuntimeError(f"main table copy mismatch at +0x{i:03X}: A=0x{a:02X} B=0x{b:02X}")

    # Hook signatures (little-endian bytes)
    expected = {
        0x1E64: 0x90,  # goto 0x5520 (little-endian)
        0x2E6E: 0x20,  # goto 0x5440
        0x3DAC: 0x60,  # goto 0x54C0
        0x4028: 0x00,  # goto 0x5400
    }
    for a, want in expected.items():
        got = main_new.get(a, 0xFF)
        if got != want:
            raise RuntimeError(f"main hook mismatch at 0x{a:04X}: got 0x{got:02X}, want 0x{want:02X}")

    # cmd tail guard checks: preserve legacy compares and append cmd=0x20.
    cmd_tail_expected = {
        0x5522: 0x1D,  # xorlw 0x1D -> goto 0x1E02 (legacy cmd 0x1D)
        0x5526: 0x01,
        0x5527: 0xEF,
        0x5528: 0x0F,
        0x5529: 0xF0,
        0x552C: 0x1E,  # xorlw 0x1E -> goto 0x1E1C (legacy cmd 0x1E)
        0x5530: 0x0E,
        0x5531: 0xEF,
        0x5532: 0x0F,
        0x5533: 0xF0,
        0x5536: 0x20,  # xorlw 0x20 (new preset command)
        # Idempotent cmd=0x20 apply paths:
        # - A-path: only apply when bit2 was set
        0x5540: 0x5E,  # btfss 0x05E,2
        0x5541: 0xA4,
        0x5546: 0x5E,  # bcf 0x05E,2
        0x5547: 0x94,
        0x5548: 0xBA,  # call 0x4574
        0x5549: 0xEC,
        0x554A: 0x22,
        0x554B: 0xF0,
        # - B-path: only apply when bit2 was clear
        0x5550: 0x5E,  # btfsc 0x05E,2
        0x5551: 0xB4,
        0x5556: 0x5E,  # bsf 0x05E,2
        0x5557: 0x84,
        0x5558: 0xBA,  # call 0x4574
        0x5559: 0xEC,
        0x555A: 0x22,
        0x555B: 0xF0,
    }
    for a, want in cmd_tail_expected.items():
        got = main_new.get(a, 0xFF)
        if got != want:
            raise RuntimeError(
                f"main cmd-tail guard mismatch at 0x{a:04X}: got 0x{got:02X}, want 0x{want:02X}"
            )

    # MAIN EEPROM tuple must remain stock 2.30 (revert prior 2.31 tweak).
    main_ver = [main_new.get(a, 0xFF) for a in (0xF00080, 0xF00081, 0xF00082)]
    if main_ver != [0x02, 0x03, 0x30]:
        raise RuntimeError(
            f"main EEPROM version tuple mismatch: got {[hex(x) for x in main_ver]}, want [0x2,0x3,0x30]"
        )
    orig_ver = [main_orig.get(a, 0xFF) for a in (0xF00080, 0xF00081, 0xF00082)]
    if main_ver != orig_ver:
        raise RuntimeError(
            f"main EEPROM version tuple drift vs stock: new={[hex(x) for x in main_ver]} "
            f"orig={[hex(x) for x in orig_ver]}"
        )

    # USB host info response literal should report 2.4 (cmd=0x06, subcmd=0x03 path).
    usb_ver_expected = {
        0x240C: 0x03,
        0x2412: 0x02,
        0x2416: 0x04,
    }
    for a, want in usb_ver_expected.items():
        got = main_new.get(a, 0xFF)
        if got != want:
            raise RuntimeError(
                f"main USB version literal mismatch at 0x{a:04X}: got 0x{got:02X}, want 0x{want:02X}"
            )


def check_control(control_orig: Dict[int, int], control_new: Dict[int, int]) -> None:
    # Keep stock BL-timeout clamp behavior (preset no longer uses 0x0EB/0x73 path).
    if control_new.get(0x0B1E, 0xFF) != 0x05 or control_new.get(0x0B1F, 0xFF) != 0x0E:
        raise RuntimeError("control BL-timeout clamp unexpectedly changed at 0x0B1E")
    if control_new.get(0x0B28, 0xFF) != 0x01 or control_new.get(0x0B29, 0xFF) != 0x0E:
        raise RuntimeError("control BL-timeout default unexpectedly changed at 0x0B28")

    # --- Patch 0: startup state init ---
    # 0x1106: clrf 0x01F,ACCESS (deterministic init for preset/latch bits)
    if control_new.get(0x1106, 0xFF) != 0x1F or control_new.get(0x1107, 0xFF) != 0x6A:
        raise RuntimeError("control startup flag init missing at 0x1106 (expected clrf 0x01F)")
    # 0x116E: call preset_boot_init_wrapper in stub area.
    if control_new.get(0x116F, 0xFF) != 0xEC or control_new.get(0x1171, 0xFF) != 0xF0:
        raise RuntimeError("control startup preset-load hook missing at 0x116E")

    # --- Patch 1: Navigation wrap (movlw 0x03) ---
    for addr, label in [(0x1264, "RIGHT"), (0x1288, "LEFT")]:
        got = control_new.get(addr, 0xFF)
        if got != 0x03:
            raise RuntimeError(
                f"control nav wrap {label} at 0x{addr:04X}: got 0x{got:02X}, want 0x03"
            )

    # --- Patch 2: String table index fixes ---
    # function_047 (Setup): movlw 0x02; movwf 0x027
    if control_new.get(0x149A, 0xFF) != 0x02 or control_new.get(0x149B, 0xFF) != 0x0E:
        raise RuntimeError("control string index fix missing at 0x149A (Setup)")
    if control_new.get(0x149D, 0xFF) != 0x6E:
        raise RuntimeError("control string index fix missing at 0x149C (Setup movwf)")
    # function_052 (Input): movlw 0x01; movwf 0x027
    if control_new.get(0x1A08, 0xFF) != 0x01 or control_new.get(0x1A09, 0xFF) != 0x0E:
        raise RuntimeError("control string index fix missing at 0x1A08 (Input)")
    if control_new.get(0x1A0B, 0xFF) != 0x6E:
        raise RuntimeError("control string index fix missing at 0x1A0A (Input movwf)")

    # --- Patch 3: Dispatch redirect at 0x123E ---
    # Must be a goto (EFxx Fxxx) to 0x7000 area
    if control_new.get(0x123F, 0xFF) != 0xEF:
        raise RuntimeError("control dispatch hook at 0x123E not a goto instruction")
    if control_new.get(0x7000, 0xFF) == 0xFF:
        raise RuntimeError("control dispatch stub missing at 0x7000")

    # --- Patch 4: Volume indicator hook at 0x13AE ---
    # Must be a goto (EFxx Fxxx) to stub area
    if control_new.get(0x13AF, 0xFF) != 0xEF:
        raise RuntimeError("control volume indicator hook at 0x13AE not a goto instruction")

    # --- Patch 5: Full-sync entry hook at 0x0B52 ---
    # Must be a goto to stub area (replacing clrf/movlw prologue).
    if control_new.get(0x0B53, 0xFF) != 0xEF:
        raise RuntimeError(
            f"control full-sync hook mismatch at 0x0B53: got 0x{control_new.get(0x0B53, 0xFF):02X}, want 0xEF"
        )
    if control_new.get(0x0B55, 0xFF) != 0xF0:
        raise RuntimeError(
            f"control full-sync hook mismatch at 0x0B55: got 0x{control_new.get(0x0B55, 0xFF):02X}, want 0xF0"
        )

    # --- Patch 6: IR dispatch pre-hook at 0x0E46 ---
    # Verify this is a goto and that it targets the new 0x7000 stub area,
    # not the stock label_166 dispatch at 0x0E4C.
    ir_w1_lo = control_new.get(0x0E46, 0xFF)
    ir_w1_hi = control_new.get(0x0E47, 0xFF)
    ir_w2_lo = control_new.get(0x0E48, 0xFF)
    ir_w2_hi = control_new.get(0x0E49, 0xFF)
    if ir_w1_hi != 0xEF or ir_w2_hi != 0xF0:
        raise RuntimeError("control IR dispatch hook at 0x0E46 not a goto instruction")
    # PIC18 GOTO encoding (byte-address target):
    # target = (((word2_low12 << 8) | word1_low8) * 2).
    ir_target = ((((ir_w2_hi & 0x0F) << 8) | ir_w2_lo) << 8 | ir_w1_lo) * 2
    if ir_target == 0x0E4C:
        raise RuntimeError("control IR dispatch hook target drifted to stock label_166 (0x0E4C)")
    if not (0x7000 <= ir_target < 0x7200):
        raise RuntimeError(
            f"control IR dispatch hook target out of stub range: 0x{ir_target:04X} (want 0x7000..0x71FF)"
        )

    # Full-sync stub must call the TX-only preset sender (same call target as
    # send_preset_frame's first instruction), but avoid hard-coded stub offsets.
    def _find_seq(seq: list[int], lo: int = 0x7000, hi: int = 0x7200) -> int | None:
        n = len(seq)
        for a in range(lo, hi - n + 1):
            if all(control_new.get(a + i, 0xFF) == seq[i] for i in range(n)):
                return a
        return None

    full_sync_anchor = _find_seq([0x28, 0x6A, 0x06, 0x0E, 0x28, 0x60])  # clrf 0x028; movlw 0x06; cpfslt 0x028
    if full_sync_anchor is None or full_sync_anchor < 0x7004:
        raise RuntimeError("control full-sync stub signature not found in 0x7000 stub area")
    full_sync_call = [control_new.get(a, 0xFF) for a in range(full_sync_anchor - 4, full_sync_anchor)]
    if full_sync_call[1] != 0xEC or full_sync_call[3] != 0xF0:
        raise RuntimeError("control full-sync stub missing call to TX-only preset sender")

    send_persist_anchor = _find_seq([0x74, 0x0E, 0xA9, 0x6E])  # movlw 0x74; movwf EEADR
    if send_persist_anchor is None or send_persist_anchor < 0x7004:
        raise RuntimeError("control send_preset_frame persistence signature missing (EEPROM[0x74])")
    send_persist_call = [control_new.get(a, 0xFF) for a in range(send_persist_anchor - 4, send_persist_anchor)]
    if send_persist_call[1] != 0xEC or send_persist_call[3] != 0xF0:
        raise RuntimeError("control send_preset_frame missing initial TX-only call")
    if full_sync_call != send_persist_call:
        raise RuntimeError("control full-sync stub not linked to same TX-only sender as send_preset_frame")

    # Ensure the new preset persistence byte is used in stub code.
    if _find_seq([0x73, 0x0E, 0xA9, 0x6E]) is not None:
        raise RuntimeError("control stub still writes preset persistence to EEPROM[0x73]")
    if _find_seq([0x72, 0x0E, 0xA9, 0x6E]) is not None:
        raise RuntimeError("control stub still writes preset persistence to EEPROM[0x72]")

    # IR preset shortcuts must exist in stub code: xorlw 0x38 and xorlw 0x39.
    if _find_seq([0x38, 0x0A]) is None:
        raise RuntimeError("control IR preset shortcut missing xorlw 0x38 (F1->preset A)")
    if _find_seq([0x39, 0x0A]) is None:
        raise RuntimeError("control IR preset shortcut missing xorlw 0x39 (F2->preset B)")

    # Verify stub calls function_042 (0x0D24) at some point
    found_fn042 = False
    for a in range(0x7000, 0x7200, 2):
        lo = control_new.get(a, 0xFF)
        hi = control_new.get(a + 1, 0xFF)
        # call 0x0D24: EC92 F006 -> bytes 92 EC 06 F0
        if lo == 0x92 and hi == 0xEC:
            nxt_lo = control_new.get(a + 2, 0xFF)
            nxt_hi = control_new.get(a + 3, 0xFF)
            if nxt_lo == 0x06 and nxt_hi == 0xF0:
                found_fn042 = True
                break
    if not found_fn042:
        raise RuntimeError("control stub area missing call to function_042 (0x0D24)")

    # Verify send_preset_frame emits route 0xB0, cmd 0x20
    found_b0 = False
    found_20 = False
    for a in range(0x7000, 0x7200, 2):
        lo = control_new.get(a, 0xFF)
        hi = control_new.get(a + 1, 0xFF)
        if lo == 0xB0 and hi == 0x0E:  # movlw 0xB0
            found_b0 = True
        if lo == 0x20 and hi == 0x0E and found_b0:  # movlw 0x20
            found_20 = True
            break
    if not (found_b0 and found_20):
        raise RuntimeError("control stub missing send_preset_frame (route=0xB0, cmd=0x20)")

    # CONTROL version tuple should be 1.41 (EEPROM 0x70..0x72) and startup
    # splash literal should render "1.41" (minor literal movlw 0x29).
    control_ver = [control_new.get(a, 0xFF) for a in (0xF00070, 0xF00071, 0xF00072)]
    if control_ver != [0x01, 0x04, 0x31]:
        raise RuntimeError(
            f"control version tuple mismatch: got {[hex(x) for x in control_ver]}, want [0x1,0x4,0x31]"
        )
    if control_new.get(0x11A4, 0xFF) != 0x29 or control_new.get(0x11A5, 0xFF) != 0x0E:
        raise RuntimeError("control startup splash literal mismatch at 0x11A4 (expected movlw 0x29)")

    # --- Text labels preserved (USBaudio NOT overwritten) ---
    def s(addr: int) -> str:
        return bytes(control_new.get(addr + i, 0x20) for i in range(16)).decode("ascii", "replace")

    vol_hdr = s(0x1062)
    if vol_hdr != "Volume:         ":
        raise RuntimeError(f"control Volume header changed: {vol_hdr!r}")
    usb_lbl = s(0x16C0)
    if not usb_lbl.startswith("USB"):
        raise RuntimeError(f"control USBaudio label overwritten: {usb_lbl!r}")

    # Original should still have old bytes at key locations
    if control_orig.get(0x1264, 0x00) != 0x02:
        raise RuntimeError("control original mismatch at 0x1264 (expected movlw 0x02)")
    if control_orig.get(0x123E, 0x00) != 0xBF:
        raise RuntimeError("control original mismatch at 0x123E (expected decfsz 0xBF)")
    if control_orig.get(0x0B52, 0x00) != 0x28:
        raise RuntimeError("control original mismatch at 0x0B52 (expected clrf 0x028)")
    if (
        control_orig.get(0x0E46, 0x00) != 0x26
        or control_orig.get(0x0E47, 0x00) != 0xEF
        or control_orig.get(0x0E48, 0x00) != 0x07
        or control_orig.get(0x0E49, 0x00) != 0xF0
    ):
        raise RuntimeError("control original mismatch at 0x0E46 (expected goto label_166)")
    if control_orig.get(0x1106, 0x00) != 0x1F or control_orig.get(0x1107, 0x00) != 0x96:
        raise RuntimeError("control original mismatch at 0x1106 (expected bcf 0x01F,3)")
    if (
        control_orig.get(0x116E, 0x00) != 0x31
        or control_orig.get(0x116F, 0x00) != 0xEC
        or control_orig.get(0x1170, 0x00) != 0x05
        or control_orig.get(0x1171, 0x00) != 0xF0
    ):
        raise RuntimeError("control original mismatch at 0x116E (expected call function_026)")
    if control_orig.get(0x11A4, 0x00) != 0x04 or control_orig.get(0x11A5, 0x00) != 0x0E:
        raise RuntimeError("control original mismatch at 0x11A4 (expected movlw 0x04)")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--main-orig",
        type=pathlib.Path,
        default=STOCK_MAIN_HEX,
    )
    ap.add_argument(
        "--main-new",
        type=pathlib.Path,
        default=PATCHED_MAIN_HEX,
    )
    ap.add_argument(
        "--control-orig",
        type=pathlib.Path,
        default=STOCK_CONTROL_HEX_V14,
    )
    ap.add_argument(
        "--control-new",
        type=pathlib.Path,
        default=PATCHED_CONTROL_HEX,
    )
    args = ap.parse_args()

    main_orig = parse_intel_hex(args.main_orig.resolve())
    main_new = parse_intel_hex(args.main_new.resolve())
    control_orig = parse_intel_hex(args.control_orig.resolve())
    control_new = parse_intel_hex(args.control_new.resolve())

    check_main(main_orig, main_new)
    check_control(control_orig, control_new)

    print("OK: main + control preset A/B patches validated.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
