# V3.2 MAIN Size Optimization Spec and Implementation Plan

Date: 2026-04-21 (original) / 2026-04-23 (reopened with `free >= 500 B`
target)
Status: active — reopened 2026-04-23 after wake-path hardening
checkpoint drifted the W03-R01 accepted baseline from `free=378` back
down to `free=310`. New stop condition: `free >= 500 B`. Target means
recovering at least 190 additional bytes from the current
post-checkpoint baseline.
Target source: `src/dlcp_fw/asm/dlcp_main_v32.asm`
Target build: `firmware/patched/releases/DLCP_Firmware_V3.2.hex`

## Goal

Reduce the size of `dlcp_main_v32.asm` as far as possible without
breaking any V3.2 behavior. The work is a size-reduction campaign, not a
feature campaign and not a behavioral cleanup campaign.

This campaign succeeds the frozen V3.1 campaign documented in
`docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md`. V3.2 forked from V3.1
`W08-R01` source and inherited every W02–W08 accepted optimization
(dead-code removals, `call` → `rcall` sweep, `send_status_burst`
preamble/postamble helpers, `cmd_dispatch_gated_i2c_pair` helper,
counted-loop rewrite in `main_core_service_297e`, `computed_volume ->
logical_volume` copy helper, etc.). V3.2 then consumed ~780 bytes of the
recovered slack on new features: asynchronous preset job state machine,
bounded START/STOP waits, mute/preset coalescing, standby/reconnect
cancellation, Layer 1 bounded TX, Layer 2 full-sync, Layer 5 Tier-1
diagnostics (rev 0x37), no-pop flash entry helper.

## Pressure Statement

V3.2 was at the limit at campaign launch. Original baseline
(2026-04-21):

- `used_bytes_pre_preset_b=15257`
- `last_used_pre_preset_b=0x4BFD`
- `free_bytes_before_0x4C00=2`

Waves `W01` / `W02` / `W03` recovered `-377 B` (14880/0x4A85/378) before
the `W03-R01` accept on 2026-04-21. The wake-path hardening checkpoint
landed the next day and ate 62 B of that recovery, leaving the current
active baseline at `14942 / 0x4AC9 / 310`. The new stop condition
(`free >= 500 B`) requires recovering at least another **190 B** so
that the V3.2 line can absorb both the already-merged hardening and
the next round of Layer 5 / hang-hardening extensions without
reshaping the Preset B anchor.

## Non-Negotiable Requirements

- Functionality shall be equivalent to V3.2.
- The optimized build shall pass the full V3.2 validation gate recorded
  in this spec on every merge-eligible candidate.
- No new executable code islands are allowed. The executable body must
  remain the normal contiguous program rooted at `org 0x1000`.
- `org 0x4C00` remains the Preset B anchor. It is not a general patch
  area. Do not introduce new `org 0x54xx`, `org 0x55xx`, or other
  fixed-address code stubs.
- `org 0x5600` and `org 0xF00000` remain data anchors only.
- Every function and structural code/data block in V3.2 must be reviewed
  for size opportunities. Nothing is skipped because it "looks fine."
- If dead code is suspected, it must first be written to a candidate
  list with evidence and risk. Removal is high risk by default unless
  the code is clearly unreachable by both static and dynamic evidence.
- The process must be iterative: analyze, edit, assemble, count bytes,
  run tests, reject on any failure, and only then consider merge.
- The process must run in waves of 8 experiments in parallel.
- Those 8 parallel experiments must execute in 8 isolated edit scopes,
  preferably separate git worktrees under `artifacts/reanalysis/...`.
- Subagents may be used to drive those isolated worktrees, but their
  outputs are advisory until the coordinator remeasures and retests the
  resulting candidate in the authoritative checkout.
- The agent executing this campaign shall not self-terminate because it
  found one good result. Any passing merged result becomes the new
  baseline for the next wave.
