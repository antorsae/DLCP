"""Build a USB-safe V3.0 MAIN HEX.

V3.0 is memory-identical to stock V2.3 on all programmed bytes, but the
committed app-only HEX omits some stock-emitted 0xFF records in erased/user-id
space. For sparse updaters that only touch pages present in the HEX, those
omitted records can leave stale bytes behind.

This builder restores every address that exists in the stock V2.3 HEX but is
absent from the canonical V3.0 HEX, preserving the stock byte value at each
such address. Today those bytes are all 0xFF.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import FIRMWARE_PATCHED_DIR, STOCK_MAIN_HEX, V30_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex


OUT_HEX = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.0_usb_safe.hex"


def build(out_hex: Path = OUT_HEX) -> Path:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    v30 = parse_intel_hex(V30_MAIN_HEX)
    merged = dict(v30)

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
