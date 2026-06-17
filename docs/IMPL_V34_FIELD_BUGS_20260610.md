# IMPL V34 Field Bugs 20260610

Date: 2026-06-13
Status: Implemented and simulator-verified in MAIN V3.4 rev `0x9A`
Source spec: `docs/V34_FIELD_BUGS_20260610.md`
Scope: FIELD-5 only: MAIN V3.4 preset APPLY can commit/unmute a mixed
TAS3108 coefficient image on the two-MAIN chain. FIELD-1..4 remain fixed and
must stay green.

## Source Requirements

Goals:

- Fix FIELD-5 at the root. Async preset APPLY must publish a preset only after
  the selected preset table source is stable, every expected row is validated,
  and the final row succeeds.
- Cover both deterministic repro shapes:
  - locked Auto Detect RXCKR estimator hole plus IR B->A;
  - phase-only IR B->A with no SRC perturbation.
- Keep audio force-muted through retry, cancellation, and recovery until the
  final validated row succeeds.
- Preserve FIELD-4A ACK/NACK retry semantics, FIELD-4B volume-family row skip
  behavior, FIELD-3 LCD behavior, SRC lock robustness, and legacy boot apply.
- Keep MAIN compact. The current V3.4 app region is at the `0x4C00` wall.
  User override 2026-06-13: the release listing-margin floor is relaxed to
  10 bytes for this FIELD-5 safety fix.

Non-goals:

- No CONTROL change unless new evidence proves CONTROL contributes directly.
- No broad SRC4382 rewrite; SRC holes are a timing trigger, not the root fix.
- No TAS `0x59` special case and no post-apply TAS readback audit.
- No unrelated `chain_copy`, TOS/GIE, ISR alias, or SRC lock refactor.

Explicit user decisions:

- The fix must be robust, simple, elegant, and size-aware.
- Existing strict XFAIL DSP-integrity tests should be fixed, not bypassed by
  retries, timing sleeps, or one-row patches.

## Required Docs Read

- `AGENTS.md`: canonical paths, V3.4/V1.73 build/test/flash policy.
- `README.md`: current recommended pair, build, flash, and validation commands.
- `docs/V34_FIELD_BUGS_20260610.md`: FIELD-5 failure evidence and rejected
  bandaids.
- `docs/SIMULATION.md`: rust silicon-ring simulator and Python `Chain` facade.
- `docs/TEST_SIMULATOR.md`: simulator history and current authority pointers.
- `docs/HARDWARE_TEST.md`: live-rig identification, skipped hardware markers,
  and smoke policy.
- `docs/V34_SIZE_OPTIMIZATION_FINDINGS.md`: V3.4 code-size pressure.
- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md` and
  `docs/IMPL_SRC4382_AUTODETECT_LOCK_ROBUSTNESS.md`: SRC RXCKR-hole context.

## Current Implementation Evidence

MAIN preset APPLY:

- `src/dlcp_fw/asm/dlcp_main_v34.asm:5740`:
  `preset_table_apply_entry_core` reads a 4-byte header into `0x17..0x1A`,
  copies the TAS register to `stock_02F` and length to `stock_031`, then reads
  payload into the same scratch window.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:5755`: FIELD-4B skips TAS `0x30..0x36`.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:5781`: payload read reuses
  `flash_read_fsr2_0017`, so a stale/wrong header can redirect a valid payload.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:10071`: async
  `preset_job_apply_i2c_entry` retries only on carry or latched NACK.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:10331`: APPLY advances index/address on
  C=0. COMMIT later restores audio; it does not prove row identity.

Source selection:

- `src/dlcp_fw/asm/dlcp_main_v34.asm:4358`:
  `preset_b_remap_start_addr` maps logical `0x56xx..0x5Fxx` to B physical
  `0x4Cxx..0x55xx` from live `active_flags.bit2`.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:10309`: async APPLY seeds logical
  `0x5600` and relies on that live remap. Because A and B table headers have
  the same register/length sequence, header validation alone cannot detect a
  wrong physical A/B window.

Table-shape proof:

