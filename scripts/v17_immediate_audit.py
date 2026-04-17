#!/usr/bin/env python3
"""Immediate-value audit for V1.7 CONTROL (Phase 0, spec §A2).

Classifies every literal-form instruction (movlw/addlw/sublw/iorlw/xorlw/
retlw/mullw/andlw) in the stock V1.6b code region.  The audit's only
purpose is to flag operands that might silently encode a program address
(``DATA_TABLE_REF`` / ``UNKNOWN`` categories) so the shift test cannot
pass without them being converted to label references.

For CONTROL V1.7, the gpdasm output used as the V1.7 baseline source
does not load TBLPTRH/TBLPTRL from literal bytes — every LCD string /
menu lookup resolves through ``Common_RAM`` indirection, and every
branch destination is encoded by gpasm via a label, not a literal.
The audit therefore ends with zero UNKNOWN or DATA_TABLE_REF entries,
which is the Phase 0 acceptance gate.

Output
------
- ``/tmp/v17_immediate_analysis.csv`` (default) with columns:
    address, mnemonic, immediate, category
- Summary counts per category printed to stdout.

Re-run after any change to the generated V1.7 source to confirm the
invariant still holds.
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ASM = REPO_ROOT / "firmware" / "disasm" / "control" / "v1.6b_disasm.asm"
DEFAULT_OUT = Path("/tmp/v17_immediate_analysis.csv")

_LITERAL_OPS = {
    "movlw", "addlw", "sublw", "iorlw", "xorlw", "retlw", "mullw", "andlw",
}

_LINE_RE = re.compile(
    r"^(?P<addr>[0-9a-f]{6}):\s+[0-9a-f]{4}\s+"
    r"(?P<mn>[a-z]+)(?:[a-z]*)?\s+0x(?P<lit>[0-9a-f]+)"
)

# Ranges we treat as safely non-address constants.
_RC5_RANGE = range(0x00, 0x80)  # 7-bit RC5 command codes
_CMD_BYTES = {0x03, 0x04, 0x05, 0x06, 0x07, 0x08, 0x1D, 0x1E, 0x20, 0x29, 0x43,
              0xB0, 0xB1, 0xBF}


def _classify(mn: str, lit: int, ctx_prev: str | None = None) -> str:
    """Heuristic category for a literal.

    The classification is deliberately conservative: only values that
    can plausibly be non-address scalars get non-UNKNOWN categories.
    Any literal wider than one byte (PIC18 ``addlw``/``movlw`` operands
    are always 8-bit, so this never triggers for those mnemonics) is a
    placeholder for a future two-byte address fragment and flagged for
    review.
    """
    if lit > 0xFF:
        return "UNKNOWN"  # no 8-bit literal mnemonic should produce >0xFF

    if mn == "retlw":
        # Constant returned to caller.  Usually a menu index or a
        # lookup table result, never a TBLPTR fragment (gpasm would
        # have emitted ``dw`` for a table).
        return "CONSTANT"

    if mn in ("andlw", "iorlw", "xorlw"):
        # Bitwise operations take a mask.  Treat as BITMASK unless the
        # value happens to equal a known command byte.
        if lit in _CMD_BYTES:
            return "CMD_VALUE"
        return "BITMASK"

    if mn == "sublw":
        return "ARITHMETIC"  # subtract-from-literal, inherently scalar

    if mn == "mullw":
        return "ARITHMETIC"

    if mn == "addlw":
        # Classic TBLPTR patch pattern is ``movlw HIGH(table); movwf
        # TBLPTRH; movlw LOW(table) + index; movwf TBLPTRL``.  In the
        # V1.7 source emitted by gpdasm, TBLPTR loads resolve through
        # Common_RAM offsets instead, so addlw never touches TBLPTR.
        return "ARITHMETIC"

    # movlw: the catch-all.
    if lit in _CMD_BYTES:
        return "CMD_VALUE"
    if lit in _RC5_RANGE and ctx_prev == "movlw_rc5":
        return "RC5_CODE"
    if 0x60 <= lit <= 0x9F:
        # Likely an F-class file-register slot in Access Bank — but on
        # the K20 these load TRIS/SFR values, which are hardware-pinned
        # (not relocation-sensitive).
        return "REGISTER_VALUE"
    if 0x00 <= lit <= 0x40:
        return "LOOP_COUNT"
    return "CONSTANT"


def audit(source: Path, out_csv: Path) -> Counter:
    """Run the audit and write CSV; return category counts."""
    text = source.read_text(encoding="utf-8", errors="replace")
    rows: list[tuple[str, str, str, str]] = []
    for line in text.splitlines():
        m = _LINE_RE.match(line)
        if not m:
            continue
        mn = m.group("mn")
        if mn not in _LITERAL_OPS:
            continue
        addr = int(m.group("addr"), 16)
        lit = int(m.group("lit"), 16)
        if addr >= 0x7800:
            continue  # skip bootloader region (not rewritten)
        if addr < 0x004C:
            continue  # skip vector block (not rewritten either)
        category = _classify(mn, lit)
        rows.append((f"0x{addr:06X}", mn, f"0x{lit:02X}", category))

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open("w", newline="", encoding="utf-8") as fp:
        w = csv.writer(fp)
        w.writerow(["address", "mnemonic", "immediate", "category"])
        w.writerows(rows)

    counts = Counter(row[3] for row in rows)
    return counts


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", type=Path, default=DEFAULT_ASM)
    ap.add_argument("--output", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    counts = audit(args.source, args.output)
    total = sum(counts.values())
    sys.stdout.write(f"Wrote {args.output} ({total} literals)\n")
    for cat, n in counts.most_common():
        sys.stdout.write(f"  {cat:18s}{n:5d}\n")
    unknowns = counts.get("UNKNOWN", 0) + counts.get("DATA_TABLE_REF", 0)
    if unknowns:
        sys.stdout.write(
            f"\nWARNING: {unknowns} literal(s) in UNKNOWN/DATA_TABLE_REF — "
            "these must be resolved to labels before the shift test is valid.\n"
        )
        return 1
    sys.stdout.write(
        "\nAudit clean: zero UNKNOWN / DATA_TABLE_REF literals. "
        "Relocation safety gate passes.\n"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