- Recording a passing result, updating the ledger, or writing a status
  summary is not completion. Those are checkpoint actions only.
- The campaign should continue indefinitely until externally stopped or
  blocked by a hard dependency that requires human input or tool
  installation.
- The campaign ledger must be maintained in
  `docs/V32_SIZE_OPTIMIZATION_PROGRESS.md`.

## Definition Of Equivalent

Equivalent means the optimized firmware preserves the externally
observable V3.2 behavior, including:

- boot entry behavior at `0x1000`, ISR entry behavior at `0x1008`, and
  the low-priority stub behavior at `0x1018`
- USB/HID command behavior and version identity (`03/02/37` marker,
  `cmd 0x44` diag snapshot, `cmd 0x22` reset-flags burst)
- preset A/B behavior, flash remap behavior, filename slot behavior,
  EEPROM persistence behavior
- DSP boot state, volume-update path, robustness/recovery behavior
- async preset job state machine: `preset_job_state` transitions,
  mute/preset coalescing, standby/reconnect cancellation, bounded
  START/STOP waits
- Layer 1 bounded TX / Layer 2 full-sync / Layer 5 Tier-1 diagnostics
  counters and `cmd 0x21` / `cmd 0x22` / `cmd 0x44` semantics
- no-pop flash entry helper (`flash_entry_quiet_shutdown`) and its
  bounded-I2C secondary-device interaction
- current V3.2 source-level semantics unless a change is proven to be
  dead code removal and explicitly accepted as such

## Full V3.2 Validation Gate

The V3.2 gate is the V3.1 89-node gate (inherited from
`docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md` §Full V3.1 Validation
Suite) **plus** the V3.2-specific test files.

### Required V3.1-inherited files (87 tests + 5 targeted nodes)

These exercise V3.2's inherited V3.1 surface. They are executed against
both V3.1 and V3.2 builds today via parameterization; any regression in
V3.1 behavior must also fail here.

- `tests/sim/test_firmware_version_label.py`
- `tests/sim/test_main_gpsim_usb_engine.py`
- `tests/sim/test_v31_command_matrix.py`
- `tests/sim/test_v31_dsp_boot_equivalence.py`
- `tests/sim/test_v31_happy_path.py`
- `tests/sim/test_v31_review_findings.py`
- `tests/sim/test_v31_usb_hid_dispatch.py`
- `tests/sim/test_v31_usb_preset_ab.py`
- `tests/sim/test_v31_v163b_robustness.py`
- `tests/sim/test_main_dsp_deafness_chain.py::test_main_dsp_deafness_chain_ackstat_dirty_readback[main_v31]`
- `tests/sim/test_main_dsp_deafness_chain.py::test_main_v31_immune_to_dsp_deafness_chain`
- `tests/sim/test_wire_chain_gpsim.py::test_wire_supported_patched_pairs_reach_display[v162b_v31]`
- `tests/sim/test_reconnect_wake_gate.py::test_v31_v163b_wire_chain_standby_reconnect_dsp_gate`
- `tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]`

### Required V3.2-specific files

- `tests/sim/test_v32_layer5_diag_counters.py`
- `tests/sim/test_v32_no_pop_flash_entry.py`
- `tests/sim/test_v28_wire_delayed_switch_repros.py`
- `tests/sim/test_dlcp_diag.py`
- `tests/sim/test_dlcp_v32_release_flash.py`
- `tests/sim/test_v171_v32_layer5_diag_chain.py`
- `tests/sim/test_v171_layer5_diag_page.py`

Total gate: 89 V3.1 nodes + 167 V3.2-specific nodes = **256 selected
tests** (collection verified 2026-04-21).

## Required Verification Gate

A candidate is not merge-eligible unless it assembles cleanly and passes
the full V3.2 validation gate in parallel.

Canonical full-gate command:

