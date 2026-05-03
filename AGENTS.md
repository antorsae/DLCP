# DLCP Firmware Analysis — Master Index (Migrated Layout)

Last updated: 2026-05-03
Scope: `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`

## Purpose

`AGENTS.md` is the single source of truth for repository layout, canonical paths, and operational commands.

If any file is moved/renamed, update this document in the same change.

## System Overview

- Product: Hypex DLCP (Digital Loudspeaker Control Processor)
- Main MCU: PIC18F2455-class firmware image (`V2.3` stock, patched `V2.4`–`V2.8`, source-assembled `V3.0`/`V3.1`)
- Control MCU: PIC18F25K20 firmware image (`V1.4`/`V1.5b`/`V1.6b` stock, patched `V1.41`/`V1.51b`/`V1.61b`/`V1.62b`/`V1.63b`/`V1.64b`)
- DSP: TI TAS3108
- Host interface: USB HID (`VID 0x04D8`, `PID 0xFF89`)
- Inter-unit link: 31,250 baud current-loop serial (3-byte frames: route/cmd/data)

## Canonical Layout

```text
analysis/
├── AGENTS.md
├── tests/
│   ├── conftest.py
│   ├── hardware/
│   └── sim/
├── docs/
│   ├── AB_PRESETS.md
│   ├── ROBUSTNESS.md
│   ├── R_L_ROUTING.md
│   ├── SIMULATION.md
│   ├── TEST_SIMULATOR.md
│   ├── IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md
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
- Control AB + BF/08 + IR endpoint standby/wake: `firmware/patched/releases/DLCP_Control_V1.64b.hex`

### Source-assembled releases (V3.x / V1.7x)

- Main V3.0 (stock-equivalent rewrite): `firmware/patched/releases/DLCP_Firmware_V3.0.hex`
- Main V3.1 (all features inline): `firmware/patched/releases/DLCP_Firmware_V3.1.hex`
  - Canonical `V3.1` includes HID `cmd 0x43` diagnostic flash/EEPROM memread.
- Main V3.2 (async delayed-switch + Layer 5 diag counters): `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
  - **Recommended deployed MAIN release** when flashed with baked preset A/B captures (operator runbook: `docs/V32_RELEASE.md`).
  - Canonical build path: `scripts/build_v32_release.py` bumps the EEPROM revision byte at `eeprom_data[0x82]` on every build, then assembles the release back into the same canonical filename. Do not mint ad-hoc suffixed release names for V3.2.
- Control V1.71 (feature-bearing source rewrite + Layer 1/2/5): `firmware/patched/releases/DLCP_Control_V1.71.hex`
  - **Recommended deployed CONTROL release** when paired with V3.2 MAIN (operator runbook: `docs/V171_RELEASE.md`).
  - Canonical build path: `scripts/build_v171_release.py` bumps the flashed release-metadata revision byte at `control_release_metadata[11]` on every build, then assembles the release back into the same canonical filename.
- Source: `src/dlcp_fw/asm/dlcp_main_v30.asm`, `src/dlcp_fw/asm/dlcp_main_v31.asm`, `src/dlcp_fw/asm/dlcp_main_v32.asm`, `src/dlcp_fw/asm/dlcp_control_v17.asm`, `src/dlcp_fw/asm/dlcp_control_v171.asm`
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
- Reference docs: `firmware/reference/{DLCP-datasheet-R3.pdf,dlcp.md,DLCP-manual-R3.pdf,tas3108.pdf,tas3108.md,sleu067a.pdf,DLCP-control-intro.pdf,39632e.pdf,39632e.md,40001303h.pdf,40001303h.md}`
  - For the PIC18F2455 datasheet, `39632e.pdf` is authoritative. Use `39632e.md` as the line-stable converted companion for repo citations.
  - For the PIC18F25K20 datasheet, `40001303h.pdf` is authoritative. Use `40001303h.md` as the line-stable converted companion for repo citations.
  - For the TAS3108 datasheet, `tas3108.pdf` is authoritative. Use `tas3108.md` as the line-stable converted companion when repo citations are needed.

## Source Code Map (`src/dlcp_fw`)

### `src/dlcp_fw/paths.py`

Canonical constants used across scripts/tests:

