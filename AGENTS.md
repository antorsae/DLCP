# DLCP Firmware Analysis — Master Index (Migrated Layout)

Last updated: 2026-04-11
Scope: `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`

## Purpose

`AGENTS.md` is the single source of truth for repository layout, canonical paths, and operational commands.

If any file is moved/renamed, update this document in the same change.

## System Overview

- Product: Hypex DLCP (Digital Loudspeaker Control Processor)
- Main MCU: PIC18F2455-class firmware image (`V2.3` stock, patched `V2.4`–`V2.8`, source-assembled `V3.0`/`V3.1`)
- Control MCU: PIC18F25K20 firmware image (`V1.4`/`V1.5b`/`V1.6b` stock, patched `V1.41`/`V1.51b`/`V1.61b`/`V1.62b`/`V1.63b`)
- DSP: TI TAS3108
- Host interface: USB HID (`VID 0x04D8`, `PID 0xFF89`)
- Inter-unit link: 31,250 baud current-loop serial (3-byte frames: route/cmd/data)

## Canonical Layout

```text
analysis/
├── AGENTS.md
├── docs/
│   ├── AB_PRESETS.md
│   ├── ROBUSTNESS.md
│   ├── R_L_ROUTING.md
│   ├── SIMULATION.md
│   ├── TEST_SIMULATOR.md
│   └── analysis/
├── firmware/
│   ├── stock/
│   │   ├── main/
│   │   ├── control/
│   │   └── PC/
│   ├── patched/releases/
│   ├── disasm/
│   │   ├── main/
│   │   ├── control/
│   │   └── PC/
│   ├── dumps/
│   └── reference/
├── src/dlcp_fw/
│   ├── paths.py
│   ├── asm/
│   ├── sim/
│   ├── patch/
│   ├── flash/
│   ├── analysis/
│   └── cli/
├── scripts/
├── tests/sim/
├── vendor/
│   └── gpsim-0.32.1-xtc/
├── artifacts/
│   ├── LX521.4/
│   ├── sim/current/
│   ├── reanalysis/
│   ├── tools/gpsim-xtc/
│   └── probes/
└── dlcp_fw/            # namespace bootstrap package
```

## Path Policy

Use these locations only:

- Stock firmware: `firmware/stock/...`
- Stock PC host tools/installers: `firmware/stock/PC/...`
- Patched firmware releases: `firmware/patched/releases/...`
- Disassembly: `firmware/disasm/...`
- PC reverse-engineering artifacts: `firmware/disasm/PC/...`
- Binary dumps: `firmware/dumps/...`
- Assembly source (V3.x): `src/dlcp_fw/asm/...`
- Local third-party source forks: `vendor/...`
- Generated runtime/test artifacts: `artifacts/sim/current/...`
- Local manual preset captures: `artifacts/LX521.4/...`
- Local tool builds/wrappers: `artifacts/tools/...`
- Python package code: `src/dlcp_fw/...`
- CLI entry scripts: `scripts/...`

## Firmware Artifacts

### Stock

- Main: `firmware/stock/main/DLCP Firmware V2.3.hex`
- Main program-memory export: `firmware/stock/main/DLCP Firmware V2.3-Program Memory.hex`
- Main tabular dump: `firmware/stock/main/DLCP Firmware V2.3-dump.hex`
- Main dump converted to Intel HEX: `firmware/stock/main/DLCP Firmware V2.3-dump-converted.hex`
- Main export recombination: `firmware/stock/main/DLCP Firmware V2.3-combined.hex`
- Main export fragment: `firmware/stock/main/DLCP Firmware V2.3-Configuration Bits.hex`
- Main export fragment: `firmware/stock/main/DLCP Firmware V2.3-EE Data Memory.hex`
- Main export fragment: `firmware/stock/main/DLCP Firmware V2.3-User ID Memory.hex`
- Control V1.4: `firmware/stock/control/DLCP Control Firmware V1.4.hex`
- Control V1.5b: `firmware/stock/control/DLCP Control Firmware V1.5b.hex`
- Control V1.6b: `firmware/stock/control/DLCP Control Firmware V1.6b.hex`
- PC host app bundle: `firmware/stock/PC/HFD_v2.12/...`
- PC host installer bundle: `firmware/stock/PC/HFD_v4.97/...`