```bash
DLCP_GPSIM_BIN=/path/to/built/scripts/gpsim-xtc \
.venv_ep0/bin/python -m pytest -n 16 -q \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_main_gpsim_usb_engine.py \
  tests/sim/test_v31_command_matrix.py \
  tests/sim/test_v31_dsp_boot_equivalence.py \
  tests/sim/test_v31_happy_path.py \
  tests/sim/test_v31_review_findings.py \
  tests/sim/test_v31_usb_hid_dispatch.py \
  tests/sim/test_v31_usb_preset_ab.py \
  tests/sim/test_v31_v163b_robustness.py \
  tests/sim/test_main_dsp_deafness_chain.py::test_main_dsp_deafness_chain_ackstat_dirty_readback[main_v31] \
  tests/sim/test_main_dsp_deafness_chain.py::test_main_v31_immune_to_dsp_deafness_chain \
  tests/sim/test_wire_chain_gpsim.py::test_wire_supported_patched_pairs_reach_display[v162b_v31] \
  tests/sim/test_reconnect_wake_gate.py::test_v31_v163b_wire_chain_standby_reconnect_dsp_gate \
  tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31] \
  tests/sim/test_v32_layer5_diag_counters.py \
  tests/sim/test_v32_no_pop_flash_entry.py \
  tests/sim/test_v28_wire_delayed_switch_repros.py \
  tests/sim/test_dlcp_diag.py \
  tests/sim/test_dlcp_v32_release_flash.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v171_layer5_diag_page.py
```

Expected xfails / skips on baseline (record on first baseline gate run
and carry forward):

- `tests/sim/test_v31_v163b_robustness.py::test_wire_mssp_stop_cascade_full_dsp_recovery`
  remains xfailed because the gpsim wire-chain STOP-state model still
  blocks the final post-recovery DSP write in V3.1/V3.2.
- `tests/sim/test_v28_wire_delayed_switch_repros.py` was recorded as
  `5 xfailed` in the 2026-04-14 `AGENTS.md` verification list; confirm
  the same shape on the V3.2 baseline before comparing candidates.
- `tests/sim/test_v31_usb_hid_dispatch.py:221` skipped (`cmd 0x06`
  response not staged in RAM — no USB in gpsim).

If any non-expected-xfail test fails for an experiment, that experiment
is rejected immediately and is not stacked with additional edits.

## Review Scope

The review must cover all `; Function:` blocks in
`src/dlcp_fw/asm/dlcp_main_v32.asm`, plus these structural regions:

- app entry block
- USB descriptors and related tables
- HID dispatch and update-relay logic
- UART, I2C, flash, preset, EEPROM, and recovery helpers
- V3.2 async preset job state machine (`preset_job_*` labels)
- V3.2 no-pop flash entry helper (`flash_entry_quiet_shutdown` / related)
- V3.2 Layer 5 Tier-1 diagnostics (`diag_*` labels, `cmd 0x21`, `cmd
  0x22`, `cmd 0x44` handlers, `diag_send_burst` helper)
- Layer 1 bounded TX / Layer 2 full-sync helpers added in V3.2
- Preset B and Preset A tables
- EEPROM data block

Each reviewed item must be classified in the progress ledger as one of:

- `keep`
- `optimize locally`
- `share/reuse candidate`
- `candidate dead code`
- `high-risk / do not touch`

## Allowed Size-Reduction Tactics

- remove redundant instructions
- shorten branch structure or use fall-through where behavior is
  preserved
- merge duplicated tails or wrappers when the net byte count improves
- replace repeated straight-line sequences with a shared helper only if
  the total call/return overhead still saves bytes
- tighten literal/materialization sequences
- remove duplicated data or comments-only scaffolding that affects
  output size
- reuse existing helpers instead of cloning near-identical logic
- convert `call` → `rcall` for reachable targets (bank-0, ≤ ±1024
  words) — but reach must be validated by gpasm; V3.1's W06 exhaustive
  sweep means residual V3.2 `call` sites are **either new V3.2 code or
  previously-rejected-as-unreachable**, so each V3.2 conversion needs
  fresh reach validation

