# IMPL V34 FIELD-6-DSP Wake Route-Sync DSP Ownership

Date: 2026-06-13
Status: Implemented and simulator-gated in MAIN V3.4 rev 0xA0
Source spec: `docs/V34_FIELD_BUGS_20260610.md` (`FIELD-6-DSP`)
Scope: MAIN V3.4 wake/reconnect DSP ownership after route/channel sync.
CONTROL changes, Diagnostics-page STBY behavior, and IR mapping are out of
scope unless implementation evidence proves MAIN cannot enforce the safety
contract locally.

## Source Requirements

Goals:

- Fix FIELD-6-DSP at the root: no wake/reconnect lifecycle may report an awake,
  healthy, audio-capable MAIN while TAS `0x37..0x90` differs from the selected
  preset's clean image.
- Make DSP ownership explicit: route/channel sync may run, but a validated
  selected-preset writer must be the final writer of preset-owned coefficient
  bytes before any nonzero TAS `0x30` volume restore.
- Reuse the existing FIELD-5 physical-source/header-validation/NACK-aware apply
  semantics. Do not add a second `0x60`-row preset-table walker.
- Keep route-dirty handling single-owner. Do not copy the dispatcher bit1/bit4
  route ladders into wake/reconnect unless measured size evidence proves a
  shared path is impossible and all side effects are listed.
- Keep the implementation compact. MAIN V3.4 is size-constrained and the
  current listing margin must be verified before code changes.
- Tighten tests so live-audio predicates use actual TAS `0x30..0x33` register
  bytes, not only the last direct write-log payload.

Non-goals:

- No CONTROL rewrite, SRC4382 policy rewrite, new coefficient readback feature,
  or TAS `0x37` special case.
- No weakening of FIELD-3/4/5, SRC lock, mute, preset LCD, RAM-bank, or size
  gates.
- No implementation work in this IMPL pass.
- No live hardware flashing or playback in the implementation `/goal` unless
  the user separately authorizes hardware validation after sim/release gates.

Explicit user decisions:

- Robustness, first principles, elegance, DRY, simplicity, and compactness are
  mandatory.
- The current strict XFAIL must be fixed, not hidden by retries, sleeps, or a
  narrower oracle.

## Required Docs Read

- `AGENTS.md`: canonical paths, V3.4/V1.73 build/test/flash policy.
- `README.md`: recommended V3.4/V1.73 release pair and operator commands.
- `docs/V34_FIELD_BUGS_20260610.md`: FIELD-1..6-DSP bug ledger and source spec.
- `docs/IMPL_V34_FIELD_BUGS_20260610.md`: prior FIELD-5 async APPLY fix.
- `docs/SIMULATION.md`: rust `Chain` API and DSP register/write-log visibility.
- `docs/TEST_SIMULATOR.md`: historical preset simulator contracts.
- `docs/HARDWARE_TEST.md`: live-rig safety limits and bounded smoke commands.
- `docs/HARDWARE_LOOP.md`: artifact/acoustic decision patterns only; it is
  stale for V3.4/V1.73 and must not be copied verbatim.
- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md`: SRC route-hold contracts.
- `docs/IMPL_MUTE_DSP_REFRESH_BUG.md`: mute/volume ownership contracts.
- `docs/PRESET_FILENAME_LCD_SPEC.md`: preset UI/lifecycle scope and tests.

## Original Implementation Evidence

- `tests/sim/test_v34_v173_field_repros_20260613.py:191` is the route-sync
  strict XFAIL; its reason still says FIELD-5 and must be renamed. The separate
  Diagnostics-page front-panel STBY XFAIL in the same file is not this bug.
- `_tas30()` at `tests/sim/test_v34_v173_field_repros_20260613.py:132` reads
  the last direct `0x30` payload. Actual TAS register bytes are available via
  `read_main_dsp_reg`.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:4282` in `adc_boot_gate` writes zero TAS
  `0x30`, then calls `main_core_service_4574`, the legacy blocking preset walk.
- `src/dlcp_fw/asm/dlcp_main_v34.asm:4306-4312` sets `event_flags.bit1`,
  bit3, and bit4 together, then calls `cmd_dispatch_gated`.