- Directory roots: `PROJECT_ROOT`, `DOCS_DIR`, `FIRMWARE_DIR`, `ARTIFACTS_DIR`, `SCRIPTS_DIR`, `VENDOR_DIR`, `TOOLS_ARTIFACTS_DIR`
- Firmware dirs: `FIRMWARE_STOCK_DIR`, `FIRMWARE_PATCHED_DIR`, `FIRMWARE_DISASM_DIR`, `FIRMWARE_DUMPS_DIR`, `FIRMWARE_REFERENCE_DIR`
- Stock main: `STOCK_MAIN_HEX`, `STOCK_MAIN_PROGRAM_MEMORY_EXPORT`, `STOCK_MAIN_DUMP_TABLE`, `STOCK_MAIN_DUMP_CONVERTED_HEX`, `STOCK_MAIN_COMBINED_HEX`, `STOCK_MAIN_CONFIG_BITS_EXPORT`, `STOCK_MAIN_EE_DATA_EXPORT`, `STOCK_MAIN_USER_ID_EXPORT`
- Stock control: `STOCK_CONTROL_HEX_V14`, `STOCK_CONTROL_HEX_V15B`, `STOCK_CONTROL_HEX_V16B`
- Patched main: `PATCHED_MAIN_HEX_V24`, `PATCHED_MAIN_HEX_V25`, `PATCHED_MAIN_HEX_V26`, `PATCHED_MAIN_HEX_V27`, `PATCHED_MAIN_HEX_V28`, `PATCHED_MAIN_HEX` (alias for V2.7)
- Source-assembled main: `V30_MAIN_HEX`, `V30_MAIN_ASM`, `V30_MAIN_ASM_COMMENTS`, `V31_MAIN_HEX_CANONICAL`, `V31_MAIN_ASM_CANONICAL`, `V31_MAIN_HEX`, `V31_MAIN_ASM`, `V32_MAIN_HEX`, `V32_MAIN_ASM`
  - `V31_MAIN_HEX_CANONICAL` / `V31_MAIN_ASM_CANONICAL` are the repo-stable inputs for canonical V3.1 builders
  - `V31_MAIN_HEX` / `V31_MAIN_ASM` may be overridden for diagnostics with `DLCP_FW_V31_MAIN_HEX` / `DLCP_FW_V31_MAIN_ASM`
  - `V32_MAIN_HEX` is the canonical V3.2 release artifact at `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
- Source-assembled control: `V17_CONTROL_ASM`, `V17_CONTROL_ASM_COMMENTS`, `V17_CONTROL_ASM_SHIFTED`, `V171_CONTROL_ASM`, `V171_CONTROL_HEX`
  - `V171_CONTROL_HEX` is the canonical V1.71 release artifact at `firmware/patched/releases/DLCP_Control_V1.71.hex`
- Patched control: `PATCHED_CONTROL_HEX` (alias for V1.41), `PATCHED_CONTROL_HEX_V141`, `PATCHED_CONTROL_HEX_V151B`, `PATCHED_CONTROL_HEX_V161B`, `PATCHED_CONTROL_HEX_V162B`, `PATCHED_CONTROL_HEX_V163B`, `PATCHED_CONTROL_HEX_V164B`
- Disassembly: `MAIN_DISASM`, `MAIN_DISASM_ALT`, `MAIN_DISASM_SHORT`, `CONTROL_DISASM_V14`, `CONTROL_DISASM_V15B`, `CONTROL_DISASM_V16B`
- Sim/tools: `SIM_ARTIFACTS_DIR`, `REANALYSIS_ARTIFACTS_DIR`, `GPSIM_XTC_SOURCE_DIR`, `GPSIM_XTC_ARTIFACTS_DIR`, `GPSIM_XTC_BUILD_DIR`, `GPSIM_XTC_BIN_DIR`, `GPSIM_XTC_BINARY`, `GPSIM_XTC_COMPAT_BINARY`, `GPSIM_XTC_BUILD_BINARY`, `GPSIM_XTC_MODULE_DIR`
- Docs: `SEMANTIC_FUNCTION_MAP`

Always prefer these constants over hardcoded paths.

### Simulation package (`src/dlcp_fw/sim`)

- Core: `bus.py`, `protocol.py`, `scenarios.py`, `main_model.py`, `control_ui.py`
- gpsim harness: `control_gpsim.py`, `main_gpsim.py`, `main_gpsim_timer3.py`, `chain_gpsim.py`, `wire_chain_gpsim.py`, `gpsim.py`
- V3.0 tooling: `v30_symbols.py` (gpasm listing symbol parser, shifted ASM builder, assembly helper)
- V1.7 CONTROL tooling: `v17_symbols.py` (K20 assembly helper, CONTROL shifted-source builder, `parse_v17_symbols`)
- support: `hexio.py`, `lcd.py`, `overlay.py`, `manifests.py`, `paths.py`

### Assembly source package (`src/dlcp_fw/asm`)

- V3.0 stock-equivalent source: `dlcp_main_v30.asm`, `dlcp_main_v30_comments.asm` (canonical, zero auto-labels)
- V3.1 full-feature source: `dlcp_main_v31.asm`
- V1.7 CONTROL stock-equivalent source: `dlcp_control_v17.asm` (auto-labeled), `dlcp_control_v17_comments.asm` (canonical, zero auto-labels); shift-test source `dlcp_control_v17_shifted.asm` is generated on demand, not committed
- V1.71 CONTROL feature-bearing source: `dlcp_control_v171.asm` (cloned from V1.7 commented source; inlines V1.61b–V1.64b features per `docs/V16B_SOURCE_REWRITE_SPEC.md`)
- Support: `dlcp_main_ram.inc` (RAM equates), `dlcp_control_ram.inc` (CONTROL RAM equates), `region_manifest.py` (flash region metadata)

### Patch package (`src/dlcp_fw/patch`)

- Builders: `build_main_presets_ab.py`, `build_control_presets_ab.py`, `build_control_presets_ab_v15b.py`, `build_control_presets_ab_v16b.py`, `build_control_presets_ab_v162b.py`, `build_control_presets_ab_v163b.py`, `build_control_presets_ab_v164b.py`
- V3.1 diagnostics/build helpers: `build_v31_cmd07_stock_guard_usb_safe.py`, `build_v31_diag_coeff_stock.py`, `build_v31_diag_memread_usb_safe.py`, `build_v31_diag_no_flash_remap_usb_safe.py`, `build_v31_diag_stock_bf.py`, `build_v31_diag_stock_bf_reg1f.py`, `build_v31_diag_stock_i2c_byte_tx.py`, `build_v31_diag_v27_pen_hook.py`, `build_v31_nop_variants.py`, `build_v31_usb_safe.py`, `bake_preset_capture.py`
- Verifiers: `verify_presets_ab.py`, `verify_isr_vectors.py`

### Flash/probe package (`src/dlcp_fw/flash`)

- Safe control flasher: `dlcp_control_flash.py`
- Safe main flasher: `dlcp_main_flash.py`
- Canonical V3.1 operator wrapper: `dlcp_v31_release_flash.py`
- Preset query/switch helper: `dlcp_preset.py`
- V3.2 Tier-1 cmd 0x44 diag-snapshot reader: `dlcp_diag.py`
  (operator runbook: `scripts/dlcp_diag.py`; spec: `docs/V32_DIAG_TIER1_SPEC.md`)
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
- `scripts/hardware_flipper_ir.py`
- `scripts/hardware_lcd_probe.py`
- `scripts/hardware_state_test.py`
- `scripts/hardware_loop.py`
- `scripts/dlcp_preset.py`
- `scripts/dlcp_diag.py`
- `scripts/build_v171_release.py`
- `scripts/build_v32_release.py`
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

## Tests (`tests`)

Current suite (86 test files, 1049 tests collected):

Pytest markers:

- `slow`: long-running simulation test
- `gpsim`: requires gpsim binary
- `wire`: gpsim current-loop / wire-chain test
- `hardware`: live hardware test; skipped by default unless `--run-hardware` is passed

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
- `test_hardware_flipper_ir.py`, `test_hardware_loop.py`, `test_hardware_state_test.py`

Live hardware (optional):
- `tests/hardware/test_live_state_transitions.py` (preset convergence, rapid-toggle convergence, preset→mute timing sweep, preset→standby/wake timing sweep, reconnect responsiveness soak, and the V1.71+V3.2 Layer 5 Diagnostics-page rendering test on the real DLCP rig — the diag-page test gates on `DLCP_HW_LAYER5_AT_DIAG=1` after the operator manually navigates CONTROL to Diagnostics via physical RIGHT/RIGHT button presses; see `docs/HARDWARE_TEST.md` §"Diagnostics page" for the full operator walk-through)

V2.7 + V1.63b:
- `test_v27_v163b_robustness.py` (bus-clear, DSP ping, fault reporting, PEN timeout)

V3.0 source rewrite:
- `test_v30_equivalence.py` (hex integrity + source quality)
- `test_v30_gpsim_equivalence.py` (behavioral parity with stock)
- `test_v30_relocation.py` (10 structural + 6 gpsim behavioral shift tests)

V1.7 CONTROL source rewrite:
- `test_v17_equivalence.py` (hex integrity vs stock V1.6b, RAM equates, source quality)
- `test_v17_relocation.py` (structural shift test: vector block, bootloader pin, 0x222-byte label shift; gpsim standalone + dynamic-overlay parity)
- `test_v17_chain.py` (chain parity: V1.7 rebuild and V1.7 shifted + stock MAIN V2.3 reach the Volume screen and fall back to WAITING on blackout/wake)
- `test_v17_shifted_full_parity.py` (18 behavioral parity scenarios: idle warmup, volume up/down/mixed, menu select + mixed nav, STBY toggle, BF/03/05/06/07/1D parser echo, volume and input sweeps, press→RX echo, IR dispatch (volume/preset/standby), boot full-sync burst, host preset select, host cmd1d sweep)

V1.71 CONTROL feature-bearing source rewrite:
- `test_v171_baseline.py` (structural gates: vector block, bootloader, config, EEPROM version tuple + preset slot, app-code growth vs stock)
- `test_v171_preset_inline.py` (V1.61b: IR 0x38/0x39 A/B shortcuts, boot init from EEPROM 0x74, A↔B toggle, idempotence)
- `test_v171_ir_endpoints.py` (V1.64b: IR 0x3A/0x3B explicit standby/wake endpoints, first-frame ordering)
- `test_v171_fault_indicator.py` (V1.63b: BF/08 DSP-fault parser, bf08_fault_byte store at 0x0AB, DSP_FAULT_BIT set/clear, no-op on clean clear)
- `test_v171_reconnect_wake.py` (V1.62b: OERR soft-recover clears latch + re-enables CREN, parser continues after OERR, can still process fresh BF/08 frame)
- `test_v171_preset_menu.py` (V1.61b Phase B.4: preset screen body symbols, 4-way nav wrap literals, state=1 dispatch to v171_preset_screen)
- `test_v171_full_sync_retry.py` (V1.61b Phase B.5: retry counter block at full_sync_burst head, reuses v171_send_preset_frame_and_persist, preset frame appears in post-connect TX)
- `test_v171_sentinel_reconnect.py` (V1.62b Phase C.3: sentinel-check body markers, UART soft-recover embedded, wake + idle-timer reload on exit, sentinels clear after heartbeat warmup)
- `test_v171_v31_chain.py` (V1.71 × V3.1 MAIN chain parity gate: reach Volume screen, blackout/wake → WAITING)

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

Recent verification (latest 2026-04-22):

- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests --collect-only -q` -> `1049 tests collected`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_control_flash_safety.py tests/sim/test_v171_baseline.py` -> `20 passed`
- `.venv_ep0/bin/python scripts/build_v171_release.py` -> canonical `DLCP_Control_V1.71.hex` rebuilt with release rev bump `0x01 -> 0x02`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_main_flash.py tests/sim/test_dlcp_v32_release_flash.py tests/sim/test_dlcp_diag.py tests/sim/test_v32_no_pop_flash_entry.py` -> `77 passed`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_read_coeffs.py tests/sim/test_dlcp_preset.py tests/sim/test_hardware_state_test.py tests/sim/test_dlcp_hfd_upload.py` -> `57 passed`
- `PYTHONPATH=src .venv_ep0/bin/python scripts/build_v32_release.py` -> canonical `DLCP_Firmware_V3.2.hex` rebuilt with EEPROM rev bump `0x37 -> 0x38`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_control_gpsim_ir_preset_switch.py -k "waiting or reaches_main"` -> `2 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_v28_wire_delayed_switch_repros.py` -> `5 xfailed`
- `.venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py --collect-only -q` -> `6 tests collected` (5 existing + 1 V1.71/V3.2 Layer 5 Diagnostics-page test)
- `.venv_ep0/bin/python -m pytest -q tests/hardware/test_live_state_transitions.py --run-hardware` -> `6 skipped` (expected when camera or HID open-path access is unavailable; the Layer 5 test additionally requires `DLCP_HW_LAYER5_AT_DIAG=1` after the operator manually navigates CONTROL to Diagnostics)

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
- `docs/HARDWARE_TEST.md` (real-hardware state-transition validation runbook for two MAINs, CONTROL, IR, and LCD capture)
- `docs/HARDWARE_LOOP.md` (real-hardware audio playback/capture workflow and firmware comparison matrix)
- `docs/RECOVERY.md` (PICkit 5 readback recombination and full MAIN recovery image workflow)
- `docs/ROBUSTNESS.md` (robustness findings, release policy, and implementation plan)
- `docs/DLCP_LINK_V2_SPEC.md` (lean robust replacement for the legacy 3-byte CONTROL<->MAIN current-loop protocol)
- `docs/R_L_ROUTING.md` (MAIN/CONTROL/HFD routing semantics and `R-L` extension plan)
- `docs/SIMULATION.md` (co-simulation architecture and usage)
- `docs/SIM_REWRITE_RUST_SPEC.md` (Rust single-process PIC18 simulator rewrite specification)
- `docs/IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md` (implementation plan for Rust PIC18 silicon-fidelity gap closure)
- `docs/TEST_SIMULATOR.md` (test framework and commands)
- `docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md` (wire-chain delayed preset desynchronization analysis and source-level remediation plan)
- `docs/V31_RELEASE.md` (`V3.1` MAIN deployment workflow with baked preset A/B captures)
- `docs/V32_RELEASE.md` (recommended `V3.2` MAIN deployment workflow + V1.71 CONTROL pairing)
- `docs/V171_RELEASE.md` (recommended `V1.71` CONTROL deployment workflow + V3.2 MAIN pairing)
- `docs/NO_POP_FIRMWARE_FLASH.md` (V3.2+ pop-free flash-entry path; implemented as `flash_entry_quiet_shutdown`; operator validation runbook in `docs/HARDWARE_TEST.md` §"Re-flash pop monitoring")
- `docs/V27_V163B_SPEC.md` (V2.7 MAIN + V1.63b CONTROL specification)
- `docs/V27_V163B_STATUS.md` (V2.7 + V1.63b implementation status)
- `docs/V30_SOURCE_REWRITE_SPEC.md` (V3.0 MAIN source-level rewrite specification)
- `docs/IMPL_V30_SOURCE_REWRITE_SPEC.md` (V3.0 source rewrite implementation prompt)
- `docs/IMPL_V30_SOURCE_REWRITE_SPECv2.md` (V3.0 source rewrite polished implementation — supersedes above)
- `docs/V31_SOURCE_REWRITE_SPEC.md` (V3.1 MAIN source rewrite specification)
- `docs/IMPL_V31_SOURCE_REWRITE_SPEC.md` (V3.1 source rewrite implementation prompt)
- `docs/V163B_DIAGNOSTICS_MENU_SPEC.md` (Layer 5 Diagnostics page / counter protocol; implemented in the committed V1.71 CONTROL + V3.2 MAIN pair)
- `docs/V31_SIZE_OPTIMIZATION_SPEC_and_IMPL.md` (V3.1 MAIN size-reduction campaign — **frozen 2026-04-21**)
- `docs/V31_SIZE_OPTIMIZATION_PROGRESS.md` (V3.1 size campaign ledger — **frozen 2026-04-21**)
- `docs/V32_SIZE_OPTIMIZATION_SPEC_and_IMPL.md` (V3.2 MAIN size-reduction campaign — **active successor**)
- `docs/V32_SIZE_OPTIMIZATION_PROGRESS.md` (V3.2 size campaign ledger — **active**)
- `docs/V32_MAIN_HANG_HARDENING_PLAN.md` (V3.2 MAIN hang-prevention and fail-safe hardening roadmap for two-MAIN chains)
- `docs/V16B_SOURCE_REWRITE_SPEC.md` (V1.71 CONTROL feature-bearing source rewrite specification)
- `docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md` (V1.7 CONTROL byte-identical source rebuild — polished implementation, parent of V1.71)

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
python3 -m dlcp_fw.patch.build_control_presets_ab_v164b
python3 -m dlcp_fw.patch.verify_presets_ab
```

Assemble V3.1 source:

```bash
.venv_ep0/bin/python -c "from dlcp_fw.sim.v30_symbols import assemble_v30; from dlcp_fw.paths import V31_MAIN_ASM, V31_MAIN_HEX; assemble_v30(V31_MAIN_ASM, V31_MAIN_HEX)"
```

Build the canonical V3.2 release:

```bash
.venv_ep0/bin/python scripts/build_v32_release.py
```

Build the canonical V1.71 CONTROL release:

```bash
.venv_ep0/bin/python scripts/build_v171_release.py
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

