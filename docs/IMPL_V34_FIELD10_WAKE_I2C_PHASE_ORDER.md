# IMPL: FIELD-10 wake I2C phase order

Date: 2026-06-14
Status: Implemented in simulator, hardware promotion pending
Source spec: `docs/V34_FIELD_BUGS_20260610.md` (`FIELD-10`)
Scope: MAIN V3.4 wake/reconnect lifecycle I2C ordering. CONTROL changes are out of scope except for chain-level regression coverage.

## Source Requirements

Goals:

- Preserve the `d69d689` FIELD-6/FIELD-7 safety invariant: route/channel sync may touch TAS coefficient space, so it must run while muted and before the final validated selected-preset writer.
- Eliminate the startup `I6` class where input-route physical I2C side effects run before the post-wake device-init barrier.
- Split lifecycle side effects by phase:
  1. keep audio muted;
  2. drain `event_flags.bit4` route/channel sync before the final selected-preset reassert;
  3. run the final selected-preset reassert through the existing FIELD-5 validated row writer;
  4. only after `main_i2c_service_32f8` or equivalent device init, run `event_flags.bit1` input-route physical side effects;
  5. restore nonzero volume only after bit1 succeeds or after a visible fault keeps the MAIN muted/safe.
- Keep the fix compact. MAIN program space is tight; current project policy accepts a minimum 10-byte free-space floor for this release train.

Non-goals:

- Do not clear, discount, or special-case `diag_i`; it is the observable that caught this bug.
- Do not use blind sleeps or retry loops as the correctness mechanism.
- Do not duplicate the route ladder, preset APPLY walker, or TAS coefficient writer.
- Do not move the full normal dispatcher earlier again. The fix must name which side effects are legal before and after the wake device-init barrier.
- Do not redesign SRC4382 Auto Detect, CONTROL UI, or the flasher diagnostics path in this work unit.
- Do not flash live hardware as part of implementation without a separate operator request.
- User decision for exploratory review: after the 30-minute hunt, use subagents as LLM judges; do not use `codex -p`. If `scripts/exploratory_oracle_run.py` is used, it must use a non-`codex -p` model command approved by the operator. Otherwise the subagent workflow must mirror the same judge, artifact-verify, correctness-verify, synthesize, schema-like buckets, and `run_ok`/error gate.

## Docs Read

- `AGENTS.md`: canonical layout, release artifact paths, test categories, and operator commands.
- `README.md`: current V3.4/V1.73 release train, `.venv_ep0` setup, full simulator gate with `-n 16`, and hardware boundary.
- `docs/HARDWARE_TEST.md`: live hardware tests are opt-in and require explicit operator gates.
- `docs/TEST_SIMULATOR.md`: historical simulator context; rust silicon-ring backend is now canonical.
- `docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md`: exploratory runner contract, duration/campaign/output options.
- `docs/exploratory_oracle/ORACLE_PROTOCOL.md`: 30-minute hunt plus card selection and external judging workflow.
- `docs/REFACTORING_V34_V173_SPEC.md` and `docs/IMPL_REFACTORING_V34_V173.md`: V3.4/V1.73 release, size, role-safe flash, and hardware-promotion policy.
- `docs/V32_RELEASE.md` and `docs/V171_RELEASE.md`: historical release operator flow and no-ad-hoc-artifact precedent.
- `docs/V34_FIELD_BUGS_20260610.md`: FIELD-6/FIELD-7/FIELD-10 constraints and rejection list.
- `docs/IMPL_V34_FIELD6_WAKE_ROUTE_SYNC_DSP_OWNERSHIP.md` and `docs/IMPL_V34_FIELD7_FIELD8_PRESET_DSP_SAFETY.md`: existing lifecycle/preset safety contracts that must stay intact.

## Current Implementation Evidence