- Regular rows are index `0x00..0x5F`; final row is index `0x60`.
- For A: regular physical address `0x5600 + index*0x18`, final `0x5F00`.
- For B: regular physical address `0x4C00 + index*0x18`, final `0x5500`.
- Expected header:
  - index `0x60`: byte0 `0x01`, reg `0xD4`, len `0x04`, byte3 `0x00`;
  - `(index & 0x0F) == 0`: byte0 `0x01`, reg `0xC8 + (index >> 4)`,
    len `0x04`, byte3 `0x00`;
  - otherwise: byte0 `0x01`, reg `0x36 + index - (index >> 4)`, len `0x14`,
    byte3 `0x00`.
- The repro row at index `0x25` should be header `01 59 14 00`.

Tests:

- `tests/sim/test_v34_preset_src_hole_field_bug.py` had two strict XFAILs for
  FIELD-5. They proved PB2 could idle/unmute on A while missing TAS `0x59`
  and holding the wrong coefficient image. The XFAIL markers are removed in
  the implementation result below.
- `tests/sim/test_v34_field_bugs_20260610.py` pins FIELD-3/4A/4B.
- `tests/sim/test_v34_v173_refactoring_contracts.py` has the V3.4/V1.73 size
  gate and the separate `chain_copy` XFAIL.
- `tests/sim/test_ram_bank_safety.py` is the structural bank-safety gate.
- `src/dlcp_fw/sim/dlcp_sim_native.py:720` exposes `Chain.patch_core_flash`,
  enough to inject a bad row header without new simulator infrastructure.

## Gap Analysis

Exists:

- Force-mute before preset APPLY.
- Per-entry retry on bounded START/STOP timeout and TAS NACK.
- A compact row cursor and simulator visibility into TAS writes, MAIN RAM,
  LCD, fault counters, and coefficient snapshots.

Missing:

- Immutable job-owned physical source for the async transaction.
- Runtime proof that the row read matches `preset_job_index` before a TAS write.
- COMMIT proof that the final validated row for the latched source succeeded.
- Direct corrupted-header retry/cancel tests.

Risky:

- The shared core is used by both legacy blocking apply and async apply. Async
  validation must be opt-in and must not require legacy callers to set
  `preset_job_index`.
- MAIN size is at the edge. Current local baseline before FIELD-5 code was
  `listing_app_end=0x4B38`, `byte_margin=200`; the explicit user override for
  this safety fix lowered the acceptance floor to 10 bytes.

## Implementation Result - 2026-06-13

Status: FIELD-5 fixed in canonical MAIN `V3.4 rev 0x9A`; no CONTROL source or
artifact changes.

Changed files for the FIELD-5 implementation:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `tests/sim/test_v34_preset_src_hole_field_bug.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_preset_filename_lcd_spec.py`
- `tests/sim/test_v34_src4382_lock_hysteresis.py`
- `docs/V34_FIELD_BUGS_20260610.md`
- `docs/IMPL_V34_FIELD_BUGS_20260610.md`

MAIN implementation summary:

- Async preset APPLY now latches a job-owned physical cursor at
  HOLDING->APPLY: A regular rows start at `0x5600` and final row at `0x5F00`;
  B regular rows start at `0x4C00` and final row at `0x5500`.
- Async APPLY bypasses the live A/B remap and validates every 4-byte table
  header against `preset_job_index` before any TAS write. Header mismatch
  returns C=1 with `stock_00D.0=0`, does not advance the index, and stays in
  the muted retry path.
- Target changes during APPLY/retry rearm the job from row 0 of the new
  physical source while retaining the force-mute context.
- Standby/reconnect cancellation no longer clears a force-mute shadow for a
  partial preset image; lifecycle code owns any later safe unmute.
- Broad-gate verification exposed one adjacent SRC safety issue: Auto Detect
  route churn must not dirty master volume while unmuted, or the detect-cycle
  regression can still write a louder TAS `0x30` coefficient. The final source
  keeps muted route refreshes on the zero-write path and fixed-input route
  changes on the trim-convergence path.

Size ledger:

- Pre-FIELD-5 local V3.4 app end: `0x4B38`, margin `200` bytes before
  `preset_table_b` at `0x4C00`.
- Final V3.4 rev `0x9A` app end: `0x4BC8`, margin `56` bytes.
- User override for this safety fix: hard floor `10` bytes. Final margin
  passes both listing pins.

