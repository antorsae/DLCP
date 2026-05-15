"""Known user-visible desync bugs in the V1.71 CONTROL + 2x V3.2 MAIN pair.

These tests intentionally pin current firmware failures rather than
source contracts.  They use the rust three-core chain so each failure is
observable at the same boundary an operator sees: LCD state, MAIN
standby counters, and active preset bits.
"""

from __future__ import annotations

import pytest

from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain

    _RUST_OK = True
    _RUST_ERR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_OK = False
    _RUST_ERR = exc


CONTROL_FLAGS = 0x01F
CONTROL_PRESET_BIT = 6
DISPLAY_STATE_INDEX = 0x0BF
TX_RING_RD = 0x096
TX_RING_WR = 0x097
V171_TX_SATURATE_COUNT = 0x1AD

MAIN_ACTIVE_FLAGS = 0x05E
MAIN_ACTIVE_PRESET_MASK = 0x04
MAIN_ACTIVE_GATE_MASK = 0x08
MAIN_DIAG_STANDBY = 0x2E7
MAIN_PRESET_JOB_STATE = 0x2DE
MAIN_PRESET_JOB_TARGET = 0x2DF

PRESET_IR_ADDR = 0x10
IR_PRESET_A = 0x38
IR_PRESET_B = 0x39
IR_STANDBY = 0x3A
IR_WAKE = 0x3B

PRESET_JOB_IDLE = 0
PRESET_JOB_APPLY = 3


def _require_runtime() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust dlcp_sim_native facade not importable: {_RUST_ERR!r}")
    if not V171_CONTROL_HEX.exists():
        pytest.skip(f"missing canonical V1.71 CONTROL hex: {V171_CONTROL_HEX}")
    if not V32_MAIN_HEX.exists():
        pytest.skip(f"missing canonical V3.2 MAIN hex: {V32_MAIN_HEX}")


def _boot_chain():
    _require_runtime()
    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chunks = chain.run_until_connected(limit=400)
    assert chunks < 400, f"chain did not reach Volume display; lcd={chain.lcd_lines()!r}"
    assert "Volume:" in chain.lcd_lines()[0]
    return chain


def _tap_control_pin(chain, port: str, bit: int) -> None:
    """Short active-low panel tap, avoiding the facade's long auto-repeat hold."""
    chain.set_control_pin(port, bit, False)
    chain.step_ticks(5_000_000)
    chain.set_control_pin(port, bit, True)
    chain.step_ticks(5_000_000)


def _main_preset_bits(chain) -> tuple[int, int]:
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_PRESET_MASK) >> 2
        for unit in (0, 1)
    )


def _main_active_gates(chain) -> tuple[int, int]:
    return tuple(
        (chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS) & MAIN_ACTIVE_GATE_MASK) >> 3
        for unit in (0, 1)
    )


def _main_job_states(chain) -> tuple[int, int]:
    return tuple(chain.read_main_reg(unit, MAIN_PRESET_JOB_STATE) for unit in (0, 1))


def _wait_until(chain, predicate, *, ticks: int = 1_000_000, attempts: int = 500) -> None:
    for _ in range(attempts):
        if predicate():
            return
        chain.step_ticks(ticks)
    pytest.fail(
        f"predicate did not converge after {attempts * ticks} ticks; "
        f"lcd={chain.lcd_lines()!r} states={_main_job_states(chain)} "
        f"preset_bits={_main_preset_bits(chain)}"
    )


def _inject_ir(chain, cmd: int) -> None:
    chain.inject_decoded_ir_event(addr=PRESET_IR_ADDR, cmd=cmd)
    chain.step_ticks(5_000_000)


