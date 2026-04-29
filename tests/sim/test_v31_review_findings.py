"""Tests driven by Codex-CLI review findings for V3.1 MAIN firmware.

These tests exercise specific code paths and edge cases identified
during the deep review of the V3.0→V3.1 delta:

  (a) Critical: BSR safety in i2c_byte_tx ACKSTAT write
  (b) High:    i2c_wait_bus_idle unbounded behavior under PEN fault
  (c) Gaps:    Degraded-state assertions during faults; BF/08 payload check
  (d) Cleanup: _force_clear_sspcon2 scoping and pre-assertions
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
from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

# --- PIC18F2455 SFR addresses (absolute) ---
_BSR = 0xFE0
_SSPCON2 = 0xFC5
_SSPCON1 = 0xFC6

# --- GPR addresses (bank 0, read via _read_reg absolute) ---
_FLAGS_7E = 0x07E
_FLAGS_7F = 0x07F
_STATUS_5E = 0x05E

_DSP_FAULT_BIT = 6  # 0x07F.bit6
_ACKSTAT_BIT = 2    # 0x07F.bit2


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


def _new_main_harness(main_hex: Path) -> MainChainHarness:
    return MainChainHarness(
        main_hex,
        chunk_cycles=200_000,
        standby_mode="hold",
        rc2_mode="low",
        bypass_i2c=False,
        transport_mode="native_ring",
    )


def _boot_and_activate(harness: MainChainHarness) -> None:
    for _ in range(20):
        harness.step()
    harness.inject_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    for _ in range(20):
        harness.step()
    assert _read_reg(harness._issue, _STATUS_5E) & 0x08, "MAIN not active"


def _dsp34_snapshot(harness: MainChainHarness) -> dict[int, int]:
    return {r: harness.read_i2c_regfile("dsp34", r) for r in range(256)}


def _dsp34_diff(before: dict[int, int], after: dict[int, int]) -> list:
    return [(r, before[r], after[r]) for r in range(256) if before[r] != after[r]]


# ---- Backend-uniform helpers (mirror of test_v31_happy_path.py) ----
#
# Each adapter exposes:
#   * `advance_tcy(tcy)` -- advance by `tcy` MAIN-Tcy.  gpsim
#     loops `tcy // chunk_tcy` chunked step() calls (its
#     single-process scheduler can't advance more than
#     chunk_tcy between core swaps); rust does a single
#     `step_tcy(tcy)` call (universal-clock scheduler runs
#     both cores in lock-step at instruction granularity, so
#     chunking is a gpsim implementation artifact we don't
#     replicate).
#   * `probe_step()` -- advance exactly one chunk_tcy worth of
#     simulated time and return so the caller can sample
#     transient state.  Used by the volume_dsp_write_retry
#     test where the firmware's retry counter is only briefly
#     elevated and per-chunk granularity is needed on both
#     backends to catch it.


class _GpsimMainOnlyAdapter:
    """gpsim-side adapter.  `chunk_tcy` is the gpsim
    `chunk_cycles` constructor knob: gpsim's single-process
    scheduler can't advance more than `chunk_tcy` between core
    swaps, so `advance_tcy(N)` loops `N // chunk_tcy` step()
    calls and `probe_step()` does exactly one chunk."""

    def __init__(self, main_hex: Path, *, chunk_tcy: int = 200_000) -> None:
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
        """Advance exactly one chunk, returning so the caller
        can sample state.  Used by tests that need to catch
        transient firmware state mid-burst."""
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

    def read_dsp_reg(self, subaddr: int) -> int:
        return self._h.read_i2c_regfile("dsp34", subaddr)

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

    def read_dsp_snapshot(self) -> dict[int, int]:
        return {r: self._h.read_i2c_regfile("dsp34", r) for r in range(256)}

    def close(self) -> None:
        self._h.close()


class _RustMainOnlyAdapter:
    """rust-side adapter.  `chunk_tcy` is only used by
    `probe_step` (per-call advancement for tests that need to
    catch transient state); `advance_tcy(N)` advances the full
    `N` MAIN-Tcy in a single `step_tcy` call -- the rust
    universal-clock scheduler runs both cores in lock-step at
    instruction granularity, so chunking is a gpsim
    implementation artifact we don't replicate."""

    def __init__(self, main_hex: Path, *, chunk_tcy: int = 200_000) -> None:
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

    def read_dsp_reg(self, subaddr: int) -> int:
        return self._c.read_dsp_reg(subaddr)

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

    def read_dsp_snapshot(self) -> dict[int, int]:
        return {r: self._c.read_dsp_reg(r) for r in range(256)}

    def close(self) -> None:
        pass


