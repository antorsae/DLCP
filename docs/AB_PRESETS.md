# DLCP A/B Presets

Reliability-first A/B preset patches for:

- MAIN `V2.3` stock -> patched `V2.4`
- CONTROL `V1.4` stock -> patched `V1.41`
- CONTROL `V1.5b` stock -> patched `V1.51b`
- CONTROL `V1.6b` stock -> patched `V1.61b`

## Status

Current design status:

- Working in the current test gate.
- Full gpsim-inclusive suite passes: `211 passed`.
- Full collect-only count: `211 tests collected`.
- `V1.61b` includes and preserves the real-hardware fix for the stale Setup LCD garbage issue.
- Real-hardware confirmation: `DLCP_Firmware_V2.4.hex` + `DLCP_Control_V1.61b.hex` was flashed and verified working on a real unit.

This document supersedes the earlier filename-display design. The current patch set does **not** transport or display DSP filenames on the CONTROL LCD.

## Design Goals

The current implementation is intentionally minimal.

Goals:

- keep bootloader and firmware-update risk low
- keep MAIN table banking simple and local to MAIN
- make preset switching idempotent
- avoid current-loop chatter that proved brittle on hardware
- preserve stock command compatibility outside the new `cmd=0x20` preset command

Non-goals in the current design:

- no DSP filename fetch/display on CONTROL
- no `0x21` / `0x22` / `0x2F` / `0x30..0x37` filename side protocol
- no periodic preset spam beyond bounded retry bursts
- no attempt to turn CONTROL into the authority for per-unit DSP metadata

## User-Visible Behavior

Top-level screens:

- `Volume` -> state `0`
- `Preset` -> state `1`
- `Input` -> state `2`
- `Setup` -> state `3`

Navigation wraps across 4 screens.

Preset behavior:

- On the `Preset` screen, `UP` selects preset `A`.
- On the `Preset` screen, `DOWN` selects preset `B`.
- Selecting the already-active preset is idempotent.
- The `Volume` screen shows the active preset at LCD column 15.
- The `Preset` screen is simple text only:
  - line 1: `Preset`
  - line 2: `Active: A` or `Active: B`

IR behavior:

- RC5 `F1` (`0x38`) selects preset `A`.
- RC5 `F2` (`0x39`) selects preset `B`.
- IR switching is idempotent.
- IR switching updates internal preset state even when the Preset screen is not visible.

Examples:

```text
Screen 0 (Volume, A):        Screen 1 (Preset, A):
|Volume:        A|           |Preset          |
|-96.0 dB        |           |Active: A       |

Screen 0 (Volume, B):        Screen 1 (Preset, B):
|Volume:        B|           |Preset          |
|-96.0 dB        |           |Active: B       |
```

## Protocol

The only new current-loop command in the A/B feature is:

- `cmd=0x20`, data `0` for preset `A`, data `1` for preset `B`

Protocol policy:

- route: broadcast `0xB0`
- no filename metadata commands are added
- no preset readback command is added

CONTROL retry policy:

- explicit user or IR preset change:
  - send one immediate `0x20`
  - queue `2` more retries
- boot:
  - queue `3` retries
- reconnect:
  - queue `3` retries when link-connected transitions `0 -> 1`
- retries are emitted one-per-full-sync cycle
- retries terminate after the bounded budget is exhausted

This is deliberate. The design trades immediate metadata richness for lower link complexity and better recovery characteristics.

## MAIN Patch (`V2.4`)

Patch strategy:

1. Copy stock preset table `A` from `0x5600..0x5FFF` to table `B` at `0x4A00..0x53FF`.
2. Remap flash read/write/erase access into the `B` window when preset `B` is active.
3. Add idempotent current-loop `cmd=0x20` handling.
4. Leave stock USB `cmd03` filename paths intact.

Patch map:

| Component | Address | Purpose |
|---|---:|---|
| Table copy `A -> B` | `0x4A00..0x53FF` | Clone of stock DSP table bank |
| Read remap stub | `0x5400` | Redirect reads from `0x56xx..0x5Fxx` to `0x4Axx..0x53xx` when `B` active |
| Write remap stub | `0x5440` | Redirect table writes to `B` bank when `B` active |
| Erase remap stub | `0x54C0` | Redirect table erase window to `B` bank when `B` active |
| Command tail stub | `0x5500` | Preserve stock `0x1D` / `0x1E`, add idempotent `0x20` |
| Hook sites | `0x1E64`, `0x2E6E`, `0x3DAC`, `0x4028` | Redirect to the stubs above |

Runtime preset state:

- MAIN uses `0x05E.2`
- `0` = preset `A`
- `1` = preset `B`

`cmd=0x20` behavior:

- if requested preset equals current preset: do nothing
- if requested preset differs: update `0x05E.2`, then call the stock table-apply routine once

