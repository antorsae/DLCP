# gpsim Simulation Fidelity: What Tests Can Trust

## Purpose

This document audits the gpsim co-simulation harness for DLCP firmware testing and explicitly catalogs where the simulator diverges from real hardware. It was originally written because V3.2 hardening saw multiple V1.71 Layer 2 chain tests report as "failing" and the initial hypothesis was that gpsim collapsed timing windows into single instruction cycles. That hypothesis has since been **retracted by direct measurement** — see the 2026-04-18 correction immediately below.

The goal is still to separate firmware regressions from harness artifacts, enabling faster iteration without second-guessing every test failure against "could this be gpsim?"

**How to use this document:** Start with the correction section below. Then consult the [Test-class fidelity matrix](#test-class-fidelity-matrix) to decide whether a failing test needs real hardware validation. Read the [Specific known-broken cases](#specific-known-broken-cases) section for test names and their exact gaps. Use [Recommendations](#recommendations) to place new tests in the appropriate validation band.

---

## 2026-04-18 correction — TAS3108 / preset-apply collapse claim retracted by measurement

An earlier draft of this document asserted that gpsim collapses a 97-byte TAS3108 coefficient write into "one instruction cycle (~62.5 ns at 16 MHz MAIN Fosc)", making interleaved-mute and preset-soak race tests impossible to exercise faithfully. Two targeted probes on branch `feature/gpsim-i2c-fidelity-probe` show both the collapse claim and its downstream consequences are wrong.

Probes (in that branch):
- `scripts/probe_gpsim_i2c_byte_timing.py` — single-MAIN, measures cycles between `preset_job_state` rising and falling edges.
- `scripts/probe_ir_vs_apply_race.py` — two-MAIN, logs `apply_started` / `ir_injected` / `ir_bf03_on_wire` / `ir_arrived_m{0,1}` / `apply_ended` cycles.

Probes use `-gpsim-probe` suffixed copies of `DLCP_Control_V1.71.hex` and `DLCP_Firmware_V3.2.hex` living under `artifacts/probes/` so they cannot be flashed to hardware by accident.

### What the code actually does

- `src/dlcp_fw/asm/dlcp_main_v32.asm:5096` sets `SSPADD = 0x77` → SCL ≈ **33 kHz** (not 400 kHz).
- `vendor/gpsim-0.32.1-xtc/src/ssp.cc:1754-1817` runs a 4-phase callback per bit. Each phase is scheduled via `setBRG()` (line 2529) which adds `(SSPADD/4)+1 = 31` instruction cycles. One byte ≈ 9 × 4 × 31 ≈ **1,116 cycles ≈ 279 µs** at 4 MHz MAIN Tcy.
- For a 97-byte coefficient transaction: ~108,000 instruction cycles ≈ **27 ms of raw I2C wire time**, matching the ~29 ms real hardware would take at 33 kHz.

### Single-MAIN measurement (V1.71 CONTROL + V3.2 MAIN, IR 0x39, chunk_cycles = 60,000)

```
[after-profile] main0.cycle=25,039,808 preset_job=0x00 preset=0 status=0x09
>>> apply started: step 1,  main0.cycle=25,119,808 job=0x02
>>> apply done:    step 37, main0.cycle=28,079,788 previous_step=27,999,789 (step_chunk=79,999)
>>> samples observed with job != 0: 36 (max job state=0x03)

MAIN cycles during preset apply: 2,879,981 .. 2,959,980
Equivalent MAIN wall time:       720.00 ms .. 740.00 ms
```

Reference points:
- 33 kHz wire time for 97 bytes: ~29 ms (~116,000 cycles)
- Full hardware apply (doc claim): ~600 ms (~2,400,000 cycles)
- "Collapsed to 1 cycle" claim: 62.5 ns (~1 cycle)

**Verdict: hardware-faithful within 20 %.** gpsim is actually slightly *slower* than the real hardware claim here, not faster.

### Two-MAIN IR-mute-during-apply measurement (same pair, IR 0x35, chunk_cycles = 60,000)

```
apply_started     : main0.cycle=31,999,724   7999.93 ms   (preset_job_state → non-zero)
ir_injected       : main0.cycle=31,999,724   7999.93 ms   (inject_decoded_ir_event)
ir_bf03_on_wire   : main0.cycle=32,079,723   8019.93 ms   (CONTROL emits BF/03/02 frame)
ir_arrived_m0     : main0.cycle=32,079,723   8019.93 ms   (rx_wr 0x2F → 0x59, 42-byte burst)
ir_arrived_m1     : main1.cycle=32,079,734   8019.93 ms   (rx_wr 0x48 → 0x73, 43-byte burst)
apply_ended       : main0.cycle=39,119,668   9779.92 ms   (preset_job_state → 0)

main0 final status=0x3C  preset=1  muted=1
main1 final status=0x3C  preset=1  muted=1

apply window:  7,119,944 MAIN cycles = 1,779.99 ms   (two-MAIN ≈ 2× single-MAIN, as expected)
IR arrived DURING apply window? YES, at +79,999 cycles (+20.00 ms)
```

**Verdict:** the IR-mute-during-apply race works in gpsim. The firmware correctly preserves both `preset=1` and `muted=1`. The race window exists, IR arrival is realistic (~20 ms CONTROL-emit latency), and the outcome is correct.

### What this retraction affects in the rest of the document

- §[Components and their fidelity → TAS3108 I2C device](#tas3108-i2c-device-mainicregfiledevice-in-srcdlcp_fwsimmain_gpsimpy-line-55): "Critical gap" paragraph, "Byte timing" bullet, and "Race-window collapse" failure mode are retracted and replaced inline below.
- §[Test-class fidelity matrix](#test-class-fidelity-matrix): preset-apply race rows are re-rated.
- §[Specific known-broken cases](#specific-known-broken-cases): the two V3.2 wire-chain entries have corrected root-cause text.
- §[Sizing the gap](#sizing-the-gap): "Most impactful gap: TAS3108 I2C byte timing" is demoted to "retracted — not a gap".

The **UART bridge causality-shift** behaviour and **IR/button injection latency bypass** described elsewhere in this document have not been independently re-measured. Treat those as still-open until probed similarly. A separate harness-level artefact *was* observed in the IR-race probe: with default `control_chunk_cycles = 1,000,000`, RX frames are delivered to MAIN in bursts of ~14 per chain step (step_chunk ≈ 333 ms). Tightening to `control_chunk_cycles = 60,000` resolved this; tests timing sub-chunk events should consider lowering the default.

---

## Components and their fidelity

### TAS3108 I2C device (`MainI2CRegFileDevice` in `src/dlcp_fw/sim/main_gpsim.py` line 55)

**What it models:**
- PIC18 MSSP I2C master-mode initiates write transactions to two fixed slaves: `cfg71` (0x71) and `dsp34` (0x34).
- Each write is a sequence of address byte + data bytes, each with ACK/NACK, clock-stretching (SCL held low by slave), and SDA-stuck faults.
- gpsim's `i2c_regfile` module handles ACK/NACK and basic stretching via properties like `Address_Stretch_SCL_Cycles`, `Data_Stuck_SDA_Cycles`.

**How faithfully:**
- Address matching and byte ACK/NACK are accurate (lines 154–162 in `main_gpsim.py`).
- `i2c_regfile` supports optional SCL-hold and SDA-stuck fault injection (lines 156–171), which matches real TAS3108 failure modes.
- **Byte and transaction timing are faithful.** DLCP firmware runs I2C at SSPADD=0x77 (~33 kHz, slow-mode). gpsim's `ssp.cc` runs a 4-phase callback per bit, producing ~1,116 instruction cycles per byte. A 97-byte coefficient write takes ~27 ms of simulated wire time, and a full preset apply (with firmware overhead) measures 720 ms single-MAIN / 1,780 ms two-MAIN — vs. ~600 ms on real hardware. See the [2026-04-18 correction](#2026-04-18-correction--tas3108--preset-apply-collapse-claim-retracted-by-measurement) at the top of this document for the raw probe data.

**Where it diverges from real hardware:**
- **Write completion delay:** A real TAS3108 coefficient write is not available for reads until ~5 ms after the stop condition. gpsim reflects the write to the regfile state immediately, making the coefficient available on the next MAIN instruction. This remains a real gap but is minor for the current test suite because firmware rarely reads back a coefficient it just wrote within the 5 ms window.
- **Multi-byte streaming:** Real hardware can experience mid-stream errors (bit-flip, underrun, collision). gpsim does not model electrical noise or partial-transmission recovery.
- ~~**Byte timing** (earlier claim retracted 2026-04-18): both the per-byte SCL clocking and the aggregate 97-byte transaction match real hardware within 20 % in gpsim. The "one instruction cycle" claim was not supported by the `ssp.cc` source or by measurement.~~

**Failure modes it produces in tests:**
1. ~~**Race-window collapse**~~ **[retracted 2026-04-18]** — the two-MAIN probe shows the interleaved-mute race firing correctly (IR arrives at +20 ms into a 1,780 ms apply window, final state is `preset=1 muted=1` on both MAINs). `test_v32_wire_two_main_interleaved_mute_during_delayed_switch_preserves_state` should not be xfailed on the grounds that gpsim collapses this race.

2. **Fault recovery bypass:** MSSP STOP faults followed by bus-clear (bitbanging 9 SCL cycles to unstick a slave) depend on SCL-held periods in real hardware. gpsim's stretch injection can simulate this, but the regfile module does not automatically model multi-byte deadlock scenarios that firmware bus-clear is designed to handle.
   - **Affected test:** `test_wire_mssp_stop_cascade_full_dsp_recovery` (line 245 of `test_v31_v163b_robustness.py`).

---

### UART bridge (`_StreamingUartBridge` in `src/dlcp_fw/sim/wire_chain_gpsim.py` line 65)

**What it models:**
- Multi-process gpsim harness: each PIC (CONTROL, MAIN0, MAIN1) runs in a separate gpsim instance.
- UART TX pin transitions from sender are recorded to a file (via gpsim's `FileRecorder` module, line 38 in `wire_chain_gpsim.py`).
- A Python bridge reads the file and forwards edges to the receiver's RX pin via a named FIFO (gpsim's `FileStimulus` module, line 47).
- The bridge performs cycle-count scaling (line 34: `_scaled_cycles`), mapping sender cycles to receiver clock domain, and enforces causality by shifting batches forward if the receiver has advanced past the sender's scheduled edge.

**How faithfully:**
- Byte-level timing is preserved within each gpsim process: MAIN's EUSART module in gpsim does execute the three-sample RX majority detect, RCREG FIFO, and OERR logic.
- Baud-rate match between processes is enforced by the `_scaled_cycles` clock scaling (line 261 in `wire_chain_gpsim.py`), converting from `CONTROL_TCY_HZ` (3 MHz) to `MAIN_TCY_HZ` (4 MHz).
- The bridge's `flush()` method (line 118) correctly detects when the receiver's clock has outrun the sender's scheduled cycle and shifts the batch forward while preserving intra-batch spacing.

**Where it diverges from real hardware:**
- **Zero-latency forwarding:** A real UART cable has ~10 ns propagation delay per meter. gpsim's file-based forwarding has sub-microsecond latency but is still orders of magnitude faster than electrical transmission.
- **Timing jitter collapse:** Real UART hardware has phase noise on both the sender and receiver clocks (±2–3% on cheap crystals). Both MCUs in a pair experience independent clock drift. gpsim uses perfect (integer) clock rates, so sender and receiver frequencies are identical. Over a 100-byte frame at 31,250 baud (320 ms), real hardware can accumulate 5–10 ms of relative skew. gpsim does not.
- **Causality enforcement cost:** When the receiver's step() has advanced beyond the sender's natural mapped cycle, the bridge shifts the entire batch forward (line 169). This preserves causality (no backwards-in-time edges) but loses the original sender→receiver timing relationship. The shift amount is tracked (line 174: `max_shift_cycles`), which tests can assert against, but the default behavior is silent.
  - Tests with strict timing expectations (e.g., `test_v32_wire_two_main_interleaved_mute_during_delayed_switch_preserves_state`) should pass `bridge_shift_warn_threshold` to the `WireMultiMainChainHarness` constructor (line 243) to catch hidden shifts.

**Failure modes it produces in tests:**
1. **Causality-enforced timing loss:** A test that expects a precise IRQ-window relative to UART byte arrival will pass in gpsim (because the shift is silent) but fail on hardware (because the real shift would be much smaller or absent). The test framework currently does not warn by default.
   - **Affected test scenarios:** Any test combining high-frequency IR or button inject with UART chain activity, especially preset-apply.

2. **Crystal-skew immunity:** A test that would timeout on hardware due to receiver clock drift (e.g., overrun on a long-running command) will pass in gpsim because clocks are perfect.
   - **Affected test scenarios:** Multi-minute soak tests, high-bandwidth preset-table uploads.

---

### Clock scaling (`_scaled_cycles` in `src/dlcp_fw/sim/wire_chain_gpsim.py` line 34)

**What it models:**
- CONTROL runs at 12 MHz Fosc ⇒ 3 MHz instruction clock (`CONTROL_TCY_HZ`).
- MAIN runs at 16 MHz Fosc ⇒ 4 MHz instruction clock (`MAIN_TCY_HZ`).
- When the CONTROL harness runs for `control_chunk_cycles` instruction cycles, the MAIN harness must step for `_scaled_cycles(control_chunk_cycles, from_hz=CONTROL_TCY_HZ, to_hz=MAIN_TCY_HZ)` cycles to keep wall-clock time in sync.

**How faithfully:**
- The scaling formula (line 35) is exact: `max(1, int((cycles * to_hz + (from_hz // 2)) // from_hz))` uses rounding division to avoid truncation bias.
- Both gpsim processes execute real firmware instructions (no semantic simplification), so instruction-level timing is preserved within each process.

**Where it diverges from real hardware:**
- **Perfect synchronization:** Real hardware CONTROL and MAIN MCUs have independent clocks. Over a 1-second run, a 0.1% crystal tolerance on each MCU means the two clocks can drift by up to 2 ms relative to each other. gpsim's scaling ensures perfect synchronization.
- **Deterministic execution:** Real firmware has data-dependent loop counts, cache behavior (on PIC18, minimal), and ADC conversion timing that varies with input. gpsim executes deterministically. A test that passes may still fail on hardware if firmware timing is close to an interrupt edge or UART edge.

**Failure modes it produces in tests:**
1. **False pass on clock-critical tests:** A test asserting that "MAIN's ACK arrives within 100 µs of CONTROL's request" will pass in gpsim but may fail on hardware if the actual arrival is 100 µs ± 5 µs of crystal jitter.

---

### EEPROM write timing (no direct simulation; relies on gpsim's default PIC18 EEPROM model)

**What it models:**
- PIC18 EEPROM write is triggered by setting EECON1 bits RD (read) or WR (write), then a brief wait.
- gpsim's built-in PIC18 EEPROM model reflects the register writes to the EEPROM array state after a latency.

**How faithfully:**
- gpsim's default EEPROM latency is negligible (single-cycle or a few cycles at most).
- Real PIC18 EEPROM writes take 2–10 ms per byte, depending on voltage and temperature, with no firmware visibility into completion time (the firmware must poll EECON1.WR to check if done, and even then the bit may take several cycles to clear).

**Where it diverges from real hardware:**
- **Write-complete latency:** A real EEPROM write (e.g., preset persistence byte at 0x74) takes 2–5 ms. gpsim completes it in nanoseconds.
- **Concurrent-write blocking:** Real PIC18 firmware cannot issue a second EEPROM write command until the previous one completes. The firmware typically polls EECON1.WR in a tight loop. gpsim completes before the poll loop can execute.

**Failure modes it produces in tests:**
1. **EEPROM race collapse:** Any test that initiates an EEPROM write (e.g., preset persistence) and then expects another subsystem to timeout waiting for that write to complete will see the timeout fail in gpsim (write already done) but pass on hardware (write still in progress).
   - **Affected test scenarios:** Preset-save + immediate IR injection; rare but possible in edge-case tests.

---

### MSSP fault injection (`set_mssp_stop_fault`, `clear_mssp_stop_faults` in `src/dlcp_fw/sim/chain_gpsim.py` line 438)

**What it models:**
- Injects MSSP (I2C) stop-condition delay via gpsim module attributes `ssp_stop_busy_cycles` and `ssp_stop_busy_count`.
- Firmware attempts a STOP condition, and gpsim delays the SSPCON2.PEN bit from clearing by the specified cycle count.
- Allows tests to reproduce bus-stuck scenarios where the I2C slave holds a line low, forcing firmware bus-clear (bitbang SCL to unstick).

**How faithfully:**
- The delay is accurate to the cycle count specified.
- Firmware sees the PEN bit held for the requested delay, matching the real hardware fault scenario.

**Where it diverges from real hardware:**
- **Fault trigger:** Real MSSP STOP faults are triggered by electrical SDA/SCL conditions (slave not releasing SDA, arbitration loss). gpsim must be told to inject the fault via test code. There is no automatic fault generation.
- **Recovery latency:** Real bus-clear (bitbang 9 SCL cycles) depends on I2C clock rate and slave response time. gpsim's bitbang is unobstructed because the I2C slave is simulated, so clock-stretching and SDA-stuck conditions must be manually configured via the `i2c_regfile` module to see realistic recovery times.

**Failure modes it produces in tests:**
1. **Incomplete bus-clear simulation:** A test asserting "after MSSP STOP fault, bus-clear succeeds and DSP ping works" will pass in gpsim only if the test explicitly sets up I2C fault conditions on the DSP slave (address NACK or SDA-stuck). If the test does not, the firmware's bus-clear succeeds in gpsim but would fail on hardware if the slave were actually stuck.
   - **Affected test:** `test_wire_mssp_stop_cascade_full_dsp_recovery` (line 245 of `test_v31_v163b_robustness.py`) currently passes because it manually configures `address_nack_count=60000` on the `dsp34` device, but without that configuration the test would be incomplete.

---

### IR injection (`inject_decoded_ir_event` in `src/dlcp_fw/sim/control_gpsim.py` line 768)

**What it models:**
- Bypasses the RB5 IR receiver waveform (RC6 modulation, 36 kHz carrier, Manchester coding).
- Directly writes decoded IR command and address to registers 0x01D and 0x01E, then clears the IR_ARMED bit at 0x01F.bit0 to trigger the foreground dispatch.

**How faithfully:**
- Once the IR dispatcher is triggered, the firmware's response is identical to real hardware.

**Where it diverges from real hardware:**
- **No waveform processing:** Real IR injection goes through gpsim's RB5 stimulus (not currently used in wire-mode harness), the PIC's edge detector, the Timer1 gate capture, and the firmware's RC6 decoder. Each step has timing: edge detection (~100 ns), Timer1 capture (~125 ns per bit at 2 µs/bit in RC6, 50 bits per code word = 100 µs per code), Manchester decode in firmware (~50 µs). Total: ~200 µs to dispatch an IR event in hardware. gpsim bypasses all of this and dispatches in one register write.
- **Timing race collapse:** A test asserting "during preset-apply, an IR event can interrupt and force mute" will pass in gpsim because the IR dispatch is instantaneous, ensuring it happens during the (collapsed) apply window. On hardware, the IR must be received and decoded (200 µs) while the apply is still in flight (600 ms), which is a generous window. But if the apply window is actually ~100 ms shorter than the test expects, hardware might miss the race.

**Failure modes it produces in tests:**
1. **IR timing insensitivity:** Any test timing an IR event relative to preset-apply will not catch race conditions that hardware would expose.
   - **Affected test scenarios:** Mute/unmute during preset switch, volume change during preset load.

---

### Front-panel button presses (`chain.press(...)` in `src/dlcp_fw/sim/chain_gpsim.py` line 970)

**What it models:**
- Calls `control.press(key)` (line 370 in `control_gpsim.py`), which injects button debounce RAM state via `_apply_key_levels` (line 852).
- Firmware's debounce routine treats the RAM state as a newly pressed button and triggers the associated handler.

**How faithfully:**
- Once the button handler is triggered, the firmware's response is identical to real hardware.

**Where it diverges from real hardware:**
- **No debounce timing:** Real hardware buttons are debounced by firmware polling over ~40 ms (typical de-bounce interval). gpsim injects the debounced state directly into RAM, skipping the 40 ms polling phase.
- **No contact chatter:** Real buttons can bounce (multiple presses before settling). gpsim injects a clean state.

**Failure modes it produces in tests:**
1. **Debounce timing collapse:** A test asserting "button press interrupts a long-running command" will pass in gpsim (button dispatched immediately) but might fail on hardware if the command finishes before the 40 ms debounce window closes. Rare, but possible in millisecond-scale timing tests.

---

### LCD readback / OCR-equivalent (`chain.lcd_lines()` in `src/dlcp_fw/sim/chain_gpsim.py` line 961)

**What it models:**
- Parses gpsim's log file for HD44780 DDRAM write commands (firmware writes to port C + LATCH latches, simulating address lines).
- Reconstructs the 16×2 LCD display from the write sequence.

**How faithfully:**
- The HD44780 state machine is accurately modeled by `LcdState` (src/dlcp_fw/sim/lcd.py), including DDRAM addressing, cursor movement, and character write sequences.
- gpsim's port logging captures every port write, so no LCD transitions are missed.

**Where it diverges from real hardware:**
- **Character encoding:** gpsim's reconstruction assumes the firmware writes valid ASCII or standard HD44780 characters. If firmware writes garbage or relies on custom character ROM definitions (CGRAM), gpsim may display incorrect text. Real hardware would show the custom character bitmap.
- **Timing independence:** Real LCD writes involve setup/hold times and clock edges. gpsim does not model these.

**Failure modes it produces in tests:**
1. **LCD encoding mismatch:** A test asserting "LCD shows 'WAITING FOR DLCP'" will pass if the firmware's write sequence produces that string via standard ASCII codes. If the firmware uses custom CGRAM characters, gpsim will show garbage while hardware shows the correct display. Very rare.

---

## Test-class fidelity matrix

| Test Category | gpsim Faithful? | Why | What this means for release gate |
|---|---|---|---|
| **Preset-apply APPLY-vs-IR/button race** | Yes (measured 2026-04-18) | V1.71 CONTROL + V3.2 MAIN two-MAIN probe: 1,780 ms apply window, IR arrives at +20 ms, race resolves with both preset and mute preserved. See [correction](#2026-04-18-correction--tas3108--preset-apply-collapse-claim-retracted-by-measurement). | **Trust gpsim alone** for functional correctness of the race. Hardware still recommended for absolute timing bounds. |
| **Preset-apply APPLY-vs-serial mute** | Yes (measured 2026-04-18) | Same 1,780 ms window measured end-to-end; serial-path mute lands via the same UART bridge as IR-emitted mute. | **Trust gpsim alone** for functional correctness. |
| **MSSP STOP → bus-clear → DSP recovery** | Mostly | MSSP delay injection works; bus-clear depends on I2C slave fault setup (clock-stretch or SDA-stuck) being correct; incomplete if those faults are not configured | **Use both gpsim AND hardware**; gpsim passes only if you manually configure realistic slave faults |
| **UART chain byte forwarding, no races** | Yes | UART EUSART RX state machine is cycle-accurate; no race condition present | **Trust gpsim alone** |
| **UART chain UART-error recovery (OERR)** | Mostly | EUSART OERR flag is set correctly by gpsim on overrun, but overrun condition is unlikely unless you artificially stress the link; gpsim's zero-latency bridge does not naturally produce the jitter that causes real overruns | **Use both gpsim AND hardware** |
| **USB HID command dispatch (cmd 0x03)** | Yes | Instruction-level simulation; firmware's register state and control flow are deterministic | **Trust gpsim alone** |
| **USB HID command ISR timing** | Mostly | ISR dispatch is cycle-accurate, but interrupt latency assumes no competing hardware peripherals (I2C, UART, ADC); in gpsim, I2C is zero-latency so high-priority ISRs always respond immediately | **Use both gpsim AND hardware** for time-critical ISR tests |
| **IR endpoint dispatch (button press during idle)** | Yes | IR inject is instantaneous (not realistic timing), but once dispatched the firmware path is deterministic | **Trust gpsim alone** for functional dispatch; not for timing |
| **IR dispatch during MAIN activity** | No-with-bias | IR dispatch is instantaneous, so it always "wins" against any competing firmware activity; on hardware it might lose | **Hardware-only release gate** for race scenarios |
| **Preset-apply soak under reconnect + full-sync** | Mixed | V1.71 Layer 2 full-sync cadence (one frame per step) is slower than V1.6b burst. gpsim timing at 33 kHz SCL is faithful (see correction above), but clock-perfect execution still hides jitter-induced sync loss that real crystals would produce. | **Use both gpsim AND hardware**; gpsim verifies firmware state-machine correctness, hardware verifies convergence under real clock jitter. |
| **EEPROM persistence (preset save + load)** | Mostly | EEPROM writes complete instantly in gpsim (2–5 ms on hardware), so back-to-back EEPROM access never races; but single EEPROM writes are correct once complete | **Use both gpsim AND hardware** for multi-second EEPROM sequences |
| **Clock skew / jitter tests** | No | gpsim uses perfect integer clocks; no crystal drift, no phase noise | **Hardware-only release gate** |
| **Timing-sensitive LED blink rates** | Mostly | Timer counters are accurate, but jitter from other peripherals (UART interrupt latency, I2C clock-stretching) can cause small phase shifts; gpsim removes that jitter | **Use both gpsim AND hardware** |
| **Multi-minute soak tests** | Mostly | Deterministic execution means gpsim will not discover rare race conditions that only occur on hardware under load; but functional correctness (no hang, no crash) is verified | **Use both gpsim AND hardware** |

---

## Specific known-broken cases

### V3.2 wire-chain tests (delayed-switch repro suite)

**`test_v32_wire_two_main_interleaved_mute_during_delayed_switch_preserves_state`** (line 695 of `test_v28_wire_delayed_switch_repros.py`)
- ~~**Exact gap:** TAS3108 I2C coefficient write (preset apply, 97 bytes) collapses to 1 instruction cycle.~~ **[Retracted 2026-04-18]**
- **Measured gpsim behavior (V1.71 CONTROL + V3.2 MAIN):** 1,780 ms two-MAIN apply window; IR mute arrives at +20 ms and the firmware correctly resolves the race to `preset=1 muted=1` on both MAINs. Raw probe data is in the [correction section](#2026-04-18-correction--tas3108--preset-apply-collapse-claim-retracted-by-measurement).
- **Recommendation:** remove the xfail on this test. If the user-facing failure reappears, the cause is not the originally-assumed byte-timing collapse; re-investigate with the probes on branch `feature/gpsim-i2c-fidelity-probe` or run similar probes against the specific failing pair.

**`test_v32_wire_two_main_preset_soak_under_reconnect_and_full_sync_keeps_both_mains_responsive`** (line 835 of `test_v28_wire_delayed_switch_repros.py`)
- **Partial retraction 2026-04-18.** The "zero-latency UART bridge" claim is not supported by measurement (the same IR-race probe shows ~20 ms CONTROL → MAIN latency). What *is* unexposed in gpsim is real crystal jitter and independent clock drift across MCUs — gpsim's perfect integer clocks remove that source of sync loss.
- **Expected behavior on hardware:** After reconnect, full-sync must converge (all 6 channels synced) within ~1 minute. Under clock jitter and UART timing variation, convergence may stall if the frame rate is too slow. V1.71 L2 timing was calibrated on hardware.
- **gpsim behavior:** Converges in deterministic cycles, no timeout. Timing is faithful at SCL-clocking level but jitter-free.
- **Status:** Hardware validation still recommended for the convergence-under-jitter guarantee, but a pure `xfail(strict=True)` in gpsim is too strong — the test likely passes and would need `XPASS` handling. Consider either (a) removing the xfail and letting it pass, or (b) converting to a skip with `reason="jitter-under-load is a hardware-only property"`.

### V3.1 robustness test

**`test_wire_mssp_stop_cascade_full_dsp_recovery`** (line 245 of `test_v31_v163b_robustness.py`)
- **Exact gap:** MSSP STOP fault injection + bus-clear bitbang depend on I2C slave clock-stretching behavior. gpsim's `i2c_regfile` module correctly simulates SCL-hold via `Address_Stretch_SCL_Cycles`, but the test must manually configure this fault, and gpsim does not auto-discover slave stuck conditions.
- **Expected behavior on hardware:** After MSSP STOP fault, firmware bitbangs 9 SCL cycles to unstick the slave. If the slave is truly stuck (SDA held low), bus-clear fails and DSP ping never succeeds. If bus-clear succeeds, DSP accepts a ping at the probe address (0x34). Real TAS3108 may take 1–2 ms to release SDA after SCL is pulsed.
- **gpsim behavior:** Test passes if it explicitly configures `address_nack_count=60000` on the `dsp34` device to simulate a stuck slave. Without that, bus-clear "succeeds" (no I2C fault) and DSP ping succeeds, but the test does not validate that the slave was actually stuck and then recovered.
- **Status:** Test does configure the fault correctly, so it passes. But the test framework would not auto-detect incomplete fault setup if a developer forgot to configure the slave fault.

### V2.7 robustness (stock V2.6 + V1.62b CONTROL)

**`test_main_bus_clear_recovers_after_mssp_stop_fault` → `test_main_dsp_ping_latches_fault_on_persistent_nack`** (line 128 and 177 of `test_v27_v163b_robustness.py`)
- **Status:** These tests pass in gpsim because they manually configure I2C slave faults. Same principle as the V3.1 test above.

---

## Recommendations

### Trust gpsim alone (release gate without hardware)

- **USB HID command dispatch** (cmd 0x03 control-flow path): Instruction-level simulation, no race condition involved.
- **UART chain forwarding** (single-main, no timing race): EUSART RX is cycle-accurate; no artificial jitter needed.
- **IR decode dispatch** (functional check, not timing): Once IR is injected, firmware path is deterministic.
- **Preset-apply completion** (no race): A test that only checks "after preset apply, DSP coeff X is written" will pass in gpsim and hardware alike.
- **Preset-apply IR/button/mute races** (functional correctness, added 2026-04-18): Measured 1,780 ms two-MAIN window, IR lands at +20 ms, firmware correctly preserves both preset and mute bits. See the [correction section](#2026-04-18-correction--tas3108--preset-apply-collapse-claim-retracted-by-measurement).

### Use both gpsim AND hardware (validation gate)

- **ISR timing tests**: Interrupt latency can vary on hardware due to competing peripherals; gpsim's zero-latency I2C masks this.
- **UART OERR recovery**: Overrun conditions are rare in gpsim's ideal link; hardware may surface them under load.
- **EEPROM multi-write sequences**: Firmware that writes multiple EEPROM bytes in quick succession must not assume immediate readback. gpsim's instant completion is optimistic.
- **MSSP fault injection + bus-clear**: Require both gpsim (to verify firmware state machine correctness) and hardware (to confirm I2C recovery timing).
- **LED timing / blink rates**: Verify functional correctness in gpsim, then measure actual jitter on hardware.
- **Multi-minute soak tests**: gpsim will not discover rare race conditions triggered only by load or jitter.

### Hardware-only release gate

- ~~**Preset-apply race windows**: APPLY vs IR/button/mute — the collapsed I2C timing in gpsim makes these races disappear.~~ **[Retracted 2026-04-18]** — these races work in gpsim; see the [correction section](#2026-04-18-correction--tas3108--preset-apply-collapse-claim-retracted-by-measurement). Move to "Trust gpsim alone" for functional correctness; hardware still useful for absolute timing bounds.
- **V1.71 Layer 2 convergence timing under clock jitter**: Full-sync cadence is faithful in gpsim at the SCL-clocking level, but gpsim's perfect integer clocks do not expose sync loss caused by independent crystal drift on the two MCUs.
- **Clock skew / jitter tests**: gpsim's perfect clocks do not expose real hardware sensitivity to crystal tolerance.
- **Extended stress tests** (>1 hour): Deterministic gpsim execution will not discover rare failure modes triggered by long uptime or thermal drift.

---

## Sizing the gap

### ~~Most impactful gap: TAS3108 I2C byte timing~~ [retracted 2026-04-18 — not a gap]

**Retraction:** The 97-byte preset apply does NOT collapse to 1 instruction cycle. Direct measurement of gpsim shows 720 ms single-MAIN / 1,780 ms two-MAIN apply windows (vs. ~600 ms on hardware), and the IR-mute-during-apply race resolves correctly. See the [correction section at the top](#2026-04-18-correction--tas3108--preset-apply-collapse-claim-retracted-by-measurement).

No fix is needed in gpsim's `i2c_regfile` module for byte timing. The earlier fix proposal in this section (adding `Byte_Time_Cycles`) would solve a non-problem. The post-STOP 5 ms write-completion delay is still an unmodeled detail but no test currently depends on it.

### Second-order gap: UART clock jitter and timing causality

**Current state:** `_StreamingUartBridge` shifts batches of UART edges forward to enforce causality when the receiver clock outpaces the sender, losing sender→receiver timing without warning (line 169 in `wire_chain_gpsim.py`).

**Fix scope:**
1. Make `bridge_shift_warn_threshold` default behavior: all wire-chain tests receive a warning if shifts occur.
2. Track per-byte shift amount (not just per-batch) to expose sub-frame timing loss.
3. Optionally: implement optional RNG-based clock jitter injection (±0.5% per MCU) to simulate real crystal tolerance.

**Estimated effort:** 1–2 days (instrumentation + optional jitter RNG).

**Impact:** Catches tests that rely on precise sender→receiver timing without knowing it. Would have caught the Layer 2 convergence timing issue earlier.

### Third-order gap: IR and button injection latency

**Current state:** IR and button events are injected instantaneously (register writes), bypassing firmware's real ISR latency (~200 µs for IR, ~40 ms for debounce).

**Fix scope:**
1. Add optional `inject_ir_with_latency(...)` and `press_with_debounce_latency(...)` methods that schedule the actual register write for N cycles in the future.
2. Default: keep current instant behavior for fast CI.
3. Opt-in: tests that care about race windows can call the latency-aware methods.

**Estimated effort:** <1 day (add thin wrapper methods, no gpsim changes needed).

**Impact:** Allows selective race-window testing for IR/button scenarios without slowing down the rest of the test suite.

---

## Closing note

gpsim is a powerful tool for firmware regression and functional testing, but it is not a substitute for hardware validation when timing, races, or load-dependent behavior is involved. This document's recommendations are meant to help you decide which tests can safely rely on gpsim and which must include a hardware gate. As we verify harness fidelity (as was done for I2C byte timing on 2026-04-18), more tests should migrate from "hardware-only" to "use both" and eventually to "trust gpsim alone."

When you encounter a test failure that "looks like a race," check the [Specific known-broken cases](#specific-known-broken-cases) section first. If the test is not listed, consult the [Test-class fidelity matrix](#test-class-fidelity-matrix) for its category, and use the "What this means for release gate" column to decide whether to:
1. Debug the firmware (test is in "trust gpsim" band).
2. Check gpsim instrumentation (test is in "use both" band; may need manual verification in gpsim output).
3. Move directly to hardware (test is in "hardware-only" band).

**Before assuming gpsim has collapsed a timing window, measure it.** The 2026-04-18 correction above exists because an initial hypothesis based on code inspection proved wrong under direct measurement. When a similar "gpsim must be collapsing X" theory arises, write a targeted probe (the two scripts on `feature/gpsim-i2c-fidelity-probe` are concise templates) and confirm with cycle counts before planning a fix.

---

## Changelog

- **2026-04-18** — Retracted the TAS3108 I2C byte-timing collapse claim after measuring 720 ms single-MAIN / 1,780 ms two-MAIN apply windows in gpsim (vs. ~600 ms on real hardware). Updated the TAS3108 component section, the preset-apply matrix rows, the two V3.2 "known-broken" entries, the "Sizing the gap" section, and the Trust/Hardware-only recommendations accordingly. Probe scripts and sample output are on branch `feature/gpsim-i2c-fidelity-probe` under `scripts/probe_gpsim_i2c_byte_timing.py` and `scripts/probe_ir_vs_apply_race.py`. UART bridge causality-shift and IR/button injection latency claims left untouched pending their own measurement.
- **2026-04-15** (initial draft) — Initial audit based on code inspection; subsequently superseded in part by the 2026-04-18 measurement.
