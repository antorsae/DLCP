# DLCP Firmware Analysis — Master Index (Migrated Layout)

Last updated: 2026-03-08
Scope: `/Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis`

## Purpose

`AGENTS.md` is the single source of truth for repository layout, canonical paths, and operational commands.

If any file is moved/renamed, update this document in the same change.

## System Overview

- Product: Hypex DLCP (Digital Loudspeaker Control Processor)
- Main MCU: PIC18F2455-class firmware image (`V2.3` stock, patched `V2.4`)
- Control MCU: PIC18F2550-class firmware image (`V1.4`/`V1.5b`/`V1.6b` stock, patched `V1.41`/`V1.51b`/`V1.61b`)
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
│   ├── sim/
│   ├── patch/
│   ├── flash/
│   ├── analysis/
│   └── cli/
├── scripts/
├── tests/sim/
├── artifacts/
│   ├── sim/current/
│   ├── reanalysis/
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
- Generated runtime/test artifacts: `artifacts/sim/current/...`
- Python package code: `src/dlcp_fw/...`
- CLI entry scripts: `scripts/...`

## Firmware Artifacts

### Stock

- Main: `firmware/stock/main/DLCP Firmware V2.3.hex`
- Control V1.4: `firmware/stock/control/DLCP Control Firmware V1.4.hex`
- Control V1.5b: `firmware/stock/control/DLCP Control Firmware V1.5b.hex`
- Control V1.6b: `firmware/stock/control/DLCP Control Firmware V1.6b.hex`
- PC host app bundle: `firmware/stock/PC/HFD_v2.12/...`
- PC host installer bundle: `firmware/stock/PC/HFD_v4.97/...`

### Patched releases

- Main AB: `firmware/patched/releases/DLCP_Firmware_V2.4.hex`
- Control AB: `firmware/patched/releases/DLCP_Control_V1.41.hex`
- Control AB (V1.5b port): `firmware/patched/releases/DLCP_Control_V1.51b.hex`
- Control AB (V1.6b port): `firmware/patched/releases/DLCP_Control_V1.61b.hex`

### Disassembly

- Main primary: `firmware/disasm/main/gpdasm_output.asm`
- Main alternates: `firmware/disasm/main/full_disasm.asm`, `firmware/disasm/main/gpdasm_short.asm`
- Control primary: `firmware/disasm/control/v1.4_disasm.asm`
- Control variants: `firmware/disasm/control/v1.5b_disasm.asm`, `firmware/disasm/control/v1.6b_disasm.asm`
- Legacy/raw control disasm: `firmware/disasm/control/v14.asm`, `firmware/disasm/control/v15b.asm`, `firmware/disasm/control/v16b.asm`
- PC HFD RE artifacts: `firmware/disasm/PC/HFD_v2.12/...`, `firmware/disasm/PC/HFD_v4.97/...`

### Dumps and references

- Dumps: `firmware/dumps/{firmware.bin,code_only.bin,eeprom.bin,dlcp_flash_0800_7fff.bin,dlcp_probe_1000.bin}`
- Reference docs: `firmware/reference/{DLCP-datasheet-R3.pdf,DLCP-manual-R3.pdf,tas3108.pdf,sleu067a.pdf,DLCP-control-intro.pdf,39632e.pdf,39632e.txt}`

## Source Code Map (`src/dlcp_fw`)

### `src/dlcp_fw/paths.py`

Canonical constants used across scripts/tests:

- `STOCK_MAIN_HEX`
- `STOCK_CONTROL_HEX_V14`
- `PATCHED_MAIN_HEX`
- `PATCHED_CONTROL_HEX`
- `SIM_ARTIFACTS_DIR`

Always prefer these constants over hardcoded paths.

### Simulation package (`src/dlcp_fw/sim`)

- Core: `bus.py`, `protocol.py`, `scenarios.py`, `main_model.py`, `control_ui.py`
- gpsim harness: `control_gpsim.py`, `main_gpsim.py`, `main_gpsim_timer3.py`, `gpsim.py`
- support: `hexio.py`, `lcd.py`, `overlay.py`, `manifests.py`, `paths.py`

### Patch package (`src/dlcp_fw/patch`)

- Builders: `build_main_presets_ab.py`, `build_control_presets_ab.py`, `build_control_presets_ab_v15b.py`, `build_control_presets_ab_v16b.py`
- Verifiers: `verify_presets_ab.py`, `verify_isr_vectors.py`

### Flash/probe package (`src/dlcp_fw/flash`)

- Safe control flasher: `dlcp_control_flash.py`
- EEPROM shadow dump: `dlcp_ep0_eeprom_shadow_dump.py`
- DSP filename A/B probe: `dsp_filename_ab_probe.py`

