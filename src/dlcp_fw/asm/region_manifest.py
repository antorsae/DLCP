"""Stock V2.3 MAIN address space classification for the disasm-to-source converter.

Classifies every byte address in the stock firmware range as code, data, or erased.
"""

from __future__ import annotations

from typing import Literal

# Region boundaries: (start_inclusive, end_exclusive, type)
_REGIONS: list[tuple[int, int, str]] = [
    (0x1000, 0x1018, "code"),     # App entry + ISR dispatch stubs
    (0x1018, 0x10AC, "data"),     # USB descriptors, pointer/lookup tables
    (0x10AC, 0x47E6, "code"),     # function_000 through pre-inline-data code
    (0x47E6, 0x47FC, "data"),     # Inline data table (22 bytes, TBLRD target)
    (0x47FC, 0x4970, "code"),     # Remaining code after inline data
    (0x4970, 0x5600, "erased"),   # Free flash
    (0x5600, 0x6000, "data"),     # DSP preset table A
]


def classify_address(addr: int) -> Literal["code", "data", "erased"]:
    """Return the region type for a stock V2.3 byte address."""
    for start, end, rtype in _REGIONS:
        if start <= addr < end:
            return rtype  # type: ignore[return-value]
    raise ValueError(f"Address 0x{addr:04X} outside classified range")
