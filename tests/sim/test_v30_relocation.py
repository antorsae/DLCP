"""V3.0 relocation safety proof — shift test suite.

Inserts 0x222 bytes of NOP padding into the V3.0 source, shifting all
code by 0x222 bytes while keeping the entry block (0x1000-0x1013) and
preset table (0x5600) pinned.  Verifies the structural invariants:

  - Shifted ASM assembles without errors
  - App entry at 0x1000, ISR dispatch at 0x1008 (before padding)
  - Config bits and EEPROM identical to stock
  - Preset table pinned at 0x5600
  - Code region is 0x222 bytes larger than stock
  - All code symbols shift by exactly 0x222; preset_table_a stays pinned

Four earlier gpsim-only behavioral tests
(``test_shifted_an0_boot_gate_exit_cycle``,
``test_shifted_command_matrix`` (3-way parametrized),
``test_shifted_chain_reaches_display``,
``test_shifted_chain_blackout_wake_shows_waiting``) were deleted in
PF.4 phase 2 batch 8: all relied on gpsim's
``probe_main_an0_boot_exit_cycle`` (PC breakpoint at the gate-exit
address), ``run_main_mailbox_gpsim`` (mailbox-overlay TX-byte
capture), or ``SingleMainChainHarness`` (gpsim wire chain) — none
have direct rust analogues.  The structural relocation-safety
invariants are covered by the 10 byte/symbol tests below; runtime
parity for V3.x MAIN with stock CONTROL is exercised end-to-end by
``test_v17_chain.py`` and the V1.71+V3.2 chain tests.
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX, V30_MAIN_ASM_COMMENTS
from dlcp_fw.sim.hexio import parse_intel_hex
from dlcp_fw.sim.v30_symbols import assemble_v30, build_shifted_asm, parse_gpasm_symbols

SHIFT_AMOUNT = 0x222


# ---------------------------------------------------------------------------
# Session-scoped fixtures: build shifted hex + symbols once per test run
# ---------------------------------------------------------------------------

@pytest.fixture(scope="session")
def shifted_build() -> Dict:
    """Build shifted ASM, assemble, and return paths + symbols."""
    td = tempfile.mkdtemp(prefix="v30_reloc_")
    td_path = Path(td)
    shifted_asm = td_path / "dlcp_main_v30_shifted.asm"
    shifted_hex = td_path / "dlcp_main_v30_shifted.hex"

    build_shifted_asm(V30_MAIN_ASM_COMMENTS, shifted_asm)
    assemble_v30(shifted_asm, shifted_hex)
    lst = shifted_asm.with_suffix(".lst")
    symbols = parse_gpasm_symbols(lst)

    return {
        "hex": shifted_hex,
        "asm": shifted_asm,
        "lst": lst,
        "symbols": symbols,
    }


@pytest.fixture(scope="session")
def shifted_hex(shifted_build) -> Path:
    return shifted_build["hex"]


@pytest.fixture(scope="session")
def shifted_symbols(shifted_build) -> Dict[str, int]:
    return shifted_build["symbols"]


# ---------------------------------------------------------------------------
# Structural tests
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
def test_shifted_assembles(shifted_hex: Path) -> None:
    """Shifted ASM assembles without errors and produces a hex file."""
    assert shifted_hex.exists()
    assert shifted_hex.stat().st_size > 0


@pytest.mark.dual_supported
def test_shifted_app_entry_at_0x1000(shifted_hex: Path) -> None:
    """App entry at 0x1000 is present (boot block target)."""
    mem = parse_intel_hex(shifted_hex)
    assert 0x1000 in mem, "No code at 0x1000"
    # Must be a GOTO instruction (EF xx xx F0)
    assert mem.get(0x1001, 0) == 0xEF, "0x1000 is not a GOTO"


@pytest.mark.dual_supported
def test_shifted_isr_at_0x1008(shifted_hex: Path) -> None:
    """ISR dispatch stub is at 0x1008 (before padding)."""
    mem = parse_intel_hex(shifted_hex)
    # movff FSR2L, isr_save_fsr2l encodes as CFD9 F001
    # Low byte at 0x1008 = 0xD9 (FSR2L & 0xFF), high byte = 0xCF
    assert mem.get(0x1008, 0) == 0xD9, \
        f"0x1008 low byte: expected 0xD9, got 0x{mem.get(0x1008, 0):02X}"
    assert (mem.get(0x1009, 0) & 0xF0) == 0xC0, \
        f"0x1009 high nibble: expected 0xC, got 0x{mem.get(0x1009, 0):02X}"


@pytest.mark.dual_supported
def test_shifted_no_boot_block(shifted_hex: Path) -> None:
    """Shifted hex must not emit boot block bytes."""
    mem = parse_intel_hex(shifted_hex)
    boot_bytes = [a for a in mem if a < 0x1000]
    assert boot_bytes == [], \
        f"Boot block bytes: {[hex(a) for a in boot_bytes[:10]]}"


@pytest.mark.dual_supported
def test_shifted_config_identical(shifted_hex: Path) -> None:
    """Config bits must match stock V2.3."""
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    built = parse_intel_hex(shifted_hex)
    for addr in range(0x300000, 0x30000E):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"Config mismatch at 0x{addr:06X}"


@pytest.mark.dual_supported
def test_shifted_eeprom_identical(shifted_hex: Path) -> None:
    """EEPROM data must match stock V2.3."""
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    built = parse_intel_hex(shifted_hex)
    for addr in range(0xF00000, 0xF00100):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"EEPROM mismatch at 0x{addr:06X}"


@pytest.mark.dual_supported
def test_shifted_preset_pinned_at_0x5600(shifted_hex: Path) -> None:
    """Preset table A must remain at 0x5600."""
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    built = parse_intel_hex(shifted_hex)
    for addr in range(0x5600, 0x6000):
        assert built.get(addr, 0xFF) == stock.get(addr, 0xFF), \
            f"Preset mismatch at 0x{addr:04X}"


@pytest.mark.dual_supported
def test_shifted_code_region_larger(shifted_hex: Path) -> None:
    """Shifted code+data region is ~0x222 bytes larger than stock."""
    stock = parse_intel_hex(STOCK_MAIN_HEX)
    built = parse_intel_hex(shifted_hex)
    stock_code = sum(1 for a in range(0x1000, 0x5600) if stock.get(a, 0xFF) != 0xFF)
    built_code = sum(1 for a in range(0x1000, 0x5600) if built.get(a, 0xFF) != 0xFF)
    delta = built_code - stock_code
    # Padding is 0x222 bytes of NOP (0x00).  The erased-flash fill formula
    # changes slightly, allowing up to 1 byte of fill-boundary variation.
    assert abs(delta - SHIFT_AMOUNT) <= 1, \
        f"Code region delta: {delta} (expected ~{SHIFT_AMOUNT})"


@pytest.mark.dual_supported
def test_shifted_symbols_consistent(shifted_symbols: Dict[str, int]) -> None:
    """All code symbols shift by exactly 0x222; preset_table_a stays pinned."""
    stock_addrs = {
        "hid_command_dispatch": 0x10AC,
        "adc_boot_gate": 0x2D8C,
        "timer3_blocking_delay": 0x447E,
        "rx_ring_read": 0x45FA,
        "rx_ring_has_data": 0x4872,
        "uart_tx_byte_blocking": 0x4896,
        "i2c_wait_bus_idle": 0x48B6,
    }
    for name, stock in stock_addrs.items():
        shifted = shifted_symbols.get(name, -1)
        assert shifted == stock + SHIFT_AMOUNT, \
            f"{name}: expected 0x{stock + SHIFT_AMOUNT:04X}, got 0x{shifted:04X}"

    assert shifted_symbols.get("preset_table_a") == 0x5600


@pytest.mark.dual_supported
def test_shifted_padding_is_nop(shifted_hex: Path) -> None:
    """The NOP padding region (0x1014-0x1235) must be all 0x00 (NOP)."""
    mem = parse_intel_hex(shifted_hex)
    for addr in range(0x1014, 0x1014 + SHIFT_AMOUNT):
        assert mem.get(addr, 0x00) == 0x00, \
            f"Non-NOP byte at 0x{addr:04X}: 0x{mem.get(addr, 0):02X}"


