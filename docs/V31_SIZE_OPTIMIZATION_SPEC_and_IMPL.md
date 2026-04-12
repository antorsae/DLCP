# V3.1 MAIN Size Optimization Spec and Implementation Plan

Date: 2026-04-12
Status: draft
Target source: `src/dlcp_fw/asm/dlcp_main_v31.asm`
Target build: `firmware/patched/releases/DLCP_Firmware_V3.1.hex`

## Goal

Reduce the size of `dlcp_main_v31.asm` as far as possible without
breaking any V3.1 behavior. The work is a size-reduction campaign, not a
feature campaign and not a behavioral cleanup campaign.

## Non-Negotiable Requirements

- Functionality shall be equivalent to V3.1.
- The optimized build shall pass the full V3.1 validation suite
  recorded in this spec on every merge-eligible candidate.
- No new executable code islands are allowed. The executable body must
  remain the normal contiguous program rooted at `org 0x1000`.
- `org 0x4C00` remains the Preset B anchor in the current V3.1 layout.
  It is not a general patch area. Do not introduce new `org 0x54xx`,
  `org 0x55xx`, or other fixed-address code stubs.
- `org 0x5600` and `org 0xF00000` remain data anchors only.
- Every function and structural code/data block in V3.1 must be reviewed
  for size opportunities. Nothing is skipped because it "looks fine."
- If dead code is suspected, it must first be written to a candidate list
  with evidence and risk. Removal is high risk by default unless the code
  is clearly unreachable by both static and dynamic evidence.
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
  `docs/V31_SIZE_OPTIMIZATION_PROGRESS.md`.

## Definition Of Equivalent

Equivalent means the optimized firmware preserves the externally
observable V3.1 behavior, including:

- boot entry behavior at `0x1000`, ISR entry behavior at `0x1008`, and
  the low-priority stub behavior at `0x1018`
- USB/HID command behavior and version identity
- preset A/B behavior, flash remap behavior, filename slot behavior, and
  EEPROM persistence behavior
- DSP boot state, volume-update path, and robustness/recovery behavior
- current V3.1 source-level semantics unless a change is proven to be
  dead code removal and explicitly accepted as such

## Full V3.1 Validation Suite

As of 2026-04-12, the full V3.1 suite in this repo is 89 selected tests:
9 full files plus 5 targeted nodes from 4 additional files. This was
verified with:

```bash
.venv_ep0/bin/python -m pytest -q --collect-only \
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
  tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]
```

Per-file coverage:

Required files:

- `tests/sim/test_firmware_version_label.py` — 7 tests
- `tests/sim/test_main_gpsim_usb_engine.py` — 4 tests
- `tests/sim/test_v31_command_matrix.py` — 16 tests
- `tests/sim/test_v31_dsp_boot_equivalence.py` — 5 tests
- `tests/sim/test_v31_happy_path.py` — 16 tests
- `tests/sim/test_v31_review_findings.py` — 8 tests
- `tests/sim/test_v31_usb_hid_dispatch.py` — 5 tests
- `tests/sim/test_v31_usb_preset_ab.py` — 17 tests
- `tests/sim/test_v31_v163b_robustness.py` — 6 tests

Required targeted nodes:

- `tests/sim/test_main_dsp_deafness_chain.py::test_main_dsp_deafness_chain_ackstat_dirty_readback[main_v31]`
- `tests/sim/test_main_dsp_deafness_chain.py::test_main_v31_immune_to_dsp_deafness_chain`
- `tests/sim/test_wire_chain_gpsim.py::test_wire_supported_patched_pairs_reach_display[v162b_v31]`
- `tests/sim/test_reconnect_wake_gate.py::test_v31_v163b_wire_chain_standby_reconnect_dsp_gate`
- `tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]`

Total: 89 selected tests

Notes:

- This is the exact full suite currently used to validate V3.1.
- Latest clean parallel result as of 2026-04-12:
  - `86 passed, 2 skipped, 1 xfailed in 503.92s (0:08:23)`
  - skipped nodes: `tests/sim/test_v31_usb_hid_dispatch.py:221`
    because `cmd 0x06 response not staged in RAM (no USB in gpsim)`
