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

Three earlier wire-chain tests
(``test_wire_dsp_fault_reporting``,
``test_wire_mssp_stop_cascade_control_path_recovers_without_sim_pokes``,
``test_wire_mssp_stop_cascade_full_dsp_recovery``) were gpsim-only by
design: they used ``WireMultiMainChainHarness`` whose PTY-bridged
single-process scheduler is not modeled by the rust universal-clock
engine.  The MAIN-side bus-clear / DSP-ping behaviour is fully
exercised by the MAIN-only tests below; the CONTROL-side dsp_fault
flag transition has end-to-end coverage via the V1.71×V3.2 chain
tests (``test_v171_v32_layer5_diag_chain.py``).
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V31_MAIN_HEX,
    V32_MAIN_ASM,
    V32_MAIN_HEX,
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
_FLAGS_7F = 0x07F
_LOGICAL_VOLUME_REG = 0x066
_VOLUME_REG = 0x06E
_RX_RING_RD = 0x0C6
_RX_RING_WR = 0x0C7
_PRESET_B_BIT = 0x04
_PRESET_JOB_STATE = 0x2DE
_PRESET_JOB_TARGET = 0x2DF
_PRESET_JOB_INDEX = 0x2E0
_DIAG_I_ADDR = 0x2E5
_DIAG_R_ADDR = 0x2E9
_MAIN_RX_FRAME_GAP_TIMEOUT = 0x2F1
_I2C_RECOVER_FLAGS = 0x2F2
_DSP_FAULT_BIT = 6  # 0x07F.bit6: persistent DSP fault


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


_DEFAULT_CHUNK_TCY = 200_000


class _RustMainOnlyAdapter:
    """rust-side MAIN-only adapter.  ``advance_tcy(N)`` advances the
    full ``N`` MAIN-Tcy in a single ``step_tcy`` call; ``probe_step()``
    advances exactly ``chunk_tcy`` so callers can sample transient
    state at fixed granularity."""

    def __init__(self, main_hex: Path, *, chunk_tcy: int = _DEFAULT_CHUNK_TCY) -> None:
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

    def set_mssp_start_fault(self, *, cycles: int, count: int) -> None:
        self._c.set_mssp_start_fault(cycles=cycles, count=count)

    def clear_mssp_start_faults(self) -> None:
        self._c.clear_mssp_start_faults()

    def clear_mssp_stop_faults(self) -> None:
        self._c.clear_mssp_stop_faults()

    def force_clear_sspcon2(self) -> None:
        # Aborts any in-flight MSSP state-machine transaction; the
        # rust MSSP keeps its own state-machine countdown so an
        # explicit reset is needed to mirror gpsim's
        # `p18f2455.sspcon2 = 0` privileged write.
        self._c.force_reset_main_mssp()


def _make_adapter(
    main_hex: Path, *, chunk_tcy: int = _DEFAULT_CHUNK_TCY
) -> _RustMainOnlyAdapter:
    _require_rust()
    return _RustMainOnlyAdapter(main_hex, chunk_tcy=chunk_tcy)


