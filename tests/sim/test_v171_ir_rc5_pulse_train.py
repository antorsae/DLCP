"""V1.71 IR RC5 pulse-train regression test.

The other IR sim tests (``test_v171_ir_endpoints.py``,
``test_v171_preset_inline.py``, ``test_v171_ir_command_matrix.py``)
inject the decoded result directly via ``inject_decoded_ir_event``
-- a RAM poke that writes ``ir_decoded_cmd`` (0x01D),
``ir_decoded_addr`` (0x01E), and clears ``control_flags.IR_ARMED``
(0x01F.bit0).  That bypasses the bit-bang Manchester decoder
entirely, so a regression in the port-B IOC -> RBIF -> ISR latch
path, the M3 Timer1-driven sample state machine, or the post-process
hand-off to ``flow_ir_rc5_decode_025E`` would not be detected by
the inject-based tests.

This file drives a real Manchester-encoded RC5 pulse train at
CONTROL's RB5 input pin with 889 µs half-bit timing.  Three test
shapes:

  1. ``test_v171_rc5_pulse_train_decodes_standby_endpoint`` -- the
     original black-box gate: drives cmd=0x3A and asserts the
     standby chain TX frame appears.

  2. ``test_v16b_and_v171_rc5_pulse_train_decode_same_command_stress`` --
     drives the same RB5 waveform matrix into stock V1.6b and V1.71,
     including the current Hypex profile-1 commands used by the
     Flipper hardware sender.

  3. ``test_v171_rc5_pulse_train_decodes_inline_shortcut_cmd`` --
     parametrized over all four V1.71 inline cmds (0x38/0x39/0x3A/
     0x3B) and asserts on ``ir_decoded_cmd`` / ``ir_decoded_addr``
     registers post-decode.  This locks in the M3 timing fix from
     61e17a7 (V171_IR_TMR1_FULL retune 0xF595 -> 0xF5D8) as an
     automated regression gate.

Polarity convention (validated empirically against stock V1.6b
CONTROL by the codex sandbox 2026-05-07): the DLCP firmware
expects bit '1' = HIGH-then-LOW at the MCU pin, bit '0' =
LOW-then-HIGH.  Idle = HIGH between frames.  This is INVERTED
from the standard TSOP-active-low convention.

Decoder pipeline post-M3 (per 86d88e0 + 61e17a7):
  RB5 falling edge -> port-B IOC -> RBIF -> isr_entry ->
  v171_ir_start_decode -> 32 x v171_ir_sample_handler ->
  v171_ir_decode_done -> v171_ir_post_process ->
  flow_ir_rc5_decode_025E -> ir_decoded_cmd / ir_decoded_addr ->
  control_core_service_0DCE foreground dispatch -> V1.71 inline
  shortcut case (preset A/B / standby / wake) -> chain TX frame.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import STOCK_CONTROL_HEX_V16B, V17_CONTROL_RAM_INC, V171_CONTROL_ASM
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
RC5_INTER_FRAME_GAP_TICKS = 90_000 * 48

IR_DECODED_CMD_PHYS = 0x01D
IR_DECODED_ADDR_PHYS = 0x01E
CONTROL_FLAGS_PHYS = 0x01F
IR_ARMED_MASK = 0x01


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


def _build_warmed_ir_chain(hex_path: Path):  # type: ignore[no-untyped-def]
    chain = RustChain.from_v17_chain(str(hex_path))
    chain.warmup(25_000_000)
    chain.pause_heartbeat()
    for _ in range(40):
        chain.step()
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_INTER_FRAME_GAP_TICKS)
    return chain


def _prime_for_rc5_decode(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(0x01B, 0x00)
    chain.write_reg(0x01C, 0x00)
    chain.write_reg(IR_DECODED_CMD_PHYS, 0x00)
    chain.write_reg(IR_DECODED_ADDR_PHYS, 0x00)
    flags = chain.read_reg(CONTROL_FLAGS_PHYS)
    chain.write_reg(CONTROL_FLAGS_PHYS, (flags & ~0x32) | IR_ARMED_MASK)
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_INTER_FRAME_GAP_TICKS)


def _wait_for_decoded(chain, *, addr: int, cmd: int, label: str) -> None:  # type: ignore[no-untyped-def]
    for _ in range(20):
        if (
            chain.read_reg(IR_DECODED_CMD_PHYS) == cmd
            and chain.read_reg(IR_DECODED_ADDR_PHYS) == addr
        ):
            return
        chain.step_ticks(1_000_000)
    pytest.fail(
        f"{label}: RC5 pulse train did not decode to addr=0x{addr:02X} "
        f"cmd=0x{cmd:02X}; got addr=0x{chain.read_reg(IR_DECODED_ADDR_PHYS):02X} "
        f"cmd=0x{chain.read_reg(IR_DECODED_CMD_PHYS):02X} "
        f"flags=0x{chain.read_reg(CONTROL_FLAGS_PHYS):02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v16b_and_v171_rc5_pulse_train_decode_same_command_stress(
    v171_hex: Path,
) -> None:
    """Drive the same real-RB5 RC5 pulse sequence into stock V1.6b and V1.71.

    This is the parity gate for BUG-IR-01: stock V1.6b is the known-good
    reference for real IR, and V1.71 must decode the same waveform for
    the current Hypex profile, standard profile, and V1.71 shortcut
    commands.  The test does not use ``inject_decoded_ir_event``; every
    command enters via CONTROL.RB5 timing edges.
    """
    _require_rust()
    if not STOCK_CONTROL_HEX_V16B.is_file():
        pytest.skip(f"missing V1.6b stock hex: {STOCK_CONTROL_HEX_V16B}")

    cases = [
        (0x10, 0x33, "hypex profile volume up"),
        (0x10, 0x34, "hypex profile volume down"),
        (0x10, 0x35, "hypex profile mute"),
        (0x10, 0x36, "hypex profile input/preset next"),
        (0x10, 0x37, "hypex profile input/preset previous"),
        (0x10, 0x10, "standard profile volume up"),
        (0x10, 0x11, "standard profile volume down"),
        (0x10, 0x20, "standard profile input/preset next"),
        (0x10, 0x21, "standard profile input/preset previous"),
        (0x10, 0x0D, "standard profile mute"),
        (0x10, 0x38, "preset A shortcut"),
        (0x10, 0x39, "preset B shortcut"),
        (0x10, 0x3B, "wake shortcut"),
        # Keep side-effecting power/standby commands last.  The goal
        # here is decoder parity, not testing post-standby dispatch
        # from the same warmed chain.
        (0x10, 0x32, "hypex profile power"),
        (0x10, 0x0C, "standard profile power"),
        (0x10, 0x3A, "standby shortcut"),
    ]

    for image_label, hex_path in (("V1.6b", STOCK_CONTROL_HEX_V16B), ("V1.71", v171_hex)):
        for repeat in range(2):
            chain = _build_warmed_ir_chain(hex_path)
            for addr, cmd, label in cases:
                _prime_for_rc5_decode(chain)
                _drive_rc5_pulse_train(chain, addr=addr, cmd=cmd, toggle=repeat & 1)
                _wait_for_decoded(
                    chain,
                    addr=addr,
                    cmd=cmd,
                    label=f"{image_label} repeat {repeat + 1} {label}",
                )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_rc5_pulse_train_decodes_standby_endpoint(v171_hex: Path) -> None:
    """Drive RC5 (addr=0x10, cmd=0x3A) at CONTROL.RB5 and verify
    the V1.71 inline IR dispatch emits ``[B0, 03, 00]`` (standby
    frame) to CONTROL's TX stream.

    Exercises the FULL M3 IR pipeline (post-86d88e0 / 61e17a7):
      RB5 falling edge → port-B IOC → RBIF → isr_entry →
      v171_ir_start_decode (Timer1 first preload 0xF0BC) →
      32 x v171_ir_sample_handler (Timer1 reload 0xF5D8) →
      v171_ir_decode_done → v171_ir_post_process →
      flow_ir_rc5_decode_025E (Manchester pair-validation) →
      ir_decoded_cmd / ir_decoded_addr written → control_core_
      service_0DCE foreground dispatch → V1.71 inline standby
      case (asm:3422) → v171_send_standby_cmd_frame → TX
      standby frame.

    Asserts on the TX standby frame appearing in the new frames.
    The companion parametrized test below
    (test_v171_rc5_pulse_train_decodes_inline_shortcut_cmd) covers
    all four V1.71 inline cmds (0x38/0x39/0x3A/0x3B) via direct
    ir_decoded_cmd register inspection -- this test remains as a
    black-box pipeline gate for the standby-specific TX-byte path.
    """
    _require_rust()
    chain = RustChain.from_v17_chain(str(v171_hex))
    h = chain  # facade exposes warmup/step/tx_frames/etc on Chain directly
    h.warmup(25_000_000)
    h.pause_heartbeat()
    for _ in range(40):
        h.step()

    # RB5 starts HIGH (idle).  Must be confirmed before injection
    # because the decoder's RB5=LOW gate at asm:879-880 only arms
    # the M3 state machine on RBIF when RB5 is currently LOW (i.e.
    # post falling-edge of S1's first half).
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        h.step()

    before_tx = len(h.tx_frames())

    # Drive the RC5 pulse train: addr=0x10 (preset menu),
    # cmd=0x3A (V1.64b explicit standby endpoint).
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x3A)

    # Settle in chunks (post-frame the M3 sample handler keeps
    # firing until count == 32, then post_process runs).  20 x 1M
    # universal ticks ~ 417 ms simulated covers the worst-case
    # decode + dispatch tail.
    for _ in range(20):
        h.step_ticks(1_000_000)
    for _ in range(40):
        h.step()

    decoded_cmd = chain.read_reg(0x01D)
    decoded_addr = chain.read_reg(0x01E)

    new_frames = h.tx_frames()[before_tx:]
    standby_frame = (0xB0, 0x03, 0x00)
    new_tuples = list(new_frames)
    assert standby_frame in new_tuples, (
        f"V1.71 inline IR dispatch should emit {standby_frame} after "
        f"RC5 (addr=0x10, cmd=0x3A) at RB5; got TX frames {new_tuples}.  "
        f"Diagnostic: ir_decoded_cmd post-settle = 0x{decoded_cmd:02X} "
        f"(expected 0x3A), ir_decoded_addr = 0x{decoded_addr:02X} "
        f"(expected 0x10)."
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
