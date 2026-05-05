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

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM


# Note: this file is intentionally NOT marked
# `@pytest.mark.dual_supported`.  4 of the 14 tests (the
# `*_checks_each_enqueue*` family) document an in-progress
# V1.71 hardening goal (see
# `docs/V32_MAIN_HANG_HARDENING_PLAN.md` §3b) and stay on
# strict-xfail decorators until the firmware fix lands.
# The marker is informational post-PF.4 phase 2; this file
# gets it in the same follow-up commit that lands the
# hardening.


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _read_v171_source() -> str:
    return V171_CONTROL_ASM.read_text(encoding="utf-8")


def _read_v171_ram_inc() -> str:
    return V17_CONTROL_RAM_INC.read_text(encoding="utf-8")


def _equ_address(text: str, name: str) -> int | None:
    m = re.search(rf"^\s*{re.escape(name)}\s+equ\s+(0x[0-9A-Fa-f]+)\s*$", text, re.MULTILINE)
    return int(m.group(1), 16) if m else None


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


def _label_lineno_span(text: str, start_label: str, end_label: str) -> tuple[int, int]:
    start_idx = text.find(f"{start_label}:")
    assert start_idx >= 0, f"{start_label} label missing"
    end_idx = text.find(f"{end_label}:", start_idx + 1)
    assert end_idx > start_idx, f"could not delimit {start_label}..{end_label}"
    start_line = text[:start_idx].count("\n") + 1
    end_line = text[:end_idx].count("\n") + 1
    return start_line, end_line


def _label_block(text: str, start_label: str, end_label: str) -> str:
    start = text.find(f"{start_label}:")
    assert start >= 0, f"{start_label} label missing"
    end = text.find(f"{end_label}:", start + 1)
    assert end > start, f"could not delimit {start_label}..{end_label}"
    return text[start:end]


def _label_base_lineno(text: str, label: str) -> int:
    start = text.find(f"{label}:")
    assert start >= 0, f"{label} label missing"
    return text[:start].count("\n") + 1


def _assert_immediate_branch_after_calls(
    *,
    text: str,
    start_label: str,
    end_label: str,
    abort_label: str,
    expected_count: int,
    call_pattern: str = r"\b(call|rcall)\s+tx_byte_enqueue\b",
) -> None:
    body = _label_block(text, start_label, end_label)
    helper_lines = body.splitlines()
    base_lineno = _label_base_lineno(text, start_label)
    full_lines = text.splitlines()
    call_indices = [
        i for i, line in enumerate(helper_lines)
        if re.search(call_pattern, line)
    ]
    assert len(call_indices) == expected_count, (
        f"{start_label} should issue exactly {expected_count} checked enqueue call(s); "
        f"found {len(call_indices)}"
    )
    for body_idx in call_indices:
        src_idx = base_lineno - 1 + body_idx
        nxt = _next_instruction_lines(full_lines, src_idx, max_lookahead=1)
        assert nxt, f"{start_label} call at line {src_idx + 1} has no following instruction"
        nxt_line_no, nxt_raw = nxt[0]
        assert re.search(
            rf"^\s*bc\s+{re.escape(abort_label)}\b",
            nxt_raw,
            re.IGNORECASE,
        ), (
            f"{start_label} call at line {src_idx + 1} is not immediately followed by "
            f"`bc {abort_label}`; next instruction at line {nxt_line_no} was {nxt_raw!r}"
        )
    assert f"{abort_label}:" in body, (
        f"{start_label} missing abort label {abort_label}:"
    )


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

    # The parser's single-byte 0xFE echo path is intentionally best-effort:
    # it is not a multi-byte frame helper and carries no success-side state
    # mutation beyond the attempted echo itself.  The audit here is about the
    # residual multi-byte routed-frame risk.
    parser_echo_lo, parser_echo_hi = _label_lineno_span(
        text,
        "flow_rx_parser_entry_0478",
        "flow_rx_parser_entry_048A",
    )
    unchecked = [
        (n, line)
        for n, line in unchecked
        if not (parser_echo_lo <= n < parser_echo_hi)
    ]

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


