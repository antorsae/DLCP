"""Simulator/model validation for MAIN DSP filename command/storage behavior."""

from __future__ import annotations

from pathlib import Path

from dlcp_fw.sim.main_model import MainUnitModel


ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_DISASM = ROOT / "firmware" / "disasm" / "main" / "gpdasm_output.asm"


def _encode_filename_payload(name: str) -> bytes:
    raw = name.encode("ascii")
    raw = raw[:30]
    return raw + (b"\x00" * (30 - len(raw)))


def _decode_filename_slot(slot: bytes) -> str:
    out = bytearray()
    for b in slot[:30]:
        if b in (0x00, 0xFF):
            break
        out.append(b)
    return out.decode("ascii")


def _changed_offsets(before: bytes, after: bytes) -> list[int]:
    return [i for i, (a, b) in enumerate(zip(before, after)) if a != b]


def test_cmd03_filename_roundtrip_and_command_log(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)

    names = [
        "A",
        "LX521.4 22MG10F-v5",
        "123456789012345678901234567890",  # exactly 30 chars
        "filename-over-thirty-characters-gets-trimmed",
    ]
    for name in names:
        payload = _encode_filename_payload(name)
        m.usb_cmd03(0x09, payload)
        out = m.usb_cmd03(0x08)
        assert _decode_filename_slot(out) == name[:30]

    assert len(m.usb_cmd03_log) == len(names) * 2
    assert all(evt.subcmd in (0x08, 0x09) for evt in m.usb_cmd03_log)


def test_filename_persist_writes_only_eeprom_60_7d(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)

    before = bytes(m.eeprom)
    m.usb_cmd03(0x09, _encode_filename_payload("DSP-A"))
    assert m.filename_dirty is True
    assert m.persist_dirty_filename_to_eeprom() is True
    after = bytes(m.eeprom)
    changed = _changed_offsets(before, after)
    assert changed
    assert all(0x60 <= addr <= 0x7E for addr in changed)
    assert after[0x60:0x7E] == m.filename_ram_bytes()
    assert after[0x7E] == ((before[0x7E] + 1) & 0x7F)

    # No second write when dirty flag is clear.
    after_once = bytes(m.eeprom)
    assert m.persist_dirty_filename_to_eeprom() is False
    assert bytes(m.eeprom) == after_once