- `src/dlcp_fw/asm/dlcp_main_v34.asm` `adc_boot_gate`: after `mssp_hard_reset` and `clrf_i2c_coeff_0123_and_write`, the current wake path sets `event_flags.bit1`, `event_flags.bit4`, and `active_flags.bit7`, then calls `cmd_dispatch_gated` before `main_i2c_service_32f8`.
- `cmd_dispatch_gated`: calls `cmd_dispatch_input_route_if_dirty` before checking `active_flags.bit7`, so lifecycle reassert does not currently isolate input-route side effects from the active7 phase.
- `flow_cmd_dispatch_gated_1a76`: active7 lifecycle cancels preset APPLY, mutes, calls `cmd_dispatch_input_route_if_dirty`, calls `cmd_dispatch_route_sync_if_dirty`, clears bit6, and runs `main_core_service_4574`.
- `cmd_dispatch_input_route_if_dirty`: for `event_flags.bit1`, reaches the physical route ladder and can call `i2c_secondary_dev_write`, `main_i2c_service_48e2`, `main_core_service_4516`, and `i2c_tas3108_reg1f_write`.
- `i2c_tas3108_reg1f_write`: emits six TAS bytes (`0x68, 0x1F, 0, 0, 0, data`), matching the observed `I6` if a not-ready device NACKs that transaction.
- `i2c_secondary_dev_write`: emits three bytes to the secondary/SRC side; the route ladder can emit two such writes plus a TAS `0x1F` refresh.
- `i2c_byte_tx`: latches ACKSTAT into `dsp_fault_flags.bit2` and increments `diag_i`. The fix must respect that latch instead of hiding it.
- `main_i2c_service_32f8`: current post-wake secondary/SRC init table; FIELD-10 names this as the device-readiness barrier.
- `main_i2c_service_2100`: route/channel sync can touch the secondary device and TAS coefficient space, so it belongs before final selected-preset reassert while muted.
- `preset_job_commit`: FIELD-7 sets `active_flags.bit7` and then can clear mute latches before active7 runs. The protected invariant is not "mute latch remains set"; it is "TAS volume remains zero and no nonzero `volume_dsp_write` occurs until the selected image is golden and the lifecycle fault gate is clean."
- `tests/sim/test_v34_v173_refactoring_contracts.py`: currently pins the old active7 and `adc_boot_gate` ordering; these tests must be updated to encode the FIELD-10 split.
- `tests/sim/test_v34_v173_field_repros_20260613.py` and `tests/sim/test_v34_field_bugs_20260610.py`: already contain FIELD-6/FIELD-7 style lifecycle repro helpers and TAS NACK injections.
- `src/dlcp_fw/sim/dlcp_sim_native.py`: exposes SRC4382 and TAS3108 NACK injection plus I2C stats. Existing count-based hooks are not enough by themselves to prove phase order; FIELD-10 tests need PC barriers and transaction/log assertions.

## Gap Analysis

What exists:

- A single active7 lifecycle owner for mute, route/channel sync, final selected-preset reassert, and preset-filename reload.
- A separate helper for bit4 route/channel sync.
- ACKSTAT and timeout fault observability through `diag_i`, `dsp_fault_flags`, and BF/08 status.
- Simulator fault injection for TAS3108 and SRC4382/secondary NACKs.

What is missing:

- A contract that active7 lifecycle never runs bit1 input-route physical I2C before post-wake device init.
- A clean late route-input phase that is isolated from volume restore, retryable on failure, and checks a well-owned ACKSTAT/fault state.
- A barrier status phase around `main_i2c_service_32f8`; the barrier itself performs secondary I2C writes and must not be erased by a later ACKSTAT clear.
- Regression tests that reproduce startup `I6` behavior with an injected early-not-ready window.
- Structural tests proving bit4 remains before final selected-preset reassert while bit1 is after the device-init barrier.
- A release-size gate tied to the relaxed 10-byte free-space floor.

Risk to control:

- If bit1 is merely delayed but volume can still restore after a bit1 NACK, FIELD-10 becomes a hidden "healthy but unsafe" state. The implementation must either withhold volume or surface a fault/muted-safe state.
- If bit4 is delayed with bit1, FIELD-6/FIELD-7 can regress because route/channel sync can again become the last writer into TAS coefficient space.
- If the fix duplicates route logic to save a branch, it risks diverging from the HFD/IR/input-select paths already covered by old tests.
- If ACKSTAT ownership is ambiguous, the implementation can either hide a real barrier fault or falsely blame late bit1 for an older fault.

## Proposed Implementation

### WU0 - Baselines and tests first

Before editing firmware:

- Record current MAIN rev, source SHA, release HEX SHA/CRC, listing path, `used_bytes_pre_preset_b`, `last_used_pre_preset_b`, `free_bytes_before_0x4C00`, `free_object_words`, listing byte margin before `0x4C00`, and a concise program-byte diff summary for `0x1000..0x4BFF`.
- Add strict structural/temp-assembled tests first. Tests that load canonical `firmware/patched/releases/DLCP_Firmware_V3.4.hex` are acceptance tests and must run only after `scripts/build_v34_release.py`, otherwise stale release HEX can be approved.
- Use `PY="${DLCP_PYTHON:-.venv_ep0/bin/python}"` in commands so linked worktrees can use the shared tool venv.

