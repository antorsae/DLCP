"""USB HID, preset A/B, and config name tests for V3.1.

Tests USB config upload, preset flash isolation, config name round-trips,
and delayed-switch detection across V2.4, V2.8, and V3.1.
"""
from __future__ import annotations

from pathlib import Path

import pytest

# Pure source / hex tests -- no sim backend needed.
pytestmark = pytest.mark.dual_supported


from dlcp_fw.paths import (
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V28,
    V31_MAIN_ASM,
    V31_MAIN_HEX,
)
from dlcp_fw.sim.main_model import MainUnitModel


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


def _build_payload(fill: int) -> bytes:
    """Build a 0xA00-byte payload with a recognizable pattern."""
    return bytes([(fill + i) & 0xFF for i in range(0xA00)])


def _encode_filename(name: str) -> bytes:
    raw = name.encode("ascii", errors="ignore")[:30]
    return raw + (b"\x00" * (30 - len(raw)))


def _decode_filename(resp: bytes) -> str:
    return resp.rstrip(b"\x00\xFF").decode("ascii", errors="replace")


# ---- Version-parametrized fixtures ----

_PRESET_VERSIONS = [
    pytest.param(PATCHED_MAIN_HEX_V24, 0x4A00, 0x0C00, id="v24"),
    pytest.param(PATCHED_MAIN_HEX_V28, 0x4A00, 0x0C00, id="v28"),
    pytest.param(V31_MAIN_HEX, 0x4C00, 0x0A00, id="v31"),
]


# ===================================================================
# Test 1: Static V3.1 remap guard
# ===================================================================


def test_v31_static_remap_constants() -> None:
    """V3.1 ASM must keep the 0x4C00 layout and delayed preset helper."""
    _skip_missing(V31_MAIN_ASM)
    text = V31_MAIN_ASM.read_text(encoding="utf-8", errors="replace")

    assert "org 0x4C00" in text, "preset B org 0x4C00 not found in V3.1 ASM"
    assert "preset_delay_150ms:" in text, "delayed preset helper label missing"
    delay_block = text[text.index("preset_delay_150ms:") : text.index("preset_force_mute:")]
    assert "movlw       0x96" in delay_block, "150 ms literal missing from delayed preset helper"
    assert (
        "call        timer3_blocking_delay, 0x0" in delay_block
        or "rcall       timer3_blocking_delay" in delay_block
    ), "Timer3 delay call missing from delayed preset helper"

    for anchor in ("flash_read:", "flash_write:", "flash_erase:"):
        idx = text.index(anchor)
        block = text[idx : idx + 600]
        assert "movlw       0x0A" in block, (
            f"remap delta 0x0A not found near {anchor}"
        )
        assert "movlw       0x56" in block, (
            f"preset A high byte 0x56 check not found near {anchor}"
        )


# ===================================================================
# Test 2: Upload bank mapping — writes correct physical flash region
# ===================================================================


@pytest.mark.parametrize("hex_path, expected_b_base, delta", _PRESET_VERSIONS)
def test_upload_targets_correct_physical_bank(
    hex_path: Path, expected_b_base: int, delta: int,
) -> None:
    """USB config upload writes to the correct physical flash region.

    Preset A always at 0x5600. Preset B at version-specific base.
    """
    _skip_missing(hex_path)
    m = MainUnitModel.from_hex("main", 1, hex_path)

    payload_a = _build_payload(0x11)
    payload_b = _build_payload(0x7C)

    # Upload to preset A
    m.set_preset(0)
    m.upload_hfd_table(payload_a)
    assert bytes(m.flash[0x5600 : 0x5600 + 0xA00]) == payload_a

    # Upload to preset B
    m.flash_writes.clear()
    m.set_preset(1)
    m.upload_hfd_table(payload_b)

    assert bytes(m.flash[expected_b_base : expected_b_base + 0xA00]) == payload_b
    # Preset A should be untouched
    assert bytes(m.flash[0x5600 : 0x5600 + 0xA00]) == payload_a
    # First write should target the expected base
    assert m.flash_writes[0].physical_addr == expected_b_base


# ===================================================================
# Test 3: Preset A/B isolation — independent tables + correct re-apply
# ===================================================================


