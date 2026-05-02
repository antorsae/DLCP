# Task #45 — V1.71+V3.2 STDBY/wake asymmetric-recovery field bug

**Status:** root cause not yet determined. 3 ranked hypotheses (codex investigation 2026-05-02) with rust-sim reproduction paths and HW confirm/deny tests for each.
**Hardware session:** 2026-04-27 (V1.71 CONTROL + 2× V3.2 MAIN).
**Existing sim coverage:** symptom-equivalent end-state only (`right_main_held_in_reset_control_stuck_in_waiting`, `control_in_waiting_state_does_not_emit_stdby_frame_on_button_press`, `v32_main_runtime_counters_baseline_and_post_stdby_cycle`, `v32_main_parser_driven_stdby_wake_stdby_cycle_after_settle`).

## 1. Field-observation timeline (2026-04-27)

| Time | Event | Observation |
| ---- | ----- | ----------- |
| T0 | Cold POR | Both MAINs HEALTHY; cmd 0x44 returns `I0 D0 S0 B0 R0 A0 P0` from each. LCD `Volume:-50.0dB A / Auto Detect`. |
| T1 | Operator presses panel STBY | Both MAINs power-cut. USB enum empty. LCD black. |
| T2 | Operator presses panel STBY again to wake | **ONLY LEFT MAIN re-enumerated.** LEFT cmd 0x44: `S1 B1` (post-wake increments). RIGHT MAIN absent. CONTROL LCD: `Waiting for DLCP`. |
| T3 | ~5 min idle, USB re-poll every 3s for 15s | RIGHT never came back. LEFT path stable. |
| T4 | Operator presses panel STBY again | NO RESPONSE from CONTROL. LCD still WAITING. LEFT cmd 0x44 still `S1 B1` — `S` did NOT increment, so CONTROL never propagated a new STDBY frame onto the wire. |
| T5 | Hard mains-side power cycle | Both MAINs back; HEALTHY POR; LCD `Volume:-50.0dB A`. |