Final verification commands and results:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0x99 -> 0x9A)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom \
  tests/sim/test_preset_filename_lcd_spec.py::test_v34_v173_refactoring_layout_labels_are_pinned --tb=short
# 30 passed in 168.95s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_preset_src_hole_field_bug.py --tb=short
# 8 passed in 185.71s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_ram_bank_safety.py --tb=short
# 81 passed, 1 xfailed in 244.13s

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q \
  -k "v34 or v173 or preset or ram_bank or src4382"
# 599 passed, 1 xfailed in 244.71s

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
# 1590 passed, 2 skipped, 1 xfailed, 7 warnings in 636.25s
```

Known non-blocking outcomes:

- The xfail is
  `tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_chain_copy_call_sites_are_pre_gie_or_helper_masks_tos_rewrite`,
  the already-documented failed proof that `chain_copy` is interrupt-safe.
- The two skips are the existing V1.4/V1.5b stock CONTROL button precondition
  and a phase-sensitive ISR scratch-collision runtime catch whose structural
  companion remains pinned.
- No hardware playback or flashing was performed in this implementation pass.

## Proposed Implementation

### WU0 - Size Budget Before Code

- Measure current listing margin before edits and record it in this IMPL.
- Set `test_v34_v173_listing_size_gates_keep_refactoring_headroom` to
  `min_margin=10` per the explicit 2026-06-13 user override.
- Candidate fix should remain as compact as practical. Record the actual size
  cost and any size recovered, but the hard acceptance floor is now 10 bytes.
- Compare assembled deltas for the two compact shapes before committing:
  1. async-specific checked read/apply entry;
  2. shared-core validation mode.
  Choose the smaller correct shape.
- Feature demotion or diagnostics removal still requires explicit user
  approval.
- Post-implementation size evidence must include the full V3.4 ledger:
  source/commit or dirty-baseline identifier, `used_bytes_pre_preset_b`,
  `last_used_pre_preset_b`, `free_bytes_before_0x4C00`,
  listing app end/margin, and an explained program-byte diff for
  `0x1000..0x4BFF`.

### WU1 - Strengthen FIELD-5 Tests First

- Keep `tests/sim/test_v34_preset_src_hole_field_bug.py`.
- This test currently boots `V34_MAIN_HEX`. After any ASM edit, rebuild the
  canonical V3.4 hex before running it, or change the test to assemble a temp
  V3.4 hex from `V34_MAIN_ASM` and use that temp artifact. Do not run it
  against a stale release hex and treat the result as evidence for the source
  edit.
- Before firmware changes, make the expected success oracle explicit:
  - PB1 and PB2 must emit the final validated coefficient rows before
    effective mute clears or TAS `0x30` becomes nonzero;
  - for the known repro, both MAINs must emit TAS `0x59` before unmute;
  - if APPLY cannot validate a row, it must stay muted/retrying and must not
    reach healthy IDLE/COMMIT.
- After the fix lands, remove strict XFAILs and require both tests green.

### WU2 - Add Mandatory Corrupted-Header Runtime Tests

Use existing `Chain.patch_core_flash`; do not add simulator core features.

- Patch one MAIN's physical row header for row index `0x25`, e.g. register
  byte `0x59 -> 0x7F`, leaving payload untouched.
- Drive a preset switch through APPLY.
- Assert externally observable behavior:
  - no TAS write to the corrupt register;
  - no TAS `0x30` volume restore and effective mute remains asserted;
  - `preset_job_index` does not advance past the bad row;
  - job remains in APPLY/retry, not COMMIT/IDLE;
  - validation mode/temp state is clear after the call returns;
  - `stock_00D.0` is not set for a header mismatch.
- Patch the header back to `0x59`, step again, and assert the same transaction
  finishes safely.
- Add standby and reconnect variants while the mismatch is persistent. They
  must cancel/preempt without unmuting, clear validation temp state, stop
  Timer3, and leave UART/heartbeat service alive.

### WU3 - MAIN ASM: Transaction-Owned Physical Source

Edit `src/dlcp_fw/asm/dlcp_main_v34.asm`.

- At HOLDING->APPLY after final coalescing and after toggling
  `active_flags.bit2`, latch the physical source into preset-job state:
  A regular rows start at `0x5600`, final `0x5F00`; B regular rows start at
  `0x4C00`, final `0x5500`.
- Prefer reusing `preset_job_tbl_hi/lo` as the physical cursor to avoid new RAM.
  Update comments so these fields are physical during async APPLY, not logical.
- Async APPLY must read from that latched physical cursor and bypass
  `preset_b_remap_start_addr`. Keep the existing remap for legacy callers.
- COMMIT may publish/unmute only after the final row for this latched physical
  source succeeds. If the target changes during APPLY, rearm a new transaction
  from row 0 while retaining forced mute.
- Cancellation on standby/reconnect must not unmute a partial image. If the job
  force-muted audio, keep the user-audible path safe through the lifecycle
  transition; do not clear the forced-mute shadow unless a later full apply or
  explicit lifecycle owner restores volume safely.

### WU4 - MAIN ASM: Async-Only Header Validation

Implement validation in the smallest assembled form found in WU0.

Contract:

- Validation applies only to async preset APPLY, never to legacy blocking boot
  apply unless explicitly entered through the checked async path.
- Validate all four header bytes: `0x01`, expected TAS register, expected
  length, `0x00`.
- Use `preset_job_index` to compute expected register/length; no 97-byte table.
- Compare against the canonical consumed header copy (`stock_02F` for register,
  `stock_031` for length) and the original byte0/byte3 scratch before payload
  read. Do not duplicate register/length comparisons.
- On mismatch: no TAS write, no index advance, no COMMIT, C=1,
  `stock_00D.0=0`, retry/recovery path entered, audio remains muted.

PIC18 safety:

- Use physical `movff ..._phys` aliases or an explicit `movlb 0x2` plus a
  documented BSR exit contract for every bank-2 operand. Add a structural test
  for the validator site.
- If a transient validation flag is used, define it in source comments, make it
  clear outside `preset_job_apply_i2c_entry`, and clear it on all exits using
  C-neutral instructions. Do not destroy `STATUS.C` before the caller branches.
- Prefer branching on C before any flag-affecting cleanup if that is smaller
  than preserving/restoring C. Prove mismatch and timeout do not advance index.
- Do not use `stock_00D` as validator scratch unless restored exactly.
- Do not mask GIE around APPLY.

### WU5 - Coalescing, Cancellation, And Regression Coverage

- Add A->B->A and B->A->B tests where the second target arrives during APPLY
  and during a forced validation retry. The second transaction must start at row
  0 of the correct latched physical source and remain muted continuously.
- Keep FIELD-3/4A/4B tests green.
- Keep SRC lock robustness tests green; SRC changes are out of scope.
- Keep legacy blocking apply/no-pop behavior unchanged with a structural or
  focused sim test proving legacy callers do not enter async validation.

### WU6 - Build, Size, And Release Artifacts

- Before ASM edits, the current focused FIELD-5 tests may be run once to
  confirm the strict XFAIL baseline on the current canonical hex.
- After any ASM edit, the post-fix evidence sequence is:
  1. assemble/build the edited MAIN before testing hex-backed behavior;
  2. run focused FIELD-5 tests against that candidate;
  3. run fresh listing-margin and RAM-safety gates against that candidate;
  4. run canonical `scripts/build_v34_release.py`;
  5. rerun focused FIELD-5, SRC-lock, and listing-margin tests against the
     canonical artifacts.
- The simplest approved path is to use `scripts/build_v34_release.py` as the
  candidate build before each post-edit test command that imports
  `V34_MAIN_HEX`. If implementation instead teaches FIELD-5/SRC tests to
  consume a temp hex assembled from `V34_MAIN_ASM`, it must still perform the
  final canonical build and rerun focused tests against canonical artifacts.
- Run the listing-margin gate after every ASM attempt. The authoritative gate
  is `test_v34_v173_listing_size_gates_keep_refactoring_headroom`, not a raw
  HEX free-byte scan.
- Run RAM-bank safety after ASM edits.
- CONTROL rebuild is not required.
- If any CONTROL source/artifact or CONTROL/IR behavior changes despite the
  intended MAIN-only scope, run `tests/sim/test_v17x_isr_scratch_collision.py`
  plus the relevant V1.73 wake/preset IR suites before release.

## Likely Files

Code:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- possibly `src/dlcp_fw/asm/dlcp_main_ram.inc` if RAM comments/aliases need
  pinning for a transient flag or source-state field

Tests:

- `tests/sim/test_v34_preset_src_hole_field_bug.py`
- `tests/sim/test_v34_field_bugs_20260610.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_ram_bank_safety.py`

Artifacts/docs:

- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `docs/V34_FIELD_BUGS_20260610.md`
- this IMPL with post-implementation evidence

## Test Plan

Focused pre-fix red/green baseline on the current canonical hex:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_preset_src_hole_field_bug.py --tb=short
```