## Disallowed Or High-Risk Tactics

- new feature work
- semantic cleanups that are not required for byte savings
- timing-sensitive rewrites without proof (especially the async preset
  state machine's bounded waits and the Layer 5 diag counter
  saturation macro)
- moving behavior into new fixed-address patch islands
- deleting code based only on lack of current test coverage
- removing functions without a ledger entry, risk classification, and
  evidence trail
- `movlw 0x00 + movwf F → clrf F` rewrites without a per-site flag /
  value audit. V3.1 `W06-E06` / `W06-E07` proved several candidate
  sites actually materialize 0/1 selectors, not zeros, so `clrf` would
  change stored values not just flags.

## Tooling

Primary sources of truth:

- `src/dlcp_fw/asm/dlcp_main_v32.asm`
- the generated `.lst` file from gpasm
- the generated `.hex` file
- `dlcp_fw.sim.v30_symbols.parse_gpasm_symbols()`
- `dlcp_fw.sim.hexio.parse_intel_hex()`

Optional analysis tools:

- `gpdasm`
- `radare2` / `rizin`
- Ghidra
- custom static scripts under `src/dlcp_fw/analysis/`

If a tool would materially improve the analysis and is not installed,
ask the user to install it before relying on it.

## Build And Measurement

Baseline and candidate assembly should use the existing helper:

```bash
.venv_ep0/bin/python - <<'PY'
from dlcp_fw.paths import V32_MAIN_ASM, V32_MAIN_HEX
from dlcp_fw.sim.v30_symbols import assemble_v30

assemble_v30(
    V32_MAIN_ASM,
    V32_MAIN_HEX,
    output_lst=V32_MAIN_ASM.with_suffix(".lst"),
)
print(V32_MAIN_HEX)
print(V32_MAIN_ASM.with_suffix(".lst"))
PY
```

Byte counting must be recorded for each candidate. At minimum record:

- non-`0xFF` byte count in `0x1000..0x4BFF`
- highest used byte below `0x4C00`
- free bytes remaining before Preset B

Reference measurement snippet:

```bash
.venv_ep0/bin/python - <<'PY'
from dlcp_fw.paths import V32_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex

mem = parse_intel_hex(V32_MAIN_HEX)
used = [a for a in range(0x1000, 0x4C00) if mem.get(a, 0xFF) != 0xFF]
last_used = max(used) if used else 0x0FFF
print(f"used_bytes_pre_preset_b={len(used)}")
print(f"last_used_pre_preset_b=0x{last_used:04X}")
print(f"free_bytes_before_0x4C00={0x4C00 - (last_used + 1)}")
PY
```

## Measurement Gotchas

File-size-on-disk is not a valid delta signal for this campaign.

- Every experiment that edits source upstream of `org 0x4C00` shifts
  non-`0xFF` code bytes down, but the assembled `.hex` still pads out
  to the Preset B anchor. The file size on disk therefore does not
  reflect the actual change in used code bytes.
- Use `used_bytes_pre_preset_b`, `last_used_pre_preset_b`, and
  `free_bytes_before_0x4C00` from the measurement snippet above
  exclusively. Any experiment result claiming "no binary delta" must
  show those three numeric metrics, not a file-size comparison.
- When reopening a previously rejected experiment, also diff
  `mem[0x1000..0x4BFF]` content (not just the metrics) to confirm
  whether the earlier rejection was a measurement artifact. See V3.1
  `W01-E01` history for the cautionary case.

## Required Experiment Workflow

1. Build the current baseline V3.2 source and record its measured size.
2. Refresh the full review inventory for every function and structural
   block.
3. Generate 8 parallel experiment hypotheses for the next wave.
4. Create 8 isolated experiment worktrees and assign one experiment to
   each worktree. Subagents may assist, but the coordinator remains
   responsible for authoritative remeasurement and retest.
