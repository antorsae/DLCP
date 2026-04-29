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

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

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


# ---- Backend-uniform helpers (mirror of test_v31_review_findings) ----
#
# Each adapter exposes:
#   * `advance_tcy(tcy)`  -- bulk time advance.  gpsim loops
#     `tcy // chunk_tcy` chunked step() calls; rust does a
#     single `step_tcy(tcy)` call.
#   * `probe_step()` -- advance exactly chunk_tcy and return so
#     the caller can sample state.
#   * standard read/inject/fault accessors.

_GPSIM_CHUNK_TCY = 200_000


class _GpsimMainOnlyAdapter:
    def __init__(self, main_hex: Path, *, chunk_tcy: int = _GPSIM_CHUNK_TCY) -> None:
        self._chunk_tcy = chunk_tcy
        self._h = MainChainHarness(
            main_hex,
            chunk_cycles=chunk_tcy,
            standby_mode="hold",
            rc2_mode="low",
            bypass_i2c=False,
            transport_mode="native_ring",
        )

    def advance_tcy(self, tcy: int) -> None:
        for _ in range(tcy // self._chunk_tcy):
            self._h.step()

    def probe_step(self) -> None:
        self._h.step()

    @property
    def chunk_tcy(self) -> int:
        return self._chunk_tcy

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        return self._h.inject_frames_fifo(frames, fifo_limit=fifo_limit)

    def read_reg(self, addr: int) -> int:
        return _read_reg(self._h._issue, addr)

    def write_reg(self, addr: int, value: int) -> None:
        # gpsim's SSPCON2.put() ignores writes during active I2C;
        # use the raw register-poke command which bypasses the
        # SFR write filter.  Mirrors `harness._issue("p18f2455.
        # sspcon2 = ...")` shape for SFR addresses.
        sfr_name = _GPSIM_SFR_NAME_BY_ADDR.get(addr)
        if sfr_name is not None:
            try:
                self._h._issue(f"p18f2455.{sfr_name} = 0x{value:02x}", 5.0)
            except Exception:
                pass
        else:
            self._h._issue(f"reg(0x{addr:03X})=0x{value:02X}", 5.0)

    def read_dsp_reg(self, subaddr: int) -> int:
        return self._h.read_i2c_regfile("dsp34", subaddr)

    def read_dsp_snapshot(self) -> dict[int, int]:
        return {r: self._h.read_i2c_regfile("dsp34", r) for r in range(256)}

    def set_i2c_fault(self, device: str, *, address_nack_count: int) -> None:
        self._h.set_i2c_fault(device, address_nack_count=address_nack_count)

    def clear_i2c_faults(self, device: str = "dsp34") -> None:
        self._h.clear_i2c_faults(device)

    def set_mssp_stop_fault(
        self, *, stop_busy_cycles: int, stop_busy_count: int
    ) -> None:
        self._h.set_mssp_stop_fault(
            stop_busy_cycles=stop_busy_cycles,
            stop_busy_count=stop_busy_count,
        )

    def clear_mssp_stop_faults(self) -> None:
        self._h.clear_mssp_stop_faults()

    def force_clear_sspcon2(self) -> None:
        try:
            self._h._issue("p18f2455.sspcon2 = 0", 5.0)
        except Exception:
            pass

    def close(self) -> None:
        self._h.close()


# Mapping from physical SFR address to gpsim's `p18f2455.<sfr>`
# name for harness write-bypass.  Only SFRs whose put() filter
# blocks normal RAM-poke writes need an entry here.
_GPSIM_SFR_NAME_BY_ADDR = {
    0xFC5: "sspcon2",
}


class _RustMainOnlyAdapter:
    def __init__(self, main_hex: Path, *, chunk_tcy: int = _GPSIM_CHUNK_TCY) -> None:
        self._c = RustChain.from_v3x_main_only(str(main_hex))
        self._chunk_tcy = chunk_tcy

    def advance_tcy(self, tcy: int) -> None:
        self._c.step_tcy(tcy)

    def probe_step(self) -> None:
        self._c.step_tcy(self._chunk_tcy)

    @property
    def chunk_tcy(self) -> int:
        return self._chunk_tcy

    def inject_main_frames_fifo(
        self, frames: list[list[int]], fifo_limit: int
    ) -> tuple[int, int]:
        return self._c.inject_main_frames_fifo(frames, fifo_limit)

    def read_reg(self, addr: int) -> int:
        return self._c.read_reg(addr)

    def write_reg(self, addr: int, value: int) -> None:
        self._c.write_reg(addr, value)

    def read_dsp_reg(self, subaddr: int) -> int:
        return self._c.read_dsp_reg(subaddr)

    def read_dsp_snapshot(self) -> dict[int, int]:
        return {r: self._c.read_dsp_reg(r) for r in range(256)}

    def set_i2c_fault(self, device: str, *, address_nack_count: int) -> None:
        self._c.set_i2c_fault(device, address_nack_count=address_nack_count)

    def clear_i2c_faults(self, device: str = "dsp34") -> None:
        self._c.clear_i2c_faults(device)

    def set_mssp_stop_fault(
        self, *, stop_busy_cycles: int, stop_busy_count: int
    ) -> None:
        self._c.set_mssp_stop_fault(
            stop_busy_cycles=stop_busy_cycles,
            stop_busy_count=stop_busy_count,
        )

    def clear_mssp_stop_faults(self) -> None:
        self._c.clear_mssp_stop_faults()

    def force_clear_sspcon2(self) -> None:
        # Mirror of gpsim's `p18f2455.sspcon2 = 0` privileged
        # register write: BOTH clears SSPCON2 SFR trigger bits
        # AND aborts any in-flight MSSP state-machine
        # transaction (gpsim polls SSPCON2 each tick and
        # aborts when trigger bits are cleared externally; the
        # rust MSSP keeps its own state-machine countdown so
        # we need an explicit reset).
        self._c.force_reset_main_mssp()

    def close(self) -> None:
        pass


def _make_adapter(main_hex: Path, backend: str, *, chunk_tcy: int = _GPSIM_CHUNK_TCY):
    if backend == "rust":
        return _RustMainOnlyAdapter(main_hex, chunk_tcy=chunk_tcy)
    return _GpsimMainOnlyAdapter(main_hex, chunk_tcy=chunk_tcy)


def _enabled_backends(dlcp_sim_backend: str) -> list[str]:
    backends: list[str] = []
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        backends.append("rust")
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        backends.append("gpsim")
    return backends


def _boot_and_activate_h(h) -> None:
    h.advance_tcy(20 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


def _wait_for_uart_settled_h(h, *, limit: int = 80) -> None:
    """Poll until the V3.2 wake path finishes arming the UART
    and clears the native RX ring (RCSTA SPEN+CREN set, rx_ring_wr
    cleared)."""
    rcsta = 0
    rx_wr = 0
    for _ in range(limit):
        rcsta = h.read_reg(0xFAB)  # RCSTA SFR
        rx_wr = h.read_reg(0x0C7)  # rx_ring_wr
        if (rcsta & 0x90) == 0x90 and rx_wr == 0:
            return
        h.probe_step()
    raise AssertionError(
        f"wake never reached quiescent UART state within {limit} probes: "
        f"RCSTA=0x{rcsta:02X} rx_wr=0x{rx_wr:02X}"
    )


def _wait_for_preset_job_state_h(
    h, expected_state: int, *, limit: int = 300
) -> None:
    state = 0
    for _ in range(limit):
        h.probe_step()
        state = h.read_reg(_PRESET_JOB_STATE)
        if state == expected_state:
            return
    raise AssertionError(
        f"preset job did not reach state {expected_state} within {limit} probes: "
        f"state=0x{state:02X} index=0x{h.read_reg(_PRESET_JOB_INDEX):02X} "
        f"target=0x{h.read_reg(_PRESET_JOB_TARGET):02X}"
    )


def _wait_for_preset_job_idle_h(h, *, limit: int = 320) -> None:
    _wait_for_preset_job_state_h(h, 0x00, limit=limit)


def _inject_main_frame_h(h, *, cmd: int, data: int) -> None:
    delivered, overruns = h.inject_main_frames_fifo(
        [[0xB0, cmd, data]], fifo_limit=47
    )
    assert delivered == 3 and overruns == 0, (
        f"failed to inject MAIN frame B0/{cmd:02X}/{data:02X}: "
        f"delivered={delivered} overruns={overruns}"
    )


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


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_main_bus_clear_recovers_after_mssp_stop_fault(
    dlcp_sim_backend: str,
) -> None:
    """After extended MSSP STOP fault cascade, bus-clear recovers DSP."""
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)

            snap_a = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            assert any(
                snap_a[r] != h.read_dsp_reg(r) for r in range(256)
            ), f"[{backend}] baseline broken"

            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)

            h.clear_mssp_stop_faults()
            h.advance_tcy(15 * h.chunk_tcy)

            snap_b = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            after_b = h.read_dsp_snapshot()
            diff_recovery = [
                (r, snap_b[r], after_b[r])
                for r in range(256)
                if snap_b[r] != after_b[r]
            ]

            assert len(diff_recovery) > 0, (
                f"[{backend}] DSP path not recovered after MSSP STOP "
                f"cascade -- bus-clear did not restore I2C communication"
            )
        finally:
            h.close()