Worktree shared-artifact setup:

```bash
export DLCP_WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
export DLCP_TOOLS_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

mkdir -p "$DLCP_WORKTREE_ROOT/artifacts"
if [ -e "$DLCP_WORKTREE_ROOT/artifacts/LX521.4" ] && [ ! -L "$DLCP_WORKTREE_ROOT/artifacts/LX521.4" ]; then
  echo "Expected worktree artifacts/LX521.4 to be absent or a symlink; fix manually before continuing." >&2
  exit 1
fi
ln -sfn "$DLCP_TOOLS_ROOT/artifacts/LX521.4" "$DLCP_WORKTREE_ROOT/artifacts/LX521.4"
```

Recommended shell environment in any worktree:

```bash
export DLCP_WORKTREE_ROOT="$(git rev-parse --show-toplevel)"
export DLCP_TOOLS_ROOT="$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")"

export DLCP_PYTHON="$DLCP_TOOLS_ROOT/.venv_ep0/bin/python"
export DLCP_GPSIM_BIN="$DLCP_TOOLS_ROOT/scripts/gpsim-xtc"
export PATH="$DLCP_WORKTREE_ROOT/scripts:$PATH"
```

Notes:

- `DLCP_WORKTREE_ROOT` is the active checkout/worktree you are editing.
- `DLCP_TOOLS_ROOT` is the checkout that owns the shared `.venv_ep0` and compiled local `gpsim`. In the main checkout it resolves to the same directory as `DLCP_WORKTREE_ROOT`; in linked worktrees it resolves to the shared/base checkout.
- New worktrees should expose `artifacts/LX521.4` as a symlink to `"$DLCP_TOOLS_ROOT/artifacts/LX521.4"` so they reuse the base checkout artifact tree.
- Prefer `"$DLCP_PYTHON"` over guessing whether `.venv_ep0` exists inside the current worktree.
- `src/dlcp_fw/sim/gpsim.py` resolves gpsim in this order:
  - `DLCP_GPSIM_BIN`
  - `GPSIM_BIN`
  - repo wrapper `scripts/gpsim-xtc`
  - `gpsim-xtc` / `gpsim` on `PATH`
