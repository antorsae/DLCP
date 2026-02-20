# DLCP A/B Presets

Binary patches to CONTROL V1.4/V1.5b and MAIN V2.3 firmware that add
dual-bank preset (A/B) support.  The stock firmware has a single preset
table; this patch adds a second bank so users can switch between two
independent DSP configurations without re-uploading via HFD.

## Status

**Working.**  Build, verify, protocol simulation, and full test suite all
pass.  Patched HEX files are ready for flashing.

## What It Does

### User-visible behavior

- **Preset is a top-level menu screen** between Volume and Input.
- Navigation: Volume(0) → Preset(1) → Input(2) → Setup(3) → (wrap).
- On the Preset screen, UP selects **Preset A**, DOWN selects **Preset B**.
- The active preset is shown with selection brackets `>A<` or `>B<`.
- The Volume screen shows the active preset letter at column 15:
  `Volume:        A` or `Volume:        B`.
- IR shortcuts on the Hypex RC5 remote are supported:
  `F1` (`0x38`) selects Preset A, `F2` (`0x39`) selects Preset B.
- IR preset switching is idempotent: pressing F1 while already on A (or F2
  while already on B) performs no extra preset TX/persist writes.
- IR preset switching updates runtime state regardless of current menu screen.
  If the active screen shows preset state (Volume or Preset), the display is
  refreshed to the new A/B state.
- USBaudio sub-parameter is **preserved** (not repurposed).
- HFD table uploads are transparent — they always target the active preset's
  bank.  Switching presets changes which physical flash region is written.
- On boot, CONTROL emits a one-time preset sync frame (`0xB0 0x20 0|1`)
  after restoring EEPROM state.
- CONTROL also re-emits preset during the existing full-sync cycle, so
  late-joining/rebooted MAIN units resync to the active preset.

### LCD layout

```
Screen 0 (Volume):          Screen 1 (Preset, A active):
|Volume:        A|          |Preset       >A<|
|-96.0dB         |          |              B |

Screen 1 (Preset, B active):
|Preset        A |          Screen 2 (Input):       Screen 3 (Setup):
|             >B<|          |Input:          |      |Setup           |
                            |Auto Detect     |      |DLCP 1          |
```

### Protocol

- New current-loop command **`0x20`** (set preset), data = `0` (A) or `1` (B).
- Routed as broadcast `0xB0` so all MAIN units in the chain switch together.
- Command `0x20` was chosen to avoid collision with existing handlers
  (`0x1F` is already used in MAIN firmware).

### MAIN firmware patch (V2.3)

| Component | Address range | Description |
|-----------|---------------|-------------|
| Table copy A→B | `0x4A00..0x53FF` | Clone of original table at `0x5600..0x5FFF` (0xA00 bytes) |
| Read remap | `0x5400` (stub) | `function_061_patch`: remaps TBLRD high-byte from `0x56..0x5F` to `0x4A..0x53` when preset B active |
| Write remap | `0x5440` (stub) | `function_025_patch`: remaps flash-write destination for preset B |
| Erase remap | `0x54C0` (stub) | `function_054_patch`: remaps erase start/end window for preset B |
| Command dispatch | `0x5520` (stub) | `cmd_tail_patch`: preserves legacy `cmd=0x1D` and `cmd=0x1E` branches, then handles `cmd=0x20` with idempotent set/clear of `0x05E.2` and conditional `apply_table` (`0x4574`) |
| Hook points | `0x1E64`, `0x2E6E`, `0x3DAC`, `0x4028` | `goto` redirections to stubs above |

The active preset is stored as bit2 of RAM `0x05E`:
- `0x05E.2 = 0` → Preset A (table at `0x5600`)
- `0x05E.2 = 1` → Preset B (table at `0x4A00`)

### CONTROL firmware patch (V1.4) — top-level Preset screen

