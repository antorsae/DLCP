"""Expanded edge-case stock-vs-patched compatibility checks for MAIN commands."""

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


def _run_one(main_hex: Path, *, route: int, cmd: int, data: int):
    return run_main_mailbox_gpsim(
        frames=[SerialFrame(route=route, cmd=cmd, data=data)],
        main_hex=main_hex,
        cycles=120_000_000,
    )


def _reg_subset(res, regs: tuple[int, ...]) -> dict[int, int]:
    return {addr: res.regs.get(addr, 0xFF) for addr in regs}


VOL_REGS = (0x066, 0x067, 0x068, 0x069, 0x06E, 0x06F, 0x070, 0x071)


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("route", "cmd", "data", "label", "check_regs"),
    [
        (0xB0, 0x03, 0xFF, "cmd03_out_of_range_data", (0x05E,)),
        (0xB0, 0x06, 0x00, "cmd06_input_min", (0x099, 0x0B3)),
        (0xB0, 0x06, 0x08, "cmd06_input_max", (0x099, 0x0B3)),
        (0xB0, 0x07, 0x00, "cmd07_volume_min", VOL_REGS),
        (0xB0, 0x07, 0x72, "cmd07_volume_max", VOL_REGS),
        (0xB0, 0x1D, 0x00, "cmd1d_timeout_min", (0x0B8,)),
        (0xB0, 0x1D, 0x0F, "cmd1d_timeout_high", (0x0B8,)),
        (0xB1, 0x1D, 0x07, "cmd1d_route_unit1", (0x0B8,)),
        (0xB2, 0x1D, 0x07, "cmd1d_route_unit2", (0x0B8,)),
        (0xB0, 0x1E, 0x00, "cmd1e_link_min", (0x0B2, 0x0C3)),
        (0xB0, 0x1E, 0x0F, "cmd1e_link_high", (0x0B2, 0x0C3)),
        (0xB1, 0x1E, 0x02, "cmd1e_route_unit1", (0x0B2, 0x0C3)),
        (0xB2, 0x1E, 0x02, "cmd1e_route_unit2", (0x0B2, 0x0C3)),
    ],
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_main_edge_cases_match_stock(
    patched_main_hex: Path,
    route: int,
    cmd: int,
    data: int,
    label: str,
    check_regs: tuple[int, ...],
) -> None:
    del label
    _require_gpsim()
    if not STOCK_MAIN_HEX.exists():
        raise RuntimeError(f"missing stock main HEX: {STOCK_MAIN_HEX}")

    stock = _run_one(STOCK_MAIN_HEX, route=route, cmd=cmd, data=data)
    patched = _run_one(patched_main_hex, route=route, cmd=cmd, data=data)

    assert stock.parser_break_hit is True
    assert patched.parser_break_hit is True

    assert stock.regs.get(0x7C0) == 3
    assert stock.regs.get(0x7C1) == 3
    assert patched.regs.get(0x7C0) == stock.regs.get(0x7C0)
    assert patched.regs.get(0x7C1) == stock.regs.get(0x7C1)
    assert patched.regs.get(0x7C3) == stock.regs.get(0x7C3)

    assert patched.tx_bytes == stock.tx_bytes
    assert _reg_subset(patched, check_regs) == _reg_subset(stock, check_regs)
