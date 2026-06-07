# Preset Filename LCD IMPL

Date: 2026-06-07
Status: **Implemented - simulator verified; hardware OCR not run**
Source spec: `docs/PRESET_FILENAME_LCD_SPEC.md`
Scope: fix the remaining Preset LCD row-0 blank/stuck immediate re-entry bug in
the paired MAIN `V3.3` / CONTROL `V1.72` filename feature. Keep the fix local
to CONTROL display lifecycle unless code evidence proves MAIN changes are
required.

This is a targeted bug-fix IMPL. The prior filename implementation already
covers slot-specific MAIN filename replies, CONTROL parsing/cache, Preset row-1
scrolling, A/B transition convergence, RAM-bank safety, and broad simulator
coverage. The remaining open defect is:

```text
B -> A -> B -> Input first visible -> immediate LEFT
observed LCD: ('                ', '521.4 22MG10F-v7')
```

The row-1 filename is valid, but row 0 is all spaces and did not self-recover in
a 60,188 ms native-chain probe. WU0 below created the file-backed red
regression evidence; the final evidence section records the lifecycle fix.

## Source Requirements

### Goals

- Preserve the Preset layout:
  - row 0: `Preset` plus compact health/fault/preset status, ending in
    `A`, `B`, or `!`;
  - row 1: active preset filename, incrementally rendered and scrolled.
- Fix the immediate-return race without adding retries or test sleeps.
- Ensure row-1 filename/cache text cannot be visible while Preset row 0 is
  16 spaces.
- Preserve same-slot cache reuse: the exact immediate LEFT path after B re-entry
  must issue zero fresh filename queries and consume zero new filename replies.
- Keep existing A/B transition, settled re-entry, standby/wake, parser, and RAM
  safety behavior passing.

### Non-Goals

- No PC host app changes.
- No protocol renumbering. Keep CONTROL query `0x26` and MAIN reply
  `BF/2D..4E`.
- No MAIN source or release-artifact churn unless source evidence proves the
  smallest safe fix requires it.
- No broad rewrite of the CONTROL menu, display loop, UART parser, or MAIN
  filename job state machine.
- No hardware flash during implementation unless separately requested after
  simulator/build gates pass.
- No masking by sleeps in firmware tests, operator docs, or production code.

### Timing Constants

Use the native simulator's 48 MHz universal clock:

- `TICKS_PER_MS = 48_000`.
- `PRESET_REENTRY_POLL_TICKS <= 4_800` (`0.1 ms`) while waiting for first
  visible Input and while monitoring immediate return.
- `ROW0_PRESET_REPAINT_BUDGET_TICKS = 960_000` (`20 ms`) from first sampled
  Preset re-entry state to a valid Preset row-0 line.
- `ROW0_BLANK_WITH_FILENAME_BUDGET_TICKS = 0`: once row 1 contains any
  filename/cache character during Preset re-entry, no sampled state may have row
  0 equal to 16 spaces.

### Invariants

- Filename-capable images remain paired: MAIN `V3.3` rev `>= 0x73` and CONTROL
  `V1.72` rev `>= 0x39`.
- CONTROL ignores stale filename replies whose echoed query id does not match
  the current `v172_fname_id`.
- Malformed, partial, or stale filename replies do not render partial text as
  valid.
- Query issue requires Preset, connected, and non-standby state. Reset, blanking,
  deadline cleanup, and row-0 health/fault status changes must still run or be
  synchronously invoked for Preset interruption cases such as PB1 loss or
  disconnect.
- Preset row-0 readiness must be established before row-1 valid/cache render can
  make filename text visible on a re-entered Preset screen.
- The row-0 status patch service only repairs cols 14/15; it is not a recovery
  mechanism for an all-space row 0.

### Explicit User Decisions

- Treat the all-blank first row as a real robustness bug, not an acceptable
  transient.
- Keep observing/reusing the existing implementation; most code is already
  present and works except for this race.
- Use a principled fix, not retries, not broad polling, and not test sleeps.
- Use 10 independent review agents/angles for this IMPL. The reviewer suggestion
  to reduce the count is intentionally not adopted because it conflicts with the
  explicit user request; scope discipline is enforced in the work units instead.

## Required Docs Read

- `AGENTS.md`: canonical layout, source/release paths, build scripts, simulator
  command policy, hardware gates, role-safe flashing requirements, and no-flash
  distinction.
- `README.md`: current V3.3/V1.72 release guidance, validation commands,
  flashing commands, and smoke checks.
