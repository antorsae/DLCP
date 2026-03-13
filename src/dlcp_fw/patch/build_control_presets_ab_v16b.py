#!/usr/bin/env python3
"""
Build a patched DLCP control firmware (v1.6b) with A/B preset support.

Patch summary (reliability-first design):
- Add Preset as a top-level menu screen between Volume and Input.
- Navigation: Volume(0) <-> Preset(1) <-> Input(2) <-> Setup(3) (wrap).
- Preset screen is simple: shows preset status only, no DSP filename transport.
- Volume screen shows active preset letter (A/B) at column 15.
- Preset change broadcasts route=0xB0 cmd=0x20 data=0|1.
- Retry policy:
  - user/IR preset change: send immediately, then queue 2 more retries
  - boot/reconnect: queue 3 retries
  - retries are emitted one-per-full-sync cycle; no perpetual preset broadcast
- No filename request/parser/cache protocol is added.
- IR F1/F2 shortcuts: RC5 0x38 -> preset A, RC5 0x39 -> preset B.
- Preset state stored in state_flags bit6 (0x01F.6); persisted at EEPROM 0x74.
- Preserves the V1.61b setup-index migration fix for stale EEPROM[0x01].
- Firmware version policy: display/version tuple updated to 1.61b.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile
from typing import Dict, List, Tuple

from dlcp_fw.paths import PATCHED_CONTROL_HEX_V161B, STOCK_CONTROL_HEX_V16B


class HexParseError(RuntimeError):
    pass


PATCH_ASM = r"""
LIST P=18F25K20
#include <p18f25k20.inc>

org 0x10B2
    bcf 0x01F, 3, ACCESS
    bcf 0x01F, 4, ACCESS

org 0x111C
    call preset_boot_init_wrapper

org 0x1152
    movlw 0x3D

org 0x1216
    movlw 0x03

org 0x123A
    movlw 0x03

org 0x1406
    movlw 0x02
    movwf 0x027, ACCESS

org 0x191A
    movlw 0x01
    movwf 0x027, ACCESS

org 0x11F0
    goto new_dispatch_stub
    nop

org 0x137A
    goto volume_indicator_stub

org 0x0B36
    goto full_sync_entry_stub

org 0x0DE6
    goto ir_dispatch_pre_stub

org 0x7000
preset_boot_init_wrapper:
    call 0x0A46                 ; function_026 (stock settings load)
    movf 0x0BA, W, BANKED
    bz preset_boot_setup_ok
    clrf 0x0BA, BANKED
    movlw 0x01
    movwf EEADR, ACCESS
    clrf WREG, ACCESS
    call 0x01A2                 ; function_011 (EEPROM byte write)
preset_boot_setup_ok:
    movlw 0x74
    call 0x0196                 ; function_010 (EEPROM byte read)
    movwf 0x027, ACCESS
    bcf 0x01F, 6, ACCESS
    movlw 0x01
    cpfseq 0x027, ACCESS
    goto preset_boot_init_done
    bsf 0x01F, 6, ACCESS
preset_boot_init_done:
    movlb 0x01
    movlw 0x03
    movwf 0x70, BANKED
    clrf 0x71, BANKED
    movlb 0x00
    clrf 0xBF, BANKED
    return

ir_dispatch_pre_stub:
    movf 0x01E, W, ACCESS
    cpfseq 0x020, ACCESS
    goto ir_dispatch_passthrough

    movf 0x01D, W, ACCESS
    xorlw 0x38
    bz ir_set_preset_a

    movf 0x01D, W, ACCESS
    xorlw 0x39
    bz ir_set_preset_b

    goto ir_dispatch_passthrough

ir_set_preset_a:
    btfss 0x01F, 6, ACCESS
    goto ir_dispatch_done
    bcf 0x01F, 6, ACCESS
    movlb 0x00
    call send_preset_frame
    bsf 0x01F, 3, ACCESS
    goto ir_dispatch_done

ir_set_preset_b:
    btfsc 0x01F, 6, ACCESS
    goto ir_dispatch_done
    bsf 0x01F, 6, ACCESS
    movlb 0x00
    call send_preset_frame
    bsf 0x01F, 3, ACCESS
    goto ir_dispatch_done

ir_dispatch_done:
    bsf 0x01F, 0, ACCESS
    return

ir_dispatch_passthrough:
    movlb 0x00
    goto 0x0DEC