def _make_adapter(main_hex: Path, backend: str, *, chunk_tcy: int = 200_000):
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


# ===================================================================
# (a) Critical: BSR safety — i2c_byte_tx ACKSTAT write to 0x07F
# ===================================================================


# NOTE: NOT marked `dual_supported`.  This test asserts a CLEAN
# `dsp_fault_flags == 0x00` baseline after a successful volume
# command, before injecting NACKs.  On rust the baseline is 0x04
# (ACKSTAT bit set) after the same boot+activate+volume sequence:
# the rust MSSP/TAS3108 path leaves SSPCON2.ACKSTAT=1 after some
# byte in the burst, which the firmware latches to
# `dsp_fault_flags.2` via the V3.1 BSR-safe ACKSTAT-check at
# dlcp_main_v31.asm:5933.  Probed both backends:
#   * gpsim: 0x07F = 0x00 throughout (clean baseline).
#   * rust:  0x07F transitions 0x00 -> 0x04 between step+10 and
#            step+15 of the volume burst.
# This is a real backend divergence in the rust I²C TX path
# (`Chain::dispatch_i2c_to_coupled_slaves` + `Mssp::override_
# acked` interaction); investigating it is a separate sub-task.
# The post-NACK ACKSTAT-set invariant this test signals is
# partly covered by `test_volume_dsp_write_retry_counter_
# increments` (dual_supported below) -- that test asserts the
# retry counter at `dsp_fault_flags[5:3]` increments under
# persistent NACKs, which only happens if the BSR-safe ACKSTAT
# check at :5933 is firing correctly.


@pytest.mark.gpsim
@pytest.mark.slow
def test_bsr_safety_ackstat_write_after_volume_nack() -> None:
    """Verify dsp_fault_flags.2 is correctly set when DSP NACKs volume.

    The ACKSTAT latch in i2c_byte_tx uses BANKED access to 0x07F,
    which requires BSR=0.  This test injects NACKs during a volume
    write (which enters via volume_dsp_write → coeff_write →
    i2c_byte_tx, a path where BSR is set to 0 by volume_dsp_write)
    and verifies the flag is written to the correct address.

    If BSR were wrong, 0x07F would remain 0 and the retry mechanism
    would not trigger.
    """
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    harness = _new_main_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(harness)

        # Baseline volume — must succeed
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()
        assert _read_reg(harness._issue, _FLAGS_7F) == 0x00, (
            "dsp_fault_flags should be clean after successful volume"
        )

        # NACKs on DSP
        harness.set_i2c_fault("dsp34", address_nack_count=60000)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        flags = _read_reg(harness._issue, _FLAGS_7F)
        ackstat = bool(flags & (1 << _ACKSTAT_BIT))
        assert ackstat, (
            f"dsp_fault_flags.2 (ACKSTAT) not set after NACKed volume — "
            f"0x07F=0x{flags:02X}.  BSR may have been wrong during "
            f"i2c_byte_tx ACKSTAT write (BANKED access to 0x07F)."
        )

        # Also verify BSR is 0 at this point (main loop context)
        bsr = _read_reg(harness._issue, _BSR)
        assert bsr == 0, f"BSR={bsr}, expected 0 in main loop context"

    finally:
        harness.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_bsr_safety_no_ram_corruption_on_nack(
    dlcp_sim_backend: str,
) -> None:
    """Verify that NACKed I2C doesn't corrupt RAM at wrong bank addresses.

    If BSR != 0 when `bsf dsp_fault_flags, 2, BANKED` executes, the
    write goes to (BSR*256 + 0x7F) instead of 0x07F.  This test
    checks several bank-offset locations for unexpected writes.

    The V3.1 fix adds `movlb 0x0` before the ACKSTAT write to
    guarantee BSR=0 regardless of the caller's bank context.
    """
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)

            bank_addrs = [0x17F, 0x27F, 0x37F]
            before = {a: h.read_reg(a) for a in bank_addrs}

            h.set_i2c_fault("dsp34", address_nack_count=60000)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)

            after = {a: h.read_reg(a) for a in bank_addrs}
            corrupted = [
                (a, before[a], after[a])
                for a in bank_addrs
                if before[a] != after[a]
                and (after[a] & 0x04)
                and not (before[a] & 0x04)
            ]
            assert not corrupted, (
                f"[{backend}] RAM corrupted at wrong bank offsets "
                f"(BSR issue): "
                f"{[(hex(a), hex(b), hex(v)) for a, b, v in corrupted]}"
            )
        finally:
            h.close()