def _set_control_preset_bit(chain, value: int) -> None:
    flags = chain.read_reg(CONTROL_FLAGS)
    mask = 1 << CONTROL_PRESET_BIT
    if value:
        flags |= mask
    else:
        flags &= ~mask
    chain.write_reg(CONTROL_FLAGS, flags & 0xFF)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_preset_screen_stby_tap_sends_both_mains_to_standby() -> None:
    chain = _boot_chain()

    _tap_control_pin(chain, "A", 4)  # RIGHT: Volume -> Preset
    assert chain.read_reg(DISPLAY_STATE_INDEX) == 1
    assert chain.lcd_lines()[0].startswith("Preset")

    before_standby = tuple(chain.read_main_reg(unit, MAIN_DIAG_STANDBY) for unit in (0, 1))
    _tap_control_pin(chain, "A", 3)  # STBY
    chain.step_many(20)

    assert "ZZZ" in chain.lcd_lines()[0].upper(), (
        f"CONTROL should render standby after STBY tap; lcd={chain.lcd_lines()!r}"
    )
    for unit in (0, 1):
        after = chain.read_main_reg(unit, MAIN_DIAG_STANDBY)
        assert after > before_standby[unit], (
            f"MAIN{unit} did not receive standby from Preset screen STBY tap: "
            f"diag_s before={before_standby[unit]} after={after}; "
            f"lcd={chain.lcd_lines()!r}"
        )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_explicit_ir_standby_updates_control_lcd_state() -> None:
    chain = _boot_chain()

    before_frames = len(chain.tx_frames())
    _inject_ir(chain, IR_STANDBY)

    assert (0xB0, 0x03, 0x00) in chain.tx_frames()[before_frames:], (
        f"CONTROL did not emit explicit IR standby frame; "
        f"new_frames={chain.tx_frames()[before_frames:]!r}"
    )
    assert _main_active_gates(chain) == (0, 0), (
        f"both MAINs should close their active gates after explicit IR standby; "
        f"active_gates={_main_active_gates(chain)} "
        f"flags={[hex(chain.read_main_reg(unit, MAIN_ACTIVE_FLAGS)) for unit in (0, 1)]}"
    )

    for _ in range(50):
        if "ZZZ" in chain.lcd_lines()[0].upper():
            break
        chain.step_many(5)

    assert "ZZZ" in chain.lcd_lines()[0].upper(), (
        f"CONTROL LCD stayed out of standby after IR 0x3A; lcd={chain.lcd_lines()!r} "
        f"control_flags=0x{chain.read_reg(CONTROL_FLAGS):02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_explicit_ir_wake_returns_control_lcd_to_volume() -> None:
    chain = _boot_chain()

    chain.press("STBY")
    assert "ZZZ" in chain.lcd_lines()[0].upper(), (
        f"panel STBY precondition failed; lcd={chain.lcd_lines()!r}"
    )
    before_frames = len(chain.tx_frames())
    _inject_ir(chain, IR_WAKE)

    assert (0xB0, 0x03, 0x01) in chain.tx_frames()[before_frames:], (
        f"CONTROL did not emit explicit IR wake frame; "
        f"new_frames={chain.tx_frames()[before_frames:]!r}"
    )
    _wait_until(chain, lambda: _main_active_gates(chain) == (1, 1), attempts=1000)

    chunks = chain.run_until_connected(limit=200)
    assert chunks < 200 and "Volume:" in chain.lcd_lines()[0], (
        f"CONTROL LCD did not return to Volume after IR 0x3B wake; "
        f"chunks={chunks} lcd={chain.lcd_lines()!r} "
        f"control_flags=0x{chain.read_reg(CONTROL_FLAGS):02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_ir_preset_b_tx_saturation_does_not_change_local_preset_state() -> None:
    chain = _boot_chain()
    _set_control_preset_bit(chain, 0)
    chain.write_reg(V171_TX_SATURATE_COUNT, 0)

    # Leave only two free slots in the 48-byte CONTROL TX ring, so the
    # atomic 3-byte reserve in v171_send_preset_frame_txonly must abort.
    chain.write_reg(TX_RING_RD, 0x00)
    chain.write_reg(TX_RING_WR, 0x2D)

    before_frames = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=PRESET_IR_ADDR, cmd=IR_PRESET_B)
    chain.step_ticks(5_000_000)

    new_frames = chain.tx_frames()[before_frames:]
    assert (0xB0, 0x20, 0x01) not in new_frames, (
        f"precondition failed: saturated TX ring still emitted preset B frame: {new_frames!r}"
    )
    assert chain.read_reg(V171_TX_SATURATE_COUNT) > 0, (
        "precondition failed: tx_ring_reserve_3 did not record saturation"
    )

    preset_bit = (chain.read_reg(CONTROL_FLAGS) >> CONTROL_PRESET_BIT) & 0x01
    assert preset_bit == 0, (
        f"CONTROL changed local PRESET_BIT even though preset B frame was not emitted; "
        f"control_flags=0x{chain.read_reg(CONTROL_FLAGS):02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_rapid_preset_reversal_during_apply_finishes_on_latest_target() -> None:
    chain = _boot_chain()
    chain.step_ticks(50_000_000)

    chain.inject_decoded_ir_event(addr=PRESET_IR_ADDR, cmd=IR_PRESET_B)
    _wait_until(
        chain,
        lambda: (
            PRESET_JOB_APPLY in _main_job_states(chain)
            and 1 in _main_preset_bits(chain)
        ),
        ticks=100_000,
        attempts=1000,
    )

    _inject_ir(chain, IR_PRESET_A)
    _wait_until(chain, lambda: _main_job_states(chain) == (PRESET_JOB_IDLE, PRESET_JOB_IDLE))

    control_target = (chain.read_reg(CONTROL_FLAGS) >> CONTROL_PRESET_BIT) & 0x01
    main_targets = tuple(chain.read_main_reg(unit, MAIN_PRESET_JOB_TARGET) for unit in (0, 1))
    assert control_target == 0, f"precondition failed: CONTROL did not request preset A"
    assert main_targets == (0, 0), f"precondition failed: MAIN targets are {main_targets}"
    assert _main_preset_bits(chain) == (0, 0), (
        f"rapid B->A reversal finished with MAINs on wrong preset: "
        f"bits={_main_preset_bits(chain)} states={_main_job_states(chain)} "
        f"targets={main_targets} control_flags=0x{chain.read_reg(CONTROL_FLAGS):02X}"
    )
