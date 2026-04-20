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


def test_menu_dispatch_inserts_diag_at_state_2() -> None:
    """The ``flow_post_connect_init_11F0`` dispatch must call
    ``v171_diag_screen`` for state == 2 and shift Input/Setup to 3/4.

    Spec menu order: Vol(0) ↔ Preset(1) ↔ Diagnostics(2) ↔ Input(3) ↔ Setup(4).
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    body_start = _label_offset(text, "flow_post_connect_init_11F0")
    assert body_start >= 0, "dispatch entry label missing"
    # Capture a generous body window through to the boot_handshake_wait
    # block (which holds the state == 4 / Setup branch).
    body_end = text.find("flow_boot_handshake_wait_120A:", body_start)
    body = text[body_start:body_end]
    assert re.search(r"rcall\s+v171_preset_screen", body), "state 1 → preset wiring"
    assert re.search(r"rcall\s+v171_diag_screen", body), "state 2 → diagnostics wiring"
    assert re.search(
        r"movlw\s+0x03[^\n]*\n\s*cpfseq\s+0xbf",
        body,
    ), "state 3 (Input) cpfseq literal"
    assert re.search(
        r"movlw\s+0x04[^\n]*\n\s*cpfseq\s+0xbf",
        body,
    ), "state 4 (Setup) cpfseq literal"


def test_nav_wrap_literals_bump_to_0x04() -> None:
    """DOWN upper bound, UP wrap target, AND Setup-state cpfseq literals
    must all be 0x04 after Layer 5.

    V1.61b had ring={Vol,Preset,Input,Setup} and both nav-wrap literals
    were 0x03; the Setup-state cpfseq was 0x02 (Input shifted to 1, Setup
    to 2 — wait, Setup was 3 in the V1.71 V1.61b layout per the
    pre-Layer-5 dispatch).  Layer 5 expands the ring with Diagnostics
    inserted at state 2, so the three literals all bump:

      - DOWN nav upper bound:        movlw 0x04 / cpfseq 0xbf
      - UP   nav wrap target:        movlw 0x04 / movwf  0xbf
      - Setup-state dispatch check:  movlw 0x04 / cpfseq 0xbf

    Three matches total = correct for Layer 5; two would indicate a
    nav-only edit that forgot to bump Setup.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    matches = re.findall(
        r"movlw\s+0x04[^\n]*\n\s*(?:movwf|cpfseq)\s+0xbf",
        text,
    )
    assert len(matches) == 3, (
        f"expected exactly three 0x04 nav/dispatch literals (UP wrap, "
        f"DOWN bound, Setup-state cpfseq); found {len(matches)}: {matches}"
    )


def test_diag_screen_label_exists_and_initializes_target() -> None:
    """``v171_diag_screen:`` must be a top-level label, and its first
    body block must initialize ``v171_diag_target`` from the present mask
    (target=0 on first entry so the very first cadence-driven query goes
    to PB1 per spec; toggle now happens on BF/27 reception (the LAST
    frame of the 7-frame burst), not in the cadence loop, so we don't
    pre-flip it any more)."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_screen")
    assert off >= 0, "v171_diag_screen label missing"
    # Window: from label through first ~700 chars covers the init block.
    head = text[off:off + 700]
    assert "v171_diag_present" in head, "first block must touch present mask"
    assert "bcf     v171_diag_target, 0, BANKED" in head, (
        "first-entry init must clear diag_target.0 so the first cadence "
        "query goes to PB1"
    )


def test_diag_screen_body_renders_compact_layout() -> None:
    """Both row drawers must emit the I/D/S/B/R/A/P banner letters in order.

    The encoding is 16 chars per row: '1'/'2', ':', then 7 letter+nib
    pairs.  The render uses lcd_char_write with literal letters, so the
    sequence is observable from the source.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_screen")
    body_end = _label_offset(text, "v171_diag_emit_letter")
    body = text[off:body_end]
    expected_letters_each_row = ["I", "D", "S", "B", "R", "A", "P"]
    # Each row should contain `movlw   'L'` followed by an emit_letter
    # call.  Scan once and count occurrences of each letter token.
    for letter in expected_letters_each_row:
        # Each banner letter appears twice: once in row 0 (PB1), once
        # in row 1 (PB2).
        count = len(re.findall(rf"movlw\s+'{letter}'", body))
        assert count >= 2, (
            f"banner letter '{letter}' must appear in both PB1 and PB2 "
            f"rows ({count} occurrences found)"
        )