@pytest.mark.parametrize("hex_path, expected_b_base, delta", _PRESET_VERSIONS)
def test_preset_banks_isolated_and_switch_reapplies(
    hex_path: Path, expected_b_base: int, delta: int,
) -> None:
    """Writing to A and B produces independent flash regions.
    Switching preset triggers DSP re-apply from the correct bank."""
    _skip_missing(hex_path)
    m = MainUnitModel.from_hex("main", 1, hex_path)

    payload_a = _build_payload(0x11)
    payload_b = _build_payload(0x7C)

    m.set_preset(0)
    m.upload_hfd_table(payload_a)
    digest_a = m.table_digest(0x5600)

    m.set_preset(1)
    m.upload_hfd_table(payload_b)
    digest_b = m.table_digest(expected_b_base)

    assert digest_a != digest_b, "A and B payloads should differ"

    # Switch to A → DSP should ingest from 0x5600
    m.set_preset(0)
    assert m.dsp_ingest[-1].table_base == 0x5600
    assert m.dsp_ingest[-1].table_sha256 == digest_a

    # Switch to B → DSP should ingest from expected_b_base
    m.set_preset(1)
    assert m.dsp_ingest[-1].table_base == expected_b_base
    assert m.dsp_ingest[-1].table_sha256 == digest_b


# ===================================================================
# Test 4: Config name round-trip per preset
# ===================================================================


@pytest.mark.parametrize("hex_path, expected_b_base, delta", _PRESET_VERSIONS)
def test_config_name_roundtrip_per_preset(
    hex_path: Path, expected_b_base: int, delta: int,
) -> None:
    """Filenames are stored per-preset and survive switching.

    Write "ALPHA-A" on preset A, switch to B, write "BRAVO-B",
    switch back to A → "ALPHA-A" must be restored.
    """
    _skip_missing(hex_path)
    m = MainUnitModel.from_hex("main", 1, hex_path)

    m.set_preset(0)
    m.usb_cmd03(0x09, _encode_filename("ALPHA-A"))
    assert _decode_filename(m.usb_cmd03(0x08)) == "ALPHA-A"

    m.set_preset(1)
    m.usb_cmd03(0x09, _encode_filename("BRAVO-B"))
    assert _decode_filename(m.usb_cmd03(0x08)) == "BRAVO-B"

    # Switch back to A — must restore A's name
    m.set_preset(0)
    assert _decode_filename(m.usb_cmd03(0x08)) == "ALPHA-A"

    # Switch to B — must restore B's name
    m.set_preset(1)
    assert _decode_filename(m.usb_cmd03(0x08)) == "BRAVO-B"


# ===================================================================
# Test 5: Config name persists to correct EEPROM slot
# ===================================================================


@pytest.mark.parametrize("hex_path, expected_b_base, delta", _PRESET_VERSIONS)
def test_config_name_persists_to_correct_eeprom_slot(
    hex_path: Path, expected_b_base: int, delta: int,
) -> None:
    """Preset A name → EEPROM 0x60, preset B name → EEPROM 0x83."""
    _skip_missing(hex_path)
    m = MainUnitModel.from_hex("main", 1, hex_path)

    m.set_preset(0)
    m.usb_cmd03(0x09, _encode_filename("FILE-A"))

    m.set_preset(1)  # triggers persist of A's dirty filename
    m.usb_cmd03(0x09, _encode_filename("FILE-B"))

    m.set_preset(0)  # triggers persist of B's dirty filename

    # Check EEPROM slots
    ee_a = bytes(m.eeprom[0x60 : 0x60 + 6])
    ee_b = bytes(m.eeprom[0x83 : 0x83 + 6])
    assert ee_a == b"FILE-A", f"EEPROM A: {ee_a!r}"
    assert ee_b == b"FILE-B", f"EEPROM B: {ee_b!r}"


# ===================================================================
# Test 6: Model auto-detects preset B base from HEX
# ===================================================================


def test_model_autodetects_preset_b_base() -> None:
    """MainUnitModel.from_hex auto-detects the 0x4C00 preset-B layout."""
    _skip_missing(V31_MAIN_HEX)
    m = MainUnitModel.from_hex("main", 1, V31_MAIN_HEX)
    assert m._preset_b_base == 0x4C00, (
        f"V3.1 model detected preset B base 0x{m._preset_b_base:04X}, "
        f"expected 0x4C00"
    )
    assert m._preset_b_remap_delta == 0x0A00


def test_model_v24_uses_legacy_preset_b_base() -> None:
    """V2.4 model uses legacy 0x4A00 preset B base."""
    _skip_missing(PATCHED_MAIN_HEX_V24)
    m = MainUnitModel.from_hex("main", 1, PATCHED_MAIN_HEX_V24)
    assert m._preset_b_base == 0x4A00
    assert m._preset_b_remap_delta == 0x0C00


@pytest.mark.parametrize("hex_path", [PATCHED_MAIN_HEX_V28, V31_MAIN_HEX])
def test_delayed_preset_switch_enabled_for_v28_and_v31(hex_path: Path) -> None:
    _skip_missing(hex_path)
    m = MainUnitModel.from_hex("main", 1, hex_path)
    assert m.uses_delayed_preset_switch() is True
