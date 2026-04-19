"""V1.71 Layer 5 Phase B: CONTROL diagnostics page.

Adds the "Diagnostics" top-level menu page (state 2 in the new
Vol/Preset/Diagnostics/Input/Setup ring) per
``docs/V163B_DIAGNOSTICS_MENU_SPEC.md``:

* RAM cache for per-PB packed counter bytes (BANK 1, 0x80..0x8B)
* ``v171_diag_screen`` page body that renders the spec layout
* ``v171_diag_send_query`` raw 3-byte enqueue (route / 0x21 / 0x00)
* ``v171_bf2x_case_check`` parser case for BF/21..24 replies
* ``v171_diag_emit_nib_w`` nibble-to-LCD-char encoder
* Menu dispatch: state 2 → diag, state 3 → Input, state 4 → Setup
* Nav wrap upper bound bumped from 0x03 to 0x04

Three tiers, mirroring the Layer 1 / Layer 2 / Phase A test layout:

* **Tier A — source-level structural**: pin RAM EQUs, label locations,
  menu dispatch wiring, nav-wrap literals, parser-case insertion.

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

# 7-byte cache layout (one cell per counter — replaces the earlier
# 4-byte packed layout that had data >= 0x80 on chain).
V171_DIAG_PB1_I_EQU = 0x080
V171_DIAG_PB1_D_EQU = 0x081
V171_DIAG_PB1_S_EQU = 0x082
V171_DIAG_PB1_B_EQU = 0x083
V171_DIAG_PB1_R_EQU = 0x084
V171_DIAG_PB1_A_EQU = 0x085
V171_DIAG_PB1_P_EQU = 0x086
V171_DIAG_PB2_I_EQU = 0x087
V171_DIAG_PB2_D_EQU = 0x088
V171_DIAG_PB2_S_EQU = 0x089
V171_DIAG_PB2_B_EQU = 0x08A
V171_DIAG_PB2_R_EQU = 0x08B
V171_DIAG_PB2_A_EQU = 0x08C
V171_DIAG_PB2_P_EQU = 0x08D
V171_DIAG_TARGET_EQU = 0x08E
V171_DIAG_PRESENT_EQU = 0x08F
V171_DIAG_POLL_LO_EQU = 0x090
V171_DIAG_POLL_HI_EQU = 0x091

# Physical addresses for gpsim CLI reads (BSR=1 << 8 | offset).
V171_DIAG_PB1_I_PHYS = 0x180
V171_DIAG_PB2_I_PHYS = 0x187
V171_DIAG_TARGET_PHYS = 0x18E
V171_DIAG_PRESENT_PHYS = 0x18F

ALL_DIAG_CACHE_EQUS = (
    ("v171_diag_pb1_i", V171_DIAG_PB1_I_EQU),
    ("v171_diag_pb1_d", V171_DIAG_PB1_D_EQU),
    ("v171_diag_pb1_s", V171_DIAG_PB1_S_EQU),
    ("v171_diag_pb1_b", V171_DIAG_PB1_B_EQU),
    ("v171_diag_pb1_r", V171_DIAG_PB1_R_EQU),
    ("v171_diag_pb1_a", V171_DIAG_PB1_A_EQU),
    ("v171_diag_pb1_p", V171_DIAG_PB1_P_EQU),
    ("v171_diag_pb2_i", V171_DIAG_PB2_I_EQU),
    ("v171_diag_pb2_d", V171_DIAG_PB2_D_EQU),
    ("v171_diag_pb2_s", V171_DIAG_PB2_S_EQU),
    ("v171_diag_pb2_b", V171_DIAG_PB2_B_EQU),
    ("v171_diag_pb2_r", V171_DIAG_PB2_R_EQU),
    ("v171_diag_pb2_a", V171_DIAG_PB2_A_EQU),
    ("v171_diag_pb2_p", V171_DIAG_PB2_P_EQU),
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
    m = re.search(
        rf"^\s*{re.escape(name)}\s+(?:EQU|equ)\s+(0x[0-9A-Fa-f]+)\s*",
        text,
        re.MULTILINE,
    )
    return int(m.group(1), 16) if m else None


def _label_offset(text: str, label: str) -> int:
    """Return character offset of ``label:`` definition in the source.

    Differs from ``text.find(label + ':')`` in that we anchor to the
    start-of-line so that doc comments mentioning the label don't
    confuse the test.
    """
    m = re.search(rf"^{re.escape(label)}:", text, re.MULTILINE)
    return m.start() if m else -1


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
    to PB1 per spec; toggle now happens on BF/24 reception, not in the
    cadence loop, so we don't pre-flip it any more)."""
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
    body = text[off:off + 1500]
    assert re.search(r"movlw\s+0xB1", body), "PB1 route literal missing"
    assert re.search(r"movlw\s+0xB2", body), "PB2 route literal missing"
    assert re.search(r"movlw\s+0x21", body), "cmd 0x21 literal missing"
    # Three tx_byte_enqueue invocations (route, cmd, data).
    enqueue_calls = re.findall(r"call\s+tx_byte_enqueue", body)
    assert len(enqueue_calls) == 3, (
        f"expected 3 tx_byte_enqueue calls (route/cmd/data); found "
        f"{len(enqueue_calls)}: {enqueue_calls}"
    )


def test_bf2x_parser_case_handles_cmds_21_through_27() -> None:
    """Parser must recognize cmd 0x21..0x27 from BF replies and write
    the payload into the diag cache slot indexed by the in-flight target.

    Cmd codes outside 0x21..0x27 (0x20, 0x28+) must NOT trigger a write.
    The 7-frame protocol replaces the original 4-frame packed scheme
    so each data byte stays < 0x80 (chain-forwarder safe).
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    off = _label_offset(text, "v171_bf2x_case_check")
    assert off >= 0, "v171_bf2x_case_check label missing"
    body = text[off:off + 4000]
    # Range gate: must reject < 0x21 and >= 0x28.
    assert re.search(r"movlw\s+0x21\s*\n\s*cpfslt\s+rx_parsed_cmd", body), (
        "lower-bound check (cmd < 0x21 → exit) missing"
    )
    assert re.search(r"movlw\s+0x28\s*\n\s*cpfslt\s+rx_parsed_cmd", body), (
        "upper-bound check (cmd < 0x28 → ok) missing"
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
    # Target-toggle on BF/27 (last frame, col_offset == 6) — fixes the
    # cadence-vs-reply race in the wire-chain.
    assert re.search(r"btg\s+v171_diag_target", body), (
        "target toggle on BF/27 missing"
    )
    assert re.search(r"movlw\s+0x06\s*\n\s*cpfseq\s+\(Common_RAM \+ 4\)", body), (
        "deferred-update gate (col_offset == 6) missing"
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