new_dispatch_stub:
    movlb 0x00
    decfsz 0xBF, W, BANKED
    goto check_state_2
    call preset_screen
    goto 0x120A

check_state_2:
    movlw 0x02
    cpfseq 0xBF, BANKED
    goto check_state_3
    call 0x1912
    goto 0x120A

check_state_3:
    movlw 0x03
    cpfseq 0xBF, BANKED
    goto 0x120A
    call 0x13FE
    goto 0x120A

volume_indicator_stub:
    movlw 0x80
    movwf 0x001, ACCESS
    movlw 0x8F
    call 0x0066
    movlw 'A'
    btfsc 0x01F, 6, ACCESS
    movlw 'B'
    call 0x00EC
    call 0x0CB2
    goto 0x137E

full_sync_entry_stub:
    movlb 0x01
    btfsc 0x01F, 1, ACCESS
    goto fs_connected
    movf 0x71, F, BANKED
    bz fs_send_check
    clrf 0x71, BANKED
    goto fs_send_check
fs_connected:
    movf 0x71, F, BANKED
    bnz fs_send_check
    movlw 0x01
    movwf 0x71, BANKED
    movf 0x70, F, BANKED
    bnz fs_send_check
    movlw 0x03
    movwf 0x70, BANKED
fs_send_check:
    movf 0x70, F, BANKED
    bz fs_continue
    movlb 0x00
    call send_preset_frame_txonly
    movlb 0x01
    decf 0x70, F, BANKED
fs_continue:
    movlb 0x00
    call 0x0C40                 ; function_031 (original)
    goto 0x0B3A

preset_screen:
prs_screen_draw:
    movlw 0x80
    movwf 0x001, ACCESS
    movlw 0x80
    call 0x0066
    movlw 'P'
    call 0x00EC
    movlw 'r'
    call 0x00EC
    movlw 'e'
    call 0x00EC
    movlw 's'
    call 0x00EC
    movlw 'e'
    call 0x00EC
    movlw 't'
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC

    movlw 0xC0
    call 0x0066
    movlw 'A'
    call 0x00EC
    movlw 'c'
    call 0x00EC
    movlw 't'
    call 0x00EC
    movlw 'i'
    call 0x00EC
    movlw 'v'
    call 0x00EC
    movlw 'e'
    call 0x00EC
    movlw ':'
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw 'A'
    btfsc 0x01F, 6, ACCESS
    movlw 'B'
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC
    movlw ' '
    call 0x00EC

    movlb 0x01
    clrf 0x72, BANKED
    btfsc 0x01F, 6, ACCESS
    incf 0x72, F, BANKED

preset_loop:
    movlb 0x00
    call 0x0CB2
    movlb 0x00
    btfsc 0x01F, 3, ACCESS
    bcf 0x01F, 3, ACCESS
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    movlb 0x01
    xorwf 0x72, W, BANKED
    movlb 0x00
    bz prs_check_up
    goto prs_screen_draw

prs_check_up:
    btfss 0x09A, 1, BANKED
    goto prs_check_down
    btfss 0x01F, 6, ACCESS
    goto preset_loop
    bcf 0x01F, 6, ACCESS
    call send_preset_frame
    goto prs_screen_draw

prs_check_down:
    btfss 0x09A, 2, BANKED
    goto preset_exit_check
    btfsc 0x01F, 6, ACCESS
    goto preset_loop
    bsf 0x01F, 6, ACCESS
    call send_preset_frame
    goto prs_screen_draw

preset_exit_check:
    bcf 0x01F, 3, ACCESS
    clrf WREG, ACCESS
    btfsc 0x09A, 5, BANKED
    movlw 0x01
    movwf 0x018, ACCESS
    clrf WREG, ACCESS
    btfsc 0x09A, 4, BANKED
    movlw 0x01
    iorwf 0x018, F, ACCESS
    movlw 0x01
    btfsc 0x01F, 1, ACCESS
    clrf WREG, ACCESS
    iorwf 0x018, F, ACCESS
    btfsc STATUS, Z, ACCESS
    bra preset_loop
    movlb 0x00
    return

send_preset_frame_txonly:
    movlw 0xB0
    movwf 0x027, ACCESS
    call 0x05EC
    movlw 0x20
    movwf 0x027, ACCESS
    call 0x05EC
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    movwf 0x027, ACCESS
    call 0x05EC
    return

