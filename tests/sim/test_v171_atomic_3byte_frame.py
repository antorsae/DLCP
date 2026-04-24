"""V1.71 atomic 3-byte frame guard (closes silent-drop partial-frame hazard).

Pins the ``tx_ring_reserve_3`` helper + the 4 wrapped 3-byte senders
(``v171_send_wake_cmd_frame``, ``v171_send_standby_cmd_frame``,
``serial_tx_routed_frame``, ``poll_frame_send``) + the Layer B retry
at ``flow_reconnect_wait_loop_12CE``.

Motivation (see docs/V32_MAIN_HANG_HARDENING_PLAN.md §3b for operator-
visible symptom):

Before the fix, the 3-byte senders enqueued bytes one at a time and
checked ``STATUS.C`` per byte.  If byte 1 committed but byte 2 or 3
saturated on the TX ring (e.g. while ``ir_rc5_decode`` blocked the
TX ISR for ~7-10 ms), the caller saw an abort but the partial route
byte was already on the wire.  MAIN's parser either time-limited out
via ``main_service_rx_frame_gap`` or — worst case — fused the next
unrelated TX byte as the standby/wake data, flipping chain state the
opposite of what the operator requested.

The fix makes each 3-byte frame atomic via a pre-enqueue reservation:
``tx_ring_reserve_3`` probes the ring for >=3 free slots BEFORE any
``tx_byte_enqueue`` runs.  Either the caller gets all 3 slots or
STATUS.C=1 with zero bytes touched.  Because the main loop is the
only producer and the TX ISR only drains, ring room can only grow
between the reserve check and the 3 back-to-back enqueues — the
atomicity guarantee holds without locking.

Tier A here is the source-shape guard; Tier B exercises the actual
assembled bytes.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
from intelhex import IntelHex

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM
from dlcp_fw.sim.v17_symbols import assemble_v17, parse_v17_symbols


# ---------------------------------------------------------------------------
# Tier A: source-shape guards
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_source() -> str:
    return V171_CONTROL_ASM.read_text()


def test_tx_ring_reserve_3_label_exists(v171_source: str) -> None:
    assert re.search(r"^tx_ring_reserve_3:\s*$", v171_source, re.MULTILINE), (
        "tx_ring_reserve_3 label must be defined; it's the Layer A entry point."
    )


def _slice_fn_body(source: str, start_label: str, next_top_label: str) -> str:
    """Return the text between ``start_label:`` and ``next_top_label:``
    (exclusive on the latter).  ``next_top_label`` is the next adjacent
    top-level label that definitively ends the routine we care about —
    passed in because regex-based "next unindented label" breaks on
    multi-label routines like tx_ring_reserve_3 (which has internal
    `_saturated:` and `_sat_done:` labels).

    Label lines may have trailing ``; address: 0x....`` comments, so we
    match the whole label line permissively."""
    m = re.search(
        rf"^{re.escape(start_label)}:[^\n]*\n(.*?)^{re.escape(next_top_label)}:",
        source,
        re.DOTALL | re.MULTILINE,
    )
    assert m is not None, (
        f"could not slice body between {start_label!r} and {next_top_label!r}"
    )
    return m.group(1)


def test_tx_ring_reserve_3_body_has_occupancy_compute(v171_source: str) -> None:
    """Body must compute occupancy from (wr - rd) with the wrap-correction
    add of 0x30 (48) when subwf borrowed, then add 0x03 for the 3-byte
    capacity probe."""
    body = _slice_fn_body(v171_source, "tx_ring_reserve_3", "tx_byte_enqueue")
    assert "subwf   tx_ring_wr, W, B" in body, "missing wr-rd compute"
    assert "addlw   0x30" in body, "missing wrap-correction add (48)"
    assert "addlw   0x03" in body, "missing 3-slot capacity probe"
    assert "cpfslt  v171_tx_enq_retry" in body, "missing capacity compare"


def test_tx_ring_reserve_3_has_saturating_clamp(v171_source: str) -> None:
    """The saturated path must bump v171_tx_saturate_count with the
    incfsz/bra/setf clamp pattern (matches tx_byte_enqueue's idiom so
    Layer 5 diagnostics observe frame-drops and byte-drops through the
    same counter)."""
    body = _slice_fn_body(v171_source, "tx_ring_reserve_3", "tx_byte_enqueue")
    assert "tx_ring_reserve_3_saturated:" in body, (
        "missing `tx_ring_reserve_3_saturated:` internal label"
    )
    assert "incfsz  v171_tx_saturate_count, F, BANKED" in body
    assert "setf    v171_tx_saturate_count, BANKED" in body, (
        "missing saturating clamp at 0xFF"
    )
    assert "bsf     STATUS, C, A" in body, "saturated path must set C=1"


_SENDERS = [
    # STDBY/WAKE — the frames that the user-visible wedge was traced to.
    "v171_send_wake_cmd_frame",
    "v171_send_standby_cmd_frame",
    # Generic chain-link frame emitters (used by mute_frame_send and
    # standby_wake_broadcast at full_sync_burst step 5 / menu transitions).
    "serial_tx_routed_frame",
    # Status poll used by the WAITING reconnect loops.
    "poll_frame_send",
    # full_sync_burst periodic state broadcasters (steps 1, 2, 4, 6) — not
    # involved in the STDBY/WAKE path per se, but share the same partial-
    # frame hazard.  Wrapping them uniformly eliminates the class.
    "input_frame_send",
    "volume_frame_send",
    "cmd1d_setting_frame_send",
    "v171_send_preset_frame_txonly",
]


@pytest.mark.parametrize("sender", _SENDERS)
def test_sender_starts_with_atomic_reserve(v171_source: str, sender: str) -> None:
    """Every 3-byte sender must begin with a call/rcall to
    tx_ring_reserve_3 followed immediately by `bc <sender>_aborted`.
    This is the atomicity guarantee — no partial frames."""
    # Label line may have a trailing `; address: 0x....` comment.  Allow
    # comment / blank lines between label and first instruction.  The
    # first real instruction must be the atomic-reserve prologue —
    # either `rcall tx_ring_reserve_3` (in-range callers) or
    # `call tx_ring_reserve_3, 0x0` (far callers) — immediately followed
    # by `bc <sender>_aborted`.
    pattern = (
        rf"^{sender}:[^\n]*\n"
        rf"(?:\s*(?:;[^\n]*)?\n)*"   # allow comment lines / blank lines
        rf"\s+(?:rcall|call)\s+tx_ring_reserve_3(?:,\s*0x0)?\s*\n"
        rf"\s+bc\s+{sender}_aborted\s*\n"
    )
    assert re.search(pattern, v171_source, re.MULTILINE), (
        f"{sender} must start with `(r)call tx_ring_reserve_3` + "
        f"`bc {sender}_aborted` (atomic reserve prologue)."
    )


@pytest.mark.parametrize("sender", _SENDERS)
def test_sender_has_no_inner_bc_abort(v171_source: str, sender: str) -> None:
    """After the atomic reserve, the 3 `tx_byte_enqueue` calls are
    guaranteed to succeed.  The old per-byte `bc <sender>_aborted`
    checks are dead code; they must be removed so a future reader
    doesn't think partial-frame abort is still possible."""
    body = _slice_fn_body(v171_source, sender, f"{sender}_aborted")

    # Exactly one `bc <sender>_aborted` remains - the prologue check.
    # Anything > 1 means an old per-byte check slipped through.
    aborts = re.findall(rf"\bbc\s+{sender}_aborted\b", body)
    assert len(aborts) == 1, (
        f"{sender}: expected exactly 1 `bc {sender}_aborted` (the atomic "
        f"prologue), found {len(aborts)}. "
        f"Per-byte aborts are dead code after the reserve."
    )


