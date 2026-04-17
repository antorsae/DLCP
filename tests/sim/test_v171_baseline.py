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


def test_v171_eeprom_matches_stock_except_version_and_preset(v171_hex: Path) -> None:
    """Gate 6: EEPROM byte-identical to stock except version (0x71-0x73) and preset (0x74)."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    allowed_diff_addrs = {0xF00071, 0xF00072, 0xF00073, 0xF00074}
    for addr in range(0xF00000, 0xF00100):
        if addr in allowed_diff_addrs:
            continue
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), (
            f"EEPROM byte diverges at 0x{addr:06X}: "
            f"stock=0x{stock.get(addr, 0xFF):02X} v171=0x{built.get(addr, 0xFF):02X}"
        )


def test_v171_eeprom_version_tuple_bumped(v171_hex: Path) -> None:
    """Version tuple at EEPROM 0x70..0x73 reflects V1.71 identifier (not V1.6b)."""
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)
    # Must differ from stock V1.6b tuple 01 06 30 01.
    stock_tuple = tuple(stock.get(a, 0xFF) for a in range(0xF00070, 0xF00074))
    v171_tuple = tuple(built.get(a, 0xFF) for a in range(0xF00070, 0xF00074))
    assert stock_tuple == (0x01, 0x06, 0x30, 0x01), (
        f"unexpected stock V1.6b version tuple: {stock_tuple!r}"
    )
    assert v171_tuple != stock_tuple, (
        f"V1.71 version tuple not bumped from stock: {v171_tuple!r}"
    )
    # Must encode V1.71 somewhere (minor byte at 0x71 is 0x07, ASCII at 0x72 is '1').
    assert v171_tuple[1] == 0x07, f"V1.71 minor byte != 0x07: {v171_tuple!r}"
    assert v171_tuple[2] == 0x31, f"V1.71 sub byte (ASCII '1') != 0x31: {v171_tuple!r}"


def test_v171_app_code_has_grown_past_stock(v171_hex: Path) -> None:
    """Once Phase B features inline, the V1.71 app code tail exceeds stock V1.6b.

    This is the positive signal that inline feature work is landing
    (and the negative signal if feature code has been accidentally
    reverted).  Stock V1.6b app code ends at 0x1A0B; V1.71 must end
    strictly later than that, and strictly before the pinned
    bootloader at 0x7800.
    """
    stock = parse_intel_hex(STOCK_CONTROL_HEX_V16B)
    built = parse_intel_hex(v171_hex)

    def _tail(mem) -> int:
        return max(
            (a for a, b in mem.items() if a < 0x7800 and b != 0xFF),
            default=-1,
        )

    stock_tail = _tail(stock)
    v171_tail = _tail(built)
    assert stock_tail == 0x1A0B, f"stock tail regression: 0x{stock_tail:04X}"
    assert v171_tail > stock_tail, (
        f"V1.71 app code not growing past stock (tail 0x{v171_tail:04X} "
        f"vs stock 0x{stock_tail:04X}) — has feature inlining regressed?"
    )
    assert v171_tail < 0x7800, (
        f"V1.71 app code overruns bootloader: tail=0x{v171_tail:04X} ≥ 0x7800"
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