- expected `xfail` node:
  `tests/sim/test_v31_v163b_robustness.py::test_wire_mssp_stop_cascade_full_dsp_recovery`
  because gpsim's wire-chain STOP-state model still blocks the final
  post-recovery DSP write in V3.1.
- Some files include parameterized stock/V2.4/V2.6 cases. Those cases
  still remain part of the suite because they are part of the existing
  V3.1 validation files and help catch harness or shared-model
  regressions.
- There is one active `xfail` node in this suite as of 2026-04-12, as
  recorded above.
- `tests/sim/test_v31_usb_preset_ab.py::test_v31_static_remap_constants`
  now intentionally accepts either
  `call        timer3_blocking_delay, 0x0` or
  `rcall       timer3_blocking_delay` inside `preset_delay_150ms`.
  That assertion is guarding the delayed preset helper's existence and
  layout, not the exact call encoding.
- Normal execution mode for the full suite is parallel `pytest-xdist`,
  matching the repo-wide full test gate in `AGENTS.md`.
- In auxiliary git worktrees that do not contain a built local
  `artifacts/tools/gpsim-xtc/build/gpsim/gpsim`, set `DLCP_GPSIM_BIN`
  to another built repo-local `scripts/gpsim-xtc` wrapper before
  running gpsim-backed tests. Do not rely on the Homebrew `gpsim`
  fallback; it prints the banner but not the interactive `**gpsim>`
  prompt expected by the harness.
- If the collected count or file set changes later, this document must
  be updated in the same change.

## Required Verification Gate

A candidate is not merge-eligible unless it assembles cleanly and passes
the full V3.1 validation suite in parallel.

Canonical full-suite command:

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
  tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]
```

Serial fallback for local debugging only:

```bash
DLCP_GPSIM_BIN=/path/to/built/scripts/gpsim-xtc \
.venv_ep0/bin/python -m pytest -q \
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
  tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]
```

If any test in this gate fails for an experiment, that experiment is
rejected immediately and is not stacked with additional edits.

## Review Scope

The review must cover all `; Function:` blocks in
`src/dlcp_fw/asm/dlcp_main_v31.asm`, plus these structural regions:

- app entry block
- USB descriptors and related tables
- HID dispatch and update-relay logic
- UART, I2C, flash, preset, EEPROM, and recovery helpers
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

## Disallowed Or High-Risk Tactics

- new feature work
- semantic cleanups that are not required for byte savings
- timing-sensitive rewrites without proof
- moving behavior into new fixed-address patch islands
- deleting code based only on lack of current test coverage
- removing functions without a ledger entry, risk classification, and
  evidence trail

## Tooling

Primary sources of truth:

- `src/dlcp_fw/asm/dlcp_main_v31.asm`
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
from dlcp_fw.paths import V31_MAIN_ASM, V31_MAIN_HEX
from dlcp_fw.sim.v30_symbols import assemble_v30

assemble_v30(
    V31_MAIN_ASM,
    V31_MAIN_HEX,
    output_lst=V31_MAIN_ASM.with_suffix(".lst"),
)
print(V31_MAIN_HEX)
print(V31_MAIN_ASM.with_suffix(".lst"))
PY
```

Byte counting must be recorded for each candidate. At minimum record:

- non-`0xFF` byte count in `0x1000..0x4BFF`
- highest used byte below `0x4C00`
- free bytes remaining before Preset B

Reference measurement snippet:

```bash
.venv_ep0/bin/python - <<'PY'
from dlcp_fw.paths import V31_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex

mem = parse_intel_hex(V31_MAIN_HEX)
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
  non-`0xFF` code bytes down, but the assembled `.hex` still pads out to
  the Preset B anchor. The file size on disk therefore does not reflect
  the actual change in used code bytes.
- Use `used_bytes_pre_preset_b`, `last_used_pre_preset_b`, and
  `free_bytes_before_0x4C00` from the measurement snippet above
  exclusively. Any experiment result claiming "no binary delta" must
  show those three numeric metrics, not a file-size comparison.
- When reopening a previously rejected experiment, also diff
  `mem[0x1000..0x4BFF]` content (not just the metrics) to confirm
  whether the earlier rejection was a measurement artifact.
- Prior experiment `W01-E01` (removal of `movff X, X` self-moves) was
  rejected on the basis of "no binary delta" but its measurement method
  is not documented in the ledger. Any reopening of that territory must
  capture all three metrics plus a byte-for-byte content diff of the
  code region to produce an authoritative verdict.

## Required Experiment Workflow

1. Build the current baseline V3.1 source and record its measured size.
2. Refresh the full review inventory for every function and structural
   block.
3. Generate 8 parallel experiment hypotheses for the next wave.
4. Create 8 isolated experiment worktrees and assign one experiment to
   each worktree. Subagents may assist, but the coordinator remains
   responsible for authoritative remeasurement and retest.
5. Keep each experiment narrow. One experiment should test one small
   optimization idea or one tightly related edit cluster.
6. For each experiment: edit, assemble, record byte counts, run the
   relevant fast checks, then run the full 89-node V3.1 validation
   suite.
7. Abort that experiment on the first failed required check or test.
8. Compare surviving experiments by net byte savings, risk, and code
   clarity.
9. Recombine compatible successful experiments into stronger combined
   candidates whenever possible. Treat the campaign as an evolutionary
   search: preserve good local improvements, then combine them to see
   whether the merged candidate saves more bytes while still passing the
   full gate.
10. Merge only the best proven-compatible combined result, then rerun the
   full gate on the merged result before starting the next wave.
11. Treat that merged passing result as the new baseline and
    immediately begin the next wave rather than concluding the campaign.
12. After updating the spec/progress docs for that new baseline,
    actually launch the next experiments. Do not stop after merely
    stating that the next wave should happen.

## Continuation Rule

This campaign has no internal "done" state.

- A passing candidate is not completion. It is only the next baseline.
- An accepted merge does not end the work. It starts the next search
  wave.
- Updating `docs/V31_SIZE_OPTIMIZATION_PROGRESS.md` does not end the
  work. It is only a checkpoint before the next wave begins.
- Updating `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md` does not end
  the work. It is only a checkpoint before the next wave begins.
- The agent should keep iterating indefinitely, wave after wave,
  continuing analysis, recombination, and new experiments.
- The agent should not stop because the remaining savings look small,
  because the code is currently stable, or because one optimization wave
  succeeded.
- The agent should not stop after phrases such as "accepted baseline",
  "next wave", "ready for another pass", or "the next candidate should
  be ...". It must actually perform the next pass.
- The only valid pause or stop conditions are:
  - explicit external stop from the user
  - environment/runtime termination
  - a hard blocker that requires human input, approval, or missing tool
    installation
- If blocked, the agent should report the blocker, request the needed
  input or tool, and then resume the iterative campaign rather than
  declaring completion.

## Interim Reporting Rule

Interim reporting is allowed. Final completion reporting is not.

- The agent may emit short progress updates while the campaign is
  running.
- Any such update must be followed by more optimization work in the same
  execution unless one of the valid pause/stop conditions applies.
- A progress message that ends after one wave without starting the next
  wave is a spec violation.
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
  `docs/V31_SIZE_OPTIMIZATION_PROGRESS.md`.
- If a recombined candidate fails, keep the parent results and only
  reject the combined child.
- Use this process like genetic recombination: good traits should be
  carried forward and evolved into later waves when compatible.

## Parallelism Rule

Optimization work proceeds in waves of 8 experiments in parallel, each
in its own isolated worktree.

- Do not run ad hoc single experiments outside the wave system.
- Do not collapse the wave into one dirty worktree. The eight edits must
  remain independently attributable.
- If fewer than 8 fresh ideas remain, fill the remaining slots with
  confirmation variants of the strongest ideas rather than dropping to a
  serial process.
- Each experiment must have a unique ID such as `W01-E03`.
- Each experiment must have an isolated edit scope and its own size/test
  record.
- Each experiment must also record the responsible executor
  (subagent or coordinator).
- Recombined follow-up candidates should also get their own IDs and must
  record which earlier experiments they inherit from.
- The main agent acts as coordinator: it prepares experiment briefs,
  launches workers or local worktrees, collects results, chooses
  recombinations, and launches the next wave.
- If worker isolation fails and a worker mutates the coordinator
  checkout, freeze worker activity immediately and treat only the
  coordinator's remeasurement/retest as authoritative.

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

`docs/V31_SIZE_OPTIMIZATION_PROGRESS.md` must be the running ledger for
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

## Deliverables

These are checkpoint artifacts, not a termination condition.

- optimized `src/dlcp_fw/asm/dlcp_main_v31.asm`
- assembled optimized V3.1 HEX
- updated `docs/V31_SIZE_OPTIMIZATION_PROGRESS.md`
- explicit list of accepted size-saving actions
- explicit list of dead-code removal candidates, even if none are
  removed

## Actions Recorded So Far

- 2026-03-29: created this specification document
- 2026-03-29: expanded the verification gate to the full V3.1 suite
  currently collected in this repo: 59 tests across 8 files
- 2026-03-29: no size-changing source edits have been accepted yet
- 2026-03-30: expanded the verification gate again to the current 80-node
  V3.1 suite: 9 full files plus 5 targeted nodes from 4 additional files
- 2026-03-30: validated the current accepted size candidate with the
  expanded parallel gate: `78 passed, 2 skipped in 511.93s`
- 2026-04-11: refreshed the exact V3.1 gate to the current 89-node
  suite and recorded the clean parallel result:
  `86 passed, 2 skipped, 1 xfailed in 493.63s`
- 2026-04-11: W05 showed that even explicitly assigned worker-owned
  worktrees can still contaminate the coordinator checkout, so the spec
  now treats only coordinator remeasurement/retest as authoritative.
- 2026-04-11: auxiliary git worktrees without a built local
  `gpsim-xtc` need `DLCP_GPSIM_BIN` pinned to a working repo-local
  wrapper; the Homebrew `gpsim` fallback does not emit the interactive
  prompt expected by the harness.
- 2026-04-11: external audit of `W01-E01` rejection found its "no binary
  delta" result inconsistent with `.lst` evidence — each
  `movff X, X` self-move emits 4 bytes of object code. Added the
  `## Measurement Gotchas` subsection to this spec and scheduled
  `W04-E03..E05` to reopen self-move removal under content-diff
  validation.
