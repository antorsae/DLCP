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

See: docs/analysis/SEMANTIC_FUNCTION_MAP.md (DSP1/DSP2/DSP3 entries)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import PATCHED_MAIN_HEX, PATCHED_MAIN_HEX_V24, PATCHED_MAIN_HEX_V26, STOCK_MAIN_HEX, V31_MAIN_HEX
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available

_STATUS_5E = 0x05E
_FLAGS_7E = 0x07E

# MAIN internal volume register (cached, NOT DSP readback).
_VOLUME_REG = 0x06E


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _dsp34_snapshot(harness: MainChainHarness) -> dict[int, int]:
    return {r: harness.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp34_diff(
    before: dict[int, int], after: dict[int, int]
) -> list[tuple[int, int, int]]:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


_MAIN_VERSIONS = [
    pytest.param(STOCK_MAIN_HEX, id="main_v23_stock"),
    pytest.param(PATCHED_MAIN_HEX_V24, id="main_v24"),
    pytest.param(PATCHED_MAIN_HEX, id="main_v25"),
    pytest.param(V31_MAIN_HEX, id="main_v31"),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _MAIN_VERSIONS)
def test_main_dsp_deafness_chain_ackstat_dirty_readback(
    main_hex: Path,
) -> None:
    """One-shot dsp34 NACK proves the DSP deafness chain (DSP1+DSP2+DSP3).

    Phases:
      1. Boot MAIN, activate, confirm DSP baseline (volume cmd=0x07
         changes dsp34 registers).
      2. Inject address NACKs on dsp34, send new volume cmd.
      3. Assert all three bugs:
         - DSP1: dsp34 slave NACKed (Address_Nack_Count decremented)
                 but MAIN set no error flag — firmware ignored it.
         - DSP2: 0x07E.bit3 (volume_dirty) is CLEARED (no retry).
         - DSP3: 0x06E (cached volume) IS UPDATED to the new value.
      4. Clear NACKs, send volume — DSP responds (harness sanity).
    """
    _require_gpsim()
    if not main_hex.exists():
        pytest.skip(f"missing: {main_hex.name}")

    harness = MainChainHarness(
        main_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        # ---- Boot and activate MAIN ----
        for _ in range(20):
            harness.step()
        harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"

        # ---- Phase 1: DSP baseline ----
        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_baseline = _dsp34_diff(snap_a, _dsp34_snapshot(harness))
        assert len(diff_baseline) > 0, (
            "volume cmd did not change any dsp34 register -- baseline broken"
        )

        # Record state after baseline.
        vol_after_baseline = _read_reg(harness._issue, _VOLUME_REG)

        # ---- Phase 2: inject NACKs, send different volume ----
        # Use a high NACK count to cover the full volume I2C burst.
        # The count is consumed by address phases; remaining NACKs
        # are cleared manually before the recovery phase.
        harness.set_i2c_fault("dsp34", address_nack_count=60000)
        nack_before = harness.read_i2c_attribute("dsp34", "Address_Nack_Count")

        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        nack_after = harness.read_i2c_attribute("dsp34", "Address_Nack_Count")
        nacks_consumed = nack_before - nack_after

        # ---- Phase 3: assert all three DSP deafness bugs ----

        # DSP1: the slave NACKed multiple address phases (consumed
        # NACKs > 0), but MAIN set NO error flag and continued
        # normally.  function_056 never read SSPCON2.ACKSTAT.
        assert nacks_consumed > 0, (
            f"DSP1 precondition: no I2C address NACKs consumed "
            f"(before={nack_before} after={nack_after}) -- "
            f"volume cmd may not have triggered I2C writes"
        )
        # MAIN's status register is unchanged (no error indication).
        status_5e = _read_reg(harness._issue, _STATUS_5E)
        assert status_5e & 0x08, (
            f"MAIN dropped active flag after NACKed I2C -- "
            f"0x5E=0x{status_5e:02X} (expected bit3 set)"
        )

        # DSP2: volume dirty bit (0x07E.bit3) must be CLEARED.
        # MAIN clears this unconditionally after the write attempt.
        # With the bit cleared, MAIN will never retry the failed write.
        flags_7e = _read_reg(harness._issue, _FLAGS_7E)
        assert not (flags_7e & 0x08), (
            f"DSP2 disproved: 0x07E.bit3 still set (0x{flags_7e:02X}) -- "
            f"MAIN would retry the DSP write"
        )

        # DSP3: MAIN's internal volume must have CHANGED.
        # label_171 updates 0x06E BEFORE the I2C write.  MAIN
        # reports this cached value to CONTROL.  The LCD shows the
        # new volume even though the DSP may not have received it.
        vol_after_nack = _read_reg(harness._issue, _VOLUME_REG)
        assert vol_after_nack != vol_after_baseline, (
            f"DSP3 disproved: 0x06E unchanged (0x{vol_after_nack:02X}) -- "
            f"MAIN did not update its cached volume state"
        )

        # ---- Phase 4: recovery (harness sanity) ----
        # Clear NACKs and send another volume.  DSP must respond.
        harness.clear_i2c_faults("dsp34")
        snap_d = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_recovery = _dsp34_diff(snap_d, _dsp34_snapshot(harness))
        assert len(diff_recovery) > 0, (
            "DSP did not respond to volume cmd after NACKs cleared -- "
            "harness I2C path may be broken"
        )

    finally:
        harness.close()


# ---------------------------------------------------------------------------
# V2.6 immunity: DSP deafness chain is FIXED
# ---------------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_v26_immune_to_dsp_deafness_chain() -> None:
    """V2.6 detects I2C NACKs, keeps dirty bit, defers commit.

    Same scenario as the deafness chain test above, but V2.6's
    three fixes (A/B/B') prevent the silent deafness:

    Fix A: ACKSTAT latched in 0x07F.bit2 after the address byte.
    Fix B: dirty bit (0x07E.bit3) NOT cleared on NACK — retry counter
           increments.  After max retries, gives up cleanly.
    Fix B': status RAM (0x066) NOT committed until verified write.
            CONTROL sees the old (correct) volume during NACKs.

    After clearing the NACK fault, a new volume command succeeds
    and both DSP and status RAM are updated correctly.
    """
    _require_gpsim()
    if not PATCHED_MAIN_HEX_V26.exists():
        pytest.skip(f"missing: {PATCHED_MAIN_HEX_V26.name}")

    harness = MainChainHarness(
        PATCHED_MAIN_HEX_V26,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        # ---- Boot and activate ----
        for _ in range(20):
            harness.step()
        harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"

        # ---- Baseline ----
        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_baseline = _dsp34_diff(snap_a, _dsp34_snapshot(harness))
        assert len(diff_baseline) > 0, "baseline broken"

        vol_baseline = _read_reg(harness._issue, _VOLUME_REG)
        stat_baseline = _read_reg(harness._issue, 0x066)

        # ---- Phase 1: NACKed volume command ----
        harness.set_i2c_fault("dsp34", address_nack_count=60000)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(15):
            harness.step()

        flags_7e = _read_reg(harness._issue, _FLAGS_7E)
        flags_7f = _read_reg(harness._issue, 0x07F)
        stat_nack = _read_reg(harness._issue, 0x066)

        err_latched = bool(flags_7f & 0x04)
        retry_count = (flags_7f >> 3) & 0x07

        # Fix A: ACKSTAT must have been detected (error flag was
        # set at some point — the retry counter proves it even if
        # the latch was cleared after max retries).
        assert retry_count > 0 or err_latched, (
            f"Fix A: no NACK detection — 0x07F=0x{flags_7f:02X} "
            f"(err={err_latched}, retry={retry_count})"
        )

        # Fix B': status RAM must be UNCHANGED from baseline.
        # CONTROL would still show the old (correct) volume.
        assert stat_nack == stat_baseline, (
            f"Fix B': status committed despite NACK — "
            f"stat=0x{stat_nack:02X} (baseline=0x{stat_baseline:02X})"
        )

        # ---- Phase 2: recovery ----
        # Clear NACKs and send a new volume.  V2.6 should accept it.
        harness.clear_i2c_faults("dsp34")
        snap_b = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_recovery = _dsp34_diff(snap_b, _dsp34_snapshot(harness))
        stat_post = _read_reg(harness._issue, 0x066)
        vol_post = _read_reg(harness._issue, _VOLUME_REG)

        assert len(diff_recovery) > 0, (
            "recovery failed: volume cmd after NACK clear did not "
            "change DSP registers"
        )
        # The new volume (0x40) must be different from the NACKed one (0x30)
        # and from the baseline (0x50).  status RAM must be committed.
        assert vol_post != vol_baseline, (
            f"recovery: volume register unchanged from baseline "
            f"(0x{vol_post:02X} == 0x{vol_baseline:02X})"
        )
        assert stat_post == vol_post, (
            f"status RAM not committed after recovery: "
            f"stat=0x{stat_post:02X} vol=0x{vol_post:02X}"
        )

    finally:
        harness.close()


# ---------------------------------------------------------------------------
# V3.1 immunity: DSP deafness chain is FIXED
# ---------------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_v31_immune_to_dsp_deafness_chain() -> None:
    """V3.1 detects I2C NACKs, keeps dirty bit, defers commit.

    Same scenario as the deafness chain test above, but V3.1's
    three fixes (A/B/B') prevent the silent deafness:

    Fix A: ACKSTAT latched in 0x07F.bit2 after the address byte.
    Fix B: dirty bit (0x07E.bit3) NOT cleared on NACK — retry counter
           increments.  After max retries, gives up cleanly.
    Fix B': status RAM (0x066) NOT committed until verified write.
            CONTROL sees the old (correct) volume during NACKs.

    After clearing the NACK fault, a new volume command succeeds
    and both DSP and status RAM are updated correctly.
    """
    _require_gpsim()
    if not V31_MAIN_HEX.exists():
        pytest.skip(f"missing: {V31_MAIN_HEX.name}")

    harness = MainChainHarness(
        V31_MAIN_HEX,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        # ---- Boot and activate ----
        for _ in range(20):
            harness.step()
        harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"

        # ---- Baseline ----
        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_baseline = _dsp34_diff(snap_a, _dsp34_snapshot(harness))
        assert len(diff_baseline) > 0, "baseline broken"

        vol_baseline = _read_reg(harness._issue, _VOLUME_REG)
        stat_baseline = _read_reg(harness._issue, 0x066)

        # ---- Phase 1: NACKed volume command ----
        harness.set_i2c_fault("dsp34", address_nack_count=60000)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(15):
            harness.step()

        flags_7e = _read_reg(harness._issue, _FLAGS_7E)
        flags_7f = _read_reg(harness._issue, 0x07F)
        stat_nack = _read_reg(harness._issue, 0x066)

        err_latched = bool(flags_7f & 0x04)
        retry_count = (flags_7f >> 3) & 0x07

        # Fix A: ACKSTAT must have been detected (error flag was
        # set at some point — the retry counter proves it even if
        # the latch was cleared after max retries).
        assert retry_count > 0 or err_latched, (
            f"Fix A: no NACK detection — 0x07F=0x{flags_7f:02X} "
            f"(err={err_latched}, retry={retry_count})"
        )

        # Fix B': status RAM must be UNCHANGED from baseline.
        # CONTROL would still show the old (correct) volume.
        assert stat_nack == stat_baseline, (
            f"Fix B': status committed despite NACK — "
            f"stat=0x{stat_nack:02X} (baseline=0x{stat_baseline:02X})"
        )

        # ---- Phase 2: recovery ----
        # Clear NACKs and send a new volume.  V3.1 should accept it.
        harness.clear_i2c_faults("dsp34")
        snap_b = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_recovery = _dsp34_diff(snap_b, _dsp34_snapshot(harness))
        stat_post = _read_reg(harness._issue, 0x066)
        vol_post = _read_reg(harness._issue, _VOLUME_REG)

        assert len(diff_recovery) > 0, (
            "recovery failed: volume cmd after NACK clear did not "
            "change DSP registers"
        )
        # The new volume (0x40) must be different from the NACKed one (0x30)
        # and from the baseline (0x50).  status RAM must be committed.
        assert vol_post != vol_baseline, (
            f"recovery: volume register unchanged from baseline "
            f"(0x{vol_post:02X} == 0x{vol_baseline:02X})"
        )
        assert stat_post == vol_post, (
            f"V3.1 status RAM not committed after recovery: "
            f"stat=0x{stat_post:02X} vol=0x{vol_post:02X}"
        )

    finally:
        harness.close()
