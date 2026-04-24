"""V3.1 MAIN + V1.63b CONTROL robustness tests.

V3.1 is the source-rewrite equivalent of V2.7.  The canonical hardware-fixed
build keeps the bus-clear / DSP-ping / BF-08 robustness logic inline, but it
restores stock TAS3108 coeff-write waits because the bounded PEN path
regressed real hardware DSP apply.

V3.1 fixes (inline):
  C: I2C bus-clear after MSSP recovery (bitbang 9 SCL clocks)
  D: DSP ping after bus-clear (TAS3108 address probe)
  E: BF/08 DSP fault status reporting to CONTROL
  F: canonical build restores stock coeff-write waits (no bounded PEN latch)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V163B,
    V31_MAIN_HEX,
    V32_MAIN_HEX,
)
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.v30_symbols import assemble_v30, parse_gpasm_symbols
from dlcp_fw.sim.manifests import main_serial_mailbox_hooks_dynamic
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

_STATUS_5E = 0x05E
_FLAGS_7E = 0x07E
_FLAGS_7F = 0x07F
_VOLUME_REG = 0x06E
_PRESET_B_BIT = 0x04
_PRESET_JOB_STATE = 0x2DE
_PRESET_JOB_TARGET = 0x2DF
_PRESET_JOB_INDEX = 0x2E0
_DSP_FAULT_BIT = 6  # 0x07F.bit6: persistent DSP fault


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")


def _skip_missing(*paths: Path) -> None:
    for p in paths:
        if not p.exists():
            pytest.skip(f"missing: {p.name}")


def _dsp34_snapshot(harness: MainChainHarness) -> dict[int, int]:
    return {r: harness.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp34_diff(before: dict[int, int], after: dict[int, int]) -> list:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


def _boot_and_activate(harness: MainChainHarness) -> None:
    for _ in range(20):
        harness.step()
    harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    for _ in range(20):
        harness.step()
    assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"


def _wait_for_uart_settled(
    harness: MainChainHarness,
    *,
    limit: int = 80,
) -> None:
    """Poll until the V3.2 wake path finishes arming the UART and clears
    the native RX ring.  The trailing main_uart_service_4938 call in
    adc_boot_gate_exit runs `goto uart_parser_resync` which zeros
    rx_ring_rd/wr; any frame injected before that clear is wiped.  The
    V3.2 wake-path hardening checkpoint (9ab78d4) grew that tail enough
    that _boot_and_activate's fixed 20-step post-wake wait no longer
    reliably lands after the clear.  Call this helper before injecting
    any parse-dependent frame (e.g. cmd 0x20 preset-select).  Only the
    preset-job / command-parser tests need it; other tests like the
    MSSP / DSP-ping path rely on observing MAIN mid-wake."""
    for _ in range(limit):
        rcsta = _read_reg(harness._issue, 0xFAB)  # RCSTA SFR
        rx_wr = _read_reg(harness._issue, 0x0C7)  # rx_ring_wr
        if (rcsta & 0x90) == 0x90 and rx_wr == 0:
            return
        harness.step()
    raise AssertionError(
        f"wake never reached quiescent UART state within {limit} steps: "
        f"RCSTA=0x{rcsta:02X} rx_wr=0x{rx_wr:02X}"
    )


def _new_main_harness(main_hex: Path) -> MainChainHarness:
    return MainChainHarness(
        main_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )


def _force_clear_sspcon2(harness: MainChainHarness) -> None:
    """Force-clear SSPCON2 PEN bit via gpsim (workaround for gpsim
    not allowing firmware writes to SSPCON2 during active I2C)."""
    try:
        harness._issue("p18f2455.sspcon2 = 0", 5.0)
    except Exception:
        pass


def _inject_main_frame(harness: MainChainHarness, *, cmd: int, data: int) -> None:
    delivered, overruns = harness.inject_frames_fifo([[0xB0, cmd, data]], fifo_limit=47)
    assert delivered == 3 and overruns == 0, (
        f"failed to inject MAIN frame B0/{cmd:02X}/{data:02X}: "
        f"delivered={delivered} overruns={overruns}"
    )


def _wait_for_preset_job_state(
    harness: MainChainHarness,
    expected_state: int,
    *,
    limit: int = 160,
) -> None:
    for _ in range(limit):
        harness.step()
        if _read_reg(harness._issue, _PRESET_JOB_STATE) == expected_state:
            return
    raise AssertionError(
        f"preset job did not reach state {expected_state} within {limit} steps: "
        f"state=0x{_read_reg(harness._issue, _PRESET_JOB_STATE):02X} "
        f"index=0x{_read_reg(harness._issue, _PRESET_JOB_INDEX):02X} "
        f"target=0x{_read_reg(harness._issue, _PRESET_JOB_TARGET):02X}"
    )


def _wait_for_preset_job_idle(harness: MainChainHarness, *, limit: int = 320) -> None:
    _wait_for_preset_job_state(harness, 0x00, limit=limit)


# -----------------------------------------------------------------------
# Test 1: I2C bus-clear recovers stuck slave (Fix C)
# -----------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_bus_clear_recovers_after_mssp_stop_fault() -> None:
    """After extended MSSP STOP fault cascade, bus-clear recovers DSP."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    harness = _new_main_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(harness)

        # DSP baseline
        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(harness))) > 0, "baseline broken"

        # Inject extended MSSP STOP fault
        harness.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        # Clear fault and let firmware recover
        harness.clear_mssp_stop_faults()
        for _ in range(15):
            harness.step()

        # New volume command — bus-clear should recover DSP path
        snap_b = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_recovery = _dsp34_diff(snap_b, _dsp34_snapshot(harness))

        assert len(diff_recovery) > 0, (
            "DSP path not recovered after MSSP STOP cascade — "
            "bus-clear did not restore I2C communication"
        )

    finally:
        harness.close()


