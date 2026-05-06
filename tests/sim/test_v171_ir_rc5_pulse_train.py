"""V1.71 IR RC5 pulse-train regression test.

The existing IR sim tests (``test_v171_ir_endpoints.py``,
``test_v171_preset_inline.py``) inject the decoded result directly
via ``inject_decoded_ir_event`` -- a RAM poke that writes to
``ir_decoded_cmd`` (0x01D), ``ir_decoded_addr`` (0x01E), and
clears ``control_flags.IR_ARMED`` (0x01F.bit0).  That bypasses
``ir_rc5_decode`` (asm:546+) entirely.

This test instead drives a real Manchester-encoded RC5 pulse
train at CONTROL's RB5 input pin with canonical 889 µs half-bit
timing, then asserts that:

  1. The ISR latches the IR event (``v171_ir_decode_pending``
     bit set, OR ``IR_ARMED`` cleared after foreground service
     drains the pending flag).
  2. The foreground decoder runs ``ir_rc5_decode`` and writes
     the expected ``cmd`` value into ``ir_decoded_cmd`` (0x01D)
     and ``addr`` into ``ir_decoded_addr`` (0x01E).
  3. The V1.71 inline IR dispatch fires (cmd=0x3A → standby
     frame ``[B0, 03, 00]`` appears in CONTROL TX).

Commit ``bc61c70`` ("Harden V1.71 link handling") replaced the
in-ISR ``rcall ir_rc5_decode`` with a deferred foreground decode
(``setf v171_ir_decode_pending`` in ISR, then
``v171_service_pending_ir_decode`` from
``display_loop_iteration`` after ``button_scan_debounce``).  The
RC5 decoder is a bit-bang RB5 poll with ~889 µs half-bit timing
that assumes it starts near the falling edge.  Foreground
service runs significantly later than the ISR latch, so the
decoder's bit-bang sample timing is off and it misreads almost
every press on real hardware.

This test exposes that regression at the simulator level.

If the test FAILS (decoder misreads the cmd / dispatch never
fires), the bug is reproduced.  The fix path is to revert the
deferral so ``ir_rc5_decode`` runs from the ISR (the V1.7 stock
pattern that worked reliably).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


# RC5 protocol:
#
# - 14-bit frame: S1 (start, '1') + S2 (start, '1') + T (toggle) +
#   5-bit address + 6-bit command.
# - Manchester encoding at the MCU pin: '1' = LOW-then-HIGH
#   (carrier first half, idle second half), '0' = HIGH-then-LOW.
#   Idle = HIGH at MCU pin (TSOP IR receivers output HIGH for "no
#   carrier", LOW when the 36 kHz carrier is on -- so a logical
#   '1' active in the first half-bit drives the pin LOW).
# - Half-bit time: 889 µs (full bit = 1.778 ms).
# - Frame total: 14 × 1.778 ms = 24.9 ms; inter-frame gap >= 89 ms.
#
# At the MCU pin (RB5) per the ``ir_rc5_decode`` body:
#
#   - btfsc PORTB, RB5 at decode entry: must be LOW (carrier on)
#     to proceed -- so the START bit S1 looks like LOW-first-half
#     at the MCU pin.
#   - Mid-bit sample reads HIGH = bit 1, LOW = bit 0.  S1='1' at
#     the MCU pin is LOW-then-HIGH (carrier first, idle second);
#     mid-bit-second-half sample reads HIGH → decoder bit value 1. ✓
#   - S2='1' similarly LOW-then-HIGH.
#   - T='0' = HIGH-then-LOW.
#   - Etc.

# K20 timing: 16 ticks/Tcy at Fcy=16 MHz → 1 µs = 256 ticks.
RC5_HALF_BIT_TICKS = 889 * 256  # 227,584 ticks per half-bit


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_ir_rc5_pulse_train")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


def _rc5_frame_bits(addr: int, cmd: int, toggle: int = 0) -> list[int]:
    """Build the 14-bit RC5 frame as a flat MSB-first bit list.

    Bit order: S1, S2, T, A4..A0, C5..C0.  S1 and S2 are always 1.
    """
    if addr < 0 or addr > 0x1F:
        raise ValueError(f"RC5 address must be 5-bit; got {addr:#x}")
    if cmd < 0 or cmd > 0x3F:
        raise ValueError(f"RC5 command must be 6-bit; got {cmd:#x}")
    if toggle not in (0, 1):
        raise ValueError(f"RC5 toggle must be 0 or 1; got {toggle}")
    bits = [1, 1, toggle]
    for i in range(4, -1, -1):
        bits.append((addr >> i) & 1)
    for i in range(5, -1, -1):
        bits.append((cmd >> i) & 1)
    return bits


def _drive_rc5_pulse_train(chain, addr: int, cmd: int, toggle: int = 0) -> None:
    """Drive a Manchester-encoded RC5 frame at CONTROL.RB5.

    Idle = HIGH (no carrier).  Each bit is two half-bits at
    ``RC5_HALF_BIT_TICKS`` ticks each.  Bit '1' at MCU pin is
    LOW-then-HIGH; bit '0' is HIGH-then-LOW.

    After the frame, leaves RB5 HIGH (idle) and steps an extra
    half-bit so the decoder sees a clean post-frame idle.
    """
    # Ensure idle state before the frame.
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_HALF_BIT_TICKS)

    bits = _rc5_frame_bits(addr, cmd, toggle)
    for bit in bits:
        if bit == 1:
            # '1' = LOW-then-HIGH at MCU.
            chain.set_control_pin("B", 5, False)
            chain.step_ticks(RC5_HALF_BIT_TICKS)
            chain.set_control_pin("B", 5, True)
            chain.step_ticks(RC5_HALF_BIT_TICKS)
        else:
            # '0' = HIGH-then-LOW at MCU.
            chain.set_control_pin("B", 5, True)
            chain.step_ticks(RC5_HALF_BIT_TICKS)
            chain.set_control_pin("B", 5, False)
            chain.step_ticks(RC5_HALF_BIT_TICKS)

    # Post-frame idle: leave RB5 HIGH and drain a half-bit so the
    # decoder's tail bit sees a stable idle.
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_HALF_BIT_TICKS)


_RC5_BC61C70_REGRESSION_XFAIL = pytest.mark.xfail(
    strict=True,
    reason=(
        "bc61c70 (\"Harden V1.71 link handling and probe flash-entry "
        "volume\") moved ir_rc5_decode out of the ISR into a deferred "
        "foreground service routine v171_service_pending_ir_decode "
        "that runs from display_loop_iteration after "
        "button_scan_debounce.  The RC5 decoder is a bit-bang RB5 "
        "poll with ~889 us half-bit timing that assumes it starts "
        "near the falling edge of S1.  Foreground service runs "
        "significantly later than the ISR latch, so the decoder's "
        "sample windows are off and it returns to the "
        "flow_ir_rc5_decode_02E4 abort path with ir_decoded_cmd "
        "untouched at 0xFF.  Diagnostic in the test body shows "
        "post-train pending=0xFF (ISR fires + latches during the "
        "pulse train) and post-settle pending=0x00 (foreground "
        "drained the flag) -- only the decoder's output is wrong, "
        "isolating the bug to the foreground-vs-bit-bang timing.  "
        "XPASS will surface when "
        "the firmware is fixed (likely by reverting bc61c70's "
        "deferral so ir_rc5_decode runs from the ISR again, the "
        "V1.7 stock pattern).  Strict so XPASS = real failure: the "
        "decorator must be removed in the same commit that fixes "
        "the firmware."
    ),
)


@_RC5_BC61C70_REGRESSION_XFAIL
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_rc5_pulse_train_decodes_standby_endpoint(v171_hex: Path) -> None:
    """Drive RC5 (addr=0x10, cmd=0x3A) at CONTROL.RB5 and verify the
    decoder produces ``ir_decoded_cmd == 0x3A`` AND the V1.71 inline
    IR dispatch emits ``[B0, 03, 00]`` (standby frame).

    This exercises the FULL IR path:
      RBIF ISR latch → v171_ir_decode_pending → foreground
      v171_service_pending_ir_decode → ir_rc5_decode → inline
      dispatch.

    It will FAIL if commit ``bc61c70``'s deferred foreground
    decode breaks RC5 timing reliability (the bug under
    investigation).
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(v171_hex))
    h = chain  # facade exposes warmup/step/tx_frames/etc on Chain directly
    h.warmup(25_000_000)
    h.pause_heartbeat()
    for _ in range(40):
        h.step()

    # RB5 starts HIGH (idle).  Must be confirmed before injection
    # because the decoder aborts if RB5 is HIGH at decode entry --
    # but ARRIVES at decode entry only after the falling edge of
    # S1's first half.
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        h.step()

    # Snapshot pre-injection state.
    before_tx = len(h.tx_frames())
    pre_decoded_cmd = chain.read_reg(0x01D)
    pre_decoded_addr = chain.read_reg(0x01E)
    pre_pending = chain.read_reg(0x0AA)  # v171_ir_decode_pending
    pre_flags = chain.read_reg(0x01F)    # control_flags (bit0 = IR_ARMED)

    # Drive the RC5 pulse train: addr=0x10 (preset menu),
    # cmd=0x3A (V1.64b explicit standby endpoint).
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x3A)

    # Post-train snapshot (immediately after the pulse train,
    # before the foreground-service settle).  The pulse train
    # spans ~25 ms simulated, during which the ISR has been
    # firing on every RB5 edge and latching pending=0xFF if
    # the IOC->RBIF->ISR chain works.  If post_train_pending
    # is 0xFF here, the ISR latch path is intact; the bug is
    # localised to the foreground decoder timing.
    post_train_pending = chain.read_reg(0x0AA)
    post_train_flags = chain.read_reg(0x01F)

    # Step enough ticks for the foreground service routine to drain
    # the pending flag and run ir_rc5_decode -- the decoder itself
    # takes ~7-10 ms (~28K Tcy, ~450K ticks); add slack for the
    # foreground scheduler to actually call it.
    h.step_ticks(20_000_000)
    for _ in range(40):
        h.step()

    # Read the decoded values the firmware should have written.
    decoded_cmd = chain.read_reg(0x01D)
    decoded_addr = chain.read_reg(0x01E)
    post_pending = chain.read_reg(0x0AA)
    post_flags = chain.read_reg(0x01F)

    new_frames = h.tx_frames()[before_tx:]

    # Diagnostic eprint so a failure shows what the decoder
    # actually saw.  Distinguishes:
    #   - ISR didn't fire        -> post_train_pending == 0
    #   - ISR fired, fg ran      -> post_pending == 0, decoded_cmd correct
    #   - ISR fired, fg ran late -> post_pending == 0, decoded_cmd wrong (bc61c70 regression)
    #   - ISR fired, fg never    -> post_pending != 0
    print(
        f"\nRC5 pulse-train decode result:\n"
        f"  pre:        ir_decoded_cmd=0x{pre_decoded_cmd:02X}, addr=0x{pre_decoded_addr:02X}, "
        f"pending=0x{pre_pending:02X}, flags=0x{pre_flags:02X}\n"
        f"  post-train: pending=0x{post_train_pending:02X}, flags=0x{post_train_flags:02X}\n"
        f"  post-settle: ir_decoded_cmd=0x{decoded_cmd:02X}, addr=0x{decoded_addr:02X}, "
        f"pending=0x{post_pending:02X}, flags=0x{post_flags:02X}\n"
        f"  expected: cmd=0x3A, addr=0x10\n"
        f"  TX frames after injection: {list(new_frames)}"
    )

    # If decoder + dispatch worked end-to-end, this passes.
    # If commit bc61c70 broke timing, decoded_cmd != 0x3A and
    # the standby frame won't be in the TX stream -- the test
    # fails, exposing the bug.
    assert decoded_cmd == 0x3A, (
        f"ir_decoded_cmd should be 0x3A after RC5 pulse train; got "
        f"0x{decoded_cmd:02X}.  This is the bc61c70 deferred-decode "
        f"regression: the foreground decoder runs after the ISR "
        f"latch but the bit-bang timing windows have shifted, so "
        f"the decoder reads garbage instead of cmd=0x3A."
    )
    assert decoded_addr == 0x10, (
        f"ir_decoded_addr should be 0x10; got 0x{decoded_addr:02X}"
    )

    standby_frame = (0xB0, 0x03, 0x00)
    new_tuples = list(new_frames)
    assert standby_frame in new_tuples, (
        f"V1.71 inline dispatch should emit {standby_frame} after "
        f"RC5 cmd=0x3A; got {new_tuples}"
    )