- Prefer the shared wrapper `"$DLCP_GPSIM_BIN"` over the system `gpsim`.
- `"$DLCP_GPSIM_BIN"` points to `scripts/gpsim-xtc`, which automatically exports `GPSIM_MODULE_PATH` to the matching `artifacts/tools/gpsim-xtc/build/modules/.libs`.
- If you bypass the wrapper and invoke the built binary directly, export:

```bash
export GPSIM_MODULE_PATH="$DLCP_TOOLS_ROOT/artifacts/tools/gpsim-xtc/build/modules/.libs${GPSIM_MODULE_PATH:+:$GPSIM_MODULE_PATH}"
```

Safe control flash preflight/live:

```bash
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh
```

## V3.2 Release Ceremony

- Canonical MAIN release output is always `firmware/patched/releases/DLCP_Firmware_V3.2.hex`.
- Each canonical `V3.2` build must increment the EEPROM revision byte in `src/dlcp_fw/asm/dlcp_main_v32.asm` at `eeprom_data[0x82]`; `scripts/build_v32_release.py` is the required path because it bumps the byte before assembling.
- `scripts/dlcp_main_flash.py` and `scripts/dlcp_v32_release_flash.py` must read version + revision from both the selected device and the target hex before flashing. If the device is already at the same or newer firmware identity, emit a `WARNING` rather than silently downgrading.
- When `--path` is omitted but the operator supplies `--left`, `--right`, or `--all-ch L|R`, the MAIN flasher should auto-pick the target only when exactly one connected app-mode MAIN reports a uniform matching route table (`all L` or `all R`). Any ambiguity must stay a hard error.