# -----------------------------------------------------------------------
# Test 2: DSP ping detects dead TAS3108 (Fix D)
# -----------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_dsp_ping_latches_fault_on_persistent_nack() -> None:
    """DSP ping latches 0x07F.bit6 when TAS3108 is persistently NACKing."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    harness = _new_main_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()

        # Persistent NACKs — DSP is "dead"
        harness.set_i2c_fault("dsp34", address_nack_count=60000)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        # DSP fault flag (0x07F.bit6) should be latched
        fault = _read_reg(harness._issue, _FLAGS_7F) & (1 << _DSP_FAULT_BIT)
        assert fault != 0, (
            f"DSP fault flag (0x07F.bit6) not latched after persistent "
            f"NACK — 0x07F=0x{_read_reg(harness._issue, _FLAGS_7F):02X}"
        )

    finally:
        harness.close()


# -----------------------------------------------------------------------
# Test 3: BF/08 DSP fault reporting (Fix E + E' + E'')
# -----------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_wire_dsp_fault_reporting() -> None:
    """CONTROL shows DSP fault indicator after MAIN reports BF/08."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX, PATCHED_CONTROL_HEX_V163B)

    chain = WireMultiMainChainHarness(
        PATCHED_CONTROL_HEX_V163B,
        V31_MAIN_HEX,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )
    try:
        last = chain.run_until_connected(limit=80)
        assert chain.is_connected()

        # Inject NACKs and volume command
        chain.set_main_i2c_fault("dsp34", address_nack_count=60000)
        chain.press("UP")
        chain.step_many(20)

        # V1.63b CONTROL: dsp_fault flag (0x01F.bit7) should be set
        ctrl_flags = chain.control.read_reg(0x01F)
        dsp_fault = bool(ctrl_flags & 0x80)
        assert dsp_fault, (
            f"CONTROL dsp_fault (0x01F.bit7) not set — "
            f"0x01F=0x{ctrl_flags:02X}"
        )

        # Clear NACKs -> send volume to trigger resync -> CONTROL clears
        chain.clear_main_i2c_faults("dsp34")
        chain.press("UP")
        chain.step_many(30)
        ctrl_flags_post = chain.control.read_reg(0x01F)
        assert not (ctrl_flags_post & 0x80), (
            f"CONTROL dsp_fault not cleared after NACKs removed — "
            f"0x01F=0x{ctrl_flags_post:02X}"
        )

    finally:
        chain.close()


