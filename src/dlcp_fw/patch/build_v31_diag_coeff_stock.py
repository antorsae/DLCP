"""Build a V3.1 diagnostic variant with stock coeff-write START/STOP waits.

This variant is for hardware A/B testing only:
- keep the current V3.1 `cmd 0x07` upload reseed fix
- restore stock/unbounded START and STOP waits inside
  `i2c_tas3108_coeff_write`

If this variant restores audible biquad behavior on hardware, the
remaining V3.1 regression surface is narrowed to the post-boot
coefficient write timing path rather than flash upload placement.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import V31_MAIN_ASM_CANONICAL, V31_MAIN_HEX_CANONICAL
from dlcp_fw.sim.v30_symbols import assemble_v30

SOURCE_ASM = V31_MAIN_ASM_CANONICAL
SOURCE_HEX = V31_MAIN_HEX_CANONICAL

_OLD_COEFF_BLOCK = """i2c_tas3108_coeff_write:
    call        i2c_wait_bus_idle, 0x0
    bsf         SSPCON2, 0, ACCESS          ; SEN = START
    call        wait_sen_bounded, 0x0
    bc          coeff_write_pen_done
    movlw       0x68
    call        i2c_byte_tx, 0x0
    movlw       0x30
    call        i2c_byte_tx, 0x0
    movff       i2c_coeff_0, ram_0x049
    movff       i2c_coeff_1, ram_0x04A
    movff       i2c_coeff_2, ram_0x04B
    movff       i2c_coeff_3, ram_0x04C
    call        main_i2c_service_39a6, 0x0
    bsf         SSPCON2, 2, ACCESS          ; PEN = STOP
    ; Fix F: boot-gated PEN wait — bounded after boot, stock during boot
    btfss       event_flags, 7, BANKED      ; boot complete?
    bra         coeff_write_pen_stock       ; no: stock unbounded (safe during DSP init)
    call        wait_pen_bounded, 0x0
    bc          coeff_write_pen_timeout
    bra         coeff_write_pen_done
coeff_write_pen_timeout:
    ; PEN stuck: flag fault and force NACK for retry. On real HW the
    ; watchdog would catch true hangs; in gpsim the test harness
    ; force-clears SSPCON2 after clearing the fault model.
    bsf         dsp_fault_flags, 6, BANKED  ; flag DSP fault
    bsf         dsp_fault_flags, 2, BANKED  ; force NACK → volume_dsp_write retries
    bra         coeff_write_pen_done
coeff_write_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    bra         coeff_write_pen_done
    bra         coeff_write_pen_stock
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
    bsf         SSPCON2, 2, ACCESS          ; stock STOP wait
coeff_write_pen_stock:
    btfss       SSPCON2, 2, ACCESS
    bra         coeff_write_pen_done
    bra         coeff_write_pen_stock
coeff_write_pen_timeout:
coeff_write_pen_done:
    return      0
"""


def _is_already_stock_coeff_write(text: str) -> bool:
    """Structural "already stock" detector.

    Tolerant of ``call``→``rcall`` optimizations and minor whitespace
    drift inside ``i2c_tas3108_coeff_write``.  Codex flagged the
    earlier exact-text equality check (``_NEW_COEFF_BLOCK in text``)
    as brittle against the rev where the canonical V3.1 source
    converted three of the helper's ``call`` sites to ``rcall``;
    that drift is what made the builder non-idempotent on the
    current canonical source.

    The stock-wait shape is uniquely identifiable by the presence
    of BOTH the START-wait label ``coeff_write_wait_sen_stock:`` and
    the STOP-wait label ``coeff_write_pen_stock:`` AND the absence
    of the bounded-wait helper call ``wait_sen_bounded`` inside the
    function body.  The bounded variant (``_OLD_COEFF_BLOCK``) has
    neither of the stock labels and DOES call wait_sen_bounded, so
    the predicate cleanly distinguishes the two shapes.
    """
    body_start = text.find("i2c_tas3108_coeff_write:")
    if body_start < 0:
        return False
    # Bound the search to the function body.  The canonical source
    # ends the function at ``coeff_write_pen_done:`` followed by
    # ``return  0``; stop the scan at the next blank-line gap or
    # the next top-level label.
    body_end = text.find("\n\n", body_start)
    if body_end < 0:
        body_end = body_start + 4000
    body = text[body_start:body_end]
    return (
        "coeff_write_wait_sen_stock:" in body
        and "coeff_write_pen_stock:" in body
        and "wait_sen_bounded" not in body
    )


def _rewrite_source(text: str) -> str:
    if _is_already_stock_coeff_write(text) or _NEW_COEFF_BLOCK in text:
        return text
    if _OLD_COEFF_BLOCK not in text:
        raise RuntimeError("V3.1 coeff-write block not found; source drifted")
    return text.replace(_OLD_COEFF_BLOCK, _NEW_COEFF_BLOCK, 1)


def build_diag_variant() -> tuple[Path, Path]:
    source_text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    diag_asm = SOURCE_ASM.with_name("dlcp_main_v31_diag_coeff_stock.asm")
    diag_hex = SOURCE_HEX.with_name("DLCP_Firmware_V3.1_diag_coeff_stock.hex")

    diag_text = _rewrite_source(source_text)
    diag_asm.write_text(diag_text, encoding="utf-8")
    assemble_v30(diag_asm, diag_hex)
    return diag_asm, diag_hex


def main() -> int:
    diag_asm, diag_hex = build_diag_variant()
    print(diag_asm)
    print(diag_hex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
