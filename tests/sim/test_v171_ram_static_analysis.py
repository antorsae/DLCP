"""V1.71 CONTROL RAM static-analysis gates (Tier-1).

Catches the bug shapes we hit during V1.71 RAM work — equate collisions,
BSR/access-mode mismatches, movff bank aliasing, and ISR save/restore
imbalance — at static-analysis time, before the bug ships.

Per the 2026-05-08 RAM-conflict detection plan in response to user
question "how can we make sure there are no conflicts in ram use"
(task #156).  Tier-1 is the cheapest tier (parse-only, <1 s).
Tiers 2-3 (runtime write tracking, region manifest) are deferred --
this gate alone would have caught every earlier RAM/bank bug at
PR time.

Bug classes covered
===================

T1.1  Equate collision -- two non-alias RAM-cell names map to the
      same equate value.  Example caught: the spec-pre-fix collision
      where an early V1.71 IR draft picked operand 0x0AB which was
      already owned by ``bf08_fault_byte``.

T1.2  BSR discipline -- every BANKED access to a known BANK-1
      equate must have ``movlb 0x01`` in the same routine before
      the access.  Generalizes test_phase3_4_renderer_movlb_
      discipline_before_banked_writes to ALL BANK-1 equates.

T1.3  movff bank aliasing -- ``movff`` takes a 12-bit literal that
      IGNORES BSR.  Using a BANK-1 equate (whose value is the 8-bit
      BANKED operand) as a movff source/dest silently addresses
      BANK 0 instead.

T1.4  ISR context safety:
      (a) Save/restore balance: every register saved in the ISR
          prologue must be restored in the epilogue and vice versa.
      (b) ISR-context functions must not touch FSR1*: isr_entry
          saves FSR0 but NOT FSR1.  Foreground diag-renderer walks use
          FSR1, and ISR-side POSTINC1 would silently clobber the
          foreground walk pointer.
"""

from __future__ import annotations

import re
import warnings

from dlcp_fw.paths import V17_CONTROL_RAM_INC, V171_CONTROL_ASM


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _is_lowercase_ram_name(name: str) -> bool:
    """RAM cell names start with a lowercase letter or 'Common_RAM'.

    Convention used in dlcp_control_ram.inc:
      * lowercase identifiers (``ir_decoded_cmd``, ``v171_diag_target``)
        denote individual RAM cells
      * UPPERCASE identifiers (``IR_ARMED``, ``V171_DIAG_FLAG_DIRTY``)
        denote bit positions or constants — NOT RAM cells; they may
        legitimately share values with each other (e.g.,
        ``V171_DIAG_FLAG_DIRTY equ 0x00`` and ``IR_ARMED equ 0x00``
        are bit positions in different bytes).
    """
    if not name:
        return False
    return name[0].islower()


# Equate parser: matches `name equ value  ; comment` lines.
_EQU_PATTERN = re.compile(
    r"^\s*(\w+)\s+(?:equ|EQU)\s+(\S+)\s*(?:;(.*))?$",
    re.MULTILINE,
)


