"""V1.71 IR RC5 pulse-train regression test.

The existing IR sim tests (``test_v171_ir_endpoints.py``,
``test_v171_preset_inline.py``) inject the decoded result directly
via ``inject_decoded_ir_event`` -- a RAM poke that writes to
``ir_decoded_cmd`` (0x01D), ``ir_decoded_addr`` (0x01E), and
clears ``control_flags.IR_ARMED`` (0x01F.bit0).  That bypasses
``ir_rc5_decode`` (asm:546+) entirely, so a regression in the
bit-bang decoder, the port-B IOC -> RBIF -> ISR latch path, or
the V1.71 deferred-decode service routine
(``v171_service_pending_ir_decode``) would not be detected.

This test drives a real Manchester-encoded RC5 pulse train at
CONTROL's RB5 input pin with 889 µs half-bit timing, then asserts
that the V1.71 inline IR dispatch emits the expected standby
frame to CONTROL's TX stream.  Asserting on the TX frame (rather
than on the transient ``ir_decoded_cmd``/``ir_decoded_addr``
register state) is the correct functional contract: the deferred
decoder runs MID-pulse-train (the train spans ~25 ms during which
the foreground display_loop_iteration cycles) and writes the cmd
byte briefly while the dispatch fires, but a SECOND decoder run
later in the same train (triggered by subsequent RB5 edges
re-latching ``v171_ir_decode_pending``) takes the abort path and
overwrites ir_decoded_cmd back to 0xFF.

Polarity convention (validated empirically against stock V1.6b
CONTROL by the codex sandbox 2026-05-07): the DLCP firmware
expects bit '1' = HIGH-then-LOW at the MCU pin, bit '0' =
LOW-then-HIGH.  Idle = HIGH between frames.  This is INVERTED
from the standard TSOP-active-low convention.

Investigation arc summary (commits a3851f4 .. 82fbb29 + this
follow-up):
  - First version of this test used the wrong Manchester
    polarity, so all variants xfailed.  Both bc61c70-deferred and
    a bc61c70-revert variant produced ir_decoded_cmd=0xFF, which
    looked like a sim fidelity gap.
  - The bc61c70 revert was tested and breaks 4 layer5_diag_chain
    tests by re-introducing Bug C3 (``ir_decode_blocks_isr_10ms``)
    -- the in-ISR decoder stalls UART RX/button RBIF/TXIE for
    ~7-10 ms, so the deferral cannot be reverted blindly.
  - Codex investigation confirmed the polarity is inverted and
    the rust sim DOES faithfully decode RC5 once the polarity is
    fixed.  Test now passes against the current bc61c70-deferred
    source -- meaning the user's reported real-hardware IR bug,
    if any, is NOT reproduced at the simulator level.
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


# RC5 protocol (DLCP-specific Manchester polarity):
#
# - 14-bit frame: S1 (start, '1') + S2 (start, '1') + T (toggle) +
#   5-bit address + 6-bit command.
# - Manchester encoding at the MCU pin (DLCP convention, validated
#   empirically against stock V1.6b CONTROL on the rust sim):
#     bit '1' = HIGH-then-LOW
#     bit '0' = LOW-then-HIGH
#   Idle = HIGH between frames.  This is the OPPOSITE of the
#   standard TSOP-active-low + first-half-active reading -- the
#   DLCP's `ir_rc5_decode` (asm:546+) expects the firmware-visible
#   pin level to follow the inverted convention, presumably because
#   the receiver hardware is wired active-high or because the
#   firmware reads polarity-inverted Manchester.  Either way, the
#   empirical result is what matters: this polarity makes stock
#   V1.6b decode `addr=0x10, cmd=0x3A` from the pulse train below
#   (`ir_decoded_cmd=0x3A` post-decode), as confirmed by the codex
#   sandbox investigation 2026-05-07.
# - Half-bit time: 889 µs (full bit = 1.778 ms).
# - Frame total: 14 × 1.778 ms = 24.9 ms; inter-frame gap >= 89 ms.
#
# At the MCU pin (RB5) per the ``ir_rc5_decode`` body:
#   - btfsc PORTB, RB5 at decode entry: must be LOW (post falling
#     edge) to proceed.  ISR fires on RB5 falling edge; for bit '1'
#     under the inverted convention, the falling edge happens at
#     the mid-bit transition (HIGH first half → LOW second half).
#     So decoder enters during S1's second half with RB5 LOW.
#   - Sample-shift polarity (asm:573-576):
#       bsf STATUS, C, A      ; assume bit value = 1
#       btfsc PORTB, RB5, A   ; skip clear-C if RB5 LOW
#       bcf STATUS, C, A      ; clear C → bit value = 0
#       rlcf INDF0, F, A      ; rotate C into accumulator
#     So the decoder shifts in '1' when RB5 reads LOW, '0' when
#     RB5 reads HIGH -- the opposite of a naïve "level == bit"
#     reading.  Combined with the inverted Manchester driving
#     above (bit '1' at the MCU pin = HIGH first-half → LOW
#     second-half), the decoder reading LOW in the second-half
#     sample-window correctly shifts in '1'.

# K20 timing: the rust sim's K20 default uses
# `peripherals::osc::ticks_per_tcy(K20) = 16` at a 48 MHz universal
# clock (per `peripherals/osc.rs:UNIVERSAL_CLOCK_HZ`) → 1 Tcy =
# 333.3 ns, so 1 µs = 48 universal ticks.  This corresponds to a
# K20 Fcy of 3 MHz (12 MHz Fosc with no PLL — the DLCP external
# oscillator constant `DLCP_EXTERNAL_OSC_HZ = 12_000_000`).  RC5
# half-bit at this universal-clock rate is 889 × 48 = 42,672 ticks.
RC5_HALF_BIT_TICKS = 889 * 48  # 42,672 ticks per half-bit


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
    """Drive a Manchester-encoded RC5 frame at CONTROL.RB5 using
    the DLCP firmware's inverted polarity convention.

    Idle = HIGH between frames.  Each bit is two half-bits at
    ``RC5_HALF_BIT_TICKS`` ticks each.  Bit '1' at MCU pin is
    HIGH-then-LOW; bit '0' is LOW-then-HIGH.  This polarity is
    inverted from the standard TSOP-active-low convention but
    is what `ir_rc5_decode` empirically expects (codex
    investigation 2026-05-07 confirmed `cmd=0x3A` decoding on
    stock V1.6b with this polarity).

    After the frame, leaves RB5 HIGH (idle) and steps an extra
    half-bit so the decoder sees a clean post-frame idle.
    """
    # Ensure idle state before the frame.
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_HALF_BIT_TICKS)

    bits = _rc5_frame_bits(addr, cmd, toggle)
    for bit in bits:
        if bit == 1:
            # '1' = HIGH-then-LOW at MCU (DLCP convention).
            chain.set_control_pin("B", 5, True)
            chain.step_ticks(RC5_HALF_BIT_TICKS)
            chain.set_control_pin("B", 5, False)
            chain.step_ticks(RC5_HALF_BIT_TICKS)
        else:
            # '0' = LOW-then-HIGH at MCU (DLCP convention).
            chain.set_control_pin("B", 5, False)
            chain.step_ticks(RC5_HALF_BIT_TICKS)
            chain.set_control_pin("B", 5, True)
            chain.step_ticks(RC5_HALF_BIT_TICKS)

    # Post-frame idle: leave RB5 HIGH and drain a half-bit so the
    # decoder's tail bit sees a stable idle.
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_HALF_BIT_TICKS)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_rc5_pulse_train_decodes_standby_endpoint(v171_hex: Path) -> None:
    """Drive RC5 (addr=0x10, cmd=0x3A) at CONTROL.RB5 and verify
    the V1.71 inline IR dispatch emits ``[B0, 03, 00]`` (standby
    frame) to CONTROL's TX stream.

    This exercises the FULL IR pipeline:
      RB5 falling edge → port-B IOC → RBIF → ISR latch
      ``v171_ir_decode_pending`` → foreground
      ``v171_service_pending_ir_decode`` → ``ir_rc5_decode``
      bit-bang → inline dispatch → ``v171_send_standby_cmd_frame``
      → TX standby frame.

    Asserts on the TX frame rather than ``ir_decoded_cmd`` because
    the latter is transient mid-state -- the deferred decoder runs
    MID-pulse-train, writes the cmd byte briefly while the
    dispatch fires, then a SECOND decoder run later in the same
    train (re-latched pending=0xFF on subsequent RB5 edges) takes
    the abort path and overwrites it back to 0xFF.  The TX frame
    is the durable functional outcome.
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
    post_train_cmd = chain.read_reg(0x01D)
    post_train_addr = chain.read_reg(0x01E)

    # Settle in chunks and sample ir_decoded_cmd at each chunk
    # boundary so we can see if/when it becomes 0x3A and whether
    # something later clears it back to 0xFF.
    settle_trace: list[tuple[int, int, int, int, int]] = []
    for chunk_idx in range(20):
        h.step_ticks(1_000_000)
        settle_trace.append((
            chunk_idx,
            chain.read_reg(0x01D),  # ir_decoded_cmd
            chain.read_reg(0x01E),  # ir_decoded_addr
            chain.read_reg(0x0AA),  # pending
            chain.read_reg(0x01F),  # flags
        ))
    for _ in range(40):
        h.step()

    # Read the decoded values the firmware should have written.
    decoded_cmd = chain.read_reg(0x01D)
    decoded_addr = chain.read_reg(0x01E)
    post_pending = chain.read_reg(0x0AA)
    post_flags = chain.read_reg(0x01F)

    new_frames = h.tx_frames()[before_tx:]
    for idx, c, a, p, f in settle_trace:
        if c != 0xFF or p != 0:
            print(
                f"  settle[{idx}]: cmd=0x{c:02X} addr=0x{a:02X} "
                f"pending=0x{p:02X} flags=0x{f:02X}"
            )

    # Diagnostic eprint so a failure shows what the decoder
    # actually saw.  Distinguishes:
    #   - ISR didn't fire        -> post_train_pending == 0
    #   - ISR fired, fg ran      -> post_pending == 0, decoded_cmd correct
    #   - ISR fired, fg ran twice -> decoded_cmd 0xFF (overwritten by second-run abort)
    #   - ISR fired, fg never    -> post_pending != 0
    print(
        f"\nRC5 pulse-train decode result:\n"
        f"  pre:        ir_decoded_cmd=0x{pre_decoded_cmd:02X}, addr=0x{pre_decoded_addr:02X}, "
        f"pending=0x{pre_pending:02X}, flags=0x{pre_flags:02X}\n"
        f"  post-train: ir_decoded_cmd=0x{post_train_cmd:02X}, "
        f"addr=0x{post_train_addr:02X}, "
        f"pending=0x{post_train_pending:02X}, flags=0x{post_train_flags:02X}\n"
        f"  post-settle: ir_decoded_cmd=0x{decoded_cmd:02X}, addr=0x{decoded_addr:02X}, "
        f"pending=0x{post_pending:02X}, flags=0x{post_flags:02X}\n"
        f"  expected: cmd=0x3A, addr=0x10\n"
        f"  TX frames after injection: {list(new_frames)}"
    )

    # The functional contract is the V1.71 inline dispatch firing
    # in response to the RC5 cmd=0x3A.  ir_decoded_cmd / ir_decoded_addr
    # are TRANSIENT mid-state -- the deferred decoder runs MID-pulse-
    # train (the train spans ~25 ms during which the foreground
    # display_loop_iteration cycles), writes 0x3A briefly while the
    # dispatch fires and emits the standby frame, then a SECOND
    # decoder run later in the same train (triggered by subsequent
    # RB5 edges latching pending=0xFF again) takes the abort path
    # and overwrites ir_decoded_cmd back to 0xFF.  So we assert on
    # the TX standby frame appearing (the visible/functional
    # outcome) rather than the transient register state.
    standby_frame = (0xB0, 0x03, 0x00)
    new_tuples = list(new_frames)
    assert standby_frame in new_tuples, (
        f"V1.71 inline IR dispatch should emit {standby_frame} after "
        f"RC5 (addr=0x10, cmd=0x3A) at RB5; got TX frames {new_tuples}.  "
        f"Diagnostic: ir_decoded_cmd at post-train = "
        f"0x{post_train_cmd:02X}, post-settle = 0x{decoded_cmd:02X}; "
        f"pending post-train = 0x{post_train_pending:02X}, post-settle = "
        f"0x{post_pending:02X}."
    )


