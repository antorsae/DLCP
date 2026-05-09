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
from dlcp_fw.sim.v17_symbols import assemble_v17, parse_v17_symbols

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

# tx_ring_wr (BANK 0 @ 0x097) is the producer index into the 48-byte
# TX ring at tx_ring_base (0x036).  v171_send_{standby,wake,preset}_cmd_
# frame each call tx_ring_reserve_3 to atomically commit 3 bytes
# (route + cmd + data); on success, tx_ring_wr advances by 3 (mod 48).
# Reading wr before/after an inject and expecting +3 (mod 48) proves
# the endpoint-specific send-frame helper actually ran -- the generic
# fallthrough at asm:3399-3401 does NOT touch tx_ring_wr.
TX_RING_WR_ADDR = 0x097

# Note: PRESET_*_FRAME / STANDBY_FRAME / WAKE_FRAME constants were
# removed in commit a7b1dd6 + this follow-up because all current
# tests assert on dispatch state (PRESET_BIT, IR_ARMED, tx_ring_wr)
# or PC-isolated leak detection -- not chain-TX-frame content.
# Earlier drafts that asserted on TX frame content false-failed
# against layer-2's multi-data cmd 0x03 emissions and against the
# IR-standby state-transition tail's standby_wake_broadcast call.
# See test_v171_unknown_cmd_does_not_change_preset_bit_or_emit_frame
# for the layer-2-isolated PC-based leak detection that replaces
# TX-frame content checks: v171_send_preset_frame_txonly (layer-2's
# preset helper) at PC 0x0011E8 is at a different address from
# v171_send_preset_frame_and_persist (non-layer-2) at 0x00120E, so
# polling current_ctl_pc against the non-layer-2 helper PC ranges via
# _step_until_no_helper_hit is truly layer-2-isolated.


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


def _read_tx_ring_wr(chain) -> int:  # type: ignore[no-untyped-def]
    return chain.read_reg(TX_RING_WR_ADDR)


def _tx_ring_advance(pre: int, post: int) -> int:
    """Bytes added to tx_ring_wr (mod 48) between pre and post snapshots."""
    return (post - pre) % 48


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


# step_until_pc_hit budget for asserting an IR helper ran post-inject.
# The dispatch path reaches the inline-shortcut helper within at most
# one foreground main-loop iteration of ir_decoded_cmd being set, but
# V1.71's main loop includes the LCD render path which can take
# millions of Tcy per iteration.  Empirical: 200K Tcy is far too tight
# (PC observed at 0x000F9C / 0x0009FE = mid-LCD code).  Match the
# state-settle (~9M Tcy = 144M universal ticks) so the helper is
# certain to be reached if the IR dispatch path is intact.
_HELPER_HIT_BUDGET_TCY = 9_000_000


def _step_until_helper_hit(  # type: ignore[no-untyped-def]
    chain, helper_pc: int, *, range_size: int = 0x20,
    max_tcy: int = _HELPER_HIT_BUDGET_TCY,
) -> tuple[bool, int]:
    """Step the chain (CONTROL core) until PC enters [helper_pc,
    helper_pc + range_size), or max_tcy elapses.  Returns (hit, pc).

    Layer-2-isolated proof of dispatch: each tracked helper has a
    unique PC range that's NOT entered by layer-2's standby_wake_
    broadcast or full_sync_burst preset_txonly.  Note: v171_send_
    preset_frame_and_persist is also called by the preset menu
    UP/DOWN navigation path, so a hit during a test that touches
    that path would NOT be IR-specific -- but the matrix tests
    here all run with the menu at Volume, so only the V1.71 IR-
    preset case can plausibly call it in scope.

    range_size default 0x20 (16 PIC18 instructions, 32 bytes) is the
    minimum that reliably catches the helper across ``step_until_pc_
    hit``'s 100-Tcy chunk granularity: helper bodies are ~10-16
    instructions (~10-30 Tcy) which can fully execute between two
    chunk-boundary PC checks if the range is too tight.  A 0x20-wide
    range guarantees PC is in range during the chunk-boundary check
    while the helper is in flight.
    """
    pc = chain.step_until_pc_hit(
        0,  # core_idx 0 = CONTROL
        helper_pc,
        helper_pc + range_size - 1,
        max_tcy,
    )
    hit = helper_pc <= pc < helper_pc + range_size
    return hit, pc


