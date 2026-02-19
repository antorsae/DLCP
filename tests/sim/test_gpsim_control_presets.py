"""gpsim-level tests for CONTROL firmware preset UI and persistence.

All tests require gpsim and are marked slow — run with:
    pytest -m gpsim tests/sim/test_gpsim_control_presets.py
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness


WARMUP_CYCLES = 25_000_000  # boot(~7M) + WAITING(~16M) + DISPLAY entry(~19M) + margin
STEP_COUNT = 12  # steps per button press to allow debounce + render


def _require_gpsim():
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
        # Keep UI navigation tests deterministic; synthetic heartbeat traffic
        # can alias with short key pulses and create timing-only flakes.
        heartbeat_rx_mode="none",
        heartbeat_force_connected=True,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _press_and_step(h: GpsimControlHarness, key: str, steps: int = STEP_COUNT):
    """Press a key and step until the firmware processes it."""
    h.press(key)
    for _ in range(steps):
        h.step()


@pytest.mark.gpsim
@pytest.mark.slow
def test_boot_shows_preset_a(patched_control_hex) -> None:
    """Fresh EEPROM boot -> LCD column 15 shows 'A'."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        # Step a few more times for LCD to settle
        for _ in range(8):
            h.step()
        l1, _ = h.lcd_lines()
        assert l1[15] == "A", f"expected 'A' at col 15, got {l1!r}"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_screen_navigation(patched_control_hex) -> None:
    """R -> Preset(>A<), D -> (>B<), L -> Volume(B)."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        # Navigate RIGHT to Preset screen
        _press_and_step(h, "R")
        l1, l2 = h.lcd_lines()
        assert "Preset" in l1
        assert ">A<" in l1, f"expected >A< in line1, got {l1!r}"
        assert "B" in l2

        # DOWN -> select B
        _press_and_step(h, "D")
        l1, l2 = h.lcd_lines()
        assert ">B<" in l2, f"expected >B< in line2, got {l2!r}"

        # LEFT -> back to Volume
        _press_and_step(h, "L")
        l1, _ = h.lcd_lines()
        assert l1[15] == "B", f"expected 'B' at col 15, got {l1!r}"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_emits_serial_frames(patched_control_hex) -> None:
    """DOWN -> (0xB0,0x20,0x01), UP -> (0xB0,0x20,0x00)."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        # Navigate to Preset screen
        _press_and_step(h, "R")

        # Press DOWN (select B)
        tx_before = len(h.tx_frames())
        _press_and_step(h, "D")
        frames = h.tx_frames()[tx_before:]
        preset_frames = [f for f in frames if f.cmd == 0x20]
        assert len(preset_frames) >= 1, f"expected preset frame, got {frames}"
        assert preset_frames[0].route == 0xB0
        assert preset_frames[0].data == 0x01  # B

        # Press UP (select A)
        tx_before = len(h.tx_frames())
        _press_and_step(h, "U")
        frames = h.tx_frames()[tx_before:]
        preset_frames = [f for f in frames if f.cmd == 0x20]
        assert len(preset_frames) >= 1, f"expected preset frame, got {frames}"
        assert preset_frames[0].route == 0xB0
        assert preset_frames[0].data == 0x00  # A
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_preset_persists_power_cycle(patched_control_hex) -> None:
    """Set B -> dump EEPROM -> new session with loaded EEPROM -> boot shows B."""
    _require_gpsim()
    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"

        # Session 1: switch to preset B and dump EEPROM
        h1 = _boot_harness(patched_control_hex)
        try:
            _press_and_step(h1, "R")   # -> Preset screen
            _press_and_step(h1, "D")   # -> select B
            l1, l2 = h1.lcd_lines()
            assert ">B<" in l2, f"expected >B< in line2, got {l2!r}"
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()

        assert eeprom_path.exists(), "EEPROM dump file not created"

        # Session 2: boot with the saved EEPROM
        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            for _ in range(8):
                h2.step()
            l1, _ = h2.lcd_lines()
            assert l1[15] == "B", f"expected 'B' at col 15 after EEPROM restore, got {l1!r}"
        finally:
            h2.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_four_screen_wraparound(patched_control_hex) -> None:
    """R x4: menu_state cycles 0->1->2->3->0."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        states = [h.read_reg(0x0BF)]
        for _ in range(4):
            _press_and_step(h, "R")
            states.append(h.read_reg(0x0BF))
        assert states == [0, 1, 2, 3, 0], f"menu_state sequence: {states}"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_volume_resets_on_power_cycle(patched_control_hex) -> None:
    """Volume is volatile — RAM changes don't survive power cycle.

    Volume (0x0B9) is synced from MAIN via serial, not stored in EEPROM.
    After a power cycle the register returns to the heartbeat-injected
    default regardless of the value it had before the reset.
    """
    _require_gpsim()
    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"

        # Session 1: change volume in RAM directly, then dump EEPROM.
        h1 = _boot_harness(patched_control_hex)
        try:
            vol_default = h1.read_reg(0x0B9)
            # Simulate a volume change by writing directly to RAM
            h1._issue("reg(0x0B9)=0x30", 5.0)
            vol_changed = h1.read_reg(0x0B9)
            assert vol_changed == 0x30, (
                f"direct RAM write failed: expected 0x30, got 0x{vol_changed:02X}"
            )
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()

        # Session 2: boot with same EEPROM — volume should revert to
        # the heartbeat-injected value, proving it's not in EEPROM.
        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            for _ in range(8):
                h2.step()
            vol_reset = h2.read_reg(0x0B9)
            assert vol_reset == vol_default, (
                f"volume should reset to 0x{vol_default:02X} on power cycle, "
                f"got 0x{vol_reset:02X}"
            )
        finally:
            h2.close()