- `docs/PRESET_FILENAME_LCD_SPEC.md`: behavioral/protocol contract and row-0
  immediate re-entry bug record.
- `docs/SIMULATION.md`: native chain simulator API and 48 MHz tick base.
- `docs/HARDWARE_TEST.md`: live hardware gate policy, role-derived HID paths,
  camera/OCR capabilities, and current stale `Active: A|B` references.
- `tests/sim/test_preset_filename_lcd_spec.py`: native-chain helpers, A/B state
  matrix, re-entry matrix, parser/code-size/RAM tests, and filename hardware
  manifest tests.
- `tests/hardware/test_live_state_transitions.py`: live front-panel preset and
  filename gates that must no longer accept the old Preset `Active: A|B` layout.
- `scripts/run_v171_v32_ledger_hardware_gate.py`: hardware phase text that still
  names `Active: A|B`.
- `src/dlcp_fw/asm/dlcp_control_v172.asm`: Preset draw, Input exit/dispatcher,
  filename reset/query, row-0 patch, deadline/query wait, and row-1 renderer.
- `src/dlcp_fw/asm/dlcp_main_v33.asm`: MAIN filename reply and prior RAM-bank
  fixes, to verify whether MAIN is truly untouched.

## Pre-Fix Implementation Evidence

- `tests/sim/test_preset_filename_lcd_spec.py`
  - `_wait_for_lcd()` defaults to `1_000_000` ticks (`20.83 ms`), too coarse for
    the immediate-return red test because `1 ms` extra settle avoided the bug in
    probes.
  - `test_v172_v33_full_native_chain_filename_preset_reentry_matrix` currently
    inserts `chain.step_ticks(20_000_000)` after first visible Input. That is a
    useful settled-navigation test but cannot be the canonical race regression.
  - Existing tests already cover many required side contracts:
    `test_v172_native_filename_clean_burst_sets_valid_len_cache`,
    `test_v172_fname_parser_duplicate_len_aborts`,
    `test_v172_fname_parser_late_len_after_char_aborts`,
    `test_v172_fname_parser_corrupt_len_aborts`,
    `test_v172_fname_parser_old_echo_positions_0_1_2_do_not_finalize`,
    `test_v172_fname_parser_old_echo_multiframe_start_len_end_do_not_finalize`,
    `test_v172_native_parser_old_echo_multiframe_start_len_end_do_not_finalize`,
    `test_v172_filename_acquisition_gates_background_health_polling_native`,
    `test_v172_native_row0_patch_consumes_lcd_budget_only`,
    `test_v172_fname_ram_equates_do_not_overlap_diag_identity`,
    `test_v172_filename_code_size_fits_before_bootloader`,
    `test_v33_v172_fixed_layout_labels_are_pinned`, and deployment identity spec
    tests.
- `src/dlcp_fw/asm/dlcp_control_v172.asm`
  - `v171_prs_screen_draw` writes row 0 before normal cache reuse, but the
    current source still fails in the immediate Input -> LEFT timing path. A
    static label-order proof inside this one label is therefore insufficient.
  - `v172_preset_filename_service` can render row 1 whenever Preset state and
    filename dirty/cache flags allow it.
  - `v172_preset_status_patch_service` patches only row-0 cols 14/15 and cannot
    reconstruct `Preset` after row 0 is all spaces.
  - The likely race crosses Input exit / dispatcher code, not only the Preset
    draw label. Required inspection points include `control_core_service_1912`,
    `v171_menu_dispatch`, `v171_prs_screen_draw`, and the filename services.
- Hardware/operator docs:
  - `docs/HARDWARE_TEST.md` and `tests/hardware/test_live_state_transitions.py`
    still contain front-panel preset acceptance text/assertions for
    `Active: A|B`. Those must be updated or explicitly scoped as legacy.
  - The separate filename-positive hardware gate already rejects `Active: A/B`,
    but the generic front-panel preset gate remains stale.

## Gap Analysis

### Already Working

- MAIN filename query/reply command shape and identity-framed burst.
- CONTROL parser validity checks, stale-id rejection, length seal, and cache
  finalization.
- Incremental row-1 render and scroll.
- A/B state transition convergence in native chain.
- Same-slot cache reuse after settled menu navigation.
- No-retry parser abort behavior.
- RAM-bank safety checker and broad sim suite after prior fixes.

### Missing / Stale

- No immediate no-settle Input -> LEFT regression test using sub-millisecond
  sampling.
