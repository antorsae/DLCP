"""Regression tests for CONTROL->MAIN preset resync with bounded retry bursts."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.protocol import SerialFrame


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


def _deliver_preset_frames(main: MainUnitModel, frames) -> None:
    for f in frames:
        main.process_frame(SerialFrame(route=f.route, cmd=f.cmd, data=f.data))


def _eeprom_byte(path: Path, addr: int) -> int:
    mem = parse_intel_hex(path)
    return mem.get(addr, 0xFF)


def _preset_frames(frames) -> list[tuple[int, int, int]]:
    return [(f.route, f.cmd, f.data) for f in frames if f.cmd == 0x20]


def _wait_for_preset_frame_count(
    h: GpsimControlHarness,
    expected: int,
    *,
    limit: int = 160,
) -> list[tuple[int, int, int]]:
    for _ in range(limit):
        frames = _preset_frames(h.tx_frames())
        if len(frames) >= expected:
            return frames
        h.step()
    raise AssertionError(f"failed to collect {expected} preset frames, got {_preset_frames(h.tx_frames())!r}")


@pytest.mark.gpsim
@pytest.mark.slow
def test_control_boot_resyncs_main_preset_after_full_power_cycle(
    patched_control_hex: Path,
    patched_main_hex: Path,
) -> None:
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"

        h1 = _boot_harness(patched_control_hex)
        try:
            _press_and_step(h1, "R")
            _press_and_step(h1, "D")
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()

        main_after_boot = MainUnitModel.from_hex("main", 1, patched_main_hex)
        assert main_after_boot.preset_idx == 0

        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            boot_frames = _wait_for_preset_frame_count(h2, 3)
            assert boot_frames[:3] == [
                (0xB0, 0x20, 0x01),
                (0xB0, 0x20, 0x01),
                (0xB0, 0x20, 0x01),
            ]
            _deliver_preset_frames(main_after_boot, h2.tx_frames())
            assert main_after_boot.preset_idx == 1
            assert main_after_boot.apply_count == 1

            before = len(_preset_frames(h2.tx_frames()))
            for _ in range(24):
                h2.step()
            after = len(_preset_frames(h2.tx_frames()))
            assert after == before, "boot retry burst did not terminate after three sends"
        finally:
            h2.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_reconnect_queues_exactly_three_additional_preset_retries(
    patched_control_hex: Path,
) -> None:
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.hex"
        h = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            baseline = len(_preset_frames(h.tx_frames()))
            flags = h.read_reg(0x01F)
            h._issue(f"reg(0x01F)=0x{flags & ~0x02:02X}", 5.0)
            for _ in range(4):
                h.step()
            baseline = len(_preset_frames(h.tx_frames()))
            flags = h.read_reg(0x01F)
            h._issue(f"reg(0x01F)=0x{flags | 0x02:02X}", 5.0)

            burst = _wait_for_preset_frame_count(h, baseline + 3)[baseline:]
            assert burst[:3] == [
                (0xB0, 0x20, 0x00),
                (0xB0, 0x20, 0x00),
                (0xB0, 0x20, 0x00),
            ]
            stable = len(_preset_frames(h.tx_frames()))
            for _ in range(24):
                h.step()
            assert len(_preset_frames(h.tx_frames())) == stable
        finally:
            h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_retry_burst_does_not_rewrite_preset_eeprom(
    patched_control_hex: Path,
) -> None:
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "seed.hex"
        after_path = Path(td) / "after.hex"

        h1 = _boot_harness(patched_control_hex)
        try:
            _press_and_step(h1, "R")
            _press_and_step(h1, "D")
            h1.dump_eeprom(eeprom_path)
        finally:
            h1.close()
        assert _eeprom_byte(eeprom_path, 0x74) == 0x01

        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            for _ in range(40):
                h2.step()
            h2.dump_eeprom(after_path)
        finally:
            h2.close()

        assert _eeprom_byte(after_path, 0x74) == 0x01
