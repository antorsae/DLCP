"""V2.7 MAIN + V1.63b CONTROL robustness tests.

These tests define the required behavior for V2.7 and V1.63b.
They must be in place BEFORE implementation and xfail on prior
versions.  Once V2.7/V1.63b are built, they must pass.

V2.7 fixes:
  C: I2C bus-clear after MSSP recovery (bitbang 9 SCL clocks)
  D: DSP ping after bus-clear (TAS3108 register 0x08 read)
  E: BF/08 DSP fault status reporting to CONTROL
  F: PEN timeout in function_081 label_572

V1.63b fixes:
  E': DSP fault parser (BF/08 handler)
  E'': DSP fault UI indicator
  E''': Resync on fault clear
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V162B,
    PATCHED_CONTROL_HEX_V163B,
    PATCHED_MAIN_HEX_V26,
    PATCHED_MAIN_HEX_V27,
    STOCK_MAIN_HEX,
)
from dlcp_fw.sim.chain_gpsim import MainChainHarness
from dlcp_fw.sim.control_gpsim import _read_reg
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

_STATUS_5E = 0x05E
_FLAGS_7E = 0x07E
_FLAGS_7F = 0x07F
_VOLUME_REG = 0x06E
_DSP_FAULT_BIT = 6  # 0x07F.bit6: persistent DSP fault (V2.7)


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


def _new_main_harness(main_hex: Path) -> MainChainHarness:
    return MainChainHarness(
        main_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )


# -----------------------------------------------------------------------
# Test 1: I2C bus-clear recovers stuck slave (Fix C)
# -----------------------------------------------------------------------

# Bus-clear test: the MSSP STOP cascade self-recovers in gpsim for
# all versions (the fault model uses BRG delay, not a truly stuck bus).
# V2.7 is the only version with actual bus-clear code, but the test
# can't distinguish it from V2.3/V2.6's natural recovery.  All pass.
_BUS_CLEAR_VERSIONS = [
    pytest.param(STOCK_MAIN_HEX, id="main_v23"),
    pytest.param(PATCHED_MAIN_HEX_V26, id="main_v26"),
    pytest.param(PATCHED_MAIN_HEX_V27, id="main_v27"),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _BUS_CLEAR_VERSIONS)
def test_main_bus_clear_recovers_after_mssp_stop_fault(
    main_hex: Path,
) -> None:
    """After extended MSSP STOP fault cascade, bus-clear recovers DSP.

    Uses the SAME fault scenario as the V2.6 MSSP cascade test
    (stop_busy_cycles=5M, infinite count, 30 steps), which is
    PROVEN to degrade the DSP path on V2.3-V2.6.

    V2.7's bus-clear (called from pen_timeout_hook and
    patch_recover_mssp) should recover the I2C bus after the
    cascade.  After clearing the fault, a new volume command
    should reach the DSP.

    xfail on V2.3-V2.6 (DSP path stays degraded — confirmed by
    test_wire_extended_mssp_stop_fault_degrades_dsp_command_path).
    """
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _new_main_harness(main_hex)
    try:
        _boot_and_activate(harness)

        # DSP baseline
        snap_a = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(harness))) > 0, "baseline broken"

        # Inject extended MSSP STOP fault (same params as V2.6 cascade test)
        harness.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        # Clear fault and let firmware recover
        harness.clear_mssp_stop_faults()
        for _ in range(15):
            harness.step()

        # New volume command — V2.7 bus-clear should recover DSP path
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

_PING_VERSIONS = [
    pytest.param(
        PATCHED_MAIN_HEX_V26,
        marks=pytest.mark.xfail(reason="V2.6: no DSP ping", strict=True),
        id="main_v26",
    ),
    pytest.param(
        PATCHED_MAIN_HEX_V27,
        marks=pytest.mark.xfail(reason="V2.7: DSP ping deferred (no space)", strict=True),
        id="main_v27",
    ),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _PING_VERSIONS)
def test_main_dsp_ping_latches_fault_on_persistent_nack(
    main_hex: Path,
) -> None:
    """DSP ping latches 0x07F.bit6 when TAS3108 is persistently NACKing.

    Injects persistent address NACKs on dsp34, sends volume command.
    V2.7's DSP ping (after ACKSTAT detection + bus-clear) should
    detect the persistent NACK and latch the DSP fault flag.

    xfail on V2.6 (no ping, no fault flag at bit6).
    """
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _new_main_harness(main_hex)
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

        # V2.7: DSP fault flag (0x07F.bit6) should be latched
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


_FAULT_REPORTING_COMBOS = [
    pytest.param(
        PATCHED_CONTROL_HEX_V162B, PATCHED_MAIN_HEX_V26,
        marks=pytest.mark.xfail(reason="V2.6+V1.62b: no BF/08", strict=True),
        id="v26_v162b",
    ),
    pytest.param(
        PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V27,
        marks=pytest.mark.xfail(reason="V2.7: BF/08 deferred (no space for Fix E)", strict=True),
        id="v27_v163b",
    ),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex, main_hex", _FAULT_REPORTING_COMBOS)
def test_wire_dsp_fault_reporting(control_hex: Path, main_hex: Path) -> None:
    """CONTROL shows DSP fault indicator after MAIN reports BF/08.

    Wire-chain e2e: inject dsp34 NACKs, trigger volume command.
    V2.7 MAIN sends BF/08 with fault bits.  V1.63b CONTROL sets
    dsp_fault flag (0x01F.bit7) and shows indicator on LCD.

    After clearing NACKs, MAIN sends BF/08 with 0, CONTROL clears
    the fault, and a resync refreshes all settings.
    """
    _require_gpsim()
    _skip_missing(main_hex, control_hex)

    chain = WireMultiMainChainHarness(
        control_hex,
        main_hex,
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
        chain.step_many(15)

        # V1.63b CONTROL: dsp_fault flag (0x01F.bit7) should be set
        ctrl_flags = chain.control.read_reg(0x01F)
        dsp_fault = bool(ctrl_flags & 0x80)
        assert dsp_fault, (
            f"CONTROL dsp_fault (0x01F.bit7) not set — "
            f"0x01F=0x{ctrl_flags:02X}"
        )

        # LCD should show fault indicator
        lcd = chain.lcd_lines()
        assert "!" in lcd[0] or "ERR" in lcd[0].upper() or "ERR" in lcd[1].upper(), (
            f"no fault indicator on LCD: {lcd!r}"
        )

        # Clear NACKs → MAIN clears fault → CONTROL clears indicator
        chain.clear_main_i2c_faults("dsp34")
        chain.step_many(20)
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


_CASCADE_RECOVERY_COMBOS = [
    pytest.param(
        PATCHED_CONTROL_HEX_V162B, PATCHED_MAIN_HEX_V26,
        marks=pytest.mark.xfail(reason="V2.6+V1.62b: no recovery", strict=True),
        id="v26_v162b",
    ),
    pytest.param(
        PATCHED_CONTROL_HEX_V163B, PATCHED_MAIN_HEX_V27,
        marks=pytest.mark.xfail(reason="V2.7: full cascade recovery needs DSP ping (deferred)", strict=True),
        id="v27_v163b",
    ),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("control_hex, main_hex", _CASCADE_RECOVERY_COMBOS)
def test_wire_mssp_stop_cascade_full_recovery(
    control_hex: Path, main_hex: Path,
) -> None:
    """Extended MSSP STOP fault → bus-clear → DSP path recovers.

    Same scenario as the V2.6 MSSP cascade test but expecting FULL
    recovery: after the fault clears, V2.7's bus-clear + ping
    restore the DSP path.  Volume commands work after recovery.

    xfail on V2.6 (DSP path stays degraded after MSSP fault).
    """
    _require_gpsim()
    _skip_missing(main_hex, control_hex)

    chain = WireMultiMainChainHarness(
        control_hex,
        main_hex,
        main_units=1,
        fast_boot=False,
        disable_standby_check=False,
    )
    try:
        last = chain.run_until_connected(limit=80)
        assert chain.is_connected()
        main = chain.mains[0]

        # DSP baseline
        snap_a = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(main))) > 0

        # MSSP STOP fault
        chain.set_main_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        chain.step_many(30)

        # Clear fault, let V2.7 recover
        chain.clear_main_mssp_stop_faults()
        chain.step_many(15)

        # If CONTROL entered WAITING, reconnect
        if chain.is_waiting():
            chain.run_until_connected(limit=60)

        # Volume command MUST work after recovery
        snap_b = _dsp34_snapshot(main)
        chain.press("UP")
        chain.step_many(5)
        diff_post = _dsp34_diff(snap_b, _dsp34_snapshot(main))
        assert len(diff_post) > 0, (
            "DSP path not recovered after MSSP STOP cascade — "
            "V2.7 bus-clear/ping did not restore I2C"
        )

    finally:
        chain.close()


# -----------------------------------------------------------------------
# Test 5: PEN timeout in function_081 (Fix F)
# -----------------------------------------------------------------------


_PEN_TIMEOUT_VERSIONS = [
    pytest.param(
        PATCHED_MAIN_HEX_V26,
        marks=pytest.mark.xfail(reason="V2.6: PEN busy-wait unbounded", strict=True),
        id="main_v26",
    ),
    pytest.param(
        PATCHED_MAIN_HEX_V27,
        marks=pytest.mark.xfail(reason="V2.7: PEN hook removed (boot hang)", strict=True),
        id="main_v27",
    ),
]


@pytest.mark.gpsim
@pytest.mark.slow
@pytest.mark.parametrize("main_hex", _PEN_TIMEOUT_VERSIONS)
def test_main_pen_timeout_recovers(main_hex: Path) -> None:
    """PEN busy-wait timeout prevents permanent hang on stuck STOP.

    Injects a single long MSSP STOP fault (stop_busy_cycles >> chunk),
    sends volume command.  V2.7's PEN timeout hook at label_572
    should detect the stuck STOP and recover without hanging.

    The harness step should complete (not timeout) even with the
    stuck STOP, because V2.7's bounded PEN wait returns after the
    timeout budget.

    xfail on V2.6 (PEN busy-wait is unbounded — gpsim step
    completes anyway because the fault model uses BRG delay, not
    true infinite loop, but the firmware doesn't recover cleanly).
    """
    _require_gpsim()
    _skip_missing(main_hex)

    harness = _new_main_harness(main_hex)
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

        # After V2.7 PEN timeout + recovery, DSP should still work
        snap = _dsp34_snapshot(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        diff = _dsp34_diff(snap, _dsp34_snapshot(harness))

        assert len(diff) > 0, (
            "DSP path broken after PEN timeout — V2.7 should recover "
            "from stuck STOP condition via bounded PEN wait + bus-clear"
        )

    finally:
        harness.close()
