# V2.8 Delayed Switch Issue and Remediation Plan

Last updated: 2026-04-11
Scope: MAIN `V2.8` delayed preset switching with CONTROL `V1.63b`, especially on a wire chain with two MAIN units.

## Summary

Real hardware reported two related failures after a few remote-driven preset/profile switches:

- CONTROL and MAIN can desynchronize. CONTROL continues issuing `0x03` commands such as standby and mute, but one or more MAIN units stop reacting.
- MAIN can go silent after a preset/profile switch and remain effectively muted or otherwise unresponsive.

The new two-MAIN wire repros in `tests/sim/test_v28_wire_delayed_switch_repros.py` reproduce the same class of failure in simulation:

- rapid `F1/F2` switching can leave `CONTROL` and `MAIN0` on preset `B` while `MAIN1` remains on `A`
- interleaving `0x03` mute during the delayed switch shows the same split-brain outcome
- standby/reconnect and reconnect/full-sync soak cases continue to expose delayed-switch desynchronization
- injecting a `0x381C` START/STOP fault during the delayed switch can reconnect the chain while preset state is still wrong

These repros are currently marked strict `xfail` for `V2.8` and are intended to flip to passing for the next source-level MAIN release.

## Problem Statement

`V2.8` added a delayed preset helper so preset switching happens muted and after a `150 ms` hold. That change improved the audible switch artifact, but it kept the entire operation synchronous and inline with the UART parser.

That is the core design problem.

When `cmd=0x20` arrives:

- MAIN parses the frame in the UART service path
- MAIN may force mute immediately
- MAIN blocks for `150 ms`
- MAIN applies the full preset table in one call
- only after that does MAIN return to normal command service

While that work runs, the UART RX ISR still enqueues bytes into the native ring. The ring has wraparound logic, but no full/overflow detection. If the parser is held too long, later bytes can overwrite unread earlier bytes or be consumed after parser state has drifted.

## Evidence

### 1. `cmd=0x20` runs inline in the UART parser

Relevant sites:

- `src/dlcp_fw/patch/build_main_presets_ab.py`
- `src/dlcp_fw/asm/dlcp_main_v31.asm`

The `V2.8` binary patch helper at `preset_select_delayed` does the whole job in one call:

- compare requested preset
- optionally persist dirty filename
- optionally force mute
- wait `150 ms`
- switch bank
- apply preset table
- optionally unmute

The source equivalent in `V3.1` still follows the same synchronous structure:

- `main_uart_service_1be6`
- `preset_select_handler`
- `preset_select_delayed`
- `main_core_service_4574`

This means preset switching is still parser-blocking, even in the source rewrite.

### 2. Preset apply is monolithic

`main_core_service_4574` iterates the preset table and repeatedly calls `main_i2c_service_381c`.

That means one preset switch is not one small transaction. It is a long sequence of back-to-back I2C writes, all inside the same parser-triggered call path.

### 3. The low-level MSSP helper blocks on raw START/STOP waits

`main_i2c_service_381c` uses raw:

- `SSPCON2.SEN` wait loops
- `SSPCON2.PEN` wait loops

with no per-record success/failure return and no preset-level rollback/abort path.

If START or STOP stalls, or if the chain is partially applied before recovery, MAIN can be left muted or half-updated with no explicit state machine to recover cleanly.

### 4. The RX ring has no full/overflow protection

The UART RX ISR stores each received byte at `rx_ring_wr`, increments it, wraps at `0xC0`, and continues.

There is no:

- `next_wr == rd` check
- overflow flag
- parser reset on overflow
- telemetry for dropped bytes

That makes long parser stalls especially dangerous under rapid preset toggles and follow-up `0x03` commands.

### 5. CONTROL only reasserts desired preset; it does not confirm convergence

`V1.63b` sends bounded preset retries and has reconnect/parser hardening, but it still assumes MAIN eventually converges after receiving `cmd=0x20`.

Today there is no explicit "preset apply committed" handshake from MAIN back to CONTROL. CONTROL can therefore show preset `B` while one or more MAIN units are still logically or effectively on preset `A`.

## Root Cause Assessment

The most likely root causes, in order:

1. Parser starvation during delayed switch/apply.
2. RX ring overwrite or parser desynchronization while `cmd=0x20` is still running.
3. Partial preset apply or stuck MSSP START/STOP during `main_i2c_service_381c`.
4. Mute/standby state being entangled with the switch helper rather than managed as independent desired state.
5. CONTROL lacking an explicit convergence check beyond bounded retry bursts.

