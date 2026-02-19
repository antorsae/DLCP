#!/usr/bin/env python3
"""
Build a patched DLCP control firmware (v1.4) with A/B preset support.

Patch summary (top-level Preset screen design):
- Add Preset as a top-level menu screen between Volume and Input.
- Navigation: Volume(0) <-> Preset(1) <-> Input(2) <-> Setup(3) (wrap).
- USBaudio sub-parameter is left untouched (original function preserved).
- Preset screen shows >A< / >B< selection brackets; UP=A, DOWN=B.
- Volume screen shows active preset letter (A/B) at column 15.
- Preset change broadcasts route=0xB0 cmd=0x20 data=0|1.
- IR F1/F2 shortcuts: RC5 0x38 -> preset A, RC5 0x39 -> preset B.
- Preset state stored in state_flags bit6 (0x01F.6); persisted at EEPROM 0x74.
- Firmware version policy: display/version tuple updated to 1.41.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile
from typing import Dict, List, Tuple

from dlcp_fw.paths import PATCHED_CONTROL_HEX, STOCK_CONTROL_HEX_V14


class HexParseError(RuntimeError):
    pass


PATCH_ASM = r"""
LIST P=18F2550
#include <p18f2550.inc>

; ============================================================
; Patch 0 - Startup flag init
; ============================================================
; Ensure custom state bits (5/6) start from known values each boot.
; Original: bcf 0x01F,3
org 0x1106
    clrf 0x01F, ACCESS

; ============================================================
; Patch 1 - Startup preset load hook
; ============================================================
; Original: call function_026
org 0x116E
    call preset_boot_init_wrapper

; Version splash minor/patch component: 4 -> 41 (0x29)
; Original at 0x11A4: movlw 0x04
org 0x11A4
    movlw 0x29

; ============================================================
; Patch 2 - Navigation wrap: 3 screens -> 4 screens
; ============================================================

; RIGHT: wrap limit 2 -> 3
org 0x1264
    movlw 0x03

; LEFT: wrap target 2 -> 3
org 0x1288
    movlw 0x03

; ============================================================
; Patch 3 - String table index fixes
; ============================================================

; function_047 (Setup, now menu_state=3): force string index 2
; Original: movff 0xBF, 0x027 (copies menu_state as index)
org 0x149A
    movlw 0x02
    movwf 0x027, ACCESS

; function_052 (Input, now menu_state=2): force string index 1
; Original: movff 0xBF, 0x027
org 0x1A08
    movlw 0x01
    movwf 0x027, ACCESS

; ============================================================
; Patch 4 - Dispatch redirect at label_207 (0x123E)
; ============================================================
; Original: decfsz 0xBF, W, BANKED / goto label_208
; Replace with goto to new dispatch stub + nop filler
org 0x123E
    goto new_dispatch_stub
    nop

; ============================================================
; Patch 5 - Volume preset indicator hook
; ============================================================
; Original: call 0x0D24 (function_042)
org 0x13AE
    goto volume_indicator_stub

; ============================================================
; Patch 6 - Full-sync hook (function_028 entry)
; ============================================================
; Original:
;   0x0B52: clrf 0x028, ACCESS
;   0x0B54: movlw 0x06
; Replace with stub that emits preset sync (TX-only) then
; restores original instructions.
org 0x0B52
    goto full_sync_entry_stub
    nop

; ============================================================
; Patch 7 - IR dispatch pre-hook
; ============================================================
; Original: 0x0E46 -> goto label_166 (0x0E4C)
; Route through wrapper to handle RC5 F1/F2 as preset shortcuts.
org 0x0E46
    goto ir_dispatch_pre_stub

; ============================================================
; New code in erased flash area (0x7000+)
; ============================================================
org 0x7000

; ------------------------------------------------------------
; preset_boot_init_wrapper:
; - preserve stock function_026 behavior
; - load preset from EEPROM[0x74] into state_flags bit6
; ------------------------------------------------------------
preset_boot_init_wrapper:
    call 0x0A62                 ; function_026 (stock settings load)
    movlw 0x74
    call 0x0196                 ; function_010 (EEPROM byte read)
    movwf 0x027, ACCESS
    bcf 0x01F, 6, ACCESS        ; default A unless value == 1
    movlw 0x01
    cpfseq 0x027, ACCESS
    goto preset_boot_init_done
    bsf 0x01F, 6, ACCESS
