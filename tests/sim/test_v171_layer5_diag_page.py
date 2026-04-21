"""V1.71 Layer 5 Phase B: CONTROL diagnostics page.

Adds the "Diagnostics" top-level menu page (state 2 in the new
Vol/Preset/Diagnostics/Input/Setup ring) per
``docs/V163B_DIAGNOSTICS_MENU_SPEC.md``:

* RAM cache for per-PB diag counters (BANK 1, 14 bytes at 0x80..0x8D
  — 7 cells per PB, one counter per cell with the value in the low
  nibble; the original 4-byte packed-nibble layout was retired
  2026-04-19, see Phase A docstring for the rationale)
* Flag byte at 0x094 with DIRTY (cache changed since last redraw) and
  PENDING (query in flight, awaiting BF/27) bits
* ``v171_diag_screen`` page body that renders the spec layout
* ``v171_diag_send_query`` 3-byte enqueue (route / 0x21 / 0x00) with
  STATUS.C-checked frame atomicity on TX-ring saturation
* ``v171_bf2x_case_check`` parser case for BF/21..27 replies — sets
  DIRTY on every cache write; on BF/27 (last frame) also clears
  PENDING, sets present-mask bit, and toggles target
* ``v171_diag_emit_nib_w`` nibble-to-LCD-char encoder
* Menu dispatch: state 2 → diag, state 3 → Input, state 4 → Setup
* Nav wrap upper bound bumped from 0x03 to 0x04

Three tiers, mirroring the Layer 1 / Layer 2 / Phase A test layout:

* **Tier A — source-level structural**: pin RAM EQUs, label locations,
  menu dispatch wiring, nav-wrap literals, parser-case insertion,
  flag-byte semantics, silent-PB cadence skip.

* **Tier B — build verification**: V1.71 source assembles cleanly and
  every new symbol resolves at the expected addresses.

* **Tier C — behavioral via gpsim**: at boot the diagnostics cache is
  zero and the present mask is zero (no PB has replied yet); when the
  display state index is forced to 2, ``v171_diag_screen`` runs and
  enqueues the cmd 0x21 query bytes alternating PB1/PB2.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.gpsim import gpsim_available
from dlcp_fw.sim.v17_symbols import assemble_v17, parse_v17_symbols


# ---------------------------------------------------------------------------
# Constants pinned by the Phase B design (see ram.inc + asm)
# ---------------------------------------------------------------------------

# 11-byte cache layout per PB (V1.71 Tier-1, V32_DIAG_TIER1_SPEC.md).
# Layer 5 baseline = 7 runtime counters (I D S B R A P, BF/21..BF/27).
# Tier-1 (rev 0x37) extension = 4 reset-cause flags (O V W X, BF/28..BF/2B).
# PB2 base shifted from +7 to +11; trailing state cells shifted +8.
V171_DIAG_PB1_I_EQU = 0x080
V171_DIAG_PB1_D_EQU = 0x081
V171_DIAG_PB1_S_EQU = 0x082
V171_DIAG_PB1_B_EQU = 0x083
V171_DIAG_PB1_R_EQU = 0x084
V171_DIAG_PB1_A_EQU = 0x085
V171_DIAG_PB1_P_EQU = 0x086
V171_DIAG_PB1_RESET_POR_EQU = 0x087   # Tier-1
V171_DIAG_PB1_RESET_BOR_EQU = 0x088   # Tier-1
V171_DIAG_PB1_RESET_WDT_EQU = 0x089   # Tier-1
V171_DIAG_PB1_RESET_SW_EQU  = 0x08A   # Tier-1
V171_DIAG_PB2_I_EQU = 0x08B
V171_DIAG_PB2_D_EQU = 0x08C
V171_DIAG_PB2_S_EQU = 0x08D
V171_DIAG_PB2_B_EQU = 0x08E
V171_DIAG_PB2_R_EQU = 0x08F
V171_DIAG_PB2_A_EQU = 0x090
V171_DIAG_PB2_P_EQU = 0x091
V171_DIAG_PB2_RESET_POR_EQU = 0x092   # Tier-1
V171_DIAG_PB2_RESET_BOR_EQU = 0x093   # Tier-1
V171_DIAG_PB2_RESET_WDT_EQU = 0x094   # Tier-1
V171_DIAG_PB2_RESET_SW_EQU  = 0x095   # Tier-1
V171_DIAG_TARGET_EQU = 0x096
V171_DIAG_PRESENT_EQU = 0x097
V171_DIAG_POLL_LO_EQU = 0x098
V171_DIAG_POLL_HI_EQU = 0x099

# Physical addresses for gpsim CLI reads (BSR=1 << 8 | offset).
V171_DIAG_PB1_I_PHYS = 0x180
V171_DIAG_PB2_I_PHYS = 0x18B
V171_DIAG_TARGET_PHYS = 0x196
V171_DIAG_PRESENT_PHYS = 0x197

ALL_DIAG_CACHE_EQUS = (
    ("v171_diag_pb1_i", V171_DIAG_PB1_I_EQU),
    ("v171_diag_pb1_d", V171_DIAG_PB1_D_EQU),
    ("v171_diag_pb1_s", V171_DIAG_PB1_S_EQU),
    ("v171_diag_pb1_b", V171_DIAG_PB1_B_EQU),
    ("v171_diag_pb1_r", V171_DIAG_PB1_R_EQU),
    ("v171_diag_pb1_a", V171_DIAG_PB1_A_EQU),
    ("v171_diag_pb1_p", V171_DIAG_PB1_P_EQU),
    ("v171_diag_pb1_reset_por", V171_DIAG_PB1_RESET_POR_EQU),
    ("v171_diag_pb1_reset_bor", V171_DIAG_PB1_RESET_BOR_EQU),
    ("v171_diag_pb1_reset_wdt", V171_DIAG_PB1_RESET_WDT_EQU),
    ("v171_diag_pb1_reset_sw",  V171_DIAG_PB1_RESET_SW_EQU),
    ("v171_diag_pb2_i", V171_DIAG_PB2_I_EQU),
    ("v171_diag_pb2_d", V171_DIAG_PB2_D_EQU),
    ("v171_diag_pb2_s", V171_DIAG_PB2_S_EQU),
    ("v171_diag_pb2_b", V171_DIAG_PB2_B_EQU),
    ("v171_diag_pb2_r", V171_DIAG_PB2_R_EQU),
    ("v171_diag_pb2_a", V171_DIAG_PB2_A_EQU),
    ("v171_diag_pb2_p", V171_DIAG_PB2_P_EQU),
    ("v171_diag_pb2_reset_por", V171_DIAG_PB2_RESET_POR_EQU),
    ("v171_diag_pb2_reset_bor", V171_DIAG_PB2_RESET_BOR_EQU),
    ("v171_diag_pb2_reset_wdt", V171_DIAG_PB2_RESET_WDT_EQU),
    ("v171_diag_pb2_reset_sw",  V171_DIAG_PB2_RESET_SW_EQU),
    ("v171_diag_target", V171_DIAG_TARGET_EQU),
    ("v171_diag_present", V171_DIAG_PRESENT_EQU),
    ("v171_diag_poll_lo", V171_DIAG_POLL_LO_EQU),
    ("v171_diag_poll_hi", V171_DIAG_POLL_HI_EQU),
)

# Constants exported from ram.inc:
V171_DIAG_POLL_RELOAD_LO_EXPECTED = 0x80
V171_DIAG_POLL_RELOAD_HI_EXPECTED = 0x00


# ---------------------------------------------------------------------------
# Shared fixture: build the Layer 5 V1.71 hex once per module
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_hex(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, dict[str, int]]:
    tmp = tmp_path_factory.mktemp("v171_layer5")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    lst_out = tmp / "dlcp_control_v171.lst"
    assemble_v17(asm, hex_out, output_lst=lst_out)
    syms = parse_v17_symbols(lst_out)
    return hex_out, syms


def _equ_address(text: str, name: str) -> int | None:
    """Return the integer value an EQU resolves to.

    Handles both numeric literals (`equ 0x1F`) and symbolic-alias EQUs
    (`equ V171_DIAG_FLAG_RUNTIME_PENDING`) by recursing on the alias
    target.  Returns None if the name has no EQU or if the alias chain
    can't be resolved to a literal.
    """
    m = re.search(
        rf"^\s*{re.escape(name)}\s+(?:EQU|equ)\s+(\S+)",
        text,
        re.MULTILINE,
    )
    if not m:
        return None
    value = m.group(1)
    if value.startswith(("0x", "0X")):
        return int(value, 16)
    if value.isdigit():
        return int(value, 10)
    # Symbolic alias -- recurse.
    return _equ_address(text, value)


def _label_offset(text: str, label: str) -> int:
    """Return character offset of ``label:`` definition in the source.

    Differs from ``text.find(label + ':')`` in that we anchor to the
    start-of-line so that doc comments mentioning the label don't
    confuse the test.
    """
    m = re.search(rf"^{re.escape(label)}:", text, re.MULTILINE)
    return m.start() if m else -1


def _label_body(text: str, start_label: str, end_label: str) -> str:
    """Return source text from ``start_label:`` up to (exclusive) the
    next occurrence of ``end_label:``.  Use this instead of a fixed
    char-window when in-line documentation can grow and shrink the
    routine's footprint between revisions.
    """
    start = _label_offset(text, start_label)
    if start < 0:
        return ""
    end = _label_offset(text[start:], end_label)
    if end < 0:
        return text[start:]
    return text[start:start + end]


# ===========================================================================
# Tier A — source-level structural assertions
# ===========================================================================


def test_ram_inc_diag_block_pins_at_expected_addresses() -> None:
    """Each diagnostics RAM cell must EQU to its specified BANK 1 offset.

    The block lives at 0x80..0x8B in BANK 1 — physical 0x180..0x18B.
    EQU values are 8-bit BANKED-form operands (firmware sets BSR=1
    before access).  gpsim CLI reads via the PHYSICAL address.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    for name, expected_addr in ALL_DIAG_CACHE_EQUS:
        addr = _equ_address(text, name)
        assert addr == expected_addr, (
            f"{name} EQU expected at 0x{expected_addr:03X} (BANK 1 offset; "
            f"physical 0x{0x100 | expected_addr:03X}); "
            f"ram.inc has {('0x%03X' % addr) if addr is not None else None}"
        )


