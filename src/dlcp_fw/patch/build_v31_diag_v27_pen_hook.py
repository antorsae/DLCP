"""Build a V3.1 diagnostic variant with a V2.7-shaped PEN timeout hook.

This is a hardware diagnosis build, not a canonical release:

- keep the current V3.1 logic base
- keep stock/unbounded START wait
- mirror the V2.7 Fix F shape at the STOP/PEN site:
  - stock PEN loop during boot
  - bounded PEN wait after boot
  - MSSP hard reset on PEN timeout
  - sticky DSP-fault flag on timeout

The timeout path intentionally mirrors the V2.7 hook semantics rather than
the current V3.1 caller contract. Use this build only for A/B diagnosis.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import V31_MAIN_ASM_CANONICAL, V31_MAIN_HEX_CANONICAL
from dlcp_fw.sim.v30_symbols import assemble_v30

SOURCE_ASM = V31_MAIN_ASM_CANONICAL
SOURCE_HEX = V31_MAIN_HEX_CANONICAL

_OLD_COEFF_BLOCK = """i2c_tas3108_coeff_write:
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; stock START wait
coeff_write_wait_sen_stock:
    btfsc       SSPCON2, 0, ACCESS
    bra         coeff_write_wait_sen_stock
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x30
    call        i2c_byte_tx, 0x0
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    bsf         SSPCON2, 2, ACCESS          ; stock STOP wait
coeff_write_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    bra         coeff_write_pen_done
    bra         coeff_write_pen_stock
coeff_write_pen_timeout:
coeff_write_pen_done:
    return      0
"""

_NEW_COEFF_BLOCK = """i2c_tas3108_coeff_write:
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; stock START wait
coeff_write_wait_sen_stock:
    btfsc       SSPCON2, 0, ACCESS
    bra         coeff_write_wait_sen_stock
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x30
    call        i2c_byte_tx, 0x0
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    bsf         SSPCON2, 2, ACCESS          ; V2.7-style PEN hook
    btfss       event_flags, 7, BANKED      ; boot complete?
    bra         coeff_write_pen_stock       ; no: stock loop during boot
    call        wait_pen_bounded, 0x0
    bc          coeff_write_pen_timeout
    return      0
coeff_write_pen_timeout:
    movlw       0x80                        ; mirror V2.7 patch_recover_mssp
    movwf       ram_0x003, ACCESS
    movlw       0x08
    call        mssp_hard_reset, 0x0
    bsf         dsp_fault_flags, 6, BANKED
    return      0
coeff_write_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         coeff_write_pen_stock
"""


def build_diag_variant() -> tuple[Path, Path]:
    source_text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    if _OLD_COEFF_BLOCK not in source_text:
        raise RuntimeError("V3.1 coeff-write block not found; source drifted")

    diag_asm = SOURCE_ASM.with_name("dlcp_main_v31_diag_v27_pen_hook.asm")
    diag_hex = SOURCE_HEX.with_name("DLCP_Firmware_V3.1_diag_v27_pen_hook.hex")
    diag_lst = diag_hex.with_suffix(".lst")

    diag_text = source_text.replace(_OLD_COEFF_BLOCK, _NEW_COEFF_BLOCK, 1)
    diag_asm.write_text(diag_text, encoding="utf-8")
    assemble_v30(diag_asm, diag_hex, output_lst=diag_lst)
    return diag_asm, diag_hex


def main() -> int:
    diag_asm, diag_hex = build_diag_variant()
    print(diag_asm)
    print(diag_hex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