Source: `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §6.

## 2. Three ranked root-cause hypotheses

### H1 (HIGH confidence) — MAIN1 stuck in `adc_boot_gate` due to per-board PSU/MCLR/AN0 wake conditions

**Hypothesis**: CONTROL did broadcast wake. MAIN0 received it, `wake_request_handler` raised the event, `standby_event_dispatch` took the bring-up branch, `diag_b → 1`, the bring-up path called `adc_boot_gate` which sampled AN0 until rail-rise threshold `>= 0x0236`, returned, and USB rearmed. MAIN1 received the same wake byte stream but its `adc_boot_gate` never returned because AN0 (rail-sense input) never crossed the threshold — meaning RIGHT MAIN's rail/MCLR/inrush behavior on this specific power cycle didn't bring the board up.

**Why it fits the timeline**:
- Single broadcast wake reaches both MAINs; only one completes bring-up because rail-rise / MCLR-release / inrush / local board wake timing is per-board.
- `adc_boot_gate` has no timeout — it busy-waits for the AN0 sample to cross threshold. If the rail never rises (PSU droop, MCLR held externally, BOR triggered, etc.), MAIN1's CPU stays in that loop indefinitely.
- USB enumeration only happens after `adc_boot_gate` returns + DSP/coeff-write bring-up completes. Stuck MAIN1 → no USB.
- Hard mains-side power cycle resets the MAIN's wake-state machine entirely → both rails come up cleanly → both MAINs boot.

**Source citations**:
- `wake_request_handler` at `src/dlcp_fw/asm/dlcp_main_v32.asm:1881`
- `standby_request_handler` at `src/dlcp_fw/asm/dlcp_main_v32.asm:1906`
- `adc_boot_gate` at `src/dlcp_fw/asm/dlcp_main_v32.asm:4008` (rail-rise sample loop)
- `standby_event_dispatch` increment paths at `src/dlcp_fw/asm/dlcp_main_v32.asm:8386`

**Rust sim reproduction**:
1. Extend `v32_main_parser_driven_stdby_wake_stdby_cycle_after_settle` (a6d51d6) into a 3-core dynamic test using `build_v171_v32_chain` (now reaches DISPLAY mode after 8d547fe).
2. Boot healthy. Drive parser-driven STDBY (B0/03/00 broadcast).
3. Wait for both MAINs `diag_s = 1`.
4. Before injecting wake frame, choose ONE of:
   - **Option A (MCLR-held)**: `chain.hold_core_in_reset(i_main1)`. Models hardware MCLR held externally.
   - **Option B (AN0 stuck)**: `MAIN1.peripherals.adc.set_an0_sample(0x0000)`. Models rail-sense never rising.
5. Inject wake (B0/03/01 broadcast).
6. Assert: MAIN0 `diag_s=1, diag_b=1`, MAIN1 either cycles frozen (option A) or PC stuck in adc_boot_gate (option B). CONTROL LCD reaches `Waiting for DLCP`. Later RA3 panel press emits no new B0/03/00 (covered by existing test #49's contract).

**Primitives required**: rust crate already has `hold_core_in_reset` and `set_an0_sample`. Python facade currently lacks per-core reset-hold and per-core AN0 setters — would need to add `chain.hold_main_in_reset(unit)` and `chain.set_main_an0_sample(unit, value)` PyO3 methods (small additions).

**Hardware confirm/deny tests**:
- Scope MAIN1's MCLR pin during the failed wake — does it stay LOW longer than expected?
- Scope MAIN1's AN0 (rail-sense) input — does the rail rise above threshold during wake?
- Scope MAIN1's TX pin — does it emit ANY UART traffic after wake (would imply CPU running but USB-pre-rearm)?
- Scope MAIN1's USB D+ — any enumeration attempt?
- Compare with healthy LEFT signals on the same scope.
- **Confirm**: wake byte triplet arrives at MAIN1 RX cleanly, but AN0 / MCLR / rail prevents `adc_boot_gate` exit and USB re-enumeration.
- **Deny**: MAIN1 is gate-open and USB-visible while CONTROL remains stuck.

### H2 (MEDIUM confidence) — Wake frame reaches MAIN0 but is not forwarded to MAIN1

**Hypothesis**: The DLCP chain "broadcast" semantic is firmware-level, not a physical star bus. The silicon-correct ring topology is:
```
CONTROL.TX -> MAIN0.RX -> [MAIN0 forwards] -> MAIN1.RX -> [MAIN1 forwards] -> CONTROL.RX
```
MAIN1 only sees the wake if MAIN0 forwards the broadcast bytes while in its own standby/wake transition. V3.2 forwards non-addressed route/data bytes through the parser's main UART path. If MAIN0's EUSART / baud / CPU is briefly quiesced (low-power baud change, TXIE gated, USART reset glitch) during the wake-transition window, the three wake bytes (B0/03/01) could be dropped or corrupted between MAIN0 receive and MAIN0 retransmit. Result: MAIN0 wakes and enumerates; MAIN1 never sees wake, stays in standby (gate closed, low-power state).

**Why it's lower confidence than H1**:
- Real-HW report explicitly says "RIGHT MAIN absent" from USB enum — consistent with both H1 (stuck in adc_boot_gate, USB never rearmed) AND H2 (still in standby, USB never powered-on).
- BUT operator's `cmd 0x44 returns S1 B1 from LEFT` confirms MAIN0 went through full STDBY/wake. If MAIN0 truncates a wake-broadcast retransmit, that's a forwarder-bug; otherwise the STDBY broadcast would also be missing and MAIN1 would be in a different state.
- MAIN1 not enumerating USB IS the same observable for both H1 and H2; need scope traces to disambiguate.

**Source citations**:
- 3-coupling silicon-correct ring at `crates/dlcp-sim-py/src/lib.rs:481` (build_v171_v32_chain)
- MAIN forward path at `src/dlcp_fw/asm/dlcp_main_v32.asm:1767` (uart_service entry)
- Parser forwarding at `src/dlcp_fw/asm/dlcp_main_v32.asm:1836`
- CONTROL broadcast emitter at `src/dlcp_fw/asm/dlcp_control_v171.asm:2702` (standby_wake_broadcast)

**Rust sim reproduction**:
Build from `right_main_held_in_reset_control_stuck_in_waiting`, but make it dynamic. Boot healthy chain. Drive STDBY broadcast. Then inject/drop ONLY the MAIN0→MAIN1 wake forwarding segment.

**Primitives required**:
- Today `Chain::set_uart_blackout(bool)` is GLOBAL (drops all bytes on all couplings). 
- Need a NEW per-coupling blackout/drop primitive: `Chain::set_uart_coupling_drop(coupling_idx, drop_count)` or similar, that drops the next N bytes on a specific UartCoupling entry while leaving others intact.
- Or: a test-only path that injects `B0/03/01` into MAIN0's RX directly via `inject_main_frames_fifo` AND simultaneously suppresses MAIN0's retransmit for those three bytes (no current API for this).

**Assertions**: MAIN0 `diag_b=1`, MAIN1 `diag_b=0` AND `active_flags.bit3` still clear, MAIN1 emits no TX after the wake injection, CONTROL LCD `Waiting for DLCP`, later RA3 press still gated.

**Hardware confirm/deny tests**:
- Scope BOTH current-loop segments simultaneously: CTL.TX→M0.RX and M0.TX→M1.RX
- **Confirm**: `B0 03 01` is valid on CTL.TX→M0.RX but missing/malformed on M0.TX→M1.RX
- **Deny**: clean `B0 03 01` triplet at MAIN1 RX yet MAIN1 still doesn't wake (this would shift weight to H1)

### H3 (LOW for April 27 asymmetric wake; HIGH for the secondary WAITING-input-gate behavior)

**Hypothesis**: Both MAINs actually wake, but CONTROL loses sentinel/heartbeat traffic from MAIN1 during the reconnect window and becomes "modal WAITING". Once in modal WAITING, the panel STDBY input is structurally gated (the V1.71 reconnect_wait_loop intentionally consumes only RIGHT/LEFT for soft-CPU-reset; STDBY/RA3 is NOT consumed by that gate).

**Why it's lower confidence for the April 27 case**: real-HW report explicitly says "RIGHT MAIN absent from USB enum", which strongly suggests MAIN1 is NOT awake. If MAIN1 had woken but CONTROL was just in modal WAITING, we'd expect cmd 0x44 to ALSO return data from RIGHT (USB-visible) but CONTROL not believing it. Operator didn't try cmd 0x44 against the absent RIGHT during the failure window, so we can't fully rule out "MAIN1 on but USB enum lost".

**Why it IS HIGH confidence for the T4 "second STBY ignored" sub-behavior**: Once CONTROL is parked on `Waiting for DLCP`, the reconnect-loop's button gate at `dlcp_control_v171.asm:5018,5028,5029,5031,5032` consumes only RIGHT (RC5) and LEFT (RA4) for the soft-CPU-reset escape. STDBY (RA3) is intentionally NOT consumed — so a panel STDBY press during WAITING does nothing, which is exactly what the operator observed at T4. Test `control_in_waiting_state_does_not_emit_stdby_frame_on_button_press` (#49) already locks this contract.

**Source citations**:
- WAITING screen LCD write at `src/dlcp_fw/asm/dlcp_control_v171.asm:4657`
- Reconnect sentinels at `src/dlcp_fw/asm/dlcp_control_v171.asm:4970`
- RIGHT/LEFT-only gate at `src/dlcp_fw/asm/dlcp_control_v171.asm:5018,5028,5029,5031,5032`
- RA3 (STBY) debounce mapping at `src/dlcp_fw/asm/dlcp_control_v171.asm:1968`
- Existing WAITING+RA3 test at `crates/dlcp-sim/tests/multicore_parity.rs:3822` (approx — `control_in_waiting_state_does_not_emit_stdby_frame_on_button_press`)

**Rust sim reproduction (for the T4 sub-behavior, already partially landed)**:
The existing tests #48 + #49 already cover the symptoms. To upgrade #49 with the deferred 3-way diagnostic from `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §7.2.C: read CONTROL RAM at 0x09A (button-debounce counter), 0x0BE (button-edge-state), 0x01F.bit1 (CONNECTED) before/after the STBY press. This classifies whether the gate is structural state-machine refusal or a soft debounce-timer issue.

