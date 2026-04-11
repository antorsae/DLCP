"""Build a V3.1 diagnostic variant with a HID memory-read command.

This keeps canonical V3.1 behavior intact and adds one new USB HID command:

- cmd 0x43: read program flash or raw EEPROM in small chunks

Request payload layout (64-byte HID OUT report):
- byte 0: command = 0x43
- byte 1: region (0 = flash, 1 = EEPROM)
- byte 2: address low
- byte 3: address high
- byte 4: length (1..61 bytes)

Response layout (64-byte HID IN report):
- byte 0: command echo = 0x43
- byte 1: status (0 = OK, 1 = bad region, 2 = bad length)
- byte 2: echoed length
- byte 3..: returned data

The output is also made USB-safe by restoring stock-emitted bytes that
canonical V3.1 omits, so sparse flashing does not leave stale data behind.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import (
    STOCK_MAIN_HEX,
    V31_DIAG_MEMREAD_USB_SAFE_ASM,
    V31_DIAG_MEMREAD_USB_SAFE_HEX,
    V31_MAIN_ASM_CANONICAL,
)
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex
from dlcp_fw.sim.v30_symbols import assemble_v30


SOURCE_ASM = V31_MAIN_ASM_CANONICAL
DIAG_ASM = V31_DIAG_MEMREAD_USB_SAFE_ASM
DIAG_HEX = V31_DIAG_MEMREAD_USB_SAFE_HEX
DIAG_LST = DIAG_HEX.with_suffix(".lst")

_DISPATCH_OLD = """    xorlw       0x03
    bnz         flow_hid_command_dispatch_15a8
    bra         fw_update_init_sequence
flow_hid_command_dispatch_15a8:
    bra         flow_hid_command_dispatch_154c
"""

_DISPATCH_NEW = """    xorlw       0x03
    bnz         hid_cmd_diag_memread_probe
    bra         fw_update_init_sequence
hid_cmd_diag_memread_probe:
    xorlw       0x01
    bnz         flow_hid_command_dispatch_15a8
    goto        hid_cmd_diag_memread
flow_hid_command_dispatch_15a8:
    bra         flow_hid_command_dispatch_154c
"""

_MEMREAD_INSERT = """
; ---------------------------------------------------------------------------
; HID Diagnostic Memory Read (cmd=0x43)
; Request : ram_0x11B=region (0=flash,1=eeprom), 0x11C/0x11D=addr, 0x11E=len
; Response: 0x15A=cmd, 0x15B=status, 0x15C=len, 0x15D..=data (max 61 bytes)
; ---------------------------------------------------------------------------
hid_cmd_diag_memread:
    movlb       0x1
    lfsr        FSR2, 0x015A
    movlw       0x43
    movwf       POSTINC2, ACCESS
    clrf        POSTINC2, ACCESS
    movf        ram_0x11E, W, BANKED
    movwf       POSTINC2, ACCESS
    iorlw       0x00
    bz          hid_cmd_diag_memread_bad_len
    movlw       0x3D
    cpfsgt      ram_0x11E, BANKED
    bra         hid_cmd_diag_memread_len_ok
hid_cmd_diag_memread_bad_len:
    movlw       0x02
    bra         hid_cmd_diag_memread_fail
hid_cmd_diag_memread_len_ok:
    movf        ram_0x11B, W, BANKED
    bz          hid_cmd_diag_memread_flash
    xorlw       0x01
    bz          hid_cmd_diag_memread_eeprom
    movlw       0x01
    bra         hid_cmd_diag_memread_fail
hid_cmd_diag_memread_flash:
    movff       ram_0x11C, ram_0x003
    movff       ram_0x11D, ram_0x004
    clrf        ram_0x005, ACCESS
    clrf        ram_0x006, ACCESS
    movff       ram_0x11E, ram_0x007
    clrf        ram_0x008, ACCESS
    movlw       0x5D
    movwf       ram_0x009, ACCESS
    movlw       0x01
    movwf       ram_0x00A, ACCESS
    call        flash_read, 0x0
    goto        flow_hid_command_dispatch_15aa
hid_cmd_diag_memread_eeprom:
    movf        ram_0x11C, W, BANKED
    movwf       ram_0x003, ACCESS
    clrf        ram_0x004, ACCESS
    movf        ram_0x11E, W, BANKED
    movwf       ram_0x00A, ACCESS
    lfsr        FSR2, 0x015D
hid_cmd_diag_memread_eeprom_lp:
    call        eeprom_read_byte, 0x0
    movwf       POSTINC2, ACCESS
    incf        ram_0x003, F, ACCESS
    decfsz      ram_0x00A, F, ACCESS
    bra         hid_cmd_diag_memread_eeprom_lp
    goto        flow_hid_command_dispatch_15aa
hid_cmd_diag_memread_fail:
    movwf       ram_0x05B, BANKED
    goto        flow_hid_command_dispatch_15aa

"""

_PRESET_TABLE_ANCHOR = """; ---------------------------------------------------------------------------
; DSP Preset Table B (clone of Preset A)
; ---------------------------------------------------------------------------
"""


def _rewrite_source(text: str) -> str:
    if "hid_cmd_diag_memread:" in text:
        return text
    if _DISPATCH_OLD not in text:
        raise RuntimeError("failed to locate HID dispatch tail")
    if _PRESET_TABLE_ANCHOR not in text:
        raise RuntimeError("failed to locate preset-table anchor")
    text = text.replace(_DISPATCH_OLD, _DISPATCH_NEW, 1)
    text = text.replace(_PRESET_TABLE_ANCHOR, _MEMREAD_INSERT + _PRESET_TABLE_ANCHOR, 1)
    return text


def _validate_code_size(output_hex: Path) -> None:
    mem = parse_intel_hex(output_hex)
    code_addrs = [addr for addr in mem if 0x1000 <= addr < 0x4C00]
    top = max(code_addrs)
    if top >= 0x4C00:
        raise RuntimeError(f"diagnostic code overflowed preset table at 0x{top:04X}")


def build() -> tuple[Path, Path]:
    text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    DIAG_ASM.write_text(_rewrite_source(text), encoding="utf-8")
    assemble_v30(DIAG_ASM, DIAG_HEX, output_lst=DIAG_LST)
    _validate_code_size(DIAG_HEX)

    stock = parse_intel_hex(STOCK_MAIN_HEX)
    built = parse_intel_hex(DIAG_HEX)
    merged = dict(built)
    restored = 0
    for addr, value in stock.items():
        if addr not in merged:
            merged[addr] = value
            restored += 1
    write_intel_hex(DIAG_HEX, merged)
    print(f"wrote {DIAG_HEX}")
    print(f"restored_stock_only_bytes={restored}")
    return DIAG_ASM, DIAG_HEX


def main() -> int:
    diag_asm, diag_hex = build()
    print(diag_asm)
    print(diag_hex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