- In `cmd_dispatch_gated`, bit1 route mutation runs early, bit3/volume is
  serviced before reconnect/bit6/bit4, and bit4 route sync calls
  `main_i2c_service_2100` near the end.
- `main_i2c_service_2100` emits overlapping TAS bursts; the isolated session-5
  delta includes `0x28..0x37`, which overwrites preset A's `0x37`.
- The FIELD-5 validated async path exists at `preset_job_apply_i2c_entry` plus
  `preset_table_apply_entry_core_async`; it is physical-source, header-checked,
  and NACK-aware. The legacy `main_core_service_4574` path is not.

Observed repro facts:

```text
before second IR power:
  digest 527246c85ab5, TAS 0x37 = 0x0f, actual TAS30..33 = 00000000
after second IR power:
  route-sync writes include 0x28..0x37
  digest 40436d84c08b, first diff (0x37, 0x0f -> 0x00)
  actual TAS30..33 = 00000000, last direct TAS30 payload = 00120bdb
after one normal volume-up:
  actual TAS30..33 = 0014408f, digest still 40436d84c08b
```

## Gap Analysis

Exists:

- A hardened async preset row-apply primitive.
- A legacy blocking wake/reconnect preset reapply.
- Simulator visibility into actual TAS registers and per-subaddress payloads.

Missing:

- A lifecycle final-writer invariant for wake/reconnect.
- A single shared muted route-drain owner that preserves bit1-before-bit4
  semantics without servicing volume before final selected-preset validation.
- Explicit ownership of deferred `event_flags.bit3`, `event_flags.bit6`,
  `event_flags.bit4`, `active_flags.bit7`, `preset_job_state`, and mute/fault
  state across success and failure.
- Wake/reconnect failure-injection tests for lifecycle reassert NACK, header
  mismatch, and timeout.
- A reconnect behavioral repro.
- Selected-preset coverage for both A and B, not only preset A.
- A V3.4-specific or parameterized `main_i2c_service_2100` table-shape guard.

Original risks:

- Calling full `cmd_dispatch_gated` to "run route sync" is unsafe because it can
  service bit3 volume and bit6 coefficient work before bit4.
- Calling plain `main_core_service_4574` after route sync is not enough because
  it lacks FIELD-5 validation and ACK/NACK retry.
- Moving or factoring `main_i2c_service_2100` requires an explicit clobber
  contract: TBLPTR/TABLAT/FSR1/FSR2/W/STATUS are not preserved; reload BSR
  before later BANKED accesses.
- A second preset walker will likely fail the 10-byte free-space floor and is
  worse lifecycle design even if it happens to fit.

## Final Implementation Summary

Implemented in MAIN V3.4 rev `0xA0`.

Files changed for FIELD-6-DSP:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `tests/sim/test_v34_v173_field_repros_20260613.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_v32_main_i2c_service_2100_tables.py`
- `tests/sim/test_preset_filename_lcd_spec.py`
- `docs/V34_FIELD_BUGS_20260610.md`
- this IMPL

Code shape:

- `cmd_dispatch_input_route_if_dirty` is the single factored owner for
  `event_flags.bit1` input-route work.  It may mark bit3 dirty for later
  fixed-input/mute convergence, but it returns before normal bit3/bit6 service.
- `cmd_dispatch_route_sync_if_dirty` remains the single owner for
  `event_flags.bit4` route/channel sync and preserves the original side effects:
  clear bit4, dirty filename row 1, set `stock_0C1=0x05`, and run the USB/timer
  tail when required.
- The reconnect/lifecycle owner (`active_flags.bit7`) now performs: cancel async
  APPLY, write TAS volume zero, drain bit1, drain bit4, clear bit6, run
  `main_core_service_4574`, and only after success allow normal volume dispatch.
- `main_core_service_4574` now uses the FIELD-5 validated
  physical-source/header/NACK-aware row writer (`preset_job_apply_i2c_entry`)
  instead of the legacy `main_i2c_service_381c` coefficient writer.
