"""Expanded edge-case stock-vs-patched compatibility checks for MAIN commands.

Each parametrized case picks a (route, cmd, data) frame and asserts that
patched MAIN (V2.7 by default via the `patched_main_hex` fixture) produces
the same firmware-internal RAM as stock V2.3 for the registers that the
command is supposed to touch.

Both firmwares boot a MAIN-only rust chain via the native RX ring, inject
the activation frame, then the test frame, and snapshot the watch_regs
subset.  The stock-vs-patched equality is a firmware invariant.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


_PHASE_TCY = 4_000_000


def _run_command(
    main_hex: Path,
    *,
    route: int,
    cmd: int,
    data: int,
    watch_regs: tuple[int, ...],
) -> dict[int, int]:
    """Boot the rust MAIN-only chain, send activation + test frame on
    the native RX ring, snapshot watch_regs."""
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)

    chain.inject_main_frames_fifo([[route, cmd, data]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)

    return {r: chain.read_reg(r) for r in watch_regs}


VOL_REGS = (0x066, 0x067, 0x068, 0x069, 0x06E, 0x06F, 0x070, 0x071)


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("route", "cmd", "data", "label", "check_regs"),
    [
        (0xB0, 0x03, 0xFF, "cmd03_out_of_range_data", (0x05E,)),
        (0xB0, 0x06, 0x00, "cmd06_input_min", (0x099, 0x0B3)),
        (0xB0, 0x06, 0x08, "cmd06_input_max", (0x099, 0x0B3)),
        (0xB0, 0x07, 0x00, "cmd07_volume_min", VOL_REGS),
        (0xB0, 0x07, 0x72, "cmd07_volume_max", VOL_REGS),
        (0xB1, 0x17, 0x03, "cmd17_route_unit1", (0x0A5,)),
        (0xB2, 0x17, 0x03, "cmd17_route_unit2", (0x0A5,)),
        (0xB1, 0x18, 0x03, "cmd18_route_unit1", (0x0A6,)),
        (0xB2, 0x18, 0x03, "cmd18_route_unit2", (0x0A6,)),
        (0xB1, 0x19, 0x03, "cmd19_route_unit1", (0x0A7,)),
        (0xB2, 0x19, 0x03, "cmd19_route_unit2", (0x0A7,)),
        (0xB1, 0x1A, 0x03, "cmd1a_route_unit1", (0x0A8,)),
        (0xB2, 0x1A, 0x03, "cmd1a_route_unit2", (0x0A8,)),
        (0xB1, 0x1B, 0x03, "cmd1b_route_unit1", (0x0A9,)),
        (0xB2, 0x1B, 0x03, "cmd1b_route_unit2", (0x0A9,)),
        (0xB1, 0x1C, 0x03, "cmd1c_route_unit1", (0x0AA,)),
        (0xB2, 0x1C, 0x03, "cmd1c_route_unit2", (0x0AA,)),
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
    """Patched MAIN must produce identical register state as stock V2.3
    for every (route, cmd, data) edge case the legacy compatibility
    suite covers."""
    del label
    _skip_missing(STOCK_MAIN_HEX, patched_main_hex)
    stock = _run_command(
        STOCK_MAIN_HEX, route=route, cmd=cmd, data=data,
        watch_regs=check_regs,
    )
    patched = _run_command(
        patched_main_hex, route=route, cmd=cmd, data=data,
        watch_regs=check_regs,
    )
    for reg in check_regs:
        assert patched[reg] == stock[reg], (
            f"route=0x{route:02X} cmd=0x{cmd:02X} data=0x{data:02X}: "
            f"reg 0x{reg:03X} patched=0x{patched[reg]:02X} "
            f"stock=0x{stock[reg]:02X}"
        )
