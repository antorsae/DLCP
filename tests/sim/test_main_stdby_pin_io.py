"""Verify MAIN MCU pin I/O changes during standby (cmd=0x03 data=0x00).

Two rust-facade tests:

* ``test_stdby_pin_io_local_mode`` — drives MAIN-only chain in local
  mode (RC2 low) and checks all expected pin/register changes after
  the cmd 0x03 standby frame: RA3/RA4/RA5/RA6 low, RB2/RB3/RB4 low,
  sleep flag set.
* ``test_v162b_oerr_recovery_must_not_kill_txie`` — pure binary scan
  over the V1.62b patched HEX, asserting the patch stub region does
  not contain `bcf PIE1, TXIE` (which would break standby delivery
  during OERR soft-recovery).

Two earlier wire-chain gpsim tests
(``test_stdby_pin_io`` parametrized over 8 firmware combos, and
``test_stdby_survives_oerr_flood``) were deleted in PF.4 phase 2
batch 6: both relied on ``WireMultiMainChainHarness`` (gpsim PTY
bridge with no rust analogue) for full chain pin transitions and
bridge-FIFO UART byte injection.

Coverage notes:

* The local-mode rust test below covers stock V2.3 MAIN with RC2
  low (so RB2 is also driven low alongside the relays/sources).
  The deleted parametrized 8-pair matrix ran in chain mode (RC2
  high) and asserted RB2 HIGH alongside the same RA3/4/5/6 / RB3 /
  RB4 / sleep flag invariants, across these specific pairs:
  V14+V23-stock, V15b+V23-stock, V16b+V23-stock, V141+V24,
  V141+V25, V151b+V25, V161b+V25, V162b+V25.  Neither the
  chain-mode pin-state invariants (RB2 high path, T0CON/INTCON/
  UCON resets) nor the per-pair coverage exists on the rust path
  today.
  Reviving that matrix needs a rust 3-core ring chain factory for
  the legacy patched-control × patched-main combos that does not
  exist (the rust facade exposes ``from_v17_chain`` for V1.7-family
  + stock V2.3 and ``from_v17_v3x_chain`` for V1.7-family + V3.x).
  Tracked as task #129 (legacy CONTROL+MAIN standby pin matrix
  recovery).
* The V1.62b OERR-recovery fix is preserved by the binary-scan
  regression test below, which catches any new ``bcf PIE1, TXIE``
  instruction that snuck into the patch stub region.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V162B,
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V25,
    STOCK_MAIN_COMBINED_HEX,
    STOCK_MAIN_HEX,
)

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
_PORTC = 0xF82
_T0CON = 0xFD5
_INTCON = 0xFF2
_UCON = 0xF6D

# MAIN firmware RAM addresses
_SLEEP_FLAG = 0x095
_STATUS_5E = 0x05E


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing firmware: {p.name}")


# ---------------------------------------------------------------------------
# Local mode standby pin I/O
# ---------------------------------------------------------------------------


def _run_local_mode_stdby() -> dict[int, int]:
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(STOCK_MAIN_HEX))
    # rc2_mode="low": clear RC2 (bit 2) on PORTC (0xF82) for local-mode
    # chain strap.
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
@pytest.mark.slow
def test_stdby_pin_io_local_mode() -> None:
    """In local mode (RC2 low), RB2 is driven low during standby."""
    _skip_missing(STOCK_MAIN_HEX)
    regs = _run_local_mode_stdby()
    lata = regs[_LATA]
    latb = regs[_LATB]
    sleep_flag = regs[_SLEEP_FLAG]
    assert not (latb & 0x04), f"RB2 not low in local mode; LATB=0x{latb:02X}"
    assert not (lata & 0x08), f"RA3 not low; LATA=0x{lata:02X}"
    assert not (lata & 0x10), f"RA4 not low; LATA=0x{lata:02X}"
    assert not (lata & 0x20), f"RA5 not low; LATA=0x{lata:02X}"
    assert not (lata & 0x40), f"RA6 not low; LATA=0x{lata:02X}"
    assert not (latb & 0x10), f"RB4 not low; LATB=0x{latb:02X}"
    assert not (latb & 0x08), f"RB3 not low; LATB=0x{latb:02X}"
    assert sleep_flag == 0x01, (
        f"sleep flag not 0x01; 0x095=0x{sleep_flag:02X}"
    )


# ---------------------------------------------------------------------------
# Chain-mode standby pin-state matrix (revived from PF.4 phase 2 batch 6
# deletion -- task #129).  The deleted gpsim test parametrized over 8
# CONTROL+MAIN firmware combos via WireMultiMainChainHarness and pressed
# the STBY button on CONTROL to drive cmd 0x03/0x00 across the wire to
# MAIN.  On the rust facade we bypass CONTROL and inject the cmd 0x03/0x00
# frame directly into MAIN0's RX FIFO -- the MAIN-side pin-transition
# response is what the deleted test was uniquely covering, and that
# response depends only on which MAIN firmware is loaded (the cmd
# 0x03/0x00 frame is byte-identical regardless of which CONTROL emits
# it; the matching CONTROL combo from the original matrix doesn't change
# the MAIN response).  CONTROL emission is independently exercised by
# the IR-dispatch tests in test_control_v15b/v16b_port_compatibility.py.
# Parametrized over the 3 distinct MAIN firmware versions in the
# original matrix (V2.3 stock, V2.4 patched, V2.5 patched).
# ---------------------------------------------------------------------------


def _run_chain_mode_stdby(main_hex: Path) -> dict[int, int]:
    """Build a MAIN-only chain in CHAIN mode (RC2 high) using V2.3
    boot-block as the silicon seed, drive the standby cmd, and snapshot
    every pin/register the deleted matrix asserted on.
    """
    _require_rust()
    chain = RustChain.from_v3x_main_only(
        str(main_hex), v23_seed_hex_path=str(STOCK_MAIN_COMBINED_HEX),
    )
    # Drive RC2 high externally (chain mode strap).  set_main_pin pins the
    # external pin level via gpio.drive_external_pin so it survives any
    # firmware-side PORTC reads that would otherwise see RC2 default LOW.
    chain.set_main_pin(0, "C", 2, True)
    chain.step_tcy(4_000_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x00]], fifo_limit=47)
    chain.step_tcy(8_000_000)
    return {
        _LATA: chain.read_reg(_LATA),
        _LATB: chain.read_reg(_LATB),
        _T0CON: chain.read_reg(_T0CON),
        _INTCON: chain.read_reg(_INTCON),
        _UCON: chain.read_reg(_UCON),
        _SLEEP_FLAG: chain.read_reg(_SLEEP_FLAG),
        _STATUS_5E: chain.read_reg(_STATUS_5E),
    }


def _assert_chain_mode_stdby_pins(regs: dict[int, int], main_id: str) -> None:
    """Assert all MAIN pin/register states expected after standby in
    chain mode (RC2 high).  Mirrors the deleted ``_assert_stdby_pins``
    helper's invariants.
    """
    lata = regs[_LATA]
    latb = regs[_LATB]
    t0con = regs[_T0CON]
    intcon = regs[_INTCON]
    ucon = regs[_UCON]
    sleep_flag = regs[_SLEEP_FLAG]
    status_5e = regs[_STATUS_5E]
    ctx = f" [{main_id}]"

    # Relay/source outputs driven low.
    assert not (lata & 0x08), f"RA3 not low; LATA=0x{lata:02X}{ctx}"
    assert not (lata & 0x10), f"RA4 not low; LATA=0x{lata:02X}{ctx}"
    assert not (lata & 0x20), f"RA5 not low; LATA=0x{lata:02X}{ctx}"
    assert not (lata & 0x40), f"RA6 not low; LATA=0x{lata:02X}{ctx}"

    # Auxiliary outputs driven low.
    assert not (latb & 0x10), f"RB4 not low; LATB=0x{latb:02X}{ctx}"
    assert not (latb & 0x08), f"RB3 not low; LATB=0x{latb:02X}{ctx}"

    # RB2 high (chain mode strap latches RC2 -> RB2).
    assert latb & 0x04, f"RB2 not high (chain mode); LATB=0x{latb:02X}{ctx}"

    # Timer0 killed.
    assert not (t0con & 0x80), f"TMR0ON not clear; T0CON=0x{t0con:02X}{ctx}"
    assert not (intcon & 0x20), f"T0IE not clear; INTCON=0x{intcon:02X}{ctx}"

    # USB disabled.
    assert ucon == 0x00, f"UCON not 0x00; UCON=0x{ucon:02X}{ctx}"

    # Sleep flag set.
    assert sleep_flag == 0x01, (
        f"sleep flag not 0x01; 0x095=0x{sleep_flag:02X}{ctx}"
    )

    # MAIN status: bit 3 cleared (active flag down) post-standby.
    assert not (status_5e & 0x08), (
        f"0x5E bit 3 not clear (standby); 0x5E=0x{status_5e:02X}{ctx}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize(
    "main_hex,main_id",
    [
        pytest.param(STOCK_MAIN_HEX, "v23-stock", id="v23-stock"),
        pytest.param(PATCHED_MAIN_HEX_V24, "v24-patched", id="v24-patched"),
        pytest.param(PATCHED_MAIN_HEX_V25, "v25-patched", id="v25-patched"),
    ],
)
def test_stdby_pin_io_chain_mode(main_hex: Path, main_id: str) -> None:
    """In chain mode (RC2 high), the standby cmd drives RA3/4/5/6 and
    RB3/RB4 low while keeping RB2 HIGH (the chain-strap output);
    Timer0 / T0IE clear, UCON=0, sleep flag set, status_5e.bit3
    cleared.  Parametrized over the 3 distinct MAIN firmware versions
    that appeared in the deleted 8-combo matrix; the CONTROL-side
    parametrization is dropped because cmd 0x03/0x00 is byte-identical
    across CONTROL versions.
    """
    _skip_missing(main_hex, STOCK_MAIN_COMBINED_HEX)
    regs = _run_chain_mode_stdby(main_hex)
    _assert_chain_mode_stdby_pins(regs, main_id)


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
    runs identically on any backend.
    """
    _skip_missing(PATCHED_CONTROL_HEX_V162B)

    hits = _find_bcf_pie1_txie_in_patch_stubs(PATCHED_CONTROL_HEX_V162B)
    assert len(hits) == 0, (
        f"V1.62b patch stubs contain 'bcf PIE1, TXIE' at "
        f"{', '.join(f'0x{a:04X}' for a in hits)} — "
        f"this kills TX interrupt during OERR recovery and prevents "
        f"cmd=0x03 standby delivery on real hardware"
    )