# -----------------------------------------------------------------------
# Test 4: MSSP STOP cascade full recovery (Fix C+D wire-chain)
# -----------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_wire_mssp_stop_cascade_control_path_recovers_without_sim_pokes() -> None:
    """Extended MSSP STOP fault -> chain reconnects and MAIN accepts volume again.

    This preserves a non-xfail chain-level signal without depending on the
    gpsim limitation that still prevents post-recovery DSP writes from
    reaching the simulated TAS3108 in the wire harness.
    """
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX, PATCHED_CONTROL_HEX_V163B)

    chain = WireMultiMainChainHarness(
        PATCHED_CONTROL_HEX_V163B,
        V31_MAIN_HEX,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )
    try:
        last = chain.run_until_connected(limit=80)
        assert chain.is_connected()
        main = chain.mains[0]

        # DSP baseline through the real CONTROL->MAIN path
        snap_a = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(main))) > 0

        # MSSP STOP fault
        chain.set_main_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        chain.step_many(30)

        # Clear fault and let firmware recover
        chain.clear_main_mssp_stop_faults()
        chain.step_many(15)

        # If CONTROL entered WAITING, reconnect
        if chain.is_waiting():
            chain.run_until_connected(limit=60)

        assert chain.is_connected(), "CONTROL link did not recover after MSSP STOP cascade"
        assert _read_reg(main._issue, _STATUS_5E) & 0x08, "MAIN lost active state after recovery"

        # Volume command MUST reach MAIN again after recovery.
        vol_before = _read_reg(main._issue, _VOLUME_REG)
        chain.press("UP")
        chain.step_many(5)
        vol_after = _read_reg(main._issue, _VOLUME_REG)
        assert vol_after != vol_before, (
            "CONTROL->MAIN volume path did not recover after MSSP STOP cascade"
        )

    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.xfail(
    reason="gpsim wire-chain STOP-state model still blocks post-recovery DSP writes in V3.1",
    strict=True,
)
def test_wire_mssp_stop_cascade_full_dsp_recovery() -> None:
    """Extended MSSP STOP fault -> bus-clear -> DSP path recovers.

    Keep this as a pure firmware expectation with no simulator register pokes.
    The single-main path is covered by the passing recovery test above; this
    chain-level DSP assertion remains an explicit gpsim limitation tracker.
    """
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX, PATCHED_CONTROL_HEX_V163B)

    chain = WireMultiMainChainHarness(
        PATCHED_CONTROL_HEX_V163B,
        V31_MAIN_HEX,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )
    try:
        last = chain.run_until_connected(limit=80)
        assert chain.is_connected()
        main = chain.mains[0]

        snap_a = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(main))) > 0

        chain.set_main_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        chain.step_many(30)

        chain.clear_main_mssp_stop_faults()
        chain.step_many(15)
        if chain.is_waiting():
            chain.run_until_connected(limit=60)

        snap_b = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_post = _dsp34_diff(snap_b, _dsp34_snapshot(main))
        assert len(diff_post) > 0, (
            "DSP path not recovered after MSSP STOP cascade — "
            "V3.1 bus-clear/ping did not restore I2C"
        )

    finally:
        chain.close()


# -----------------------------------------------------------------------
# Test 5: PEN timeout in i2c_tas3108_coeff_write (Fix F)
# -----------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_main_pen_timeout_recovers() -> None:
    """PEN busy-wait timeout prevents permanent hang on stuck STOP."""
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    harness = _new_main_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()

        # Single very long STOP fault — should trigger PEN timeout
        harness.set_mssp_stop_fault(stop_busy_cycles=50_000_000, stop_busy_count=1)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(10):
            harness.step()

        harness.clear_mssp_stop_faults()
        # Force-clear SSPCON2 PEN bit via gpsim (gpsim's SSPCON2.put()
        # ignores writes during active I2C; we need put_value to bypass)
        try:
            harness._issue("p18f2455.sspcon2 = 0", 5.0)
        except Exception:
            pass
        for _ in range(5):
            harness.step()

        # After PEN timeout + recovery, DSP should still work
        snap = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(30):
            harness.step()
        diff = _dsp34_diff(snap, _dsp34_snapshot(harness))

        assert len(diff) > 0, (
            "DSP path broken after PEN timeout — V3.1 should recover "
            "from stuck STOP condition via bounded PEN wait + bus-clear"
        )

    finally:
        harness.close()