### Patched releases (binary-patched)

- Main AB (legacy): `firmware/patched/releases/DLCP_Firmware_V2.4.hex`
- Main AB + robustness: `firmware/patched/releases/DLCP_Firmware_V2.5.hex`
- Main AB + DSP robustness: `firmware/patched/releases/DLCP_Firmware_V2.6.hex`
- Main AB + bus-clear/ping/PEN: `firmware/patched/releases/DLCP_Firmware_V2.7.hex`
- Main AB + delayed switch hold: `firmware/patched/releases/DLCP_Firmware_V2.8.hex`
- Control AB: `firmware/patched/releases/DLCP_Control_V1.41.hex`
- Control AB (V1.5b port): `firmware/patched/releases/DLCP_Control_V1.51b.hex`
- Control AB (V1.6b port): `firmware/patched/releases/DLCP_Control_V1.61b.hex`
- Control AB + reconnect robustness: `firmware/patched/releases/DLCP_Control_V1.62b.hex`
- Control AB + BF/08 fault indicator/resync: `firmware/patched/releases/DLCP_Control_V1.63b.hex`

### Source-assembled releases (V3.x)

- Main V3.0 (stock-equivalent rewrite): `firmware/patched/releases/DLCP_Firmware_V3.0.hex`
- Main V3.1 (all features inline): `firmware/patched/releases/DLCP_Firmware_V3.1.hex`
  - Recommended deployed MAIN release when flashed with baked preset A/B captures.
  - Canonical `V3.1` includes HID `cmd 0x43` diagnostic flash/EEPROM memread.
- Source: `src/dlcp_fw/asm/dlcp_main_v30.asm`, `src/dlcp_fw/asm/dlcp_main_v31.asm`
- gpasm byproducts such as `.cod` / `.lst` may exist beside source-assembled outputs; only the `.hex` files above are canonical release payloads.
- Additional local experiment sources such as `src/dlcp_fw/asm/dlcp_main_v31_diag*.asm`, `src/dlcp_fw/asm/dlcp_main_v31_with_nops.asm`, `src/dlcp_fw/asm/dlcp_main_v31_without_nops.asm`, and matching `DLCP_Firmware_V3.1_diag*` / `DLCP_Firmware_V3.1_WITH*_NOPS.hex` build outputs may also be present. Treat them as non-canonical unless the current task explicitly targets them.
- Dedicated USB-safe memread artifact: `firmware/patched/releases/DLCP_Firmware_V3.1_diag_memread_usb_safe.hex`

### Disassembly

- Main primary: `firmware/disasm/main/gpdasm_output.asm`
- Main alternates: `firmware/disasm/main/full_disasm.asm`, `firmware/disasm/main/gpdasm_short.asm`
- Control primary: `firmware/disasm/control/v1.4_disasm.asm`
- Control variants: `firmware/disasm/control/v1.5b_disasm.asm`, `firmware/disasm/control/v1.6b_disasm.asm`
- Legacy/raw control disasm: `firmware/disasm/control/v14.asm`, `firmware/disasm/control/v15b.asm`, `firmware/disasm/control/v16b.asm`
- PC HFD RE artifacts: `firmware/disasm/PC/HFD_v2.12/...`, `firmware/disasm/PC/HFD_v4.97/...`

### Annotated disassembly (generated, gitignored)

Generated by `scripts/annotate_disasm.py` from `docs/analysis/SEMANTIC_FUNCTION_MAP.md`.
These overlay semantic function/label names onto the raw gpdasm output.
**Prefer these over the raw files** when reading disassembly for analysis.