**Hardware confirm/deny tests** (for the original T2 asymmetric wake under H3 lens):
While LCD says `Waiting for DLCP`, attempt cmd 0x44 against BOTH MAINs over USB.
- **Confirm**: both MAINs USB-visible, both gate-open, both healthy via cmd 0x44, but CONTROL RAM shows reconnect sentinels still at `0x80` and BF status bursts at CONTROL RX not reflected in CONTROL cache/state.
- **Deny**: RIGHT remains USB-absent (the actual T2 observation) — strengthens H1.

## 3. Recommended next investigation steps

### A. Rust-sim work (no HW required)

**A1. Build the H1 reproduction (HIGHEST priority)**: dynamic 3-core test with parser-driven STDBY + `hold_core_in_reset(MAIN1)` mid-cycle + parser-driven WAKE + LCD-WAITING assertion. Re-uses `v32_main_parser_driven_stdby_wake_stdby_cycle_after_settle` shape with multi-core + reset-hold injection. Estimated ~150 lines.

**A2. Add per-coupling UART fault primitive (for H2)**: extend `Chain::set_uart_blackout` to a per-coupling form `Chain::set_uart_coupling_drop(coupling_idx, drop_count)`. This generalizes the existing whole-chain blackout and unblocks H2 reproduction + ~25 wire-chain fault-injection tests in P4.7 (gpsim has the gpsim-side equivalent `set_link_fault`). Estimated ~80 lines rust + facade.