# -----------------------------------------------------------------------
# Test 2: DSP ping detects dead TAS3108 (Fix D)
# -----------------------------------------------------------------------


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_main_dsp_ping_latches_fault_on_persistent_nack(
    dlcp_sim_backend: str,
) -> None:
    """DSP ping latches 0x07F.bit6 when TAS3108 is persistently NACKing."""
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)

            h.set_i2c_fault("dsp34", address_nack_count=60000)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)

            flags = h.read_reg(_FLAGS_7F)
            fault = flags & (1 << _DSP_FAULT_BIT)
            assert fault != 0, (
                f"[{backend}] DSP fault flag (0x07F.bit6) not latched "
                f"after persistent NACK -- 0x07F=0x{flags:02X}"
            )
        finally:
            h.close()


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


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_main_pen_timeout_recovers(dlcp_sim_backend: str) -> None:
    """PEN busy-wait timeout prevents permanent hang on stuck STOP."""
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)

            h.set_mssp_stop_fault(
                stop_busy_cycles=50_000_000, stop_busy_count=1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(10 * h.chunk_tcy)

            h.clear_mssp_stop_faults()
            h.force_clear_sspcon2()
            h.advance_tcy(5 * h.chunk_tcy)

            snap = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)
            after = h.read_dsp_snapshot()
            diff = [
                (r, snap[r], after[r])
                for r in range(256)
                if snap[r] != after[r]
            ]

            assert len(diff) > 0, (
                f"[{backend}] DSP path broken after PEN timeout -- V3.1 "
                f"should recover from stuck STOP condition via bounded "
                f"PEN wait + bus-clear"
            )
        finally:
            h.close()


