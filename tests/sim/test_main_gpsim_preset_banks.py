"""gpsim-level tests for MAIN preset-command mailbox handling.

These tests keep the gpsim mailbox harness focused on observables it proves
reliably today: parser progress, echoed reply bytes, mailbox counters, and
broadcast routing. Bank-selection semantics are covered separately in
``test_main_model_banking.py``.
"""

from __future__ import annotations

import pytest

from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
from dlcp_fw.sim.protocol import SerialFrame


def _require_gpsim():
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _assert_mailbox_exchange(res, *, tx_bytes: list[int], consumed_bytes: int) -> None:
    assert res.parser_break_hit is True
    assert res.tx_bytes == tx_bytes
    assert res.regs.get(0x7C0) == consumed_bytes
    assert res.regs.get(0x7C1) == consumed_bytes
    assert res.regs.get(0x7C3) == len(tx_bytes)


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_a_mailbox_reply() -> None:
    """cmd=0x20 data=0 -> mailbox reply echoes preset A selection."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x00)],
        cycles=120_000_000,
    )
    _assert_mailbox_exchange(res, tx_bytes=[0xB0, 0x20, 0x00], consumed_bytes=3)


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_b_mailbox_reply() -> None:
    """cmd=0x20 data=1 -> mailbox reply echoes preset B selection."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    _assert_mailbox_exchange(res, tx_bytes=[0xB0, 0x20, 0x01], consumed_bytes=3)


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_switch_ab_mailbox_sequence() -> None:
    """Set B then A -> both frames are consumed and echoed in order."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[
            SerialFrame(route=0xB0, cmd=0x20, data=0x01),  # B
            SerialFrame(route=0xB0, cmd=0x20, data=0x00),  # A
        ],
        cycles=140_000_000,
    )
    _assert_mailbox_exchange(
        res,
        tx_bytes=[0xB0, 0x20, 0x01, 0xB0, 0x20, 0x00],
        consumed_bytes=6,
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_broadcast_reaches_unit() -> None:
    """route=0xB0 is consumed by unit (broadcast addressing)."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    _assert_mailbox_exchange(res, tx_bytes=[0xB0, 0x20, 0x01], consumed_bytes=3)
