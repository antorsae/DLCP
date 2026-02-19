"""Deep gpsim regression: preset isolation + persistence across config edits."""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.sim.control_gpsim import GpsimControlHarness
from dlcp_fw.sim.hexio import parse_intel_hex


WARMUP_CYCLES = 25_000_000
STEP_COUNT = 18

# Channel parameter blocks in RAM for Source CH1..CH6.
CH_RAM_BASES = [0x0C1, 0x0C7, 0x0CD, 0x0D3, 0x0D9, 0x0DF]


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
        # Keep UI responsive without overwriting user-edited settings via
        # synthetic BF/05/07/06/1D traffic.
        heartbeat_rx_mode="none",
        heartbeat_force_connected=True,
        heartbeat_reset_idle=False,
    )
    h.warmup(WARMUP_CYCLES)
    return h


def _step_n(h: GpsimControlHarness, n: int = STEP_COUNT) -> None:
    for _ in range(n):
        h.step()


def _press(h: GpsimControlHarness, key: str, n: int = STEP_COUNT) -> None:
    h.press(key)
    _step_n(h, n)


def _menu_state(h: GpsimControlHarness) -> int:
    return h.read_reg(0x0BF) & 0xFF


def _preset_reg(h: GpsimControlHarness) -> int:
    return (h.read_reg(0x01F) >> 6) & 0x01


def _assert_preset(h: GpsimControlHarness, expected: int, context: str) -> None:
    got = _preset_reg(h)
    assert got == expected, (
        f"{context}: preset drifted, expected {expected}, got {got}; "
        f"lcd={h.lcd_lines()}"
    )


def _goto_menu_state(h: GpsimControlHarness, target: int, *, max_moves: int = 40) -> None:
    assert 0 <= target <= 3
    for _ in range(max_moves):
        cur = _menu_state(h)
        if cur == target:
            return
        right = (target - cur) % 4
        left = (cur - target) % 4
        _press(h, "R" if right <= left else "L")
    raise AssertionError(f"failed to reach menu_state={target}, now={_menu_state(h)}")


def _in_setup_editor(h: GpsimControlHarness) -> bool:
    if _menu_state(h) != 3:
        return False
    line1, _ = h.lcd_lines()
    return line1.strip() != "Setup"


def _enter_setup_editor(h: GpsimControlHarness) -> None:
    for _ in range(10):
        if _in_setup_editor(h):
            return
        _press(h, "S")
    raise AssertionError(f"failed to enter setup editor; lcd={h.lcd_lines()}")


def _exit_setup_editor(h: GpsimControlHarness) -> None:
    for _ in range(10):
        if not _in_setup_editor(h):
            return
        _press(h, "S")
    raise AssertionError(f"failed to exit setup editor; lcd={h.lcd_lines()}")


def _goto_setup_item(h: GpsimControlHarness, item_idx: int, *, max_moves: int = 40) -> None:
    assert 0 <= item_idx <= 6
    _goto_menu_state(h, 3)
    _exit_setup_editor(h)
    for _ in range(max_moves):
        cur = h.read_reg(0x0BA) & 0xFF
        if cur == item_idx:
            return
        up = (item_idx - cur) % 7
        down = (cur - item_idx) % 7
        _press(h, "U" if up <= down else "D")
    raise AssertionError(
        f"failed to reach setup item {item_idx}, now={h.read_reg(0x0BA)} lcd={h.lcd_lines()}"
    )


def _set_param_idx(h: GpsimControlHarness, target: int, *, max_moves: int = 24) -> None:
    assert 0 <= target <= 6
    for _ in range(max_moves):
        cur = h.read_reg(0x0C0) & 0xFF
        if cur == target:
            return
        right = (target - cur) % 7
        left = (cur - target) % 7
        _press(h, "R" if right <= left else "L")
    raise AssertionError(
        f"failed to reach param_idx={target}, now={h.read_reg(0x0C0)} lcd={h.lcd_lines()}"
    )


def _set_line2_contains(h: GpsimControlHarness, token: str, *, max_presses: int = 12) -> None:
    for _ in range(max_presses):
        _, line2 = h.lcd_lines()
        if token in line2:
            return
        _press(h, "U")
    raise AssertionError(f"failed to reach option containing {token!r}; lcd={h.lcd_lines()}")


