"""DSP boot state equivalence: V3.1 preset A must produce identical DSP
register state as stock V2.3.

Both firmwares have byte-identical preset table A at 0x5600. After boot,
the TAS3108 DSP registers loaded via I2C must match exactly. Any
difference means the I2C write path (i2c_byte_tx, coefficient math,
flash_read) has a regression in V3.1.

This is the highest-fidelity test for the "do biquad coefficients
reach the DSP correctly" question.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V26,
    STOCK_MAIN_HEX,
    V31_MAIN_HEX,
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


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


# Total MAIN-Tcy for each phase.  Advanced in single `step_tcy` calls
# under the rust universal-clock scheduler.
_BOOT_TCY = 4_000_000
_ACTIVATE_TCY = 4_000_000
# 12 M MAIN-Tcy settle: safely past the preset-loader convergence
# point (rust converges around 10 M Tcy).
_SETTLE_TCY = 12_000_000


def _boot_and_snapshot_dsp(main_hex: Path) -> dict[int, int]:
    """Boot the rust MAIN-only chain, activate, settle, return the full
    TAS3108 register snapshot after the preset loader has converged."""
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(main_hex))
    chain.step_tcy(_BOOT_TCY)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(_ACTIVATE_TCY)
    assert chain.read_reg(0x05E) & 0x08, "MAIN not active"

    chain.step_tcy(_SETTLE_TCY)

    return {r: chain.read_dsp_reg(r) for r in range(256)}


# ===================================================================
# Test 1: V3.1 DSP boot state matches stock V2.3 (preset A)
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v31_dsp_boot_state_matches_stock_preset_a() -> None:
    """V3.1 must produce identical DSP register state as stock V2.3.

    Both have the same preset table A at 0x5600. The I2C write path
    (i2c_byte_tx → coefficient math → DSP) must deliver identical data.

    Any mismatch means V3.1's i2c_byte_tx changes (bounded BF wait,
    ACKSTAT check, BSR save/restore) are altering the data path.
    """
    _skip_missing(STOCK_MAIN_HEX, V31_MAIN_HEX)
    stock_dsp = _boot_and_snapshot_dsp(STOCK_MAIN_HEX)
    v31_dsp = _boot_and_snapshot_dsp(V31_MAIN_HEX)
    mismatches = [
        (r, stock_dsp[r], v31_dsp[r])
        for r in range(256)
        if stock_dsp[r] != v31_dsp[r]
    ]
    assert not mismatches, (
        f"V3.1 DSP boot state differs from stock V2.3 in "
        f"{len(mismatches)} registers — preset A biquads NOT reaching "
        f"DSP correctly.\nFirst 10 mismatches: "
        f"{[(f'reg 0x{r:02X}: stock=0x{s:02X} v31=0x{v:02X}') for r, s, v in mismatches[:10]]}"
    )


# ===================================================================
# Test 2: All patched versions match stock DSP boot state
# ===================================================================


_PATCHED_VERSIONS = [
    pytest.param(PATCHED_MAIN_HEX_V24, id="v24"),
    pytest.param(PATCHED_MAIN_HEX_V26, id="v26"),
    pytest.param(V31_MAIN_HEX, id="v31"),
]


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("patched_hex", _PATCHED_VERSIONS)
def test_patched_dsp_boot_state_matches_stock(
    patched_hex: Path,
) -> None:
    """Every patched firmware must produce the same DSP boot state as stock.

    The preset table A is identical across all versions. The I2C data
    path must deliver the same coefficients to the TAS3108.
    """
    _skip_missing(STOCK_MAIN_HEX, patched_hex)
    stock_dsp = _boot_and_snapshot_dsp(STOCK_MAIN_HEX)
    patched_dsp = _boot_and_snapshot_dsp(patched_hex)
    mismatches = [
        (r, stock_dsp[r], patched_dsp[r])
        for r in range(256)
        if stock_dsp[r] != patched_dsp[r]
    ]
    assert not mismatches, (
        f"DSP boot state differs from stock in "
        f"{len(mismatches)} registers.\nMismatches: "
        f"{[(f'0x{r:02X}: stock=0x{s:02X} patched=0x{v:02X}') for r, s, v in mismatches[:10]]}"
    )


# ===================================================================
# Test 3: DSP non-zero registers match across versions
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_dsp_boot_nonzero_registers_consistent() -> None:
    """The SET of non-zero DSP registers after boot must be the same
    for stock and V3.1.  Catches silent byte drops (registers that
    should be written but aren't).
    """
    _skip_missing(STOCK_MAIN_HEX, V31_MAIN_HEX)
    stock_dsp = _boot_and_snapshot_dsp(STOCK_MAIN_HEX)
    v31_dsp = _boot_and_snapshot_dsp(V31_MAIN_HEX)
    stock_nz = {r for r, v in stock_dsp.items() if v != 0}
    v31_nz = {r for r, v in v31_dsp.items() if v != 0}
    missing_in_v31 = stock_nz - v31_nz
    extra_in_v31 = v31_nz - stock_nz
    assert not missing_in_v31, (
        f"V3.1 missing {len(missing_in_v31)} DSP registers "
        f"that stock sets: {[hex(r) for r in sorted(missing_in_v31)]}"
    )
    assert not extra_in_v31, (
        f"V3.1 has {len(extra_in_v31)} extra DSP registers "
        f"not in stock: {[hex(r) for r in sorted(extra_in_v31)]}"
    )