def test_v171_ram_inc_defines_ir_defer_and_parser_gap_slots() -> None:
    """The first-pass hardening plan uses the remaining 0x0AA / 0x0AC gap
    for the new IR-defer latch and parser frame-gap timeout byte.

    Pin the slots here so the asm and tests move in lockstep and we do
    not silently collide with the V1.71 scratch/cache layout.
    """
    text = _read_v171_ram_inc()
    assert _equ_address(text, "v171_ir_decode_pending") == 0x0AA, (
        "v171_ir_decode_pending should live at 0x0AA"
    )
    assert _equ_address(text, "v171_rx_frame_gap_timeout") == 0x0AC, (
        "v171_rx_frame_gap_timeout should live at 0x0AC"
    )


def test_v171_new_bank0_state_cells_are_not_accessed_via_access_bank() -> None:
    """0x0AA / 0x0AC live in bank-0 GPR space, not the PIC18 access bank.

    Using `, A` on these symbols silently hits the wrong physical window
    (high access-bank / SFR space) and can destabilize unrelated runtime
    state while the structural tests still pass.  Pin the fix here:
    every operational access to the new cells must be BANKED.
    """
    text = _read_v171_source()
    offenders: list[tuple[int, str]] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        code = re.sub(r";.*$", "", raw)
        if "v171_ir_decode_pending" not in code and "v171_rx_frame_gap_timeout" not in code:
            continue
        if re.search(r"\b(v171_ir_decode_pending|v171_rx_frame_gap_timeout)\b.*,\s*A\b", code):
            offenders.append((lineno, raw.rstrip()))

    assert not offenders, (
        "new bank-0 hardening cells must not use access-bank addressing; "
        "offending site(s):\n"
        + "\n".join(f"  line {lineno}: {raw}" for lineno, raw in offenders)
    )
    for name in ("v171_ir_decode_pending", "v171_rx_frame_gap_timeout"):
        assert re.search(rf"\b{name}\b.*\bBANKED\b", text), (
            f"{name} should be accessed via explicit BANKED operands"
        )


_V171_HARDENING_PENDING_XFAIL = pytest.mark.xfail(
    reason=(
        "V1.71 TX-enqueue hardening pending per "
        "docs/V32_MAIN_HANG_HARDENING_PLAN.md.  Each `call tx_byte_enqueue` "
        "in routed/poll/input/volume/cmd1d/standby/wake helpers should "
        "immediately read STATUS.C and `bc <abort-label>` so a TX-ring "
        "saturation byte-drop doesn't silently break the wire frame.  "
        "Tracked as P4-followup #104; the broader unchecked-caller audit "
        "test_v171_serial_tx_routed_frame_propagates_enqueue_failure "
        "above already xfails at runtime via pytest.xfail() -- these "
        "narrower per-helper gates use the decorator form so the suite "
        "stays green until the firmware fix lands.  Strict so XPASS "
        "surfaces as a real "
        "failure: when the hardening lands, this decorator must be "
        "removed in the same commit (codex LOW from 9cca525 -- "
        "non-strict xfail would silently green-light a stale gate)."
    ),
    strict=True,
    run=True,
)


@_V171_HARDENING_PENDING_XFAIL
def test_v171_serial_tx_routed_frame_checks_each_enqueue_and_skips_sync_reset_on_abort() -> None:
    """Wake/reconnect-critical routed traffic must abort on the first
    dropped byte and only debounce full-sync on success.

    This is the narrow pass-required version of the broader unchecked-
    caller audit above.  The initial hardening pass only requires the
    routed-frame choke-point to be fixed; the repo-wide audit can stay
    xfail until the rest of the callers are cleaned up.
    """
    text = _read_v171_source()
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="serial_tx_routed_frame",
        end_label="full_sync_burst",
        abort_label="serial_tx_routed_frame_aborted",
        expected_count=3,
    )
    body = _label_block(text, "serial_tx_routed_frame", "full_sync_burst")
    assert "clrf    0x9f" in body and "clrf    0xa0" in body, (
        "serial_tx_routed_frame must still debounce full_sync_lo/full_sync_hi on success"
    )
    assert re.search(
        r"clrf\s+0x9f.*\n.*clrf\s+0xa0.*\n.*return\s+0x0.*\nserial_tx_routed_frame_aborted:\n.*return\s+0x0",
        body,
        re.DOTALL,
    ), (
        "serial_tx_routed_frame should return on the success path before the "
        "abort label so a `bc serial_tx_routed_frame_aborted` branch skips the "
        "full_sync reset entirely"
    )


