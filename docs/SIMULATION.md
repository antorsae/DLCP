# DLCP Co-Simulation Guide

gpsim-backed co-simulation of CONTROL (V1.4) and MAIN (V2.3) PIC18F2550
firmware.  Runs unmodified firmware images with minimal binary overlays
for reset-vector redirection, UART mailbox hooks, and optional Timer3 shim.

## Quick Start

### TUI (interactive)

```bash
# Single MAIN unit, fast boot, active standby:
python scripts/gpsim_tui_simulator.py \
    firmware/stock/control/'DLCP Control Firmware V1.4.hex' \
    --main-hex 'firmware/stock/main/DLCP Firmware V2.3.hex' \
    --single-main --fast-boot --main-ra0 0x0228

# Two MAIN units (full daisy chain):
python scripts/gpsim_tui_simulator.py \
    firmware/stock/control/'DLCP Control Firmware V1.4.hex' \
    --main-hex 'firmware/stock/main/DLCP Firmware V2.3.hex' \
    --main-ra0 0x0228

# Full boot (no fast_boot, shows "Firmware V1.4" splash):
python scripts/gpsim_tui_simulator.py \
    firmware/stock/control/'DLCP Control Firmware V1.4.hex' \
    --main-hex 'firmware/stock/main/DLCP Firmware V2.3.hex' \
    --single-main --main-ra0 0x0228
```

### Headless regression tests

```bash
# Full boot sequence (48M cycles, ~4s simulated):
python scripts/test_full_boot.py

# Button press smoke test (SELECT, UP, DOWN):
python scripts/test_button_inject.py
```

## Architecture

```
 +-----------+     LinkPipe      +--------+     LinkPipe      +--------+
 | CONTROL   |  CTL->M0 (960Tcy) |  MAIN  |  M0->M1 (960Tcy) |  MAIN  |
 | gpsim     | <--------------->  |   #0   | <--------------->  |   #1   |
 | session   |  M0->CTL (960Tcy) | gpsim  |  M1->M0 (960Tcy) | gpsim  |
 +-----------+                    +--------+                    +--------+
       |                               |                            |
   LCD decode                     Timer3 shim                  Terminated
   (HD44780 log)                  Mailbox hooks                (--single-main
   Button stimuli                 AN0 ADC model                 omits this)
   Heartbeat model                RC2 strap model
```

Each unit runs in its own gpsim process.  The harness steps them in
round-robin order, pumping serial frames between steps via `LinkPipe`.

### Key components

| Component | File | Role |
|-----------|------|------|
| `GpsimControlSession` | `scripts/gpsim_tui_simulator.py` | CONTROL gpsim wrapper; LCD decode, button stimuli, RX ring injection |
| `GpsimControlHarness` | `src/dlcp_fw/sim/control_gpsim.py` | Non-interactive CONTROL gpsim harness for automated tests; EEPROM SFR read/write |
| `MainGpsimSession` | `scripts/gpsim_tui_simulator.py` | MAIN gpsim wrapper; mailbox hooks, Timer3 model, AN0/RC2 pin models |
| `LinkPipe` | `scripts/gpsim_tui_simulator.py` | Byte-paced serial transport; wire-rate spacing at 31,250 baud 8N1 |
| `LiveLogDecoder` | `scripts/gpsim_tui_simulator.py` | Parses gpsim log writes to extract LCD commands and TX frames |
| `LcdState` | `src/dlcp_fw/sim/lcd.py` | HD44780 protocol state machine |
| `apply_overlays` | `src/dlcp_fw/sim/overlay.py` | Binary patching engine for HEX files |
| Manifests | `src/dlcp_fw/sim/manifests.py` | Overlay definitions: reset redirect, boot wait bypass, standby check bypass, UART hooks |

### Serial transport model (LinkPipe)

Each serial link is modelled as a byte-paced queue matching PIC18F2550
EUSART at 31,250 baud, 8N1:

- **Wire time**: 960 instruction cycles per byte (320 us at 3 MIPS)
- **Frame size**: 3 bytes (route, cmd, data) = 2,880 Tcy per frame
- **FIFO depth**: CONTROL ring = 47 usable slots; MAIN mailbox = 63 slots
- **Overrun**: frames that arrive when the sink's ring/mailbox is full are
  silently dropped (models OERR on real silicon)

Frames are injected atomically (all 3 bytes or none) to preserve parser
framing.  This is a slight simplification — real EUSART delivers bytes
individually — but preserves protocol correctness.

### Heartbeat model

CONTROL's inner event loop (function_042, 0x0D24) blocks until a button
event (`0x9A != 0`) or serial data flag (`flags.bit3 != 0`).  In real
hardware, CONTROL toggles RC1 (heartbeat) and MAIN responds with status
frames that set bit3.  The simulator does not model this feedback loop,
so a synthetic heartbeat is injected:

1. **bit3 injection**: before each CONTROL step, `flags.bit3` is set via
   `reg(0x01F)` so function_042 can exit.

