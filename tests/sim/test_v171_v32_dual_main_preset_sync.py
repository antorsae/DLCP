"""Dual-MAIN preset-sync test: V1.71 CONTROL + V3.2 LEFT MAIN + V3.2 RIGHT MAIN.

Verifies that a CONTROL preset-switch broadcast (cmd=0x20, route=B0)
keeps BOTH MAINs in perfect sync across an A→B→A→B cycle.  The user
needs 100% confidence that whatever CONTROL broadcasts, both MAINs
land at identical state -- no mis-cached filename, no DSP/biquad
desync between LEFT and RIGHT, no off-by-one preset interpretation.

What's asserted at every phase
==============================

  1. **Active preset bit agreement**: V3.2 stores the active-preset
     selector at ``active_flags.bit 2`` (RAM 0x05E bit 2 -- 0 = preset
     A, 1 = preset B per ``dlcp_main_v32.asm:9434+``
     ``preset_select_handler``).  MAIN0 and MAIN1 must read identical
     values.

  2. **Filename RAM agreement**: V3.2 stores the active preset's
     30-byte filename in RAM at ``preset_filename_ram_base = 0x2C0``
     (per ``dlcp_main_v32.asm:125``).  When CONTROL broadcasts a
     preset switch, both MAINs persist their dirty outgoing slot and
     load the incoming slot from EEPROM.  After every switch, MAIN0's
     filename RAM and MAIN1's filename RAM must be byte-equal.  Note:
     the canonical fresh-flash V3.2 EEPROM has empty filename slots
     (0xFF padding), so on a freshly-built rig both MAINs' filenames
     stay empty -- the test still asserts byte-equality of whatever
     value is there.

  3. **DSP/biquad register file agreement**: V3.2 writes biquads and
     coefficients into the TAS3108 over I²C as part of the preset
     switch.  The rust sim models a per-MAIN TAS3108 slave;
     ``read_main_dsp_reg(unit, subaddr)`` exposes each one's register
     file independently.  After every switch, MAIN0's DSP register
     file and MAIN1's must be byte-equal across all 256 subaddresses
     -- including the biquad range (0x37..=0x90, 5x32-bit per entry
     per TAS3108 datasheet §6.2.1).

  4. **Switch is real, not a no-op**: between Phase A1 (initial
     boot-default state on preset A) and Phase B1 (after first switch
     to preset B), at least one cell of the snapshot must DIFFER.
     Otherwise the "switch" never took effect and the byte-equality
     assertions would pass vacuously.

Failure modes this test catches
================================

  - MAIN0 handler updates active_flags.bit 2, MAIN1 doesn't (or
    vice-versa) -- chain-forwarding bug or one-MAIN handler bug.
  - Filename RAM gets corrupted on switch (wrong EEPROM slot loaded).
  - Biquad write to TAS3108 races / drops bytes on one MAIN but not
    the other.
  - Off-by-one in preset job state machine causing one MAIN to land
    on the wrong target.
  - Cross-talk between LEFT and RIGHT physical-bank-remapped
    addressing (codex task #45 #94 territory).

CONTROL-driven trigger model
============================

The test drives CONTROL's PRESET_BIT (``control_flags`` bit 6 at
RAM 0x01F) directly and lets V1.71 Layer 2's ``full_sync_burst``
naturally broadcast the new preset state down to both MAINs.  This
matches the real hardware flow (every full-sync cycle re-emits the
preset frame, which is the architectural fix for the V1.61b retry-
queue desync — see ``dlcp_control_v171.asm:2347+``).

An earlier draft of this test injected B0/20/data frames directly
into MAIN0's RX ring, but that races against CONTROL's periodic
preset broadcast — every cycle CONTROL re-broadcasts ITS current
preset state, which would silently revert any direct injection
once a step-6 ``v171_send_preset_frame_txonly`` fires.  Driving
CONTROL's bit aligns CONTROL's broadcasts with the test's intent.

Convergence is verified by polling: after each switch, the helper
waits until BOTH MAINs report ``active_flags.bit2 == target`` AND
``preset_job_state == IDLE`` (both per-MAIN copies of RAM 0x2DE).
Polling protects against (a) reading state mid-HOLDING/APPLY (V3.2
toggles ``bit2`` at HOLDING→APPLY transition before the I²C-table
APPLY phase actually writes biquads), and (b) settle budgets that
are too short for a full ``full_sync_burst`` cycle to reach step 6.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from dlcp_fw.paths import V171_CONTROL_HEX, V32_MAIN_HEX

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


# V3.2 MAIN RAM map (per `src/dlcp_fw/asm/dlcp_main_v32.asm`):
_ACTIVE_FLAGS = 0x05E              # bit 2 = preset selector (0=A, 1=B)
_ACTIVE_FLAGS_PRESET_BIT = 0x04    # bit mask for bit 2
_FILENAME_RAM_BASE = 0x2C0
_FILENAME_RAM_LEN = 0x1E           # 30 bytes
_PRESET_JOB_STATE = 0x2DE          # 0=IDLE,1=PENDING,2=HOLDING,3=APPLY,4=COMMIT
_PRESET_JOB_IDLE = 0

# V1.71 CONTROL RAM map (per `src/dlcp_fw/asm/dlcp_control_v171.asm`
# and `src/dlcp_fw/asm/dlcp_control_ram.inc`):
_CONTROL_FLAGS_ADDR = 0x01F        # bit 6 = PRESET_BIT (0=A, 1=B)
_CONTROL_PRESET_BIT = 6
_PRESET_IR_ADDR = 0x10             # V1.71 menu-configured IR address
                                    # cmd 0x38 -> preset A, 0x39 -> preset B
# v171_full_sync_step lives at bank-1 offset 0x70 (BANKED accesses
# after `movlb 0x01` per asm:2371-2372).  Physical address = 0x170.
# Step counter cycles 1..6; step 6 emits the periodic preset frame
# (`v171_send_preset_frame_txonly` at asm:3274), which is what the
# user-IR test must NOT race against during its immediate-emit
# window.
_V171_FULL_SYNC_STEP_ADDR = 0x170
# Set of pre-call step values that could lead to step 6 (preset
# dispatch) firing inside ``_IR_IMMEDIATE_EMIT_WINDOW_TICKS``.
#
# Two-increment derivation: walk pre-steps 0..6 against the rule
# "no path reaches step 6 within 2 incf increments":
#
#   * pre-step 5: 1st incf -> 6 (preset).            UNSAFE
#   * pre-step 4: 1st incf -> 5, 2nd incf -> 6.      UNSAFE
#   * pre-step 3: 1st incf -> 4, 2nd incf -> 5.      safe
#   * pre-step 2: 1st incf -> 3, 2nd incf -> 4.      safe
#   * pre-step 1: 1st incf -> 2, 2nd incf -> 3.      safe
#   * pre-step 0: 1st incf -> 1, 2nd incf -> 2.      safe
#   * pre-step 6: 1st incf -> 7 wrap to 1, then -> 2. safe
#
# Why two increments and not one: codex measurements on the V1.71
# display loop (asm:2793) recorded the periodic ``full_sync_burst``
# call cadence at ~4 M ticks during boot transient and ~50 M ticks
# in steady state (post-``run_until_connected`` + 50 M settle).
# In steady state only one call fits inside 5 M ticks, so a one-
# increment guard ({5}) would suffice, but the conservative two-
# increment guard ({4, 5}) protects against the boot-transient
# cadence and against future display-loop changes that might
# compress the period.  Over-rejection cost is small (rejects 2
# of 7 step values, ~29%), under-rejection cost is silent
# vacuous-pass on the immediate-emit assertion.
_V171_FULL_SYNC_STEP_UNSAFE_FOR_IR = frozenset({4, 5})

# Convergence budget per switch.  V1.71 ``full_sync_burst`` advances
# one step per ~20000 display-loop iterations; step 6 (preset frame)
# fires every 6 invocations.  Adding the V3.2 HOLDING (~150 ms = 7.2 M
# ticks) + APPLY (96 I²C entries) means a full converge can take
# 0.5..1.5 G ticks in the worst case.  The deadline is generous to
# accommodate variability in when step-6 lands relative to the bit
# being set.
_SWITCH_POLL_CHUNK_TICKS = 50_000_000
_SWITCH_POLL_CHUNKS = 60   # 60 × 50 M = 3.0 G ticks (~62 s sim)

# Window in which the IR-driven immediate emit must appear on
# CONTROL's TX.  At 31250 baud the 3-byte frame transmits in
# ~960 µs (~46 K ticks at 48 MHz universal clock).  Pad to 5 M
# ticks to absorb dispatcher latency and any IR-handoff settle.
#
# Isolation from the periodic broadcaster: ``full_sync_burst``
# dispatches the PRESET frame only when the post-increment
# ``v171_full_sync_step`` lands on 6.  The IR helper rejects any
# pre-call step in ``_V171_FULL_SYNC_STEP_UNSAFE_FOR_IR`` so no
# periodic call inside the 5 M window can dispatch step 6.  See
# the constant's comment for the full case analysis and the
# conservative-vs-empirical period reasoning; the assertion is
# robust to test-sequence reorders that would otherwise let a
# periodic rebroadcast vacuously satisfy the immediate-emit
# assertion below (codex LOW from 3e497e8 + 25072cc).
_IR_IMMEDIATE_EMIT_WINDOW_TICKS = 5_000_000


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _require_v32_hex(hex_path: Path) -> None:
    if not hex_path.exists():
        pytest.skip(f"missing V3.2 hex: {hex_path}")


def _require_v171_hex(hex_path: Path) -> None:
    if not hex_path.exists():
        pytest.skip(f"missing V1.71 hex: {hex_path}")


def _snapshot_main(chain, unit: int) -> dict[str, object]:
    """Capture a comparable snapshot of one MAIN's preset state."""
    active_flags = chain.read_main_reg(unit, _ACTIVE_FLAGS)
    preset_bit = bool(active_flags & _ACTIVE_FLAGS_PRESET_BIT)
    filename = bytes(
        chain.read_main_reg(unit, _FILENAME_RAM_BASE + i)
        for i in range(_FILENAME_RAM_LEN)
    )
    dsp_regs = bytes(chain.read_main_dsp_reg(unit, sub) for sub in range(256))
    return {
        "active_flags": active_flags,
        "preset_bit": preset_bit,
        "filename": filename,
        "dsp_regs": dsp_regs,
    }


