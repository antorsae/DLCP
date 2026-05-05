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

from dlcp_fw.paths import V31_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

# --- PIC18F2455 SFR addresses (absolute) ---
_BSR = 0xFE0

# --- GPR addresses (bank 0, read via read_reg absolute) ---
_FLAGS_7E = 0x07E
_FLAGS_7F = 0x07F
_STATUS_5E = 0x05E

_DSP_FAULT_BIT = 6  # 0x07F.bit6
_ACKSTAT_BIT = 2    # 0x07F.bit2


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


class _RustMainOnlyAdapter:
    """rust-side MAIN-only adapter.  ``chunk_tcy`` is only used by
    ``probe_step`` (per-call advancement for tests that need to catch
    transient state); ``advance_tcy(N)`` advances the full ``N``
    MAIN-Tcy in a single ``step_tcy`` call -- the rust universal-clock
    scheduler runs the core in lock-step at instruction granularity."""

    def __init__(self, main_hex: Path, *, chunk_tcy: int = 200_000) -> None:
        self._c = RustChain.from_v3x_main_only(str(main_hex))
        self._chunk_tcy = chunk_tcy

    def advance_tcy(self, tcy: int) -> None:
        self._c.step_tcy(tcy)

    def probe_step(self) -> None:
        """Advance exactly one chunk so the caller can sample
        transient firmware state."""
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


def _make_adapter(
    main_hex: Path, *, chunk_tcy: int = 200_000,
) -> _RustMainOnlyAdapter:
    _require_rust()
    return _RustMainOnlyAdapter(main_hex, chunk_tcy=chunk_tcy)


def _boot_and_activate_h(h: _RustMainOnlyAdapter) -> None:
    h.advance_tcy(20 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert h.read_reg(_STATUS_5E) & 0x08, "MAIN not active"


# ===================================================================
# (a) Critical: BSR safety — i2c_byte_tx ACKSTAT write to 0x07F
# ===================================================================


@pytest.mark.dual_supported
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
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    _boot_and_activate_h(h)

    # Baseline volume — must succeed.
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert h.read_reg(_FLAGS_7F) == 0x00, (
        f"dsp_fault_flags should be clean after successful volume "
        f"(0x07F=0x{h.read_reg(_FLAGS_7F):02X})"
    )

    # NACKs on DSP.
    h.set_i2c_fault("dsp34", address_nack_count=60000)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
    h.advance_tcy(30 * h.chunk_tcy)

    flags = h.read_reg(_FLAGS_7F)
    ackstat = bool(flags & (1 << _ACKSTAT_BIT))
    assert ackstat, (
        f"dsp_fault_flags.2 (ACKSTAT) not set after NACKed volume -- "
        f"0x07F=0x{flags:02X}.  BSR may have been wrong during "
        f"i2c_byte_tx ACKSTAT write (BANKED access to 0x07F)."
    )

    # Also verify BSR is 0 at this point (main loop context).
    bsr = h.read_reg(_BSR)
    assert bsr == 0, f"BSR={bsr}, expected 0 in main loop context"


@pytest.mark.dual_supported
@pytest.mark.slow
def test_bsr_safety_no_ram_corruption_on_nack() -> None:
    """Verify that NACKed I2C doesn't corrupt RAM at wrong bank addresses.

    If BSR != 0 when `bsf dsp_fault_flags, 2, BANKED` executes, the
    write goes to (BSR*256 + 0x7F) instead of 0x07F.  This test
    checks several bank-offset locations for unexpected writes.

    The V3.1 fix adds `movlb 0x0` before the ACKSTAT write to
    guarantee BSR=0 regardless of the caller's bank context.
    """
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
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
        f"RAM corrupted at wrong bank offsets (BSR issue): "
        f"{[(hex(a), hex(b), hex(v)) for a, b, v in corrupted]}"
    )


# ===================================================================
# (b) High: i2c_wait_bus_idle unbounded behavior under PEN fault
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_idle_wait_blocks_during_pen_fault_then_recovers() -> None:
    """i2c_wait_bus_idle blocks while PEN is pending, then resumes.

    With stock unbounded i2c_wait_bus_idle, a stuck PEN causes the
    firmware to spin.  After clearing the MSSP STOP fault, PEN resolves
    and the firmware continues.  Verify the firmware is NOT crashed
    (active_flags still set) and processes new volume after recovery.
    """
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    _boot_and_activate_h(h)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)

    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
    h.advance_tcy(30 * h.chunk_tcy)

    h.clear_mssp_stop_faults()
    h.advance_tcy(15 * h.chunk_tcy)

    active = h.read_reg(_STATUS_5E) & 0x08
    assert active, "MAIN lost active state during PEN fault -- hard_reset?"

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
        "DSP path broken after PEN fault resolved -- "
        "i2c_wait_bus_idle may not have recovered"
    )


