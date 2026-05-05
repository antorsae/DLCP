"""Isolated proof of the three DSP deafness bugs (DSP1/DSP2/DSP3).

After a transient I2C address NACK on the TAS3108 (dsp34), MAIN
silently loses the ability to update DSP coefficients.  Three bugs
conspire to make this invisible:

DSP1 — ``i2c_ackstat_never_checked``: function_056 (i2c_byte_tx at
0x3EB8) checks WCOL, SSPIF, and BF but never reads SSPCON2.ACKSTAT
(bit 6 of 0xFC5).  A NACKed address phase goes undetected.

DSP2 — ``dirty_bit_cleared_unconditionally``: after the I2C write
attempt, the volume dirty flag (0x07E.bit3) is cleared regardless
of whether the write succeeded.  MAIN will not retry.

DSP3 — ``no_dsp_readback``: MAIN updates its internal volume state
(0x06E) BEFORE the I2C write and reports that cached value to
CONTROL.  There is no TAS3108 readback via address 0x69.  CONTROL
sees the new volume on the LCD; the audio doesn't change.

All three bugs are present in V2.3 (stock), V2.4, and V2.5.
V2.5's MSSP timeout recovery adds bounded waits and MSSP reset
but still does not check ACKSTAT or verify DSP state.

V2.6/V3.1 fix the chain (Fix A/B/B' below in immune-version tests).

See: docs/analysis/SEMANTIC_FUNCTION_MAP.md (DSP1/DSP2/DSP3 entries)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_MAIN_HEX_V24,
    PATCHED_MAIN_HEX_V25,
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


_STATUS_5E = 0x05E
_FLAGS_7E = 0x07E
_VOLUME_REG = 0x06E

_BOOT_TCY = 4_000_000
_BASELINE_TCY = 4_000_000
_NACK_TCY = 6_000_000
_NACK_SHORT_TCY = 3_000_000
_RECOVERY_TCY = 4_000_000


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


class _RustBackend:
    """Thin rust adapter exposing the helper surface used in this file."""

    def __init__(self, main_hex: Path):
        self._c = RustChain.from_v3x_main_only(str(main_hex))

    def boot_and_activate(self) -> None:
        self._c.step_tcy(_BOOT_TCY)
        self._c.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        self._c.step_tcy(_BOOT_TCY)

    def step_tcy(self, tcy: int) -> None:
        self._c.step_tcy(tcy)

    def read_reg(self, addr: int) -> int:
        return self._c.read_reg(addr)

    def dsp_snapshot(self) -> dict[int, int]:
        return {r: self._c.read_dsp_reg(r) for r in range(256)}

    def inject_frame(self, frame: list[int]) -> None:
        self._c.inject_main_frames_fifo([frame], fifo_limit=47)

    def set_nack_fault(self, count: int) -> None:
        self._c.set_i2c_fault("dsp34", address_nack_count=count)

    def clear_nack_faults(self) -> None:
        self._c.clear_i2c_faults("dsp34")

    def read_nack_remaining(self) -> int:
        return int(self._c.read_dsp_address_nack_count_remaining())


def _make_backend(main_hex: Path) -> _RustBackend:
    _require_rust()
    return _RustBackend(main_hex)


def _dsp34_diff(
    before: dict[int, int], after: dict[int, int],
) -> list[tuple[int, int, int]]:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


_MAIN_VERSIONS = [
    pytest.param(STOCK_MAIN_HEX, id="main_v23_stock"),
    pytest.param(PATCHED_MAIN_HEX_V24, id="main_v24"),
    pytest.param(PATCHED_MAIN_HEX_V25, id="main_v25"),
    pytest.param(V31_MAIN_HEX, id="main_v31"),
]


def _run_deafness_chain_test(
    bk: _RustBackend, *, expect_dsp_deafness: bool,
) -> None:
    """Body shared by the parametrized deafness-chain test.

    expect_dsp_deafness=True for V2.3/V2.4/V2.5 (the bug is present);
    False for V3.1 (the bug is fixed; the immune-version tests separately
    drill into the V3.1-specific Fix A/B/B' invariants).
    """
    bk.boot_and_activate()
    assert bk.read_reg(_STATUS_5E) & 0x08, "MAIN not active"

    # Phase 1: DSP baseline -- volume cmd should change dsp34 regs.
    snap_a = bk.dsp_snapshot()
    bk.inject_frame([0xB0, 0x07, 0x50])
    bk.step_tcy(_BASELINE_TCY)
    diff_baseline = _dsp34_diff(snap_a, bk.dsp_snapshot())
    assert len(diff_baseline) > 0, (
        "volume cmd did not change any dsp34 register -- baseline broken"
    )

    vol_after_baseline = bk.read_reg(_VOLUME_REG)

    # Phase 2: inject NACKs, send different volume.
    bk.set_nack_fault(60000)
    nack_before = bk.read_nack_remaining()
    bk.inject_frame([0xB0, 0x07, 0x30])
    bk.step_tcy(_NACK_TCY)

    nack_after = bk.read_nack_remaining()
    nacks_consumed = nack_before - nack_after

    # Phase 3: assert all three DSP deafness bugs (or, for V3.1,
    # the bug-class is fixed and these assertions don't hold).
    if expect_dsp_deafness:
        # DSP1: NACKs consumed but MAIN set NO error flag.
        assert nacks_consumed > 0, (
            f"DSP1 precondition: no I2C address NACKs consumed "
            f"(before={nack_before} after={nack_after}) -- "
            "volume cmd may not have triggered I2C writes"
        )
        # MAIN's status register is unchanged (no error indication).
        status_5e = bk.read_reg(_STATUS_5E)
        assert status_5e & 0x08, (
            f"MAIN dropped active flag after NACKed I2C -- "
            f"0x5E=0x{status_5e:02X} (expected bit3 set)"
        )

        # DSP2: volume dirty bit (0x07E.bit3) must be CLEARED.
        flags_7e = bk.read_reg(_FLAGS_7E)
        assert not (flags_7e & 0x08), (
            f"DSP2 disproved: 0x07E.bit3 still set "
            f"(0x{flags_7e:02X}) -- MAIN would retry the DSP write"
        )

        # DSP3: MAIN's internal volume must have CHANGED.
        vol_after_nack = bk.read_reg(_VOLUME_REG)
        assert vol_after_nack != vol_after_baseline, (
            f"DSP3 disproved: 0x06E unchanged "
            f"(0x{vol_after_nack:02X}) -- MAIN did not update its "
            "cached volume state"
        )

    # Phase 4: recovery.
    bk.clear_nack_faults()
    snap_d = bk.dsp_snapshot()
    bk.inject_frame([0xB0, 0x07, 0x40])
    bk.step_tcy(_RECOVERY_TCY)
    diff_recovery = _dsp34_diff(snap_d, bk.dsp_snapshot())
    assert len(diff_recovery) > 0, (
        "DSP did not respond to volume cmd after NACKs cleared -- "
        "harness I2C path may be broken"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _MAIN_VERSIONS)
def test_main_dsp_deafness_chain_ackstat_dirty_readback(
    main_hex: Path,
) -> None:
    """One-shot dsp34 NACK proves the DSP deafness chain (DSP1+DSP2+DSP3).

    For V2.3/V2.4/V2.5 (deafness present), assert the bug surface:
      - DSP1: dsp34 slave NACKed (Address_Nack_Count decremented)
              but MAIN set no error flag — firmware ignored it.
      - DSP2: 0x07E.bit3 (volume_dirty) is CLEARED (no retry).
      - DSP3: 0x06E (cached volume) IS UPDATED to the new value.
    For V3.1 (deafness fixed), the assertions are weaker (DSP retry
    is in flight; the immune-version test drills into Fix A/B/B').
    """
    if not main_hex.exists():
        pytest.skip(f"missing: {main_hex.name}")
    expect_deafness = main_hex != V31_MAIN_HEX
    bk = _make_backend(main_hex)
    _run_deafness_chain_test(bk, expect_dsp_deafness=expect_deafness)


def _run_v26_immune_test(bk: _RustBackend) -> None:
    bk.boot_and_activate()
    assert bk.read_reg(_STATUS_5E) & 0x08, "MAIN not active"

    # Baseline.
    snap_a = bk.dsp_snapshot()
    bk.inject_frame([0xB0, 0x07, 0x50])
    bk.step_tcy(_BASELINE_TCY)
    diff_baseline = _dsp34_diff(snap_a, bk.dsp_snapshot())
    assert len(diff_baseline) > 0, "baseline broken"

    vol_baseline = bk.read_reg(_VOLUME_REG)
    stat_baseline = bk.read_reg(0x066)

    # Phase 1: NACKed volume command.
    bk.set_nack_fault(60000)
    bk.inject_frame([0xB0, 0x07, 0x30])
    bk.step_tcy(_NACK_SHORT_TCY)

    flags_7f = bk.read_reg(0x07F)
    stat_nack = bk.read_reg(0x066)

    err_latched = bool(flags_7f & 0x04)
    retry_count = (flags_7f >> 3) & 0x07

    # Fix A: ACKSTAT must have been detected.
    assert retry_count > 0 or err_latched, (
        f"Fix A: no NACK detection — 0x07F=0x{flags_7f:02X} "
        f"(err={err_latched}, retry={retry_count})"
    )
    # Fix B': status RAM must be UNCHANGED from baseline.
    assert stat_nack == stat_baseline, (
        f"Fix B': status committed despite NACK — "
        f"stat=0x{stat_nack:02X} (baseline=0x{stat_baseline:02X})"
    )

    # Phase 2: recovery.
    bk.clear_nack_faults()
    snap_b = bk.dsp_snapshot()
    bk.inject_frame([0xB0, 0x07, 0x40])
    bk.step_tcy(_RECOVERY_TCY)
    diff_recovery = _dsp34_diff(snap_b, bk.dsp_snapshot())
    stat_post = bk.read_reg(0x066)
    vol_post = bk.read_reg(_VOLUME_REG)

    assert len(diff_recovery) > 0, (
        "recovery failed: volume cmd after NACK clear did not change "
        "DSP registers"
    )
    assert vol_post != vol_baseline, (
        f"recovery: volume register unchanged from baseline "
        f"(0x{vol_post:02X} == 0x{vol_baseline:02X})"
    )
    assert stat_post == vol_post, (
        f"status RAM not committed after recovery: "
        f"stat=0x{stat_post:02X} vol=0x{vol_post:02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main_v26_immune_to_dsp_deafness_chain() -> None:
    """V2.6 detects I2C NACKs, keeps dirty bit, defers commit."""
    if not PATCHED_MAIN_HEX_V26.exists():
        pytest.skip(f"missing: {PATCHED_MAIN_HEX_V26.name}")
    bk = _make_backend(PATCHED_MAIN_HEX_V26)
    _run_v26_immune_test(bk)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main_v31_immune_to_dsp_deafness_chain() -> None:
    """V3.1 detects I2C NACKs, keeps dirty bit, defers commit.
    Same Fix A/B/B' invariants as V2.6."""
    if not V31_MAIN_HEX.exists():
        pytest.skip(f"missing: {V31_MAIN_HEX.name}")
    bk = _make_backend(V31_MAIN_HEX)
    _run_v26_immune_test(bk)