def test_layer_b_retry_at_reconnect_wait_done(v171_source: str) -> None:
    """Layer B: the wake broadcast at flow_reconnect_wait_loop_12CE
    must retry the whole reconnect cycle on saturation.  This closes
    the V162B_RECONNECT_WAKE_BUG gap when the second wake emit drops
    — without this, MAIN gates can stay closed after the reconnect
    completes and the next user commands silently fail until the
    full_sync_burst step-5 cycle re-emits (~480 ms later)."""
    body = _slice_fn_body(
        v171_source,
        "flow_reconnect_wait_loop_12CE",
        "flow_reconnect_wait_loop_12CE_delivered",
    )
    assert "call    standby_wake_broadcast" in body, (
        "the standby_wake_broadcast emit at reconnect-done must remain."
    )
    # bnc jump to the _delivered label (success fast-path) + unconditional
    # bra back into reconnect_wait_loop on saturation.
    assert re.search(
        r"bnc\s+flow_reconnect_wait_loop_12CE_delivered\s*\n\s*bra\s+reconnect_wait_loop",
        body,
    ), (
        "Layer B retry: expected `bnc _delivered / bra reconnect_wait_loop` "
        "pattern after the wake broadcast call."
    )


# ---------------------------------------------------------------------------
# Tier B: assembled-hex guards
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def v171_assembled(tmp_path_factory: pytest.TempPathFactory):
    """Per-worker assembled V1.71 build (xdist-safe; does not touch
    the canonical release hex at V171_CONTROL_HEX)."""
    tmp = tmp_path_factory.mktemp("v171_atomic_3byte")
    (tmp / V17_CONTROL_RAM_INC.name).write_bytes(V17_CONTROL_RAM_INC.read_bytes())
    asm = tmp / V171_CONTROL_ASM.name
    asm.write_bytes(V171_CONTROL_ASM.read_bytes())
    hex_out = tmp / "dlcp_control_v171.hex"
    lst_out = tmp / "dlcp_control_v171.lst"
    assemble_v17(asm, hex_out, output_lst=lst_out, pad_program_flash=False)
    syms = parse_v17_symbols(lst_out)
    ih = IntelHex(str(hex_out))
    return syms, ih


