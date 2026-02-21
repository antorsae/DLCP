# DLCP CONTROL Firmware Delta Report

## Scope

This document summarizes stock CONTROL firmware deltas for:

- `V1.4 -> V1.5b`
- `V1.5b -> V1.6b`

Focus is on byte-level changes, disassembly-backed behavior changes, and explicit
hypotheses where intent is not provable from binaries alone.

## Method

- Intel HEX byte diff on `firmware/stock/control/*.hex`
- Disassembly cross-check on:
  - `firmware/disasm/control/v1.4_disasm.asm`
  - `firmware/disasm/control/v1.5b_disasm.asm`
  - `firmware/disasm/control/v1.6b_disasm.asm`
- Behavioral cross-check against existing gpsim parity tests:
  - `tests/sim/test_control_v15b_port_compatibility.py`
  - `tests/sim/test_control_v16b_port_compatibility.py`

## Executive Summary

- `V1.4 -> V1.5b` looks like a hardening/update-flow change:
  - remote `cmd=0x18` reset/update behavior removed from main serial handler path
  - multiple config bytes changed to `0xFF`
  - EEPROM byte `0xF000FE` changed `0x01 -> 0xFF`
- `V1.5b -> V1.6b` looks like a UI/menu behavior refactor:
  - large app code changes, no config-word changes
  - EEPROM version byte `0xF00071` changed `0x04 -> 0x06`
  - front-panel/menu strings and display routines reshaped (including "combi display" behavior in prior analysis)
- UART transport programming is unchanged across all three versions.

## Quantified Deltas

### V1.4 -> V1.5b

- Total changed bytes: `4763`
- Region split:
  - app (`0x0000..0x77BF`): `4753`
  - bootloader (`0x77C0..0x7FFF`): `0`
  - config (`0x300000..0x30000D`): `9`
  - EEPROM (`0xF00000..0xF000FF`): `1`
- Changed app ranges: `331`

### V1.5b -> V1.6b

- Total changed bytes: `5166`
- Region split:
  - app (`0x0000..0x77BF`): `5165`
  - bootloader (`0x77C0..0x7FFF`): `0`
  - config (`0x300000..0x30000D`): `0`
  - EEPROM (`0xF00000..0xF000FF`): `1`
- Changed app ranges: `239`

## Detailed Findings

### 1) V1.4 -> V1.5b

#### A. Config-space changes

The following config addresses changed:

| Address | V1.4 | V1.5b |
|---|---:|---:|
| `0x300000` | `0x00` | `0xFF` |
| `0x300004` | `0x00` | `0xFF` |
| `0x300007` | `0x00` | `0xFF` |
| `0x300008` | `0x0F` | `0xFF` |
| `0x300009` | `0xC0` | `0xFF` |
| `0x30000A` | `0x0F` | `0xFF` |
| `0x30000B` | `0xE0` | `0xFF` |
| `0x30000C` | `0x0F` | `0xFF` |
| `0x30000D` | `0x40` | `0xFF` |

Prior analysis already flagged this family as `CONFIG1L` plus `CONFIG5..7`-class hardening/reconfiguration.

#### B. EEPROM change

- `0xF000FE`: `0x01 -> 0xFF`
- Version tuple remains `0xF00070..72 = 01 04 30`.

#### C. Command-path change tied to update/reset behavior

In the serial command handler block around `0x05A2..0x05F4`:

- V1.4 at `0x05C6`: `movlw 0x18` (compare against incoming cmd)
- V1.5b at `0x05C6`: `movlw 0x1D`

In V1.4, the `0x18` path includes EEPROM write + reset sequence (bootloader entry flow). In V1.5b this path is no longer reachable via `cmd=0x18` in that location.

This matches observed behavioral split in tests and docs:

- V1.4 responds to injected `0xBF,0x18,0x01` with reset/update-like flow.
- V1.5b does not.

#### D. UART/EUSART check (explicit)

Init sequence in `0x038C..0x03A0` is byte-identical in V1.4 and V1.5b:

- `SPBRG = 0x05`
- `TXSTA.BRGH = 0`
- `BAUDCON.BRG16 = 0`
- `TXSTA.SYNC = 0`
- `RCSTA.SPEN = 1`
- `TXSTA.TXEN = 1`
- `RCSTA.CREN = 1`

Only the following `goto` target byte at `0x03A2` changes because of downstream code layout shifts.

#### Hypothesis for intent

- High confidence: release goal included preventing host-triggered update/reset entry from the normal runtime command surface.
- Medium confidence: config changes were part of that hardening (and possibly anti-reflash/anti-enumeration behavior from normal product operation).
- Low confidence: every individual config-byte rationale without vendor source.

### 2) V1.5b -> V1.6b

#### A. Config-space stability

- No config-byte differences at `0x300000..0x30000D`.
- This is not another config/hardening jump like `V1.4 -> V1.5b`.

#### B. EEPROM/version change

- `0xF00071`: `0x04 -> 0x06`
- Version tuple: `01 04 30 -> 01 06 30`
- `0xF000FE` remains `0xFF`.

#### C. UI/menu surface refactor evidence

- Large app-only code delta (`5165` bytes) with no bootloader or config changes suggests functional refactor in application behavior.
- Text/location evidence:
  - `"DLCP 1"` present in V1.5b at `0x1414`, absent in V1.6b app region.
  - Header text block shifts:
    - V1.4 `"Volume:"` at `0x1062`
    - V1.5b `"Volume:"` at `0x1052`
    - V1.6b `"Volume:"` at `0x100C`
- Existing analysis attributes V1.6b to "combi display" behavior and reduced front-panel channel-routing UI exposure.

#### D. Handler refactor around `0x0590..0x05EA`

- The command handling block is structurally reshaped again.
- `cmd=0x1D` compare is retained (moved to later bytes due refactor), consistent with keeping the V1.5b-era behavior split from V1.4 `cmd=0x18`.

#### E. UART/EUSART check (explicit)

V1.5b and V1.6b keep the same UART init bytes in `0x038C..0x03A0` (same baud and control bits).

#### Hypothesis for intent

- High confidence: V1.6b focused on user-facing UI/menu behavior (display/menu model), not transport/protocol reconfiguration.
- Medium confidence: removing front-panel routing complexity was deliberate product UX simplification while retaining software/HFD control paths.

## What Did Not Change (Both Transitions)

- Bootloader region bytes (`0x77C0..0x7FFF`) are unchanged in both transitions.
- RC5 profile behavior at dispatch level remains compatible in existing parity tests.
- UART wire parameters stay fixed (31,250 baud setup sequence unchanged).

## Confidence and Limits

- Facts above are high confidence when directly byte/disassembly derived.
- Intent/reason sections are hypotheses and should be treated as informed inference.
- Without vendor source and changelog, exact product-management rationale cannot be proven.