def _parse_equates() -> list[tuple[str, int | None, str, str]]:
    """Return list of (name, value_int_or_None, raw_value, comment).

    ``value_int_or_None`` is ``None`` for symbolic-alias equates
    (e.g., ``V171_DIAG_FLAG_PENDING equ V171_DIAG_FLAG_RUNTIME_PENDING``)
    and integer otherwise.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    out: list[tuple[str, int | None, str, str]] = []
    for m in _EQU_PATTERN.finditer(text):
        name = m.group(1)
        raw = m.group(2)
        comment = (m.group(3) or "").strip()
        if raw.lower().startswith("0x"):
            try:
                value: int | None = int(raw, 16)
            except ValueError:
                value = None
        elif raw.isdigit():
            value = int(raw, 10)
        else:
            value = None  # symbolic alias
        out.append((name, value, raw, comment))
    return out


# ---------------------------------------------------------------------------
# T1.1 — Equate collision detector
# ---------------------------------------------------------------------------


def test_t1_1_no_duplicate_ram_cell_addresses() -> None:
    """No two RAM-cell equate names in the SAME BANK resolve to the
    same operand value.

    Catches the bug class where a new equate is added at an address
    already owned by another same-bank cell (e.g., the spec-pre-fix
    V1.71 IR draft that put the IR buffer at 0x0AB, already owned
    by ``bf08_fault_byte``).

    Bank-aware: a bank-0 equate (default; no docblock annotation)
    and a bank-1 equate (docblock says ``BANK 1`` or
    ``physical 0x1xx``) at the same operand DO NOT collide because
    they live in different physical cells.  This is an intentional
    pattern in the .inc file (e.g. ``tx_ring_rd`` bank-0 at 0x96
    aliases ``v171_diag_target`` bank-1 at 0x96 = phys 0x196).
    BSR discipline (T1.2) protects the cross-bank cells.

    Skips:
      * UPPERCASE names (constants / bit positions; share values
        legitimately across different cells)
      * Symbolic aliases (``X equ Y``)
      * The special base symbol ``Common_RAM``
    """
    equates = _parse_equates()
    bank1 = {name for name, _ in _bank1_equates()}

    def bank_of(name: str) -> str:
        return "1" if name in bank1 else "0"

    by_bank_value: dict[tuple[str, int], list[str]] = {}
    for name, value, raw, _ in equates:
        if not _is_lowercase_ram_name(name):
            continue
        if name == "Common_RAM":
            continue
        if value is None:
            continue
        if value < 0 or value > 0xFF:
            continue
        by_bank_value.setdefault((bank_of(name), value), []).append(name)

    collisions = {
        bv: names for bv, names in by_bank_value.items() if len(names) > 1
    }
    assert not collisions, (
        "RAM-cell equate collision within the same bank:\n"
        + "\n".join(
            f"  bank {bank} @ 0x{v:02X}: {', '.join(names)}"
            for (bank, v), names in sorted(collisions.items())
        )
        + "\n\nTwo same-bank names at the same operand silently corrupt\n"
        "each other on every access.  Either move one cell or, if the\n"
        "aliasing is intentional, document it via a symbolic-alias EQU\n"
        "(`name2 equ name1`) which is exempt from this check."
    )


# ---------------------------------------------------------------------------
# T1.2 — BSR discipline for known BANK-1 equates
# ---------------------------------------------------------------------------


_BANK1_COMMENT_PATTERN = re.compile(
    r"physical\s+0x1[0-9a-fA-F]{2}|\bBANK\s+1\b",
    re.IGNORECASE,
)


# Prefix conventions: equate-name prefixes that live in BANK 1 by
# project convention (per the section-header comments at the top of
# their respective blocks in dlcp_control_ram.inc).  Names matching
# any of these prefixes are classified as BANK 1 even when the
# per-equate block comment doesn't repeat the marker.
#
_BANK1_NAME_PREFIXES = (
    "v171_diag_",
)


def _bank1_equates() -> list[tuple[str, int]]:
    """Return [(name, value), ...] for equates documented as BANK 1.

    Two sources of classification:
      1. The equate's own comment OR its preceding-block-comment
         contains ``physical 0x1xx`` or ``BANK 1``.
      2. The equate name matches one of the BANK-1 prefix
         conventions in ``_BANK1_NAME_PREFIXES`` (e.g. ``v171_diag_*``)
         -- these families have section headers
         documenting BANK 1 globally even when individual sub-blocks
         don't repeat the marker (e.g., ``v171_diag_reset_*``).

    Block-comment association: walk the .inc file linewise; each
    comment-only line accumulates into the "current docblock" buffer;
    the next equate inherits the block's contents until a non-comment
    non-equate line clears the buffer.
    """
    text = V17_CONTROL_RAM_INC.read_text(encoding="utf-8")
    out: list[tuple[str, int]] = []
    block_comments: list[str] = []
    for raw_line in text.split("\n"):
        line = raw_line.rstrip()
        if not line.strip():
            block_comments.clear()
            continue
        if line.lstrip().startswith(";"):
            block_comments.append(line)
            continue
        m = _EQU_PATTERN.match(line)
        if not m:
            block_comments.clear()
            continue
        name = m.group(1)
        raw = m.group(2)
        own_comment = (m.group(3) or "")
        if not _is_lowercase_ram_name(name):
            continue
        if not raw.lower().startswith("0x"):
            continue
        try:
            value = int(raw, 16)
        except ValueError:
            continue
        if not (0 <= value <= 0xFF):
            continue
        full_comment = own_comment + "\n" + "\n".join(block_comments)
        is_bank1 = (
            _BANK1_COMMENT_PATTERN.search(full_comment) is not None
            or any(name.startswith(p) for p in _BANK1_NAME_PREFIXES)
        )
        if is_bank1:
            out.append((name, value))
    return out


# Mnemonics that take a file operand (read OR write).  Sourced from the
# pattern in test_v171_layer5_diag_page.py::test_phase3_4_renderer_movlb_
# discipline_before_banked_writes (which lists every PIC18 mnemonic
# that can take an f-operand) and verified against PIC18F25K20 datasheet
# table 24-2.
_F_OPERAND_MNEMONICS = (
    "movwf|movf|clrf|setf|"
    "addwf|addwfc|subfwb|subwf|subwfb|negf|"
    "btfsc|btfss|bsf|bcf|btg|"
    "cpfslt|cpfseq|cpfsgt|"
    "incf|incfsz|infsnz|decf|decfsz|dcfsnz|"
    "iorwf|andwf|xorwf|comf|"
    "rlcf|rlncf|rrcf|rrncf|swapf|"
    "tstfsz"
)


def test_t1_2_bank1_equates_accessed_under_movlb_0x01() -> None:
    """Every BANKED access to a BANK-1 equate must have ``movlb 0x01``
    upstream on the same control-flow path as the access.

    Walks each access backward through INSTRUCTION lines.  When the
    walk crosses a label boundary into a different basic block, the
    test recurses into the IMMEDIATE PREDECESSOR branches targeting
    that label and checks each one's tail (single-level dataflow).
    This catches the bug shape the older diag-renderer test would
    flag as a false-positive AND avoids exempting real leaks across
    label boundaries.

    Verdict per access:
      * ``movlb 0x01`` / ``movlb 0x1``     local path -> BSR=1 SAFE
      * ``rcall v171_diag_load_fsr1_base`` local path -> BSR=1 SAFE
      * ``movlb 0x00`` / ``movlb 0x0``     local path  -> LEAK
      * Walked into different block -> check predecessors:
          - all predecessors SAFE      -> SAFE
          - any predecessor confirmed LEAK -> LEAK
          - mix of SAFE + indeterminate    -> INDETERMINATE (warn)
    """
    bank1 = _bank1_equates()
    bank1_names = {name for name, _ in bank1}
    if not bank1_names:
        raise AssertionError(
            "T1.2 helper found zero BANK-1 equates; the comment "
            "heuristic ('physical 0x1xx' or 'BANK 1') may have "
            "drifted.  Check dlcp_control_ram.inc."
        )

    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    lines = text.split("\n")

    name_alt = "|".join(re.escape(n) for n in sorted(bank1_names, key=len, reverse=True))
    access_pattern = re.compile(
        rf"\b(?:{_F_OPERAND_MNEMONICS}|movff)\s+"
        rf"(?:{name_alt})(?:,\s*[FW])?(?:,\s*\w+)?,\s*(?:BANKED|B)\b"
    )
    movlb_b1_pattern = re.compile(r"\bmovlb\s+0x0?1\b")
    movlb_b0_pattern = re.compile(r"\bmovlb\s+0x0?0\b")
    bsr1_helper_pattern = re.compile(r"\brcall\s+v171_diag_load_fsr1_base\b")
    label_pattern = re.compile(r"^\w+:\s*$")
    separator_pattern = re.compile(r"^\s*;\s*-{20,}\s*$")

    def is_instruction(line: str) -> bool:
        s = line.split(";", 1)[0].strip()
        if not s:
            return False
        if label_pattern.match(s):
            return False
        return True

    def is_label(line: str) -> bool:
        s = line.split(";", 1)[0].strip()
        return bool(label_pattern.match(s))

    label_def_pattern = re.compile(r"^(\w+):\s*$")

    def walk_block(start_idx: int) -> tuple[str, str]:
        """Walk backward through the basic block ENDING at start_idx.

        Returns (verdict, detail).  Verdict: ``safe`` / ``leak`` /
        ``label:LABELNAME`` / ``boundary``.  ``label:`` means the walk
        exited the block via the named label (caller should evaluate
        predecessors).  ``boundary`` means we hit a routine-separator
        comment with no movlb resolution.
        """
        steps = 0
        for back in range(1, len(lines)):
            i = start_idx - back
            if i < 0:
                return "boundary", "walked off file start"
            prev = lines[i]
            if separator_pattern.match(prev):
                return "boundary", f"routine-separator at line {i + 1}"
            mlbl = label_def_pattern.match(prev.split(';', 1)[0].strip())
            if mlbl:
                return f"label:{mlbl.group(1)}", f"label at line {i + 1}"
            if not is_instruction(prev):
                continue
            if movlb_b1_pattern.search(prev) or bsr1_helper_pattern.search(prev):
                return "safe", f"movlb 0x01 (or helper) at line {i + 1}"
            if movlb_b0_pattern.search(prev):
                return "leak", f"`movlb 0x00` at line {i + 1}"
            steps += 1
            if steps > 400:
                return "boundary", "no movlb in 400 instructions"
        return "boundary", "exhausted"

    def evaluate_predecessors(label: str, visited: set[str]) -> tuple[str, str]:
        """Single-level predecessor walk: find every ``bra LABEL`` /
        ``goto LABEL`` reference and walk back from each.

        Returns ``safe`` if ALL predecessors are safe.  ``leak`` if
        ANY predecessor is a confirmed leak.  ``indeterminate``
        otherwise.  Recursion guarded by ``visited`` set.
        """
        if label in visited:
            return "indeterminate", f"label {label} already visited (cycle)"
        visited = visited | {label}
        # All PIC18 control-flow instructions that can target a label:
        # unconditional (bra, goto), conditional skip-on-flag (bz, bnz,
        # bc, bnc, bn, bnn, bov, bnov), call (call, rcall).  Caller's
        # tail BSR state determines whether the branch leaves the
        # block in BSR=1 or BSR=0.
        ref_pattern = re.compile(
            rf"\b(?:bra|goto|bz|bnz|bc|bnc|bn|bnn|bov|bnov|call|rcall)"
            rf"\s+{re.escape(label)}\b"
        )
        pred_indices = [i for i, l in enumerate(lines) if ref_pattern.search(l)]
        if not pred_indices:
            return "indeterminate", f"no predecessor branches to {label}"
        verdicts: list[str] = []
        leak_detail: str | None = None
        for pi in pred_indices:
            v, d = walk_block(pi)
            if v.startswith("label:"):
                # Recurse one more level: a predecessor's block also
                # ended at a label.  Single-level recursion guards.
                inner_label = v.split(":", 1)[1]
                v, d = evaluate_predecessors(inner_label, visited)
            verdicts.append(v)
            if v == "leak" and leak_detail is None:
                leak_detail = f"via predecessor branch at line {pi + 1}: {d}"
        if all(v == "safe" for v in verdicts):
            return "safe", f"all {len(verdicts)} predecessor(s) safe"
        if "leak" in verdicts:
            return "leak", leak_detail or "predecessor leak"
        return "indeterminate", (
            f"predecessor verdicts mixed: "
            f"{verdicts.count('safe')} safe, "
            f"{verdicts.count('indeterminate')} indeterminate, "
            f"{verdicts.count('boundary')} boundary"
        )

    leak_sites: list[tuple[int, str, str]] = []
    indeterminate_sites: list[tuple[int, str, str]] = []
    for idx, line in enumerate(lines):
        if not access_pattern.search(line):
            continue
        verdict, detail = walk_block(idx)
        if verdict.startswith("label:"):
            label = verdict.split(":", 1)[1]
            verdict, detail = evaluate_predecessors(label, set())
        if verdict == "leak":
            leak_sites.append((idx + 1, line.strip(), detail))
        elif verdict in ("indeterminate", "boundary"):
            indeterminate_sites.append((idx + 1, line.strip(), detail))

    # Indeterminate cases are surfaced as a Python ``UserWarning`` so
    # pytest's session summary lists them (a plain ``print`` is
    # captured + hidden for passing tests by default; codex correctly
    # flagged that as still-silent on 6008238).  The warning includes
    # the line list so reviewers can audit each site to confirm BSR=1
    # is established via a path the single-level predecessor walk
    # couldn't statically prove.
    if indeterminate_sites:
        warning_lines = [
            f"  line {n}: {ln}\n      reason: {v}"
            for n, ln, v in indeterminate_sites
        ]
        warnings.warn(
            f"[T1.2] INDETERMINATE BANK-1 access sites "
            f"({len(indeterminate_sites)} total; predecessor BSR not "
            f"statically proven; manual review needed):\n"
            + "\n".join(warning_lines),
            UserWarning,
            stacklevel=2,
        )

    assert not leak_sites, (
        f"BANKED access to BANK-1 equate WITH a confirmed BSR=0 leak path:\n"
        + "\n".join(
            f"  line {n}: {ln}\n      reason: {v}"
            for n, ln, v in leak_sites
        )
        + "\n\nA missing movlb 0x01 lands the access at PHYSICAL 0x0xx\n"
        "(BANK 0) instead of 0x1xx (BANK 1) -- silent corruption of\n"
        "whatever bank-0 cell shares the operand."
    )


# ---------------------------------------------------------------------------
# T1.3 — movff bank aliasing
# ---------------------------------------------------------------------------


def test_t1_3_bank1_equates_never_used_as_movff_operand() -> None:
    """A BANK-1 equate name must NOT appear as either operand of a
    ``movff`` instruction.

    ``movff src, dst`` takes two 12-bit literals that bypass BSR.
    A BANK-1 equate's value is the 8-bit BANKED operand; using the bare
    name as a movff operand evaluates the literal at face value and
    addresses physical BANK 0 instead of BANK 1.

    Correct pattern: ``lfsr 0x0, 0x1D7`` then ``movff POSTINC0, dst``
    -- the lfsr explicitly loads the 12-bit physical address into
    FSR0, and POSTINC0 references that physical address verbatim.

    The legacy ISR save/restore pattern uses ``movff (Common_RAM + N),
    SFR`` which is fine because Common_RAM+N evaluates to 0x000-0x07F
    (ACCESS bank, no BSR concern).
    """
    bank1 = _bank1_equates()
    if not bank1:
        raise AssertionError(
            "T1.3 helper found zero BANK-1 equates; comment heuristic drifted."
        )
    bank1_names = {name for name, _ in bank1}
    name_alt = "|".join(re.escape(n) for n in sorted(bank1_names, key=len, reverse=True))
    # movff takes two operands separated by a comma; a BANK-1 name on
    # either side is unsafe.
    movff_pattern = re.compile(
        rf"\bmovff\s+(?:[\w()+\s]+|\(.+?\))\s*,\s*(?:[\w()+\s]+|\(.+?\))"
    )
    bank1_word = re.compile(rf"\b(?:{name_alt})\b")

    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    bad: list[tuple[int, str, list[str]]] = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        # Strip line comments before scanning.
        body = line.split(";", 1)[0]
        if not movff_pattern.search(body):
            continue
        names_used = bank1_word.findall(body)
        if names_used:
            bad.append((lineno, line.strip(), names_used))

    assert not bad, (
        "movff with BANK-1 equate as operand (12-bit literal bypasses BSR; "
        "addresses BANK 0 instead of BANK 1):\n"
        + "\n".join(
            f"  line {n}: {ln}\n      bank-1 name(s): {', '.join(names)}"
            for n, ln, names in bad
        )
        + "\n\nFix: use lfsr 0x0, 0x1NN to load physical address, then\n"
        "movff POSTINC0/INDF0/PLUSW0 to reference it (the lfsr value\n"
        "is the full 12-bit physical address; FSR0 honours the upper\n"
        "nibble verbatim)."
    )


# ---------------------------------------------------------------------------
# T1.4 — ISR context safety (save/restore + no FSR1)
# ---------------------------------------------------------------------------


# Functions that run in ISR context.  Hardcoded list rather than call-graph
# analysis -- adding a new ISR-context function requires updating this list,
# which is a feature (forces explicit review of ISR safety).  Functions
# called from these must also be ISR-safe; transitive coverage is task #157
# (T2 follow-up).
_ISR_CONTEXT_FUNCS = [
    "isr_entry",
]


# Registers explicitly NOT saved by isr_entry's prologue.  Foreground
# code routinely uses these; an ISR-side write would silently corrupt
# the foreground state when the ISR returns.
_UNSAVED_REGISTERS = {
    # FSR1 — used by foreground diag-renderer walks (asm:3857, 3943,
    # 4004) and various LCD/scratch paths.
    "FSR1L", "FSR1H",
    "POSTINC1", "POSTDEC1", "PREINC1", "PLUSW1", "INDF1",
    # FSR2 — used by foreground (heavy GPR walks).
    "FSR2L", "FSR2H",
    "POSTINC2", "POSTDEC2", "PREINC2", "PLUSW2", "INDF2",
    # PRODL/PRODH — multiplication result, used by foreground arithmetic.
    "PRODL", "PRODH",
    # TBLPTR* / TABLAT — flash/EE access, used by foreground EEPROM
    # routines that must NOT be interrupted mid-state.
    "TBLPTRL", "TBLPTRH", "TBLPTRU", "TABLAT",
    # PCLATH / PCLATU — program counter latches; corrupting these
    # corrupts the next foreground computed-goto.
    "PCLATH", "PCLATU",
}


def _function_body(text: str, name: str) -> tuple[int, int, list[str]]:
    """Return (start_line, end_line, body_lines) for a function.

    Ends at the first ``return`` or ``retfie`` instruction whose
    indentation matches a function body line.  ``body_lines`` is a
    list of (lineno, raw_line) tuples for lines INSIDE the body.
    """
    lines = text.split("\n")
    start = None
    for idx, line in enumerate(lines):
        if re.match(rf"^\s*{re.escape(name)}\s*:", line):
            start = idx
            break
    if start is None:
        raise AssertionError(f"Function {name!r} not found in ASM")
    end = None
    for idx in range(start + 1, len(lines)):
        line = lines[idx].split(";", 1)[0]
        if re.search(r"\b(?:return|retfie)\b", line):
            end = idx
            break
    if end is None:
        raise AssertionError(f"No return/retfie found for {name!r}")
    body = lines[start:end + 1]
    return start + 1, end + 1, body


def test_t1_4a_isr_entry_save_restore_balance() -> None:
    """Every register saved in isr_entry's prologue must be restored
    in the epilogue and vice versa.

    PROLOGUE = the first contiguous run of save instructions
    immediately after the ``isr_entry:`` label, before any branching
    code or non-save instruction.

    EPILOGUE = the last contiguous run of restore instructions
    immediately before ``retfie``, walking backward.

    Asymmetry => bug.  Either the ISR clobbers a register and doesn't
    restore it (silent foreground corruption) or it loads a stale
    value from a save slot that was never written this ISR run.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    _, _, body = _function_body(text, "isr_entry")

    # Save instruction patterns (per-line).
    save_movff = re.compile(
        r"^\s*movff\s+([A-Z0-9_]+)\s*,\s*\(Common_RAM\s*\+\s*(\d+)\)\s*(?:;|$)"
    )
    save_movwf = re.compile(
        r"^\s*movwf\s+\(Common_RAM\s*\+\s*(\d+)\)\s*,\s*A\s*(?:;|$)"
    )
    # Restore instruction patterns (per-line).
    restore_movff = re.compile(
        r"^\s*movff\s+\(Common_RAM\s*\+\s*(\d+)\)\s*,\s*([A-Z0-9_]+)\s*(?:;|$)"
    )
    restore_movf_w = re.compile(
        r"^\s*movf\s+\(Common_RAM\s*\+\s*(\d+)\)\s*,\s*W\s*,\s*A\s*(?:;|$)"
    )

    def looks_like_save(line: str) -> tuple[str, str] | None:
        s = line.split(";", 1)[0].rstrip()
        m = save_movff.match(s + ";")
        if m:
            return m.group(1), f"(Common_RAM + {m.group(2)})"
        m = save_movwf.match(s + ";")
        if m:
            return "W", f"(Common_RAM + {m.group(1)})"
        return None

    def looks_like_restore(line: str) -> tuple[str, str] | None:
        s = line.split(";", 1)[0].rstrip()
        m = restore_movff.match(s + ";")
        if m:
            return m.group(2), f"(Common_RAM + {m.group(1)})"
        m = restore_movf_w.match(s + ";")
        if m:
            return "W", f"(Common_RAM + {m.group(1)})"
        return None

    # PROLOGUE: from the label, take the first contiguous block of
    # save instructions, allowing blanks/comments between them.
    saves: dict[str, str] = {}
    for line in body[1:]:  # skip the `isr_entry:` line itself
        s = line.split(";", 1)[0].strip()
        if not s:
            continue  # blank line; allowed inside prologue
        sv = looks_like_save(line)
        if sv is None:
            break  # first non-save instruction terminates prologue
        reg, slot = sv
        if reg in saves:
            # Duplicate save of the same register in the prologue --
            # unusual but allowed; keep the last.
            pass
        saves[reg] = slot

    # EPILOGUE: from the retfie line walking back, take the last
    # contiguous block of restore instructions.
    restores: dict[str, str] = {}
    # Body's last line is the retfie; walk backward.
    for line in reversed(body[:-1]):
        s = line.split(";", 1)[0].strip()
        if not s:
            continue
        rs = looks_like_restore(line)
        if rs is None:
            break
        reg, slot = rs
        if reg in restores:
            pass
        restores[reg] = slot

    saved = set(saves)
    restored = set(restores)
    saved_not_restored = saved - restored
    restored_not_saved = restored - saved
    slot_mismatches: list[tuple[str, str, str]] = []
    for reg in saved & restored:
        if saves[reg] != restores[reg]:
            slot_mismatches.append((reg, saves[reg], restores[reg]))

    # Slot uniqueness: each save slot used by AT MOST one register.
    # Two registers sharing a slot means the second save overwrites
    # the first -- restore would pull a corrupt value.
    slot_to_regs: dict[str, list[str]] = {}
    for reg, slot in saves.items():
        slot_to_regs.setdefault(slot, []).append(reg)
    slot_collisions = {s: regs for s, regs in slot_to_regs.items() if len(regs) > 1}

    # Minimum required save set.  V1.71 isr_entry must save at least
    # these registers -- the direct ir_rc5_decode path modifies them.
    # An empty save+restore
    # block would be "balanced" but catastrophic -- this gate makes
    # that case fail explicitly.
    required_saves = {"STATUS", "W", "BSR", "FSR0L", "FSR0H"}
    missing_required = required_saves - saved

    msg_parts: list[str] = []
    if saved_not_restored:
        msg_parts.append(
            f"saved but not restored: {sorted(saved_not_restored)}"
        )
    if restored_not_saved:
        msg_parts.append(
            f"restored but not saved: {sorted(restored_not_saved)}"
        )
    if slot_mismatches:
        msg_parts.append(
            "save-slot != restore-slot: "
            + ", ".join(f"{reg}: {s} vs {r}" for reg, s, r in slot_mismatches)
        )
    if slot_collisions:
        msg_parts.append(
            "two registers sharing the same save slot: "
            + ", ".join(f"{s}: {', '.join(regs)}" for s, regs in slot_collisions.items())
        )
    if missing_required:
        msg_parts.append(
            f"missing required saves: {sorted(missing_required)} "
            f"(ISR paths depend on these being saved)"
        )
    assert not msg_parts, (
        "isr_entry save/restore imbalance:\n  "
        + "\n  ".join(msg_parts)
        + "\n\nProlog saves: " + ", ".join(f"{r}={s}" for r, s in sorted(saves.items()))
        + "\nEpilog restores: " + ", ".join(f"{r}={s}" for r, s in sorted(restores.items()))
    )