def _boot_and_activate_h(h: _RustMainOnlyAdapter) -> None:
    h.advance_tcy(20 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


def _wait_for_uart_settled_h(h: _RustMainOnlyAdapter, *, limit: int = 80) -> None:
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
    h: _RustMainOnlyAdapter, expected_state: int, *, limit: int = 300
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


def _wait_for_preset_job_idle_h(h: _RustMainOnlyAdapter, *, limit: int = 320) -> None:
    _wait_for_preset_job_state_h(h, 0x00, limit=limit)


def _inject_main_frame_h(
    h: _RustMainOnlyAdapter, *, cmd: int, data: int
) -> None:
    delivered, overruns = h.inject_main_frames_fifo(
        [[0xB0, cmd, data]], fifo_limit=47
    )
    assert delivered == 3 and overruns == 0, (
        f"failed to inject MAIN frame B0/{cmd:02X}/{data:02X}: "
        f"delivered={delivered} overruns={overruns}"
    )


def test_v32_i2c_recover_latch_does_not_clobber_rx_gap_timeout() -> None:
    """The MSSP recovery latch must not reuse live parser liveness RAM."""
    text = V32_MAIN_ASM.read_text()
    ram_inc = V32_MAIN_ASM.with_name("dlcp_main_ram.inc").read_text()
    mssp_reset_body = text.split("mssp_hard_reset:", 1)[1].split(
        "; ---------------------------------------------------------------------------",
        1,
    )[0]

    assert _I2C_RECOVER_FLAGS != _MAIN_RX_FRAME_GAP_TIMEOUT
    assert f"i2c_recover_flags       EQU  0x{_I2C_RECOVER_FLAGS:03X}" in text
    assert (
        f"main_rx_frame_gap_timeout   EQU  0x{_MAIN_RX_FRAME_GAP_TIMEOUT:03X}"
        in ram_inc
    )
    assert "movlw       0xC0" in mssp_reset_body
    assert "andwf       SSPSTAT, F, ACCESS" in mssp_reset_body


def test_v32_volume_dsp_write_reasserts_bank0_after_i2c_helper() -> None:
    """The NACK test must read dsp_fault_flags in bank 0 after I2C calls."""
    text = V32_MAIN_ASM.read_text()
    body = text.split("volume_dsp_write:", 1)[1].split(
        "vol_write_nacked:",
        1,
    )[0]

    assert re.search(
        r"(?:rcall\s+i2c_tas3108_coeff_write|call\s+i2c_tas3108_coeff_write,\s*0x0)\s*\n"
        r"\s*movlb\s+0x0+\s*[^\n]*\n"
        r"\s*btfsc\s+dsp_fault_flags,\s*2,\s*BANKED",
        body,
    ), "volume_dsp_write must reassert BSR=0 before testing dsp_fault_flags.bit2"


# -----------------------------------------------------------------------
# Test 1: I2C bus-clear recovers stuck slave (Fix C)
# -----------------------------------------------------------------------


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main_bus_clear_recovers_after_mssp_stop_fault() -> None:
    """After extended MSSP STOP fault cascade, bus-clear recovers DSP."""
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    _boot_and_activate_h(h)

    snap_a = h.read_dsp_snapshot()
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert any(
        snap_a[r] != h.read_dsp_reg(r) for r in range(256)
    ), "baseline broken"

    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
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
        "DSP path not recovered after MSSP STOP cascade -- "
        "bus-clear did not restore I2C communication"
    )


# -----------------------------------------------------------------------
# Test 2: DSP ping detects dead TAS3108 (Fix D)
# -----------------------------------------------------------------------


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main_dsp_ping_latches_fault_on_persistent_nack() -> None:
    """DSP ping latches 0x07F.bit6 when TAS3108 is persistently NACKing."""
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    _boot_and_activate_h(h)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)

    h.set_i2c_fault("dsp34", address_nack_count=60000)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
    h.advance_tcy(30 * h.chunk_tcy)

    flags = h.read_reg(_FLAGS_7F)
    fault = flags & (1 << _DSP_FAULT_BIT)
    assert fault != 0, (
        f"DSP fault flag (0x07F.bit6) not latched after persistent NACK "
        f"-- 0x07F=0x{flags:02X}"
    )


# -----------------------------------------------------------------------
# Test 3: PEN timeout in i2c_tas3108_coeff_write (Fix F)
# -----------------------------------------------------------------------


@pytest.mark.dual_supported
@pytest.mark.slow
def test_main_pen_timeout_recovers() -> None:
    """PEN busy-wait timeout prevents permanent hang on stuck STOP."""
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    _boot_and_activate_h(h)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)

    h.set_mssp_stop_fault(stop_busy_cycles=50_000_000, stop_busy_count=1)
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
        "DSP path broken after PEN timeout -- V3.1 should recover from "
        "stuck STOP condition via bounded PEN wait + bus-clear"
    )