- No dynamic trace that proves row 1 cannot become visible before row-0 Preset
  readiness.
- Current re-entry matrix hides the race with a `20,000,000`-tick sleep.
- Hardware front-panel preset gate/runbook still references old Preset row 1
  `Active: A|B`.
- Release identity docs (`README.md`, `AGENTS.md`, release notes/archive) must
  be updated if and only if canonical release artifacts are rebuilt.

### Must Not Be Deleted Or Migrated

- Keep the existing full native-chain A/B state matrix.
- Preserve the settled-navigation matrix as a separately named/non-race test if
  useful, but it cannot be the primary re-entry regression.
- Keep MAIN `filename_rev` torn-data protection.
- Keep no-retry parser abort behavior.
- Keep row-1 incremental rendering; whole-row row-1 rewriting is not an option
  for V1.72.
- Do not add persistent CONTROL RAM for this fix in the approved first pass. If
  implementation proves a new state cell/bit is unavoidable, pause, update this
  IMPL with the exact address/bit, update `dlcp_control_ram.inc` and aliases,
  preserve `0x245..0x254`, add cold-clear/overlap/BSR tests, and rerun review.

## Proposed Implementation

### WU0 - Reproduce And Pin The Bug

Add `test_v172_v33_full_native_chain_preset_reentry_immediate_left_never_blanks_row0`.

Required test shape:

1. Build the exact state:
   - initial preset B;
   - enter Preset and assert `('Preset         B', '521.4 22MG10F-v7')`;
   - press UP and assert `('Preset         A', '521.4 22MG10F-v5')`;
   - press DOWN and assert `('Preset         B', '521.4 22MG10F-v7')`.
2. Press RIGHT to Input.
3. Detect first visible Input using polling `<= 4_800` ticks, not `_wait_for_lcd`
   defaults.
4. Capture `input_visible_tick`, drive LEFT low within one poll quantum
   (`<= 4_800` ticks), and record `left_down_tick`.
5. Mark CONTROL TX/RX before LEFT.
6. Sample LCD and relevant CONTROL state every `<= 4_800` ticks:
   `display_state_index`, `FNAME_VALID`, `FNAME_ROW_DIRTY`, `FNAME_WANT_QUERY`,
   `FNAME_PENDING`, `v172_fname_gen`, `v172_fname_id`, `render_col/off`, and LCD
   rows.
7. Fail on:
   - any sampled state where row 1 contains filename/cache text and row 0 is
     16 spaces;
   - row 0 not reaching `Preset         B` within `960_000` ticks from first
     sampled Preset re-entry state;
   - any fresh `[0xB1, 0x26, *]` query;
   - any fresh `BF/2D..4E` filename reply;
   - `FNAME_WANT_QUERY` or `FNAME_PENDING` re-arming after row 1 is showing the
     cached B filename;
   - `v172_fname_gen` or `v172_fname_id` changing on this same-slot cache-reuse
     path.

Acceptance for WU0: the test is red on current source and records enough state
in the failure message to diagnose row-0/row-1 ordering.

### WU1 - Fix CONTROL Row-0 Readiness Ordering

Implement the smallest CONTROL lifecycle fix that makes row-0 Preset readiness a
real gate for row-1 cache/filename rendering.

Required inspection points:

- `control_core_service_1912` and the Input page LEFT/RIGHT return path;
- `v171_menu_dispatch` / display-state decrement/increment paths;
- `v171_prs_screen_draw`;
- `v172_preset_blank_row1_entry`;
- `fname_reset_blank`;
- `fname_reset_and_query`;
- `fname_reset_and_delay_query`;
- `v172_preset_filename_service`;
- `v172_preset_status_patch_service`;
- row-0 status snapshot helpers.

Required behavior:

1. Clear Preset row-0 readiness on every non-Preset exit/navigation transition
   or equivalent source-proven transition boundary.
2. Establish row-0 readiness only after full row-0 Preset draw plus row-1 entry
   blank has completed, or prove an equivalent ordering with native trace.
3. Block `fname_mark_row_dirty_valid` and/or row-1 render while row-0 readiness
   is false. Do not rely on the two-cell row-0 patch service to recover a blank
   full row.
4. Preserve valid same-slot cache reuse without issuing `cmd 0x26`.
5. Do not add retries or polling. Do not add persistent RAM in the approved first
   pass.
