from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


@pytest.mark.gpsim
@pytest.mark.slow
def test_stock_wire_single_main_chain_exchanges_real_uart_frames(
    stock_control_hex_v14: Path,
    stock_main_hex: Path,
) -> None:
    _require_gpsim()
    chain = WireMultiMainChainHarness(
        stock_control_hex_v14,
        stock_main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )
    try:
        assert not chain.mains[0].uses_adc_boot_wait_hook

        last = chain.run_until_main_reply(limit=45, main_index=0)
        assert last is not None, "wire chain never produced a step result"
        assert chain.main_rx_activity(0), "MAIN0 never showed native RX activity from CONTROL"
        assert chain.control_rx_activity(), "CONTROL never consumed UART data from MAIN0"

        frames = chain.main_tx_frames(0)
        assert frames, "MAIN0 never emitted a UART reply over the wire bridge"
        assert any((f.route, f.cmd, f.data) == (0xBF, 0x03, 0x01) for f in frames), frames[-10:]
    finally:
        chain.close()
