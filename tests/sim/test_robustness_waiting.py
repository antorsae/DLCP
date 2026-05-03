from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
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


def _lcd_contains_waiting(h: GpsimControlHarness) -> bool:
    l1, l2 = h.lcd_lines()
    text = (l1 + " " + l2).lower()
    return "waiting for dlcp" in text


def _wait_for_waiting(h: GpsimControlHarness, *, limit: int) -> bool:
    for _ in range(limit):
        h.step()
        if _lcd_contains_waiting(h):
            return True
    return False


def _wait_for_connected_clear(h: GpsimControlHarness, *, limit: int) -> bool:
    for _ in range(limit):
        h.step()
        if (h.read_reg(0x01F) & 0x02) == 0:
            return True
    return False


def _lcd_text_lower(lines) -> str:
    return (lines[0] + " " + lines[1]).lower()


def _wait_for_waiting_rust(c, *, limit: int, chunk_tcy: int) -> bool:
    for _ in range(limit):
        c.step_tcy(chunk_tcy)
        if "waiting for dlcp" in _lcd_text_lower(c.lcd_lines()):
            return True
    return False


def _run_v14_no_main_test_gpsim(stock_control_hex_v14: Path) -> tuple[bool, list[str]]:
    h = GpsimControlHarness(
        stock_control_hex_v14,
        fast_boot=False,
        chunk_cycles=300_000,
        hold_cycles=120_000,
        heartbeat_rx_mode="none",
        heartbeat_force_connected=False,
        heartbeat_reset_idle=False,
        disable_standby_check=False,
    )
    try:
        if not _wait_for_waiting(h, limit=120):
            return False, list(h.lcd_lines())
        for _ in range(24):
            h.step()
        return _lcd_contains_waiting(h), list(h.lcd_lines())
    finally:
        h.close()


def _run_v14_no_main_test_rust(stock_control_hex_v14: Path) -> tuple[bool, list[str]]:
    c = RustChain.from_v17_control_only(str(stock_control_hex_v14))
    if not _wait_for_waiting_rust(c, limit=120, chunk_tcy=300_000):
        return False, list(c.lcd_lines())
    # Hold for ~24 chunks worth of cycles to confirm it stays.
    c.step_tcy(24 * 300_000)
    text = _lcd_text_lower(c.lcd_lines())
    return ("waiting for dlcp" in text), list(c.lcd_lines())


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_control_v14_without_main_shows_waiting_on_lcd(
    stock_control_hex_v14: Path,
    dlcp_sim_backend: str,
) -> None:
    """V1.4 stock CONTROL without MAIN: LCD reaches and stays on WAITING."""
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        ok, final_lcd = _run_v14_no_main_test_rust(stock_control_hex_v14)
        assert ok, f"[rust] lcd never stuck on WAITING without MAIN: {final_lcd!r}"
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        ok, final_lcd = _run_v14_no_main_test_gpsim(stock_control_hex_v14)
        assert ok, f"[gpsim] lcd never stuck on WAITING without MAIN: {final_lcd!r}"


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_control_v14_runtime_response_blackout_falls_back_to_waiting(
    stock_control_hex_v14: Path,
) -> None:
    """V1.4 stock CONTROL: after a synthetic-MAIN warmup, pausing
    the heartbeat must drop CONTROL back to WAITING within a
    bounded window.

    Stays gpsim-only.  Two rust paths were tried:
      - `Chain.from_v17_control_only` + `enable_force_connected`
        + `pause_heartbeat`: rust's `pause_heartbeat` is a no-op,
        and `enable_force_connected` keeps applying the
        CONNECTED+DISPLAY hook each chunk indefinitely (no
        `disable_force_connected` primitive exists), so CONTROL
        never sees the absence-of-heartbeat condition.
      - `Chain.from_v17_chain` (real V1.4+V2.3 chain) +
        `set_blackout(True)`: dropping all UART byte traffic
        does NOT clear CONNECTED on rust within a 600-step
        budget (~40 s sim time).  V1.4 stock's no-heartbeat
        timeout under blackout doesn't fire on rust within the
        test budget.
    Migrating this requires either a `disable_force_connected`
    rust facade primitive (Category B-class) or a deeper probe
    of why V1.4's no-heartbeat timeout doesn't fire on rust
    under chain blackout.  Tracked for a future session.
    """
    _require_gpsim()
    h = GpsimControlHarness(
        stock_control_hex_v14,
        fast_boot=True,
        chunk_cycles=200_000,
        hold_cycles=120_000,
        heartbeat_rx_mode="full",
        heartbeat_force_connected=False,
        heartbeat_reset_idle=True,
        disable_standby_check=False,
    )
    try:
        h.warmup(25_000_000)
        assert h.read_reg(0x01F) & 0x02, f"failed to reach DISPLAY mode: flags=0x{h.read_reg(0x01F):02X}"

        h.pause_heartbeat()
        assert _wait_for_connected_clear(h, limit=80), (
            f"CONNECTED bit did not clear after response blackout: flags=0x{h.read_reg(0x01F):02X}"
        )
        assert _lcd_contains_waiting(h), f"lcd did not show WAITING after response blackout: {h.lcd_lines()!r}"
    finally:
        h.close()
