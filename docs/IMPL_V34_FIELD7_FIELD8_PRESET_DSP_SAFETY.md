# IMPL V34 FIELD-7/FIELD-8 Preset DSP Safety

Date: 2026-06-14
Status: Implemented in MAIN V3.4 rev 0xA4 - simulator validated, not hardware promoted
Source spec: `docs/V34_FIELD_BUGS_20260610.md` (`FIELD-7-DSP`, `FIELD-8-PRESET`)
Scope: current MAIN V3.4 + CONTROL V1.73 pair, plus staged compatibility
pairs named by `tests/sim/test_v34_v173_compatibility.py`.

FIELD-7 is a MAIN DSP safety bug: live audio can be restored while TAS
`0x37..0x90` is not the golden coefficient image for the MAIN's reported
active preset.  FIELD-8 is a value-propagation bug: CONTROL/PB1 and PB2 can
diverge on preset or mute while no operator-visible fault/lost state is
surfaced.

## Source Requirements

Goals:

- Fix FIELD-7 at the root.  A MAIN must never be connected, fault-free,
  source-live, unmuted, job-idle, and carrying nonzero TAS `0x30..0x33` while
  TAS `0x37..0x90` differs from the selected-preset golden image.
- Fix FIELD-8 at the root.  CONTROL, PB1, and PB2 must converge to the same
  preset/mute value or surface an operator-visible fault/lost state.  Hidden
  gate drops or silent PB splits do not satisfy the contract.
- For mute-on, convergence means actual audio safety: every non-standby,
  source-live MAIN must either close the gate or drive TAS `0x30..0x33` to
  zero.  For mute-off, nonzero volume may return only after the selected
  coefficient image is golden.
- Keep the implementation compact and first-principled.  No subaddress hacks,
  sleeps, or blind retry loops as the correctness mechanism.
- Reuse existing owners: MAIN async preset APPLY, FIELD-5/6 validated
  coefficient/lifecycle ownership, CONTROL full-sync step 6, and V1.73 muted
  reassert.  Add a new owner only if trace proves no existing owner fits.
- Preserve the size rule: MAIN V3.4 must retain at least 10 bytes before the
  `0x4C00` table wall.

Non-goals:

- No live hardware flashing/playback in this implementation goal unless the
  user separately authorizes it after simulator and release gates pass.
- No SRC4382 policy rewrite.  `SRC 0x13=0` with `UNLOCK=0` is a locked RXCKR
  estimator hole, not hard source loss.
- No CONTROL UI redesign, TAS readback audit feature, duplicate preset state
  machine, or canonical ASM/HEX trace instrumentation.

Explicit constraints:

- Existing XFAIL preset/DSP tests are to be fixed, not worked around.
- RAM-bank, TOS, carry, BSR, STATUS.C, and GIE safety must be proven for every
  touched path.  The existing `chain_copy` XFAIL is not permission to touch an
  affected unsafe path.

## Required Docs Read

- `AGENTS.md`, `README.md`, and `docs/HARDWARE_TEST.md`.
- `docs/V34_FIELD_BUGS_20260610.md`.
- `docs/IMPL_V34_FIELD_BUGS_20260610.md`.
- `docs/IMPL_V34_FIELD6_WAKE_ROUTE_SYNC_DSP_OWNERSHIP.md`.
- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md` and
  `docs/IMPL_SRC4382_AUTODETECT_LOCK_ROBUSTNESS.md`.
- `docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md`.
- `docs/SIM_EXPLORATORY_BUG_TAXONOMY.md`.
- `docs/SIMULATION.md` and `docs/TEST_SIMULATOR.md`.
- `docs/PRESET_FILENAME_LCD_SPEC.md`.
- PIC reference companions named by `AGENTS.md` if GIE/TOS/BSR/STATUS behavior
  is touched: `firmware/reference/39632e.md` and `40001303h.md`.

## Current Evidence

Strict XFAIL anchors in
`tests/sim/test_v34_v173_field_repros_20260613.py`:

- `test_field7_preset_phase_sweep_never_leaves_live_audio_on_wrong_coefficients`:
  IR B, 160M ticks, IR A, 160M + 12.174408M ticks, then 80-sample live-audio
  window.  With `--runxfail`, PB1 repeatedly observes preset A digest
  `054b166d80e6` instead of golden A `527246c85ab5`; first diff is TAS `0x4E`,
  expected `0x00`, observed `0x01`.
- `test_field8_ir_mute_converges_control_and_both_mains_under_filename_churn`:
  session-15 prefix with explicit `src_initial=flap` (`0x12=0`, `0x13=0`,
  `0x14=0`) and firmware HID filename read/write transactions.  With
  `--runxfail`, CONTROL/PB1 are muted while healthy PB2 remains unmuted and
  source-live.
- `test_field8_preset_down_converges_control_and_both_mains_under_filename_churn`:
  same prefix, then Preset-page DOWN.  With `--runxfail`, CONTROL/PB1 are B
  and muted while healthy PB2 remains A/unmuted.
- `test_field8_asleep_preset_b_host_traffic_converges_after_wake`: asleep IR
  preset B plus host preset traffic, then wake.  With `--runxfail`, CONTROL
  wakes showing B while both MAINs are active A with `job_state=0`,
  `job_target=1`.

Focused evidence:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q <four anchors>
4 xfailed in 47.53s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail <four anchors>
4 failed in 47.57s
```

