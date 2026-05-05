"""Regression tests for MAIN legacy command compatibility.

These tests compare stock vs patched MAIN firmware behavior for existing
commands that must remain compatible after adding preset command 0x20.
Both firmwares boot a MAIN-only rust chain via the native RX ring,
inject the activation frame, then the test frame, snapshot the
firmware-internal RAM at the per-command watch registers, and assert
patched-vs-stock equality.
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


_PHASE_TCY = 4_000_000


def _run_command(
    main_hex: Path, *, cmd: int, data: int, watch_regs: tuple[int, ...],
) -> dict[int, int]:
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)
    return {r: chain.read_reg(r) for r in watch_regs}


def _assert_patched_matches_stock(
    *, patched_main_hex: Path, cmd: int, data: int,
    watch_regs: tuple[int, ...],
) -> None:
    stock = _run_command(
        STOCK_MAIN_HEX, cmd=cmd, data=data, watch_regs=watch_regs,
    )
    patched = _run_command(
        patched_main_hex, cmd=cmd, data=data, watch_regs=watch_regs,
    )
    for reg in watch_regs:
        assert patched[reg] == stock[reg], (
            f"cmd=0x{cmd:02X} data=0x{data:02X}: "
            f"reg 0x{reg:03X} patched=0x{patched[reg]:02X} "
            f"stock=0x{stock[reg]:02X}"
        )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_cmd_0x1d_backlight_timeout_matches_stock(patched_main_hex: Path) -> None:
    """Legacy cmd=0x1D semantics must remain unchanged."""
    if not STOCK_MAIN_HEX.exists():
        pytest.skip(f"missing stock main HEX: {STOCK_MAIN_HEX.name}")
    _assert_patched_matches_stock(
        patched_main_hex=patched_main_hex,
        cmd=0x1D, data=0x07, watch_regs=(0x0B8,),
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_cmd_0x1e_link_address_matches_stock(patched_main_hex: Path) -> None:
    """Legacy cmd=0x1E semantics must remain unchanged."""
    if not STOCK_MAIN_HEX.exists():
        pytest.skip(f"missing stock main HEX: {STOCK_MAIN_HEX.name}")
    _assert_patched_matches_stock(
        patched_main_hex=patched_main_hex,
        cmd=0x1E, data=0x07, watch_regs=(0x0B2, 0x0C3),
    )
