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
    pattern (see v171_diag_send_query_w in dlcp_control_v171.asm)."""
    nxt = _next_instruction_lines(text_lines, call_line_idx, max_lookahead=1)
    if not nxt:
        return False
    _, raw = nxt[0]
    return bool(re.search(r"^\s*bc\s+\w", raw))


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
    enqueue_calls = re.findall(r"call\s+tx_byte_enqueue", body)
    bc_checks = re.findall(r"bc\s+v171_diag_send_query_aborted", body)
    assert len(enqueue_calls) == 3, (
        f"diag-query helper should issue exactly 3 byte enqueues "
        f"(route + cmd + data); found {len(enqueue_calls)}"
    )
    assert len(bc_checks) == 3, (
        f"diag-query helper should bc-check after EVERY byte enqueue "
        f"(3 checks for 3 enqueues); found {len(bc_checks)}"
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

    This structural test searches the RX ISR body for any sign of an
    unread-data guard (typically a comparison of rx_ring_wr against
    rx_ring_rd before commit).  If present, the test passes.  If
    absent, xfail with the rationale so the operator / fix-campaign-
    author knows the contract is incomplete.

    The corresponding behavioral test (Tier C, deferred) would inject
    >48 byte storm and verify the parser eventually re-syncs without
    permanent state loss.
    """
    text = _read_v171_source()
    # The RX ISR landmark is the rx_ring_base += rx_ring_wr write
    # path.  Look for the section header / label that owns this code.
    # Using the canonical comment marker from dlcp_control_v171.asm.
    isr_idx = text.find("ISR producer side")
    if isr_idx < 0:
        # Fallback: search for the rx_ring_wr increment+wrap pattern.
        isr_idx = text.find("rx_ring_wr")
    assert isr_idx >= 0, "rx_ring producer site not found"

    # Look at the next 2000 chars for any cpfsgt / cpfslt / xorwf
    # pattern testing rx_ring_wr against rx_ring_rd (the canonical
    # "would-this-write-stomp-an-unread-byte" guard shape).
    isr_window = text[isr_idx:isr_idx + 2000]
    has_guard = bool(
        re.search(r"cpf(seq|sgt|slt)\s+rx_ring_rd", isr_window)
        or re.search(r"xorwf\s+rx_ring_rd", isr_window)
        or re.search(r"subwf\s+rx_ring_rd", isr_window)
    )
    if not has_guard:
        pytest.xfail(
            "V1.71 RX ISR has NO unread-data guard before writing "
            "rx_ring_base[rx_ring_wr].  Producer can wrap the 48-byte "
            "ring before the consumer drains, overwriting in-flight "
            "frame bytes.  Codex shipping-confidence finding -- fix "
            "shape: in the RX ISR, before committing the byte, "
            "compute (rx_ring_wr + 1) mod 48 and compare against "
            "rx_ring_rd; if equal, drop the new byte (or set an "
            "OERR-style fault flag) instead of overwriting.  When "
            "the fix lands, this xfail flips to passing."
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

    This structural test searches rx_parser_entry for any timeout-
    style code -- decrement-on-each-tick + reset-position-on-zero
    pattern.  If absent, xfail with rationale.
    """
    text = _read_v171_source()
    parser_idx = text.find("rx_parser_entry:")
    assert parser_idx >= 0, "rx_parser_entry label missing"
    # Consume ~3000 chars after the label to cover the parser body.
    parser_window = text[parser_idx:parser_idx + 3000]
    # Look for any decrement of an idle-counter cell + bcf rx_frame_position.
    # The canonical frame-gap timeout shape is:
    #   decfsz <gap_counter>
    #   <reset rx_frame_position to 0>
    has_timeout = bool(
        re.search(r"decfsz\s+\w*(gap|timeout|stall)\w*", parser_window, re.IGNORECASE)
    )
    if not has_timeout:
        pytest.xfail(
            "V1.71 RX parser has NO frame-gap timeout.  A single "
            "dropped byte mid-frame leaves rx_frame_position stuck "
            "non-zero until a future Bx route byte arrives AND the "
            "parser's modulo state happens to align.  Codex shipping-"
            "confidence finding -- fix shape: add a small per-byte "
            "decrementing counter; on each parser tick that does NOT "
            "advance position, decrement; on zero, reset position to "
            "0 so the next genuine Bx is treated as a fresh frame "
            "start.  When the fix lands, this xfail flips to passing."
        )
