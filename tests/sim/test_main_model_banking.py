from __future__ import annotations

from dlcp_fw.sim.main_model import MainUnitModel
from dlcp_fw.sim.scenarios import build_payload
from dlcp_fw.sim.protocol import SerialFrame


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


def test_cmd21_emits_filename_chunks_without_dsp_apply(patched_main_hex) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    base = b"DSP-FILE-XYZ"
    m.usb_cmd03(0x09, base + (b"\x00" * (30 - len(base))))

    assert m.apply_count == 0
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x21, data=0x00)) is True
    assert m.apply_count == 0
    assert len(m.tx_frames) == 9
    assert [f.cmd for f in m.tx_frames] == [0x2F] + list(range(0x30, 0x38))
    assert m.tx_frames[0].data == 0x00

    # Page 3 (data bits2:1=3 -> 0x06) returns tail idx 24..29 (6 bytes).
    m.tx_frames.clear()
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x21, data=0x06)) is True
    assert len(m.tx_frames) == 7
    assert [f.cmd for f in m.tx_frames] == [0x2F] + list(range(0x30, 0x36))
    assert m.tx_frames[0].data == 0x06

    # cmd=0x22 returns generation metadata only (context + generation byte).
    m.tx_frames.clear()
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x22, data=0x10)) is True
    assert m.apply_count == 0
    assert [f.cmd for f in m.tx_frames] == [0x2F, 0x22]
    assert m.tx_frames[0].data == 0x10

    # Duplicate "set preset B" must not trigger extra table apply.
    assert m.process_frame(SerialFrame(route=0xB0, cmd=0x20, data=0x01)) is True
    assert m.preset_idx == 1
    assert m.apply_count == 1
    assert len(m.dsp_ingest) == 1
