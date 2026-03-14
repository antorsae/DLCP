from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.main_gpsim import MAIN_AN0_BOOT_EXIT_ADDR, probe_main_an0_boot_exit_cycle

STOCK_MAIN_AN0_BOOT_EXIT_CYCLE = 4_061_516
PATCHED_MAIN_AN0_BOOT_EXIT_CYCLE = 4_061_234


@pytest.mark.gpsim
@pytest.mark.parametrize(
    ("fixture_name", "expected_cycle"),
    [
        pytest.param("stock_main_hex", STOCK_MAIN_AN0_BOOT_EXIT_CYCLE, id="stock_v23"),
        pytest.param("patched_main_hex_v24", PATCHED_MAIN_AN0_BOOT_EXIT_CYCLE, id="patched_v24"),
        pytest.param("patched_main_hex", PATCHED_MAIN_AN0_BOOT_EXIT_CYCLE, id="patched_v25"),
    ],
)
def test_main_boot_gate_exits_with_real_an0_stimulus(
    fixture_name: str,
    expected_cycle: int,
    request: pytest.FixtureRequest,
) -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")

    main_hex = request.getfixturevalue(fixture_name)
    cycle = probe_main_an0_boot_exit_cycle(main_hex)
    assert MAIN_AN0_BOOT_EXIT_ADDR == 0x2DC8
    assert cycle == expected_cycle
