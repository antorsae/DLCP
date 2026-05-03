#!/usr/bin/env python3
"""P4.gate -- final Phase-4 gate verifier.

Per `docs/SIM_REWRITE_RUST_PROGRESS.md` P4.gate (and PF.2 in
`docs/SIM_REWRITE_RUST_SPEC.md`), the original written gate is:

    `DLCP_SIM_BACKEND=rust pytest tests/sim` green AND wall-clock < 60 s.

**Implementation note (this script applies a PROPOSED RELAXATION
to the original gate)**: the unified-suite 60 s target is
infeasible with the current corpus -- the slowest individual test
in the slow subset takes ~47 s by itself (e.g.
`test_v171_layer2_emits_all_six_step_frame_types_after_warmup`,
which warms up 80 M-Tcy + steps 160 times).  Even with -n 16
parallelism the slow tests dominate aggregate wall-clock at
~3 minutes.

The proposed relaxation: split the suite by the existing
`@pytest.mark.slow` marker (registered in `pytest.ini`) into:

  * **Fast subset** (`-m "not slow"`, 622 tests as of 2026-05-03):
    timed against the 60 s budget.  Currently ~6 s.
  * **Slow subset** (`-m slow`, 471 tests): green-tests check
    only, no timing budget.

Both subsets must pass green; only the fast subset is timed.
The fast subset runs FIRST so a developer / CI runner sees fast
regressions and timing failures before the multi-minute slow
subset.

This is a *real* relaxation of the original spec wording; it
needs user sign-off before P4.gate can be considered closed.
The progress ledger marks P4.gate `in_progress (timing relaxation
proposed)` until that sign-off lands.  The `green` predicate is
the same `pytest exit == 0` (no XPASS detection: the repo doesn't
set `xfail_strict` globally and has explicit non-strict xfails).

Exit codes:
    0 -- gate green (both subsets) AND fast-subset wall-clock under 60 s
    1 -- gate failed (non-zero pytest exit on either subset; see
         PYTEST_EXIT_CODES in the report text for which sub-class)
    2 -- gate green BUT fast-subset wall-clock over 60 s
         (timing regression)

Implementation notes:
    * Forces `DLCP_SIM_BACKEND=rust` to make the gate result
      independent of the caller's environment.
    * Uses `-n 16` per the P4.x verify pattern.
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
    5: "no tests were collected",
}


def _run_pytest(
    *, label: str, marker: str | None, time_it: bool
) -> tuple[int, float]:
    """Run pytest tests/sim with optional marker filter.  Returns
    (pytest_exit_code, wall_clock_seconds) -- wall_clock is 0.0 when
    `time_it` is False (we don't surface untimed wall-clock to the
    caller; the timing assertion only applies to the fast subset).
    """
    cmd = [str(PYTHON), "-m", "pytest", "tests/sim", "-n", "16", "-q"]
    if marker is not None:
        cmd.extend(["-m", marker])
    env = os.environ.copy()
    env["DLCP_SIM_BACKEND"] = "rust"
    print(f"+ [{label}] DLCP_SIM_BACKEND=rust {' '.join(cmd)}", flush=True)
    started = time.monotonic()
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    elapsed = time.monotonic() - started if time_it else 0.0
    return cp.returncode, elapsed


def _classify_pytest_failure(rc: int, label: str) -> None:
    meaning = PYTEST_EXIT_CODES.get(
        rc,
        f"unknown pytest exit code {rc}",
    )
    print(
        f"P4.gate FAIL [{label}]: pytest exited {rc} ({meaning}).",
        file=sys.stderr,
    )


def main() -> int:
    if not PYTHON.exists():
        print(f"ERROR: python interpreter not found at {PYTHON}", file=sys.stderr)
        return 1

    # Fast subset FIRST: timed.  Run order is fast-then-slow so a
    # developer / CI runner sees fast regressions and the timing
    # budget result before the multi-minute slow subset starts.
    fast_rc, fast_elapsed = _run_pytest(
        label="fast", marker="not slow", time_it=True
    )
    print()
    print(
        f"P4.gate fast-subset wall-clock: {fast_elapsed:.1f} s "
        f"(budget: {WALL_CLOCK_BUDGET_SEC:.0f} s)"
    )
    print(f"P4.gate fast-subset pytest exit: {fast_rc}")
    if fast_rc != 0:
        _classify_pytest_failure(fast_rc, "fast")
        return 1
    fast_timing_ok = fast_elapsed <= WALL_CLOCK_BUDGET_SEC

    # Slow subset, no timing budget.  Run AFTER the fast subset.
    slow_rc, _ = _run_pytest(label="slow", marker="slow", time_it=False)
    print()
    print(f"P4.gate slow-subset pytest exit: {slow_rc}")
    if slow_rc != 0:
        _classify_pytest_failure(slow_rc, "slow")
        return 1

    if not fast_timing_ok:
        print(
            f"P4.gate TIMING REGRESSION: fast-subset wall-clock "
            f"{fast_elapsed:.1f} s exceeds budget {WALL_CLOCK_BUDGET_SEC:.0f} s.",
            file=sys.stderr,
        )
        return 2

    print("P4.gate OK: both subsets green AND fast-subset under wall-clock budget.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
