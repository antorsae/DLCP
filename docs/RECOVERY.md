# Main Unit Recovery

This document captures the recovery flow for a bricked DLCP main unit.

Context:

- I read all available MAIN regions from a working unit with PICkit 5.
- The goal is to produce one Intel HEX file that contains program memory, config words, EEPROM, and user IDs so the MAIN MCU can be reprogrammed as a full-device recovery image.

## Source Exports

- `firmware/stock/main/DLCP Firmware V2.3-Program Memory.hex`
- `firmware/stock/main/DLCP Firmware V2.3-Configuration Bits.hex`
- `firmware/stock/main/DLCP Firmware V2.3-EE Data Memory.hex`
- `firmware/stock/main/DLCP Firmware V2.3-User ID Memory.hex`

## Mapping

- Program Memory export:
  - raw tabular word dump
  - maps directly to `0x0000..0x5FFF`
- Configuration Bits export:
  - decoded config report, not raw Intel HEX bytes
  - normalized to raw config bytes at `0x300000..0x30000D`
  - uses `firmware/stock/main/DLCP Firmware V2.3.hex` as the reference for masked and omitted raw-byte values
- EE Data Memory export:
  - raw `0x100`-byte page
  - maps to `0xF00000..0xF000FF`
- User ID Memory export:
  - raw `8`-byte table
  - maps to `0x200000..0x200007`

## Build The Recovery HEX

Run:

```bash
python3 scripts/word_dump_to_ihex.py combine-v23-main-exports
```

This writes:

- `firmware/stock/main/DLCP Firmware V2.3-combined.hex`

## What The Combined HEX Contains

- boot block from the PICkit 5 Program Memory readback
- application and DSP table space from the same Program Memory readback
- config-word region synthesized from the Configuration Bits report
- EEPROM bytes from the PICkit 5 EE Data readback
- user IDs from the PICkit 5 User ID readback

## Why This Matters

`DLCP Firmware V2.3.hex` in the repo is not a full-device recovery image by itself:

- it does not contain the boot block at `0x0000..0x0FFF`
- it contains the repo stock EEPROM snapshot, not the live unit EEPROM dump

`DLCP Firmware V2.3-combined.hex` is the file intended for full MAIN-unit recovery flashing when a bricked unit needs all regions restored from the PICkit 5 readback set.

## Verification

Tool regression:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_word_dump_to_ihex.py
```

Current expected delta vs repo stock `DLCP Firmware V2.3.hex`:

- extra boot-block bytes at `0x0000..0x0FFF`
- populated DSP-table differences in `0x5600..0x5EFF`
- EEPROM differences in `0xF00000..0xF000FF`
