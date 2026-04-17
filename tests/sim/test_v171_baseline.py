"""V1.71 CONTROL baseline tests.

Phase A of the V1.71 rollout (``docs/V16B_SOURCE_REWRITE_SPEC.md``):
the freshly-cloned ``dlcp_control_v171.asm`` must assemble cleanly and
remain byte-identical to stock V1.6b until V1.71 features are inlined
in subsequent phases.  These tests lock that scaffolding in so later
phases can grow the source with confidence that the pre-change state
was clean.

As the phases land (V1.61b presets, V1.62b reconnect, V1.63b BF/08,
V1.64b IR endpoints), the byte-identity expectation here relaxes and
moves to parity against the V1.61b..V1.64b binary overlays — tracked
in `test_v171_preset_menu.py`, `test_v171_reconnect_wake.py`,
`test_v171_fault_indicator.py`, `test_v171_ir_endpoints.py`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
)
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v17_symbols import assemble_v17


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_baseline")
    # Stage the RAM include next to the ASM so gpasm resolves it.
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


# ---------------------------------------------------------------------------
# Source-file presence
# ---------------------------------------------------------------------------

def test_v171_asm_exists() -> None:
    assert V171_CONTROL_ASM.exists(), (
        f"V1.71 source missing: {V171_CONTROL_ASM}. "
        "Run Phase A scaffolding before attempting feature work."
    )


def test_v171_ram_inc_has_feature_equates() -> None:
    """RAM include carries the V1.71 flag-bit and fault-byte equates."""
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    required = [
        "PRESET_BIT",
        "DSP_FAULT_BIT",
        "RECONNECT_PENDING",
        "RECONNECT_PRIMED",
        "RECONNECT_WAIT_DONE",
        "bf08_fault_byte",
        "RC5_PRESET_A",
        "RC5_PRESET_B",
        "RC5_STANDBY_ENTER",
        "RC5_WAKE",
        "EEPROM_PRESET_STATE_ADDR",
    ]
    missing = [name for name in required if not re.search(rf"^\s*{re.escape(name)}\s+equ\s", text, re.MULTILINE)]
    assert not missing, f"V1.71 equates missing from RAM include: {missing}"


# ---------------------------------------------------------------------------
# Phase-A byte-identity gate (temporary — relaxes as features land)
# ---------------------------------------------------------------------------

def test_v171_phase_a_assembles_without_errors(v171_hex: Path) -> None:
    assert v171_hex.exists() and v171_hex.stat().st_size > 0


def test_v171_phase_a_vector_block_byte_identical(v171_hex: Path) -> None:
    """0x0000–0x004B must always match stock — gate 3 of the spec."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x0000, 0x004C):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"vector block diverges at 0x{addr:04X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} v171=0x{built.get(addr, 0xFF):02X}"
        )


def test_v171_phase_a_bootloader_byte_identical(v171_hex: Path) -> None:
    """Bootloader 0x7800–0x7FFF — gate 4 of the spec."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x7800, 0x8000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"bootloader diverges at 0x{addr:04X}"
        )


def test_v171_phase_a_config_bits_byte_identical(v171_hex: Path) -> None:
    """Config bits at 0x300000..0x30000D — gate 5 of the spec."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    for addr in range(0x300000, 0x30000E):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"config bit diverges at 0x{addr:06X}"
        )


def test_v171_phase_a_scaffolding_still_matches_stock(v171_hex: Path) -> None:
    """Full byte-identity during Phase A — before any features inline.

    Once V1.71 features start landing this test is expected to fail and
    will be replaced by the feature-level parity tests.  Keep it as a
    checkpoint that captures the clean scaffolding state at commit time.
    """
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    addrs = set(stock.keys()) | set(built.keys())
    diffs = [a for a in sorted(addrs) if stock.get(a, 0xFF) != built.get(a, 0xFF)]
    assert not diffs, (
        f"V1.71 scaffolding diverges from stock V1.6b at {len(diffs)} addresses; "
        f"first 5: {[(hex(a), hex(stock.get(a, 0xFF)), hex(built.get(a, 0xFF))) for a in diffs[:5]]}.  "
        "Phase A must stay byte-identical; move the failing feature into "
        "Phase B / C / D / E and replace this test with the relevant parity gate."
    )


# ---------------------------------------------------------------------------
# Banner sanity
# ---------------------------------------------------------------------------

def test_v171_banner_identifies_feature_scope() -> None:
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # The banner must name V1.71 (so downstream readers know which
    # feature set to expect) and reference each of the 4 parent
    # overlays whose features it inlines.
    for marker in ("V1.71", "V1.61b", "V1.62b", "V1.63b", "V1.64b"):
        assert marker in text[:2000], f"banner missing marker: {marker}"
