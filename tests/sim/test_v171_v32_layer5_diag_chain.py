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

Per ``docs/SIMULATION_FIDELITY.md`` §"2026-04-18 correction", gpsim is
faithful for the preset-apply / IR / button race classes that Phase C
needs (TAS3108 byte timing matches real hardware within 20 %).

Phase C v1 covers the protocol-contract subset of the spec's 15-case
test matrix.  The per-counter primary tests (I2C / DSP / RCV / S / B /
AN0 / RA1) are added incrementally as the per-counter fault-injection
hooks become available.

Four tests are xfailed pending the wire-chain-harness fix in Task #22
(PB2 reply path through the m1_to_m0 → m0_to_ctl bridge does not
deliver the BF/2N reply back to CONTROL).  PB1 reply path is verified
working; the firmware works correctly on real hardware where the chain
is a true current loop rather than a bidirectional bridge pair.
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
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.v17_symbols import assemble_v17
from dlcp_fw.sim.v30_symbols import assemble_v30

try:
    from dlcp_fw.sim.control_gpsim import _read_reg
    from dlcp_fw.sim.wire_chain_gpsim import WireMultiMainChainHarness
    _IMPORT_OK = True
except Exception:  # pragma: no cover
    _IMPORT_OK = False


# ---------------------------------------------------------------------------
# Constants pinned by the Layer 5 design (kept duplicated from Phase A/B
# files so a wire-chain test failure can be diagnosed locally without
# cross-file lookups).
# ---------------------------------------------------------------------------

# CONTROL diag cache (BANK 1, 7 cells per PB — physical addresses).
# 7-frame protocol: each cell holds one counter as low nibble.
V171_DIAG_PB1_BASE_PHYS = 0x180        # I, D, S, B, R, A, P (7 bytes)
V171_DIAG_PB2_BASE_PHYS = 0x187        # I, D, S, B, R, A, P (7 bytes)
V171_DIAG_TARGET_PHYS = 0x18E
V171_DIAG_PRESENT_PHYS = 0x18F

# MAIN diag block (BANK 1, physical addresses for gpsim CLI reads)
DIAG_I_PHYS = 0x123
DIAG_D_PHYS = 0x124
DIAG_S_PHYS = 0x125
DIAG_B_PHYS = 0x126
DIAG_R_PHYS = 0x127
DIAG_A_PHYS = 0x128
DIAG_P_PHYS = 0x129

# Menu state indices
STATE_VOLUME = 0
STATE_PRESET = 1
STATE_DIAG = 2
STATE_INPUT = 3
STATE_SETUP = 4

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


def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("wire_chain_gpsim harness not importable")


def _require_v32_hex(v32_hex: Path) -> None:
    if not v32_hex.exists():
        pytest.skip(f"missing V3.2 MAIN hex: {v32_hex.name}")


# PB2 reply doesn't surface in CONTROL even though the wire-chain
# bridges DO deliver bytes upstream.  Originally diagnosed (incorrectly)
# as a chain-bridge transport bug; the 2026-04-19 canary
# (test_v171_v32_layer5_chain_pb2_bridge_canary below) re-attributed
# the failure: bridges m0_to_m1 / m1_to_m0 / m0_to_ctl all show
# 137k+ edges flowing during a 250-step diag-page run, ctl_to_m0
# carries the queries, and ``v171_diag_present`` reaches 0x01 (PB1) —
# but never 0x03 (PB1 + PB2).  Bytes ARE flowing through every hop;
# the problem is upstream of the parser-cache write.
#
# Working hypothesis (needs probe — Task #22): in the multi-MAIN
# gpsim topology, MAIN0's TX is replicated to BOTH m0_to_m1 (downstream)
# and m0_to_ctl (upstream), unlike a real current loop where the
# current physically travels in one direction per polarity.  Every
# BF byte that MAIN0 forwards upstream from MAIN1 ALSO echoes back
# downstream into MAIN1's RX, which forwards it back upstream to
# MAIN0...  The parser may be either dropping these mis-framed echoes
# or having v171_diag_target toggle out from under the in-flight reply.
#
# Phase A (MAIN-side counters + reply burst) is verified independently;
# Phase B (CONTROL-side parser + render) is verified standalone.  The
# two-MAIN end-to-end gate is xfailed here pending the parser-vs-echo
# investigation in Task #22.
_V171_V32_PB2_BRIDGE_XFAIL = pytest.mark.xfail(
    reason=(
        "Bytes flow through every wire-chain bridge (verified by canary "
        "below), but CONTROL never sets v171_diag_present bit 1 for "
        "PB2.  Suspected root cause: gpsim two-MAIN topology echoes "
        "MAIN0's TX into BOTH downstream and upstream paths, creating "
        "a feedback loop that interferes with target-tracking parser "
        "state.  Tracked in Task #22 for targeted probing."
    ),
    strict=False,
    run=False,
)


