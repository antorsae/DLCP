"""Annotate gpdasm disassembly files with semantic names.

Reads SEMANTIC_FUNCTION_MAP.md, then produces .annotated.asm copies of each
disassembly file with:
  - block comments above function/label definitions
  - inline comments on call/bra/goto/rcall instructions
"""

from __future__ import annotations

import argparse
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from dlcp_fw.paths import (
    CONTROL_DISASM_V14,
    CONTROL_DISASM_V15B,
    CONTROL_DISASM_V16B,
    MAIN_DISASM,
    SEMANTIC_FUNCTION_MAP,
)

SEMANTIC_MAP_PATH = SEMANTIC_FUNCTION_MAP

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class SemanticEntry:
    auto_name: str
    semantic_name: str
    confidence: str
    evidence: str


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

# Sections whose tables contain function_NNN / label_NNN mappings.
_RELEVANT_SECTIONS = frozenset({
    "MAIN Functions",
    "MAIN Labels",
    "CONTROL Functions",
    "CONTROL Labels",
})

_SECTION_RE = re.compile(r'^##\s+(.+)')
_ROW_RE = re.compile(
    r'^\|\s*(function_\d+|label_\d+)\s*\|'   # auto-name
    r'\s*`([^`]+)`\s*\|'                       # semantic name
    r'\s*[^|]*\|'                               # address (ignored — match by name)
    r'\s*(\w+)\s*\|'                            # confidence
    r'\s*(.*?)\s*\|$'                           # evidence
)

# Also match the version-qualified bit map rows that use the pattern:
#   V1.4: `name`; V1.5b+: `name2`
# These don't start with function_/label_ so they're naturally skipped.


def parse_semantic_map(
    md_path: Path = SEMANTIC_MAP_PATH,
) -> tuple[dict[str, SemanticEntry], dict[str, SemanticEntry]]:
    """Parse SEMANTIC_FUNCTION_MAP.md → (main_map, control_map)."""
    main_map: dict[str, SemanticEntry] = {}
    control_map: dict[str, SemanticEntry] = {}

    current_section: str | None = None
    text = md_path.read_text(encoding="utf-8")

    for line in text.splitlines():
        # Track which ## section we're in.
        m = _SECTION_RE.match(line)
        if m:
            heading = m.group(1).strip()
            # Strip trailing content like "(PIC18F2455)".
            for name in _RELEVANT_SECTIONS:
                if heading.startswith(name):
                    current_section = name
                    break
            else:
                current_section = None
            continue

        if current_section is None:
            continue

        m = _ROW_RE.match(line)
        if not m:
            continue

        entry = SemanticEntry(
            auto_name=m.group(1),
            semantic_name=m.group(2),
            confidence=m.group(3),
            evidence=m.group(4),
        )

        target = main_map if "MAIN" in current_section else control_map
        # First occurrence wins (avoid ISR-table duplicates overwriting).
        if entry.auto_name not in target:
            target[entry.auto_name] = entry

    return main_map, control_map


# ---------------------------------------------------------------------------
# Annotation engine
# ---------------------------------------------------------------------------

_DEF_RE = re.compile(r'^(function_\d+|label_\d+):(.*)$')
_REF_RE = re.compile(r'(call|rcall|goto|bra)\s+(function_\d+|label_\d+)')


def _first_sentence(text: str, max_len: int = 120) -> str:
    """Extract the first sentence, truncating if needed."""
    # Cut at first ". " or end-of-string period.
    m = re.search(r'\.\s', text)
    s = text[:m.start() + 1] if m else text
    if len(s) > max_len:
        s = s[:max_len - 1] + "\u2026"
    return s


def _format_block_comment(entry: SemanticEntry) -> list[str]:
    """Two-line block comment for a definition site."""
    lines = [f"; === {entry.semantic_name} [{entry.confidence}] ==="]
    if entry.evidence:
        lines.append(f"; {_first_sentence(entry.evidence)}")
    return lines


def _append_inline(line: str, sem_name: str) -> str:
    """Append [semantic_name] to a reference line."""
    stripped = line.rstrip()
    if ";" in stripped:
        return f"{stripped}  [{sem_name}]"
    return f"{stripped}    ; [{sem_name}]"


@dataclass
class AnnotationStats:
    total_lines: int = 0
    definitions: int = 0
    references: int = 0


def annotate_file(
    input_path: Path,
    output_path: Path,
    sem_map: dict[str, SemanticEntry],
    *,
    dry_run: bool = False,
) -> AnnotationStats:
    """Read *input_path*, write annotated copy to *output_path*."""
    stats = AnnotationStats()
    out_lines: list[str] = []
    text = input_path.read_text(encoding="utf-8", errors="replace")

    for line in text.splitlines():
        stats.total_lines += 1

        # --- definition site ---
        dm = _DEF_RE.match(line)
        if dm:
            auto_name = dm.group(1)
            entry = sem_map.get(auto_name)
            if entry:
                stats.definitions += 1
                out_lines.extend(_format_block_comment(entry))
            out_lines.append(line)
            continue

        # --- reference site ---
        rm = _REF_RE.search(line)
        if rm:
            target_name = rm.group(2)
            entry = sem_map.get(target_name)
            if entry:
                stats.references += 1
                line = _append_inline(line, entry.semantic_name)
            out_lines.append(line)
            continue

        out_lines.append(line)

    if not dry_run:
        output_path.write_text("\n".join(out_lines) + "\n", encoding="utf-8")

    return stats


# ---------------------------------------------------------------------------
# Targets
# ---------------------------------------------------------------------------

_TARGETS = {
    "main": ("MAIN", MAIN_DISASM),
    "v14": ("CONTROL", CONTROL_DISASM_V14),
    "v15b": ("CONTROL", CONTROL_DISASM_V15B),
    "v16b": ("CONTROL", CONTROL_DISASM_V16B),
}


def _output_path(p: Path) -> Path:
    return p.with_suffix(".annotated.asm")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Annotate disassembly files with semantic function/label names.",
    )
    parser.add_argument(
        "--file",
        choices=list(_TARGETS),
        help="process only the specified file (default: all)",
    )
    parser.add_argument("--dry-run", action="store_true", help="parse and match but do not write")
    parser.add_argument("--quiet", action="store_true", help="suppress non-error output")
    args = parser.parse_args(argv)

    main_map, control_map = parse_semantic_map()
    maps = {"MAIN": main_map, "CONTROL": control_map}

    if not args.quiet:
        print(f"Parsed semantic map: {len(main_map)} MAIN + {len(control_map)} CONTROL entries")

    targets = {args.file: _TARGETS[args.file]} if args.file else _TARGETS
    ok = True

    for key, (section, disasm_path) in targets.items():
        if not disasm_path.exists():
            print(f"  SKIP {key}: {disasm_path} not found")
            ok = False
            continue

        out = _output_path(disasm_path)
        stats = annotate_file(disasm_path, out, maps[section], dry_run=args.dry_run)

        if not args.quiet:
            verb = "would write" if args.dry_run else "wrote"
            print(
                f"  {key}: {stats.definitions} definitions, "
                f"{stats.references} references annotated "
                f"({stats.total_lines} lines) → {verb} {out.name}"
            )

    return 0 if ok else 1
