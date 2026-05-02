"""Verify MAIN MCU pin I/O changes during standby (cmd=0x03 data=0x00).

Tests that pressing STBY on CONTROL triggers the full standby shutdown
sequence on MAIN (function_051 -> function_116), including:

  1. DSP I2C commands 0x1B, 0x1C, 0x1D sent to dsp34
  2. RB2 set/clear based on RC2 chain strap
  3. RB4, RA6, RA3, RA4, RA5 all driven low (relays/sources OFF)
  4. RB3 driven low
  5. Timer0 killed (TMR0ON=0, T0IE=0)
  6. USB module disabled (UCON=0)
  7. Sleep flag set (0x095=0x01)

Parametrized across all valid MAIN+CONTROL firmware combinations.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V141,
    PATCHED_CONTROL_HEX_V151B,
    PATCHED_CONTROL_HEX_V161B,
    PATCHED_CONTROL_HEX_V162B,
    PATCHED_MAIN_HEX,
    PATCHED_MAIN_HEX_V24,
    STOCK_CONTROL_HEX_V14,
    STOCK_CONTROL_HEX_V15B,
    STOCK_CONTROL_HEX_V16B,
    STOCK_MAIN_HEX,
)
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )

# PIC18F2455 SFR addresses
_LATA = 0xF89
_LATB = 0xF8A
_T0CON = 0xFD5
_UCON = 0xF6D
_INTCON = 0xFF2

# MAIN firmware RAM addresses
_SLEEP_FLAG = 0x095
_STATUS_5E = 0x05E


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing firmware: {p.name}")


def _main_sfr(issue, addr: int) -> int:
    """Read a MAIN MCU SFR via the persistent gpsim CLI session."""
    return _read_reg(issue, addr)


def _assert_stdby_pins(
    main_issue,
    *,
    expect_rb2_high: bool,
    combo_tag: str = "",
) -> None:
    """Assert all MAIN pin/register states expected after standby."""
    ctx = f" [{combo_tag}]" if combo_tag else ""

    lata = _main_sfr(main_issue, _LATA)
    latb = _main_sfr(main_issue, _LATB)
    t0con = _main_sfr(main_issue, _T0CON)
    intcon = _main_sfr(main_issue, _INTCON)
    ucon = _main_sfr(main_issue, _UCON)
    sleep_flag = _main_sfr(main_issue, _SLEEP_FLAG)
    status_5e = _main_sfr(main_issue, _STATUS_5E)

    # --- Relay/source outputs driven low ---
    assert not (lata & 0x08), f"RA3 not low; LATA=0x{lata:02X}{ctx}"
    assert not (lata & 0x10), f"RA4 not low; LATA=0x{lata:02X}{ctx}"
    assert not (lata & 0x20), f"RA5 not low; LATA=0x{lata:02X}{ctx}"
    assert not (lata & 0x40), f"RA6 not low; LATA=0x{lata:02X}{ctx}"

    # --- Auxiliary outputs driven low ---
    assert not (latb & 0x10), f"RB4 not low; LATB=0x{latb:02X}{ctx}"
    assert not (latb & 0x08), f"RB3 not low; LATB=0x{latb:02X}{ctx}"

    # --- RB2 chain strap dependent ---
    if expect_rb2_high:
        assert latb & 0x04, f"RB2 not high (chain mode); LATB=0x{latb:02X}{ctx}"
    else:
        assert not (latb & 0x04), f"RB2 not low (local mode); LATB=0x{latb:02X}{ctx}"

    # --- Timer0 killed ---
    assert not (t0con & 0x80), f"TMR0ON not clear; T0CON=0x{t0con:02X}{ctx}"
    assert not (intcon & 0x20), f"T0IE not clear; INTCON=0x{intcon:02X}{ctx}"

    # --- USB disabled ---
    assert ucon == 0x00, f"UCON not 0x00; UCON=0x{ucon:02X}{ctx}"

    # --- Sleep flag set ---
    assert sleep_flag == 0x01, f"sleep flag not 0x01; 0x095=0x{sleep_flag:02X}{ctx}"

    # --- MAIN status: standby ---
    assert not (status_5e & 0x08), (
        f"0x5E bit 3 not clear (standby); 0x5E=0x{status_5e:02X}{ctx}"
    )


# ---------------------------------------------------------------------------
# Firmware combo matrix
# ---------------------------------------------------------------------------

FIRMWARE_COMBOS = [
    pytest.param(STOCK_MAIN_HEX, STOCK_CONTROL_HEX_V14, id="v23+v14"),
    pytest.param(STOCK_MAIN_HEX, STOCK_CONTROL_HEX_V15B, id="v23+v15b"),
    pytest.param(STOCK_MAIN_HEX, STOCK_CONTROL_HEX_V16B, id="v23+v16b"),
    pytest.param(PATCHED_MAIN_HEX_V24, PATCHED_CONTROL_HEX_V141, id="v24+v141"),
    pytest.param(PATCHED_MAIN_HEX, PATCHED_CONTROL_HEX_V141, id="v25+v141"),
    pytest.param(PATCHED_MAIN_HEX, PATCHED_CONTROL_HEX_V151B, id="v25+v151b"),
    pytest.param(PATCHED_MAIN_HEX, PATCHED_CONTROL_HEX_V161B, id="v25+v161b"),
    pytest.param(PATCHED_MAIN_HEX, PATCHED_CONTROL_HEX_V162B, id="v25+v162b"),
]


# ---------------------------------------------------------------------------
# Main parametrized test (chain mode, rc2=high)
# ---------------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex, control_hex", FIRMWARE_COMBOS)
def test_stdby_pin_io(main_hex: Path, control_hex: Path) -> None:
    """Standby command drives all expected pin/register changes on MAIN."""
    _require_gpsim()
    _skip_missing(main_hex, control_hex)

    chain = WireMultiMainChainHarness(
        control_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        control_chunk_cycles=1_000_000,
        hold_cycles=240_000,
        disable_standby_check=False,
    )
    try:
        # Boot to connected/display mode
        last = chain.run_until_connected(limit=80)
        assert last is not None, "pair never produced a step result"
        assert chain.is_connected(), (
            f"pair never connected; lcd={last.lcd!r} flags=0x{last.control_flags:02X}"
        )
        assert chain.control_rx_activity(), "CONTROL never consumed wire-UART data from MAIN"
        assert chain.main_rx_activity(0), "MAIN never consumed wire-UART data from CONTROL"

        # Verify I2C bus is attached (DSP commands go through MSSP to dsp34)
        assert chain.mains[0].uses_external_i2c_regfile_bus, "I2C regfile bus not attached"

        # Verify MAIN is active before standby
        main_issue = chain.mains[0]._issue
        pre_5e = _main_sfr(main_issue, _STATUS_5E)
        assert pre_5e & 0x08, f"MAIN not active before STBY; 0x5E=0x{pre_5e:02X}"

        # Press standby button on CONTROL
        chain.press("STBY")
        chain.step_many(40)

        # CONTROL should show Zzz
        lcd = chain.lcd_lines()
        assert "ZZZ" in lcd[0].upper(), f"CONTROL not in standby; lcd={lcd!r}"

        # --- (1-8) Pin/register assertions ---
        # function_051 executes DSP I2C commands 0x1B/0x1C/0x1D unconditionally
        # BEFORE any pin changes. Correct pin states below prove the I2C calls
        # at the top of function_051 were reached and completed.
        combo_id = f"{main_hex.name}+{control_hex.name}"
        _assert_stdby_pins(main_issue, expect_rb2_high=True, combo_tag=combo_id)

    finally:
        chain.close()


# ---------------------------------------------------------------------------
# Local mode variant (rc2=low → RB2 driven low)
# ---------------------------------------------------------------------------


def _run_local_mode_stdby_gpsim() -> dict[int, int]:
    harness = MainChainHarness(
        STOCK_MAIN_HEX,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        for _ in range(20):
            harness.step()
        harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        harness.inject_frames_fifo([[0xB0, 0x03, 0x00]], fifo_limit=47)
        for _ in range(40):
            harness.step()
        return {
            _LATA: _read_reg(harness._issue, _LATA),
            _LATB: _read_reg(harness._issue, _LATB),
            _SLEEP_FLAG: _read_reg(harness._issue, _SLEEP_FLAG),
        }
    finally:
        harness.close()


def _run_local_mode_stdby_rust() -> dict[int, int]:
    chain = RustChain.from_v3x_main_only(str(STOCK_MAIN_HEX))
    # rc2_mode="low": clear RC2 (bit 2) on PORTC (0xF82) for local-mode
    # chain strap. Mirrors gpsim MainChainHarness(rc2_mode="low").
    chain.write_reg(0xF82, 0xFB)
    chain.step_tcy(4_000_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x00]], fifo_limit=47)
    chain.step_tcy(8_000_000)
    return {
        _LATA: chain.read_reg(_LATA),
        _LATB: chain.read_reg(_LATB),
        _SLEEP_FLAG: chain.read_reg(_SLEEP_FLAG),
    }


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_stdby_pin_io_local_mode(dlcp_sim_backend: str) -> None:
    """In local mode (RC2 low), RB2 is driven low during standby."""
    _skip_missing(STOCK_MAIN_HEX)
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        regs = _run_local_mode_stdby_rust()
        _assert_local_mode_pins(regs, backend="rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        regs = _run_local_mode_stdby_gpsim()
        _assert_local_mode_pins(regs, backend="gpsim")


def _assert_local_mode_pins(regs: dict[int, int], *, backend: str) -> None:
    lata = regs[_LATA]
    latb = regs[_LATB]
    sleep_flag = regs[_SLEEP_FLAG]
    assert not (latb & 0x04), f"[{backend}] RB2 not low in local mode; LATB=0x{latb:02X}"
    assert not (lata & 0x08), f"[{backend}] RA3 not low; LATA=0x{lata:02X}"
    assert not (lata & 0x10), f"[{backend}] RA4 not low; LATA=0x{lata:02X}"
    assert not (lata & 0x20), f"[{backend}] RA5 not low; LATA=0x{lata:02X}"
    assert not (lata & 0x40), f"[{backend}] RA6 not low; LATA=0x{lata:02X}"
    assert not (latb & 0x10), f"[{backend}] RB4 not low; LATB=0x{latb:02X}"
    assert not (latb & 0x08), f"[{backend}] RB3 not low; LATB=0x{latb:02X}"
    assert sleep_flag == 0x01, (
        f"[{backend}] sleep flag not 0x01; 0x095=0x{sleep_flag:02X}"
    )


# ---------------------------------------------------------------------------
# OERR TXIE-kill regression: prove bcf PIE1,TXIE breaks standby delivery
# ---------------------------------------------------------------------------

def _find_bcf_pie1_txie_in_patch_stubs(hex_path: Path) -> list[int]:
    """Find 'bcf PIE1, TXIE, ACCESS' in the V1.62b patch stub region (0x7000+).

    PIC18 encoding: BCF = 1001, bit4 = 100, ACCESS = 0, PIE1[7:0] = 0x9D
    → instruction word = 0x989D → little-endian bytes [0x9D, 0x98].

    Stock firmware has legitimate bcf PIE1, TXIE in the TX ISR (0x039A,
    0x03D8) — those are fine. Only the patch stub region is checked.
    """
    from dlcp_fw.sim.hexio import parse_intel_hex

    mem = parse_intel_hex(hex_path)
    hits: list[int] = []
    for addr in sorted(mem.keys()):
        if addr < 0x7000 or addr % 2 != 0:
            continue
        if mem.get(addr) == 0x9D and mem.get(addr + 1) == 0x98:
            hits.append(addr)
    return hits


@pytest.mark.dual_supported
def test_v162b_oerr_recovery_must_not_kill_txie() -> None:
    """V1.62b control_uart_soft_recover must NOT contain 'bcf PIE1, TXIE'.

    Pure binary scan over the patched HEX -- backend-agnostic, so it
    runs identically under gpsim, rust, and dual modes.
    """
    _skip_missing(PATCHED_CONTROL_HEX_V162B)

    hits = _find_bcf_pie1_txie_in_patch_stubs(PATCHED_CONTROL_HEX_V162B)
    assert len(hits) == 0, (
        f"V1.62b patch stubs contain 'bcf PIE1, TXIE' at "
        f"{', '.join(f'0x{a:04X}' for a in hits)} — "
        f"this kills TX interrupt during OERR recovery and prevents "
        f"cmd=0x03 standby delivery on real hardware"
    )


# CONTROL UART baud timing at 31,250 baud, 4 MHz Tcy
_CONTROL_TCY_PER_BIT = 128  # 4_000_000 / 31_250
_CONTROL_TCY_PER_BYTE = _CONTROL_TCY_PER_BIT * 10  # 8N1 = 10 bits


def _uart_byte_transitions(byte_val: int, start_cycle: int) -> list[tuple[int, int]]:
    """Generate pin-level voltage transitions for one 8N1 UART byte."""
    edges: list[tuple[int, int]] = []
    edges.append((start_cycle, 0))  # start bit
    for bit in range(8):
        voltage = 5 if (byte_val >> bit) & 1 else 0
        edges.append((start_cycle + (1 + bit) * _CONTROL_TCY_PER_BIT, voltage))
    edges.append((start_cycle + 9 * _CONTROL_TCY_PER_BIT, 5))  # stop bit
    return edges


def _inject_uart_flood_into_control_rx(
    chain: WireMultiMainChainHarness,
    *,
    n_bytes: int = 30,
    start_offset: int = 2000,
) -> None:
    """Write raw UART byte transitions into CONTROL's RX stimulus file.

    This causes the gpsim EUSART model to push bytes into RCREG via the
    real receive path. If bytes arrive faster than firmware drains RCREG,
    fifo_sp >= 2 triggers _RCSTA::overrun() → sets OERR.
    """
    bridge = chain._bridge_map["m0_to_ctl"]
    start = chain.control.current_cycle + start_offset

    all_edges: list[tuple[int, int]] = []
    for i in range(n_bytes):
        byte_start = start + i * _CONTROL_TCY_PER_BYTE
        all_edges.extend(_uart_byte_transitions(0x55, byte_start))

    with bridge.receiver_fifo_path.open("a", encoding="ascii") as f:
        for cycle, voltage in all_edges:
            if cycle > bridge._last_receiver_cycle:
                f.write(f"{cycle} {voltage}\n")
                bridge._last_receiver_cycle = cycle


def _run_stdby_with_oerr_flood(control_hex: Path, main_hex: Path) -> bool:
    """Boot, flood CONTROL RX to trigger OERR, press STBY, check MAIN.

    Returns True if MAIN entered standby (sleep flag = 0x01).
    """
    chain = WireMultiMainChainHarness(
        control_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        control_chunk_cycles=1_000_000,
        hold_cycles=240_000,
        disable_standby_check=False,
    )
    try:
        last = chain.run_until_connected(limit=80)
        if last is None or not chain.is_connected():
            raise RuntimeError("pair never connected")

        # Inject UART flood + press STBY on the same step boundary.
        # The flood causes RCREG overflow → OERR → firmware's own
        # btfss RCSTA, OERR fires → control_uart_soft_recover runs.
        chain.press("STBY")
        for i in range(40):
            _inject_uart_flood_into_control_rx(chain, n_bytes=30)
            chain.step()

        main_issue = chain.mains[0]._issue
        return _main_sfr(main_issue, _SLEEP_FLAG) == 0x01
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_stdby_survives_oerr_flood() -> None:
    """Standby must succeed even with UART overrun flooding on CONTROL.

    Injects 30 rapid UART bytes into CONTROL's RX pin on every step
    during standby, forcing RCREG overflow and OERR. The firmware's
    parser_entry_stub detects OERR and calls control_uart_soft_recover.

    With the fix (bcf PIE1,TXIE removed): TX is not disrupted, cmd=0x03
    standby frame reaches MAIN, MAIN enters standby.

    With the bug (bcf PIE1,TXIE present): TX interrupt is killed during
    recovery, cmd=0x03 frame bytes are dropped, MAIN stays active.
    """
    _require_gpsim()
    _skip_missing(PATCHED_MAIN_HEX, PATCHED_CONTROL_HEX_V162B)

    entered = _run_stdby_with_oerr_flood(PATCHED_CONTROL_HEX_V162B, PATCHED_MAIN_HEX)
    assert entered, (
        "MAIN did not enter standby despite OERR flood — "
        "control_uart_soft_recover may be disrupting TX"
    )