6. If the fix touches BSR-sensitive code around `lcd_*`, FSR0, bank-2 filename
   state, parser exits, or display-loop exits, keep explicit `movlb` discipline
   and let the RAM-bank checker prove it.

Acceptance for WU1: localized CONTROL diff, no MAIN source change unless
documented evidence requires it.

### WU2 - Add Dynamic Row0-Before-Row1 Guard

Add `test_v172_native_preset_entry_paint_precedes_filename_cache_reuse`.

This must be a dynamic native trace or DDRAM write-order proof for the immediate
return path. Static source-label ordering is supplemental only because the
broken source already mostly satisfies local `v171_prs_screen_draw` ordering.

The trace must record:

- first tick `display_state_index` is Preset after LEFT;
- first tick row 0 is a valid `Preset ... A|B|!` line;
- first tick row 1 contains filename/cache text;
- `FNAME_VALID`, `FNAME_ROW_DIRTY`, `render_col/off`, and LCD rows.

Required assertion: row-1 filename/cache visibility cannot precede row-0 Preset
readiness, and row-0 readiness must occur within `960_000` ticks.

### WU3 - Update Re-entry Matrices Without Hiding The Race

1. Make the primary six-case re-entry matrix immediate/no-settle after first
   visible Input, using the same `<=4_800`-tick watcher.
2. If the current `20_000_000`-tick settled path remains useful, rename it as a
   non-race/manual-settled coverage test so it cannot hide this class of bug.
3. Keep the existing A/B state matrix and standby/wake case.
4. Ensure all same-slot cache-reuse re-entry cases assert zero fresh filename
   queries. A delayed single query remains allowed only for slot flip or
   invalid/missing cache cases.

### WU4 - Hardware Gate And Docs Cleanup

Update stale operator/hardware surfaces that still describe old Preset row 1
`Active: A|B` as a valid Preset layout:

- `docs/HARDWARE_TEST.md`
- `tests/hardware/test_live_state_transitions.py`
- `scripts/run_v171_v32_ledger_hardware_gate.py`

Required behavior:

- Generic front-panel preset gate validates row-0 col 15 `A|B|!` on Preset and
  keeps MAIN active-preset/RAM checks.
- Filename-positive gate remains opt-in with
  `DLCP_HW_PRESET_FILENAME_CONFIRM=1` and reconstructs row 1 filename.
- Do not claim continuous live proof that row 0 “never blanks” unless a video or
  equivalent continuous capture method is added. With current OCR/still tooling,
  live immediate-reentry evidence is an optional manual spot check that can only
  show “does not remain blank after return” over the sampled capture window.

### WU5 - Release, Builders, And Evidence

Builder rules:

- CONTROL-only fix:
  - assemble/temp-test from source first;
  - run `scripts/build_v172_release.py --build-date 20260607` only when ready to
    update canonical CONTROL artifact;
  - do **not** run `scripts/build_v33_release.py` for “release consistency”.
- MAIN source/release change:
  - run `scripts/build_v33_release.py`;
  - record MAIN size impact and run MAIN RAM/code-size/version-label gates;
  - update README/AGENTS/release docs with the exact new MAIN identity.

Docs after artifact rebuild:

- If canonical release artifacts are rebuilt, update `README.md`, `AGENTS.md`,
  and release notes/archive/current runbook entries so advertised identities
  match the generated HEX:
  - MAIN filename-capable `V3.3` rev `>=0x73`;
  - CONTROL filename-capable `V1.72` rev `>=0x39` and build date.
- If no release artifact is rebuilt, record the no-artifact/no-doc-update reason
  explicitly.

Spec after code fix:

- Replace the open bug section in `docs/PRESET_FILENAME_LCD_SPEC.md` with
  resolved evidence: exact tests, measured maximum row-0 blank duration, source
  and release identities, and hardware status (`not run`, `manual spot check`,
  or `full OCR acceptance`).

## Likely Files

Expected:

- `src/dlcp_fw/asm/dlcp_control_v172.asm`
- `tests/sim/test_preset_filename_lcd_spec.py`
- `docs/PRESET_FILENAME_LCD_SPEC.md`
- `docs/IMPL_PRESET_FILENAME_LCD.md`
- `docs/HARDWARE_TEST.md`
- `tests/hardware/test_live_state_transitions.py`
- `scripts/run_v171_v32_ledger_hardware_gate.py`

If CONTROL release artifact is rebuilt:

- `firmware/patched/releases/DLCP_Control_V1.72.hex`
- `README.md`
- `AGENTS.md`
- release archive/current release docs if they mention exact V1.72 identity

