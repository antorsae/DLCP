#!/usr/bin/env python3
"""check_gpsim_excision.py — regression gate against re-introducing gpsim.

The gpsim retirement (PF.4 phases 1 + 2) is complete:

  Phase 1 (commit 5a56279 + 802e932 AST walker): deleted 30 gpsim-only
  test files + 14 gpsim-only operator scripts.

  Phase 2 (commits a049114, abf5db6, b915d35 plan + batches 1-9, ending
  at the e023c01 wrapper deletion): surgically migrated 31 dual_supported
  files off the 6 gpsim wrapper modules, then deleted the wrappers along
  with the 3 Category-A test files that solely exercised them.

This script now serves as a regression gate.  It scans the entire
working tree for any of the following and exits non-zero if anything
is found:

  * imports of the 6 deleted wrapper modules
    (chain_gpsim, control_gpsim, wire_chain_gpsim, main_gpsim,
     main_gpsim_timer3, gpsim — the gpsim-binary locator).
  * references to any of the deleted operator scripts.
  * any of the GPSIM_XTC_* constants (deleted from src/dlcp_fw/paths.py).

Exit codes:
    0 — clean.  No live gpsim references in the codebase.
    1 — at least one re-introduction found; details printed to stderr.

Run:
    .venv_ep0/bin/python scripts/check_gpsim_excision.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# 6 wrapper modules deleted in commit e023c01 (PF.4 phase 2 batch 9).
DELETED_WRAPPER_MODULES: tuple[str, ...] = (
    "chain_gpsim",
    "control_gpsim",
    "wire_chain_gpsim",
    "main_gpsim",
    "main_gpsim_timer3",
    "gpsim",
)

# Operator scripts deleted in PF.4 phase 1 (commit 5a56279).
DELETED_OPERATOR_SCRIPTS: tuple[str, ...] = (
    "gpsim_tui_simulator.py",
    "gpsim_menu_command_audit.py",
    "gpsim_lcd_capture_decode.py",
    "gpsim_headless_chain_diagnose.py",
    "test_full_boot.py",
    "test_button_inject.py",
    "simctl.py",
    "probe_baudcon_mapping.py",
    "probe_v171_layer2_chain.py",
    "capture_v171_early_boot_parity.py",
    "capture_gpsim_ground_truth.py",
    "run_phase0_blessing.py",
    "replay_ground_truth.py",
    "check_ground_truth_capture.py",
)

# Constants removed from src/dlcp_fw/paths.py in PF.4 phase 2 batch 9
# follow-up.  Any re-introduction must trip this gate.
DELETED_PATH_CONSTANTS: tuple[str, ...] = (
    "GPSIM_XTC_SOURCE_DIR",
    "GPSIM_XTC_ARTIFACTS_DIR",
    "GPSIM_XTC_BUILD_DIR",
    "GPSIM_XTC_BIN_DIR",
    "GPSIM_XTC_BINARY",
    "GPSIM_XTC_COMPAT_BINARY",
    "GPSIM_XTC_BUILD_BINARY",
    "GPSIM_XTC_MODULE_DIR",
)

# Skip these directories when scanning.
SKIP_DIRS: tuple[str, ...] = (
    ".git",
    ".venv_ep0",
    ".venv",
    "__pycache__",
    "vendor",
    "artifacts",
    ".pytest_cache",
    ".ruff_cache",
    "target",
    "node_modules",
)


def _iter_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in SKIP_DIRS for part in path.parts):
            continue
        # Skip the gate script itself — it documents the deleted names.
        if path.resolve() == Path(__file__).resolve():
            continue
        yield path


def _scan_imports(files) -> list[tuple[Path, int, str]]:
    """Find imports of deleted wrapper modules.

    Catches both shapes:
      from dlcp_fw.sim.<wrapper> import ...
      import dlcp_fw.sim.<wrapper>
      from dlcp_fw.sim import <wrapper>            (single)
      from dlcp_fw.sim import (..., <wrapper>, ...)  (parenthesized list)
    """
    wrappers = "|".join(DELETED_WRAPPER_MODULES)
    # Form A: dotted-path import.
    pat_dotted = re.compile(
        rf"\b(?:from|import)\s+dlcp_fw\.sim\.({wrappers})\b"
    )
    # Form B: package re-export import.  Matches the wrapper name as a
    # bare identifier inside a `from dlcp_fw.sim import ...` clause,
    # whether single-line or parenthesized.  We track being inside a
    # `from dlcp_fw.sim import (` block via simple state.
    pat_from_import_open = re.compile(r"\bfrom\s+dlcp_fw\.sim\s+import\s+(.*)$")
    pat_wrapper_name = re.compile(rf"\b({wrappers})\b")
    hits: list[tuple[Path, int, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        in_paren_block = False
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pat_dotted.search(line):
                hits.append((path, lineno, line.rstrip()))
                continue
            m = pat_from_import_open.search(line)
            if m:
                tail = m.group(1).strip()
                # Open-paren multi-line import.
                if tail.startswith("("):
                    in_paren_block = True
                    if pat_wrapper_name.search(tail):
                        hits.append((path, lineno, line.rstrip()))
                else:
                    in_paren_block = False
                    if pat_wrapper_name.search(tail):
                        hits.append((path, lineno, line.rstrip()))
                continue
            if in_paren_block:
                if pat_wrapper_name.search(line):
                    hits.append((path, lineno, line.rstrip()))
                if ")" in line:
                    in_paren_block = False
    return hits


def _scan_path_constants(files) -> list[tuple[Path, int, str]]:
    """Find references to deleted GPSIM_XTC_* constants."""
    names = "|".join(DELETED_PATH_CONSTANTS)
    pat = re.compile(rf"\b({names})\b")
    hits: list[tuple[Path, int, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if pat.search(line):
                hits.append((path, lineno, line.rstrip()))
    return hits


def _scan_operator_scripts(files) -> list[tuple[Path, int, str]]:
    """Find IMPORTS or shell invocations of deleted operator scripts.

    Skip historical mentions in docstrings/comments — those are
    deletion-history notes that future readers benefit from.  Only
    flag a re-introduction at import time or as a subprocess argument,
    which is the only shape that would resurrect a deleted script.
    """
    bare_names = [n[:-3] for n in DELETED_OPERATOR_SCRIPTS if n.endswith(".py")]
    bare_names_pat = "|".join(re.escape(n) for n in bare_names)
    # Match `import scripts.<name>`, `from scripts.<name>`, or
    # `python scripts/<name>.py` shell invocations.
    pat = re.compile(
        rf"\b(?:import\s+scripts\.|from\s+scripts\.)({bare_names_pat})\b"
        rf"|scripts/({bare_names_pat})\.py\b(?!\s*\)|\s*`)"
    )
    hits: list[tuple[Path, int, str]] = []
    for path in files:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.lstrip()
            # Skip commented lines and docstring-style markers entirely;
            # those are documentation, not re-introduction.
            if stripped.startswith("#") or stripped.startswith('"') or stripped.startswith("'"):
                continue
            if pat.search(line):
                hits.append((path, lineno, line.rstrip()))
    return hits


def main() -> int:
    files = list(_iter_python_files(REPO_ROOT))
    wrapper_hits = _scan_imports(files)
    constant_hits = _scan_path_constants(files)
    operator_hits = _scan_operator_scripts(files)

    if not (wrapper_hits or constant_hits or operator_hits):
        print("gpsim retirement clean: no live references found.")
        print(f"  scanned {len(files)} python files.")
        return 0

    if wrapper_hits:
        print("\nIMPORT REGRESSIONS — gpsim wrapper modules re-introduced:",
              file=sys.stderr)
        for path, lineno, line in wrapper_hits:
            print(f"  {path.relative_to(REPO_ROOT)}:{lineno}: {line}",
                  file=sys.stderr)

    if constant_hits:
        print("\nCONSTANT REGRESSIONS — GPSIM_XTC_* constants re-introduced:",
              file=sys.stderr)
        for path, lineno, line in constant_hits:
            print(f"  {path.relative_to(REPO_ROOT)}:{lineno}: {line}",
                  file=sys.stderr)

    if operator_hits:
        print("\nSCRIPT REGRESSIONS — deleted operator scripts re-introduced:",
              file=sys.stderr)
        for path, lineno, line in operator_hits:
            print(f"  {path.relative_to(REPO_ROOT)}:{lineno}: {line}",
                  file=sys.stderr)

    return 1


if __name__ == "__main__":
    sys.exit(main())