5. Keep each experiment narrow. One experiment should test one small
   optimization idea or one tightly related edit cluster.
6. For each experiment: edit, assemble, record byte counts, run the
   relevant fast checks, then run the full 256-node V3.2 validation
   gate.
7. Abort that experiment on the first failed required check or test.
8. Compare surviving experiments by net byte savings, risk, and code
   clarity.
9. Recombine compatible successful experiments into stronger combined
   candidates whenever possible. Treat the campaign as an evolutionary
   search: preserve good local improvements, then combine them to see
   whether the merged candidate saves more bytes while still passing
   the full gate.
10. Merge only the best proven-compatible combined result, then rerun
    the full gate on the merged result before starting the next wave.
11. Treat that merged passing result as the new baseline and
    immediately begin the next wave rather than concluding the
    campaign.
12. After updating the spec/progress docs for that new baseline,
    actually launch the next experiments. Do not stop after merely
    stating that the next wave should happen.

## Continuation Rule

This campaign has no internal "done" state.

- A passing candidate is not completion. It is only the next baseline.
- An accepted merge does not end the work. It starts the next search
  wave.
- Updating `docs/V32_SIZE_OPTIMIZATION_PROGRESS.md` does not end the
  work. It is only a checkpoint before the next wave begins.
- Updating this spec does not end the work. It is only a checkpoint
  before the next wave begins.
- The agent should keep iterating indefinitely, wave after wave,
  continuing analysis, recombination, and new experiments.
- The agent should not stop because the remaining savings look small,
  because the code is currently stable, or because one optimization
  wave succeeded.
- The only valid pause or stop conditions are:
  - explicit external stop from the user
  - environment/runtime termination
  - a hard blocker that requires human input, approval, or missing
    tool installation
- If blocked, the agent should report the blocker, request the needed
  input or tool, and then resume the iterative campaign rather than
  declaring completion.

## Interim Reporting Rule

Interim reporting is allowed. Final completion reporting is not.

- The agent may emit short progress updates while the campaign is
  running.
- Any such update must be followed by more optimization work in the
  same execution unless one of the valid pause/stop conditions
  applies.
- A progress message that ends after one wave without starting the
  next wave is a spec violation.
- If a wave finishes successfully, the next required actions are:
  - write the new baseline to the progress ledger
  - queue the next 8 experiments or recombined children
  - start executing them

## Experiment Recombination Rule

The optimization campaign should evolve over time. It should not behave
like a sequence of isolated single-winner trials.

- When two or more experiments independently produce safe savings in
  different parts of the source, combine them into a new candidate and
  measure/test that combined result.
- Prefer combining low-risk wins from disjoint scopes before attempting
  higher-risk rewrites.
- Record parent experiment IDs for every recombined candidate in
  `docs/V32_SIZE_OPTIMIZATION_PROGRESS.md`.
- If a recombined candidate fails, keep the parent results and only
  reject the combined child.
- Use this process like genetic recombination: good traits should be
  carried forward and evolved into later waves when compatible.

## Parallelism Rule

Optimization work proceeds in waves of 8 experiments in parallel, each
in its own isolated worktree.

- Do not run ad hoc single experiments outside the wave system.
- Do not collapse the wave into one dirty worktree. The eight edits
  must remain independently attributable.
- If fewer than 8 fresh ideas remain, fill the remaining slots with
  confirmation variants of the strongest ideas rather than dropping to
  a serial process.
- Each experiment must have a unique ID such as `W01-E03`.
- Each experiment must have an isolated edit scope and its own
  size/test record.
- Each experiment must also record the responsible executor
  (subagent or coordinator).
- Recombined follow-up candidates should also get their own IDs and
  must record which earlier experiments they inherit from.
- The main agent acts as coordinator: it prepares experiment briefs,
  launches workers or local worktrees, collects results, chooses
  recombinations, and launches the next wave.
