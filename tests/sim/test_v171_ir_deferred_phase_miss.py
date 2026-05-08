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
half-bit), the decoder aborts at line 556 and returns 0xFF (and
0xFF in (Common_RAM+13)) -- the IR press is silently dropped.  The
foreground service clears IR_ARMED after the call (asm:2626), but
the V1.71 inline dispatch RE-ARMS it (asm:3157, 3188, 3207, 3227)
after the cmd-0xFF lookup falls through, so IR_ARMED is not a
durable signal of "abort happened" -- only cmd/addr=0xFF are.

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

This file pins the bug deterministically by directly injecting
``v171_ir_decode_pending = 0xFF`` (equivalent to "ISR latched
pending a moment ago while RB5 was LOW") and leaving RB5 HIGH at
foreground entry, then asserting the decoder aborts with
``ir_decoded_cmd = 0xFF`` (the abort path's signature value).  On
real V1.71 hardware, this is the failure mode reported by the user
(2026-05-09): foreground was busy when RBIF fired, by the time the
deferred service runs the LOW window has elapsed.

We do NOT assert on IR_ARMED because the V1.71 inline dispatch
re-arms it after every foreground decode pass (asm:3157, 3188,
3207, 3227) -- so IR_ARMED is not a stable signal of "abort
happened".  The cmd/addr=0xFF outputs are the durable signature of
the abort path (asm:670-672 ``movlw 0xFF / movwf (Common_RAM+12) /
movwf (Common_RAM+13)``).

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

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
)
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


def _build_warmed_chain(hex_path: Path):  # type: ignore[no-untyped-def]
    chain = RustChain.from_v17_chain(str(hex_path))
    chain.warmup(25_000_000)
    chain.pause_heartbeat()
    for _ in range(40):
        chain.step()
    # RB5 idle HIGH (TSOP convention).
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        chain.step()
    return chain


def _run_phase_miss_setup(chain) -> dict:  # type: ignore[no-untyped-def]
    """Shared phase-miss reproducer setup (used by V1.71 and V1.6b
    variants).

    On V1.71: pokes the deferred-decode pending byte at 0x0AA, which
    the foreground service ``v171_service_pending_ir_decode`` reads
    on the next display_loop_iteration pass and uses to invoke
    ``ir_rc5_decode``.  With RB5 HIGH at decoder entry, the decoder
    aborts to 0xFF.

    On V1.6b: pokes RAM 0x0AA which is unrelated to IR (the V1.6b
    decoder is in-ISR, not deferred).  Nothing reads 0x0AA during
    foreground; ``ir_decoded_cmd``/``ir_decoded_addr`` stay at the
    pre-cleared 0x00.

    Returns a dict of post-step register values for the caller to
    assert on.
    """
    pre_flags = chain.read_reg(_CONTROL_FLAGS)
    pre_pending = chain.read_reg(_V171_IR_DECODE_PENDING)

    # Force IR_ARMED so V1.71's foreground service calls the decoder.
    # On V1.6b this is harmless -- the IR_ARMED bit gates the in-ISR
    # decoder entry, which only fires on RB5 transitions; we don't
    # drive any RB5 transition here, so V1.6b's decoder never runs.
    chain.write_reg(_CONTROL_FLAGS, pre_flags | _IR_ARMED_BIT)
    chain.write_reg(_IR_DECODED_CMD, 0x00)
    chain.write_reg(_IR_DECODED_ADDR, 0x00)
    chain.write_reg(_V171_IR_DECODE_PENDING, 0xFF)

    rb5_at_inject = chain.read_reg(0xF81) & 0x20  # PORTB.RB5
    assert rb5_at_inject != 0, (
        f"RB5 must be HIGH for this test; PORTB=0x{chain.read_reg(0xF81):02X}"
    )

    chain.step_ticks(48_000 * 5)  # 5 ms sim time

    return {
        "pre_flags": pre_flags,
        "pre_pending": pre_pending,
        "post_cmd": chain.read_reg(_IR_DECODED_CMD),
        "post_addr": chain.read_reg(_IR_DECODED_ADDR),
        "post_pending": chain.read_reg(_V171_IR_DECODE_PENDING),
        "post_flags": chain.read_reg(_CONTROL_FLAGS),
    }


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
    result = _run_phase_miss_setup(chain)

    print(
        f"\nV1.71 deferred-decode phase-miss outcome:\n"
        f"  pre:  pending=0x{result['pre_pending']:02X} "
        f"flags=0x{result['pre_flags']:02X}\n"
        f"  inject: pending=0xFF, IR_ARMED set, RB5=HIGH "
        f"(foreground will reach decoder with RB5 already HIGH)\n"
        f"  post: cmd=0x{result['post_cmd']:02X} "
        f"addr=0x{result['post_addr']:02X} "
        f"pending=0x{result['post_pending']:02X} "
        f"flags=0x{result['post_flags']:02X}\n"
        f"  expected (decoder aborted -> bug present):\n"
        f"    cmd=0xFF, addr=0xFF, pending=0x00\n"
        f"    (IR_ARMED is re-armed by inline dispatch -- not asserted)\n"
    )

    # Bug-present assertions.  Currently PASSING (bug is there).
    # When firmware is fixed (decoder no longer aborts), post_cmd
    # will be the actual decoded value or stay at the pre-clear 0x00,
    # this assertion will FAIL, and the failure will flag the fix.
    # The test should then be deleted or rewritten to pin the new
    # (correct) behavior.
    assert result["post_cmd"] == 0xFF, (
        f"V1.71 deferred decode SHOULD have aborted to 0xFF (bug "
        f"present); got cmd=0x{result['post_cmd']:02X}.  If this "
        f"assertion failed, the firmware fix is in -- delete or "
        f"rewrite this test to pin the new behavior."
    )
    assert result["post_addr"] == 0xFF, (
        f"V1.71 deferred decode SHOULD have aborted (addr=0xFF); "
        f"got addr=0x{result['post_addr']:02X}."
    )
    # NB: IR_ARMED gets RE-ARMED by the V1.71 inline dispatch at the
    # end of control_core_service_0DCE (asm:3157, 3188, 3207, 3227)
    # AFTER the cmd-0xFF lookup falls through.  So IR_ARMED is not a
    # reliable signal of "abort happened" -- cmd/addr=0xFF are.  We
    # don't assert on IR_ARMED here.
    assert result["post_pending"] == 0, (
        f"V1.71 deferred service SHOULD have cleared pending after "
        f"calling ir_rc5_decode; got pending="
        f"0x{result['post_pending']:02X}.  (If pending stays 0xFF, "
        f"the foreground service didn't run."
    )


@pytest.mark.dual_supported
def test_v16b_stock_in_isr_decode_immune_to_phase_miss() -> None:
    """V1.6b sister test: prove the phase-miss bug is V1.71-specific.

    V1.6b stock has the in-ISR decoder (the V1.7 / pre-bc61c70 path):
    ``ir_rc5_decode`` is called directly from the ISR at the RB5
    falling edge, NOT deferred to a foreground service.  Crucially,
    V1.6b has NO equivalent of ``v171_ir_decode_pending`` at 0x0AA --
    that RAM byte is unrelated to IR on V1.6b.

    Apply the SAME phase-miss setup the V1.71 test uses (poke
    pending=0xFF, RB5 HIGH, step 5 ms) and verify the decoder did
    NOT run -- ``ir_decoded_cmd`` stays at the pre-cleared 0x00,
    NOT 0xFF.

    This is the regression-detector pair to the V1.71 test:

      * V1.71 test passes -> deferred-decode bug present.
      * V1.6b test passes -> in-ISR path immune.
      * If V1.71 test starts failing -> firmware fix detected.
      * If V1.6b test starts failing -> something changed in the
        V1.6b stock hex (shouldn't happen; it's stock).

    Together these tests pin the gap: the bug is introduced by
    V1.71's deferred-decode design, NOT by anything in
    ``ir_rc5_decode`` itself or the V1.6b/V1.7 hardware
    interaction.
    """
    _require_rust()
    if not STOCK_CONTROL_HEX_V16B.is_file():
        pytest.skip(f"missing V1.6b stock hex: {STOCK_CONTROL_HEX_V16B}")

    chain = _build_warmed_chain(STOCK_CONTROL_HEX_V16B)
    result = _run_phase_miss_setup(chain)

    print(
        f"\nV1.6b stock phase-miss outcome (sister to V1.71 test):\n"
        f"  pre:  pending=0x{result['pre_pending']:02X} "
        f"flags=0x{result['pre_flags']:02X}\n"
        f"  inject: same as V1.71 test (pending=0xFF, IR_ARMED set, "
        f"RB5=HIGH)\n"
        f"  post: cmd=0x{result['post_cmd']:02X} "
        f"addr=0x{result['post_addr']:02X} "
        f"pending=0x{result['post_pending']:02X} "
        f"flags=0x{result['post_flags']:02X}\n"
        f"  expected (decoder did NOT run -> no bug):\n"
        f"    cmd=0x00 (stayed at pre-cleared value)\n"
        f"    addr=0x00\n"
        f"    pending=0xFF (V1.6b doesn't consume 0x0AA)\n"
    )

    # No-bug assertions: decoder did NOT run, did NOT abort.
    # cmd/addr stay at the pre-cleared 0x00.
    assert result["post_cmd"] != 0xFF, (
        f"V1.6b stock unexpectedly aborted -- got cmd=0xFF.  V1.6b "
        f"has no deferred-decode mechanism so the foreground "
        f"shouldn't be invoking ir_rc5_decode.  If this assertion "
        f"failed, something is fundamentally different about the "
        f"V1.6b setup vs expectation -- investigate."
    )
    assert result["post_addr"] != 0xFF, (
        f"V1.6b stock unexpectedly aborted -- got addr=0xFF."
    )
    assert result["post_cmd"] == 0x00, (
        f"V1.6b stock should leave ir_decoded_cmd at the pre-cleared "
        f"0x00 (no decoder ran).  Got cmd=0x{result['post_cmd']:02X}."
    )
    assert result["post_addr"] == 0x00, (
        f"V1.6b stock should leave ir_decoded_addr at the pre-cleared "
        f"0x00.  Got addr=0x{result['post_addr']:02X}."
    )
    # V1.6b doesn't read or clear 0x0AA -- it stays at our injected 0xFF.
    assert result["post_pending"] == 0xFF, (
        f"V1.6b stock should NOT touch RAM 0x0AA (no foreground "
        f"service for it).  Got pending=0x{result['post_pending']:02X}; "
        f"if cleared, V1.6b unexpectedly has a service for that RAM "
        f"byte -- investigate."
    )
