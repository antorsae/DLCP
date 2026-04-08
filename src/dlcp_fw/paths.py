"""Canonical repository paths for DLCP firmware tooling."""

from __future__ import annotations

import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]

DOCS_DIR = PROJECT_ROOT / "docs"
FIRMWARE_DIR = PROJECT_ROOT / "firmware"
ARTIFACTS_DIR = PROJECT_ROOT / "artifacts"
SCRIPTS_DIR = PROJECT_ROOT / "scripts"
VENDOR_DIR = PROJECT_ROOT / "vendor"
TOOLS_ARTIFACTS_DIR = ARTIFACTS_DIR / "tools"

FIRMWARE_STOCK_DIR = FIRMWARE_DIR / "stock"
FIRMWARE_PATCHED_DIR = FIRMWARE_DIR / "patched" / "releases"
FIRMWARE_DISASM_DIR = FIRMWARE_DIR / "disasm"
FIRMWARE_DUMPS_DIR = FIRMWARE_DIR / "dumps"
FIRMWARE_REFERENCE_DIR = FIRMWARE_DIR / "reference"

STOCK_MAIN_HEX = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3.hex"
STOCK_MAIN_PROGRAM_MEMORY_EXPORT = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-Program Memory.hex"
STOCK_MAIN_DUMP_TABLE = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-dump.hex"
STOCK_MAIN_DUMP_CONVERTED_HEX = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-dump-converted.hex"
STOCK_MAIN_COMBINED_HEX = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-combined.hex"
STOCK_MAIN_CONFIG_BITS_EXPORT = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-Configuration Bits.hex"
STOCK_MAIN_EE_DATA_EXPORT = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-EE Data Memory.hex"
STOCK_MAIN_USER_ID_EXPORT = FIRMWARE_STOCK_DIR / "main" / "DLCP Firmware V2.3-User ID Memory.hex"
STOCK_CONTROL_HEX_V14 = FIRMWARE_STOCK_DIR / "control" / "DLCP Control Firmware V1.4.hex"
STOCK_CONTROL_HEX_V15B = FIRMWARE_STOCK_DIR / "control" / "DLCP Control Firmware V1.5b.hex"
STOCK_CONTROL_HEX_V16B = FIRMWARE_STOCK_DIR / "control" / "DLCP Control Firmware V1.6b.hex"

PATCHED_MAIN_HEX_V24 = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.4.hex"
PATCHED_MAIN_HEX_V25 = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.5.hex"
PATCHED_MAIN_HEX_V26 = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.6.hex"
PATCHED_MAIN_HEX_V27 = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.7.hex"
PATCHED_MAIN_HEX_V28 = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V2.8.hex"
V30_MAIN_HEX = FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.0.hex"
V30_MAIN_ASM = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30.asm"
V30_MAIN_ASM_COMMENTS = PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v30_comments.asm"


def _path_override(env_name: str, default: Path) -> Path:
    raw = os.environ.get(env_name)
    if not raw:
        return default
    path = Path(raw).expanduser()
    if not path.is_absolute():
        path = PROJECT_ROOT / path
    return path.resolve()


V31_MAIN_ASM = _path_override(
    "DLCP_FW_V31_MAIN_ASM",
    PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v31.asm",
)
V31_MAIN_HEX = _path_override(
    "DLCP_FW_V31_MAIN_HEX",
    FIRMWARE_PATCHED_DIR / "DLCP_Firmware_V3.1.hex",
)
# Active main patch alias: keep the established baseline for legacy tests/tools.
PATCHED_MAIN_HEX = PATCHED_MAIN_HEX_V27
PATCHED_CONTROL_HEX_V141 = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.41.hex"
PATCHED_CONTROL_HEX_V151B = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.51b.hex"
PATCHED_CONTROL_HEX_V161B = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.61b.hex"
PATCHED_CONTROL_HEX_V162B = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.62b.hex"
PATCHED_CONTROL_HEX_V163B = FIRMWARE_PATCHED_DIR / "DLCP_Control_V1.63b.hex"
# Backward-compatible alias: existing tests/tools use this as the active control patch.
PATCHED_CONTROL_HEX = PATCHED_CONTROL_HEX_V141

MAIN_DISASM = FIRMWARE_DISASM_DIR / "main" / "gpdasm_output.asm"
MAIN_DISASM_ALT = FIRMWARE_DISASM_DIR / "main" / "full_disasm.asm"
MAIN_DISASM_SHORT = FIRMWARE_DISASM_DIR / "main" / "gpdasm_short.asm"

CONTROL_DISASM_V14 = FIRMWARE_DISASM_DIR / "control" / "v1.4_disasm.asm"
CONTROL_DISASM_V15B = FIRMWARE_DISASM_DIR / "control" / "v1.5b_disasm.asm"
CONTROL_DISASM_V16B = FIRMWARE_DISASM_DIR / "control" / "v1.6b_disasm.asm"

SEMANTIC_FUNCTION_MAP = DOCS_DIR / "analysis" / "SEMANTIC_FUNCTION_MAP.md"

SIM_ARTIFACTS_DIR = ARTIFACTS_DIR / "sim" / "current"
REANALYSIS_ARTIFACTS_DIR = ARTIFACTS_DIR / "reanalysis" / "20260214"
GPSIM_XTC_SOURCE_DIR = VENDOR_DIR / "gpsim-0.32.1-xtc"
GPSIM_XTC_ARTIFACTS_DIR = TOOLS_ARTIFACTS_DIR / "gpsim-xtc"
GPSIM_XTC_BUILD_DIR = GPSIM_XTC_ARTIFACTS_DIR / "build"
GPSIM_XTC_BIN_DIR = SCRIPTS_DIR
GPSIM_XTC_BINARY = GPSIM_XTC_BIN_DIR / "gpsim-xtc"
GPSIM_XTC_COMPAT_BINARY = GPSIM_XTC_BIN_DIR / "gpsim"
GPSIM_XTC_BUILD_BINARY = GPSIM_XTC_BUILD_DIR / "gpsim" / "gpsim"
GPSIM_XTC_MODULE_DIR = GPSIM_XTC_BUILD_DIR / "modules" / ".libs"
