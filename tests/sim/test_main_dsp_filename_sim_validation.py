from __future__ import annotations

from pathlib import Path

from dlcp_fw.sim.main_model import MainUnitModel


ROOT = Path(__file__).resolve().parent.parent.parent
MAIN_DISASM = ROOT / "firmware" / "disasm" / "main" / "gpdasm_output.asm"


def _encode_filename_payload(name: str) -> bytes:
    raw = name.encode("ascii", errors="ignore")[:30]
    return raw + (b"\x00" * (30 - len(raw)))


def _decode_filename_slot(slot: bytes) -> str:
    chars = []
    for b in slot[:30]:
        if b in (0x00, 0xFF):
            break
        chars.append(chr(b))
    return "".join(chars)


def test_cmd03_filename_roundtrip_and_command_log(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    names = ["LX521.4 22MG10F-v5", "AB", "123456789012345678901234567890"]

    for name in names:
        payload = _encode_filename_payload(name)
        m.usb_cmd03(0x09, payload)
        out = m.usb_cmd03(0x08)
        assert _decode_filename_slot(out) == name[:30]

    assert len(m.usb_cmd03_log) == len(names) * 2
    assert all(evt.subcmd in (0x08, 0x09) for evt in m.usb_cmd03_log)


def test_filename_persist_writes_only_eeprom_60_7e(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    before = bytes(m.eeprom)

    m.usb_cmd03(0x09, _encode_filename_payload("DSP-A"))
    assert m.filename_dirty is True
    assert m.persist_dirty_filename_to_eeprom() is True
    after = bytes(m.eeprom)

    changed = {idx for idx, (b, a) in enumerate(zip(before, after)) if b != a}
    assert changed.issubset(set(range(0x60, 0x7F)))
    assert 0x7E in changed
    assert after[0x60:0x7E] == m.filename_ram_bytes()
    assert (after[0x7E] & 0x7F) == ((before[0x7E] + 1) & 0x7F)
    assert m.persist_dirty_filename_to_eeprom() is False


def test_boot_load_restores_filename_from_single_persisted_slot(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    name = "BOOT-RESTORE-NAME"

    m.usb_cmd03(0x09, _encode_filename_payload(name))
    m.persist_dirty_filename_to_eeprom()
    m.ram[0x2C0 : 0x2C0 + 30] = b"\xFF" * 30

    assert _decode_filename_slot(m.filename_ram_bytes()) == ""
    m.boot_load_filename_from_eeprom()
    assert _decode_filename_slot(m.filename_ram_bytes()) == name


def test_cmd03_erase_clears_slot_and_persists_blank(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    m.usb_cmd03(0x09, _encode_filename_payload("VOLATILE"))
    m.persist_dirty_filename_to_eeprom()

    m.usb_cmd03(0x0A, b"")
    assert m.filename_ram_bytes() == bytes([0xFF] * 30)
    assert m.persist_dirty_filename_to_eeprom() is True
    assert m.filename_eeprom_bytes() == bytes([0xFF] * 30)


def test_boot_load_clears_volatile_dirty_state(patched_main_hex: Path) -> None:
    m = MainUnitModel.from_hex("main", 1, patched_main_hex)
    m.usb_cmd03(0x09, _encode_filename_payload("VOLATILE-DIRTY"))
    assert m.filename_dirty is True

    m.boot_load_filename_from_eeprom()
    assert m.filename_dirty is False
    assert m.persist_dirty_filename_to_eeprom() is False


def test_disasm_anchors_for_cmd03_paths_remain_present() -> None:
    text = MAIN_DISASM.read_text(encoding="utf-8", errors="replace")
    assert "function_003:" in text
    assert "label_003:" in text
    assert "0010d0:  c11b  movff   0x11b, 0x097" in text
    assert "0020be:  0e60  movlw   0x60" in text
    assert "0027c0:  0e60  movlw   0x60" in text
