#!/usr/bin/env python3
"""
Verify A/B preset patches for DLCP main + control firmware.
"""

from __future__ import annotations

import argparse
import pathlib
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


def check_control_v15b(control_orig: Dict[int, int], control_new: Dict[int, int]) -> None:
    # Keep stock BL-timeout clamp behavior (preset no longer uses 0x0EB/0x73 path).
    if control_new.get(0x0AF8, 0xFF) != 0x05 or control_new.get(0x0AF9, 0xFF) != 0x0E:
        raise RuntimeError("control BL-timeout clamp unexpectedly changed at 0x0AF8")
    if control_new.get(0x0B02, 0xFF) != 0x01 or control_new.get(0x0B03, 0xFF) != 0x0E:
        raise RuntimeError("control BL-timeout default unexpectedly changed at 0x0B02")

    # --- Patch 0: startup state init ---
    # 0x10F6: clrf 0x01F,ACCESS (deterministic init for preset/latch bits)
    if control_new.get(0x10F6, 0xFF) != 0x1F or control_new.get(0x10F7, 0xFF) != 0x6A:
        raise RuntimeError("control startup flag init missing at 0x10F6 (expected clrf 0x01F)")
    # 0x1160: call preset_boot_init_wrapper in stub area.
    if control_new.get(0x1161, 0xFF) != 0xEC or control_new.get(0x1163, 0xFF) != 0xF0:
        raise RuntimeError("control startup preset-load hook missing at 0x1160")

    # --- Patch 1: Navigation wrap (movlw 0x03) ---
    for addr, label in [(0x1256, "RIGHT"), (0x127A, "LEFT")]:
        got = control_new.get(addr, 0xFF)
        if got != 0x03:
            raise RuntimeError(
                f"control nav wrap {label} at 0x{addr:04X}: got 0x{got:02X}, want 0x03"
            )

    # --- Patch 2: String table index fixes ---
    # function_047 (Setup): movlw 0x02; movwf 0x027
    if control_new.get(0x148C, 0xFF) != 0x02 or control_new.get(0x148D, 0xFF) != 0x0E:
        raise RuntimeError("control string index fix missing at 0x148C (Setup)")
    if control_new.get(0x148F, 0xFF) != 0x6E:
        raise RuntimeError("control string index fix missing at 0x148E (Setup movwf)")
    # function_052 (Input): movlw 0x01; movwf 0x027
    if control_new.get(0x19FA, 0xFF) != 0x01 or control_new.get(0x19FB, 0xFF) != 0x0E:
        raise RuntimeError("control string index fix missing at 0x19FA (Input)")
    if control_new.get(0x19FD, 0xFF) != 0x6E:
        raise RuntimeError("control string index fix missing at 0x19FC (Input movwf)")

    # --- Patch 3: Dispatch redirect at 0x1230 ---
    # Must be a goto (EFxx Fxxx) to 0x7000 area
    if control_new.get(0x1231, 0xFF) != 0xEF:
        raise RuntimeError("control dispatch hook at 0x1230 not a goto instruction")
    if control_new.get(0x7000, 0xFF) == 0xFF:
        raise RuntimeError("control dispatch stub missing at 0x7000")

    # --- Patch 4: Volume indicator hook at 0x13A0 ---
    # Must be a goto (EFxx Fxxx) to stub area
    if control_new.get(0x13A1, 0xFF) != 0xEF:
        raise RuntimeError("control volume indicator hook at 0x13A0 not a goto instruction")

    # --- Patch 5: Full-sync entry hook at 0x0B2C ---
    # Must be a goto to stub area (replacing clrf/movlw prologue).
    if control_new.get(0x0B2D, 0xFF) != 0xEF:
        raise RuntimeError(
            f"control full-sync hook mismatch at 0x0B2D: got 0x{control_new.get(0x0B2D, 0xFF):02X}, want 0xEF"
        )
    if control_new.get(0x0B2F, 0xFF) != 0xF0:
        raise RuntimeError(
            f"control full-sync hook mismatch at 0x0B2F: got 0x{control_new.get(0x0B2F, 0xFF):02X}, want 0xF0"
        )

    # --- Patch 6: IR dispatch pre-hook at 0x0E32 ---
    # Verify this is a goto and that it targets the new 0x7000 stub area,
    # not the stock label_164 dispatch at 0x0E38.
    ir_w1_lo = control_new.get(0x0E32, 0xFF)
    ir_w1_hi = control_new.get(0x0E33, 0xFF)
    ir_w2_lo = control_new.get(0x0E34, 0xFF)
    ir_w2_hi = control_new.get(0x0E35, 0xFF)
    if ir_w1_hi != 0xEF or ir_w2_hi != 0xF0:
        raise RuntimeError("control IR dispatch hook at 0x0E32 not a goto instruction")
    # PIC18 GOTO encoding (byte-address target):
    # target = (((word2_low12 << 8) | word1_low8) * 2).
    ir_target = ((((ir_w2_hi & 0x0F) << 8) | ir_w2_lo) << 8 | ir_w1_lo) * 2
    if ir_target == 0x0E38:
        raise RuntimeError("control IR dispatch hook target drifted to stock label_164 (0x0E38)")
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

    # Verify stub calls function_042 (0x0CFE) at some point.
    found_fn042 = False
    for a in range(0x7000, 0x7200, 2):
        lo = control_new.get(a, 0xFF)
        hi = control_new.get(a + 1, 0xFF)
        # call 0x0CFE: EC7F F006 -> bytes 7F EC 06 F0
        if lo == 0x7F and hi == 0xEC:
            nxt_lo = control_new.get(a + 2, 0xFF)
            nxt_hi = control_new.get(a + 3, 0xFF)
            if nxt_lo == 0x06 and nxt_hi == 0xF0:
                found_fn042 = True
                break
    if not found_fn042:
        raise RuntimeError("control stub area missing call to function_042 (0x0CFE)")

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

    # CONTROL version tuple should be 1.51 (EEPROM 0x70..0x72) and startup
    # splash literal should render "1.51" (minor literal movlw 0x33).
    control_ver = [control_new.get(a, 0xFF) for a in (0xF00070, 0xF00071, 0xF00072)]
    if control_ver != [0x01, 0x05, 0x31]:
        raise RuntimeError(
            f"control version tuple mismatch: got {[hex(x) for x in control_ver]}, want [0x1,0x5,0x31]"
        )
    if control_new.get(0x1196, 0xFF) != 0x33 or control_new.get(0x1197, 0xFF) != 0x0E:
        raise RuntimeError("control startup splash literal mismatch at 0x1196 (expected movlw 0x33)")

    # --- Text labels preserved (USBaudio NOT overwritten) ---
    def s(addr: int) -> str:
        return bytes(control_new.get(addr + i, 0x20) for i in range(16)).decode("ascii", "replace")

    vol_hdr = s(0x1052)
    if vol_hdr != "Volume:         ":
        raise RuntimeError(f"control Volume header changed: {vol_hdr!r}")
    app_window = bytes(control_new.get(a, 0x20) for a in range(0x1000, 0x1B00))
    if b"USBaudio" not in app_window:
        raise RuntimeError("control USBaudio label missing from app text window")

    # Original should still have old bytes at key locations.
    if control_orig.get(0x1256, 0x00) != 0x02:
        raise RuntimeError("control original mismatch at 0x1256 (expected movlw 0x02)")
    if control_orig.get(0x1230, 0x00) != 0xBF:
        raise RuntimeError("control original mismatch at 0x1230 (expected decfsz 0xBF)")
    if control_orig.get(0x0B2C, 0x00) != 0x28:
        raise RuntimeError("control original mismatch at 0x0B2C (expected clrf 0x028)")
    if (
        control_orig.get(0x0E32, 0x00) != 0x1C
        or control_orig.get(0x0E33, 0x00) != 0xEF
        or control_orig.get(0x0E34, 0x00) != 0x07
        or control_orig.get(0x0E35, 0x00) != 0xF0
    ):
        raise RuntimeError("control original mismatch at 0x0E32 (expected goto label_164)")
    if control_orig.get(0x10F6, 0x00) != 0x1F or control_orig.get(0x10F7, 0x00) != 0x96:
        raise RuntimeError("control original mismatch at 0x10F6 (expected bcf 0x01F,3)")
    if (
        control_orig.get(0x1160, 0x00) != 0x1E
        or control_orig.get(0x1161, 0x00) != 0xEC
        or control_orig.get(0x1162, 0x00) != 0x05
        or control_orig.get(0x1163, 0x00) != 0xF0
    ):
        raise RuntimeError("control original mismatch at 0x1160 (expected call function_026)")
    if control_orig.get(0x1196, 0x00) != 0x04 or control_orig.get(0x1197, 0x00) != 0x0E:
        raise RuntimeError("control original mismatch at 0x1196 (expected movlw 0x04)")


