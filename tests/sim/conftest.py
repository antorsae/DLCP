from __future__ import annotations

from pathlib import Path
import sys

import pytest


ROOT = Path(__file__).resolve().parent.parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PATCHED_MAIN = ROOT / "firmware" / "patched" / "releases" / "DLCP_Firmware_V2.4.hex"
PATCHED_CONTROL = ROOT / "firmware" / "patched" / "releases" / "DLCP_Control_V1.41.hex"


@pytest.fixture(scope="session")
def patched_main_hex() -> Path:
    if not PATCHED_MAIN.exists():
        raise RuntimeError(f"missing patched main HEX: {PATCHED_MAIN}")
    return PATCHED_MAIN


@pytest.fixture(scope="session")
def patched_control_hex() -> Path:
    if not PATCHED_CONTROL.exists():
        raise RuntimeError(f"missing patched control HEX: {PATCHED_CONTROL}")
    return PATCHED_CONTROL