## V1.71 Release Ceremony

- Canonical CONTROL release output is always `firmware/patched/releases/DLCP_Control_V1.71.hex`.
- Each canonical `V1.71` build must increment the flashed release-metadata byte in `src/dlcp_fw/asm/dlcp_control_v171.asm` at `control_release_metadata[11]`; `scripts/build_v171_release.py` is the required path because it bumps the byte before assembling.
- `scripts/flash_control_safe.sh` now defaults to the canonical `V1.71` hex.
- `src/dlcp_fw/flash/dlcp_control_flash.py` must read version + revision from the target hex and report them during preflight/live flash. The current CONTROL update relay does not expose a live version/revision probe, so device-versus-hex compare is not currently available there.

## Simulator Rewrite (`feature/sim-rewrite-rust`)

This branch hosts the in-progress rewrite of the simulation harness from
gpsim-PTY-bridged-three-process to a single-process cycle-perfect Rust
engine (`crates/dlcp-sim/`).  Goal: kill the cross-process UART bridge
and PTY overhead, run the full sim gate in < 60 s, and natively model
multi-clock-domain + boot-offset behaviour so the Task #22 echo-loop
disappears mechanically.

**Canonical artifacts (this branch only):**

- Spec: `docs/SIM_REWRITE_RUST_SPEC.md` (complete design; 6 phases + final
  acceptance + risk register + glossary)