- `firmware/disasm/main/gpdasm_output.annotated.asm`
- `firmware/disasm/control/v1.4_disasm.annotated.asm`
- `firmware/disasm/control/v1.5b_disasm.annotated.asm`
- `firmware/disasm/control/v1.6b_disasm.annotated.asm`

Regenerate after any semantic map update: `python3 scripts/annotate_disasm.py`

### Dumps and references

- Dumps: `firmware/dumps/{firmware.bin,code_only.bin,eeprom.bin,dlcp_flash_0800_7fff.bin,dlcp_probe_1000.bin}`
- Reference docs: `firmware/reference/{DLCP-datasheet-R3.pdf,dlcp.md,DLCP-manual-R3.pdf,tas3108.pdf,tas3108.md,sleu067a.pdf,DLCP-control-intro.pdf,39632e.pdf,39632e.md}`
  - For the PIC18F2455 datasheet, `39632e.pdf` is authoritative. Use `39632e.md` as the line-stable converted companion for repo citations.
  - For the TAS3108 datasheet, `tas3108.pdf` is authoritative. Use `tas3108.md` as the line-stable converted companion when repo citations are needed.

## Source Code Map (`src/dlcp_fw`)

### `src/dlcp_fw/paths.py`

Canonical constants used across scripts/tests:

- Directory roots: `PROJECT_ROOT`, `DOCS_DIR`, `FIRMWARE_DIR`, `ARTIFACTS_DIR`, `SCRIPTS_DIR`, `VENDOR_DIR`, `TOOLS_ARTIFACTS_DIR`
- Firmware dirs: `FIRMWARE_STOCK_DIR`, `FIRMWARE_PATCHED_DIR`, `FIRMWARE_DISASM_DIR`, `FIRMWARE_DUMPS_DIR`, `FIRMWARE_REFERENCE_DIR`
- Stock main: `STOCK_MAIN_HEX`, `STOCK_MAIN_PROGRAM_MEMORY_EXPORT`, `STOCK_MAIN_DUMP_TABLE`, `STOCK_MAIN_DUMP_CONVERTED_HEX`, `STOCK_MAIN_COMBINED_HEX`, `STOCK_MAIN_CONFIG_BITS_EXPORT`, `STOCK_MAIN_EE_DATA_EXPORT`, `STOCK_MAIN_USER_ID_EXPORT`
- Stock control: `STOCK_CONTROL_HEX_V14`, `STOCK_CONTROL_HEX_V15B`, `STOCK_CONTROL_HEX_V16B`
- Patched main: `PATCHED_MAIN_HEX_V24`, `PATCHED_MAIN_HEX_V25`, `PATCHED_MAIN_HEX_V26`, `PATCHED_MAIN_HEX_V27`, `PATCHED_MAIN_HEX_V28`, `PATCHED_MAIN_HEX` (alias for V2.7)
- Source-assembled main: `V30_MAIN_HEX`, `V30_MAIN_ASM`, `V30_MAIN_ASM_COMMENTS`, `V31_MAIN_HEX_CANONICAL`, `V31_MAIN_ASM_CANONICAL`, `V31_MAIN_HEX`, `V31_MAIN_ASM`
  - `V31_MAIN_HEX_CANONICAL` / `V31_MAIN_ASM_CANONICAL` are the repo-stable inputs for canonical V3.1 builders
  - `V31_MAIN_HEX` / `V31_MAIN_ASM` may be overridden for diagnostics with `DLCP_FW_V31_MAIN_HEX` / `DLCP_FW_V31_MAIN_ASM`
