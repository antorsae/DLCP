from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.patch import build_main_presets_ab
from dlcp_fw.patch.verify_presets_ab import check_control, check_main, parse_intel_hex


ROOT = Path(__file__).resolve().parent.parent.parent
STOCK_MAIN_HEX = ROOT / "firmware" / "stock" / "main" / "DLCP Firmware V2.3.hex"
STOCK_CONTROL_HEX = ROOT / "firmware" / "stock" / "control" / "DLCP Control Firmware V1.4.hex"


def test_check_main_accepts_current_cmd_tail_guard(patched_main_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)
    check_main(stock, patched)


def test_check_main_accepts_v24_filename_banking(patched_main_hex_v24: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex_v24)
    check_main(stock, patched, variant="v24")


def test_main_patch_asm_is_byte_identical_under_2455_and_2550_headers() -> None:
    if shutil.which("gpasm") is None:
        pytest.skip("gpasm not installed")

    asm_2455 = build_main_presets_ab.PATCH_ASM
    asm_2550 = (
        asm_2455.replace("LIST P=18F2455", "LIST P=18F2550")
        .replace("#include <p18f2455.inc>", "#include <p18f2550.inc>")
    )

    with tempfile.TemporaryDirectory(prefix="v25_target_equiv_") as td:
        td_path = Path(td)
        outputs: dict[str, dict[int, int]] = {}
        for name, proc, asm_text in (
            ("2455", "18f2455", asm_2455),
            ("2550", "18f2550", asm_2550),
        ):
            asm_path = td_path / f"{name}.asm"
            hex_path = td_path / f"{name}.hex"
            asm_path.write_text(asm_text, encoding="ascii")
            cp = subprocess.run(
                ["gpasm", f"-p{proc}", "-o", str(hex_path), str(asm_path)],
                capture_output=True,
                text=True,
            )
            if cp.returncode != 0:
                raise RuntimeError(
                    f"gpasm failed for {proc} (rc={cp.returncode}):\n{cp.stderr}\n{cp.stdout}"
                )
            outputs[name] = parse_intel_hex(hex_path)

    assert outputs["2455"] == outputs["2550"]


def test_check_main_rejects_cmd_tail_guard_drift(patched_main_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)
    mut = dict(patched)
    hit = None
    for addr in range(0x54C0, 0x5510):
        if mut.get(addr, 0xFF) == 0x1D and mut.get(addr + 1, 0xFF) == 0x0A:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: main xorlw 0x1D signature not found")
    mut[hit] = 0x1A
    with pytest.raises(RuntimeError, match="cmd-tail missing xorlw 0x1D"):
        check_main(stock, mut)


def test_check_main_rejects_reintroduced_filename_command_literal(patched_main_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)
    mut = dict(patched)
    hit = None
    for addr in range(0x54C0, 0x5510):
        if mut.get(addr, 0xFF) == 0x20 and mut.get(addr + 1, 0xFF) == 0x0A:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: main xorlw 0x20 signature not found")
    mut[hit] = 0x21
    with pytest.raises(RuntimeError, match="missing xorlw 0x20"):
        check_main(stock, mut)


def test_check_main_rejects_mssp_idle_wait_logic_drift(patched_main_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    patched = parse_intel_hex(patched_main_hex)
    mut = dict(patched)
    hit = None
    seq = [
        0xC5,
        0xCF,
        0x03,
        0xF0,
        0x1F,
        0x0E,
        0x03,
        0x14,
        0xD8,
        0xA4,
        0x03,
        0xD0,
        0xC7,
        0xB4,
        0x01,
        0xD0,
        0x05,
        0xD0,
        0x0B,
        0x2E,
        0xF5,
        0xD7,
        0x0C,
        0x2E,
        0xF3,
        0xD7,
        0x02,
        0xD0,
        0xD8,
        0x90,
    ]
    for addr in range(0x5576, 0x5594):
        if all(mut.get(addr + off, 0xFF) == byte for off, byte in enumerate(seq)):
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: MSSP idle wait signature not found")
    mut[hit + 1] = 0xB4
    with pytest.raises(RuntimeError, match="packed MSSP idle wait logic"):
        check_main(stock, mut)


def test_check_control_accepts_current_full_sync_hook(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    check_control(stock, patched)


def test_check_control_rejects_full_sync_hook_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)
    mut[0x0B53] = 0xEE
    with pytest.raises(RuntimeError, match="full-sync hook"):
        check_control(stock, mut)


def test_check_control_rejects_ir_dispatch_hook_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)
    mut[0x0E47] = 0xEE
    with pytest.raises(RuntimeError, match="IR dispatch hook"):
        check_control(stock, mut)


def test_check_control_rejects_ir_shortcut_constant_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
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
        check_control(stock, mut)


def test_check_control_rejects_ir_dispatch_target_reverted_to_stock(
    patched_control_hex: Path,
) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)
    mut[0x0E46] = 0x26
    mut[0x0E48] = 0x07
    with pytest.raises(RuntimeError, match="drifted to stock target"):
        check_control(stock, mut)


def test_check_control_rejects_parser_site_drift(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
    mut = dict(patched)
    mut[0x05EC] = 0x00
    with pytest.raises(RuntimeError, match="parser site drift"):
        check_control(stock, mut)


def test_check_control_rejects_reintroduced_filename_literal(patched_control_hex: Path) -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX)
    patched = parse_intel_hex(patched_control_hex)
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
        check_control(stock, mut)
