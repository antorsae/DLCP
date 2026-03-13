"""gpsim regression tests for CONTROL parser handling of MAIN response commands."""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.gpsim import gpsim_available


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 12


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _boot_harness(
    patched_control_hex: Path,
    *,
    eeprom_file: Path | None = None,
) -> GpsimControlHarness:
    h = GpsimControlHarness(
        patched_control_hex,
        fast_boot=True,
        eeprom_file=eeprom_file,
        chunk_cycles=600_000,
        hold_cycles=300_000,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _step_n(h: GpsimControlHarness, n: int) -> None:
    for _ in range(n):
        h.step()


@pytest.mark.gpsim
@pytest.mark.slow
def test_response_cmd_0x29_is_ignored_without_state_corruption(patched_control_hex: Path) -> None:
    """Response cmd=0x29 should be safely ignored by the CONTROL parser."""
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
        h.inject_host_command(cmd=0x29, data=0x01, steps=0)
        _step_n(h, 8)
        after = {
            0x0A1: h.read_reg(0x0A1),
            0x0A7: h.read_reg(0x0A7),
            0x0B8: h.read_reg(0x0B8),
            0x0B9: h.read_reg(0x0B9),
            0x0BF: h.read_reg(0x0BF),
        }
        assert after == before
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_response_cmd_0x18_data1_triggers_reset_path(patched_control_hex: Path) -> None:
    """Response cmd=0x18 data=1 should drive the parser into boot/reset flow."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        # Move away from default menu state so a reset is observable.
        h.press("R")
        _step_n(h, STEP_COUNT)
        assert h.read_reg(0x0BF) == 1

        h.inject_host_command(cmd=0x18, data=0x01, steps=0)
        seen = []
        for _ in range(40):
            h.step()
            l1, l2 = h.lcd_lines()
            seen.append((l1, l2, h.read_reg(0x0BF)))

        assert any(
            ("Firmware V1.4" in l1) or ("Waiting for DLCP" in l1) or ("Waiting for DLCP" in l2)
            for l1, l2, _ in seen
        ), "expected boot/reset text after cmd=0x18 data=1"
        assert any(menu_state == 0 for _, _, menu_state in seen), "menu state did not reset to 0"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_response_cmd_0x18_data0_does_not_reset(patched_control_hex: Path) -> None:
    """Response cmd=0x18 with non-reset data should not trigger reboot path."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        h.press("R")
        _step_n(h, STEP_COUNT)
        assert h.read_reg(0x0BF) == 1

        h.inject_host_command(cmd=0x18, data=0x00, steps=0)
        seen = []
        for _ in range(30):
            h.step()
            l1, l2 = h.lcd_lines()
            seen.append((l1, l2, h.read_reg(0x0BF)))

        assert all(
            ("Firmware V1.4" not in l1) and ("Waiting for DLCP" not in l1) and ("Waiting for DLCP" not in l2)
            for l1, l2, _ in seen
        ), "unexpected boot/reset text for cmd=0x18 data=0"
        assert all(menu_state == 1 for _, _, menu_state in seen), "menu state changed unexpectedly"
    finally:
        h.close()
