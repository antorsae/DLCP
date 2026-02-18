"""gpsim-level tests for MAIN firmware preset bank targeting.

Verifies that the preset command (0x20) correctly sets/clears bit2 of
register 0x05E to select bank A or B.

Uses the existing ``run_main_mailbox_gpsim()`` harness from ``dlcp_fw.sim/main_gpsim.py``.
"""

from __future__ import annotations

import shutil

import pytest

from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
from dlcp_fw.sim.protocol import SerialFrame


def _require_gpsim():
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_a_reg5e_bit2_clear() -> None:
    """cmd=0x20 data=0 -> reg 0x05E bit2=0 (preset A)."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x00)],
        cycles=120_000_000,
    )
    assert res.parser_break_hit is True
    reg5e = res.regs.get(0x05E, 0xFF)
    assert (reg5e >> 2) & 1 == 0, f"expected bit2=0 (preset A), got 0x05E=0x{reg5e:02X}"


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_b_reg5e_bit2_set() -> None:
    """cmd=0x20 data=1 -> reg 0x05E bit2=1 (preset B)."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    assert res.parser_break_hit is True
    reg5e = res.regs.get(0x05E, 0xFF)
    assert (reg5e >> 2) & 1 == 1, f"expected bit2=1 (preset B), got 0x05E=0x{reg5e:02X}"


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_switch_ab_sequence() -> None:
    """Set B then A -> final bit2=0, mailbox fully consumed."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[
            SerialFrame(route=0xB0, cmd=0x20, data=0x01),  # B
            SerialFrame(route=0xB0, cmd=0x20, data=0x00),  # A
        ],
        cycles=140_000_000,
    )
    assert res.parser_break_hit is True
    reg5e = res.regs.get(0x05E, 0xFF)
    assert (reg5e >> 2) & 1 == 0, f"expected bit2=0 after A, got 0x05E=0x{reg5e:02X}"
    # All 6 bytes consumed
    assert res.regs.get(0x7C0) == 6
    assert res.regs.get(0x7C1) == 6


@pytest.mark.gpsim
@pytest.mark.slow
def test_broadcast_reaches_unit() -> None:
    """route=0xB0 is consumed by unit (broadcast addressing)."""
    _require_gpsim()
    res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x20, data=0x01)],
        cycles=120_000_000,
    )
    assert res.parser_break_hit is True
    # Frame consumed: rx_rd advanced past the 3 bytes
    assert res.regs.get(0x7C0) == 3
    # Reply frame emitted: tx_wr > 0
    assert res.regs.get(0x7C3, 0) == 3