Expected before fix: strict XFAILs. Expected after fix and XFAIL removal:
FIELD-5 tests pass.

After ASM edits, build before tests that import `V34_MAIN_HEX`:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py --tb=short
```

Safety regression group:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_ram_bank_safety.py
```

Broader gate after ASM/build changes:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q \
  -k "v34 or v173 or preset or ram_bank or src4382"
```

Build and authoritative size gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom
```

Mandatory full simulator gate before release promotion or hardware playback:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Hardware Validation And Smoke

No live flash is part of IMPL drafting. Before recommending a fixed build for
speaker-connected playback:

1. Do not run unmuted/speaker-connected playback until these are all green:
   focused FIELD-5 tests, safety regression group, broader V3.4/V1.73 sim
   gate, build/size/RAM gates, and full `pytest tests/sim -n 16 -q`. Before
   that point, live activity is limited to HID/diagnostic checks with playback
   muted or speakers disconnected.
2. Preflight baked LX521.4 captures for both preset slots:
   `artifacts/LX521.4/LX521.4_22MG10F-v5.bin`,
   `artifacts/LX521.4/LX521.4_22MG10F-v5.json`,
   `artifacts/LX521.4/LX521.4_22MG10F-v7.bin`, and
   `artifacts/LX521.4/LX521.4_22MG10F-v7.json` must exist. These are shared
   A/B captures baked into each left/right flash, not side-specific captures.
   Abort on any release-flasher missing-capture/unbaked warning.