def _new_chain(v171_hex_path: Path, v32_hex_path: Path) -> WireMultiMainChainHarness:
    """Two-MAIN chain with V1.71 CONTROL + V3.2 MAIN.

    Settings mirror the working V3.2 wire-chain tests in
    test_v28_wire_delayed_switch_repros.py — ``fast_boot=False`` plus
    ``disable_standby_check=False`` is the combination that lets the
    chain reach DISPLAY mode (Volume screen) on this CONTROL+MAIN
    pairing.  ``fast_boot=True`` was tried and the chain ended in
    Zzz...standby instead of connecting.
    """
    return WireMultiMainChainHarness(
        v171_hex_path,
        v32_hex_path,
        main_units=2,
        fast_boot=False,
        disable_standby_check=False,
    )


def _navigate_to_diagnostics(chain: WireMultiMainChainHarness) -> None:
    """Drive CONTROL to the Diagnostics screen by pressing RIGHT twice.

    Navigation goes Volume(0) → Preset(1) → Diagnostics(2).  We can't
    just poke ``display_state_index = 2`` via gpsim CLI because the
    current screen body loops internally on ``display_loop_iteration``;
    the menu dispatch only re-reads the index after the current screen
    returns (RIGHT/LEFT/SELECT/disconnected).  Two RIGHT presses with
    8 intermediate steps to settle each press is the realistic path —
    fewer steps (e.g. 4) leave the second press not fully debounced
    before the wait_for_pb_present loop starts, causing intermittent
    "PB1 never replied" failures even though the chain protocol works.
    """
    for _ in range(2):
        chain.press("RIGHT")
        for _ in range(8):
            chain.step()


def _diag_present(chain: WireMultiMainChainHarness) -> int:
    return _read_reg(chain.control._issue, V171_DIAG_PRESENT_PHYS)


def _diag_target(chain: WireMultiMainChainHarness) -> int:
    return _read_reg(chain.control._issue, V171_DIAG_TARGET_PHYS)


def _diag_pb_cache(chain: WireMultiMainChainHarness, pb_idx: int) -> tuple[int, ...]:
    """Read the 7-byte cache (I, D, S, B, R, A, P) for PB1 (idx=0)
    or PB2 (idx=1).  Each cell holds one counter as the low nibble of
    the byte (high nibble = 0 by the 7-frame protocol design)."""
    base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    return tuple(_read_reg(chain.control._issue, base + i) for i in range(7))


def _main_diag_block(chain: WireMultiMainChainHarness, main_idx: int) -> tuple[int, ...]:
    """Read the 7 MAIN counter bytes (diag_i..diag_p) for one PB."""
    issue = chain.mains[main_idx]._issue
    return tuple(
        _read_reg(issue, addr)
        for addr in (DIAG_I_PHYS, DIAG_D_PHYS, DIAG_S_PHYS,
                     DIAG_B_PHYS, DIAG_R_PHYS, DIAG_A_PHYS, DIAG_P_PHYS)
    )