# -----------------------------------------------------------------------
# V3.2 robustness regression — same scenarios, async preset job baseline
# -----------------------------------------------------------------------


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_main_bus_clear_recovers_after_mssp_stop_fault() -> None:
    """V3.2 consumes fresh runtime commands after an MSSP STOP cascade."""
    _skip_missing(V32_MAIN_HEX)

    h = _make_adapter(V32_MAIN_HEX)
    _boot_and_activate_h(h)
    _wait_for_uart_settled_h(h)

    snap_a = h.read_dsp_snapshot()
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert any(
        snap_a[r] != h.read_dsp_reg(r) for r in range(256)
    ), "baseline broken"

    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
    h.advance_tcy(30 * h.chunk_tcy)

    h.clear_mssp_stop_faults()
    h.advance_tcy(15 * h.chunk_tcy)
    assert h.read_reg(_DIAG_I_ADDR) > 0, "STOP timeout was not counted in diag_i"
    assert h.read_reg(_DIAG_R_ADDR) > 0, "STOP recovery was not counted in diag_r"

    _inject_main_frame_h(h, cmd=0x07, data=0x40)
    for _ in range(80):
        h.probe_step()
        if (
            h.read_reg(_LOGICAL_VOLUME_REG) == 0xE0
            and h.read_reg(_VOLUME_REG) == 0xE0
            and h.read_reg(_RX_RING_RD) == h.read_reg(_RX_RING_WR)
        ):
            break
    else:
        raise AssertionError(
            "V3.2 did not consume the follow-up volume command after "
            "MSSP STOP recovery"
        )

    assert not (h.read_reg(_FLAGS_7F) & 0x44), (
        f"follow-up volume command left DSP/I2C fault bits set: "
        f"0x07F=0x{h.read_reg(_FLAGS_7F):02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_main_pen_timeout_recovers() -> None:
    """V3.2 preserves PEN timeout recovery from stuck STOP condition."""
    _skip_missing(V32_MAIN_HEX)

    h = _make_adapter(V32_MAIN_HEX)
    _boot_and_activate_h(h)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)

    h.set_mssp_stop_fault(stop_busy_cycles=50_000_000, stop_busy_count=1)
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

    assert len(diff) > 0, "V3.2 DSP path broken after PEN timeout"


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_runtime_start_timeout_keeps_main_loop_responsive_and_flags_fault() -> None:
    """A permanent START/SEN fault in a normal runtime DSP write must not
    strand MAIN in an MSSP busy-wait.

    This covers the long-soak field symptom: audio keeps playing because
    MAIN is trapped inside an I2C/MSSP wait and later control frames are
    never serviced.  A robust V3.2 MAIN must bound the wait, run recovery,
    advertise the fault via the existing BF/08 state byte, and return to
    the parser so a follow-up command can be consumed.
    """
    _skip_missing(V32_MAIN_HEX)

    h = _make_adapter(V32_MAIN_HEX)
    _boot_and_activate_h(h)
    _wait_for_uart_settled_h(h)

    h.set_mssp_start_fault(cycles=5_000_000, count=-1)
    _inject_main_frame_h(h, cmd=0x07, data=0x30)
    h.advance_tcy(8 * h.chunk_tcy)

    _inject_main_frame_h(h, cmd=0x20, data=0x01)
    h.advance_tcy(8 * h.chunk_tcy)

    assert h.read_reg(_PRESET_JOB_TARGET) == 0x01, (
        "follow-up preset command was not consumed after a runtime START "
        "fault; MAIN likely wedged inside an unbounded MSSP wait"
    )
    assert h.read_reg(_FLAGS_7F) & 0x44, (
        f"DSP/I2C fault was not advertised in dsp_fault_flags after "
        f"bounded START recovery; flags=0x{h.read_reg(_FLAGS_7F):02X}"
    )
    assert h.read_reg(_DIAG_I_ADDR) > 0, "I2C timeout was not counted in diag_i"
    assert h.read_reg(_DIAG_R_ADDR) > 0, "I2C recovery was not counted in diag_r"


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_keeps_main_loop_responsive() -> None:
    """A stuck STOP during async APPLY must return to the main loop.

    Arms the persistent STOP fault BEFORE injecting the preset-select
    frame so the first APPLY iteration hits the fault.
    """
    _skip_missing(V32_MAIN_HEX)

    h = _make_adapter(V32_MAIN_HEX)
    _boot_and_activate_h(h)
    _wait_for_uart_settled_h(h)
    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
    _inject_main_frame_h(h, cmd=0x20, data=0x01)
    _wait_for_preset_job_state_h(h, 0x03)
    assert h.read_reg(_PRESET_JOB_INDEX) == 0x00, (
        "async APPLY advanced past the first table entry even though "
        "the STOP fault was armed before preset-select"
    )

    _inject_main_frame_h(h, cmd=0x20, data=0x00)
    h.advance_tcy(8 * h.chunk_tcy)

    assert h.read_reg(_PRESET_JOB_STATE) == 0x03, (
        "async APPLY left retryable state during persistent STOP fault"
    )
    assert h.read_reg(_PRESET_JOB_INDEX) == 0x00, (
        "async APPLY advanced the table index during STOP timeout"
    )
    assert h.read_reg(_PRESET_JOB_TARGET) == 0x00, (
        "follow-up preset command was not consumed while STOP fault "
        "was active; the APPLY path likely wedged instead of returning "
        "to the main loop"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_does_not_advance_index() -> None:
    """A timed-out APPLY entry must stay queued until the fault clears."""
    _skip_missing(V32_MAIN_HEX)

    h = _make_adapter(V32_MAIN_HEX)
    _boot_and_activate_h(h)
    _wait_for_uart_settled_h(h)
    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
    _inject_main_frame_h(h, cmd=0x20, data=0x01)
    _wait_for_preset_job_state_h(h, 0x03)

    index_before = h.read_reg(_PRESET_JOB_INDEX)
    h.advance_tcy(12 * h.chunk_tcy)

    assert index_before == 0x00, (
        f"test setup expected the first APPLY entry to be pending; "
        f"got index_before=0x{index_before:02X}"
    )
    assert h.read_reg(_PRESET_JOB_INDEX) == index_before, (
        "async APPLY index advanced while STOP timeout recovery was "
        "still retrying"
    )
    assert h.read_reg(_PRESET_JOB_STATE) == 0x03, (
        "async APPLY left state 3 during a retryable STOP timeout"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_async_apply_stop_timeout_recovers_and_completes() -> None:
    """Clearing a STOP fault must let the same async APPLY job finish."""
    _skip_missing(V32_MAIN_HEX)

    h = _make_adapter(V32_MAIN_HEX)
    _boot_and_activate_h(h)
    _wait_for_uart_settled_h(h)
    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
    _inject_main_frame_h(h, cmd=0x20, data=0x01)
    _wait_for_preset_job_state_h(h, 0x03)
    h.advance_tcy(8 * h.chunk_tcy)
    assert h.read_reg(_PRESET_JOB_INDEX) == 0x00, (
        "STOP timeout test lost the first pending APPLY entry before "
        "recovery"
    )

    h.clear_mssp_stop_faults()
    _wait_for_preset_job_idle_h(h)

    assert h.read_reg(_PRESET_JOB_INDEX) == 0x60, (
        "async APPLY did not finish the 96 regular table entries "
        "after STOP fault recovery"
    )
    assert h.read_reg(_STATUS_5E) & _PRESET_B_BIT, (
        "preset B was not committed after STOP fault recovery"
    )