# ===================================================================
# (b) High: i2c_wait_bus_idle unbounded behavior under PEN fault
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_idle_wait_blocks_during_pen_fault_then_recovers(
    dlcp_sim_backend: str,
) -> None:
    """i2c_wait_bus_idle blocks while PEN is pending, then resumes.

    With stock unbounded i2c_wait_bus_idle, a stuck PEN causes the
    firmware to spin.  After clearing the MSSP STOP fault, PEN resolves
    and the firmware continues.  Verify the firmware is NOT crashed
    (active_flags still set) and processes new volume after recovery.
    """
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)

            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)

            h.clear_mssp_stop_faults()
            h.advance_tcy(15 * h.chunk_tcy)

            active = h.read_reg(_STATUS_5E) & 0x08
            assert active, (
                f"[{backend}] MAIN lost active state during PEN fault "
                f"-- hard_reset?"
            )

            snap = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            after = h.read_dsp_snapshot()
            diff = [
                (r, snap[r], after[r])
                for r in range(256)
                if snap[r] != after[r]
            ]
            assert len(diff) > 0, (
                f"[{backend}] DSP path broken after PEN fault resolved -- "
                f"i2c_wait_bus_idle may not have recovered"
            )
        finally:
            h.close()


# ===================================================================
# (c) Test gap: Degraded state during fault (tests 1 & 4)
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_dsp_path_recovers_after_mssp_stop_fault_cleared(
    dlcp_sim_backend: str,
) -> None:
    """After clearing an active MSSP STOP fault, the DSP path
    must recover and process subsequent volumes.

    Note on naming/scope: this test was originally named
    `test_dsp_path_degraded_during_mssp_stop_fault` with a
    docstring claiming it "addresses the review gap: tests 1 & 4
    assert recovery but not degradation".  In practice, asserting
    "DSP not changed during fault" is unsound on either backend:
    I²C bytes land in the slave's regs DURING the data phase
    of a transaction (STOP comes AFTER the bytes are accepted),
    and the STOP-fault only delays the trailing STOP -- the data
    bytes already reached the slave by then.  Probed both
    backends with a degradation-during-fault assertion: gpsim
    AND rust both show the volume cmd reaches the DSP during
    the fault, because the bytes lead the faulted STOP.

    Renamed and re-docstring'd so the test name matches what
    the assertion actually checks (recovery), not what the
    original docstring aspired to (degradation).  Two sibling
    tests in this file also drive the STOP-fault knobs:
      - test_idle_wait_blocks_during_pen_fault_then_recovers
      - test_pen_timeout_firmware_detects_before_sspcon2_poke

    NOTE: under a hypothetical no-op STOP-fault model, ALL
    three of these tests (including this one) would still
    pass for the wrong reason: a no-op fault lets the
    firmware complete the volume burst normally, so the
    recovery checks pass trivially and the
    pen_timeout test's `assert not fault6_seen` also passes
    because the firmware never enters the bounded-PEN-wait
    path that would set fault6.  Hence: the actual
    STOP-fault model fidelity is exercised by the rust
    `Mssp` unit tests
    (`pen_with_stop_fault_extends_deadline`,
    `pen_with_stop_fault_count_negative_one_runs_forever`,
    `clear_stop_faults_disables_extension`) at
    `crates/dlcp-sim/src/peripherals/mssp.rs`; the migrated
    integration tests here exercise the firmware's
    response-under-fault graceful behaviour, not the
    fidelity of the fault model itself.
    """
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            _boot_and_activate_h(h)

            # Baseline: volume reaches DSP.
            snap_pre = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            assert any(
                snap_pre[r] != h.read_dsp_reg(r) for r in range(256)
            ), f"[{backend}] baseline volume failed"

            # Activate fault, drive a volume cmd through the
            # fault window.  We don't assert anything about the
            # DSP state DURING the fault -- see test docstring.
            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
            h.advance_tcy(30 * h.chunk_tcy)

            # Clear fault, let firmware recover.
            h.clear_mssp_stop_faults()
            h.advance_tcy(15 * h.chunk_tcy)

            # After recovery: a new volume MUST reach the DSP.
            snap_post = h.read_dsp_snapshot()
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)
            after_post = h.read_dsp_snapshot()
            diff_post = [
                (r, snap_post[r], after_post[r])
                for r in range(256)
                if snap_post[r] != after_post[r]
            ]
            assert len(diff_post) > 0, (
                f"[{backend}] DSP path not recovered after MSSP STOP fault "
                f"cleared"
            )
        finally:
            h.close()