- Patched control: `PATCHED_CONTROL_HEX` (alias for V1.41), `PATCHED_CONTROL_HEX_V141`, `PATCHED_CONTROL_HEX_V151B`, `PATCHED_CONTROL_HEX_V161B`, `PATCHED_CONTROL_HEX_V162B`, `PATCHED_CONTROL_HEX_V163B`
- Disassembly: `MAIN_DISASM`, `MAIN_DISASM_ALT`, `MAIN_DISASM_SHORT`, `CONTROL_DISASM_V14`, `CONTROL_DISASM_V15B`, `CONTROL_DISASM_V16B`
- Sim/tools: `SIM_ARTIFACTS_DIR`, `REANALYSIS_ARTIFACTS_DIR`, `GPSIM_XTC_SOURCE_DIR`, `GPSIM_XTC_ARTIFACTS_DIR`, `GPSIM_XTC_BUILD_DIR`, `GPSIM_XTC_BIN_DIR`, `GPSIM_XTC_BINARY`, `GPSIM_XTC_COMPAT_BINARY`, `GPSIM_XTC_BUILD_BINARY`, `GPSIM_XTC_MODULE_DIR`
- Docs: `SEMANTIC_FUNCTION_MAP`

Always prefer these constants over hardcoded paths.

### Simulation package (`src/dlcp_fw/sim`)

- Core: `bus.py`, `protocol.py`, `scenarios.py`, `main_model.py`, `control_ui.py`
- gpsim harness: `control_gpsim.py`, `main_gpsim.py`, `main_gpsim_timer3.py`, `chain_gpsim.py`, `wire_chain_gpsim.py`, `gpsim.py`
- V3.0 tooling: `v30_symbols.py` (gpasm listing symbol parser, shifted ASM builder, assembly helper)
- support: `hexio.py`, `lcd.py`, `overlay.py`, `manifests.py`, `paths.py`

### Assembly source package (`src/dlcp_fw/asm`)

- V3.0 stock-equivalent source: `dlcp_main_v30.asm`, `dlcp_main_v30_comments.asm` (canonical, zero auto-labels)
- V3.1 full-feature source: `dlcp_main_v31.asm`
- Support: `dlcp_main_ram.inc` (RAM equates), `region_manifest.py` (flash region metadata)

### Patch package (`src/dlcp_fw/patch`)

- Builders: `build_main_presets_ab.py`, `build_control_presets_ab.py`, `build_control_presets_ab_v15b.py`, `build_control_presets_ab_v16b.py`, `build_control_presets_ab_v162b.py`, `build_control_presets_ab_v163b.py`
- V3.1 diagnostics/build helpers: `build_v31_cmd07_stock_guard_usb_safe.py`, `build_v31_diag_coeff_stock.py`, `build_v31_diag_memread_usb_safe.py`, `build_v31_diag_no_flash_remap_usb_safe.py`, `build_v31_diag_stock_bf.py`, `build_v31_diag_stock_bf_reg1f.py`, `build_v31_diag_stock_i2c_byte_tx.py`, `build_v31_diag_v27_pen_hook.py`, `build_v31_nop_variants.py`, `build_v31_usb_safe.py`, `bake_preset_capture.py`
- Verifiers: `verify_presets_ab.py`, `verify_isr_vectors.py`

### Flash/probe package (`src/dlcp_fw/flash`)

- Safe control flasher: `dlcp_control_flash.py`
- Safe main flasher: `dlcp_main_flash.py`
- Canonical V3.1 operator wrapper: `dlcp_v31_release_flash.py`
- Preset query/switch helper: `dlcp_preset.py`
- EP0 flash window reader: `dlcp_ep0_flash_probe.py`
- EEPROM shadow dump: `dlcp_ep0_eeprom_shadow_dump.py`
- DSP filename A/B probe: `dsp_filename_ab_probe.py`
- HID preset capture reader: `read_coeffs.py` (CLI: `scripts/dlcp_read_coeffs.py`)

### Analysis package (`src/dlcp_fw/analysis`)

Contains migrated analysis scripts and utilities including:

- `analyze_firmware.py`, `analyze_control_firmware.py`
- `code_analysis.py`, `deep_analysis.py`, `deep_analysis2.py`, `ultra_deep.py`
- `channel_dsp_analysis.py`, `dsp_comm_analysis.py`, `coefficient_format_analysis.py`
- `data_structure_analysis.py`, `filter_stages_analysis.py`, `final_analysis.py`
- `control_firmware_analysis.py`, `dlcp_table_decode.py`, `reconstruct_main_bins.py`
- `config_analysis.py`, `word_dump_to_ihex.py`
- `annotate_disasm.py` (generates `.annotated.asm` files from semantic map)

