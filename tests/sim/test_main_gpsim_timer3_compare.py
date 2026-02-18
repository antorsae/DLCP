from __future__ import annotations

import shutil

import pytest

from dlcp_fw.sim.main_gpsim_timer3 import compare_timer3_models, run_main_mailbox_gpsim_harness_timer3
from dlcp_fw.sim.protocol import SerialFrame


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_gpsim_harness_timer3_consumes_frame() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")
    res = run_main_mailbox_gpsim_harness_timer3(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    assert res.run.parser_break_hit is True
    assert res.mailbox_consumed is True
    assert len(res.timer3_events) > 0
    assert res.run.regs.get(0x7C1) == 3
    assert res.run.regs.get(0x7C3) == 3
    assert res.run.tx_bytes[:3] == [0xB0, 0x20, 0x01]


@pytest.mark.gpsim
@pytest.mark.slow
def test_compare_timer3_models_match_dispatch_observables() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")
    cmp_res = compare_timer3_models(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    # Both models now converge on REG 0x05E — semantic shim and harness agree.
    assert cmp_res.same_reg5e is True
    assert cmp_res.same_mailbox_counters is True
    assert len(cmp_res.harness.timer3_events) > 0
