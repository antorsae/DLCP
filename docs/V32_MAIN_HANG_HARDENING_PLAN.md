# V3.2 MAIN Hang Hardening Plan

Last updated: 2026-04-15
Scope: MAIN `V3.2` robustness against control-path hangs on two-MAIN chain (`CONTROL <> PB1 <> PB2`)

## Problem Statement

Field symptom pattern:

- CONTROL keeps sending `STDBY` / `MUTE`, but one or both MAINs stop reacting.
- Audio may continue as if commands were never received.
- Power-cycling PB1 can produce a large pop, consistent with a non-graceful shutdown state.

In the current architecture, PB1 software performs forwarding to PB2 in `main_uart_service_1be6`.
If PB1 parser/service gets wedged, downstream control traffic can stall.

## Objectives

1. MAIN must not block indefinitely in runtime service paths.
2. If MAIN cannot make progress, it must fail safe (mute/standby) and recover automatically.
3. PB2 must not remain indefinitely active if PB1/upstream control is lost.
4. Regressions must be gated in simulation/wire tests and on live hardware.

## Hardening Workstreams

## 1) Eliminate Remaining Unbounded Waits

Current gap: only async preset APPLY path has bounded I2C waits in V3.2; legacy `main_i2c_service_381c` call sites still exist.

Implementation:

- Add bounded wait wrappers for all runtime I2C transactions (not only delayed-switch APPLY).
- On timeout: `mssp_hard_reset -> i2c_bus_clear -> dsp_ping`, then retry boundedly.
- If retries exceed threshold, trigger fail-safe path (see Workstream 5).

Primary code areas:

- `main_i2c_service_381c` and call sites in `dlcp_main_v32.asm`
- `wait_sen_bounded`, `wait_pen_bounded`

Tests:

- Extend `tests/sim/test_v31_v163b_robustness.py` V3.2 sections with non-preset I2C fault injection.
- Add targeted STOP/SEN/PEN timeout tests that prove return to main loop within bounded time.

## 2) UART Parser/Forwarder Liveness Hardening

Implementation:

- Add frame assembly timeout reset (`route/cmd/data` parser must not wait forever).
- Keep OERR/FERR recovery strict and idempotent.
- Preserve "drop-oldest + parser-resync" on RX overflow; never full-ring destructive flush.
- Add parser-forward watchdog counter for repeated resync loops.

Primary code area:

- `main_uart_service_1be6`

Tests:

- Add wire test where malformed/incomplete frame burst is injected during command traffic; assert parser recovers and later `0x03` commands still apply.
- Add long soak where forwarding remains alive under repeated preset + mute + standby bursts.

## 3) Strict Preemption and Target-State Reconciliation

Implementation:

- Keep `0x03` standby/mute as top-priority target-state updates.
- Ensure delayed-switch/preset jobs never override final user-intent mute/active state.
- Reconcile continuously toward desired state instead of one-shot command assumptions.

Primary code areas:

- `cmd03_*` handlers
- `preset_job_*` state machine (`PENDING/HOLDING/APPLY/COMMIT/CANCEL`)
- `standby_event_dispatch`

Tests:

- Continue using `tests/sim/test_v28_wire_delayed_switch_repros.py` as acceptance for interleaved `0x20` + `0x03`.
- Add assertions for "last command wins" under burst interleave.

## 4) PB2 Upstream-Loss Fail-Safe

Rationale: if PB1 wedges, PB2 may stop receiving control frames.

Implementation:

- Add upstream-link heartbeat timeout on MAINs (especially PB2 role).
- If no valid upstream frame/status for `T_upstream_timeout`, enter safe mute or standby path.
- Make timeout and policy explicit constants (no hidden magic values).

Tests:

- New wire-chain test: stall PB1 forwarding; assert PB2 transitions to safe state within bounded window.
- Hardware test: unplug PB1<>PB2 serial link during active playback; assert PB2 safe-state behavior.

## 5) Fail-Safe Escalation Path ("panic-safe")

Implementation:

- Add escalation ladder:
  1. bounded retry/recover,
  2. force mute + set degraded flag,
  3. controlled soft reset when progress cannot be restored.
- Ensure mute is asserted before reset attempt.

Tests:

- Fault-injection tests proving escalation level transitions and no infinite busy-loop.
- Verify post-reset control-path recovery without manual power cycle.

## 6) Watchdog Integration (System-Level)

Implementation:

- Enable WDT policy for MAIN.
- Clear WDT only from healthy main-loop checkpoint (never from deep workers).
- Persist reset-cause counters (WDT/BOR/etc.) for diagnostics.

Notes:

- Requires careful config-bit and timing validation; treat as a dedicated phase.

Tests:

- Static checks for WDT configuration and `CLRWDT` placement.
- Hardware soak with induced stalls to confirm auto-recovery behavior.

## 7) Observability and Diagnostics

Implementation:

- Add counters for:
  - I2C SEN/PEN timeouts
  - RX overflow and parser resync
  - upstream-link timeout events
  - panic-safe resets
- Surface counters to CONTROL diagnostics path (or documented probe command path).

Tests:

- Counter increment/reset semantics in sim tests.
- Hardware readback checks after stress runs.

## Test Strategy and Gate Policy

Classify required gates:

- **wire/gpsim required**: deterministic protocol/fault-path liveness tests.
- **hardware required for release candidate**: standby/mute/preset/reconnect soak and upstream-loss safe-state behavior.

Minimum release gate:

1. `tests/sim/test_v28_wire_delayed_switch_repros.py` delayed-switch + interleaved `0x03` cases pass for V3.2 target line.
2. V3.2 robustness tests (I2C bounded recovery + parser liveness) pass with no new xfails.
3. `tests/hardware/test_live_state_transitions.py --run-hardware` targeted suite passes on two-MAIN rig.

## Recommended Phasing

Phase 1 (immediate): Workstreams 1, 2, 3
Phase 2 (chain safety): Workstream 4
Phase 3 (recovery depth): Workstreams 5, 6
Phase 4 (operations): Workstream 7 + release soak

## Definition of Done

- No known unbounded runtime wait paths remain in MAIN service code.
- PB1 wedge does not leave PB2 indefinitely active without a safe-state transition.
- Long-run command responsiveness (`STDBY`, `MUTE`, preset) remains intact under stress.
- Failures are diagnosable from counters, not only inferred from audible behavior.
