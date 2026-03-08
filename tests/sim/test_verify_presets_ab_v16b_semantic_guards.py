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
    mut[0x0B37] = 0xEE
    with pytest.raises(RuntimeError, match="full-sync hook"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_ir_dispatch_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)
    mut[0x0DE7] = 0xEE
    with pytest.raises(RuntimeError, match="IR dispatch hook"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_ir_shortcut_constant_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
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
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_ir_dispatch_target_reverted_to_stock() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)
    mut[0x0DE6] = 0xF6
    mut[0x0DE8] = 0x06
    with pytest.raises(RuntimeError, match="drifted to stock target"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_parser_site_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)
    mut[0x05D0] = 0x00
    with pytest.raises(RuntimeError, match="parser site drift"):
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_reintroduced_filename_literal() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
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
        check_control_v16b(stock, mut)


def test_check_control_v16b_rejects_boot_setup_index_clamp_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V161B)
    mut = dict(patched)

    hit = None
    seq = [0xBA, 0x51, 0x06, 0xE0, 0xBA, 0x6B, 0x01, 0x0E, 0xA9, 0x6E]
    for addr in range(0x7000, 0x7300):
        if all(mut.get(addr + off, 0xFF) == byte for off, byte in enumerate(seq)):
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: stale setup-index clamp signature not found")
    mut[hit + 4] = 0x00

    with pytest.raises(RuntimeError, match="stale setup-index clamp"):
        check_control_v16b(stock, mut)