3. Run `scripts/hardware_state_test.py identify-mains --require-left-right`,
   derive `$LEFT_HID` and `$RIGHT_HID`, and flash by explicit role-derived
   paths, e.g. `scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --left`
   and `--path "$RIGHT_HID" --right`. Re-run `identify-mains` after
   re-enumeration.
4. Record the expected MAIN revision emitted by the fixed
   `scripts/build_v34_release.py`. Run `scripts/dlcp_diag.py --json --ch-map
   LEFT="$LEFT_HID" --ch-map RIGHT="$RIGHT_HID"` before and after. Capture PB1
   and PB2 Diagnostics LCD pages showing fresh `PB1 OK v3.4 NNNN` /
   `PB2 OK v3.4 NNNN` identity where `NNNN` exactly matches that expected
   fixed build revision on both MAINs after flash/re-enumeration.
5. Verify both MAINs expose A=`LX521.4 22MG10F-v5` and
   B=`LX521.4 22MG10F-v7`.
6. Hardware cannot currently prove live TAS coefficient equality from normal
   diagnostics alone; the reported failure looked `HEALTHY`. Hardware
   acceptance therefore requires artifacted, bounded audio/acoustic smoke or a
   separately added live coefficient oracle. Do not claim coefficient equality
   from flags/LCD/route alone.
7. Reproducible IR smoke: run A/B toggles at `100 ms`, `250 ms`, and `500 ms`
   inter-press delays, at least enough iterations to end on both A and B for
   each delay. Save command logs, diag JSON before/after each block, LCD
   captures, and audio/acoustic artifacts under a dated artifact directory.
8. Accept only if there is no audible/acoustic filter excursion, no spontaneous
   route/preset change, no DSP fault churn, PB1/PB2 identity stays fresh, and
   the final preset/filename matches the commanded end state for every block.

Rollback/mitigation:

- If any unsafe behavior remains, do not use the affected V3.4 build for
  playback. Keep playback muted during preset changes or flash a safer pair.
- If code size cannot meet the 10-byte gate, stop for size recovery instead
  of weakening the gate again.

## Acceptance Criteria

- Both FIELD-5 strict XFAILs become green with XFAIL removed.
- Direct corrupted-header tests prove no TAS write, no index advance, no
  COMMIT/IDLE, no unmute, and recovery after header repair.