Only if MAIN source/release changes:

- `src/dlcp_fw/asm/dlcp_main_v33.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.3.hex`
- MAIN release docs/identity entries

Only if new RAM is unavoidable after review update:

- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- generated RAM alias/checker artifacts

## Test Plan

### Focused Red/Green Tests

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_full_native_chain_preset_reentry_immediate_left_never_blanks_row0 \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_preset_entry_paint_precedes_filename_cache_reuse
```

Expected before fix: immediate LEFT test fails on current source. Expected after
fix: both pass.

### Existing Preset Filename Regression Suite

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py::test_v33_an0_hysteresis_monitor_banks_delay_counter_before_uart_ring_alias \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_full_native_chain_filename_preset_state_matrix \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_full_native_chain_filename_preset_reentry_matrix \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_full_native_chain_preset_b_survives_next_menu_standby_wake \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v32_native_chain_filename_control_old_main_blanks_after_timeout \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_raw_parser_old_echo_frame_positions_do_not_finalize
```

Add/update the old-MAIN timeout test so it asserts exactly one `cmd 0x26` from
Preset entry through pending expiry, then steps an additional expiry window and
asserts no new `cmd 0x26`, no `VALID`, no `PENDING`, and no `WANT_QUERY`.

### Protocol / Parser Compatibility Gate

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_filename_clean_burst_sets_valid_len_cache \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_parser_duplicate_len_aborts \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_parser_late_len_after_char_aborts \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_parser_corrupt_len_aborts \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_filename_wrong_id_start_disarms_keeps_pending \
  tests/sim/test_preset_filename_lcd_spec.py::test_raw_protocol_model_wrong_generation_start_len_end_does_not_finalize \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_parser_old_echo_positions_0_1_2_do_not_finalize \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_parser_old_echo_multiframe_start_len_end_do_not_finalize \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_parser_old_echo_multiframe_start_len_end_do_not_finalize \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_filename_acquisition_gates_background_health_polling_native \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_row0_patch_consumes_lcd_budget_only \
  tests/sim/test_preset_filename_lcd_spec.py::test_preset_filename_spec_splits_cmd26_from_cmd25_identity
```

Add a native behavioral `cmd 0x25` identity test before/during/after filename
acquisition if no existing behavioral test already proves ordered `BF/4F..53`
under filename activity.

### CONTROL Safety / Layout / RAM Gates

Run whenever `dlcp_control_v172.asm` or `dlcp_control_ram.inc` changes:

```sh
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.paths import SIM_ARTIFACTS_DIR, V172_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17

SIM_ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)
assemble_v17(
    V172_CONTROL_ASM,
    SIM_ARTIFACTS_DIR / "v172_control_listing_refresh.hex",
    output_lst=V172_CONTROL_ASM.with_suffix(".lst"),
)
PY
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v172
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_ram_equates_do_not_overlap_diag_identity \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_filename_code_size_fits_before_bootloader \
  tests/sim/test_preset_filename_lcd_spec.py::test_v33_v172_fixed_layout_labels_are_pinned \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_dirty_paths_reset_render_cursor \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_fname_preset_exit_cancels_pending_or_armed_query \
  tests/sim/test_preset_filename_lcd_spec.py::test_preset_filename_row1_pending_blank_is_incremental_not_full_clear
```

If MAIN source changes, also run:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v33 --target control-v172
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_preset_filename_lcd_spec.py::test_v33_filename_code_size_fits_before_preset_table \
  tests/sim/test_firmware_version_label.py
```

### Builder / Flash Safety Tests

Run if release artifacts are rebuilt:

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v172_v33_release_builders.py \
  tests/sim/test_dlcp_v33_release_flash.py \
  tests/sim/test_dlcp_control_flash_safety.py
```

After rebuilding `firmware/patched/releases/DLCP_Control_V1.72.hex`, add or run
a canonical-artifact immediate-reentry smoke using canonical release HEXes, not
only temp-assembled source HEXes.

### Hardware Helper / Runbook Tests

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_ledger_hardware_gate.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py --collect-only
```

Live hardware tests remain opt-in and are not required for simulator acceptance.

### Broad Simulator Gate

Canonical command from README/SIMULATION:

```sh
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Capacity fallback allowed with identical pass criteria:

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 tests/sim
```

For any CONTROL display-loop/lifecycle change, full `tests/sim` is a blocking
acceptance gate. Record exact command, pass/fail summary, warnings, and skipped
tests.

