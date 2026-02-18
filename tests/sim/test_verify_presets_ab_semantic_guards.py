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
