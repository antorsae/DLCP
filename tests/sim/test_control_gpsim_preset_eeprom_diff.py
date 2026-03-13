"""Strict EEPROM diff checks for preset-toggle operations."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.hexio import parse_intel_hex, write_intel_hex


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 12


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _boot_harness(control_hex: Path, *, eeprom_file: Path) -> GpsimControlHarness:
    h = GpsimControlHarness(
        control_hex,
        fast_boot=True,
        eeprom_file=eeprom_file,
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


def _ensure_display_ready(h: GpsimControlHarness, *, max_steps: int = 24) -> None:
    for _ in range(max_steps):
        if (h.read_reg(0x0BF) & 0xFF) == 0:
            return
        h.step()
    raise AssertionError(
        f"CONTROL UI did not enter display mode; menu_state={h.read_reg(0x0BF)} lcd={h.lcd_lines()}"
    )


def _seed_default_like_eeprom(path: Path) -> None:
    # Match harness default boot behavior: gpsim EEPROM defaults to 0x00,
    # and 0x73/0x74 are explicitly set to erased 0xFF.
    mem = {addr: 0x00 for addr in range(256)}
    mem[0x73] = 0xFF
    mem[0x74] = 0xFF
    write_intel_hex(path, mem)


def _dump_eeprom(h: GpsimControlHarness, path: Path) -> dict[int, int]:
    h.dump_eeprom(path)
    mem = parse_intel_hex(path)
    return {addr: mem.get(addr, 0xFF) for addr in range(256)}


def _diff(before: dict[int, int], after: dict[int, int]) -> dict[int, tuple[int, int]]:
    out: dict[int, tuple[int, int]] = {}
    for addr in range(256):
        b = before.get(addr, 0xFF)
        a = after.get(addr, 0xFF)
        if b != a:
            out[addr] = (b, a)
    return out


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("fixture_name", "label"),
    [
        pytest.param("patched_control_hex", "v1.41", id="v141"),
        pytest.param("patched_control_hex_v151b", "v1.51b", id="v151b"),
        pytest.param("patched_control_hex_v161b", "v1.61b", id="v161b"),
    ],
)
def test_preset_toggles_only_mutate_eeprom_0x74(
    request: pytest.FixtureRequest,
    fixture_name: str,
    label: str,
) -> None:
    """A/B toggles must only write preset persistence byte (EEPROM[0x74])."""
    _require_gpsim()
    control_hex = request.getfixturevalue(fixture_name)

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td)
        seed = tmp / f"{label}_seed.hex"
        d0 = tmp / "00_boot.hex"
        d1 = tmp / "10_after_b.hex"
        d2 = tmp / "20_after_a.hex"
        d3 = tmp / "30_after_a_idempotent.hex"
        _seed_default_like_eeprom(seed)

        h = _boot_harness(control_hex, eeprom_file=seed)
        try:
            _ensure_display_ready(h)
            _press_and_step(h, "R")  # Volume -> Preset
            assert h.read_reg(0x0BF) == 1

            e0 = _dump_eeprom(h, d0)

            _press_and_step(h, "D")  # Preset A -> B
            e1 = _dump_eeprom(h, d1)
            diff_01 = _diff(e0, e1)
            assert set(diff_01.keys()) == {0x74}, f"{label}: unexpected EEPROM diff {diff_01}"
            assert diff_01[0x74] == (0xFF, 0x01)

            _press_and_step(h, "U")  # Preset B -> A
            e2 = _dump_eeprom(h, d2)
            diff_12 = _diff(e1, e2)
            assert set(diff_12.keys()) == {0x74}, f"{label}: unexpected EEPROM diff {diff_12}"
            assert diff_12[0x74] == (0x01, 0x00)

            _press_and_step(h, "U")  # Preset A -> A (idempotent)
            e3 = _dump_eeprom(h, d3)
            diff_23 = _diff(e2, e3)
            assert diff_23 == {}, f"{label}: idempotent A-select wrote EEPROM: {diff_23}"
            assert e3[0x74] == 0x00
        finally:
            h.close()
