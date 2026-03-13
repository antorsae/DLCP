from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import PATCHED_MAIN_HEX_V24, PATCHED_MAIN_HEX_V25
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _new_wire_chain(control_hex: Path, main_hex: Path) -> WireMultiMainChainHarness:
    return WireMultiMainChainHarness(
        control_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )


def _enter_standby(chain: WireMultiMainChainHarness) -> None:
    chain.press("STBY")
    chain.step_many(20)
    assert "ZZZ" in chain.lcd_lines()[0].upper(), f"pair did not enter standby before wake: {chain.lcd_lines()!r}"


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v161b_v24"),
        pytest.param(PATCHED_MAIN_HEX_V25, id="v161b_v25"),
    ],
)
def test_wire_v161b_one_shot_cfg71_address_stretch_strands_both_main_versions(
    patched_control_hex_v161b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_wire_chain(patched_control_hex_v161b, main_hex)
    try:
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY before one-shot wake I2C fault"

        _enter_standby(chain)

        chain.set_main_i2c_fault(
            "cfg71",
            address_stretch_scl_cycles=35_000,
            address_stretch_count=1,
        )
        chain.press("STBY")
        held = chain.run_until_waiting(limit=8)
        assert held is not None, "pair produced no steps during one-shot wake I2C fault"
        assert chain.is_waiting(), f"pair never entered WAITING under one-shot wake I2C fault: {held.lcd!r}"

        recovered = chain.run_until_connected(limit=32)
        assert recovered is not None, "pair produced no steps after one-shot wake I2C fault"
        assert not chain.is_connected(), f"pair unexpectedly reconnected after one-shot wake I2C fault: {recovered.lcd!r}"
        assert chain.is_waiting(), f"pair left WAITING after one-shot wake I2C fault: {recovered.lcd!r}"
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex",
    [
        pytest.param(PATCHED_MAIN_HEX_V24, id="v162b_v24"),
        pytest.param(PATCHED_MAIN_HEX_V25, id="v162b_v25"),
    ],
)
def test_wire_v162b_one_shot_cfg71_address_stretch_recovers_both_main_versions(
    patched_control_hex_v162b: Path,
    main_hex: Path,
) -> None:
    _require_gpsim()
    chain = _new_wire_chain(patched_control_hex_v162b, main_hex)
    try:
        first = chain.run_until_connected(limit=60)
        assert first is not None, "pair never reached DISPLAY before one-shot wake I2C fault"

        _enter_standby(chain)

        chain.set_main_i2c_fault(
            "cfg71",
            address_stretch_scl_cycles=500_000,
            address_stretch_count=1,
        )
        chain.press("STBY")
        held = chain.run_until_waiting(limit=8)
        assert held is not None, "pair produced no steps during one-shot wake I2C fault"
        assert chain.is_waiting(), f"pair never entered WAITING under one-shot wake I2C fault: {held.lcd!r}"

        recovered = chain.run_until_connected(limit=32)
        assert recovered is not None, "pair produced no steps after one-shot wake I2C fault"
        assert chain.is_connected(), f"pair never reconnected after one-shot wake I2C fault: {recovered.lcd!r}"
        assert not chain.is_waiting(), f"pair stayed in WAITING after one-shot wake I2C fault: {recovered.lcd!r}"
        assert "Volume:" in recovered.lcd[0], f"unexpected recovered LCD after one-shot wake I2C fault: {recovered.lcd!r}"
    finally:
        chain.close()