def test_tx_ring_reserve_3_assembles(v171_assembled) -> None:
    syms, _ = v171_assembled
    assert "tx_ring_reserve_3" in syms, (
        "tx_ring_reserve_3 symbol missing from assembled listing."
    )
    addr = syms["tx_ring_reserve_3"]
    # helper lives in the low-address cluster near tx_byte_enqueue
    assert 0x0400 <= addr < 0x0A00, (
        f"tx_ring_reserve_3 at unexpected address 0x{addr:04X}; "
        f"Layer B senders use rcall which requires <= 1024-word range."
    )


_RCALL_SENDERS = (
    "serial_tx_routed_frame",
    "poll_frame_send",
    "input_frame_send",
    "volume_frame_send",
    "cmd1d_setting_frame_send",
)


def test_rcall_senders_in_range_of_reserve_3(v171_assembled) -> None:
    """The closer senders use `rcall tx_ring_reserve_3` for size savings
    (2-byte encoding vs. 4-byte `call`).  If a future layout change
    pushes any of them outside ±1024 words, gpasm will error — but this
    test gives a clear semantic failure before the assemble step."""
    syms, _ = v171_assembled
    tgt = syms["tx_ring_reserve_3"]
    for sender in _RCALL_SENDERS:
        src = syms[sender]
        disp = (tgt - (src + 2)) // 2   # +2: pc after rcall opcode; //2: word addresses
        assert -1024 <= disp <= 1023, (
            f"{sender} at 0x{src:04X} can no longer rcall tx_ring_reserve_3 "
            f"at 0x{tgt:04X} (displacement {disp}); switch to `call` or "
            f"move the helper."
        )


def test_release_metadata_rev_present(v171_assembled) -> None:
    """``scripts/build_v171_release.py`` bumps
    ``control_release_metadata[11]`` on every canonical build.  The
    per-worker fixture hex uses whatever byte was in the source at
    test-run time; assert it's a plausible monotonic value (non-zero,
    not 0xFF sentinel).  Pinning an exact value would make the test
    flap every release bump."""
    syms, ih = v171_assembled
    base = syms["control_release_metadata"]
    rev_byte = ih[base + 11]
    assert 0x01 <= rev_byte <= 0xFE, (
        f"release rev byte at 0x{base + 11:04X} is 0x{rev_byte:02X}; "
        f"0x00 and 0xFF are reserved sentinels — did the release "
        f"ceremony misfire?"
    )
