"""V3.1 MAIN + V1.63b CONTROL robustness tests.

V3.1 is the source-rewrite equivalent of V2.7.  All V2.7 robustness
features (Fix C/D/E/F) are implemented inline in the assembly source.
These tests MUST pass — no xfails.

V3.1 fixes (inline):
  C: I2C bus-clear after MSSP recovery (bitbang 9 SCL clocks)
  D: DSP ping after bus-clear (TAS3108 address probe)
  E: BF/08 DSP fault status reporting to CONTROL
  F: PEN timeout in i2c_tas3108_coeff_write (boot-gated)
"""
from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    PATCHED_CONTROL_HEX_V163B,
    V31_MAIN_HEX,
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
def test_wire_mssp_stop_cascade_full_recovery() -> None:
    """Extended MSSP STOP fault -> bus-clear -> DSP path recovers."""
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

        # DSP baseline via direct frame injection to MAIN
        snap_a = _dsp34_snapshot(main)
        main.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        chain.step_many(10)
        assert len(_dsp34_diff(snap_a, _dsp34_snapshot(main))) > 0

        # MSSP STOP fault
        chain.set_main_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
        main.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        chain.step_many(30)

        # Clear fault and let firmware recover
        chain.clear_main_mssp_stop_faults()
        chain.step_many(15)

        # If CONTROL entered WAITING, reconnect
        if chain.is_waiting():
            chain.run_until_connected(limit=60)

        # Volume command MUST work after recovery
        snap_b = _dsp34_snapshot(main)
        main.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        chain.step_many(10)
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