| Component | Address range | Description |
|-----------|---------------|-------------|
| Startup flag init | `0x1106` | `bcf 0x01F,3` → `clrf 0x01F` so preset/latch bits start deterministic |
| Startup preset-load hook | `0x116E` | Redirects stock `call function_026` to wrapper that preserves stock load then restores preset from EEPROM `0x74` into `0x01F.6` |
| Version splash tweak | `0x11A4` | `movlw 0x04` → `movlw 0x29` so splash shows `Firmware V1.41` |
| Navigation wrap | `0x1264`, `0x1288` | `movlw 0x02` → `movlw 0x03` (4-screen wraparound) |
| String table fix (Setup) | `0x149A` | `movff 0xBF,0x027` → `movlw 0x02; movwf 0x027` (state 3 → index 2) |
| String table fix (Input) | `0x1A08` | `movff 0xBF,0x027` → `movlw 0x01; movwf 0x027` (state 2 → index 1) |
| Dispatch redirect | `0x123E` | `goto new_dispatch_stub` — routes states 1/2/3 to correct functions |
| IR dispatch pre-hook | `0x0E46` | `goto ir_dispatch_pre_stub` — adds F1/F2 preset shortcuts, then tail-jumps to stock IR dispatcher |
| Volume indicator | `0x13AE` | `goto volume_indicator_stub` — shows A/B at LCD column 15 |
| Full-sync hook | `0x0B52` | `goto full_sync_entry_stub` — emits periodic preset sync (`0x20`) via TX-only path |
| Stub block | `0x7000+` | Boot-load wrapper, dispatch, volume indicator, full-sync, preset screen, frame send helpers |
| Send preset TX-only | `0x7000+` | `send_preset_frame_txonly`: transmits route=0xB0 cmd=0x20 data=(bit6) |
| Send preset + persist | `0x7000+` | `send_preset_frame`: TX-only send + EEPROM write at `0x74` |
| Preset runtime state | `0x01F.6` | `0=A`, `1=B` (state_flags bit6; avoids collision with stock `0x0EB`) |

**USBaudio labels and command are preserved** — no text patches applied.

### CONTROL firmware port mapping (V1.5b → V1.51b)

V1.51b is the V1.5b rebase of the same A/B feature set used by V1.41.

| Patch element | V1.41 address (from V1.4) | V1.51b address (from V1.5b) | Notes |
|---------------|----------------------------|-----------------------------|-------|
| Startup flag init | `0x1106` | `0x10F6` | `bcf 0x01F,3` → `clrf 0x01F` |
| Startup preset-load hook | `0x116E` | `0x1160` | Redirect stock `call function_026` to wrapper |
| Version splash literal | `0x11A4` (`0x29`) | `0x1196` (`0x33`) | Splash shows `1.41` vs `1.51` |
| Navigation wrap | `0x1264`, `0x1288` | `0x1256`, `0x127A` | `movlw 0x03` for 4-screen wrap |
| String index fix (Setup) | `0x149A` | `0x148C` | Force Setup title index = 2 |
| String index fix (Input) | `0x1A08` | `0x19FA` | Force Input title index = 1 |
| Dispatch redirect | `0x123E` | `0x1230` | Redirect to `new_dispatch_stub` |
| Volume indicator hook | `0x13AE` | `0x13A0` | Redirect to `volume_indicator_stub` |
| Full-sync hook | `0x0B52` | `0x0B2C` | Redirect to `full_sync_entry_stub` |
| IR dispatch pre-hook | `0x0E46` | `0x0E32` | Redirect to `ir_dispatch_pre_stub` |

Retargeted stock call/jump anchors inside the V1.51b stub:

| Stub reference | V1.41 target | V1.51b target |
|----------------|--------------|---------------|
| `function_026` (startup settings load) | `0x0A62` | `0x0A3C` |
| `function_042` (volume screen draw) | `0x0D24` | `0x0CFE` |
| `function_052` (Input screen) | `0x1A00` | `0x19F2` |
| `function_047` (Setup screen) | `0x1492` | `0x1484` |
| IR passthrough label | `0x0E4C` | `0x0E38` |
| Full-sync loop targets | `0x0BA8` / `0x0B5A` | `0x0B82` / `0x0B36` |
| Serial TX byte helper | `0x0608` | `0x05E2` |