Exploratory artifact inputs:

- FIELD-7:
  `artifacts/sim/current/exploratory/20260613_rerun_30m_subagent_judges/cards_all/20260613_211929_573cba82a35d9fef__s0001.md`.
- FIELD-8:
  `artifacts/sim/current/exploratory/20260613_rerun_30m_subagent_judges/cards_realistic/20260613_211929_573cba82a35d9fef__s0015.md`.
- FIELD-8 asleep/host:
  `artifacts/sim/current/exploratory/20260613_rerun_30m_subagent_judges/cards_realistic/20260613_211929_573cba82a35d9fef__s0004.md`.
- FIELD-8 supporting host/diagnostics evidence:
  `artifacts/sim/current/exploratory/20260613_rerun_30m_subagent_judges/cards_realistic/20260613_211929_573cba82a35d9fef__s0085.md`.
  This is not a separate acceptance branch yet; the strict asleep/host XFAIL
  anchors the shared host `cmd 0x20` convergence class.  If WU3 trace proves
  `s0085` has a diagnostics-specific mechanism, add a strict repro before
  runtime code is accepted.

Current source facts:

- `src/dlcp_fw/asm/dlcp_main_v34.asm` `preset_select_handler` records
  `preset_job_target_b2`, coalesces while `preset_job_state_b2` is nonzero, and
  starts PENDING only when target differs from `active_flags.bit2`.
- `preset_job_pending` waits for filename dirty work, persists the outgoing
  filename, force-mutes if needed, and arms hold.
- `preset_job_holding` toggles `active_flags.bit2`, loads filename, then
  initializes the job-owned physical cursor before APPLY.
- `preset_job_apply_i2c_entry` uses the FIELD-5 row writer and NACK handling.
  `preset_job_commit` may restore volume if the job force-muted and the user
  did not request mute.
- `cmd_dispatch_gated`, route/SRC refresh, lifecycle reassert, and volume
  restore are interacting writers.
- `src/dlcp_fw/asm/dlcp_control_v173.asm` preset-page UP/DOWN calls
  `v171_send_preset_frame_and_persist`; full-sync step 6 emits preset with
  `v171_send_preset_frame_txonly`; V1.73 adds a raw muted-only reassert.
- First-wave independent FIELD-8 probe saw CONTROL TX `B0 03 02`, PB1 RX
  `B0 03 02`, PB1 TX `B0 03 02`, PB2 RX empty; preset showed the same shape
  for `B0 20 01`.  WU3 must confirm/falsify in-tree before code changes.

## Gap Analysis

Exists:

- Golden coefficient oracle and source-live/unmuted/fault-free predicates.
- Four deterministic strict XFAIL anchors.
- MAIN async APPLY, FIELD-6 lifecycle reassert, CONTROL full-sync step 6, and
  muted reassert.

Missing:

- FIELD-7 final-writer proof for every TAS `0x37..0x90` divergence across the
  whole live-audio transition.
- Exhaustive writer inventory for `preset_job_apply_i2c_entry`, lifecycle
  reassert, `preset_replay_selected_table_blocking`, `i2c_apply_channel_route_sync_burst`, every
  `preset_table_apply_entry_legacy_blocking` caller including normal `event_flags.bit6`, route/SRC
  refresh, and volume restore ordering around TAS `0x30..0x33`.
- FIELD-8 hop proof from CONTROL enqueue through PB1 RX/TX, PB2 RX, parser
  dispatch, and handler hit.
