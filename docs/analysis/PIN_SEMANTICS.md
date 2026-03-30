# PIC I/O Pin Semantics (CONTROL + MAIN)

This is a fresh pin-level map from disassembly + board manuals, with confidence levels.

Migration note (2026-03-30):

- Path examples below use the pre-migration short form.
- Translate `control/disasm/...` to `firmware/disasm/control/...`.
- Translate `disasm/...` to `firmware/disasm/main/...`.

## Scope and Method
- CONTROL firmware evidence: `control/disasm/v1.4_disasm.asm`
- MAIN firmware evidence: `disasm/gpdasm_output.asm`
- Board connector semantics: `DLCP-datasheet-R3.pdf` (J1/J2/J3/J7/J10-J17 tables), `DLCP-manual-R3.pdf` (control-chain behavior)
- PIC multiplexing cross-check:
  - MAIN: `39632e.pdf` (PIC18F2455/2550/4455/4550 datasheet)
  - CONTROL: `PIC18F25K20` register map cross-check from gputils include definitions

Legend:
- `High`: directly read/written and behavior clear in firmware.
- `Medium`: strongly inferred from firmware patterns + connector docs.
- `Low`: configured but no direct runtime use observed.

---

## CONTROL PIC (panel controller, PIC18F25K20)

Important note:
- Older disassembly labels in this repo used `PIC18F2550` SFR names.
- For CONTROL, addresses in the `0xF6C..0xF7F` block should now be interpreted as
  `PIC18F25K20` registers such as `CM1CON0/CM2CON0/IOCB/ANSEL/ANSELH`, not USB endpoint registers.

Boot GPIO setup:
- `TRISA=0xDF`, `TRISB=0x3C`, `TRISC=0xBD`, `ADCON1=0x0F` at `control/disasm/v1.4_disasm.asm:604`, `control/disasm/v1.4_disasm.asm:607`, `control/disasm/v1.4_disasm.asm:609`, `control/disasm/v1.4_disasm.asm:615`.

| Pin | Dir @ boot | Semantics | Confidence | Evidence |
|---|---|---|---|---|
| RA0 | Input | No functional reads found; likely unused on panel firmware | Low | `control/disasm/v1.4_disasm.asm:605` |
| RA1 | Input | `Select` button (active-low) | High | `control/disasm/v1.4_disasm.asm:1606` |
| RA2 | Input | `Down` button (active-low) | High | `control/disasm/v1.4_disasm.asm:1603` |
| RA3 | Input | `Standby` button (active-low) | High | `control/disasm/v1.4_disasm.asm:1597` |
| RA4 | Input | `Right` button (active-low) | High | `control/disasm/v1.4_disasm.asm:1612` |
| RA5 | Output | LCD `RS` control | High | `control/disasm/v1.4_disasm.asm:16637`, `control/disasm/v1.4_disasm.asm:16700` |
| RA6 | Input | No functional reads found | Low | `control/disasm/v1.4_disasm.asm:605` |
| RA7 | Input | No functional reads found | Low | `control/disasm/v1.4_disasm.asm:605` |
| RB0 | Output (LCD bus) | LCD data nibble bit (D4) | High | `control/disasm/v1.4_disasm.asm:16712`, `control/disasm/v1.4_disasm.asm:16715` |
| RB1 | Output (LCD bus) | LCD data nibble bit (D5) | High | `control/disasm/v1.4_disasm.asm:16712`, `control/disasm/v1.4_disasm.asm:16715` |
| RB2 | Input at boot, driven during LCD writes | LCD data nibble bit (D6) in 4-bit transfers | High | `control/disasm/v1.4_disasm.asm:16641`, `control/disasm/v1.4_disasm.asm:16715` |
| RB3 | Input at boot, driven during LCD writes | LCD data nibble bit (D7) in 4-bit transfers | High | `control/disasm/v1.4_disasm.asm:16641`, `control/disasm/v1.4_disasm.asm:16715` |
| RB4 | Output | LCD `E` strobe | High | `control/disasm/v1.4_disasm.asm:16636`, `control/disasm/v1.4_disasm.asm:16710` |
| RB5 | Input | IR receiver input (RC-5 decode + RBIF path) | High | `control/disasm/v1.4_disasm.asm:397`, `control/disasm/v1.4_disasm.asm:699` |
| RB6 | Output | Forced low at boot; panel-side auxiliary output (exact board net not explicit) | Medium | `control/disasm/v1.4_disasm.asm:16978`, `control/disasm/v1.4_disasm.asm:16979` |
| RB7 | Input | No functional reads found | Low | `control/disasm/v1.4_disasm.asm:607` |
| RC0 | Input | `Up` button (active-low) | High | `control/disasm/v1.4_disasm.asm:1600` |
| RC1 | Output | Panel illumination / power-state indicator line (driven in standby/active paths) | High | `control/disasm/v1.4_disasm.asm:2328`, `control/disasm/v1.4_disasm.asm:2387`, `control/disasm/v1.4_disasm.asm:3043` |
| RC2 | Input | No functional reads found | Low | `control/disasm/v1.4_disasm.asm:609` |
| RC3 | Input | No functional reads found | Low | `control/disasm/v1.4_disasm.asm:609` |
| RC4 | Input | No functional reads found in panel app | Low | `control/disasm/v1.4_disasm.asm:609` |
| RC5 | Input | `Left` button (active-low) | High | `control/disasm/v1.4_disasm.asm:1609` |
| RC6 | UART TX | Current-loop serial TX to DLCP chain (31,250 baud) | High | `control/disasm/v1.4_disasm.asm:620`, `control/disasm/v1.4_disasm.asm:629` |
| RC7 | UART RX | Current-loop serial RX from DLCP chain | High | `control/disasm/v1.4_disasm.asm:629`, `control/disasm/v1.4_disasm.asm:687` |