Required tests:

1. Structural FIELD-10 ordering test in `tests/sim/test_v34_v173_refactoring_contracts.py`:
   - `cmd_dispatch_gated` must bypass bit1 input-route work while `active_flags.bit7` is set.
   - `flow_cmd_dispatch_gated_1a76` must drain `cmd_dispatch_route_sync_if_dirty` before `main_core_service_4574`.
   - `flow_cmd_dispatch_gated_1a76` must not call `cmd_dispatch_input_route_if_dirty`.
   - `adc_boot_gate` must not set or drain `event_flags.bit1` before `main_i2c_service_32f8`; pre-existing bit1 must survive active7 and remain pending for the late phase.
   - active7 must not arm `event_flags.bit3`/volume restore while wake-late bit1 is pending.
   - no `volume_dsp_write` can occur between late bit1 and its ACK/fault classification gate.
2. Active7 source matrix:
   - inventory every `active_flags.bit7` producer: HID/config flow, wake/cold boot, reconnect, and preset COMMIT.
   - either make bit1 deferral wake-specific, or prove the global active7 ordering is safe for every producer.
   - add a preset-COMMIT-with-pending-bit1 regression so FIELD-7 remains protected.
3. Behavioral clean-boot/wake chain test:
   - boot V1.73 + two V3.4 MAINs, wait through settle, and assert both MAINs report `diag_i == 0` through cmd `0x44` (`firmware_hid_report` + `parse_cmd44_diag_response`), not only direct RAM reads.
   - exercise cold boot, standby/wake, reconnect/reset paths, and both PB1/PB2.
4. Phase-locked early-not-ready tests:
   - construct `Chain` directly and arm/reset I2C stats before first stepping for cold-start tests; avoid helpers that already run to connected.
   - use `step_until_pc_hit` or an equivalent PC barrier for `cmd_dispatch_gated`, `flow_cmd_dispatch_gated_1a76`, `main_i2c_service_32f8`, late bit1, and volume restore.
   - reset TAS/SRC stats and write logs around each phase.
   - assert no pre-barrier TAS `0x1F` or secondary route-ladder bit1 transaction is consumed.
   - table-drive both MAIN units and both device families: TAS address/data NACK and secondary/SRC address/data NACK.
   - if current stats cannot attribute the transaction, add the smallest simulator transaction timeline or not-ready-until-PC hook and test that hook.
5. Barrier and late-bit1 failure/retry tests:
   - inject NACK during `main_i2c_service_32f8`; assert BF/08-visible fault, effective mute, bit1/volume not run, and retry/success path before volume.
   - inject NACK during late bit1; assert `event_flags.bit1` remains or is re-armed, TAS volume remains zero, BF/08/CONTROL `!` is visible, and retry succeeds only after the injected window clears.
   - include pre-existing `dsp_fault_flags.bit2` and bit6 cases to prove prior faults are preserved and volume restore is gated on `(dsp_fault_flags & 0x44) == 0`.
   - seed/pre-arm `event_flags.bit3` before wake and from active7 success; prove no nonzero `volume_dsp_write` occurs until barrier success plus late-bit1 success.
   - test user-muted and user-unmuted recovery. Fault-forced mute must not clear real user mute, and retry success must not leave user-unmuted units stuck muted.
   - test asleep preset target re-arm before volume scheduling; if asleep target differs from active preset, TAS volume stays zero until the re-armed preset job applies the target and the selected image is golden.
   - classify the wake-tail secondary `0x1B` write: either move it into the same checked pre-volume phase or test/document why it cannot produce a live hidden `I6`.
6. FIELD-5/FIELD-6/FIELD-7 regression guard:
   - existing wrong-DSP-image and final-writer tests must remain green.
   - add structural proof that the final reassert path is the FIELD-5 validated physical-source/header/NACK-aware row writer or an equivalent checked path, not a plain unvalidated blocking rewalk.
   - assert the selected preset golden image is present before any nonzero TAS `0x30..0x33` restore after wake.

Use existing simulator NACK hooks first. If aggregate stats cannot distinguish bit1 route-ladder traffic from legal barrier/bit4 traffic, add the smallest native transaction-timeline or not-ready-until-PC hook needed to prove attribution. If native files are touched, run:

```bash
cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
```

plus the cargo/Python tests that cover the touched hook.

### WU1 - Firmware phase split

Required compact shape:

1. Keep `cmd_dispatch_input_route_if_dirty` as the sole physical owner for bit1 route/input side effects. Do not duplicate the route ladder.
2. In `cmd_dispatch_gated`, check `active_flags.bit7` before calling `cmd_dispatch_input_route_if_dirty`. This makes active7 an explicit lifecycle bypass instead of letting pending bit1 run as a preamble. Update stale comments that say FIELD-6 lifecycle uses bit1 before preset validation.
3. In `flow_cmd_dispatch_gated_1a76`, remove the `cmd_dispatch_input_route_if_dirty` call. Keep:
   - cancel preset APPLY;
   - force mute through `clrf_i2c_coeff_0123_and_write`;
   - drain `cmd_dispatch_route_sync_if_dirty`;
   - clear `event_flags.bit6` only; do not clear `dsp_fault_flags.bit6` except through the existing BF/08 fault-clear owner;
   - run the FIELD-5 validated selected-image reassert path (`main_core_service_4574` only if that path remains the validated row writer by current code evidence);
   - on failure, keep mute and set the existing BF/08-visible fault bits.
4. In `adc_boot_gate`, before `main_i2c_service_32f8`, set only the lifecycle bits needed for route/channel sync and selected-preset reassert (`event_flags.bit4` and `active_flags.bit7`). Do not set or drain bit1 there.
5. Add an explicit barrier status phase around `main_i2c_service_32f8`:
   - sample/preserve prior visible fault state;
   - clear the ACKSTAT latch only for an isolated barrier attempt;
   - introduce or reuse an audited compact wake lifecycle state with explicit `barrier_pending`, `late_bit1_pending`, and `fault_mute_owned` semantics. One byte or spare audited bits are acceptable; the selected storage must be named in implementation evidence.
   - if the barrier sets bit2 or any visible fault bit remains (`dsp_fault_flags & 0x44`), assert effective mute (`active_flags.bit4`), set `barrier_pending`, advertise/keep BF/08, clear/suppress any stale `event_flags.bit3`, do not run late bit1, and do not schedule volume.
   - retry `main_i2c_service_32f8` only from this named pending state. Do not depend on accidental future wake/reconnect traffic. On success, clear `barrier_pending`, proceed to `late_bit1_pending`, and keep volume suppressed.
6. Add an isolated late-bit1 wrapper/entry after the barrier and UART-safe wake housekeeping:
   - run the existing `cmd_dispatch_input_route_if_dirty` owner;
   - return before any volume path;
   - classify only newly-set bit2 as the late-bit1 result while preserving pre-existing visible faults;
   - on failure, assert effective mute, set/keep `fault_mute_owned` only if user mute was not already active, advertise/keep BF/08, clear/suppress any stale `event_flags.bit3`, and preserve or re-arm bit1 plus `late_bit1_pending` for retry;
   - on success and only when `(dsp_fault_flags & 0x44) == 0`, clear `late_bit1_pending`; clear fault-owned mute only when user mute intent is false; schedule the existing bit3 volume/refresh path.
   - wake asleep-preset re-arm must happen before any bit3 volume scheduling. If the target differs from the active preset, defer volume until the re-armed preset job and final lifecycle reassert have made the target image golden.
7. Treat the wake-tail secondary `0x1B` write as part of the checked pre-volume wake phase or move it before the final volume scheduling. It must not be a post-volume source of hidden `diag_i`.

Implementation detail may differ if a smaller equivalent proves the same contract, but it must keep a single owner for route input logic and a single owner for coefficient reassert.

### WU2 - Size and release artifact

- Rebuild only the canonical V3.4 release with `PYTHONPATH=src "$PY" scripts/build_v34_release.py` after replacing `PY` as shown in the test plan.
- Measure program-space headroom after build and record it here. The executable floor is already pinned by
  `tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom`
  at 10 bytes before `0x4C00`; run that test explicitly after every size-affecting edit.
- Record final MAIN rev, source SHA, release HEX SHA/CRC, `used_bytes_pre_preset_b`, `last_used_pre_preset_b`, `free_bytes_before_0x4C00`, `free_object_words`, listing margin, program-byte diff summary for `0x1000..0x4BFF`, and delta from the pre-edit baseline.
- If the fix falls below the 10-byte floor, stop. Do not weaken FIELD-10 semantics or improvise size cuts inside this goal; open a separate size-reclaim/user-decision step.
- Do not mint ad-hoc V3.4 filenames.
- Final committed release payload is only `firmware/patched/releases/DLCP_Firmware_V3.4.hex`. `src/dlcp_fw/asm/dlcp_main_v34.lst` is generated local evidence; do not add release-side `.lst`/`.cod` byproducts or local suffixed HEX variants.

