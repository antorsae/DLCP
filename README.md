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

### DSP Fault Reporting (V2.7+/V3.1 + V1.63b/V1.71)

When the MAIN firmware detects a persistent DSP-path fault, it emits a
`BF/08/<fault_byte>` status frame. `V1.63b` and `V1.71` CONTROL both
add the matching parser, latch a DSP-fault flag, show `!` in the
volume-header slot where `A` / `B` normally appears, and force a full
resync once MAIN reports the fault cleared. `V1.71` additionally
stores the last received fault byte at RAM slot `0x0AB` so future
diagnostic menus can display the exact fault code.

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
| **V3.1** | Source-assembled | **Release** | Full source rewrite. All V2.4-V2.8 features inline. Recommended MAIN release when flashed with baked preset A/B captures. |
| V3.0 | Source-assembled | Reference | Clean V2.3-equivalent rewrite, byte-exact behavioral parity proven. |
| V2.8 | Binary-patched | Release | V2.7 + delayed mute/hold preset switch to provide an audible cue and avoid coefficient-load blips. |
| **V2.7** | Binary-patched | **Release** | V2.6 + I2C bus-clear, DSP ping, fault status frames, PEN timeout. |
| V2.6 | Binary-patched | Release | V2.5 + DSP ACKSTAT check, conditional dirty-bit, deferred volume commit. |
| V2.5 | Binary-patched | Release | V2.4 + bounded timeouts on all UART/MSSP/I2C blocking waits. |
| V2.4 | Binary-patched | Release | A/B preset switching only (no robustness). |

### CONTROL firmware

| Version | Type | Status | Adds |
|---------|------|--------|------|
| **V1.71** | Source-assembled | **Release** | Full source rewrite. All V1.61b–V1.64b features inline. Recommended CONTROL release. |
| V1.7 | Source-assembled | Reference | Clean V1.6b-equivalent rewrite, byte-exact behavioral parity proven (70-test suite, structural + relocation-safe under 0x222 shift). |
| V1.64b | Binary-patched | Release | V1.63b + explicit IR standby (RC5 0x3A) / wake (RC5 0x3B) endpoints. |
| V1.63b | Binary-patched | Release | V1.62b + BF/08 fault parser, LCD `!` indicator, and resync-on-clear. |
| V1.62b | Binary-patched | Release | V1.61b + UART OERR recovery, bounded reconnect handshake. |
| V1.61b | Binary-patched | Release | A/B preset UI + V1.6b setup LCD garbage fix. |

### Recommended pair

**[`DLCP_Firmware_V3.1.hex`](firmware/patched/releases/DLCP_Firmware_V3.1.hex) + `dlcp_control_v171.asm`** (assembled from source) — recommended deployed pair. Both halves are source-assembled clean-sheet rewrites that inline every feature previously delivered by binary overlays, with no jump-out hooks or stub regions.

Flash MAIN through [`scripts/dlcp_v31_release_flash.py`](scripts/dlcp_v31_release_flash.py) so the canonical `V3.1` image, baked preset A/B captures, and per-box routing are applied as one operator-safe command. Assemble and flash the CONTROL side from [`src/dlcp_fw/asm/dlcp_control_v171.asm`](src/dlcp_fw/asm/dlcp_control_v171.asm).

**[`DLCP_Firmware_V2.8.hex`](firmware/patched/releases/DLCP_Firmware_V2.8.hex) + [`DLCP_Control_V1.64b.hex`](firmware/patched/releases/DLCP_Control_V1.64b.hex)** remains the recommended legacy binary-patched pair when you explicitly want the last patch-on-stock images instead of the source-assembled `V3.1` / `V1.71` line.

All versions are backward-compatible: `V3.1` and `V2.8` work with `V1.71` or any of the `V1.6xb` binary overlays; `V2.8` works with `V1.62b` (no BF/08 fault UI/resync); `V2.5` works with `V1.61b` (no reconnect hardening); and `V1.71` degrades gracefully against stock V2.3 MAIN (no presets, no fault UI, IR 0x3A/0x3B still drive stock standby/wake frames).

Earlier versions (`V2.4`–`V2.7`, `V1.41`–`V1.64b`) are also available in [`firmware/patched/releases/`](firmware/patched/releases/).

## Recommended V3.1 Deployment

The recommended operator entrypoint is
[`scripts/dlcp_v31_release_flash.py`](scripts/dlcp_v31_release_flash.py). It
hardcodes the canonical `V3.1` image plus the local preset A/B capture paths
under `artifacts/LX521.4/`, then forwards to the underlying
[`scripts/dlcp_main_flash.py`](scripts/dlcp_main_flash.py) implementation.

Place the captured tables under the ignored local artifact directory:

- `artifacts/LX521.4/LX521.4_22MG10F-v5.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.bin`

Verified working commands for a stereo pair:

PB1 (left):

```bash
.venv_ep0/bin/python scripts/dlcp_v31_release_flash.py --left
```