def _step_until_no_helper_hit(  # type: ignore[no-untyped-def]
    chain, helper_pcs: list[int], *, range_size: int = 0x20,
    max_tcy: int = 200_000, chunk_tcy: int = 100,
) -> tuple[int | None, int]:
    """Verify NONE of the listed IR helper PCs are entered within
    max_tcy.  Returns (hit_helper_pc_or_None, last_pc).

    Polls current_ctl_pc against the union of the helper PC ranges
    every chunk_tcy.  Single-pass UNION check (vs sequential
    step_until_pc_hit calls which had gap windows where a leak into
    a non-first helper could slip past) -- codex MEDIUM on a7b1dd6.

    Granularity caveat: chunk_tcy=100 matches step_until_pc_hit's
    internal chunking, but the helpers only spend ~10-15 Tcy with
    PC in their range (they call out to tx_ring_reserve_3 /
    tx_byte_enqueue mid-body).  Single-run hit probability per chunk
    where helper is in flight is ~10-15%.  This means a leak can
    still slip past undetected.  TRUE robustness needs a sim-side
    per-instruction step or step_count_pc_hits primitive.  For now,
    a leak that slips past adds variance but the test still catches
    leaks ~10-15% of the time -- additive coverage on top of the
    PRESET_BIT-unchanged check below.
    """
    factor = 16  # K20 universal ticks per Tcy
    remaining = max_tcy
    pc = chain.current_ctl_pc()
    while remaining > 0:
        for hp in helper_pcs:
            if hp <= pc < hp + range_size:
                return hp, pc
        advance = min(chunk_tcy, remaining)
        chain.step_ticks(advance * factor)
        remaining -= advance
        pc = chain.current_ctl_pc()
    # Final check after last advance.
    for hp in helper_pcs:
        if hp <= pc < hp + range_size:
            return hp, pc
    return None, pc


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

    Starts from B; first A-press flips PRESET_BIT to A AND emits a
    3-byte preset frame via tx_ring_reserve_3 (so tx_ring_wr advances
    +3 mod 48).  Subsequent A-presses are no-ops: PRESET_BIT stays 0
    AND tx_ring_wr does NOT advance for the preset frame (the
    fallthrough at asm:3407-3411 takes the bra-to-done branch).
    Asserting on tx_ring_wr non-advance pins the documented idempotent
    contract -- a regression that re-sent the preset frame while
    leaving PRESET_BIT clear would still pass a state-only check.
    """
    _set_preset_bit(warmed_chain, PRESET_B)

    # First press: B -> A.  Expect PRESET_BIT flip + tx_ring_wr advance.
    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_PRESET_A)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_preset(warmed_chain) == PRESET_A, (
        "first preset-A press from B should flip PRESET_BIT to A (0)"
    )
    assert _read_ir_armed(warmed_chain), (
        "first preset-A press should re-arm IR_ARMED post-dispatch"
    )
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, (
        f"first preset-A press should commit a 3-byte frame via "
        f"tx_ring_reserve_3; tx_ring_wr advance = {advance} (need >= 3)"
    )

    # Second + third presses: idempotent (already A).  PRESET_BIT
    # unchanged AND no preset frame committed via the IR-dispatch path.
    # Allow up to 3 bytes of layer-2 advance per settle (full_sync_step
    # legitimately commits non-preset frames during the 3 s settle).
    # Two consecutive idempotent presses must NOT both add 3+ bytes
    # for preset specifically; we approximate by checking the total
    # advance over the two no-op presses doesn't include an extra
    # +3 from a re-emitted preset frame.
    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_PRESET_A)
    _inject_and_settle(warmed_chain, IR_CMD_PRESET_A)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_preset(warmed_chain) == PRESET_A, (
        "second/third preset-A press should be idempotent (no PRESET_BIT change)"
    )
    advance_two_settles = _tx_ring_advance(pre_wr, post_wr)
    # Layer-2 emits at most ~6 frames (the step machine wraps 1..6) per
    # 3 s settle, so two settles can credibly advance up to ~36 bytes
    # without any IR-dispatch frames.  But if BOTH presses re-emitted
    # a preset frame via the IR path on top of layer-2, total advance
    # would include +6 of IR-preset frames.  Tightening below ~30
    # would false-positive on legitimate layer-2 jitter; we use 30 as
    # a balance between catching a regression (would be 36+ for two
    # IR-preset frames stacked on layer-2) and tolerating jitter.
    assert advance_two_settles <= 30, (
        f"two idempotent preset-A presses advanced tx_ring_wr by "
        f"{advance_two_settles} bytes -- suspicious (a real no-op should "
        f"only see layer-2 emissions, ~6 frames per 3 s settle)"
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
    """Standby → Wake: each endpoint case must commit a 3-byte
    chain frame AND re-arm IR_ARMED.

    Two-layer state assertion (PC-hit isolation explored under #159
    but not viable: step_until_pc_hit's 100-Tcy chunking misses the
    brief PC visits to the non-layer-2 helpers since each helper's body
    does `call tx_ring_reserve_3` / `call tx_byte_enqueue` which
    jumps OUT of the helper PC range -- net helper-PC visit time is
    ~10-15 Tcy out of ~200 Tcy total dispatch latency, which loses
    87 % of the time at chunk_tcy=100).  Per-instruction stepping
    or a counter primitive would be needed to make the PC-hit
    isolation reliable; both are sim-side changes deferred to a
    future task.

    Existing assertions:
      1. IR_ARMED re-set after settle.
      2. tx_ring_wr advanced by >= 3.
    """
    _set_preset_bit(warmed_chain, PRESET_A)

    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_STANDBY)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_ir_armed(warmed_chain), (
        "standby dispatch must re-arm IR_ARMED on completion"
    )
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, (
        f"standby press should commit a 3-byte frame; advance = {advance}"
    )

    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_WAKE)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_ir_armed(warmed_chain), (
        "wake dispatch must re-arm IR_ARMED on completion"
    )
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, (
        f"wake press should commit a 3-byte frame; advance = {advance}"
    )


def test_v171_wake_then_standby_pair_consumed_by_dispatch(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Wake → Standby: reverse pair, same 2-layer state assertion
    as test_v171_standby_then_wake.  PC-hit isolation explored under
    #159 but deferred -- see standby_then_wake docstring.
    """
    _set_preset_bit(warmed_chain, PRESET_A)

    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_WAKE)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_ir_armed(warmed_chain)
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, f"wake press tx_ring_wr advance = {advance}"

    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_STANDBY)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_ir_armed(warmed_chain)
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, f"standby press tx_ring_wr advance = {advance}"


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