def test_t1_4b_isr_context_funcs_dont_use_unsaved_registers() -> None:
    """ISR-context functions must not write to FSR1*, FSR2*, PRODL/H,
    TBLPTR*, TABLAT, or PCLATH/U -- isr_entry doesn't save these,
    and foreground routinely uses them.

    Foreground diag-renderer walks use FSR1.  Any ISR-context helper that
    touches it can silently corrupt the foreground walk pointer.

    Reads of the unsaved registers are also flagged because reading
    POSTINC1/PREINC1/POSTDEC1 modifies FSR1 as a side effect.

    The legacy ir_rc5_decode body is called synchronously from isr_entry, so
    the ISR save/restore budget is still pinned by this test.
    """
    text = V171_CONTROL_ASM.read_text(encoding="utf-8")
    # Pattern: any instruction whose operand is one of the unsaved
    # registers.  Word-boundary anchored to avoid matching e.g.
    # "FSR1L_save" if that were ever introduced.
    unsaved_alt = "|".join(
        re.escape(r) for r in sorted(_UNSAVED_REGISTERS, key=len, reverse=True)
    )
    unsaved_pattern = re.compile(rf"\b(?:{unsaved_alt})\b")

    violations: list[tuple[str, int, str, str]] = []
    for func in _ISR_CONTEXT_FUNCS:
        try:
            start_lineno, _, body = _function_body(text, func)
        except AssertionError:
            # Function not present (e.g., feature not yet implemented
            # in the canonical source).  Skip silently.
            continue
        for offset, raw_line in enumerate(body):
            # Strip comments before searching.
            instr = raw_line.split(";", 1)[0]
            if not instr.strip():
                continue
            for m in unsaved_pattern.finditer(instr):
                reg = m.group(0)
                violations.append((func, start_lineno + offset, reg, raw_line.strip()))

    assert not violations, (
        "ISR-context function references an unsaved register:\n"
        + "\n".join(
            f"  {func} @ line {ln}: uses {reg}\n      {body}"
            for func, ln, reg, body in violations
        )
        + "\n\nisr_entry's prologue saves only W/STATUS/BSR/FSR0L/FSR0H.\n"
        "Touching any other register inside the ISR (or its directly-\n"
        "called helpers) silently corrupts foreground state when the\n"
        "ISR returns.  Either:\n"
        "  (a) Don't use the register -- rework via FSR0 / Common_RAM.\n"
        "  (b) Save and restore it explicitly in isr_entry's pro/epilogue.\n"
        "Option (a) is strongly preferred -- option (b) extends the\n"
        "ISR latency budget."
    )
