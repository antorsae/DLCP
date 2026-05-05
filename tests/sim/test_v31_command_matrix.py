"""V3.1 command matrix: every serial command must produce identical
register state as stock V2.3.

Uses the rust MAIN-only chain via `RustChain.from_v3x_main_only`.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX, V31_MAIN_HEX

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


# Per-phase MAIN-Tcy advancement.  Rust advances the total Tcy in
# single `step_tcy` calls -- the universal-clock scheduler runs the
# core in lock-step at instruction granularity.
_PHASE_TCY = 4_000_000


def _run_command(
    main_hex: Path, cmd: int, data: int, watch_regs: tuple[int, ...]
) -> dict[int, int]:
    """Boot the rust MAIN-only chain, send one command, read register state."""
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)

    chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)

    return {r: chain.read_reg(r) for r in watch_regs}


# The 16 original DLCP serial commands and the registers they affect.
_COMMAND_MATRIX = [
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
]


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    ("cmd", "data", "label", "check_regs"),
    _COMMAND_MATRIX,
    ids=[m[2] for m in _COMMAND_MATRIX],
)
def test_v31_command_matches_stock(
    cmd: int,
    data: int,
    label: str,
    check_regs: tuple[int, ...],
) -> None:
    """V3.1 must produce identical register state as stock V2.3 for every
    original serial command."""
    _skip_missing(STOCK_MAIN_HEX, V31_MAIN_HEX)
    stock_regs = _run_command(STOCK_MAIN_HEX, cmd, data, check_regs)
    v31_regs = _run_command(V31_MAIN_HEX, cmd, data, check_regs)
    for reg in check_regs:
        assert v31_regs[reg] == stock_regs[reg], (
            f"Command 0x{cmd:02X} data=0x{data:02X} ({label}): "
            f"reg 0x{reg:03X} V3.1=0x{v31_regs[reg]:02X} "
            f"stock=0x{stock_regs[reg]:02X}"
        )