@_V171_HARDENING_PENDING_XFAIL
def test_v171_poll_frame_send_checks_each_enqueue_and_aborts_early() -> None:
    text = _read_v171_source()
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="poll_frame_send",
        end_label="input_frame_send",
        abort_label="poll_frame_send_aborted",
        expected_count=3,
    )


@_V171_HARDENING_PENDING_XFAIL
def test_v171_input_volume_and_cmd1d_helpers_check_each_enqueue() -> None:
    text = _read_v171_source()
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="input_frame_send",
        end_label="volume_frame_send",
        abort_label="input_frame_send_aborted",
        expected_count=3,
    )
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="volume_frame_send",
        end_label="cmd1d_setting_frame_send",
        abort_label="volume_frame_send_aborted",
        expected_count=3,
    )
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="cmd1d_setting_frame_send",
        end_label="v171_service_pending_ir_decode",
        abort_label="cmd1d_setting_frame_send_aborted",
        expected_count=3,
    )


@_V171_HARDENING_PENDING_XFAIL
def test_v171_explicit_ir_standby_and_wake_helpers_check_each_enqueue() -> None:
    text = _read_v171_source()
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="v171_send_standby_cmd_frame",
        end_label="v171_send_wake_cmd_frame",
        abort_label="v171_send_standby_cmd_frame_aborted",
        expected_count=3,
    )
    _assert_immediate_branch_after_calls(
        text=text,
        start_label="v171_send_wake_cmd_frame",
        end_label="v171_send_preset_frame_txonly",
        abort_label="v171_send_wake_cmd_frame_aborted",
        expected_count=3,
    )


def test_v171_preset_persist_skips_eeprom_write_after_tx_abort() -> None:
    text = _read_v171_source()
    body = _label_block(text, "v171_send_preset_frame_and_persist", "v171_preset_screen")
    assert re.search(r"rcall\s+v171_send_preset_frame_txonly", body), (
        "v171_send_preset_frame_and_persist must still send the tx-only frame first"
    )
    assert re.search(
        r"rcall\s+v171_send_preset_frame_txonly[^\n]*\n\s+bc\s+v171_send_preset_frame_and_persist_aborted\b",
        body,
        re.IGNORECASE,
    ), (
        "v171_send_preset_frame_and_persist must branch to an abort label when "
        "the tx-only helper returns C=1"
    )
    assert "call    eeprom_write_byte" in body, (
        "EEPROM persistence call missing from v171_send_preset_frame_and_persist"
    )
    assert "v171_send_preset_frame_and_persist_aborted:" in body, (
        "missing abort label in v171_send_preset_frame_and_persist"
    )


def test_v171_ir_decode_is_deferred_out_of_isr() -> None:
    """The expensive RC5 bit-bang decoder must no longer run inside the
    ISR critical section.

    First-pass shape: the ISR sets a pending byte, returns quickly, and
    a foreground helper owns the actual `ir_rc5_decode` call.
    """
    text = _read_v171_source()
    isr_block = _label_block(text, "isr_entry", "rx_parser_entry")
    assert "rcall   ir_rc5_decode" not in isr_block, (
        "ISR should not call ir_rc5_decode directly once RC5 is deferred"
    )
    assert re.search(r"setf\s+v171_ir_decode_pending\b", isr_block), (
        "ISR should latch v171_ir_decode_pending instead of running ir_rc5_decode inline"
    )


