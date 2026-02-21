"""gpsim tests for public host-command injection helpers."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness, RxTriplet


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 12


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
    h.warmup(WARMUP_CYCLES)
    return h


def _press_and_step(h: GpsimControlHarness, key: str, steps: int = STEP_COUNT) -> None:
    h.press(key)
    for _ in range(steps):
        h.step()


@pytest.mark.gpsim
@pytest.mark.slow
def test_host_injection_sequence_preserves_non_reset_then_triggers_reset(
    patched_control_hex: Path,
) -> None:
    """Public injection helpers should drive parser state transitions deterministically."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")
        assert h.read_reg(0x0BF) == 1

        # cmd=0x18 data=0: should not reset.
        h.inject_host_command(cmd=0x18, data=0x00, steps=24)
        assert h.read_reg(0x0BF) == 1

        # cmd=0x18 data=1: should reset to boot/waiting path.
        h.inject_host_command(cmd=0x18, data=0x01, steps=48)
        seen = []
        for _ in range(16):
            h.step()
            l1, l2 = h.lcd_lines()
            seen.append((l1, l2, h.read_reg(0x0BF)))
        assert any(menu_state == 0 for _, _, menu_state in seen)
        assert any(
            ("Firmware V" in l1) or ("Waiting for DLCP" in l1) or ("Waiting for DLCP" in l2)
            for l1, l2, _ in seen
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_host_injection_normalizes_triplet_bytes(patched_control_hex: Path) -> None:
    """Injection helper normalizes >8-bit route/cmd/data before parser dispatch."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        before = {
            0x0A1: h.read_reg(0x0A1),
            0x0A7: h.read_reg(0x0A7),
            0x0B8: h.read_reg(0x0B8),
            0x0B9: h.read_reg(0x0B9),
            0x0BF: h.read_reg(0x0BF),
        }
        h.inject_host_commands(
            [RxTriplet(route=0x1BF, cmd=0x129, data=0x101)],
            steps_per_command=8,
        )
        after = {
            0x0A1: h.read_reg(0x0A1),
            0x0A7: h.read_reg(0x0A7),
            0x0B8: h.read_reg(0x0B8),
            0x0B9: h.read_reg(0x0B9),
            0x0BF: h.read_reg(0x0BF),
        }
        # 0x1BF/0x129/0x101 normalizes to BF/29/01 (ignored command path).
        assert after == before
    finally:
        h.close()