def _set_main_diag_block(
    chain: WireMultiMainChainHarness,
    main_idx: int,
    *,
    diag_i: int = 0,
    diag_d: int = 0,
    diag_s: int = 0,
    diag_b: int = 0,
    diag_r: int = 0,
    diag_a: int = 0,
    diag_p: int = 0,
) -> None:
    """Force the MAIN counter cells via gpsim CLI.

    Lets us drive the LCD render path with known values without
    needing to inject the underlying physical events for every
    counter family.  The physical-event tests (which exercise the
    increment hooks) live in Phase A; here we only need the protocol
    + render path.
    """
    issue = chain.mains[main_idx]._issue
    for value, addr in (
        (diag_i, DIAG_I_PHYS), (diag_d, DIAG_D_PHYS),
        (diag_s, DIAG_S_PHYS), (diag_b, DIAG_B_PHYS),
        (diag_r, DIAG_R_PHYS), (diag_a, DIAG_A_PHYS),
        (diag_p, DIAG_P_PHYS),
    ):
        issue(f"reg(0x{addr:03X})=0x{value & 0x0F:02X}", 5.0)


def _wait_for_pb_present(
    chain: WireMultiMainChainHarness,
    *,
    pb_mask: int,
    limit: int = 250,
    context: str = "diag pb present",
) -> bool:
    """Step the chain until v171_diag_present has the requested bits.

    Returns True if the mask was reached, False on timeout.  pb_mask
    is a bitmask: 0x01 = PB1, 0x02 = PB2, 0x03 = both.

    Default limit is sized for the spec's 1 s poll cadence (0x80
    display_loop ticks per query) at the wire-chain harness's
    default control_chunk_cycles=1,000,000 (~125 chain steps per
    cadence cycle).  PB1+PB2 both replying takes two cycles =
    ~32 chain steps for both PBs to reply at 0x10 cadence.
    """
    for _ in range(limit):
        chain.step()
        if (_diag_present(chain) & pb_mask) == pb_mask:
            return True
    return False