- Bounded convergence tests for `cmd 0x03 data=0x02/0x03` and
  `cmd 0x20 data=0x00/0x01` under SRC-flap, filename churn, and TAS-NACK/I2C
  foreground pressure.
- V1.73/V3.4 dual-MAIN preset/DSP sync matrix adapted from
  `tests/sim/test_v171_v32_dual_main_preset_sync.py`.
- Release freshness guard tying behavior tests to rebuilt canonical V3.4/V1.73
  hexes.

Risky:

- CONTROL retries can mask lost frames without proving PB2 acceptance.
- A separate final coefficient writer would duplicate FIELD-5/6 ownership.
- Broad CONTROL sender refactoring can break raw health/filename/diag and
  mute-reassert paths.
- MAIN size is very tight; if margin is 14 bytes and floor is 10, only 4
  discretionary bytes are available before reclaim.

## Proposed Implementation

### WU0 - Repro and Ledger Pinning

Completed in this planning pass:

- Added four strict XFAIL repro tests.
- Updated `docs/V34_FIELD_BUGS_20260610.md` with FIELD-7/FIELD-8 evidence,
  full artifact paths, commands, SRC-hole semantics, visible fault/lost
  definition, and mute audio-safety contract.
- Tightened FIELD-8 helpers so hidden gate drops are not accepted and mute-on
  requires actual TAS/gate/source safety.

### WU1 - FIELD-7 Trace And Writer Inventory

Use existing simulator observability first; temporary local instrumentation is
allowed only if write logs cannot answer the question and must not be committed.

Required evidence:

- For every divergent TAS `0x37..0x90` byte, record final writer label/PC,
  subaddress, data, physical source, target preset, `active_flags`,
  `event_flags`, `dsp_fault_flags`, `preset_job_state/index/target/flags`, and
  TAS `0x30..0x33` when audio becomes nonzero/unmuted.
- Sample from APPLY/COMMIT through later volume-dirty passes.  Source-live +
  unmuted + fault-free + job-idle + nonzero TAS30..33 implies selected golden
  image.
- Produce a writer table for all coefficient paths: owner, callers, range,
  after-APPLY possibility, final-before-volume possibility, and guard.
- Add a structural test forbidding an unvalidated legacy writer from being
  final before nonzero TAS `0x30..0x33`.
- Audit affected paths for TOS/`chain_copy`, GIE, BSR, STATUS.C/carry, and
  RAM-bank aliases.  If touched code uses `chain_copy` post-GIE, remove that
  use, preserve TOS/GIE locally, or prove interrupts cannot happen.

### WU2 - FIELD-7 Compact MAIN Fix

Choose the smallest fix supported by WU1:

- If async APPLY is the bad final writer, repair that owner: rearm from row 0
  on source/target inconsistency, keep audio muted until selected-source image
  validates, and make COMMIT unreachable after failed/mismatched rows.
- If route/SRC/lifecycle mutates preset-owned bytes after valid APPLY, route it
  through FIELD-6 lifecycle ownership or force validated selected-preset
  reassert before nonzero volume restore.
- If idle stale target is involved, normalize only boot/unowned stale RAM.  If
  `cmd 0x20` reached the handler, `job_state=0` with `target != active` must
  arm PENDING/APPLY or surface operator-visible fault/lost state.
- Reuse async APPLY or FIELD-6 lifecycle owner.  Do not add a third coefficient
  state machine.
- Add fault-mode tests for TAS address NACK, TAS data NACK, header mismatch if
  applicable, and START/STOP timeout.  Audio must stay muted or visibly faulted
  until validated reassert succeeds.
- Add structural checks for GIE preservation around any moved/added interrupt
  masks, and RAM-bank tests for every new/moved alias in
  `tests/sim/test_ram_bank_safety.py`.

### WU3 - FIELD-8 Hop Proof And Value Convergence

Scope to the observed value-bearing commands unless trace expands it:

- `cmd 0x03 data=0x02`: mute on.
- `cmd 0x03 data=0x03`: mute off.
- `cmd 0x20 data=0x00/0x01`: preset A/B.

Required hop matrix:

1. CONTROL enqueue succeeds or aborts before changing UI.
2. PB1 RX accepts the frame.
3. PB1 TX forwards the same frame without clobber.
4. PB2 EUSART/RX ring accepts the frame; record OERR/CREN and rd/wr.
5. PB2 dispatches to `cmd03_mute_on_handler`, `cmd03_mute_off_handler`, or
   `preset_select_handler`.
