# DLCP Firmware: Robustness, A/B Presets, and Live Diagnostics

Drop-in replacement firmware for the **Hypex DLCP** (Digital Loudspeaker Control Processor) amplifier module — both the MAIN unit (PIC18F2455) and CONTROL unit (PIC18F25K20). These images fix the stock firmware's permanent **"WAITING FOR DLCP"** hangs by adding bounded timeouts, I2C bus recovery, and DSP fault detection across the entire communication path. They also add **A/B preset switching**, an **on-LCD live diagnostics page**, and a **non-blocking IR decoder** that doesn't stall UART/RX during RC5 frame reception.

## The problem with stock firmware

Stock DLCP units develop a permanent hang where the CONTROL LCD shows:

```
+----------------+
|WAITING FOR DLCP|
|                |
+----------------+
```

This requires a full power cycle to recover, and recurs unpredictably. Root causes in stock firmware:

- **CONTROL** has two forever-loops (boot poll, reconnect wait) with no timeout — once MAIN stops responding, CONTROL waits permanently
- **MAIN** has unbounded blocking waits on UART TX, I2C/MSSP bus, and DSP coefficient writes — any bus glitch deadlocks the MCU
- No watchdog recovery — stock config words leave WDT effectively disabled
- No I2C bus-clear — if the TAS3108 DSP holds SCL/SDA low after a glitch, the bus stays stuck through peripheral reset
- RX ring buffers have no overflow detection — burst traffic silently drops bytes, causing parser misalignment
- The stock IR decoder bit-bangs RC5 frames inside the ISR, stalling UART RX, button RBIF, and TXIE for ~7-10 ms per frame

These compound into cascading failures, especially in daisy-chained multi-PB configurations where one stalled MAIN poisons the entire serial chain.

## New functionality

### A/B Preset switching

Two independent DSP configuration banks (A and B) stored in MAIN flash. Each bank holds the complete DSP register set including filename metadata.

- `V2.4`-`V2.7`: switching is instantaneous
- `V2.8` and `V3.1`: MAIN briefly mutes, waits about `150 ms`, switches bank, reapplies the DSP image, then restores audio
- `V3.2`: **async delayed-switch** — both MAINs in a 2-MAIN chain coordinate the mute/wait/apply sequence so the silence cue is synchronized across the stereo pair (no audible "leg-pulled" effect from one MAIN switching ahead of the other)

The delayed-switch behavior was introduced in `V2.8` for two reasons:

- give a small silence cue that the A/B switch actually happened
- avoid the audible blip from live-loading DSP coefficients while audio is playing

`V3.2`'s async refinement remediates a real-HW desync regression observed on stereo 2-MAIN rigs (see [`docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md`](docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md)).

**LCD menu** (CONTROL adds top-level Preset and Diagnostics pages):

```
Volume:          Preset:          Input:          Setup:           Diagnostics:
+----------------+ +----------------+ +----------------+ +----------------+ +----------------+
|Volume:-17.0dB A| |Preset          | |Input:          | |Setup           | |PB1: I2 D1 S1 B1|
|Auto Detect     | |Active: A       | |Auto Detect     | |BL Timeout      | |R1 A0 P0 O1     |
+----------------+ +----------------+ +----------------+ +----------------+ +----------------+
```

Menu navigation wraps: **Volume** ↔ **Preset** ↔ **Input** ↔ **Setup** ↔ **Diag**

Switching: UP/DOWN on the Preset page, or IR remote `0x38`/`0x39` from any page. Standby/wake: IR remote `0x3A`/`0x3B`.

### DSP Fault Reporting (V2.7+/V3.1+ + V1.63b/V1.71)

When the MAIN firmware detects a persistent DSP-path fault, it emits a `BF/08/<fault_byte>` status frame. `V1.63b` and `V1.71` CONTROL both parse it, latch a DSP-fault flag, show `!` in the volume-header slot where `A` / `B` normally appears, and force a full resync once MAIN reports the fault cleared. `V1.71` additionally stores the last received fault byte at RAM slot `0x0AB` and surfaces it on the Layer 5 diagnostics page below.

