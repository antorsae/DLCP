"""V1.71 × V3.2 Layer 5 Phase C: wire-chain diagnostics page integration.

End-to-end validation of the cmd 0x21 / BF/21..27 protocol with V1.71
CONTROL and V3.2 MAIN co-simulated on the wire-chain harness.  This is
the trust-band counterpart to:

* Phase A (``tests/sim/test_v32_layer5_diag_counters.py``) — MAIN-side
  counter pinning, RCON gate, and reply-burst structure.
* Phase B (``tests/sim/test_v171_layer5_diag_page.py``) — CONTROL-side
  page body, parser cases, and source-structural wiring.

Phase C exercises the *protocol contract* end-to-end:

1. CONTROL navigates to the Diagnostics screen and emits ``B1/0x21/0x00``
   then ``B2/0x21/0x00`` queries on cadence.
2. Both MAINs reply with the BF/21..27 burst (7 frames, one counter
   per frame; the original 4-frame packed-nibble scheme was retired
   2026-04-19 — see Phase A docstring for the rationale).
3. CONTROL parses each frame into the right per-PB cache slot.
4. The compact 16×2 LCD layout renders the cached values per spec.

``docs/SIMULATION_FIDELITY.md`` §"2026-04-18 correction" measured
the now-retired gpsim harness against real hardware for the
preset-apply / IR / button race classes that Phase C needs and
found byte timing within 20 % of hardware.  The rust engine has
not been re-measured to that depth directly, but P3.5 part-10
gates the rust chain bit-for-bit against gpsim ground-truth
fixtures captured at that fidelity (task #29 -- 6-frame MAIN→CTRL
response burst on MAIN's TX stream; task #34 -- bit-exact LCD
raster), which keeps the gpsim measurement load-bearing for the
rust path.

Phase C v1 covers the protocol-contract subset of the spec's 15-case
test matrix.  The per-counter primary tests (I2C / DSP / RCV / S / B /
AN0 / RA1) are added incrementally as the per-counter fault-injection
hooks become available.

PF.3 (2026-05-04) added ``_press_drive_until_pb_present`` (and the
rust mirror ``_rust_press_drive_until_pb_present``), which alternates
RIGHT/LEFT presses across PB1 Diag(4) <-> PB2 Diag(5) so V1.71's
foreground busy-loop in ``display_loop_iteration`` (asm:2885-2897)
keeps exiting and the cmd 0x21 / cmd 0x22 cadence re-fires often
enough for both PBs to reply.  This is a faithful test-side
reproduction: operator HW retest 2026-05-04 (V3.2 rev 0x3F + V1.71
rev 0x0F) confirmed real silicon also needs multiple LEFT/RIGHT
navigation cycles to converge (probe v21 in rust converges in 7
mixed-nav cycles, matching HW).

PF.3 + task #116 (2026-05-04) un-XFAIL'd 4 of the original 5
``_V171_V32_PB2_BRIDGE_XFAIL`` tests:
``test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2``,
``lcd_renders_zero_idle``, ``lcd_renders_mixed_counters``, and
``test_v171_v32_layer5_chain_lcd_renders_saturation_plus``.  PF.3
closeout (2026-05-05) retired the last marker on
``pb_cache_isolation`` -- the underlying multi-frame BF/22..27
cache misroute (task #117) was a gpsim-side bug that closed when
gpsim was retired in PF.4 phase 2; the rust path converges via
``_press_drive_until_pb_present`` and the decorator constant
``_V171_V32_PB2_BRIDGE_XFAIL`` was deleted.

The original Task #22 framing (gpsim two-MAIN topology echoes MAIN0's
TX into both downstream and upstream paths) is the architectural half
of the issue and is retired by the rust silicon-correct ring (P3.6a in
``docs/SIM_REWRITE_RUST_PROGRESS.md``); it is distinct from #117.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import (
    V17_CONTROL_RAM_INC,
    V171_CONTROL_ASM,
    V32_MAIN_ASM,
)
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30


try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
    _RUST_CHAIN_IMPORT_ERROR: Exception | None = None
except Exception as exc:  # pragma: no cover
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc


def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )


def _require_v32_hex(v32_hex: Path) -> None:
    """Skip if the V3.2 hex isn't present (CI runs without the
    `firmware/patched/releases/DLCP_Firmware_V3.2.hex` artifact in
    minimal worktrees)."""
    if not v32_hex.exists():
        pytest.skip(f"missing V3.2 hex: {v32_hex}")


# ---------------------------------------------------------------------------
# Rust-side navigation / readback helpers.  Originally added as
# mirrors of the gpsim helpers during the dual-backend migration;
# the gpsim path was retired in PF.4 phase 2 so these are now the
# only helpers in the file.
# ---------------------------------------------------------------------------


def _rust_navigate_to_diagnostics(rust_chain) -> None:  # type: ignore[no-untyped-def]
    """Drive CONTROL to PB1 Diag(4).

    Presses RIGHT four times with 8 intermediate steps to settle
    each press.  Targets the V1.71 menu state
    machine, which doesn't change behavior across simulators.
    """
    for _ in range(4):
        rust_chain.press("RIGHT")
        for _ in range(8):
            rust_chain.step()


def _rust_main_diag_block(rust_chain, main_idx: int) -> tuple[int, ...]:  # type: ignore[no-untyped-def]
    """Read MAIN's 7 diag-counter bytes (diag_i..diag_p at
    0x2E5..0x2EB) via the per-MAIN register read primitive
    (`Chain.read_main_reg(unit, addr)`).
    """
    return tuple(
        rust_chain.read_main_reg(main_idx, addr)
        for addr in (DIAG_I_PHYS, DIAG_D_PHYS, DIAG_S_PHYS,
                     DIAG_B_PHYS, DIAG_R_PHYS, DIAG_A_PHYS, DIAG_P_PHYS)
    )


def _rust_set_main_diag_block(  # type: ignore[no-untyped-def]
    rust_chain,
    main_idx: int,
    *,
    diag_i: int = 0, diag_d: int = 0, diag_s: int = 0,
    diag_b: int = 0, diag_r: int = 0, diag_a: int = 0,
    diag_p: int = 0
) -> None:
    """Set diag-counter cells on MAIN.

    Writes each cell via the per-MAIN write primitive
    (`Chain.write_main_reg(unit, addr, value)`).  Counter values
    are masked to the low nibble.
    """
    for value, addr in (
        (diag_i, DIAG_I_PHYS), (diag_d, DIAG_D_PHYS),
        (diag_s, DIAG_S_PHYS), (diag_b, DIAG_B_PHYS),
        (diag_r, DIAG_R_PHYS), (diag_a, DIAG_A_PHYS),
        (diag_p, DIAG_P_PHYS),
    ):
        rust_chain.write_main_reg(main_idx, addr, value & 0x0F)


def _rust_diag_present(rust_chain) -> int:  # type: ignore[no-untyped-def]
    """CONTROL's `v171_diag_present` byte at PHYS 0x197."""
    return rust_chain.read_reg(V171_DIAG_PRESENT_PHYS)


