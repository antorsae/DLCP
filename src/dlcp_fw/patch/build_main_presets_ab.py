#!/usr/bin/env python3
"""
Build a patched DLCP main firmware HEX with A/B preset banks.

Patch strategy:
1) Copy preset table A (0x5600..0x5FFF, 0xA00 bytes) to preset table B at
   0x4A00..0x53FF.
2) Inject code stubs in erased app space to:
   - remap table flash reads/writes/erases from 0x56xx..0x5Fxx to
     0x4Axx..0x53xx when preset B is active;
   - add current-loop command 0x20: set preset A/B and apply immediately;
   - add current-loop command 0x21: emit paged LCD filename display with
     context frame (cmd 0x2F) + local chunk commands (0x30..0x37);
   - add current-loop command 0x22: emit filename-generation metadata
     (context frame + generation byte) for low-traffic cache validation;
   - bank cmd03 DSP filename EEPROM/RAM load+persist paths by preset.
3) Emit a full Intel HEX output.

Version policy:
- MAIN EEPROM tuple is kept at stock 2.30 (bytes 0x02, 0x03, 0x30 at
  0xF00080..0xF00082).
- USB-reported firmware version literal is patched to 2.4 in application code.
"""

from __future__ import annotations

import argparse
import pathlib
import subprocess
import tempfile
from typing import Dict, List, Tuple

from dlcp_fw.paths import PATCHED_MAIN_HEX, STOCK_MAIN_HEX


class HexParseError(RuntimeError):
    pass


