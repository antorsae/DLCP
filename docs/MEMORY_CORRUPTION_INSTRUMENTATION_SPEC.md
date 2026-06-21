# Memory Corruption Instrumentation SPEC

Date: 2026-06-21

Scope: add simulator and test infrastructure that can prove or rule out the current MAIN V3.5 / CONTROL V1.73 filename EEPROM corruption path, then reuse the same machinery for broader RAM/EEPROM corruption hunting.

## Problem

The live rig reproduced persistent preset filename corruption after both MAINs were repaired to a clean baseline:

- Firmware under test: CONTROL V1.73 with MAIN V3.5 rev `0x008F`.
- Baseline: both MAIN EEPROM filename slots A/B were written through normal app paths and verified clean repeatedly.
- User then did a full power cycle, A/B toggles, volume changes, and menu navigation.
- Read-only post-cycle probe found both MAINs active on clean preset A, while persistent preset B was bad on both units:
  - expected B slot: `LX521.4 22MG10F-v7`
  - observed B slot: `LX521.4 22MG\x000F-v7`
  - affected byte: EEPROM address `0x8F` (`preset_filename_eeprom_b 0x83 + offset 0x0C`)
  - expected `0x31` (`'1'`), observed `0x00`

The old V3.5 filename NUL root cause was the pre-`0x0085` high-IRQ vector alignment bug. That bug is now guarded, and the current live image reports rev `0x008F`. This SPEC therefore treats the current recurrence as unproven until the writer is captured.

Live evidence anchors:

- `artifacts/probes/live_filename_eeprom_surgery_20260621.json`
- `artifacts/probes/live_filename_eeprom_left_b_repair2_20260621.json`
- `artifacts/probes/live_filename_eeprom_post_powercycle_check_20260621.json`
- RIGHT after recurrence: `DevSrvsID:4296310231`, EEPROM B `4c583532312e342032324d470030462d7637ffffffffffffffffffffffff`
- LEFT after recurrence: `DevSrvsID:4296310320`, EEPROM B same bad bytes

## 2026-06-21 Simulator Finding

The first instrumented V1.73/V3.5 live-like run reproduced the same byte
corruption in sim.  The first protected write was:

- role: `MAIN0`
- kind: `EepromArm`
- stimulus: first menu `RIGHT` press after preset-B IR, volume-down IR, and idle
- EEPROM address: `0x8F` (`preset_filename_eeprom_b + 0x0C`)
- old/new: `0x31 -> 0x00`
- PC: `0x3984` (`nvm_unlock_and_set_wr`, `bsf EECON1.WR`)
- EEPROM arm metadata: `EEADR=0x8F`, `EEDATA=0x00`
- stack: `0x3E30 -> 0x3D28 -> 0x20A6 -> 0x210E -> 0x396A`

Mapped through `src/dlcp_fw/asm/dlcp_main_v35.lst`, that stack is:

- `run_main_foreground_loop`
- `run_main_service_pass`, returning after `persist_dirty_runtime_state_to_eeprom`
- `persist_dirty_runtime_state_to_eeprom`, returning after block-0 `eeprom_persist_block_walker`
- `eeprom_persist_block_walker` record tail
- `eeprom_write_blocking`

Therefore this recurrence is MAIN-side firmware corruption, not CONTROL and not
USB/host direct EEPROM writing.  The root cause is the V3.5 runtime-state EEPROM
table walker keeping its packed-record cursor in `TBLPTR` across calls to
`eeprom_write_byte_if_changed`.  That helper routes through the chain-copy
trampoline, which also uses/clobbers `TBLPTR`; after the first changed block-0
record, the walker resumes from a corrupted table cursor and can consume bogus
EEPROM offset/data pairs, including `0x8F <- 0x00` inside preset-B filename
EEPROM.

Artifact with full trace and final state:

- `artifacts/reanalysis/memory_corruption/20260621T145830Z_v173-v35-live-like_00350173/`

That artifact includes `manifest.json`, `stimulus.jsonl`, `trace.jsonl`,
`final_state.json`, `summary.md`, `live_evidence.json`,
`uart_tx_records.jsonl`, and `uart_rx_records.jsonl`.  `trace.jsonl` records
include listing-backed `source_map` fields for PC context.  The stimulus log
captures the explicit filename-query stimulus `[0xB1, 0x26, 0x01]` and the
observed reply pairs including `BF/2D`, `BF/30`, and `BF/4E` before the final
POR clears UART history.

## Phase 1 Focus

Phase 1 is intentionally narrow:

- MAIN EEPROM filename slots A/B (`0x60..0x7D`, `0x83..0xA0`) on MAIN0 and MAIN1.
- MAIN active filename RAM (`0x02C0..0x02DD`) on MAIN0 and MAIN1.
- MAIN state bytes needed to interpret filename writes: `active_flags`, `filename_dirty_flags`, `event_flags`, `preset_job_state`, `preset_job_target`.
- EEPROM arm/commit provenance.
- UART/control stimulus provenance around the write.

Deferred until after the writer is proven: broad CONTROL EEPROM hunting, full RX/TX ring protection, diagnostics-cache guards, exploratory oracle integration, and static protected-region reports beyond what is needed for this bug.

Terminology: "CONTROL-driven" means MAIN corruption that only occurs when CONTROL-originated UART/button/IR/host traffic is present. CONTROL cannot directly write MAIN EEPROM; it can only provoke MAIN code paths.

## Requirements