preset_boot_init_done:
    return

; ------------------------------------------------------------
; ir_dispatch_pre_stub:
; - adds RC5 F1/F2 preset shortcuts before stock IR dispatch
; - cmd 0x38 (F1) -> preset A
; - cmd 0x39 (F2) -> preset B
; ------------------------------------------------------------
ir_dispatch_pre_stub:
    ; Match configured RC5 address first (same gate as stock dispatch).
    movf 0x01E, W, ACCESS
    cpfseq 0x020, ACCESS
    goto ir_dispatch_passthrough

    ; F1 (0x38) -> preset A
    movf 0x01D, W, ACCESS
    xorlw 0x38
    bz ir_set_preset_a

    ; F2 (0x39) -> preset B
    movf 0x01D, W, ACCESS
    xorlw 0x39
    bz ir_set_preset_b

    goto ir_dispatch_passthrough

ir_set_preset_a:
    ; Idempotent: if already A, do nothing.
    btfss 0x01F, 6, ACCESS
    goto ir_dispatch_done
    bcf 0x01F, 6, ACCESS
    movlb 0x00
    call send_preset_frame
    bsf 0x01F, 3, ACCESS         ; request UI refresh
    goto ir_dispatch_done

ir_set_preset_b:
    ; Idempotent: if already B, do nothing.
    btfsc 0x01F, 6, ACCESS
    goto ir_dispatch_done
    bsf 0x01F, 6, ACCESS
    movlb 0x00
    call send_preset_frame
    bsf 0x01F, 3, ACCESS         ; request UI refresh
    goto ir_dispatch_done

ir_dispatch_done:
    bsf 0x01F, 0, ACCESS         ; re-arm IR path (matches stock tail)
    return

ir_dispatch_passthrough:
    movlb 0x00
    goto 0x0E4C                  ; stock label_166

; ------------------------------------------------------------
; new_dispatch_stub: handle menu states 1, 2, 3
; State 0 (Volume) is handled by original code before this point.
; ------------------------------------------------------------
new_dispatch_stub:
    ; 0xBF = menu_state, known != 0 at this point
    decfsz 0xBF, W, BANKED     ; W = BF-1; skip if was 1 (Preset)
    goto check_state_2
    call preset_screen
    goto 0x1258                 ; label_209 (post-screen nav)

check_state_2:
    movlw 0x02
    cpfseq 0xBF, BANKED        ; skip if BF == 2 (Input)
    goto check_state_3
    call 0x1A00                 ; function_052 (Input)
    goto 0x1258                 ; label_209

check_state_3:
    movlw 0x03
    cpfseq 0xBF, BANKED        ; skip if BF == 3 (Setup)
    goto 0x1258                 ; unknown state -> skip
    call 0x1492                 ; function_047 (Setup)
    goto 0x1258                 ; label_209

; ------------------------------------------------------------
; volume_indicator_stub: show A/B at line 1 col 15, then
; call function_042 (the original call we replaced).
; ------------------------------------------------------------
volume_indicator_stub:
    ; One-time boot resync: emit current preset once after startup so
    ; mains can follow EEPROM-restored state after a full power cycle.
    ; Reuse flags bit5 as "preset sync sent" latch.
    btfsc 0x01F, 5, ACCESS
    goto vol_draw
    bsf 0x01F, 5, ACCESS
    call send_preset_frame_txonly

vol_draw:
    movlw 0x80
    movwf 0x001, ACCESS         ; LCD output target
    movlw 0x8F                  ; cursor: line 1, column 15
    call 0x0066                 ; LCD command routine
    movlw 'A'
    btfsc 0x01F, 6, ACCESS      ; preset bit6: 0=A, 1=B
    movlw 'B'
    call 0x00EC                 ; LCD char output
    call 0x0D24                 ; function_042 (original)
    goto 0x13B2                 ; return to post-function_042

