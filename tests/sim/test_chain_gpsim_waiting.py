from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness
from dlcp_fw.sim.gpsim import gpsim_available


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _new_pair(control_hex: Path, main_hex: Path) -> SingleMainChainHarness:
    return SingleMainChainHarness(
        control_hex,
        main_hex,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_single_main_chain_reaches_display(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_pair(stock_control_hex_v14, stock_main_hex)
    try:
        assert pair.main.uses_adc_boot_wait_hook is False
        last = pair.run_until_connected(limit=140)
        assert last is not None, "pair never produced a step result"
        assert last.main.transport_mode == "native_ring"
        assert pair.is_connected(), f"pair never connected; lcd={last.lcd!r} flags=0x{last.control_flags:02X}"
        assert not pair.is_waiting(), f"pair stayed in WAITING after connect; lcd={last.lcd!r}"
        assert "Volume:" in last.lcd[0], f"unexpected post-connect lcd: {last.lcd!r}"
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_chain_attaches_default_external_i2c_bus(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_pair(stock_control_hex_v14, stock_main_hex)
    try:
        assert pair.main.uses_external_i2c_regfile_bus is True
        assert pair.main.read_i2c_regfile("cfg71", 0x00) == 0x00
        assert pair.main.read_i2c_regfile("dsp34", 0x00) == 0x00
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_single_main_blackout_on_wake_shows_waiting(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_pair(stock_control_hex_v14, stock_main_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected; lcd={last.lcd!r} flags=0x{last.control_flags:02X}"

        pair.set_blackout(True)
        pair.press("STBY")
        pair.step_many(80)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {pair.lcd_lines()!r}"

        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=20)
        assert waiting is not None, "pair produced no steps while waiting for reconnect"
        assert pair.is_waiting(), f"pair did not fall back to WAITING after wake blackout: {waiting.lcd!r}"
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_blackout_drops_link_but_main_keeps_running(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_pair(stock_control_hex_v14, stock_main_hex)
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected; lcd={last.lcd!r} flags=0x{last.control_flags:02X}"

        pair.set_blackout(True)
        step1 = pair.step()
        step2 = pair.step()

        assert step1.main.cycle > last.main.cycle
        assert step2.main.cycle > step1.main.cycle
        assert step1.main.transport_mode == step2.main.transport_mode
    finally:
        pair.close()