## CLI Entry Points

### Canonical (new)

- `scripts/gpsim-xtc`
- `scripts/gpsim`
- `scripts/simctl.py`
- `scripts/hardware_loop.py`
- `scripts/dlcp_preset.py`
- `scripts/dlcp_main_flash.py`
- `scripts/dlcp_v31_release_flash.py`
- `scripts/dlcp_read_coeffs.py`
- `scripts/dlcp_ep0_flash_probe.py`
- `scripts/gpsim_tui_simulator.py`
- `scripts/gpsim_menu_command_audit.py`
- `scripts/gpsim_lcd_capture_decode.py`
- `scripts/gpsim_headless_chain_diagnose.py`
- `scripts/sim_presets_ab.py`
- `scripts/sim_link_control_main_presets_ab.py`
- `scripts/sim_control_ui_presets.py`
- `scripts/flash_control_safe.sh`
- `scripts/bake_preset_capture.py`
- `scripts/test_full_boot.py`, `scripts/test_button_inject.py`
- `scripts/word_dump_to_ihex.py`
- `scripts/annotate_disasm.py`

## Tests (`tests/sim`)

Current suite (84 test files, 649 tests collected):

Overlay/patch integrity:
- `test_overlay_engine.py`, `test_patch_compatibility.py`
- `test_verify_presets_ab_semantic_guards.py`, `test_verify_presets_ab_v15b_semantic_guards.py`, `test_verify_presets_ab_v16b_semantic_guards.py`, `test_verify_presets_ab_v162b_semantic_guards.py`
- `test_region_manifest.py`

Robustness/recovery:
- `test_robustness_waiting.py` (WAITING FOR DLCP regression)
- `test_chain_gpsim_waiting.py` (chain WAITING regression)
- `test_chain_gpsim_v25_recovery.py` (raw-main V2.5 chain characterization)
- `test_chain_gpsim_v25_v162b_recovery.py` (V2.5 + V1.62b recovery)
- `test_chain_gpsim_v141_v24_v25_recovery.py` (V1.41/V2.4/V2.5 chain recovery)
- `test_chain_gpsim_v161b_v24_v25_i2c_faults.py` (V1.61b I2C fault chain)
- `test_reconnect_wake_gate.py` (V1.62b reconnect wake gate)
- `test_main_v25_timeout_recovery.py` (MAIN V2.5 timeout probe)

Wire-chain/multi-PB:
- `test_wire_chain_gpsim.py` (UART smoke regression)
- `test_wire_chain_gpsim_stock_faults.py` (stock fault injection)
- `test_wire_chain_gpsim_i2c_faults.py` (I2C wake characterization)
- `test_wire_chain_gpsim_internal_faults.py` (internal-fault wake characterization)
- `test_v28_wire_delayed_switch_repros.py` (two-MAIN delayed-switch desync, mute/standby interleave, START/STOP fault, and soak repros)
- `test_gpsim_multi_processor_uart_topology.py` (multi-processor UART)

Main behavior:
- `test_main_model_banking.py`, `test_main_dsp_refresh_behavior.py`
- `test_main_dsp_deafness_chain.py` (DSP1/DSP2/DSP3 isolation)
- `test_main_dsp_filename_sim_validation.py` (filename A/B simulation)
- `test_main_stdby_pin_io.py` (standby pin I/O + V1.62b TXIE guard)
- `test_main_gpsim_an0_boot.py`, `test_main_gpsim_cmd03_instruction_path.py`
- `test_main_gpsim_command_compatibility.py`, `test_main_gpsim_command_edges.py`, `test_main_gpsim_command_matrix.py`
- `test_main_gpsim_fault_injection.py`
- `test_main_gpsim_filename_ab.py`, `test_main_gpsim_i2c_regfile.py`
- `test_main_gpsim_mailbox.py`, `test_main_gpsim_preset_banks.py`
- `test_main_gpsim_timer3_compare.py`
- `test_main_gpsim_usb_engine.py` (USB SIE filename forward+reverse, stock compat)

