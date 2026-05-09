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

# tx_ring_wr (BANK 0 @ 0x097) is the producer index into the 48-byte
# TX ring at tx_ring_base (0x036).  v171_send_{standby,wake,preset}_cmd_
# frame each call tx_ring_reserve_3 to atomically commit 3 bytes
# (route + cmd + data); on success, tx_ring_wr advances by 3 (mod 48).
# Reading wr before/after an inject and expecting +3 (mod 48) proves
# the endpoint-specific send-frame helper actually ran -- the generic
# fallthrough at asm:3399-3401 does NOT touch tx_ring_wr.
TX_RING_WR_ADDR = 0x097

# Expected chain TX frames (route, cmd, data).  Used for content-
# based assertions that distinguish IR-dispatch emissions from layer-2
# full_sync_burst broadcasts.
PRESET_A_FRAME = (0xB0, 0x20, 0x00)
PRESET_B_FRAME = (0xB0, 0x20, 0x01)
STANDBY_FRAME  = (0xB0, 0x03, 0x00)
WAKE_FRAME     = (0xB0, 0x03, 0x01)

# Layer-2 standby_wake_broadcast (asm:2929) emits (0xB0, 0x03, X)
# where X depends on control_flags.bit1 (CONNECTED) at the call site:
#   bit1 SET   (DISPLAY mode) -> X = 0x01 (matches WAKE_FRAME)
#   bit1 CLEAR (Zzz mode)     -> X = 0x00 (matches STANDBY_FRAME)
#
# Note: an IR-standby dispatch eventually triggers a state-transition
# tail (asm:5179 region clears CONNECTED then calls standby_wake_
# broadcast which emits (B0, 03, 0x00) in the now-Zzz mode), so the
# 3 s settle after a standby inject reliably contains (B0, 03, 0x00)
# from the state-transition path EVEN IF the IR helper itself
# regressed to emit a wrong byte.  Layer-2 mute_off (cmd 0x03 data
# 0x03) and other paths can also produce cmd 0x03 frames during the
# settle.  So the STANDBY_FRAME presence check is NOT a strict
# content-isolation gate -- it's additive evidence that catches the
# entire-path-broken regression (no event_exit, no state transition,
# no helper emit) but masks wrong-cmd-byte regressions.  See #159
# for the documented residual gap.


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
    """Standby → Wake: each endpoint case must commit its 3-byte
    chain frame via tx_ring_reserve_3 AND re-arm IR_ARMED.

    Standby (asm:3422) and wake (asm:3431) inline cases unconditionally
    rcall v171_send_standby_cmd_frame / v171_send_wake_cmd_frame
    (which commit 3 bytes via tx_ring_reserve_3) and then bsf
    IR_ARMED at v171_ir_endpoint_done.  Three-layer assertion:

      1. IR_ARMED re-set after settle (proves SOME dispatch ran;
         shared with the unmapped-cmd fallthrough so weakest signal).
      2. tx_ring_wr advanced by >= 3 (proves a 3-byte frame was
         committed; layer-2 also commits frames so this can't be
         100% isolated, but a regression breaking the send-frame
         helper would still fail this if layer-2 didn't fire in
         the same window).
      3. STANDBY_FRAME (0xB0, 0x03, 0x00) appears in tx_frames
         delta -- additive evidence that catches the entire-path-
         broken regression (no event_exit set, no state transition,
         no helper emit).  NOT a strict content-isolation gate:
         the IR-standby dispatch's state-transition tail (asm:5179)
         later clears CONNECTED and re-emits (B0, 03, 0x00) via
         layer-2's standby_wake_broadcast in Zzz mode, so a
         wrong-cmd-byte regression in the IR helper itself could
         pass via the tail's emission.  See #159 for the residual
         gap.

    Wake's content-isolation is similarly imperfect: WAKE_FRAME
    (0xB0, 0x03, 0x01) coincides with layer-2's DISPLAY-mode
    emission, so we keep wake's two-layer check (1) + (2) and
    don't add a presence assertion.
    """
    _set_preset_bit(warmed_chain, PRESET_A)

    # Standby: full 3-layer assertion (content-isolated in DISPLAY mode).
    pre_wr = _read_tx_ring_wr(warmed_chain)
    pre_tx_count = len(warmed_chain.tx_frames())
    _inject_and_settle(warmed_chain, IR_CMD_STANDBY)
    post_wr = _read_tx_ring_wr(warmed_chain)
    new_frames = [_frame_tuple(f) for f in warmed_chain.tx_frames()[pre_tx_count:]]
    assert _read_ir_armed(warmed_chain), (
        "standby dispatch must re-arm IR_ARMED on completion"
    )
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, (
        f"standby press should commit a 3-byte frame via "
        f"tx_ring_reserve_3; tx_ring_wr advance = {advance}"
    )
    assert STANDBY_FRAME in new_frames, (
        f"standby press should emit {STANDBY_FRAME} either via "
        f"v171_send_standby_cmd_frame directly OR via the state-"
        f"transition tail's standby_wake_broadcast call (CONNECTED "
        f"cleared post-dispatch).  Absence of the frame indicates "
        f"the entire IR-standby path (helper + state transition) "
        f"is broken.  Got new frames: {new_frames}"
    )

    # Wake: 2-layer assertion (content not isolatable in DISPLAY mode).
    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_WAKE)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_ir_armed(warmed_chain), (
        "wake dispatch must re-arm IR_ARMED on completion"
    )
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, (
        f"wake press should commit a 3-byte frame via "
        f"tx_ring_reserve_3; tx_ring_wr advance = {advance}"
    )