This is not primarily a "retry count too small" problem. It is a "long-running work happens in the wrong execution context" problem.

## Recommended Fix

### Release strategy

Do not try to solve this with another binary patch on `V2.8`.

The fix needs:

- new runtime state
- chunked work across multiple passes
- explicit failure handling
- possibly a richer MAIN->CONTROL status contract

That is source-level work. The recommended target is a new source release after `V3.1`, effectively a `V3.2` delayed-switch hardening release.

### MAIN-side architecture change

Replace synchronous delayed switching with an asynchronous preset job state machine.

### Required state

Add explicit fields for:

- `current_preset`
- `target_preset`
- `preset_job_state`
- `preset_job_deadline` or equivalent timer countdown
- `preset_apply_index`
- `preset_forced_mute`
- `preset_fault_latched`
- `uart_rx_overflow_latched`

Do not use the single current preset bit as both requested state and committed state.

### Parser behavior

On `cmd=0x20`:

- validate the requested preset
- if it matches the already-committed preset and no job is active: return
- otherwise store it in `target_preset`
- mark `preset_job_pending`
- return immediately

No blocking delay, no mute write, no table apply from the UART parser.

### Preset job states

A robust minimal state machine:

1. `IDLE`
2. `PERSIST_FILENAME_IF_DIRTY`
3. `FORCE_MUTE_IF_NEEDED`
4. `HOLD_DELAY`
5. `APPLY_TABLE_ENTRY`
6. `LOAD_FILENAME_SLOT`
7. `COMMIT_PRESET`
8. `RESTORE_VOLUME_OR_MUTE_STATE`
9. `FAULT`

Important rules:

- `APPLY_TABLE_ENTRY` should process one table record per main-loop pass, not the entire preset table.
- `COMMIT_PRESET` must happen only after the table apply completes successfully.
- `FORCE_MUTE_IF_NEEDED` must remember whether mute was already set by the user.
- `RESTORE_VOLUME_OR_MUTE_STATE` must not unmute if the user requested mute while the job was active.

### Command priority rules

Not all commands are equal while a preset job is active.

Recommended policy:

- `0x03 standby on/off` has higher priority than the preset job.
- `0x03 mute on/off` updates desired end state immediately.
- a new `0x20` preset request coalesces with the existing job and replaces the target preset.

If standby arrives during `HOLD_DELAY` or `APPLY_TABLE_ENTRY`:

- suspend or cancel the preset job
- execute standby cleanly
- after wake/reconnect, compare `current_preset` and `target_preset`
- requeue the preset job if needed

That avoids the current "helper owns the machine until it is done" failure mode.

### I2C/MSSP hardening

Refactor the preset apply path so low-level I2C failures become first-class events.

Required changes:

- make `main_i2c_service_381c` return success/failure for each record
- add bounded START and STOP waits
- on timeout, perform MSSP reset and bus-clear/ping recovery as appropriate
- retry a single record a bounded number of times
- if still failing, enter `FAULT` state instead of pretending the preset committed

Keep the stock-style TAS3108 coefficient START/STOP waits for coeff writes. The source already documents that a bounded replacement regressed real hardware even when simulation passed.

### UART hardening

Add explicit RX ring overflow handling in the ISR.

When `next_wr == rx_ring_rd`:

- set an overflow flag or counter
- discard the newest byte or flush the queue in a controlled way
- reset parser state
- surface the fault to higher layers

Silent overwrite is not robust enough for a long-running delayed-switch path.

### CONTROL-side changes

`V1.63b` reconnect handling is useful and should remain:

- robust parser wrapper
- periodic UART/parser re-prime
- reconnect exit wake frame
- bounded preset retry bursts

However, CONTROL should stop relying only on hope plus retries.

Recommended improvement:

- MAIN should expose "preset commit complete" and "preset fault" status
- CONTROL should compare desired preset vs confirmed MAIN preset
- if they differ after reconnect or after a fault-clear event, CONTROL should trigger a targeted resync

If protocol surface must stay minimal, a weaker fallback is acceptable:

- reuse existing status traffic to expose committed preset bit and fault flags
- trigger an immediate full-sync whenever MAIN reports preset-fault clear or preset mismatch

## Suggested Development Plan

### Phase 1: design and state allocation

Deliverables:

- reserve RAM for preset-job state
- define the job-state enum and fault flags
- document the exact ownership of mute, standby, and preset state
- identify the main-loop service slot that will advance the preset job

Exit criteria:

- no parser path still performs blocking preset work
- implementation plan reviewed against current symbol map and free RAM

### Phase 2: asynchronous preset job

Deliverables:

- replace inline `preset_select_delayed` behavior with queue-only parser logic
- implement the main-loop preset job state machine
- coalesce repeated `F1/F2`
- separate user mute from forced switch mute

Exit criteria:

- the new two-MAIN delayed-switch repros can be run against the development build
- rapid `F1/F2` no longer leaves `MAIN1` stuck on the wrong preset

### Phase 3: chunked table apply and MSSP failure handling

Deliverables:

- split preset apply into bounded per-step work
- add per-record success/failure return from the apply helper
- add bounded START/STOP waits, MSSP reset, and retry
- latch preset fault if apply cannot complete cleanly

Exit criteria:

- START/STOP injected faults fail deterministically
- no commit happens unless the entire preset apply succeeds

### Phase 4: CONTROL convergence logic

Deliverables:

- add MAIN status reporting for preset commit/fault
- teach CONTROL resync logic to react to explicit preset mismatch rather than only retry blindly
- ensure reconnect path reasserts wake/preset in the right order

Exit criteria:

- reconnect/full-sync soak converges to the same preset on CONTROL, MAIN0, and MAIN1
- a transient MAIN-side apply fault does not leave CONTROL permanently ahead of MAIN

### Phase 5: validation and release hardening

Deliverables:

- flip the new `V2.8` repro tests from `xfail` to pass for the new source build
- run existing `V3.1 + V1.63b` robustness suite
- run hardware validation with repeated remote switching and standby/reconnect cycles

Exit criteria:

- no desynchronization across CONTROL, MAIN0, and MAIN1
- no mute-stuck or silent-after-switch failures across the test matrix
- release candidate documented with exact differences from `V3.1`

### Required Test Gates

The following scenarios should be mandatory for the new source release:

- `tests/sim/test_v28_wire_delayed_switch_repros.py`
  Expected outcome:
  all cases flip from `xfail` to pass, with no `WAITING`, no split-brain preset state, and no permanently muted or unresponsive MAIN.
  Specific checks:
  rapid `F1/F2` must leave CONTROL, `MAIN0`, and `MAIN1` on the last requested preset, and follow-up mute/unmute must affect all MAINs.
  interleaved mute during delayed switch must converge to the requested preset while preserving the requested mute state across all MAINs.
  interleaved standby during delayed switch must enter standby cleanly, reconnect cleanly, and wake with all MAINs active and on the requested preset.
  `0x381C` START/STOP fault during delayed switch must not hang or silently miscommit. The system must either recover to the requested preset within bounded time or latch a visible fault without claiming the new preset committed.
  reconnect/full-sync soak must complete repeated preset changes plus standby/reconnect cycles without CONTROL drifting ahead of any MAIN.
- `tests/sim/test_control_gpsim_ir_preset_switch.py`
  Expected outcome:
  `F1/F2` remain idempotent, stay out of `WAITING`, and the final requested preset reaches MAIN over the wire path.
- `tests/sim/test_control_main_powercycle_sync.py`
  Expected outcome:
  boot and reconnect still use bounded retry bursts, those bursts terminate, and CONTROL resynchronizes MAIN to the persisted desired preset without perpetual preset spam.
- `tests/sim/test_v31_v163b_robustness.py`
  Expected outcome:
  existing `V3.1 + V1.63b` robustness behavior remains intact, including bus-clear recovery, DSP ping fault latching, fault-status reporting, and bounded MSSP/PEN recovery.
- targeted hardware loop validation after the simulation gate is green
  Expected outcome:
  repeated real-hardware remote switching, mute toggles, and standby/reconnect cycles produce no audible stuck-mute state, no CONTROL/MAIN desync, and no requirement for manual recovery.

### Immediate Practical Recommendation

If the goal is a robust production build, the shortest path is:

1. branch from the source MAIN line, not from `V2.8`
2. implement asynchronous `cmd=0x20` handling first
3. make preset apply chunked and failure-aware
4. keep CONTROL reconnect hardening, then add explicit preset convergence
5. use the new two-MAIN wire repros as the acceptance gate for the fix

That addresses the real failure mode instead of only increasing delays or retry counts.
