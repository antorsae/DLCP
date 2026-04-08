# DLCP Firmware: Robustness & A/B Preset Replacement Firmware

Drop-in replacement firmware for the **Hypex DLCP** (Digital Loudspeaker Control Processor) amplifier module — both the MAIN unit (PIC18F2455) and CONTROL unit (PIC18F25K20). These images fix the stock firmware's permanent **"WAITING FOR DLCP"** hangs by adding bounded timeouts, I2C bus recovery, and DSP fault detection across the entire communication path. They also add **A/B preset switching** — store two complete DSP configurations and switch between them from the front panel, IR remote, or USB.

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

These compound into cascading failures, especially in daisy-chained multi-PB configurations where one stalled MAIN poisons the entire serial chain.

## New functionality

### A/B Preset switching

Two independent DSP configuration banks (A and B) stored in MAIN flash. Each bank holds the complete DSP register set including filename metadata.

- `V2.4`-`V2.7`: switching is instantaneous
- `V2.8` and `V3.1+`: MAIN briefly mutes, waits about `150 ms`, switches bank, reapplies the DSP image, then restores audio if it was not already muted

The `V2.8` delayed-switch behavior was added for two reasons:

- give a small silence cue that the A/B switch actually happened
- avoid the audible blip from live-loading DSP coefficients while audio is playing

**LCD menu** (CONTROL adds a new top-level Preset page between Volume and Input):

```
Volume screen:              Preset screen:
+----------------+          +----------------+
|Volume:-17.0dB A|          |Preset          |
|Auto Detect     |          |Active: A       |
+----------------+          +----------------+

Input screen:               Setup screen:
+----------------+          +----------------+
|Input:          |          |Setup           |
|Auto Detect     |          |BL Timeout      |
+----------------+          +----------------+
```

After switching to Preset B:

```
+----------------+          +----------------+
|Volume:-17.0dB B|          |Preset          |
|Auto Detect     |          |Active: B       |
+----------------+          +----------------+
```

Menu navigation wraps: **Volume** <-> **Preset** <-> **Input** <-> **Setup**

Switching: UP/DOWN on the Preset page, or IR remote F1/F2 from any page.

### DSP Fault Reporting (V2.7/V3.1 + V1.63b)

When the MAIN firmware detects a persistent DSP-path fault, it emits a
`BF/08/<fault_byte>` status frame. `V1.63b` CONTROL adds the matching
parser, latches a DSP-fault flag, shows `!` in the volume-header slot
where `A` / `B` normally appears, and forces a full resync once MAIN
reports the fault cleared.

```
+----------------+
|Volume:-17.0dB !|
|Auto Detect     |
+----------------+
```

The separate diagnostics-page/counter design in
[`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`](docs/V163B_DIAGNOSTICS_MENU_SPEC.md)
is still a draft and is not implemented in the committed `V1.63b`
CONTROL or `V3.1` MAIN hexes.

## Release status

### MAIN firmware

| Version | Type | Status | Adds |
|---------|------|--------|------|
| V3.1 | Source-assembled | **WIP** | Full source rewrite. All V2.4-V2.8 features inline. Unresolved issue under investigation. |
| V3.0 | Source-assembled | Reference | Clean V2.3-equivalent rewrite, byte-exact behavioral parity proven. |
| **V2.8** | Binary-patched | **Release** | V2.7 + delayed mute/hold preset switch to provide an audible cue and avoid coefficient-load blips. |
| **V2.7** | Binary-patched | **Release** | V2.6 + I2C bus-clear, DSP ping, fault status frames, PEN timeout. |
| V2.6 | Binary-patched | Release | V2.5 + DSP ACKSTAT check, conditional dirty-bit, deferred volume commit. |
| V2.5 | Binary-patched | Release | V2.4 + bounded timeouts on all UART/MSSP/I2C blocking waits. |
| V2.4 | Binary-patched | Release | A/B preset switching only (no robustness). |

### CONTROL firmware

| Version | Type | Status | Adds |
|---------|------|--------|------|
| **V1.63b** | Binary-patched | **Release** | V1.62b + BF/08 fault parser, LCD `!` indicator, and resync-on-clear. |
| V1.62b | Binary-patched | Release | V1.61b + UART OERR recovery, bounded reconnect handshake. |
| V1.61b | Binary-patched | Release | A/B preset UI + V1.6b setup LCD garbage fix. |