Important stock behavior preserved:

- stock USB `cmd03` handler bytes at `0x20BE` and `0x27C0` are unchanged
- stock filename persistence behavior remains available for USB/HFD tooling
- removed filename transport commands `0x21` / `0x22` are ignored on the current-loop path

Version policy:

- EEPROM tuple remains stock-style `2.30` at `0xF00080..0xF00082`
- USB-visible application version is patched to `2.4`

## CONTROL Patch (`V1.41`, `V1.51b`, `V1.61b`)

Common design across all three CONTROL ports:

- add `Preset` as top-level menu state `1`
- keep `Volume`, `Input`, `Setup`
- use `0x01F.6` as runtime preset bit
- persist preset at `EEPROM[0x74]`
- keep bounded retry state in bank 1 patch-owned RAM:
  - `0x170` retry budget
  - `0x171` reconnect shadow
  - `0x172` last-drawn preset on Preset screen
- force boot to `Volume` by clearing menu state `0x0BF`
- no parser-tail filename hook
- no filename cache RAM
- no filename request sender

### CONTROL `V1.41`

Key hook points:

| Component | Address | Purpose |
|---|---:|---|
| Startup flag init | `0x1106` | Preserve stock bit clearing for `0x01F.3/.4` |
| Startup boot wrapper hook | `0x116E` | Load stock settings, restore preset from `EEPROM[0x74]`, seed retry state, clear menu state |
| Dispatch hook | `0x123E` | Add 4-screen top-level dispatch |
| Volume hook | `0x13AE` | Overlay `A/B` in volume header |
| Full-sync hook | `0x0B52` | Emit one queued preset retry per cycle |
| IR hook | `0x0E46` | Add F1/F2 preset shortcuts before stock IR path |
| TX helper target | `0x0608` | Stock serial TX byte helper used by preset sender |

### CONTROL `V1.51b`

Key hook points:

| Component | Address | Purpose |
|---|---:|---|
| Startup flag init | `0x10F6` | Preserve stock bit clearing for `0x01F.3/.4` |
| Startup boot wrapper hook | `0x1160` | Load stock settings, restore preset from `EEPROM[0x74]`, seed retry state, clear menu state |
| Dispatch hook | `0x1230` | Add 4-screen top-level dispatch |
| Volume hook | `0x13A0` | Overlay `A/B` in volume header |
| Full-sync hook | `0x0B2C` | Emit one queued preset retry per cycle |
| IR hook | `0x0E32` | Add F1/F2 preset shortcuts before stock IR path |
| TX helper target | `0x05E2` | Stock serial TX byte helper used by preset sender |

### CONTROL `V1.61b`

Key hook points:

| Component | Address | Purpose |
|---|---:|---|
| Startup flag init | `0x10B2` | Preserve stock bit clearing for `0x01F.3/.4` |
| Startup boot wrapper hook | `0x111C` | Load stock settings, restore preset, preserve setup fix, seed retry state, clear menu state |
| Dispatch hook | `0x11F0` | Add 4-screen top-level dispatch |
| Volume hook | `0x137A` | Overlay `A/B` in volume header |
| Full-sync hook | `0x0B36` | Emit one queued preset retry per cycle, then continue stock `V1.6b` full-sync flow |
| IR hook | `0x0DE6` | Add F1/F2 preset shortcuts before stock IR path |
| TX helper target | `0x05EC` | Stock serial TX byte helper used by preset sender |

## `V1.61b` Setup LCD Garbage Fix

This fix is preserved in the current simplified design.

Problem:

- stock `V1.6b` restores stale `EEPROM[0x01]` into live setup index `0x0BA`
- `V1.6b` only retains one visible Setup item (`BL Timeout`)
- a nonzero stale index makes the setup renderer walk into code bytes instead of the one valid string
- result on real hardware: garbage label text on the Setup screen

Patched `V1.61b` boot wrapper behavior:

- after stock settings load, check live `0x0BA`
- if nonzero:
  - clear `0x0BA`
  - rewrite `EEPROM[0x01] = 0x00` once
- then continue normal preset restore and retry seeding

This fix has:

- semantic verifier coverage
- gpsim regression coverage
- real-hardware confirmation

## Persistence

Preset persistence is intentionally isolated.

CONTROL:

- preset stored only at `EEPROM[0x74]`
- deep EEPROM-diff tests confirm preset toggles do not mutate unrelated CONTROL EEPROM bytes

MAIN:

- bank selection is runtime state in `0x05E.2`
- bank contents live in flash table windows:
  - `A`: `0x5600..0x5FFF`
  - `B`: `0x4A00..0x53FF`
- USB/HFD writes target the currently active bank through the stock write/erase path plus bank remap stubs

## Deliberate Removal of Filename Display