Control board connector naming for buttons/display/IR is documented in `DLCP-manual-R3.pdf` (section 2.5.2.1, page 11 text extract).

---

## MAIN PIC (DLCP processing board, PIC18F2455)

Boot GPIO/peripheral setup:
- `TRISA=0x07`, `TRISB=0x00`, `TRISC=0x87` at `disasm/gpdasm_output.asm:6174`, `disasm/gpdasm_output.asm:6175`, `disasm/gpdasm_output.asm:6177`.
- `ADCON0=0x01`, `ADCON1=0x0C` (AN0 analog, rest digital) at `disasm/gpdasm_output.asm:6183`, `disasm/gpdasm_output.asm:6185`.
- MSSP and baud config initialized at `disasm/gpdasm_output.asm:6181`, `disasm/gpdasm_output.asm:6193`.

| Pin | Dir @ boot | Semantics | Confidence | Evidence |
|---|---|---|---|---|
| RA0 / AN0 | Input (analog) | Standby sense ADC input (threshold logic around ~0x0228) | High | `disasm/gpdasm_output.asm:6185`, `disasm/gpdasm_output.asm:4894`, `disasm/gpdasm_output.asm:4915`, `disasm/gpdasm_output.asm:8126` |
| RA1 | Input | No clear runtime consumption found | Low | `disasm/gpdasm_output.asm:6174` |
| RA2 | Input | No clear runtime consumption found | Low | `disasm/gpdasm_output.asm:6174` |
| RA3 | Output | One of three source/relay control bits (multi-state combinations) | Medium | `disasm/gpdasm_output.asm:8777`, `disasm/gpdasm_output.asm:8782` |
| RA4 | Output | One of three source/relay control bits (multi-state combinations) | Medium | `disasm/gpdasm_output.asm:8786`, `disasm/gpdasm_output.asm:8799` |
| RA5 | Output | One of three source/relay control bits (multi-state combinations) | Medium | `disasm/gpdasm_output.asm:8787`, `disasm/gpdasm_output.asm:8803` |
| RA6 | Output | Auxiliary control line toggled in startup/power paths | Medium | `disasm/gpdasm_output.asm:4935`, `disasm/gpdasm_output.asm:4965`, `disasm/gpdasm_output.asm:6834` |
| RA7 | Output in TRIS write, but oscillator-mux sensitive | Likely not general-purpose in final hardware due oscillator muxing; no direct firmware use observed | Low | `disasm/gpdasm_output.asm:6174`, `39632e.pdf` pin mux text for oscillator modes |
| RB0 | Output at boot, later input for MSSP | I2C/serial-data line (DSP + secondary I2C device) | High | `disasm/gpdasm_output.asm:4940`, `disasm/gpdasm_output.asm:9252`, `39632e.pdf` `RB0...SDI/SDA` |
| RB1 | Output at boot, later input for MSSP | I2C/serial-clock line | High | `disasm/gpdasm_output.asm:4939`, `disasm/gpdasm_output.asm:9251`, `39632e.pdf` `RB1...SCK/SCL` |
| RB2 | Output | Chain-role/status output driven from RC2 strap branch | Medium | `disasm/gpdasm_output.asm:6814`, `disasm/gpdasm_output.asm:6823`, `disasm/gpdasm_output.asm:7272`, `disasm/gpdasm_output.asm:7281` |
| RB3 | Output | Auxiliary control line (set/clear in startup and source-state transitions) | Medium | `disasm/gpdasm_output.asm:4936`, `disasm/gpdasm_output.asm:4975`, `disasm/gpdasm_output.asm:6833` |
| RB4 | Output | Auxiliary control line (set/clear in startup and state transitions) | Medium | `disasm/gpdasm_output.asm:4934`, `disasm/gpdasm_output.asm:4946`, `disasm/gpdasm_output.asm:6831` |
| RB5 | Output | Auxiliary control line, initialized low; exact board net unclear | Low | `disasm/gpdasm_output.asm:6832` |
| RB6 | Output | Set high during init; likely enable/status output | Medium | `disasm/gpdasm_output.asm:6227` |
| RB7 | Output | Initialized low; exact board net unclear | Low | `disasm/gpdasm_output.asm:6838` |
| RC0 | Input | Current-loop receive state gate used in runtime path checks | High | `disasm/gpdasm_output.asm:4240`, `disasm/gpdasm_output.asm:6960`, `disasm/gpdasm_output.asm:9177` |
| RC1 | Input | No direct runtime use found | Low | `disasm/gpdasm_output.asm:6177` |
| RC2 | Input | Role strap (`control/local` vs chain mode), switches SPBRG/clock path | High | `disasm/gpdasm_output.asm:6812`, `disasm/gpdasm_output.asm:7270`, `disasm/gpdasm_output.asm:7284` |
| RC3 | Output/peripheral | No direct GPIO use observed; peripheral/shared role only | Low | `disasm/gpdasm_output.asm:6177` |
| RC4 | USB peripheral | USB D-/VM when USB module enabled | High | `disasm/gpdasm_output.asm:9121`, `39632e.pdf` `RC4/D-/VM` |
| RC5 | USB peripheral | USB D+/VP when USB module enabled | High | `disasm/gpdasm_output.asm:9121`, `39632e.pdf` `RC5/D+/VP` |
| RC6 | UART TX/CK | Current-loop serial TX path | High | `disasm/gpdasm_output.asm:8835`, `disasm/gpdasm_output.asm:8843`, `39632e.pdf` `RC6/TX/CK` |
| RC7 | UART RX/DT | Current-loop serial RX path | High | `disasm/gpdasm_output.asm:8834`, `disasm/gpdasm_output.asm:8844`, `39632e.pdf` `RC7/RX/DT` |

Board-level endpoint context (J3) for USB/MIDI/relay rails is documented in `DLCP-datasheet-R3.pdf` page 7 text extract.

---

## What is still not provable from firmware alone
- Exact net mapping for MAIN outputs `RA6`, `RB2`, `RB3`, `RB4`, `RB5`, `RB6`, `RB7` to specific connector pins (relay control vs amp_enable vs LED) requires PCB netlist/schematic continuity.
- The code clearly toggles these pins, but firmware symbols alone do not encode board-net names.