Bit allocation note for V1.51b:
- Preset state remains `0x01F.6` (`0=A`, `1=B`).
- The boot-time one-shot resync latch uses `0x01F.7` in V1.51b
  (V1.5b uses bit5 in stock logic).

### EEPROM persistence

Preset persistence is decoupled from stock BL-timeout storage:

- Runtime preset state is `state_flags bit6` (`0x01F.6`), not RAM `0x0EB`.
- User preset changes persist to **EEPROM `0x74`** in `send_preset_frame`.
- Boot restore runs from a startup wrapper (hook at `0x116E` on V1.41,
  `0x1160` on V1.51b):
  it calls stock `function_026`, then reads EEPROM `0x74` and sets/clears
  `0x01F.6` (`0x01` => B, anything else => A).
- Periodic/full-sync preset broadcasts use TX-only send and do not write EEPROM.
- Stock BL-timeout behavior (`0x0EB`/EEPROM `0x73` and its clamps) is unchanged.
- CONTROL EEPROM version tuple:
  - V1.41: `0xF00070..72 = 01 04 31`
  - V1.51b: `0xF00070..72 = 01 05 31`
- MAIN EEPROM version tuple is kept at stock `2.30` (`0xF00080..82 = 02 03 30`).
- MAIN USB host-info version literal is patched to `2.4` in app code
  (`0x240C/0x2412/0x2416 = 03/02/04` in the `cmd=0x06` response path).

Volume (`0x0B9`) is **not persisted** in stock firmware — it is volatile and
synced from the MAIN unit via serial command `0x07`.  Volume resets to its
default value on every power cycle.

## Artifacts

| File | Description |
|------|-------------|
| `firmware/patched/releases/DLCP_Firmware_V2.4.hex` | Patched MAIN firmware |
| `firmware/patched/releases/DLCP_Control_V1.41.hex` | Patched CONTROL firmware |
| `firmware/patched/releases/DLCP_Control_V1.51b.hex` | Patched CONTROL firmware (V1.5b port baseline) |

## Build

Requires `gpasm` (from gputils) and Python 3.

```bash
python3 -m dlcp_fw.patch.build_main_presets_ab      # -> firmware/patched/releases/DLCP_Firmware_V2.4.hex
python3 -m dlcp_fw.patch.build_control_presets_ab      # V1.4  -> V1.41
python3 -m dlcp_fw.patch.build_control_presets_ab_v15b # V1.5b -> V1.51b
```

Both scripts accept `--in-hex`, `--out-hex`, and `--gpasm` overrides.
`build_main_presets_ab.py` also accepts `--force-copy` to overwrite a
non-erased destination range.

## Verification and Simulation

### Static verification

```bash
# MAIN + CONTROL V1.4 -> V1.41 path
python3 -m dlcp_fw.patch.verify_presets_ab

# MAIN + CONTROL V1.5b -> V1.51b path
python3 -m dlcp_fw.patch.verify_presets_ab --control-new-v151b --control-profile v15b
```

Byte-level checks: table copy correctness, hook signatures, cmd dispatch,
navigation wrap, string index fixes, volume/full-sync hooks, preset stub
presence, and profile-specific V1.5b hook-target validation.

### Protocol simulation (no gpsim needed)

```bash
# Basic two-main preset sync:
python3 scripts/sim_presets_ab.py

# End-to-end Control<->Main link simulation:
python3 scripts/sim_link_control_main_presets_ab.py

# Console LCD UI simulation (scripted key presses):
python3 scripts/sim_control_ui_presets.py --script "R,D,R,R,R"
```

### Test suite (pytest)

```bash
# Python-level tests (no gpsim required):
python3 -m pytest tests/sim/ -q -k "not gpsim"

# gpsim instruction-level tests (requires gpsim):
python3 -m pytest tests/sim/ -q -m gpsim

# All tests:
python3 -m pytest tests/sim/ -q
```

### gpsim-level preset tests

