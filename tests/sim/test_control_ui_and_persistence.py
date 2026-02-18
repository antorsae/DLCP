from __future__ import annotations

import tempfile
from pathlib import Path

from dlcp_fw.sim.control_ui import ControlPersistentState, ControlStrings, ControlUISim
from dlcp_fw.sim.protocol import SerialFrame


def test_preset_screen_navigation(patched_control_hex) -> None:
    """Volume -> Preset -> switch to B -> back to Volume shows B."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    # Initial state: Volume with A
    l1, l2 = sim.render()
    assert l1 == "Volume:        A"

    # RIGHT -> Preset screen (A active by default)
    sim.press("R")
    l1, l2 = sim.render()
    assert l1 == "Preset       >A<"
    assert l2 == "              B "

    # DOWN -> select B
    sim.press("D")
    l1, l2 = sim.render()
    assert l1 == "Preset        A "
    assert l2 == "             >B<"
    assert sim.preset == 1

    # LEFT -> back to Volume, shows B
    sim.press("L")
    l1, _ = sim.render()
    assert l1 == "Volume:        B"


def test_keypress_script_emits_preset_frames(patched_control_hex) -> None:
    """Preset screen UP/DOWN emits correct serial frames."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    # Navigate to Preset, switch B then A
    script = ["R", "D", "U"]
    sim.run_script(script)

    assert len(sim.tx_frames) == 2
    assert sim.tx_frames[0] == SerialFrame(route=0xB0, cmd=0x20, data=0x01)
    assert sim.tx_frames[1] == SerialFrame(route=0xB0, cmd=0x20, data=0x00)


def test_four_screen_wraparound(patched_control_hex) -> None:
    """Navigation wraps: Volume -> Preset -> Input -> Setup -> Volume."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    assert sim.menu_state == 0  # Volume
    sim.press("R")
    assert sim.menu_state == 1  # Preset
    sim.press("R")
    assert sim.menu_state == 2  # Input
    sim.press("R")
    assert sim.menu_state == 3  # Setup
    sim.press("R")
    assert sim.menu_state == 0  # Volume (wrap)

    # And LEFT wraps the other way
    sim.press("L")
    assert sim.menu_state == 3  # Setup
    sim.press("L")
    assert sim.menu_state == 2  # Input
    sim.press("L")
    assert sim.menu_state == 1  # Preset
    sim.press("L")
    assert sim.menu_state == 0  # Volume


def test_power_cycle_persists_last_preset(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    # Navigate to Preset and switch to B
    sim.run_script(["R", "D"])
    assert sim.preset == 1
    assert sim.persist.load_preset() == 1
    # Verify EEPROM address matches patched firmware (0x74)
    assert sim.persist.eeprom[0x74] == 1

    sim2 = sim.power_cycle()
    assert sim2.preset == 1
    line1, _ = sim2.render()
    assert line1 == "Volume:        B"


def test_eeprom_file_roundtrip(patched_control_hex) -> None:
    """Save EEPROM to file, load in new sim, verify preset survives."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R", "D"])  # switch to preset B
    assert sim.preset == 1

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.bin"
        sim.persist.save_to_file(eeprom_path)
        assert eeprom_path.exists()
        assert len(eeprom_path.read_bytes()) == 256

        # Create a fresh sim with a new persistent state loaded from file
        persist2 = ControlPersistentState()
        persist2.load_from_file(eeprom_path)
        sim2 = ControlUISim(st=st, persist=persist2)
        sim2.boot()
        assert sim2.preset == 1
        line1, _ = sim2.render()
        assert line1 == "Volume:        B"


def test_fresh_eeprom_defaults_to_preset_a(patched_control_hex) -> None:
    """Fresh 0xFF EEPROM defaults to preset A."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    persist = ControlPersistentState()
    # All 0xFF — simulates blank EEPROM
    assert persist.eeprom[0x74] == 0xFF
    sim = ControlUISim(st=st, persist=persist)
    sim.boot()
    assert sim.preset == 0
    line1, _ = sim.render()
    assert line1 == "Volume:        A"


def test_volume_resets_on_power_cycle(patched_control_hex) -> None:
    """Volume is volatile — it resets to default (0x33) on power cycle."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    # Change volume
    sim.press("U")
    sim.press("U")
    sim.press("U")
    assert sim.volume_steps == 0x36

    sim2 = sim.power_cycle()
    assert sim2.volume_steps == 0x33


def test_preset_selection_is_idempotent(patched_control_hex) -> None:
    """Selecting already-active preset should not emit duplicate frames."""
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R"])  # Volume -> Preset

    # Already in A; UP should be no-op.
    sim.press("U")
    assert sim.preset == 0
    assert sim.tx_frames == []

    # Switch to B once, then press DOWN again (no-op).
    sim.press("D")
    sim.press("D")
    assert sim.preset == 1
    assert sim.tx_frames == [SerialFrame(route=0xB0, cmd=0x20, data=0x01)]