- Wake does not duplicate the lifecycle writer.  It writes TAS volume zero,
  sets bit1/bit4, arms `active_flags.bit7`, and calls `cmd_dispatch_gated` to
  enter the lifecycle owner.  This is the deliberate, guarded lifecycle bypass:
  active7 is set before the full dispatcher call, so bit3/bit6 cannot run before
  final validated reassert.  It is not the rejected unguarded full-dispatch
  route-drain shortcut.
- The lifecycle owner checks `INTCON.GIE` before the filename critical section;
  wake enters with GIE already off, so it skips the `bcf/call/bsf INTCON,7`
  filename reload sequence and cannot re-enable interrupts early.
- No second `0x60`-row preset-table walker was added.

Test changes:

- FIELD-6 XFAILs were removed; the separate Diagnostics front-panel STBY XFAIL
  remains out of scope.
- Live-audio detection now uses actual TAS `0x30..0x33` register bytes plus
  selected-preset golden coefficient images.
- Wake and reconnect lifecycle failure tests cover TAS address NACK, TAS data
  NACK, row-header mismatch, and MSSP STOP timeout.
- `tests/sim/test_v32_main_i2c_service_2100_tables.py` now parametrizes the
  route-sync table guard over V3.2 and V3.4.
- `tests/sim/test_preset_filename_lcd_spec.py` now detects CONTROL TX filename
  queries with aligned frames first and a sliding-frame fallback for capture
  windows that begin one byte before a valid `B1/26` query.  This preserves the
  filename contract while removing a capture-alignment assumption exposed by
  the final GIE-preserving timing shift.

Build/revision history during implementation:

- rev `0x9B`: rejected; first source attempt failed the 10-byte size floor
  with only 2 bytes free.
- rev `0x9C`: rejected; next source attempt failed the 10-byte size floor with
  only 8 bytes free.
- rev `0x9D`: intermediate green build before the route-drain refactor was
  corrected.
- rev `0x9E`: rejected; clean route-drain refactor assembled but consumed the
  entire reserve (`app_end=0x4C00`, 0 bytes free).
- rev `0x9F`: intermediate green build before the GIE-preserving filename
  critical-section guard.
- rev `0xA0`: final implemented build.  `app_end=0x4BF2`, 14 bytes free before
  `0x4C00`; 10-byte floor passes.

Final gate evidence:

```text
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
  built canonical V3.4 release (EEPROM rev 0x9F -> 0xA0)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_wake_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_reconnect_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply
  10 passed in 201.55s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_main_i2c_service_2100_tables.py
  6 passed in 0.32s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py
  194 passed in 368.56s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 16 tests/sim
  1623 passed, 2 skipped, 3 xfailed, 7 warnings in 536.83s
```

Remaining XFAILs are not FIELD-6-DSP:

- Diagnostics-page front-panel STBY ignored while parked on PB1/PB2 Diagnostics.
- `chain_copy` still rewrites TOS and has post-GIE call sites; this remains the
  strict interrupt-safety proof failure.

Release promotion/README update is deferred.  The fixed artifact is
simulator-gated, but this implementation goal explicitly excluded live hardware
flashing/playback; promote the recommended release only after a separately
authorized bounded hardware smoke.

## Proposed Implementation

### WU0 - Tighten FIELD-6-DSP Tests First

Update only the route-sync coefficient-safety test(s):

- Rename the XFAIL reason to `FIELD-6-DSP`.
- Leave the Diagnostics-page STBY XFAIL in this file explicitly out of scope or
  give it a different bug ID.
- Add `_tas_volume_regs(unit)` using actual `read_main_dsp_reg(unit, 0x30..0x33)`.
  Keep `_tas30_write_payload()` for log evidence and do not change unrelated
  mute/diagnostics tests that intentionally check emitted zero writes.
- Learn clean selected-preset images for both A and B.
- Add high-rate sampling from the second power/wake edge through convergence:
  fail on any sample where gates are up, MAIN is not logically muted, fault
  flags are clear, SRC is live, actual TAS `0x30..0x33` is nonzero, and the
  selected preset image differs from its golden.
- Add the existing follow-up proof: after the session-5 sequence, issue Hypex
  volume up/down and assert the selected image stays golden before and after
  actual TAS `0x30..0x33` becomes nonzero.
- Add an explicit XFAIL inventory assertion after the fix: no `FIELD-6-DSP`
  XFAIL remains; unrelated Diagnostics STBY XFAIL has a separate bug ID.