def test_ram_inc_poll_reload_constants_are_documented() -> None:
    """Poll cadence reload literals must be present and pin to the spec range.

    Spec calls for 500 ms .. 1 s.  At 0x0080 ticks the LCD refreshes
    near the upper end.  Pinning the value here means future changes
    have to update both the EQU and this test.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    lo = _equ_address(text, "V171_DIAG_POLL_RELOAD_LO")
    hi = _equ_address(text, "V171_DIAG_POLL_RELOAD_HI")
    assert lo == V171_DIAG_POLL_RELOAD_LO_EXPECTED, lo
    assert hi == V171_DIAG_POLL_RELOAD_HI_EXPECTED, hi


def test_ram_inc_does_not_collide_with_existing_v171_cells() -> None:
    """The diagnostics block must not overlap the existing V1.71 BANK 1
    cells (full_sync_step at 0x70, tx_saturate_count at 0xAD)."""
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    fs_step = _equ_address(text, "v171_full_sync_step")
    tx_sat = _equ_address(text, "v171_tx_saturate_count")
    assert fs_step == 0x070, fs_step
    assert tx_sat == 0x0AD, tx_sat
    diag_range = set(range(0x80, 0x8C))
    assert fs_step not in diag_range
    assert tx_sat not in diag_range


def test_menu_dispatch_tier1_layout() -> None:
    """The ``flow_post_connect_init_11F0`` dispatch must implement the
    Tier-1 menu layout (V32_DIAG_TIER1_SPEC.md §"V1.71 CONTROL menu
    rework"):

      Vol(0) <-> Preset(1) <-> Input(2) <-> Setup(3) <-> PB1 Diag(4) <-> PB2 Diag(5)

    Diagnostics moves from state 2 (between Preset and Input) to states
    4-5 (after Setup) so it's the deepest menu — operators reach it
    intentionally during troubleshooting.  Input shifts back to state 2;
    Setup shifts to state 3.  Both PB diag entries call into a single
    v171_diag_pb_screen routine with PB-index 0 / 1 in W.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body_start = _label_offset(text, "flow_post_connect_init_11F0")
    assert body_start >= 0, "dispatch entry label missing"
    # Capture a generous body window through to the boot_handshake_wait
    # block (which holds the state == 5 / PB2-Diag branch).
    body_end = text.find("flow_boot_handshake_wait_120A:", body_start)
    body = text[body_start:body_end]
    assert re.search(r"rcall\s+v171_preset_screen", body), "state 1 -> preset wiring"
    # State 2 is now Input (was Diagnostics in pre-Tier-1 Layer 5).
    assert re.search(
        r"movlw\s+0x02[^\n]*\n\s*cpfseq\s+0xbf[\s\S]{0,200}call\s+control_core_service_1912",
        body,
    ), "state 2 -> Input wiring (Tier-1 reordering)"
    # State 3 is now Setup.
    assert re.search(
        r"movlw\s+0x03[^\n]*\n\s*cpfseq\s+0xbf[\s\S]{0,200}call\s+control_core_service_13FE",
        body,
    ), "state 3 -> Setup wiring (Tier-1 reordering)"
    # State 4 is PB1 Diag with W = 0 in PB-index parameter.
    assert re.search(
        r"movlw\s+0x04[^\n]*\n\s*cpfseq\s+0xbf[\s\S]{0,200}movlw\s+0x00\s*\n\s*rcall\s+v171_diag_pb_screen",
        body,
    ), "state 4 -> PB1 Diag wiring (W = PB-index 0)"


def test_nav_wrap_literals_tier1_bumped_to_0x05() -> None:
    """V1.71 Tier-1 expands the menu ring from 5 states to 6 states by
    splitting Diagnostics into PB1 Diag + PB2 Diag at the END of the
    cycle.  Three literals downstream must all be 0x05 after this:

      - DOWN nav upper bound:        movlw 0x05 / cpfseq 0xbf
      - UP   nav wrap target:        movlw 0x05 / movwf  0xbf
      - PB2-Diag-state dispatch:     movlw 0x05 / cpfseq 0xbf

    Three matches total = correct for Tier-1; two would indicate a
    nav-only edit that forgot to bump the PB2-Diag-state cpfseq.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    matches = re.findall(
        r"movlw\s+0x05[^\n]*\n\s*(?:movwf|cpfseq)\s+0xbf",
        text,
    )
    assert len(matches) == 3, (
        f"expected exactly three 0x05 nav/dispatch literals (UP wrap, "
        f"DOWN bound, PB2-Diag-state cpfseq); found {len(matches)}: {matches}"
    )


def test_diag_pb_screen_stashes_index_and_falls_through_to_screen() -> None:
    """Tier-1 (Phase 3.4) introduces v171_diag_pb_screen as the menu
    dispatch target for both state 4 (PB1 Diag, W=0) and state 5
    (PB2 Diag, W=1).

    Phase 3.4 implementation: stash the PB index into the BANK 1 cell
    v171_diag_render_pb_index (so the cadence loop's redraw path can
    pick the right cache base / present-mask bit / title char on every
    redraw without re-passing W) then fall through to v171_diag_screen
    for the page-entry hooks (clear reset_seen + first-entry target
    init) and the initial render + cadence loop.

    An earlier draft tried to stash the PB-index into a BANK 0 access
    cell here at the entry, but the cell picked aliased ir_decoded_cmd
    (live RC5 decode sink at 0x01D), which would have overwritten an
    in-flight RC5 command byte during diag-page entry.  Phase 3.4 picks
    v171_diag_render_pb_index in BANK 1 (operand 0x0CD, physical
    0x1CD) -- documented in dlcp_control_ram.inc.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_pb_screen")
    assert off >= 0, (
        "v171_diag_pb_screen label missing -- menu dispatch will fail "
        "at link time because state 4 / state 5 reference it."
    )
    body = text[off:off + 800]
    # Body must NOT touch ir_decoded_cmd / Common_RAM+29 (the failed-
    # stash cell from an earlier draft).  Pin its absence so a future
    # re-introduction has to also touch this assertion.
    assert not re.search(r"movwf\s+\(Common_RAM\s*\+\s*29\)", body), (
        "v171_diag_pb_screen must NOT stash anything into Common_RAM+29 "
        "(= 0x01D = ir_decoded_cmd, a live RC5 decode sink).  Phase 3.4 "
        "uses v171_diag_render_pb_index in BANK 1 instead."
    )
    # Phase 3.4: must stash W into v171_diag_render_pb_index (BANK 1).
    assert re.search(
        r"movwf\s+v171_diag_render_pb_index", body,
    ), (
        "Phase 3.4: v171_diag_pb_screen must stash the PB index (W) into "
        "v171_diag_render_pb_index so the redraw path knows which PB to "
        "render on every cadence iteration."
    )
    # Body must NOT have a bra/goto to skip past v171_diag_screen --
    # Phase 3.4 falls through to share the page-entry hooks (reset_seen
    # clear + first-entry target init).  An earlier placeholder used
    # `bra v171_diag_screen` but that's redundant once we fall through.
    assert not re.search(r"bra\s+v171_diag_screen\b", body), (
        "Phase 3.4 falls through to v171_diag_screen instead of bra-ing "
        "to it -- the bra was a placeholder before the renderer landed."
    )


def test_diag_screen_label_exists_and_initializes_target() -> None:
    """``v171_diag_screen:`` must be a top-level label, and its first
    body block must initialize ``v171_diag_target`` from the present mask
    (target=0 on first entry so the very first cadence-driven query goes
    to PB1 per spec; toggle now happens on BF/27 reception (the LAST
    frame of the 7-frame burst), not in the cadence loop, so we don't
    pre-flip it any more).

    Tier-1 (2026-04-20) added a clrf v171_diag_reset_seen at the same
    init point so the page-entry hook fires cmd 0x22 ONCE per PB on
    each Diag-page visit.  Window extended to cover the new init line.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_screen")
    assert off >= 0, "v171_diag_screen label missing"
    # Window: from label through first ~1500 chars covers the (now larger
    # with Tier-1) init block including the reset_seen clear.
    head = text[off:off + 1500]
    assert "v171_diag_present" in head, "first block must touch present mask"
    assert "bcf     v171_diag_target, 0, BANKED" in head, (
        "first-entry init must clear diag_target.0 so the first cadence "
        "query goes to PB1"
    )
    assert "clrf    v171_diag_reset_seen" in head, (
        "Tier-1 page-entry hook must clear v171_diag_reset_seen so the "
        "cadence loop fires cmd 0x22 ONCE per PB per Diag-page visit"
    )


def test_diag_screen_body_renders_per_pb_sparse_layout() -> None:
    """Phase 3.4 (V32_DIAG_TIER1_SPEC.md §"LCD layouts (Option D)"):
    the renderer is per-PB sparse, not the legacy dual-PB compact
    layout.

    Pin shapes that must be present in the source:

    1. Each cell letter (I D S B R A P O V W X) appears exactly ONCE
       in the renderer span -- in the v171_diag_letter_for_idx cascade
       that maps cell-index 0..10 to the corresponding letter.  The
       legacy dual-PB layout duplicated each letter (PB1 row + PB2
       row); the per-PB layout consults the cascade once per non-zero
       cell.

    2. Special tokens for the three layout cases:
       - "PB" prefix (common to all three layouts)
       - ':'  (degraded-only -- column 3 separator)
       - "OK" (healthy)
       - "n/a" via 'n','/','a' literals (absent)
       - ".." via two '.' literals (overflow when count >= 10)
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")

    # 1. v171_diag_letter_for_idx must emit every Tier-1 cell letter
    #    exactly once (one cascade entry per cell index 0..10).
    cascade_body = _label_body(
        text, "v171_diag_letter_for_idx", "v171_diag_pad_spaces",
    )
    assert cascade_body, (
        "v171_diag_letter_for_idx body could not be located"
    )
    expected_letters = ("I", "D", "S", "B", "R", "A", "P", "O", "V", "W", "X")
    for letter in expected_letters:
        count = len(re.findall(rf"movlw\s+'{letter}'", cascade_body))
        assert count == 1, (
            f"Phase 3.4 cascade entry for letter '{letter}' must appear "
            f"exactly once; got {count} occurrences"
        )
    # And the cascade must NOT have any other letters that would imply a
    # different display order than the spec.
    cascade_movlws = set(re.findall(r"movlw\s+'(\w)'", cascade_body))
    extras = cascade_movlws - set(expected_letters)
    assert not extras, (
        f"unexpected letter(s) in v171_diag_letter_for_idx cascade: "
        f"{sorted(extras)} (expected only {expected_letters})"
    )

    # 2. The renderer body (between v171_diag_screen and the cascade)
    #    must include the special-case layout literals.
    render_body = _label_body(
        text, "v171_diag_screen", "v171_diag_letter_for_idx",
    )
    assert render_body, (
        "renderer span (v171_diag_screen .. v171_diag_letter_for_idx) "
        "not located in source"
    )
    assert re.search(r"movlw\s+'P'", render_body), (
        "PB-prefix 'P' literal missing"
    )
    assert re.search(r"movlw\s+'B'", render_body), (
        "PB-prefix 'B' literal missing"
    )
    assert re.search(r"movlw\s+':'", render_body), (
        "degraded ':' separator missing"
    )
    assert re.search(r"movlw\s+'O'", render_body), (
        "healthy 'O' (of 'OK') missing"
    )
    assert re.search(r"movlw\s+'K'", render_body), (
        "healthy 'K' (of 'OK') missing"
    )
    assert re.search(r"movlw\s+'n'", render_body), (
        "absent 'n' (of 'n/a') missing"
    )
    assert re.search(r"movlw\s+'/'", render_body), (
        "absent '/' (of 'n/a') missing"
    )
    assert re.search(r"movlw\s+'a'", render_body), (
        "absent 'a' (of 'n/a') missing"
    )
    # Two '.' literals for the ".." overflow indicator (count >= 10).
    dot_count = len(re.findall(r"movlw\s+'\.'", render_body))
    assert dot_count >= 2, (
        f"overflow '..' indicator must emit two '.' literals; got "
        f"{dot_count}"
    )


def test_diag_render_absent_path_renders_na_for_silent_pb() -> None:
    """Phase 3.4: when the present-mask bit for the rendered PB is
    clear, the renderer routes to v171_diag_render_absent which writes
    "PBn" + 13 spaces on row 0 and "n/a" + 13 spaces on row 1.

    Single per-PB sentinel path (one v171_diag_render_absent label
    handles BOTH PB1 and PB2 because the PB-index dispatch happens
    earlier via v171_diag_render_pb_index).  This collapses the
    legacy dual-PB layout's two separate render_na blocks into one.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # Single sentinel path -- not per-PB.
    absent_labels = re.findall(
        r"^v171_diag_render_absent\w*:", text, re.MULTILINE,
    )
    assert absent_labels == ["v171_diag_render_absent:"], (
        f"Phase 3.4 must have exactly one absent-render path; got "
        f"{absent_labels}.  Legacy dual-PB layout had two "
        f"(v171_diag_pb1_render_na + v171_diag_pb2_render_na); the "
        f"per-PB layout collapses them via v171_diag_render_pb_index."
    )
    # The absent path emits 'n', '/', 'a' literals.
    body = _label_body(
        text, "v171_diag_render_absent", "v171_diag_render_healthy",
    )
    assert body, "v171_diag_render_absent body could not be located"
    for ch in ("'n'", "'/'", "'a'"):
        assert ch in body, f"absent path missing {ch} literal"


def test_diag_send_query_uses_b1_or_b2_route_and_cmd_byte_param() -> None:
    """V1.71 Tier-1 (2026-04-20) refactored ``v171_diag_send_query`` from
    a hard-coded cmd 0x21 emitter into a parameterized helper that takes
    the cmd byte in W.  Two thin wrappers expose the original two query
    types:

      v171_diag_send_runtime_query  -> movlw 0x21; bra ..._w  (cmd 0x21)
      v171_diag_send_reset_query    -> movlw 0x22; bra ..._w  (cmd 0x22)

    The shared helper v171_diag_send_query_w enqueues 3 bytes: route
    (0xB1 or 0xB2 depending on v171_diag_target bit 0), the cmd byte from
    W, and a data byte 0x00.  Backward-compat alias v171_diag_send_query
    forwards to v171_diag_send_runtime_query so older call sites still
    work.

    Pin both wrappers + the shared helper structure (3 tx_byte_enqueue
    calls) so a refactor that drops one of the wrappers fails loudly.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # Both wrappers + alias must be present.
    for label in (
        "v171_diag_send_runtime_query",
        "v171_diag_send_reset_query",
        "v171_diag_send_query",         # alias
        "v171_diag_send_query_w",       # shared helper
    ):
        assert _label_offset(text, label) >= 0, f"label {label}: missing"
    # Wrappers seed W with their respective cmd byte.
    runtime = _label_body(
        text, "v171_diag_send_runtime_query", "v171_diag_send_reset_query"
    )
    assert re.search(r"movlw\s+0x21\b", runtime), (
        "runtime wrapper must seed W = 0x21"
    )
    reset = _label_body(
        text, "v171_diag_send_reset_query", "v171_diag_send_query:"
    )
    assert re.search(r"movlw\s+0x22\b", reset), (
        "reset wrapper must seed W = 0x22"
    )
    # Shared helper structure.
    body = _label_body(text, "v171_diag_send_query_w", "control_core_service_0F54")
    assert re.search(r"movlw\s+0xB1", body), "PB1 route literal missing"
    assert re.search(r"movlw\s+0xB2", body), "PB2 route literal missing"
    # Three tx_byte_enqueue invocations (route, cmd, data).
    enqueue_calls = re.findall(r"call\s+tx_byte_enqueue", body)
    assert len(enqueue_calls) == 3, (
        f"expected 3 tx_byte_enqueue calls (route/cmd/data); found "
        f"{len(enqueue_calls)}: {enqueue_calls}"
    )


def test_bf2x_parser_case_handles_cmds_21_through_2b() -> None:
    """Parser must recognize cmd 0x21..0x2B from BF replies and write
    the payload into the diag cache slot indexed by the in-flight target.

    V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) extends the
    accepted range from 0x21..0x27 (Layer 5 baseline, cmd 0x21 only)
    to 0x21..0x2B (Layer 5 + Tier-1, cmd 0x21 + cmd 0x22).

    Cmd codes outside 0x21..0x2B (0x20, 0x2C+) must NOT trigger a write.
    Each data byte stays < 0x80 because every cell carries either a
    saturating-byte counter (0..0x0F) or a binary flag (0 or 1).
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_bf2x_case_check")
    assert off >= 0, "v171_bf2x_case_check label missing"
    # Window must extend through the v171_bf2x_check_reset_last block
    # added for Tier-1 (RESET LAST frame on BF/2B) AND the codex MEDIUM
    # fix (effective-target picker for cmd 0x22 frames).  8 KB covers
    # the full handler body including all comments.
    body = text[off:off + 8000]
    # Range gate: must reject < 0x21 and >= 0x2C.
    assert re.search(r"movlw\s+0x21\s*\n\s*cpfslt\s+rx_parsed_cmd", body), (
        "lower-bound check (cmd < 0x21 -> exit) missing"
    )
    assert re.search(r"movlw\s+0x2C\s*\n\s*cpfslt\s+rx_parsed_cmd", body), (
        "upper-bound check (cmd < 0x2C -> ok) missing -- Tier-1 expanded "
        "the range from 0x28 to 0x2C to cover the new BF/28..BF/2B "
        "reset-cause reply burst (cmd 0x22)."
    )
    # Slot offset = cmd - 0x21 and base depends on diag_target bit 0.
    assert re.search(r"subwf\s+rx_parsed_cmd,\s*W", body), (
        "col_offset = cmd - 0x21 missing"
    )
    assert re.search(r"v171_diag_pb1_i\b", body), "PB1 base symbol missing"
    assert re.search(r"v171_diag_pb2_i\b", body), "PB2 base symbol missing"
    # Present-mask update: PB1 sets bit0, PB2 sets bit1.
    assert re.search(r"iorwf\s+v171_diag_present", body), (
        "present-mask OR-in missing"
    )
    # Target-toggle on BF/27 (runtime last frame, col_offset == 6).
    assert re.search(r"btg\s+v171_diag_target", body), (
        "target toggle on BF/27 missing"
    )
    assert re.search(r"movlw\s+0x06\s*\n\s*cpfseq\s+\(Common_RAM \+ 4\)", body), (
        "deferred-update gate (col_offset == 6 = BF/27 runtime last) missing"
    )
    # Tier-1: BF/2B (col_offset == 0x0A) is the RESET LAST FRAME.  When
    # it arrives, parser sets v171_diag_reset_seen bit for the in-flight
    # PB and clears RESET_PENDING -- mirrors the BF/27 RUNTIME LAST path.
    assert re.search(r"movlw\s+0x0A\s*\n\s*cpfseq\s+\(Common_RAM \+ 4\)", body), (
        "Tier-1 RESET LAST frame gate (col_offset == 0x0A = BF/2B) missing "
        "-- without this, the page-entry hook would re-fire cmd 0x22 on "
        "every loop iteration because v171_diag_reset_seen never gets set."
    )
    assert re.search(r"iorwf\s+v171_diag_reset_seen", body), (
        "Tier-1 reset_seen OR-in missing -- cmd 0x22 would re-fire forever"
    )


def test_bf08_handler_jumps_to_bf2x_check_on_miss() -> None:
    """The fall-through from the BF/08 case must land on
    ``v171_bf2x_case_check`` so BF/2N replies aren't dropped at the
    BF/08 mismatch boundary."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_bf08_case_check")
    assert off >= 0
    body = text[off:off + 2500]
    assert re.search(r"goto\s+v171_bf2x_case_check", body), (
        "BF/08 mismatch fall-through must redirect to v171_bf2x_case_check"
    )