; ------------------------------------------------------------
; full_sync_entry_stub: emit periodic preset sync alongside the
; existing full-sync block (function_028) without EEPROM writes.
; ------------------------------------------------------------
full_sync_entry_stub:
    call send_preset_frame_txonly
    clrf 0x028, ACCESS
full_sync_loop_entry:
    movlw 0x06
    cpfslt 0x028, ACCESS
    goto 0x0BA8                 ; label_143
    goto 0x0B5A                 ; continue original loop body

; ------------------------------------------------------------
; preset_screen: full Preset screen render + event loop
; Line 1: "Preset       >A<" or "Preset        A "
; Line 2: "              B " or "             >B<"
; ------------------------------------------------------------
preset_screen:
    ; --- Line 1 ---
    movlw 0x80
    movwf 0x001, ACCESS         ; LCD output target
    movlw 0x80                  ; cursor: line 1, column 0
    call 0x0066

    ; "Preset" (6 chars)
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

    ; 7 spaces (columns 6-12)
    movlw 0x07
    movwf 0x028, ACCESS
line1_sp:
    movlw ' '
    call 0x00EC
    decfsz 0x028, F, ACCESS
    bra line1_sp

    ; Column 13: '>' if preset=A (bit6=0), else ' '
    movlw '>'
    btfsc 0x01F, 6, ACCESS
    movlw ' '
    call 0x00EC
    ; Column 14: 'A'
    movlw 'A'
    call 0x00EC
    ; Column 15: '<' if preset=A, else ' '
    movlw '<'
    btfsc 0x01F, 6, ACCESS
    movlw ' '
    call 0x00EC

    ; --- Line 2 ---
    movlw 0xC0                  ; cursor: line 2, column 0
    call 0x0066

    ; 13 spaces (columns 0-12)
    movlw 0x0D
    movwf 0x028, ACCESS
line2_sp:
    movlw ' '
    call 0x00EC
    decfsz 0x028, F, ACCESS
    bra line2_sp

    ; Column 13: '>' if preset=B (bit6=1), else ' '
    movlw '>'
    btfss 0x01F, 6, ACCESS
    movlw ' '
    call 0x00EC
    ; Column 14: 'B'
    movlw 'B'
    call 0x00EC
    ; Column 15: '<' if preset=B, else ' '
    movlw '<'
    btfss 0x01F, 6, ACCESS
    movlw ' '
    call 0x00EC

    ; Shadow rendered preset in scratch byte 0x02D for out-of-band
    ; change detection (avoids reusing stock state_flags bits).
    clrf 0x02D, ACCESS
    btfsc 0x01F, 6, ACCESS
    incf 0x02D, F, ACCESS

; --- Event loop ---
preset_loop:
    call 0x0D24                 ; function_042 (wait for event)

    ; If preset changed out-of-band (e.g. IR F1/F2), redraw this screen.
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    xorwf 0x02D, W, ACCESS
    bz prs_shadow_ok
    goto preset_screen
prs_shadow_ok:

    ; Check UP (0x9A bit1) -> set preset A
    btfss 0x09A, 1, BANKED
    goto prs_check_down
    btfss 0x01F, 6, ACCESS      ; already A -> no-op
    goto preset_loop
    bcf 0x01F, 6, ACCESS
    call send_preset_frame
    goto preset_screen           ; full re-render

prs_check_down:
    ; Check DOWN (0x9A bit2) -> set preset B
    btfss 0x09A, 2, BANKED
    goto preset_exit_check
    btfsc 0x01F, 6, ACCESS      ; already B -> no-op
    goto preset_loop
    bsf 0x01F, 6, ACCESS
    call send_preset_frame
    goto preset_screen           ; full re-render