def test_filename_persist_targets_active_preset_bank(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    before_gen_a = m.filename_generation(0)
    before_gen_b = m.filename_generation(1)

    # Preset A path -> EEPROM 0x60..0x7D.
    m.usb_cmd03(0x09, _encode_filename_payload("A-NAME"))
    assert m.persist_dirty_filename_to_eeprom() is True
    slot_a = m.filename_eeprom_bytes(0)
    assert _decode_filename_slot(slot_a) == "A-NAME"
    gen_a = m.filename_generation(0)
    assert gen_a == ((before_gen_a + 1) & 0x7F)
    assert m.filename_generation(1) == before_gen_b

    # Switch preset (simulates cmd=0x20 apply path) and write B.
    m.set_preset(1)
    m.usb_cmd03(0x09, _encode_filename_payload("B-NAME"))
    assert m.persist_dirty_filename_to_eeprom() is True
    slot_b = m.filename_eeprom_bytes(1)
    assert _decode_filename_slot(slot_b) == "B-NAME"
    gen_b = m.filename_generation(1)
    assert gen_b == ((before_gen_b + 1) & 0x7F)

    # A/B EEPROM slots must remain isolated.
    assert _decode_filename_slot(m.filename_eeprom_bytes(0)) == "A-NAME"
    assert _decode_filename_slot(m.filename_eeprom_bytes(1)) == "B-NAME"
    assert m.filename_generation(0) == gen_a

    # Preset switch reloads active slot into RAM.
    m.set_preset(0)
    assert _decode_filename_slot(m.filename_ram_bytes()) == "A-NAME"
    m.set_preset(1)
    assert _decode_filename_slot(m.filename_ram_bytes()) == "B-NAME"


def test_boot_reload_and_erase_semantics(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)

    name = "RebootCheck-v7"
    m.usb_cmd03(0x09, _encode_filename_payload(name))
    m.persist_dirty_filename_to_eeprom()

    # Corrupt RAM slot, then emulate boot reload from EEPROM.
    m.ram[m._FILENAME_RAM_BASE : m._FILENAME_RAM_BASE + m._FILENAME_LEN] = b"\x00" * 30
    assert _decode_filename_slot(m.filename_ram_bytes()) == ""
    m.boot_load_filename_from_eeprom()
    assert _decode_filename_slot(m.filename_ram_bytes()) == name

    # Erase command should clear slot to 0xFF and persist.
    m.usb_cmd03(0x0A, b"")
    assert m.filename_ram_bytes() == bytes([0xFF] * 30)
    assert m.persist_dirty_filename_to_eeprom() is True
    assert m.eeprom[0x60:0x7E] == bytes([0xFF] * 30)


def test_boot_reload_clears_volatile_dirty_latch(patched_main_hex: Path) -> None:
    """
    Simulated reboot must clear cmd03 dirty state, matching boot RAM reload semantics.
    """
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    baseline = bytes(m.eeprom)

    m.usb_cmd03(0x09, _encode_filename_payload("VOLATILE-DIRTY"))
    assert m.filename_dirty is True

    # Reboot before persisting: RAM is reloaded from EEPROM and dirty must clear.
    m.boot_load_filename_from_eeprom()
    assert m.filename_dirty is False
    assert bytes(m.eeprom) == baseline
    assert m.persist_dirty_filename_to_eeprom() is False
    assert bytes(m.eeprom) == baseline


def test_cmd21_emits_paged_display_chunk_frames(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    m.usb_cmd03(0x09, _encode_filename_payload("LX521.4 22MG10F-v5"))

    out0 = m.emit_filename_display_frames(0x00)  # page0
    out1 = m.emit_filename_display_frames(0x02)  # page1
    out2 = m.emit_filename_display_frames(0x04)  # page2
    out3 = m.emit_filename_display_frames(0x06)  # page3
    out = out0 + out1 + out2 + out3

    assert len(out0) == 9
    assert len(out1) == 9
    assert len(out2) == 9
    assert len(out3) == 7
    assert out[0].route == 0xBF
    assert out[0].cmd == 0x2F
    assert out[-1].cmd == 0x35
    assert [f.cmd for f in out0] == [0x2F] + list(range(0x30, 0x38))
    assert [f.cmd for f in out1] == [0x2F] + list(range(0x30, 0x38))
    assert [f.cmd for f in out2] == [0x2F] + list(range(0x30, 0x38))
    assert [f.cmd for f in out3] == [0x2F] + list(range(0x30, 0x36))
    chunk_out = [f for f in out if 0x30 <= f.cmd <= 0x37]
    line = bytes(f.data for f in chunk_out).decode("ascii", "replace")
    assert line == "LX521.4 22MG10F-v5" + (" " * 12)

    # Full 30-byte names are returned untrimmed across pages.
    m.usb_cmd03(0x09, _encode_filename_payload("123456789012345678901234567890"))
    out_full = []
    for req in (0x00, 0x02, 0x04, 0x06):
        out_full.extend(m.emit_filename_display_frames(req))
    line2 = bytes(f.data for f in out_full if 0x30 <= f.cmd <= 0x37).decode("ascii", "replace")
    assert line2 == "123456789012345678901234567890"


def test_cmd22_emits_generation_metadata_and_persist_bumps_it(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    before = m.filename_generation(0)

    m.usb_cmd03(0x09, _encode_filename_payload("GEN-A"))
    assert m.persist_dirty_filename_to_eeprom() is True
    after = m.filename_generation(0)
    assert after == ((before + 1) & 0x7F)

    out = m.emit_filename_generation_frames(0x28)
    assert [f.cmd for f in out] == [0x2F, 0x22]
    assert out[0].data == 0x28
    assert out[1].data == after


def test_disasm_anchors_for_filename_paths() -> None:
    text = MAIN_DISASM.read_text(encoding="utf-8", errors="replace")

    # cmd=0x03 filename subcmd dispatch (0x09 write, 0x0A erase).
    assert "0010d8:  0a09  xorlw   0x09" in text
    assert "001108:  0a0a  xorlw   0x0a" in text

    # RAM filename slot base uses 0x02BE + idx(0x02..0x1F) => 0x02C0..0x02DD.
    assert "0010e8:  0ebe  movlw   0xbe" in text
    assert "001100:  6458  cpfsgt  (Common_RAM + 88), A" in text
    assert "001116:  6458  cpfsgt  (Common_RAM + 88), A" in text

    # Dirty persist loop writes EEPROM 0x60..0x7D via function_094/function_110.
    assert "0027c0:  0e60  movlw   0x60" in text
    assert "0027e2:  0e7d  movlw   0x7d" in text
    assert "function_094:                                               ; address: 0x0046de" in text
    assert "function_110:                                               ; address: 0x004884" in text