def test_diag_emit_nib_w_encoding_paths() -> None:
    """The nibble encoder must have all four output paths:
    zero → ' ', 1..9 → digit, A..E → alpha, F → '+'.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_emit_nib_w")
    assert off >= 0
    body = text[off:off + 1500]
    # Zero path: bz target loads a space literal.
    assert re.search(r"v171_diag_emit_nib_zero:[\s\S]*?movlw\s+' '", body), (
        "zero → ' ' path missing"
    )
    # Saturated path: '+'
    assert re.search(r"v171_diag_emit_nib_sat:[\s\S]*?movlw\s+'\+'", body), (
        "saturated → '+' path missing"
    )
    # Digit path: '1'..'9' computed as 0x30 + nib (since nib > 0)
    assert re.search(r"movlw\s+0x30\s*\n\s*addwf\s+\(Common_RAM \+ 4\)", body), (
        "digit path (0x30 + nib) missing"
    )
    # Alpha path: 'A'..'E' computed as 0x37 + nib
    assert re.search(
        r"v171_diag_emit_nib_alpha:[\s\S]*?movlw\s+0x37\s*\n\s*addwf\s+\(Common_RAM \+ 4\)",
        body,
    ), (
        "alpha path (0x37 + nib) missing"
    )


# ===========================================================================
# Tier B — build verification
# ===========================================================================


def test_v171_assembles_with_diag_layer(v171_hex: tuple[Path, dict[str, int]]) -> None:
    """Layer 5 V1.71 source assembles cleanly and the hex output exists."""
    hex_path, _ = v171_hex
    assert hex_path.exists()
    assert hex_path.stat().st_size > 0


def test_v171_layer5_symbols_resolve(v171_hex: tuple[Path, dict[str, int]]) -> None:
    """All Phase 3.4 + Layer 5 baseline code labels must resolve from
    the gpasm listing.  Phase 3.4 (V32_DIAG_TIER1_SPEC.md) replaced
    the legacy dual-PB labels (v171_diag_pb1_render_na / pb2_render_na)
    with single per-PB-dispatched labels (v171_diag_render_absent /
    v171_diag_render_healthy / v171_diag_render_degraded).
    """
    _, syms = v171_hex
    expected_labels = (
        # Layer 5 baseline (still present after Phase 3.4)
        "v171_diag_pb_screen",
        "v171_diag_screen",
        "v171_diag_screen_draw",
        "v171_diag_loop",
        "v171_diag_emit_letter",
        "v171_diag_emit_nib_w",
        "v171_diag_emit_nib_zero",
        "v171_diag_emit_nib_sat",
        "v171_diag_emit_nib_alpha",
        "v171_diag_send_query",
        "v171_bf2x_case_check",
        # Phase 3.4 per-PB sparse renderer additions
        "v171_diag_render_absent",
        "v171_diag_render_healthy",
        "v171_diag_render_degraded",
        "v171_diag_load_fsr1_base",
        "v171_diag_letter_for_idx",
        "v171_diag_pad_spaces",
    )
    missing = [name for name in expected_labels if name not in syms]
    assert not missing, f"unresolved Layer 5 / Phase 3.4 labels: {missing}"


# ===========================================================================
# Tier C — behavioral via gpsim
# ===========================================================================


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_layer5_diag_block_zero_at_boot(
    v171_hex: tuple[Path, dict[str, int]]
) -> None:
    """Healthy boot must leave the diag cache and present mask at 0.

    No PB has replied yet, so cache slots stay zero and the present
    mask reads 0 — the renderer's `n/a` path will fire when the page
    is opened.
    """
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    try:
        from dlcp_fw.sim.control_gpsim import GpsimControlHarness, _read_reg
    except Exception:
        pytest.skip("control_gpsim harness not importable")

    hex_path, _ = v171_hex
    h = GpsimControlHarness(hex_path)
    try:
        h.warmup(2_000_000)
        for name, equ_addr in ALL_DIAG_CACHE_EQUS:
            phys = 0x100 | equ_addr
            value = _read_reg(h._issue, phys)
            assert value == 0, (
                f"healthy boot left {name} (phys 0x{phys:03X}) at 0x{value:02X}; "
                f"expected 0 — cold-init must clear the diag cache"
            )
    finally:
        h.close()


@pytest.mark.gpsim
@pytest.mark.slow
def test_v171_layer5_diag_block_holds_zero_through_boot_and_warmup(
    v171_hex: tuple[Path, dict[str, int]]
) -> None:
    """Across a long warmup with the harness's heartbeat injection
    (which drives CONTROL into DISPLAY mode and exercises the volume /
    input / preset frame-send paths), the diagnostics block must stay
    at zero — the cmd 0x21 query path is page-local and never fires
    outside the Diagnostics screen, so no spurious increments must
    leak into the diag cache from the steady-state command path.

    This is the negative proof that complements the positive primary-
    counter coverage that lives in the Phase C wire-chain integration
    test (where CONTROL+V3.2 MAIN are co-simulated and we can drive
    the page → query → reply round trip end-to-end).
    """
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    try:
        from dlcp_fw.sim.control_gpsim import GpsimControlHarness, _read_reg
    except Exception:
        pytest.skip("control_gpsim harness not importable")

    hex_path, _ = v171_hex
    h = GpsimControlHarness(
        hex_path,
        heartbeat_force_connected=True,
    )
    try:
        h.warmup(25_000_000)
        # Even if DISPLAY mode never reached the active state, the
        # diag cache must stay zero — there's no path that touches it
        # without the Diagnostics page being entered.
        for name, equ_addr in ALL_DIAG_CACHE_EQUS:
            phys = 0x100 | equ_addr
            value = _read_reg(h._issue, phys)
            assert value == 0, (
                f"warmup leaked into {name} (phys 0x{phys:03X}) at 0x{value:02X}; "
                f"diag block must stay zero outside the Diagnostics page"
            )
    finally:
        h.close()


# ===========================================================================
# Coverage gaps surfaced by 2026-04-19 review — structural assertions for
# the dirty-flag and pending-flag fixes that close them.
# ===========================================================================


def test_v171_diag_flags_byte_pinned_and_bit_aliases() -> None:
    """``v171_diag_flags`` byte EQU + bit aliases.  V1.71 Tier-1
    (V32_DIAG_TIER1_SPEC.md, 2026-04-20) shifted the flag byte from
    0x094 to 0x09C and added a third bit alias for RESET_PENDING:

      bit 0  V171_DIAG_FLAG_DIRTY            cache changed since last
                                             redraw (set on every cache
                                             write)
      bit 1  V171_DIAG_FLAG_RUNTIME_PENDING  cmd 0x21 query in flight,
                                             awaiting BF/27 (set on
                                             cadence query-send, cleared
                                             on BF/27 reception)
      bit 2  V171_DIAG_FLAG_RESET_PENDING    cmd 0x22 query in flight,
                                             awaiting BF/2B (set by the
                                             page-entry hook, cleared
                                             on BF/2B reception)

    Backward-compat alias V171_DIAG_FLAG_PENDING points at bit 1
    (RUNTIME_PENDING) so older callers continue to work.

    Pinning here documents the bit assignment so a future change has to
    update both ram.inc and this test together.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    assert _equ_address(text, "v171_diag_flags") == 0x09C
    assert _equ_address(text, "V171_DIAG_FLAG_DIRTY") == 0x00
    assert _equ_address(text, "V171_DIAG_FLAG_RUNTIME_PENDING") == 0x01
    assert _equ_address(text, "V171_DIAG_FLAG_RESET_PENDING") == 0x02
    # Backward-compat alias must still resolve to bit 1.
    assert _equ_address(text, "V171_DIAG_FLAG_PENDING") == 0x01


