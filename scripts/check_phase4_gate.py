#!/usr/bin/env python3
"""P4.gate -- final Phase-4 gate verifier.

Per `docs/SIM_REWRITE_RUST_PROGRESS.md` P4.gate:

    asserts `DLCP_SIM_BACKEND=rust pytest tests/sim` is green
    AND wall-clock < 60 s.

The "green" predicate as enforced here is `pytest exit == 0`.
That covers failed tests and errors but does NOT inspect for
unexpected-pass xfails (XPASS): the repo does not set
`xfail_strict` globally and has explicit non-strict xfails, so
an XPASS does not propagate to a non-zero pytest exit. Skipped
tests (still on the P4.5/4.6/4.7 migration backlog) and expected
xfails (documented firmware bugs) do NOT fail the gate.

Wall-clock budget: 60 seconds end-to-end pytest invocation. This
includes pytest's own collection / fixture / xdist startup overhead.

Exit codes:
    0 -- gate green AND wall-clock under 60 s
    1 -- gate failed (non-zero pytest exit; see PYTEST_EXIT_CODES
         in the report text for which sub-class)
    2 -- gate green BUT wall-clock over 60 s (timing regression)

Implementation notes:
    * Forces `DLCP_SIM_BACKEND=rust` to make the gate result
      independent of the caller's environment.
    * Uses `-n 16` per the P4.x verify pattern (matches the rest
      of the ledger).
    * Reports the pytest exit code symbolically when nonzero so a
      CI runner can quickly tell test-failure (1) from no-tests-
      collected (5) or usage-error (4) without re-reading the
      pytest log.
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
PYTHON = REPO_ROOT / ".venv_ep0" / "bin" / "python"

WALL_CLOCK_BUDGET_SEC = 60.0

# Symbolic names for nonzero pytest exit codes per pytest docs.
# We surface these in the failure report so a CI runner can
# distinguish a test-suite regression (1) from harness-level
# breakage (4 / 5 / >=128) without re-reading the pytest log.
PYTEST_EXIT_CODES: dict[int, str] = {
    1: "tests collected but at least one failed",
    2: "test execution interrupted by the user (Ctrl-C)",
    3: "internal error inside pytest itself",
    4: "pytest CLI usage error",
    5: "no tests were collected (likely a collection-time import error)",
}


def main() -> int:
    if not PYTHON.exists():
        print(f"ERROR: python interpreter not found at {PYTHON}", file=sys.stderr)
        return 1

    cmd = [str(PYTHON), "-m", "pytest", "tests/sim", "-n", "16", "-q"]
    env = os.environ.copy()
    env["DLCP_SIM_BACKEND"] = "rust"

    print(f"+ DLCP_SIM_BACKEND=rust {' '.join(cmd)}", flush=True)
    started = time.monotonic()
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    elapsed = time.monotonic() - started

    print()
    print(f"P4.gate wall-clock: {elapsed:.1f} s (budget: {WALL_CLOCK_BUDGET_SEC:.0f} s)")
    print(f"P4.gate pytest exit: {cp.returncode}")

    if cp.returncode != 0:
        meaning = PYTEST_EXIT_CODES.get(
            cp.returncode,
            f"unknown pytest exit code {cp.returncode}",
        )
        print(
            f"P4.gate FAIL: pytest exited {cp.returncode} ({meaning}).",
            file=sys.stderr,
        )
        return 1

    if elapsed > WALL_CLOCK_BUDGET_SEC:
        print(
            f"P4.gate TIMING REGRESSION: wall-clock {elapsed:.1f} s "
            f"exceeds budget {WALL_CLOCK_BUDGET_SEC:.0f} s. "
            "Use --durations=20 to identify the slow tests; the spec target "
            "was set assuming a leaner test corpus post-P4.9.",
            file=sys.stderr,
        )
        return 2

    print("P4.gate OK: green AND under wall-clock budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
