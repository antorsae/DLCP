from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_MAIN_HEX,
    V31_DIAG_MEMREAD_USB_SAFE_HEX,
    V31_MAIN_ASM_CANONICAL,
    V31_MAIN_HEX_CANONICAL,
)
from dlcp_fw.patch import build_v31_diag_memread_usb_safe as builder
from dlcp_fw.sim.hexio import parse_intel_hex

pytestmark = pytest.mark.dual_supported


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            raise AssertionError(f"missing generated artifact: {p}")


def test_diag_memread_builder_rewrite_is_idempotent_on_canonical_v31() -> None:
    _skip_missing(V31_MAIN_ASM_CANONICAL)
    text = V31_MAIN_ASM_CANONICAL.read_text(encoding="utf-8", errors="replace")

    assert builder._rewrite_source(text) == text
    assert "hid_cmd_diag_memread:" in text
    assert text.index("goto        hid_cmd_diag_memread") < text.index("hid_cmd_diag_memread:")
    assert text.index("hid_cmd_diag_memread:") < text.index(builder._PRESET_TABLE_ANCHOR)


def test_canonical_v31_release_listing_contains_memread_dispatch_and_handler() -> None:
    lst_path = V31_MAIN_HEX_CANONICAL.with_suffix(".lst")
    _skip_missing(lst_path)
    text = lst_path.read_text(encoding="utf-8", errors="replace")

    assert "hid_cmd_diag_memread_probe" in text
    assert "goto        hid_cmd_diag_memread" in text
    assert "hid_cmd_diag_memread:" in text
    assert "org 0x4C00" in text
    assert text.index("hid_cmd_diag_memread:") < text.index("org 0x4C00")


def test_diag_memread_usb_safe_hex_only_restores_stock_sparse_gaps() -> None:
    _skip_missing(STOCK_MAIN_HEX, V31_MAIN_HEX_CANONICAL, V31_DIAG_MEMREAD_USB_SAFE_HEX)
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    canonical = parse_intel_hex(V31_MAIN_HEX_CANONICAL)
    diag = parse_intel_hex(V31_DIAG_MEMREAD_USB_SAFE_HEX)

    differing = {
        addr: (canonical.get(addr), diag.get(addr))
        for addr in set(canonical) | set(diag)
        if canonical.get(addr) != diag.get(addr)
    }
    assert differing, "expected USB-safe artifact to restore at least one sparse stock byte"

    stock_only = {addr for addr in stock if addr not in canonical}
    assert set(differing) <= stock_only
    for addr in differing:
        assert diag[addr] == stock[addr]
        assert canonical.get(addr) is None

    assert diag.get(0x4C00, 0xFF) == canonical.get(0x4C00, 0xFF)
    assert diag.get(0x55FF, 0xFF) == canonical.get(0x55FF, 0xFF)
