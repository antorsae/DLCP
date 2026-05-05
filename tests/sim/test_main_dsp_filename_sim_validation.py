from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.sim.main_model import MainUnitModel


# All tests in this module are backend-agnostic (Python-level
# behavioral models, hex/source byte comparisons, flash-tool plumbing,
# scenario runners).  No gpsim runtime, no rust facade.
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


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


def _fixture_hex(request: pytest.FixtureRequest, fixture_name: str) -> Path:
    return request.getfixturevalue(fixture_name)


@pytest.mark.parametrize(
    "main_hex_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_cmd03_filename_roundtrip_tracks_active_preset(
    request: pytest.FixtureRequest,
    main_hex_fixture: str,
) -> None:
    m = MainUnitModel.from_hex("main", 1, _fixture_hex(request, main_hex_fixture))

    m.usb_cmd03(0x09, _encode_filename_payload("ALPHA-A"))
    assert _decode_filename_slot(m.usb_cmd03(0x08)) == "ALPHA-A"
    assert m.persist_dirty_filename_to_eeprom() is True
    assert _decode_filename_slot(m.filename_eeprom_bytes(0)) == "ALPHA-A"

    m.set_preset(1)
    assert _decode_filename_slot(m.usb_cmd03(0x08)) == ""

    m.usb_cmd03(0x09, _encode_filename_payload("BRAVO-B"))
    assert _decode_filename_slot(m.usb_cmd03(0x08)) == "BRAVO-B"
    assert m.persist_dirty_filename_to_eeprom() is True
    assert _decode_filename_slot(m.filename_eeprom_bytes(1)) == "BRAVO-B"

    m.set_preset(0)
    assert _decode_filename_slot(m.usb_cmd03(0x08)) == "ALPHA-A"
    m.set_preset(1)
    assert _decode_filename_slot(m.usb_cmd03(0x08)) == "BRAVO-B"

    assert all(evt.subcmd in (0x08, 0x09) for evt in m.usb_cmd03_log)


@pytest.mark.parametrize(
    "main_hex_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_filename_persist_writes_only_active_preset_slot(
    request: pytest.FixtureRequest,
    main_hex_fixture: str,
) -> None:
    m = MainUnitModel.from_hex("main", 1, _fixture_hex(request, main_hex_fixture))

    before = bytes(m.eeprom)
    m.usb_cmd03(0x09, _encode_filename_payload("PRESET-A"))
    assert m.persist_dirty_filename_to_eeprom() is True
    after_a = bytes(m.eeprom)
    changed_a = {idx for idx, (b, a) in enumerate(zip(before, after_a)) if b != a}
    assert changed_a.issubset(set(range(0x60, 0x7E)))
    assert _decode_filename_slot(after_a[0x60:0x7E]) == "PRESET-A"
    assert set(after_a[0x83:0xA1]) == {0xFF}

    m.set_preset(1)
    m.usb_cmd03(0x09, _encode_filename_payload("PRESET-B"))
    assert m.persist_dirty_filename_to_eeprom() is True
    after_b = bytes(m.eeprom)
    changed_b = {idx for idx, (b, a) in enumerate(zip(after_a, after_b)) if b != a}
    assert changed_b.issubset(set(range(0x83, 0xA1)))
    assert _decode_filename_slot(after_b[0x60:0x7E]) == "PRESET-A"
    assert _decode_filename_slot(after_b[0x83:0xA1]) == "PRESET-B"


@pytest.mark.parametrize(
    "main_hex_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_preset_switch_flushes_dirty_outgoing_slot_and_loads_incoming_slot(
    request: pytest.FixtureRequest,
    main_hex_fixture: str,
) -> None:
    m = MainUnitModel.from_hex("main", 1, _fixture_hex(request, main_hex_fixture))

    m.usb_cmd03(0x09, _encode_filename_payload("ALPHA"))
    m.persist_dirty_filename_to_eeprom()
    m.set_preset(1)

    m.usb_cmd03(0x09, _encode_filename_payload("BRAVO"))
    assert m.filename_dirty is True
    m.set_preset(0)

    assert m.filename_dirty is False
    assert _decode_filename_slot(m.filename_eeprom_bytes(1)) == "BRAVO"
    assert _decode_filename_slot(m.filename_ram_bytes()) == "ALPHA"

    m.set_preset(1)
    assert _decode_filename_slot(m.filename_ram_bytes()) == "BRAVO"


@pytest.mark.parametrize(
    "main_hex_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_cmd03_erase_is_active_preset_local(
    request: pytest.FixtureRequest,
    main_hex_fixture: str,
) -> None:
    m = MainUnitModel.from_hex("main", 1, _fixture_hex(request, main_hex_fixture))

    m.usb_cmd03(0x09, _encode_filename_payload("ALPHA"))
    m.persist_dirty_filename_to_eeprom()
    m.set_preset(1)
    m.usb_cmd03(0x09, _encode_filename_payload("BRAVO"))
    m.persist_dirty_filename_to_eeprom()

    m.usb_cmd03(0x0A, b"")
    assert m.filename_ram_bytes() == bytes([0xFF] * 30)
    assert m.persist_dirty_filename_to_eeprom() is True

    assert _decode_filename_slot(m.filename_eeprom_bytes(0)) == "ALPHA"
    assert m.filename_eeprom_bytes(1) == bytes([0xFF] * 30)


@pytest.mark.parametrize(
    "main_hex_fixture",
    [
        pytest.param("patched_main_hex_v24", id="v24"),
        pytest.param("patched_main_hex", id="v25"),
    ],
)
def test_boot_load_defaults_to_a_and_switch_restores_b_slot(
    request: pytest.FixtureRequest,
    main_hex_fixture: str,
) -> None:
    m = MainUnitModel.from_hex("main", 1, _fixture_hex(request, main_hex_fixture))

    m.usb_cmd03(0x09, _encode_filename_payload("ALPHA"))
    m.persist_dirty_filename_to_eeprom()
    m.set_preset(1)
    m.usb_cmd03(0x09, _encode_filename_payload("BRAVO"))
    m.persist_dirty_filename_to_eeprom()

    m.ram[0x2C0 : 0x2C0 + 30] = b"\xFF" * 30
    m.preset_idx = 0
    m.boot_load_filename_from_eeprom()
    assert _decode_filename_slot(m.filename_ram_bytes()) == "ALPHA"

    m.set_preset(1)
    assert _decode_filename_slot(m.filename_ram_bytes()) == "BRAVO"


def test_disasm_anchors_for_cmd03_paths_remain_present() -> None:
    text = MAIN_DISASM.read_text(encoding="utf-8", errors="replace")
    assert "function_003:" in text
    assert "label_003:" in text
    assert "0010d0:  c11b  movff   0x11b, 0x097" in text
    assert "0020be:  0e60  movlw   0x60" in text
    assert "0027c0:  0e60  movlw   0x60" in text
