# V3.3 MAIN Size Optimization Progress

Date: 2026-05-29
Status: active
Target source: `src/dlcp_fw/asm/dlcp_main_v33.asm`
Target build: `firmware/patched/releases/DLCP_Firmware_V3.3.hex`

## Baseline Size Snapshot

- Current baseline source: current main-line V3.3 before this campaign.
- Baseline assembly: clean via `assemble_v30(V33_MAIN_ASM, V33_MAIN_HEX)`.
- Baseline measured size:
  - `used_bytes_pre_preset_b=14939`
  - `last_used_pre_preset_b=0x4AC9`
  - `free_bytes_before_0x4C00=310`
- V3.3 identity feature drift vs current V3.2:
  - V3.2 current: `used=14883`, `last_used=0x4A91`, `free=366`
  - V3.3 current: `used=14939`, `last_used=0x4AC9`, `free=310`
  - Net V3.3 identity cost: `+56` used bytes, `-56` free bytes.

## Gate Status

Acceptance gate for each landed item:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests
```

Focused structure/build checks may run before the full gate, but a row is
not accepted until the full gate has completed without a new regression.

Exception noted 2026-05-29: an unrelated untracked draft pair,
`docs/PRESET_FILENAME_LCD_SPEC.md` plus
`tests/sim/test_preset_filename_lcd_spec.py`, is present in the workspace and
currently fails its own text-pin assertions. Size rows are therefore accepted
against the tracked repository suite using:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 tests \
  --ignore=tests/sim/test_preset_filename_lcd_spec.py
```

## Candidate Sequence

| Item | Candidate | Rationale | Risk |
| --- | --- | --- | --- |
| 1 | Mechanical current-V3.3 `call` -> `rcall` sweep | 14 reachable local calls remained in I2C recovery/hardening code after V3.3 layout drift. | low |
| 2 | Helper-based `diag_inc_sat` macro | The post-clamp macro expands to 9 instructions at 9 sites; tests must assert behavior/structure rather than exact macro body. | medium |
| 3 | Table-drive `main_i2c_service_27f0` source-route matrix | Route selection is large and table-shaped; V3.2 source-select/SRC4382 tests should be parameterized for V3.3 before edits. | medium/high |
| 4 | Factor preset-table I2C apply bodies | `main_i2c_service_381c` and `preset_job_apply_i2c_entry` share flash-read/TAS-burst shape, with different timeout returns. | medium/high |
| 5 | Reopen preset-B remap helper | V3.1/V3.2 ledgers left this blocked on old gpsim coverage; Rust sim can now carry a direct remap regression. | medium |

## Wave Ledger

| Wave | Scope | Edit | Assembles | Used Bytes | Last Used | Free Bytes | Delta vs Baseline | Tests | Result | Notes |
| --- | --- | --- | --- | ---: | --- | ---: | ---: | --- | --- | --- |
| W01 | Item 1: V3.3 `call` -> `rcall` sweep | Converted 14 reachable `call` sites in I2C timeout/recovery, bus-clear, ping, BF wait, and DSP fault status paths. | yes | 14913 | `0x4AAD` | 338 | `-26` used / `+28` free | `1215 passed, 18 skipped, 7 warnings in 633.60s` | accepted | Remaining reachable `call` -> `rcall` candidates: 0. |
| W02 | Item 2: helper-backed `diag_inc_sat` | Relaxed the diag-counter source tests to pin the clamp/saturate/increment contract for both V3.2 and V3.3, then changed V3.3 macro expansions to `movlb 0x02; lfsr FSR0,counter; rcall diag_inc_sat_fsr0`. | yes | 14839 | `0x4A65` | 410 | `-100` used / `+100` free vs baseline; `-74` used / `+72` free vs W01 | focused `69 passed`; tracked gate `1184 passed, 18 skipped, 10 warnings in 598.23s` | accepted | Full all-files run also found 4 failures in unrelated untracked `test_preset_filename_lcd_spec.py`; those files were not modified. Helper intentionally clobbers FSR0; audited current call sites for no live FSR0 dependency. |
| W03 | Item 3: table-driven `main_i2c_service_27f0` fixed-source route matrix | Parameterized source-select/SRC4382 tests to run current MAIN cases against both V3.2 and V3.3, then replaced the V3.3 fixed-input/status branch ladder with `main_i2c_service_27f0_route_table`. | yes | 14735 | `0x49FD` | 514 | `-204` used / `+204` free vs baseline; `-104` used / `+104` free vs W02 | focused `61 passed`; tracked gate `1212 passed, 18 skipped, 7 warnings in 642.15s` | accepted | Table rows preserve the old intermediate route request before the existing PORTC.0 route-2 fallback. Includes an overflow row for impossible SRC status bytes. |
| W04 | Item 4: shared preset-table apply core | Factored the duplicate flash header/data read plus TAS burst body from `main_i2c_service_381c` and `preset_job_apply_i2c_entry` into `preset_table_apply_entry_core`; legacy wrapper still dispatches SEN vs PEN timeout recovery separately. | yes | 14647 | `0x49A5` | 602 | `-292` used / `+292` free vs baseline; `-88` used / `+88` free vs W03 | focused `86 passed`; tracked gate `1212 passed, 18 skipped, 7 warnings in 680.47s` | accepted | Shared core returns `C=1` on timeout and uses `ram_0x00D.bit0` to mark PEN timeout for the legacy recovery path; async preset job still maps any timeout to retry/recover. |
| W05 | Item 5: preset-B remap helper | Added a V3.3 Rust-sim regression for assembly-side preset-B flash remap, then shared the duplicated start-address remap body across `flash_write`, `flash_erase`, and `flash_read` via `preset_b_remap_start_addr`; the erase end-address remap remains inline. | yes | 14613 | `0x4983` | 636 | `-326` used / `+326` free vs baseline; `-34` used / `+34` free vs W04 | focused `26 passed`; tracked gate `1214 passed, 18 skipped, 7 warnings in 618.73s` | accepted | Runtime regression drives V3.3 cmd `0x43` and HFD-style upload through the firmware HID dispatcher with active preset B, proving logical `0x5600` maps to physical `0x4C00` while preset A stays untouched. |