### WU3 - Docs and observability

- Update `docs/V34_FIELD_BUGS_20260610.md` FIELD-10 from OPEN to sim-fixed only after deterministic tests, full tests, and exploration/subagent judging pass. Do not mark release-promoted or recommended until operator-approved live smoke evidence exists.
- Update this IMPL with actual changed files, exact size delta, exact test commands/results, and exploratory/subagent results.
- Keep `diag_i` behavior visible in docs and diagnostics. A clean boot should be `I0`; an injected I2C failure should remain observable.

## Likely Files

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_v34_field_bugs_20260610.py`
- `tests/sim/test_v34_v173_field_repros_20260613.py`
- `src/dlcp_fw/sim/dlcp_sim_native.py` and native rust simulator files only if transaction attribution cannot be proven with existing hooks/stats
- `docs/V34_FIELD_BUGS_20260610.md`
- this IMPL document

## Test Plan

Set the interpreter once:

```bash
PY="${DLCP_PYTHON:-.venv_ep0/bin/python}"
```

Pre-edit tests: structural/temp-assembled tests only. Do not run canonical-HEX behavioral tests as acceptance before rebuilding.

Build before release-HEX tests:

```bash
PYTHONPATH=src "$PY" scripts/build_v34_release.py
```

Focused post-build tests:

```bash
PYTHONPATH=src "$PY" -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_firmware_version_label.py::test_v34_usb_and_eeprom_version_match_release_identity \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py
```

Full simulator gate, required before accepting:

```bash
PYTHONPATH=src "$PY" -m pytest -q -n 16 tests/sim
```

Exploratory bug-hunt gate, required by user before accepting this goal. This is broad bug hunting; deterministic FIELD-10 tests remain the proof for phase ordering.

```bash
PYTHONPATH=src "$PY" scripts/sim_chain_exploratory.py \
  --duration 30m \
  --campaign all \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/sim/current/exploratory/field10_$(date +%Y%m%d_%H%M%S)
```

Record the parent `--out-dir`, generated child run directory, manifest, seed, and replay command. Before LLM judging, run a mechanical scan over all `observations.jsonl` files:

- treat any no-explicit-fault session with nonzero PB1/PB2 `diag.I` as blocking unless concrete event evidence reclassifies it as an explicit injected fault or known benign simulator artifact. Render mandatory cards for diagnosis, but do not let card rendering replace the gate.
- require at least: 3 POR/hard-reset-like sessions, 3 standby-reset sessions, 12 total wake events, 10 no-explicit-fault sessions, and cmd-`0x44`/diagnostic observations from both PB1 and PB2 after wake/reset paths;
- if quorum is low, run a targeted `--campaign standby-reset` add-on hunt.

Then select cards from the parent hunt directory:

```bash
PYTHONPATH=src "$PY" scripts/sim_exploratory_select_cards.py \
  artifacts/sim/current/exploratory/<field10_parent_dir> \
  --out /tmp/field10_cards \
  --realistic \
  --top 14 \
  --sample 10
