from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness
from dlcp_fw.sim.gpsim import gpsim_available


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _new_v25_pair(control_hex: Path, main_hex: Path) -> SingleMainChainHarness:
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
        enable_main_timeout_test_hooks=True,
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_v25_v161b_native_ring_chain_reaches_display(
    patched_control_hex_v161b: Path,
    patched_main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_v25_pair(patched_control_hex_v161b, patched_main_hex)
    try:
        assert pair.main.uses_adc_boot_wait_hook is False
        last = pair.run_until_connected(limit=180)
        assert last is not None, "pair never produced a step result"
        assert last.main.transport_mode == "native_ring"
        assert pair.is_connected(), f"pair never connected; lcd={last.lcd!r} flags=0x{last.control_flags:02X}"
        assert not pair.is_waiting(), f"pair stayed in WAITING after connect; lcd={last.lcd!r}"
        assert "Volume:" in last.lcd[0], f"unexpected post-connect lcd: {last.lcd!r}"
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "fault_kwargs",
    [
        pytest.param({"uart_tx_stall": True}, id="uart_timeout"),
        pytest.param({"mssp_wait_stall": True}, id="mssp_timeout"),
    ],
)
def test_v25_v161b_runtime_timeout_fault_recovers_without_waiting(
    patched_control_hex_v161b: Path,
    patched_main_hex: Path,
    fault_kwargs: dict[str, bool],
) -> None:
    _require_gpsim()
    pair = _new_v25_pair(patched_control_hex_v161b, patched_main_hex)
    try:
        first = pair.run_until_connected(limit=180)
        assert first is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected before fault: lcd={first.lcd!r}"

        pair.set_main_fault_flags(**fault_kwargs)
        pair.press("UP")
        pair.step_many(10)
        pair.clear_main_fault_flags()

        recovered = pair.run_until_connected(limit=120)
        assert recovered is not None, "pair produced no steps during recovery"
        assert pair.is_connected(), f"pair disconnected after transient timeout fault: lcd={recovered.lcd!r}"
        assert not pair.is_waiting(), f"pair fell into WAITING after transient timeout fault: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered lcd: {recovered.lcd!r}"
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v25_v161b_wake_uart_timeout_fault_recovers_after_fault_clear(
    patched_control_hex_v161b: Path,
    patched_main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_v25_pair(patched_control_hex_v161b, patched_main_hex)
    try:
        first = pair.run_until_connected(limit=180)
        assert first is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected before fault: lcd={first.lcd!r}"

        pair.set_main_fault_flags(uart_tx_stall=True)
        pair.press("STBY")
        pair.step_many(60)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {pair.lcd_lines()!r}"

        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=20)
        assert waiting is not None, "pair produced no steps while waiting for reconnect"
        assert pair.is_waiting(), f"pair did not fall back to WAITING after wake fault: {waiting.lcd!r}"

        pair.clear_main_fault_flags()
        recovered = pair.run_until_connected(limit=180)
        assert recovered is not None, "pair produced no steps after clearing wake fault"
        assert pair.is_connected(), f"pair never reconnected after wake fault cleared: {recovered.lcd!r}"
        assert not pair.is_waiting(), f"pair stayed in WAITING after wake fault cleared: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered lcd after wake fault: {recovered.lcd!r}"
    finally:
        pair.close()
