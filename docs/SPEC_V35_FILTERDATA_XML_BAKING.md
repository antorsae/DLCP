# V3.5 FilterData XML Preset Baking Spec

Date: 2026-06-26
Status: implemented in V3.5 release tooling

## Goal

Change the V3.5 MAIN release flash path so `scripts/dlcp_v35_release_flash.py`
bakes preset tables directly from Hypex FilterData XML instead of requiring
pre-captured `.bin` plus `.json` sidecars.

Default V3.5 release inputs:

- Preset A: `artifacts/LX521.4/FilterData/LX521.4 22MG10F-v5/Config.xml`
- Preset B: `artifacts/LX521.4/FilterData/LX521.4 22MG10F-v8/Config.xml`

The release path must not create `LX521.4_*.bin` or `LX521.4_*.json` artifacts.
It must compute the equivalent 0x0A00 preset-table payload in memory, derive
the filename slot from the FilterData directory name, then reuse the existing
MAIN flash overlay/finalize machinery.

## Current Behavior

`src/dlcp_fw/flash/dlcp_release_flash_common.py` hard-codes:

- `artifacts/LX521.4/LX521.4_22MG10F-v5.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v5.json`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.json`

The V3.5 wrapper forwards these as `--capture-a --meta-a --capture-b --meta-b`
to `dlcp_main_flash.py`. `dlcp_main_flash.py` loads each 0x0A00 binary table,
loads the filename bytes from the JSON sidecar, resolves the flash base, and
overlays the table into the target hex before bootloader streaming.

The existing overlay contract is still correct:

- Preset A table: `0x5600..0x5FFF`
- Preset B table for V3.1+: `0x4C00..0x55FF`
- Filename EEPROM slot A: `0x60..0x7D`
- Filename EEPROM slot B: `0x83..0xA0`
- Active filename RAM remains `0x02C0..0x02DD`

## Required New Behavior

`scripts/dlcp_v35_release_flash.py --left|--right|--all-ch` must:

1. Require the canonical V3.5 hex as before.
2. Require the default XML files above, not `.bin/.json` captures.
3. Build preset A and preset B tables in memory from XML.
4. Use HFD pole/zero recomputation mode, not embedded XML coefficient cache.
5. Derive config names from the FilterData directory names:
   - `LX521.4 22MG10F-v5`
   - `LX521.4 22MG10F-v8`
6. Encode filename slots exactly like the old sidecar path: ASCII bytes,
   truncated to 0x1E if needed, padded with `0xFF`.
7. Construct the same `CaptureOverlay` shape already consumed by
   `dlcp_main_flash.py`: `preset`, `table`, `name_slot`, `config_name`,
   `flash_base`.
8. Print preflight lines that identify XML path, config name, mode, flash base,
   and table SHA256.
9. Never write generated `.bin` or `.json` files as part of release flashing.

The lower-level `.bin/.json` capture arguments may remain available for
manual/debug compatibility, but V3.5 defaults must not depend on them.

## XML Conversion Requirements

The XML conversion must use the existing HFD semantic converter behavior:

- table size: `0x0A00`
- 6 channels
- 15 biquads per channel
- channel config rows: TAS registers `0xC8..0xCD`
- biquad rows: TAS registers `0x37..0x90`
- final gain/default rows preserved as currently emitted
- delay encoding preserved: payload `00 <floor(delay/10)> 00 00`
- TAS coefficients packed as signed 28-bit fixed-point words

The V3.5 release path must force `mode="hfd-pz"` for these XML inputs. This is
important because v5/v8 XML files can contain stale embedded `b0/b1/b2/a1/a2`
and `zconst` cache values. The release source of truth is the semantic XML
filter fields, not the embedded coefficient cache.

Known validation anchors:

- v5 XML in `hfd-pz` mode generates SHA256
  `5e352d409ce18c79ae5aa558b988fb0dddbacda4ca455aa0ffb9336a138e78d8`,
  matching the existing v5 captured `.bin`.
- v8 XML in `hfd-pz` mode generates SHA256
  `474f93fceabb7d06e6936e11c1075ad59c1e588a9696290f831cf9039d2eb043`.

## Suggested Implementation Shape

Prefer a first-class XML overlay loader over temporary files.

Add lower-level `dlcp_main_flash.py` support for XML sources, for example:

- `--filterdata-a PATH`
- `--filterdata-b PATH`
- optional `--filterdata-mode {hfd-pz,direct,legacy,auto}`, default `hfd-pz`
- optional `--name-a/--name-b` remains an override

`PATH` may be either a `Config.xml` file or a FilterData directory containing
`Config.xml`. If `--name-*` is absent, derive the display name from the
directory that contains `Config.xml`.

Then update `dlcp_v35_release_flash.py` / shared release wrapper to forward:

- `--filterdata-a artifacts/LX521.4/FilterData/LX521.4 22MG10F-v5`
- `--filterdata-b artifacts/LX521.4/FilterData/LX521.4 22MG10F-v8`

Do not route this through generated capture files. The handoff to the existing
flash code should be in-memory `CaptureOverlay` objects.

## Tests

Add or update tests for these gates:

1. V3.5 wrapper forwards XML defaults, not capture defaults.
2. Missing XML inputs are a hard parser error before USB writes.
3. Missing `.bin/.json` captures no longer trigger the V3.5 "without baked
   presets" warning when XML inputs exist.
4. `--info-only` and `--finalize-only` still do not require XML inputs.
5. XML-derived v5 table equals the existing v5 captured table byte-for-byte.
6. XML-derived v8 table has the expected SHA256 above.
7. Filename slots derived from directory names match expected padded bytes.
8. Preflight output includes XML path, config name, mode, flash base, and table
   SHA256.
9. The release path does not create `.bin` or `.json` output files.
10. Existing `--capture-a/--capture-b` lower-level compatibility remains tested
    in `dlcp_main_flash.py` tests.

## Docs To Update With Implementation

- `AGENTS.md`: V3.5 release ceremony and CLI map.
- `README.md`: current operator flash flow.
- Any V3.5 release/runbook text that still says local `.bin/.json` captures are
  required for the default V3.5 path.

Historical V3.1/V3.2/V3.3/V3.4 runbooks may continue documenting captured
`.bin/.json` behavior unless those wrappers are migrated separately.
