"""gpsim regression tests for original CONTROL->MAIN command emission."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness, TxTriplet


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
        chunk_cycles=600_000,
        hold_cycles=300_000,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _press_and_step(h: GpsimControlHarness, key: str, steps: int = STEP_COUNT) -> list[TxTriplet]:
    before = len(h.tx_frames())
    h.press(key)
    for _ in range(steps):
        h.step()
    return h.tx_frames()[before:]


@pytest.mark.gpsim
@pytest.mark.slow
def test_boot_emits_original_command_set_baseline(patched_control_hex: Path) -> None:
    """Boot-time sync traffic should include original legacy command IDs."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        frames = h.tx_frames()
        assert frames, "expected command traffic after boot warmup"

        expected_per_channel = {0x17, 0x18, 0x19, 0x1A, 0x1B, 0x1C, 0x1E}
        # Allow extra time for the periodic full-sync burst to appear.
        for _ in range(40):
            seen_per_channel = {f.cmd for f in frames if 0xB1 <= f.route <= 0xB6}
            if expected_per_channel.issubset(seen_per_channel):
                break
            h.step()
            frames = h.tx_frames()

        # Poll + global controls.
        assert any(f.route == 0xB1 and f.cmd == 0x04 and f.data == 0x00 for f in frames)
        assert any(f.route == 0xB0 and f.cmd == 0x06 for f in frames)
        assert any(f.route == 0xB0 and f.cmd == 0x07 for f in frames)
        assert any(f.route == 0xB0 and f.cmd == 0x1D for f in frames)

        # Per-channel config + link-address commands (unit-scoped routes 0xB1..0xB6).
        for cmd in sorted(expected_per_channel):
            assert any(0xB1 <= f.route <= 0xB6 and f.cmd == cmd for f in frames), (
                f"missing boot-time legacy command 0x{cmd:02X}"
            )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_user_actions_emit_legacy_cmd03_subcommands(patched_control_hex: Path) -> None:
    """User actions should exercise all cmd=0x03 subcommands (0,1,2,3)."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        seen = {(f.cmd, f.data) for f in h.tx_frames() if f.route == 0xB0 and f.cmd == 0x03}

        # SELECT toggles mute ON then OFF.
        seen.update((f.cmd, f.data) for f in _press_and_step(h, "S") if f.route == 0xB0)
        seen.update((f.cmd, f.data) for f in _press_and_step(h, "S") if f.route == 0xB0)

        # STBY sends standby OFF/ON variants.
        seen.update((f.cmd, f.data) for f in _press_and_step(h, "B") if f.route == 0xB0)
        for _ in range(4):
            seen.update((f.cmd, f.data) for f in _press_and_step(h, "B") if f.route == 0xB0)

        cmd03_values = {data for (cmd, data) in seen if cmd == 0x03}
        assert {0x00, 0x01, 0x02, 0x03}.issubset(cmd03_values), (
            f"cmd=0x03 subcommand coverage incomplete: saw {sorted(cmd03_values)}"
        )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_user_actions_emit_volume_and_input_legacy_commands(patched_control_hex: Path) -> None:
    """Volume and Input key actions must emit cmd=0x07 and cmd=0x06."""
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        new_vol = _press_and_step(h, "U")
        assert any(f.route == 0xB0 and f.cmd == 0x07 for f in new_vol), (
            f"volume-up did not emit cmd=0x07, got {new_vol}"
        )

        # Volume -> Preset -> Input.
        _press_and_step(h, "R")
        _press_and_step(h, "R")
        new_input = _press_and_step(h, "U")
        assert any(f.route == 0xB0 and f.cmd == 0x06 for f in new_input), (
            f"input-up did not emit cmd=0x06, got {new_input}"
        )
    finally:
        h.close()
