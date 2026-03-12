# DLCP Preset Test Simulator Framework

## 1. Scope

This document defines the simulation framework for validating DLCP preset functionality
end-to-end with simulation-only overlays and deterministic tests.

Current target matrix:

- Main firmware: `firmware/patched/releases/DLCP_Firmware_V2.5.hex`
- Control firmware: `firmware/patched/releases/DLCP_Control_V1.62b.hex`
- Compatibility control firmware: `firmware/patched/releases/DLCP_Control_V1.61b.hex`
- Topology: one Control + two Main units

Constraints:

- Source HEX files stay clean.
- All simulation-only hooks are applied to temporary HEX files.
- The gate is exhaustive in simulation (no hardware required).

## 2. Goals and Success Criteria

The framework must prove:

1. Control UI preset selection emits the expected current-loop command.
2. Both mains synchronize to the selected preset.
3. HFD logical table writes remain transparent and bank correctly by active preset.
4. Preset state persists across simulated power cycles.
5. Faults (drop, duplicate, corruption) are observable and regression-tested.
6. gpsim execution of control firmware remains decodable at LCD level.

Pass condition:

- Full `tests/sim` suite passes.
- Compatibility-byte checks pass for both patched HEX files.
- Scenario digests remain deterministic.

## 3. Toolchain Prerequisites

Required:

- `python3`
- `gpasm` (for firmware patch build, not required for every test run)
- repo-local `artifacts/tools/gpsim-xtc/bin/gpsim-xtc` (tests also see the
  compatibility shim `artifacts/tools/gpsim-xtc/bin/gpsim`)
- `pytest` (test runner)

Optional:

- `.venv_ep0` virtual environment

Install example:

```bash
.venv_ep0/bin/python -m pip install pytest
```

## 4. Architecture

Framework package: `src/dlcp_fw/sim/`

### 4.1 Modules

- `src/dlcp_fw/sim/hexio.py`
  - Intel HEX parse/write/checksum.
  - byte assertions and patch application.
- `src/dlcp_fw/sim/overlay.py`
  - Simulation overlay manifest engine.
  - chained overlay application into temp HEX.
- `src/dlcp_fw/sim/manifests.py`
  - built-in simulation-only overlays.
  - `control_reset_to_appstart`: reset -> app entry for gpsim.
  - `control_disable_boot_wait`: optional speed overlay.
- `src/dlcp_fw/sim/gpsim.py`
  - deterministic gpsim script generation and execution.
- `src/dlcp_fw/sim/lcd.py`
  - HD44780 decode from `PORT/LAT` write logs.
- `src/dlcp_fw/sim/control_ui.py`
  - keypress-driven control UI behavioral sim.
  - emits current-loop preset frames.
  - persistence model with EEPROM-like store.
- `src/dlcp_fw/sim/main_model.py`
  - main firmware state model with:
    - route filtering
    - command `0x20` handling
    - bank remap logic
    - flash write event log
    - DSP ingest event log
- `src/dlcp_fw/sim/bus.py`
  - current-loop bus delivery and deterministic fault injection.
- `src/dlcp_fw/sim/scenarios.py`
  - roundtrip and fault-matrix scenario helpers.
- `src/dlcp_fw/sim/main_gpsim.py`
  - instruction-level main dispatch runs in gpsim.
  - uses the physical `p18f2455` gpsim model for MAIN.
  - app-only MAIN HEX inputs are merged onto the dump-based
    `DLCP Firmware V2.3-combined.hex` seed before gpsim-only overlays, so tests
    keep recovered boot/config/EEPROM/User-ID context by default.
  - simulation-only UART mailbox hooks for RX/TX probing.
- `src/dlcp_fw/sim/main_gpsim_timer3.py`
  - native no-shim Timer3 compare harness.
  - observes the real `function_079` / `PIR2.TMR3IF` path before parser dispatch.
  - retains UART mailbox hooks + ADC boot-wait hook, but no Timer3 firmware shim.
- `src/dlcp_fw/sim/control_gpsim.py`
  - non-interactive gpsim harness for CONTROL firmware.
  - LCD decode, button injection, serial frame capture.
  - EEPROM read/write via PIC18 SFR registers (EEADR, EEDATA, EECON1/2).
  - applies `control_disable_standby_check` overlay for standalone operation.
  - physical CONTROL silicon and gpsim target are both `PIC18F25K20`
    via the repo-local `gpsim-xtc` build.