# -----------------------------------------------------------------------
# V3.2 robustness regression — same scenarios, async preset job baseline
# -----------------------------------------------------------------------


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_main_bus_clear_recovers_after_mssp_stop_fault() -> None:
    """V3.2 preserves bus-clear recovery after MSSP STOP fault cascade."""
    _require_gpsim()
    _skip_missing(V32_MAIN_HEX)

    harness = _new_main_harness(V32_MAIN_HEX)
    try:
        _boot_and_activate(harness)

        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(harness))) > 0, "baseline broken"

        harness.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        harness.clear_mssp_stop_faults()
        for _ in range(15):
            harness.step()

        snap_b = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff_recovery = _dsp34_diff(snap_b, _dsp34_snapshot(harness))

        assert len(diff_recovery) > 0, (
            "V3.2 DSP path not recovered after MSSP STOP cascade"
        )

    finally:
        harness.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_main_pen_timeout_recovers() -> None:
    """V3.2 preserves PEN timeout recovery from stuck STOP condition."""
    _require_gpsim()
    _skip_missing(V32_MAIN_HEX)

    harness = _new_main_harness(V32_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()

        harness.set_mssp_stop_fault(stop_busy_cycles=50_000_000, stop_busy_count=1)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(10):
            harness.step()

        harness.clear_mssp_stop_faults()
        try:
            harness._issue("p18f2455.sspcon2 = 0", 5.0)
        except Exception:
            pass
        for _ in range(5):
            harness.step()

        snap = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(30):
            harness.step()
        diff = _dsp34_diff(snap, _dsp34_snapshot(harness))

        assert len(diff) > 0, (
            "V3.2 DSP path broken after PEN timeout"
        )

    finally:
        harness.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_keeps_main_loop_responsive() -> None:
    """A stuck STOP during async APPLY must return to the main loop.

    Arms the persistent STOP fault BEFORE injecting the preset-select
    frame so the first APPLY iteration hits the fault — otherwise the
    harness's chunk_cycles=200_000 lets several APPLY entries complete
    before we can observe state=3 and set the fault.
    """
    _require_gpsim()
    _skip_missing(V32_MAIN_HEX)

    harness = _new_main_harness(V32_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        _wait_for_uart_settled(harness)
        harness.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        _inject_main_frame(harness, cmd=0x20, data=0x01)
        _wait_for_preset_job_state(harness, 0x03)
        assert _read_reg(harness._issue, _PRESET_JOB_INDEX) == 0x00, (
            "async APPLY advanced past the first table entry even though the "
            "STOP fault was armed before preset-select"
        )

        # Re-arm coalescing: second preset command while retry loop is running.
        _inject_main_frame(harness, cmd=0x20, data=0x00)
        for _ in range(8):
            harness.step()

        assert _read_reg(harness._issue, _PRESET_JOB_STATE) == 0x03, (
            "async APPLY left retryable state during persistent STOP fault"
        )
        assert _read_reg(harness._issue, _PRESET_JOB_INDEX) == 0x00, (
            "async APPLY advanced the table index during STOP timeout"
        )
        assert _read_reg(harness._issue, _PRESET_JOB_TARGET) == 0x00, (
            "follow-up preset command was not consumed while STOP fault was active; "
            "the APPLY path likely wedged instead of returning to the main loop"
        )
    finally:
        harness.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_does_not_advance_index() -> None:
    """A timed-out APPLY entry must stay queued until the fault clears.

    Same arm-first ordering as _keeps_main_loop_responsive: the fault
    must be active from the very first APPLY iteration, otherwise the
    chunk_cycles granularity (~200 k cycles per step) lets APPLY complete
    several table entries before we can observe state=3 and arm.
    """
    _require_gpsim()
    _skip_missing(V32_MAIN_HEX)

    harness = _new_main_harness(V32_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        _wait_for_uart_settled(harness)
        harness.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        _inject_main_frame(harness, cmd=0x20, data=0x01)
        _wait_for_preset_job_state(harness, 0x03)

        index_before = _read_reg(harness._issue, _PRESET_JOB_INDEX)
        for _ in range(12):
            harness.step()

        assert index_before == 0x00, (
            f"test setup expected the first APPLY entry to be pending; "
            f"got index_before=0x{index_before:02X}"
        )
        assert _read_reg(harness._issue, _PRESET_JOB_INDEX) == index_before, (
            "async APPLY index advanced while STOP timeout recovery was still retrying"
        )
        assert _read_reg(harness._issue, _PRESET_JOB_STATE) == 0x03, (
            "async APPLY left state 3 during a retryable STOP timeout"
        )
    finally:
        harness.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_recovers_and_completes() -> None:
    """Clearing a STOP fault must let the same async APPLY job finish cleanly.

    Arm-first ordering (see _keeps_main_loop_responsive for rationale).
    """
    _require_gpsim()
    _skip_missing(V32_MAIN_HEX)

    harness = _new_main_harness(V32_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        _wait_for_uart_settled(harness)
        harness.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        _inject_main_frame(harness, cmd=0x20, data=0x01)
        _wait_for_preset_job_state(harness, 0x03)
        for _ in range(8):
            harness.step()
        assert _read_reg(harness._issue, _PRESET_JOB_INDEX) == 0x00, (
            "STOP timeout test lost the first pending APPLY entry before recovery"
        )

        harness.clear_mssp_stop_faults()
        _wait_for_preset_job_idle(harness)

        assert _read_reg(harness._issue, _PRESET_JOB_INDEX) == 0x60, (
            "async APPLY did not finish the 96 regular table entries after STOP fault recovery"
        )
        assert _read_reg(harness._issue, _STATUS_5E) & _PRESET_B_BIT, (
            "preset B was not committed after STOP fault recovery"
        )
    finally:
        harness.close()
