"""V1.71 deferred-IR-decode phase-miss reproducer.

Hypothesis (task #151): bc61c70 deferred ``ir_rc5_decode`` from the
ISR (V1.7 / V1.6b stock) to the foreground ``display_loop_iteration``
loop (V1.71).  This breaks IR on real hardware because the decoder
requires ``RB5 = LOW`` at entry (asm:556 ``btfsc PORTB, RB5, A`` →
abort to 0xFF return path).

In V1.7 the decoder runs IN-ISR, immediately at the falling edge that
latched RBIF -- RB5 is guaranteed LOW.  In V1.71 the ISR only sets
``v171_ir_decode_pending``; the foreground enters the decoder at some
later time depending on:

  * Where in ``display_loop_iteration`` the foreground was when RBIF
    fired.
  * Whether any blocking call (``eeprom_write_byte`` ~3.3 ms,
    ``control_core_service_0990`` 9× EEPROM writes ~30 ms,
    ``ir_rc5_decode`` body itself ~7-10 ms) is in flight.

If the foreground reaches ``ir_rc5_decode`` AFTER the falling-edge's
LOW half-bit window has ended (i.e. RB5 has flipped HIGH for the next
half-bit), the decoder aborts at line 556, returns 0xFF, and clears
IR_ARMED.

The existing ``test_v171_ir_rc5_pulse_train.py`` does NOT catch this
because:

  * The test driver's ``set_control_pin + step_ticks(889 µs)`` keeps
    RB5 LOW for the full half-bit window.
  * No ``control_core_service_0990`` (~30 ms EEPROM block) fires
    during the ~25 ms test window because ``idle_timeout_counter``
    (0x9D/0x9E) hasn't incremented to its trigger value (0xEA60)
    yet -- it takes ~60 k iterations from boot, far longer than
    the test runs.
  * Foreground reaches ``v171_service_pending_ir_decode`` within
    a few µs of the falling edge (no blocking call interposed),
    well within the 889 µs LOW window.

This file pins the bug deterministically: we manually set RB5 LOW
just enough for the ISR to latch pending=0xFF, then flip RB5 HIGH
BEFORE foreground reaches the decoder, and assert the decoder aborts
with ``ir_decoded_cmd = 0xFF`` and IR_ARMED cleared.  On real V1.71
hardware, this is the failure mode reported by the user (2026-05-09).

The fix path (for a separate commit) is one of:

  * Revert the deferral and accept the 7-10 ms ISR stall (Bug C3).
  * Rewrite ``ir_rc5_decode`` as a non-blocking sample-driven state
    machine driven by a fast tick (Timer3 ISR samples at 889 µs
    half-bit boundaries, decoder accumulates bits across samples).
  * Inline the entry-LOW check into the ISR pending-set:  only
    latch pending if RB5 is currently LOW (matches the V1.7
    decoder's implicit timing).  Foreground entry would still be
    later but the entry-LOW check would have already passed.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERROR = exc


# RAM addresses (cross-checked vs V1.71 ram_inc / asm equates).
_IR_DECODED_CMD = 0x01D
_IR_DECODED_ADDR = 0x01E
_CONTROL_FLAGS = 0x01F  # bit 0 = IR_ARMED
_IR_ARMED_BIT = 0x01
_V171_IR_DECODE_PENDING = 0x0AA  # banked


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_ir_deferred_phase_miss")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _build_warmed_chain(v171_hex: Path):  # type: ignore[no-untyped-def]
    chain = RustChain.from_v17_chain(str(v171_hex))
    chain.warmup(25_000_000)
    chain.pause_heartbeat()
    for _ in range(40):
        chain.step()
    # RB5 idle HIGH (TSOP convention).
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        chain.step()
    return chain


@pytest.mark.dual_supported
def test_v171_deferred_decode_aborts_when_foreground_misses_low_window(v171_hex: Path) -> None:
    """Deterministic phase-miss reproducer.

    Pins the V1.71 deferred-decode BUG (introduced bc61c70): when
    foreground reaches ``ir_rc5_decode`` AFTER the RB5-LOW half-bit
    window has elapsed, the decoder aborts to 0xFF and the IR press
    is silently dropped.  This is the user-reported real-HW failure
    mode (2026-05-09).

    Sequence:
      1. Build chain at idle (RB5 HIGH).
      2. Force IR_ARMED set + clear ``ir_decoded_cmd``/``ir_decoded_addr``.
      3. Manually inject ``v171_ir_decode_pending = 0xFF`` (bypasses
         the ISR-latch question; equivalent to "ISR ran a moment ago
         and latched pending while RB5 was LOW").
      4. Leave RB5 HIGH (simulating foreground entry occurring AFTER
         the LOW half-bit window has ended -- the realistic
         real-HW timing when foreground was busy with eeprom_write_byte
         / LCD update / etc).
      5. Step ~5 ms sim time so foreground enters
         ``v171_service_pending_ir_decode`` -> ``ir_rc5_decode``.
      6. Assert: decoder aborted (cmd=0xFF, addr=0xFF, pending cleared).

    **This test PASSES today (bug present).  When the firmware is
    fixed -- by reverting bc61c70's deferral, by rewriting the
    decoder as non-blocking, or by gating pending-latch on RB5=LOW
    in the ISR -- this test will FAIL.  That failure flags the bug
    as fixed and the test should be either deleted or rewritten to
    pin the new (correct) behavior.**
    """
    _require_rust()
    chain = _build_warmed_chain(v171_hex)

    # Pre-snapshot: chain stable, RB5 HIGH (idle).  IR_ARMED state
    # depends on the boot path; we explicitly arm it to ensure the
    # foreground service will call the decoder.
    pre_pending = chain.read_reg(_V171_IR_DECODE_PENDING)
    pre_flags = chain.read_reg(_CONTROL_FLAGS)

    # Force IR_ARMED set so v171_service_pending_ir_decode actually
    # calls ir_rc5_decode (not the drop path).
    chain.write_reg(_CONTROL_FLAGS, pre_flags | _IR_ARMED_BIT)
    # Pre-clear the decoded-result bytes so we can detect the abort
    # (which writes 0xFF) vs the initial state (typically 0x00).
    chain.write_reg(_IR_DECODED_CMD, 0x00)
    chain.write_reg(_IR_DECODED_ADDR, 0x00)
    # Bypass the ISR-latch question: directly set pending=0xFF as if
    # the ISR had latched it.  This is the firmware-visible state
    # that triggers v171_service_pending_ir_decode to call
    # ir_rc5_decode on the next foreground pass.
    chain.write_reg(_V171_IR_DECODE_PENDING, 0xFF)

    # RB5 is HIGH at this point (idle).  This simulates the "real-HW
    # busy foreground" scenario: ISR latched pending while RB5 was
    # LOW (during a real falling edge), but by the time foreground
    # reaches the decoder, RB5 has flipped HIGH (next half-bit).
    # With RB5 HIGH at decoder entry, ir_rc5_decode aborts at the
    # entry-LOW check (asm:556).
    rb5_at_inject = chain.read_reg(0xF81) & 0x20  # PORTB.RB5
    assert rb5_at_inject != 0, (
        f"RB5 must be HIGH for this test; PORTB=0x{chain.read_reg(0xF81):02X}"
    )

    # Step long enough for foreground to enter the decoder.
    # ~5 ms sim time should be enough for foreground to complete
    # any in-flight call + reach v171_service_pending_ir_decode +
    # call ir_rc5_decode.  ir_rc5_decode's first instruction after
    # setup is the entry-LOW check at asm:556 -- with RB5 HIGH the
    # decoder branches to the abort path at flow_ir_rc5_decode_02E4
    # (asm:668-674) which writes 0xFF to ir_decoded_cmd and
    # ir_decoded_addr.  The foreground service then writes 0xFF
    # into ir_decoded_cmd from W and clears IR_ARMED (asm:2625-2626).
    chain.step_ticks(48_000 * 5)  # 5 ms sim time

    # Assert the decoder aborted.
    post_cmd = chain.read_reg(_IR_DECODED_CMD)
    post_addr = chain.read_reg(_IR_DECODED_ADDR)
    post_pending = chain.read_reg(_V171_IR_DECODE_PENDING)
    post_flags = chain.read_reg(_CONTROL_FLAGS)

    print(
        f"\nDeferred-decode phase-miss outcome:\n"
        f"  pre:  pending=0x{pre_pending:02X} flags=0x{pre_flags:02X}\n"
        f"  inject: pending=0xFF, IR_ARMED set, RB5=HIGH "
        f"(foreground will reach decoder with RB5 already HIGH)\n"
        f"  post: cmd=0x{post_cmd:02X} addr=0x{post_addr:02X} "
        f"pending=0x{post_pending:02X} flags=0x{post_flags:02X}\n"
        f"  expected (decoder aborted -> bug present):\n"
        f"    cmd=0xFF, addr=0xFF, pending=0x00, IR_ARMED cleared\n"
    )

    # The "bug present" assertions: decoder aborted, ir_decoded_cmd=0xFF.
    # Strict-xfail: when the firmware is fixed (decoder no longer aborts),
    # post_cmd would be the actual decoded value or stay 0x00, and this
    # assertion would fail -> xfail STRICT means pytest reports a test
    # regression (fix detected).
    assert post_cmd == 0xFF, (
        f"V1.71 deferred decode SHOULD have aborted to 0xFF (bug "
        f"present); got cmd=0x{post_cmd:02X}.  If this assertion "
        f"failed, the firmware fix is in -- flip the @xfail decorator "
        f"off."
    )
    assert post_addr == 0xFF, (
        f"V1.71 deferred decode SHOULD have aborted (addr=0xFF); "
        f"got addr=0x{post_addr:02X}."
    )
    # NB: IR_ARMED gets RE-ARMED by the V1.71 inline dispatch at the
    # end of control_core_service_0DCE (asm:3157, 3188, 3207, 3227)
    # AFTER the cmd-0xFF lookup falls through.  So IR_ARMED is not a
    # reliable signal of "abort happened" -- cmd/addr=0xFF are.  We
    # don't assert on IR_ARMED here.
    assert post_pending == 0, (
        f"V1.71 deferred service SHOULD have cleared pending after "
        f"calling ir_rc5_decode; got pending=0x{post_pending:02X}.  "
        f"(If pending stays 0xFF, the foreground service didn't run."
    )