```
+----------------+
|Volume:-17.0dB !|
|Auto Detect     |
+----------------+
```

### Layer 5 Live Diagnostics (V3.2 MAIN + V1.71 CONTROL)

A new top-level **Diag** menu page on CONTROL displays real-time per-PB counters and reset causes from each MAIN:

- **I2** — I2C transport-fault episodes
- **D1** — DSP-fault episodes (BF/08 events)
- **S1** — standby dispatches
- **B1** — bring-up dispatches
- **R1** — recovery-branch entries
- **A0** — AN0-triggered standby
- **P0** — RA1 edge events
- **O1 / B0 / W0 / X0** — reset-cause flags (POR / BOR / WDT / SW reset, Tier-1)

CONTROL polls each MAIN with `BF/21` (runtime counters) every ~1 second and `BF/22` once per page-entry (reset causes). Counters survive ordinary firmware reset; cleared only on POR/BOR. The healthy-system shorthand renders `OK`; degraded systems sparse-render only the non-zero abnormal cells. Spec: [`docs/V32_DIAG_TIER1_SPEC.md`](docs/V32_DIAG_TIER1_SPEC.md).

### V1.71 non-blocking IR decoder (M3, Timer1-driven)

The legacy V1.6b IR decoder bit-bangs RC5 inside the high-priority ISR, stalling UART RX, button RBIF, and TXIE for ~7-10 ms per IR frame. Under sustained chain traffic this caused real-HW IR drops and frame-gap parser corruption.

`V1.71` replaces this with a Timer1-driven non-blocking sample state machine:

- RB5 falling edge arms Timer1; sample handler fires every ~890 µs and reads RB5 into a 4-byte buffer
- After 32 samples, the legacy Manchester pair-validation post-process runs to extract `cmd` / `addr`
- ISR-context FSR1/FSR2/PRODL/PCLATH stays untouched (only FSR0/W/STATUS/BSR are saved)
- Per-sample Timer1 preload tuned to absorb the actual ~70-Tcy ISR-path overhead so cumulative drift over 32 samples stays below the Manchester half-bit margin

All four V1.71 inline IR shortcuts (`0x38` preset A, `0x39` preset B, `0x3A` standby, `0x3B` wake) decode reliably end-to-end. Spec: [`docs/V171_IR_NONBLOCK_DECODER_SPEC.md`](docs/V171_IR_NONBLOCK_DECODER_SPEC.md).

## Release status

### MAIN firmware

| Version | Type | Status | Adds |
|---------|------|--------|------|
| **V3.2** | Source-assembled | **Recommended** | V3.1 + async delayed-switch + Layer 5 diag counters + Tier-1 reset-cause cells + cmd 0x44 HID diag-snapshot + pop-free flash-entry path. Recommended deployed MAIN release when paired with V1.71 CONTROL. |
| V3.1 | Source-assembled | Release | Full source rewrite (precursor of V3.2). All V2.4-V2.8 features inline. |
| V3.0 | Source-assembled | Reference | Clean V2.3-equivalent rewrite, byte-exact behavioral parity proven. |
| V2.8 | Binary-patched | Release | V2.7 + delayed mute/hold preset switch. |
| V2.7 | Binary-patched | Release | V2.6 + I2C bus-clear, DSP ping, fault status frames, PEN timeout. |
| V2.6 | Binary-patched | Release | V2.5 + DSP ACKSTAT check, conditional dirty-bit, deferred volume commit. |
| V2.5 | Binary-patched | Release | V2.4 + bounded timeouts on all UART/MSSP/I2C blocking waits. |
| V2.4 | Binary-patched | Release | A/B preset switching only (no robustness). |

### CONTROL firmware