- Pre-fix red evidence must use `--runxfail` or temporary marker removal after
  WU0. A normal strict-XFAIL pytest pass is not red evidence.

### WU1 - Add Reconnect And Failure Behavioral Coverage

Add deterministic sim tests:

- `test_reconnect_reassert_never_restores_live_audio_on_wrong_coefficients`
  drives the `active_flags.bit7` reconnect reapply path with route sync dirty.
  Exercise both MAINs and selected preset A and B, or pair one dynamic B case
  with a structural preset-agnostic proof.
- `test_wake_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply`
  injects TAS data/address NACK, header mismatch, and bounded timeout in the
  wake lifecycle final writer.
- `test_reconnect_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply`
  repeats the same failure classes for reconnect.

Each failure test must assert:

- actual TAS `0x30..0x33` stays zero, or MAIN remains effectively muted/faulted;
- no healthy audio-capable state is reported with a wrong coefficient image;
- the path does not spin indefinitely;
- diagnostics/recovery flags surface using existing mechanisms;
- after the injected fault is cleared, the selected image becomes golden before
  any nonzero volume restore.

This is a required acceptance gate, not an audit-only task.

### WU2 - MAIN ASM: One Shared Muted Route-Drain Owner

Implement an explicit lifecycle order for wake and reconnect:

1. Keep actual TAS volume zero and defer any nonzero volume restore.
2. Drain the route mutation/sync work while muted in the existing semantic
   order: bit1 route mutation first, bit4 `main_i2c_service_2100` second.
3. Use one shared owner for bit1/bit4 route drain. Prefer factoring/jumping to
   existing dispatcher bodies/tails so normal dispatch and lifecycle
   wake/reconnect use the same code. Do not copy the route ladder or bit4 tail
   unless measured size evidence proves it is smaller and safer; if copied, list
   every copied side effect explicitly.
4. Preserve bit4 tail side effects currently adjacent to `main_i2c_service_2100`
   (`bcf event_flags.bit4`, filename dirty bit1, `stock_0C1=0x05`, and any
   required USB/timer side effects) or prove they are inapplicable at the new
   call site.
5. Do not service bit3 volume restore or bit6 table/coeff work before the final
   selected-preset writer. If bit3/bit6 are pending, save/defer/mask them under
   the transition table below.
6. Reload BSR and any required scratch after moved/factored route-sync calls;
   no live TBLPTR/FSR/STATUS assumptions may cross `main_i2c_service_2100`.

Do not implement this by calling full `cmd_dispatch_gated` and hoping mute
state routes around volume; the dispatcher order is the current bug surface.

### WU3 - MAIN ASM: One Shared Validated Preset Apply Primitive

The final selected-preset writer must be validated, NACK-aware, and shared:

- Reuse or factor the existing FIELD-5 apply primitive so async APPLY and
  lifecycle reassert call the same regular/final-row write logic. Acceptable
  shapes:
  - factor the existing `preset_job_apply_i2c_entry`/core into a callable row
    step used by both async APPLY and lifecycle reassert; or
  - replace/factor `main_core_service_4574` into the validated physical-source
    walker so there is only one full-table walk implementation.
- Explicitly forbid adding another loop over the `0x60` preset rows.
- Use existing bank2 preset-job cursor/index fields as scratch only when the
  async job is idle/cancelled, or keep/reuse the async job as the persistent
  lifecycle-reassert owner while forced-muted.
- Select the physical source from `active_flags.bit2`: A regular `0x5600`,
  A final `0x5F00`; B regular `0x4C00`, B final `0x5500`.
- On timeout, header mismatch, or TAS NACK, use one bounded failure model:
  either preserve/reuse preset-job APPLY state for retry while forced-muted, or
  exit with an explicit DSP fault/status and no volume-restore path until a
  later scheduled validated reassert succeeds. Do not allow "state idle, volume
  zero" as the whole recovery contract.
- Plain `main_core_service_4574` may still exist for legacy contexts only if it
  cannot be reached as the final FIELD-6-DSP safety writer.

If this shared validated path cannot fit the 10-byte floor, stop for size
recovery. Do not weaken the final-writer contract.