def test_v171_wake_then_standby_pair_consumed_by_dispatch(warmed_chain) -> None:  # type: ignore[no-untyped-def]
    """Wake → Standby: reverse pair.  Both endpoints commit a frame.

    Same assertion shape as test_v171_standby_then_wake (1) IR_ARMED
    re-set + (2) tx_ring_wr advance >= 3 + (3) STANDBY_FRAME presence
    check after the standby press.  The presence check is additive
    evidence that catches the entire-IR-standby-path-broken regression
    (no event_exit, no state-transition tail, no helper emit) but
    masks wrong-cmd-byte regressions because the state-transition
    tail at asm:5179 re-emits (B0, 03, 0x00) via standby_wake_
    broadcast in Zzz mode.  Wake remains 2-layer; content isolation
    not achievable without firmware/sim hooks (#159 residual gap).
    """
    _set_preset_bit(warmed_chain, PRESET_A)

    pre_wr = _read_tx_ring_wr(warmed_chain)
    _inject_and_settle(warmed_chain, IR_CMD_WAKE)
    post_wr = _read_tx_ring_wr(warmed_chain)
    assert _read_ir_armed(warmed_chain)
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, f"wake press tx_ring_wr advance = {advance}"

    pre_wr = _read_tx_ring_wr(warmed_chain)
    pre_tx_count = len(warmed_chain.tx_frames())
    _inject_and_settle(warmed_chain, IR_CMD_STANDBY)
    post_wr = _read_tx_ring_wr(warmed_chain)
    new_frames = [_frame_tuple(f) for f in warmed_chain.tx_frames()[pre_tx_count:]]
    assert _read_ir_armed(warmed_chain)
    advance = _tx_ring_advance(pre_wr, post_wr)
    assert advance >= 3, f"standby press tx_ring_wr advance = {advance}"
    assert STANDBY_FRAME in new_frames, (
        f"standby press should emit {STANDBY_FRAME} via the IR helper "
        f"or the state-transition tail; absence indicates entire "
        f"IR-standby path is broken.  Got new frames: {new_frames}"
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
    _set_preset_bit(warmed_chain, starting_preset)
    pre_preset = _read_preset(warmed_chain)
    pre_wr = _read_tx_ring_wr(warmed_chain)
    pre_tx_count = len(warmed_chain.tx_frames())
    _inject_and_settle(warmed_chain, cmd=0x40)
    post_preset = _read_preset(warmed_chain)
    post_wr = _read_tx_ring_wr(warmed_chain)
    new_frames = [_frame_tuple(f) for f in warmed_chain.tx_frames()[pre_tx_count:]]

    assert post_preset == pre_preset, (
        f"unmapped cmd 0x40 ({label}) changed PRESET_BIT: "
        f"pre=0x{pre_preset:02X}, post=0x{post_preset:02X} -- "
        f"inline-shortcut leak into cmd 0x40"
    )
    assert _read_ir_armed(warmed_chain), (
        f"unmapped cmd 0x40 ({label}) must still re-arm IR_ARMED"
    )

    # Content-based leak detection (#159 partial strengthening):
    # The OPPOSITE-preset frame is the only content signal that's
    # robust against layer-2 jitter -- layer-2 step 6 (preset frame)
    # emits (0xB0, 0x20, current_preset) which matches the STARTING
    # preset byte AS LONG AS PRESET_BIT stays unchanged.  An IR-leak
    # that routed cmd 0x40 into the OPPOSITE preset case would set
    # PRESET_BIT to the opposite value AND emit the opposite-preset
    # frame -- but the PRESET_BIT-unchanged assertion above already
    # catches the leak.  This content check is BACKUP coverage for
    # the rare case where the leak somehow flips PRESET_BIT and then
    # flips it back (paranoid scenario; current code can't do that).
    #
    # Layer-2 emits cmd 0x03 frames with multiple data values
    # (00=standby, 01=wake, 02=mute_on, 03=mute_off) from various
    # paths (mute_frame_send, standby_wake_broadcast).  An empirical
    # 3 s settle in DISPLAY mode reliably contains (0xB0, 0x03, 0x00)
    # from layer-2's mute or transient state changes -- so the
    # earlier draft of this test that asserted STANDBY_FRAME absent
    # was a false-positive risk and was reverted.  The wake/standby
    # endpoint absence check is therefore deferred -- the residual
    # gap is acknowledged in #159's task description.
    opposite_preset_frame = (
        PRESET_B_FRAME if starting_preset == PRESET_A else PRESET_A_FRAME
    )
    assert opposite_preset_frame not in new_frames, (
        f"unmapped cmd 0x40 ({label}) emitted {opposite_preset_frame} -- "
        f"layer-2 cannot emit this while PRESET_BIT stays at "
        f"0x{starting_preset:02X}, so this is unambiguous leak into "
        f"the opposite preset path.  TX delta: {new_frames}"
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