def test_diag_parser_sets_dirty_on_every_bf2x_write() -> None:
    """Coverage for HIGH #1: redraw on counter change with stable present.

    Without the dirty flag the screen freezes once both PBs have been
    seen present at least once — the only redraw trigger was
    ``v171_diag_present XOR snap``.  The fix sets DIRTY in
    ``v171_bf2x_case_check`` after every cache write so the next
    ``v171_diag_check_redraw`` triggers regardless of present-mask
    movement.  This test guards that the bsf is BEFORE the
    ``cpfseq col_offset == 6`` BF/27 gate (so it fires for ALL frames,
    not just the last one).
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_bf2x_case_check")
    assert off >= 0
    body = text[off:off + 8000]
    # Locate the cache write (movff rx_parsed_data, INDF0) and the
    # BF/27 last-frame gate (cpfseq with W=0x06).  bsf DIRTY must sit
    # between them.  NOTE: there are TWO cpfseq instructions on
    # (Common_RAM + 4) in the parser body now -- the codex MEDIUM fix
    # added a cpfslt gate for the col-7 effective-target picker, but
    # we explicitly find the BF/27 gate by anchoring on the movlw 0x06
    # immediately preceding it.
    write_pos = body.find("movff   rx_parsed_data, INDF0")
    gate_pos = body.find("movlw   0x06\n        cpfseq  (Common_RAM + 4), A")
    assert write_pos >= 0 and gate_pos > write_pos
    between = body[write_pos:gate_pos]
    assert re.search(
        r"bsf\s+v171_diag_flags,\s*V171_DIAG_FLAG_DIRTY,\s*BANKED",
        between,
    ), (
        "DIRTY flag must be set after the cache write but BEFORE the "
        "BF/27-only gate — otherwise BF/21..26 writes don't redraw"
    )


def test_diag_check_redraw_honors_dirty_flag() -> None:
    """Coverage for HIGH #1: ``v171_diag_check_redraw`` must redraw on
    DIRTY=1 even when present-mask snapshot matches.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_check_redraw")
    assert off >= 0
    body = text[off:off + 1200]
    # btfsc on DIRTY must come BEFORE the present-XOR check, and bra
    # to the redraw path on DIRTY=1.
    btfsc_pos = body.find("btfsc   v171_diag_flags, V171_DIAG_FLAG_DIRTY, BANKED")
    xor_pos = body.find("xorwf   v171_diag_present_snap")
    assert 0 <= btfsc_pos < xor_pos, (
        "DIRTY check must run before the present-XOR (so cache changes "
        "trigger redraw without needing a present-mask change)"
    )
    # The redraw path must clear DIRTY so the next iter is idempotent.
    assert re.search(
        r"bcf\s+v171_diag_flags,\s*V171_DIAG_FLAG_DIRTY,\s*BANKED",
        body,
    ), "redraw path must clear DIRTY after redraw fires"


def test_diag_loop_advances_target_on_silent_pb() -> None:
    """Coverage for HIGH #2: silent-PB skip-on-pending in the cadence loop.

    Without this gate, a silent or unsupported PB would never advance
    the target (which only flips on BF/27 reception), pinning the poll
    loop on the missing slot forever.  The fix: cadence checks
    RUNTIME_PENDING; if still set when the next cadence fires, advance
    target BEFORE sending so the responding PB gets re-queried.

    V1.71 Tier-1 (2026-04-20) renamed PENDING -> RUNTIME_PENDING (bit 1)
    and added RESET_PENDING (bit 2) for the new cmd 0x22 page-entry
    query.  Only RUNTIME_PENDING gates the silent-target skip; the
    cmd 0x22 page-entry hook has its own RESET_PENDING handling and
    doesn't participate in target-advance logic.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_loop")
    assert off >= 0
    # Window through the cadence-expired path.  Tier-1 expanded the loop
    # body twice: first with the cmd 0x22 fire-once-per-PB block, then
    # with the RESET_PENDING timeout-give-up path.  Bump window to 6000.
    body = text[off:off + 6000]
    # btfss on RUNTIME_PENDING + bra to skip the toggle: when set
    # (silent), don't skip -> btg target.
    assert re.search(
        r"btfss\s+v171_diag_flags,\s*V171_DIAG_FLAG_RUNTIME_PENDING,\s*BANKED",
        body,
    ), "silent-PB gate must check RUNTIME_PENDING before sending"
    assert re.search(
        r"btg\s+v171_diag_target,\s*0,\s*BANKED",
        body,
    ), "silent-PB gate must toggle target when RUNTIME_PENDING is still set"
    # The cadence path must SET RUNTIME_PENDING after sending so the
    # next cadence can detect a no-reply.
    assert re.search(
        r"bsf\s+v171_diag_flags,\s*V171_DIAG_FLAG_RUNTIME_PENDING,\s*BANKED",
        body,
    ), "cadence path must set RUNTIME_PENDING when issuing a query"


def test_diag_parser_clears_pending_on_bf27() -> None:
    """Coverage for HIGH #2: BF/27 reception must clear RUNTIME_PENDING
    so the NEXT cadence sees a "reply landed" state and doesn't skip
    target.  V1.71 Tier-1 renamed PENDING -> RUNTIME_PENDING (bit 1)
    and added a separate RESET_PENDING (bit 2) for the new cmd 0x22
    page-entry-only query.  This test pins the BF/27 path clearing
    RUNTIME_PENDING."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_bf2x_case_check")
    assert off >= 0
    body = text[off:off + 8000]
    # RUNTIME_PENDING clear must be inside the col_offset == 6 (BF/27) path.
    # Anchor on `movlw 0x06\ncpfseq (Common_RAM + 4)` to skip over the
    # codex-MEDIUM-fix col-7 effective-target picker (which uses
    # `movlw 0x07\ncpfslt (Common_RAM + 4)` -- different mnemonic but
    # same scratch cell).
    gate_pos = body.find("movlw   0x06\n        cpfseq  (Common_RAM + 4), A")
    assert gate_pos >= 0
    after_gate = body[gate_pos:gate_pos + 2000]
    assert re.search(
        r"bcf\s+v171_diag_flags,\s*V171_DIAG_FLAG_RUNTIME_PENDING,\s*BANKED",
        after_gate,
    ), "BF/27 path must clear RUNTIME_PENDING (Tier-1 rename of PENDING)"