The `GpsimControlHarness` (`src/dlcp_fw/sim/control_gpsim.py`) provides a non-interactive
gpsim harness for CONTROL firmware.  It runs the patched firmware to
instruction-level fidelity with LCD decode, button injection, serial frame
capture, and EEPROM read/write via PIC18 SFR registers.

Tests in `tests/sim/test_gpsim_control_presets.py`:

| Test | Verifies |
|------|----------|
| `test_boot_shows_preset_a` | Fresh EEPROM → LCD col 15 = 'A' |
| `test_preset_screen_navigation` | R→Preset(>A<), D→(>B<), L→Volume(B) |
| `test_preset_emits_serial_frames` | DOWN→(0xB0,0x20,0x01), UP→(0xB0,0x20,0x00) |
| `test_preset_persists_power_cycle` | Set B → dump EEPROM → reload → boot shows B |
| `test_four_screen_wraparound` | R×4: menu_state 0→1→2→3→0 |
| `test_volume_resets_on_power_cycle` | Volume (RAM only) resets after power cycle |

Tests in `tests/sim/test_main_gpsim_preset_banks.py`:

| Test | Verifies |
|------|----------|
| `test_preset_a_reg5e_bit2_clear` | cmd=0x20 data=0 → reg 0x05E bit2=0 |
| `test_preset_b_reg5e_bit2_set` | cmd=0x20 data=1 → reg 0x05E bit2=1 |
| `test_preset_switch_ab_sequence` | Set B then A → final bit2=0 |
| `test_broadcast_reaches_unit` | route=0xB0 consumed by any unit address |

Additional regression coverage:

| File | Purpose |
|------|---------|
| `tests/sim/test_main_gpsim_command_compatibility.py` | Focused legacy command compatibility checks (`0x1D`/`0x1E`) |
| `tests/sim/test_main_gpsim_command_matrix.py` | Exhaustive stock-vs-patched sweep across original MAIN command set |
| `tests/sim/test_main_gpsim_command_edges.py` | Edge conditions (min/max data, routing variants) for legacy MAIN commands |
| `tests/sim/test_control_main_powercycle_sync.py` | Full power-cycle + late-join MAIN preset resync behavior |
| `tests/sim/test_control_gpsim_command_emission_legacy.py` | Legacy CONTROL→MAIN command emission coverage during boot/runtime |
| `tests/sim/test_control_gpsim_response_parser.py` | CONTROL RX parser behavior for response commands and reset path handling |
| `tests/sim/test_control_gpsim_ir_compatibility.py` | Decoded-IR dispatch parity (stock V1.4 vs patched V1.41): both RC5 profiles, action emissions, and negative cases |
| `tests/sim/test_control_gpsim_ir_preset_switch.py` | Patched-only IR preset switching: F1/F2 mapping, idempotency, off-screen updates, and LCD consistency |
| `tests/sim/test_control_v15b_port_compatibility.py` | V1.5b/V1.51b parity + V1.4↔V1.5b delta-preservation checks (static + gpsim) |
| `tests/sim/test_verify_presets_ab_v15b_semantic_guards.py` | V1.5b verifier semantic guards (hook/target/literal drift rejection) |
| `tests/sim/test_control_gpsim_full_config_persistence.py` | Deep gpsim matrix: Input/BL Timeout/DLCP1/DLCP2 edits + persistence + preset drift isolation checks |
| `tests/sim/test_main_dsp_refresh_behavior.py` | MAIN DSP refresh characterization: boot apply path, preset-change apply semantics, USB upload no-auto-apply behavior |
| `tests/sim/test_verify_presets_ab_semantic_guards.py` | Semantic guard tests for verifier drift detection (main/control hooks) |

#### V1.5b → V1.51b test matrix (executed)

