from __future__ import annotations

from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.protocol import SerialFrame
from dlcp_fw.sim.scenarios import build_payload


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.  Mark the
# whole module dual_supported so DLCP_SIM_BACKEND={rust,dual} does
# not auto-skip them.
import pytest

pytestmark = pytest.mark.dual_supported


def test_bank_mapping_and_flash_write_log(patched_main_hex) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    payload_a = build_payload(0x11)
    payload_b = build_payload(0x7C)
    expected_b_base = m._preset_b_base

    m.set_preset(0)
    m.upload_hfd_table(payload_a)
    digest_a = m.table_digest(0x5600)
    assert len(m.flash_writes) == 0xA00
    assert all(e.physical_addr >= 0x5600 for e in m.flash_writes[:16])

    m.flash_writes.clear()
    m.set_preset(1)
    m.upload_hfd_table(payload_b)
    digest_b = m.table_digest(expected_b_base)
    assert len(m.flash_writes) == 0xA00
    assert all(expected_b_base <= e.physical_addr <= expected_b_base + 0x9FF for e in m.flash_writes[:64])

    assert digest_a != digest_b
    assert len(m.dsp_ingest) >= 1
    assert m.dsp_ingest[-1].table_base == expected_b_base


def test_repeated_preset_frame_is_idempotent_for_dsp_apply(patched_main_hex) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    assert m.preset_idx == 0
    assert m.apply_count == 0

    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x01)) is True
    assert m.preset_idx == 1
    assert m.apply_count == 1
    assert len(m.dsp_ingest) == 1

    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x01)) is True
    assert m.preset_idx == 1
    assert m.apply_count == 1
    assert len(m.dsp_ingest) == 1


def test_removed_filename_transport_commands_are_ignored(patched_main_hex) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x21, data=0x00)) is False
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x22, data=0x00)) is False
    assert m.apply_count == 0
    assert m.tx_frames == []


def test_delayed_preset_switch_temp_mutes_and_restores_on_v28_layout(patched_main_hex_v28) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex_v28)
    assert m.uses_delayed_preset_switch() is True
    assert m.muted is False

    m.set_preset(1)

    assert m.preset_idx == 1
    assert m.muted is False
    assert [event.kind for event in m.preset_switch_log] == [
        "mute_on",
        "delay_ms",
        "switch",
        "mute_off",
    ]
    assert m.preset_switch_log[1].value == 150


def test_delayed_preset_switch_preserves_existing_mute_on_v28_layout(patched_main_hex_v28) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex_v28)
    m.muted = True

    m.set_preset(1)

    assert m.preset_idx == 1
    assert m.muted is True
    assert [event.kind for event in m.preset_switch_log] == ["delay_ms", "switch"]
    assert m.preset_switch_log[0].value == 150