### Recommended pair

**[`DLCP_Firmware_V2.8.hex`](firmware/patched/releases/DLCP_Firmware_V2.8.hex) + [`DLCP_Control_V1.63b.hex`](firmware/patched/releases/DLCP_Control_V1.63b.hex)** — full robustness, A/B presets, BF/08 fault reporting, and the delayed preset-switch mute/hold that gives a small audible cue while avoiding blips during live DSP coefficient reload.

All versions are backward-compatible: V2.8 works with V1.62b (no BF/08 fault UI/resync), V2.5 works with V1.61b (no reconnect hardening).

Earlier versions (V2.4-V2.7, V1.41-V1.62b) are also available in [`firmware/patched/releases/`](firmware/patched/releases/).

## V3.x vs V2.x: source-assembled vs binary-patched

**V2.x** releases are binary patches applied to the stock V2.3 hex image. Patch code is injected into dead zones and unused flash regions, with hooks redirecting execution. This works but is constrained by available free space and increasingly fragile as fixes stack up — V2.8 is effectively the last comfortable binary-patched stop before the source-based V3.x line becomes the practical place for further feature work.

**V3.x** releases are assembled from a complete PIC18 source file ([`src/dlcp_fw/asm/dlcp_main_v31.asm`](src/dlcp_fw/asm/dlcp_main_v31.asm)). The source was reconstructed from the stock V2.3 disassembly, verified for byte-exact equivalence at V3.0, then extended with all robustness and preset features inline. This removes all space constraints and makes future development sustainable.

## Test suite

The firmware is validated by a **554-test simulation suite** that exercises every firmware version across the full operational envelope.

The test infrastructure co-simulates **two daisy-chained DLCP units** (PB1 + PB2) using a [patched gpsim fork](vendor/gpsim-0.32.1-xtc/) that models the PIC18 MCUs cycle-accurately — MSSP/I2C, UART, USB SIE, and Timer peripherals. A Python harness drives the serial bus, injects faults, and verifies LCD output, DSP register state, and protocol behavior.

Test categories:

- **Happy path** — boot sequence, preset load, volume-to-DSP, all 16 serial commands
- **DSP boot equivalence** — all 256 DSP registers match stock V2.3 after boot
- **A/B preset isolation** — flash bank mapping, filename persistence, USB upload routing
- **Robustness** — I2C bus-clear, DSP ping, MSSP timeout, PEN timeout, fault reporting
- **Fault injection** — ACKSTAT dirty readback, OERR parser corruption, stuck-bus faults
- **Wire-chain end-to-end** — two-PB daisy chain through reconnect, wake, and stock fault scenarios
- **Patch integrity** — semantic guards on every binary patch, ISR vector verification
- **Cross-version compatibility** — every MAIN/CONTROL version pair tested for interop

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q          # full gate, 554 tests
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v31" # V3.1 only, 80 tests
```

## Documentation

- [`docs/AB_PRESETS.md`](docs/AB_PRESETS.md) — A/B preset design, protocol, patch maps
- [`docs/ROBUSTNESS.md`](docs/ROBUSTNESS.md) — root cause analysis, failure chains, fix strategy
- [`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`](docs/V163B_DIAGNOSTICS_MENU_SPEC.md) — draft future diagnostics page / counter protocol
- [`docs/SIMULATION.md`](docs/SIMULATION.md) — co-simulation architecture
- [`docs/TEST_SIMULATOR.md`](docs/TEST_SIMULATOR.md) — test framework reference
- [`AGENTS.md`](AGENTS.md) — full project index, canonical paths, build commands

## Disclaimer

**NO WARRANTY, EXPRESS OR IMPLIED.** The Hypex DLCP is end-of-life hardware. This firmware is released as a community bugfix, not a supported product. Use it entirely at your own risk.

I make no guarantees of any kind — of correctness, fitness for purpose, or safety. I accept no responsibility for any outcome of using this firmware. If you brick your device, that is on you. Only flash these images if you are comfortable working with PIC microcontroller firmware and understand the risks.

In the unlikely event that a flash goes wrong, recovery requires a [PICkit](https://www.microchip.com/en-us/development-tool/pg164150) programmer to re-flash the MCU directly.
