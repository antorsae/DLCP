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
        enable_main_timeout_test_hooks=True,
    )


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("main_fixture", "expect_recovery"),
    [
        pytest.param("patched_main_hex_v24", False, id="v141_v24"),
        pytest.param("patched_main_hex", True, id="v141_v25"),
    ],
)
def test_v141_wake_uart_helper_fault_separates_v24_from_v25(
    request: pytest.FixtureRequest,
    patched_control_hex_v141: Path,
    main_fixture: str,
    expect_recovery: bool,
) -> None:
    """
    Comparison harness:

    - V2.4 uses a simulation-only clearable stall hook at the stock helper.
    - V2.5 uses the existing timeout-entry seed hook and exercises the real
      timeout/recovery wrapper.

    Both pairs are driven through the same V1.41 wake/reconnect scenario.
    """
    _require_gpsim()
    main_hex = request.getfixturevalue(main_fixture)
    pair = _new_pair(patched_control_hex_v141, main_hex)
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

        if expect_recovery:
            assert pair.is_connected(), f"pair never reconnected after wake fault cleared: {recovered.lcd!r}"
            assert not pair.is_waiting(), f"pair stayed in WAITING after wake fault cleared: {recovered.lcd!r}"
            assert "Volume:" in recovered.lcd[0], f"unexpected recovered lcd after wake fault: {recovered.lcd!r}"
        else:
            assert not pair.is_connected(), f"V2.4 unexpectedly reconnected in comparison harness: {recovered.lcd!r}"
            assert pair.is_waiting(), f"V2.4 left WAITING unexpectedly in comparison harness: {recovered.lcd!r}"
    finally:
        pair.close()