### WU4 - Lifecycle Transition Table

Wake and reconnect must share this ownership model:

| Phase | Owner/action | Required state |
| --- | --- | --- |
| Entry snapshot | Wake or reconnect prologue | TAS volume zero; record pending bit3/bit6 if set; do not clear them until success/failure owner decides |
| Muted route drain | Shared bit1/bit4 route-drain owner | `event_flags.bit1` and bit4 side effects handled once; bit3/bit6 not serviced |
| Final preset writer | Shared validated FIELD-5 apply primitive | selected A/B image is written from physical source and validated; no route/coeff writer follows before volume |
| Success | Lifecycle owner | clear lifecycle pending state; allow/defer bit3 volume restore only now; allow normal dispatch to resume; `preset_job_state` is idle or cleanly owned |
| Failure | Lifecycle owner | keep TAS volume zero/effective mute; surface existing fault/recovery status; preserve retry owner or schedule reassert; no healthy audio-capable wrong-image state |

Additional requirements:

- `adc_boot_gate`: drain route work while muted, then validated selected-preset
  reassert, then allow volume restore/status.
- `active_flags.bit7` reconnect branch: use the same ownership order and the
  same final writer; do not leave bit4/bit6 work to run after the final writer.
- Preserve GIE policy: wake-gate execution keeps GIE off until the existing
  wake re-enable point. Do not route wake through a helper that blindly executes
  the reconnect branch's `bsf INTCON,7` filename critical-section exit.
- Add structural tests for this GIE/restoration contract.

### WU5 - Structural Guards

Add/update structural tests:

- At named lifecycle helper/label boundaries, prove the happens-before contract:
  route sync before validated final writer; no coefficient writer after final
  writer before nonzero volume restore; no duplicated preset-table full walk.
- No wake/reconnect `main_i2c_service_2100` may run after the final validated
  preset writer unless another validated writer runs before any nonzero TAS
  `0x30`.
- Broaden this to all post-final-preset TAS coefficient writers: bit4
  `main_i2c_service_2100`, bit6/legacy `main_i2c_service_381c`, and direct
  volume restore ordering.
- Pin no TAS `0x37` special case and no duplicated preset-table logic.
- Add a duplication guard for route-drain fragments: copied route ladder/table
  fragments require explicit measured size justification in the IMPL update.
- Refactor the V3.2 `main_i2c_service_2100` table-shape test into a
  parameterized V3.2/V3.4 guard with one expected-table definition, rather than
  cloning a sibling test with duplicate expectations.
- Because Python lacks ordered cross-subaddress TAS transaction logs, runtime
  ownership assertions should rely on structural happens-before order plus
  final register state/high-rate live sampling unless an ordered transaction API
  is added.

### WU6 - Build, Size, Release, And Dirty-Tree Discipline

Before implementation:

- Run `git status --short`.
- Inspect focused diffs for V3.4 ASM/HEX/tests/docs so existing user work is not
  overwritten:

```bash
git diff -- src/dlcp_fw/asm/dlcp_main_v34.asm firmware/patched/releases/DLCP_Firmware_V3.4.hex tests/sim docs
```

- Capture baseline V3.4 revision, listing margin, and expected next revision.

During implementation:

- Build once per source attempt with `scripts/build_v34_release.py`; reuse that
  artifact for all gates unless source changes.
- If a successful build revision is superseded by more source changes, record
  that revision as rejected in the IMPL/ledger before rebuilding.
- Keep the explicit 10-byte free-space floor. If the shared validated lifecycle
  helper cannot fit, stop and do a size-recovery pass instead of weakening
  safety.

For release-ready status:

- Update `docs/V34_FIELD_BUGS_20260610.md` with the fixed V3.4 revision, test
  snapshot, and FIELD-6-DSP status.
- Update `README.md` recommended V3.4 revision if this becomes the canonical
  safety release. If README/release docs are deferred, explicitly state the
  build is not release-ready.

## Likely Files

