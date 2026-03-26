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

Tests:
  - Semantic guard: hex scan for call 0x0C98 after bsf 0x01F,1
  - MAIN DSP behavioral: standalone gate open/close/reopen via I2C
  - Wire-chain end-to-end: CONTROL+MAIN standby cycle with DSP gate check
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.patch.verify_presets_ab import parse_intel_hex
from dlcp_fw.paths import PATCHED_CONTROL_HEX_V162B, PATCHED_MAIN_HEX
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

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


# ---------------------------------------------------------------------------
# Wire-chain end-to-end: standby → reconnect → gate + DSP
# ---------------------------------------------------------------------------

# PIC18F2455 SFR addresses restored after function_051 to simulate partial
# standby failure (I2C glitch) with V2.5 timeout recovery.
_SFR_SPBRG = 0xFAF
_SFR_SPBRGH = 0xFB0
_SFR_OSCCON = 0xFD3
_SFR_T0CON = 0xFD5
_SFR_INTCON = 0xFF2
_SFR_TXSTA = 0xFAC
_SFR_RCSTA = 0xFAB
_SLEEP_FLAG = 0x095

_MAIN_SFR_RESTORE_SET = (
    _SFR_SPBRG, _SFR_SPBRGH, _SFR_OSCCON, _SFR_T0CON,
    _SFR_INTCON, _SFR_TXSTA, _SFR_RCSTA, _SLEEP_FLAG,
)


def _wire_dsp34_snapshot(main: MainChainHarness) -> dict[int, int]:
    return {r: main.read_i2c_regfile("dsp34", r) for r in range(256)}


