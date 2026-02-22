import shutil
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness


def _require_gpsim() -> None:
    if shutil.which("gpsim") is None:
        pytest.skip("gpsim not installed")

def _boot_harness(patched_control_hex: Path) -> GpsimControlHarness:
    h = GpsimControlHarness(
        patched_control_hex,
        fast_boot=True,
        chunk_cycles=200_000,
        hold_cycles=120_000,
        heartbeat_rx_mode="none",
        heartbeat_force_connected=True,
    )
    h.warmup(25_000_000)
    return h

@pytest.mark.gpsim
def test_storm(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        h.press("R")
        for _ in range(10):
            h.step()

        frames = h.tx_frames()
        gen_reqs = [f for f in frames if f.cmd == 0x22]
        reqs = [f for f in frames if f.cmd == 0x21]
        assert gen_reqs, "expected at least one generation request on Preset entry"

        # Inject one chunk without context: parser must ignore and not start storms.
        h.inject_host_command(cmd=0x30, data=65, steps=1)
        for _ in range(200):
            h.step()

        frames_after = h.tx_frames()
        reqs_after = [f for f in frames_after if f.cmd == 0x21]
        assert len(reqs_after) == len(reqs), "storm detected: chunk without context triggered requests"
    finally:
        h.close()