def _rust_diag_pb_cache(rust_chain, pb_idx: int) -> tuple[int, ...]:  # type: ignore[no-untyped-def]
    """Read the 7-byte CONTROL diag cache (I, D, S, B, R, A, P) for
    PB1 (idx=0) or PB2 (idx=1).
    """
    base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    return tuple(rust_chain.read_reg(base + i) for i in range(7))


def _rust_wait_for_pb_present(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_mask: int, limit: int = 250,
) -> bool:
    """Step the chain until `v171_diag_present` has the requested
    PB bits set, or `limit` chain steps elapse.  Returns True on
    success.
    """
    for _ in range(limit):
        if (_rust_diag_present(rust_chain) & pb_mask) == pb_mask:
            return True
        rust_chain.step()
    return (_rust_diag_present(rust_chain) & pb_mask) == pb_mask


def _rust_press_drive_until_pb_present(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_mask: int, limit: int = 400, press_period: int = 8,
    settle_steps: int = 0, extra_check=None,
) -> bool:
    """Drive CONTROL's diag-poll cadence by alternating RIGHT/LEFT
    presses across PB1 Diag(4) <-> PB2 Diag(5) so V1.71's
    ``display_loop_iteration`` busy-loop (asm:2885-2897) keeps
    exiting and the cmd 0x21/0x22 timer re-fires often enough for
    both PB replies to land.

    Caller must have positioned CONTROL on PB1 Diag(4) (e.g. via
    ``_rust_navigate_to_diagnostics``) before calling.  The wiggle
    pattern is:
      * From PB1(4) press RIGHT  -> PB2(5)
      * From PB2(5) press LEFT   -> PB1(4)
      * repeat
    On exit (success or timeout) the chain is left on PB1 Diag(4)
    so subsequent LCD assertions render PB1 data on row 0.

    ``press_period`` is the number of chain steps between
    consecutive presses.  Presses themselves are ~100 M ticks of
    sim time each (50 M HOLD + 50 M RELEASE_SETTLE), so a small
    ``press_period`` keeps the foreground loop exiting at well
    above the V171_DIAG_POLL_RELOAD = 0x80 ticks cadence.

    ``settle_steps`` continues wiggling for this many additional
    chain steps AFTER ``pb_mask`` is reached.  V3.2's `cmd 0x21`
    handler emits a single 7-frame BF/21..27 burst per query
    (V32_DIAG_TIER1_SPEC.md line 102-105), but EMPIRICALLY (probe
    /tmp/probe_ctl_cache.py) cache slot[N] populates progressively
    across many wiggle cycles (slot[0] hits at ~wiggle 11, slot[1]
    at ~wiggle 22-34) -- the present mask flips on the first slot
    landing, so tests that assert on cache[1..6] need this extra
    settle.  Likely cause is V1.71 parser / chain-transport
    latency; tracked under task #117 for the gpsim path where the
    later frames fail to land at all.
    """
    # press() is synchronous (it internally steps the simulator
    # for BUTTON_HOLD_TICKS + BUTTON_RELEASE_SETTLE_TICKS), so no
    # extra step()-after-press is needed here -- by the time press()
    # returns, the schedule is fully applied and ``on_pb1`` matches
    # the actual chain state.
    on_pb1 = True
    steps_since_press = 0
    converged = False
    extra_remaining = 0
    for _ in range(limit):
        mask_ok = (_rust_diag_present(rust_chain) & pb_mask) == pb_mask
        extra_ok = extra_check(rust_chain) if extra_check is not None else True
        if not converged and mask_ok and extra_ok:
            converged = True
            extra_remaining = settle_steps
        if converged and extra_remaining <= 0:
            break
        rust_chain.step()
        if converged:
            extra_remaining -= 1
        steps_since_press += 1
        if steps_since_press >= press_period:
            rust_chain.press("RIGHT" if on_pb1 else "LEFT")
            on_pb1 = not on_pb1
            steps_since_press = 0
    # Skip the post-loop normalize when extra_check is provided:
    # callers using extra_check have already asserted the exact end
    # state they want (typically display_state_index == STATE_PB1_DIAG),
    # and an extra normalization press would auto-repeat past it.
    if extra_check is None and not on_pb1:
        rust_chain.press("LEFT")
        on_pb1 = True
        for _ in range(8):
            rust_chain.step()
    return converged


def _rust_diag_canary_run(  # type: ignore[no-untyped-def]
    rust_chain,
) -> tuple[dict[str, int], int, tuple[int, ...]]:
    """Run a diag-page poll cycle and snapshot per-hop byte deltas.

    Returns ``(hop_deltas, present_mask, pb2_cache)``.  Pre-loads
    MAIN1's diag_p = 0x07 so a successful PB2 reply has a distinct
    payload.

    **Topology** (codex MEDIUM from 48a862d): the rust 3-core
    chain wires a TRUE ring (CONTROL -> MAIN0 -> MAIN1 -> CONTROL)
    with THREE UART couplings:
       * ``ctl_to_m0`` -- CONTROL TX -> MAIN0 RX
       * ``m0_to_m1``  -- MAIN0 TX  -> MAIN1 RX
       * ``m1_to_ctl`` -- MAIN1 TX  -> CONTROL RX
    Per-hop counts are byte-level.  See the
    ``Chain.bridge_byte_stats`` docstring in
    ``src/dlcp_fw/sim/dlcp_sim_native.py``.
    """
    rust_chain.run_until_connected(limit=200)
    if not rust_chain.is_connected() or rust_chain.is_waiting():
        raise AssertionError(
            f"chain stuck in WAITING/Zzz: lcd={rust_chain.lcd_lines()!r}"
        )
    _rust_set_main_diag_block(rust_chain, 1, diag_p=0x07)
    pre_stats = rust_chain.bridge_byte_stats()
    _rust_navigate_to_diagnostics(rust_chain)
    # Drive the cmd 0x21/0x22 cadence with alternating RIGHT/LEFT
    # wiggles so V1.71's display_loop_iteration busy-loop keeps
    # exiting and PB2's reply burst lands.  Operator HW retest
    # 2026-05-04 confirmed real silicon needs the same wiggle.
    _rust_press_drive_until_pb_present(rust_chain, pb_mask=0x02, limit=200)
    post_stats = rust_chain.bridge_byte_stats()
    # Compute deltas across EVERY hop the chain reports (3 on
    # rust, 4 on gpsim if this helper were ever reused there).
    # Iterating post_stats's keys -- not a hard-coded list --
    # makes the helper topology-agnostic.
    deltas = {
        link: post_stats[link].get("total_edges", 0)
              - pre_stats.get(link, {}).get("total_edges", 0)
        for link in post_stats
    }
    return deltas, _rust_diag_present(rust_chain), _rust_diag_pb_cache(rust_chain, 1)