@_RC5_BC61C70_REGRESSION_XFAIL
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_rc5_pulse_train_decodes_wake_endpoint(v171_hex: Path) -> None:
    """Same test shape for cmd=0x3B (wake endpoint).  Asserts
    ``ir_decoded_cmd == 0x3B`` and ``[B0, 03, 01]`` in TX.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(v171_hex))
    h = chain
    h.warmup(25_000_000)
    h.pause_heartbeat()
    for _ in range(40):
        h.step()

    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        h.step()

    before_tx = len(h.tx_frames())
    pre_pending = chain.read_reg(0x0AA)
    pre_flags = chain.read_reg(0x01F)

    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x3B)

    post_train_pending = chain.read_reg(0x0AA)
    post_train_flags = chain.read_reg(0x01F)

    h.step_ticks(20_000_000)
    for _ in range(40):
        h.step()

    decoded_cmd = chain.read_reg(0x01D)
    decoded_addr = chain.read_reg(0x01E)
    post_pending = chain.read_reg(0x0AA)
    post_flags = chain.read_reg(0x01F)
    new_frames = h.tx_frames()[before_tx:]

    print(
        f"\nRC5 wake pulse-train decode result:\n"
        f"  pre:        pending=0x{pre_pending:02X}, flags=0x{pre_flags:02X}\n"
        f"  post-train: pending=0x{post_train_pending:02X}, flags=0x{post_train_flags:02X}\n"
        f"  post-settle: ir_decoded_cmd=0x{decoded_cmd:02X} (expected 0x3B), "
        f"addr=0x{decoded_addr:02X} (expected 0x10), "
        f"pending=0x{post_pending:02X}, flags=0x{post_flags:02X}\n"
        f"  TX frames after injection: {list(new_frames)}"
    )

    assert decoded_cmd == 0x3B, (
        f"ir_decoded_cmd should be 0x3B; got 0x{decoded_cmd:02X}.  "
        f"bc61c70 deferred-decode regression."
    )
    assert decoded_addr == 0x10
    wake_frame = (0xB0, 0x03, 0x01)
    new_tuples = list(new_frames)
    assert wake_frame in new_tuples, (
        f"V1.71 inline dispatch should emit {wake_frame} after RC5 "
        f"cmd=0x3B; got {new_tuples}"
    )


# Note on test scope: the xfail tests above print the
# v171_ir_decode_pending and control_flags state at three points
# (pre, post-train, post-settle).  When investigating an xfail or
# the firmware fix landing, read the captured stdout: a healthy
# IOC->RBIF->ISR->pending chain shows ``post-train pending=0xFF``
# (ISR latched the IR event during the pulse train) and
# ``post-settle pending=0x00`` (foreground service drained the
# flag).  That isolates the bc61c70 regression to the foreground
# decoder's bit-bang timing alone.
