"""Build a V3.1 diagnostic variant with stock i2c_byte_tx master logic.

This variant is for hardware A/B testing only:
- keep the current V3.1 upload/remap logic
- keep the current V3.1 coeff-write path
- restore the full stock master-side `i2c_byte_tx` behavior
  (no bounded BF wait, no ACKSTAT/BSR handling)

If this variant restores full DSP audibility on hardware, the regression
surface is narrowed to the V3.1 `i2c_byte_tx` rewrite rather than the
surrounding preset-table or coeff-write logic.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import V31_MAIN_ASM_CANONICAL, V31_MAIN_HEX_CANONICAL
from dlcp_fw.sim.v30_symbols import assemble_v30

SOURCE_ASM = V31_MAIN_ASM_CANONICAL
SOURCE_HEX = V31_MAIN_HEX_CANONICAL

_OLD_I2C_BYTE_TX = """i2c_byte_tx:
    movff       WREG, ram_0x005
    movff       ram_0x005, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         flow_i2c_byte_tx_exit
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_master
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bz          flow_i2c_byte_tx_master
    bsf         SSPCON1, 4, ACCESS
flow_i2c_byte_tx_sspif:
    btfss       PIR1, 3, ACCESS
    bra         flow_i2c_byte_tx_sspif
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_master:
    ; Re-check mode (stock pattern preserved)
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_bf
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bnz         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_bf:
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
flow_i2c_byte_tx_exit:
    return      0
"""

_NEW_I2C_BYTE_TX = """i2c_byte_tx:
    movff       WREG, ram_0x005
    movff       ram_0x005, SSPBUF
    btfsc       SSPCON1, 7, ACCESS
    bra         flow_i2c_byte_tx_exit
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_master
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bz          flow_i2c_byte_tx_master
    bsf         SSPCON1, 4, ACCESS
flow_i2c_byte_tx_sspif:
    btfss       PIR1, 3, ACCESS
    bra         flow_i2c_byte_tx_sspif
    btfss       SSPSTAT, 2, ACCESS
    movf        SSPSTAT, W, ACCESS
    bra         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_master:
    ; DIAG: restore full stock master-side i2c_byte_tx path
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x08
    bz          flow_i2c_byte_tx_bf
    movff       SSPCON1, ram_0x004
    movlw       0x0F
    andwf       ram_0x004, F, ACCESS
    movf        ram_0x004, W, ACCESS
    xorlw       0x0B
    bnz         flow_i2c_byte_tx_exit
flow_i2c_byte_tx_bf:
    btfsc       SSPSTAT, 0, ACCESS
    bra         flow_i2c_byte_tx_bf
    call        i2c_wait_bus_idle, 0x0
    movf        SSPCON2, W, ACCESS
flow_i2c_byte_tx_exit:
    return      0
"""


def build_diag_variant() -> tuple[Path, Path]:
    source_text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    if _OLD_I2C_BYTE_TX not in source_text:
        raise RuntimeError("V3.1 i2c_byte_tx block not found; source drifted")

    diag_asm = SOURCE_ASM.with_name("dlcp_main_v31_diag_stock_i2c_byte_tx.asm")
    diag_hex = SOURCE_HEX.with_name("DLCP_Firmware_V3.1_diag_stock_i2c_byte_tx.hex")
    diag_lst = diag_hex.with_suffix(".lst")

    diag_text = source_text.replace(_OLD_I2C_BYTE_TX, _NEW_I2C_BYTE_TX, 1)
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