### Analysis package (`src/dlcp_fw/analysis`)

Contains migrated analysis scripts and utilities including:

- `analyze_firmware.py`, `analyze_control_firmware.py`
- `code_analysis.py`, `deep_analysis.py`, `deep_analysis2.py`, `ultra_deep.py`
- `channel_dsp_analysis.py`, `dsp_comm_analysis.py`, `coefficient_format_analysis.py`
- `data_structure_analysis.py`, `filter_stages_analysis.py`, `final_analysis.py`
- `control_firmware_analysis.py`, `dlcp_table_decode.py`, `reconstruct_main_bins.py`
- `config_analysis.py`

## CLI Entry Points

### Canonical (new)

- `scripts/simctl.py`
- `scripts/gpsim_tui_simulator.py`
- `scripts/gpsim_menu_command_audit.py`
- `scripts/gpsim_lcd_capture_decode.py`
- `scripts/gpsim_headless_chain_diagnose.py`
- `scripts/sim_presets_ab.py`
- `scripts/sim_link_control_main_presets_ab.py`
- `scripts/sim_control_ui_presets.py`
- `scripts/flash_control_safe.sh`
- `scripts/test_full_boot.py`, `scripts/test_button_inject.py`

## Tests (`tests/sim`)

Current suite includes:

- Overlay/patch integrity: `test_overlay_engine.py`, `test_patch_compatibility.py`, `test_verify_presets_ab_*semantic_guards.py`
- Main behavior: `test_main_model_banking.py`, `test_main_dsp_refresh_behavior.py`, `test_main_gpsim_*`
- Control behavior: `test_control_ui_and_persistence.py`, `test_gpsim_control_presets.py`, `test_control_v*b_port_compatibility.py`, `test_control_gpsim_*`
- End-to-end/faults: `test_scenarios.py`, `test_bus_faults.py`, `test_control_main_powercycle_sync.py`
- Flash/probe tools: `test_dlcp_control_flash_safety.py`, `test_dlcp_ep0_eeprom_shadow_dump.py`, `test_dsp_filename_ab_probe.py`

Recent verification (2026-03-08):

- `.venv_ep0/bin/python -m pytest -q tests/sim` -> `211 passed`
- `.venv_ep0/bin/python -m pytest -q tests/sim --collect-only` -> `211 tests collected`

## Documentation Map

Top-level docs:

- `docs/AB_PRESETS.md` (A/B preset patch design, flashing, checks)
- `docs/ROBUSTNESS.md` (robustness findings, release policy, and implementation plan)
- `docs/R_L_ROUTING.md` (MAIN/CONTROL/HFD routing semantics and `R-L` extension plan)
- `docs/SIMULATION.md` (co-simulation architecture and usage)
- `docs/TEST_SIMULATOR.md` (test framework and commands)

Deep analysis docs:

- `docs/analysis/ANALYSIS_REPORT_CLAUDE.md`
- `docs/analysis/CONTROL_FW_VERSION_DIFFS.md`
- `docs/analysis/CONTROL_UNIT_ANALYSIS.md`
- `docs/analysis/FIRMWARE_UPDATE_MECHANISM.md`
- `docs/analysis/HFD_v2.12-codex.md`
- `docs/analysis/HFD_v2.12-RL-binary-patch-plan.md`
- `docs/analysis/HFD_v4.97-codex.md`
- `docs/analysis/PIN_SEMANTICS.md`
- `docs/analysis/REANALYSIS_CORRECTIONS_2026-02-16.md`
- `docs/analysis/SIMULATION_STDBY_WAIT_DIAGNOSIS.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-gpt-5.4-xhigh.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-gpt-5.2-pro.md`
- `docs/analysis/STOCK_SYNC_DEADLOCK_ANALYSIS_2026-03-08-opus-4.6.md`

## Artifacts and Caches

Reanalysis artifacts (local by default; ignored via `.gitignore`):

- `artifacts/reanalysis/...`

Generated/ephemeral (ignored):

- `artifacts/sim/current/...`
- `artifacts/probes/...`
- `__pycache__/`, `.pytest_cache/`, `.ruff_cache/`, `.venv*`, etc.

## Common Commands

Build patched firmware:

```bash
python3 -m dlcp_fw.patch.build_main_presets_ab
python3 -m dlcp_fw.patch.build_control_presets_ab
python3 -m dlcp_fw.patch.build_control_presets_ab_v15b
python3 -m dlcp_fw.patch.build_control_presets_ab_v16b
python3 -m dlcp_fw.patch.verify_presets_ab
```

Run full test gate (gpsim-inclusive):

```bash
.venv_ep0/bin/python -m pytest -q tests/sim
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
