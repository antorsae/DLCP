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

# MAIN firmware RAM addresses
_SLEEP_FLAG = 0x095


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
