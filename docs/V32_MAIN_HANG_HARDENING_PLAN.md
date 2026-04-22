# V3.2 MAIN Hang Hardening Plan

Last updated: 2026-04-21
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

## 3b) Standby/Wake Reconnect Hardening (current canonical pair)

Added 2026-04-21 after a field-reproducible wedge: after the operator
pressed `STDBY` on CONTROL and then `WAKE`, CONTROL was locked on
`WAITING FOR DLCP` indefinitely with both MAINs still alive on USB.
Real-HW probe (scripts/dlcp_probe_chain_link.py) confirmed the MAINs
were healthy (gate open, no faults, audio would resume if queried) --
the wedge was on the CONTROL-side sentinel-clear protocol.

The original MAIN-only diagnosis is now stale for the current source.
As of the 2026-04-22 real-hardware run on the canonical pair
(`V3.2 / rev 0x38` + `V1.71 / rev 0x04`), both MAINs were already awake,
healthy, gate-open, and visible on USB while CONTROL still showed
`WAITING FOR DLCP`.  That disproves the older "MAIN never finished wake"
explanation for the current revision.  See
`docs/analysis/V171_V32_STDBY_WAKE_WAITING_REAL_HW_2026-04-22.md`.

Current root cause is CONTROL-side reconnect fragility:

- MAIN wake now does re-advertise state during `adc_boot_gate`
  (`cmd_dispatch_gated` + `send_status_burst`), so the downstream side
  is no longer the primary blocker.
- CONTROL still performs RC5 IR decode in the ISR hot path.  That
  blocks UART TX/RX servicing for ~7-10 ms exactly when the wake
  command, reconnect poll, and MAIN status burst collide.
- The critical CONTROL 3-byte frame senders
  (`poll_frame_send`, `serial_tx_routed_frame` / `standby_wake_broadcast`,
  and the V1.71 explicit wake/standby IR helpers) still ignore
  `STATUS.C` from `tx_byte_enqueue`.  Under Layer-1 bounded-TX
  semantics, that means silent byte-drop on saturation rather than an
  atomic retry or abort.

Net effect: MAIN can already be awake and passing audio while CONTROL
remains stranded on its reconnect screen because CONTROL lost or
phase-shifted the reconnect traffic itself.

Interim mitigation landed 2026-04-21 on V1.71 CONTROL side:
operator can press `RIGHT` or `LEFT` after a ~10 s grace to trigger
a PIC18 soft `RESET` and re-run the full CONTROL cold-init +
full-sync-burst.  See `docs/V171_RELEASE.md` §"WAITING FOR DLCP
operator recovery".  This is a UX escape hatch, not a root-cause fix.

Implementation (CONTROL-side priority, MAIN-side audit secondary):

- Move or defer the RC5 decode out of the ISR-critical wake/reconnect
  window so UART TX/RX service is not starved during the first wake
  exchange.
- Make wake/poll frame emission atomic: check `STATUS.C` after every
  `tx_byte_enqueue` in the standby/wake and reconnect senders, then
  retry or abort cleanly instead of silently dropping bytes.
- Keep the MAIN-side wake-time `send_status_burst` path, but treat it as
  necessary-not-sufficient; the remaining field wedge is no longer
  solved by MAIN-only changes.
- Audit other CONTROL best-effort frame senders that still ignore
  bounded-TX saturation.

Primary code areas:

- CONTROL:
  - `ir_rc5_decode`
  - `tx_byte_enqueue`
  - `poll_frame_send`
  - `serial_tx_routed_frame`
  - `standby_wake_broadcast`
  - `v171_send_wake_cmd_frame`
- MAIN:
  - `adc_boot_gate`
  - `send_status_burst`
  - `cmd04_status_response`

Tests:

- Add an end-to-end wake test that drives the real CONTROL wake path
  (`STDBY` / `WAKE`, not only source-level contracts) and asserts that
  CONTROL leaves `WAITING FOR DLCP` without requiring the operator
  soft-reset escape while both MAINs are already healthy.
- Add a focused CONTROL test for the current Layer-1 mismatch: prove
  that the wake/poll senders either emit all 3 bytes or explicitly
  surface saturation instead of silently dropping partial frames.
- Live-hardware soak: 100× STDBY+WAKE cycles.  Acceptance: zero
  lockups into the WAITING-loop grace-reset window (i.e., zero
  operator-visible `WAITING FOR DLCP` > 5 s after wake).

Release-gate note: with the V1.71 grace-reset in place this hang is
operator-recoverable without a power cycle, so it's no longer a
blocker for V3.2 shipping.  Remaining work is to eliminate the
recovery requirement entirely on the next canonical pair revision,
with CONTROL reconnect hardening as the lead item.

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