def check_control_v16b(control_orig: Dict[int, int], control_new: Dict[int, int]) -> None:
    # Keep stock BL-timeout clamp behavior (preset no longer uses 0x0EB/0x73 path).
    if control_new.get(0x0B02, 0xFF) != 0x05 or control_new.get(0x0B03, 0xFF) != 0x0E:
        raise RuntimeError("control BL-timeout clamp unexpectedly changed at 0x0B02")
    if control_new.get(0x0B0C, 0xFF) != 0x01 or control_new.get(0x0B0D, 0xFF) != 0x0E:
        raise RuntimeError("control BL-timeout default unexpectedly changed at 0x0B0C")

    # --- Patch 0: startup state init ---
    # 0x10B2: clrf 0x01F,ACCESS (deterministic init for preset/latch bits)
    if control_new.get(0x10B2, 0xFF) != 0x1F or control_new.get(0x10B3, 0xFF) != 0x6A:
        raise RuntimeError("control startup flag init missing at 0x10B2 (expected clrf 0x01F)")
    # 0x111C: call preset_boot_init_wrapper in stub area.
    if control_new.get(0x111D, 0xFF) != 0xEC or control_new.get(0x111F, 0xFF) != 0xF0:
        raise RuntimeError("control startup preset-load hook missing at 0x111C")

    # --- Patch 1: Navigation wrap (movlw 0x03) ---
    for addr, label in [(0x1216, "RIGHT"), (0x123A, "LEFT")]:
        got = control_new.get(addr, 0xFF)
        if got != 0x03:
            raise RuntimeError(
                f"control nav wrap {label} at 0x{addr:04X}: got 0x{got:02X}, want 0x03"
            )

    # --- Patch 2: String table index fixes ---
    # function_040 (Setup): movlw 0x02; movwf 0x027
    if control_new.get(0x1406, 0xFF) != 0x02 or control_new.get(0x1407, 0xFF) != 0x0E:
        raise RuntimeError("control string index fix missing at 0x1406 (Setup)")
    if control_new.get(0x1409, 0xFF) != 0x6E:
        raise RuntimeError("control string index fix missing at 0x1408 (Setup movwf)")
    # function_044 (Input): movlw 0x01; movwf 0x027
    if control_new.get(0x191A, 0xFF) != 0x01 or control_new.get(0x191B, 0xFF) != 0x0E:
        raise RuntimeError("control string index fix missing at 0x191A (Input)")
    if control_new.get(0x191D, 0xFF) != 0x6E:
        raise RuntimeError("control string index fix missing at 0x191C (Input movwf)")

    # --- Patch 3: Dispatch redirect at 0x11F0 ---
    # Must be a goto (EFxx Fxxx) to 0x7000 area.
    if control_new.get(0x11F1, 0xFF) != 0xEF:
        raise RuntimeError("control dispatch hook at 0x11F0 not a goto instruction")
    if control_new.get(0x7000, 0xFF) == 0xFF:
        raise RuntimeError("control dispatch stub missing at 0x7000")

    # --- Patch 4: Volume indicator hook at 0x137A ---
    # Must be a goto (EFxx Fxxx) to stub area.
    if control_new.get(0x137B, 0xFF) != 0xEF:
        raise RuntimeError("control volume indicator hook at 0x137A not a goto instruction")

    # --- Patch 5: Full-sync entry hook at 0x0B36 ---
    # Must be a goto to stub area (replacing call function_031).
    if control_new.get(0x0B37, 0xFF) != 0xEF:
        raise RuntimeError(
            f"control full-sync hook mismatch at 0x0B37: got 0x{control_new.get(0x0B37, 0xFF):02X}, want 0xEF"
        )
    if control_new.get(0x0B39, 0xFF) != 0xF0:
        raise RuntimeError(
            f"control full-sync hook mismatch at 0x0B39: got 0x{control_new.get(0x0B39, 0xFF):02X}, want 0xF0"
        )

    # --- Patch 6: IR dispatch pre-hook at 0x0DE6 ---
    # Verify this is a goto and that it targets the new 0x7000 stub area,
    # not the stock label_162 dispatch at 0x0DEC.
    ir_w1_lo = control_new.get(0x0DE6, 0xFF)
    ir_w1_hi = control_new.get(0x0DE7, 0xFF)
    ir_w2_lo = control_new.get(0x0DE8, 0xFF)
    ir_w2_hi = control_new.get(0x0DE9, 0xFF)
    if ir_w1_hi != 0xEF or ir_w2_hi != 0xF0:
        raise RuntimeError("control IR dispatch hook at 0x0DE6 not a goto instruction")
    # PIC18 GOTO encoding (byte-address target):
    # target = (((word2_low12 << 8) | word1_low8) * 2).
    ir_target = ((((ir_w2_hi & 0x0F) << 8) | ir_w2_lo) << 8 | ir_w1_lo) * 2
    if ir_target == 0x0DEC:
        raise RuntimeError("control IR dispatch hook target drifted to stock label_162 (0x0DEC)")
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

    # call 0x0C40 (function_031): bytes 20 EC 06 F0
    full_sync_anchor = _find_seq([0x20, 0xEC, 0x06, 0xF0])
    if full_sync_anchor is None or full_sync_anchor < 0x7004:
        raise RuntimeError("control full-sync stub signature not found in 0x7000 stub area")
    full_sync_call = [control_new.get(a, 0xFF) for a in range(full_sync_anchor - 4, full_sync_anchor)]
    if full_sync_call[1] != 0xEC or full_sync_call[3] != 0xF0:
        raise RuntimeError("control full-sync stub missing call to TX-only preset sender")
    # Following instruction must be goto 0x0B3A (continue original flow).
    goto_w1_lo = control_new.get(full_sync_anchor + 4, 0xFF)
    goto_w1_hi = control_new.get(full_sync_anchor + 5, 0xFF)
    goto_w2_lo = control_new.get(full_sync_anchor + 6, 0xFF)
    goto_w2_hi = control_new.get(full_sync_anchor + 7, 0xFF)
    if goto_w1_hi != 0xEF or goto_w2_hi != 0xF0:
        raise RuntimeError("control full-sync stub missing goto continuation to original flow")
    goto_target = ((((goto_w2_hi & 0x0F) << 8) | goto_w2_lo) << 8 | goto_w1_lo) * 2
    if goto_target != 0x0B3A:
        raise RuntimeError(
            f"control full-sync continuation target mismatch: got 0x{goto_target:04X}, want 0x0B3A"
        )

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

    # Verify stub calls function_035 (0x0CB2) at some point.
    found_fn035 = False
    for a in range(0x7000, 0x7200, 2):
        lo = control_new.get(a, 0xFF)
        hi = control_new.get(a + 1, 0xFF)
        # call 0x0CB2: EC59 F006 -> bytes 59 EC 06 F0
        if lo == 0x59 and hi == 0xEC:
            nxt_lo = control_new.get(a + 2, 0xFF)
            nxt_hi = control_new.get(a + 3, 0xFF)
            if nxt_lo == 0x06 and nxt_hi == 0xF0:
                found_fn035 = True
                break
    if not found_fn035:
        raise RuntimeError("control stub area missing call to function_035 (0x0CB2)")

    # Verify send_preset_frame emits route 0xB0, cmd 0x20.
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

    # CONTROL version tuple should be 1.61 (EEPROM 0x70..0x72) and startup
    # splash literal should render "1.61" (minor literal movlw 0x3D).
    control_ver = [control_new.get(a, 0xFF) for a in (0xF00070, 0xF00071, 0xF00072)]
    if control_ver != [0x01, 0x06, 0x31]:
        raise RuntimeError(
            f"control version tuple mismatch: got {[hex(x) for x in control_ver]}, want [0x1,0x6,0x31]"
        )
    if control_new.get(0x1152, 0xFF) != 0x3D or control_new.get(0x1153, 0xFF) != 0x0E:
        raise RuntimeError("control startup splash literal mismatch at 0x1152 (expected movlw 0x3D)")

    # --- Text labels preserved (USBaudio NOT overwritten) ---
    def s(addr: int) -> str:
        return bytes(control_new.get(addr + i, 0x20) for i in range(16)).decode("ascii", "replace")

    vol_hdr = s(0x100C)
    if vol_hdr != "Volume:         ":
        raise RuntimeError(f"control Volume header changed: {vol_hdr!r}")
    app_window = bytes(control_new.get(a, 0x20) for a in range(0x1000, 0x1B00))
    if b"USBaudio" not in app_window:
        raise RuntimeError("control USBaudio label missing from app text window")

    # Original should still have old bytes at key locations.
    if control_orig.get(0x1216, 0x00) != 0x02:
        raise RuntimeError("control original mismatch at 0x1216 (expected movlw 0x02)")
    if control_orig.get(0x11F0, 0x00) != 0xBF:
        raise RuntimeError("control original mismatch at 0x11F0 (expected decfsz 0xBF)")
    if control_orig.get(0x0B36, 0x00) != 0x20:
        raise RuntimeError("control original mismatch at 0x0B36 (expected call function_031)")
    if (
        control_orig.get(0x0DE6, 0x00) != 0xF6
        or control_orig.get(0x0DE7, 0x00) != 0xEF
        or control_orig.get(0x0DE8, 0x00) != 0x06
        or control_orig.get(0x0DE9, 0x00) != 0xF0
    ):
        raise RuntimeError("control original mismatch at 0x0DE6 (expected goto label_162)")
    if control_orig.get(0x10B2, 0x00) != 0x1F or control_orig.get(0x10B3, 0x00) != 0x96:
        raise RuntimeError("control original mismatch at 0x10B2 (expected bcf 0x01F,3)")
    if (
        control_orig.get(0x111C, 0x00) != 0x23
        or control_orig.get(0x111D, 0x00) != 0xEC
        or control_orig.get(0x111E, 0x00) != 0x05
        or control_orig.get(0x111F, 0x00) != 0xF0
    ):
        raise RuntimeError("control original mismatch at 0x111C (expected call function_026)")
    if control_orig.get(0x1152, 0x00) != 0x06 or control_orig.get(0x1153, 0x00) != 0x0E:
        raise RuntimeError("control original mismatch at 0x1152 (expected movlw 0x06)")


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