- Standby/reconnect during retry cannot unmute a partial image.
- Coalesced A/B/A and B/A/B during APPLY/retry restart from row 0 of the
  correct physical source and stay muted continuously.
- Legacy blocking apply is unchanged.
- FIELD-3/4A/4B, SRC lock, RAM-bank safety, and listing-margin gates pass.
- IMPL is updated with changed files, size delta, exact test output, and
  no-deploy or hardware-smoke evidence.

## Risks, Assumptions, Open Questions

- The low-level scratch corruption phase is not yet instruction-proven. The
  transaction guard fixes the audio-safety contract regardless.
- Cancellation semantics may require careful ownership of forced mute across
  standby/reconnect. Treat any unmute of a partial image as a failing test.
- The compact validator may require size recovery before implementation. That
  is part of the work, not a reason to lower the gate.

## Reviewer Findings And Iteration History

Initial draft created 2026-06-13. Ten independent reviewer agents were used,
followed by two targeted rechecks for release/build/size and hardware smoke:

1. Robustness/root-cause coverage.
2. Simplicity/scope discipline.
3. State-machine elegance.
4. MAIN code-size compactness.
5. PIC18 assembly correctness/BSR/carry hazards.
6. Async concurrency/ISR/Timer3/UART safety.
7. Test-oracle completeness.
8. Release/build/size gate adequacy.
9. Hardware-validation realism.
10. Regression compatibility.

High/Medium findings addressed in this revision:

- Immutable APPLY source was optional. It is now mandatory WU3 with physical
  A/B regular and final-row addresses.
- Header-validation-only was insufficient because A/B headers match. The fix
  is now a transaction-owned physical source plus validation.
- Direct corrupted-header runtime test was optional. It is now mandatory and
  uses existing `Chain.patch_core_flash`.
- Size budget was vague. WU0 now requires baseline measurement and final size
  ledger evidence. Later user override relaxed the hard MAIN floor to 10 bytes.
- BSR and `STATUS.C` hazards were missing. WU4 now requires explicit bank
  discipline, C-neutral cleanup or branch-before-cleanup, and structural gates.
- `stock_00D.0` mismatch semantics were unspecified. WU4 now requires C=1 with
  `stock_00D.0=0`.
- Tests around cancellation/coalescing/retry were missing. WU2/WU5 now require
  standby, reconnect, A->B->A, and B->A->B coverage.
- The pre-unmute row-emission oracle was optional. WU1 now makes it mandatory.
- Raw HEX free-byte scan was not authoritative. The test plan now uses the
  listing-margin test.
- Regression review found that FIELD-5/SRC tests read `V34_MAIN_HEX`; the test
  plan now requires a V3.4 rebuild before any post-edit hex-backed tests, or an
  explicit temp-hex conversion.
- Release/size review strengthened that into a canonical artifact ceremony:
  candidate build/test, fresh listing/RAM gates, canonical build, canonical
  focused retest, and mandatory full simulator gate before release-ready or
  hardware-playback recommendation.
- Hardware review required speaker-safety gates. The hardware plan now forbids
  unmuted playback until all simulator gates are green, requires baked v5/v7
  capture preflight and explicit role-derived flashing, records PB1/PB2
  identity artifacts, and refuses to claim coefficient equality from ordinary
  healthy diagnostics alone.
- Hardware recheck required exact artifact identity. The plan now names the
  exact `LX521.4_22MG10F-v5.{bin,json}` and `LX521.4_22MG10F-v7.{bin,json}`
  capture files and requires PB1/PB2 LCD identity to match the expected fixed
  build revision emitted by `scripts/build_v34_release.py`.

Remaining Low findings:

- The compact implementation shape is intentionally not chosen in the IMPL; WU0
  requires assembled byte-delta comparison before coding. This is deliberate
  because PIC18 size can invert apparent source-level simplicity.
- Reuse of the existing recovery/advertise path for header mismatch may blur
  diagnostics. That is accepted for compactness unless free space permits a
  distinct diagnostic bit without lowering the size gate.
- CONTROL/IR no-churn tests are conditional because the approved scope is
  MAIN-only. If implementation touches CONTROL or IR behavior, WU6 names the
  extra V1.73 scratch/IR regression gate.

Review gate summary: no unresolved High or Medium findings remain in the IMPL.
