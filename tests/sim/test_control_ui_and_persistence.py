from __future__ import annotations

import tempfile
from pathlib import Path

from dlcp_fw.sim.control_ui import ControlPersistentState, ControlStrings, ControlUISim
from dlcp_fw.sim.protocol import SerialFrame

import pytest

# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


def _preset_frames(sim: ControlUISim) -> list[SerialFrame]:
    return [f for f in sim.tx_frames if f.route == 0xB0 and f.cmd == 0x20]


def test_preset_screen_navigation(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    l1, l2 = sim.render()
    assert l1 == "Volume:        A"
    assert "dB" in l2

    sim.press("R")
    l1, l2 = sim.render()
    assert l1 == "Preset          "
    assert l2 == "Active: A       "

    sim.press("D")
    l1, l2 = sim.render()
    assert sim.preset == 1
    assert l1 == "Preset          "
    assert l2 == "Active: B       "

    sim.press("L")
    l1, _ = sim.render()
    assert l1 == "Volume:        B"


def test_keypress_script_emits_immediate_and_queued_preset_frames(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    assert sim.retry_budget == 3

    sim.run_script(["R", "D"])
    preset_frames = _preset_frames(sim)
    assert preset_frames == [SerialFrame(route=0xB0, cmd=0x20, data=0x01)]
    assert sim.retry_budget == 2

    sim.service_full_sync(connected=True)
    sim.service_full_sync(connected=True)
    sim.service_full_sync(connected=True)
    preset_frames = _preset_frames(sim)
    assert preset_frames == [
        SerialFrame(route=0xB0, cmd=0x20, data=0x01),
        SerialFrame(route=0xB0, cmd=0x20, data=0x01),
        SerialFrame(route=0xB0, cmd=0x20, data=0x01),
    ]
    assert sim.retry_budget == 0


def test_four_screen_wraparound(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    assert sim.menu_state == 0
    sim.press("R")
    assert sim.menu_state == 1
    sim.press("R")
    assert sim.menu_state == 2
    sim.press("R")
    assert sim.menu_state == 3
    sim.press("R")
    assert sim.menu_state == 0

    sim.press("L")
    assert sim.menu_state == 3
    sim.press("L")
    assert sim.menu_state == 2
    sim.press("L")
    assert sim.menu_state == 1
    sim.press("L")
    assert sim.menu_state == 0


def test_power_cycle_persists_last_preset(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R", "D"])
    assert sim.preset == 1
    assert sim.persist.load_preset() == 1
    assert sim.persist.eeprom[0x74] == 1

    sim2 = sim.power_cycle()
    assert sim2.preset == 1
    assert sim2.retry_budget == 3
    line1, _ = sim2.render()
    assert line1 == "Volume:        B"


def test_eeprom_file_roundtrip(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.run_script(["R", "D"])

    with tempfile.TemporaryDirectory() as td:
        eeprom_path = Path(td) / "eeprom.bin"
        sim.persist.save_to_file(eeprom_path)

        persist2 = ControlPersistentState()
        persist2.load_from_file(eeprom_path)
        sim2 = ControlUISim(st=st, persist=persist2)
        sim2.boot()
        assert sim2.preset == 1
        assert sim2.render()[0] == "Volume:        B"


def test_fresh_eeprom_defaults_to_preset_a(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    persist = ControlPersistentState()
    sim = ControlUISim(st=st, persist=persist)
    sim.boot()
    assert sim.preset == 0
    assert sim.render()[0] == "Volume:        A"


def test_volume_resets_on_power_cycle(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.press("U")
    sim.press("U")
    sim.press("U")
    assert sim.volume_steps == 0x36

    sim2 = sim.power_cycle()
    assert sim2.volume_steps == 0x33


def test_preset_selection_is_idempotent(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()
    sim.press("R")

    assert _preset_frames(sim) == []
    sim.press("U")
    assert sim.preset == 0
    assert _preset_frames(sim) == []

    sim.press("D")
    sim.press("D")
    assert sim.preset == 1
    assert _preset_frames(sim) == [SerialFrame(route=0xB0, cmd=0x20, data=0x01)]


def test_boot_and_reconnect_queue_three_bounded_retries(patched_control_hex) -> None:
    st = ControlStrings.from_hex_path(patched_control_hex)
    sim = ControlUISim(st=st)
    sim.boot()

    for _ in range(5):
        sim.service_full_sync(connected=True)
    assert _preset_frames(sim) == [
        SerialFrame(route=0xB0, cmd=0x20, data=0x00),
        SerialFrame(route=0xB0, cmd=0x20, data=0x00),
        SerialFrame(route=0xB0, cmd=0x20, data=0x00),
    ]
    assert sim.retry_budget == 0

    sim.service_full_sync(connected=False)
    assert sim.retry_budget == 0
    sim.service_full_sync(connected=True)
    assert sim.retry_budget == 2
    for _ in range(4):
        sim.service_full_sync(connected=True)
    assert _preset_frames(sim)[-3:] == [
        SerialFrame(route=0xB0, cmd=0x20, data=0x00),
        SerialFrame(route=0xB0, cmd=0x20, data=0x00),
        SerialFrame(route=0xB0, cmd=0x20, data=0x00),
    ]
    assert sim.retry_budget == 0