def test_diag_send_query_aborts_on_tx_saturation() -> None:
    """Coverage for MED #2 (revised 2026-04-19 round 2): v171_diag_send_query
    must check STATUS.C after EVERY tx_byte_enqueue (including the final
    data byte) and bail on saturation, rather than always pumping all
    three bytes.  Without the final-byte check, a saturated TX ring
    could drop the data byte but leave 'B1 21' on the wire — MAIN would
    eventually frame-recover but only on the next route byte.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "v171_diag_send_query", "control_core_service_0F54")
    assert body, "v171_diag_send_query label missing"
    # Three bc (branch on carry) checks — one after every byte
    # enqueue (route, cmd, data).  The final-byte check was added in
    # the 2026-04-19 round-2 review fix.
    bc_count = len(re.findall(r"\n\s+bc\s+v171_diag_send_query_aborted", body))
    assert bc_count >= 3, (
        f"send_query must bc-check after EVERY enqueue (route + cmd + data); "
        f"found {bc_count} bc instructions but need >= 3"
    )
    # And the abort label must exist as a return target.
    assert "v171_diag_send_query_aborted:" in body, (
        "abort label missing — bc has no target"
    )


def test_diag_send_query_clears_pending_on_abort() -> None:
    """Coverage for F2 round 2 (2026-04-19) + codex LOW (2026-04-20):
    on TX-ring saturation, v171_diag_send_query must clear the
    pending flag matching the just-aborted query type, and ONLY that
    flag, so a sibling query already in flight keeps its tracking.

    History:
      * Round 1: clear single PENDING flag (only one query type
        existed in pre-Tier-1 V1.71).
      * Round 2: with Tier-1 RESET_PENDING added, round-1 was
        broadcast-replaced with "clear both bits" (see commit d3d15cd).
      * Codex LOW review against 86b1d1a: "clear both" is wrong when
        the cadence has cmd 0x22 already in flight (RESET_PENDING set,
        cmd 0x22 sent OK) and the immediately-following cmd 0x21 send
        aborts mid-frame.  Clearing RESET_PENDING then loses tracking
        of the in-flight cmd 0x22 and lets the next cadence re-fire
        a duplicate cmd 0x22.

    Current contract (post-codex-LOW fix):
      * Read cmd byte from (Common_RAM + 28) -- it was stashed at the
        top of v171_diag_send_query_w before any TX, so always valid.
      * cmd 0x21 -> bcf RUNTIME_PENDING only.
      * cmd 0x22 (or anything else) -> bcf RESET_PENDING only.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    abort_body = _label_body(
        text, "v171_diag_send_query_aborted", "control_core_service_0F54"
    )
    assert abort_body, "abort label missing"
    end_ret = abort_body.find("return")
    assert end_ret > 0, "abort path missing return"
    abort_body = abort_body[:end_ret + 20]
    # Both bcfs must still be present -- one for each branch.
    assert re.search(
        r"bcf\s+v171_diag_flags,\s*V171_DIAG_FLAG_RUNTIME_PENDING,\s*BANKED",
        abort_body,
    ), "abort path missing bcf RUNTIME_PENDING"
    assert re.search(
        r"bcf\s+v171_diag_flags,\s*V171_DIAG_FLAG_RESET_PENDING,\s*BANKED",
        abort_body,
    ), "abort path missing bcf RESET_PENDING"
    # NEW (codex LOW fix): the abort path must dispatch on the saved
    # cmd byte at (Common_RAM + 28) so it clears ONLY the matching bit.
    # Pin the cmd-byte load + xorlw 0x21 + bz to the runtime branch.
    assert re.search(
        r"movf\s+\(Common_RAM \+ 28\),\s*W,\s*A",
        abort_body,
    ), (
        "abort path must read the saved cmd byte from (Common_RAM + 28) "
        "to dispatch on the just-aborted query type -- pre-codex-LOW "
        "version cleared both bits unconditionally and could lose "
        "tracking of an in-flight sibling query"
    )
    assert re.search(
        r"xorlw\s+0x21\s*\n\s*bz\s+v171_diag_send_query_aborted_runtime",
        abort_body,
    ), (
        "abort path must dispatch via `xorlw 0x21; bz <runtime-label>` "
        "so cmd 0x21 takes the RUNTIME_PENDING branch and cmd 0x22 "
        "(or any non-0x21) falls through to the RESET_PENDING branch"
    )
    # And it must re-assert BANK 1 first (tx_byte_enqueue may have
    # left BSR anywhere).
    bank_assert_pos = abort_body.find("movlb   0x01")
    bcf_pos = abort_body.find("bcf")
    assert 0 <= bank_assert_pos < bcf_pos, (
        "abort path must movlb 0x01 before bcf v171_diag_flags so the "
        "flag-byte access lands in the right bank regardless of where "
        "tx_byte_enqueue left BSR"
    )


# V32-side BSR safety test lives in test_v32_layer5_diag_counters.py.


# ===========================================================================
# F1 (2026-04-19 round 2): spec-collapse — single sentinel for both
# "topology absent" and "PB silent / unsupported".
# ===========================================================================


def test_diag_renderer_uses_single_sentinel_no_topology_byte() -> None:
    """The chain protocol does not give CONTROL an independent way to
    distinguish "PB2 doesn't exist" from "PB2 exists but is silent or
    doesn't support cmd 0x21" — every probe goes through the same
    diag query path.  Spec was revised 2026-04-19 to retire the
    draft's `--` rendering and use `n/a` for both cases.

    Phase 3.4 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) preserved this
    design under the per-PB sparse layout: v171_diag_render_absent
    is the single sentinel path, dispatched via the BANK 1 cell
    v171_diag_render_pb_index rather than per-PB labels.

    This test pins:
    * No separate ``v171_diag_topology`` symbol.
    * No `--` literal in the render path.
    * The present-mask gate uses v171_diag_present (read into W via
      andwf with a per-PB mask computed from v171_diag_render_pb_index).
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # No separate topology state.
    assert "v171_diag_topology" not in text, (
        "no separate topology byte allowed — spec collapse uses "
        "v171_diag_present alone for both 'topology absent' and "
        "'PB silent' cases"
    )
    ram = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    assert "v171_diag_topology" not in ram, (
        "no v171_diag_topology equ allowed in ram.inc — spec collapse"
    )
    # No `--` literal in the render path (must use 'n/a' for both).
    render_body = _label_body(
        text, "v171_diag_screen", "v171_diag_pad_spaces",
    )
    assert render_body, (
        "renderer span (v171_diag_screen .. v171_diag_pad_spaces) not "
        "located in source"
    )
    assert "'-'" not in render_body, (
        "no '-' character literal in render path — spec collapse "
        "uses 'n/a' for both topology-absent and silent-PB cases"
    )
    # Per-PB layout gates on v171_diag_present using a computed per-PB
    # mask.  Phase 3.4 form: `andwf v171_diag_present, W, BANKED` after
    # loading W with 0x01 (PB1) or 0x02 (PB2).
    assert re.search(
        r"andwf\s+v171_diag_present,\s*W,\s*BANKED",
        render_body,
    ), (
        "Phase 3.4 must gate the absent path via "
        "`andwf v171_diag_present, W, BANKED` with W = per-PB mask "
        "(0x01 for PB1, 0x02 for PB2)"
    )


def test_diag_renderer_single_per_pb_dispatched_sentinel_path() -> None:
    """Phase 3.4 collapses the legacy two-label layout
    (``v171_diag_pb1_render_na`` + ``v171_diag_pb2_render_na``) into
    ONE label (``v171_diag_render_absent``) that handles both PB1 and
    PB2 via PB-index dispatch from v171_diag_render_pb_index.

    Adding a second sentinel block would re-introduce the per-PB
    branching the per-PB layout was designed to eliminate.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # Legacy per-PB labels must NOT exist in Phase 3.4.
    pb1_na = re.findall(r"^v171_diag_pb1_render_\w+:", text, re.MULTILINE)
    pb2_na = re.findall(r"^v171_diag_pb2_render_\w+:", text, re.MULTILINE)
    assert not pb1_na, (
        f"legacy v171_diag_pb1_render_* labels must be removed in "
        f"Phase 3.4; got {pb1_na}"
    )
    assert not pb2_na, (
        f"legacy v171_diag_pb2_render_* labels must be removed in "
        f"Phase 3.4; got {pb2_na}"
    )
    # New single sentinel path.
    absent = re.findall(
        r"^v171_diag_render_absent\w*:", text, re.MULTILINE,
    )
    assert absent == ["v171_diag_render_absent:"], (
        f"Phase 3.4 must have exactly one absent-render path; got "
        f"{absent}"
    )


def test_diag_renderer_collapse_documented_in_spec() -> None:
    """Spec must explicitly call out the 2026-04-19 collapse decision
    so future readers don't re-introduce the `--` vs `n/a` distinction
    based on the draft's earlier wording.  The relevant CONTROL-side
    requirements line must mention `n/a` and the rationale.
    """
    from dlcp_fw.paths import DOCS_DIR
    spec = (DOCS_DIR / "V163B_DIAGNOSTICS_MENU_SPEC.md").read_text(encoding="utf-8")
    # Spec must mention the collapse decision and the rationale.
    assert "retired" in spec.lower() and "--" in spec, (
        "spec must document that the `--` rendering was retired in favor "
        "of single `n/a` sentinel"
    )
    assert "topology absence" in spec.lower() or "topology" in spec.lower(), (
        "spec must explain the topology-vs-silence collapse rationale"
    )


# ===========================================================================
# V1.71 Tier-1 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) -- cmd 0x22 fire-once-
# per-PB hook tests.
# ===========================================================================