6. PB2 value converges, or an operator-visible fault/lost state is surfaced.

If PB1 TX exists but PB2 RX is empty, investigate PB1 TX ownership,
current-loop line state, PB2 OERR/CREN, RX ring overflow/drop, and parser
starvation before changing CONTROL UI code.

Fix policy:

- Primary command path must be correct.  CONTROL full-sync step 6 and
  `v173_mute_reassert` are mandatory convergence backstops, not substitutes.
- CONTROL remains out of scope unless WU3 proves producer/sender ownership is
  faulty.  If CONTROL is touched, preserve raw-vs-routed classes: routed
  helpers may reset full-sync; raw health/filename/diag/mute-reassert must not.
  Preserve `tx_ring_reserve_3`, `STATUS.C`, full-sync side effects, and TX
  atomicity.
- If MAIN receives but rejects frames due to SRC loss or filename churn, narrow
  MAIN gating so awake value-bearing safety/control commands are accepted:
  mute on/off immediately; preset records/arms the normal job when real
  preconditions allow.  Do not relax volume/input policy without a regression
  proving it is unchanged.
- Add a pressure regression driving `B0 03 02`, `B0 03 03`, and `B0 20 xx`
  under TAS-NACK or equivalent I2C-retry foreground pressure, or prove FIELD-8
  cannot share the prior parser-loss path.
- Define bounded convergence in ticks.  The current XFAIL bound is 20 windows
  of `1_000_000` ticks after the distilled action delay; adjust only with
  measured reason.

### WU4 - Regression And Oracle Expansion

Convert the four strict XFAILs only after they pass under `--runxfail`.

Required additions before runtime fix acceptance:

- FIELD-7 structural/runtime test for the exact writer identified by WU1.
- FIELD-7 failure tests named in WU2.
- FIELD-8 delivery/gating tests for `B0 03 02`, `B0 03 03`, and `B0 20 xx`
  under SRC-flap + filename churn and under foreground I2C pressure.
- FIELD-8 host/asleep preset regression for `s0004`.  Treat `s0085` as
  supporting evidence unless WU3 proves a distinct diagnostics-specific
  mechanism; if so, add a dedicated strict repro before accepting runtime code.
- Settled invariant: no awake connected MAIN may have `preset_job_state=0`
  with `preset_job_target != active preset`, unless operator-visible
  fault/lost is shown.
- V1.73/V3.4 dual-MAIN preset/DSP sync matrix, reusing the
  `test_v171_v32_dual_main_preset_sync.py` pattern where possible.
- Release freshness guard or temporary build fixture so behavior tests do not
  exercise stale canonical hex after ASM edits.

### WU5 - Build, Size, And Gate Discipline

Before editing MAIN source:

- Record current V3.4 app-end/free bytes from the listing.
- If estimated delta exceeds bytes available above the 10-byte floor, identify
  reclaim candidates before adding code.

Required after any MAIN source/HEX change:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_field7_preset_phase_sweep_never_leaves_live_audio_on_wrong_coefficients \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_field8_ir_mute_converges_control_and_both_mains_under_filename_churn \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_field8_preset_down_converges_control_and_both_mains_under_filename_churn \
  tests/sim/test_v34_v173_field_repros_20260613.py::test_field8_asleep_preset_b_host_traffic_converges_after_wake
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v171_v32_dual_main_preset_sync.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_firmware_version_label.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Additional required if CONTROL changes:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v172_v33_diag_identity.py \
  tests/sim/test_v171_layer2_full_sync_step.py \
  tests/sim/test_v171_preset_inline.py \
  tests/sim/test_v171_ir_endpoints.py \
  tests/sim/test_dlcp_control_flash_safety.py \
  tests/sim/test_ram_bank_safety.py
```

If CONTROL is touched, add or extend V1.73-specific structural sender checks
for `serial_tx_routed_frame`, `v171_send_preset_frame_txonly`, raw
diagnostics/health senders, and `v173_mute_reassert`, including `STATUS.C`,
full-sync side effects, and 3-byte TX atomicity.

Freshness evidence is mandatory: record the pre-fix MAIN/CONTROL revisions,
post-build revision output, canonical hex paths, listing app-end/free bytes,
and release identity tests.  README identity updates are deferred until release
promotion; until then, README must not be used as the source of current
worktree revision truth.

### WU6 - Documentation And Final Evidence

Update:

- `docs/V34_FIELD_BUGS_20260610.md` with root cause, code shape, tests, size,
  no-deploy/hardware status, and remaining risk.
- This IMPL with actual files changed, code-size delta, exact command results,
  no-deploy reason, review follow-up, and final acceptance status.
- `docs/SIM_EXPLORATORY_BUG_TAXONOMY.md` only if classification changes.
- `README.md` only if the result is promoted/recommended; otherwise state it is
  intentionally deferred.

## Likely Files

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_v173.asm` only if WU3 proves CONTROL TX
  ownership faulty.
