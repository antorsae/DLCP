"""Build a V3.1 diagnostic variant with stock BF wait in i2c_byte_tx.

This variant is for hardware A/B testing only:
- keep the current V3.1 upload/remap logic
- keep the current V3.1 ACKSTAT + BSR-safety handling
- restore only the stock/unbounded BF spin in `i2c_byte_tx`

If this variant restores full DSP audibility on hardware, the remaining
regression surface is narrowed to the V3.1 low-level I2C byte transmit path.
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
    ; DIAG: stock unbounded BF wait restored (isolating BF timeout vs other)
flow_i2c_byte_tx_bf_spin:
    btfsc       SSPSTAT, 0, ACCESS          ; BF set?
    bra         flow_i2c_byte_tx_bf_spin    ; yes: spin (stock behavior)
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


def build_diag_variant() -> tuple[Path, Path]:
    source_text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    if _OLD_BF_BLOCK not in source_text:
        raise RuntimeError("V3.1 BF block not found; source drifted")

    diag_asm = SOURCE_ASM.with_name("dlcp_main_v31_diag_stock_bf.asm")
    diag_hex = SOURCE_HEX.with_name("DLCP_Firmware_V3.1_diag_stock_bf.hex")
    diag_lst = diag_hex.with_suffix(".lst")

    diag_text = source_text.replace(_OLD_BF_BLOCK, _NEW_BF_BLOCK, 1)
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