- Implementation plan: `docs/IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md`
  (PIC18 silicon-fidelity gap closure for spec section 11c)
- Progress ledger (machine-readable): `docs/SIM_REWRITE_RUST_PROGRESS.md`
- Automation entry: `scripts/sim_rewrite_next.py`
  - `python3 scripts/sim_rewrite_next.py status` — current phase + next pending sub-task
  - `python3 scripts/sim_rewrite_next.py advance` — claim next pending task, run its verify command, mark done on pass
  - `python3 scripts/sim_rewrite_next.py verify-phase N` — run all gates for a phase
  - `python3 scripts/sim_rewrite_next.py report` — counts by status and phase
  - `python3 scripts/sim_rewrite_next.py block <ID> --reason "..."` — pause a sub-task
- Rust crate (created during P1.1): `crates/dlcp-sim/`
- PyO3 wrapper crate (created during P4.1): `crates/dlcp-sim-py/`
- Ground truth fixtures: `artifacts/ground_truth/<test_id>/`
- Divergence reports: `artifacts/sim_rewrite_divergences/<task_id>__<ts>.log`

**Latest Rust simulator verification (2026-05-03):**

- `cargo test -p dlcp-sim --release` -> passed (existing ignored tests only)
- `cargo build --release -p dlcp-sim-py && bash crates/dlcp-sim-py/build.sh` -> passed
- `DLCP_SIM_BACKEND=rust .../analysis/.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -m "not slow"` -> `582 passed, 39 skipped, 1 xfailed`
- `DLCP_SIM_BACKEND=rust .../analysis/.venv_ep0/bin/python -m pytest tests/sim -n 16 -q -m slow` -> `204 passed, 260 skipped, 7 xfailed`

