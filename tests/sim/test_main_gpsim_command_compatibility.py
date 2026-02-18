"""gpsim regression tests for MAIN legacy command compatibility.

These tests compare stock vs patched MAIN firmware behavior for existing
commands that must remain compatible after adding preset command 0x20.
"""

from __future__ import annotations

from pathlib import Path
import shutil

import pytest

from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
from dlcp_fw.sim.protocol import SerialFrame


ROOT = Path(__file__).resolve().parent.parent.parent
STOCK_MAIN_HEX = ROOT / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex"


def _require_gpsim() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")


def _run_single(main_hex: Path, *, cmd: int, data: int):
    return run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=main_hex,
        cycles=120_000_000,
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd_0x1d_backlight_timeout_matches_stock(patched_main_hex: Path) -> None:
    """Legacy cmd=0x1D semantics must remain unchanged."""
    _require_gpsim()
    if not STOCK_MAIN_HEX.exists():
        raise RuntimeError(f"missing stock main HEX: {STOCK_MAIN_HEX}")

    data = 0x07
    stock = _run_single(STOCK_MAIN_HEX, cmd=0x1D, data=data)
    patched = _run_single(patched_main_hex, cmd=0x1D, data=data)

    assert stock.parser_break_hit is True
    assert patched.parser_break_hit is True

    stock_timeout = stock.regs.get(0x0B8, 0xFF)
    patched_timeout = patched.regs.get(0x0B8, 0xFF)

    assert stock_timeout == data, (
        f"stock baseline changed unexpectedly for cmd 0x1D: "
        f"expected 0x{data:02X}, got 0x{stock_timeout:02X}"
    )
    assert patched_timeout == stock_timeout, (
        f"patched cmd 0x1D mismatch vs stock: "
        f"stock 0x0B8=0x{stock_timeout:02X}, patched 0x0B8=0x{patched_timeout:02X}"
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd_0x1e_link_address_matches_stock(patched_main_hex: Path) -> None:
    """Legacy cmd=0x1E semantics must remain unchanged."""
    _require_gpsim()
    if not STOCK_MAIN_HEX.exists():
        raise RuntimeError(f"missing stock main HEX: {STOCK_MAIN_HEX}")

    data = 0x07
    stock = _run_single(STOCK_MAIN_HEX, cmd=0x1E, data=data)
    patched = _run_single(patched_main_hex, cmd=0x1E, data=data)

    assert stock.parser_break_hit is True
    assert patched.parser_break_hit is True

    stock_b2 = stock.regs.get(0x0B2, 0xFF)
    stock_c3 = stock.regs.get(0x0C3, 0xFF)
    patched_b2 = patched.regs.get(0x0B2, 0xFF)
    patched_c3 = patched.regs.get(0x0C3, 0xFF)

    assert stock_b2 == data, (
        f"stock baseline changed unexpectedly for cmd 0x1E: "
        f"expected 0x0B2=0x{data:02X}, got 0x{stock_b2:02X}"
    )
    assert stock_c3 == data, (
        f"stock baseline changed unexpectedly for cmd 0x1E: "
        f"expected 0x0C3=0x{data:02X}, got 0x{stock_c3:02X}"
    )
    assert patched_b2 == stock_b2, (
        f"patched cmd 0x1E mismatch vs stock at 0x0B2: "
        f"stock=0x{stock_b2:02X}, patched=0x{patched_b2:02X}"
    )
    assert patched_c3 == stock_c3, (
        f"patched cmd 0x1E mismatch vs stock at 0x0C3: "
        f"stock=0x{stock_c3:02X}, patched=0x{patched_c3:02X}"
    )