# ===========================================================================
# Parametrized pulse-train decode coverage for all 4 V1.71 inline shortcuts
# (#157).
#
# Asserts on ir_decoded_cmd / ir_decoded_addr REGISTERS post-decode rather
# than on the chain TX stream.  Why: the V1.71 layer-2 full_sync_step
# machine emits preset/standby/wake frames on its own cadence (independent
# of IR), so a TX-frame assertion can pass coincidentally.  Direct register
# inspection isolates "did the decoder actually decode this cmd" from
# "did the dispatcher fire AND did layer-2 not happen to emit the same
# frame".
#
# This locks in the decoder timing fix from 61e17a7 (V171_IR_TMR1_FULL
# preload retune from 0xF595 -> 0xF5D8).  Pre-fix, cmds with cmd LSB = 1
# (0x39 preset B, 0x3B wake) failed Manchester pair-validation on the
# last sample pair and the legacy decoder bailed to error path
# (ir_decoded_cmd = 0xFF).  Post-fix, all four cmds decode correctly.
# ===========================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("cmd, label", [
    (0x38, "preset A"),
    (0x39, "preset B"),
    (0x3A, "standby"),
    (0x3B, "wake"),
])
def test_v171_rc5_pulse_train_decodes_inline_shortcut_cmd(
    v171_hex: Path, cmd: int, label: str,
) -> None:
    """Drive RC5 (addr=0x10, cmd=<param>) at CONTROL.RB5 and verify
    the M3 Timer1-driven decoder lands the expected value in
    ir_decoded_cmd / ir_decoded_addr.

    Exercises the FULL pipeline post-M3 (per 86d88e0 + 61e17a7):
      RB5 falling edge -> port-B IOC -> RBIF -> isr_entry ->
      v171_ir_start_decode (Timer1 first preload 0xF0BC) -> 32x
      v171_ir_sample_handler (Timer1 reload preload 0xF5D8) ->
      v171_ir_decode_done -> v171_ir_post_process ->
      flow_ir_rc5_decode_025E (legacy Manchester pair-validation) ->
      ir_decoded_cmd / ir_decoded_addr written.

    Direct register check, no TX-frame coincidence.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(v171_hex))
    chain.warmup(25_000_000)
    chain.pause_heartbeat()
    for _ in range(40):
        chain.step()
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        chain.step()

    _drive_rc5_pulse_train(chain, addr=0x10, cmd=cmd)
    # Settle long enough for decode + post_process to land cmd/addr
    # (~150 ms simulated covers the worst-case ISR-dispatch tail).
    for _ in range(8):
        chain.step_ticks(1_000_000)

    decoded_cmd = chain.read_reg(0x01D)
    decoded_addr = chain.read_reg(0x01E)
    assert decoded_cmd == cmd, (
        f"{label} (cmd 0x{cmd:02X}): decoded_cmd=0x{decoded_cmd:02X}, "
        f"expected 0x{cmd:02X}.  Decoder bailed to error path (0xFF) "
        f"or never wrote cmd (0x00 / pre-warmup value).  Check the "
        f"M3 Timer1 preloads in dlcp_control_ram.inc -- the FULL "
        f"preload V171_IR_TMR1_FULL must produce a sample-to-sample "
        f"interval close to RC5's 890 us at the btfsc PORTB,RB5 step."
    )
    assert decoded_addr == 0x10, (
        f"{label} (cmd 0x{cmd:02X}): decoded_addr=0x{decoded_addr:02X}, "
        f"expected 0x10."
    )