def _assert_mains_synchronised(chain, phase: str) -> dict[str, object]:
    """Sample MAIN0 and MAIN1 and assert byte-equality on every
    comparable cell.  Returns MAIN0's snapshot for phase-to-phase
    comparison."""
    s0 = _snapshot_main(chain, 0)
    s1 = _snapshot_main(chain, 1)

    assert s0["preset_bit"] == s1["preset_bit"], (
        f"[{phase}] preset bit (active_flags.bit2) differs: "
        f"MAIN0=0x{s0['active_flags']:02X} (bit2={s0['preset_bit']}) "
        f"vs MAIN1=0x{s1['active_flags']:02X} (bit2={s1['preset_bit']})"
    )

    assert s0["filename"] == s1["filename"], (
        f"[{phase}] filename RAM 0x2C0..0x2DD differs:\n"
        f"  MAIN0: {s0['filename'].hex()}\n"
        f"  MAIN1: {s1['filename'].hex()}\n"
        f"first-diff index: {next(i for i in range(_FILENAME_RAM_LEN) if s0['filename'][i] != s1['filename'][i])}"
    )

    if s0["dsp_regs"] != s1["dsp_regs"]:
        diffs = [
            (i, s0["dsp_regs"][i], s1["dsp_regs"][i])
            for i in range(256)
            if s0["dsp_regs"][i] != s1["dsp_regs"][i]
        ]
        raise AssertionError(
            f"[{phase}] DSP register file differs at {len(diffs)} "
            f"subaddrs (first 10): "
            f"{[(f'0x{i:02X}', f'0x{a:02X}', f'0x{b:02X}') for i, a, b in diffs[:10]]}"
        )

    return s0