# ===================================================================
# (c) Test gap: BF/08 payload verification (test 3)
# ===================================================================


@pytest.mark.gpsim
@pytest.mark.slow
def test_bf08_payload_bytes_on_dsp_fault() -> None:
    """Verify MAIN sends correct BF/08/<status> triplet on DSP fault.

    The send_dsp_fault_status function sends a 3-byte frame:
      0xBF (route), 0x08 (cmd), <fault_byte> (bits 6+2 of 0x07F)

    After persistent NACKs exhaust retries, the fault byte should
    have bit 6 (DSP ping fault) set.  After recovery, the fault byte
    should be 0x00.

    Addresses review gap: test 3 checks CONTROL flag only, not payload.
    """
    _require_gpsim()
    _skip_missing(V31_MAIN_HEX)

    harness = _new_main_harness(V31_MAIN_HEX)
    try:
        _boot_and_activate(harness)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
        for _ in range(20):
            harness.step()

        # Inject persistent NACKs — trigger exhausted path
        harness.set_i2c_fault("dsp34", address_nack_count=60000)
        harness.inject_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        # Check MAIN TX log for BF/08 frames
        decoder = harness.decoder
        bf08_frames = [
            t for t in decoder.tx_frames
            if t.route == 0xBF and t.cmd == 0x08
        ]
        assert len(bf08_frames) > 0, (
            "No BF/08 frames found in MAIN TX — send_dsp_fault_status "
            "may not have executed"
        )

        # The last BF/08 frame during NACKs should have fault bits set
        last_fault_frame = bf08_frames[-1]
        fault_byte = last_fault_frame.data
        has_dsp_fault = bool(fault_byte & 0x40)  # bit 6
        assert has_dsp_fault, (
            f"BF/08 fault byte 0x{fault_byte:02X} missing bit 6 "
            f"(DSP ping fault) — dsp_ping may not have run or "
            f"send_dsp_fault_status has wrong payload"
        )

        # Clear NACKs and send successful volume
        harness.clear_i2c_faults("dsp34")
        harness.inject_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
        for _ in range(30):
            harness.step()

        # After success: new BF/08 frame should have fault byte = 0x00
        bf08_post = [
            t for t in decoder.tx_frames
            if t.route == 0xBF and t.cmd == 0x08
            and t.cycle > last_fault_frame.cycle
        ]
        if bf08_post:
            clear_byte = bf08_post[-1].data
            assert clear_byte == 0x00, (
                f"BF/08 clear frame has data=0x{clear_byte:02X}, "
                f"expected 0x00 (all faults cleared)"
            )

    finally:
        harness.close()


