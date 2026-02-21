"""Canonical repository paths for DLCP firmware tooling."""

from __future__ import annotations

from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DOCS_DIR = PROJECT_ROOT / "docs"
FIRMWARE_DIR = PROJECT_ROOT / "firmware"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"

FIRMWARE_STOCK_DIR = FIRMWARE_DIR / "stock"
FIRMWARE_PATCHED_DIR = FIRMWARE_DIR / "patched" / "releases"
FIRMWARE_DISASM_DIR = FIRMWARE_DIR / "disasm"
FIRMWARE_DUMPS_DIR = FIRMWARE_DIR / "dumps"
FIRMWARE_REFERENCE_DIR = FIRMWARE_DIR / "reference"

STOCK_MAIN_HEX = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3.hex"
STOCK_CONTROL_HEX_V14 = FIRMWARE_STOCK_DIR / "control" / "DLCP Control Firmware V1.4.hex"
STOCK_CONTROL_HEX_V15B = FIRMWARE_STOCK_DIR / "control" / "DLCP Control Firmware V1.5b.hex"
STOCK_CONTROL_HEX_V16B = FIRMWARE_STOCK_DIR / "control" / "DLCP Control Firmware V1.6b.hex"

PATCHED_MAIN_HEX = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.4.hex"
PATCHED_CONTROL_HEX_V141 = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.41.hex"
PATCHED_CONTROL_HEX_V151B = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.51b.hex"
PATCHED_CONTROL_HEX_V161B = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.61b.hex"
# Backward-compatible alias: existing tests/tools use this as the active control patch.
PATCHED_CONTROL_HEX = PATCHED_CONTROL_HEX_V141

MAIN_DISASM = FIRMWARE_DISASM_DIR / "main" / "gpdasm_output.asm"
MAIN_DISASM_ALT = FIRMWARE_DISASM_DIR / "main" / "full_disasm.asm"
MAIN_DISASM_SHORT = FIRMWARE_DISASM_DIR / "main" / "gpdasm_short.asm"

CONTROL_DISASM_V14 = FIRMWARE_DISASM_DIR / "control" / "v1.4_disasm.asm"
CONTROL_DISASM_V15B = FIRMWARE_DISASM_DIR / "control" / "v1.5b_disasm.asm"
CONTROL_DISASM_V16B = FIRMWARE_DISASM_DIR / "control" / "v1.6b_disasm.asm"

SIM_ARTIFACTS_DIR = ARTIFACTS_DIR / "sim" / "current"
REANALYSIS_ARTIFACTS_DIR = ARTIFACTS_DIR / "reanalysis" / "20260214"