# ===================================================================
# (c) Test gap: Degraded state during fault (tests 1 & 4)
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_dsp_path_recovers_after_mssp_stop_fault_cleared() -> None:
    """After clearing an active MSSP STOP fault, the DSP path
    must recover and process subsequent volumes.

    Asserting "DSP not changed during fault" is unsound: I²C bytes
    land in the slave's regs DURING the data phase of a transaction
    (STOP comes AFTER the bytes are accepted), and the STOP-fault
    only delays the trailing STOP -- the data bytes already reached
    the slave by then.  This test asserts the recovery invariant
    only.

    The actual STOP-fault model fidelity is exercised by the rust
    `Mssp` unit tests (`pen_with_stop_fault_extends_deadline`,
    `pen_with_stop_fault_count_negative_one_runs_forever`,
    `clear_stop_faults_disables_extension`) at
    `crates/dlcp-sim/src/peripherals/mssp.rs`; this integration
    test exercises the firmware's response-under-fault graceful
    behaviour, not the fidelity of the fault model itself.
    """
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    _boot_and_activate_h(h)

    # Baseline: volume reaches DSP.
    snap_pre = h.read_dsp_snapshot()
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)
    assert any(
        snap_pre[r] != h.read_dsp_reg(r) for r in range(256)
    ), "baseline volume failed"

    # Activate fault, drive a volume cmd through the fault window.
    # We don't assert anything about the DSP state DURING the fault
    # -- see test docstring.
    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
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
        "DSP path not recovered after MSSP STOP fault cleared"
    )


# ===================================================================
# (c) Test gap: BF/08 payload verification (test 3)
# ===================================================================


def _bf08_frames_from_bytes(raw: list[int]) -> list[int]:
    """Scan a flat TX byte stream for 3-byte BF/08/<data> frames and
    return their data bytes in order.  Frame boundaries are a strict
    BF/08 start-of-frame search; non-frame bytes are skipped without
    interrupting subsequent frame detection."""
    out: list[int] = []
    i = 0
    n = len(raw)
    while i + 2 < n:
        if raw[i] == 0xBF and raw[i + 1] == 0x08:
            out.append(raw[i + 2] & 0xFF)
            i += 3
        else:
            i += 1
    return out


@pytest.mark.dual_supported
@pytest.mark.slow
def test_bf08_payload_bytes_on_dsp_fault() -> None:
    """Verify MAIN sends correct BF/08/<status> triplet on DSP fault.

    The send_dsp_fault_status function sends a 3-byte frame:
      0xBF (route), 0x08 (cmd), <fault_byte> (bits 6+2 of 0x07F)

    After persistent NACKs exhaust retries, the fault byte should
    have bit 6 (DSP ping fault) set.  After recovery, the fault byte
    should be 0x00.
    """
    _skip_missing(V31_MAIN_HEX)
    _require_rust()
    chain = RustChain.from_v3x_main_only(str(V31_MAIN_HEX))
    chain.step_tcy(4_000_000)
    chain.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    assert chain.read_reg(_STATUS_5E) & 0x08, "MAIN not active"
    chain.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    chain.step_tcy(4_000_000)
    chain.mark_tx_capture_point()
    chain.set_i2c_fault("dsp34", address_nack_count=60000)
    chain.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)
    chain.step_tcy(6_000_000)
    nack_bytes = chain.tx_record_since_last_capture()
    nack_frames = _bf08_frames_from_bytes(nack_bytes)

    chain.mark_tx_capture_point()
    chain.clear_i2c_faults("dsp34")
    chain.inject_main_frames_fifo([[0xB0, 0x07, 0x40]], fifo_limit=47)
    chain.step_tcy(6_000_000)
    post_bytes = chain.tx_record_since_last_capture()
    post_frames = _bf08_frames_from_bytes(post_bytes)

    assert len(nack_frames) > 0, (
        "No BF/08 frames found in MAIN TX during NACKs — "
        "send_dsp_fault_status may not have executed"
    )
    last_fault_byte = nack_frames[-1]
    has_dsp_fault = bool(last_fault_byte & 0x40)
    assert has_dsp_fault, (
        f"BF/08 fault byte 0x{last_fault_byte:02X} missing bit 6 (DSP "
        f"ping fault) — dsp_ping may not have run or "
        f"send_dsp_fault_status has wrong payload"
    )
    if post_frames:
        clear_byte = post_frames[-1]
        assert clear_byte == 0x00, (
            f"BF/08 clear frame has data=0x{clear_byte:02X}, "
            f"expected 0x00 (all faults cleared)"
        )


