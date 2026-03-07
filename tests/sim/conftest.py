from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX,
    PATCHED_CONTROL_HEX_V151B,
    PATCHED_CONTROL_HEX_V161B,
    PATCHED_MAIN_HEX,
)


@pytest.fixture(scope="session")
def patched_main_hex() -> Path:
    if not PATCHED_MAIN_HEX.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN_HEX}")
    return PATCHED_MAIN_HEX


@pytest.fixture(scope="session")
def patched_control_hex() -> Path:
    if not PATCHED_CONTROL_HEX.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX}")
    return PATCHED_CONTROL_HEX


@pytest.fixture(scope="session")
def patched_control_hex_v151b() -> Path:
    if not PATCHED_CONTROL_HEX_V151B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V151B}")
    return PATCHED_CONTROL_HEX_V151B


@pytest.fixture(scope="session")
def patched_control_hex_v161b() -> Path:
    if not PATCHED_CONTROL_HEX_V161B.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL_HEX_V161B}")
    return PATCHED_CONTROL_HEX_V161B