Control behavior:
- `test_control_ui_and_persistence.py`, `test_gpsim_control_presets.py`, `test_gpsim_control_lcd.py`
- `test_control_v15b_port_compatibility.py`, `test_control_v16b_port_compatibility.py`
- `test_control_gpsim_command_emission_legacy.py`, `test_control_gpsim_full_config_persistence.py`
- `test_control_gpsim_host_command_injection.py`, `test_control_gpsim_ir_compatibility.py`
- `test_control_gpsim_ir_preset_switch.py`, `test_control_gpsim_preset_eeprom_diff.py`
- `test_control_gpsim_response_parser.py`

End-to-end/faults:
- `test_scenarios.py`, `test_bus_faults.py`, `test_control_main_powercycle_sync.py`

Flash/probe tools:
- `test_dlcp_main_flash.py`
- `test_dlcp_v31_release_flash.py`
- `test_dlcp_control_flash_safety.py`, `test_dlcp_ep0_eeprom_shadow_dump.py`, `test_dsp_filename_ab_probe.py`
- `test_dlcp_ep0_flash_probe.py`

Tooling/analysis:
- `test_word_dump_to_ihex.py`, `test_disasm_to_source.py`
- `test_bake_preset_capture.py`

Hardware-loop tooling:
- `test_hardware_loop.py`

V2.7 + V1.63b:
- `test_v27_v163b_robustness.py` (bus-clear, DSP ping, fault reporting, PEN timeout)

V3.0 source rewrite:
- `test_v30_equivalence.py` (hex integrity + source quality)
- `test_v30_gpsim_equivalence.py` (behavioral parity with stock)
- `test_v30_relocation.py` (10 structural + 6 gpsim behavioral shift tests)

V3.1 source rewrite:
- `test_v31_v163b_robustness.py` (bus-clear, DSP ping, fault reporting, PEN timeout)
- `test_v31_review_findings.py` (BSR safety, degraded state, BF/08 payload, retry counter)
- `test_v31_happy_path.py` (boot preset load, volume→DSP, computed volume — 4 versions)
- `test_v31_dsp_boot_equivalence.py` (all 256 DSP regs match stock V2.3/V2.4/V2.6)
- `test_v31_command_matrix.py` (all 16 serial commands identical to stock V2.3)
- `test_v31_usb_preset_ab.py` (upload bank mapping, flash isolation, config names)
- `test_v31_usb_hid_dispatch.py` (filename RAM, cmd 0x20 switch, version staging)
- `test_v31_diag_memread_usb_safe.py` (canonical + USB-safe diagnostic HID flash/EEPROM memory reads)

Version labels:
- `test_firmware_version_label.py` (USB HID + EEPROM version bytes in HEX)

Recent verification (2026-04-11):

- `.venv_ep0/bin/python -m pytest tests/sim --collect-only -q` -> `649 tests collected`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_main_flash.py tests/sim/test_dlcp_control_flash_safety.py` -> `13 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_ep0_flash_probe.py tests/sim/test_dsp_filename_ab_probe.py tests/sim/test_dlcp_ep0_eeprom_shadow_dump.py` -> `10 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_hardware_loop.py` -> `12 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_main_gpsim_portability.py tests/sim/test_v31_patch_builders.py` -> `13 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_bake_preset_capture.py tests/sim/test_v31_diag_memread_usb_safe.py` -> `4 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_control_gpsim_ir_preset_switch.py -k "waiting or reaches_main"` -> `2 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_v28_wire_delayed_switch_repros.py` -> `5 xfailed`

V3.1-only gate (80 tests, ~8 min):

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v31"
```

