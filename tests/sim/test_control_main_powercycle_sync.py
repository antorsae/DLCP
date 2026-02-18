"""Regression test for CONTROL->MAIN preset resync after full power cycle."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.protocol import SerialFrame


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
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _press_and_step(h: GpsimControlHarness, key: str, steps: int = STEP_COUNT) -> None:
    h.press(key)
    for _ in range(steps):
        h.step()


def _deliver_preset_frames(main: MainUnitModel, frames) -> None:
    for f in frames:
        main.process_frame(SerialFrame(route=f.route, cmd=f.cmd, data=f.data))


def _eeprom_byte(path: Path, addr: int) -> int:
    mem = parse_intel_hex(path)
    return mem.get(addr, 0xFF)


@pytest.mark.gpsim
@pytest.mark.slow
def test_control_boot_resyncs_main_preset_after_full_power_cycle(
    patched_control_hex: Path,
    patched_main_hex: Path,
) -> None:
    """If CONTROL restores preset B from EEPROM, boot must re-emit cmd=0x20 data=1."""
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"

        # Session 1: user selects preset B and CONTROL persists EEPROM[0x74].
        h1 = _boot_harness(patched_control_hex)
        try:
            _press_and_step(h1, "R")  # Volume -> Preset
            tx_before = len(h1.tx_frames())
            _press_and_step(h1, "D")  # Select B (emits cmd=0x20 data=1)
            tx_after_select = h1.tx_frames()[tx_before:]
            preset_frames = [f for f in tx_after_select if f.cmd == 0x20]
            assert preset_frames, "selecting preset B did not emit cmd=0x20 frame"
            assert preset_frames[-1].data == 0x01
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()

        # Session 2: full power cycle for both CONTROL and MAIN.
        # MAIN starts in preset A (bit clear) after boot and depends on
        # CONTROL's boot-time preset frame to resync to B.
        main_after_boot = MainUnitModel.from_hex("main", 1, patched_main_hex)
        assert main_after_boot.preset_idx == 0

        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            for _ in range(10):
                h2.step()
            line1, _ = h2.lcd_lines()
            assert line1[15] == "B", f"expected CONTROL UI to restore B, got {line1!r}"

            boot_frames = h2.tx_frames()
            _deliver_preset_frames(main_after_boot, boot_frames)

            assert any(f.cmd == 0x20 and f.data == 0x01 for f in boot_frames), (
                "CONTROL boot did not emit preset-resync frame cmd=0x20 data=1"
            )
            assert main_after_boot.preset_idx == 1, (
                "MAIN remained in preset A after full power cycle; "
                "expected CONTROL boot to resync MAIN to preset B"
            )
        finally:
            h2.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_late_join_main_reboot_resyncs_via_periodic_preset_broadcast(
    patched_control_hex: Path,
    patched_main_hex: Path,
) -> None:
    """A MAIN rebooting mid-run should be pulled back to CONTROL's current preset."""
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"
        eeprom_after_path = Path(td) / "eeprom_after.hex"

        # Session 1: persist preset B in CONTROL EEPROM.
        h1 = _boot_harness(patched_control_hex)
        try:
            _press_and_step(h1, "R")  # Volume -> Preset
            _press_and_step(h1, "D")  # Select B
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()
        assert _eeprom_byte(eeprom_path, 0x74) == 0x01

        # Session 2: CONTROL runs with preset B restored.
        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            boot_frames = h2.tx_frames()
            assert any(f.cmd == 0x20 and f.data == 0x01 for f in boot_frames)

            # MAIN #1 online at startup follows preset B.
            main1 = MainUnitModel.from_hex("main1", 1, patched_main_hex)
            _deliver_preset_frames(main1, boot_frames)
            assert main1.preset_idx == 1
            assert main1.apply_count == 1

            # MAIN #2 reboots later (starts from preset A) and must recover to B
            # from periodic CONTROL preset broadcasts.
            main2 = MainUnitModel.from_hex("main2", 1, patched_main_hex)
            assert main2.preset_idx == 0

            frame_idx = len(h2.tx_frames())
            saw_periodic_preset = False
            for _ in range(80):
                h2.step()
                new_frames = h2.tx_frames()[frame_idx:]
                frame_idx += len(new_frames)
                _deliver_preset_frames(main2, new_frames)
                if any(f.cmd == 0x20 and f.data == 0x01 for f in new_frames):
                    saw_periodic_preset = True
                if saw_periodic_preset and main2.preset_idx == 1:
                    break

            assert saw_periodic_preset, "no periodic preset resync frame observed after startup"
            assert main2.preset_idx == 1, "late-join MAIN did not recover to CONTROL preset B"
            # MAIN cmd=0x20 is idempotent: repeated set-B frames should not re-apply.
            assert main2.apply_count == 1

            # Periodic sync path should not rewrite preset EEPROM.
            h2.dump_eeprom(eeprom_after_path)
        finally:
            h2.close()

        assert _eeprom_byte(eeprom_after_path, 0x74) == 0x01