- `src/dlcp_fw/asm/dlcp_control_ram.inc` only if CONTROL RAM changes.
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `firmware/patched/releases/DLCP_Control_V1.73.hex` only if CONTROL changes.
- `tests/sim/test_v34_v173_field_repros_20260613.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_v34_mute_refresh_bug.py`
- `tests/sim/test_ram_bank_safety.py`
- `tests/sim/test_v34_v173_compatibility.py`
- A new/adapted V1.73/V3.4 dual-MAIN preset sync test if not folded into the
  field repro file.
- `docs/V34_FIELD_BUGS_20260610.md`
- this IMPL.

## Deployment And Smoke Plan

Default for this implementation goal: no deploy/flash.  Simulator green means
"fixed in sim/release artifacts", not field-safe or recommended.

No promotion/recommended status is allowed until a separately authorized
low-volume hardware smoke covers mute, A/B switching, Auto Detect locked RXCKR
holes, confirmed unlock loss/reacquire, and no audible volume excursion.

If hardware is later authorized:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py detect
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --left
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$RIGHT_HID" --right
scripts/flash_control_safe.sh --path "$LEFT_HID"   # only if CONTROL changed
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --info-only
```

Abort hardware validation on missing/unbaked capture warnings.  Record exact
built revs, role-derived HID paths, PB1/PB2 LCD identity, diag JSON, and
artifacted low-volume A/B/mute timing/acoustic notes.

## Implementation Result

Implemented files:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `tests/sim/test_v34_v173_field_repros_20260613.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_v34_preset_src_hole_field_bug.py`
- `tests/sim/test_v34_diag_src_counters.py`
- `docs/V34_FIELD_BUGS_20260610.md`
- `docs/IMPL_V34_FIELD7_FIELD8_PRESET_DSP_SAFETY.md`

Root causes found:

- FIELD-7: async preset APPLY could commit and restore volume after the
  sampled phase even though the selected coefficient image was not yet owned
  by a final validated writer.  The fix reuses the FIELD-6 lifecycle reassert
  owner as the final selected-image owner: COMMIT sets `active_flags.bit7`
  while TAS30 is still zero, lifecycle drains route/input side effects,
  replays the selected physical table through the validated row writer, and
  only then schedules volume restore if user mute state allows it.
- FIELD-8 filename/SRC churn: PB1 forwarded value-bearing frames while PB2's
  RX interrupt path could remain disabled after gated foreground work.  The
  common gated tail now re-enables CREN and RCIE.
- FIELD-8 asleep/wake: preset commands accepted while asleep only parked
  `preset_job_target`; standby cancellation cleared `preset_job_state`.  Wake
  now re-arms PENDING after hardware is back when target differs from active
  preset.
- Supporting BF/08 issue: preset APPLY timeout recovery sent BF/08 bit2 but
  later cleared `dsp_fault_flags.bit2` silently, leaving CONTROL with a stale
  `!`.  The next retry boundary now emits BF/08=0 when clearing a previously
  advertised transport bit.

Size and safety:

- Canonical MAIN rebuilt by
  `PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py`.
- Final release identity: `DLCP_Firmware_V3.4.hex`, EEPROM/runtime rev
  `0xA4`.
- Listing boundary: last app instruction is the two-word `goto` at `0x4BF2`;
  `preset_table_b` starts at `0x4C00`, leaving exactly 10 bytes
  (`0x4BF6..0x4BFF`) free.
- CONTROL was not changed; `build_v173_release.py` was not run.
- `assert_targets_safe(["main-v34"])` ran inside the V3.4 builder.
- Touched MAIN paths preserve W/STATUS for the chain-TX mark helper, return
  BSR=0 where existing callers require banked access, and avoid new GIE/TOS
  interactions.  The pre-existing `chain_copy` interrupt-safety XFAIL remains
  intentionally unresolved and documented.

Verification:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail <four FIELD-7/FIELD-8 anchors>
4 passed in 46.58s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q <four FIELD-7/FIELD-8 anchors>
4 passed in 46.45s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_preset_src_hole_field_bug.py
8 passed in 182.35s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_diag_src_counters.py
10 passed in 47.93s

Focused IMPL gate:
325 passed, 3 xfailed in 1213.49s

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
1627 passed, 2 skipped, 3 xfailed, 7 warnings in 674.13s
```