send_preset_frame:
    call send_preset_frame_txonly
    movlw 0x02
    movlb 0x01
    movwf 0x70, BANKED
    movlb 0x00
    movlw 0x74
    movwf EEADR, ACCESS
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    call 0x01A2
    return

end
"""


def parse_intel_hex(path: pathlib.Path) -> Dict[int, int]:
    mem: Dict[int, int] = {}
    upper = 0

    def b(h: str) -> int:
        try:
            return int(h, 16)
        except ValueError as e:
            raise HexParseError(f"bad hex byte {h!r} in {path}") from e

    with path.open("r", encoding="ascii", errors="strict") as f:
        for lineno, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            if not line.startswith(":"):
                raise HexParseError(f"{path}:{lineno}: missing ':'")

            ll = b(line[1:3])
            aaaa = int(line[3:7], 16)
            rtype = b(line[7:9])
            data_hex = line[9 : 9 + ll * 2]
            cc = b(line[9 + ll * 2 : 11 + ll * 2])

            total = ll + ((aaaa >> 8) & 0xFF) + (aaaa & 0xFF) + rtype
            data: List[int] = []
            for i in range(0, len(data_hex), 2):
                bb = b(data_hex[i : i + 2])
                data.append(bb)
                total += bb
            total &= 0xFF
            calc = (~total + 1) & 0xFF
            if calc != cc:
                raise HexParseError(
                    f"{path}:{lineno}: checksum mismatch (got 0x{cc:02X}, want 0x{calc:02X})"
                )

            if rtype == 0x00:
                base = (upper << 16) | aaaa
                for i, bb in enumerate(data):
                    mem[base + i] = bb
            elif rtype == 0x01:
                break
            elif rtype == 0x04:
                if ll != 2:
                    raise HexParseError(f"{path}:{lineno}: type 04 with ll={ll}")
                upper = (data[0] << 8) | data[1]
            else:
                continue

    return mem


def _record(addr16: int, rtype: int, payload: bytes) -> str:
    ll = len(payload)
    total = ll + ((addr16 >> 8) & 0xFF) + (addr16 & 0xFF) + rtype + sum(payload)
    cc = (~total + 1) & 0xFF
    return f":{ll:02X}{addr16:04X}{rtype:02X}{payload.hex().upper()}{cc:02X}"


def write_intel_hex(path: pathlib.Path, mem: Dict[int, int], chunk: int = 16) -> None:
    addrs = sorted(mem.keys())
    lines: List[str] = []
    current_upper: int | None = None

    i = 0
    while i < len(addrs):
        start = addrs[i]
        upper = (start >> 16) & 0xFFFF
        if upper != current_upper:
            current_upper = upper
            lines.append(_record(0x0000, 0x04, bytes([(upper >> 8) & 0xFF, upper & 0xFF])))

        addr16 = start & 0xFFFF
        data = bytearray([mem[start]])
        i += 1

        while i < len(addrs):
            a = addrs[i]
            if ((a >> 16) & 0xFFFF) != upper:
                break
            if (a & 0xFFFF) != ((addr16 + len(data)) & 0xFFFF):
                break
            if len(data) >= chunk:
                break
            data.append(mem[a] & 0xFF)
            i += 1

        lines.append(_record(addr16, 0x00, bytes(data)))

    lines.append(":00000001FF")
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def assemble_patch(gpasm: str) -> Dict[int, int]:
    with tempfile.TemporaryDirectory(prefix="dlcp_control_patch_") as td:
        td_path = pathlib.Path(td)
        asm = td_path / "control_presets_patch.asm"
        out_hex = td_path / "control_presets_patch.hex"
        asm.write_text(PATCH_ASM, encoding="ascii")
        result = subprocess.run(
            [gpasm, "-p18f25k20", "-o", str(out_hex), str(asm)],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"gpasm failed (rc={result.returncode}):\n{result.stderr}\n{result.stdout}"
            )
        return parse_intel_hex(out_hex)


def apply_patch_bytes(mem: Dict[int, int], patch: Dict[int, int]) -> Tuple[int, int]:
    written = 0
    changed = 0
    for a, v in patch.items():
        old = mem.get(a, 0xFF)
        mem[a] = v
        written += 1
        if old != v:
            changed += 1
    return written, changed


def summarize_diff(old_mem: Dict[int, int], new_mem: Dict[int, int]) -> int:
    all_addrs = set(old_mem.keys()) | set(new_mem.keys())
    diff = 0
    for a in all_addrs:
        if old_mem.get(a, 0xFF) != new_mem.get(a, 0xFF):
            diff += 1
    return diff


def validate_expected(mem: Dict[int, int]) -> None:
    """Validate original V1.6b firmware bytes at all patch points."""
    expected = {
        # Patch 0: startup flag init hook (original bcf 0x01F,3)
        0x10B2: 0x1F,
        0x10B3: 0x96,
        # Patch 1: startup preset hook (original call function_026)
        0x111C: 0x23,
        0x111D: 0xEC,
        0x111E: 0x05,
        0x111F: 0xF0,
        # Patch 1b: version literal (movlw 0x06)
        0x1152: 0x06,
        0x1153: 0x0E,
        # Patch 2: nav wrap literals (movlw 0x02)
        0x1216: 0x02,
        0x1217: 0x0E,
        0x123A: 0x02,
        0x123B: 0x0E,
        # Patch 3: string table index (movff 0xBF, 0x027)
        0x1406: 0xBF,
        0x1407: 0xC0,
        0x191A: 0xBF,
        0x191B: 0xC0,
        # Patch 4: dispatch hook (decfsz 0xBF, W, BANKED)
        0x11F0: 0xBF,
        0x11F1: 0x2D,
        # Patch 5: volume indicator hook (call function_035 = call 0x0CB2)
        0x137A: 0x59,
        0x137B: 0xEC,
        0x137C: 0x06,
        0x137D: 0xF0,
        # Patch 6: full-sync entry hook (call function_031 = call 0x0C40)
        0x0B36: 0x20,
        0x0B37: 0xEC,
        0x0B38: 0x06,
        0x0B39: 0xF0,
        # Patch 7: IR dispatch pre-hook (original goto label_162)
        0x0DE6: 0xF6,
        0x0DE7: 0xEF,
        0x0DE8: 0x06,
        0x0DE9: 0xF0,
        # Patch 8: parser-tail hook site (original label_063: movlw 0x1D)
        0x05D0: 0x1D,
        0x05D1: 0x0E,
    }
    for a, want in expected.items():
        got = mem.get(a, 0xFF)
        if got != want:
            raise RuntimeError(
                f"input firmware mismatch at 0x{a:04X}: got 0x{got:02X}, expected 0x{want:02X}"
            )


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in-hex",
        type=pathlib.Path,
        default=STOCK_CONTROL_HEX_V16B,
        help="input control v1.6b hex",
    )
    ap.add_argument(
        "--out-hex",
        type=pathlib.Path,
        default=PATCHED_CONTROL_HEX_V161B,
        help="output patched control hex",
    )
    ap.add_argument("--gpasm", default="gpasm", help="gpasm executable (default: gpasm)")
    args = ap.parse_args()

    in_hex = args.in_hex.resolve()
    out_hex = args.out_hex.resolve()
    out_hex.parent.mkdir(parents=True, exist_ok=True)

    base = parse_intel_hex(in_hex)
    validate_expected(base)
    new_mem = dict(base)

    # No text patches — USBaudio labels and Volume header are preserved.
    # Preset text is rendered at runtime by the preset_screen stub.

    patch_mem = assemble_patch(args.gpasm)
    patch_written, patch_changed = apply_patch_bytes(new_mem, patch_mem)

    # Keep CONTROL version tuple at 1.61 in EEPROM defaults.
    version_bytes = {
        0xF00070: 0x01,
        0xF00071: 0x06,
        0xF00072: 0x31,
    }
    ver_written = 0
    ver_changed = 0
    for a, v in version_bytes.items():
        old = new_mem.get(a, 0xFF)
        new_mem[a] = v
        ver_written += 1
        if old != v:
            ver_changed += 1

    total_diff = summarize_diff(base, new_mem)

    write_intel_hex(out_hex, new_mem)

    print(f"input:  {in_hex}")
    print(f"output: {out_hex}")
    print(
        "code patch:",
        f"bytes={patch_written}",
        f"changed={patch_changed}",
        "hooks=[0x10B2,0x111C,0x1152,0x0B36,0x0DE6,0x1216,0x123A,0x1406,0x191A,0x11F0,0x137A]",
        "stub_range=0x7000+",
    )
    print(
        "version patch:",
        f"bytes={ver_written}",
        f"changed={ver_changed}",
        "eeprom=[0xF00070..0xF00072]=[0x01,0x06,0x31]",
    )
    print(f"total bytes changed vs input: {total_diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