- 2026-04-11: Queued `W06` execution wave consisting of low-risk structure optimizations including 122 instances of `call` -> `rcall` conversion, `call`+`return 0` tail-call optimization into branches, removal of redundant `iorlw 0x00` ops, preamble extraction for `send_status_burst`, and safe flag-audited `movwf` -> `clrf` zero-materializations.
- 2026-04-11: Accepted `W06-R03` after coordinator-only rebuild and full-gate validation. Accepted actions were the full 122-site reachable `call` -> `rcall` sweep, 4 redundant `iorlw 0x00` deletions after `rx_ring_has_data`, and the local `send_status_burst` preamble helper. Rejected actions were the 11-site tail-call family (`W06-E03`) after a real happy-path regression and the queued `movwf` -> `clrf` sites (`W06-E06` / `W06-E07`) after static re-audit showed their stored values were load-bearing booleans.
- 2026-04-11: Queued `W07` execution wave. Target estimated size reduction: ~150-160 bytes. Features: array-mapping elimination in `cmd_dispatch_gated`, local helper for repetitive I2C payload writes, shared postamble for `send_status_burst`, pointer-load tightening in ring buffers, and several single-instruction wrapper inlinings.
- 2026-04-12: Executed `W07` in eight isolated detached worktrees under
  `artifacts/reanalysis/size_opt_w07/` and remeasured every experiment
  in the coordinator checkout before any merge decision.
- 2026-04-12: `W07-E01`, `W07-E02`, `W07-E03`, and `W07-E06` all passed
  the established 32-node smoke gate with the expected lone wire-chain
  STOP-state `xfail`. `W07-E04` regressed
  `test_v31_v163b_wire_chain_standby_reconnect_dsp_gate` and was
  rejected intact.
