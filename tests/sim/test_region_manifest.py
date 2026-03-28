"""Tests for the stock address space region manifest."""

from __future__ import annotations

from dlcp_fw.asm.region_manifest import classify_address


def test_manifest_covers_full_stock_range():
    for addr in range(0x1000, 0x6000):
        assert classify_address(addr) in ("code", "data", "erased")


def test_manifest_usb_data_boundary():
    for addr in range(0x1018, 0x10AC):
        assert classify_address(addr) == "data"
    assert classify_address(0x10AC) == "code"


def test_manifest_inline_data_0x47E6():
    """Inline data table at 0x47E6-0x47FB must be classified as data."""
    for addr in range(0x47E6, 0x47FC):
        assert classify_address(addr) == "data"


def test_manifest_preset_table():
    for addr in range(0x5600, 0x6000):
        assert classify_address(addr) == "data"


def test_manifest_erased():
    for addr in range(0x4970, 0x5600):
        assert classify_address(addr) == "erased"


def test_manifest_known_code():
    for addr in [0x1000, 0x10AC, 0x18F2, 0x2D8C, 0x4896]:
        assert classify_address(addr) == "code"


def test_manifest_entry_stub_is_code():
    """0x1000-0x1017 is app entry + ISR dispatch stubs."""
    for addr in range(0x1000, 0x1018):
        assert classify_address(addr) == "code"


def test_manifest_code_after_inline_data():
    """Code resumes at 0x47FC after inline data."""
    assert classify_address(0x47FC) == "code"