- If worker isolation fails and a worker mutates the coordinator
  checkout, freeze worker activity immediately and treat only the
  coordinator's remeasurement/retest as authoritative. This occurred
  twice in the V3.1 campaign (W02 and W05); do not assume fresh
  workers are isolated just because the directory structure looks
  correct.

## Dead Code Candidate Policy

Any suspected dead code must be tracked before removal with:

- label or address range
- reason it looks dead
- static evidence
- dynamic evidence or lack thereof
- tests that would cover the removal
- risk level
- removal decision

Default risk for function removal is `high`.

## Progress Ledger Requirements

`docs/V32_SIZE_OPTIMIZATION_PROGRESS.md` must be the running ledger for
this campaign. It must contain at least:

- baseline size snapshot
- per-wave experiment table
- per-experiment byte counts and deltas
- per-experiment test status
- merge decisions
- per-experiment executor ownership
- recombination lineage for combined candidates
- cumulative action log of accepted size reductions
- dead code candidate list
- open questions and blocked tooling

Minimum per-experiment fields:

`Wave`, `Experiment`, `Executor`, `Scope`, `Hypothesis`, `Assembles`,
`Used Bytes`, `Last Used`, `Free Bytes`, `Delta`, `Tests`, `Result`,
`Merged`, `Risk`, `Notes`

## Carried-Forward V3.1 Context

- V3.1 `W04` queue is largely exhausted in V3.2 before execution:
  - `W04-E01` (`movlw 0x00` before `clrf`) — **0 sites** in V3.2
    (V3.1's `W05-R01` removed the cluster; V3.2 inherits).
  - `W04-E02` (`movlw 0x00 + movwf F → clrf F`) — 12 sites remain,
    most materialize 0/1 selectors and were rejected by V3.1 `W06`
    re-audit. Per-site flag/value audit required before any conversion.
  - `W04-E03..E05` (`movff X, X` self-move sweep) — **0 sites** in
    V3.2 (V3.1's `W05-R01` removed 22 instances).
  - `W04-E06` (shared BF-status helper for `report_cmd29_status` +
    `factory_reset_status_emit`) — still applicable, small (~2 B net).
  - `W04-E07` (`send_status_burst` Variant A preamble helper) —
    **already landed** in V3.1 `W06-E05` and inherited as
    `send_status_burst_preamble`.
- V3.1 `W08-E02` (shared preset-B remap helper across `flash_read` /
  `flash_write` / `flash_erase`) remains blocked on a missing gpsim
  regression test that drives HID `cmd 0x07` + 8 data chunks with
  `active_flags.2 = 1` and reads back `flash[0x4C00..0x4CBF]`. This is
  also a V3.2 coverage gap. Estimated savings once unblocked: ~36 B
  with a single-arg helper, ~44 B with a parametric start/end helper.

## Deliverables

These are checkpoint artifacts, not a termination condition.

- optimized `src/dlcp_fw/asm/dlcp_main_v32.asm`
- assembled optimized V3.2 HEX
- updated `docs/V32_SIZE_OPTIMIZATION_PROGRESS.md`
- explicit list of accepted size-saving actions
- explicit list of dead-code removal candidates, even if none are
  removed

## Actions Recorded So Far

- 2026-04-21: created this specification document. V3.2 baseline
  measured from current `main` source: `used_bytes_pre_preset_b=15257`,
  `last_used_pre_preset_b=0x4BFD`, `free_bytes_before_0x4C00=2`.
- 2026-04-21: queued `W01` wave of 8 experiments (see progress
  ledger). Scope: V3.2-local mechanical optimizations in code regions
  added by V3.2 (async preset job state machine, Layer 5 diagnostics,
  no-pop flash entry helper, reset-cause classification). Savings
  target: ≥30 bytes recombined, recovering meaningful headroom before
  `0x4C00`.