def test_v171_foreground_ir_decode_helper_exists_and_is_serviced_from_display_loop() -> None:
    text = _read_v171_source()
    helper_body = _label_block(text, "v171_service_pending_ir_decode", "mute_frame_send")
    assert re.search(r"rcall\s+ir_rc5_decode\b", helper_body), (
        "foreground IR service helper must own the ir_rc5_decode call"
    )
    assert "clrf    v171_ir_decode_pending" in helper_body, (
        "foreground IR service helper must clear the pending latch once serviced"
    )

    display_loop = _label_block(text, "display_loop_iteration", "control_core_service_0DCE")
    assert re.search(r"call\s+v171_service_pending_ir_decode\b", display_loop), (
        "display_loop_iteration must service deferred IR decode"
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


def test_v171_bf2x_case_check_resets_bsr_before_parser_tail_exit() -> None:
    """REGRESSION GATE (real-HW disaster 2026-04-20): every exit from
    v171_bf2x_case_check that bras to flow_rx_parser_entry_05EA MUST
    have `movlb 0x00` immediately preceding it (within the prior 30
    instructions), so the parser tail's BANKED reads of rx_ring_rd /
    rx_ring_wr (operands 0x098/099) hit BANK 0 instead of BANK 1.

    Background: the Tier-1 cache shifted into operand range
    0x096..0x09F which aliases:
      * v171_diag_target  (0x096) ↔ tx_ring_rd
      * v171_diag_present (0x097) ↔ tx_ring_wr
      * v171_diag_poll_lo (0x098) ↔ rx_ring_rd
      * v171_diag_poll_hi (0x099) ↔ rx_ring_wr
      * v171_diag_reset_seen   (0x09D) ↔ idle_timeout_lo
      * v171_diag_reset_target (0x09E) ↔ idle_timeout_hi
      * v171_diag_reset_timeout(0x09F) ↔ full_sync_lo
    A BSR=1 leak from the parser case-check into the parser tail
    causes the tail to read MY cells as ring positions, mis-parse
    every byte, and cascade to the symptoms observed on real HW
    (garbled LCD, button presses lost, backlight off as
    idle_timeout aliases v171_diag_reset_seen and counts down).

    The pre-Tier-1 source had the same BSR-leak class but its
    consequence was benign because the aliased cells were rx_ring
    body (a circular buffer where corruption gets overwritten).
    Phase 3.1's cache extension changed that.

    This gate fires every commit so a future regression that re-
    introduces a bra-without-movlb-0x00 exit fails fast.
    """
    text = _read_v171_source()
    case_check_idx = text.find("v171_bf2x_case_check:")
    assert case_check_idx >= 0, "v171_bf2x_case_check label missing"
    # Window: from the case_check label to the end of v171_bf2x_*
    # routines (signaled by flow_rx_parser_entry_05EA: label).
    end_idx = text.find("\nflow_rx_parser_entry_05EA:", case_check_idx)
    assert end_idx > case_check_idx, "could not delimit case_check region"
    region = text[case_check_idx:end_idx]
    region_lines = region.splitlines()

    # Find every `bra flow_rx_parser_entry_05EA` in the region.
    leaky_exits: List[Tuple[int, str]] = []
    base_lineno = text[:case_check_idx].count("\n") + 1
    for i, line in enumerate(region_lines):
        # Strip comments before checking.
        stripped = re.sub(r";.*$", "", line).strip()
        if not re.match(r"bra\s+flow_rx_parser_entry_05EA\b", stripped):
            continue
        src_lineno = base_lineno + i
        # Look back up to 30 instruction lines for either:
        #   * `movlb 0x00` (resets BSR) -- exit is safe
        #   * `movlb 0x01` with no intervening `movlb 0x00` (BSR=1) -- LEAK
        # The lookback also needs to handle the early-exit case where the
        # bra lands BEFORE any movlb has fired -- in that case BSR is the
        # caller's state (not our concern).
        bsr_state: str = "caller"  # no movlb seen yet
        for j in range(i - 1, max(-1, i - 30), -1):
            back = re.sub(r";.*$", "", region_lines[j]).strip()
            m = re.match(r"movlb\s+(0x0?\d+)", back)
            if m:
                val = int(m.group(1), 0)
                if val == 0:
                    bsr_state = "0"
                else:
                    bsr_state = "1"
                break
            # If we hit a label, stop looking back -- the bra reached
            # us via a control-flow merge, BSR could be anything.
            if back.endswith(":") and not back.startswith("v171_") and " " not in back[:-1]:
                bsr_state = "merge"
                break
        if bsr_state == "1":
            leaky_exits.append((src_lineno, line.strip()))

    assert not leaky_exits, (
        f"v171_bf2x_case_check has {len(leaky_exits)} bra-to-parser-tail "
        f"exit(s) with BSR left at 1 -- the parser tail's BANKED reads of "
        f"rx_ring_rd / rx_ring_wr (operands 0x098/099) will hit BANK 1 "
        f"(my v171_diag_poll_lo / v171_diag_poll_hi) instead of BANK 0 "
        f"and mis-parse every subsequent RX byte.  Real-HW disaster "
        f"2026-04-20 confirmed this exact failure mode.  Each leaky "
        f"exit needs `movlb 0x00` immediately before the bra.  Sites:\n"
        + "\n".join(f"    line {n}: {l}" for n, l in leaky_exits)
    )


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

    Robust shape: count EVERY clrf-to-zero of rx_frame_position (RAM
    address 0x0A6) in BOTH the symbolic form (`clrf rx_frame_position`)
    AND the raw-address form (`clrf 0xa6` -- gpasm output style for
    pre-equate code paths).  Codex MEDIUM fix vs 2ee4abe pointed out
    that counting only the symbolic form missed the 2 raw-address
    resets at lines 983 and 3984, so the prior premise of "pre-fix == 2
    resets" was wrong.

    Pre-fix actual count: 4 sites (2 symbolic + 2 raw):
      * line 910: clrf rx_frame_position, BANKED -- parser end-of-frame
      * line 983: clrf 0xa6, B -- parser route-byte fresh-start
      * line 3984: clrf 0xa6, B -- reconnect-exit cold-reset
      * line 4460: clrf rx_frame_position, BANKED -- cold-init / reconnect

    A correct timeout fix MUST add a 5th reset path in the timeout-
    handler branch (regardless of what the timeout cell or decrement
    mnemonic is called, or whether the new code uses the symbolic or
    raw addressing form).  So `count >= 5` == timeout fix has landed.

    Note on `movlw 0; movwf` form: a hypothetical fix using that
    pattern instead of `clrf` would slip past this gate.  In practice
    PIC18 idiom is `clrf` (1 instruction vs 2), and the existing 4
    resets all use clrf, so a fix using movwf would be deeply unusual
    and would warrant a comment explaining why -- at which point the
    test can be updated.
    """
    text = _read_v171_source()
    parser_idx = text.find("rx_parser_entry:")
    assert parser_idx >= 0, "rx_parser_entry label missing"

    # Strip asm comments so a future doc line containing the literal
    # text `clrf rx_frame_position` or `clrf 0xa6` doesn't false-pass
    # the count gate (codex LOW fix vs 8a5e0ff: gpasm comment syntax
    # is a single `;` to end-of-line; remove that span from each line).
    code_only = "\n".join(
        re.sub(r";.*$", "", line) for line in text.splitlines()
    )

    # Count BOTH symbolic and raw-address clrf forms targeting 0x0A6.
    # The symbolic form: `clrf rx_frame_position` with optional
    # `, BANKED` / `, A` suffix.  The raw form: `clrf 0xa6` (or 0xA6,
    # case-insensitive) with optional `, B` / `, A` suffix.
    symbolic_sites = re.findall(
        r"\bclrf\s+rx_frame_position\b",
        code_only,
    )
    raw_sites = re.findall(
        r"\bclrf\s+0x[aA]6\b",
        code_only,
    )
    n_resets = len(symbolic_sites) + len(raw_sites)
    # Pre-fix: 4 resets (parser in-band + parser route + reconnect-exit
    # + cold-init).  Fix: adds a 5th reset on the timeout-expiry branch.
    if n_resets < 5:
        pytest.xfail(
            f"V1.71 RX parser has only {n_resets} `clrf rx_frame_position` "
            f"reset sites (symbolic={len(symbolic_sites)}, "
            f"raw=0xa6={len(raw_sites)}; need >= 5 for a frame-gap "
            f"timeout fix to be present).  Pre-fix shape: 4 resets cover "
            f"the parser's in-band end-of-frame path, the parser's route-"
            f"byte fresh-start, the reconnect-exit cold-reset, and the "
            f"cold-init / reconnect -- none of which fire when a frame "
            f"STALLS mid-way.  A single dropped byte therefore leaves "
            f"rx_frame_position stuck non-zero until a future Bx route "
            f"byte AND the parser's modulo state align by luck.  Codex "
            f"shipping-confidence finding -- fix shape: add a small "
            f"per-byte decrementing counter (any name -- `rx_idle_ctr`, "
            f"`rx_gap`, etc.); on each parser tick that does NOT advance "
            f"position, decrement; on zero, `clrf rx_frame_position` "
            f"(symbolic OR raw 0xa6 form) so the next genuine Bx is "
            f"treated as a fresh frame start.  When the fix adds the 5th "
            f"reset site, this xfail flips to passing."
        )