def test_diag_loop_fires_cmd_22_once_per_pb_per_page_entry() -> None:
    """The cadence loop must check v171_diag_reset_seen for the in-flight
    target and, if the bit is clear AND RESET_PENDING is clear, fire
    cmd 0x22 (via v171_diag_send_reset_query) and set RESET_PENDING.

    Without this, the reset-cause cells stay at 0 forever -- the cmd 0x22
    chain handler exists in MAIN but is never invoked from CONTROL.

    Pin the gate structure so a refactor that drops the fire-once
    guarantee (e.g. firing on every cadence cycle, which would burn
    chain bandwidth) fails this test.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_loop")
    # 6 KB window covers the loop body through the cmd 0x22 hook +
    # the RESET_PENDING timeout-give-up path + cmd 0x21 cadence +
    # check_redraw block.
    body = text[off:off + 6000]
    # The hook must check RESET_PENDING.  Tier-1 timeout (F1 fix) made
    # this a btfss + bra-to-check-reset-seen pattern: when PENDING is
    # SET, fall into the timeout-decrement branch; when CLEAR, branch to
    # the "should we fire?" check.  Either btfsc or btfss against
    # RESET_PENDING is acceptable -- pin presence of either.
    assert re.search(
        r"btf[sc]{2}\s+v171_diag_flags,\s*V171_DIAG_FLAG_RESET_PENDING,\s*BANKED",
        body,
    ), "cmd 0x22 hook must check RESET_PENDING before firing"
    # Must reference v171_diag_reset_seen.
    assert "v171_diag_reset_seen" in body, (
        "cmd 0x22 hook must check v171_diag_reset_seen for the in-flight PB"
    )
    # Must call the reset-query helper.
    assert re.search(r"rcall\s+v171_diag_send_reset_query", body), (
        "cmd 0x22 hook must call v171_diag_send_reset_query"
    )
    # Must set RESET_PENDING before firing (not after) so the parser's
    # BF/2B handler can clear it without racing the cmd 0x21 path.
    set_pos = body.find("bsf     v171_diag_flags, V171_DIAG_FLAG_RESET_PENDING, BANKED")
    rcall_pos = body.find("rcall   v171_diag_send_reset_query")
    assert 0 <= set_pos < rcall_pos, (
        "RESET_PENDING must be set BEFORE the rcall to send_reset_query "
        "so a fast BF/2B reply can't clear PENDING before it's set"
    )


def test_bf2x_parser_uses_effective_target_for_cmd22_frames() -> None:
    """Codex MEDIUM review (against commit d3d15cd, 2026-04-20):
    v171_bf2x_case_check must pick the cache base from the EFFECTIVE
    target -- v171_diag_target for col 0..6 (cmd 0x21 reply frames),
    v171_diag_reset_target for col 7..10 (cmd 0x22 reply frames).

    Bug pre-fix: the parser always read v171_diag_target.0 to pick the
    cache base.  v171_diag_target can toggle independently between
    cmd 0x22 send and BF/2B reception (via an interleaved cmd 0x21
    BF/27 from the OTHER PB), so reading the live target for cmd 0x22
    frames would mis-route the 4 reset bytes to the wrong PB's cache
    cells AND set the wrong v171_diag_reset_seen bit on BF/2B.

    Fix: stash the effective target into (Common_RAM + 5) before the
    cache-base compute, with a cpfslt(0x07) gate that overrides with
    v171_diag_reset_target when col >= 7.  Then both the cache-base
    btfsc AND the BF/2B reset_seen-OR-in btfsc read from
    (Common_RAM + 5) instead of v171_diag_target directly.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_bf2x_case_check")
    body = text[off:off + 8000]
    # The col-7 gate must be present (cpfslt against W=0x07 on col_offset).
    assert re.search(
        r"movlw\s+0x07\s*\n\s*cpfslt\s+\(Common_RAM \+ 4\),\s*A",
        body,
    ), (
        "col-7 effective-target gate missing -- without it, cmd 0x22 "
        "frames (col 7..10) get routed by the live target which can "
        "drift mid-burst via BF/27 toggle from the other PB"
    )
    # The override must read v171_diag_reset_target (the snapshot).
    assert re.search(
        r"movf\s+v171_diag_reset_target,\s*W,\s*BANKED",
        body,
    ), (
        "col-7 override must load v171_diag_reset_target "
        "(snapshot at cmd 0x22 send time)"
    )
    # And the override must store into (Common_RAM + 5) so downstream
    # cache-base + reset_seen logic picks it up.
    override_pos = body.find("v171_bf2x_use_reset_target:")
    assert override_pos >= 0, "override label missing"
    override_body = body[override_pos:override_pos + 200]
    assert re.search(
        r"movwf\s+\(Common_RAM \+ 5\),\s*A",
        override_body,
    ), "override must write effective_target into (Common_RAM + 5)"
    # Cache-base picker must read (Common_RAM + 5), NOT v171_diag_target.
    # Search for the btfsc on (Common_RAM + 5), 0 between the override-
    # done label and the FSR0L write.
    have_label = "v171_bf2x_have_effective_target:"
    have_pos = body.find(have_label)
    assert have_pos >= 0, "effective-target-done label missing"
    fsr0l_pos = body.find("movwf   FSR0L", have_pos)
    assert fsr0l_pos > have_pos, "FSR0L write missing after effective-target picker"
    base_block = body[have_pos:fsr0l_pos]
    assert re.search(
        r"btfsc\s+\(Common_RAM \+ 5\),\s*0,\s*A",
        base_block,
    ), (
        "cache-base picker must btfsc on (Common_RAM + 5), 0 -- NOT "
        "v171_diag_target.  Reading v171_diag_target here re-introduces "
        "the cmd 0x22 frame-mis-routing bug."
    )
    # BF/2B reset_seen path must also btfsc (Common_RAM + 5), 0 (NOT
    # v171_diag_target) -- pin this explicitly.
    reset_last_pos = body.find("v171_bf2x_check_reset_last:")
    assert reset_last_pos > 0, "reset-last-frame label missing"
    reset_block = body[reset_last_pos:reset_last_pos + 1500]
    iorwf_pos = reset_block.find("iorwf   v171_diag_reset_seen")
    assert iorwf_pos > 0, "reset_seen OR-in missing"
    pre_iorwf = reset_block[:iorwf_pos]
    assert re.search(
        r"btfsc\s+\(Common_RAM \+ 5\),\s*0,\s*A",
        pre_iorwf,
    ), (
        "BF/2B reset_seen OR-in must btfsc on (Common_RAM + 5), 0 -- "
        "reading v171_diag_target here would set the wrong reset_seen "
        "bit if target toggled mid-burst"
    )


def test_diag_loop_times_out_reset_pending_after_n_cadences() -> None:
    """V1.71 Tier-1 F1 fix (2026-04-20 review): RESET_PENDING must time
    out after a fixed number of cadence cycles so a silent or pre-0x37
    PB doesn't lock cmd 0x22 path forever.

    Without this gate, RESET_PENDING stays set forever after the first
    cmd 0x22 send to a non-responding target, blocking BOTH PBs from
    receiving cmd 0x22 for the rest of the Diag-page visit.

    The fix:
      * Snapshot v171_diag_target into v171_diag_reset_target at send
        time so the timeout-give-up path knows which PB to mark as
        reset_seen (target may toggle independently via the cmd 0x21
        BF/27 path between send and timeout).
      * Reload v171_diag_reset_timeout to V171_DIAG_RESET_TIMEOUT_RELOAD
        on send.
      * Each cadence with RESET_PENDING set decrements the timeout.
      * On reaching zero: set v171_diag_reset_seen.reset_target bit
        (treat as "unknown" per spec) and clear RESET_PENDING.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_loop")
    body = text[off:off + 6000]
    # Snapshot of v171_diag_target into v171_diag_reset_target on send.
    assert re.search(
        r"movwf\s+v171_diag_reset_target,\s*BANKED",
        body,
    ), (
        "send path must snapshot v171_diag_target into "
        "v171_diag_reset_target so the timeout path can identify the "
        "in-flight reset PB independent of v171_diag_target drift"
    )
    # Timeout reload on send.
    assert re.search(
        r"movlw\s+V171_DIAG_RESET_TIMEOUT_RELOAD\s*\n\s*"
        r"movwf\s+v171_diag_reset_timeout,\s*BANKED",
        body,
    ), "send path must reload v171_diag_reset_timeout to spec value"
    # Decrement on cadence with PENDING set.
    assert re.search(
        r"decf\s+v171_diag_reset_timeout,\s*F,\s*BANKED",
        body,
    ), "cadence loop must decrement v171_diag_reset_timeout when PENDING is set"
    # On timeout-expiry: iorwf into v171_diag_reset_seen using
    # v171_diag_reset_target as the bit selector + bcf RESET_PENDING.
    assert re.search(
        r"btfsc\s+v171_diag_reset_target,\s*0,\s*BANKED",
        body,
    ), (
        "timeout-give-up path must select PB1/PB2 mask based on "
        "v171_diag_reset_target snapshot (NOT v171_diag_target which "
        "may have toggled)"
    )
    # Must clear RESET_PENDING on timeout (otherwise we'd loop forever).
    bcf_pending = re.findall(
        r"bcf\s+v171_diag_flags,\s*V171_DIAG_FLAG_RESET_PENDING,\s*BANKED",
        body,
    )
    assert len(bcf_pending) >= 1, (
        "timeout-give-up path must clear RESET_PENDING -- otherwise the "
        "timeout decrement would underflow and lock the path forever"
    )


# ===========================================================================
# Phase 3.4 (V32_DIAG_TIER1_SPEC.md, 2026-04-20) -- per-PB Option-D sparse
# renderer structural gates.  These pin shape decisions that the renderer
# must preserve (layout dispatch on count, FSR1 cache base loading via
# pb_index, scratch cells in BANK 1 to avoid the Phase 3.1 aliasing
# landmine that caused the 2026-04-20 real-HW disaster).
# ===========================================================================


def test_phase3_4_render_scratch_cells_pinned_in_safe_bank1_range() -> None:
    """The Phase 3.4 sparse renderer needs scratch cells that survive
    across the cadence loop's redraw path.  All cells live in BANK 1
    (operand range 0x0CD..0x0D3) -- a range chosen to be SAFE in the
    aliasing sense:

    * BANK 0 operand 0xCD..0xD3 is used by the EEPROM saved-settings
      load/save/clear routines (lfsr 0x0, 0x0CD walks).  That's ABSOLUTE
      addressing via FSR0; doesn't touch BSR=1 banked accesses to the
      same operand value, which land at PHYSICAL 0x1CD..0x1D3 (BANK 1).
    * No other BANK 1 EQU touches operand 0xCD..0xD3 in V1.71.

    A future change that picked operands < 0x0CD would risk re-creating
    the Phase 3.1 aliasing landmine that caused the 2026-04-20 real-HW
    disaster (cache cells at 0x080..0x09F aliased rx_ring_rd/wr,
    tx_ring_rd/wr, idle_timeout, full_sync_lo when BSR=1 leaked into
    parser tail code).
    """
    ram = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    expected = (
        ("v171_diag_render_pb_index", 0xCD),
        ("v171_diag_render_count",    0xCE),
        ("v171_diag_render_emitted",  0xCF),
        ("v171_diag_render_walk_idx", 0xD0),
        ("v171_diag_render_value",    0xD1),
        ("v171_diag_render_skipped",  0xD2),
        ("v171_diag_render_letter_tmp", 0xD3),
        ("v171_diag_render_abnormal", 0xD4),
    )
    for name, expected_op in expected:
        actual = _equ_address(ram, name)
        assert actual == expected_op, (
            f"{name} must equ 0x{expected_op:02X}; got "
            f"{actual:#x}" if actual is not None else f"{name} not defined"
        )


def test_phase3_4_load_fsr1_base_branches_on_pb_index() -> None:
    """v171_diag_load_fsr1_base must dispatch on v171_diag_render_pb_index
    bit 0 to load FSR1 with PB1 base (0x180) or PB2 base (0x18B).
    Without this, the row walks would always read PB1 (or always PB2),
    breaking the per-PB layout.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "v171_diag_load_fsr1_base", "v171_diag_letter_for_idx")
    assert body, "v171_diag_load_fsr1_base body could not be located"
    # PB-index dispatch via btfsc on bit 0.
    assert re.search(
        r"btfsc\s+v171_diag_render_pb_index,\s*0,\s*BANKED",
        body,
    ), "must dispatch on v171_diag_render_pb_index.0 (PB index)"
    # Load FSR1 with both PB1 and PB2 cache bases.
    assert re.search(r"lfsr\s+0x1,\s*0x180", body), (
        "PB1 path must load FSR1 with 0x180 (v171_diag_pb1_i physical)"
    )
    assert re.search(r"lfsr\s+0x1,\s*0x18B", body), (
        "PB2 path must load FSR1 with 0x18B (v171_diag_pb2_i physical)"
    )