**A3. Upgrade test #49 with the deferred 3-way diagnostic (for H3 sub-behavior)**: extend the existing test to also probe 0x09A debounce counter, 0x0BE button-edge state, 0x01F.bit1 CONNECTED before/after the STBY press while CONTROL is in WAITING. Classifies the gate as structural vs soft. Estimated ~30 lines.

### B. Hardware operator session (required for full root-cause)

**B1. Repeat the April-27 setup**: V1.71 + V3.2 + V3.2 rig, panel STDBY, panel STDBY again to wake. Capture:
- Scope BOTH MAIN's MCLR pins, AN0 rail-sense, USB D+, and chain-loop UART RX during the wake transition.
- cmd 0x44 against BOTH MAINs immediately on observing the failure (within 5 s of the failed wake) — answers H3-vs-H1/H2 directly.
- Specifically test if RIGHT cmd 0x44 returns ANY data during the WAITING state (vs USB-absent).

**B2. Repeat the T4 retry**: from the WAITING state, press panel STDBY again and capture CONTROL.TX with the chain-loop probe. Confirms test #49's contract on real silicon.

### C. Decision matrix for confirmed H1

If B1 confirms H1, the firmware-level mitigation is to add a TIMEOUT to `adc_boot_gate` so a stuck rail-rise doesn't hang MAIN1 forever — `docs/V32_MAIN_HANG_HARDENING_PLAN.md` already proposes this class of hardening. The rust sim reproduction (A1) becomes a regression gate for the timeout: with the fix, MAIN1's CPU exits adc_boot_gate after the timeout and at least attempts USB re-enumeration; without the fix, MAIN1's CPU stays in the loop indefinitely.

## 4. Cross-references

- `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §6 — original field timeline
- `docs/V32_MAIN_HANG_HARDENING_PLAN.md` — V3.2 hang hardening roadmap (covers adc_boot_gate timeout class)
- `docs/analysis/TASK_44_LCD_VS_CMD44_DIVERGENCE.md` — sister field bug + fix proposal pattern
- `crates/dlcp-sim/tests/multicore_parity.rs::right_main_held_in_reset_control_stuck_in_waiting` — symptom-equivalent end-state model
- `crates/dlcp-sim/tests/multicore_parity.rs::control_in_waiting_state_does_not_emit_stdby_frame_on_button_press` — T4 input-gate contract
- `crates/dlcp-sim/tests/multicore_parity.rs::v32_main_parser_driven_stdby_wake_stdby_cycle_after_settle` — full parser-driven STDBY/WAKE/STDBY single-MAIN baseline (closes task #51)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4008` — adc_boot_gate (the H1 stuck point)
- `src/dlcp_fw/asm/dlcp_control_v171.asm:5018` — V1.71 reconnect_wait_loop button gate (the H3-confirmed STBY-ignored mechanism)