# ===================================================================
# (d) _force_clear_sspcon2: pre-assertion and proper scoping
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_pen_timeout_firmware_detects_before_sspcon2_poke(
    dlcp_sim_backend: str,
) -> None:
    """Canonical V3.1 should NOT latch a coeff-write PEN timeout in
    simulator.

    The canonical hardware-fixed V3.1 restores stock coeff-write
    START/STOP waits. That means a simulator's synthetic stuck-PEN
    model should not produce the old bounded-wait fault latch before
    the explicit `SSPCON2` clear workaround.
    """
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        # Fine probe granularity (50_000 Tcy/probe_step) to catch the
        # transient dsp_fault_flags state.
        h = _make_adapter(V31_MAIN_HEX, backend, chunk_tcy=50_000)
        try:
            h.advance_tcy(100 * h.chunk_tcy)
            h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
            h.advance_tcy(100 * h.chunk_tcy)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(200 * h.chunk_tcy)

            boot_complete = bool(h.read_reg(_FLAGS_7E) & 0x80)
            assert boot_complete, (
                f"[{backend}] boot_complete not set -- can't test PEN timeout"
            )

            h.set_mssp_stop_fault(
                stop_busy_cycles=5_000_000, stop_busy_count=-1
            )
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)

            fault6_seen = False
            for _ in range(200):
                h.probe_step()
                flags = h.read_reg(_FLAGS_7F)
                if flags & (1 << _DSP_FAULT_BIT):
                    fault6_seen = True
                    break

            assert not fault6_seen, (
                f"[{backend}] canonical V3.1 unexpectedly latched the old "
                f"bounded PEN timeout fault before the SSPCON2 clear "
                f"workaround"
            )

            h.clear_mssp_stop_faults()
            h.advance_tcy(100 * h.chunk_tcy)
        finally:
            h.close()


# ===================================================================
# Additional: Verify V3.1 specific features
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_boot_complete_flag_set_during_activation(
    dlcp_sim_backend: str,
) -> None:
    """Verify event_flags.7 (boot_complete) is set during activation.

    V3.1 sets boot_complete in the activation sequence (after
    adaptive_baud_select).  This gates the bounded PEN wait.
    """
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        h = _make_adapter(V31_MAIN_HEX, backend)
        try:
            h.advance_tcy(20 * h.chunk_tcy)
            h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
            h.advance_tcy(20 * h.chunk_tcy)

            boot_complete = bool(h.read_reg(_FLAGS_7E) & 0x80)
            assert boot_complete, (
                f"[{backend}] event_flags.7 (boot_complete) not set after "
                f"activation — bounded PEN wait will not be used"
            )
        finally:
            h.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_volume_dsp_write_retry_counter_increments(
    dlcp_sim_backend: str,
) -> None:
    """Verify the retry counter in dsp_fault_flags[5:3] increments on NACK.

    After injecting NACKs, volume_dsp_write should bump the retry
    counter.  This proves the NACK detection → retry path works.
    """
    _skip_missing(V31_MAIN_HEX)

    for backend in _enabled_backends(dlcp_sim_backend):
        # Fine probe granularity (50_000 Tcy/probe_step) to
        # catch transient retry-counter state.  Bulk advances
        # before the probe loop go through advance_tcy
        # (single step_tcy on rust, gpsim chunked internally).
        h = _make_adapter(V31_MAIN_HEX, backend, chunk_tcy=50_000)
        try:
            h.advance_tcy(100 * h.chunk_tcy)
            h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
            h.advance_tcy(100 * h.chunk_tcy)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
            h.advance_tcy(200 * h.chunk_tcy)

            h.set_i2c_fault("dsp34", address_nack_count=60000)
            h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)

            # Probe loop: per-iteration sample of the retry
            # counter at chunk_tcy granularity.  Both backends
            # need this granularity to catch the transient.
            max_retry_seen = 0
            for _ in range(200):
                h.probe_step()
                flags = h.read_reg(_FLAGS_7F)
                retry = (flags >> 3) & 0x07
                if retry > max_retry_seen:
                    max_retry_seen = retry

            assert max_retry_seen > 0, (
                f"[{backend}] Retry counter never incremented — "
                f"volume_dsp_write NACK path may not be executing "
                f"(BSR issue? ACKSTAT not set?)"
            )
        finally:
            h.close()