; --- Exit check (same pattern as function_046 at 0x1402) ---
preset_exit_check:
    bcf 0x01F, 3, ACCESS        ; clear refresh flag
    clrf WREG, ACCESS            ; W = 0
    btfsc 0x09A, 5, BANKED      ; RIGHT pressed?
    movlw 0x01
    movwf 0x018, ACCESS
    clrf WREG, ACCESS
    btfsc 0x09A, 4, BANKED      ; LEFT pressed?
    movlw 0x01
    iorwf 0x018, F, ACCESS
    movlw 0x01
    btfsc 0x01F, 1, ACCESS      ; still connected?
    clrf WREG, ACCESS            ; connected -> W=0
    iorwf 0x018, F, ACCESS
    btfsc STATUS, Z, ACCESS      ; skip if nonzero (exit)
    bra preset_loop              ; zero -> stay in screen
    return

; ------------------------------------------------------------
; send_preset_frame: transmit route=0xB0 cmd=0x20 data=preset
; ------------------------------------------------------------
send_preset_frame_txonly:
    movlw 0xB0                  ; route = broadcast
    movwf 0x027, ACCESS
    call 0x0608                 ; function_020 (serial TX byte)
    movlw 0x20                  ; cmd = set preset
    movwf 0x027, ACCESS
    call 0x0608
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01                  ; data = preset value (0 or 1)
    movwf 0x027, ACCESS
    call 0x0608
    return

send_preset_frame:
    call send_preset_frame_txonly
    ; EEPROM persist: write preset to EEPROM[0x74]
    movlw 0x74
    movwf EEADR, ACCESS
    clrf WREG, ACCESS
    btfsc 0x01F, 6, ACCESS
    movlw 0x01
    call 0x01A2                 ; function_011 (EEPROM byte write)
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
            [gpasm, "-p18f2550", "-o", str(out_hex), str(asm)],
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
    """Validate original firmware bytes at all patch points."""
    expected = {
        # Patch 0: startup flag init hook (original bcf 0x01F,3)
        0x1106: 0x1F,
        0x1107: 0x96,
        # Patch 1: startup preset hook (original call function_026)
        0x116E: 0x31,
        0x116F: 0xEC,
        0x1170: 0x05,
        0x1171: 0xF0,
        # Patch 1b: version literal (movlw 0x04)
        0x11A4: 0x04,
        0x11A5: 0x0E,
        # Patch 2: nav wrap literals (movlw 0x02)
        0x1264: 0x02,
        0x1265: 0x0E,
        0x1288: 0x02,
        0x1289: 0x0E,
        # Patch 3: string table index (movff 0xBF, 0x027)
        0x149A: 0xBF,
        0x149B: 0xC0,
        0x1A08: 0xBF,
        0x1A09: 0xC0,
        # Patch 4: dispatch hook (decfsz 0xBF, W, BANKED)
        0x123E: 0xBF,
        0x123F: 0x2D,
        # Patch 5: volume indicator hook (call function_042 = call 0x0D24)
        0x13AE: 0x92,
        0x13AF: 0xEC,
        0x13B0: 0x06,
        0x13B1: 0xF0,
        # Patch 6: full-sync entry prologue
        0x0B52: 0x28,  # clrf 0x028, ACCESS
        0x0B53: 0x6A,
        0x0B54: 0x06,  # movlw 0x06
        0x0B55: 0x0E,
        # Patch 7: IR dispatch pre-hook (original goto label_166)
        0x0E46: 0x26,
        0x0E47: 0xEF,
        0x0E48: 0x07,
        0x0E49: 0xF0,
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
        default=STOCK_CONTROL_HEX_V14,
        help="input control v1.4 hex",
    )
    ap.add_argument(
        "--out-hex",
        type=pathlib.Path,
        default=PATCHED_CONTROL_HEX,
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

    # Keep CONTROL version tuple at 1.41 in EEPROM defaults.
    version_bytes = {
        0xF00070: 0x01,
        0xF00071: 0x04,
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
        "hooks=[0x1106,0x116E,0x11A4,0x0B52,0x0E46,0x1264,0x1288,0x149A,0x1A08,0x123E,0x13AE]",
        "stub_range=0x7000+",
    )
    print(
        "version patch:",
        f"bytes={ver_written}",
        f"changed={ver_changed}",
        "eeprom=[0xF00070..0xF00072]=[0x01,0x04,0x31]",
    )
    print(f"total bytes changed vs input: {total_diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