# -----------------------------------------------------------------------
# V3.2 robustness regression — same scenarios, async preset job baseline
# -----------------------------------------------------------------------


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_main_bus_clear_recovers_after_mssp_stop_fault(
    dlcp_sim_backend: str,
) -> None:
    """V3.2 preserves bus-clear recovery after MSSP STOP fault cascade."""
    _skip_missing(V32_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V32_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)

            snap_a = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            assert any(
                snap_a[r] != h.read_dsp_reg(r) for r in range(256)
            ), f"[{backend}] baseline broken"

            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)

            h.clear_mssp_stop_faults()
            h.advance_tcy(15 * h.chunk_tcy)

            snap_b = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            after_b = h.read_dsp_snapshot()
            diff_recovery = [
                (r, snap_b[r], after_b[r])
                for r in range(256)
                if snap_b[r] != after_b[r]
            ]

            assert len(diff_recovery) > 0, (
                f"[{backend}] V3.2 DSP path not recovered after MSSP "
                f"STOP cascade"
            )
        finally:
            h.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_main_pen_timeout_recovers(dlcp_sim_backend: str) -> None:
    """V3.2 preserves PEN timeout recovery from stuck STOP condition."""
    _skip_missing(V32_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V32_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)

            h.set_mssp_stop_fault(
                stop_busy_cycles=50_000_000, stop_busy_count=1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(10 * h.chunk_tcy)

            h.clear_mssp_stop_faults()
            h.force_clear_sspcon2()
            h.advance_tcy(5 * h.chunk_tcy)

            snap = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)
            after = h.read_dsp_snapshot()
            diff = [
                (r, snap[r], after[r])
                for r in range(256)
                if snap[r] != after[r]
            ]

            assert len(diff) > 0, (
                f"[{backend}] V3.2 DSP path broken after PEN timeout"
            )
        finally:
            h.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_keeps_main_loop_responsive(
    dlcp_sim_backend: str,
) -> None:
    """A stuck STOP during async APPLY must return to the main loop.

    Arms the persistent STOP fault BEFORE injecting the preset-select
    frame so the first APPLY iteration hits the fault.
    """
    _skip_missing(V32_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V32_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            _wait_for_uart_settled_h(h)
            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            _inject_main_frame_h(h, cmd=0x20, data=0x01)
            _wait_for_preset_job_state_h(h, 0x03)
            assert h.read_reg(_PRESET_JOB_INDEX) == 0x00, (
                f"[{backend}] async APPLY advanced past the first table "
                f"entry even though the STOP fault was armed before "
                f"preset-select"
            )

            _inject_main_frame_h(h, cmd=0x20, data=0x00)
            h.advance_tcy(8 * h.chunk_tcy)

            assert h.read_reg(_PRESET_JOB_STATE) == 0x03, (
                f"[{backend}] async APPLY left retryable state during "
                f"persistent STOP fault"
            )
            assert h.read_reg(_PRESET_JOB_INDEX) == 0x00, (
                f"[{backend}] async APPLY advanced the table index "
                f"during STOP timeout"
            )
            assert h.read_reg(_PRESET_JOB_TARGET) == 0x00, (
                f"[{backend}] follow-up preset command was not consumed "
                f"while STOP fault was active; the APPLY path likely "
                f"wedged instead of returning to the main loop"
            )
        finally:
            h.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_does_not_advance_index(
    dlcp_sim_backend: str,
) -> None:
    """A timed-out APPLY entry must stay queued until the fault clears."""
    _skip_missing(V32_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V32_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            _wait_for_uart_settled_h(h)
            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            _inject_main_frame_h(h, cmd=0x20, data=0x01)
            _wait_for_preset_job_state_h(h, 0x03)

            index_before = h.read_reg(_PRESET_JOB_INDEX)
            h.advance_tcy(12 * h.chunk_tcy)

            assert index_before == 0x00, (
                f"[{backend}] test setup expected the first APPLY entry "
                f"to be pending; got index_before=0x{index_before:02X}"
            )
            assert h.read_reg(_PRESET_JOB_INDEX) == index_before, (
                f"[{backend}] async APPLY index advanced while STOP "
                f"timeout recovery was still retrying"
            )
            assert h.read_reg(_PRESET_JOB_STATE) == 0x03, (
                f"[{backend}] async APPLY left state 3 during a "
                f"retryable STOP timeout"
            )
        finally:
            h.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_recovers_and_completes(
    dlcp_sim_backend: str,
) -> None:
    """Clearing a STOP fault must let the same async APPLY job finish."""
    _skip_missing(V32_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V32_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            _wait_for_uart_settled_h(h)
            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            _inject_main_frame_h(h, cmd=0x20, data=0x01)
            _wait_for_preset_job_state_h(h, 0x03)
            h.advance_tcy(8 * h.chunk_tcy)
            assert h.read_reg(_PRESET_JOB_INDEX) == 0x00, (
                f"[{backend}] STOP timeout test lost the first pending "
                f"APPLY entry before recovery"
            )

            h.clear_mssp_stop_faults()
            _wait_for_preset_job_idle_h(h)

            assert h.read_reg(_PRESET_JOB_INDEX) == 0x60, (
                f"[{backend}] async APPLY did not finish the 96 regular "
                f"table entries after STOP fault recovery"
            )
            assert h.read_reg(_STATUS_5E) & _PRESET_B_BIT, (
                f"[{backend}] preset B was not committed after STOP "
                f"fault recovery"
            )
        finally:
            h.close()