```

Use available subagents as LLM judges over the selected cards and mandatory FIELD-10 cards. Do not use `codex -p`. The subagent workflow must mirror `exploratory_oracle_run.py`: judge, artifact-verify, correctness-verify, synthesize, schema-like `confirmed`/`needs_human`/`refuted` buckets, and an equivalent `run_ok`/error gate. Archive each prompt, assigned card set, verdict, raw subagent result, and reconciliation. Required result: `run_ok`-equivalent true and no unresolved confirmed or needs-human High/Medium safety findings. If a non-`codex -p` model command is available and the operator approves it, `scripts/exploratory_oracle_run.py --cards-index /tmp/field10_cards/workflow_args.json --model-cmd '<approved cmd>' --out artifacts/sim/current/exploratory/field10_oracle.json` may be used in addition to subagents; require `run_ok: true`.

## Deployment and Smoke Plan

Implementation and simulator verification do not require live hardware flashing. FIELD-10 may be marked sim-fixed after simulator and exploratory gates pass, but not release-promoted/recommended until operator-approved hardware smoke is recorded.

Operator-only role-safe flash commands, if live flashing is separately approved:

```bash
PY="${DLCP_PYTHON:-.venv_ep0/bin/python}"
PYTHONPATH=src "$PY" scripts/hardware_state_test.py detect
PYTHONPATH=src "$PY" scripts/hardware_state_test.py identify-mains --require-left-right
# refresh/export LEFT_HID and RIGHT_HID from latest identify output
PYTHONPATH=src "$PY" scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --left
PYTHONPATH=src "$PY" scripts/dlcp_v34_release_flash.py --path "$RIGHT_HID" --right
PYTHONPATH=src "$PY" scripts/hardware_state_test.py identify-mains --require-left-right
# refresh/export LEFT_HID and RIGHT_HID after re-enumeration
# Manually enter CONTROL bootloader: power-cycle while holding UP+DOWN for ~6s; do not press SELECT.
scripts/flash_control_safe.sh --path "$LEFT_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex --preflight-only
scripts/flash_control_safe.sh --path "$LEFT_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex
# Cold power-cycle CONTROL plus both MAINs before smoke.
PYTHONPATH=src "$PY" scripts/hardware_state_test.py identify-mains --require-left-right
```

Post-flash smoke, if separately approved, must write durable artifacts under `artifacts/probes/field10_<timestamp>/` and include exact HID paths, revs, JSON diagnostics, LCD captures, IR sequence timing, and stop conditions:

- `dlcp_main_flash.py --path "$LEFT_HID" --info-only` and same for RIGHT;
- `dlcp_preset.py --path "$LEFT_HID" --info-only` and same for RIGHT;
- `dlcp_diag.py --json --ch-map LEFT="$LEFT_HID" --ch-map RIGHT="$RIGHT_HID"`;
- verify Hypex IR profile and run finalize-only recovery if mismatched before relying on IR mute/STBY:
  `scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --finalize-only --profile hypex` and same for RIGHT;
- low-volume IR A/B, mute, standby/wake, rapid toggle, preset convergence, preset-mute timing, preset-standby/wake timing, and short reconnect-responsiveness soak;
- verify clean hard power-cycle reports `Runtime: I0` on both MAINs and no audio excursion or wrong preset image is observed.

## Acceptance Criteria

- `cmd_dispatch_gated` and active7 lifecycle structurally prevent bit1 input-route physical I2C before post-wake device init.
- `event_flags.bit4` route/channel sync still drains before final selected-preset reassert.
- Final selected-preset reassert is structurally proven to use the FIELD-5 validated row writer or an equivalent checked path.
- Barrier success (`main_i2c_service_32f8`) and late bit1 success are both required before any nonzero volume restore; failures assert effective mute, preserve/re-arm retry state, and surface BF/08/CONTROL `!`.
- Clean cold boot, standby/wake, and reconnect settle with cmd-`0x44` `diag_i == 0` on both MAINs in simulation when no explicit fault is injected.
- Phase-locked TAS and secondary/SRC early-not-ready windows cannot produce a healthy, unmuted `I6` state, and late-window failures retry cleanly before volume restore.
- Existing FIELD-5/FIELD-6/FIELD-7 DSP coefficient-safety tests remain green.
- V3.4 build leaves at least 10 bytes free.
- `PYTHONPATH=src "$PY" -m pytest -q -n 16 tests/sim` passes.
- A 30-minute exploratory run plus subagent LLM judging produces no unresolved High or Medium findings.
- Live hardware promotion is explicitly pending unless separate operator-approved smoke evidence is attached.

## Implementation Evidence

Implemented files:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `tests/sim/test_v34_field_bugs_20260610.py`
- `tests/sim/test_v34_mute_refresh_bug.py`
- `tests/sim/test_v34_v173_exploratory_bug_regressions.py`
- `docs/V34_FIELD_BUGS_20260610.md`
- `docs/IMPL_V34_FIELD10_WAKE_I2C_PHASE_ORDER.md`

Final mechanism:

- `stock_094.bit6` is FIELD-10 `barrier_pending`.
- `stock_094.bit7` is the per-dispatch bit1-attempt marker.
- `event_flags.bit1` is the retryable late input-route phase.
- `active_flags.bit5` owns automatic/fault mute while `active_flags.bit4`
  keeps effective mute asserted.
- `cmd_dispatch_gated` retries a pending wake barrier before active7 or normal
  volume work.  `wake_i2c_barrier_attempt` owns `main_i2c_service_32f8` plus
  the secondary `0x1B` wake-tail write and returns carry on ACKSTAT/fault.
- Active7 no longer drains bit1 as a preamble.  It zero-mutes, drains bit4,
  clears bit6, validates the selected preset image through
  `main_core_service_4574`, and leaves filename/volume work gated by the later
  FIELD-10 phases.
- `adc_boot_gate` runs the post-wake barrier before arming late bit1 and volume
  restore.
- Late bit1 NACKs are retryable and keep fault-owned mute until success.
- `preset_job_apply_i2c_entry` now treats a pre-existing ACKSTAT latch as a
  row failure.  This prevents an active7 zero-mute NACK from being cleared just
  before coefficient rows start.
- Direct user mute clears `event_flags.bit5` only after the verified TAS
  zero-write succeeds.
- A preset job held by the USB filename gate stays force-muted instead of
  returning with old-preset live audio.

Build and size ledger:

```text
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
built canonical V3.4 release: DLCP_Firmware_V3.4.hex (EEPROM rev 0xAB -> 0xAC)

