"""Firmware version label consistency tests.

The DLCP firmware reports its version to HFD via two mechanisms:
1. USB HID cmd 0x06 response: bytes at ram_0x15B/15C/15D (hardcoded in code)
   - Format: [flag, major, minor] — HFD displays as "vMAJOR.MINOR"
2. EEPROM offset 0x80-0x82: [major, minor, patch] — secondary/backup

These tests verify BOTH are consistent with the intended firmware label.
They parse the HEX file statically (no gpsim needed).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from intelhex import IntelHex

from dlcp_fw.paths import (
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V26,
    PATCHED_MAIN_HEX_V27,
    STOCK_MAIN_HEX,
    V30_MAIN_HEX,
    V31_MAIN_HEX,
)


def _skip_missing(p: Path) -> None:
    if not p.exists():
        pytest.skip(f"missing: {p.name}")


def _read_eeprom_version(hex_path: Path) -> tuple[int, int, int]:
    """Read EEPROM version tuple at offset 0x80-0x82."""
    ih = IntelHex(str(hex_path))
    base = 0xF00000
    return (ih[base + 0x80], ih[base + 0x81], ih[base + 0x82])


def _find_hid_version_bytes(hex_path: Path) -> tuple[int, int, int] | None:
    """Find the HID cmd 0x06 version response bytes in program memory.

    PIC18 little-endian instruction encoding:
        movlw  FLAG  → [FLAG, 0x0E]
        movlb  0x1   → [0x01, 0x01]
        movwf  0x5B  → [0x5B, 0x6F]  (BANKED)
        movlw  MAJOR → [MAJOR, 0x0E]
        movwf  0x5C  → [0x5C, 0x6F]
        movlw  MINOR → [MINOR, 0x0E]
        movwf  0x5D  → [0x5D, 0x6F]

    Total: 14 bytes. We match the fixed bytes and extract the literals.
    """
    ih = IntelHex(str(hex_path))
    for addr in range(0x1000, 0x5600, 2):
        # Match: movlw ?; movlb 1; movwf 0x5B; movlw ?; movwf 0x5C; movlw ?; movwf 0x5D
        if (ih[addr + 1] == 0x0E and          # movlw FLAG
                ih[addr + 2] == 0x01 and ih[addr + 3] == 0x01 and  # movlb 0x1
                ih[addr + 4] == 0x5B and ih[addr + 5] == 0x6F and  # movwf 0x5B
                ih[addr + 7] == 0x0E and                            # movlw MAJOR
                ih[addr + 8] == 0x5C and ih[addr + 9] == 0x6F and  # movwf 0x5C
                ih[addr + 11] == 0x0E and                           # movlw MINOR
                ih[addr + 12] == 0x5D and ih[addr + 13] == 0x6F):  # movwf 0x5D
            flag = ih[addr]      # movlw literal byte
            major = ih[addr + 6]
            minor = ih[addr + 10]
            return (flag, major, minor)
    return None


# ---- USB HID version (what HFD actually displays) ----

_HID_VERSION_CASES = [
    pytest.param(STOCK_MAIN_HEX, 0x02, 0x03, "2.3", id="v23_stock"),
    pytest.param(V31_MAIN_HEX, 0x03, 0x01, "3.1", id="v31"),
]


@pytest.mark.parametrize("hex_path, expected_major, expected_minor, label", _HID_VERSION_CASES)
def test_usb_hid_version_matches_label(
    hex_path: Path, expected_major: int, expected_minor: int, label: str,
) -> None:
    """USB HID cmd 0x06 response must report the correct firmware version.

    HFD reads the version from this response. If the hardcoded bytes
    are wrong, HFD displays the wrong version (e.g. V3.1 showing as v2.3).
    """
    _skip_missing(hex_path)
    result = _find_hid_version_bytes(hex_path)
    assert result is not None, (
        f"Could not find HID version pattern in {hex_path.name}"
    )
    flag, major, minor = result
    assert major == expected_major and minor == expected_minor, (
        f"USB HID version mismatch for {label}: "
        f"HEX has major=0x{major:02X} minor=0x{minor:02X}, "
        f"expected major=0x{expected_major:02X} minor=0x{expected_minor:02X}"
    )


def test_v31_usb_version_not_stock() -> None:
    """V3.1 USB HID version must differ from stock V2.3."""
    _skip_missing(V31_MAIN_HEX)
    _skip_missing(STOCK_MAIN_HEX)

    stock = _find_hid_version_bytes(STOCK_MAIN_HEX)
    v31 = _find_hid_version_bytes(V31_MAIN_HEX)
    assert stock is not None and v31 is not None

    assert v31[1:] != stock[1:], (
        f"V3.1 USB version is still stock: "
        f"major=0x{v31[1]:02X} minor=0x{v31[2]:02X}"
    )


# ---- EEPROM version (secondary) ----

_EEPROM_VERSION_CASES = [
    pytest.param(STOCK_MAIN_HEX, (0x02, 0x03, 0x30), "2.3", id="v23_stock"),
    pytest.param(V31_MAIN_HEX, (0x03, 0x01, 0x31), "3.1", id="v31"),
]


@pytest.mark.parametrize("hex_path, expected_tuple, label", _EEPROM_VERSION_CASES)
def test_eeprom_version_matches_label(
    hex_path: Path, expected_tuple: tuple[int, int, int], label: str,
) -> None:
    """EEPROM version tuple must match the firmware label."""
    _skip_missing(hex_path)
    actual = _read_eeprom_version(hex_path)
    assert actual == expected_tuple, (
        f"EEPROM version mismatch for {label}: "
        f"got (0x{actual[0]:02X}, 0x{actual[1]:02X}, 0x{actual[2]:02X}), "
        f"expected (0x{expected_tuple[0]:02X}, 0x{expected_tuple[1]:02X}, "
        f"0x{expected_tuple[2]:02X})"
    )