def test_phase3_4_renderer_dispatches_three_layouts() -> None:
    """The renderer must branch on the abnormal-count to dispatch into
    one of three layout paths:
    * v171_diag_render_absent  (present-mask bit clear)
    * v171_diag_render_healthy (abnormal == 0; POR-only or all-zero)
    * v171_diag_render_degraded (any runtime/BOR/WDT/SW non-zero)

    The healthy gate uses v171_diag_render_abnormal, NOT
    v171_diag_render_count.  Counting POR (cell index 7) toward the
    gate would make "OK" unreachable because Phase 2.2 cold-init
    classification always sets exactly one of POR/BOR/WDT/SW to 1
    on every power-on, and POR is the most common.  See
    V32_DIAG_TIER1_SPEC.md §"LCD layouts" + §"Status classification"
    -- POR is "expected" / "normal" and not operator-actionable.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    for label in ("v171_diag_render_absent",
                  "v171_diag_render_healthy",
                  "v171_diag_render_degraded"):
        assert _label_offset(text, label) >= 0, (
            f"Phase 3.4 layout label '{label}' must exist"
        )
    # Render dispatch: abnormal == 0 -> healthy, else -> degraded.
    body = _label_body(text, "v171_diag_screen_present", "v171_diag_render_absent")
    assert body, "v171_diag_screen_present body could not be located"
    # The gate MUST test v171_diag_render_abnormal (NOT
    # v171_diag_render_count which counts POR too).
    assert re.search(
        r"movf\s+v171_diag_render_abnormal,\s*F,\s*BANKED",
        body,
    ), (
        "healthy/degraded gate must test v171_diag_render_abnormal "
        "(not v171_diag_render_count -- that would include POR which "
        "is set on every cold-init, making 'OK' unreachable)"
    )
    assert re.search(
        r"bz\s+v171_diag_render_healthy", body,
    ), "abnormal == 0 must branch to v171_diag_render_healthy"
    assert re.search(
        r"bra\s+v171_diag_render_degraded", body,
    ), "abnormal != 0 must fall through to v171_diag_render_degraded"


def test_phase3_4_count_walk_excludes_por_from_abnormal() -> None:
    """v171_diag_screen_present uses 3 sub-passes to walk the cache:
      * sub-pass A: cells [0..6] = runtime counters (I D S B R A P)
                    -> increment BOTH count AND abnormal.
      * sub-pass B: cell  [7]    = POR flag (O)
                    -> increment ONLY count, NOT abnormal.
      * sub-pass C: cells [8..10] = BOR / WDT / SW flags (V W X)
                    -> increment BOTH count AND abnormal.

    This split implements the spec's POR-is-expected rule.  A
    regression that re-merged the walk into a single 11-cell pass
    would either break the OK gate (if abnormal is incremented for
    POR too) or break the row-1 gating (if count loses POR).

    Pin the 3-sub-pass shape via the loop labels.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "v171_diag_screen_present", "v171_diag_render_absent")
    assert body, "v171_diag_screen_present body could not be located"
    # Each sub-pass has a distinct label.
    for label in (
        "v171_diag_count_runtime_loop",
        "v171_diag_count_por_skip",
        "v171_diag_count_abnormal_loop",
    ):
        assert label + ":" in body, (
            f"sub-pass label '{label}' missing from count walk -- "
            f"the 3-pass split is what implements POR-as-expected"
        )
    # POR sub-pass MUST NOT touch v171_diag_render_abnormal.  Locate the
    # POR span (between v171_diag_count_runtime_skip end and
    # v171_diag_count_abnormal_loop start) and assert no abnormal incf
    # appears there.
    por_start = body.find("v171_diag_count_runtime_skip:")
    por_loop_idx = body.find("v171_diag_count_abnormal_loop:", por_start)
    assert por_start >= 0 and por_loop_idx > por_start
    # Find the POR sub-pass body: from after the runtime decfsz through
    # the v171_diag_count_por_skip label.
    por_section_start = body.find("v171_diag_count_runtime_loop\n", por_start)
    if por_section_start < 0:
        por_section_start = por_start
    por_section = body[por_section_start:por_loop_idx]
    abnormal_incs_in_por = re.findall(
        r"incf\s+v171_diag_render_abnormal,\s*F,\s*BANKED",
        por_section,
    )
    assert not abnormal_incs_in_por, (
        "POR sub-pass must NOT increment v171_diag_render_abnormal -- "
        "that would make 'OK' unreachable when POR=1 (which is every "
        "cold-init).  Found increments at: " + str(abnormal_incs_in_por)
    )


def test_phase3_4_overflow_marker_only_when_count_ge_10() -> None:
    """The ".." overflow marker is emitted only when count >= 10
    (4 entries on row 0 + 5 entries on row 1 + ".." indicating MORE).
    The decision uses cpfslt with literal 0x0A.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body = _label_body(text, "v171_diag_row1_done", "v171_diag_load_fsr1_base")
    assert body, "v171_diag_row1_done body could not be located"
    # cpfslt against 0x0A or 10 (10 == 0x0A).
    assert re.search(
        r"movlw\s+0x0[Aa]\b", body,
    ), "overflow gate must use literal 0x0A (= 10)"
    assert re.search(
        r"cpfslt\s+v171_diag_render_count,\s*BANKED", body,
    ), "overflow gate must compare v171_diag_render_count against 0x0A"
    # Overflow path emits two '.' literals.
    overflow_body = _label_body(
        text, "v171_diag_row1_overflow", "v171_diag_load_fsr1_base",
    )
    assert overflow_body, "v171_diag_row1_overflow body could not be located"
    dot_count = len(re.findall(r"movlw\s+'\.'", overflow_body))
    assert dot_count == 2, (
        f"overflow path must emit exactly two '.' literals; got {dot_count}"
    )


# ---------------------------------------------------------------------------
# Phase 3.4 follow-up gates: codex MEDIUM finding (against commit 9bed274)
# ---------------------------------------------------------------------------
# Codex flagged that the four "Phase 3.4" gates above are mostly shape /
# literal checks -- they don't lock down the highest-risk regressions
# the renderer commit could re-introduce.  The four gates below close
# the gap by pinning:
#   1. No other BANK 1 EQU collides with the new 0xCD..0xD3 scratch
#      range (the docstring claim from
#      test_phase3_4_render_scratch_cells_pinned_in_safe_bank1_range
#      lifted into an assertion).
#   2. movlb 0x01 discipline before BANKED writes to the new scratch
#      cells (a missing movlb 0x01 = silent corruption of EEPROM
#      saved-settings cache at physical 0x0CD..0x0D3).
#   3. Pad-count math for both rows (12 - emitted*3 row 0;
#      17 - emitted*3 row 1).  An off-by-one here breaks the layout
#      width invariant for ALL count values 1..9.
#   4. FSR1 isn't clobbered across letter_for_idx / pad_spaces /
#      lcd_char_write helper calls in the two row walks.
# ---------------------------------------------------------------------------


def test_phase3_4_no_other_bank1_equ_collides_with_scratch_range() -> None:
    """Phase 3.4 cells live at operands 0xCD..0xD3 in BANK 1.  Verify
    no other named EQU in dlcp_control_ram.inc resolves to any of those
    operand values -- a collision would mean two different names
    referring to the same physical BANK 1 cell, with one of them silently
    corrupted on every renderer call.

    This is the strong form of the safety claim the original Phase 3.4
    docstring made; codex flagged that the docstring wasn't backed by
    an assertion.
    """
    ram = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    phase3_4_names = {
        "v171_diag_render_pb_index",
        "v171_diag_render_count",
        "v171_diag_render_emitted",
        "v171_diag_render_walk_idx",
        "v171_diag_render_value",
        "v171_diag_render_skipped",
        "v171_diag_render_letter_tmp",
        "v171_diag_render_abnormal",
    }
    phase3_4_operands = {0xCD, 0xCE, 0xCF, 0xD0, 0xD1, 0xD2, 0xD3, 0xD4}
    # Walk every EQU in the file; flag any that resolves (literal OR
    # symbolic alias chain) to a Phase 3.4 operand.  Symbolic aliases
    # like `V171_DIAG_FLAG_PENDING equ V171_DIAG_FLAG_RUNTIME_PENDING`
    # exist in this file (line ~274), so a literal-only regex would
    # miss alias-style collisions -- _equ_address resolves them
    # recursively.
    collisions: list[tuple[str, int]] = []
    for m in re.finditer(
        r"^\s*(\w+)\s+(?:EQU|equ)\s+\S+",
        ram, re.MULTILINE,
    ):
        name = m.group(1)
        if name in phase3_4_names:
            continue
        value = _equ_address(ram, name)
        if value is None:
            # Unresolvable alias -- skip (e.g., refers to a name not
            # defined in this file).  Real cells must resolve.
            continue
        if value in phase3_4_operands:
            collisions.append((name, value))
    assert not collisions, (
        f"BANK 1 operand collision with Phase 3.4 scratch range: "
        + ", ".join(f"{n}=0x{v:02X}" for n, v in collisions)
        + ".  Either move the colliding cell or move the Phase 3.4 "
        "scratch range -- two names at the same operand means silent "
        "corruption on every renderer call."
    )


def test_phase3_4_renderer_movlb_discipline_before_banked_writes() -> None:
    """Every BANKED write to the new Phase 3.4 scratch cells must be
    preceded by `movlb 0x01` somewhere upstream in the routine.

    The 2026-04-20 real-HW disaster (commit 4acbcfb) was a BSR-leak
    bug -- the parser tail ran with BSR=1 instead of BSR=0 and read
    rx_ring/idle_timeout cells as if they were diag-cache cells.  A
    SAME-CLASS bug in the renderer would silently corrupt EEPROM
    saved-settings cache at physical 0x0CD..0x0D3 (since BSR=0 +
    operand 0xCD reaches the same cells the EEPROM lfsr 0x0, 0x0CD
    walks touch).

    This test walks every BANKED access to a v171_diag_render_*
    cell.  For each access, it walks BACKWARD through INSTRUCTION
    lines (skipping comments/blanks except for routine separators)
    and applies these rules:

      * `movlb 0x01` (or `movlb 0x1`) -> BSR=1 confirmed, OK.
      * `rcall v171_diag_load_fsr1_base` -> helper leaves BSR=1 on
        return (documented contract; see asm comments).
      * `movlb 0x00` (or `movlb 0x0`) -> BSR=0 BARRIER: walking
        past a BSR=0 setter without finding a subsequent movlb 0x01
        in between means BSR is 0 at the access -> leak.
      * Routine-separator comment line (`;  -----...---`) ->
        ROUTINE BARRIER: that line marks the start of the routine
        the access lives in.  If we walked past it without finding
        movlb 0x01, the routine doesn't establish BSR=1 at entry.

    `return` is intentionally NOT treated as a barrier: cascading
    routines like v171_diag_letter_for_idx have multiple internal
    `return` blocks separating bra-target labels that share the
    routine-entry's movlb 0x01.  Walking past `return` to reach
    the routine entry is correct.  The routine-separator comment
    is the trustworthy boundary.

    Also covers `decfsz` / `decf` / `incfsz` (loop counters) and
    every PIC18 instruction mnemonic that can take a file operand.
    Codex flagged the original pattern missing `decfsz` (real
    use at v171_asm:3406); broadened here to all f-operand
    mnemonics so future additions don't slip past.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    lines = text.split("\n")

    def is_instruction(line: str) -> bool:
        """True if the line carries an actual instruction (not blank,
        not a label-only line, not a pure comment)."""
        s = line.split(";", 1)[0].strip()
        if not s:
            return False
        # Label-only line: ends with ':' and has no whitespace before.
        if re.match(r"^\w+:\s*$", s):
            return False
        return True

    # Match BANKED accesses to any v171_diag_render_* cell.  Pattern
    # covers every PIC18 mnemonic that takes an f-operand: read/write
    # (mov*, clrf, setf), arithmetic (add*, sub*, neg*), bit-test/set
    # (btf*, bs*/bcf, btg), compare (cpfs*), increment/decrement
    # including the -sz / -snz skip variants (incf, incfsz, decf,
    # decfsz, dcfsnz, infsnz), bitwise (and*, ior*, xor*), rotate
    # (rlcf, rlncf, rrcf, rrncf, swapf), test (tstfsz), file-to-file
    # (movff -- treated as one of the operands).
    access_pattern = re.compile(
        r"\b(?:movwf|movf|movff|clrf|setf|"
        r"addwf|addwfc|subfwb|subwf|subwfb|negf|"
        r"btfsc|btfss|bsf|bcf|btg|"
        r"cpfslt|cpfseq|cpfsgt|"
        r"incf|incfsz|infsnz|decf|decfsz|dcfsnz|"
        r"iorwf|andwf|xorwf|comf|"
        r"rlcf|rlncf|rrcf|rrncf|swapf|"
        r"tstfsz)"
        r"\s+v171_diag_render_\w+(?:,\s*[FW])?(?:,\s*\w+)?,\s*BANKED"
    )
    movlb_b1_pattern = re.compile(r"\bmovlb\s+0x0?1\b")
    movlb_b0_pattern = re.compile(r"\bmovlb\s+0x0?0\b")
    bsr1_helper_pattern = re.compile(r"\brcall\s+v171_diag_load_fsr1_base\b")
    # Routine separator: comment line composed mostly of dashes.  Two
    # such lines bracket each routine's docstring header in this file.
    separator_pattern = re.compile(r"^\s*;\s*-{20,}\s*$")

    leak_sites: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        if not access_pattern.search(line):
            continue
        # Walk backward.  Skip blank lines and label-only lines, but
        # DO inspect comment lines (we need to detect the routine
        # separator).
        verdict: str | None = None
        steps = 0
        for back in range(1, len(lines)):
            if idx - back < 0:
                verdict = "walked off start of file with no movlb 0x01"
                break
            prev = lines[idx - back]
            # Routine boundary: separator comment.
            if separator_pattern.match(prev):
                verdict = (
                    f"walked past routine-separator comment at line "
                    f"{idx - back + 1} without finding movlb 0x01 "
                    f"(routine entry doesn't establish BSR=1)"
                )
                break
            if not is_instruction(prev):
                continue
            if movlb_b1_pattern.search(prev) or bsr1_helper_pattern.search(prev):
                # Confirmed BSR=1 upstream -- safe.
                break
            if movlb_b0_pattern.search(prev):
                verdict = (
                    f"upstream `movlb 0x00` at line {idx - back + 1} "
                    f"with no intervening movlb 0x01"
                )
                break
            steps += 1
            if steps > 200:
                verdict = "no movlb 0x01 found within 200 instruction lines"
                break
        if verdict:
            leak_sites.append((idx + 1, line.strip(), verdict))
    assert not leak_sites, (
        f"BANKED v171_diag_render_* access without an upstream movlb "
        f"0x01 (or rcall to v171_diag_load_fsr1_base, which leaves "
        f"BSR=1 on return):\n"
        + "\n".join(f"  line {n}: {ln}\n      reason: {v}"
                    for n, ln, v in leak_sites)
        + "\n\nA BSR=0 leak here would land at PHYSICAL 0x0CD..0x0D3 "
        "(EEPROM saved-settings cache region) -- silent corruption."
    )