# ===================================================================
# (d) _force_clear_sspcon2: pre-assertion and proper scoping
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_pen_timeout_firmware_detects_before_sspcon2_poke() -> None:
    """Canonical V3.1 should NOT latch a coeff-write PEN timeout in
    simulator.

    The canonical hardware-fixed V3.1 restores stock coeff-write
    START/STOP waits. That means a simulator's synthetic stuck-PEN
    model should not produce the old bounded-wait fault latch before
    the explicit `SSPCON2` clear workaround.
    """
    _skip_missing(V31_MAIN_HEX)

    # Fine probe granularity (50_000 Tcy/probe_step) to catch the
    # transient dsp_fault_flags state.
    h = _make_adapter(V31_MAIN_HEX, chunk_tcy=50_000)
    h.advance_tcy(100 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(100 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(200 * h.chunk_tcy)

    boot_complete = bool(h.read_reg(_FLAGS_7E) & 0x80)
    assert boot_complete, "boot_complete not set -- can't test PEN timeout"

    h.set_mssp_stop_fault(stop_busy_cycles=5_000_000, stop_busy_count=-1)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)

    fault6_seen = False
    for _ in range(200):
        h.probe_step()
        flags = h.read_reg(_FLAGS_7F)
        if flags & (1 << _DSP_FAULT_BIT):
            fault6_seen = True
            break

    assert not fault6_seen, (
        "canonical V3.1 unexpectedly latched the old bounded PEN "
        "timeout fault before the SSPCON2 clear workaround"
    )

    h.clear_mssp_stop_faults()
    h.advance_tcy(100 * h.chunk_tcy)


# ===================================================================
# Additional: Verify V3.1 specific features
# ===================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_boot_complete_flag_set_during_activation() -> None:
    """Verify event_flags.7 (boot_complete) is set during activation.

    V3.1 sets boot_complete in the activation sequence (after
    adaptive_baud_select).  This gates the bounded PEN wait.
    """
    _skip_missing(V31_MAIN_HEX)

    h = _make_adapter(V31_MAIN_HEX)
    h.advance_tcy(20 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(20 * h.chunk_tcy)

    boot_complete = bool(h.read_reg(_FLAGS_7E) & 0x80)
    assert boot_complete, (
        "event_flags.7 (boot_complete) not set after activation — "
        "bounded PEN wait will not be used"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_volume_dsp_write_retry_counter_increments() -> None:
    """Verify the retry counter in dsp_fault_flags[5:3] increments on NACK.

    After injecting NACKs, volume_dsp_write should bump the retry
    counter.  This proves the NACK detection → retry path works.
    """
    _skip_missing(V31_MAIN_HEX)

    # Fine probe granularity (50_000 Tcy/probe_step) to catch
    # transient retry-counter state.
    h = _make_adapter(V31_MAIN_HEX, chunk_tcy=50_000)
    h.advance_tcy(100 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x03, 0x01]], fifo_limit=47)
    h.advance_tcy(100 * h.chunk_tcy)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x50]], fifo_limit=47)
    h.advance_tcy(200 * h.chunk_tcy)

    h.set_i2c_fault("dsp34", address_nack_count=60000)
    h.inject_main_frames_fifo([[0xB0, 0x07, 0x30]], fifo_limit=47)

    # Probe loop: per-iteration sample of the retry counter at
    # chunk_tcy granularity.
    max_retry_seen = 0
    for _ in range(200):
        h.probe_step()
        flags = h.read_reg(_FLAGS_7F)
        retry = (flags >> 3) & 0x07
        if retry > max_retry_seen:
            max_retry_seen = retry

    assert max_retry_seen > 0, (
        "Retry counter never incremented — volume_dsp_write NACK "
        "path may not be executing (BSR issue? ACKSTAT not set?)"
    )
