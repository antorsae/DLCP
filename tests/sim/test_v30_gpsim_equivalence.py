"""V3.0 gpsim behavioral equivalence tests.

Replicates all stock-compatible gpsim tests using V3.0 hex instead of
stock V2.3, validating that the source-rewritten firmware behaves
identically under simulation.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V30_MAIN_HEX
from dlcp_fw.sim.gpsim import gpsim_available


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _require_v30() -> Path:
    if not V30_MAIN_HEX.exists():
        pytest.skip("V3.0 hex not built")
    return V30_MAIN_HEX


# ---------------------------------------------------------------------------
# AN0 boot gate (from test_main_gpsim_an0_boot.py)
# ---------------------------------------------------------------------------

STOCK_MAIN_AN0_BOOT_EXIT_CYCLE = 4_061_516


@pytest.mark.gpsim
def test_v30_an0_boot_gate_exit_cycle() -> None:
    """V3.0 must exit the AN0 boot gate at the exact stock cycle count."""
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.main_gpsim import (
        MAIN_AN0_BOOT_EXIT_ADDR,
        probe_main_an0_boot_exit_cycle,
    )

    cycle = probe_main_an0_boot_exit_cycle(v30)
    assert MAIN_AN0_BOOT_EXIT_ADDR == 0x2DC8
    assert cycle == STOCK_MAIN_AN0_BOOT_EXIT_CYCLE


# ---------------------------------------------------------------------------
# I2C regfile probes (from test_main_gpsim_i2c_regfile.py)
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v30_i2c_regfile_volume_command() -> None:
    """V3.0 I2C volume command must match stock mailbox behavior."""
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
    from dlcp_fw.sim.protocol import SerialFrame
    from dlcp_fw.paths import STOCK_MAIN_HEX

    # Volume command exercises I2C write path
    stock_res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x07, data=0x45)],
        main_hex=STOCK_MAIN_HEX,
        cycles=3_000_000,
    )
    v30_res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x07, data=0x45)],
        main_hex=v30,
        cycles=3_000_000,
    )

    assert stock_res.parser_break_hit == v30_res.parser_break_hit
    assert stock_res.tx_bytes == v30_res.tx_bytes
    # Volume registers should match
    for reg in (0x066, 0x067, 0x068, 0x069, 0x06E, 0x06F, 0x070, 0x071):
        assert stock_res.regs.get(reg) == v30_res.regs.get(reg), \
            f"Reg 0x{reg:03X}: stock=0x{stock_res.regs.get(reg, -1):02X} v30=0x{v30_res.regs.get(reg, -1):02X}"


# ---------------------------------------------------------------------------
# Fault injection (from test_main_gpsim_fault_injection.py)
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v30_uart_tx_fault_stalls_status_reply() -> None:
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.main_gpsim import (
        MAIN_FAULT_UART_TX_STALL,
        run_main_mailbox_gpsim,
    )
    from dlcp_fw.sim.protocol import SerialFrame

    baseline = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x04, data=0x00)],
        main_hex=v30,
        cycles=3_000_000,
    )
    stalled = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x04, data=0x00)],
        main_hex=v30,
        fault_flags=MAIN_FAULT_UART_TX_STALL,
        cycles=3_000_000,
    )

    assert baseline.parser_break_hit is True
    assert stalled.parser_break_hit is True
    assert baseline.regs.get(0x7C0) == 3
    assert baseline.regs.get(0x7C3, 0) > 0
    assert stalled.regs.get(0x7C7) == MAIN_FAULT_UART_TX_STALL
    assert stalled.regs.get(0x7C0, 0) < baseline.regs.get(0x7C0, 0)
    assert stalled.regs.get(0x7C3) == 0


@pytest.mark.gpsim
@pytest.mark.slow
def test_v30_mssp_fault_inert_until_wait_site() -> None:
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.main_gpsim import (
        MAIN_FAULT_MSSP_WAIT_STALL,
        run_main_mailbox_gpsim,
    )
    from dlcp_fw.sim.protocol import SerialFrame

    baseline = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x07, data=0x45)],
        main_hex=v30,
        cycles=3_000_000,
    )
    stalled = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=0x07, data=0x45)],
        main_hex=v30,
        fault_flags=MAIN_FAULT_MSSP_WAIT_STALL,
        cycles=3_000_000,
    )

    assert baseline.parser_break_hit is True
    assert stalled.parser_break_hit is True
    assert baseline.regs.get(0x7C0) == 3
    assert stalled.regs.get(0x7C0) == 3
    assert stalled.tx_bytes == baseline.tx_bytes == [0xB0, 0x07, 0x45]


# ---------------------------------------------------------------------------
# Command matrix (from test_main_gpsim_command_matrix.py)
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("cmd", "data", "label"),
    [
        (0x03, 0x00, "cmd03_standby_off"),
        (0x03, 0x01, "cmd03_standby_on"),
        (0x04, 0x00, "cmd04_status_request"),
        (0x07, 0x45, "cmd07_set_volume"),
    ],
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_v30_command_matrix_subset(cmd: int, data: int, label: str) -> None:
    """Core command subset must produce identical results to stock."""
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
    from dlcp_fw.sim.protocol import SerialFrame
    from dlcp_fw.paths import STOCK_MAIN_HEX
    from dlcp_fw.sim.hexio import parse_intel_hex

    stock_res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=STOCK_MAIN_HEX,
        cycles=120_000_000,
    )
    v30_res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=v30,
        cycles=120_000_000,
    )

    assert stock_res.parser_break_hit == v30_res.parser_break_hit
    assert stock_res.tx_bytes == v30_res.tx_bytes, \
        f"TX mismatch for {label}: stock={stock_res.tx_bytes} v30={v30_res.tx_bytes}"


# ---------------------------------------------------------------------------
# Chain waiting (from test_chain_gpsim_waiting.py)
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_v30_chain_reaches_display(
    stock_control_hex_v14: Path,
) -> None:
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness

    pair = SingleMainChainHarness(
        stock_control_hex_v14,
        v30,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), \
            f"pair never connected; lcd={last.lcd!r}"
        assert not pair.is_waiting()
        assert "Volume:" in last.lcd[0]
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v30_chain_blackout_wake_shows_waiting(
    stock_control_hex_v14: Path,
) -> None:
    _require_gpsim()
    v30 = _require_v30()
    from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness

    pair = SingleMainChainHarness(
        stock_control_hex_v14,
        v30,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected()

        pair.set_blackout(True)
        pair.press("STBY")
        pair.step_many(80)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), \
            f"did not enter standby: {pair.lcd_lines()!r}"

        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=20)
        assert waiting is not None
        assert pair.is_waiting(), \
            f"did not fall back to WAITING after wake: {waiting.lcd!r}"
    finally:
        pair.close()