## Deployment And Smoke Plan

No deployment happens during IMPL drafting.

Implementation can be accepted with simulator/no-flash evidence. Live hardware
acceptance is separate and must be recorded as `not run` unless actually run.

### Role-Safe Flashing If User Later Approves Live Deploy

Preflight and bind role-derived paths:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py detect
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
```

Record `LEFT_HID` and `RIGHT_HID` from the role identification output, then:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v33_release_flash.py --path "$LEFT_HID" --left
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v33_release_flash.py --path "$RIGHT_HID" --right
scripts/flash_control_safe.sh --path "$LEFT_HID" --preflight-only
scripts/flash_control_safe.sh --path "$LEFT_HID"
```

### Post-Flash Gates If Live Deploy Runs

Informational USB/HID probes:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json
```

Blocking filename-capable identity gate before LCD behavior validation:

- add or run a concrete helper/test command that captures PB1 app-resident chain
  identity via `[0xB1, 0x25, id]`, for example a new
  `scripts/hardware_state_test.py pb1-app-identity --left-path "$LEFT_HID"`
  subcommand or an equivalent `tests/hardware/... --run-hardware` gate;
- the command must write JSON evidence with raw ordered `BF/4F..53` frames,
  assert major/minor `3.3`, reconstruct MAIN rev `>=0x73`, and record the JSON
  artifact path;
- validate CONTROL reports `V1.72` rev `>=0x39` in the same gate or a companion
  JSON-producing gate;
- treat USB/EEPROM rev evidence as informational only.

Blocking PB1 LCD behavior gate if live deploy/flash runs:

```sh
DLCP_HW_PRESET_FILENAME_CONFIRM=1 \
DLCP_HW_EXPECTED_PRESET_FILENAME='LX521.4 22MG10F-v7' \
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_preset_filename_lcd_confirm_reconstructs_pb1_name \
  --run-hardware