def _set_control_preset_bit(chain, target: int) -> None:
    """Force CONTROL's PRESET_BIT (control_flags.bit6) to ``target``.
    V1.71 Layer 2 ``full_sync_burst`` step 6 will then naturally
    broadcast the new preset down to both MAINs."""
    assert target in (0, 1), f"target must be 0 (A) or 1 (B); got {target}"
    flags = chain.read_reg(_CONTROL_FLAGS_ADDR)
    mask = 1 << _CONTROL_PRESET_BIT
    if target:
        flags |= mask
    else:
        flags &= ~mask
    chain.write_reg(_CONTROL_FLAGS_ADDR, flags & 0xFF)


def _wait_for_preset_convergence(chain, target: int, *, trigger: str) -> None:
    """Poll until BOTH MAINs converge on (``active_flags.bit2 ==
    target``) AND (``preset_job_state == IDLE``).  Raises an
    AssertionError if the chain hasn't converged within the
    deadline.

    ``trigger`` is a short label used in the deadline-AssertionError
    diagnostic so the failure tells the operator whether the
    upstream trigger was the periodic-broadcast path or the
    user-IR path.

    Why poll instead of fixed-budget step:
      * V3.2 toggles ``active_flags.bit2`` at the HOLDING -> APPLY
        transition (asm:9582), BEFORE APPLY's 96-entry I²C cycle
        completes.  Reading bit2 alone could observe "switched"
        while DSP biquads are still mid-write.
      * Polling on ``preset_job_state == IDLE`` ensures APPLY +
        COMMIT have fully finished.
      * V1.71 ``full_sync_burst`` step 6 (preset frame) only fires
        every 6 cycles, so a fixed-budget settle that's too short
        could miss the broadcast entirely.
    """
    for _ in range(_SWITCH_POLL_CHUNKS):
        chain.step_ticks(_SWITCH_POLL_CHUNK_TICKS)
        af0 = chain.read_main_reg(0, _ACTIVE_FLAGS)
        af1 = chain.read_main_reg(1, _ACTIVE_FLAGS)
        bit0 = (af0 & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        bit1 = (af1 & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        pjs0 = chain.read_main_reg(0, _PRESET_JOB_STATE)
        pjs1 = chain.read_main_reg(1, _PRESET_JOB_STATE)
        if (
            bit0 == target
            and bit1 == target
            and pjs0 == _PRESET_JOB_IDLE
            and pjs1 == _PRESET_JOB_IDLE
        ):
            return
    af0 = chain.read_main_reg(0, _ACTIVE_FLAGS)
    af1 = chain.read_main_reg(1, _ACTIVE_FLAGS)
    pjs0 = chain.read_main_reg(0, _PRESET_JOB_STATE)
    pjs1 = chain.read_main_reg(1, _PRESET_JOB_STATE)
    raise AssertionError(
        f"chain failed to converge on preset target={target} via "
        f"{trigger} within "
        f"{_SWITCH_POLL_CHUNKS * _SWITCH_POLL_CHUNK_TICKS} ticks: "
        f"M0(af=0x{af0:02X} bit2={(af0 >> 2) & 1} pjs={pjs0}) "
        f"M1(af=0x{af1:02X} bit2={(af1 >> 2) & 1} pjs={pjs1})"
    )


def _switch_preset_via_control(chain, target: int) -> None:
    """Drive CONTROL via the periodic-broadcast path: set
    ``control_flags.bit6`` (PRESET_BIT) and let
    ``full_sync_burst`` step 6 emit the broadcast on its next
    cycle.  Mirrors what would happen on a HID-host preset switch
    that lands the bit but does not directly invoke
    ``v171_send_preset_frame_and_persist``."""
    _set_control_preset_bit(chain, target)
    _wait_for_preset_convergence(
        chain, target, trigger="periodic full_sync_burst step 6"
    )


def _switch_preset_via_ir(chain, target: int) -> None:
    """Drive CONTROL via the user-IR path: inject decoded IR
    event ``cmd=0x39`` (preset B) or ``cmd=0x38`` (preset A) on
    ``PRESET_ADDR=0x10`` (V1.71 menu-configured preset endpoint).
    The IR dispatcher calls ``v171_send_preset_frame_and_persist``
    (asm:3306) which IMMEDIATELY emits ``[B0, 0x20, target]`` AND
    writes EEPROM 0x74 -- distinct from the periodic
    ``v171_send_preset_frame_txonly`` (asm:3274) the
    control-bit-direct path eventually exercises.

    To prove the IMMEDIATE-emit path actually fired (rather than
    the eventual periodic rebroadcast covering for it), this
    helper asserts that ``[B0, 0x20, target]`` appears on
    CONTROL's TX wire within a short window after IR injection
    (``_IR_IMMEDIATE_EMIT_WINDOW_TICKS``).  Isolation from the
    periodic preset broadcaster relies on the pre-injection guard
    below (``_V171_FULL_SYNC_STEP_UNSAFE_FOR_IR``); see that
    constant's comment for the case analysis and the empirical-
    vs-conservative period reasoning.  Without the guard, a
    regression in ``v171_send_preset_frame_and_persist`` could
    pass the test as long as the periodic txonly path eventually
    rebroadcast the same bit (codex MEDIUM from bb3a67b).
    """
    assert target in (0, 1), f"target must be 0 (A) or 1 (B); got {target}"
    cmd = 0x39 if target == 1 else 0x38
    target_frame = (0xB0, 0x20, target)

    # Defensive: ensure no periodic full_sync_burst call inside the
    # immediate-emit window can dispatch step 6 (preset).  See
    # ``_V171_FULL_SYNC_STEP_UNSAFE_FOR_IR`` for the derivation;
    # the conservative two-increment rule rejects {4, 5} so the
    # guard stays correct under boot-transient cadence and under
    # future display-loop changes that might compress the period.
    for _ in range(8):
        fs_step = chain.read_reg(_V171_FULL_SYNC_STEP_ADDR)
        if fs_step not in _V171_FULL_SYNC_STEP_UNSAFE_FOR_IR:
            break
        chain.step_ticks(_SWITCH_POLL_CHUNK_TICKS)
    fs_step = chain.read_reg(_V171_FULL_SYNC_STEP_ADDR)
    assert fs_step not in _V171_FULL_SYNC_STEP_UNSAFE_FOR_IR, (
        f"v171_full_sync_step == {fs_step} at IR injection time -- "
        f"a periodic full_sync_burst call inside the "
        f"{_IR_IMMEDIATE_EMIT_WINDOW_TICKS}-tick immediate-emit "
        f"window could reach step 6 (preset) and vacuously satisfy "
        f"the assertion below.  Unsafe pre-step set is "
        f"{sorted(_V171_FULL_SYNC_STEP_UNSAFE_FOR_IR)}.  Step the "
        f"chain a bit further before re-injecting, or restructure "
        f"the test sequence so this hazard does not align."
    )

    pre_frame_count = len(chain.tx_frames())
    chain.inject_decoded_ir_event(addr=_PRESET_IR_ADDR, cmd=cmd)
    chain.step_ticks(_IR_IMMEDIATE_EMIT_WINDOW_TICKS)
    new_frames = chain.tx_frames()[pre_frame_count:]
    assert target_frame in new_frames, (
        f"after IR cmd=0x{cmd:02X}, expected immediate-emit of "
        f"{target_frame!r} on CONTROL TX within "
        f"{_IR_IMMEDIATE_EMIT_WINDOW_TICKS} ticks; got new TX frames: "
        f"{new_frames!r}.  This proves "
        f"v171_send_preset_frame_and_persist (asm:3306) actually fired "
        f"-- without this guard, the periodic full_sync_burst step 6 "
        f"rebroadcast could mask a regression in the immediate-emit path."
    )
    _wait_for_preset_convergence(
        chain, target, trigger=f"user IR cmd=0x{cmd:02X}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_dual_main_preset_sync_AB_AB_chain() -> None:
    """The flagship sync test.  CONTROL broadcasts A→B→A→B; assert
    MAIN0 and MAIN1 stay byte-equal on active_flags.bit2,
    filename RAM (0x2C0..0x2DD), and full TAS3108 DSP register
    file (256 subaddresses including biquads at 0x37..=0x90)."""
    _require_rust()
    _require_v171_hex(V171_CONTROL_HEX)
    _require_v32_hex(V32_MAIN_HEX)

    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )

    # Boot the chain to connected.  This brings both MAINs through
    # cold-init, the boot sentinel exchange, and the first preset-load
    # job (boots to preset A by default per V3.2 cold-init).
    chain.run_until_connected(limit=400)
    assert chain.is_connected() and not chain.is_waiting(), (
        f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
    )
    # Allow extra settle for the boot-side preset-load job to finish
    # writing biquads to both DSPs.
    chain.step_ticks(50_000_000)

    # Phase A1 (boot default).
    snap_A1 = _assert_mains_synchronised(chain, phase="A1-boot-default")
    assert snap_A1["preset_bit"] is False, (
        f"V3.2 cold-init should boot to preset A (active_flags.bit2 == 0); "
        f"got active_flags=0x{snap_A1['active_flags']:02X}"
    )

    # Each phase appends a uniform 50M-tick post-IDLE settle so any
    # background DSP-rewrite tail (V1.71 layer-2 broadcast triggering
    # incremental I2C uploads on either MAIN) lands at the same
    # phase before the snapshot is taken.  Without this, B1 was
    # captured ~50 ms earlier in the post-IDLE rewrite tail than B2
    # (whose IDLE point is reached AFTER more accumulated layer-2
    # cycles), and DSP byte 0x37 differed by 0x80.  Aligning the
    # post-IDLE settle makes the biquad snapshots deterministic.
    # Bumped per #153 (M3 IR code shift moved the layer-2 cadence
    # phase relative to the convergence-poll exit point).
    #
    # CAVEAT (codex LOW vs a7e4169): empirically the late-tail DSP
    # rewrite occurs ~1M ticks AFTER preset_job_state == IDLE, so
    # the contract "IDLE implies DSP-stable" is approximate, not
    # strict.  This test now waits past the late-tail rather than
    # asserting IDLE alone is enough.  If the late-tail is ever
    # found to be a real firmware bug (vs an expected layer-2
    # incremental-upload pattern), revisit and tighten.
    _POST_IDLE_SETTLE_TICKS = 50_000_000

    # Phase B1: switch to preset B.
    _switch_preset_via_control(chain, target=1)
    chain.step_ticks(_POST_IDLE_SETTLE_TICKS)
    snap_B1 = _assert_mains_synchronised(chain, phase="B1-switched-to-B")
    assert snap_B1["preset_bit"] is True, (
        f"after B0/20/01 broadcast, active_flags.bit2 must be 1 (preset B); "
        f"got active_flags=0x{snap_B1['active_flags']:02X}"
    )
    # Switch must be REAL: at least one comparable cell must differ
    # vs the baseline snapshot.  Otherwise the byte-equality
    # assertions in _assert_mains_synchronised pass vacuously.
    _assert_snapshot_differs(snap_A1, snap_B1, phase_a="A1", phase_b="B1")

    # Phase A2: switch back to preset A.
    _switch_preset_via_control(chain, target=0)
    chain.step_ticks(_POST_IDLE_SETTLE_TICKS)
    snap_A2 = _assert_mains_synchronised(chain, phase="A2-switched-back-to-A")
    assert snap_A2["preset_bit"] is False, (
        f"after B0/20/00 broadcast, active_flags.bit2 must be 0 (preset A); "
        f"got active_flags=0x{snap_A2['active_flags']:02X}"
    )

    # Phase B2: switch to preset B again.
    _switch_preset_via_control(chain, target=1)
    chain.step_ticks(_POST_IDLE_SETTLE_TICKS)
    snap_B2 = _assert_mains_synchronised(chain, phase="B2-switched-to-B-again")
    assert snap_B2["preset_bit"] is True

    # Round-trip property on the BIQUAD range (0x37..=0x90)
    # specifically: between consecutive same-preset switch-resolutions,
    # the biquad coefficients must be deterministic.  The cold-init A
    # snapshot (A1) is intentionally NOT compared against A2 because
    # cold-init writes more TAS3108 state than a runtime switch
    # (mute/source/init), so A1 and A2 legitimately differ on
    # non-biquad cells.  But the biquads themselves should be
    # deterministic across switch-back-to-same-preset events.
    biquad_B1 = snap_B1["dsp_regs"][0x37:0x91]
    biquad_B2 = snap_B2["dsp_regs"][0x37:0x91]
    assert biquad_B1 == biquad_B2, (
        "biquad register file at 0x37..=0x90 (DSP slots B) differs "
        "between the first switch-to-B and the second switch-to-B -- "
        "indicates that runtime preset switching is not "
        "deterministic, or that some between-switch state "
        "(filename-dirty, queued frames) leaks into the biquad "
        "write path."
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_dual_main_preset_bit_tracks_broadcast_payload() -> None:
    """Tighter focus on JUST the active-preset bit: every B0/0x20/x
    broadcast must drive both MAINs' active_flags.bit2 to ``x``.

    Cheaper than the full dual-MAIN snapshot test (no DSP / filename
    comparison), runs faster, and produces a clearer error when the
    failure is specifically a preset-bit-not-updated bug rather than
    a biquad/filename desync.  Useful as a smoke gate before the
    heavier sync test.
    """
    _require_rust()
    _require_v171_hex(V171_CONTROL_HEX)
    _require_v32_hex(V32_MAIN_HEX)

    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    chain.step_ticks(50_000_000)

    # Boot default = preset A on both MAINs.
    af0 = chain.read_main_reg(0, _ACTIVE_FLAGS)
    af1 = chain.read_main_reg(1, _ACTIVE_FLAGS)
    assert (af0 & _ACTIVE_FLAGS_PRESET_BIT) == 0, (
        f"MAIN0 active_flags.bit2 must be 0 at boot; "
        f"got 0x{af0:02X}"
    )
    assert (af1 & _ACTIVE_FLAGS_PRESET_BIT) == 0, (
        f"MAIN1 active_flags.bit2 must be 0 at boot; "
        f"got 0x{af1:02X}"
    )

    # Drive the CONTROL preset bit cycle and assert both MAINs'
    # bit2 follow.  ``_switch_preset_via_control`` polls until both
    # MAINs reach (bit2 == target) AND (preset_job_state == IDLE),
    # so the assertions below are a redundant final check rather
    # than a gate against in-flight job state -- but they catch
    # a regression where the polling helper wrongly returns early.
    for target in (1, 0, 1, 0):
        _switch_preset_via_control(chain, target=target)
        af0 = chain.read_main_reg(0, _ACTIVE_FLAGS)
        af1 = chain.read_main_reg(1, _ACTIVE_FLAGS)
        bit0 = (af0 & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        bit1 = (af1 & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        assert bit0 == target and bit1 == target, (
            f"after CONTROL preset bit set to {target}: "
            f"MAIN0.bit2={bit0} (af=0x{af0:02X}), "
            f"MAIN1.bit2={bit1} (af=0x{af1:02X}); expected both = {target}"
        )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_dual_main_dsp_biquad_byte_equal_after_each_switch() -> None:
    """Tighter focus on JUST the DSP biquad register file (subaddrs
    0x37..=0x90, 5x32-bit per entry per TAS3108 datasheet §6.2.1):
    after every preset broadcast, MAIN0's TAS3108 and MAIN1's
    TAS3108 must be byte-equal across the entire biquad range.

    Strips the filename and active_flags comparisons of the flagship
    test to give a sharper error when MAIN0 vs MAIN1 disagree
    specifically on coefficient state -- the most-load-bearing
    sync property for audio behaviour.
    """
    _require_rust()
    _require_v171_hex(V171_CONTROL_HEX)
    _require_v32_hex(V32_MAIN_HEX)

    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    chain.step_ticks(50_000_000)

    def _read_biquads(unit: int) -> bytes:
        return bytes(
            chain.read_main_dsp_reg(unit, sub) for sub in range(0x37, 0x91)
        )

    def _assert_biquads_equal(label: str) -> None:
        m0 = _read_biquads(0)
        m1 = _read_biquads(1)
        if m0 != m1:
            diffs = [
                (0x37 + i, m0[i], m1[i])
                for i in range(len(m0))
                if m0[i] != m1[i]
            ]
            raise AssertionError(
                f"[{label}] biquad register file (0x37..=0x90) differs "
                f"at {len(diffs)} subaddrs: "
                f"{[(f'0x{i:02X}', f'0x{a:02X}', f'0x{b:02X}') for i, a, b in diffs[:10]]}"
            )

    def _assert_switch_was_delivered(label: str, target: int) -> None:
        """Guard against vacuous biquad-equality: if the switch never
        actually reached the firmware, both MAINs would trivially
        match on whatever state they had before.  Verify by reading
        active_flags.bit2 on both MAINs (proves the broadcast was
        delivered AND the preset_select_handler executed)."""
        af0 = chain.read_main_reg(0, _ACTIVE_FLAGS)
        af1 = chain.read_main_reg(1, _ACTIVE_FLAGS)
        bit0 = (af0 & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        bit1 = (af1 & _ACTIVE_FLAGS_PRESET_BIT) >> 2
        assert bit0 == target and bit1 == target, (
            f"[{label}] switch delivery guard failed: "
            f"M0(af=0x{af0:02X} bit2={bit0}) M1(af=0x{af1:02X} bit2={bit1}); "
            f"expected both bit2={target}.  Biquad-equality assertion "
            f"would have passed vacuously without this guard."
        )

    _assert_biquads_equal("boot-default-A")
    for label, target in [
        ("after-switch-to-B", 1),
        ("after-switch-back-to-A", 0),
        ("after-switch-to-B-again", 1),
        ("after-switch-back-to-A-again", 0),
    ]:
        _switch_preset_via_control(chain, target=target)
        _assert_switch_was_delivered(label, target)
        _assert_biquads_equal(label)


@pytest.mark.dual_supported
@pytest.mark.slow
def test_dual_main_preset_sync_via_user_ir_chain() -> None:
    """Complementary to ``test_dual_main_preset_sync_AB_AB_chain``:
    triggers preset switches via the user-initiated IR remote
    path (``cmd=0x38`` -> preset A, ``cmd=0x39`` -> preset B on
    ``PRESET_ADDR=0x10``) instead of directly setting CONTROL's
    PRESET_BIT.

    The user-IR path goes through the V1.71 IR dispatcher, which
    calls ``v171_send_preset_frame_and_persist`` (asm:3306) --
    that helper IMMEDIATELY emits ``[B0, 0x20, target]`` AND
    writes EEPROM 0x74.  The other three tests in this file
    drive the periodic-broadcast path (``full_sync_burst`` step 6
    -> ``v171_send_preset_frame_txonly`` at asm:3274) by setting
    the bit and waiting; those tests would still pass even if
    the immediate-emit / EEPROM-persist plumbing regressed, as
    long as the periodic re-broadcaster stays healthy.  This
    test closes that coverage gap (codex LOW from eebe8ca,
    tracked as task #133).

    Asserted properties match the flagship test: after every
    IR-driven switch, MAIN0 and MAIN1 are byte-equal on
    ``active_flags.bit2``, filename RAM 0x2C0..0x2DD, and the
    full TAS3108 DSP register file (256 subaddresses).
    """
    _require_rust()
    _require_v171_hex(V171_CONTROL_HEX)
    _require_v32_hex(V32_MAIN_HEX)

    chain = RustChain.from_v171_v32(
        control_hex_path=str(V171_CONTROL_HEX),
        main_hex_path=str(V32_MAIN_HEX),
    )
    chain.run_until_connected(limit=400)
    assert chain.is_connected() and not chain.is_waiting(), (
        f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
    )
    chain.step_ticks(50_000_000)

    # Phase A1 (boot default).
    snap_A1 = _assert_mains_synchronised(chain, phase="A1-boot-default")
    assert snap_A1["preset_bit"] is False

    # Match the control-bit path's post-IDLE settle: preset_job_state can
    # reach IDLE just before a late DSP rewrite tail lands, so byte-level
    # DSP equality must be sampled after the small tail has drained.
    _POST_IR_IDLE_SETTLE_TICKS = 50_000_000

    # Phase B1: IR cmd 0x39 -> preset B.
    _switch_preset_via_ir(chain, target=1)
    chain.step_ticks(_POST_IR_IDLE_SETTLE_TICKS)
    snap_B1 = _assert_mains_synchronised(chain, phase="B1-via-IR-0x39")
    assert snap_B1["preset_bit"] is True, (
        f"after IR cmd=0x39, active_flags.bit2 must be 1 (preset B); "
        f"got active_flags=0x{snap_B1['active_flags']:02X}"
    )
    _assert_snapshot_differs(snap_A1, snap_B1, phase_a="A1", phase_b="B1-via-IR")

    # Phase A2: IR cmd 0x38 -> preset A.
    _switch_preset_via_ir(chain, target=0)
    chain.step_ticks(_POST_IR_IDLE_SETTLE_TICKS)
    snap_A2 = _assert_mains_synchronised(chain, phase="A2-via-IR-0x38")
    assert snap_A2["preset_bit"] is False, (
        f"after IR cmd=0x38, active_flags.bit2 must be 0 (preset A); "
        f"got active_flags=0x{snap_A2['active_flags']:02X}"
    )

    # Phase B2: IR cmd 0x39 again -> preset B.  Verifies that the
    # user-IR path is repeatable, not a one-shot artefact of the
    # boot-default state.
    _switch_preset_via_ir(chain, target=1)
    chain.step_ticks(_POST_IR_IDLE_SETTLE_TICKS)
    snap_B2 = _assert_mains_synchronised(chain, phase="B2-via-IR-0x39-again")
    assert snap_B2["preset_bit"] is True


def _assert_snapshot_differs(
    snap_a: dict[str, object],
    snap_b: dict[str, object],
    phase_a: str,
    phase_b: str,
) -> None:
    """Assert that two snapshots differ on at least one cell --
    proving the preset switch took effect (otherwise byte-equality
    asserts pass vacuously)."""
    if snap_a["preset_bit"] != snap_b["preset_bit"]:
        return
    if snap_a["filename"] != snap_b["filename"]:
        return
    if snap_a["dsp_regs"] != snap_b["dsp_regs"]:
        return
    raise AssertionError(
        f"snapshots at {phase_a} and {phase_b} are byte-identical -- "
        f"preset switch broadcast did not take effect.  This invalidates "
        f"the MAIN0 == MAIN1 byte-equality assertions because they would "
        f"pass vacuously even if the firmware never ran the switch handler."
    )