2. **BF/03/01 injection**: every 5 steps, a synthetic `BF/03/01` frame
   is enqueued into the M0->CTL link (with queue-depth guard) to maintain
   `flags.bit1 = 1` and prevent fallback to STANDBY.

3. **Activation**: the heartbeat activates after the WAITING-loop sentinel
   variables (0xB8, 0xB9, 0xA7, 0xA1) transition through 0x80 (entered)
   and then change (exit), using two-phase detection to avoid false
   positives from uninitialised RAM.

### Button simulation

gpsim `asynchronous_stimulus` objects permanently drive all six button
pins HIGH (unpressed).  This is necessary because `btg PORTC, RC1`
(heartbeat toggle in function_042) corrupts input pins on PORTC via
read-modify-write.

Since stimulus state cannot be toggled at runtime, button presses are
injected into function_023's debounce state machine:

- `RAM[0x0BE]` (accepted scan) = desired scan pattern
- `RAM[0x0BB]` (debounce counter) = 0

This triggers edge detection (`0x0BE != 0x0BD`) inside function_023,
which sets `0x9A = scan_pattern`.  function_042 exits on `0x9A != 0`,
and the DISPLAY handler (function_046) processes the button event.

Only rising edges (newly-pressed keys) are injected; held keys produce
no repeat events, matching real hardware.

**gpsim stimulus creation note**: `period 0` creates a dead stimulus
(`Vth=0V`).  The correct syntax is:
```
stimulus asynchronous_stimulus initial_state 1 start_cycle 0 { 1, 1 } name X end
```

## TUI Keyboard Controls

| Key | Action |
|-----|--------|
| `w` | UP (volume up) |
| `x` or `c` | DOWN (volume down) |
| `a` | LEFT |
| `d` | RIGHT |
| `s` | SELECT (mute toggle / menu enter) |
| `f` | STANDBY |
| `0` | Force MAIN AN0 ADC = 0x0000 (both units) |
| `1` | Force MAIN AN0 ADC = 0x0228 (both units) |
| `2` | Force MAIN AN0 ADC = 0x0FFF (both units) |
| `h` | Toggle help/notes overlay |
| `q` or ESC | Quit |

Arrow keys also work for UP/DOWN/LEFT/RIGHT.

## TUI Display Panels

- **LCD**: 2x16 character display decoded from CONTROL firmware's
  HD44780 bus writes (PORTB data, LATA control lines).
- **CTL RAM**: flags (0x1F), input_sel (0xB8), volume (0xB9),
  menu_state (0xBF), PORTC/TRISC/LATC for RC1 bus state.
- **Keys**: visual press feedback with highlighted key labels.
- **DLCP #0 / #1**: MAIN firmware RAM state — volume current/target,
  input, link register, channel config, ADC values, mailbox pointers.
- **Reconnect Diagnostics**: bit1 state, bit1 event history,
  reconnect hit count, wake lifecycle counters, mailbox occupancy.
- **Trace**: scrolling log of TX frames and key presses.
- **Status bar**: cycle counters, queue depths, delivery counts,
  overrun totals, diagnostic reason codes.

## Command-Line Options

| Option | Default | Description |
|--------|---------|-------------|
| `hex` (positional) | — | CONTROL firmware HEX path |
| `--main-hex` | (required) | MAIN firmware HEX; pass once for both units or twice for #0/#1 |
| `--single-main` | false | Run with one MAIN unit (terminated chain) |
| `--fast-boot` | false | Bypass one startup delay call in CONTROL firmware |
| `--gpasm` | `gpasm` | gpasm executable for hook assembly |
| `--chunk-cycles` | 300000 | CONTROL cycles per simulation step |
| `--main-chunk-cycles` | 300000 | MAIN cycles per simulation step |
| `--sim-quantum-cycles` | 0 | If >0, force shared small quantum for CONTROL and MAIN |
| `--hold-cycles` | 240000 | Key hold pulse width in cycles |
| `--initial-cycles` | 20000000 | Warm-up cycles at startup (before interactive loop) |
| `--poll-s` | 0.15 | UI refresh interval in seconds |
| `--main-ra0` | 0x0000 | Force MAIN AN0 ADC sample (both units); hotkeys 0/1/2 |
| `--main0-standby` | hold | MAIN #0 standby model: hold/release/control/auto |
| `--main1-standby` | hold | MAIN #1 standby model: hold/release/control/auto |
| `--main0-rc2` | high | MAIN #0 RC2 strap: high (local), low (chain), keep |
| `--main1-rc2` | low | MAIN #1 RC2 strap: high (local), low (chain), keep |
| `--main-timer3` | shim | Timer3 mode: shim (firmware patched) or harness (external) |
| `--rx-fifo-limit` | 47 | Max bytes in RX mailbox before overrun |

### Standby models

- **hold**: AN0 ADC held HIGH (above active threshold 0x0228) — MAIN stays active.
- **release**: AN0 ADC driven LOW — MAIN enters standby sensing.
- **control** / **auto**: AN0 follows CONTROL RC1 bus state (heartbeat-driven).

### RC2 strap models

