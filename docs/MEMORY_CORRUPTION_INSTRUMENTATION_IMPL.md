# Memory Corruption Instrumentation IMPL

Source SPEC: `docs/MEMORY_CORRUPTION_INSTRUMENTATION_SPEC.md`

Date: 2026-06-21

## Status

Phase 1 implemented.  No MAIN or CONTROL behavior changes were made in this
work unit; the changes are simulator instrumentation, Python bindings,
operator artifact tooling, tests, and documentation.

## Implementation Closeout

The instrumented V1.73/V3.5 live-like run reproduces the current rev `0x008F`
failure after clean firmware-path A/B filename repair:

- first protected write: `MAIN0` `EepromArm`
- address: EEPROM `0x8F` (`preset_filename_eeprom_b + 0x0C`)
- old/new: `0x31 -> 0x00`
- PC/source: `0x3984`, `nvm_unlock_and_set_wr`, `bsf EECON1, 1, ACCESS`
- stack: `run_main_foreground_loop -> run_main_service_pass ->
  persist_dirty_runtime_state_to_eeprom -> eeprom_persist_block_walker ->
  eeprom_write_blocking`

Root cause: MAIN V3.5's runtime-state EEPROM table walker keeps its packed
record cursor in `TBLPTR` across calls to `eeprom_write_byte_if_changed`.
That helper reaches the chain-copy trampoline path, which clobbers `TBLPTR`.
The walker then resumes from a corrupted table cursor and consumes bogus
EEPROM offset/data pairs, including `0x8F <- 0x00`.  CONTROL is a stimulus
source, not the EEPROM writer.

Final replayable artifact:

- `artifacts/reanalysis/memory_corruption/20260621T145830Z_v173-v35-live-like_00350173/`

The artifact includes firmware/listing SHA256s, git status summary, watch
config, final MAIN0/MAIN1 EEPROM/RAM hex, trace counters, live probe anchors,
source-map-enriched trace records, UART TX/RX history, and a stimulus log
capturing the explicit `[B1, 0x26, id]` filename query plus `BF/2D`,
`BF/30`, and `BF/4E` reply evidence.

## Current Evidence

- Live recurrence: both MAINs re-corrupted preset-B filename EEPROM byte `0x8F` after a clean surgery baseline and user power-cycle/A-B/menu churn. The byte should be `0x31` and became `0x00`.
- Existing focused sim coverage passes:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py
# 4 passed in 33.17s

.venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
# 19 passed in 1.01s