Code:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`

Tests:

- `tests/sim/test_v34_v173_field_repros_20260613.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_v32_main_i2c_service_2100_tables.py`
- `tests/sim/test_ram_bank_safety.py`

Artifacts/docs:

- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `README.md`
- `docs/V34_FIELD_BUGS_20260610.md`
- this IMPL

## Test Plan

Focused pre-fix red after WU0, before firmware changes:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_session5_power_toggle_never_restores_live_audio_on_wrong_a_coefficients \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_reconnect_reassert_never_restores_live_audio_on_wrong_coefficients \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_wake_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_reconnect_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply
```

Post-implementation, build once and run focused gates:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_session5_power_toggle_never_restores_live_audio_on_wrong_a_coefficients \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_reconnect_reassert_never_restores_live_audio_on_wrong_coefficients \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_wake_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_reconnect_lifecycle_reassert_failure_keeps_audio_muted_until_validated_reapply \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_ram_bank_safety.py --tb=short
```

Release-adjacent gate, using the same built artifact if source did not change:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_dlcp_control_flash_safety.py::test_detect_static_hex_control_release_info_v173 \
  tests/sim/test_dlcp_control_flash_safety.py::test_preflight_reports_v173_target_release \
  tests/sim/test_dlcp_control_flash_safety.py::test_safe_control_wrapper_defaults_to_v173_release \
  tests/sim/test_firmware_version_label.py::test_v34_usb_and_eeprom_version_match_release_identity \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py
```

XFAIL inventory:

```bash
rg -n "FIELD-6-DSP|session5_power_toggle" tests docs
```

Broader gate, using the same built artifact if source did not change:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q \
  -k "v34 or v173 or preset or ram_bank or src4382 or field"
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Hardware Validation And Smoke

Hardware is not part of the implementation `/goal`. Do not run HFD, flasher
commands, HID writes, live hardware pytest, or speaker-connected playback unless
the user separately authorizes hardware validation after all simulator/release
gates pass.

If separately authorized, use a bounded V3.4/V1.73 smoke only after all sim
gates pass:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --left --path <LEFT_HID_PATH>
.venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --right --path <RIGHT_HID_PATH>
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json
.venv_ep0/bin/python scripts/hardware_state_test.py preset-standby-wake-timing-sweep \
  --delays-ms 50,250,1000 \
  --standby-dwell-s 1.0 \
  --wake-phase-a-timeout-s 15 \
  --wake-phase-b-timeout-s 25 \
  --wake-role-stable-polls 3
.venv_ep0/bin/python scripts/hardware_state_test.py reconnect-responsiveness-soak \
  --iterations 5 \
  --standby-dwell-s 1.0
