"""Build a V3.1 diagnostic variant with stock flash helper entry paths.

This variant removes only the V3.1 preset-B remap prologues from:
- flash_write
- flash_erase
- flash_read

The stock helper bodies remain in place. The output is also made USB-safe by
restoring stock-emitted bytes that canonical V3.1 omits, so sparse flashing
does not leave stale data behind.
"""

from __future__ import annotations

import re
from pathlib import Path

from dlcp_fw.paths import (
    FIRMWARE_PATCHED_DIR,
    STOCK_MAIN_HEX,
    V31_MAIN_ASM_CANONICAL,
)
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex
from dlcp_fw.sim.v30_symbols import assemble_v30


SOURCE_ASM = V31_MAIN_ASM_CANONICAL
DIAG_ASM = SOURCE_ASM.with_name("dlcp_main_v31_diag_no_flash_remap_usb_safe.asm")
DIAG_HEX = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.1_diag_no_flash_remap_usb_safe.hex"
DIAG_LST = DIAG_HEX.with_suffix(".lst")


def _strip_prologue(text: str, entry: str, stock_label: str) -> str:
    pattern = rf"{entry}:\n(?:.*\n)*?{stock_label}:\n"
    repl = (
        f"{entry}:\n"
        f"    ; DIAG: bypass V3.1 preset-bank remap prologue\n"
    )
    new_text, count = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"failed to rewrite {entry} prologue")
    return new_text


def build() -> tuple[Path, Path]:
    text = SOURCE_ASM.read_text(encoding="utf-8", errors="replace")
    text = _strip_prologue(text, "flash_write", "flash_write_stock")
    text = _strip_prologue(text, "flash_erase", "flash_erase_stock")
    text = _strip_prologue(text, "flash_read", "flash_read_stock")

    DIAG_ASM.write_text(text, encoding="utf-8")
    assemble_v30(DIAG_ASM, DIAG_HEX, output_lst=DIAG_LST)

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
