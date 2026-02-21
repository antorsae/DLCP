from __future__ import annotations

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v16b, parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V161B, STOCK_CONTROL_HEX_V16B


def test_check_control_v16b_accepts_current_full_sync_hook() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    check_control_v16b(stock, patched)


def test_check_control_v16b_rejects_full_sync_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)
    # Corrupt the full-sync hook goto opcode byte.
    mut[0x0B37] = 0xEE

    with pytest.raises(RuntimeError, match="full-sync hook mismatch at 0x0B37"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_ir_dispatch_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)
    # Corrupt the IR dispatch hook goto opcode byte.
    mut[0x0DE7] = 0xEE

    with pytest.raises(RuntimeError, match="IR dispatch hook at 0x0DE6"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_ir_shortcut_constant_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)

    # Remove xorlw 0x38 signature used for F1->preset A.
    hit = None
    for addr in range(0x7000, 0x7200):
        if mut.get(addr, 0xFF) == 0x38 and mut.get(addr + 1, 0xFF) == 0x0A:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: xorlw 0x38 signature not found")
    mut[hit] = 0x3A

    with pytest.raises(RuntimeError, match="xorlw 0x38"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_ir_dispatch_target_reverted_to_stock() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)

    # Keep goto opcodes intact (EF/F0), but retarget low bytes back to stock
    # label_162 destination (0x0DEC): bytes F6 EF 06 F0 at 0x0DE6.
    mut[0x0DE6] = 0xF6
    mut[0x0DE8] = 0x06

    with pytest.raises(RuntimeError, match="target drifted to stock label_162"):
        check_control_v16b(stock, mut)