def _force_persist_tick(h: GpsimControlHarness) -> None:
    # Trigger the periodic save branch in function_042: set timer to 0xEA60.
    h._issue("reg(0x09D)=0x60", 5.0)
    h._issue("reg(0x09E)=0xEA", 5.0)
    # Allow enough runtime for the EEPROM save loop to fully complete in gpsim.
    # Shorter windows can capture a mid-save image (early bytes updated, later
    # bytes still stale), which causes false persistence mismatches.
    _step_n(h, 20)


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("preset_idx,preset_key", [(0, "U"), (1, "D")])
def test_full_config_runtime_and_persistence_matrix(
    patched_control_hex: Path,
    preset_idx: int,
    preset_key: str,
) -> None:
    """Change Input/BL Timeout/DLCP1/DLCP2 settings; preset must never drift."""
    _require_gpsim()

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / f"eeprom_preset_{preset_idx}.hex"

        h = _boot_harness(patched_control_hex)
        try:
            # Select target preset first.
            _goto_menu_state(h, 1)
            for _ in range(6):
                if _preset_reg(h) == preset_idx:
                    break
                _press(h, preset_key)
            _assert_preset(h, preset_idx, "after preset selection")

            # Input: sweep across all available options.
            _goto_menu_state(h, 2)
            seen_input_labels = {h.lcd_lines()[1].strip()}
            for _ in range(36):
                _press(h, "U")
                _assert_preset(h, preset_idx, "during input sweep")
                seen_input_labels.add(h.lcd_lines()[1].strip())
                if len(seen_input_labels) >= 7:
                    break
            assert len(seen_input_labels) >= 7, f"input sweep coverage too low: {seen_input_labels}"

            # BL Timeout: walk all options, preset must remain unchanged.
            _goto_setup_item(h, 6)
            _enter_setup_editor(h)
            for token in ("30 sec", "2 min", "5 min", "Off (no timeout)"):
                _set_line2_contains(h, token)
                _assert_preset(h, preset_idx, f"during BL Timeout option {token}")
            _exit_setup_editor(h)

            # DLCP1 + DLCP2: CH1..CH6 Right->Left and USBaudio CAT/AES->S/PDIF.
            expected_chan: dict[tuple[int, int], int] = {}
            expected_aux: dict[int, int] = {}
            for unit in (0, 1):
                _goto_setup_item(h, unit)
                _enter_setup_editor(h)

                for param_idx, base in enumerate(CH_RAM_BASES):
                    _set_param_idx(h, param_idx)
                    _set_line2_contains(h, ":Right")
                    _assert_preset(h, preset_idx, f"unit {unit+1} ch{param_idx+1} set Right")
                    _set_line2_contains(h, ":Left")
                    _assert_preset(h, preset_idx, f"unit {unit+1} ch{param_idx+1} set Left")
                    expected_chan[(unit, param_idx)] = h.read_reg(base + unit) & 0xFF

                _set_param_idx(h, 6)
                _set_line2_contains(h, "CAT/AES")
                _assert_preset(h, preset_idx, f"unit {unit+1} USBaudio set CAT/AES")
                _set_line2_contains(h, "S/PDIF")
                _assert_preset(h, preset_idx, f"unit {unit+1} USBaudio set S/PDIF")
                expected_aux[unit] = h.read_reg(0x0E5 + unit) & 0xFF

                _exit_setup_editor(h)

            # Force-save and verify EEPROM persistence for the edited fields.
            for _ in range(3):
                _force_persist_tick(h)
            h.dump_eeprom(eeprom_path)
            eep = parse_intel_hex(eeprom_path)

            expected_preset_eep = 0x01 if preset_idx else 0xFF
            assert eep.get(0x74, 0xFF) == expected_preset_eep, (
                "preset EEPROM byte mismatch"
            )

            for (unit, param_idx), ram_val in expected_chan.items():
                eep_addr = 0x03 + (param_idx * 6) + unit
                assert eep.get(eep_addr, 0xFF) == ram_val, (
                    f"EEPROM mismatch for unit {unit+1} ch{param_idx+1} at 0x{eep_addr:02X}"
                )
            for unit, ram_val in expected_aux.items():
                eep_addr = 0x27 + unit
                assert eep.get(eep_addr, 0xFF) == ram_val, (
                    f"EEPROM mismatch for unit {unit+1} USBaudio at 0x{eep_addr:02X}"
                )
        finally:
            h.close()

        # Reboot with captured EEPROM and verify key persisted values reload.
        h2 = _boot_harness(patched_control_hex, eeprom_file=eeprom_path)
        try:
            assert _preset_reg(h2) == preset_idx, "preset did not restore after reboot"
            for (unit, param_idx), ram_val in expected_chan.items():
                got = h2.read_reg(CH_RAM_BASES[param_idx] + unit) & 0xFF
                assert got == ram_val, f"reboot mismatch unit {unit+1} ch{param_idx+1}"
            for unit, ram_val in expected_aux.items():
                got = h2.read_reg(0x0E5 + unit) & 0xFF
                assert got == ram_val, f"reboot mismatch unit {unit+1} USBaudio"
        finally:
            h2.close()
