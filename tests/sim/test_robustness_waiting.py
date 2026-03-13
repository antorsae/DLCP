from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.gpsim import gpsim_available


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


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


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_control_v14_without_main_shows_waiting_on_lcd(
    stock_control_hex_v14: Path,
) -> None:
    _require_gpsim()
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
        assert _wait_for_waiting(h, limit=120), f"lcd never reached WAITING state: {h.lcd_lines()!r}"

        for _ in range(24):
            h.step()
        assert _lcd_contains_waiting(h), f"lcd did not stay on WAITING without MAIN: {h.lcd_lines()!r}"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_control_v14_runtime_response_blackout_falls_back_to_waiting(
    stock_control_hex_v14: Path,
) -> None:
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
