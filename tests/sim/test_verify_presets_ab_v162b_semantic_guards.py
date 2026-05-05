from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

from dlcp_fw.patch import build_control_presets_ab_v162b
from dlcp_fw.patch.verify_presets_ab import check_control_v162b, parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V162B, STOCK_CONTROL_HEX_V16B


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


def test_check_control_v162b_accepts_current_patch() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    check_control_v162b(stock, patched)


def test_verify_presets_ab_auto_profile_accepts_explicit_v162b_pair() -> None:
    cp = subprocess.run(
        [
            sys.executable,
            "-m",
            "dlcp_fw.patch.verify_presets_ab",
            "--control-orig",
            str(STOCK_CONTROL_HEX_V16B),
            "--control-new",
            str(PATCHED_CONTROL_HEX_V162B),
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        raise RuntimeError(f"verify_presets_ab failed:\nSTDOUT:\n{cp.stdout}\nSTDERR:\n{cp.stderr}")


def test_v162b_patch_asm_is_byte_identical_under_k20_and_2550_headers() -> None:
    if shutil.which("gpasm") is None:
        pytest.skip("gpasm not installed")

    asm_k20 = build_control_presets_ab_v162b.PATCH_ASM
    asm_2550 = (
        asm_k20.replace("LIST P=18F25K20", "LIST P=18F2550")
        .replace("#include <p18f25k20.inc>", "#include <p18f2550.inc>")
    )

    with tempfile.TemporaryDirectory(prefix="v162b_target_equiv_") as td:
        td_path = Path(td)
        outputs: dict[str, dict[int, int]] = {}
        for name, proc, asm_text in (
            ("k20", "18f25k20", asm_k20),
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

    assert outputs["k20"] == outputs["2550"]


def test_check_control_v162b_rejects_full_sync_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    mut[0x0B37] = 0xEE
    with pytest.raises(RuntimeError, match="full-sync hook"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_ir_dispatch_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    mut[0x0DE7] = 0xEE
    with pytest.raises(RuntimeError, match="IR dispatch hook"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_ir_shortcut_constant_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    hit = None
    for addr in range(0x7000, 0x7400):
        if mut.get(addr, 0xFF) == 0x38 and mut.get(addr + 1, 0xFF) == 0x0A:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: xorlw 0x38 signature not found")
    mut[hit] = 0x3A
    with pytest.raises(RuntimeError, match="xorlw 0x38"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_ir_dispatch_target_reverted_to_stock() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    mut[0x0DE6] = 0xF6
    mut[0x0DE8] = 0x06
    with pytest.raises(RuntimeError, match="drifted to stock target"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_parser_site_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    mut[0x05D0] = 0x00
    with pytest.raises(RuntimeError, match="parser site drift"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_reintroduced_filename_literal() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    hit = None
    for addr in range(0x7000, 0x7400):
        if mut.get(addr, 0xFF) == 0x20 and mut.get(addr + 1, 0xFF) == 0x0E:
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: cmd=0x20 literal not found")
    mut[hit] = 0x21
    with pytest.raises(RuntimeError, match="removed filename cmd literal 0x21"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_boot_setup_index_clamp_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)

    hit = None
    seq = [0xBA, 0x51, 0x06, 0xE0, 0xBA, 0x6B, 0x01, 0x0E, 0xA9, 0x6E]
    for addr in range(0x7000, 0x7400):
        if all(mut.get(addr + off, 0xFF) == byte for off, byte in enumerate(seq)):
            hit = addr
            break
    if hit is None:
        raise RuntimeError("test setup failed: stale setup-index clamp signature not found")
    mut[hit + 4] = 0x00

    with pytest.raises(RuntimeError, match="stale setup-index clamp"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_parser_entry_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    mut[0x044B] = 0xEE
    with pytest.raises(RuntimeError, match="parser entry hook"):
        check_control_v162b(stock, mut)


def test_check_control_v162b_rejects_reconnect_hook_drift() -> None:
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    patched = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    mut = dict(patched)
    mut[0x12BD] = 0xEE
    with pytest.raises(RuntimeError, match="reconnect hook"):
        check_control_v162b(stock, mut)
