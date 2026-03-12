from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.main_gpsim import MAIN_AN0_BOOT_EXIT_ADDR, probe_main_an0_boot_exit_cycle

MAIN_AN0_BOOT_EXIT_CYCLE = 4_061_516


@pytest.mark.gpsim
@pytest.mark.parametrize(
    "fixture_name",
    ["stock_main_hex", "patched_main_hex"],
    ids=["stock_v23", "patched_v25"],
)
def test_main_boot_gate_exits_with_real_an0_stimulus(
    fixture_name: str,
    request: pytest.FixtureRequest,
) -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")

    main_hex = request.getfixturevalue(fixture_name)
    cycle = probe_main_an0_boot_exit_cycle(main_hex)
    assert MAIN_AN0_BOOT_EXIT_ADDR == 0x2DC8
    assert cycle == MAIN_AN0_BOOT_EXIT_CYCLE