used_bytes_pre_preset_b=15200
last_used_pre_preset_b=0x4BF1
app_end=0x4BF2
contiguous_free_before_0x4C00=14
erased_holes_before_0x4C00=160
free_object_words=7
```

Focused tests:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_field_bugs_20260610.py::test_field10_clean_boot_and_standby_wake_keep_cmd44_i0 \
  tests/sim/test_v34_field_bugs_20260610.py::test_field10_late_bit1_nack_is_retryable_before_volume_restore

2 passed in 10.57s
```

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py \
  tests/sim/test_v34_v173_refactoring_contracts.py

95 passed, 3 xfailed in 405.17s
```

Full simulator gate:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 16 tests/sim

1655 passed, 2 skipped, 3 xfailed, 7 warnings in 608.89s
```

Expected non-green statuses:

- `test_diag_page_front_panel_stby_enters_standby_and_closes_both_main_gates`
  for PB1/PB2 Diagnostics remains strict XFAIL for the separate DIAG-STBY
  CONTROL/UI bug.
- `test_v34_chain_copy_call_sites_are_pre_gie_or_helper_masks_tos_rewrite`
  remains strict XFAIL for the documented `chain_copy` interrupt-safety proof.
- Two skips are pre-existing simulator/precondition skips outside FIELD-10.

Exploratory hunter:

```text
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 30m --campaign all \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/sim/current/exploratory/field10_20260614_230724

run: artifacts/sim/current/exploratory/field10_20260614_230724/20260614_230724_2326ea9090b99eab
seed: 0x2326ea9090b99eab
sessions/events/observations: 78 / 7498 / 5138
incidents: LOW=1 only
golden live checks: 679 observations / 1171 unit-samples, 0 wrong images
active7 observations: 1183
wake-like sessions: 49
PB1/PB2 diagnostic observations: 187 / 111
```

Subagent judge reconciliation:

- DSP-safety and oracle judges found no live wrong coefficient image and no
  missed High/Medium safety finding in the final hunt.
- The only LOW card, `ui.waiting.connected`, stayed Low: source was not live
  PCM, TAS `0x30` was zero, and the next observation recovered.
- Sessions 24, 50, and 61 `diag.I` concerns were reclassified as synthetic
  random-triplet sessions.  Each had arbitrary CONTROL RX `triplet` injection
  before the first nonzero `diag.I`, so they are not clean boot/wake
  no-fault evidence.
- Sessions 38 and 48 were explicit-fault/source-lost stress candidates.  They
  resolved without live wrong audio and do not block FIELD-10.
- Procedural judge blocks about missing docs/evidence are closed by this
  section and the updated FIELD-10 ledger.

Implementation gate status: simulator-fixed, no unresolved High/Medium, live
hardware smoke pending.  Do not promote or recommend until operator-approved
low-volume live smoke confirms clean hard power-cycle `I0` on both MAINs.

## Reviewer Findings and Iteration History

Initial reviewer set requested by user: 10 subagents covering robustness, size, compactness, coherency, contract, and simplicity.

First pass findings resolved in this revision:

