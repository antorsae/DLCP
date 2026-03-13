from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.gpsim import GpsimRunConfig, run_gpsim
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.lcd import LcdState, decode_lcd_bytes
from dlcp_fw.sim.manifests import control_reset_to_appstart
from dlcp_fw.sim.overlay import apply_overlays


@pytest.mark.gpsim
@pytest.mark.slow
def test_gpsim_lcd_decode_boot_screen(patched_control_hex: Path) -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")

    with tempfile.TemporaryDirectory(prefix="test_gpsim_lcd_") as td:
        td_path = Path(td)
        sim_hex = td_path / "sim.hex"
        apply_overlays(patched_control_hex, sim_hex, manifests=[control_reset_to_appstart()])

        result = run_gpsim(
            GpsimRunConfig(
                hex_path=sim_hex,
                cycles=50_000_000,
            ),
            td_path / "run",
        )
        lcd_bytes = decode_lcd_bytes(result.log_path)
        assert len(lcd_bytes) > 0
        state = LcdState.new()
        for b in lcd_bytes:
            state.apply(b)
        final = (state.line1() + state.line2()).lower()
        assert "waiting for dlcp" in final or "volume" in final