.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
# RAM bank safety: OK (main-v35, control-v173)
```

- The affected EEPROM address is in the preset-B filename slot, whose legitimate writer is `preset_persist_filename`; this narrows candidate commits but does not prove the root cause.
- The existing `trace_main_ram_transitions` hook is useful but insufficient: MAIN-only, RAM-only, poll-based, and unable to attribute delayed EEPROM commits.

## Phase 1 Work Units

### 1. Add Narrow Chain-Owned Trace Infrastructure

Add `crates/dlcp-sim/src/memtrace.rs` with default-off, range-driven tracing. Keep this first pass focused on the filename recurrence, not a broad simulator API.

Minimum structures:

- `MemSpace`: `DataRam`, `Sfr`, `Eeprom`, `HardwareDma`
- `TraceKind`: `FirmwareDataWrite`, `FirmwareSfrWrite`, `PeripheralSfrSideEffect`, `EepromArm`, `EepromCommit`, `EepromResetDrop`, `HostRamPoke`, `HostEepromSeed`
- `TraceOrigin`: `FirmwareInstruction`, `EepromCommit`, `PeripheralSideEffect`, `HexImageLoad`, `V23SeedMerge`, `PythonPreBootSeed`, `PythonRuntimePoke`
- `TraceRecord`: role, core index, tick, core Tcy, pre-PC, kind, memory space, address, old/new, changed, label, phase, origin, CPU snapshot, optional source-map fields.
- `TraceState`: config, bounded rolling records, `first_match_by_watch`, `first_violation`, `total_count`, `dropped_count`, `overflowed`, `stop_requested`.

Use a single rolling policy. Guard checks must happen before enqueue, and first-match/first-violation records must be retained outside the rolling buffer.

### 2. Define Trace Context Ownership

Implement tracing as Chain-level ownership with per-core context injection:

- `Chain` holds role mapping (`i_ctl`, `i_main0`, `i_main1`) and trace config/state.
- Before `exec::step`, `Chain::execute_core_step` sets context on the core: role, core index, current tick, ticks/Tcy, pre-core Tcy, phase.
- `exec::step_inner` sets `trace_current_pc` after IRQ dispatch declines to vector and before `core.set_pc(pc + byte_count)`.
- The context is cleared after the instruction.
- Do not add trace events to `EventQueue`; tracing must not change execution order.
- Direct PyO3 subroutine helpers that call `dlcp_sim::exec::step` directly, such as HID report helpers, must either set equivalent context or label records as missing Chain context.

Disabled tracing must cost only a cheap flag/Option check in write paths.

### 3. Instrument Firmware RAM/SFR Writes

Hook `write_addr_masked` in `crates/dlcp-sim/src/exec.rs` for firmware file-register writes:

- Capture watched MAIN active filename RAM, selected state bytes, and any explicitly watched SFRs.
- Do not attempt to record every simulator-side SFR mirror mutation in phase 1.
- Keep the existing `trace_main_ram_transitions` method until replacement tests are passing.

Host RAM pokes through PyO3 (`write_reg`, `write_main_reg`) should be classified as host origins if tracing is enabled, but normal tests should seed before starting the recurrence trace.

### 4. Instrument EEPROM Arm, Commit, and Reset Drop

Extend `crates/dlcp-sim/src/peripherals/eeprom.rs`:

- On valid data EEPROM arm in `handle_eecon1_write`, assign `arm_seq` and latch pending trace metadata: arm PC, arm tick, arm core Tcy, EECON1 intended/landed value, EEADR, EEDATA, and old byte at arm.
- Emit `EepromArm` for watched/protected ranges.
- On `tick_tcy` commit, emit `EepromCommit` for watched/protected ranges even if `old == new`; include `changed`.
- Copy arm metadata into every commit record so commit provenance survives rolling-buffer eviction.
- On reset dropping `pending_tcy`, emit `EepromResetDrop` with reset source and `arm_seq`.

Pass a tiny trace context through `Core::advance_cycles` / `Peripherals::tick_tcy` only as far as EEPROM needs. If exact commit tick is implemented, derive it from pending countdown and ticks/Tcy; otherwise document it as instruction-event tick without pretending sub-instruction precision.

### 5. Expose a Minimal Python API

Add only what the tests/scripts need:

- `begin_memory_trace(config: dict) -> None`
- `clear_memory_trace() -> None`
- `memory_trace_records() -> list[dict]`
- `memory_trace_summary() -> dict`
- `memory_trace_first_violation() -> dict | None`

Do not add a broad public API such as general `run_until_memory_write` unless required. Stop/fail guard mode should be Rust-side in the write/commit hook; Python chunk polling is only informational.

### 6. Add Artifact and Scenario Helpers

Add `tests/sim/memory_corruption_helpers.py` and a small operator script, `scripts/memory_corruption_trace.py`.

The helper/script must write:

- `manifest.json`: argv, pytest nodeid/scenario, git status summary, firmware/listing paths and SHA256s, topology, seed, watch config, rerun command.
- `stimulus.jsonl`: ordered phase/event table with ticks and APIs used.
- `trace.jsonl`: enriched trace records.
- `final_state.json`: MAIN0/MAIN1 EEPROM A/B and active RAM hex, selected preset, state bytes.
- `summary.md`: human-readable result and classification.
- `live_evidence.json`: links/hashes for the live probe artifacts above.

Planned commands:

```bash
.venv_ep0/bin/python scripts/memory_corruption_trace.py live-like --topology two-main --seed 20260621 --out artifacts/reanalysis/memory_corruption
.venv_ep0/bin/python scripts/memory_corruption_trace.py summarize artifacts/reanalysis/memory_corruption/<run-dir>
DLCP_MEMTRACE_OUT=artifacts/reanalysis/memory_corruption .venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py::test_v35_v173_two_main_live_like_filename_eeprom_trace
```

### 7. Add Focused Tests

Create `tests/sim/test_memory_corruption_instrumentation.py`.

Required tests:

1. `test_memory_trace_captures_main_eeprom_commit_provenance`
   - Use firmware dirty-service staging to persist a filename byte.
   - Assert `EepromArm` and `EepromCommit` records include arm metadata and source context.

2. `test_v35_v173_baseline_writes_use_firmware_paths`
   - Establish MAIN0 and MAIN1 A/B clean filenames through HID `cmd 0x03` if stable, otherwise firmware dirty-service staging.
   - Trace and label expected baseline writes, then clear trace before recurrence.

3. `test_v35_v173_two_main_live_like_filename_eeprom_trace`
   - Build V1.73 + two V3.5 MAINs, assert `main0 != main1`.
   - Seed/check MAIN0 and MAIN1 independently.
   - Run a fixed stimulus table:
     - POR/connect and idle drain.
     - Navigate to Preset page and verify filename query traffic (`B1/26`, `BF/2D`, `BF/30..`, `BF/4E`).
     - A/B preset toggles.
     - Volume changes.
     - Input/menu navigation.
     - Idle drain.
     - POR/reconnect and final idle drain.
   - Watch MAIN0/MAIN1 EEPROM `0x8F`, active RAM `0x02CC`, filename slots, dirty flags, active flags, and preset job state.
   - Fail with artifact if any protected evidence drops.
   - Report whether corruption is symmetric, PB1-only, PB2-only, broadcast-correlated, addressed-correlated, or not reproduced.

4. Isolation tests:
   - MAIN-only control case, assert `main0 == main1` and no recurrence.
   - CONTROL+single-MAIN control case, assert collapsed MAIN identity explicitly.
   - Direct MAIN RX injection variants for `B0/20/x`, `B1/26/id`, and raw UART bytes to separate serial stimulus from CONTROL UI state.

During recurrence/churn, any firmware-origin write to EEPROM `0x8F` is suspicious unless the phase explicitly performs a filename write. Do not allow a value-specific rule to hide an unauthorized `0x31 -> 0x31` rewrite.

### 8. Static Risk Reporting, Deferred

Do not block phase 1 on a broad static checker expansion.

When added, keep it typed:

- `ERROR`: multiple non-stock owners at same physical RAM byte.
- `HAZARD`: same 8-bit operand across banks requiring BSR proof.
- `INFO`: stock-derived compatibility aliases.
- `NOTE`: numeric coincidences across memory spaces, e.g. EEPROM `0x8F` vs RAM operand `0x8F`.

Call it a static allocation/access-risk report, not a writer proof. Dynamic trace owns writer attribution.

## Validation

Focused:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_memory_corruption_instrumentation.py
.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_filename_eeprom_nul_repro.py
.venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
```

Broader after core/scheduler trace changes:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_compatibility.py tests/sim/test_v173_multi_pb_input_selection.py tests/sim/test_v32_flasher_sim_backend_hid.py
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Review Ledger

- Simplicity/scope: narrowed phase 1 to filename EEPROM/RAM and serial provenance; deferred broad corruption framework.
- Rust architecture: added Chain-owned context, exact pre-PC capture point, no EventQueue trace events, direct PyO3 context handling.
- EEPROM fidelity: require all commit attempts, mandatory arm/commit association, reset-drop records, and host-origin separation.
- MAIN vs CONTROL isolation: added stimulus-axis matrix, MAIN0/MAIN1 independent coverage, and CONTROL-driven definition.
- Static RAM analysis: typed memory spaces, numeric coincidences as notes, and static access-risk wording.
- Test design: require firmware-path baseline writes, fixed stimulus table, two-MAIN assertions, and phase-specific guards.
- Performance/reliability: first-match retention outside rolling buffer, fixed overflow policy, default-off hot-path contract, Rust-side stop/fail.
- Operator/debug usability: added artifact contract, source-map/CPU context, failure template, and exact trace/summarize commands.
