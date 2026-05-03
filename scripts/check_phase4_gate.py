#!/usr/bin/env python3
"""P4.gate -- final Phase-4 gate verifier.

Per `docs/SIM_REWRITE_RUST_PROGRESS.md` P4.gate:

    asserts `DLCP_SIM_BACKEND=rust pytest tests/sim` is green
    AND wall-clock < 60 s.

The "green" predicate is interpreted as: zero failed tests, zero
errors, zero unexpected-pass xfails. Skipped tests (still on the
P4.5/4.6/4.7 migration backlog) and expected xfails (documented
firmware bugs) do NOT fail the gate.

Wall-clock budget: 60 seconds end-to-end pytest invocation. This
includes pytest's own collection / fixture / xdist startup overhead.

Exit codes:
    0 -- gate green AND wall-clock under 60 s
    1 -- gate failed (non-zero exit OR failed tests OR errors)
    2 -- gate green BUT wall-clock over 60 s (timing regression)

Implementation notes:
    * Forces `DLCP_SIM_BACKEND=rust` to make the gate result
      independent of the caller's environment.
    * Uses `-n 16` per the P4.x verify pattern (matches the rest
      of the ledger).
    * Captures the full pytest output for the timing-fail report
      so a CI runner can see which tests dominated.
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
        print("P4.gate FAIL: pytest exited non-zero (failed tests / errors).",
              file=sys.stderr)
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