- **high**: RC2 = 1 — MAIN operates as primary/local unit (SPBRG=0x3F, SCS1 set).
- **low**: RC2 = 0 — MAIN operates as downstream/chain unit (SPBRG=0x7F).
- **keep**: leave RC2 at gpsim/firmware default.

### Timer3 modes

- **shim**: function_079 in MAIN firmware is patched to return immediately.
  Faster execution; Timer3 overflow effects are approximated.
- **harness**: Timer3 overflow is modelled externally by the harness,
  setting TMR3IF at computed intervals.  Higher fidelity, slower.

## Firmware Overlay Summary

All overlays are minimal binary patches applied to the HEX before loading.
The firmware executes natively in gpsim — no behavioural stubs replace
firmware logic.

### CONTROL overlays

| Overlay | Effect |
|---------|--------|
| `control_reset_to_appstart` | Redirect reset vector from bootloader (0x7800) to app entry (0x0040) |
| `control_disable_boot_wait` | NOP a startup delay call (fast_boot mode only) |
| `control_disable_standby_check` | NOP the standby-handler jump at 0x1228 so firmware stays in DISPLAY mode without live MAIN heartbeat |

### MAIN overlays

| Overlay | Effect |
|---------|--------|
| `main_reset_to_appstart` | Redirect reset vector to app entry (0x1000) |
| `main_serial_mailbox_hooks` | Replace UART ISR with mailbox-backed RX/TX for harness injection |
| `main_adc_boot_wait_hook` | Hook ADC read during boot wait for harness-controlled AN0 |
| `main_i2c_bypass` | Bypass I2C initialisation (TAS3108 not simulated) |

## Known Limitations

1. **No RC1-to-MAIN feedback loop**.  The heartbeat (CONTROL toggling RC1,
   MAIN detecting via ADC, responding with BF/03/01) is replaced by
   synthetic bit3 and BF/03/01 injection.  This means the exact heartbeat
   timing and the MAIN-side ADC threshold behaviour are not exercised.

2. **Button presses bypass pin-level simulation**.  Because gpsim stimuli
   cannot be toggled at runtime, buttons are injected at the RAM level
   (debounce state machine).  The pin-read and XOR-inversion path in
   function_023 is not exercised for pressed buttons.

3. **I2C / TAS3108 not modelled**.  The TAS3108 audio DSP is not simulated.
   I2C init is bypassed.  Volume/input changes are visible in CONTROL RAM
   and serial frames but have no audio-side effect.

4. **Single-byte vs. frame-atomic injection**.  Real EUSART delivers bytes
   individually; the simulator injects 3-byte frames atomically.  This is
   correct for protocol framing but slightly simplifies byte-level timing.

5. **Timer3 shim approximation**.  In shim mode, function_079 is NOPed and
   Timer3 overflow is not precisely timed.  Harness mode is more accurate
   but slower.

6. **No USB / bootloader path**.  The bootloader at 0x7800 is bypassed.
   USB enumeration and firmware-update paths are not exercised.

7. **Wall-clock speed**.  The simulation runs ~10-50x slower than real time
   depending on chunk size and number of MAIN units.  A 20M-cycle warmup
   (1.67s simulated) takes ~0.8s wall clock; interactive steps at 300K
   cycles are fast enough for responsive UI at 0.15s poll rate.

## File Map

### Simulation engine

```
scripts/gpsim_tui_simulator.py  — TUI and co-simulation core
src/dlcp_fw/sim/control_gpsim.py       — non-interactive CONTROL gpsim harness (tests)
src/dlcp_fw/sim/main_gpsim.py          — MAIN gpsim harness (mailbox injection)
src/dlcp_fw/sim/manifests.py           — overlay definitions
src/dlcp_fw/sim/main_gpsim_timer3.py   — gpsim register helpers, Timer3 model
src/dlcp_fw/sim/lcd.py                 — HD44780 LCD state machine
src/dlcp_fw/sim/overlay.py             — HEX binary patching
src/dlcp_fw/sim/hexio.py               — Intel HEX parse/write/checksum
src/dlcp_fw/sim/protocol.py            — serial frame constants
```

### Test scripts

```
scripts/test_full_boot.py       — full boot regression (48M cycles)
scripts/test_button_inject.py   — button press regression (SELECT/UP/DOWN)
```

### Firmware

```
firmware/stock/control/DLCP Control Firmware V1.4.hex  — CONTROL binary
firmware/stock/main/DLCP Firmware V2.3.hex             — MAIN binary
firmware/disasm/control/v1.4_disasm.asm                — CONTROL disassembly
firmware/disasm/main/gpdasm_output.asm                 — MAIN disassembly
```

### Related documentation

```
AB_PRESETS.md                       — A/B preset patch documentation
SIMULATION_STDBY_WAIT_DIAGNOSIS.md  — diagnosis log for the standby/reconnect bug
TEST_SIMULATOR.md                   — preset test framework documentation
PIN_SEMANTICS.md                    — pin-level semantics reference
CONTROL_UNIT_ANALYSIS.md            — CONTROL firmware reverse-engineering notes
```
