# gpsim `PIC18F25K20` Port Plan

Date: 2026-03-11

Status update (2026-03-12):

- the fork is now implemented at `vendor/gpsim-0.32.1-xtc/`
- the local binary is `scripts/gpsim-xtc`
- repo CONTROL gpsim harnesses now use `p18f25k20` directly
- the planning detail below is retained as the implementation brief / historical rationale

## Recommendation

Move the downloaded upstream tree out of the repository root and keep it as an explicit local fork:

- proposed source path: `vendor/gpsim-0.32.1-xtc/`
- proposed installed binary name: `gpsim-xtc`
- proposed build/output area: `artifacts/tools/gpsim-xtc/`

Rationale:

- `gpsim-0.32.1/` at repo root looks like a temporary drop, not a maintained fork.
- `vendor/gpsim-0.32.1-xtc/` preserves the upstream version and makes local divergence obvious.
- `gpsim-xtc` avoids ambiguity with the system `gpsim` already installed on the machine.
- keeping build outputs under `artifacts/` avoids polluting the source tree.

If you later update to a newer upstream base, keep the fork naming pattern:

- `vendor/gpsim-0.32.2-xtc/`
- `vendor/gpsim-0.33.x-xtc/`

## Current Evidence

At the time of this plan, the physical CONTROL MCU was already known to be
`PIC18F25K20`, but the installed system `gpsim` did not support it. The repo
now uses the local `gpsim-xtc` fork and selects `p18f25k20` directly in
[control_gpsim.py](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/src/dlcp_fw/sim/control_gpsim.py#L50).

The upstream source tree already supports many nearby PIC18 parts in [PROCESSORS](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/PROCESSORS#L35), including `pic18f2520`, `pic18f2455`, `pic18f2550`, and `pic18f26k22`, but not `pic18f25k20`.

The CONTROL firmware actively uses the K20-era register block at `0xF7A..0xF7F`, plus enhanced EUSART SFRs:

- startup clears `0xF7A`, `0xF7B`, `0xF7E`, `0xF7F` and touches `0xF7D` at [v1.6b_disasm.asm](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/disasm/control/v1.6b_disasm.asm#L610)
- later code sets another bit in `0xF7D` at [v1.6b_disasm.asm](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/disasm/control/v1.6b_disasm.asm#L2788)
- the firmware also uses `BAUDCON` at [v1.6b_disasm.asm](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/firmware/disasm/control/v1.6b_disasm.asm#L622)

The real `PIC18F25K20` header map has:

- `CM2CON1 0xF79`, `CM2CON0 0xF7A`, `CM1CON0 0xF7B`, `IOCB 0xF7D`, `ANSEL 0xF7E`, `ANSELH 0xF7F`
- `SPBRGH 0xFB0`, `BAUDCON 0xFB8`, `ADCON2 0xFC0`

See [p18f25k20.inc](/opt/homebrew/share/gputils/header/p18f25k20.inc#L68).

This is exactly why `p18f2550` is a misleading surrogate for CONTROL: it maps `0xF7A..0xF7F` to USB endpoint registers instead of comparator / IOC / analog-select registers. See [p18f2550.inc](/opt/homebrew/share/gputils/header/p18f2550.inc#L84).

## Best Porting Strategy

Do not implement `PIC18F25K20` as a clone of `P18F2550`.

Recommended approach:

- add a new `P18F25K20` model in `src/p18fk.h` and `src/p18fk.cc`
- borrow K-series register modeling from `P18F14K22`
- borrow the 28-pin package / port topology from `P18F2x21`
- keep the memory geometry and access-bank split of the real `PIC18F25K20`

Why this base is best:

- `P18F14K22` already models K-series style `CMxCON0`, `CM2CON1`, `ANSEL/ANSELH`, `IOCB`, `WPUB`, `SPBRGH`, and `BAUDCON` in [p18fk.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18fk.cc#L399)
- `P18F2x21` already models the correct 28-pin family layout for the `18F2520/2550` line in [p18x.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18x.cc#L1939)
- the real `PIC18F25K20` linker geometry is `32 KB` program space with GPRs through `0x5FF` and access SFRs beginning at `0xF60`, which matches the K20 header and linker script in [18f25k20_g.lkr](/opt/homebrew/share/gputils/lkr/18f25k20_g.lkr#L21)

Avoid using `P18F26K22` as the direct base:

- it is K-series, but it has moved registers, many extra peripherals, different `ANSELx` placement, and much larger RAM/EEPROM state in [p18fk.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18fk.cc#L1018)

## Detailed Task

### 1. Fork Layout

- move current upstream drop from `gpsim-0.32.1/` to `vendor/gpsim-0.32.1-xtc/`
- add a short `README.md` in that directory with:
  - upstream version
  - source URL or tarball provenance
  - local modifications policy
  - local binary name `gpsim-xtc`
- keep build outputs out of the fork source tree

### 2. Add the New Processor Identity

Update the processor type enum in [pic-processor.h](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/pic-processor.h#L70):

- add `_P18F25K20_`

Update the processor constructor table in [pic-processor.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/pic-processor.cc#L321):

- add a `ProcessorConstructor` entry for:
  - `__18F25K20`
  - `pic18f25k20`
  - `p18f25k20`
  - `18f25k20`

Update [PROCESSORS](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/PROCESSORS#L35):

- add `pic18f25k20` to the supported PIC18 list

### 3. Add the Device Class

Implement a new `P18F25K20` class in [p18fk.h](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18fk.h#L52) and [p18fk.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18fk.cc#L45).

Recommended shape:

- base class: `_16bit_processor`
- package: 28-pin
- access GPR split: `0x60`
- program memory size: `0x8000`
- last actual GPR: `0x05FF`
- EEPROM size: `256`
- base ISA: `_PIC18_PROCESSOR_`

The goal is a hybrid:

- package and port topology similar to `P18F2x21`
- K-series SFR block and comparator/ANSEL behavior similar to `P18F14K22`

### 4. Create the 28-Pin I/O Package Map

Implement `create_iopin_map()` for the real 28-pin device.

Use the existing `P18F2x21` 28-pin mapping in [p18x.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18x.cc#L1845) as the starting point, then verify against the `PIC18F25K20` datasheet pinout.

Minimum requirements for DLCP CONTROL fidelity:

- `RA1`, `RA2`, `RA3`, `RA4` must behave correctly because the harness drives those buttons
- `RC0` and `RC5` must behave correctly for the remaining buttons
- `RC6` / `RC7` must be correct for the control-unit serial path
- `RB` port pull-up / IOC behavior must be present because CONTROL uses `IOCB`

### 5. Create the Real SFR Map

This is the most important part.

The new model must expose the real K20 SFRs used by CONTROL:

- `CM2CON1 @ 0xF79`
- `CM2CON0 @ 0xF7A`
- `CM1CON0 @ 0xF7B`
- `IOCB    @ 0xF7D`
- `ANSEL   @ 0xF7E`
- `ANSELH  @ 0xF7F`
- `SPBRGH  @ 0xFB0`
- `BAUDCON @ 0xFB8`
- `ADCON2  @ 0xFC0`

The source reference for that layout is [p18f25k20.inc](/opt/homebrew/share/gputils/header/p18f25k20.inc#L68).

Do not expose USB endpoint SFRs at `0xF7A..0xF7F`.

This is the current CONTROL mis-modeling problem in `p18f2550`, where `UEP10..UEP15` occupy those addresses in [p18f2550.inc](/opt/homebrew/share/gputils/header/p18f2550.inc#L84).

Implementation guidance:

- reuse `ComparatorModule2`, `CMxCON0_V2`, and `CM2CON1_V2` patterns from `P18F14K22`
- reuse `ANSEL_2A` style analog-select registers from `P18F14K22`
- reuse `WPU` and `IOC` setup for Port B from `P18F14K22`
- reuse enhanced USART support for `SPBRGH` and `BAUDCON`
- keep the ADC wiring compatible with the K20 analog channel layout

### 6. Remove Old Assumptions from the Model

If the new class starts from any `P18F2x21` logic, make sure to remove or avoid the old-register assumptions from [p18x.cc](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/vendor/gpsim-0.32.1-xtc/src/p18x.cc#L1935):

- old `CMCON` / `CVRCON`-centric comparator setup
- old analog-channel assumptions tied to `P18F2520/2550`
- any USB SFR block registration

### 7. Oscillator and Config Semantics

The model does not need perfect low-power behavior for DLCP work, but it does need sane config-word handling.

Verify:

- K20 config-word naming and bit decoding
- oscillator mode handling
- access-bank split and valid RAM range
- POR values for `ANSEL`, `ANSELH`, `IOCB`, `WPUB`

The K20 linker geometry to match is in [18f25k20_g.lkr](/opt/homebrew/share/gputils/lkr/18f25k20_g.lkr#L21).

### 8. CLI and Build Verification

After implementation, the fork must pass the basic discovery checks:

- `processor p18f25k20` works in gpsim CLI
- `processor list` includes `pic18f25k20`
- a simple `load` of the DLCP CONTROL HEX does not error out immediately

### 9. Regression Tests Inside the gpsim Fork

Add a minimal upstream-style regression for the new processor.

At minimum:

- instantiate `p18f25k20`
- verify package pins exist for `porta1`, `porta2`, `porta3`, `porta4`, `portc0`, `portc5`, `portc6`, `portc7`
- verify writes to `0xF7A..0xF7F` land on comparator / IOC / ANSEL registers, not USB regs
- verify `SPBRGH` and `BAUDCON` exist and are writable

If practical, add a small assembly test that:

- clears `CM1CON0`, `CM2CON0`, `ANSEL`, `ANSELH`
- toggles `IOCB`
- configures EUSART
- asserts the expected SFR values

### 10. Reintegrate with This DLCP Repo

Integration status after the fork build:

- [control_gpsim.py](/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis/src/dlcp_fw/sim/control_gpsim.py#L54) now selects `p18f25k20`
- scripts that assumed the surrogate name have been updated
- CONTROL gpsim tests have been rerun on the repo-local fork

Priority DLCP tests after the port:

- `tests/sim/test_gpsim_control_lcd.py`
- `tests/sim/test_control_v16b_port_compatibility.py`
- `tests/sim/test_robustness_waiting.py`
- `tests/sim/test_chain_gpsim_waiting.py`
- `tests/sim/test_chain_gpsim_v25_recovery.py`
- `tests/sim/test_chain_gpsim_v25_v162b_recovery.py`

## Acceptance Criteria

The port is successful when all of these are true:

1. `gpsim-xtc` accepts `processor p18f25k20`.
2. The CONTROL firmware boots under `p18f25k20` without using a surrogate processor.
3. The CONTROL startup writes at `0xF7A..0xF7F` affect the correct K20 register block.
4. Existing CONTROL gpsim tests pass with the real target selected.
5. The standby / reconnect / `WAITING FOR DLCP` tests no longer rely on a USB-part surrogate for CONTROL.

Current status:

- criteria `1` through `5` are now satisfied for the CONTROL-side processor model
- remaining DLCP chain failures are in MAIN-side simulation behavior, not missing `PIC18F25K20` support

## Practical Notes

- `p18f2520` is the best currently supported fallback, but it is still only a fallback.
- `p18f2550` is acceptable for some UI regression work, but it is specifically wrong at the addresses CONTROL touches early in boot.
- The port does not need full nanoWatt or power-management fidelity to be useful for DLCP analysis.
- The priority is correct package pins, correct SFR map, correct USART/MSSP/ADC behavior, and correct CONTROL boot/reconnect execution.
