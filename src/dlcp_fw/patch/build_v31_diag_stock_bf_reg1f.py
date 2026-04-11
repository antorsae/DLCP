"""Build a V3.1 diagnostic variant with stock BF wait + stock TAS reg1F waits.

This variant narrows the remaining real-hardware regression surface after:
- coeff writes were restored to stock START/STOP waits
- full stock i2c_byte_tx did not recover the response
- stock BF-only showed a partial improvement

It keeps V3.1 ACKSTAT/BSR handling, but restores stock wait behavior in:
- i2c_byte_tx BF spin
- i2c_tas3108_reg1f_write START/STOP waits
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import V31_MAIN_ASM_CANONICAL, V31_MAIN_HEX_CANONICAL
from dlcp_fw.sim.v30_symbols import assemble_v30

SOURCE_ASM = V31_MAIN_ASM_CANONICAL
SOURCE_HEX = V31_MAIN_HEX_CANONICAL

_OLD_BF_BLOCK = """flow_i2c_byte_tx_bf:
    ; V3.1: bounded BF wait (stock was unbounded loop)
    call        wait_bf_clear_bounded, 0x0
    bc          flow_i2c_byte_tx_exit
    call        i2c_wait_bus_idle, 0x0
    ; V3.1 Fix A: ACKSTAT check after successful master TX
    ; Save/restore BSR — callers may have any bank selected and stock
    ; i2c_byte_tx never touched BSR.
    movff       BSR, ram_0x00E              ; save caller's BSR
    movlb       0x0
    btfsc       SSPCON2, 6, ACCESS          ; ACKSTAT
    bsf         dsp_fault_flags, 2, BANKED
    movff       ram_0x00E, BSR              ; restore caller's BSR
    movf        SSPCON2, W, ACCESS
"""

_NEW_BF_BLOCK = """flow_i2c_byte_tx_bf:
    ; DIAG: stock unbounded BF wait restored
flow_i2c_byte_tx_bf_spin:
    btfsc       SSPSTAT, 0, ACCESS
    bra         flow_i2c_byte_tx_bf_spin
    call        i2c_wait_bus_idle, 0x0
    ; V3.1 Fix A: ACKSTAT check after successful master TX
    ; Save/restore BSR — callers may have any bank selected and stock
    ; i2c_byte_tx never touched BSR.
    movff       BSR, ram_0x00E              ; save caller's BSR
    movlb       0x0
    btfsc       SSPCON2, 6, ACCESS          ; ACKSTAT
    bsf         dsp_fault_flags, 2, BANKED
    movff       ram_0x00E, BSR              ; restore caller's BSR
    movf        SSPCON2, W, ACCESS
"""

_OLD_REG1F_BLOCK = """i2c_tas3108_reg1f_write:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    call        wait_sen_bounded, 0x0
    bc          i2c_reg1f_done
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x1F
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    call        wait_pen_bounded, 0x0
i2c_reg1f_done:
    return      0
"""

_NEW_REG1F_BLOCK = """i2c_tas3108_reg1f_write:
    movff       WREG, ram_0x006
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; DIAG: stock START/STOP waits
reg1f_wait_sen_stock:
    btfsc       SSPCON2, 0, ACCESS
    bra         reg1f_wait_sen_stock
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x1F
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movlw       0x00
    call        i2c_byte_tx, 0x0
    movf        ram_0x006, W, ACCESS
    call        i2c_byte_tx, 0x0
    bsf         SSPCON2, 2, ACCESS
reg1f_wait_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    return      0
    bra         reg1f_wait_pen_stock
"""


def build_diag_variant() -> tuple[Path, Path]:
    source_text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    if _OLD_BF_BLOCK not in source_text:
        raise RuntimeError("V3.1 BF block not found; source drifted")
    if _OLD_REG1F_BLOCK not in source_text:
        raise RuntimeError("V3.1 reg1F block not found; source drifted")

    diag_text = source_text.replace(_OLD_BF_BLOCK, _NEW_BF_BLOCK, 1)
    diag_text = diag_text.replace(_OLD_REG1F_BLOCK, _NEW_REG1F_BLOCK, 1)

    diag_asm = SOURCE_ASM.with_name("dlcp_main_v31_diag_stock_bf_reg1f.asm")
    diag_hex = SOURCE_HEX.with_name("DLCP_Firmware_V3.1_diag_stock_bf_reg1f.hex")
    diag_lst = diag_hex.with_suffix(".lst")

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
