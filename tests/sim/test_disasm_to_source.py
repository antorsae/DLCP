"""Tests for the disassembly-to-source converter."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest


def test_converter_produces_asm_file(tmp_path):
    from dlcp_fw.analysis.disasm_to_source import convert

    out = tmp_path / "test.asm"
    convert(output_path=out)
    assert out.exists()
    assert out.stat().st_size > 10000


def test_converter_structural_org_only(tmp_path):
    from dlcp_fw.analysis.disasm_to_source import convert

    out = tmp_path / "test.asm"
    convert(output_path=out)
    text = out.read_text()
    orgs = re.findall(
        r"^\s*org\s+(0x[0-9A-Fa-f]+)", text, re.MULTILINE | re.IGNORECASE
    )
    allowed = {0x1000, 0x5600, 0xF00000}
    for org_str in orgs:
        addr = int(org_str, 16)
        assert addr in allowed, f"Unexpected org 0x{addr:06X}"


def test_converter_has_config(tmp_path):
    from dlcp_fw.analysis.disasm_to_source import convert

    out = tmp_path / "test.asm"
    convert(output_path=out)
    assert "__CONFIG" in out.read_text()


def test_converter_has_ram_include(tmp_path):
    from dlcp_fw.analysis.disasm_to_source import convert

    out = tmp_path / "test.asm"
    convert(output_path=out)
    inc = tmp_path / "dlcp_main_ram.inc"
    assert inc.exists()
    text = inc.read_text()
    assert "active_flags" in text
    assert "EQU" in text


def test_converter_assembles(tmp_path):
    """The converter output must assemble with gpasm."""
    from dlcp_fw.analysis.disasm_to_source import convert

    out_asm = tmp_path / "test.asm"
    out_hex = tmp_path / "test.hex"
    convert(output_path=out_asm)
    result = subprocess.run(
        ["gpasm", "-p18f2455", "-I", str(tmp_path), "-o", str(out_hex), str(out_asm)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, f"gpasm failed:\n{result.stderr}"
    assert out_hex.exists()