PB2 (right):

```bash
.venv_ep0/bin/python scripts/dlcp_v31_release_flash.py --right
```

## V3.x vs V2.x: source-assembled vs binary-patched

**V2.x** releases are binary patches applied to the stock V2.3 hex image. Patch code is injected into dead zones and unused flash regions, with hooks redirecting execution. This works but is constrained by available free space and increasingly fragile as fixes stack up — V2.8 is effectively the last comfortable binary-patched stop before the source-based V3.x line becomes the practical place for further feature work.

**V3.x** releases are assembled from a complete PIC18 source file ([`src/dlcp_fw/asm/dlcp_main_v31.asm`](src/dlcp_fw/asm/dlcp_main_v31.asm)). The source was reconstructed from the stock V2.3 disassembly, verified for byte-exact equivalence at V3.0, then extended with all robustness and preset features inline. This removes all space constraints and makes future development sustainable.

## V1.7x vs V1.6xb: the same transition on the CONTROL side

**V1.6xb** releases (V1.61b–V1.64b) are binary patches over stock V1.6b, using the same overlay technique as the V2.x MAIN line: a free-flash stub region at `org 0x7000` plus ~11 hook sites that `goto` into the new code.

**V1.7x** is the CONTROL analog of V3.x:

- [`src/dlcp_fw/asm/dlcp_control_v17.asm`](src/dlcp_fw/asm/dlcp_control_v17.asm) and [`dlcp_control_v17_comments.asm`](src/dlcp_fw/asm/dlcp_control_v17_comments.asm) — **V1.7**: clean-sheet rewrite of stock V1.6b, assembles byte-identical to stock in code, config, and EEPROM regions. Relocation-safety is proven by a dedicated shift test (insert 0x222 bytes of NOP padding and verify every symbol, chain behaviour, and LCD render still matches stock).
- [`src/dlcp_fw/asm/dlcp_control_v171.asm`](src/dlcp_fw/asm/dlcp_control_v171.asm) — **V1.71**: the source-level successor of V1.64b. Inlines every feature from V1.61b, V1.62b, V1.63b, and V1.64b directly at the natural call site — no jump-out hooks, no `org 0x7000` stub region. EEPROM version tuple bumped to `01 07 31 01`.

The V1.7 byte-identical baseline is what makes V1.71 safe: any V1.71 inline edit inherits a proven, fully-tested source layout, and the relocation-safety shift test guarantees that the inline additions will not silently break an address-sensitive code path.

## Test suite

The firmware is validated by a comprehensive simulation suite that exercises every firmware version across the full operational envelope — **~640+ tests** spanning the V1.7 byte-identical baseline (70 tests), the V1.71 feature rewrite (44 tests across baseline, preset inline, IR endpoints, fault indicator, reconnect/OERR, preset menu, full-sync retry, sentinel reconnect, and the V1.71 × V3.1 chain gate), the V3.x MAIN source rewrite, and every V1.6xb / V2.x binary overlay.

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
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q              # full gate
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v31"     # V3.1 MAIN only, 80 tests
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v17 or v171" # V1.7 + V1.71 CONTROL, 114 tests
```

## Documentation

- [`docs/AB_PRESETS.md`](docs/AB_PRESETS.md) — A/B preset design, protocol, patch maps
- [`docs/V31_RELEASE.md`](docs/V31_RELEASE.md) — recommended `V3.1` deployment workflow with baked preset A/B captures
- [`docs/ROBUSTNESS.md`](docs/ROBUSTNESS.md) — root cause analysis, failure chains, fix strategy
- [`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`](docs/V163B_DIAGNOSTICS_MENU_SPEC.md) — draft future diagnostics page / counter protocol
- [`docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md`](docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md) — V1.7 CONTROL byte-identical source rebuild specification
- [`docs/V16B_SOURCE_REWRITE_SPEC.md`](docs/V16B_SOURCE_REWRITE_SPEC.md) — V1.71 CONTROL feature-bearing source rewrite specification
- [`docs/SIMULATION.md`](docs/SIMULATION.md) — co-simulation architecture
- [`docs/TEST_SIMULATOR.md`](docs/TEST_SIMULATOR.md) — test framework reference
- [`AGENTS.md`](AGENTS.md) — full project index, canonical paths, build commands

## Disclaimer

**NO WARRANTY, EXPRESS OR IMPLIED.** The Hypex DLCP is end-of-life hardware. This firmware is released as a community bugfix, not a supported product. Use it entirely at your own risk.

I make no guarantees of any kind — of correctness, fitness for purpose, or safety. I accept no responsibility for any outcome of using this firmware. If you brick your device, that is on you. Only flash these images if you are comfortable working with PIC microcontroller firmware and understand the risks.

In the unlikely event that a flash goes wrong, recovery requires a [PICkit](https://www.microchip.com/en-us/development-tool/pg164150) programmer to re-flash the MCU directly.
