"""Build a USB-safe V3.1 MAIN HEX.

Restores every address present in stock V2.3 but absent from the canonical
V3.1 HEX, preserving the stock byte at those addresses. This is intended for
sparse USB updaters that may not erase untouched pages.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import (
    ARTIFACTS_DIR,
    STOCK_MAIN_HEX,
    V31_MAIN_HEX_CANONICAL,
)
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex


SOURCE_HEX = V31_MAIN_HEX_CANONICAL
OUT_HEX = ARTIFACTS_DIR / "reanalysis" / "usb_safe" / "DLCP_Firmware_V3.1_usb_safe.hex"


def build(out_hex: Path = OUT_HEX) -> Path:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    v31 = parse_intel_hex(SOURCE_HEX)
    merged = dict(v31)

    restored = 0
    for addr, value in stock.items():
        if addr not in merged:
            merged[addr] = value
            restored += 1

    out_hex.parent.mkdir(parents=True, exist_ok=True)
    write_intel_hex(out_hex, merged)
    print(f"wrote {out_hex}")
    print(f"restored_stock_only_bytes={restored}")
    return out_hex


if __name__ == "__main__":
    build()
