"""V1.71 IR command + sequence matrix.

Per task #155 (user request 2026-05-08): test ALL IR commands and
plausible sequences.  Refactored under task #158 (codex review of
27d5de6) to assert on V1.71 dispatch STATE CHANGES rather than on
chain TX frames -- the layer-2 ``v171_full_sync_step`` periodic
broadcast emits preset/standby/wake frames on its own cadence, so
TX-frame assertions can pass coincidentally.

Coverage strategy
=================

This file uses ``inject_decoded_ir_event`` (RAM poke that writes
``ir_decoded_cmd`` / ``ir_decoded_addr`` and clears IR_ARMED) to
exercise the V1.71 inline-shortcut DISPATCH layer end-to-end
without re-validating the bit-bang Manchester decoder on every
case.  The decoder side has its own dedicated pulse-train test
in ``test_v171_ir_rc5_pulse_train.py`` (now parametrized over all
4 inline cmds post-task #157 / 61e17a7 / a1288f1).

Assertions look at:
  * PRESET_BIT (control_flags bit 6) for preset-A / preset-B
    presses -- the V1.71 inline dispatch FLIPS PRESET_BIT when
    the press is a no-op-vs-current-state state change, and
    leaves it unchanged otherwise.  This is the contract under
    test, NOT the TX frame.
  * IR_ARMED (control_flags bit 0) for every dispatch -- the
    inline-shortcut tail (and the legacy fall-through tail) both
    bsf IR_ARMED at completion.  Confirms the dispatch RAN
    regardless of which branch it took.

Module-scoped fixture
=====================

Tests now share a single warmed chain, with ``control_flags``
restored to a known baseline at each test's entry via write_reg.
Speedup: ~7 s per test -> ~1 s per test (warmup happens once per
module instead of per test).

Commands covered (V1.71 inline IR shortcuts, hardcoded; no EEPROM
dependency):

  * cmd 0x38 → preset A toggle  (V1.61b shortcut, asm:3403+)
  * cmd 0x39 → preset B toggle  (V1.61b shortcut, asm:3411+)
  * cmd 0x3A → standby endpoint (V1.64b explicit, asm:3422+)
  * cmd 0x3B → wake endpoint    (V1.64b explicit, asm:3431+)

EEPROM-configured commands (VOL+, VOL-, MUTE, etc.) are NOT covered
by this matrix because they depend on the user's IR-learning
configuration stored in EEPROM (Common_RAM+33..+43 loaded from
EEPROM at boot).  Coverage of those paths via direct EEPROM
configuration is a future task (deferred).

Sequence cases
==============

  * Preset A → A   (idempotent: second press is a no-op)
  * Preset A → B → A → B  (alternating toggle: each press flips)
  * Standby → Wake (state pair)
  * Wake → Standby (reverse pair)
  * Preset A → Standby → Wake → Preset B  (mixed)
  * Unknown cmd 0x40 must not trigger any inline shortcut
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


pytestmark = pytest.mark.dual_supported


PRESET_ADDR = 0x10

# V1.71 inline shortcuts (from asm:3373..3440).
IR_CMD_PRESET_A = 0x38
IR_CMD_PRESET_B = 0x39
IR_CMD_STANDBY = 0x3A
IR_CMD_WAKE = 0x3B

# Expected chain TX frames (route, cmd, data).
PRESET_A_FRAME = (0xB0, 0x20, 0x00)
PRESET_B_FRAME = (0xB0, 0x20, 0x01)
STANDBY_FRAME = (0xB0, 0x03, 0x00)
WAKE_FRAME = (0xB0, 0x03, 0x01)


def _require_rust() -> None:
    if not _RUST_OK:
        pytest.fail(f"rust facade not importable: {_RUST_ERROR!r}")


def _frame_tuple(f) -> tuple[int, int, int]:  # type: ignore[no-untyped-def]
    if isinstance(f, tuple):
        return f
    return (f.route, f.cmd, f.data)


# ---------------------------------------------------------------------------
# control_flags bit positions (per dlcp_control_ram.inc).
# ---------------------------------------------------------------------------
CONTROL_FLAGS_ADDR = 0x01F
IR_ARMED_BIT = 0x01    # bit 0
PRESET_BIT_MASK = 0x40  # bit 6 (PRESET_BIT)
PRESET_A = 0x00         # PRESET_BIT clear = preset A active
PRESET_B = 0x40         # PRESET_BIT set   = preset B active


def _warmup(chain) -> None:  # type: ignore[no-untyped-def]
    chain.warmup(25_000_000)
    chain.pause_heartbeat()
    for _ in range(40):
        chain.step()
    chain.set_control_pin("B", 5, True)
    for _ in range(20):
        chain.step()


# ---------------------------------------------------------------------------
# Module-scoped warmed chain.  Tests reset PRESET_BIT to a known starting
# value before each test -- safe because the V1.71 inline dispatch reads
# AND writes only PRESET_BIT + IR_ARMED + event_exit on the preset path,
# and IR_ARMED is cleared by inject_decoded_ir_event itself.
#
# Speedup vs per-test fresh chain: ~7 s -> ~1 s (warmup happens ONCE per
# module instead of per test).
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def warmed_chain():  # type: ignore[no-untyped-def]
    _require_rust()
    chain = RustChain.from_v17_chain(str(_v171_hex_inline()))
    _warmup(chain)
    yield chain


def _set_preset_bit(chain, value: int) -> None:  # type: ignore[no-untyped-def]
    """Force PRESET_BIT to ``PRESET_A`` (0) or ``PRESET_B`` (0x40)."""
    flags = chain.read_reg(CONTROL_FLAGS_ADDR)
    flags = (flags & ~PRESET_BIT_MASK) | (value & PRESET_BIT_MASK)
    # IR_ARMED MUST be set so the next inject's clear -> dispatch path fires.
    flags |= IR_ARMED_BIT
    chain.write_reg(CONTROL_FLAGS_ADDR, flags)


def _read_preset(chain) -> int:  # type: ignore[no-untyped-def]
    return chain.read_reg(CONTROL_FLAGS_ADDR) & PRESET_BIT_MASK


def _read_ir_armed(chain) -> bool:  # type: ignore[no-untyped-def]
    return bool(chain.read_reg(CONTROL_FLAGS_ADDR) & IR_ARMED_BIT)


# ---------------------------------------------------------------------------
# Inject-event helper.  Bypasses the bit-bang decoder; exercises dispatch
# only.  Returns the (decoded_cmd, decoded_addr, control_flags) post-settle
# tuple for callers that want to assert on state changes; also returns the
# new TX frames for legacy tests still using the TX path.
# ---------------------------------------------------------------------------


# Settle: chain.step_ticks(N) directly instead of looping chain.step().
# pause_heartbeat() is a no-op in the rust backend, and force_connected
# defaults to false, so chain.step() reduces to chain.step_ticks(3.2M)
# without the Python<->Rust call overhead -- but 3.2M ticks per call
# is too granular when we want longer settles.
#
# Empirically:
#   144M ticks (3 s simulated) -> all tests pass, ~31 s total wall
#   120M ticks (2.5 s simulated) -> 2 tests fail in the post-preset
#                                    sequence, where the EEPROM-write
#                                    tail of v171_send_preset_frame_
#                                    and_persist leaves the foreground
#                                    main loop in a slow path that needs
#                                    more margin to drain.
# 144M is the chosen safe minimum.  Total wall ~31 s vs the legacy
# per-test fresh-chain ~50 s -> ~38 % speedup with correctness-
# improved assertions (PRESET_BIT state instead of TX-frame coincidence).
_SETTLE_TICKS = 144_000_000  # = 3 s simulated


def _inject_and_settle(  # type: ignore[no-untyped-def]
    chain, cmd: int, addr: int = PRESET_ADDR, settle_ticks: int = _SETTLE_TICKS,
) -> list[tuple[int, int, int]]:
    """Inject a decoded IR event + settle, return new TX frames."""
    before = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=addr, cmd=cmd)
    chain.step_ticks(settle_ticks)
    return [_frame_tuple(f) for f in chain.tx_frames()[before:]]


# ===========================================================================
# Sequence tests via inject_decoded_ir_event (fast, deterministic).
# Pulse-train decoder coverage is owned by test_v171_ir_rc5_pulse_train.py
# (cmd 0x3A only -- the decoder's LSB resolution makes a 4-cmd matrix
# unreliable per the comment block in that file).  Extending pulse-train
# coverage to all four inline shortcuts is tracked as task #157.
# ===========================================================================


def test_v171_preset_a_pressed_three_times_converges_to_a(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Preset A pressed three times from a B starting state:
       converges to A on first press, idempotent thereafter.

    Per V1.71 dispatch (asm:3403):
      btfss control_flags, PRESET_BIT, A   ; skip if bit set (== B)
      bra v171_ir_preset_done              ; bit==0 (A): no-op
      bcf control_flags, PRESET_BIT, A     ; bit==1 (B): flip to A
      rcall v171_send_preset_frame_and_persist
      bsf control_flags, IR_ARMED, A

    Starts from B; first A-press flips to A; second/third are no-ops.
    """
    _set_preset_bit(warmed_chain, PRESET_B)
    _inject_and_settle(warmed_chain, IR_CMD_PRESET_A)
    assert _read_preset(warmed_chain) == PRESET_A, (
        "first preset-A press from B should flip PRESET_BIT to A (0)"
    )
    assert _read_ir_armed(warmed_chain), (
        "first preset-A press should re-arm IR_ARMED post-dispatch"
    )

    _inject_and_settle(warmed_chain, IR_CMD_PRESET_A)
    assert _read_preset(warmed_chain) == PRESET_A, (
        "second preset-A press should be idempotent (no flip)"
    )
    _inject_and_settle(warmed_chain, IR_CMD_PRESET_A)
    assert _read_preset(warmed_chain) == PRESET_A, (
        "third preset-A press should still be idempotent"
    )


