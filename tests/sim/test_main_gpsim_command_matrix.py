"""Exhaustive stock-vs-patched compatibility checks for original MAIN commands."""

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


def _run_one(main_hex: Path, *, cmd: int, data: int):
    return run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=main_hex,
        cycles=120_000_000,
    )


def _reg_subset(res, regs: tuple[int, ...]) -> dict[int, int]:
    return {addr: res.regs.get(addr, 0xFF) for addr in regs}


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("cmd", "data", "label", "check_regs"),
    [
        (0x03, 0x00, "cmd03_standby_off", (0x05E,)),
        (0x03, 0x01, "cmd03_standby_on", (0x05E,)),
        (0x03, 0x02, "cmd03_mute_on", (0x05E,)),
        (0x03, 0x03, "cmd03_mute_off", (0x05E,)),
        (0x04, 0x00, "cmd04_status_request", ()),
        (0x06, 0x02, "cmd06_set_source", (0x099, 0x0B3)),
        (0x07, 0x45, "cmd07_set_volume", (0x066, 0x067, 0x068, 0x069, 0x06E, 0x06F, 0x070, 0x071)),
        (0x10, 0x29, "cmd10_query_standby", ()),
        (0x17, 0x01, "cmd17_ch1_source", (0x0A5,)),
        (0x18, 0x02, "cmd18_ch2_source", (0x0A6,)),
        (0x19, 0x03, "cmd19_ch3_source", (0x0A7,)),
        (0x1A, 0x01, "cmd1a_ch4_source", (0x0A8,)),
        (0x1B, 0x02, "cmd1b_ch5_source", (0x0A9,)),
        (0x1C, 0x03, "cmd1c_ch6_source", (0x0AA,)),
        (0x1D, 0x07, "cmd1d_backlight_timeout", (0x0B8,)),
        (0x1E, 0x07, "cmd1e_link_address", (0x0B2, 0x0C3)),
    ],
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_original_main_command_matrix_matches_stock(
    patched_main_hex: Path,
    cmd: int,
    data: int,
    label: str,
    check_regs: tuple[int, ...],
) -> None:
    """Every original command must preserve stock behavior after patching."""
    del label  # only used for readable param ids
    _require_gpsim()
    if not STOCK_MAIN_HEX.exists():
        raise RuntimeError(f"missing stock main HEX: {STOCK_MAIN_HEX}")

    stock = _run_one(STOCK_MAIN_HEX, cmd=cmd, data=data)
    patched = _run_one(patched_main_hex, cmd=cmd, data=data)

    assert stock.parser_break_hit is True
    assert patched.parser_break_hit is True

    # Mailbox bookkeeping must remain identical.
    assert stock.regs.get(0x7C0) == 3
    assert stock.regs.get(0x7C1) == 3
    assert patched.regs.get(0x7C0) == stock.regs.get(0x7C0)
    assert patched.regs.get(0x7C1) == stock.regs.get(0x7C1)
    assert patched.regs.get(0x7C3) == stock.regs.get(0x7C3)

    # Reply stream and side-effect registers must match stock semantics.
    assert patched.tx_bytes == stock.tx_bytes
    assert _reg_subset(patched, check_regs) == _reg_subset(stock, check_regs)
