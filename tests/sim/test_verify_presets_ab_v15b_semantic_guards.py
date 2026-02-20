from __future__ import annotations

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control_v15b, parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V151B, STOCK_CONTROL_HEX_V15B


def test_check_control_v15b_accepts_current_full_sync_hook() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    check_control_v15b(stock, patched)


def test_check_control_v15b_rejects_full_sync_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    # Corrupt the full-sync hook goto opcode byte.
    mut[0x0B2D] = 0xEE

    with pytest.raises(RuntimeError, match="full-sync hook mismatch at 0x0B2D"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_ir_dispatch_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)
    # Corrupt the IR dispatch hook goto opcode byte.
    mut[0x0E33] = 0xEE

    with pytest.raises(RuntimeError, match="IR dispatch hook at 0x0E32"):
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_ir_shortcut_constant_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
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
        check_control_v15b(stock, mut)


def test_check_control_v15b_rejects_ir_dispatch_target_reverted_to_stock() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V15B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V151B)
    mut = dict(patched)

    # Keep goto opcodes intact (EF/F0), but retarget low bytes back to stock
    # label_164 destination (0x0E38): bytes 1C EF 07 F0 at 0x0E32.
    mut[0x0E32] = 0x1C
    mut[0x0E34] = 0x07

    with pytest.raises(RuntimeError, match="target drifted to stock label_164"):
        check_control_v15b(stock, mut)