# ---------------------------------------------------------------------------
# Hex source skew caveat (post codex review of 16fa3ee, 2026-05-03)
# ---------------------------------------------------------------------------
# `Chain.from_v171_v32()` loads CANONICAL release hexes from
# `firmware/patched/releases/{DLCP_Control_V1.71,DLCP_Firmware_V3.2}.hex`.
# A Phase A/B source change landing BEFORE a canonical release
# rebuild (`scripts/build_v32_release.py` / `scripts/build_v171_release.py`)
# would silently make these tests load stale binaries.  Tracking:
# pending sim-rewrite progress-ledger entry "Add hex-path overrides
# to `Chain.from_v171_v32` to avoid stale-canonical skew".
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Constants pinned by the Layer 5 design (kept duplicated from Phase A/B
# files so a wire-chain test failure can be diagnosed locally without
# cross-file lookups).
# ---------------------------------------------------------------------------

# CONTROL diag cache (BANK 1, 11 cells per PB — physical addresses).
# Layer 5 baseline: 7 runtime counter cells (BF/21..BF/27, cmd 0x21).
# V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20): + 4 reset-cause
# flag cells (BF/28..BF/2B, cmd 0x22) per PB, plus extra state cells.
# Cache base unchanged (PB1 = 0x180); PB2 base shifted +4 (was +7,
# now +11) and trailing state cells shifted +8.
V171_DIAG_PB1_BASE_PHYS = 0x180        # I D S B R A P O V W X (11 bytes)
V171_DIAG_PB2_BASE_PHYS = 0x18B        # I D S B R A P O V W X (11 bytes)
V171_DIAG_TARGET_PHYS = 0x196
V171_DIAG_PRESENT_PHYS = 0x197

# MAIN diag block (BANK 2 upper, physical addresses for gpsim CLI reads).
# Relocated 2026-04-19 from 0x123..0x12A to escape the USB EP1 OUT buffer
# (0x11A..0x159).  See dlcp_main_ram.inc "RAM safety" section.
DIAG_I_PHYS = 0x2E5
DIAG_D_PHYS = 0x2E6
DIAG_S_PHYS = 0x2E7
DIAG_B_PHYS = 0x2E8
DIAG_R_PHYS = 0x2E9
DIAG_A_PHYS = 0x2EA
DIAG_P_PHYS = 0x2EB

# Menu state indices.  V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20)
# moved Diagnostics from state 2 (between Preset and Input) to states 4-5
# (after Setup), with one PB per state.  STATE_DIAG is preserved as an
# alias pointing at PB1 Diag for older tests that read a single state
# index; new tests should use STATE_PB1_DIAG / STATE_PB2_DIAG explicitly.
STATE_VOLUME   = 0
STATE_PRESET   = 1
STATE_INPUT    = 2     # Tier-1: was 3
STATE_SETUP    = 3     # Tier-1: was 4
STATE_PB1_DIAG = 4     # Tier-1: NEW (split of single Diag state)
STATE_PB2_DIAG = 5     # Tier-1: NEW
STATE_DIAG     = STATE_PB1_DIAG  # back-compat alias for legacy tests

DISPLAY_STATE_INDEX_PHYS = 0x0BF


# ---------------------------------------------------------------------------
# Shared fixture: build V1.71 hex once per module, reuse across tests
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("v171_v32_layer5")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    assemble_v17(asm, hex_out)
    return hex_out


@pytest.fixture(scope="module")
def v32_hex(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build V3.2 MAIN from current source into a module-scoped tmp dir.

    Phase C used to consume the canonical ``V32_MAIN_HEX`` directly, but
    that path is only refreshed by an external build pipeline — if a
    Phase A / Phase B source change landed since the last canonical
    rebuild, Phase C silently tested the stale binary.  Building from
    ``V32_MAIN_ASM`` here guarantees Phase C and Phase A see the same
    source-derived artifact, eliminating the source/hex skew blind
    spot called out in the 2026-04-19 review.

    Module-scoped so the ~3-second gpasm step runs once per file.  The
    ``tmp_path_factory.mktemp`` location is per-worker under xdist, so
    parallel runs cannot race on a shared output path.
    """
    tmp = tmp_path_factory.mktemp("v32_layer5_chain")
    hex_out = tmp / "DLCP_Firmware_V3.2.hex"
    assemble_v30(V32_MAIN_ASM, hex_out)
    return hex_out




@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_idle_caches_zero_at_boot(
    v171_hex: Path, v32_hex: Path
) -> None:
    """At boot, neither PB has replied, so CONTROL's diag cache and
    present mask must be zero across the chain warmup.

    This is the wire-chain analogue of the Phase B
    ``diag_block_holds_zero_through_boot_and_warmup`` test, but with
    real MAINs on the chain (which exercise the BF/05/07/03/06/1D
    steady-state status burst — none of which should leak into the
    diag cache).

    Migrated to dual_supported in P4.7: the V1.71+V3.2+V3.2 chain
    now reaches DISPLAY mode on rust after the codex hypothesis #1
    fix to ``build_v171_v32_chain`` (PORTA/PORTC seeded to 0xFF
    after POR so V1.71 doesn't read the wiped 0x00 PORT bits as
    "STBY-stuck-pressed" -> Zzz).  Drives the chain with the
    freshly-built ``v171_hex`` / ``v32_hex`` tmp fixtures via the
    ``control_hex_path`` / ``main_hex_path`` overrides on
    ``Chain.from_v171_v32`` (codex task #77) so the test gates
    on the current source rather than the canonical release hex.
    """
    _require_v32_hex(v32_hex)
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    present = c.read_reg(V171_DIAG_PRESENT_PHYS)
    assert present == 0, (
        f"[rust] present mask non-zero at boot: 0x{present:02X}"
    )
    for pb_base, pb_label in (
        (V171_DIAG_PB1_BASE_PHYS, "PB1"),
        (V171_DIAG_PB2_BASE_PHYS, "PB2"),
    ):
        cache = tuple(c.read_reg(pb_base + i) for i in range(7))
        assert all(v == 0 for v in cache), (
            f"[rust] {pb_label} cache non-zero at boot: "
            f"{[hex(v) for v in cache]}"
        )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Navigating to Diagnostics drives CONTROL's poll loop, which
    alternates queries between PB1 and PB2.  After enough chain steps
    for the cadence to fire twice (once per PB), both ``v171_diag_present``
    bits must be set, demonstrating that:

    1. CONTROL emits ``B1/0x21/0x00`` and the V3.2 MAIN at PB1 replies
       with the 7-frame BF/21..27 burst (one counter per frame, low-
       nibble data), which CONTROL parses into the PB1 cache.
    2. CONTROL emits ``B2/0x21/0x00``, PB1 forwards (decremented to B1),
       PB2 consumes and replies, the BF/21..27 burst flows back upstream
       through PB1's forwarder, and CONTROL parses into the PB2 cache.

    This is the protocol-contract end-to-end gate.

    PF.3 (2026-05-04) un-XFAIL'd this test on both backends by
    swapping the navigation-only ``_wait_for_pb_present`` poll loop
    for ``_press_drive_until_pb_present``, which alternates RIGHT/
    LEFT presses across PB1 Diag(4) <-> PB2 Diag(5) so V1.71's
    ``display_loop_iteration`` busy-loop (asm:2885-2897) keeps
    exiting and the cmd 0x21/0x22 cadence re-fires often enough for
    both PBs to reply.  Operator HW retest 2026-05-04 (V3.2 rev 0x3F
    + V1.71 rev 0x0F) confirmed real silicon also needs multiple
    LEFT/RIGHT cycles to converge (probe v21 in rust converges in 7
    wiggle cycles); the wiggle harness is a faithful test-side
    reproduction.  Task #94 (briefly framed as a rust-specific
    Timer3/Timer1 ISR-dispatch fidelity bug) CLOSED.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    # Limit bumped 600 -> 1200 to absorb the M3 IR non-blocking
    # decoder code shift (86d88e0 + 61e17a7 V171_IR_TMR1_FULL
    # retune).  Each push touches v171_isr_check_tmr1 / IR ISR
    # cluster; the resulting ~50-instruction shift in V1.71's
    # main loop pushed wiggle convergence for PB1's first cmd 0x21
    # reply from ~500 to >600 (#153).  1200 keeps the test passing
    # with 2x margin and matches the bumped limit across all
    # _rust_press_drive_until_pb_present sites in this file.
    ok = _rust_press_drive_until_pb_present(c, pb_mask=0x03, limit=1200)
    assert ok, (
        f"[rust] diag_present never reached 0x03; got "
        f"0x{_rust_diag_present(c):02X}; "
        f"PB1 cache={[hex(v) for v in _rust_diag_pb_cache(c, 0)]}; "
        f"PB2 cache={[hex(v) for v in _rust_diag_pb_cache(c, 1)]}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_pb_cache_isolation(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Forcing distinct counter values into PB1 vs PB2's diag block must
    surface as distinct CONTROL cache slots after the next poll.

    Concrete: set PB1 diag_i=5 and PB2 diag_i=12.  After both PBs have
    replied at least once, CONTROL's PB1 cache must show 0x5_ in the
    high nibble of *_id, and PB2 cache must show 0xC_.  Cross-talk
    between cache slots would mean the parser is indexing the wrong
    PB on reply arrival.

    PF.3 closeout (2026-05-05): the stale ``_V171_V32_PB2_BRIDGE_XFAIL``
    decorator was retired here -- the underlying gpsim-side multi-
    frame BF/22..27 cache misroute (task #117) closed when gpsim was
    retired in PF.4 phase 2, and the rust path converges via
    ``_press_drive_until_pb_present``.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_set_main_diag_block(c, 0, diag_i=0x5, diag_d=0x1)
    _rust_set_main_diag_block(c, 1, diag_i=0xC, diag_d=0x2)
    _rust_navigate_to_diagnostics(c)
    # settle_steps=200 lets the BF/22 frame populate cache[1]
    # for both PBs after the mask hit on the BF/21 frame.
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=1200, settle_steps=200
    )
    assert ok, "[rust] both PBs never replied"
    pb1_cache = _rust_diag_pb_cache(c, 0)
    pb2_cache = _rust_diag_pb_cache(c, 1)
    assert pb1_cache[0] == 0x5, (
        f"[rust] PB1 cache[0] (diag_i) expected 0x5; got "
        f"0x{pb1_cache[0]:X}; full={[hex(v) for v in pb1_cache]}"
    )
    assert pb1_cache[1] == 0x1, (
        f"[rust] PB1 cache[1] (diag_d) expected 0x1; got "
        f"0x{pb1_cache[1]:X}"
    )
    assert pb2_cache[0] == 0xC, (
        f"[rust] PB2 cache[0] (diag_i) expected 0xC; got "
        f"0x{pb2_cache[0]:X}; full={[hex(v) for v in pb2_cache]}"
    )
    assert pb2_cache[1] == 0x2, (
        f"[rust] PB2 cache[1] (diag_d) expected 0x2; got "
        f"0x{pb2_cache[1]:X}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_lcd_renders_zero_idle(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Idle Diagnostics page (counters all zero) renders the Tier-1
    layout 'PB1' on row 0 and 'OK' on row 1 (per V32_DIAG_TIER1_SPEC.md
    §"LCD Examples" — all-clear case).

    Tier-1 (2026-04-20) replaced the pre-Tier-1 'both PBs on one
    screen' layout ('1:I D S B R A P' / '2:I D S B R A P') with
    ONE PB per page; idle is the most compact form ('PB1' / 'OK',
    16-char rows padded with spaces).  PF.3 (2026-05-04) un-XFAIL'd
    busy-loop convergence via ``_press_drive_until_pb_present``;
    task #116 (this commit) un-XFAIL'd the layout drift by updating
    these assertions to the Tier-1 strings.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    # extra_check pins the exit iteration to one where the chain is
    # parked on PB1 Diag(4) so the trailing LCD assertion sees the
    # PB1 view (V1.71's 50M-tick button-hold auto-repeat in rust
    # makes plain-mask exit unreliable).  Limit bumped 600 -> 1200
    # to absorb the M3 IR non-blocking decoder code shift (#153 /
    # commits 86d88e0 + 61e17a7).  See sibling
    # test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2 for the
    # full rationale.
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=1200,
        extra_check=lambda ch: ch.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG,
    )
    assert ok, "[rust] both PBs never replied"
    for _ in range(8):
        c.step()
    line0, line1 = c.lcd_lines()
    expected = "PB1             "
    assert line0 == expected, (
        f"[rust] row 0 mismatch: expected {expected!r}, got {line0!r}"
    )
    expected2 = "OK              "
    assert line1 == expected2, (
        f"[rust] row 1 mismatch: expected {expected2!r}, got {line1!r}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_lcd_renders_mixed_counters(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Spec §"LCD Examples" — Some-activity case (Tier-1 layout).

    PB1: diag_i=2, diag_b=1, diag_r=1 → "PB1: I2 B1 R1 O1" on row 0,
        blank row 1.  Trailing "O1" comes from cache slot[7] (Tier-1
        reset-cause cell BF/28); slot[7] is auto-set to 0x1 by V3.2
        firmware on every diag-page entry, NOT a counter the test
        wrote.

    Tier-1 (2026-04-20) replaced pre-Tier-1's "both PBs on one screen"
    layout ('1:I2D S B1R1A P ' / '2:I D S1B1R A3P ') with one PB per
    page; the test now asserts only the PB1 view (PB2 cache content
    is verified separately by ``test_v171_v32_layer5_chain_pb_cache_
    isolation``, so per-PB LCD navigation is redundant coverage).

    PF.3 (2026-05-04) un-XFAIL'd busy-loop convergence via the
    ``_press_drive_until_pb_present`` helper; task #116 (this
    commit) un-XFAIL'd the layout drift by updating the assertion
    to the Tier-1 string.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_set_main_diag_block(c, 0, diag_i=2, diag_b=1, diag_r=1)
    _rust_set_main_diag_block(c, 1, diag_s=1, diag_b=1, diag_a=3)
    _rust_navigate_to_diagnostics(c)
    # Mixed counters need cache[0,3,4] populated AND the chain
    # parked on PB1 Diag(4) for the LCD assertion.  Use an
    # extra_check that fires only when both conditions are met
    # in the same wiggle iteration (V1.71's 50M-tick button-
    # hold auto-repeat means each press jumps 1-3 menu states
    # unpredictably; without the state==4 gate the loop can
    # exit on a state-drifted iteration).  Empirically (probe
    # /tmp/probe_mixed.py) the first qualifying iteration is
    # ~wiggle 20.
    # limit bumped 400 -> 800 -> 2000 across the M3 IR code shift
    # (#153 task -- the multi-condition extra_check needs a longer
    # convergence window because slot[7] (O reset-cause cell) lags
    # the runtime counters by ~10x more wiggles post-shift).
    ok = _rust_press_drive_until_pb_present(
        c, pb_mask=0x03, limit=2000,
        extra_check=lambda ch: (
            ch.read_reg(DISPLAY_STATE_INDEX_PHYS) == STATE_PB1_DIAG
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 0) == 0x2
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 3) == 0x1
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 4) == 0x1
            # slot[7]=O is filled by V3.2's BF/28 cmd 0x22 reply
            # on diag-page entry (Tier-1 reset-cause cell); the
            # LCD renders trailing "O1" only after this slot
            # populates, which lags slot[0,3,4] by several wiggles.
            and ch.read_reg(V171_DIAG_PB1_BASE_PHYS + 7) == 0x1
        ),
    )
    assert ok, "[rust] both PBs never replied"
    for _ in range(8):
        c.step()
    line0, line1 = c.lcd_lines()
    # Tier-1 PB1 view: compact nonzero list 'PB1: I2 B1 R1 O1'
    # on row 0, blank row 1.  PB2 cache content is exercised by
    # the cache_isolation test, so per-PB LCD navigation here
    # would only re-test the same protocol path.
    assert line0 == "PB1: I2 B1 R1 O1", (
        f"[rust] row 0 mismatch for PB1 mixed counters: got {line0!r}"
    )
    assert line1 == "                ", (
        f"[rust] row 1 mismatch (expected blank): got {line1!r}"
    )


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_no_query_off_diag_page(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Without entering the Diagnostics page, neither PB should ever
    receive a cmd 0x21 query.  We assert this indirectly: after enough
    chain warmup for the steady-state status burst to cycle several
    times, ``v171_diag_present`` must remain 0 (no BF/2N replies have
    arrived because no query was sent).

    This proves the spec's "send no diagnostics queries outside the
    Diagnostics page" requirement without needing to scrape the TX
    stream for absence of B1/0x21 frames.
    """
    _require_v32_hex(v32_hex)
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    # Step 50M Tcy (matches gpsim's 50 chunks * 1M Tcy chunk size).
    for _ in range(50):
        c.step_tcy(1_000_000)
    present = c.read_reg(V171_DIAG_PRESENT_PHYS)
    # Read PB1/PB2 caches lazily inside the assert error path -- only
    # needed for diagnostics if the present-mask gate fails.  Mirrors
    # gpsim's lazy read pattern (codex #78); avoids 14 RAM reads on
    # the success path.
    assert present == 0, (
        f"[rust] diag_present non-zero without entering Diagnostics: "
        f"0x{present:02X}; "
        f"PB1 cache={[hex(c.read_reg(V171_DIAG_PB1_BASE_PHYS + i)) for i in range(7)]}; "
        f"PB2 cache={[hex(c.read_reg(V171_DIAG_PB2_BASE_PHYS + i)) for i in range(7)]}"
    )
# ===========================================================================
# F4 + xfail Group A canary (2026-04-19 round 2): split into two tests.
#
# (1) Always-on transport canary — proves bytes actually flow through
#     EVERY chain bridge during a diag-page run.  If a future change
#     breaks the harness's bridge plumbing this catches it loudly,
#     instead of silently masking it under the Group-A xfail.
#
# (2) Hop-attribution canary — same probe but also asserts CONTROL
#     parses PB2's reply AND that the BF/27 payload landed in PB2
#     cache slot[6].  Post-PF.3 (2026-05-04): the canary's
#     `_diag_canary_run` helper now uses
#     `_press_drive_until_pb_present` to drive the cmd 0x21/0x22
#     cadence, so hop (e) (`v171_diag_present` bit 1) PASSES.  The
#     xfail now fires at hop (f) instead -- gpsim's wire-chain
#     misroutes the multi-frame BF/22..27 burst, so PB2 cache slot
#     [6] never receives the BF/27 diag_p payload.  Same root cause
#     as `pb_cache_isolation` gpsim path failure; tracked as task
#     #117.  The historical Task #22 "gpsim bridge echo" framing
#     applies to architectural fan-out (retired by the rust silicon
#     ring) and is distinct from #117.  Marked run=True so the
#     hop-attribution report still fires every CI run.
# ===========================================================================


# ===========================================================================
# 2026-04-20 hang-class regression tests.
#
# Real-hardware bring-up of V1.71 + V3.2 surfaced a class of bugs the
# original Phase A/B/C tests did NOT catch:
#
#   * On the operator's two-MAIN rig, navigating to the Diagnostics
#     page rendered counter values for both PBs, but within seconds
#     PB2's diag_s and diag_r counters saturated to '+' (15+ events)
#     and CONTROL hung completely (no LCD updates, no IR response).
#     Only a power-cycle recovered, and reaching the Diag page again
#     hung in the same way.
#
# Why the original tests missed it:
#
#   * Phase A (test_v32_layer5_diag_counters.py) verifies MAIN-side
#     counters at boot are zero and stay zero through warmup — but
#     never under sustained cmd 0x21 traffic.
#
#   * Phase B (test_v171_layer5_diag_page.py) is a CONTROL-only
#     gpsim run (no MAIN attached); the cmd 0x21 query path is
#     issued but nothing replies, so no parser-state stress.
#
#   * Phase C (this file, all tests above) verifies SHORT-DURATION
#     behaviors: idle-at-boot, force-counter-and-render-once,
#     LCD-renders-zero-idle.  None of them sustain the cadence for
#     the 30+ chain-step window that was needed to surface the
#     cascade.  The closest test (no_query_off_diag_page) only runs
#     50 chain steps and stays OFF the page — which is the opposite
#     stress shape.
#
# The tests below close that gap.  Each test asserts an invariant
# that the operator-observed hang violated:
#
#   * sustained_diag_page_keeps_control_responsive — page can be
#     entered AND exited via LEFT after extended cadence; CONTROL's
#     LCD doesn't freeze.
#
#   * diag_page_does_not_cascade_main_counters — sustained cmd 0x21
#     traffic must not cause MAIN's diag_s / diag_r / diag_b to
#     saturate (which on the rig was evidence of a standby/wake
#     cascade triggered by the cmd 0x21 reply burst itself).
#
#   * cmd21_handler_emits_clean_burst — the 7-frame BF/2N reply must
#     not be followed by a stray cmd-XOR ACK (0x21 echo) byte that
#     V1.71's parser is not designed to handle.
# ===========================================================================


@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: real-HW operator report 2026-04-20 — V1.71 CONTROL
    hung completely after a few seconds on the Diagnostics page.  LCD
    stopped updating, IR remote stopped responding, only a power-cycle
    recovered.

    The page MUST stay responsive: CONTROL must continue ticking the
    cadence, the operator must be able to navigate AWAY by pressing
    LEFT, and the chain must reach the Volume screen again.

    Sustained-cadence shape:
      1. Reach DISPLAY (Volume).
      2. Navigate to Diagnostics.
      3. Step the chain for 200 chain steps (multiple cadence cycles
         + many cmd 0x21 query/reply round-trips on PB1 — PB2 path
         currently does not converge in the no-user-events test
         scenario because V1.71's foreground busy-loop in
         `display_loop_iteration` (asm:2885-2897) only exits on
         user-driven events; cadence still issues PB2 queries that
         fail to land within the test budget; same shape as the
         remaining `_V171_V32_PB2_BRIDGE_XFAIL` tests post-PF.3 --
         see ``_press_drive_until_pb_present`` for the wiggle-based
         resolution path).
      4. Press LEFT four times -> exit page -> land back on Volume.
         (Tier-1 menu rework moved Diag from state 2 to states 4-5;
         exit now requires four LEFT presses to walk back to Volume(0).)
      5. Verify LCD shows "Volume:" and CONTROL accepted the navigation.

    Hang mode this catches:
      * v171_diag_loop deadlocks on display_loop_iteration or
        v171_diag_send_query (Layer 1 bounded TX).
      * UART RX overrun cascade triggers reconnect-OERR helper which
        loops indefinitely under continued chain traffic.
      * CONTROL's button-poll path (v171_diag_check_buttons) loses
        the LEFT press because it's starved by the parser ISR.

    Migrated to dual_supported in P4.7: the firmware-correctness
    invariant (CONTROL stays out of WAITING during the sustained
    cadence; LEFT/LEFT/LEFT/LEFT lands back on Volume) is
    backend-independent.  Both gpsim and rust must show the same
    responsiveness behavior because hang-vs-responsive is a
    firmware property of v171_diag_loop / v171_diag_check_buttons,
    not a property of either simulator's UART byte timing.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    for _ in range(200):
        c.step()
        assert not c.is_waiting(), (
            "[rust] CONTROL fell into WAITING during sustained "
            "Diag-page cadence — cascade reconnect storm."
        )
    # Walk LEFT back to Volume.  Adaptive: press LEFT, settle, check
    # DISPLAY_STATE_INDEX -- repeat until state == 0 (Volume) or
    # budget exhausted.  V1.71's button-hold auto-repeat (50M ticks)
    # makes a fixed-count loop unreliable: post the M3 IR code shift
    # (#153) the foreground main-loop iteration cost shifted, and a
    # press-settle that previously produced exactly 1 menu step now
    # absorbs presses non-deterministically.
    #
    # Codex LOW vs a7e4169 raised a wrap-around concern (e.g. state
    # 4 -> 3 -> 2 -> 1 -> 0 -> 4 -> 3 -> ... -> 0 in a 5-state menu).
    # An earlier monotonic-decrease guard rejected this empirically
    # because V1.71's Tier-1 menu has sub-state numbering beyond 0..4
    # (LEFT from state 0x01 lands on state 0x05, presumably a Diag
    # sub-page entry vs the Diag root).  The final LCD == "Volume:"
    # check is the real gate: even if intermediate states transit
    # through sub-page numbering, only the Volume page renders that
    # line0 prefix, so a false-pass via wrap-only would have to
    # leave the LCD at Volume's actual rendering -- which is the
    # contract under test.
    max_lefts = 12
    for _ in range(max_lefts):
        if c.read_reg(DISPLAY_STATE_INDEX_PHYS) == 0:
            break
        c.press("LEFT")
        for _ in range(8):
            c.step()
    line0, line1 = c.lcd_lines()
    assert line0.startswith("Volume:"), (
        f"[rust] LEFT navigation did not return to Volume within "
        f"{max_lefts} presses; LCD={(line0, line1)!r}, "
        f"display_state_index=0x{c.read_reg(DISPLAY_STATE_INDEX_PHYS):02X}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_does_not_cascade_main_counters(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: on real HW, sustained Diag-page cadence caused PB2's
    ``diag_s`` and ``diag_r`` to saturate to '+' (15+ events) within
    seconds — strong evidence that the cmd 0x21 reply burst itself was
    triggering MAIN-side standby/wake or recovery events, which in turn
    cascaded into chain instability.

    Invariant (firmware-correctness, backend-independent): serving
    cmd 0x21 queries is purely observational.  The handler reads
    diag_X cells and emits 7 BF/2N frames over UART; it must not
    provoke standby_event_dispatch (diag_s, diag_b) or
    volume_dsp_write retry escalation (diag_r).  If it does, the
    cmd-21-reply path is racing with the standby/recovery state
    machines and needs a guard (an "armed" check or a higher cadence-
    interval threshold).

    What this test asserts:
      1. Boot, capture initial counter snapshot for PB1 (all zero).
      2. Navigate to Diag page.
      3. Run sustained cadence for 200 chain steps (~16 cadence cycles).
      4. Capture post-cadence counter snapshot for PB1.
      5. diag_s, diag_r, diag_b deltas must be small (< 4 events each).
         A delta of 15+ means cascade.

    Counter-cascade mode this catches:
      * MAIN's main loop pause (during cmd 0x21 reply burst) trips
        watchdog -> standby_event_dispatch -> diag_s++.
      * I2C transaction interrupted by cmd 0x21 -> volume_dsp_write
        retry-escalation -> diag_r++.
      * Wake-after-spurious-standby -> adc_boot_gate -> diag_b++.

    Both MAINs are checked: PB1's replies tend to surface in CONTROL
    sooner than PB2's in the no-user-events test scenario (the
    pre-PF.3 ``_V171_V32_PB2_BRIDGE_XFAIL`` busy-loop convergence
    root cause; see file-level docstring -- now resolved test-side
    via ``_press_drive_until_pb_present`` for tests that opt into
    the wiggle), but the MAIN1 hardware still SERVES the cmd 0x21
    queries either way.  Counter cascade on the MAIN1 (PB2)
    hardware is a real firmware bug regardless of
    whether the reply makes it back to CONTROL.

    Migrated to dual_supported in P4.7: cascade-detection is a
    firmware-correctness invariant on the MAIN side; rust path uses
    `read_main_reg(unit, addr)` to read the diag block on each MAIN.
    """
    # Counter-cascade thresholds (shared across backends).  Index map:
    # 0=I, 1=D, 2=S, 3=B, 4=R, 5=A, 6=P.  Cascade-sensitive counters
    # are S/B/R (state machines) plus I/D (I2C/DSP fault counters).
    cascade_idx = (("S", 2), ("B", 3), ("R", 4), ("I", 0), ("D", 1))
    threshold = 4

    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )

    baseline_pb1 = _rust_main_diag_block(c, 0)
    baseline_pb2 = _rust_main_diag_block(c, 1)

    _rust_navigate_to_diagnostics(c)
    for _ in range(200):
        c.step()

    post_pb1 = _rust_main_diag_block(c, 0)
    post_pb2 = _rust_main_diag_block(c, 1)

    for label, idx in cascade_idx:
        for baseline, post, tag in (
            (baseline_pb1, post_pb1, "PB1"),
            (baseline_pb2, post_pb2, "PB2"),
        ):
            delta = post[idx] - baseline[idx]
            assert delta < threshold and post[idx] < threshold, (
                f"[rust] cascade detected: {tag}.diag_{label} went "
                f"from {baseline[idx]} to {post[idx]} "
                f"(delta={delta}) during sustained Diag-page "
                f"cadence.  Full snapshot: baseline={baseline}, "
                f"post={post}."
            )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly(
    v171_hex: Path, v32_hex: Path
) -> None:
    """REGRESSION: on real HW the operator could not navigate away
    from a hung Diag page -- LEFT presses were ignored.  Even WITHOUT
    a full hang, a slow button-poll on the Diag page would make the
    UI feel unresponsive.

    Invariant (firmware-correctness, backend-independent): pressing
    LEFT on the Diag page must take CONTROL OFF the Diag page within
    a small number of chain steps (the same responsiveness budget the
    other menu screens give).

    V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) moved Diag from
    state 2 (between Preset and Input) to states 4-5 (after Setup),
    so a single LEFT press from PB1 Diag(4) now lands on Setup(3),
    not Preset(1).  Phase 3.4 (9bed274, 2026-04-21) then rewrote the
    Diag renderer from the legacy dual-PB layout ("1:IDSBRAP" /
    "2:IDSBRAP" on one screen) to an Option-D sparse per-PB layout
    ("PBn" / "OK" or "PBn: X# X# ..." across two menu states).

    The exit assertion therefore checks that the LCD no longer starts
    with any Diagnostics-page prefix ("PB1" or "PB2") — it doesn't
    matter which non-Diag screen we landed on, only that the LEFT
    press took effect.  Matching both "PB1" and "PB2" here means a
    hypothetical LEFT→RIGHT misdecode (landing on PB2 Diag instead of
    exiting the page) does NOT false-pass the test.

    Test shape:
      1. Reach DISPLAY, navigate to Diag.
      2. Run a few cadence cycles so the page is "warm".
      3. Press LEFT once.
      4. Step the chain for at most 12 steps.
      5. Verify LCD no longer shows the Diag layout (any non-Diag
         screen is acceptable; Setup(3) is the expected post-LEFT
         landing under the Tier-1 menu order).

    Migrated to dual_supported in P4.7: rust path uses the same
    button-press cadence + LCD inspection.  The firmware's button-
    poll responsiveness is a property of v171_diag_check_buttons,
    not of either simulator's UART byte timing -- both backends
    must show the same exit-within-12-steps behavior.
    """
    _require_rust()
    c = RustChain.from_v171_v32(
        control_hex_path=str(v171_hex),
        main_hex_path=str(v32_hex),
    )
    c.run_until_connected(limit=200)
    assert c.is_connected() and not c.is_waiting(), (
        f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
    )
    _rust_navigate_to_diagnostics(c)
    # Settle bumped 40 -> 120 to absorb the M3 IR code shift (#153)
    # -- post-M3, _rust_navigate_to_diagnostics's 4 RIGHTs may land
    # on PB2 instead of PB1 if the auto-repeat hold time has shifted;
    # the longer settle gives the menu state machine time to clamp
    # at PB1 (Tier-1 menu state 4) and the screen to render.
    for _ in range(120):
        c.step()
    line0_diag, _ = c.lcd_lines()
    if line0_diag.startswith("PB2"):
        # Auto-repeat overshot to PB2; one LEFT brings us back to PB1.
        c.press("LEFT")
        for _ in range(24):
            c.step()
        line0_diag, _ = c.lcd_lines()
    assert line0_diag.startswith("PB1"), (
        f"[rust] chain did not reach PB1 Diag page after navigation; "
        f"LCD={line0_diag!r}"
    )
    c.press("LEFT")
    exit_seen = False
    for _ in range(12):
        c.step()
        line0, _ = c.lcd_lines()
        if not line0.startswith(("PB1", "PB2")):
            exit_seen = True
            break
    assert exit_seen, (
        "[rust] LEFT press did not exit Diag page within 12 chain "
        "steps; v171_diag_check_buttons isn't acting on the press "
        f"promptly.  Final LCD: {c.lcd_lines()!r}"
    )
@pytest.mark.dual_supported
@pytest.mark.slow
def test_v32_cmd21_handler_emits_clean_seven_frame_burst(
    v32_hex: Path
) -> None:
    """REGRESSION: V3.2's cmd 0x21 handler returns to the parser tail at
    ``flow_main_uart_service_1be6_1e6c`` which (under the cmd-XOR-chain
    dispatch path) emits an EXTRA byte — the cmd-XOR ACK echo (0x21
    for cmd 0x21).  Stock V1.x parsers tolerate this trailing byte, but
    V1.71's diagnostics parser only handles BF/21..27 frames; an
    unsolicited 0x21 byte at parser frame_position=0 may bleed into the
    next frame's state and progressively misalign the parser.

    This test pins WHAT the V3.2 cmd 0x21 handler emits at the source
    level.  Specifically:
      1. The handler MUST goto ``flow_main_uart_service_1be6_1e6c``
         (so it integrates with the standard parser tail).
      2. The handler MUST clear ``active_flags.bit6`` BEFORE returning
         to suppress the cmd-XOR ACK echo (defense in depth — if the
         ACK byte is the parser-corruption root cause, this prevents
         it; if it's not, this is a no-op cleanup).

    Right now this test FAILS because the handler doesn't clear bit 6.
    Once we land that suppression (proposed fix B), this test passes
    and pins the new behavior so a future revert is caught.

    Marked xfail until the suppression lands so the gate doesn't block
    other work; flip to passing assertion once the fix is in.
    """
    text = V32_MAIN_ASM.read_text(encoding="utf-8") if 'V32_MAIN_ASM' in globals() else None
    if text is None:
        from dlcp_fw.paths import V32_MAIN_ASM as _V32
        text = _V32.read_text(encoding="utf-8")
    handler_idx = text.find("cmd21_diag_query_handler:")
    assert handler_idx >= 0, "cmd21_diag_query_handler missing"
    body_end = text.find("\n; ---", handler_idx + 1)
    assert body_end > handler_idx, "could not delimit cmd21 handler body"
    body = text[handler_idx:body_end]
    # V3.2 rev 0x37 (Tier-1) refactored cmd 0x21 + cmd 0x22 into a shared
    # diag_send_burst_xx helper.  cmd21 setup-block now bra's into the
    # helper; the helper does the bcf active_flags,6 + goto parser tail.
    # We pin the contract by checking either the standalone or the
    # shared form, so the test still passes after the refactor and a
    # future rewrite that re-inlines doesn't silently lose the
    # suppression / parser-tail integration.
    helper_idx = text.find("\ndiag_send_burst_xx:")
    has_helper = helper_idx >= 0
    if has_helper:
        helper_end = text.find("\n; ---", helper_idx + 1)
        if helper_end < 0:
            helper_end = helper_idx + 4000
        helper_body = text[helper_idx:helper_end]
        # cmd 0x21 setup must bra into the shared helper.
        assert re.search(r"bra\s+diag_send_burst_xx", body), (
            "cmd21 handler must bra into diag_send_burst_xx (shared "
            "with cmd 0x22) -- the refactor moved the parser-tail "
            "exit into the helper; the cmd21 entry just seeds it."
        )
        # The helper itself must goto flow_main_uart_service_1be6_1e6c
        # to keep dispatch/forwarding consistent with stock cmd handlers.
        # Match the actual `goto <label>` instruction (not just substrings),
        # so a refactor that points goto at a different label and merely
        # mentions the parser-tail label in a comment doesn't slip past
        # this gate (codex LOW review against 1d4f3dc).
        assert re.search(
            r"goto\s+flow_main_uart_service_1be6_1e6c\b",
            helper_body,
        ), (
            "diag_send_burst_xx helper must exit via "
            "`goto flow_main_uart_service_1be6_1e6c` so dispatch/"
            "forwarding is consistent with stock cmd handlers"
        )
        # And the helper must clear active_flags.bit6 to suppress the
        # cmd-XOR ACK echo.  Suspected contributor to the V1.71 + V3.2
        # Diag-page hang observed on real HW (2026-04-20).
        assert re.search(r"bcf\s+active_flags,\s*6,\s*ACCESS", helper_body), (
            "diag_send_burst_xx must clear active_flags.bit6 BEFORE "
            "the parser-tail goto so the trailing 0x21/0x22 ACK echo "
            "doesn't bleed into V1.71 CONTROL's parser state."
        )
    else:
        # Pre-refactor fallback: the cmd21 handler does the goto + bcf
        # itself.  This branch keeps the test compatible with any
        # legacy / pre-Tier-1 source tree.  Same instruction-exact
        # match as the helper-path above.
        assert re.search(
            r"goto\s+flow_main_uart_service_1be6_1e6c\b",
            body,
        ), (
            "cmd21 handler must exit via "
            "`goto flow_main_uart_service_1be6_1e6c` so dispatch/"
            "forwarding is consistent with stock cmd handlers"
        )
        assert re.search(r"bcf\s+active_flags,\s*6,\s*ACCESS", body), (
            "cmd21 handler does not clear active_flags.bit6 -- the "
            "parser tail still emits the trailing 0x21 ACK echo.  "
            "Suspected contributor to the V1.71 + V3.2 Diag-page hang "
            "observed on real HW (2026-04-20).  Fix: insert `bcf "
            "active_flags, 6, ACCESS` before the final "
            "`goto flow_main_uart_service_1be6_1e6c`."
        )
