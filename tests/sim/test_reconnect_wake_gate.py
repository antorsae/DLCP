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

Two rust-facade tests verify the fix:

* ``test_v162b_reconnect_exit_contains_wake_call`` — binary scan over
  the patched HEX confirms the ``call 0x0C98`` lives in the patch
  stub region after ``bsf 0x01F, 1``.  Backend-agnostic.
* ``test_main_standby_gate_blocks_dsp_writes`` — MAIN-only standalone
  proves the active gate (0x5E.bit3) opens, closes, and reopens with
  the standby/wake frame sequence, and DSP writes follow gate state.

Three earlier wire-chain gpsim tests
(``test_v162b_wire_chain_standby_reconnect_dsp_gate``,
``test_v26_v162b_wire_chain_standby_reconnect_dsp_gate``,
``test_v31_v163b_wire_chain_standby_reconnect_dsp_gate``) were deleted
in PF.4 phase 2 batch 6: they used ``WireMultiMainChainHarness`` for
bridge-FIFO suppression + SFR restore via gpsim CLI, both
gpsim-PTY-bridge-specific scaffolding with no rust analogue.

Coverage notes:

* The two remaining tests below preserve the binary-level guard
  (the wake-frame ``call 0x0C98`` lives in the right spot) and the
  MAIN-only DSP-gate behaviour (volume cmd is gated by the active
  flag).  Together they prove the firmware fix exists and the gate
  semantics work.
* The legacy V2.5/V2.6/V3.1 wire-chain integration scenarios — full
  CONTROL→MAIN standby cycle with cfg71 I²C glitch + SFR restore +
  one-step bridge suppression to isolate the reconnect_wait_done
  exit path — are NOT replaced.  ``test_v171_v32_standby_reconnect.py``
  exercises STBY/WAKE/reconnect on the V1.71+V3.2 chain but does
  not cover post-reconnect DSP writes or the legacy V2.5/V2.6
  firmware combos.  Reviving the legacy-combo integration coverage
  needs either a rust 3-core ring factory for legacy patched-control
  × patched-main pairs or a CONTROL-side stimulus pump to drive
  the standby/reconnect timing without bridge-FIFO scaffolding.
  Tracked as task #129 (legacy CONTROL+MAIN standby pin matrix
  recovery).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V162B

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


_STATUS_5E = 0x05E


# ---------------------------------------------------------------------------
# Semantic guard: reconnect_wait_done must contain call function_034
# ---------------------------------------------------------------------------

@pytest.mark.dual_supported
def test_v162b_reconnect_exit_contains_wake_call() -> None:
    """V1.62b reconnect_wait_done must call function_034 (0x0C98) after
    setting bit1 (DISPLAY).

    Pure binary scan over the patched HEX -- backend-agnostic.
    """
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

def _run_standby_gate_test(patched_main_hex: Path) -> None:
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(patched_main_hex))

    def dsp_snapshot() -> dict[int, int]:
        return {r: chain.read_dsp_reg(r) for r in range(256)}

    def dsp_diff(before: dict[int, int]) -> list:
        after = dsp_snapshot()
        return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]

    chain.step_tcy(4_000_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    assert chain.read_reg(_STATUS_5E) & 0x08, "MAIN not active"

    snap_a = dsp_snapshot()
    chain.inject_main_frames_fifo([[0xB0, 0x06, 0x50]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    assert len(dsp_diff(snap_a)) > 0, (
        "volume command did not change any DSP register with gate open "
        "-- test baseline broken"
    )

    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x00]], fifo_limit=47)
    chain.step_tcy(8_000_000)
    assert not (chain.read_reg(_STATUS_5E) & 0x08), (
        "active flag not cleared after standby"
    )

    snap_b = dsp_snapshot()
    chain.inject_main_frames_fifo([[0xB0, 0x06, 0x30]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    diff_closed = dsp_diff(snap_b)
    assert len(diff_closed) == 0, (
        f"volume command changed {len(diff_closed)} DSP register(s) "
        f"despite closed gate -- gate is not blocking"
    )

    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    assert chain.read_reg(_STATUS_5E) & 0x08, (
        "active flag not restored by wake frame"
    )

    snap_c = dsp_snapshot()
    chain.inject_main_frames_fifo([[0xB0, 0x06, 0x40]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    assert len(dsp_diff(snap_c)) > 0, (
        "volume command did not change any DSP register after wake "
        "-- gate did not reopen"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main_standby_gate_blocks_dsp_writes(patched_main_hex: Path) -> None:
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
    if not patched_main_hex.exists():
        pytest.skip(f"missing: {patched_main_hex.name}")
    _run_standby_gate_test(patched_main_hex)
