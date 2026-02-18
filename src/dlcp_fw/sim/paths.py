"""Backward-compatible path aliases for simulation tooling."""

from __future__ import annotations

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX as CONTROL_HEX_PATCHED,
    PATCHED_MAIN_HEX as MAIN_HEX_PATCHED,
    PROJECT_ROOT as ANALYSIS_ROOT,
    SIM_ARTIFACTS_DIR,
    STOCK_CONTROL_HEX_V14 as CONTROL_HEX_STOCK,
)

__all__ = [
    "ANALYSIS_ROOT",
    "MAIN_HEX_PATCHED",
    "CONTROL_HEX_PATCHED",
    "CONTROL_HEX_STOCK",
    "SIM_ARTIFACTS_DIR",
]