def test_phase3_4_pad_count_math_yields_16_chars_per_row() -> None:
    """The pad-count expressions encoded in the assembly source must
    produce the correct trailing-space counts for each row layout.

    Row 0 (degraded, after "PBN:"):
      written so far = 4 + emitted * 3 chars (PBN: + " X#" each)
      pad needed     = 16 - (4 + emitted * 3) = 12 - emitted * 3
      asm encodes this as: addwf WREG, W; addwf emitted, W; sublw 0x0C

    Row 1 (degraded, no leading space on first entry):
      written so far = 2 + (emitted - 1) * 3 = emitted * 3 - 1
                       (only when emitted >= 1; if emitted == 0 the
                        layout uses the count <= 4 blanket pad of 16
                        spaces instead).
      pad needed     = 16 - (emitted * 3 - 1) = 17 - emitted * 3
      asm encodes this as: addwf WREG, W; addwf emitted, W; sublw 0x11
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # Row 0 done block computes pad_count = 12 - emitted*3.
    row0_body = _label_body(text, "v171_diag_row0_done", "v171_diag_row1_walk_setup")
    assert row0_body, "v171_diag_row0_done body could not be located"
    assert re.search(
        r"addwf\s+v171_diag_render_emitted,\s*W,\s*BANKED", row0_body,
    ), "row 0 pad math must include addwf v171_diag_render_emitted, W (= W*3)"
    assert re.search(r"sublw\s+0x0C\b", row0_body), (
        "row 0 pad math must end with `sublw 0x0C` (= 12 - emitted*3)"
    )
    # Row 1 done block computes pad_count = 17 - emitted*3 (no overflow).
    row1_body = _label_body(text, "v171_diag_row1_done", "v171_diag_row1_overflow")
    assert row1_body, "v171_diag_row1_done body could not be located"
    assert re.search(
        r"addwf\s+v171_diag_render_emitted,\s*W,\s*BANKED", row1_body,
    ), "row 1 pad math must include addwf v171_diag_render_emitted, W (= W*3)"
    assert re.search(r"sublw\s+0x11\b", row1_body), (
        "row 1 pad math must end with `sublw 0x11` (= 17 - emitted*3)"
    )
    # Verify the math by enumerating the layout for every count value:
    # for each non-overflow count 1..9, the row 0 + row 1 widths must
    # equal exactly 16 chars each (after padding).
    for count in range(1, 10):
        row0_emitted = min(count, 4)
        row1_emitted = max(0, count - 4)
        row0_chars = 4 + row0_emitted * 3                   # "PBN:" + " X#" each
        row0_pad = 12 - row0_emitted * 3
        assert row0_chars + row0_pad == 16, (
            f"count={count}: row 0 width invariant broken: "
            f"{row0_chars} + {row0_pad} != 16"
        )
        if row1_emitted == 0:
            row1_chars = 0
            row1_pad = 16
        else:
            # First entry has no leading space; subsequent entries 3 chars.
            row1_chars = 2 + (row1_emitted - 1) * 3
            row1_pad = 17 - row1_emitted * 3
        assert row1_chars + row1_pad == 16, (
            f"count={count}: row 1 width invariant broken: "
            f"{row1_chars} + {row1_pad} != 16"
        )


def test_phase3_4_helpers_do_not_clobber_fsr1() -> None:
    """The two row walks rely on FSR1 surviving across every routine
    they call from inside the loop body.  Verify that none of those
    routines touch FSR1L / FSR1H / lfsr 0x1 -- i.e., the renderer can
    safely walk the cache via POSTINC1 across helper calls.

    Coverage list (callees reached from inside the row walks):
      * v171_diag_letter_for_idx -- letter cascade (Phase 3.4 new)
      * v171_diag_pad_spaces     -- trailing-space writer (Phase 3.4 new)
      * v171_diag_emit_letter    -- thin lcd_char_write wrapper
      * v171_diag_emit_nib_w     -- nibble-to-LCD encoder (incl.
                                    secondary entries _zero/_alpha/_sat
                                    which fall within the same body)
      * lcd_char_write           -- pre-existing LCD primitive; codex
                                    flagged that the previous version
                                    of this test claimed coverage but
                                    didn't include it in the list
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")

    # Per-helper (start_label, end_label) pairs.  end_label is the
    # IMMEDIATELY-NEXT top-level routine entry in the source -- chosen
    # explicitly per helper so the scan body is exactly the helper's
    # routine, not the helper PLUS unrelated downstream code that
    # happens to share a separator block.
    #
    # Codex flagged a previous version that scanned to the next
    # `; ----...----` separator: lcd_char_write ends at line ~356 but
    # next separator is at ~367 (so scan included
    # lcd_command_or_eeprom_read), and v171_diag_pad_spaces ends at
    # ~3725 but next separator is at ~3897 (so scan included
    # v171_diag_screen_armed through v171_diag_check_buttons).  Those
    # downstream routines aren't called from inside the row walks, so
    # an FSR1 touch there is irrelevant to row-walk correctness, but
    # it would still fail this test.  Per-helper end markers eliminate
    # the false-positive risk.
    helpers = (
        ("v171_diag_letter_for_idx", "v171_diag_pad_spaces"),
        ("v171_diag_pad_spaces",     "v171_diag_screen_armed"),
        ("v171_diag_emit_letter",    "v171_diag_emit_nib_w"),
        ("v171_diag_emit_nib_w",     "v171_diag_send_runtime_query"),
        ("lcd_char_write",           "lcd_command_or_eeprom_read"),
    )

    for helper, end_marker in helpers:
        # Defensive: verify BOTH labels exist before slicing.
        # _label_body returns text[start:] when end_label is missing
        # (silently widening the scan to EOF), so a rename of either
        # end_marker would otherwise weaken the test without failing
        # it.  Assert both endpoints explicitly.
        assert _label_offset(text, helper) >= 0, (
            f"helper start label '{helper}' missing from source"
        )
        assert _label_offset(text, end_marker) >= 0, (
            f"helper end-marker label '{end_marker}' missing from source "
            f"-- if it was renamed, update the helpers tuple to the new "
            f"name (a missing end_marker would silently widen this scan "
            f"to EOF and weaken FSR1-clobber coverage)"
        )
        body = _label_body(text, helper, end_marker)
        assert body, (
            f"helper body span empty: {helper} -> {end_marker}"
        )
        # No lfsr to FSR1.
        assert "lfsr    0x1," not in body, (
            f"{helper} clobbers FSR1 via lfsr -- breaks the row walk's "
            f"POSTINC1 cursor across helper calls"
        )
        # No direct write to FSR1L / FSR1H or the FSR1 indirect-write
        # forms.  POSTINC1 / POSTDEC1 / PREINC1 are allowed as READ
        # operands; flag if used as a WRITE target (which would advance
        # the cursor unintentionally).
        for fsr_reg in ("FSR1L", "FSR1H", "POSTINC1", "POSTDEC1", "PREINC1"):
            written = re.search(
                rf"\b(?:movwf|clrf|setf|incf|incfsz|decf|decfsz|dcfsnz|"
                rf"infsnz|negf|comf|bsf|bcf|btg|"
                rf"iorwf|andwf|xorwf|addwf|addwfc|subwf|subwfb|subfwb|"
                rf"rlcf|rlncf|rrcf|rrncf|swapf)\s+{fsr_reg}\b",
                body,
            )
            assert not written, (
                f"{helper} writes to {fsr_reg} -- breaks the row walk's "
                f"FSR1 cursor across helper calls"
            )