| Scope | Tests / Command | Expected | Result |
|-------|------------------|----------|--------|
| Static patch-map validation | `python3 -m dlcp_fw.patch.verify_presets_ab --control-new-v151b --control-profile v15b` | V1.5b hook map, targets, literals, and tuple checks pass | Pass |
| Verifier guard hardening | `tests/sim/test_verify_presets_ab_v15b_semantic_guards.py` | Detect full-sync hook drift, IR hook opcode drift, IR target reverts, shortcut literal drift | Pass |
| Stock delta preservation | `tests/sim/test_control_v15b_port_compatibility.py::test_control_v14_v15b_stock_delta_preserved_in_v151b` | Preserve V1.5b-side deltas (`CONFIG1L`, `EEPROM[0xFE]`, `cmd=0x18` path) | Pass |
| `cmd=0x18` behavior parity | `tests/sim/test_control_v15b_port_compatibility.py::test_cmd18_reset_behavior_matches_v15b_not_v14` | Match V1.5b behavior and not V1.4 behavior | Pass |
| IR dispatch parity matrix | `tests/sim/test_control_v15b_port_compatibility.py::test_ir_actions_match_stock_v15b_dispatch_behavior` | Both RC5 profiles emit same frames and state deltas as stock V1.5b | Pass |
| IR negative parity | `tests/sim/test_control_v15b_port_compatibility.py::test_ir_wrong_address_is_ignored_like_stock_v15b`, `tests/sim/test_control_v15b_port_compatibility.py::test_ir_unknown_command_is_ignored_like_stock_v15b` | Wrong address and unknown command are ignored like stock | Pass |
| Key-action parity | `tests/sim/test_control_v15b_port_compatibility.py::test_key_action_legacy_frames_match_stock_v15b` | Legacy same-screen key emissions (`S`/`U`) match stock V1.5b | Pass |
| Full regression suite | `python3 -m pytest tests/sim -q` | No regressions across sim + gpsim | `146 passed` |

#### Stock V2.3 DSP-refresh characterization progress (2026-02-18)

- Exercised disasm-backed tests:
  - `tests/sim/test_main_dsp_refresh_behavior.py::test_boot_path_contains_table_apply_call`
  - `tests/sim/test_main_dsp_refresh_behavior.py::test_usb_upload_path_does_not_call_table_apply_directly`
  - Result: both pass.
- In stock MAIN `V2.3` disassembly (`firmware/disasm/main/gpdasm_output.asm`), upload routine
  `function_021` (`0x2BB8`) calls read/erase/write helpers (`function_061`,
  `function_054`, `function_025`) and does not directly call `function_084`
  (table apply).
- Stock apply trigger path is present and explicit:
  - `cmd=0x0F` check/flag set at `0x1398..0x13A0` (sets `0x05E.7`)
  - main loop apply gate at `0x1A76..0x1A90` calls `function_084` (`0x1A88`)
    when `0x05E.7` is set, then clears the flag.
- Byte-compare confirms these regions are unchanged between stock
  `firmware/stock/main/DLCP Firmware V2.3.hex` and patched `firmware/patched/releases/DLCP_Firmware_V2.4.hex`:
  - `0x1398..0x13C8` (flag set path)
  - `0x1A76..0x1A92` (apply gate)
  - `0x2BB8..0x2CA6` (`function_021` upload body)

**Simulation overlays**: The harness auto-selects standby bypass overlay by
firmware layout (`0x1228` on V1.4 family, `0x121A` on V1.5b family) so the
firmware stays in DISPLAY mode without requiring a live MAIN heartbeat. For
no-file boot it seeds EEPROM `0x74` (preset) and `0x73` (stock BL-timeout
byte) to `0xFF`, matching real PIC18 erased defaults (`gpsim` defaults EEPROM
to `0x00`).

## Flash Order

### Safety preflight (recommended before any live flash)

```bash
# Strict wrapper: blocks unsafe flags, enforces bootloader match check,
# and runs preflight before any live flash.
scripts/flash_control_safe.sh --preflight-only
```

Notes:
- The flasher now blocks bootloader drift by default.
- Unsafe bypasses (`--skip-bootloader-check`, `--no-verify`) require explicit
  `--force-unsafe`.
- Do not use unsafe flags for production hardware updates.