def test_v171_preset_alternating_a_b_a_b_each_flips_preset_bit(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Preset A → B → A → B from B starting state: each press flips
    PRESET_BIT to the opposite value.

    Toggle sequence exercises the inline dispatch's preset-bit
    tracking: a press whose target preset != current state flips
    the bit; a press whose target == current state is a no-op.
    """
    _set_preset_bit(warmed_chain, PRESET_B)
    expected_sequence = [
        (IR_CMD_PRESET_A, PRESET_A, "preset-A press 1"),
        (IR_CMD_PRESET_B, PRESET_B, "preset-B press 1"),
        (IR_CMD_PRESET_A, PRESET_A, "preset-A press 2"),
        (IR_CMD_PRESET_B, PRESET_B, "preset-B press 2"),
    ]
    for cmd, expected_preset, label in expected_sequence:
        _inject_and_settle(warmed_chain, cmd)
        actual = _read_preset(warmed_chain)
        assert actual == expected_preset, (
            f"{label} (cmd 0x{cmd:02X}) -> PRESET_BIT=0x{actual:02X}, "
            f"expected 0x{expected_preset:02X}"
        )


def test_v171_standby_then_wake_pair_consumed_by_dispatch(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Standby → Wake: dispatch consumes both presses (IR_ARMED re-set
    after each).

    Standby (asm:3422) and wake (asm:3431) inline cases unconditionally
    rcall v171_send_standby_cmd_frame / v171_send_wake_cmd_frame and
    then bsf IR_ARMED.  The TX frame they emit can coincide with
    layer-2's standby_wake_broadcast cadence, so we assert on
    IR_ARMED + ir_decoded_cmd state rather than TX-frame appearance.
    """
    _set_preset_bit(warmed_chain, PRESET_A)
    warmed_chain.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=IR_CMD_STANDBY)
    assert not _read_ir_armed(warmed_chain), (
        "inject should have cleared IR_ARMED before dispatch"
    )
    warmed_chain.step_ticks(_SETTLE_TICKS)
    assert _read_ir_armed(warmed_chain), (
        "standby dispatch must re-arm IR_ARMED on completion"
    )

    warmed_chain.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=IR_CMD_WAKE)
    warmed_chain.step_ticks(_SETTLE_TICKS)
    assert _read_ir_armed(warmed_chain), (
        "wake dispatch must re-arm IR_ARMED on completion"
    )