1. Capture first-writer provenance for watched bytes.
   - Core index and logical role (`CONTROL`, `MAIN0`, `MAIN1`) from a Chain-level role map.
   - Universal tick, core Tcy, and pre-instruction PC.
   - Trace kind: `FirmwareDataWrite`, `FirmwareSfrWrite`, `PeripheralSfrSideEffect`, `EepromArm`, `EepromCommit`, `EepromResetDrop`, `HostRamPoke`, `HostEepromSeed`.
   - Typed memory space: `DataRam`, `Sfr`, `Eeprom`, `HardwareDma`. Overlap/collision checks must never conflate different memory spaces.
   - Address, old byte, new byte, label, phase, and origin.
   - CPU context for firmware writes: WREG, STATUS, BSR, FSR0/1/2, and stack top where available.
   - Source-map context in artifacts: asm path, listing path, listing line, nearest symbol, symbol offset, opcode words, mnemonic, access mode, and effective address.

2. Preserve evidence even under trace overflow.
   - Guard checks happen before enqueue.
   - Keep `first_match_by_watch` and `first_violation` outside the rolling buffer.
   - Use one fixed rolling policy and expose `total_count`, `dropped_count`, and `overflowed`.
   - A no-repro artifact is invalid if protected-range evidence was dropped.

3. Trace context ownership must be explicit.
   - Chain owns the role map and sets a tiny per-step context before `exec::step`.
   - The executor sets `trace_current_pc` after IRQ dispatch decides no vector is being taken and before advancing PC for the decoded instruction.
   - The context is cleared after the instruction.
   - No trace events may be scheduled in `EventQueue`, and tracing must not change scheduler ordering.
   - Direct PyO3 subroutine paths must set equivalent context or mark records as missing Chain context.

4. EEPROM is first-class.
   - Log every watched/protected EEPROM arm and commit attempt, including `old == new`, with `changed: bool`.
   - The EEPROM pending state must latch `arm_seq`, arm PC, arm tick, arm core Tcy, EECON1 intended/landed value, EEADR, EEDATA, and old byte at arm.
   - `EepromCommit` must include copied arm metadata even if the separate arm record was evicted.
   - POR/reset that drops an in-flight EEPROM write must emit `EepromResetDrop` with the same `arm_seq`.
   - Host seeds/pokes are distinct from firmware writes. Normal corruption tests should seed before tracing or record host origins (`HexImageLoad`, `V23SeedMerge`, `PythonPreBootSeed`, `PythonRuntimePoke`) and exclude them from firmware-writer verdicts.

5. Reproduce or strongly bound the live recurrence.
   - Build a two-MAIN V1.73 + V3.5 chain and assert `main0 != main1`.
   - Establish clean A/B baselines for MAIN0 and MAIN1 through firmware write paths: HID `cmd 0x03` where stable, otherwise the existing firmware dirty-service staging path. Direct EEPROM seeding may only be used for setup control tests, not the primary recurrence test.
   - Clear the trace after baseline creation and before recurrence stimuli.
   - Run a fixed stimulus table that includes POR/connect, Preset page filename query traffic (`B1/26`, `BF/2D`, `BF/30..`, `BF/4E`), A/B preset toggles, volume changes, input/menu navigation, idle drains, and POR/reconnect.
   - Record CONTROL TX/RX and MAIN RX frame history immediately preceding every watched write.
   - Guard MAIN0 and MAIN1 EEPROM `0x8F` and RAM `0x02CC`. During recurrence/churn, any firmware-origin write to EEPROM `0x8F` is suspicious unless the phase explicitly performs a filename write.
   - Classify failures as one of: active RAM already corrupt, EEPROM arm data corrupt, delayed EEPROM commit corrupt, persist source cursor/loop corrupt, or serial stimulus only.

6. Provide a replayable artifact.
   - Artifact directory: `artifacts/reanalysis/memory_corruption/<timestamp>_<scenario>_<seed>/`.
   - Required files: `manifest.json`, `stimulus.jsonl`, `trace.jsonl`, `final_state.json`, `summary.md`, `live_evidence.json`.
   - Include command argv, pytest nodeid or script scenario, git status summary, firmware hex paths and SHA256s, listing paths and SHA256s, topology, seed, watch/protect config, trace counters, rerun command, and final MAIN0/MAIN1 EEPROM/RAM hex.
   - Guard failure messages must follow this shape:
     `MEMTRACE_GUARD failed: MAIN0 EEPROM[0x8F preset_B_filename+0x0C] 0x31->0x00 kind=EepromCommit record=173 tick=... armed_by pc=0x... symbol=... stimulus_event=42 phase=... rule=... reason=... artifact=... dropped=0`

7. Keep instrumentation default-off.
   - Disabled hot path is a single cheap flag/Option check, no allocation, and no range search.
   - Stop/fail guard mode records the offending write immediately and stops after the current instruction unless a later implementation adds a separate non-fatal stop result.

## Existing Coverage

- `tests/sim/test_v35_filename_eeprom_nul_repro.py` proves MAIN0 filename persistence in several focused paths and guards the high-IRQ vector alignment fix, but it is MAIN0-centric and does not prove the current two-MAIN live recurrence.
- `tests/sim/test_ram_bank_safety.py` and `scripts/check_ram_access_safety.py --target main-v35 --target control-v173` pass today.
- The static RAM checker catches alias/BSR mistakes but cannot prove indirect FSR writer ownership or hardware/DMA writes. Dynamic trace owns true writer attribution.

## Acceptance

- A focused sim test or script reproduces the bad byte, or emits a valid no-repro artifact with complete watched-range write provenance and no protected evidence loss.
- MAIN-only, CONTROL+single-MAIN, and CONTROL+two-MAIN variants are distinguished, with topology identity asserted.
- Two-MAIN tests seed, watch, and assert MAIN0 and MAIN1 independently.
- Failure output identifies first offending writer by role, memory space, address, PC/source-map, old/new value, phase, preceding stimulus, and artifact path.
- Static RAM safety remains green:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
```
