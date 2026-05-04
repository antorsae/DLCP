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


# ---------------------------------------------------------------------------
# Rust-side mirrors of the gpsim navigation / readback helpers.  Kept
# next to the gpsim helpers so the dual-supported tests don't have to
# branch on `dlcp_sim_backend` for every line -- each backend reads its
# own helper, both produce the same firmware-observable invariant.
# ---------------------------------------------------------------------------


def _rust_navigate_to_diagnostics(rust_chain) -> None:  # type: ignore[no-untyped-def]
    """Mirror of `_navigate_to_diagnostics` for the rust facade.

    Drives CONTROL to PB1 Diag(4) by pressing RIGHT four times with
    8 intermediate steps to settle each press.  Identical key cadence
    to the gpsim helper above; both target the same V1.71 menu state
    machine, which doesn't change behavior across simulators.
    """
    for _ in range(4):
        rust_chain.press("RIGHT")
        for _ in range(8):
            rust_chain.step()


def _rust_main_diag_block(rust_chain, main_idx: int) -> tuple[int, ...]:  # type: ignore[no-untyped-def]
    """Mirror of `_main_diag_block` for the rust facade.

    Reads MAIN's 7 diag-counter bytes (diag_i..diag_p at
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
    diag_p: int = 0,
) -> None:
    """Mirror of `_set_main_diag_block` for the rust facade.

    Writes each diag-counter cell on MAIN via the per-MAIN write
    primitive (`Chain.write_main_reg(unit, addr, value)`).  Same
    low-nibble masking as the gpsim helper.
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
    """Mirror of `_diag_pb_cache` for the rust facade.  Reads the
    7-byte cache (I, D, S, B, R, A, P) for PB1 (idx=0) or PB2 (idx=1).
    """
    base = V171_DIAG_PB1_BASE_PHYS if pb_idx == 0 else V171_DIAG_PB2_BASE_PHYS
    return tuple(rust_chain.read_reg(base + i) for i in range(7))


def _rust_wait_for_pb_present(  # type: ignore[no-untyped-def]
    rust_chain, *, pb_mask: int, limit: int = 250,
) -> bool:
    """Mirror of `_wait_for_pb_present`.  Steps the chain until
    `v171_diag_present` has the requested PB bits set, or `limit`
    chain steps elapse.  Returns True on success.
    """
    for _ in range(limit):
        if (_rust_diag_present(rust_chain) & pb_mask) == pb_mask:
            return True
        rust_chain.step()
    return (_rust_diag_present(rust_chain) & pb_mask) == pb_mask


