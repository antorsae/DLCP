# V3.1 MAIN Size Optimization Spec and Implementation Plan

Date: 2026-03-29
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
- Those 8 parallel experiments must be executed via 8 subagents, with
  one subagent assigned to each experiment.
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

As of 2026-03-30, the full V3.1 suite in this repo is 80 selected tests:
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

- `tests/sim/test_firmware_version_label.py` — 5 tests
- `tests/sim/test_main_gpsim_usb_engine.py` — 4 tests
- `tests/sim/test_v31_command_matrix.py` — 16 tests
- `tests/sim/test_v31_dsp_boot_equivalence.py` — 5 tests
- `tests/sim/test_v31_happy_path.py` — 16 tests
- `tests/sim/test_v31_review_findings.py` — 8 tests
- `tests/sim/test_v31_usb_hid_dispatch.py` — 5 tests
- `tests/sim/test_v31_usb_preset_ab.py` — 11 tests
- `tests/sim/test_v31_v163b_robustness.py` — 5 tests

Required targeted nodes:

- `tests/sim/test_main_dsp_deafness_chain.py::test_main_dsp_deafness_chain_ackstat_dirty_readback[main_v31]`
- `tests/sim/test_main_dsp_deafness_chain.py::test_main_v31_immune_to_dsp_deafness_chain`
- `tests/sim/test_wire_chain_gpsim.py::test_wire_supported_patched_pairs_reach_display[v162b_v31]`
- `tests/sim/test_reconnect_wake_gate.py::test_v31_v163b_wire_chain_standby_reconnect_dsp_gate`
- `tests/sim/test_wire_chain_gpsim_stock_faults.py::test_wire_extended_mssp_stop_fault_degrades_dsp_command_path[main_v31]`

Total: 80 selected tests

Notes:

- This is the exact full suite currently used to validate V3.1.
- Latest clean parallel result as of 2026-03-30:
  - `78 passed, 2 skipped in 511.93s (0:08:31)`
  - skipped nodes: `tests/sim/test_v31_usb_hid_dispatch.py:221`
    because `cmd 0x06 response not staged in RAM (no USB in gpsim)`
- Some files include parameterized stock/V2.4/V2.6 cases. Those cases
  still remain part of the suite because they are part of the existing
  V3.1 validation files and help catch harness or shared-model
  regressions.
- There are no active `xfail` nodes in this suite as of 2026-03-30.
- Normal execution mode for the full suite is parallel `pytest-xdist`,
  matching the repo-wide full test gate in `AGENTS.md`.
- If the collected count or file set changes later, this document must
  be updated in the same change.

## Required Verification Gate

A candidate is not merge-eligible unless it assembles cleanly and passes
the full V3.1 validation suite in parallel.

Canonical full-suite command:

```bash
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

## Required Experiment Workflow

1. Build the current baseline V3.1 source and record its measured size.
2. Refresh the full review inventory for every function and structural
   block.
3. Generate 8 parallel experiment hypotheses for the next wave.
4. Spawn 8 subagents and assign one experiment to each subagent.
5. Keep each experiment narrow. One experiment should test one small
   optimization idea or one tightly related edit cluster.
6. For each experiment: edit, assemble, record byte counts, run the
   relevant fast checks, then run the full 80-node V3.1 validation
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

Optimization work proceeds in waves of 8 experiments in parallel, run by
8 subagents.

- Do not run ad hoc single experiments outside the wave system.
- Do not simulate the 8 experiments serially in one agent. Use 8
  subagents and run them concurrently.
- If fewer than 8 fresh ideas remain, fill the remaining slots with
  confirmation variants of the strongest ideas rather than dropping to a
  serial process.
- Each experiment must have a unique ID such as `W01-E03`.
- Each experiment must have an isolated edit scope and its own size/test
  record.
- Each experiment must also record the responsible subagent.
- Recombined follow-up candidates should also get their own IDs and must
  record which earlier experiments they inherit from.
- The main agent acts as coordinator: it prepares experiment briefs,
  launches the subagents, collects results, chooses recombinations, and
  launches the next wave.
- If subagents are unavailable, that is a blocker and must be reported
  explicitly rather than silently falling back to serial execution.

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
- per-experiment subagent ownership
- recombination lineage for combined candidates
- cumulative action log of accepted size reductions
- dead code candidate list
- open questions and blocked tooling

Minimum per-experiment fields:

`Wave`, `Experiment`, `Subagent`, `Scope`, `Hypothesis`, `Assembles`,
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