PATCH_ASM = r"""
LIST P=18F2550
#include <p18f2550.inc>

; --- Hooks into existing code ---
org 0x1E64
    goto cmd_tail_patch

; cmd=0x03 filename boot-load path (EEPROM->RAM 0x2C0..0x2DD)
; now needs active-preset bank selection.
org 0x20BE
    goto filename_boot_load_patch

; cmd=0x03 filename dirty persist path (RAM->EEPROM)
; now needs active-preset bank selection.
org 0x27C0
    goto filename_persist_patch

org 0x2E6E
    goto function_025_patch
org 0x2E72
    nop

org 0x3DAC
    goto function_054_patch
org 0x3DB0
    nop

org 0x4028
    goto function_061_patch
org 0x402C
    nop
org 0x402E
    nop

; --- New helpers in low erased app gap ---
org 0x4980
load_active_filename_slot:
    ; Select EEPROM filename bank by active preset:
    ; A -> 0x60..0x7D, B -> 0xA1..0xBE
    movlw 0x60
    movwf 0x0B, ACCESS
    btfss 0x05E, 2, ACCESS
    bra load_slot_base_done
    movlw 0xA1
    movwf 0x0B, ACCESS
load_slot_base_done:
    clrf 0x0A, ACCESS          ; idx = 0..29

load_slot_loop:
    movf 0x0B, W, ACCESS
    addwf 0x0A, W, ACCESS
    movwf 0x03, ACCESS         ; EEPROM addr low
    clrf 0x04, ACCESS          ; EEPROM addr high
    call 0x4884                ; function_110 (EEPROM read), W <- byte
    movwf 0x0C, ACCESS

    movlw 0xC0
    addwf 0x0A, W, ACCESS
    movwf FSR2L, ACCESS
    movlw 0x02
    movwf FSR2H, ACCESS
    movf 0x0C, W, ACCESS
    movwf INDF2, ACCESS        ; RAM[0x2C0 + idx] = byte

    incf 0x0A, F, ACCESS
    movlw 0x1D
    cpfsgt 0x0A, ACCESS
    bra load_slot_loop
    return

filename_boot_load_patch:
    call load_active_filename_slot
    goto 0x20E4

filename_persist_patch:
    ; Select EEPROM filename bank by active preset:
    ; A -> 0x60..0x7D, B -> 0xA1..0xBE
    movlw 0x60
    movwf 0x0B, ACCESS
    btfss 0x05E, 2, ACCESS
    bra persist_base_done
    movlw 0xA1
    movwf 0x0B, ACCESS
persist_base_done:
    clrf 0x0A, ACCESS          ; idx = 0..29

persist_slot_loop:
    movlw 0xC0
    addwf 0x0A, W, ACCESS
    movwf FSR2L, ACCESS
    movlw 0x02
    movwf FSR2H, ACCESS
    movf INDF2, W, ACCESS
    movwf 0x09, ACCESS         ; data byte for function_094

    movf 0x0B, W, ACCESS
    addwf 0x0A, W, ACCESS
    movwf 0x07, ACCESS         ; EEPROM addr low for function_094
    clrf 0x08, ACCESS          ; EEPROM addr high
    call 0x46DE                ; function_094 (EEPROM write)

    incf 0x0A, F, ACCESS
    movlw 0x1D
    cpfsgt 0x0A, ACCESS
    bra persist_slot_loop

    call increment_filename_generation

    bcf 0x0BD, 5, BANKED
    goto 0x27EC

send_filename_display_frames:
    goto send_filename_display_frames_hi

org 0x5468
send_filename_generation_frames:
    ; Emit generation metadata for active preset:
    ;   [BF 2F req_echo]
    ;   [BF 22 generation]
    ; Generation bytes:
    ;   A: EEPROM[0x7E], B: EEPROM[0xBF]
    movlw 0x7E
    movwf 0x03, ACCESS
    btfss 0x05E, 2, ACCESS
    bra sfg_addr_ready
    movlw 0xBF
    movwf 0x03, ACCESS
sfg_addr_ready:
    clrf 0x04, ACCESS
    call 0x4884                ; function_110 (EEPROM read), W <- generation
    andlw 0x7F
    movwf 0x0C, ACCESS

    movlw 0xBF
    call 0x4896
    movlw 0x2F
    call 0x4896
    movf 0x0A3, W, BANKED
    call 0x4896

    movlw 0xBF
    call 0x4896
    movlw 0x22
    call 0x4896
    movf 0x0C, W, ACCESS
    call 0x4896
    return

org 0x5564
increment_filename_generation:
    ; Bump per-preset filename generation byte:
    ;   A: 0x7E (= 0x60 + 0x1E), B: 0xBF (= 0xA1 + 0x1E)
    ; 0x0B still holds active filename base (0x60 or 0xA1) from persist loop setup.
    movf 0x0B, W, ACCESS
    addlw 0x1E
    movwf 0x03, ACCESS
    clrf 0x04, ACCESS
    call 0x4884                ; function_110 (EEPROM read), W <- generation
    addlw 0x01
    movwf 0x09, ACCESS         ; data byte for function_094
    movf 0x03, W, ACCESS
    movwf 0x07, ACCESS         ; EEPROM addr low for function_094
    clrf 0x08, ACCESS
    call 0x46DE                ; function_094 (EEPROM write)
    return

org 0x5580
send_filename_display_frames_hi:
    ; Paged emit from RAM[0x2C0..0x2DD].
    ; Request layout (cmd=0x21 data byte):
    ;   bit0   : preset mirror
    ;   bits2:1: page index 0..3
    ;   bits7:3: transaction id echo
    ; Window map (response cmd is local index within page):
    ;   page0 -> abs idx 0..7
    ;   page1 -> abs idx 8..15
    ;   page2 -> abs idx 16..23
    ;   page3 -> abs idx 24..29
    ; All chunk responses use cmd 0x30..0x37 and require context frame 0x2F.

    ; page = (data >> 1) & 0x03
    movf 0x0A3, W, BANKED
    andlw 0x06
    movwf 0x0B, ACCESS
    rrncf 0x0B, F, ACCESS      ; 0..3

    ; start idx = page * 8
    clrf 0x0A, ACCESS
sfd_mul8_loop:
    movf 0x0B, W, ACCESS
    bz sfd_idx_ready
    movlw 0x08
    addwf 0x0A, F, ACCESS
    decf 0x0B, F, ACCESS
    bra sfd_mul8_loop
sfd_idx_ready:
    movff 0x0A, 0x0B            ; base idx for local cmd indexing
    ; end idx = start+7 except page3 -> 29
    movlw 0x1D
    movwf 0x0C, ACCESS
    movf 0x0A, W, ACCESS
    xorlw 0x18
    bz sfd_loop
    movf 0x0A, W, ACCESS
    addlw 0x07
    movwf 0x0C, ACCESS

    ; Emit context frame first:
    ;   [BF 2F data], where data echoes req bits (txn/page/preset).
    movlw 0xBF
    call 0x4896
    movlw 0x2F
    call 0x4896
    movf 0x0A3, W, BANKED
    call 0x4896

sfd_loop:
    movlw 0xBF
    call 0x4896                ; function_111 (UART TX byte)
    movf 0x0B, W, ACCESS
    subwf 0x0A, W, ACCESS      ; W = abs_idx - base_idx => local idx 0..7
    addlw 0x30
    call 0x4896

    movlw 0xC0
    addwf 0x0A, W, ACCESS
    movwf FSR2L, ACCESS
    movlw 0x02
    movwf FSR2H, ACCESS
    movf INDF2, W, ACCESS
    bz sfd_space
    xorlw 0xFF
    bz sfd_space
    movf INDF2, W, ACCESS
    bra sfd_send_data

sfd_space:
    movlw ' '

sfd_send_data:
    call 0x4896
    incf 0x0A, F, ACCESS
    movf 0x0C, W, ACCESS
    cpfsgt 0x0A, ACCESS
    bra sfd_loop
    return

; --- New code in erased app region ---
org 0x5400
function_061_patch:
    ; original prologue (replaced)
    movff 0x003, 0x00B
    movff 0x004, 0x00C

    ; if PRESET_B=1 and address in 0x56xx..0x5Fxx (u16), remap to 0x4Axx..0x53xx
    btfss 0x05E, 2, ACCESS
    goto rd_done

    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz rd_done

    movlw 0x56
    subwf 0x00C, W, ACCESS
    bnc rd_done

    movlw 0x60
    cpfslt 0x00C, ACCESS
    goto rd_done

    movlw 0x0C
    subwf 0x00C, F, ACCESS

rd_done:
    goto 0x4030

org 0x5440
function_025_patch:
    ; original prologue (replaced)
    clrf 0x010, ACCESS
    movff 0x003, 0x014

    ; remap destination start high-byte for preset B
    btfss 0x05E, 2, ACCESS
    goto wr_done

    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz wr_done

    movlw 0x56
    subwf 0x004, W, ACCESS
    bnc wr_done

    movlw 0x60
    cpfslt 0x004, ACCESS
    goto wr_done

    movlw 0x0C
    subwf 0x004, F, ACCESS

wr_done:
    goto 0x2E74

org 0x54C0
function_054_patch:
    ; original prologue (replaced)
    clrf 0x00B, ACCESS
    movff 0x003, 0x00C

    ; remap erase start/end window for preset B
    btfss 0x05E, 2, ACCESS
    goto er_done

    ; start address high-byte in +4 if upper words are zero
    movf 0x006, W, ACCESS
    iorwf 0x005, W, ACCESS
    bnz er_chk_end

    movlw 0x56
    subwf 0x004, W, ACCESS
    bnc er_chk_end

    movlw 0x60
    cpfslt 0x004, ACCESS
    goto er_chk_end

    movlw 0x0C
    subwf 0x004, F, ACCESS

er_chk_end:
    ; end address high-byte in +8 if upper words are zero
    movf 0x00A, W, ACCESS
    iorwf 0x009, W, ACCESS
    bnz er_done

    movlw 0x56
    subwf 0x008, W, ACCESS
    bnc er_done

    movlw 0x60
    cpfslt 0x008, ACCESS
    goto er_done

    movlw 0x0C
    subwf 0x008, F, ACCESS

er_done:
    goto 0x3DB2

org 0x5500
cmd_tail_patch:
    ; We replaced compare slots at 0x1E64..0x1E66.
    ; Recreate old behavior for cmd=0x1D and cmd=0x1E, then add cmd=0x20/0x21.

    movf 0x0A2, W, BANKED
    xorlw 0x1D
    btfsc STATUS, Z, ACCESS
    goto 0x1E02

    movf 0x0A2, W, BANKED
    xorlw 0x1E
    btfsc STATUS, Z, ACCESS
    goto 0x1E1C

    movf 0x0A2, W, BANKED
    xorlw 0x20
    bnz cmd_check_21

    ; cmd 0x20: set preset (data byte low bit), then apply only on change
    movf 0x0A3, W, BANKED
    andlw 0x01
    bnz preset_b

preset_a:
    btfss 0x05E, 2, ACCESS
    goto cmd_done
    bcf 0x05E, 2, ACCESS
    call load_active_filename_slot
    call 0x4574
    goto cmd_done

preset_b:
    btfsc 0x05E, 2, ACCESS
    goto cmd_done
    bsf 0x05E, 2, ACCESS
    call load_active_filename_slot
    call 0x4574
    goto cmd_done

cmd_check_21:
    movf 0x0A2, W, BANKED
    xorlw 0x21
    bnz cmd_check_22
    call send_filename_display_frames
    goto cmd_done

cmd_check_22:
    movf 0x0A2, W, BANKED
    xorlw 0x22
    bnz cmd_done
    call send_filename_generation_frames

cmd_done:
    goto 0x1E6C

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
                # ignore other record types
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
    with tempfile.TemporaryDirectory(prefix="dlcp_main_patch_") as td:
        td_path = pathlib.Path(td)
        asm = td_path / "main_presets_patch.asm"
        out_hex = td_path / "main_presets_patch.hex"
        asm.write_text(PATCH_ASM, encoding="ascii")
        subprocess.run(
            [gpasm, "-p18f2550", "-o", str(out_hex), str(asm)],
            check=True,
            capture_output=True,
            text=True,
        )
        return parse_intel_hex(out_hex)


def copy_table_a_to_b(mem: Dict[int, int], force: bool = False) -> Tuple[int, int]:
    src = 0x5600
    dst = 0x4A00
    size = 0x0A00

    for i in range(size):
        if (src + i) not in mem:
            raise RuntimeError(f"source table missing byte @ 0x{src + i:04X}")

    if not force:
        for i in range(size):
            a = dst + i
            if a in mem and mem[a] != 0xFF:
                raise RuntimeError(
                    f"destination not erased @ 0x{a:04X}: 0x{mem[a]:02X} "
                    "(use --force-copy to overwrite)"
                )

    written = 0
    changed = 0
    for i in range(size):
        s = mem[src + i]
        a = dst + i
        old = mem.get(a, 0xFF)
        mem[a] = s
        written += 1
        if old != s:
            changed += 1

    return written, changed


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


def set_main_eeprom_version_230(mem: Dict[int, int]) -> Tuple[int, int]:
    """Set MAIN EEPROM version tuple back to stock 2.30."""
    desired = {
        0xF00080: 0x02,
        0xF00081: 0x03,
        0xF00082: 0x30,
    }
    written = 0
    changed = 0
    for a, v in desired.items():
        old = mem.get(a, 0xFF)
        mem[a] = v
        written += 1
        if old != v:
            changed += 1
    return written, changed


def patch_usb_version_24(mem: Dict[int, int]) -> Tuple[int, int]:
    """Patch USB info response literals so host sees MAIN firmware version 2.4."""
    desired = {
        # cmd=0x06, subcmd=0x03 response payload at label_245:
        # [0x06, 0x03, 0x02, 0x04, ...] -> version 2.4
        0x240C: 0x03,
        0x2412: 0x02,
        0x2416: 0x04,
    }
    written = 0
    changed = 0
    for a, v in desired.items():
        old = mem.get(a, 0xFF)
        mem[a] = v
        written += 1
        if old != v:
            changed += 1
    return written, changed


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--in-hex",
        type=pathlib.Path,
        default=STOCK_MAIN_HEX,
        help=f"input main firmware hex (default: {STOCK_MAIN_HEX})",
    )
    ap.add_argument(
        "--out-hex",
        type=pathlib.Path,
        default=PATCHED_MAIN_HEX,
        help="output patched hex path",
    )
    ap.add_argument(
        "--gpasm",
        default="gpasm",
        help="gpasm executable (default: gpasm)",
    )
    ap.add_argument(
        "--force-copy",
        action="store_true",
        help="overwrite destination preset B range even if non-FF bytes are present",
    )
    args = ap.parse_args()

    in_hex = args.in_hex.resolve()
    out_hex = args.out_hex.resolve()
    out_hex.parent.mkdir(parents=True, exist_ok=True)

    base = parse_intel_hex(in_hex)
    new_mem = dict(base)

    table_written, table_changed = copy_table_a_to_b(new_mem, force=args.force_copy)
    patch_mem = assemble_patch(args.gpasm)
    patch_written, patch_changed = apply_patch_bytes(new_mem, patch_mem)
    eep_written, eep_changed = set_main_eeprom_version_230(new_mem)
    usb_written, usb_changed = patch_usb_version_24(new_mem)
    total_diff = summarize_diff(base, new_mem)

    write_intel_hex(out_hex, new_mem)

    print(f"input:  {in_hex}")
    print(f"output: {out_hex}")
    print(
        "table copy A->B:",
        f"bytes={table_written}",
        f"changed={table_changed}",
        "src=0x5600..0x5FFF",
        "dst=0x4A00..0x53FF",
    )
    print(
        "stub patch:",
        f"bytes={patch_written}",
        f"changed={patch_changed}",
        "hook_addrs=[0x1E64,0x20BE,0x27C0,0x2E6E,0x3DAC,0x4028]",
        "stub_ranges=0x4980..0x49FF,0x5400..0x55FF",
    )
    print(
        "eeprom version tuple:",
        f"bytes={eep_written}",
        f"changed={eep_changed}",
        "eeprom=[0xF00080..0xF00082]=[0x02,0x03,0x30]",
    )
    print(
        "usb version patch:",
        f"bytes={usb_written}",
        f"changed={usb_changed}",
        "code=[0x240C,0x2412,0x2416]=[0x03,0x02,0x04]  # host reports 2.4",
    )
    print(f"total bytes changed vs input: {total_diff}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