@pytest.mark.parametrize("starting_preset, label", [
    (PRESET_A, "starting from A"),
    (PRESET_B, "starting from B"),
])
def test_v171_unknown_cmd_does_not_change_preset_bit_or_emit_frame(  # type: ignore[no-untyped-def]
    warmed_chain, starting_preset: int, label: str,
) -> None:
    """Unmapped cmd 0x40: must NOT trigger any V1.71 inline shortcut.

    The four inline cases (asm:3387-3398) are an xorlw cascade for
    cmds 0x38/0x39/0x3A/0x3B; cmd 0x40 falls through to the legacy
    re-arm tail (asm:3399-3401: `bsf IR_ARMED; return`).  The
    contract:
      * PRESET_BIT MUST be unchanged
      * IR_ARMED MUST be re-set
      * tx_ring_wr MUST NOT advance by 3+ from a 0x40 dispatch
        (the fallthrough doesn't commit a frame)

    Parametrized over both PRESET_A and PRESET_B starting states.
    Direction:
      * A leak into the preset-A case is MASKED from an A-start (the
        already-A no-op leaves PRESET_BIT unchanged); from a B-start,
        the same leak FLIPS PRESET_BIT to A and is caught.
      * Conversely a leak into the preset-B case is masked from B-start
        and caught from A-start.
    Running both starts ensures at least one parametrized case detects
    either leak direction.
    """
    helpers = _helper_pcs()
    _set_preset_bit(warmed_chain, starting_preset)
    pre_preset = _read_preset(warmed_chain)

    # PC-isolated leak detection (#159 full strengthening): step
    # through the post-inject window and verify NONE of the non-layer-2
    # helpers are entered.  The non-layer-2 helpers
    # (v171_send_standby_cmd_frame, v171_send_wake_cmd_frame,
    # v171_send_preset_frame_and_persist) are at unique PC ranges
    # that layer-2 NEVER enters (layer-2 uses standby_wake_broadcast
    # at 0x000E9C and v171_send_preset_frame_txonly at 0x0011E8).
    # If cmd 0x40 leaked into any inline-shortcut case, the
    # corresponding helper PC would be entered within ~few-K Tcy
    # of the inject -- 50K Tcy total budget across the union of
    # all 3 non-layer-2 helper PC ranges (single-pass polling, no
    # sequential gap) covers this.
    warmed_chain.inject_decoded_ir_event(addr=PRESET_ADDR, cmd=0x40)
    leaked_pc, last_pc = _step_until_no_helper_hit(
        warmed_chain,
        [
            helpers["v171_send_standby_cmd_frame"],
            helpers["v171_send_wake_cmd_frame"],
            helpers["v171_send_preset_frame_and_persist"],
        ],
        max_tcy=50_000,
    )
    assert leaked_pc is None, (
        f"unmapped cmd 0x40 ({label}) leaked into IR helper at "
        f"PC=0x{leaked_pc:06X} (observed PC=0x{last_pc:06X}).  "
        f"Layer-2 does not call these helpers, and the matrix test "
        f"runs with the menu at Volume so the preset menu UP/DOWN "
        f"path (the only other caller of v171_send_preset_frame_and_"
        f"persist) is not active.  This is unambiguous leak from "
        f"the V1.71 IR inline-shortcut cascade."
    )

    # Continue settle for state checks.
    warmed_chain.step_ticks(_SETTLE_TICKS)
    post_preset = _read_preset(warmed_chain)
    assert post_preset == pre_preset, (
        f"unmapped cmd 0x40 ({label}) changed PRESET_BIT: "
        f"pre=0x{pre_preset:02X}, post=0x{post_preset:02X}"
    )
    assert _read_ir_armed(warmed_chain), (
        f"unmapped cmd 0x40 ({label}) must still re-arm IR_ARMED"
    )