The earlier filename-display implementation was removed.

Reasons:

- it added a second current-loop protocol with more traffic and more race surface
- it was not reliable enough on real hardware
- it interfered with the core requirement: reliable preset switching without hangs or side effects

Current policy:

- MAIN still retains stock USB filename storage behavior for host tooling analysis/tests
- CONTROL does not request or display DSP filenames
- current-loop commands `0x21` / `0x22` / `0x2F` / `0x30..0x37` are not part of the shipped A/B design

## Build, Verify, Test

Build patched firmware:

```bash
python3 -m dlcp_fw.patch.build_main_presets_ab
python3 -m dlcp_fw.patch.build_control_presets_ab
python3 -m dlcp_fw.patch.build_control_presets_ab_v15b
python3 -m dlcp_fw.patch.build_control_presets_ab_v16b
```

Run static verification:

```bash
python3 -m dlcp_fw.patch.verify_presets_ab
python3 -m dlcp_fw.patch.verify_presets_ab --control-new-v151b --control-profile v15b
python3 -m dlcp_fw.patch.verify_presets_ab --control-new-v161b --control-profile v16b
```

Run full gpsim-inclusive test gate:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim
.venv_ep0/bin/python -m pytest -q tests/sim --collect-only
```

Current result:

- `211 passed`
- `211 tests collected`

## Test Coverage Summary

Key coverage for the simplified design:

| Area | Tests |
|---|---|
| MAIN bank mapping and idempotent `0x20` | `tests/sim/test_main_model_banking.py`, `tests/sim/test_main_gpsim_preset_banks.py` |
| MAIN stock command compatibility | `tests/sim/test_main_gpsim_command_compatibility.py`, `tests/sim/test_main_gpsim_command_matrix.py`, `tests/sim/test_main_gpsim_command_edges.py` |
| MAIN stock `cmd03` filename path left intact | `tests/sim/test_main_dsp_filename_sim_validation.py`, `tests/sim/test_main_gpsim_cmd03_instruction_path.py` |
| MAIN DSP refresh behavior on preset switch | `tests/sim/test_main_dsp_refresh_behavior.py` |
| CONTROL UI model behavior | `tests/sim/test_control_ui_and_persistence.py` |
| CONTROL gpsim screen navigation and persistence | `tests/sim/test_gpsim_control_presets.py` |
| CONTROL IR preset switching | `tests/sim/test_control_gpsim_ir_preset_switch.py` |
| CONTROL bounded boot/reconnect retry bursts | `tests/sim/test_control_main_powercycle_sync.py` |
| CONTROL EEPROM isolation for preset toggles | `tests/sim/test_control_gpsim_preset_eeprom_diff.py` |
| `V1.51b` stock-delta preservation | `tests/sim/test_control_v15b_port_compatibility.py` |
| `V1.61b` stock-delta preservation + setup-fix migration | `tests/sim/test_control_v16b_port_compatibility.py` |
| Static semantic guards on all patched profiles | `tests/sim/test_verify_presets_ab_semantic_guards.py`, `tests/sim/test_verify_presets_ab_v15b_semantic_guards.py`, `tests/sim/test_verify_presets_ab_v16b_semantic_guards.py` |

## Flashing Notes

Patch scope:

- no bootloader bytes are intentionally modified
- no filename transport is required for the feature
- A/B switching becomes active only when both MAIN and CONTROL are patched

Practical order:

- safest operational order is usually MAIN first, CONTROL second
- reason: stock CONTROL never emits `cmd=0x20`, so patching MAIN first is inert
- patching CONTROL first is still non-destructive, but preset switching will not function until MAIN is patched

Relevant release files:

- `firmware/patched/releases/DLCP_Firmware_V2.4.hex`
- `firmware/patched/releases/DLCP_Control_V1.41.hex`
- `firmware/patched/releases/DLCP_Control_V1.51b.hex`
- `firmware/patched/releases/DLCP_Control_V1.61b.hex`

Bench-verified pair:

- `firmware/patched/releases/DLCP_Firmware_V2.4.hex`
- `firmware/patched/releases/DLCP_Control_V1.61b.hex`

## Known Limits

- Preset domain is still binary: `A/B` only.
- CONTROL is not authoritative for per-unit routing in the way stock `V1.5b` UI attempted to be.
- DSP filename display is intentionally absent from CONTROL.
- TAS3108 itself is not simulated; tests validate firmware-level behavior, routing, persistence, and command flow.

## Related Documents

- `AGENTS.md`
- `docs/R_L_ROUTING.md`
- `docs/SIMULATION.md`
- `docs/TEST_SIMULATOR.md`
- `docs/analysis/CONTROL_FW_VERSION_DIFFS.md`
- `docs/analysis/CONTROL_UNIT_ANALYSIS.md`