The linked worktree may not contain `.venv_ep0`; use the shared tools
checkout interpreter from `$(dirname "$(git rev-parse --path-format=absolute --git-common-dir)")/.venv_ep0/bin/python`.

**Workflow (minimal user intervention):**

1. `python3 scripts/sim_rewrite_next.py status` — see what's next.
2. Either implement the sub-task by hand, or spawn an agent with the
   instructions in `docs/SIM_REWRITE_AGENT_INSTRUCTIONS.md`.
3. Run `advance` to claim+verify; on PASS the ledger is updated atomically.
4. On FAIL the divergence is captured; status remains `in_progress`;
   fix the issue and rerun `advance`.

**Rules specific to this branch:**

- The progress ledger is the source of truth; do not update phase status
  by hand-editing the markdown — always go through `sim_rewrite_next.py`.
- Every sub-task that lands a code change must include the verify command
  in its commit message, so the per-commit codex review sees the gate.
- Do not delete `vendor/gpsim-0.32.1-xtc/` or `chain_gpsim.py` /
  `wire_chain_gpsim.py` until Phase 4.9 fires — gpsim is the ground-truth
  oracle through Phase 4.
- All new code lives under `crates/dlcp-sim*/` (Rust) and
  `src/dlcp_fw/sim/dlcp_sim_native.py` (Python facade).  Existing
  `src/dlcp_fw/sim/*.py` files stay intact until their migration sub-task
  fires.
