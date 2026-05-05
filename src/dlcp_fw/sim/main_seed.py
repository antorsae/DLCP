"""Backend-agnostic seeded MAIN-image construction.

The stock/patched MAIN release HEX files are application-only images.
For simulation we want recovered-device context by default, so app-only
inputs are merged onto the dump-based V2.3 combined seed:

* preserve boot block, config bytes, EEPROM, and User ID from the seed
* preserve recovered preset/DSP table space at 0x5600..0x5FFF
* replace app code/data at 0x1000..0x55FF from the input HEX

If the input HEX already carries a programmed boot block, it is treated
as a full-device image and copied verbatim.

Pure Python (HEX parse + dict merge + HEX write) — no simulator
runtime.  Was previously a side-helper in
``dlcp_fw.sim.main_gpsim``; lifted into its own module so test code
can import it without pulling in the gpsim wrapper.
"""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.paths import STOCK_MAIN_COMBINED_HEX

from .hexio import parse_intel_hex, write_intel_hex


MAIN_APP_PATCH_START = 0x1000
MAIN_APP_PATCH_LIMIT = 0x5600


def build_seeded_main_sim_hex(
    main_hex: Path,
    output_hex: Path,
    *,
    seed_hex: Path = STOCK_MAIN_COMBINED_HEX,
) -> Path:
    """Materialize a full-device MAIN image from an app-only input HEX.

    See module docstring for the merge contract.
    """
    source_hex = Path(main_hex)
    seed_source = Path(seed_hex)
    source_mem = parse_intel_hex(source_hex)
    has_boot_block = any(
        0x0000 <= addr < MAIN_APP_PATCH_START and value != 0xFF
        for addr, value in source_mem.items()
    )

    output_hex.parent.mkdir(parents=True, exist_ok=True)
    if has_boot_block:
        output_hex.write_bytes(source_hex.read_bytes())
        return output_hex

    merged = dict(parse_intel_hex(seed_source))
    for addr, value in source_mem.items():
        if MAIN_APP_PATCH_START <= addr < MAIN_APP_PATCH_LIMIT:
            merged[addr] = value & 0xFF
    write_intel_hex(output_hex, merged)
    return output_hex