```

For a known non-empty PB1 filename, run the OCR gate and record the artifact
path. For an intentional blank-name case, hardware acceptance requires fresh
`START/LEN(0)/END` protocol evidence because a blank LCD row alone is not proof
of filename behavior. Run separate A and B OCR checks for full filename hardware
acceptance. A single B run is only a bug-reentry spot check and must be recorded
as such.

A live flash without this PB1 LCD behavior gate can be recorded as flashed and
basic-smoked, but it is **not** live hardware acceptance for this filename
feature.

No-deploy criteria:

- immediate re-entry can still produce 16-space Preset row 0;
- same-slot cache reuse emits a fresh filename query;
- query count indicates retries/polling storm;
- canonical HEX revision bumps are unexplained;
- hardware preflight cannot identify both MAIN roles.

Rollback:

- Reflash prior canonical V3.3/V1.72 artifacts from git history using the same
  role-safe wrappers.
- If only CONTROL changed, rollback CONTROL first and confirm MAIN identity,
  diagnostics, and preset state remain intact.

## Acceptance Criteria

- `docs/PRESET_FILENAME_LCD_SPEC.md` records the bug, timing constants, and
  after-fix resolved evidence.
- `docs/IMPL_PRESET_FILENAME_LCD.md` is reviewed with 10 roles and has no
  unresolved High or Medium findings.
- Immediate re-entry red test fails on current bug and passes after the fix.
- Dynamic row0-before-row1 trace fails on current bug and passes after the fix.
- Same-slot immediate re-entry issues zero fresh `cmd 0x26` queries, consumes
  zero new filename replies, and does not re-arm `WANT_QUERY`/`PENDING`.
- Primary six-case re-entry matrix no longer relies on the `20,000,000`-tick
  sleep; if retained, that slept path is renamed as non-race settled coverage.
- Existing A/B state matrix, standby/wake, parser compatibility, old-MAIN
  no-retry, CONTROL safety/code-size/RAM gates, builder/flash safety gates, and
  full `tests/sim` pass as required by changed files.
- Hardware front-panel preset gate/runbook no longer accepts the old Preset
  `Active: A|B` layout as filename-capable; generic preset confirmation now
  accepts `Volume` / `Active: A|B` only on Volume and `Preset ... A|B|!` on
  Preset.
- If release artifacts are rebuilt, README/AGENTS/release docs match final
  generated identities. If not rebuilt, docs record the no-artifact rationale.
- Hardware is not flashed unless separately requested/approved; hardware status
  is recorded as `not run`, `flashed without filename acceptance`,
  `manual spot check`, or `full OCR acceptance`.

## Post-Implementation Evidence

Actual files changed for this Preset LCD wave:

- `src/dlcp_fw/asm/dlcp_control_v172.asm`
  - removed the rejected row-0 recovery/full-redraw approach;
  - added Preset row-0 entry gating with
    `v172_fname_row0_status_snap_b2.7`;
  - made Volume, Setup, and Input page loops return to the top dispatcher when
    LEFT/RIGHT navigation is latched, so stale page code cannot keep writing
    LCD rows after menu state changes.
- `tests/sim/test_preset_filename_lcd_spec.py`
  - added the immediate no-settle re-entry regression;
  - added the dynamic row-0-entry-before-row-1-cache trace;
  - tightened the re-entry matrix so it no longer hides the race with a long
    post-Input settle sleep.
- `docs/PRESET_FILENAME_LCD_SPEC.md`
  - replaced the open bug with resolved evidence and documented bit 7 of the
    row-0 status snapshot.
- `docs/HARDWARE_TEST.md`,
  `tests/hardware/test_live_state_transitions.py`, and
  `scripts/run_v171_v32_ledger_hardware_gate.py`
  - corrected stale hardware/operator wording that expected the old Preset
    `Active: A|B` row-1 layout.
- `README.md` and `AGENTS.md`
  - updated current release/status evidence after rebuilding CONTROL.

Release artifacts:

- CONTROL was rebuilt with
  `PYTHONPATH=src .venv_ep0/bin/python scripts/build_v172_release.py --build-date 20260607`.
- Output artifact:
  `firmware/patched/releases/DLCP_Control_V1.72.hex`.
- CONTROL identity after rebuild: `V1.72 / rev 0x3F / build 20260607`.
- MAIN was not rebuilt for this bug fix. The paired existing MAIN source/hex
  identity is `V3.3 / rev 0x79`.

MAIN size impact:

- No increase from this feature wave. The implementation is CONTROL-local and
  no V3.3 build was run for the Preset row-0 re-entry fix.

CONTROL code-size/layout evidence:

- `tests/sim/test_v171_baseline.py` and
  `tests/sim/test_v172_v33_release_builders.py` passed in the static/release
  bundle below.
- `PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v172`
  -> `RAM bank safety: OK (control-v172)`.
- Release metadata remains below the bootloader region; the rebuilt CONTROL
  artifact carries metadata bytes for rev `0x3F` and build `20260607`.

Focused tests:

- Immediate re-entry focused trio:
  `test_v172_v33_full_native_chain_filename_preset_reentry_matrix`,
  `test_v172_v33_full_native_chain_preset_reentry_immediate_left_never_blanks_row0`,
  and `test_v172_native_preset_entry_paint_precedes_filename_cache_reuse`
  -> `8 passed in 76.69s`.
- Full Preset filename spec:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_preset_filename_lcd_spec.py`
  -> `176 passed in 217.59s`.
- Post-build smoke:
  selected V1.72 boot splash/waiting, immediate re-entry, entry-paint trace, and
  firmware version label tests -> `12 passed in 21.18s`.

Dynamic timing result:

- `input_visible_tick=583600000`
- `left_down_tick=583600000`
- `first_preset_tick=619200000`
- `row0_ready_tick=619200000`
- `row1_visible_tick=619200000`
- `exact_expected_tick=619200000`
- `row0_ready_delta_ms=0.000`
- No sampled state showed row-1 filename/cache text with row 0 equal to
  16 spaces.

Broad simulator gate:

- Static/release-adjacent bundle:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_ram_static_analysis.py tests/sim/test_v171_baseline.py tests/sim/test_v172_v33_release_builders.py tests/sim/test_dlcp_control_flash_safety.py tests/sim/test_v172_v33_diag_identity.py`
  -> `56 passed, 1 warning in 72.15s`.
- Full sim:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim`
  -> `1411 passed, 1 skipped, 4 warnings in 3062.67s`.
- Full collect:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests --collect-only -q`
  -> `1430 tests collected in 0.41s`.

Hardware/deploy:

- No hardware flash was performed during this bug-fix pass.
- Hardware collect:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py --collect-only -q`
  -> `18 tests collected in 0.06s`.
- Hardware phase manifest:
  `PYTHONPATH=src .venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py --collect --phase all`
  -> dry-run manifest generated with the updated Preset row-0 acceptance text.

Final status:

- Accepted in simulator: the Preset page can reuse the B filename cache on the
  immediate Input -> LEFT path without issuing a fresh filename query/reply and
  without any sampled row-1-visible/row-0-blank state.
- Remaining release risk is hardware-only: a live flash/OCR acceptance pass was
  not run in this implementation wave.

## Reviewer Findings And Iteration History

Ten independent review agents were run as requested. The draft was revised to
address all High/Medium findings before implementation.

### Review Roles

1. Simplicity/scope reviewer
2. Correctness/contract reviewer
3. Ops/tests/deploy reviewer
4. LCD lifecycle/state-machine reviewer
5. Native simulator/timing reviewer
6. Firmware RAM/BSR/code-size reviewer
7. Protocol/parser compatibility reviewer
8. Hardware/operator workflow reviewer
9. Regression/coverage reviewer
10. Maintainability/docs reviewer

### Findings Ledger

High findings addressed:

- Timing test could pass broken firmware due to `_wait_for_lcd` coarse
  `1_000_000`-tick polling. Disposition: WU0 now requires `<=4_800` tick
  polling and LEFT within one poll quantum.
- Row-0 repaint budget was undefined. Disposition: constants section defines
  `960_000` ticks / `20 ms` and zero tolerance for row1-visible plus row0-blank.
- Static label-ordering proof could pass broken source. Disposition: WU2 now
  requires dynamic native trace/DDRAM order proof; static source ordering is
  supplemental only.
- WU1 did not mandate a real row-0 readiness gate. Disposition: WU1 requires
  row-0 readiness before row-1 render and forbids relying on two-cell patch
  service.
- Same-slot immediate re-entry could pass by issuing a fresh query. Disposition:
  WU0/acceptance require zero fresh `B1/26`, zero new `BF/2D..4E`, and no
  `WANT_QUERY`/`PENDING`/id/gen churn.
- CONTROL RAM/BSR and code-size gates were conditional on MAIN changes.
  Disposition: CONTROL safety/layout gates are mandatory whenever CONTROL
  ASM/RAM changes.
- A new one-bit row0-ready state lacked legal storage. Disposition: approved
  first pass forbids new persistent RAM; any new RAM requires IMPL update and
  review rerun.
- Builder plan could bump MAIN unnecessarily. Disposition: V3.3 builder is run
  only if MAIN source/release identity intentionally changes.
- Hardware deploy commands omitted role-derived HID paths and app-resident
  identity gates. Disposition: deployment section now requires detect,
  identify-mains, explicit `--path`, PB1 app-resident `cmd 0x25` identity, and
  CONTROL rev validation.
- Hardware front-panel preset gate/runbook remained stale. Disposition: WU4 and
  likely files include `docs/HARDWARE_TEST.md`,
  `tests/hardware/test_live_state_transitions.py`, and
  `scripts/run_v171_v32_ledger_hardware_gate.py`.

Medium findings addressed:

- The primary re-entry matrix could keep the `20_000_000`-tick sleep.
  Disposition: WU3 makes immediate/no-settle the primary matrix and requires
  any slept path to be renamed non-race coverage.
- Protocol/parser compatibility was underrepresented. Disposition: test plan
  adds explicit parser, old-echo, health-poll, row0 patch, and cmd25 gates.
- Old/pre-feature MAIN no-retry was too weak. Disposition: regression suite now
  requires exactly one query through expiry and no requery after another expiry
  window.
- Query-service invariant was too broad for disconnect/loss cleanup.
  Disposition: invariants split query issue from reset/blank/status cleanup.
- Release docs were under-scoped. Disposition: WU5 updates README/AGENTS/release
  docs only when artifacts are rebuilt, otherwise records no-artifact rationale.
- Live immediate-reentry proof exceeded current OCR capabilities. Disposition:
  hardware section limits current live evidence to optional sampled/manual spot
  checks unless continuous/video capture is added.
- Full simulator gate was not blocking acceptance. Disposition: full `tests/sim`
  is a blocking acceptance gate for CONTROL display-loop/lifecycle changes.

Low findings remaining:

- None blocking. The canonical full simulator command uses `-n 16`; `-n 8` is
  retained as a capacity fallback with identical pass criteria.

### Review Gate Summary

- Targeted rerun after revisions: all 10 reviewer roles reported no remaining
  High/Medium findings.
- High findings remaining: 0
- Medium findings remaining: 0
- Low findings remaining: 0
- Review status: Reviewed - ready for implementation