| Version | Type | Status | Adds |
|---------|------|--------|------|
| **V1.71** | Source-assembled | **Recommended** | Full source rewrite. All V1.61b–V1.64b features inline + Layer 5 diagnostics page + non-blocking Timer1-driven IR decoder + bounded TX enqueue + value-bearing one-frame-per-call full-sync. Recommended deployed CONTROL release. |
| V1.7 | Source-assembled | Reference | Clean V1.6b-equivalent rewrite, byte-exact behavioral parity proven. |
| V1.64b | Binary-patched | Release | V1.63b + explicit IR standby (RC5 0x3A) / wake (RC5 0x3B) endpoints. |
| V1.63b | Binary-patched | Release | V1.62b + BF/08 fault parser, LCD `!` indicator, and resync-on-clear. |
| V1.62b | Binary-patched | Release | V1.61b + UART OERR recovery, bounded reconnect handshake. |
| V1.61b | Binary-patched | Release | A/B preset UI + V1.6b setup LCD garbage fix. |

### Recommended pair: V3.2 MAIN + V1.71 CONTROL

[`DLCP_Firmware_V3.2.hex`](firmware/patched/releases/DLCP_Firmware_V3.2.hex) + [`DLCP_Control_V1.71.hex`](firmware/patched/releases/DLCP_Control_V1.71.hex) — recommended deployed pair as of `2026-05-09`. Both halves are source-assembled clean-sheet rewrites with no jump-out hooks or stub regions. Together they unlock the Layer 5 diagnostics page, async coordinated preset switching, and the non-blocking IR decoder.

Operator runbooks:

- MAIN: [`docs/V32_RELEASE.md`](docs/V32_RELEASE.md)
- CONTROL: [`docs/V171_RELEASE.md`](docs/V171_RELEASE.md)

Flash MAIN through [`scripts/dlcp_v32_release_flash.py`](scripts/dlcp_v32_release_flash.py) so the canonical `V3.2` image, baked preset A/B captures, and per-box routing are applied as one operator-safe command. Flash CONTROL through [`scripts/flash_control_safe.sh`](scripts/flash_control_safe.sh) (defaults to V1.71). Read live MAIN diagnostic counters with [`scripts/dlcp_diag.py`](scripts/dlcp_diag.py).

`V3.1 + V1.71` remains the recommended fallback pair for chains where V3.2's async-coordinated switch is not needed. `V2.8 + V1.64b` remains the legacy binary-patched pair.

All versions are backward-compatible: V3.2/V3.1 work with V1.71 or any V1.6xb overlay; V2.8 works with V1.62b (no BF/08 fault UI); V2.5 works with V1.61b (no reconnect hardening); V1.71 degrades gracefully against stock V2.3 MAIN (no presets, no fault UI, IR 0x3A/0x3B still drive stock standby/wake frames).

Earlier versions are available in [`firmware/patched/releases/`](firmware/patched/releases/).

## V3.2 + V1.71 deployment

Place captured DSP A/B tables under the local artifact directory (gitignored):

- `artifacts/LX521.4/LX521.4_22MG10F-v5.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.bin`

PB1 (left):

```bash
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --left
scripts/flash_control_safe.sh                # CONTROL, defaults to V1.71
```

PB2 (right):

```bash
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --right
```

Live diagnostics (after flashing):

```bash
.venv_ep0/bin/python scripts/dlcp_diag.py        # snapshot all MAIN counters via cmd 0x44
```

Each canonical `V3.2` build bumps the EEPROM revision byte; each `V1.71` build bumps the flashed release-metadata byte — both per the build scripts at [`scripts/build_v32_release.py`](scripts/build_v32_release.py) and [`scripts/build_v171_release.py`](scripts/build_v171_release.py).

## V3.x vs V2.x: source-assembled vs binary-patched

**V2.x** releases are binary patches applied to the stock V2.3 hex image. Patch code is injected into dead zones and unused flash regions, with hooks redirecting execution. This works but is constrained by available free space and increasingly fragile as fixes stack up — V2.8 is the last comfortable binary-patched stop before the source-based V3.x line becomes the practical place for further feature work.