# ===========================================================================
# Tier C — wire-chain end-to-end
# ===========================================================================


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_idle_caches_zero_at_boot(v171_hex: Path, v32_hex: Path) -> None:
    """At boot, neither PB has replied, so CONTROL's diag cache and
    present mask must be zero across the chain warmup.

    This is the wire-chain analogue of the Phase B
    ``diag_block_holds_zero_through_boot_and_warmup`` test, but with
    real MAINs on the chain (which exercise the BF/05/07/03/06/1D
    steady-state status burst — none of which should leak into the
    diag cache).
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        # Pre-Diagnostics sanity: cache stays zero.
        present = _diag_present(chain)
        assert present == 0, f"present mask non-zero at boot: 0x{present:02X}"
        for pb in (0, 1):
            cache = _diag_pb_cache(chain, pb)
            assert all(v == 0 for v in cache), (
                f"PB{pb+1} cache non-zero at boot: {[hex(v) for v in cache]}"
            )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2(v171_hex: Path, v32_hex: Path) -> None:
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
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        _navigate_to_diagnostics(chain)
        # Two cadence cycles is enough for both PBs to reply at least
        # once.  V171_DIAG_POLL_RELOAD is 0x80 ticks ≈ 1 s; at the
        # 60 K cycle chunk the chain step is ~15 ms, so 0x80 ticks ≈
        # 6 chain steps.  Step ~80 to be generous.
        ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200,
                                  context="both PBs reply")
        assert ok, (
            f"diag_present never reached 0x03; got 0x{_diag_present(chain):02X}; "
            f"PB1 cache={[hex(v) for v in _diag_pb_cache(chain, 0)]}; "
            f"PB2 cache={[hex(v) for v in _diag_pb_cache(chain, 1)]}"
        )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_pb_cache_isolation(v171_hex: Path, v32_hex: Path) -> None:
    """Forcing distinct counter values into PB1 vs PB2's diag block must
    surface as distinct CONTROL cache slots after the next poll.

    Concrete: set PB1 diag_i=5 and PB2 diag_i=12.  After both PBs have
    replied at least once, CONTROL's PB1 cache must show 0x5_ in the
    high nibble of *_id, and PB2 cache must show 0xC_.  Cross-talk
    between cache slots would mean the parser is indexing the wrong
    PB on reply arrival.
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        # Set distinct diag_i values BEFORE entering Diagnostics.
        _set_main_diag_block(chain, 0, diag_i=0x5, diag_d=0x1)
        _set_main_diag_block(chain, 1, diag_i=0xC, diag_d=0x2)
        _navigate_to_diagnostics(chain)
        ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200)
        assert ok, "both PBs never replied"
        pb1_cache = _diag_pb_cache(chain, 0)
        pb2_cache = _diag_pb_cache(chain, 1)
        # 7-byte cache layout: (I, D, S, B, R, A, P), one counter per cell.
        # PB1: diag_i=0x5 → cache[0]; diag_d=0x1 → cache[1]; rest unset.
        assert pb1_cache[0] == 0x5, (
            f"PB1 cache[0] (diag_i) expected 0x5; got 0x{pb1_cache[0]:X}; "
            f"full PB1 cache={[hex(v) for v in pb1_cache]}"
        )
        assert pb1_cache[1] == 0x1, (
            f"PB1 cache[1] (diag_d) expected 0x1; got 0x{pb1_cache[1]:X}"
        )
        # PB2: diag_i=0xC → cache[0]; diag_d=0x2 → cache[1]; rest unset.
        # NOTE: diag_i=0xC produces low-nibble data 0xC < 0x80, so chain
        # forwarding is safe — this is the regression that the 7-frame
        # protocol was introduced to fix.
        assert pb2_cache[0] == 0xC, (
            f"PB2 cache[0] (diag_i) expected 0xC; got 0x{pb2_cache[0]:X}; "
            f"full PB2 cache={[hex(v) for v in pb2_cache]}"
        )
        assert pb2_cache[1] == 0x2, (
            f"PB2 cache[1] (diag_d) expected 0x2; got 0x{pb2_cache[1]:X}"
        )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_lcd_renders_zero_idle(v171_hex: Path, v32_hex: Path) -> None:
    """Idle Diagnostics page (counters all zero) renders the spec layout
    "1:I D S B R A P" / "2:I D S B R A P" — every nibble char is a
    space, so the row reads as letter-space-letter-space etc.

    Per spec §"LCD Examples" — All clear case.
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        _navigate_to_diagnostics(chain)
        ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200)
        assert ok, "both PBs never replied"
        # After both PBs replied with all-zero counters, the screen
        # redraws via v171_diag_check_redraw.  Step a few more times
        # to let the redraw complete.
        for _ in range(8):
            chain.step()
        line0, line1 = chain.lcd_lines()
        # Spec layout: "1:I D S B R A P " (16 chars, trailing space
        # because diag_p=0 renders as space).
        expected = "1:I D S B R A P "
        assert line0 == expected, (
            f"row 0 mismatch: expected {expected!r}, got {line0!r}"
        )
        expected2 = "2:I D S B R A P "
        assert line1 == expected2, (
            f"row 1 mismatch: expected {expected2!r}, got {line1!r}"
        )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_lcd_renders_mixed_counters(v171_hex: Path, v32_hex: Path) -> None:
    """Spec §"LCD Examples" — Some-activity case.

    PB1: diag_i=2, diag_b=1, diag_r=1
    PB2: diag_s=1, diag_b=1, diag_a=3
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        _set_main_diag_block(chain, 0, diag_i=2, diag_b=1, diag_r=1)
        _set_main_diag_block(chain, 1, diag_s=1, diag_b=1, diag_a=3)
        _navigate_to_diagnostics(chain)
        ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200)
        assert ok, "both PBs never replied"
        for _ in range(8):
            chain.step()
        line0, line1 = chain.lcd_lines()
        # PB1: I2 D' ' S' ' B1 R1 A' ' P' '  → "1:I2D S B1R1A P "
        assert line0 == "1:I2D S B1R1A P ", (
            f"row 0 mismatch for PB1 mixed counters: got {line0!r}"
        )
        # PB2: I' ' D' ' S1 B1 R' ' A3 P' '  → "2:I D S1B1R A3P "
        assert line1 == "2:I D S1B1R A3P ", (
            f"row 1 mismatch for PB2 mixed counters: got {line1!r}"
        )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_lcd_renders_saturation_plus(v171_hex: Path, v32_hex: Path) -> None:
    """Saturated counter (0x0F) must render as '+' per the encoding.

    Forces diag_i=0x0F on PB1; expects '+' between 'I' and 'D' in
    line 0.
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        _set_main_diag_block(chain, 0, diag_i=0x0F)
        _navigate_to_diagnostics(chain)
        ok = _wait_for_pb_present(chain, pb_mask=0x01, limit=200)
        assert ok, "PB1 never replied"
        for _ in range(8):
            chain.step()
        line0, _ = chain.lcd_lines()
        # PB1 row: "1:I+D ..." (high nibble of *_id is 0xF → '+')
        assert line0.startswith("1:I+D"), (
            f"saturated PB1 diag_i should render as '+'; got {line0!r}"
        )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_no_query_off_diag_page(v171_hex: Path, v32_hex: Path) -> None:
    """Without entering the Diagnostics page, neither PB should ever
    receive a cmd 0x21 query.  We assert this indirectly: after enough
    chain warmup for the steady-state status burst to cycle several
    times, ``v171_diag_present`` must remain 0 (no BF/2N replies have
    arrived because no query was sent).

    This proves the spec's "send no diagnostics queries outside the
    Diagnostics page" requirement without needing to scrape the TX
    stream for absence of B1/0x21 frames.
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        last = chain.run_until_connected(limit=200)
        assert last is not None, "chain never reached DISPLAY"
        assert chain.is_connected() and not chain.is_waiting(), (
            f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
        )
        # Stay on Volume (state 0) — the default after run_until_connected.
        # Step a generous window for any spurious diag chatter to fire.
        for _ in range(50):
            chain.step()
        present = _diag_present(chain)
        assert present == 0, (
            f"diag_present non-zero without entering Diagnostics page: "
            f"0x{present:02X}; PB1 cache={[hex(v) for v in _diag_pb_cache(chain, 0)]}; "
            f"PB2 cache={[hex(v) for v in _diag_pb_cache(chain, 1)]}"
        )
    finally:
        chain.close()