- 2026-04-12: `W07-E05` and `W07-E07` assembled and saved 14 bytes each
  but were intentionally held out because the remaining helper-semantics
  and STATUS proof burden was not worth the gain once the larger green
  parents already met the wave target. `W07-E08` confirmed `W07-E01`
  exactly on size metrics in a second isolated tree.
- 2026-04-12: Accepted `W07-R01` after coordinator-only recombination,
  smoke, and full-gate validation. Accepted actions were direct
  `ram_0x013/0x014` staging plus `0x5F` hoisting in
  `cmd_dispatch_gated`, a new local `cmd_dispatch_gated_i2c_pair`
  helper, the `send_status_burst` postamble helper, and direct `0x02xx`
  pointer loads in the RX ring enqueue/read paths. The accepted child
  measured `used_bytes_pre_preset_b=14719`,
  `last_used_pre_preset_b=0x49E1`, `free_bytes_before_0x4C00=542`, then
  passed the full 89-node gate with
  `86 passed, 2 skipped, 1 xfailed in 503.92s (0:08:23)`.
- 2026-04-12: Queued `W08` against the accepted `W07-R01` baseline.
  Target estimated size reduction is `~160` bytes, with the largest
  lever being a counted-loop rewrite of the 10x repeated
  `main_core_service_297e` copy/apply cluster. Additional queued
  candidates are the late-tail wrapper cluster, the final redundant
  `iorlw 0x00` in `hid_cmd_diag_memread`, a helper for the repeated
  `computed_volume -> logical_volume` copy, and several higher-risk
  stock-equivalent refactors (`flash_*` preset-B remap sharing,
  `main_i2c_service_2100`, `main_core_service_2328`, `i2c_byte_tx`).
  `W08-E02` is explicitly blocked on new preset-B remap coverage and
  should not be merged speculatively.

## Queued W08 Wave

`W08` shall derive from the accepted `W07-R01` baseline:

- `used_bytes_pre_preset_b=14719`
- `last_used_pre_preset_b=0x49E1`
- `free_bytes_before_0x4C00=542`

Queued experiments:

- `W08-E01`: `main_core_service_297e` counted-loop rewrite for the
  repeated `movff ram_0x02F..032 -> ram_0x025..028 ; movlw 0x2F ; call
  main_core_service_3ec4` cluster. Estimated savings: `~150-190` bytes.
  Risk: high.
- `W08-E02`: shared preset-B remap helper for `flash_read`,
  `flash_write`, and `flash_erase`. Estimated savings: `~30-40` bytes.
  Risk: high. Blocked until there is direct assembly-side gpsim coverage
  for preset-B remapped writes and reads.
- `W08-E03`: late-tail wrapper inlining/deletion around
  `main_core_service_4954`, `main_uart_service_495e`,
  `usb_disconnect_handler`, `main_i2c_service_4966`, and
  `main_core_service_496c`. Estimated savings: `~30-40` bytes. Risk:
  medium.
- `W08-E04`: remove the final redundant `iorlw 0x00` in
  `hid_cmd_diag_memread`. Estimated savings: `2` bytes. Risk: low.
- `W08-E05`: factor the repeated four-byte
  `computed_volume -> logical_volume` copy into a local helper if the
  call topology stays size-positive. Estimated savings: `~18` bytes.
  Risk: medium.
- `W08-E06`: shrink the `main_i2c_service_2100` data-move ladders using
  a smaller stock-equivalent structure. Estimated savings: `~20-40`
  bytes. Risk: high.
- `W08-E07`: compress the `main_core_service_2328` bit-to-byte fanout /
  boolean materialization block without changing byte values or flags.
  Estimated savings: `~16-24` bytes. Risk: medium.
- `W08-E08`: audit low-priority `i2c_byte_tx` masked-mode
  classification sharing. Estimated savings: `~6-12` bytes. Risk: high.

Execution order guidance:

- First-wave priority is `W08-E01`, `W08-E03`, `W08-E04`, and
  `W08-E05`.
- Keep `W08-E02` blocked until the remap coverage prerequisite lands.
- Treat `W08-E06..E08` as exploratory stock-equivalent candidates and
  keep them out of the first recombination child unless they are proven
  independently.
