"""gpsim regression tests for MAIN legacy command compatibility.

These tests compare stock vs patched MAIN firmware behavior for existing
commands that must remain compatible after adding preset command 0x20.

Migrated to dual_supported in P4.7: same shape as
`test_main_gpsim_command_matrix.py` (commit 463c064/1cc305b) -- both
backends independently boot a MAIN-only chain via the native RX ring,
inject the activation frame, then the test frame, snapshot the
firmware-internal RAM at the per-command watch registers, and assert
patched-vs-stock equality.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


_PHASE_TCY = 4_000_000


def _run_command_gpsim(
    main_hex: Path, *, cmd: int, data: int, watch_regs: tuple[int, ...],
) -> dict[int, int]:
    h = MainChainHarness(
        main_hex, chunk_cycles=200_000, standby_mode="hold",
        rc2_mode="low", bypass_i2c=False, transport_mode="native_ring",
    )
    try:
        for _ in range(20):
            h.step()
        h.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            h.step()
        h.inject_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
        for _ in range(20):
            h.step()
        return {r: _read_reg(h._issue, r) for r in watch_regs}
    finally:
        h.close()


def _run_command_rust(
    main_hex: Path, *, cmd: int, data: int, watch_regs: tuple[int, ...],
) -> dict[int, int]:
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)
    chain.inject_main_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    chain.step_tcy(_PHASE_TCY)
    return {r: chain.read_reg(r) for r in watch_regs}


def _run_command(
    main_hex: Path, *, cmd: int, data: int,
    watch_regs: tuple[int, ...], backend: str,
) -> dict[int, int]:
    if backend == "rust":
        return _run_command_rust(main_hex, cmd=cmd, data=data, watch_regs=watch_regs)
    return _run_command_gpsim(main_hex, cmd=cmd, data=data, watch_regs=watch_regs)


def _assert_patched_matches_stock(
    *, backend: str, patched_main_hex: Path, cmd: int, data: int,
    watch_regs: tuple[int, ...],
) -> None:
    stock = _run_command(
        STOCK_MAIN_HEX, cmd=cmd, data=data, watch_regs=watch_regs, backend=backend,
    )
    patched = _run_command(
        patched_main_hex, cmd=cmd, data=data, watch_regs=watch_regs, backend=backend,
    )
    for reg in watch_regs:
        assert patched[reg] == stock[reg], (
            f"[{backend}] cmd=0x{cmd:02X} data=0x{data:02X}: "
            f"reg 0x{reg:03X} patched=0x{patched[reg]:02X} "
            f"stock=0x{stock[reg]:02X}"
        )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd_0x1d_backlight_timeout_matches_stock(
    patched_main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Legacy cmd=0x1D semantics must remain unchanged."""
    if not STOCK_MAIN_HEX.exists():
        pytest.skip(f"missing stock main HEX: {STOCK_MAIN_HEX.name}")
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        _assert_patched_matches_stock(
            backend="rust", patched_main_hex=patched_main_hex,
            cmd=0x1D, data=0x07, watch_regs=(0x0B8,),
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _assert_patched_matches_stock(
            backend="gpsim", patched_main_hex=patched_main_hex,
            cmd=0x1D, data=0x07, watch_regs=(0x0B8,),
        )


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_cmd_0x1e_link_address_matches_stock(
    patched_main_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Legacy cmd=0x1E semantics must remain unchanged."""
    if not STOCK_MAIN_HEX.exists():
        pytest.skip(f"missing stock main HEX: {STOCK_MAIN_HEX.name}")
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        _assert_patched_matches_stock(
            backend="rust", patched_main_hex=patched_main_hex,
            cmd=0x1E, data=0x07, watch_regs=(0x0B2, 0x0C3),
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _assert_patched_matches_stock(
            backend="gpsim", patched_main_hex=patched_main_hex,
            cmd=0x1E, data=0x07, watch_regs=(0x0B2, 0x0C3),
        )
