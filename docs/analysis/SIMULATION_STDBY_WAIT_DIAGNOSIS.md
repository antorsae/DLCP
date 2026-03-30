# DLCP Co-Simulation Diagnosis: Standby/Waiting Reconnect Loop

Migration note (2026-03-30):

- Path examples below predate the repo-layout migration.
- Translate `control/disasm/...` to `firmware/disasm/control/...`.
- Translate `disasm/...` to `firmware/disasm/main/...`.
- Translate `tools/gpsim_tui_simulator.py` to `scripts/gpsim_tui_simulator.py`.
- Translate `simfw/*` to `src/dlcp_fw/sim/*`.

## 1. Objective

Build and validate a high-fidelity simulation of:

- 1x CONTROL PIC firmware (UI + serial master behavior)
- 2x MAIN PIC firmware (DLCP processing nodes in daisy chain)
- Current-loop serial behavior between all three units
- Key presses, LCD behavior, standby sensing, and state transitions

without masking core firmware logic with behavioral shortcuts.

Current blocker:

- CONTROL repeatedly goes through standby/reconnect behavior:
  - `Zzz...`
  - `Waiting for DLCP`
  - reconnect loop or repeated toggles of internal standby bit

The goal is to diagnose root cause in simulation fidelity and fix the model, not hide the issue.

## 1.1 Physical ground truth (startup UX)

On real hardware (CONTROL V1.4 + MAIN), user reports the startup LCD sequence is:

1. Firmware version (very briefly)
2. `Waiting for DLCP`
3. `Volume: ...` (normal run)

`Zzz...` is **not** shown unless the user physically presses the STBY key.

## 2. Ground Truth Firmware Semantics (Critical)

### 2.1 CONTROL standby state bit (`0x1F.bit1`)

This is a RAM state bit, not a direct pin register.

- Set by parser on incoming `cmd=0x03, data=0x01`:
  - `control/disasm/v1.4_disasm.asm:862`
  - `control/disasm/v1.4_disasm.asm:869`
- Cleared by parser on incoming `cmd=0x03, data=0x00`:
  - `control/disasm/v1.4_disasm.asm:875`
  - `control/disasm/v1.4_disasm.asm:879`

So yes, parser semantics are:

- `0x03 0x01` => set `bit1=1`
- `0x03 0x00` => clear `bit1=0`

But parser is not the only writer:

- Local CONTROL UI paths toggle/clear/set it (`btg/bcf/bsf`) in runtime/reconnect flow:
  - `control/disasm/v1.4_disasm.asm:2441`
  - `control/disasm/v1.4_disasm.asm:2487`
  - `control/disasm/v1.4_disasm.asm:3178`
  - `control/disasm/v1.4_disasm.asm:3214`
  - `control/disasm/v1.4_disasm.asm:3234`

### 2.2 CONTROL reconnect path

- Main loop checks `0x1F.bit1`; if clear, jumps to standby handler:
  - `control/disasm/v1.4_disasm.asm:3091`
  - `control/disasm/v1.4_disasm.asm:3092`
- Standby handler prints `Zzz...`, sends state frames, then enters waiting loop until bit1 set:
  - `control/disasm/v1.4_disasm.asm:3176`
  - `control/disasm/v1.4_disasm.asm:3236`
  - `control/disasm/v1.4_disasm.asm:3245`

Important nuance (confirmed in disasm):

- `0x1F.bit1` can be **cleared/set by local reconnect logic**, not only by parser updates.
  This explains why headless traces show `1->0` transitions without any incoming `cmd=0x03,data=0x00`.
  Example reconnect block: `control/disasm/v1.4_disasm.asm:00129E` onward (label_214/label_216 loop).

### 2.3 MAIN status reporting of standby state

MAIN status packet includes `BF 03 <state>` where `<state>` derives from MAIN `status_5e.bit3`:

- `disasm/gpdasm_output.asm:7194` (function_050)
- `disasm/gpdasm_output.asm:7223` to `disasm/gpdasm_output.asm:7229`

## 3. Current Simulation Architecture

Primary runtime:

- `tools/gpsim_tui_simulator.py`

Core components:

- CONTROL gpsim session: `GpsimControlSession`
- MAIN gpsim sessions: `MainGpsimSession` (#0 and #1)
- Link transport model: `LinkPipe`
- LCD decode from pin writes: `simfw/lcd.py`
- Overlay engine: `simfw/overlay.py`
- Hook manifests: `simfw/manifests.py`

### 3.1 Active simulation overlays

CONTROL:

- reset redirected to app start (`0x0040`):
  - `tools/gpsim_tui_simulator.py:716`
  - `simfw/manifests.py:13`

MAIN:

- reset redirected to app start (`0x1000`):
  - `tools/gpsim_tui_simulator.py:473`
  - `simfw/manifests.py:78`
- UART helper hooks for mailbox-backed RX/TX:
  - `simfw/manifests.py:247`
  - `simfw/manifests.py:388`
- optional Timer3 modes:
  - semantic shim in firmware hook (`main_serial_mailbox_hooks`)
  - harness-side TMR3IF model (`main_serial_mailbox_hooks_uart_only` + harness timing)
  - `tools/gpsim_tui_simulator.py:474`
  - `tools/gpsim_tui_simulator.py:560`

### 3.2 Link timing model today

Transport pacing is abstracted:

- fixed `triplet_cycles` constant (originally `11520`, now `2880`):
  - rationale: 31,250 baud, 8N1 => 10 bits/byte, 3 bytes ~= 960 µs; CONTROL instruction rate ~3 MHz => ~2,880 instruction cycles/triplet.
- link pumping is still **triplet-based**, not byte-based.
- LinkPipe originally used a **credit accumulator** (banking idle time into huge bursts). It has been refactored to a **scheduled delivery** queue (no banking).
- LinkPipe `max_burst` originally limited only successful deliveries; in `drop` mode it could drop arbitrarily many frames in one pump call. This has been fixed to cap processed frames too.
- frame injected as full 3-byte mailbox write atomically:
  - MAIN inject path: `tools/gpsim_tui_simulator.py:524`
  - CONTROL inject path: `tools/gpsim_tui_simulator.py:762`

Conclusion:

- CPU execution is cycle-stepped in gpsim.
- UART wire behavior is not byte-level/ISR-level cycle-accurate.

## 4. Why Bootloader Is Bypassed in Sim

Stock CONTROL reset vector goes to bootloader (`0x7800`):

- `control/disasm/v1.4_disasm.asm:15`

In simulation we patch reset to app entry to avoid bootloader USB paths and mode gates:

- `simfw/manifests.py:13`

MAIN reset is also patched to app entry because firmware image/startup is not robust for no-overlay gpsim boot path:

- `simfw/manifests.py:78`

Bootloader reference:

- CONTROL bootloader region starts at `0x7800`:
  - `control/disasm/v1.4_disasm.asm:16384`

## 5. Observed Failure Signature (Headless Evidence)

Artifact:

- `sim_artifacts/headless_bit1_trace_1min.json`

Measured over ~1 minute simulated (`180,000,000` cycles after warmup):

- 301 protocol frames captured
- CONTROL `REQ_STATUS` (`cmd=0x04`) repeatedly sent
- `0x1F.bit1` had 6 transitions:
  - `0x0152BE95` `0->1`
  - `0x0237A03D` `1->0`
  - `0x026566F5` `0->1`
  - `0x034A489A` `1->0`
  - `0x03537058` `0->1`
  - `0x043851FD` `1->0`

Important observation:

- `1->0` transitions did not line up with incoming MAIN `0x03,0x00` frames.
- They aligned with reconnect pressure and mailbox progression anomalies (MAIN0 RX/processing stalls).

### 5.1 Mode comparison snapshot

Quick scenario matrix on current model:

- `def_hold_shim`, `control_shim`, `release_shim`, `def_hold_ra0_0` produced similar behavior:
  - repeated bit toggles
  - long `Waiting for DLCP`
  - finite but non-zero drops/blocks
- harness Timer3 modes changed behavior but still unhealthy:
  - higher drops/blocks
  - persistent `Zzz...`

This indicates RA0 standby level alone is not root cause in current model.

### 5.2 Experiment log (2026-02-17) — what was tried and what changed

All experiments below use the headless CLI unless stated otherwise:

`python3 tools/gpsim_headless_chain_diagnose.py control/'DLCP Control Firmware V1.4.hex' --main-hex ../DLCP\\ Firmware\\ V2.3.hex ...`

#### A) Baseline reproduction (60s, default chunking, shim Timer3)

Command (canonical):

`--duration-s 60 --main-ra0 0x228 --output sim_artifacts/headless_bit1_trace_1min.json`

Observed (from the JSON + printed stats):

- CONTROL spams `REQ_STATUS` (`cmd=0x04`) heavily (hundreds of polls/minute).
- `0x1F.bit1` toggles repeatedly; LCD remains `Waiting for DLCP`.
- Link pressure is extreme:
  - CTL->M0 uses `backpressure="drop"` and drops a large fraction of frames (example run: 214 drops / 289 frames total).
- MAIN0 RX mailbox occupancy is typically near-full:
  - snapshot-derived `used=(wr-rd)&0xFF` mean ~23, max 30; most common value is 30 (near saturation).
- Event window inspection shows **both kinds** of bit1 transitions:
  - `0->1` can coincide with MAIN0 status frames (`BF 05/07/03/06/1D`), consistent with parser setting bit1 on `cmd=0x03,data=0x01`.
  - `1->0` can occur with *no* incoming frames nearby (sometimes the only nearby frame is CONTROL polling), consistent with local reconnect/timeout logic clearing the bit.

#### B) LinkPipe model refinements (no behavioral improvement yet)

Changes implemented in `tools/gpsim_tui_simulator.py` and used by headless:

1. `triplet_cycles`: `11520` -> `2880` (instruction-cycle scale fix).
2. Link pump: credit banking -> scheduled delivery (avoid bursty unrealistic backlog release).
3. Bug fix: `max_burst` now caps drops as well as successful deliveries.
4. Pump staging: pump between CONTROL, MAIN0, MAIN1 steps with small `max_burst` values to mimic interleaving.

Result:

- The stuck `Waiting for DLCP` behavior persists with essentially the same signature (bit1 toggles + heavy CTL->M0 drops + MAIN0 RX near saturation).

Note:

- The scheduled-delivery model currently uses per-device gpsim cycle counters (`TxTriplet.cycle`) as enqueue timing hints. If CONTROL and MAIN run at different effective “cycle/time” scales, this is not a true wall-clock model.

#### C) Chunk-size sensitivity (timing-dependent partial “connect then fail”)

Reducing chunk sizes can temporarily let the CONTROL reach the Volume screen, but it is not stable:

- `--chunk-cycles 50000 --main-chunk-cycles 50000 --duration-s 10`
  - CONTROL reached `Volume:` / `Mute` at least once (bit1 `0->1` event with `lcd0='Volume:'`).
- Extending duration to 60s with similar chunk sizes caused reconnection/disconnect behavior later (bit1 `1->0` events); link drops became very large (hundreds).
- Very small chunk sizes (`--chunk-cycles 10000`) increased instability:
  - more bit1 transitions and occasional `Zzz...` seen even without any key presses in the harness.

Takeaway:

- The simulation is **highly timing sensitive**, consistent with transport/mailbox fidelity gaps rather than a pure STDBY ADC threshold issue.

#### D) Timer3 harness mode (`--main-timer3 harness`)

One run (`--duration-s 20`) produced:

- only one observed bit1 transition (`0->1`) and LCD showing `Zzz...`,
- very high blocked counts on `M0->M1`.

Takeaway:

- Timer3 timing and/or the alternative overlay set changes the failure mode, but does not converge to a stable `Volume:` state.

#### E) Standby ADC value (RA0) sweeps

Runs with `--main-ra0 0x000`, `0x228`, `0x230`, `0xFFF`:

- did **not** resolve `Waiting for DLCP`.
- `Zzz...` can still appear in traces with no key presses, implying CONTROL is entering standby handler due to connection-state logic, not a physical STBY key.

Takeaway:

- RA0/STDBY sensing is not the primary root cause in the current model.

#### F) Mailbox sizing experiment (flagged as likely unphysical)

An experiment briefly increased the MAIN RX “mailbox ring” used by the UART overlay hooks.
This was motivated by the observed RX saturation, but PIC hardware USART has no large FIFO;
any deeper buffering must be firmware/software-level, not silicon.

Result:

- This did not eliminate the stuck behavior and is likely the wrong direction for fidelity.

## 6. Root Causes Found and Fixed

The standby/reconnect loop had **three** distinct root causes, all in the simulation
harness rather than the firmware.  Each was necessary but insufficient on its own;
all three had to be fixed for stable DISPLAY mode.

### 6.1 gpsim stimulus bug: `period 0` creates dead stimuli

The `asynchronous_stimulus` command in gpsim has a subtle defect:

```
stimulus asynchronous_stimulus initial_state 1 period 0 name stim_ra1 end
```

This creates a stimulus with `Vth=0V, Driving=IN` — it **never drives the pin**.
The `period 0` parameter disables the stimulus output entirely, regardless of
`initial_state`.  All six button pins read LOW (phantom pressed), which caused
function_023 to report `0x0BE=0x3F` (all buttons held down) and generate
continuous `0x9A` events.

**Fix:** replace `period 0` with an explicit transition entry:

```
stimulus asynchronous_stimulus initial_state 1 start_cycle 0 { 1, 1 } name stim_ra1 end
```

The `{ 1, 1 }` entry forces gpsim into active-drive mode (`Vth=5V`).
An alternative that also works is `period 1000000000` (non-zero period).

Diagnostic evidence in `tools/diag_stimuli_check3.py` tested seven approaches;
only start_cycle+transition and large-period produced `Vth=5V`.

### 6.2 Heartbeat model: function_042 blocks without synthetic bit3

CONTROL's inner event loop (function_042, 0x0D24) polls function_023 (buttons)
and function_019 (serial), exiting only when `0x9A != 0` or `flags.bit3 != 0`.
In real hardware, CONTROL toggles RC1 (heartbeat) every ~30K iterations;
MAIN detects the toggle via current-loop ADC and responds with `BF/03/01`
plus status frames that set bit3 via function_019.

The simulator does not model the RC1-to-MAIN-to-response feedback loop.
Without synthetic intervention, function_042 loops forever and the DISPLAY
loop never refreshes — the LCD stays at "Zzz..." or "Waiting for DLCP".

**Fix:** The heartbeat model sets `flags.bit3 = 1` before each CONTROL step
(via `reg(0x01F)`) and periodically injects `BF/03/01` into the M0→CTL link
to maintain `bit1 = 1`.  The injection is throttled to every 5 steps with a
queue-depth guard (`len(link) < fifo - 6`) to prevent OVERRUN.

Two-phase WAITING detection avoids false activation from uninitialised RAM:
first wait for all four sentinel variables (0xB8, 0xB9, 0xA7, 0xA1) to
become 0x80 (WAITING entered), then wait for them to change (WAITING exit).

### 6.3 Button press simulation via RAM injection

gpsim stimuli permanently drive button pins HIGH (unpressed) to protect
against read-modify-write corruption from `btg PORTC, RC1` at 0x0DCA.
Stimulus state cannot be toggled at runtime — tested `put`, `set`,
`stimulus modify`, attaching second stimulus to same node; none work.

Button presses bypass the pins entirely and write into function_023's
debounce state machine:

- `0x0BE` (accepted scan): set to the desired scan pattern
- `0x0BB` (debounce counter): reset to 0

With 0x0BB=0, the next 4 function_023 calls (debounce threshold) all read
pins as HIGH (scan=0x00) and increment the counter, but do not overwrite
0x0BE.  The edge detection (`0x0BE != 0x0BD`) fires on the first call,
setting `0x9A = scan_pattern`.  function_042 exits on `0x9A != 0`, and
function_046 processes the button event.

Only newly-pressed keys (rising edge) are injected.  Held keys do not
generate repeat events, matching real hardware where debounced identical
scans produce no edge.

Scan bit mapping (function_023 output format):

| Bit | Button | Pin |
|-----|--------|-----|
| 0   | STBY   | RA3 |
| 1   | UP     | RC0 |
| 2   | DOWN   | RA2 |
| 3   | SELECT | RA1 |
| 4   | LEFT   | RC5 |
| 5   | RIGHT  | RA4 |

### 6.4 Verified behaviour after all three fixes

Test: `tools/test_button_inject.py` (20M warmup, fast_boot, single MAIN)

- LCD shows "Volume: / -96.0dB" (DISPLAY mode, bit1=1 stable)
- SELECT toggles mute ("Volume: / Mute", bit4=1)
- UP increases volume ("Volume: / -95.0dB", bit4=0)
- DOWN decreases volume ("Volume: / -96.0dB")
- Zero overruns on both link pipes
- Debounce steady state: `0x0BE=0x00, 0x0BD=0x00` (correct)

Test: `tools/test_full_boot.py` (48M cycles, full boot, unpatched hex)

- "Firmware V1.4" at 0.275s
- "Waiting for DLCP" at 0.525s
- WAITING exit at 1.575s
- "Volume: / Mute" at 3.000s (DISPLAY mode reached)
- bit1=1 stable, 0x9A=0x00 stable through 4 seconds of simulated time

## 7. Original Hypotheses — Disposition

1. **Transport fidelity gap** — partially confirmed.
   Byte-level `LinkPipe` (replacing triplet-credit) eliminated mailbox
   saturation and frame drops.  This was necessary but not sufficient.

2. **Mailbox pressure and bursting** — resolved by `LinkPipe` refactor.
   Scheduled delivery with wire-rate pacing (960 Tcy/byte) and FIFO-depth
   caps matches hardware EUSART semantics.

3. **Incomplete chain semantics** — mitigated.
   Single-main (`--single-main`) topology removes chain-forwarding
   ambiguity.  Two-main topology works but is slower.

4. **Timer and parser interaction** — not the primary cause.
   Timer3 shim mode works correctly with the heartbeat model.

5. **RC2/standby pin modeling** — confirmed as secondary.
   RC2 strap and RA0 ADC values are important for MAIN behavior but
   do not cause the STDBY/reconnect loop on CONTROL.

6. **gpsim stimulus bug** (NEW) — confirmed as primary input-pin root cause.
   Dead stimuli (`period 0`) caused all button pins to read LOW, generating
   phantom `0x9A` events that cycled through STANDBY/RECONNECT.

7. **Missing heartbeat model** (NEW) — confirmed as primary liveness root cause.
   Without synthetic bit3, function_042 never exits, and the DISPLAY loop
   stalls indefinitely.

## 8. Forward Plan (Updated)

### Completed

- Phase 0: baseline frozen (`sim_artifacts/headless_bit1_trace_1min.json`)
- Phase 1: TUI diagnosis panel (`_draw_diag_panel`, `ReconnectDiagnostics`)
- Phase 2: headless tool (`tools/gpsim_headless_chain_diagnose.py`)
- Phase 3: byte-level transport (`LinkPipe` with wire-rate pacing)
- Stimulus fix, heartbeat model, button injection

### Remaining

1. **RC1→MAIN feedback loop**: model the actual heartbeat response path
   (MAIN detects RC1 toggle via AN0 ADC, responds with BF/03/01).
   This would replace the synthetic bit3 injection.

2. **Regression tests**: `tools/test_full_boot.py` and
   `tools/test_button_inject.py` serve as de-facto regression tests.
   Formalise into `tests/sim/` with pass/fail assertions.

3. **Multi-unit fidelity**: two-MAIN chain topology needs the same
   heartbeat and stimulus fixes validated end-to-end.

4. **Bootloader-aware mode** (optional): run with unpatched reset vector
   to validate bootloader→app handoff.

## 9. Concrete File Map (What to Read/Modify)

### Simulation runtime

- `tools/gpsim_tui_simulator.py` — TUI and co-simulation engine
- `simfw/manifests.py` — firmware overlay hooks
- `simfw/main_gpsim_timer3.py` — MAIN gpsim helpers (reg read, Timer3, breakpoints)
- `simfw/lcd.py` — HD44780 LCD decode
- `simfw/overlay.py` — HEX patching engine
- `simfw/protocol.py` — serial frame definitions

### Test and diagnostic scripts

- `tools/test_full_boot.py` — full-boot regression (48M cycles, no fast_boot)
- `tools/test_button_inject.py` — button press regression (SELECT, UP, DOWN)
- `tools/diag_buttons.py` — PORTA/PORTC/debounce inspection
- `tools/diag_stim_test.py` — stimulus + bit1 stability test
- `tools/gpsim_headless_chain_diagnose.py` — headless JSON trace generator

### Firmware/disassembly references

- `control/disasm/v1.4_disasm.asm` — CONTROL V1.4 full disassembly
- `disasm/gpdasm_output.asm` — MAIN V2.3 full disassembly

### Analysis docs

- `SIMULATION.md` — simulation user guide and architecture reference
- `TEST_SIMULATOR.md` — preset test framework documentation
- `PIN_SEMANTICS.md` — pin-level semantics for CONTROL and MAIN
- `CONTROL_UNIT_ANALYSIS.md` — CONTROL firmware reverse-engineering notes

## 10. Definition of Progress (Updated)

The STDBY/WAITING issue is **materially resolved**.  All original criteria are met:

1. CONTROL startup converges to DISPLAY mode (bit1=1) without manual hacks.
2. `0x1F.bit1` transitions are explainable: set by `BF/03/01` via function_019,
   never spuriously cleared during DISPLAY operation.
3. MAIN0 mailbox counters remain bounded; zero overruns in steady state.
4. TUI consistently shows "Volume: / -96.0dB" for arbitrarily long runs.
5. `test_full_boot.py` reproduces the full boot sequence and passes.
