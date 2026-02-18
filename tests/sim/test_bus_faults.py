from __future__ import annotations

from dlcp_fw.sim.bus import CurrentLoopBus, FaultProfile
from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.protocol import SerialFrame


def _make_bus(patched_main_hex, fault: FaultProfile) -> tuple[CurrentLoopBus, MainUnitModel, MainUnitModel]:
    left = MainUnitModel.from_hex("left", 1, patched_main_hex)
    right = MainUnitModel.from_hex("right", 2, patched_main_hex)
    return CurrentLoopBus(mains=[left, right], fault=fault), left, right


def test_drop_frame_fault(patched_main_hex) -> None:
    bus, left, right = _make_bus(patched_main_hex, FaultProfile(drop_indices={0}))
    handled = bus.deliver(0, SerialFrame(route=0xB0, cmd=0x20, data=1))
    assert handled == []
    assert left.preset_idx == 0
    assert right.preset_idx == 0


def test_duplicate_frame_fault(patched_main_hex) -> None:
    bus, left, right = _make_bus(patched_main_hex, FaultProfile(duplicate_indices={0}))
    handled = bus.deliver(0, SerialFrame(route=0xB0, cmd=0x20, data=1))
    assert handled.count("left") == 2
    assert handled.count("right") == 2
    # MAIN cmd=0x20 is idempotent: duplicate "set B" should not re-apply DSP.
    assert left.apply_count == 1
    assert right.apply_count == 1
    assert left.preset_idx == 1
    assert right.preset_idx == 1


def test_corrupt_faults_are_ignored(patched_main_hex) -> None:
    bus, left, right = _make_bus(
        patched_main_hex, FaultProfile(corrupt_cmd_indices={0}, corrupt_route_indices={1})
    )
    assert bus.deliver(0, SerialFrame(route=0xB0, cmd=0x20, data=1)) == []
    assert bus.deliver(1, SerialFrame(route=0xB0, cmd=0x20, data=1)) == []
    assert left.preset_idx == 0
    assert right.preset_idx == 0
