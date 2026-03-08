"""gpsim-level tests for CONTROL firmware preset UI and persistence."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 12


def _require_gpsim() -> None:
    if shutil.which("gpsim") is None:
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
        chunk_cycles=200_000,
        hold_cycles=100_000,
        heartbeat_rx_mode="none",
        heartbeat_force_connected=True,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _press_and_step(h: GpsimControlHarness, key: str, steps: int = STEP_COUNT) -> None:
    h.press(key)
    for _ in range(steps):
        h.step()


def _step_until_line1(h: GpsimControlHarness, expected: str, *, limit: int = 80) -> None:
    for _ in range(limit):
        if h.lcd_lines()[0] == expected:
            return
        h.step()
    raise AssertionError(f"failed to reach LCD line1={expected!r}, got={h.lcd_lines()!r}")


@pytest.mark.gpsim
@pytest.mark.slow
def test_boot_shows_preset_a(patched_control_hex) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        for _ in range(8):
            h.step()
        l1, _ = h.lcd_lines()
        assert l1 == "Volume:        A"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_screen_navigation(patched_control_hex) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")
        l1, l2 = h.lcd_lines()
        assert l1 == "Preset          "
        assert l2 == "Active: A       "

        _press_and_step(h, "D")
        l1, l2 = h.lcd_lines()
        assert l1 == "Preset          "
        assert l2 == "Active: B       "

        _press_and_step(h, "L")
        l1, _ = h.lcd_lines()
        assert l1 == "Volume:        B"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_emits_serial_frames(patched_control_hex) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _press_and_step(h, "R")
        tx_before = len(h.tx_frames())
        _press_and_step(h, "D")
        frames = h.tx_frames()[tx_before:]
        preset_frames = [f for f in frames if f.cmd == 0x20]
        assert preset_frames
        assert preset_frames[0].route == 0xB0
        assert preset_frames[0].data == 0x01

        tx_before = len(h.tx_frames())
        _press_and_step(h, "U")
        frames = h.tx_frames()[tx_before:]
        preset_frames = [f for f in frames if f.cmd == 0x20]
        assert preset_frames
        assert preset_frames[0].route == 0xB0
        assert preset_frames[0].data == 0x00
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_persists_power_cycle(patched_control_hex) -> None:
    _require_gpsim()
    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"

        h1 = _boot_harness(patched_control_hex)
        try:
            _press_and_step(h1, "R")
            _press_and_step(h1, "D")
            l1, l2 = h1.lcd_lines()
            assert l1 == "Preset          "
            assert l2 == "Active: B       "
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()

        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            _step_until_line1(h2, "Volume:        B")
        finally:
            h2.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_four_screen_wraparound(patched_control_hex) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        states = [h.read_reg(0x0BF)]
        for target in (1, 2, 3, 0):
            cur = states[-1]
            for _ in range(3):
                _press_and_step(h, "R")
                cur = h.read_reg(0x0BF)
                if cur == target:
                    break
            states.append(cur)
            assert cur == target, f"menu_state failed to reach {target}, sequence={states}"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_volume_resets_on_power_cycle(patched_control_hex) -> None:
    _require_gpsim()
    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"

        h1 = _boot_harness(patched_control_hex)
        try:
            vol_default = h1.read_reg(0x0B9)
            h1._issue("reg(0x0B9)=0x30", 5.0)
            assert h1.read_reg(0x0B9) == 0x30
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()

        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            for _ in range(8):
                h2.step()
            assert h2.read_reg(0x0B9) == vol_default
        finally:
            h2.close()
