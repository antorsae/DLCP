"""Build a V3.1 experiment variant with stock-style cmd 0x07 reseed semantics.

This variant restores the V2.3/V3.0 guard on the USB HID upload family:

- `cmd 0x07` reseeds the flash upload cursor/page base only when `ram_0x01B == 0`

Canonical V3.1 removed that guard and always reseeds on `cmd 0x07`.

The output is also made USB-safe by restoring every stock-emitted byte that the
assembled experiment HEX omits, so sparse flash tools do not leave stale data
behind in untouched gaps.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import (
    STOCK_MAIN_HEX,
    V31_CMD07_STOCK_GUARD_USB_SAFE_ASM,
    V31_CMD07_STOCK_GUARD_USB_SAFE_HEX,
    V31_MAIN_ASM_CANONICAL,
)
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex
from dlcp_fw.sim.v30_symbols import assemble_v30


SOURCE_ASM = V31_MAIN_ASM_CANONICAL
OUT_ASM = V31_CMD07_STOCK_GUARD_USB_SAFE_ASM
OUT_HEX = V31_CMD07_STOCK_GUARD_USB_SAFE_HEX
OUT_LST = OUT_HEX.with_suffix(".lst")

_RESEED_OLD = """    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x07
    bnz         flow_hid_command_dispatch_13ba
    ; Robustness: cmd 0x07 always reseeds the flash upload cursor/page base.
    movlb       0x1
    movlb       0x0
    clrf        ram_0x0C5, BANKED
    movlw       0x56
    movwf       ram_0x083, BANKED
    movlw       0x00
    clrf        ram_0x082, BANKED
"""

_RESEED_NEW = """    movf        i2c_coeff_2, W, ACCESS
    xorlw       0x07
    bnz         flow_hid_command_dispatch_13ba
    movlb       0x1
    tstfsz      ram_0x01B, BANKED
    bra         flow_hid_command_dispatch_13ba
    movlb       0x0
    clrf        ram_0x0C5, BANKED
    movlw       0x56
    movwf       ram_0x083, BANKED
    movlw       0x00
    clrf        ram_0x082, BANKED
"""


def _rewrite_source(text: str) -> str:
    if _RESEED_NEW in text:
        return text
    if _RESEED_OLD not in text:
        raise RuntimeError("failed to locate V3.1 cmd07 reseed block")
    return text.replace(_RESEED_OLD, _RESEED_NEW, 1)


def build(
    *,
    out_asm: Path = OUT_ASM,
    out_hex: Path = OUT_HEX,
    out_lst: Path = OUT_LST,
) -> tuple[Path, Path]:
    text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    out_asm.write_text(_rewrite_source(text), encoding="utf-8")
    assemble_v30(out_asm, out_hex, output_lst=out_lst)

    stock = parse_intel_hex(STOCK_MAIN_HEX)
    built = parse_intel_hex(out_hex)
    merged = dict(built)

    restored = 0
    for addr, value in stock.items():
        if addr not in merged:
            merged[addr] = value
            restored += 1

    write_intel_hex(out_hex, merged)
    print(f"wrote {out_hex}")
    print(f"restored_stock_only_bytes={restored}")
    return out_asm, out_hex


def main() -> int:
    out_asm, out_hex = build()
    print(out_asm)
    print(out_hex)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