@pytest.mark.gpsim
@pytest.mark.slow
def test_v162b_wire_chain_standby_reconnect_dsp_gate() -> None:
    """Full CONTROL + MAIN wire-chain standby cycle with DSP gate check.

    Reproduces the V1.62b reconnect wake bug end-to-end:

    1. Boot to DISPLAY, confirm DSP baseline (volume UP changes dsp34).
    2. Inject I2C fault on dsp34, press STBY -> Zzz.
    3. Restore MAIN SFRs (simulate partial failure + V2.5 recovery).
    4. Drop CONTROL->MAIN bridge for one step to suppress the stock wake
       frame at 0x1294 (fired between standby-exit and reconnect_wait_stub).
    5. Press STBY to wake -> reconnect -> DISPLAY.
    6. Assert MAIN's active gate (0x5E.bit3) and DSP behavior.

    **FAILS** when V1.62b is built WITHOUT ``call 0x0C98`` in
    reconnect_wait_done.  **PASSES** when V1.62b is built WITH the fix.

    Approach rationale:
    - SFR restore after function_051 models the real field scenario where
      an I2C glitch causes DSP shutdown to fail but V2.5 timeout recovery
      restores MAIN's UART/timer/oscillator state.  The active gate
      (0x5E.bit3) remains cleared because label_155 clears it BEFORE
      function_051 runs.
    - Bridge suppression for one step prevents the stock wake at 0x1294
      from reaching MAIN, isolating the reconnect_wait_done exit path.
      Stock V1.6b at 0x12BA clears bit1 before label_212, so the stock
      wake fires with data=0x01 only because bit1 was set at 0x1292.
      Dropping that one step's traffic makes reconnect_wait_done's
      function_034 call the sole source of the wake frame.
    """
    _require_gpsim()
    ctrl_hex = PATCHED_CONTROL_HEX_V162B
    main_hex = PATCHED_MAIN_HEX
    if not ctrl_hex.exists():
        pytest.skip(f"missing: {ctrl_hex.name}")
    if not main_hex.exists():
        pytest.skip(f"missing: {main_hex.name}")

    chain = WireMultiMainChainHarness(
        ctrl_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )
    try:
        # ---- Phase 1: boot and establish DSP baseline ----
        last = chain.run_until_connected(limit=80)
        assert last is not None, "chain produced no steps"
        assert chain.is_connected(), f"pair never connected; lcd={last.lcd!r}"

        main = chain.mains[0]
        main_issue = main._issue
        assert main.uses_external_i2c_regfile_bus, "I2C regfile bus not attached"
        pre_5e = _read_reg(main_issue, _STATUS_5E)
        assert pre_5e & 0x08, f"MAIN not active after boot; 0x5E=0x{pre_5e:02X}"

        # Volume UP -> DSP registers change (proves the command path works).
        snap_a = _wire_dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_baseline = _dsp34_diff(snap_a, _wire_dsp34_snapshot(main))
        assert len(diff_baseline) > 0, (
            "volume UP did not change any dsp34 register -- DSP baseline broken"
        )

        # ---- Phase 2: standby with I2C glitch ----
        # Save MAIN SFRs that function_051 will clobber.
        saved: dict[int, int] = {}
        for addr in _MAIN_SFR_RESTORE_SET:
            saved[addr] = _read_reg(main_issue, addr)

        # Inject address NACKs on dsp34 so function_051's three
        # function_093 I2C shutdown writes fail (simulates I2C glitch).
        chain.set_main_i2c_fault("dsp34", address_nack_count=100)

        chain.press("STBY")
        chain.step_many(20)

        lcd = chain.lcd_lines()
        assert "ZZZ" in lcd[0].upper(), f"not in Zzz after STBY; lcd={lcd!r}"
        assert not (_read_reg(main_issue, _STATUS_5E) & 0x08), (
            "MAIN active flag not cleared after standby broadcast"
        )

        # ---- Phase 3: simulate partial failure recovery ----
        # Restore MAIN's hardware SFRs to pre-standby values.  This
        # models: I2C glitch -> DSP shutdown failed -> V2.5 timeout
        # recovery restored UART baud rate, oscillator, Timer0.
        # The active flag (0x5E.bit3) stays cleared -- that's the bug.
        for addr, val in saved.items():
            main_issue(f"reg(0x{addr:03X})=0x{val:02X}", 5.0)

        chain.clear_main_i2c_faults("dsp34")

        assert not (_read_reg(main_issue, _STATUS_5E) & 0x08), (
            "active flag unexpectedly set after SFR restore"
        )

        # ---- Phase 4: wake with bridge suppression ----
        # Drop CONTROL->MAIN for one step so the stock wake frame at
        # 0x1294 (and the first reconnect polls) are discarded.  Only
        # reconnect_wait_done's function_034 call can send the wake.
        chain.set_link_fault("ctl_to_m0", drop=True)
        chain.press("STBY")
        chain.step()  # CONTROL exits Zzz; wake + first polls -> DROPPED

        chain.clear_link_faults()

        # ---- Phase 5: reconnect ----
        last = chain.run_until_connected(limit=80)
        assert last is not None, "chain produced no steps after wake"
        assert chain.is_connected(), f"pair never reconnected; lcd={last.lcd!r}"
        assert not chain.is_waiting(), f"still WAITING; lcd={last.lcd!r}"

        # ---- Phase 6: assert gate and DSP ----
        # With the fix, reconnect_wait_done calls function_034 (wake),
        # reopening MAIN's active gate in the same step that reconnect
        # succeeds.  Without the fix, the gate stays closed until the
        # full-sync fires ~78 display-loop iterations later.
        gate = _read_reg(main_issue, _STATUS_5E) & 0x08
        assert gate != 0, (
            "0x5E.bit3 is 0 after reconnect -- reconnect_wait_done did "
            "not send wake frame (call 0x0C98 missing)"
        )

        # Volume UP -> DSP registers must change (gate open, DSP live).
        snap_b = _wire_dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_post = _dsp34_diff(snap_b, _wire_dsp34_snapshot(main))
        assert len(diff_post) > 0, (
            "volume UP did not change dsp34 registers after reconnect -- "
            "gate is nominally open but DSP commands are not reaching the bus"
        )

    finally:
        chain.close()