1. Flash MAIN firmware with your normal main-firmware method.
2. Flash CONTROL firmware through the main USB relay:

```bash
scripts/flash_control_safe.sh
```

`scripts/flash_control_safe.sh` defaults to
`firmware/patched/releases/DLCP_Control_V1.51b.hex` with bootloader reference
`firmware/stock/control/DLCP Control Firmware V1.5b.hex`.

### Recovery notes (if update fails)

- Keep copies of stock control HEX matching your target branch:
  - `firmware/stock/control/DLCP Control Firmware V1.4.hex` (for V1.41 path)
  - `firmware/stock/control/DLCP Control Firmware V1.5b.hex` (for V1.51b path)
  and stock main HEX before flashing.
- If CONTROL update fails but relay path is still alive, re-run flash with stock
  control HEX first, then retry patched HEX.
- Documented manual control-bootloader entry is `UP+DOWN` held at power-on for
  ~5.5s (`SELECT` not pressed); treat this as a fallback path before PICkit.
- If CONTROL cannot be reached through relay, last-resort recovery is external
  programming (PICkit-class tool).

## Scripts

| Script | Role |
|--------|------|
| `scripts/flash_control_safe.sh` | Safe flashing wrapper: runs preflight first, enforces bootloader match, blocks unsafe flags, asks confirmation before live write |
| `src/dlcp_fw/patch/build_main_presets_ab.py` | Build patched MAIN HEX: assembles PIC18 stubs via gpasm, copies table A→B, applies hook redirections |
| `src/dlcp_fw/patch/build_control_presets_ab.py` | Build patched CONTROL HEX: assembles stubs for dispatch/nav/preset_screen/volume_indicator |
| `src/dlcp_fw/patch/build_control_presets_ab_v15b.py` | Build patched CONTROL HEX for V1.5b baseline: same feature set retargeted to V1.5b addresses/call graph |
| `src/dlcp_fw/patch/verify_presets_ab.py` | Static byte-level verification of both patched HEX files |
| `scripts/sim_presets_ab.py` | Protocol simulator: two MAIN units, preset switch + HFD upload, digest assertions |
| `scripts/sim_link_control_main_presets_ab.py` | Full link simulator: Control + two Mains, route filtering, patch compat check |
| `scripts/sim_control_ui_presets.py` | Console LCD simulator: 4-screen menu navigation, preset selection |

## Known Limitations

1. **No real I2C/DSP validation.**  The TAS3108 is not simulated.  Preset
   application is verified at flash-write and DSP-ingest-event level, not
   at audio output.

2. **No USB peripheral timing.**  HFD uploads are modeled as logical
   command/frame injection, not full USB enumeration.

3. **Preset value domain is `0`/`1` only.**  Extension to A/B/C requires
   additional flash bank space and table remap logic.

4. **EEPROM persistence is now active.**  The patched firmware writes preset
   changes to EEPROM[0x74] (idempotent: no write on redundant same-preset
   selection) and restores on boot. Fresh EEPROM (`0xFF`) defaults to preset A.

## Related Documentation

- `SIMULATION.md` — co-simulation guide (TUI, overlays, architecture)
- `TEST_SIMULATOR.md` — test framework documentation
- `REANALYSIS_CORRECTIONS_2026-02-16.md` — corrections found during patch development
- `CONTROL_UNIT_ANALYSIS.md` — CONTROL firmware reverse-engineering notes
- `ANALYSIS_REPORT_CLAUDE.md` — MAIN firmware analysis (notes lack of built-in preset system)

### Key simulation modules

| Module | Role |
|--------|------|
| `src/dlcp_fw/sim/control_gpsim.py` | Non-interactive gpsim harness for CONTROL firmware |
| `src/dlcp_fw/sim/control_ui.py` | Python-level CONTROL UI behavioral simulator |
| `src/dlcp_fw/sim/main_gpsim.py` | gpsim harness for MAIN firmware mailbox injection |
| `src/dlcp_fw/sim/manifests.py` | All overlay definitions (reset, boot wait, standby check) |
