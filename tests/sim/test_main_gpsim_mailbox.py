from __future__ import annotations

import shutil

import pytest

from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
from dlcp_fw.sim.protocol import SerialFrame


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_gpsim_consumes_one_frame_and_produces_reply_bytes() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    assert res.parser_break_hit is True
    assert res.regs.get(0x7C1) == 3
    assert res.regs.get(0x7C0) == 3
    assert res.regs.get(0x7C3) == 3


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_gpsim_consumes_two_frames() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")
    res = run_main_mailbox_gpsim(
        frames=[
            SerialFrame(route=0xB0, cmd=0x20, data=0x01),
            SerialFrame(route=0xB0, cmd=0x20, data=0x00),
        ],
        cycles=140_000_000,
    )
    assert res.parser_break_hit is True
    assert res.regs.get(0x7C1) == 6
    assert res.regs.get(0x7C0) == 6
    assert res.regs.get(0x7C3) == 6


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_gpsim_wrong_command_still_consumed_stably() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x21, data=0x01)],
        cycles=120_000_000,
    )
    assert res.parser_break_hit is True
    assert res.regs.get(0x7C1) == 3
    assert res.regs.get(0x7C0) == 3
    assert res.regs.get(0x7C3) == 3