### 4.2 Orchestration

CLI: `scripts/simctl.py`

Subcommands:

- `overlay-check`
- `gpsim-lcd`
- `main-gpsim`
- `run-exhaustive`

## 5. Hook Strategy (Simulation-Only)

### 5.1 Why overlays

Stock and patched production HEX files remain unchanged. Hooks are applied only to
generated temp HEX copies used by gpsim/test runners.

### 5.2 Implemented overlays

1. `control_reset_to_appstart`
   - patches reset vector to `goto 0x0040`
   - avoids gpsim stalling in control bootloader path
2. `control_disable_boot_wait` (optional)
   - removes one startup delay call to accelerate simulation
3. `main_reset_to_appstart`
   - patches reset vector to app start (`0x1000`) in gpsim
   - applied after MAIN sim materializes a seeded full-device temp HEX
     (`V2.3-combined` base + requested app bytes in `0x1000..0x55FF`)
4. `main_serial_mailbox_hooks`
   - hooks `function_109/087/111` to mailbox-backed RX/TX probes
   - hooks `function_079` with a Timer3-overflow shim for gpsim
   - hooks `function_024` to bypass ADC-GO wait loops in gpsim
   - RX mailbox: `0x780..0x79F` (with pointers `0x7C0/0x7C1`)
   - TX mailbox: `0x7A0..0x7BF` (with pointer `0x7C3`)
5. `main_serial_mailbox_hooks_uart_only` + `main_adc_boot_wait_hook`
   - used by the native no-shim Timer3 compare path where Timer3 stays unpatched in firmware.
   - a separate AN0 boot regression now proves the stock `function_024` gate can exit with a real gpsim `p18f2455.porta0` analog stimulus.
   - the compare harness still keeps the ADC boot hook because the UART-only overlay currently places helper code inside the `function_024` body.
6. Native-ring chain harness boot
   - the stock/native chain tests now clear `function_024` with a real gpsim `p18f2455.porta0` analog stimulus instead of `main_adc_boot_wait_hook`.
   - those chain tests also stopped forcing `main_ra0_adc=0x0000`; the earlier forced-low default made MAIN's first `BF 03` report standby and only passed when the old hook leaked a stale high ADC sample into the early status path.

### 5.3 Hook categories covered by framework

- Display hook: via LCD decode from actual gpsim pin writes (no fake display model).
- Keypress hook: via `ControlUISim.run_script()`.
- DSP ingest hook: via `MainUnitModel.dsp_ingest` event stream.
- Flash-write hook: via `MainUnitModel.flash_writes`.
- USB hook: modeled at protocol ingress level (logical command/frame injection).

## 6. Data Flow

1. Control UI script produces preset frames (`route=0xB0`, `cmd=0x20`, `data=0|1`).
2. Bus delivers frames to both mains, with optional injected faults.
3. Main model applies preset and logs DSP ingest event.
4. HFD upload writes logical table range `0x5600..0x5FFF`.
5. Active preset determines physical destination:
   - A: `0x5600..0x5FFF`
   - B: `0x4A00..0x53FF`

## 7. Test Suite Layout

Location: `tests/sim/`

- `test_overlay_engine.py`
  - overlay application
  - precondition failure behavior
  - temp-only patch guarantees
- `test_patch_compatibility.py`
  - byte-level compatibility checks
- `test_control_ui_and_persistence.py`
  - keypress -> frame behavior
  - persistence across simulated power cycle
- `test_main_model_banking.py`
  - A/B bank writes and digest divergence
  - flash-write and DSP ingest logging
- `test_bus_faults.py`
  - dropped, duplicated, corrupted frame injection
- `test_scenarios.py`
  - end-to-end scenario execution + fault matrix
- `test_gpsim_control_lcd.py`
  - instruction-level gpsim control run
  - LCD decode validation
- `test_main_gpsim_mailbox.py`
  - instruction-level main command dispatch via mailbox-injected frames
  - verifies parser breakpoint reach + mailbox consume/reply counters
- `test_main_gpsim_timer3_compare.py`
  - semantic-shim vs native no-shim Timer3 comparison checks
  - locks in the observed stock MAIN `0xF830` / prescale-2 Timer3 delay path
- `test_gpsim_multi_processor_uart_topology.py`
  - proves the repo-local gpsim build can host labeled `ctl` + `m0` + `m1`
    in one process and attach `RC6`/`RC7` hop nodes for a two-powerbox chain
