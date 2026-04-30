from __future__ import annotations

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v15b, parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V151B, STOCK_CONTROL_HEX_V15B


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported so DLCP_SIM_BACKEND={rust,dual}
# does not auto-skip them.
pytestmark = pytest.mark.dual_supported


def test_check_control_v15b_accepts_current_full_sync_hook() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    check_control_v15b(stock, patched)


def test_check_control_v15b_rejects_full_sync_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    mut[0x0B2D] = 0xEE
    with pytest.raises(RuntimeError, match="full-sync hook"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_ir_dispatch_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    mut[0x0E33] = 0xEE
    with pytest.raises(RuntimeError, match="IR dispatch hook"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_ir_shortcut_constant_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    hit = None
    for addr in range(0x7000, 0x7300):
        if mut.get(addr, 0xFF) == 0x38 and mut.get(addr + 1, 0xFF) == 0x0A:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: xorlw 0x38 signature not found")
    mut[hit] = 0x3A
    with pytest.raises(RuntimeError, match="xorlw 0x38"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_ir_dispatch_target_reverted_to_stock() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    mut[0x0E32] = 0x1C
    mut[0x0E34] = 0x07
    with pytest.raises(RuntimeError, match="drifted to stock target"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_parser_site_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    mut[0x05C6] = 0x00
    with pytest.raises(RuntimeError, match="parser site drift"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_reintroduced_filename_literal() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    hit = None
    for addr in range(0x7000, 0x7300):
        if mut.get(addr, 0xFF) == 0x20 and mut.get(addr + 1, 0xFF) == 0x0E:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: cmd=0x20 literal not found")
    mut[hit] = 0x21
    with pytest.raises(RuntimeError, match="removed filename cmd literal 0x21"):
        check_control_v15b(stock, mut)