**V3.x** releases are assembled from a complete PIC18 source file ([`src/dlcp_fw/asm/dlcp_main_v32.asm`](src/dlcp_fw/asm/dlcp_main_v32.asm)). The source was reconstructed from the stock V2.3 disassembly, verified for byte-exact equivalence at V3.0, then extended with all robustness, preset, and diagnostics features inline. This removes the binary-patch space constraints and makes future development sustainable. Current V3.2 has **~720 bytes** of headroom before the preset-A baked-capture region at `0x4C00`.

## V1.7x vs V1.6xb: the same transition on the CONTROL side

**V1.6xb** releases (V1.61b–V1.64b) are binary patches over stock V1.6b, using the same overlay technique as the V2.x MAIN line: a free-flash stub region at `org 0x7000` plus ~11 hook sites that `goto` into the new code.

**V1.7x** is the CONTROL analog of V3.x:

- [`src/dlcp_fw/asm/dlcp_control_v17.asm`](src/dlcp_fw/asm/dlcp_control_v17.asm) — **V1.7**: clean-sheet rewrite of stock V1.6b, assembles byte-identical to stock. Relocation-safety proven by a dedicated shift test (insert 0x222 bytes of NOP padding, verify every symbol, chain behaviour, and LCD render still matches stock).
- [`src/dlcp_fw/asm/dlcp_control_v171.asm`](src/dlcp_fw/asm/dlcp_control_v171.asm) — **V1.71**: source-level successor of V1.64b. Inlines every feature from V1.61b through V1.64b directly at the natural call site — no jump-out hooks, no `org 0x7000` stub region. Adds Layer 5 Diagnostics page, the M3 non-blocking IR decoder, bounded TX enqueue (Layer 1), and the value-bearing one-frame-per-call full-sync state machine (Layer 2).

The V1.7 byte-identical baseline is what makes V1.71 safe: any V1.71 inline edit inherits a proven, fully-tested source layout, and the relocation-safety shift test guarantees that the inline additions will not silently break an address-sensitive code path.

## Rust silicon-fidelity simulator

All test gates run against a custom **single-process cycle-perfect PIC18 simulator** at [`crates/dlcp-sim/`](crates/dlcp-sim/), with a thin PyO3 facade at [`crates/dlcp-sim-py/`](crates/dlcp-sim-py/). The earlier gpsim-based three-process PTY-bridged harness was retired in `PF.4` (commits `5a56279`, `e023c01`, `edefea4`) — the rust simulator is now the only backend.

### Why rewrite

The gpsim approach ran three OS processes (one per MCU) plus a Python supervisor, with PTY-bridged UART couplings between them. Each PTY hop added unpredictable scheduler latency, the PIC18 Tcy boundary was not strictly cycle-aligned across processes, and the test gate took **>5 minutes** to run end-to-end. Worse, multi-clock-domain effects (CONTROL at 12 MHz Fosc vs MAIN at 12 MHz Fosc but with subtle PLL/oscillator differences) and boot-offset behavior (the "Task #22 echo loop") could only be modeled by adding ad-hoc retry logic — they were emergent properties of cross-process scheduling, not the simulated silicon.

The rust simulator runs **all cores in a single process** against a **universal 48 MHz tick clock**. Every core advances on integer multiples of universal ticks (`ticks_per_tcy = 16` for the K20 CONTROL at 3 MHz Fcy, `ticks_per_tcy = 12` for the 2455 MAINs at 4 MHz Fcy) so cycle ordering is deterministic across any number of cores. UART couplings are byte-level model state, not PTY pipes — the byte you `txif`-write on one core lands in the other's `rcif` deterministically `1 + start_bit + 8 + stop_bit` Tcy later, every time.

### What's modeled

PIC18 cores (PIC18F2455 and PIC18F25K20), peripherals, and chain wiring:

- **CPU**: full PIC18 ISA dispatch — every instruction advances `pc` by 2 or 4 bytes, consumes Tcy correctly (1 Tcy default, 2 Tcy for branches/calls/skips that take, 2 Tcy for `movff` etc.), updates STATUS flags, services interrupts at Q1 boundaries.
- **Memory**: physical address space (program flash, EEPROM, SFRs, banked GPRs); BANKED vs ACCESS bank decoding via BSR; `lfsr`/`POSTINC*`/`PLUSW*`/`INDF*` indirect addressing; `tblrd*+`/`tblwt*+` flash table read/write with TBLPTR auto-increment.
- **Interrupts**: vector dispatch at 0x000008 (high) / 0x000018 (low); Q4-aligned IRQ latency (3-4 Tcy ISR entry); ISR-context save/restore is firmware's responsibility (verified by the Tier-1 RAM static-analysis gate).
- **GPIO**: PORTA/B/C with TRIS, ANSEL, IOC (interrupt-on-change for RB4..RB7), open-drain emulation for I2C lines on PORTC.
- **MSSP / I2C**: master mode with Start/Restart/Stop/ACKSTAT, baud rate divider, SSPBUF half-duplex, BF/SSPIF/PEN/RSEN/ACKEN/SEN/RCEN bits, BCLIF bus-collision detection, stretchable SCL/SDA modeled at the bus level so the firmware's bus-clear sequence reproduces faithfully.
- **EUSART**: 8/9-bit asynchronous TX/RX, baud generator (BRG16 + SPBRGH), TXIF/RCIF/OERR latches, framing/break detection. The ISR-driven 31 250 baud chain link is byte-deterministic.
- **USB SIE** (PIC18F2455 only): EP0 / IN-EP / OUT-EP buffer descriptors, control-transfer SETUP/DATA/STATUS phases, HID class request handling. Sufficient fidelity to drive `dlcp_v32_release_flash.py`'s end-to-end flash + verify path entirely in sim.
- **Timer1**: 16-bit RD16 mode with TMR1H buffer, prescaler /1/2/4/8, internal Fcy/4 source, TMR1IF on overflow. Verified against the V1.6b stock decoder's instrumented sample timing (`2674 Tcy = 890 µs` per Manchester half-bit, `4040 Tcy = 1345 µs` first-sample offset from RB5 falling edge).
- **Timer2 / Timer3**: 8-bit + 16-bit, prescaler/postscaler, PIRx flag dispatch.
- **TAS3108 DSP** (over MSSP I2C): per-MAIN model that accepts coefficient table writes, mute/source/init register sequences, and the "filename" metadata strings that the firmware uses to detect dirty A/B presets.
- **Chain wiring**: 1, 2, or 3 cores in `(CONTROL → MAIN0 → MAIN1)` daisy-chain with byte-level UART coupling and shared open-collector standby/wake lines.

### Sim primitives exposed to Python

The PyO3 facade ([`crates/dlcp-sim-py/src/lib.rs`](crates/dlcp-sim-py/src/lib.rs)) gives Python tests:

- `chain.step()` / `chain.step_ticks(n)` — advance the universal clock; all cores step deterministically
- `chain.read_reg(addr)` / `chain.write_reg(addr, value)` — direct memory poke (CONTROL); `read_main_reg(unit, addr)` / `write_main_reg(unit, addr, value)` for MAIN0/MAIN1
- `chain.current_ctl_pc()` / `chain.current_main_pc()` — firmware program counter inspection
- `chain.step_until_pc_hit(core_idx, pc_lo, pc_hi, max_tcy)` — break-and-run primitive (mirrors gpsim's `break e <addr> ; run`)
- `chain.set_control_pin(port, bit, level)` — drive an external pin (used by the IR pulse-train tests to inject RC5 frames at RB5)
- `chain.press(key)` — synthesize a panel-button press with the V1.71 50M-tick hold + release-settle profile
- `chain.inject_decoded_ir_event(addr, cmd)` — RAM poke into `ir_decoded_cmd` / `ir_decoded_addr` to bypass the bit-bang decoder when only the dispatch path is under test
- `chain.lcd_lines()` — HD44780 DDRAM snapshot as `(line1, line2)` strings
- `chain.tx_frames()` / `chain.uart_tx_records_full()` — committed chain frame history and per-byte UART event log
- `chain.warmup(ticks)` / `chain.run_until_connected(limit)` — boot-to-DISPLAY helpers
- `chain.snapshot()` / `Chain.from_snapshot(bytes)` — bincode-stable serialize/restore (used by the property + soak harnesses for round-trip determinism)

### Fidelity gates

Three gates pin the simulator's behavior:

1. **Phase 4 fast-vs-slow timing gate** ([`scripts/check_phase4_gate.py`](scripts/check_phase4_gate.py)) — sweeps a deterministic scenario at increasing universal-clock cadences and asserts the firmware's observable behavior (TX byte log, LCD lines, register state) is byte-equal across cadences. Catches any cross-Tcy-boundary nondeterminism in peripheral models.
2. **Phase 5 property + soak gate** ([`scripts/check_phase5_gate.py`](scripts/check_phase5_gate.py)) — randomized scenarios + 10⁴-iteration snapshot round-trip soak. Catches drift in the simulator's serialized state model and any randomization-sensitive ordering issue.
3. **Replay round-trip verifier** ([`scripts/check_replay_round_trip.py`](scripts/check_replay_round_trip.py)) — for each of N test scenarios, capture an event trace, decode it, replay, and assert the resulting Chain state is byte-identical to the original.

The full sim gate (1 049 tests including the three fidelity gates) runs in **~50 seconds** on a modern laptop with `-n 16`, vs **~5+ minutes** under the retired gpsim three-process bridge.

### Spec and silicon-fidelity gap-closure

- [`docs/SIM_REWRITE_RUST_SPEC.md`](docs/SIM_REWRITE_RUST_SPEC.md) — full architecture, 6-phase rollout, acceptance criteria, risk register
- [`docs/IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md`](docs/IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md) — silicon-fidelity gap-closure plan (per the spec's section 11c). Tracks remaining gaps between the simulator and the PIC18F2455 / PIC18F25K20 datasheets, with each gap fronted by a regression test that fails until closed.
- [`docs/SIM_REWRITE_RUST_PROGRESS.md`](docs/SIM_REWRITE_RUST_PROGRESS.md) — machine-readable progress ledger

The simulator is good enough to ship firmware against — every regression caught in sim has reproduced on real hardware in the validation runs we've done — but it is **not perfect**. Real-silicon-only effects (op-amp settling, DSP analog tail, bus capacitance affecting I2C rise time) are not modeled. Any sim-passing change must still be flashed to a real DLCP unit before declaring it shippable.

## Test suite

The firmware is validated by a comprehensive simulation suite — **~1 050 tests** spanning the V1.7 byte-identical baseline, the V1.71 feature rewrite, the V3.x MAIN source rewrite, every V1.6xb / V2.x binary overlay, the Layer 5 diagnostic chain, the V1.71/V3.2 dual-MAIN preset sync property tests, and the V1.71 IR pulse-train decoder gate.

The test harness drives the serial bus, injects faults, and verifies LCD output, DSP register state, and protocol behavior across **two daisy-chained DLCP units** (PB1 + PB2) running against the rust simulator described above. Test categories:

- **Happy path** — boot sequence, preset load, volume-to-DSP, all 16 serial commands
- **DSP boot equivalence** — all 256 DSP registers match stock V2.3 after boot
- **A/B preset isolation** — flash bank mapping, filename persistence, USB upload routing
- **Robustness** — I2C bus-clear, DSP ping, MSSP timeout, PEN timeout, fault reporting
- **Fault injection** — ACKSTAT dirty readback, OERR parser corruption, stuck-bus faults
- **Wire-chain end-to-end** — two-PB daisy chain through reconnect, wake, and stock fault scenarios
- **Layer 5 diagnostic chain** — V1.71 ↔ V3.2 cmd 0x21/0x22 query/reply burst, LCD render of runtime counters and reset causes
- **IR command/sequence matrix** — all V1.71 inline shortcuts (0x38/0x39/0x3A/0x3B) via direct register inspection AND parametrized RC5 pulse-train through the M3 Timer1 decoder
- **Tier-1 RAM static-analysis gates** — equate-collision detector, BSR discipline check, movff bank-aliasing detector, ISR save/restore balance + unsaved-register-use check
- **Patch integrity** — semantic guards on every binary patch, ISR vector verification
- **Cross-version compatibility** — every MAIN/CONTROL version pair tested for interop

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q              # full gate
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v32"     # V3.2 MAIN focus
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v171"    # V1.71 CONTROL focus
.venv_ep0/bin/python -m pytest tests/hardware --run-hardware   # live-rig validation (camera+HID required)
```

## Documentation

- [`docs/AB_PRESETS.md`](docs/AB_PRESETS.md) — A/B preset design, protocol, patch maps
- [`docs/V32_RELEASE.md`](docs/V32_RELEASE.md) — recommended `V3.2` MAIN deployment workflow
- [`docs/V171_RELEASE.md`](docs/V171_RELEASE.md) — recommended `V1.71` CONTROL deployment workflow
- [`docs/V32_DIAG_TIER1_SPEC.md`](docs/V32_DIAG_TIER1_SPEC.md) — Layer 5 diagnostic counter + reset-cause protocol (cmd 0x21 / cmd 0x22 / BF/2x replies)
- [`docs/V171_IR_NONBLOCK_DECODER_SPEC.md`](docs/V171_IR_NONBLOCK_DECODER_SPEC.md) — V1.71 Timer1-driven non-blocking IR decoder
- [`docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md`](docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md) — V3.2 async delayed-switch design
- [`docs/HARDWARE_TEST.md`](docs/HARDWARE_TEST.md) — real-hardware state-transition validation runbook
- [`docs/HARDWARE_LOOP.md`](docs/HARDWARE_LOOP.md) — real-hardware audio playback/capture workflow
- [`docs/RECOVERY.md`](docs/RECOVERY.md) — PICkit 5 readback recombination + full MAIN recovery
- [`docs/ROBUSTNESS.md`](docs/ROBUSTNESS.md) — root cause analysis, failure chains, fix strategy
- [`docs/V31_RELEASE.md`](docs/V31_RELEASE.md) — fallback `V3.1` MAIN deployment workflow
- [`docs/V16B_SOURCE_REWRITE_SPEC.md`](docs/V16B_SOURCE_REWRITE_SPEC.md) — V1.71 CONTROL feature-bearing source rewrite specification
- [`docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md`](docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md) — V1.7 CONTROL byte-identical source rebuild specification
- [`docs/SIMULATION.md`](docs/SIMULATION.md) — co-simulation architecture
- [`docs/SIM_REWRITE_RUST_SPEC.md`](docs/SIM_REWRITE_RUST_SPEC.md) — Rust single-process PIC18 simulator design
- [`docs/TEST_SIMULATOR.md`](docs/TEST_SIMULATOR.md) — test framework reference
- [`AGENTS.md`](AGENTS.md) — full project index, canonical paths, build commands

## Disclaimer

**NO WARRANTY, EXPRESS OR IMPLIED.** The Hypex DLCP is end-of-life hardware. This firmware is released as a community bugfix, not a supported product. Use it entirely at your own risk.

I make no guarantees of any kind — of correctness, fitness for purpose, or safety. I accept no responsibility for any outcome of using this firmware. If you brick your device, that is on you. Only flash these images if you are comfortable working with PIC microcontroller firmware and understand the risks.

In the unlikely event that a flash goes wrong, recovery requires a [PICkit](https://www.microchip.com/en-us/development-tool/pg164150) programmer to re-flash the MCU directly.
