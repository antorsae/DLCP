from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import check_control, check_main, parse_intel_hex


ROOT = Path(__file__).resolve().parent.parent.parent
STOCK_MAIN_HEX = ROOT / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex"
STOCK_CONTROL_HEX = ROOT / "firmware" / "stock" / "control" / "DLCP Control Firmware V1.4.hex"


def test_check_main_accepts_current_cmd_tail_guard(patched_main_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)
    check_main(stock, patched)


def test_check_main_rejects_cmd_tail_guard_drift(patched_main_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)
    mut = dict(patched)
    # Corrupt legacy cmd=0x1D compare constant.
    mut[0x5522] = 0x1A

    with pytest.raises(RuntimeError, match="cmd-tail guard mismatch at 0x5522"):
        check_main(stock, mut)


def test_check_control_accepts_current_full_sync_hook(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    check_control(stock, patched)


def test_check_control_rejects_full_sync_hook_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)
    # Corrupt the full-sync hook goto opcode byte.
    mut[0x0B53] = 0xEE

    with pytest.raises(RuntimeError, match="full-sync hook mismatch at 0x0B53"):
        check_control(stock, mut)


def test_check_control_rejects_ir_dispatch_hook_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)
    # Corrupt the IR dispatch hook goto opcode byte.
    mut[0x0E47] = 0xEE

    with pytest.raises(RuntimeError, match="IR dispatch hook at 0x0E46"):
        check_control(stock, mut)


def test_check_control_rejects_ir_shortcut_constant_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
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
        check_control(stock, mut)


def test_check_control_rejects_ir_dispatch_target_reverted_to_stock(
    patched_control_hex: Path,
) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)

    # Keep goto opcodes intact (EF/F0), but retarget low bytes back to stock
    # label_166 destination (0x0E4C): bytes 26 EF 07 F0 at 0x0E46.
    mut[0x0E46] = 0x26
    mut[0x0E48] = 0x07

    with pytest.raises(RuntimeError, match="target drifted to stock label_166"):
        check_control(stock, mut)
