"""Verify V1.62b reconnect exit sends function_034 wake frame.

Field symptom (2026-03-26): V2.5 + V1.62b on real hardware, after a
standby attempt that fails to fully power down (e.g. due to a transient
I2C glitch during function_051), CONTROL enters Zzz display, polls MAIN,
exits WAITING via reconnect_wait_done, and returns to DISPLAY --- but
never sends the wake frame [route, 0x03, 0x01].

All MAINs on the current loop have their active gate (0x5E.bit3) cleared
by the standby broadcast.  Without the wake frame, function_005 at
0x18F2 silently drops every command through label_144 (return 0x0).
Volume, preset, and mute commands are dead on all connected units.

Stock V1.6b sends function_034 at 0x1294 between the standby-exit
logic and the reconnect wait loop.  V1.62b's reconnect_wait_done
bypassed this call by jumping directly to label_201.

Fix: add ``call 0x0C98`` (function_034) to reconnect_wait_done after
``bsf 0x01F, 1``, so the wake frame is sent before CONTROL re-enters
the display loop.

Note: a full wire-chain end-to-end (CONTROL standby → reconnect → DSP
check) is not included because (a) MAIN enters real standby in sim,
changing baud rate and disabling Timer0, which prevents the reconnect
poll path from completing, and (b) when the gate is cleared synthetically,
the display loop's periodic function_028 → function_034 compensates for
the missing wake within a few sync cycles, masking the race window that
matters on real hardware.  The semantic guard catches the regression
directly; the MAIN DSP test proves the behavioral consequence.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V162B, PATCHED_MAIN_HEX
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available

_STATUS_5E = 0x05E


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _dsp34_snapshot(harness: MainChainHarness) -> dict[int, int]:
    return {r: harness.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp34_diff(
    before: dict[int, int], after: dict[int, int]
) -> list[tuple[int, int, int]]:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


# ---------------------------------------------------------------------------
# Semantic guard: reconnect_wait_done must contain call function_034
# ---------------------------------------------------------------------------

def test_v162b_reconnect_exit_contains_wake_call() -> None:
    """V1.62b reconnect_wait_done must call function_034 (0x0C98) after
    setting bit1 (DISPLAY)."""
    if not PATCHED_CONTROL_HEX_V162B.exists():
        pytest.skip(f"missing: {PATCHED_CONTROL_HEX_V162B.name}")

    mem = parse_intel_hex(PATCHED_CONTROL_HEX_V162B)
    bsf_lo, bsf_hi = 0x1F, 0x82
    call_bytes = (0x4C, 0xEC, 0x06, 0xF0)

    found = False
    for addr in range(0x7000, 0x8000 - 5, 2):
        if mem.get(addr) == bsf_lo and mem.get(addr + 1) == bsf_hi:
            if all(mem.get(addr + 2 + i, 0xFF) == call_bytes[i] for i in range(4)):
                found = True
                break

    assert found, (
        "reconnect_wait_done missing 'call 0x0C98' (function_034 wake) "
        "after 'bsf 0x01F, 1' in patch stubs 0x7000+"
    )


# ---------------------------------------------------------------------------
# Runtime: DSP I2C behavioral proof of the active gate
# ---------------------------------------------------------------------------

@pytest.mark.gpsim
@pytest.mark.slow
def test_main_standby_gate_blocks_dsp_writes(
    patched_main_hex: Path,
) -> None:
    """Volume commands must reach the DSP only when the active gate is open.

    Phases:
      1. Activate MAIN, send volume cmd -> DSP registers CHANGE (baseline).
      2. Enter standby (close gate), send volume cmd -> DSP registers
         DO NOT CHANGE.  This is the bug condition: without the wake
         frame from CONTROL, every command is silently dropped.
      3. Send wake frame (the fix), send volume cmd -> DSP registers
         CHANGE again.

    Prior to the fix, phase 3 never happens on real hardware because
    reconnect_wait_done does not call function_034.
    """
    _require_gpsim()
    if not patched_main_hex.exists():
        pytest.skip(f"missing: {patched_main_hex.name}")

    harness = MainChainHarness(
        patched_main_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )
    try:
        # Boot and activate MAIN via wake frame.
        for _ in range(20):
            harness.step()
        harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"

        # ---- Phase 1: gate OPEN, volume command reaches DSP ----
        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x06, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_open = _dsp34_diff(snap_a, _dsp34_snapshot(harness))
        assert len(diff_open) > 0, (
            "volume command did not change any DSP register with gate open "
            "-- test baseline broken"
        )

        # ---- Phase 2: enter standby (close gate) ----
        harness.inject_frames_fifo([[0xB0, 0x03, 0x00]], fifo_limit=47)
        for _ in range(40):
            harness.step()
        assert not (_read_reg(harness._issue, _STATUS_5E) & 0x08), (
            "active flag not cleared after standby"
        )

        # Volume command with gate closed -> DSP must NOT change.
        # This is the field bug: CONTROL reconnects, sends commands,
        # but every one is silently dropped at function_005 label_144.
        snap_b = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x06, 0x30]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_closed = _dsp34_diff(snap_b, _dsp34_snapshot(harness))
        assert len(diff_closed) == 0, (
            f"volume command changed {len(diff_closed)} DSP register(s) "
            f"despite closed gate -- gate is not blocking"
        )

        # ---- Phase 3: wake frame reopens the gate (the fix) ----
        harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert _read_reg(harness._issue, _STATUS_5E) & 0x08, (
            "active flag not restored by wake frame"
        )

        # Volume command after wake -> DSP must change again.
        snap_c = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x06, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_woken = _dsp34_diff(snap_c, _dsp34_snapshot(harness))
        assert len(diff_woken) > 0, (
            "volume command did not change any DSP register after wake "
            "-- gate did not reopen"
        )

    finally:
        harness.close()