def test_diag_screen_handles_na_for_never_seen_pb() -> None:
    """If a PB has never replied (present-mask bit clear), the row must
    render "n/a" + padding instead of the counter pairs.

    Spec: "If a PB does not support the new query, show n/a".
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_screen")
    body_end = _label_offset(text, "v171_diag_emit_letter")
    body = text[off:body_end]
    # Both PB1 and PB2 must have an n/a render path.
    assert re.search(r"v171_diag_pb1_render_na:", body), "PB1 n/a path missing"
    assert re.search(r"v171_diag_pb2_render_na:", body), "PB2 n/a path missing"
    # Each n/a path must emit 'n', '/', 'a'.
    for tag in ("pb1", "pb2"):
        seg_start = body.find(f"v171_diag_{tag}_render_na:")
        seg_end = body.find(f"v171_diag_{tag}_pad_loop:", seg_start)
        # Walk up to the loop label and into the loop body
        seg_loop_end = body.find("v171_diag_", seg_end + 25)
        seg = body[seg_start:seg_loop_end if seg_loop_end > 0 else len(body)]
        for ch in ("'n'", "'/'", "'a'"):
            assert ch in seg, f"{tag} n/a render missing {ch}"


def test_diag_send_query_uses_b1_or_b2_route_and_cmd_21() -> None:
    """``v171_diag_send_query`` enqueues 3 bytes: route (0xB1 or 0xB2),
    cmd 0x21, data 0x00.  Route alternates based on diag_target bit 0."""
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_send_query")
    assert off >= 0, "v171_diag_send_query label missing"
    # Anchor body to next top-level label so growing the routine's
    # in-line documentation doesn't truncate the body window.
    body = _label_body(text, "v171_diag_send_query", "control_core_service_0F54")
    assert re.search(r"movlw\s+0xB1", body), "PB1 route literal missing"
    assert re.search(r"movlw\s+0xB2", body), "PB2 route literal missing"
    assert re.search(r"movlw\s+0x21", body), "cmd 0x21 literal missing"
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
    # added for Tier-1 (RESET LAST frame on BF/2B).  6 KB covers the
    # full handler body including comments.
    body = text[off:off + 6000]
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
    """All new code labels must resolve from the gpasm listing."""
    _, syms = v171_hex
    expected_labels = (
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
        "v171_diag_pb1_render_na",
        "v171_diag_pb2_render_na",
    )
    missing = [name for name in expected_labels if name not in syms]
    assert not missing, f"unresolved Layer 5 labels: {missing}"


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
    body = text[off:off + 4000]
    # Locate the cache write (movff rx_parsed_data, INDF0) and the
    # BF/27 gate (cpfseq with W=0x06).  bsf DIRTY must sit between them.
    write_pos = body.find("movff   rx_parsed_data, INDF0")
    gate_pos = body.find("cpfseq  (Common_RAM + 4), A")
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
    PENDING; if still set when the next cadence fires, advance target
    BEFORE sending so the responding PB gets re-queried.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_diag_loop")
    assert off >= 0
    # Window through the cadence-expired path (~600 chars covers it).
    body = text[off:off + 1600]
    # btfss on PENDING + bra to skip the toggle: when PENDING is SET
    # (silent), don't skip → btg target.
    assert re.search(
        r"btfss\s+v171_diag_flags,\s*V171_DIAG_FLAG_PENDING,\s*BANKED",
        body,
    ), "silent-PB gate must check PENDING before sending"
    assert re.search(
        r"btg\s+v171_diag_target,\s*0,\s*BANKED",
        body,
    ), "silent-PB gate must toggle target when PENDING is still set"
    # The cadence path must SET PENDING after sending so the next
    # cadence can detect a no-reply.
    assert re.search(
        r"bsf\s+v171_diag_flags,\s*V171_DIAG_FLAG_PENDING,\s*BANKED",
        body,
    ), "cadence path must set PENDING when issuing a query"


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
    body = text[off:off + 4000]
    # RUNTIME_PENDING clear must be inside the col_offset == 6 (BF/27) path.
    gate_pos = body.find("cpfseq  (Common_RAM + 4), A")
    assert gate_pos >= 0
    after_gate = body[gate_pos:gate_pos + 1000]
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
    """Coverage for F2 round 2 (2026-04-19): on TX-ring saturation,
    v171_diag_send_query must CLEAR the PENDING flag before returning.
    Otherwise the next cadence expiry sees PENDING-still-set and
    advances target — falsely classifying local TX-ring saturation as
    remote PB silence and round-robin'ing past the original target.
    Clearing PENDING on abort makes the next cadence retry the SAME
    target, which is what the "whole-frame retry" comment claims.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    abort_body = _label_body(
        text, "v171_diag_send_query_aborted", "control_core_service_0F54"
    )
    assert abort_body, "abort label missing"
    end_ret = abort_body.find("return")
    assert end_ret > 0, "abort path missing return"
    abort_body = abort_body[:end_ret + 20]
    # The abort path must clear PENDING.
    assert re.search(
        r"bcf\s+v171_diag_flags,\s*V171_DIAG_FLAG_PENDING,\s*BANKED",
        abort_body,
    ), (
        "abort path must clear PENDING — otherwise local TX-ring "
        "saturation gets misclassified as remote PB silence by the "
        "cadence loop's PENDING-still-set gate"
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

    This test pins the design decision: the renderer must gate solely
    on ``v171_diag_present`` (one bit per PB, set on first BF/27
    reception) — no separate ``v171_diag_topology`` symbol, no `--`
    literal in the render path, and no second sentinel render block.
    A future change that re-introduces topology detection would also
    have to update this test, which forces the spec-section update.
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
    render_body = _label_body(text, "v171_diag_screen", "v171_diag_emit_letter")
    assert "'-'" not in render_body, (
        "no '-' character literal in render path — spec collapse "
        "uses 'n/a' for both topology-absent and silent-PB cases"
    )
    # Both PB rows must gate on the same v171_diag_present bit pattern.
    # PB1 row gates on bit 0; PB2 row gates on bit 1.
    assert re.search(
        r"btfss\s+v171_diag_present,\s*0,\s*BANKED",
        render_body,
    ), "PB1 row must gate on v171_diag_present bit 0"
    assert re.search(
        r"btfss\s+v171_diag_present,\s*1,\s*BANKED",
        render_body,
    ), "PB2 row must gate on v171_diag_present bit 1"


def test_diag_renderer_na_path_count_matches_pb_count() -> None:
    """Each PB row has exactly ONE sentinel-render path
    (``v171_diag_pbN_render_na``), not two (per the original spec's
    `--` vs `n/a` distinction).  Adding a second per-PB sentinel
    block would re-introduce the topology-vs-silence distinction the
    2026-04-19 revision retired.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    pb1_na = re.findall(r"^v171_diag_pb1_render_\w+:", text, re.MULTILINE)
    pb2_na = re.findall(r"^v171_diag_pb2_render_\w+:", text, re.MULTILINE)
    assert pb1_na == ["v171_diag_pb1_render_na:"], (
        f"PB1 must have exactly one sentinel render path; got {pb1_na}"
    )
    assert pb2_na == ["v171_diag_pb2_render_na:"], (
        f"PB2 must have exactly one sentinel render path; got {pb2_na}"
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
