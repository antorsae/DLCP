"""gpsim tests for IR-driven preset switching (F1/F2) in patched CONTROL firmware."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness, TxTriplet


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 10


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


def _set_profile_hypex(h: GpsimControlHarness) -> None:
    # Profile 1 address/codes: address=0x10, F1/F2=0x38/0x39.
    h._issue("reg(0x020)=0x10", 5.0)
    h._issue("reg(0x021)=0x32", 5.0)
    h._issue("reg(0x022)=0x33", 5.0)
    h._issue("reg(0x023)=0x34", 5.0)
    h._issue("reg(0x024)=0x36", 5.0)
    h._issue("reg(0x025)=0x37", 5.0)
    h._issue("reg(0x026)=0x35", 5.0)


def _preset_idx(h: GpsimControlHarness) -> int:
    return (h.read_reg(0x01F) >> 6) & 0x01


def _set_preset_idx(h: GpsimControlHarness, preset: int) -> None:
    flags = h.read_reg(0x01F)
    if preset:
        flags |= 0x40
    else:
        flags &= ~0x40
    h._issue(f"reg(0x01F)=0x{flags:02X}", 5.0)


def _preset_frames(frames: list[TxTriplet]) -> list[tuple[int, int, int]]:
    return [
        (f.route, f.cmd, f.data)
        for f in frames
        if f.route == 0xB0 and f.cmd == 0x20
    ]


@pytest.mark.gpsim
@pytest.mark.slow
def test_ir_f1_f2_switch_and_idempotent(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _set_profile_hypex(h)
        _set_preset_idx(h, 0)
        assert _preset_idx(h) == 0

        frames_b = h.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        assert _preset_idx(h) == 1
        assert _preset_frames(frames_b) == [(0xB0, 0x20, 0x01)]

        frames_b_repeat = h.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        assert _preset_idx(h) == 1
        assert _preset_frames(frames_b_repeat) == []

        frames_a = h.inject_decoded_ir_event(cmd=0x38, addr=0x10, steps=1)
        assert _preset_idx(h) == 0
        assert _preset_frames(frames_a) == [(0xB0, 0x20, 0x00)]

        frames_a_repeat = h.inject_decoded_ir_event(cmd=0x38, addr=0x10, steps=1)
        assert _preset_idx(h) == 0
        assert _preset_frames(frames_a_repeat) == []
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_ir_wrong_address_does_not_switch_preset(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _set_profile_hypex(h)
        _set_preset_idx(h, 0)
        frames = h.inject_decoded_ir_event(cmd=0x39, addr=0x00, steps=1)
        assert _preset_idx(h) == 0
        assert _preset_frames(frames) == []
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_ir_preset_switch_updates_volume_screen_indicator(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _set_profile_hypex(h)
        _set_preset_idx(h, 0)
        for _ in range(3):
            h.step()
        line1, _ = h.lcd_lines()
        assert line1[15] == "A"

        h.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        for _ in range(4):
            h.step()
        line1, _ = h.lcd_lines()
        assert _preset_idx(h) == 1
        assert line1[15] == "B"

        h.inject_decoded_ir_event(cmd=0x38, addr=0x10, steps=1)
        for _ in range(4):
            h.step()
        line1, _ = h.lcd_lines()
        assert _preset_idx(h) == 0
        assert line1[15] == "A"
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_ir_preset_switch_rerenders_preset_screen(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _set_profile_hypex(h)
        _set_preset_idx(h, 0)

        _press_and_step(h, "R")  # Volume -> Preset
        assert h.read_reg(0x0BF) == 1
        l1, l2 = h.lcd_lines()
        assert l1[15] == "A"
        assert len(l2) == 16

        h.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        for _ in range(4):
            h.step()
        assert h.read_reg(0x0BF) == 1
        l1, l2 = h.lcd_lines()
        assert _preset_idx(h) == 1
        assert l1[15] == "B"
        assert len(l2) == 16

        h.inject_decoded_ir_event(cmd=0x38, addr=0x10, steps=1)
        for _ in range(4):
            h.step()
        assert h.read_reg(0x0BF) == 1
        l1, l2 = h.lcd_lines()
        assert _preset_idx(h) == 0
        assert l1[15] == "A"
        assert len(l2) == 16
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_ir_preset_switch_works_when_preset_not_visible(patched_control_hex: Path) -> None:
    _require_gpsim()
    h = _boot_harness(patched_control_hex)
    try:
        _set_profile_hypex(h)
        _set_preset_idx(h, 0)

        _press_and_step(h, "R")  # Volume -> Preset
        _press_and_step(h, "R")  # Preset -> Input
        assert h.read_reg(0x0BF) == 2

        frames = h.inject_decoded_ir_event(cmd=0x39, addr=0x10, steps=1)
        assert _preset_idx(h) == 1
        assert _preset_frames(frames) == [(0xB0, 0x20, 0x01)]
        assert h.read_reg(0x0BF) == 2

        # Input -> Preset -> Volume; allow one extra attempt because
        # preset-screen async redraw can consume a navigation edge.
        for _ in range(3):
            if h.read_reg(0x0BF) == 0:
                break
            _press_and_step(h, "L")
        assert h.read_reg(0x0BF) == 0
        line1, _ = h.lcd_lines()
        assert line1[15] == "B"
    finally:
        h.close()