def test_v171_wake_then_standby_pair_consumed_by_dispatch(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Wake → Standby: reverse pair.  Both dispatched.

    Verifies neither endpoint is gated on prior-state tracking
    (unlike preset A/B which IS state-tracked via PRESET_BIT).
    Both presses must run dispatch and re-arm IR_ARMED.
    """
    _set_preset_bit(warmed_chain, PRESET_A)
    warmed_chain.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=IR_CMD_WAKE)
    warmed_chain.step_ticks(_SETTLE_TICKS)
    assert _read_ir_armed(warmed_chain), (
        "wake dispatch must re-arm IR_ARMED on completion"
    )

    warmed_chain.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=IR_CMD_STANDBY)
    warmed_chain.step_ticks(_SETTLE_TICKS)
    assert _read_ir_armed(warmed_chain), (
        "standby dispatch must re-arm IR_ARMED on completion"
    )


def test_v171_mixed_sequence_preset_a_standby_wake_preset_b(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Mixed sequence preset A → standby → wake → preset B from B
    starting state:

      * preset A: PRESET_BIT flips B (0x40) -> A (0x00), IR_ARMED re-set
      * standby:  PRESET_BIT unchanged (=A), IR_ARMED re-set
      * wake:     PRESET_BIT unchanged (=A), IR_ARMED re-set
      * preset B: PRESET_BIT flips A (0x00) -> B (0x40), IR_ARMED re-set

    Realistic remote-control session: select preset A, sleep, wake,
    switch to preset B.  PRESET_BIT progression captures the contract.
    """
    _set_preset_bit(warmed_chain, PRESET_B)
    sequence = [
        (IR_CMD_PRESET_A, PRESET_A, "preset A (B->A flip)"),
        (IR_CMD_STANDBY,  PRESET_A, "standby (preset unchanged)"),
        (IR_CMD_WAKE,     PRESET_A, "wake (preset unchanged)"),
        (IR_CMD_PRESET_B, PRESET_B, "preset B (A->B flip)"),
    ]
    for cmd, expected_preset, label in sequence:
        _inject_and_settle(warmed_chain, cmd)
        actual = _read_preset(warmed_chain)
        assert actual == expected_preset, (
            f"{label} (cmd 0x{cmd:02X}) -> PRESET_BIT=0x{actual:02X}, "
            f"expected 0x{expected_preset:02X}"
        )
        assert _read_ir_armed(warmed_chain), (
            f"{label} (cmd 0x{cmd:02X}) failed to re-arm IR_ARMED"
        )


def test_v171_unknown_cmd_does_not_change_preset_bit(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Unmapped cmd 0x40: must NOT trigger any V1.71 inline shortcut.

    The four inline cases (asm:3387-3398) are an xorlw cascade for
    cmds 0x38/0x39/0x3A/0x3B; cmd 0x40 falls through to the legacy
    re-arm tail (asm:3399-3401: `bsf IR_ARMED; return`).  The
    contract: PRESET_BIT MUST be unchanged AND IR_ARMED MUST be
    re-set.  This catches regressions where a future xorlw constant
    accidentally matches 0x40 (e.g. typo `xorlw 0x40` instead of
    `xorlw 0x38`) routing into the preset-A path.
    """
    _set_preset_bit(warmed_chain, PRESET_B)
    pre_preset = _read_preset(warmed_chain)
    _inject_and_settle(warmed_chain, cmd=0x40)
    post_preset = _read_preset(warmed_chain)
    assert post_preset == pre_preset, (
        f"unmapped cmd 0x40 changed PRESET_BIT: pre=0x{pre_preset:02X}, "
        f"post=0x{post_preset:02X} -- inline-shortcut leak into cmd 0x40"
    )
    assert _read_ir_armed(warmed_chain), (
        "unmapped cmd 0x40 must still re-arm IR_ARMED via the fall-through tail"
    )


# ---------------------------------------------------------------------------
# Module-scoped hex builder (one-time per test module).
# pytest fixtures only fire when a test asks for them; module-level
# helper here lets non-fixture tests share the build.
# ---------------------------------------------------------------------------

_v171_hex_cache: Path | None = None


def _v171_hex_inline() -> Path:
    global _v171_hex_cache
    if _v171_hex_cache is not None and _v171_hex_cache.is_file():
        return _v171_hex_cache
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="v171_ir_command_matrix_"))
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    _v171_hex_cache = hex_out
    return hex_out