# ---------------------------------------------------------------------------
# Hex source skew caveat (post codex review of 16fa3ee, 2026-05-03)
# ---------------------------------------------------------------------------
# The rust path uses `Chain.from_v171_v32()` which loads CANONICAL
# release hexes from `firmware/patched/releases/{DLCP_Control_V1.71,
# DLCP_Firmware_V3.2}.hex`.  The gpsim path uses the `v171_hex` and
# `v32_hex` fixtures which build from the CURRENT source via
# `assemble_v17(V171_CONTROL_ASM, ...)` and `assemble_v30(V32_MAIN_ASM,
# ...)`.  For unmodified source the two binaries are byte-identical;
# however a Phase A/B source change landing BEFORE a canonical
# release rebuild (`scripts/build_v32_release.py` /
# `scripts/build_v171_release.py`) would silently make the rust path
# test stale binaries while the gpsim path tests current source.
#
# Tracking: pending sim-rewrite progress-ledger entry "Add hex-path
# overrides to `Chain.from_v171_v32` to avoid stale-canonical skew".
# Until that lands, dual-mode failures that diverge between the two
# backends should first verify both backends are loading the SAME
# firmware revision -- compare the EEPROM revision byte at MAIN
# `eeprom_data[0x82]` (per `scripts/build_v32_release.py`) and the
# `control_release_metadata[11]` byte at CONTROL flash byte 0x77BB
# (per `scripts/build_v171_release.py`).
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
#
# UPDATE (2026-04-27, see `feature/sim-rewrite-rust`,
# `docs/SIM_REWRITE_RUST_PROGRESS.md` task P3.6a/P3.6b):
# The "bridge-mirror echo" diagnosis above turned out to be only
# half the story.  The Rust simulator rewrite uses a silicon-correct
# directional ring (CONTROL.TX -> MAIN0.RX -> MAIN1.RX -> CONTROL.RX,
# 3 directional edges, no fan-out, no self-loops) which is
# *structurally* incapable of reproducing the bridge mirror.  The
# 2026-04-27 working assumption was that rust would land the same
# PB1-only saturation as gpsim ("synthetic + firmware-driven probes
# show CONTROL emits both queries, MAIN0 emits the full 7-frame
# reply burst, MAIN1 forwards the BF/27/00 frame to CONTROL.RX
# cleanly (no OERR), but CONTROL never successfully processes BF/27
# through the BF/2N last-frame path").
#
# UPDATE (2026-05-04, task #94): empirically retested rust on the
# `_rust_navigate_to_diagnostics` -> wait-for-PB-present path.
# Rust does NOT saturate at PB1 -- it shows ZERO replies
# (v171_diag_present stays 0x00 across 2000 step() chunks ~= 400M
# Tcy).  The 2026-04-27 prediction was assumed-based, not
# empirical: the four xfailed tests below use `run=False`, so they
# never actually executed on rust to verify the PB1-saturation
# claim.  The actual rust gap is a separate Diag-page query
# emission / parser issue distinct from the gpsim bridge-mirror
# saturation -- track in task #94 (re-probe the cmd 0x21 emission
# path on V1.71 CONTROL + the BF/21..27 reply path on V3.2 MAIN).
#
# HARDWARE RESULT (2026-04-27): Path 1 hardware probe ran on the
# real DLCP rig (V1.71 CONTROL + V3.2 MAIN0 + V3.2 MAIN1, both MAINs
# healthy via cmd 0x44 USB diag).  Operator navigated CONTROL to
# PB1 Diag (state 4) and PB2 Diag (state 5); LCD camera captures
# show:
#   PB1: I+ D1 SE B4 / RA A3 O8 V6 W+..   (Overflow layout, cells)
#   PB2: I+ D  S+ B  / R+ A9  P  OB W9..  (Overflow layout, cells)
# Both pages have the `PBn:` colon prefix -> per V1.71 Tier-1 layout
# spec `v171_diag_present.bit_n = 1` on real silicon -> BOTH BF/2N
# reply convergences work on real hardware.  V1.71 firmware is
# therefore CORRECT; the gpsim Python harness shows residual PB2
# saturation (PB1 reply lands, PB2 reply lost), which the
# 2026-04-27 working assumption framed as a "shared timing /
# electrical / clock-domain" gap that rust would also reproduce.
# 2026-05-04 empirical update (task #94): rust does NOT reproduce
# the same gap -- it yields ZERO replies (neither PB1 nor PB2),
# i.e., the Diag-page cmd 0x21 query/reply path doesn't fire at
# all on rust.  So the gap is gpsim-specific (PB2-only saturation,
# tracked via Task #22 hypotheses listed in
# `docs/SIM_REWRITE_RUST_PROGRESS.md` P3.6b) AND rust has its own
# distinct gap (task #94, query never triggers PB1 reply).  The
# XFAIL marker stays until both close.
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
    """Drive CONTROL to the PB1 Diagnostics screen by pressing RIGHT four times.

    V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) moved Diagnostics
    from state 2 to states 4-5.  New ring:

        Volume(0) -> Preset(1) -> Input(2) -> Setup(3) -> PB1 Diag(4) -> PB2 Diag(5)

    Reaching PB1 Diag(4) takes FOUR RIGHT presses from Volume(0).  We
    can't just poke ``display_state_index = 4`` via gpsim CLI because
    the current screen body loops internally on
    ``display_loop_iteration``; the menu dispatch only re-reads the
    index after the current screen returns (RIGHT/LEFT/SELECT/
    disconnected).  Four RIGHT presses with 8 intermediate steps to
    settle each press is the realistic path -- fewer steps leave a
    press not fully debounced before the next press fires, causing
    intermittent "PB1 never replied" failures even though the chain
    protocol works.

    To navigate further to PB2 Diag(5), press RIGHT once more after
    calling this helper.
    """
    for _ in range(4):
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


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_idle_caches_zero_at_boot(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
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
    "STBY-stuck-pressed" -> Zzz).  Rust path uses the canonical
    V1.71 + V3.2 release hexes from the binary's path resolution,
    not the test's freshly-built ``v32_hex`` tmp fixture (which
    is identical for unmodified source).
    """
    _require_v32_hex(v32_hex)
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
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
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
            )
            # Pre-Diagnostics sanity: cache stays zero.
            present = _diag_present(chain)
            assert present == 0, (
                f"[gpsim] present mask non-zero at boot: 0x{present:02X}"
            )
            for pb in (0, 1):
                cache = _diag_pb_cache(chain, pb)
                assert all(v == 0 for v in cache), (
                    f"[gpsim] PB{pb+1} cache non-zero at boot: "
                    f"{[hex(v) for v in cache]}"
                )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
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

    XFailed on BOTH backends, but for distinct underlying gaps:
      * gpsim: shared PB2 sim fidelity gap -- saturates
        `v171_diag_present` at 0x01 (PB1 reply works, PB2 reply lost).
      * rust: separate Diag-page query gap (task #94) -- ZERO
        replies on rust (`v171_diag_present` stays 0x00); the prior
        2026-04-27 claim that rust also saturates at PB1 was
        assumption-based since `_V171_V32_PB2_BRIDGE_XFAIL` uses
        `run=False` (the body never executed empirically).
    Real hardware serves both PB convergences (verified 2026-04-27,
    see file-level UPDATE).  Marker-only migration to
    `dual_supported` keeps both backends running the same xfail
    while their distinct gaps stay open.
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
        c.run_until_connected(limit=200)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
        )
        _rust_navigate_to_diagnostics(c)
        ok = _rust_wait_for_pb_present(c, pb_mask=0x03, limit=200)
        assert ok, (
            f"[rust] diag_present never reached 0x03; got "
            f"0x{_rust_diag_present(c):02X}; "
            f"PB1 cache={[hex(v) for v in _rust_diag_pb_cache(c, 0)]}; "
            f"PB2 cache={[hex(v) for v in _rust_diag_pb_cache(c, 1)]}"
        )

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: "
                f"lcd={chain.lcd_lines()!r}"
            )
            _navigate_to_diagnostics(chain)
            # Two cadence cycles is enough for both PBs to reply at
            # least once.  V171_DIAG_POLL_RELOAD is 0x80 ticks ≈ 1 s;
            # at the 60 K cycle chunk the chain step is ~15 ms, so
            # 0x80 ticks ≈ 6 chain steps.  Step ~80 to be generous.
            ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200,
                                      context="both PBs reply")
            assert ok, (
                f"[gpsim] diag_present never reached 0x03; got "
                f"0x{_diag_present(chain):02X}; "
                f"PB1 cache={[hex(v) for v in _diag_pb_cache(chain, 0)]}; "
                f"PB2 cache={[hex(v) for v in _diag_pb_cache(chain, 1)]}"
            )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_pb_cache_isolation(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Forcing distinct counter values into PB1 vs PB2's diag block must
    surface as distinct CONTROL cache slots after the next poll.

    Concrete: set PB1 diag_i=5 and PB2 diag_i=12.  After both PBs have
    replied at least once, CONTROL's PB1 cache must show 0x5_ in the
    high nibble of *_id, and PB2 cache must show 0xC_.  Cross-talk
    between cache slots would mean the parser is indexing the wrong
    PB on reply arrival.

    XFailed on BOTH backends per the shared PB2 sim fidelity gap
    (the PB2 reply never lands in CONTROL's parser).  Marker-only
    migration to `dual_supported`.
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
        c.run_until_connected(limit=200)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
        )
        _rust_set_main_diag_block(c, 0, diag_i=0x5, diag_d=0x1)
        _rust_set_main_diag_block(c, 1, diag_i=0xC, diag_d=0x2)
        _rust_navigate_to_diagnostics(c)
        ok = _rust_wait_for_pb_present(c, pb_mask=0x03, limit=200)
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

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: "
                f"lcd={chain.lcd_lines()!r}"
            )
            # Set distinct diag_i values BEFORE entering Diagnostics.
            _set_main_diag_block(chain, 0, diag_i=0x5, diag_d=0x1)
            _set_main_diag_block(chain, 1, diag_i=0xC, diag_d=0x2)
            _navigate_to_diagnostics(chain)
            ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200)
            assert ok, "[gpsim] both PBs never replied"
            pb1_cache = _diag_pb_cache(chain, 0)
            pb2_cache = _diag_pb_cache(chain, 1)
            # 7-byte cache layout: (I, D, S, B, R, A, P), one counter per cell.
            # PB1: diag_i=0x5 → cache[0]; diag_d=0x1 → cache[1]; rest unset.
            assert pb1_cache[0] == 0x5, (
                f"[gpsim] PB1 cache[0] (diag_i) expected 0x5; "
                f"got 0x{pb1_cache[0]:X}; "
                f"full PB1 cache={[hex(v) for v in pb1_cache]}"
            )
            assert pb1_cache[1] == 0x1, (
                f"[gpsim] PB1 cache[1] (diag_d) expected 0x1; "
                f"got 0x{pb1_cache[1]:X}"
            )
            # PB2: diag_i=0xC → cache[0]; diag_d=0x2 → cache[1]; rest unset.
            # NOTE: diag_i=0xC produces low-nibble data 0xC < 0x80, so chain
            # forwarding is safe — this is the regression that the 7-frame
            # protocol was introduced to fix.
            assert pb2_cache[0] == 0xC, (
                f"[gpsim] PB2 cache[0] (diag_i) expected 0xC; "
                f"got 0x{pb2_cache[0]:X}; "
                f"full PB2 cache={[hex(v) for v in pb2_cache]}"
            )
            assert pb2_cache[1] == 0x2, (
                f"[gpsim] PB2 cache[1] (diag_d) expected 0x2; "
                f"got 0x{pb2_cache[1]:X}"
            )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_lcd_renders_zero_idle(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Idle Diagnostics page (counters all zero) renders the spec layout
    "1:I D S B R A P" / "2:I D S B R A P" — every nibble char is a
    space, so the row reads as letter-space-letter-space etc.

    Per spec §"LCD Examples" — All clear case.

    XFailed on BOTH backends per the shared PB2 sim fidelity gap
    (PB2 reply doesn't surface in CONTROL's parser).  Note: the
    expected LCD strings here are from the PRE-Tier-1 spec; under
    V1.71 Tier-1 + Phase 3.4 (Option-D layout) the actual rendering
    is per-PB ("PB1" / "OK..." / "PB1: X#...").  Both effects keep
    the test xfailing; marker-only migration to `dual_supported`.
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
        c.run_until_connected(limit=200)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
        )
        _rust_navigate_to_diagnostics(c)
        ok = _rust_wait_for_pb_present(c, pb_mask=0x03, limit=200)
        assert ok, "[rust] both PBs never replied"
        for _ in range(8):
            c.step()
        line0, line1 = c.lcd_lines()
        expected = "1:I D S B R A P "
        assert line0 == expected, (
            f"[rust] row 0 mismatch: expected {expected!r}, got {line0!r}"
        )
        expected2 = "2:I D S B R A P "
        assert line1 == expected2, (
            f"[rust] row 1 mismatch: expected {expected2!r}, got {line1!r}"
        )

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: "
                f"lcd={chain.lcd_lines()!r}"
            )
            _navigate_to_diagnostics(chain)
            ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200)
            assert ok, "[gpsim] both PBs never replied"
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
                f"[gpsim] row 0 mismatch: expected {expected!r}, got {line0!r}"
            )
            expected2 = "2:I D S B R A P "
            assert line1 == expected2, (
                f"[gpsim] row 1 mismatch: expected {expected2!r}, got {line1!r}"
            )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
@_V171_V32_PB2_BRIDGE_XFAIL
def test_v171_v32_layer5_chain_lcd_renders_mixed_counters(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
) -> None:
    """Spec §"LCD Examples" — Some-activity case.

    PB1: diag_i=2, diag_b=1, diag_r=1
    PB2: diag_s=1, diag_b=1, diag_a=3

    XFailed on BOTH backends per the shared PB2 sim fidelity gap.
    Marker-only migration to `dual_supported`.
    """
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
        c.run_until_connected(limit=200)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
        )
        _rust_set_main_diag_block(c, 0, diag_i=2, diag_b=1, diag_r=1)
        _rust_set_main_diag_block(c, 1, diag_s=1, diag_b=1, diag_a=3)
        _rust_navigate_to_diagnostics(c)
        ok = _rust_wait_for_pb_present(c, pb_mask=0x03, limit=200)
        assert ok, "[rust] both PBs never replied"
        for _ in range(8):
            c.step()
        line0, line1 = c.lcd_lines()
        assert line0 == "1:I2D S B1R1A P ", (
            f"[rust] row 0 mismatch for PB1 mixed counters: got {line0!r}"
        )
        assert line1 == "2:I D S1B1R A3P ", (
            f"[rust] row 1 mismatch for PB2 mixed counters: got {line1!r}"
        )

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: "
                f"lcd={chain.lcd_lines()!r}"
            )
            _set_main_diag_block(chain, 0, diag_i=2, diag_b=1, diag_r=1)
            _set_main_diag_block(chain, 1, diag_s=1, diag_b=1, diag_a=3)
            _navigate_to_diagnostics(chain)
            ok = _wait_for_pb_present(chain, pb_mask=0x03, limit=200)
            assert ok, "[gpsim] both PBs never replied"
            for _ in range(8):
                chain.step()
            line0, line1 = chain.lcd_lines()
            # PB1: I2 D' ' S' ' B1 R1 A' ' P' '  → "1:I2D S B1R1A P "
            assert line0 == "1:I2D S B1R1A P ", (
                f"[gpsim] row 0 mismatch for PB1 mixed counters: got {line0!r}"
            )
            # PB2: I' ' D' ' S1 B1 R' ' A3 P' '  → "2:I D S1B1R A3P "
            assert line1 == "2:I D S1B1R A3P ", (
                f"[gpsim] row 1 mismatch for PB2 mixed counters: got {line1!r}"
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


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_no_query_off_diag_page(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
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
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
        c.run_until_connected(limit=200)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
        )
        # Step 50M Tcy (matches gpsim's 50 chunks * 1M Tcy chunk size).
        for _ in range(50):
            c.step_tcy(1_000_000)
        present = c.read_reg(V171_DIAG_PRESENT_PHYS)
        pb1 = [c.read_reg(V171_DIAG_PB1_BASE_PHYS + i) for i in range(7)]
        pb2 = [c.read_reg(V171_DIAG_PB2_BASE_PHYS + i) for i in range(7)]
        assert present == 0, (
            f"[rust] diag_present non-zero without entering Diagnostics: "
            f"0x{present:02X}; PB1 cache={[hex(v) for v in pb1]}; "
            f"PB2 cache={[hex(v) for v in pb2]}"
        )
    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
            )
            for _ in range(50):
                chain.step()
            present = _diag_present(chain)
            assert present == 0, (
                f"[gpsim] diag_present non-zero without entering Diagnostics: "
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


def _navigate_back_to_volume(chain: WireMultiMainChainHarness) -> None:
    """Press LEFT four times to walk PB1 Diag(4) -> Setup(3) -> Input(2)
    -> Preset(1) -> Volume(0).

    Mirror of _navigate_to_diagnostics: 8 settle steps per press so each
    intermediate screen has time to repaint before the next press.

    V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) moved Diagnostics
    from state 2 to states 4-5, so reaching Volume(0) from PB1 Diag(4)
    now takes FOUR LEFT presses instead of the pre-Tier-1 two.
    Operators on real HW press LEFT four times to leave the Diag page;
    this helper reproduces that exit path under sim.
    """
    for _ in range(4):
        chain.press("LEFT")
        for _ in range(8):
            chain.step()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
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
         + many cmd 0x21 query/reply round-trips on PB1 — PB2 path is
         currently quarantined under Task #22 but the cadence still
         issues PB2 queries which fail silently).
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
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
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
        # Walk LEFT back to Volume (4 LEFTs through Tier-1 menu order).
        for _ in range(4):
            c.press("LEFT")
            for _ in range(8):
                c.step()
        line0, line1 = c.lcd_lines()
        assert line0.startswith("Volume:"), (
            f"[rust] LEFT*4 did not return to Volume; LCD={(line0, line1)!r}"
        )

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: lcd={chain.lcd_lines()!r}"
            )
            _navigate_to_diagnostics(chain)
            # Sustained cadence — at default chunk_cycles=1_000_000 each
            # chain step is ~83 ms wallclock, so 200 steps ≈ 16.6 s sim
            # time.  V171_DIAG_POLL_RELOAD = 0x80 ticks ≈ 1 s, so this
            # window covers ~16 cadence cycles = ~16 PB1 queries + ~16
            # PB2 queries.  More than enough to hit the cascade if it's
            # going to happen.
            for _ in range(200):
                chain.step()
                assert not chain.is_waiting(), (
                    "[gpsim] CONTROL fell into WAITING during sustained "
                    "Diag-page cadence — chain heartbeat lost.  This is "
                    "the cascade-induced reconnect storm the real-HW hang "
                    "surfaced."
                )
            # Page should still be responsive.  Walk LEFT back to Volume.
            _navigate_back_to_volume(chain)
            # Verify we landed back on Volume.
            line0, line1 = chain.lcd_lines()
            assert line0.startswith("Volume:"), (
                f"[gpsim] LEFT/LEFT did not exit Diag page; "
                f"LCD={(line0, line1)!r}.  CONTROL is wedged on the Diag "
                f"page — button-poll path isn't picking up the LEFT "
                f"press, or v171_diag_loop is deadlocked inside "
                f"display_loop_iteration."
            )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_does_not_cascade_main_counters(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
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

    Both MAINs are checked: PB1's replies surface in CONTROL today
    while PB2's are quarantined behind Group A xfail (Task #22), but
    the MAIN1 hardware still SERVES the cmd 0x21 queries either way.
    Counter cascade on the MAIN1 (PB2) hardware is a real firmware
    bug regardless of whether the reply makes it back to CONTROL.

    Migrated to dual_supported in P4.7: cascade-detection is a
    firmware-correctness invariant on the MAIN side; rust path uses
    `read_main_reg(unit, addr)` to read the diag block on each MAIN.
    """
    # Counter-cascade thresholds (shared across backends).  Index map:
    # 0=I, 1=D, 2=S, 3=B, 4=R, 5=A, 6=P.  Cascade-sensitive counters
    # are S/B/R (state machines) plus I/D (I2C/DSP fault counters).
    cascade_idx = (("S", 2), ("B", 3), ("R", 4), ("I", 0), ("D", 1))
    threshold = 4

    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
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

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            assert chain.is_connected() and not chain.is_waiting(), (
                f"[gpsim] chain stuck in WAITING/Zzz: "
                f"lcd={chain.lcd_lines()!r}"
            )

            baseline_pb1 = _main_diag_block(chain, 0)
            baseline_pb2 = _main_diag_block(chain, 1)

            _navigate_to_diagnostics(chain)
            for _ in range(200):
                chain.step()

            post_pb1 = _main_diag_block(chain, 0)
            post_pb2 = _main_diag_block(chain, 1)

            for label, idx in cascade_idx:
                for baseline, post, tag in (
                    (baseline_pb1, post_pb1, "PB1"),
                    (baseline_pb2, post_pb2, "PB2"),
                ):
                    delta = post[idx] - baseline[idx]
                    # Saturation arithmetic: if post hit 0x0F (saturated)
                    # and baseline was below, delta is at least the
                    # difference; if both saturated, delta is 0 but the
                    # post value is still high.
                    assert delta < threshold and post[idx] < threshold, (
                        f"[gpsim] cascade detected: {tag}.diag_{label} "
                        f"went from {baseline[idx]} to {post[idx]} "
                        f"(delta={delta}) during sustained Diag-page "
                        f"cadence.  Serving cmd 0x21 queries should be "
                        f"observational — if the handler triggers "
                        f"standby/wake/recovery events, the chain enters "
                        f"a cascade and CONTROL hangs.  Full snapshot: "
                        f"baseline={baseline}, post={post}."
                    )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.wire
