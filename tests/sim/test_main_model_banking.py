from __future__ import annotations

from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.protocol import SerialFrame
from dlcp_fw.sim.scenarios import build_payload


def test_bank_mapping_and_flash_write_log(patched_main_hex) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    payload_a = build_payload(0x11)
    payload_b = build_payload(0x7C)

    m.set_preset(0)
    m.upload_hfd_table(payload_a)
    digest_a = m.table_digest(0x5600)
    assert len(m.flash_writes) == 0xA00
    assert all(e.physical_addr >= 0x5600 for e in m.flash_writes[:16])

    m.flash_writes.clear()
    m.set_preset(1)
    m.upload_hfd_table(payload_b)
    digest_b = m.table_digest(0x4A00)
    assert len(m.flash_writes) == 0xA00
    assert all(0x4A00 <= e.physical_addr <= 0x53FF for e in m.flash_writes[:64])

    assert digest_a != digest_b
    assert len(m.dsp_ingest) >= 1
    assert m.dsp_ingest[-1].table_base == 0x4A00


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