```

Manual checks/caps for that authorized smoke:

- Abort on unbaked-preset warnings unless the run is explicitly an unbaked flash
  test.
- Confirm PB1/PB2 identity pages show the fixed V3.4 revision.
- Front-panel A/B: verify both A and B, then volume command after wake.
- SRC subset: known fixed digital input, switch to Auto Detect, perform one
  STBY/WAKE and one volume command at conservative level, then record
  diagnostics. Do not require the full 1-hour SRC soak unless promoting a
  release.
- First unmuted pass must be conservative volume with immediate stop on filter
  excursion, channel dropout, unexpected preset/route change, or `I`/`R`
  diagnostic growth without explanation.

## Goal Handoff Constraints

The implementation goal should do code, sim tests, build, docs, and release
evidence only. It must not:

- run HFD;
- flash MAIN or CONTROL;
- issue live HID writes to connected hardware;
- run `--run-hardware` pytest;
- do speaker-connected playback.

Hardware validation can be a later, separately authorized goal after the fixed
artifact has passed simulator and release-adjacent gates.

## Acceptance Criteria

- The route-sync coefficient-safety XFAIL named above is green with XFAIL
  removed; unrelated Diagnostics STBY XFAILs remain out of scope unless
  separately fixed.
- Actual TAS `0x30..0x33` bytes and follow-up volume restore are part of the
  FIELD-6-DSP oracle.
- Wake and reconnect tests prove selected preset A and B coefficient images are
  golden before and after a volume command.
- Wake and reconnect failure-injection tests prove final-writer NACK, header
  mismatch, and timeout cannot restore audio over a bad image and can recover
  after the fault clears.
- High-rate sampling finds no live wrong-image transient.
- Structural tests prove route/channel sync and any other coefficient writers
  cannot be final after the validated selected-preset writer.
- Structural tests prove no second preset-table walker and no duplicated
  route-drain state machine were added.
- FIELD-3/4/5, SRC lock, mute, RAM-bank, listing-size, release-adjacent, and
  full sim gates pass.
- `docs/V34_FIELD_BUGS_20260610.md` and this IMPL are updated with actual files
  changed, fixed revision, size delta, exact test commands, and final status.
- `README.md` is updated if the build is release-ready; otherwise the IMPL says
  release promotion is deferred.

## Risks, Assumptions, Open Questions

- The shared validated lifecycle reassert may still cost more bytes than a
  reorder-only fix. If so, size recovery is required; weakening the safety
  contract is not.
- Reconnect filename critical sections currently enable GIE unconditionally;
  wake must not inherit that behavior accidentally.
- The current Python API cannot prove global cross-subaddress TAS write order.
  Structural order plus final register state is acceptable unless an ordered log
  is added.
- Failure-retry ownership must not strand the unit silently muted forever; it
  must surface existing fault/recovery status and have a bounded retry owner.

## Reviewer Findings And Iteration History

Initial draft created 2026-06-13.

First review wave completed with 6 agents:

1. Root-cause fidelity.
2. DSP/TAS3108 register ownership.
3. MAIN wake/reconnect lifecycle.
4. PIC18 assembly/flags/banking safety.
5. Sim oracle correctness.
6. Regression compatibility.

Second review wave completed with 4 agents:

7. MAIN code-size compactness.
8. Simplicity/DRY/elegance.
9. Hardware safety.
10. Release/build process.

High/Medium findings addressed:

- Plain `main_core_service_4574` fallback is not validated or NACK-aware.
  WU3 now requires a shared FIELD-5-style validated lifecycle reassert.
- A second preset-table walker is too large and architecturally wrong. WU3 now
  forbids another `0x60`-row loop and requires factoring/reuse.
- Calling full `cmd_dispatch_gated` to drain route sync is unsafe because bit3
  volume and bit6 run before bit4. WU2 now requires a single shared muted drain
  owner for bit1 then bit4, with bit3/bit6 deferred.
- Copying route dispatcher fragments would create two route-sync state machines.
  WU2/WU5 now require shared route-drain ownership or measured justification.
- Deferred event/failure ownership was ambiguous. WU4 now contains an explicit
  transition table for bit3/bit4/bit6, `active_flags.bit7`, preset-job state,
  mute/fault state, success, failure, and retry ownership.
- Reconnect needed behavioral coverage. WU1 now requires a dynamic reconnect
  repro with follow-up volume command.
- Final-writer failure safety was not test-gated. WU1 now requires wake and
  reconnect NACK/header/timeout failure-injection tests.
- The test oracle used the last TAS `0x30` write payload. WU0 now requires an
  actual-register helper and separate write-log helper.
- Final-state checks could miss transient live windows. WU0 now requires
  high-rate sampling.
- A-only coverage was too narrow. WU0/WU1 require selected A and B coverage or
  a paired structural preset-agnostic proof.
- Structural guard was too narrow. WU5 now covers all post-final-preset TAS
  coefficient writers, not just bit4.
- V3.2-only route-sync table guard was insufficient. WU5 now requires a
  parameterized V3.2/V3.4 guard.
- Pre-fix red command was not actually red under strict XFAIL. Test plan now
  requires `--runxfail` after WU0.
- FIELD-6 naming conflicted with Diagnostics STBY. Docs now use FIELD-6-DSP and
  exclude the Diagnostics issue.
- Multiple build commands could bump revisions twice. WU6/test plan now says
  build once per attempt and reuse the artifact, with rejected intermediate revs
  documented.
- Dirty-worktree/revision safety was under-specified. WU6 now requires status,
  focused diffs, baseline revision, and expected next revision preflight.
- Hardware smoke was too vague and hardware was mixed into the handoff. The
  IMPL now forbids hardware in the implementation goal and gives a bounded
  separately authorized smoke recipe.
- Release docs were too loose. WU6/acceptance now require README/ledger updates
  for release-ready status.

No unresolved High/Medium review findings remain in the IMPL design.
