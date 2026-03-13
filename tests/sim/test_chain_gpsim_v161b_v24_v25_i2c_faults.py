from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import PATCHED_MAIN_HEX, PATCHED_MAIN_HEX_V24
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
        enable_main_timeout_test_hooks=False,
    )


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v161b_v24"),
        pytest.param(PATCHED_MAIN_HEX, id="v161b_v25"),
    ],
)
def test_v161b_wake_cfg71_address_stretch_fault_is_shared_external_i2c_stressor(
    patched_control_hex_v161b: Path,
    main_hex: Path,
) -> None:
    """
    Characterization of a shared external-bus fault:

    - the same cfg71 address-phase SCL stretch is injected into both V2.4 and
      V2.5 during wake/reconnect
    - both pairs fall into WAITING while the external I2C fault is active
    - both pairs reconnect once the same external fault is cleared

    This gives us a hardware-style I2C stress path without version-specific
    helper hooks, but it does not yet reproduce the real-world V2.4-only
    stranded WAITING symptom.
    """
    _require_gpsim()
    pair = _new_pair(patched_control_hex_v161b, main_hex)
    try:
        first = pair.run_until_connected(limit=180)
        assert first is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected before external I2C fault: lcd={first.lcd!r}"

        pair.press("STBY")
        pair.step_many(60)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {pair.lcd_lines()!r}"

        pair.set_main_i2c_fault("cfg71", address_stretch_scl_cycles=50_000_000)
        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=30)
        assert waiting is not None, "pair produced no steps while waiting for reconnect"
        assert pair.is_waiting(), f"pair did not enter WAITING under shared external I2C fault: {waiting.lcd!r}"

        pair.clear_main_i2c_faults("cfg71")
        recovered = pair.run_until_connected(limit=180)
        assert recovered is not None, "pair produced no steps after clearing external I2C fault"
        assert pair.is_connected(), f"pair never reconnected after external I2C fault cleared: {recovered.lcd!r}"
        assert not pair.is_waiting(), f"pair stayed in WAITING after external I2C fault cleared: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered lcd after external I2C fault: {recovered.lcd!r}"
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v161b_v24"),
        pytest.param(PATCHED_MAIN_HEX, id="v161b_v25"),
    ],
)
def test_v161b_wake_cfg71_data_nack_fault_is_shared_external_i2c_stressor(
    patched_control_hex_v161b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_pair(patched_control_hex_v161b, main_hex)
    try:
        first = pair.run_until_connected(limit=180)
        assert first is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected before external I2C fault: lcd={first.lcd!r}"

        pair.press("STBY")
        pair.step_many(60)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {pair.lcd_lines()!r}"

        pair.set_main_i2c_fault("cfg71", data_nack_count=4096)
        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=30)
        assert waiting is not None, "pair produced no steps while waiting for reconnect"
        assert pair.is_waiting(), f"pair did not enter WAITING under shared data-phase NACK fault: {waiting.lcd!r}"

        pair.clear_main_i2c_faults("cfg71")
        recovered = pair.run_until_connected(limit=180)
        assert recovered is not None, "pair produced no steps after clearing data-phase NACK fault"
        assert pair.is_connected(), f"pair never reconnected after data-phase NACK fault cleared: {recovered.lcd!r}"
        assert not pair.is_waiting(), f"pair stayed in WAITING after data-phase NACK fault cleared: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered lcd after data-phase NACK fault: {recovered.lcd!r}"
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v161b_v24"),
        pytest.param(PATCHED_MAIN_HEX, id="v161b_v25"),
    ],
)
def test_v161b_wake_cfg71_data_stuck_sda_fault_is_shared_external_i2c_stressor(
    patched_control_hex_v161b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    pair = _new_pair(patched_control_hex_v161b, main_hex)
    try:
        first = pair.run_until_connected(limit=180)
        assert first is not None, "pair never produced a step result"
        assert pair.is_connected(), f"pair never connected before external I2C fault: lcd={first.lcd!r}"

        pair.press("STBY")
        pair.step_many(60)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {pair.lcd_lines()!r}"

        pair.set_main_i2c_fault("cfg71", data_stuck_sda_cycles=20_000_000)
        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=30)
        assert waiting is not None, "pair produced no steps while waiting for reconnect"
        assert pair.is_waiting(), f"pair did not enter WAITING under shared SDA-stuck fault: {waiting.lcd!r}"

        pair.clear_main_i2c_faults("cfg71")
        recovered = pair.run_until_connected(limit=240)
        assert recovered is not None, "pair produced no steps after arming bounded SDA-stuck fault"
        assert pair.is_connected(), f"pair never reconnected after bounded SDA-stuck fault: {recovered.lcd!r}"
        assert not pair.is_waiting(), f"pair stayed in WAITING after bounded SDA-stuck fault: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered lcd after bounded SDA-stuck fault: {recovered.lcd!r}"
    finally:
        pair.close()