- Simplicity/scope: fixed stale-build test ordering, corrected the size test node, documented single-owner bit1 scope, and added role-safe deploy commands.
- ASM/call graph: added isolated late-bit1 phase, active7 producer matrix, pre-existing bit1 coverage, and distinction between mute latch and actual nonzero TAS volume.
- I2C/SRC/TAS: added barrier success gate, retryable bit1, full visible-fault mask `(0x44)`, effective-mute assertion, wake-tail `0x1B` classification, and transaction attribution requirements.
- DSP safety: required final reassert through the FIELD-5 validated writer and preserved FIELD-6/FIELD-7 final-writer tests.
- Fault handling: added ACKSTAT ownership, BF/08/CONTROL `!` assertions, prior-fault tests, and retry semantics.
- Simulator/tests: required PC-phase barriers, both MAINs, TAS and secondary address/data NACK matrix, cmd `0x44` observability, and focused I2C/diag suites.
- Exploratory/oracle: added mandatory `diag.I` mechanical scan, coverage quorum, targeted standby-reset rerun, subagent evidence archive, and optional non-`codex -p` oracle runner path.
- Size/artifacts: added pre/post size ledger, corrected artifact policy, and blocked release if the 10-byte floor is missed.
- Hardware/operator safety: split sim-fixed from hardware-promoted, added role-safe flashing, durable artifact path, IR profile check, and low-volume live smoke matrix.
- Documentation/traceability: added missing docs, rejected full-dispatcher shortcut, exact commands, and final handoff prompt.

Final targeted rechecks resolved the remaining second-pass Medium findings for oracle equivalence, size ledger, barrier retry ownership, stale/pre-armed bit3, fault-owned mute release, and asleep-preset re-arm. Remaining Low: none blocking implementation.

Review gate status: reviewed - ready for implementation, zero unresolved High/Medium.

## Handoff Goal Prompt

```text
/goal Implement FIELD-10 wake I2C phase-order fix from docs/V34_FIELD_BUGS_20260610.md using docs/IMPL_V34_FIELD10_WAKE_I2C_PHASE_ORDER.md end-to-end.

Process:
1. Read AGENTS.md, README.md, docs/V34_FIELD_BUGS_20260610.md FIELD-10, docs/IMPL_V34_FIELD10_WAKE_I2C_PHASE_ORDER.md, docs/IMPL_V34_FIELD6_WAKE_ROUTE_SYNC_DSP_OWNERSHIP.md, docs/IMPL_V34_FIELD7_FIELD8_PRESET_DSP_SAFETY.md, docs/REFACTORING_V34_V173_SPEC.md, docs/IMPL_REFACTORING_V34_V173.md, docs/HARDWARE_TEST.md, and docs/exploratory_oracle/ORACLE_PROTOCOL.md.
2. Verify the IMPL review gate has no unresolved High/Medium. If not clean, update the IMPL before coding.
3. Implement only the approved IMPL. Preserve d69d689 FIELD-6/7 final-writer safety. Keep bit4 route/channel sync before final validated preset reassert; isolate bit1 until after main_i2c_service_32f8; gate volume on barrier success + retryable late-bit1 success + (dsp_fault_flags & 0x44)==0. Add explicit compact lifecycle state for barrier_pending, late_bit1_pending, and fault_mute_owned; suppress stale bit3 until both gates pass. No diag_i clearing, blind sleeps/retries, duplicated route ladder, or unrelated refactors.
4. Add/update tests first: structural active7/adc_boot_gate ordering, active7 producer matrix, pre-existing bit1/bit3, phase-locked TAS+secondary address/data NACKs on PB1/PB2, barrier retry, retryable late-bit1, forced-mute user-intent recovery, asleep preset re-arm before volume, BF/08/CONTROL ! visibility, cmd-0x44 I0, and FIELD-5/6/7 regression guards.
5. Record pre/post MAIN size ledger: used bytes, last used, free bytes, free object words, 0x1000..0x4BFF diff. Build canonical V3.4 with `PY="${DLCP_PYTHON:-.venv_ep0/bin/python}"; PYTHONPATH=src "$PY" scripts/build_v34_release.py`; stop if margin before 0x4C00 is <10 bytes.
6. Run focused tests from the IMPL, then full sim: `PYTHONPATH=src "$PY" -m pytest -q -n 16 tests/sim`.
7. Run 30m hunter: `PYTHONPATH=src "$PY" scripts/sim_chain_exploratory.py --duration 30m --campaign all --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex --out-dir artifacts/sim/current/exploratory/field10_$(date +%Y%m%d_%H%M%S)`. Treat no-fault diag.I as blocking unless reclassified by evidence; enforce quorum: 3 POR/hard-reset-like, 3 standby-reset, 12 wakes, 10 no-fault, PB1/PB2 diag observations. Select cards, then use subagents as LLM judges mirroring judge->artifact-verify->correctness-verify->synthesize. Do not use codex -p. Reconcile all High/Medium.
8. Update the IMPL with actual files, size delta, test/exploration/subagent evidence, sim-fixed vs hardware-pending status, and unresolved Low only. Do not flash hardware unless separately requested. Commit only if requested.
```