- `test_wire_chain_gpsim.py`
  - exercises stock CONTROL `<->` stock MAIN with a live RC6/RC7 bridge
  - keeps gpsim's native EUSART RX timing, `RCREG` FIFO, and overrun logic in play
  - currently locks in MAIN-side real-UART progress and BF status replies without
    claiming full CONTROL UI connection yet
- `test_gpsim_control_presets.py`
  - gpsim instruction-level CONTROL preset UI tests
  - boot default, screen navigation, serial frames, EEPROM persistence, volume volatility
- `test_main_gpsim_preset_banks.py`
  - gpsim instruction-level MAIN bank targeting tests
  - preset A/B bit2 state, sequence switching, broadcast routing

## 8. Test Categories and Expected Outcomes

### A) Boot/UI baseline

- Overlayed control starts at app path.
- LCD decode returns meaningful output (e.g., waiting/volume states).

Expected:

- decoded byte stream length > 0
- final LCD includes recognizable status text

### B) Preset UI behavior

- Setup menu preset toggle emits exactly normalized A/B states.

Expected:

- frame sequence includes `0xB0 0x20 0x01` then `0xB0 0x20 0x00`

### C) Two-main sync

- broadcast frame updates both mains.

Expected:

- both mains same preset and matching apply counts

### D) HFD transparency and banking

- logical upload targets active bank only.

Expected:

- A digest differs from B digest after distinct payloads
- bank write addresses stay in expected windows

### E) Persistence

- preset survives power cycle.

Expected:

- LCD column 15 shows `B` after saving B then cycling
- EEPROM[0x73] = 1 after preset B selection

### F) Fault robustness

- drop/dup/corrupt faults do not cause undefined state.

Expected:

- drop: no preset change
- duplicate: idempotent preset state, increased apply count
- corrupt route/cmd: frame ignored

## 9. Reproducible Commands

Overlay sanity:

```bash
python3 scripts/simctl.py overlay-check
```

gpsim LCD run:

```bash
python3 scripts/simctl.py gpsim-lcd --cycles 50000000
```

Instruction-level main dispatch run:

```bash
python3 scripts/simctl.py main-gpsim --frames 0xB0:0x20:0x01
```

Run with harness-side Timer3 model:

```bash
python3 scripts/simctl.py main-gpsim --timer-model harness --frames 0xB0:0x20:0x01 --stage1-timeout 60
```

Compare semantic shim vs harness Timer3:

```bash
python3 scripts/simctl.py compare-timer3 --frames 0xB0:0x20:0x01
```

Observed current delta (expected):

- semantic mode leaves `REG 0x05E` at `0x00`
- harness Timer3 mode reaches `REG 0x05E = 0x08`
- mailbox counters still converge (`rx_wr == tx_wr == 3`)

Optional stage-1 parser wait tuning:

```bash
python3 scripts/simctl.py main-gpsim --stage1-timeout 30 --parser-break 0x1BEA
```

Exhaustive gate:

```bash
python3 scripts/simctl.py run-exhaustive --pytest-cmd .venv_ep0/bin/pytest
```

Direct pytest:

```bash
.venv_ep0/bin/pytest -q tests/sim
```

## 10. Artifacts and Reporting

Generated artifacts are temporary unless explicitly kept.

Persistent output location:

- `artifacts/sim/current/` (ignored by git)

Recommended report fields for CI:

- control frame count
- bus event count
- left/right apply counts
- A/B table digests (prefix acceptable)
- fault matrix boolean outcomes

## 11. Edge Cases and Robustness Notes

1. gpsim bootloader paths can stall if reset is not redirected.
2. Overlay precondition mismatch should fail fast.
3. Corrupt route (`0xAF`) must never be accepted as current-loop data.
4. Corrupt command (`!=0x20`) must not alter preset state.
5. Duplicate delivery should not corrupt A/B table content.

## 12. Limitations

1. USB transport is modeled at command/frame ingress level, not full USB peripheral timing.
2. Main gpsim path currently validates command-dispatch state and TX probes, not full analog pipeline.
3. DSP validation is ingest/write-intent level, not analog audio output validation.

## 13. Extension Path (A/B/C)

The framework is prepared for C expansion by:

- extending preset value domain to `0,1,2`
- adding third bank window mapping rules
- extending compatibility checks and scenario matrix
- expanding persistence and UI expectations
