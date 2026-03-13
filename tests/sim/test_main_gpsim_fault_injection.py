from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.main_gpsim import (
    MAIN_FAULT_MSSP_WAIT_STALL,
    MAIN_FAULT_UART_TX_STALL,
    run_main_mailbox_gpsim,
)
from dlcp_fw.sim.protocol import SerialFrame


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _run_one(main_hex: Path, *, cmd: int, data: int, fault_flags: int = 0):
    return run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=main_hex,
        fault_flags=fault_flags,
        cycles=3_000_000,
    )


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_uart_tx_fault_flag_stalls_status_reply(stock_main_hex: Path) -> None:
    """
    Forcing the UART TX helper to spin should wedge status handling before reply drain.
    """
    _require_gpsim()

    baseline = _run_one(stock_main_hex, cmd=0x04, data=0x00)
    stalled = _run_one(
        stock_main_hex,
        cmd=0x04,
        data=0x00,
        fault_flags=MAIN_FAULT_UART_TX_STALL,
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
def test_main_mssp_fault_flag_is_inert_until_wait_site_is_reached(stock_main_hex: Path) -> None:
    """
    The corrected mailbox overlay only stalls the real MSSP-idle helper path.
    A direct cmd=0x07 mailbox probe should therefore stay semantically stable.
    """
    _require_gpsim()

    baseline = _run_one(stock_main_hex, cmd=0x07, data=0x45)
    stalled = _run_one(
        stock_main_hex,
        cmd=0x07,
        data=0x45,
        fault_flags=MAIN_FAULT_MSSP_WAIT_STALL,
    )

    assert baseline.parser_break_hit is True
    assert stalled.parser_break_hit is True

    assert baseline.regs.get(0x7C0) == 3
    assert stalled.regs.get(0x7C0) == 3
    assert stalled.regs.get(0x7C7) == MAIN_FAULT_MSSP_WAIT_STALL
    assert stalled.tx_bytes == baseline.tx_bytes == [0xB0, 0x07, 0x45]
    assert stalled.regs.get(0x07E) == baseline.regs.get(0x07E) == 0


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_uart_tx_fault_flag_can_clear_mid_session(stock_main_hex: Path) -> None:
    _require_gpsim()

    harness = MainChainHarness(
        stock_main_hex,
        chunk_cycles=200_000,
        transport_mode="mailbox",
        bypass_i2c=False,
    )
    try:
        for _ in range(20):
            harness.step()

        harness.set_fault_flags(uart_tx_stall=True)
        delivered, overruns = harness.inject_frames_fifo([[0xB0, 0x04, 0x00]], fifo_limit=47)
        assert delivered == 3
        assert overruns == 0

        stalled = None
        for _ in range(6):
            stalled, _ = harness.step()
        assert stalled is not None
        assert stalled.fault_flags == MAIN_FAULT_UART_TX_STALL
        assert stalled.mailbox_rd < stalled.mailbox_wr
        assert stalled.mailbox_tx_wr == 0

        harness.clear_fault_flags()

        recovered = None
        for _ in range(20):
            recovered, _ = harness.step()
            if (
                recovered.fault_flags == 0
                and recovered.mailbox_rd == recovered.mailbox_wr == 3
                and recovered.mailbox_tx_wr > 0
            ):
                break

        assert recovered is not None
        assert recovered.fault_flags == 0
        assert recovered.mailbox_rd == recovered.mailbox_wr == 3
        assert recovered.mailbox_tx_wr > 0
    finally:
        harness.close()