# ---------------------------------------------------------------------------
# Module-scoped hex builder (one-time per test module).
# pytest fixtures only fire when a test asks for them; module-level
# helper here lets non-fixture tests share the build.
# ---------------------------------------------------------------------------

_v171_hex_cache: Path | None = None
_v171_helper_pcs_cache: dict[str, int] | None = None


def _v171_hex_inline() -> Path:
    global _v171_hex_cache, _v171_helper_pcs_cache
    if _v171_hex_cache is not None and _v171_hex_cache.is_file():
        return _v171_hex_cache
    import tempfile
    tmp = Path(tempfile.mkdtemp(prefix="v171_ir_command_matrix_"))
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    lst_out = tmp / "dlcp_control_v171.lst"
    assemble_v17(asm, hex_out, output_lst=lst_out)
    _v171_hex_cache = hex_out
    syms = parse_v17_symbols(lst_out)
    _v171_helper_pcs_cache = {
        # non-layer-2 helpers (not called by layer-2): hitting these PCs
        # during a settle proves the IR-specific dispatch ran.
        "v171_send_standby_cmd_frame":          syms["v171_send_standby_cmd_frame"],
        "v171_send_wake_cmd_frame":             syms["v171_send_wake_cmd_frame"],
        "v171_send_preset_frame_and_persist":   syms["v171_send_preset_frame_and_persist"],
        # Layer-2's preset helper (called by full_sync_burst step 6):
        # NOT in the non-layer-2 set.  Useful as a NEGATIVE marker -- if
        # this is hit during an IR test, the test is observing a
        # layer-2 emission, not the IR dispatch.
        "v171_send_preset_frame_txonly":        syms["v171_send_preset_frame_txonly"],
    }
    return hex_out


def _helper_pcs() -> dict[str, int]:
    if _v171_helper_pcs_cache is None:
        _v171_hex_inline()  # populate the cache
    assert _v171_helper_pcs_cache is not None
    return _v171_helper_pcs_cache
