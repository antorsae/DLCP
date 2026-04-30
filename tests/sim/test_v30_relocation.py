"""V3.0 relocation safety proof — shift test suite.

Inserts 0x222 bytes of NOP padding into the V3.0 source, shifting all
code by 0x222 bytes while keeping the entry block (0x1000-0x1013) and
preset table (0x5600) pinned.  Then verifies:

  Structural:
    - Shifted ASM assembles without errors
    - App entry at 0x1000, ISR dispatch at 0x1008 (before padding)
    - Config bits and EEPROM identical to stock
    - Preset table pinned at 0x5600
    - Code region is 0x222 bytes larger than stock

  Behavioral (gpsim):
    - AN0 boot gate exits at the same cycle count as stock
    - Command matrix produces identical TX bytes
    - Chain reaches display (CONTROL+MAIN link)
    - Chain blackout/wake reaches WAITING state
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Dict

import pytest

from dlcp_fw.paths import STOCK_MAIN_HEX, V30_MAIN_ASM_COMMENTS
from dlcp_fw.sim.gpsim import gpsim_available
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


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


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


# ---------------------------------------------------------------------------
# Behavioral tests (gpsim)
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
def test_shifted_an0_boot_gate_exit_cycle(
    shifted_hex: Path,
    shifted_symbols: Dict[str, int],
) -> None:
    """Shifted hex must exit the AN0 boot gate at the exact stock cycle count."""
    _require_gpsim()
    from dlcp_fw.sim.main_gpsim import probe_main_an0_boot_exit_cycle
    from tests.sim.test_v30_gpsim_equivalence import STOCK_MAIN_AN0_BOOT_EXIT_CYCLE

    shifted_exit = shifted_symbols["adc_boot_gate_exit"]
    cycle = probe_main_an0_boot_exit_cycle(
        shifted_hex,
        boot_exit_addr=shifted_exit,
    )
    assert cycle == STOCK_MAIN_AN0_BOOT_EXIT_CYCLE, \
        f"Cycle mismatch: shifted={cycle} stock={STOCK_MAIN_AN0_BOOT_EXIT_CYCLE}"


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize(
    ("cmd", "data", "label"),
    [
        (0x03, 0x00, "cmd03_standby_off"),
        (0x04, 0x00, "cmd04_status_request"),
        (0x07, 0x45, "cmd07_set_volume"),
    ],
    ids=lambda p: p if isinstance(p, str) else None,
)
def test_shifted_command_matrix(
    cmd: int,
    data: int,
    label: str,
    shifted_hex: Path,
    shifted_symbols: Dict[str, int],
) -> None:
    """Shifted hex must produce identical TX bytes to stock for each command."""
    _require_gpsim()
    from dlcp_fw.sim.main_gpsim import run_main_mailbox_gpsim
    from dlcp_fw.sim.manifests import (
        main_reset_to_appstart,
        main_serial_mailbox_hooks,
        main_serial_mailbox_hooks_dynamic,
    )
    from dlcp_fw.sim.protocol import SerialFrame

    parser_addr = shifted_symbols["flow_main_uart_service_1be6_1bea"]

    stock_res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=STOCK_MAIN_HEX,
        cycles=120_000_000,
    )
    shifted_res = run_main_mailbox_gpsim(
        frames=[SerialFrame(route=0xB0, cmd=cmd, data=data)],
        main_hex=shifted_hex,
        parser_break_addr=parser_addr,
        overlay_manifests=[
            main_reset_to_appstart(),
            main_serial_mailbox_hooks_dynamic(shifted_symbols),
        ],
        cycles=120_000_000,
    )

    assert stock_res.parser_break_hit == shifted_res.parser_break_hit
    assert stock_res.tx_bytes == shifted_res.tx_bytes, \
        f"TX mismatch for {label}: stock={stock_res.tx_bytes} shifted={shifted_res.tx_bytes}"


@pytest.mark.gpsim
@pytest.mark.slow
def test_shifted_chain_reaches_display(
    shifted_hex: Path,
    stock_control_hex_v14: Path,
) -> None:
    """Shifted hex + control V1.4 must reach connected display state."""
    _require_gpsim()
    from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness

    pair = SingleMainChainHarness(
        stock_control_hex_v14,
        shifted_hex,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected(), \
            f"pair never connected; lcd={last.lcd!r}"
        assert not pair.is_waiting()
        assert "Volume:" in last.lcd[0]
    finally:
        pair.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_shifted_chain_blackout_wake_shows_waiting(
    shifted_hex: Path,
    stock_control_hex_v14: Path,
) -> None:
    """Shifted hex must fall back to WAITING after blackout + wake."""
    _require_gpsim()
    from dlcp_fw.sim.chain_gpsim import SingleMainChainHarness

    pair = SingleMainChainHarness(
        stock_control_hex_v14,
        shifted_hex,
        fast_boot=False,
        control_chunk_cycles=200_000,
        main_chunk_cycles=200_000,
        hold_cycles=240_000,
        disable_standby_check=False,
        bypass_i2c=False,
        main_transport_mode="native_ring",
    )
    try:
        last = pair.run_until_connected(limit=140)
        assert last is not None
        assert pair.is_connected()

        pair.set_blackout(True)
        pair.press("STBY")
        pair.step_many(80)
        assert "ZZZ" in pair.lcd_lines()[0].upper(), \
            f"did not enter standby: {pair.lcd_lines()!r}"

        pair.press("STBY")
        waiting = pair.run_until_waiting(limit=20)
        assert waiting is not None
        assert pair.is_waiting(), \
            f"did not fall back to WAITING after wake: {waiting.lcd!r}"
    finally:
        pair.close()