@pytest.mark.slow
def test_v171_v32_layer5_chain_diag_page_left_button_exits_promptly(
    v171_hex: Path, v32_hex: Path, dlcp_sim_backend: str,
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
    if dlcp_sim_backend in {"rust", "dual"}:
        _require_rust()
        c = RustChain.from_v171_v32()
        c.run_until_connected(limit=200)
        assert c.is_connected() and not c.is_waiting(), (
            f"[rust] chain stuck in WAITING/Zzz: lcd={c.lcd_lines()!r}"
        )
        _rust_navigate_to_diagnostics(c)
        for _ in range(40):
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

    if dlcp_sim_backend in {"gpsim", "dual"}:
        _require_gpsim()
        _require_v32_hex(v32_hex)
        chain = _new_chain(v171_hex, v32_hex)
        try:
            last = chain.run_until_connected(limit=200)
            assert last is not None, "[gpsim] chain never reached DISPLAY"
            _navigate_to_diagnostics(chain)
            # Warm-up window — let cadence fire a couple of times.
            for _ in range(40):
                chain.step()
            # Confirm we ARE on the Diag page (sanity check before testing exit).
            # Phase 3.4: PB1 Diag state renders row 0 as "PB1" + 13 spaces (idle)
            # OR "PB1: X# ..." (one-or-more non-zero counters).  Either way the
            # row starts with "PB1".
            line0_diag, _ = chain.lcd_lines()
            assert line0_diag.startswith("PB1"), (
                f"[gpsim] chain did not reach PB1 Diag page after navigation; "
                f"LCD={line0_diag!r}"
            )
            # Single LEFT press, bounded settle window.
            # Match "PB1" AND "PB2" to treat a LEFT→RIGHT misdecode (which
            # would land on PB2 Diag instead of exiting the page) as NOT
            # exit-seen — otherwise the test would false-pass.
            chain.press("LEFT")
            exit_seen = False
            for step in range(12):
                chain.step()
                line0, _ = chain.lcd_lines()
                if not line0.startswith(("PB1", "PB2")):
                    exit_seen = True
                    break
            assert exit_seen, (
                "[gpsim] LEFT press did not exit Diag page within 12 chain "
                "steps; v171_diag_check_buttons isn't acting on the press "
                f"promptly.  Final LCD: {chain.lcd_lines()!r}"
            )
        finally:
            chain.close()


@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_v32_cmd21_handler_emits_clean_seven_frame_burst(
    v32_hex: Path,
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