Full test gate (all versions, parallel):

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Documentation Map

Top-level docs:

- `docs/AB_PRESETS.md` (A/B preset patch design, flashing, checks)
- `docs/HARDWARE_LOOP.md` (real-hardware audio playback/capture workflow and firmware comparison matrix)
- `docs/RECOVERY.md` (PICkit 5 readback recombination and full MAIN recovery image workflow)
- `docs/ROBUSTNESS.md` (robustness findings, release policy, and implementation plan)
- `docs/R_L_ROUTING.md` (MAIN/CONTROL/HFD routing semantics and `R-L` extension plan)
- `docs/SIMULATION.md` (co-simulation architecture and usage)
- `docs/TEST_SIMULATOR.md` (test framework and commands)
- `docs/V31_RELEASE.md` (recommended `V3.1` deployment workflow with baked preset A/B captures)
- `docs/V27_V163B_SPEC.md` (V2.7 MAIN + V1.63b CONTROL specification)
- `docs/V27_V163B_STATUS.md` (V2.7 + V1.63b implementation status)
- `docs/V30_SOURCE_REWRITE_SPEC.md` (V3.0 MAIN source-level rewrite specification)
- `docs/IMPL_V30_SOURCE_REWRITE_SPEC.md` (V3.0 source rewrite implementation prompt)
- `docs/IMPL_V30_SOURCE_REWRITE_SPECv2.md` (V3.0 source rewrite polished implementation — supersedes above)
- `docs/V31_SOURCE_REWRITE_SPEC.md` (V3.1 MAIN source rewrite specification)
- `docs/IMPL_V31_SOURCE_REWRITE_SPEC.md` (V3.1 source rewrite implementation prompt)
- `docs/V163B_DIAGNOSTICS_MENU_SPEC.md` (draft future diagnostics page / counter protocol; not implemented in the committed V1.63b/V3.1 pair)
- `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md` (V3.1 MAIN size-reduction campaign requirements and process)
- `docs/V31_SIZE_OPTIMIZATION_PROGRESS.md` (size campaign experiment ledger and gate status)

Deep analysis docs:

- `docs/analysis/ANALYSIS_REPORT_CLAUDE.md`
- `docs/analysis/CONTROL_FW_VERSION_DIFFS.md`
- `docs/analysis/CONTROL_UNIT_ANALYSIS.md`
- `docs/analysis/FIRMWARE_UPDATE_MECHANISM.md`
- `docs/analysis/HFD_v2.12-codex.md`
- `docs/analysis/HFD_v2.12-RL-binary-patch-plan.md`
- `docs/analysis/HFD_v4.97-codex.md`
- `docs/analysis/GPSIM_18F25K20_PORT_PLAN.md`
- `docs/analysis/GPSIM_MAIN_TIMER3_GAP_HANDOFF_PROMPT.md`
- `docs/analysis/MAIN_AN0_STANDBY_TRACE.md`
- `docs/analysis/MAIN_CLOCK_TIMING.md`
- `docs/analysis/PIN_SEMANTICS.md`
- `docs/analysis/MCU_TARGET_CORRECTION_2026-03-11.md`
- `docs/analysis/REANALYSIS_CORRECTIONS_2026-02-16.md`
- `docs/analysis/SIMULATION_STDBY_WAIT_DIAGNOSIS.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-gpt-5.4-xhigh.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-gpt-5.2-pro.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-opus-4.6.md`
- `docs/analysis/V162B_STDBY_TXIE_BUG.md`
- `docs/analysis/SEMANTIC_FUNCTION_MAP.md` (auto-name → semantic-name mapping for disassembly labels; source for annotated disasm)
- `docs/analysis/V162B_RECONNECT_WAKE_BUG.md`

## Artifacts and Caches

Reanalysis artifacts (local by default; ignored via `.gitignore`):

- `artifacts/reanalysis/...`

Generated/ephemeral (ignored):

