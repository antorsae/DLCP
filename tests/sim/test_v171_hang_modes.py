"""V1.71 CONTROL hang-mode regression tests (per codex shipping-confidence brainstorm).

Three classes, all motivated by the codex review (HEAD ~46b19d0...46dae4f):

  1. Layer-1-bounded `tx_byte_enqueue` changed the failure mode of TX
     ring saturation from "hard hang" to "silent drop".  Most callers
     don't check STATUS.C, so a dropped byte breaks the wire frame
     but CONTROL keeps moving as if everything was sent.

  2. The 48-byte RX software ring at `rx_ring_base` (0x066..0x095)
     has no unread-data guard.  An RX storm while the main loop is in
     a slow path (LCD repaint, EEPROM write, IR decode) can wrap the
     ring before the parser drains it, overwriting in-flight route /
     cmd / data bytes.

  3. The parser has no frame-gap timeout.  A single dropped or
     corrupted byte mid-frame leaves `rx_frame_position` stuck non-
     zero until a future Bx route byte happens to arrive AND the
     parser's modulo state happens to align.

Test tiers:
  * Tier A (structural) -- audit V1.71 source for the contract each
    hang class violates; xfail with rationale when the contract is
    knowingly incomplete (e.g. unchecked enqueue callers exist).
  * Tier C (behavioral via gpsim) -- reserved for follow-up commits.

This file is intentionally light on Tier C right now: the structural
audit alone closes the most ROI-valuable gap (TX-failure
propagation) by enumerating every unchecked call site.  Future
commits that fix each unchecked caller can use this audit as the
gate.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List, Tuple

import pytest

from dlcp_fw.paths import V171_CONTROL_ASM


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_v171_source() -> str:
    return V171_CONTROL_ASM.read_text(encoding="utf-8")


def _enumerate_tx_enqueue_call_sites(text: str) -> List[Tuple[int, str]]:
    """Return [(1-indexed line number, raw line)] for every `call/rcall
    tx_byte_enqueue` site in the V1.71 source."""
    out: List[Tuple[int, str]] = []
    for n, line in enumerate(text.splitlines(), start=1):
        if re.search(r"\b(call|rcall)\s+tx_byte_enqueue\b", line):
            out.append((n, line.rstrip()))
    return out


def _next_instruction_lines(
    text_lines: List[str], start_idx: int, max_lookahead: int = 4
) -> List[Tuple[int, str]]:
    """Yield up to `max_lookahead` lines after start_idx (exclusive)
    that look like asm instructions (skip blank / comment-only / label
    lines).  Returns (1-indexed line number, raw line)."""
    out: List[Tuple[int, str]] = []
    n = start_idx + 1
    while n < len(text_lines) and len(out) < max_lookahead:
        raw = text_lines[n]
        stripped = raw.strip()
        if not stripped:
            n += 1
            continue
        if stripped.startswith(";"):
            n += 1
            continue
        # Label-only line (ends with ':' and no instruction follows)
        if stripped.endswith(":") and " " not in stripped[:-1]:
            n += 1
            continue
        out.append((n + 1, raw.rstrip()))  # n is 0-indexed; report 1-indexed
        n += 1
    return out


def _next_line_is_bc(
    text_lines: List[str], call_line_idx: int
) -> bool:
    """True if the immediately-following instruction (skipping blank /
    comment / label-only lines) is a `bc <label>` -- i.e. the caller
    branches on STATUS.C set by the just-completed tx_byte_enqueue.

    `bc` is the PIC18 "branch if carry" mnemonic; our Layer 1 contract
    is that tx_byte_enqueue returns C=1 on saturation, so a bc check
    immediately after the call is the documented "frame-atomic abort"
    pattern (see v171_diag_send_query_w in dlcp_control_v171.asm).

    Match is case-insensitive because gpasm itself is case-insensitive
    on mnemonics; if a future contributor writes `BC` it still
    qualifies as a check (codex LOW review against 47a2db3)."""
    nxt = _next_instruction_lines(text_lines, call_line_idx, max_lookahead=1)
    if not nxt:
        return False
    _, raw = nxt[0]
    return bool(re.search(r"^\s*bc\s+\w", raw, re.IGNORECASE))


def _categorize_call_sites(text: str) -> Tuple[List[Tuple[int, str]], List[Tuple[int, str]]]:
    """Return (checked, unchecked) lists.  Checked = next instruction
    is `bc <label>`.  Unchecked = anything else (next byte-enqueue,
    return, fall-through to caller, etc.)."""
    lines = text.splitlines()
    checked: List[Tuple[int, str]] = []
    unchecked: List[Tuple[int, str]] = []
    for line_no, raw in _enumerate_tx_enqueue_call_sites(text):
        # _next_instruction_lines uses 0-indexed start; line_no is 1-indexed.
        if _next_line_is_bc(lines, call_line_idx=line_no - 1):
            checked.append((line_no, raw))
        else:
            unchecked.append((line_no, raw))
    return checked, unchecked


# ---------------------------------------------------------------------------
# Hang class 1: TX enqueue failure propagation (codex top ROI)
# ---------------------------------------------------------------------------


def test_v171_serial_tx_routed_frame_propagates_enqueue_failure() -> None:
    """SHIPPING-CONFIDENCE GATE: every `call tx_byte_enqueue` should
    immediately check STATUS.C via `bc <abort-label>` so a TX-ring
    saturation-induced byte drop doesn't silently break the wire frame
    while CONTROL marches on.

    Background: V1.71 Layer 1 changed `tx_byte_enqueue` from a
    hard-hang busy-wait (BUG C6) into a bounded retry that returns
    C=1 on saturation.  The diagnostics path (v171_diag_send_query_w)
    correctly checks C after every byte and aborts the frame on the
    first dropped byte.  Most other callers still treat tx_byte_enqueue
    as if it always succeeds -- so a saturated TX ring under stress
    produces a half-formed frame on the wire AND state on CONTROL
    that thinks the frame was sent.

    This test enumerates every call site and reports which ones still
    don't check.  Currently most are unchecked -- the test is xfailed
    with the list of unchecked locations so a future fix campaign can
    use it as a checklist.

    Once every caller is converted to check + abort, flip this from
    xfail to pass-required so a future regression that introduces a
    new unchecked caller fails immediately.
    """
    text = _read_v171_source()
    checked, unchecked = _categorize_call_sites(text)
    assert checked, "no checked tx_byte_enqueue callers found at all -- did the diag-query helper get removed?"

    if unchecked:
        # Format the unchecked list for the xfail message so the
        # operator / fix-campaign-author has the line numbers handy.
        listing = "\n".join(
            f"    line {n:>5}: {line.lstrip()}"
            for n, line in unchecked[:20]
        )
        more = ""
        if len(unchecked) > 20:
            more = f"\n    ... and {len(unchecked) - 20} more sites"
        pytest.xfail(
            f"V1.71 has {len(unchecked)} unchecked tx_byte_enqueue call sites "
            f"(out of {len(checked) + len(unchecked)} total).  Each one is a "
            f"silent-drop hazard under TX-ring saturation:\n"
            f"{listing}{more}\n"
            f"Fix shape per codex shipping-confidence review: each caller "
            f"that emits a multi-byte routed frame should read STATUS.C "
            f"after every `call tx_byte_enqueue` and bra to a per-call-"
            f"site abort label that resets any state the partial frame "
            f"committed (e.g. clear v171_full_sync_step before bumping)."
        )
    # If no unchecked -- contract is fully satisfied; pass.


def test_v171_diag_query_helper_is_a_reference_implementation_of_check_pattern() -> None:
    """Pin the diagnostics path as the reference implementation that
    every other multi-byte tx_byte_enqueue caller should match.

    Specifically: v171_diag_send_query_w issues 3 byte enqueues, each
    one followed by `bc v171_diag_send_query_aborted`.  The abort
    label resets the flag bits (RUNTIME_PENDING / RESET_PENDING) so
    the next cadence retries the SAME target instead of mis-classifying
    local TX saturation as remote-PB silence.

    Future fix-campaign work that converts other callers should use
    this routine as the structural template.
    """
    text = _read_v171_source()
    helper_idx = text.find("v171_diag_send_query_w:")
    assert helper_idx >= 0, "diag-query helper missing -- the reference implementation is gone"
    helper_end = text.find("\n; ---", helper_idx + 1)
    if helper_end < 0:
        helper_end = helper_idx + 4000
    body = text[helper_idx:helper_end]
    # ADJACENCY check (codex LOW fix vs 47a2db3): counting `bc`
    # occurrences in the body would pass even if a future regression
    # MOVED a bc away from its call (e.g. delayed it past an
    # intervening movlb).  The contract is that EACH `call
    # tx_byte_enqueue` is IMMEDIATELY followed by `bc
    # v171_diag_send_query_aborted` (no instructions between).
    helper_lines = body.splitlines()
    base_lineno = text[:helper_idx].count("\n") + 1
    enqueue_call_indices: List[int] = [
        i for i, line in enumerate(helper_lines)
        if re.search(r"\bcall\s+tx_byte_enqueue\b", line)
    ]
    assert len(enqueue_call_indices) == 3, (
        f"diag-query helper should issue exactly 3 byte enqueues "
        f"(route + cmd + data); found {len(enqueue_call_indices)}"
    )
    # ALL_LINES variant: also gives us access for the adjacency check
    # against the in-source line numbers when failing.
    full_lines = text.splitlines()
    for body_idx in enqueue_call_indices:
        # The full-source line index for this call.
        src_idx = base_lineno - 1 + body_idx
        # The next instruction (skipping blank / comment / label) MUST
        # be `bc v171_diag_send_query_aborted`.
        nxt = _next_instruction_lines(full_lines, src_idx, max_lookahead=1)
        assert nxt, (
            f"diag-query helper call at line {src_idx + 1} has no "
            f"following instruction at all -- can't be checked"
        )
        nxt_line_no, nxt_raw = nxt[0]
        assert re.search(
            r"^\s*bc\s+v171_diag_send_query_aborted\b",
            nxt_raw,
            re.IGNORECASE,
        ), (
            f"diag-query helper call at line {src_idx + 1} is NOT "
            f"immediately followed by `bc v171_diag_send_query_aborted` "
            f"-- next instruction at line {nxt_line_no} was: {nxt_raw!r}.  "
            f"The codex LOW fix vs 47a2db3 requires per-call adjacency, "
            f"not just three bc tokens anywhere in the body, so a "
            f"refactor that moves a bc away from its call fails fast."
        )
    # Abort label must exist as a real return target.
    assert "v171_diag_send_query_aborted:" in text, (
        "abort label missing -- the bc checks would land on a non-existent label"
    )


# ---------------------------------------------------------------------------
# Hang class 2: RX ring overrun guard
# ---------------------------------------------------------------------------


def test_v171_rx_ring_isr_path_has_no_unread_data_guard() -> None:
    """SHIPPING-CONFIDENCE GATE: the V1.71 RX ISR writes every RCREG
    byte into rx_ring_base[rx_ring_wr] and wraps at 48 bytes WITHOUT
    checking whether the parser has drained the byte at that position.
    Under sustained chain traffic (Diagnostics page cadence + BF/08 +
    BF/2N replies) the producer can outpace the consumer, overwriting
    in-flight route / cmd / data bytes.

    Anchor: the RX ISR writes via the canonical instruction sequence
    `movff RCREG, PLUSW0` (immediately preceded by `lfsr 0x0, 0x066`,
    the rx_ring_base load).  This is unique to the RX ISR producer
    path -- nothing else in the source touches RCREG via PLUSW0.
    Codex MEDIUM fix vs 47a2db3: the prior anchor on a comment string
    that doesn't exist in the source landed the search window on the
    OERR recovery reset, not the actual ISR write path.

    Look in a window of ~30 lines around the producer site for any
    cpfsgt / cpfslt / xorwf / subwf comparison against rx_ring_rd
    (the canonical "would-this-write-stomp-an-unread-byte" guard
    shape).  Direction is symmetric (before OR after) because a fix
    could insert the guard either pre-write (drop on conflict) or
    post-write (rollback on conflict).
    """
    text = _read_v171_source()
    lines = text.splitlines()
    # Find the unique RX ISR producer signature.
    rx_isr_line = None
    for i, line in enumerate(lines):
        if re.search(r"\bmovff\s+RCREG,\s*PLUSW0\b", line):
            rx_isr_line = i
            break
    assert rx_isr_line is not None, (
        "RX ISR producer signature `movff RCREG, PLUSW0` not found -- "
        "either the ISR write path was renamed/refactored or the test "
        "anchor needs updating"
    )

    # Window: 15 lines before + 15 lines after the producer write.
    window_start = max(0, rx_isr_line - 15)
    window_end = min(len(lines), rx_isr_line + 16)
    isr_window = "\n".join(lines[window_start:window_end])
    # The guard can also reference rx_ring_rd by raw address (0x098).
    has_guard = bool(
        re.search(r"cpf(seq|sgt|slt)\s+(rx_ring_rd|0x98)", isr_window)
        or re.search(r"xorwf\s+(rx_ring_rd|0x98)", isr_window)
        or re.search(r"subwf\s+(rx_ring_rd|0x98)", isr_window)
    )
    if not has_guard:
        pytest.xfail(
            f"V1.71 RX ISR (producer at line {rx_isr_line + 1}) has NO "
            f"unread-data guard before writing rx_ring_base[rx_ring_wr]. "
            f"Producer can wrap the 48-byte ring before the consumer "
            f"drains, overwriting in-flight frame bytes.  Codex shipping-"
            f"confidence finding -- fix shape: in the RX ISR, before "
            f"committing the byte, compute (rx_ring_wr + 1) mod 48 and "
            f"compare against rx_ring_rd; if equal, drop the new byte "
            f"(or set an OERR-style fault flag) instead of overwriting. "
            f"When the fix lands, this xfail flips to passing."
        )


# ---------------------------------------------------------------------------
# Hang class 3: parser frame-gap timeout
# ---------------------------------------------------------------------------


def test_v171_rx_parser_has_frame_gap_timeout() -> None:
    """SHIPPING-CONFIDENCE GATE: rx_parser_entry advances
    rx_frame_position on each route/cmd/data byte but has no timeout
    that would reset position to 0 if a frame stalls mid-way.  A
    single dropped or corrupted byte leaves the parser stuck mid-frame
    until pure luck re-syncs.

    Detection is naming-agnostic (codex MEDIUM fix vs 47a2db3): the
    prior heuristic only matched `decfsz` on cells named
    `gap|timeout|stall`, so a correct fix using `decf`, `dcfsnz`, or
    a neutral name like `rx_idle_ctr` would slip past the gate.

    Robust shape: count the number of `clrf rx_frame_position` call
    sites in the source.  The pre-fix source has exactly TWO -- the
    parser's in-band end-of-frame reset (in rx_parser_entry) and a
    cold-init reset (during reconnect / sentinel handling).  A
    correct timeout fix MUST add a THIRD reset path in the
    timeout-handler branch (regardless of what the timeout cell or
    the decrement mnemonic is called).  So `clrf rx_frame_position`
    count >= 3 == timeout fix has landed.
    """
    text = _read_v171_source()
    parser_idx = text.find("rx_parser_entry:")
    assert parser_idx >= 0, "rx_parser_entry label missing"

    # Count all clrf rx_frame_position sites in the FULL source.
    # Allow optional ", BANKED" / ", A" addressing-mode suffix.
    reset_sites = re.findall(
        r"\bclrf\s+rx_frame_position\b",
        text,
    )
    n_resets = len(reset_sites)
    # Pre-fix: 2 resets (parser in-band + cold-init/reconnect).
    # Fix: adds a 3rd reset on the timeout-expiry branch.
    if n_resets < 3:
        pytest.xfail(
            f"V1.71 RX parser has only {n_resets} `clrf rx_frame_position` "
            f"reset sites (need >= 3 for a frame-gap timeout fix to be "
            f"present).  Pre-fix shape: 2 resets cover the parser's "
            f"in-band end-of-frame path and the cold-init/reconnect "
            f"path -- neither of which fires when a frame STALLS mid-"
            f"way.  A single dropped byte therefore leaves "
            f"rx_frame_position stuck non-zero until a future Bx route "
            f"byte AND the parser's modulo state align by luck.  Codex "
            f"shipping-confidence finding -- fix shape: add a small "
            f"per-byte decrementing counter (any name -- `rx_idle_ctr`, "
            f"`rx_gap`, etc.); on each parser tick that does NOT advance "
            f"position, decrement; on zero, `clrf rx_frame_position` so "
            f"the next genuine Bx is treated as a fresh frame start.  "
            f"When the fix adds the 3rd reset site, this xfail flips "
            f"to passing."
        )