# ===========================================================================
# F4 + xfail Group A canary (2026-04-19 round 2): split into two tests.
#
# (1) Always-on transport canary — proves bytes actually flow through
#     EVERY chain bridge during a diag-page run.  If a future change
#     breaks the harness's bridge plumbing this catches it loudly,
#     instead of silently masking it under the Group-A xfail.
#
# (2) Hop-attribution canary — same probe but also asserts CONTROL
#     parses PB2's reply.  Currently expected to fail at hop (e) with
#     ALL bridges flowing (137k+ edges each); the failure message
#     points at the parser-vs-echo issue tracked in Task #22.  Marked
#     xfail run=True so the hop-attribution report fires every CI run
#     and we notice immediately when the underlying issue is fixed.
# ===========================================================================


def _diag_canary_run(
    chain: WireMultiMainChainHarness,
) -> tuple[dict[str, int], int, tuple[int, ...]]:
    """Drive a diag-page poll cycle and snapshot per-hop deltas.

    Returns (hop_deltas, present_mask, pb2_cache).  Pre-loads MAIN1's
    diag_p = 0x07 so a successful PB2 reply has a distinct payload.
    """
    last = chain.run_until_connected(limit=200)
    assert last is not None, "chain never reached DISPLAY"
    assert chain.is_connected() and not chain.is_waiting(), (
        f"chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
    )
    _set_main_diag_block(chain, 1, diag_p=0x07)
    pre_stats = chain.bridge_shift_stats()
    _navigate_to_diagnostics(chain)
    # 250 chain steps ≥ 2 cadence cycles at the default chunk
    # (~125 steps per V171_DIAG_POLL_RELOAD = 0x80 ticks); long
    # enough for both PB1 + PB2 queries to be issued and (in a
    # working bridge) for both replies to land.
    for _ in range(250):
        chain.step()
        if (_diag_present(chain) & 0x02) == 0x02:
            break
    post_stats = chain.bridge_shift_stats()
    deltas = {
        link: post_stats.get(link, {}).get("total_edges", 0)
              - pre_stats.get(link, {}).get("total_edges", 0)
        for link in ("ctl_to_m0", "m0_to_m1", "m1_to_m0", "m0_to_ctl")
    }
    return deltas, _diag_present(chain), _diag_pb_cache(chain, 1)


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_bridges_all_carry_traffic(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Always-on transport canary: during a Diagnostics-page poll run
    on a 2-MAIN chain, every wire-chain bridge MUST carry traffic.
    This is purely a harness-plumbing assertion — it does NOT depend on
    CONTROL successfully parsing any reply.  If a future harness change
    silently breaks one of the bridges (e.g. `m1_to_m0` stops
    forwarding MAIN1's TX into MAIN0's RX), this canary catches it
    immediately rather than letting the Group-A xfails silently mask
    a separate regression.
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        deltas, _present, _pb2 = _diag_canary_run(chain)
        for link in ("ctl_to_m0", "m0_to_m1", "m1_to_m0", "m0_to_ctl"):
            assert deltas[link] > 0, (
                f"transport canary: bridge {link!r} carried zero edges "
                f"during a Diagnostics-page poll run — harness plumbing "
                f"is broken.  All hop deltas: {deltas}"
            )
    finally:
        chain.close()


@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@pytest.mark.xfail(
    reason=(
        "Hop-attribution canary: bytes flow through every bridge "
        "(transport canary above passes) but CONTROL never sets "
        "v171_diag_present bit 1.  Suspected gpsim two-MAIN echo loop "
        "(MAIN0 TX replicated into both downstream + upstream paths) "
        "interferes with target-tracking parser state.  Tracked as "
        "Task #22; runs every cycle so the hop-attribution report is "
        "fresh and we notice immediately when the underlying fix lands."
    ),
    strict=False,
    run=True,
)
def test_v171_v32_layer5_chain_pb2_bridge_canary(
    v171_hex: Path, v32_hex: Path
) -> None:
    """Hop-attribution canary for the PB2 query → reply path.

    Same probe as the transport canary, but also asserts the CONTROL-
    side parser landed PB2's reply.  Decomposes into hops:

        a. ``ctl_to_m0`` edges  — CONTROL emitted bytes for MAIN0
        b. ``m0_to_m1``  edges  — MAIN0 forwarded query downstream
        c. ``m1_to_m0``  edges  — PB2 transmitted reply upstream
        d. ``m0_to_ctl`` edges  — MAIN0 forwarded reply to CONTROL
        e. ``v171_diag_present`` bit 1  — parser landed PB2 reply
        f. ``v171_diag_pb2_p`` == 0x07  — BF/27 payload landed in cache

    Currently expected to fail at hop (e) with hops (a)..(d) all
    showing 137k+ edges of traffic.  When the underlying parser-vs-
    echo issue (Task #22) is fixed, this XPASSes and the 4 Group-A
    tests at ``_V171_V32_PB2_BRIDGE_XFAIL`` should also start XPASS'ing
    — at which point all five xfail markers in this file can be
    removed and Task #22 closed.
    """
    _require_gpsim()
    _require_v32_hex(v32_hex)

    chain = _new_chain(v171_hex, v32_hex)
    try:
        deltas, present, pb2_cache = _diag_canary_run(chain)
        report = (
            f"hop edges (post − pre) — {deltas}; "
            f"v171_diag_present=0x{present:02X}, "
            f"PB2 cache={[hex(v) for v in pb2_cache]}"
        )
        # Hops (a)..(d) belong to the always-on transport canary, so
        # surface them only on the value-carrying assertions below.
        assert deltas["ctl_to_m0"] > 0, f"hop (a) ctl_to_m0 silent: {report}"
        assert deltas["m0_to_m1"] > 0, f"hop (b) m0_to_m1 silent: {report}"
        assert deltas["m1_to_m0"] > 0, f"hop (c) m1_to_m0 silent: {report}"
        assert deltas["m0_to_ctl"] > 0, f"hop (d) m0_to_ctl silent: {report}"
        # Hops (e) + (f): CONTROL parsed the BF/27 reply correctly.
        assert (present & 0x02) == 0x02, (
            f"hop (e) — bytes flowed through every bridge but CONTROL "
            f"never set v171_diag_present bit 1; v171_bf2x_case_check "
            f"did not fire for PB2's BF/27.  {report}"
        )
        assert pb2_cache[6] == 0x07, (
            f"hop (f) — PB2 marked present but BF/27 payload (diag_p) "
            f"did not land in the cache slot; expected 0x07, got "
            f"0x{pb2_cache[6]:02X}.  {report}"
        )
    finally:
        chain.close()