Remaining non-deploy notes:

- No live hardware flash or acoustic validation was performed in this goal.
- The pair is not recommended/release-promoted by this implementation.  Run
  low-volume hardware smoke before promotion: mute, A/B switching, locked
  RXCKR holes, hard unlock/reacquire, standby/wake, and no audible
  volume/filter excursion.
- Remaining XFAILs are outside FIELD-7/FIELD-8: two Diagnostics-page
  front-panel STBY tests and the documented `chain_copy` interrupt-safety
  proof.

## Acceptance Criteria

- All four FIELD-7/FIELD-8 XFAIL anchors pass under `--runxfail`, then run
  green as ordinary tests.
- FIELD-7 transition-wide oracle never observes live audio on a wrong selected
  coefficient image.
- FIELD-8 session-15 and asleep/host paths converge CONTROL/PB1/PB2 preset
  and mute values, or show operator-visible fault/lost.  If WU3 proves `s0085`
  is mechanistically distinct, its new strict repro also passes.
- Mute-on is actually audio-safe: gate closed, source not live, or TAS
  `0x30..0x33 == 0`; locked RXCKR holes are not treated as hard loss.
- No touched MAIN/CONTROL path violates GIE/TOS/BSR/STATUS.C/carry/RAM-bank
  contracts.
- MAIN V3.4 build margin remains at least 10 bytes.
- Required focused, release, compatibility, SRC, dual-MAIN, and full
  `tests/sim -n 16` gates pass.
- Docs record root cause, code shape, tests, size, and no-deploy/hardware
  status.

## Reviewer Findings And Iteration History

Review gate: 10 independent reviewer angles requested by the user.  Zero
unresolved High/Medium findings after this revision.

First wave, 6 agents:

- Simplicity/scope: High FIELD-8 scope too broad; Medium duplicate final writer
  risk; Medium test matrix too narrow.  Addressed in WU2/WU3/WU4.
- FIELD-7 DSP correctness: High incomplete writer inventory; High one-sample
  oracle; Medium stale target; Medium missing fault tests.  Addressed in WU1,
  WU2, WU4.
- FIELD-8 chain correctness: High PB1-TX/PB2-RX branch missing; High PB2
  dispatch proof missing; High host-preset missing; Medium bounded convergence
  and mute-off coverage.  Addressed in WU0, WU3, WU4.
- CONTROL correctness: High full-sync/mute-reassert under-specified; High
  raw-vs-routed sender risk; Medium V1.73 gates needed.  Addressed in WU3,
  WU5.
- Simulator/repro quality: High HID fallback, SRC fixture, FIELD-7 window, and
  visible fault semantics.  Addressed in WU0 tests.
- PIC/size safety: High `chain_copy`/TOS and GIE proof; Medium size, bank,
  carry/BSR.  Addressed in WU1/WU2/WU5.

Second wave, 4 agents:

- Documentation/traceability: High review gate incomplete and host-preset
  unanchored; Medium hardware evidence, abbreviated artifact paths, stale
  historical verification, missing release gates.  Addressed in WU0, WU5,
  deployment plan, source spec labels, and full artifact paths.
- SRC/audio safety: High mute-on could pass while audio live; High SRC
  hysteresis gate omitted; Medium parser-loss pressure and hardware boundary.
  Addressed in WU0 tests, Required Docs, WU3, WU5, deployment plan.
- Release/build/ops: High full sim conditional; High freshness not exact; High
  hardware role safety; Medium release-adjacent and CONTROL gates.  Addressed
  in WU5 and deployment plan.
- Release/build/ops recheck: Medium CONTROL flash-safety tests and exact
  CONTROL flash command.  Addressed in WU5 and deployment plan.
- Regression compatibility: High mixed-version compatibility not blocking;
  High hidden gate drop could satisfy visible fault; Medium dual-MAIN sync and
  CONTROL sender safety.  Addressed in WU0, WU4, WU5.

Remaining Low issues:

- README release identity is intentionally deferred until promotion; final
  implementation evidence must state that README is not current-revision
  authority unless the user asks to promote/release.
