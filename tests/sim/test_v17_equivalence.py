"""V1.7 CONTROL source-rewrite equivalence tests.

Validates the byte-identical baseline built from
``dlcp_control_v17.asm`` / ``dlcp_control_v17_comments.asm`` against the
stock V1.6b hex, and verifies source-quality invariants from
``docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md`` (Phases 1–2).
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_ASM,
    V17_CONTROL_ASM_COMMENTS,
    V17_CONTROL_RAM_INC,
)
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v17_symbols import assemble_v17


# All tests in this module are backend-agnostic (static source/hex
# analysis, flash-tool CLI plumbing, semantic-guard regex matchers).
# Mark the whole module dual_supported (legacy informational
# marker; see tests/sim/conftest.py for the post-PF.4 inert
# semantics).
pytestmark = pytest.mark.dual_supported


def _assemble(asm_path: Path, tmp_path: Path) -> Path:
    """Assemble the .asm through gpasm and return the produced .hex path."""
    out = tmp_path / (asm_path.stem + ".hex")
    # Stage the RAM include next to the assembled copy so gpasm resolves it.
    target_inc = tmp_path / V17_CONTROL_RAM_INC.name
    if not target_inc.exists():
        target_inc.write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    staged_asm = tmp_path / asm_path.name
    staged_asm.write_bytes(asm_path.read_bytes())
    assemble_v17(staged_asm, out)
    return out


@pytest.fixture(scope="module")
def v17_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _assemble(V17_CONTROL_ASM, tmp_path_factory.mktemp("v17"))


@pytest.fixture(scope="module")
def v17_comments_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return _assemble(V17_CONTROL_ASM_COMMENTS, tmp_path_factory.mktemp("v17c"))


# ---------------------------------------------------------------------------
# Source files exist
# ---------------------------------------------------------------------------

def test_v17_asm_exists() -> None:
    assert V17_CONTROL_ASM.exists(), f"missing V1.7 asm: {V17_CONTROL_ASM}"


def test_v17_comments_asm_exists() -> None:
    assert V17_CONTROL_ASM_COMMENTS.exists(), (
        f"missing V1.7 commented asm: {V17_CONTROL_ASM_COMMENTS}"
    )


def test_v17_ram_inc_exists() -> None:
    assert V17_CONTROL_RAM_INC.exists(), f"missing RAM include: {V17_CONTROL_RAM_INC}"


# ---------------------------------------------------------------------------
# Byte-identity vs stock V1.6b — code, config, EEPROM
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "region",
    [("code", 0x0000, 0x8000), ("config", 0x300000, 0x30000E), ("eeprom", 0xF00000, 0xF00100)],
    ids=lambda r: r[0],
)
def test_v17_asm_byte_identical(v17_hex: Path, region) -> None:
    name, lo, hi = region
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v17_hex)
    for addr in range(lo, hi):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"{name} mismatch at 0x{addr:06X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} built=0x{built.get(addr, 0xFF):02X}"
        )


@pytest.mark.parametrize(
    "region",
    [("code", 0x0000, 0x8000), ("config", 0x300000, 0x30000E), ("eeprom", 0xF00000, 0xF00100)],
    ids=lambda r: r[0],
)
def test_v17_comments_asm_byte_identical(v17_comments_hex: Path, region) -> None:
    name, lo, hi = region
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v17_comments_hex)
    for addr in range(lo, hi):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"{name} mismatch at 0x{addr:06X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} built=0x{built.get(addr, 0xFF):02X}"
        )


# ---------------------------------------------------------------------------
# Source-quality gates on the commented source
# ---------------------------------------------------------------------------

def test_v17_comments_no_auto_labels() -> None:
    """Commented source has zero function_NNN / label_NNN tokens.

    Enforces Phase 2 acceptance criterion: every auto-generated label
    from gpdasm is renamed either to its semantic name (from v16b.asm)
    or a deterministic placeholder (``control_core_service_XXXX`` /
    ``flow_local_XXXX``) derived from the program address.
    """
    text = V17_CONTROL_ASM_COMMENTS.read_text(encoding="utf-8")
    leftovers = re.findall(r"\b(?:function|label)_\d+\b", text)
    assert not leftovers, (
        f"auto-labels remain in commented source: {sorted(set(leftovers))[:10]}"
    )


def test_v17_comments_has_semantic_labels() -> None:
    """Spot-check that known semantic names appear as label definitions."""
    text = V17_CONTROL_ASM_COMMENTS.read_text(encoding="utf-8")
    expected = [
        "bootloader_entry:",
        "isr_entry:",
        "app_cold_init:",
        "lcd_command:",
        "ir_rc5_decode:",
        "rx_parser_entry:",
        "tx_byte_enqueue:",
        "full_sync_burst:",
        "main_event_loop:",
    ]
    for tag in expected:
        assert tag in text, f"missing expected label definition: {tag}"


def test_v17_comments_has_function_headers() -> None:
    """Commented source carries function header banners from v16b.asm."""
    text = V17_CONTROL_ASM_COMMENTS.read_text(encoding="utf-8")
    # v16b.asm banners use "; functionname @ 0xADDR — semantic" form.
    # After the rename pass these become "; semantic @ 0xADDR — semantic".
    banner_hits = re.findall(r"^; [a-z_][a-z_0-9]*\s+@\s+0x[0-9A-Fa-f]{4}", text, re.MULTILINE)
    assert len(banner_hits) >= 15, (
        f"too few ported function headers: {len(banner_hits)} (expected ≥15)"
    )


def test_v17_comments_includes_ram_inc() -> None:
    text = V17_CONTROL_ASM_COMMENTS.read_text(encoding="utf-8")
    assert "include dlcp_control_ram.inc" in text, (
        "commented source must include the RAM equates"
    )


# ---------------------------------------------------------------------------
# RAM include has the documented equates
# ---------------------------------------------------------------------------

@pytest.mark.parametrize(
    "name, addr",
    [
        ("ir_decoded_cmd", 0x01D),
        ("control_flags", 0x01F),
        ("tx_data_staging", 0x027),
        ("rx_parsed_cmd", 0x02F),
        ("tx_ring_base", 0x036),
        ("rx_ring_base", 0x066),
        ("tx_ring_wr", 0x097),
        ("rx_ring_wr", 0x099),
        ("rx_frame_position", 0x0A6),
        ("input_select_cache", 0x0B8),
        ("volume_cache", 0x0B9),
        ("display_state_index", 0x0BF),
        ("saved_settings_base", 0x0C1),
    ],
)
def test_v17_ram_equates_present(name: str, addr: int) -> None:
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    pat = re.compile(rf"^\s*{re.escape(name)}\s+equ\s+0x[0-9A-Fa-f]+", re.MULTILINE)
    m = pat.search(text)
    assert m, f"RAM equate not defined: {name}"
    value_pat = re.compile(rf"^\s*{re.escape(name)}\s+equ\s+0x([0-9A-Fa-f]+)", re.MULTILINE)
    v = int(value_pat.search(text).group(1), 16)
    assert v == addr, f"RAM equate {name} maps to 0x{v:03X}, expected 0x{addr:03X}"


# ---------------------------------------------------------------------------
# Conversion script is operable and produces the same bytes
# ---------------------------------------------------------------------------

def test_convert_script_regenerates_v17(tmp_path: Path) -> None:
    """Re-running the conversion pipeline must reproduce the committed V1.7."""
    out_asm = tmp_path / "regen.asm"
    subprocess.run(
        [
            "python3",
            "scripts/convert_v16b_asm_to_gpasm.py",
            "--output", str(out_asm),
            "--banner", "none",
        ],
        check=True,
        capture_output=True,
    )
    regen_hex = _assemble(out_asm, tmp_path)
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(regen_hex)
    for addr in range(0, 0x8000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"regenerated V1.7 diverges at 0x{addr:06X}"
        )