- `artifacts/LX521.4/...`
- `artifacts/sim/current/...`
- `artifacts/probes/...`
- `artifacts/tools/gpsim-xtc/...`
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.venv*`, etc.

## Common Commands

Build patched firmware:

```bash
python3 -m dlcp_fw.patch.build_main_presets_ab --variant v24
python3 -m dlcp_fw.patch.build_main_presets_ab --variant v25
python3 -m dlcp_fw.patch.build_main_presets_ab --variant v26
python3 -m dlcp_fw.patch.build_main_presets_ab --variant v27
python3 -m dlcp_fw.patch.build_main_presets_ab --variant v28
python3 -m dlcp_fw.patch.build_control_presets_ab
python3 -m dlcp_fw.patch.build_control_presets_ab_v15b
python3 -m dlcp_fw.patch.build_control_presets_ab_v16b
python3 -m dlcp_fw.patch.build_control_presets_ab_v162b
python3 -m dlcp_fw.patch.build_control_presets_ab_v163b
python3 -m dlcp_fw.patch.verify_presets_ab
```

Assemble V3.1 source:

```bash
.venv_ep0/bin/python -c "from dlcp_fw.sim.v30_symbols import assemble_v30; from dlcp_fw.paths import V31_MAIN_ASM, V31_MAIN_HEX; assemble_v30(V31_MAIN_ASM, V31_MAIN_HEX)"
```

Combine stock V2.3 main export fragments:

```bash
python3 scripts/word_dump_to_ihex.py combine-v23-main-exports
```

Configure/build local gpsim fork:

```bash
mkdir -p artifacts/tools/gpsim-xtc/build
cd artifacts/tools/gpsim-xtc/build
env CPPFLAGS=-I/opt/homebrew/include LDFLAGS=-L/opt/homebrew/lib \
  ../../../../vendor/gpsim-0.32.1-xtc/configure --disable-gui
make -C src -j4 libgpsim.la
make -C modules -j4 libgpsim_modules.la
make -C gpsim gpsim
```

Run local gpsim fork checks:

```bash
scripts/gpsim-xtc --version
make -C vendor/gpsim-0.32.1-xtc/regression/p18f25k20 sim
```

Run full test gate (gpsim-inclusive, parallel):

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Branch/worktree workflow:

```bash
git worktree add ../analysis-<topic> -b feature/<topic> HEAD
cd ../analysis-<topic>
git branch --show-current
git status --short
```

Recommended shell environment for repo-local gpsim in any worktree:

```bash
export PATH="$(pwd)/scripts:$PATH"
export DLCP_GPSIM_BIN="$(pwd)/scripts/gpsim-xtc"
```

Notes:

- `src/dlcp_fw/sim/gpsim.py` resolves gpsim in this order:
  - `DLCP_GPSIM_BIN`
  - `GPSIM_BIN`
  - repo wrapper `scripts/gpsim-xtc`
  - `gpsim-xtc` / `gpsim` on `PATH`
- Prefer the repo wrapper `scripts/gpsim-xtc` or `DLCP_GPSIM_BIN="$(pwd)/scripts/gpsim-xtc"` over the system `gpsim`.
- `scripts/gpsim-xtc` automatically exports `GPSIM_MODULE_PATH` to `artifacts/tools/gpsim-xtc/build/modules/.libs`.
- If you bypass the wrapper and invoke the built binary directly, export:

```bash
export GPSIM_MODULE_PATH="$(pwd)/artifacts/tools/gpsim-xtc/build/modules/.libs${GPSIM_MODULE_PATH:+:$GPSIM_MODULE_PATH}"
```

Safe control flash preflight/live:

```bash
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh
```

## Maintenance Rules

- Do not add new hardcoded firmware paths; use `src/dlcp_fw/paths.py`.
- Do not add new runtime output under repository root; use `artifacts/sim/current/`.
- Keep execution entrypoints under `scripts/` and implementation in `src/dlcp_fw/`.
- Keep docs and this file synchronized whenever paths or filenames change.