- Differential testing: `DLCP_SIM_BACKEND=dual pytest tests/sim` runs both
  engines and asserts identical externally-visible behaviour (UART byte
  streams, LCD raster, EEPROM image, RAM snapshots).  This is the
  migration safety net — never bypass it.

## Maintenance Rules

- Do not add new hardcoded firmware paths; use `src/dlcp_fw/paths.py`.
- Do not add new runtime output under repository root; use `artifacts/sim/current/`.
- Keep execution entrypoints under `scripts/` and implementation in `src/dlcp_fw/`.
- Keep canonical release names stable. For V3.2, rebuild `DLCP_Firmware_V3.2.hex`; do not create new release filenames for incremental revisions.
- Keep docs and this file synchronized whenever paths or filenames change.

## Per-Commit Codex Review (Claude Code only -- codex agents: skip this section)

> **Audience: Claude Code ONLY.**  This file (`AGENTS.md`) is read by
> both Claude Code (via the `CLAUDE.md` -> `AGENTS.md` symlink) and by
> codex-cli (via its standard project-instructions discovery).  This
> section instructs **Claude** to invoke the codex-cli MCP tool as a
> code-review pass after each commit.
>
> **If you are codex reading this file**: ignore this entire section.
> It does not apply to you.  Do NOT attempt to invoke yourself
> recursively, do NOT auto-trigger reviews, and do NOT treat the
> "tool call template" below as a directive for your own behavior.
> Your job, when invoked by Claude on a specific commit, is fully
> defined by the prompt Claude passes you in that invocation --
> nothing in this section overrides or supplements that prompt.

After every `git commit` that lands on this branch, the post-commit
hook at `.claude/hooks/codex-review-on-commit.sh` fires and surfaces
a `[CODEX REVIEW REQUIRED]` reminder.  When **Claude** sees that
reminder, Claude (NOT codex) calls the codex-cli MCP tool BEFORE
starting any new task.

Tool call template (executed by Claude):

```
mcp__codex-cli__codex(
    cwd="<repo root from the reminder>",
    sandbox="read-only",
    approval-policy="never",
    prompt="""
You are doing a code review of the most recent commit on this branch
(HEAD = <hash>, "<subject line>").

Context: <one-line description of what area this commit touches>.

What I need from you:
1. Run `git show HEAD` to see the full diff.
2. Read any locked spec files relevant to the change (e.g.
   V32_DIAG_TIER1_SPEC.md for diag work, ROBUSTNESS.md for chain work,
   SIMULATION.md for harness changes).
3. Read the modified source / test / doc files end-to-end -- enough
   to understand the relevant state machines, control flow, and
   contracts.
4. Flag any HIGH/MEDIUM/LOW issues: bugs, regressions, missed spec
   requirements, incorrect assumptions, dead code, RAM aliasing,
   off-by-one, race conditions, test coverage gaps, anything else.
5. For each finding, give: severity tag, one-paragraph description,
   file:line refs (use the actual paths under this repo).
6. If you find nothing, say so explicitly with what you checked.

Keep the report under 600 words.  Don't propose fixes -- just
findings.  Don't modify any files (you're in read-only sandbox).
"""
)
```

After codex reports findings (Claude acts on them):

- **HIGH or MEDIUM** -> fix in a follow-up commit BEFORE moving on,
  OR explicitly defer with the user's confirmation.
- **LOW** -> may be deferred but must be tracked (`TaskCreate` or
  noted in the next commit message).
- **No findings** -> acknowledge "codex: clean" in your reply and
  proceed.

Claude must not silently skip the codex review.  If the user
explicitly asks Claude to defer the review for a particular commit,
Claude says so and continues.

The hook is configured in `.claude/settings.json` and runs after any
Bash invocation containing `git commit` whose HEAD timestamp is
within the last 5 minutes (so amends / no-op rebases don't re-trigger
the review).  The hook is non-blocking -- it only emits a stdout
notice; it never aborts the tool call.

To disable repo-wide, remove or comment out the PostToolUse entry in
`.claude/settings.json`.
