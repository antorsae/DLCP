# Task #45 — V1.71+V3.2 STDBY/wake asymmetric-recovery field bug

**Status:** H1 firmware-OBSERVABLE reachability proven in rust sim (no MCLR-hold, no UART drop) — the test models the H1 *claim* (MAIN1's AN0 is held below threshold from the moment `wake_request_handler` fires) and shows that MAIN1's amp-enable latches `LATB.bit3`/`LATB.bit4`/`LATA.bit6` (raised at asm:4101/4084/4098 in the wake bring-up) never come up despite MAIN1 dispatching wake (`active_flags.bit3 = 1`, `diag_b >= 1`). This matches the externally-visible field symptom (RIGHT MAIN's amplifier did not turn back on after the second STDBY press). The test does NOT pin MAIN1's PC to `[adc_boot_gate, adc_boot_gate_exit)` strictly — chunked-simulator granularity and downstream wake-init dependencies (I2C writes / DSP coeff bursts post asm:4084) prevent that bit-precise claim. This is evidence for H1 *firmware-observable reachability* (the amp-pin-LOW state is reachable from per-MAIN AN0 manipulation alone), NOT independent evidence that the real PCB has the asserted asymmetric coupling — that still hinges on the open question in `docs/analysis/PIN_SEMANTICS.md:105-107` (RA6/RB3/RB4 → connector continuity unproven) and on the hardware scope traces enumerated in §B1. 3 ranked hypotheses (codex investigations 2026-05-02, 2026-05-02-pass-2, codex review of 9960ebe and acd45fb 2026-05-02-pass-3+4) with rust-sim reproduction paths and HW confirm/deny tests for each.
**Hardware session:** 2026-04-27 (V1.71 CONTROL + 2× V3.2 MAIN).
**Existing sim coverage:**
- INJECTED-FAULT reproductions: `v171_v32_v32_asymmetric_wake_main1_held_during_wake_transition` (H1 via MCLR-hold), `v171_v32_v32_asymmetric_wake_main0_to_main1_forwarder_drops_wake_triplet` (H2 via per-coupling drop).
- **SPONTANEOUS H1 reproduction (no fault)**: `v171_v32_v32_asymmetric_wake_railcoupler_spontaneous_no_fault` — RailCoupler observes MAIN0 amp-enable transitions and droops MAIN1's AN0 to model shared-rail loading; reproduces the asymmetric outcome from AN0 dynamics alone.
- Baseline control: `v171_v32_v32_wake_baseline_main1_progresses_without_fault` — confirms MAIN1 *does* wake when AN0 stays high, anchoring the RailCoupler mechanism claim.
- End-state only: `right_main_held_in_reset_control_stuck_in_waiting`, `control_in_waiting_state_does_not_emit_stdby_frame_on_button_press`.
- Counter contracts: `v32_main_runtime_counters_baseline_and_post_stdby_cycle`, `v32_main_parser_driven_stdby_wake_stdby_cycle_after_settle`.

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

### H1 (HIGH confidence) — MAIN0's wake-time amp-enable transient depresses MAIN1's AN0 rail-sense below threshold (shared-rail coupling)

**Refined hypothesis (2026-05-02 codex pass-2)**: not a generic "per-board variance" issue — a SPECIFIC chain-protocol mechanism that should be **deterministic** given the chain ordering. The bug is not random; it's an emergent property of the silicon-correct ring topology + shared analog rail + amp-enable sequencing.

**Pin map** (V3.2 MAIN, codex investigation 2026-05-02-pass-2; citation lines verified pass-3):
- **RB3 / LATB.bit3** — final amp gate. Driven LOW during true STDBY shutdown at `src/dlcp_fw/asm/dlcp_main_v32.asm:6144` (in `hw_standby_shutdown`). The bring-up path ALSO clears LATB.bit3 at `src/dlcp_fw/asm/dlcp_main_v32.asm:4078` (the first step of the wake/cold-bring-up sequence, alongside MSSP/TRIS reconfig — the firmware re-floors the amp gate before re-asserting it). Then driven HIGH late in wake at `src/dlcp_fw/asm/dlcp_main_v32.asm:4101` (after the DSP mute / coeff-write call to `main_core_service_4574` returns).
- **RB4 / LATB.bit4** — companion amp/rail enable. Raised at `src/dlcp_fw/asm/dlcp_main_v32.asm:4084` between two `timer3_blocking_delay` calls (effectively a settle window); see also `docs/NO_POP_FIRMWARE_FLASH.md:80-83`.
- **RA6 / LATA.bit6** — companion amp/rail enable. Raised at `src/dlcp_fw/asm/dlcp_main_v32.asm:4098` (after MSSP hard-reset, before `clrf_i2c_coeff_0123_and_write`).
- **SRC4382 (cfg71 at I²C 0x71) GPOs `0x1B/0x1C/0x1D`** — rail-control GPOs driving external amp-standby circuits. Wake-time order on V3.2: `main_i2c_service_32f8` is called from `src/dlcp_fw/asm/dlcp_main_v32.asm:4103` (between LATB.bit3 := 1 at :4101 and the explicit 0x1B write at :4117-4118); inside that helper, register `0x1C` is written at `src/dlcp_fw/asm/dlcp_main_v32.asm:4857-4858` (`movlw 0x1C; call i2c_secondary_dev_write`) and `0x1D` at `:4861-4862`. The explicit `0x1B` write happens AFTER the helper returns, at `:4117-4118` (`movlw 0x1B; call i2c_secondary_dev_write`). So full SRC4382 wake order is `0x1C → 0x1D → 0x1B`. SRC4382 register-file model: `crates/dlcp-sim/src/peripherals/src4382.rs:23-27`.
- **RA0 / AN0** — rail-sense ADC input. `adc_boot_gate` (`asm:4041`) busy-waits until sample `>= 0x0236`; runtime hysteresis `0x0229/0x0228`. Cite: `docs/analysis/PIN_SEMANTICS.md:76`; `docs/analysis/MAIN_AN0_STANDBY_TRACE.md:9-23,54-66`.
- **PCB-level coupling**: `docs/analysis/PIN_SEMANTICS.md:105-107` notes that exact PCB/netlist continuity from `RA6/RB3/RB4` to connector pins is "still required" — i.e. NOT proven in repo. The shared-rail-coupling claim below is INFERRED from firmware behavior + board-doc references, not from the schematic directly.

**Causal chain (deterministic, no fault injection)**:

1. Operator presses panel STBY again. CONTROL emits broadcast `B0/03/01` via `standby_wake_broadcast` (`src/dlcp_fw/asm/dlcp_control_v171.asm:2716`).
2. Silicon-correct ring delivery: MAIN0 receives the wake byte triplet first via `CTL.tx -> M0.rx`. MAIN1 receives the SAME triplet a few UART bytes later via `M0.tx -> M1.rx` forwarding (MAIN0's parser retransmits on its TX while it dispatches the wake).
3. Both MAINs enter `wake_request_handler` (asm:1881) → set `active_flags.bit3` + `event_flags.bit2` → `standby_event_dispatch` (asm:8386) → bring-up branch → `diag_b` increments → `adc_boot_gate` (asm:4041) for rail-rise wait.
4. **Asymmetric exit ordering** (REQUIRES the rail model to bias the result): MAIN0 entered `adc_boot_gate` earlier than MAIN1 by some delta (a few UART-byte times — the wake-frame propagation through the M0->M1 forwarder). Earlier ENTRY does NOT by itself guarantee earlier EXIT, since the loop exits on `AN0 >= 0x0236`. Earlier exit follows ONLY under a dynamic rail model where the rail is BELOW threshold initially and rising. In that scenario MAIN0's polling phase begins earlier, so its first sample-above-threshold occurs earlier; MAIN1 starts polling slightly later. Once MAIN0 exits, its wake path then asserts its amp-enable outputs in this firmware-pinned order (verified against the asm body in the Pin map above):
   - `LATB.bit4 := 1` (asm:4084), then a `timer3_blocking_delay` settle window
   - `LATA.bit6 := 1` (asm:4098)
   - `LATB.bit3 := 1` (asm:4101) — final amp gate HIGH
   - `main_i2c_service_32f8` call at asm:4103 → SRC4382 `0x1C` write at asm:4857-4858 → SRC4382 `0x1D` write at asm:4861-4862
   - SRC4382 `0x1B` write at asm:4117-4118 (after helper returns)
5. **Shared-rail loading**: when MAIN0 asserts the early-wake outputs (`LATB4`, `LATA6`, then `LATB3`), the audio amplifier rail begins to draw current. If MAIN1's AN0 sense is connected to the SAME rail node (board-level coupling — TBD per `PIN_SEMANTICS.md:105-107`, NOT proven in repo), MAIN0's inrush transiently depresses that rail, dropping MAIN1's AN0 sample below the `0x0236` threshold.
6. **`adc_boot_gate` has NO timeout** — MAIN1 re-samples AN0, sees the depressed value, stays in the polling loop. If the depression persists long enough (or oscillates near threshold for long enough), MAIN1 never exits.
7. **Symptom**: MAIN0 finishes wake, brings up USB enumeration, accepts cmd 0x44, returns `S1 B1`. MAIN1 stays in `adc_boot_gate` forever — CPU runs but doesn't return to main loop, USB never rearms (cmd 0x44 absent), MAIN1.TX → CONTROL.RX edge stays silent (no chain heartbeat). CONTROL's reconnect-wait loop times out → LCD shows `Waiting for DLCP`.
8. **Recovery**: hard mains-side power cycle interrupts the rail entirely → both MAINs cold-boot → both `adc_boot_gate` instances see the rail rise simultaneously from 0V → both exit at the same time → both wake symmetrically.

**Why the existing rust sim doesn't reproduce this spontaneously**:
- Rust seeds both MAINs' AN0 to STATIC `0x0300` via `MAIN.peripherals.adc.set_an0_sample(0x0300)` in the factory (`crates/dlcp-sim-py/src/lib.rs:472,474`). The value never changes during simulation — both MAINs see `>= 0x0236` always, both exit `adc_boot_gate` immediately, no asymmetric outcome.
- SRC4382 model is register-only (`crates/dlcp-sim/src/peripherals/src4382.rs:46-52`) — GPO writes latch but don't drive any external rail state.
- No `RailCoupler` between MAIN0's amp-enable outputs and MAIN1's AN0 input.
- Both cores have identical clock + boot epoch (no per-MAIN timing variance to make the asymmetric ordering manifest).

**Source citations**:
- `wake_request_handler:` label at `src/dlcp_fw/asm/dlcp_main_v32.asm:1881`
- `standby_request_handler:` label at `src/dlcp_fw/asm/dlcp_main_v32.asm:1906`
- `adc_boot_gate:` label at `src/dlcp_fw/asm/dlcp_main_v32.asm:4041` (rail-rise sample loop body starts at :4049; header comment block at :4008)
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
- 3-coupling silicon-correct ring at `crates/dlcp-sim-py/src/lib.rs:481-483` (build_v171_v32_chain impl at :462; PyO3 method at :776)
- MAIN forward path: `uart_service` entry label at `src/dlcp_fw/asm/dlcp_main_v32.asm:1786` (header comment block at :1767)
- Parser forwarding at `src/dlcp_fw/asm/dlcp_main_v32.asm:1836`
- CONTROL broadcast emitter: `standby_wake_broadcast:` label at `src/dlcp_fw/asm/dlcp_control_v171.asm:2716` (header comment block at :2702)

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

## 2.5. Why doesn't the rust simulator reproduce bug #45 spontaneously?

The bug is **deterministic** on real hardware (operator confirms it happens reliably on certain power cycles, not as a spurious random fault). For a deterministic field bug, the simulator SHOULD be able to reproduce it spontaneously without injecting any explicit fault — anything less indicates a sim fidelity gap.

Ranked sim fidelity gaps that mask H1 (codex investigation 2026-05-02-pass-2):

### Gap #1 (CRITICAL for H1 reproduction) — no rail / inrush / AN0 coupling model

Rust seeds both MAINs' AN0 to STATIC `0x0300` via `MAIN.peripherals.adc.set_an0_sample(0x0300)` in the chain factory (`crates/dlcp-sim-py/src/lib.rs:472,474`). The value never changes during simulation. SRC4382 is register-only (`crates/dlcp-sim/src/peripherals/src4382.rs:46-52`) — GPO writes latch but don't drive any external rail state. There is NO `RailCoupler` between MAIN0's amp-enable outputs (RB3/RB4/RA6 + SRC4382 GPOs) and MAIN1's AN0 input.

Without a rail-coupling model, both MAINs see `>= 0x0236` always; both exit `adc_boot_gate` immediately after the wake byte arrives; no asymmetric outcome is possible.

**Minimum change to unblock**: add a `RailCoupler` test model that:

1. Observes MAIN0's writes to SRC4382 `0x1B/0x1C/0x1D` and to `LATB.bit3/bit4` and `LATA.bit6`.
2. Maintains a "rail node" voltage state with rise/fall/inrush dynamics (rise time ~10s of ms; transient sag on amp-enable assertion).
3. Drives each MAIN's `adc.set_an0_sample(...)` from the rail node state, sampled per-MAIN with potentially different coupling coefficients (modeling per-board variance).

### Gap #2 (HIGH for H1 reproduction) — no per-board / per-MAIN analog variance

Rust models all cores identically: same clock domain, same boot epoch, same ADC value, same rail timing. Real DLCP silicon has per-board parameter variance (rail rise time, ADC offset, amp-enable transistor characteristics, decoupling capacitance, etc.). For the asymmetric-wake mechanism to manifest, MAIN1's coupling coefficient or threshold margin must differ slightly from MAIN0's.

**Minimum change to unblock**: per-MAIN rail-rise time constants, per-MAIN ADC offset/noise, optionally per-MAIN clock or boot skew (currently both schedule_initial_steps=&[0,0,0]).

### Gap #3 (MEDIUM but lower priority for #45) — POR RAM zeroing

User asked: "Why does rust POR clear RAM to known values? is it equivalent to the PIC datasheet spec?"

**Answer**: rust POR uses an explicit `for byte in core.memory.as_mut_slice() { *byte = 0; }` loop in `crates/dlcp-sim/src/reset.rs:177-183` (within the `ResetSource::PowerOn` arm) which wipes ALL data memory to zero, then writes RCON's POR-reset value back at `:184-191`, then applies SFR POR defaults via `apply_por_sfr_defaults` at `:193`. The PIC18F2455 datasheet (DS39632E) covers POR in §4.3 "Power-on Reset (POR)" with reset-state tables in §4.6; specifically §5.3.4 documents that GPRs (general-purpose RAM) have **non-initialized** state on POR — i.e. silicon does NOT guarantee any particular value (Table 4-3 entries are "u-uuu uuuu" / "xxxx xxxx" indicating unknown bits).

Rust's choice to clear to zero is a **deterministic-simulation simplification**, matching gpsim's default behavior. It does NOT match real silicon's "unknown" state — but for bug #45 specifically, it is **NOT the masking factor**, because:

- Bug #45 happens AFTER healthy cold boot + healthy first STDBY/wake cycle.
- Firmware explicitly initializes the relevant RAM cells during cold init (peripheral state, `active_flags`, `event_flags`, `diag_*` block) and those writes overwrite any POR garbage.
- The asymmetric-wake mechanism is in the rail/AN0/amp-enable analog domain, not in POR RAM state.

For bug #44 (cmd 0x44 vs LCD divergence), POR RAM zeroing IS a masking factor — the V1.71 diag cache cells (0x180+) start at 0 in rust but at random POR garbage on silicon. See `docs/analysis/TASK_44_LCD_VS_CMD44_DIVERGENCE.md` for that case. For bug #45, fix gap #1 and #2 first.

### Gap #4 (LOW) — adc_boot_gate has no timeout in firmware

This is a FIRMWARE issue, not a sim issue. `adc_boot_gate` busy-waits until AN0 crosses threshold with no timeout. Once MAIN1 is stuck, no firmware-level recovery fires. The mitigation is the adc_boot_gate timeout proposed in `docs/V32_MAIN_HANG_HARDENING_PLAN.md`.

## 2.6. Refined H1 reproduction recipe (without explicit fault injection)

Goal: spontaneous reproduction in rust simulator without `hold_core_in_reset` or per-coupling drop.

```
1. Build V1.71 + MAIN0 V3.2 + MAIN1 V3.2 chain (existing factory).
2. Add `RailCoupler` test model:
   - Inputs: MAIN0's SRC4382 GPO writes (0x1B/0x1C/0x1D) +
            MAIN0's LATB.bit3/bit4 + MAIN0's LATA.bit6 + MAIN1's
            corresponding outputs (symmetrical for the bring-up
            sequence, in case the coupling is bidirectional).
   - State: a single shared "rail voltage" value, advancing via
            ODE-like rise/fall/inrush dynamics on a tick step.
   - Output: drives each MAIN's adc_an0_sample value once per Tcy.
3. Tuning parameters:
   - Per-MAIN base rail rise constant (small variance enough to
     guarantee MAIN0 exits adc_boot_gate first).
   - Inrush sag depth + recovery time when amp-enable asserts
     (must drop below 0x0236 long enough for MAIN1's
     adc_boot_gate polling cycle to re-sample and stay below
     threshold).
4. Run STDBY broadcast as in the existing tests.  No explicit fault.
5. Inject WAKE.  Observe:
   - MAIN0 exits adc_boot_gate first, completes wake.
   - MAIN1's AN0 was depressed by MAIN0's amp-enable activity;
     MAIN1 stays in adc_boot_gate.
6. Assertion: same as existing H1 injected-fault test (MAIN0 woke,
   MAIN1 stuck), but achieved without explicit fault.
```

If the spontaneous reproduction matches the existing INJECTED-fault tests' chain-level outcome, that is strong evidence that H1 (shared-rail coupling) is the actual root cause.

If the spontaneous reproduction does NOT manifest the asymmetric outcome with reasonable parameters, that's evidence the mechanism is something else (forwarder bug per H2, or different rail topology, etc.).

**Implementation cost estimate**: 200-400 lines for the RailCoupler model, plus parameter tuning. Substantial work. Tracked as a follow-up below.

## 3. Recommended next investigation steps

### A. Rust-sim work (no HW required)

**A1. Build the H1 INJECTED-FAULT reproduction (DONE 2026-05-02, commit 93092d6)**: dynamic 3-core test with parser-driven STDBY + `hold_core_in_reset(MAIN1)` mid-cycle + parser-driven WAKE + asymmetric outcome assertion. Re-uses `v32_main_parser_driven_stdby_wake_stdby_cycle_after_settle` shape with multi-core + reset-hold injection. Test name: `v171_v32_v32_asymmetric_wake_main1_held_during_wake_transition`.

**A2. Add per-coupling UART fault primitive (DONE 2026-05-02, commit 93092d6)**: `Chain::set_uart_coupling_drop(coupling_idx, drop_count)` generalizes the existing whole-chain `set_uart_blackout` and unblocks H2 reproduction + ~25 wire-chain fault-injection tests in P4.7. Mirror of gpsim's `set_link_fault(name, drop=True)`. Used by H2 test `v171_v32_v32_asymmetric_wake_main0_to_main1_forwarder_drops_wake_triplet`.

**A3. Upgrade test #49 with the deferred 3-way diagnostic (for H3 sub-behavior)**: extend the existing test to also probe 0x09A debounce counter, 0x0BE button-edge state, 0x01F.bit1 CONNECTED before/after the STBY press while CONTROL is in WAITING. Classifies the gate as structural vs soft. Estimated ~30 lines.

**A4. Build the H1 firmware-observable reproduction via RailCoupler model (DONE 2026-05-02, refined post codex reviews of 9960ebe, acd45fb, and 087c2b5)**: a 3-core test (`v171_v32_v32_asymmetric_wake_railcoupler_spontaneous_no_fault`) that lets both MAINs process the WAKE byte normally (AN0 stays at the 0x0300 build seed during STDBY/WAKE injection), then watches MAIN1's `active_flags.bit3` (RAM 0x05E). The first chunk where `af1.bit3` transitions 0 → 1 proves MAIN1 has just executed `wake_request_handler` (asm:1894); the test drops MAIN1's AN0 to 0x0100 on that chunk. The path from `wake_request_handler` exit to the gate's first ADC conversion at asm:4048 traverses several main-loop service routines + `standby_event_dispatch` (asm:8386) + the gate prologue, leaving ample MAIN-Tcy for the droop to land before the conversion's 12-Tcy latency latches. MAIN0's AN0 is left at 0x0300 throughout — modelling the H1 *claim* that MAIN0's local sense node is closer to the regulator. After ~1.25 s of sim time post-droop, MAIN1 ends at `active_flags.bit3 = 1`, `diag_b >= 1`, the post-gate amp-enable latches (`LATB.bit3`/`LATB.bit4`/`LATA.bit6` at asm:4101/4084/4098) NEVER raise, AND MAIN1 emits ZERO UART TX bytes post-droop (the `uart_quiesce_for_wake` call at asm:4043 — the very first thing inside `adc_boot_gate` — disables EUSART RX/TX/SPEN until the post-gate re-init at asm:4128). The latch-low + zero-TX combination pins MAIN1 to `[adc_boot_gate (asm:4042), adc_boot_gate post-gate UART re-init (asm:4128))` — i.e. MAIN1 IS inside the gate body or its post-exit prologue. A companion baseline (`v171_v32_v32_wake_baseline_main1_progresses_without_fault`) confirms that without the droop MAIN1 fully wakes, so the stuck state in the RailCoupler test is attributable to the AN0 droop and not to a generic chain-forwarding sim gap. NO MCLR-hold, NO UART drop. The test does NOT prove the real PCB has the asserted asymmetric coupling — that still hinges on the netlist continuity question in `docs/analysis/PIN_SEMANTICS.md:105-107` and the §B1 hardware scope traces.

**A5. Add per-MAIN AN0 setter to PyO3 facade (DONE 2026-05-02, refined post codex review of 9960ebe)**: `Chain::set_main_an0_sample(unit, value)` PyO3 method on `crates/dlcp-sim-py/src/lib.rs` plus the `set_main_an0_sample` Python-facade wrapper on `src/dlcp_fw/sim/dlcp_sim_native.py`. `unit ∈ {0,1}`, `value` must fit in 10 bits (the PIC18F2455 ADC is 10-bit per DS39632E §21); out-of-range values raise `ValueError` rather than silently masking. Allows Python-facade tests to model rail droop on a specific MAIN before/after wake. Lighter-weight than the rust-side RailCoupler (which observes MAIN1's `diag_b` and reacts) but composable with explicit chunk-stepping for similar effect.

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
- `crates/dlcp-sim/tests/multicore_parity.rs::v171_v32_v32_asymmetric_wake_main1_held_during_wake_transition` — H1 INJECTED-FAULT reproduction (commit 93092d6)
- `crates/dlcp-sim/tests/multicore_parity.rs::v171_v32_v32_asymmetric_wake_main0_to_main1_forwarder_drops_wake_triplet` — H2 INJECTED-FAULT reproduction (commit 93092d6)
- `crates/dlcp-sim/tests/multicore_parity.rs::v171_v32_v32_asymmetric_wake_railcoupler_spontaneous_no_fault` — H1 SPONTANEOUS reproduction via shared-rail asymmetric coupling (no fault injected; AN0 dynamics only)
- `crates/dlcp-sim/tests/multicore_parity.rs::v171_v32_v32_wake_baseline_main1_progresses_without_fault` — baseline control confirming MAIN1 wakes normally in the rust sim absent any AN0 manipulation (anchors the RailCoupler mechanism claim)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4041` — `adc_boot_gate:` label (the H1 stuck point; loop body at :4049; header comment at :4008)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4084` — early-wake `LATB.bit4 := 1` (RB4 amp/rail enable; followed by `timer3_blocking_delay`)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4098` — pre-DSP-coeff `LATA.bit6 := 1` (RA6 amp/rail enable; after `mssp_hard_reset`, before `clrf_i2c_coeff_0123_and_write`)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4101` — late-wake `LATB.bit3 := 1` (RB3 final amp gate; after `main_core_service_4574` returns)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4103` — `main_i2c_service_32f8` call inside the wake path (immediately after LATB.bit3 := 1); the helper performs the SRC4382 `0x1C` and `0x1D` writes BEFORE the explicit `0x1B` write below
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4857-4858` — SRC4382 register `0x1C` write inside `main_i2c_service_32f8` (`movlw 0x1C; call i2c_secondary_dev_write`)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4861-4862` — SRC4382 register `0x1D` write inside `main_i2c_service_32f8` (`movlw 0x1D; call i2c_secondary_dev_write`)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4117-4118` — SRC4382 register `0x1B` write at the end of the wake path (`movlw 0x1B; call i2c_secondary_dev_write`); fires AFTER `main_i2c_service_32f8` returns
- `src/dlcp_fw/asm/dlcp_main_v32.asm:4078` — wake/cold-bring-up `LATB.bit3 := 0` (re-floors the final amp gate at the FIRST step of bring-up before MSSP/TRIS reconfig); NOT the true STDBY shutdown clear (that's at :6144 below)
- `src/dlcp_fw/asm/dlcp_main_v32.asm:6144` — true STDBY shutdown `LATB.bit3 := 0` inside `hw_standby_shutdown`
- `src/dlcp_fw/asm/dlcp_control_v171.asm:5018` — V1.71 reconnect_wait_loop button gate (the H3-confirmed STBY-ignored mechanism)
- `crates/dlcp-sim-py/src/lib.rs:472,474` — STATIC `set_an0_sample(0x0300)` seed (the sim fidelity gap that prevents spontaneous H1 reproduction)
- `crates/dlcp-sim/src/peripherals/src4382.rs:46-52` — SRC4382 register-only model (no rail-state side effects)
- `crates/dlcp-sim/src/reset.rs:177-183` — POR explicit `for byte in core.memory.as_mut_slice() { *byte = 0; }` loop zeros RAM (followed by RCON-write at `:184-191` and `apply_por_sfr_defaults` at `:193`); PIC18F2455 datasheet DS39632E §4.3 (POR) + §4.6 (reset-state tables) + §5.3.4 (GPR non-initialization) document silicon's POR RAM as "unknown" — so rust's behavior is a deterministic-simulation simplification, NOT silicon-faithful, but lower-priority for #45 because firmware overwrites the relevant cells during cold init
- `docs/analysis/PIN_SEMANTICS.md:76` — RA0/AN0 standby/rail-sense semantics
- `docs/analysis/PIN_SEMANTICS.md:105-107` — OPEN QUESTION: PCB netlist continuity from RA6/RB3/RB4 to connector pins (NOT proven in repo; the shared-rail-coupling claim in §H1 is INFERRED, not directly verified)
- `docs/analysis/MAIN_AN0_STANDBY_TRACE.md:9-23,54-66` — AN0 threshold/hysteresis values (`>= 0x0236` boot, `0x0229/0x0228` runtime hysteresis)
- `firmware/reference/dlcp.md:417-418,497-503` — board-doc references to `Amplifier standby` (J16/J4) and `Supply standby`
