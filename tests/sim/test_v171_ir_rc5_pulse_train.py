"""V1.71 IR RC5 pulse-train regression test.

The other IR sim tests (``test_v171_ir_endpoints.py``,
``test_v171_preset_inline.py``, ``test_v171_ir_command_matrix.py``)
inject the decoded result directly via ``inject_decoded_ir_event``
-- a RAM poke that writes ``ir_decoded_cmd`` (0x01D),
``ir_decoded_addr`` (0x01E), and clears ``control_flags.IR_ARMED``
(0x01F.bit0).  That bypasses the bit-bang Manchester decoder
entirely, so a regression in the port-B IOC -> RBIF -> stock in-ISR
``ir_rc5_decode`` path would not be detected by the inject-based tests.

This file drives a real Manchester-encoded RC5 pulse train at
CONTROL's RB5 input pin with 889 µs half-bit timing.  It is the
receiver-layer companion to the decoded-event dispatcher matrices.
Keep both layers: decoded-event tests are cheap and broad, while this
file owns the small user-visible smoke set that proves real RB5 edges
still reach dispatch.

Test shapes:

  1. ``test_v171_rc5_pulse_train_decodes_standby_endpoint`` -- the
     original black-box gate: drives cmd=0x3A and asserts the
     standby chain TX frame appears.

  2. ``test_v16b_and_v171_rc5_pulse_train_decode_same_command_stress`` --
     drives the same RB5 waveform matrix into stock V1.6b and V1.71,
     including the current Hypex profile-1 commands used by the
     Flipper hardware sender.

  3. V1.73 POWER wake regressions -- configured power-on by real RC5
     must rearm the receiver so the next standby press is not ignored.

  4. V1.73 receiver-dispatch smoke tests -- real RB5 frames exercise
     volume, mute, preset shortcut, input shortcut, standby, wake, and
     Diagnostics-page dispatch for the current V1.73/V3.5 line.

  5. ``test_v171_rc5_pulse_train_decodes_inline_shortcut_cmd`` --
     parametrized over all four V1.71 inline cmds (0x38/0x39/0x3A/
     0x3B) and asserts on ``ir_decoded_cmd`` / ``ir_decoded_addr``
     registers post-decode.  This locks in the hardware-validated
     stock-compatible ISR decode path.

Polarity convention (validated empirically against stock V1.6b
CONTROL by the codex sandbox 2026-05-07): the DLCP firmware
expects bit '1' = HIGH-then-LOW at the MCU pin, bit '0' =
LOW-then-HIGH.  Idle = HIGH between frames.  This is INVERTED
from the standard TSOP-active-low convention.

Decoder pipeline:
  RB5 falling edge -> port-B IOC -> RBIF -> isr_entry ->
  ir_rc5_decode -> ir_decoded_cmd / ir_decoded_addr ->
  control_core_service_0DCE foreground dispatch -> V1.71 inline
  shortcut case (preset A/B / standby / wake) -> chain TX frame.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import (
    STOCK_CONTROL_HEX_V16B,
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
    V173_CONTROL_ASM,
    V173_CONTROL_HEX,
    V35_MAIN_HEX,
)
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
CONTROL_CONNECTED_MASK = 0x02
CONTROL_MUTE_MASK = 0x20
CONTROL_PRESET_B_MASK = 0x40
IR_INHIBIT_LO_PHYS = 0x01B
IR_INHIBIT_HI_PHYS = 0x01C
VOLUME_CACHE_PHYS = 0x0B9
INPUT_SELECT_CACHE_PHYS = 0x0B8
RAW_STATUS_CACHE_PHYS = 0x0A1
V171_DIAG_PRESENT_PHYS = 0x197
HEALTH_SEEN_MASK_PHYS = 0x1B2
INPUT_SPLIT_FLAGS_PHYS = 0x1BA
INPUT_INTENT_PB2_PHYS = 0x1BB
INPUT_SPLIT_FLAG_PB2_SEEN = 0
INPUT_SPLIT_FLAG_PB2_LINKED = 2
IR_PROFILE_ADDR_PHYS = 0x020
IR_PROFILE_POWER_PHYS = 0x021
IR_PROFILE_VOL_UP_PHYS = 0x022
IR_PROFILE_VOL_DOWN_PHYS = 0x023
IR_PROFILE_INPUT_UP_PHYS = 0x024
IR_PROFILE_INPUT_DOWN_PHYS = 0x025
IR_PROFILE_MUTE_PHYS = 0x026
MAIN_ACTIVE_FLAGS_PHYS = 0x05E
MAIN_ACTIVE_GATE_MASK = 0x08
MAIN_ACTIVE_PRESET_B_MASK = 0x04
IR_ADDR_HYPEX = 0x10
IR_CMD_HYPEX_POWER = 0x32
IR_CMD_HYPEX_VOL_UP = 0x33
IR_CMD_HYPEX_VOL_DOWN = 0x34
IR_CMD_HYPEX_MUTE = 0x35
IR_CMD_HYPEX_INPUT_UP = 0x36
IR_CMD_HYPEX_INPUT_DOWN = 0x37
IR_CMD_PRESET_TOGGLE = 0x3D
IR_CMD_INPUT_OPTICAL_SPDIF_TOGGLE = 0x3F
IR_CMD_STANDBY = 0x3A
IR_CMD_WAKE = 0x3B
COMMAND_SETTLE_TICKS = 12_000_000
STANDBY_FRAME = (0xB0, 0x03, 0x00)
WAKE_FRAME = (0xB0, 0x03, 0x01)
BUTTON_PINS = {
    "RIGHT": ("A", 4),
}


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


@pytest.fixture(scope="module")
def v173_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v173_ir_rc5_power_wake")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V173_CONTROL_ASM.name
    asm.write_bytes(V173_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v173.hex"
    assemble_v17(asm, hex_out)
    return hex_out


@pytest.fixture(scope="module", params=("source", "canonical"))
def v173_control_image(request: pytest.FixtureRequest, v173_hex: Path) -> Path:
    if request.param == "source":
        return v173_hex
    if not V173_CONTROL_HEX.is_file():
        pytest.skip(f"missing canonical V1.73 CONTROL hex: {V173_CONTROL_HEX}")
    return V173_CONTROL_HEX


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


def _rearm_rc5_receiver_without_state_reset(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(IR_INHIBIT_LO_PHYS, 0x00)
    chain.write_reg(IR_INHIBIT_HI_PHYS, 0x00)
    chain.write_reg(IR_DECODED_CMD_PHYS, 0x00)
    chain.write_reg(IR_DECODED_ADDR_PHYS, 0x00)
    flags = chain.read_reg(CONTROL_FLAGS_PHYS)
    chain.write_reg(CONTROL_FLAGS_PHYS, flags | IR_ARMED_MASK)
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


def _drive_rearmed_real_rc5(
    chain,  # type: ignore[no-untyped-def]
    *,
    cmd: int,
    label: str,
    addr: int = IR_ADDR_HYPEX,
    toggle: int = 0,
    settle_ticks: int = COMMAND_SETTLE_TICKS,
) -> list[tuple[int, int, int]]:
    before_tx = len(chain.tx_frames())
    _rearm_rc5_receiver_without_state_reset(chain)
    _drive_rc5_pulse_train(chain, addr=addr, cmd=cmd, toggle=toggle)
    _wait_for_decoded(chain, addr=addr, cmd=cmd, label=label)
    chain.step_ticks(settle_ticks)
    return [tuple(frame) for frame in chain.tx_frames()[before_tx:]]


def _wait_until(chain, predicate, *, label: str, slices: int = 160) -> None:  # type: ignore[no-untyped-def]
    for _ in range(slices):
        if predicate():
            return
        chain.step_ticks(1_000_000)
    pytest.fail(
        f"{label}; lcd={chain.lcd_lines()!r} "
        f"decoded=0x{chain.read_reg(IR_DECODED_ADDR_PHYS):02X}/"
        f"0x{chain.read_reg(IR_DECODED_CMD_PHYS):02X} "
        f"flags=0x{chain.read_reg(CONTROL_FLAGS_PHYS):02X} "
        f"inhibit=0x{chain.read_reg(IR_INHIBIT_HI_PHYS):02X}"
        f"{chain.read_reg(IR_INHIBIT_LO_PHYS):02X}"
    )


def _build_v173_v35_chain(control_hex_path: Path):  # type: ignore[no-untyped-def]
    _require_rust()
    if not V35_MAIN_HEX.is_file():
        pytest.skip(f"missing V3.5 MAIN hex: {V35_MAIN_HEX}")
    chain = RustChain.from_v171_v32(
        control_hex_path=str(control_hex_path),
        main_hex_path=str(V35_MAIN_HEX),
    )
    assert chain.run_until_connected(limit=300) < 300, chain.lcd_lines()
    assert chain.is_connected() and not chain.is_waiting(), chain.lcd_lines()
    return chain


def _configure_hypex_ir_profile(chain) -> None:  # type: ignore[no-untyped-def]
    for addr, value in (
        (IR_PROFILE_ADDR_PHYS, IR_ADDR_HYPEX),
        (IR_PROFILE_POWER_PHYS, IR_CMD_HYPEX_POWER),
        (IR_PROFILE_VOL_UP_PHYS, IR_CMD_HYPEX_VOL_UP),
        (IR_PROFILE_VOL_DOWN_PHYS, IR_CMD_HYPEX_VOL_DOWN),
        (IR_PROFILE_INPUT_UP_PHYS, IR_CMD_HYPEX_INPUT_UP),
        (IR_PROFILE_INPUT_DOWN_PHYS, IR_CMD_HYPEX_INPUT_DOWN),
        (IR_PROFILE_MUTE_PHYS, IR_CMD_HYPEX_MUTE),
    ):
        chain.write_reg(addr, value)


def _mark_pb2_seen_linked(chain) -> None:  # type: ignore[no-untyped-def]
    chain.write_reg(V171_DIAG_PRESENT_PHYS, chain.read_reg(V171_DIAG_PRESENT_PHYS) | 0x02)
    chain.write_reg(HEALTH_SEEN_MASK_PHYS, chain.read_reg(HEALTH_SEEN_MASK_PHYS) | 0x02)
    chain.write_reg(
        INPUT_SPLIT_FLAGS_PHYS,
        (1 << INPUT_SPLIT_FLAG_PB2_SEEN) | (1 << INPUT_SPLIT_FLAG_PB2_LINKED),
    )
    chain.write_reg(INPUT_INTENT_PB2_PHYS, chain.read_reg(INPUT_SELECT_CACHE_PHYS))


def _press_front_panel(chain, key: str) -> None:  # type: ignore[no-untyped-def]
    port, bit = BUTTON_PINS[key]
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _main_active_gates(chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_GATE_MASK) >> 3
        for unit in (0, 1)
    )


def _main_preset_bits(chain) -> tuple[int, int]:  # type: ignore[no-untyped-def]
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS_PHYS) & MAIN_ACTIVE_PRESET_B_MASK) >> 2
        for unit in (0, 1)
    )


def _navigate_to_diag_page(chain, pb_idx: int) -> None:  # type: ignore[no-untyped-def]
    target = f"PB{pb_idx + 1}"
    for _ in range(8):
        if chain.lcd_lines()[0].startswith(target):
            chain.step_ticks(COMMAND_SETTLE_TICKS)
            return
        _press_front_panel(chain, "RIGHT")
    if chain.lcd_lines()[0].startswith(target):
        chain.step_ticks(COMMAND_SETTLE_TICKS)
        return
    pytest.fail(f"did not reach {target} Diagnostics page; lcd={chain.lcd_lines()!r}")


def _assert_rc5_inhibit_clear(chain, *, label: str) -> None:  # type: ignore[no-untyped-def]
    assert chain.read_reg(IR_INHIBIT_LO_PHYS) == 0x00, (
        f"{label}: inhibit low still 0x{chain.read_reg(IR_INHIBIT_LO_PHYS):02X}"
    )
    assert chain.read_reg(IR_INHIBIT_HI_PHYS) == 0x00, (
        f"{label}: inhibit high still 0x{chain.read_reg(IR_INHIBIT_HI_PHYS):02X}"
    )


def _enter_standby_from_volume(chain) -> None:  # type: ignore[no-untyped-def]
    chain.press("STBY")
    assert "ZZZ" in chain.lcd_lines()[0].upper(), chain.lcd_lines()
    chain.set_control_pin("B", 5, True)
    chain.step_ticks(RC5_INTER_FRAME_GAP_TICKS)


def _wait_for_volume_after_power_wake(chain, *, label: str) -> None:  # type: ignore[no-untyped-def]
    _wait_until(
        chain,
        lambda: (
            chain.is_connected()
            and not chain.is_waiting()
            and chain.lcd_lines()[0].startswith("Volume")
        ),
        label=label,
    )
    _assert_rc5_inhibit_clear(chain, label=label)


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
def test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby(
    v173_control_image: Path,
) -> None:
    """Power-on by real Hypex RC5 pulse train must not leave IR dead.

    This regression intentionally does not call ``_prime_for_rc5_decode``:
    the bug is that the configured power key stores a long inhibit value in
    ``0x01B/0x01C``, and the RBIF ISR skips ``ir_rc5_decode`` while those
    bytes are nonzero.  Decoded-event tests and primed pulse tests mask that.
    """
    chain = _build_v173_v35_chain(v173_control_image)
    _enter_standby_from_volume(chain)
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=1)
    _wait_for_volume_after_power_wake(
        chain,
        label="power RC5 did not wake back to the Volume menu",
    )
    assert chain.read_reg(IR_DECODED_CMD_PHYS) == 0x32

    before_tx = len(chain.tx_frames())
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x3A, toggle=0)
    _wait_until(
        chain,
        lambda: "ZZZ" in chain.lcd_lines()[0].upper(),
        label="first real RC5 standby frame after power wake was ignored",
        slices=80,
    )

    assert STANDBY_FRAME in list(chain.tx_frames()[before_tx:])
    assert chain.read_reg(IR_DECODED_CMD_PHYS) == 0x3A


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v173_power_wake_ignores_late_held_power_repeats_before_next_standby(
    v173_control_image: Path,
) -> None:
    """Clearing the shared RC5 gate must not let a held POWER press bounce.

    The extra POWER frames use the same toggle bit as the wake frame, matching
    a user who holds the remote key across the reconnect exit boundary.
    """
    chain = _build_v173_v35_chain(v173_control_image)
    _enter_standby_from_volume(chain)

    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=1)
    _wait_until(
        chain,
        lambda: chain.is_waiting() or not chain.is_connected(),
        label="power RC5 did not enter reconnect/WAITING before repeats",
        slices=40,
    )

    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=1)
    chain.step_ticks(RC5_INTER_FRAME_GAP_TICKS)
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=1)

    _wait_for_volume_after_power_wake(
        chain,
        label="power RC5 did not return to Volume after held repeats",
    )

    before_tx = len(chain.tx_frames())
    for repeat in range(2):
        _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=1)
        chain.step_ticks(RC5_INTER_FRAME_GAP_TICKS)
        assert chain.lcd_lines()[0].startswith("Volume"), (
            f"held POWER repeat {repeat + 1} bounced to {chain.lcd_lines()!r}"
        )
        assert STANDBY_FRAME not in list(chain.tx_frames()[before_tx:])

    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x3A, toggle=0)
    _wait_until(
        chain,
        lambda: "ZZZ" in chain.lcd_lines()[0].upper(),
        label="explicit standby after guarded POWER repeats was ignored",
        slices=80,
    )
    assert STANDBY_FRAME in list(chain.tx_frames()[before_tx:])


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v173_power_repeat_guard_expires_for_deliberate_second_power_press(
    v173_control_image: Path,
) -> None:
    chain = _build_v173_v35_chain(v173_control_image)
    _enter_standby_from_volume(chain)

    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=1)
    _wait_for_volume_after_power_wake(
        chain,
        label="power RC5 did not wake before guard-expiry check",
    )

    before_tx = len(chain.tx_frames())
    chain.step_ticks(48_000_000)
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x32, toggle=0)
    _wait_until(
        chain,
        lambda: "ZZZ" in chain.lcd_lines()[0].upper(),
        label="configured POWER did not toggle standby after guard expiry",
        slices=80,
    )
    assert STANDBY_FRAME in list(chain.tx_frames()[before_tx:])


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v173_real_rc5_receiver_dispatches_volume_mute_preset_and_input_shortcuts(
    v173_control_image: Path,
) -> None:
    """Current V1.73/V3.5 IR smoke must enter through RB5, not RAM injection.

    Decoded-event matrices still own broad dispatcher permutations.  This
    receiver-layer smoke covers the user-visible Hypex profile commands and
    fixed F4/F5 shortcuts that would be missed if the Manchester decoder or
    RBIF rearm path broke.
    """
    chain = _build_v173_v35_chain(v173_control_image)
    _configure_hypex_ir_profile(chain)
    chain.write_reg(VOLUME_CACHE_PHYS, 0x33)
    chain.write_reg(INPUT_SELECT_CACHE_PHYS, 0x05)
    chain.write_reg(RAW_STATUS_CACHE_PHYS, 0x03)
    _mark_pb2_seen_linked(chain)
    chain.write_reg(
        CONTROL_FLAGS_PHYS,
        (
            chain.read_reg(CONTROL_FLAGS_PHYS)
            & ~CONTROL_MUTE_MASK
            & ~CONTROL_PRESET_B_MASK
        )
        | IR_ARMED_MASK,
    )

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_HYPEX_VOL_UP,
        label="V1.73/V3.5 Hypex volume-up receiver dispatch",
    )
    assert chain.read_reg(VOLUME_CACHE_PHYS) == 0x34
    assert (0xB0, 0x07, 0x34) in frames

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_HYPEX_MUTE,
        label="V1.73/V3.5 Hypex mute receiver dispatch",
    )
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_MUTE_MASK
    assert (0xB0, 0x03, 0x02) in frames

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_PRESET_TOGGLE,
        label="V1.73/V3.5 F4 preset-toggle receiver dispatch",
        settle_ticks=80_000_000,
    )
    _wait_until(
        chain,
        lambda: _main_preset_bits(chain) == (1, 1),
        label="real-RB5 F4 preset toggle did not reach both MAINs",
    )
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_PRESET_B_MASK
    assert chain.read_control_eeprom_byte(0x74) == 0x01
    assert (0xB0, 0x20, 0x01) in frames

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_INPUT_OPTICAL_SPDIF_TOGGLE,
        label="V1.73/V3.5 F5 Optical/S/PDIF receiver dispatch",
        settle_ticks=20_000_000,
    )
    assert chain.read_reg(INPUT_SELECT_CACHE_PHYS) == 0x08
    assert (0xB1, 0x06, 0x08) in frames
    assert (0xB2, 0x06, 0x08) in frames
    assert (0xB0, 0x06, 0x08) not in frames


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v173_real_rc5_receiver_dispatches_standby_and_wake_shortcuts(
    v173_control_image: Path,
) -> None:
    chain = _build_v173_v35_chain(v173_control_image)
    _configure_hypex_ir_profile(chain)

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_STANDBY,
        label="V1.73/V3.5 explicit standby receiver dispatch",
        settle_ticks=20_000_000,
    )
    assert STANDBY_FRAME in frames
    _wait_until(
        chain,
        lambda: "ZZZ" in chain.lcd_lines()[0].upper(),
        label="real-RB5 explicit standby did not reach Zzz display",
    )
    _wait_until(
        chain,
        lambda: _main_active_gates(chain) == (0, 0),
        label="real-RB5 explicit standby did not close both MAIN gates",
    )

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_WAKE,
        label="V1.73/V3.5 explicit wake receiver dispatch",
        settle_ticks=80_000_000,
    )
    assert WAKE_FRAME in frames
    _wait_until(
        chain,
        lambda: (
            chain.is_connected()
            and bool(chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_CONNECTED_MASK)
            and "ZZZ" not in chain.lcd_lines()[0].upper()
        ),
        label="real-RB5 explicit wake did not return to connected UI",
    )
    _wait_until(
        chain,
        lambda: _main_active_gates(chain) == (1, 1),
        label="real-RB5 explicit wake did not reopen both MAIN gates",
    )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("pb_idx", [0, 1])
def test_v173_real_rc5_receiver_dispatches_hypex_mute_from_diag_pages(
    v173_control_image: Path,
    pb_idx: int,
) -> None:
    """Diagnostics pages must not rely only on decoded-event IR coverage."""
    chain = _build_v173_v35_chain(v173_control_image)
    _configure_hypex_ir_profile(chain)
    _mark_pb2_seen_linked(chain)
    chain.write_reg(
        CONTROL_FLAGS_PHYS,
        (chain.read_reg(CONTROL_FLAGS_PHYS) & ~CONTROL_MUTE_MASK) | IR_ARMED_MASK,
    )
    _navigate_to_diag_page(chain, pb_idx)

    frames = _drive_rearmed_real_rc5(
        chain,
        cmd=IR_CMD_HYPEX_MUTE,
        label=f"V1.73/V3.5 PB{pb_idx + 1} Diag mute receiver dispatch",
        settle_ticks=20_000_000,
    )
    assert chain.read_reg(CONTROL_FLAGS_PHYS) & CONTROL_MUTE_MASK
    assert (0xB0, 0x03, 0x02) in frames
    assert chain.lcd_lines()[0].startswith(f"PB{pb_idx + 1}"), chain.lcd_lines()


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_rc5_pulse_train_decodes_standby_endpoint(v171_hex: Path) -> None:
    """Drive RC5 (addr=0x10, cmd=0x3A) at CONTROL.RB5 and verify
    the V1.71 inline IR dispatch emits ``[B0, 03, 00]`` (standby
    frame) to CONTROL's TX stream.

    Exercises the full live IR pipeline:
      RB5 falling edge → port-B IOC → RBIF → isr_entry →
      ir_rc5_decode (bit-bang Manchester decode) →
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
    # because the stock decoder's RB5=LOW gate must see the falling edge
    # while RB5 is currently LOW (i.e. post falling-edge of S1's first half).
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        h.step()

    before_tx = len(h.tx_frames())

    # Drive the RC5 pulse train: addr=0x10 (preset menu),
    # cmd=0x3A (V1.64b explicit standby endpoint).
    _drive_rc5_pulse_train(chain, addr=0x10, cmd=0x3A)

    # Settle in chunks so the foreground dispatch can consume the decoded
    # cmd and emit the standby frame.
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
# This locks in the hardware-validated stock-compatible ISR decoder path.
# All four V1.71 inline shortcuts must decode correctly from a real RB5
# Manchester pulse train, not only from inject_decoded_ir_event RAM pokes.
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
    the stock-compatible in-ISR decoder lands the expected value in
    ir_decoded_cmd / ir_decoded_addr.

    Exercises the full live pipeline:
      RB5 falling edge -> port-B IOC -> RBIF -> isr_entry ->
      ir_rc5_decode (bit-bang Manchester decode) ->
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
    # Settle long enough for decode + foreground dispatch to land cmd/addr.
    for _ in range(8):
        chain.step_ticks(1_000_000)

    decoded_cmd = chain.read_reg(0x01D)
    decoded_addr = chain.read_reg(0x01E)
    assert decoded_cmd == cmd, (
        f"{label} (cmd 0x{cmd:02X}): decoded_cmd=0x{decoded_cmd:02X}, "
        f"expected 0x{cmd:02X}.  Decoder bailed to error path (0xFF) "
        f"or never wrote cmd (0x00 / pre-warmup value).  Check the "
        f"stock in-ISR ir_rc5_decode path and RC5 pulse timing."
    )
    assert decoded_addr == 0x10, (
        f"{label} (cmd 0x{cmd:02X}): decoded_addr=0x{decoded_addr:02X}, "
        f"expected 0x10."
    )
