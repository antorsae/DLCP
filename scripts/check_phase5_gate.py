#!/usr/bin/env python3
"""P5.gate -- Phase-5 gate verifier.

Per `docs/SIM_REWRITE_RUST_SPEC.md` §9 the Phase-5 exit gate is:

    cargo test -p dlcp-sim --test snapshot_property --release
    .venv_ep0/bin/python -m pytest tests/sim/soak -n 16 -q
    .venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 5

This script wraps the first two checks (the third is the ledger
walker, which calls back into THIS script via the P5.gate
verify-command line and would recurse infinitely if we ran it
ourselves).  Each sub-check is reported with a symbolic exit-code
classification so a CI runner can tell test-failure from
no-tests-collected from harness breakage without re-reading the
log.

Sub-checks:

  1. Property tests (P5.2 artifact):
     `cargo test -p dlcp-sim --test snapshot_property --release`
     Runs the 6 proptest properties (64 cases each, both empty
     chain and V1.71 chain).  A property failure surfaces with
     proptest's standard shrink-output protocol; this script
     only checks the cargo exit code.

  2. Soak suite (P5.4 artifact):
     `pytest tests/sim/soak -n 16 -q`
     Runs 5 Rust soak `#[test]`s, each looping ≥ 10⁴ scenarios
     against a deterministic seed corpus.  Failures dump
     `artifacts/sim_soak_failures/<test>_seed_<idx>.json` for
     triage with `dlcp-sim replay`.

The gate is green iff BOTH sub-checks return exit 0.

Exit codes:
    0 -- gate green.
    1 -- property test (sub-check 1) failed.
    2 -- soak suite (sub-check 2) failed.
    3 -- both sub-checks failed.
    4 -- harness breakage (cargo / pytest binary missing,
         CWD not the repo root, etc.).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Symbolic names for nonzero pytest exit codes per pytest docs.
# Mirrors `scripts/check_phase4_gate.py`.
PYTEST_EXIT_CODES: dict[int, str] = {
    1: "tests collected but at least one failed",
    2: "test execution interrupted by the user (Ctrl-C)",
    3: "internal error inside pytest itself",
    4: "pytest CLI usage error",
    5: "no tests were collected",
}


def _resolve_python() -> str:
    """Pick the venv interpreter.  In linked worktrees the .venv
    lives under the shared tools-root checkout, so we walk up to
    git's common-dir parent if `.venv_ep0` is not in REPO_ROOT.
    """
    here = REPO_ROOT / ".venv_ep0" / "bin" / "python"
    if here.exists():
        return str(here)
    try:
        common = subprocess.check_output(
            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
            cwd=str(REPO_ROOT),
            text=True,
        ).strip()
        tools_root = Path(common).resolve().parent
        candidate = tools_root / ".venv_ep0" / "bin" / "python"
        if candidate.exists():
            return str(candidate)
    except subprocess.CalledProcessError:
        pass
    # Last resort: rely on the caller's PATH.
    return sys.executable


def _check_harness(python: str) -> int:
    """Validate the local environment can run both sub-checks
    BEFORE we burn 2 minutes on the soak.  A pytest / xdist
    failure must surface as harness-error (exit 4), not as a
    false soak failure (exit 2) -- otherwise the wrapper's
    exit-code contract is meaningless.
    """
    if shutil.which("cargo") is None:
        print(
            "P5.gate FAIL [harness]: cargo is not on PATH; install Rust "
            "or `source $HOME/.cargo/env` before re-running",
            file=sys.stderr,
        )
        return 4
    # Probe the resolved Python: must import pytest (P5.4
    # uses pytest) AND xdist (P5.4 invokes `-n 16`).  We do
    # both in a single subprocess so the failure message
    # names whichever module is missing.
    cp = subprocess.run(
        [
            python,
            "-c",
            "import pytest, xdist  # noqa: F401",
        ],
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        print(
            f"P5.gate FAIL [harness]: {python!r} cannot import pytest + "
            "pytest-xdist (needed for `pytest tests/sim/soak -n 16`).  "
            f"stderr: {cp.stderr.strip()!r}",
            file=sys.stderr,
        )
        return 4
    return 0


def _run_property_tests() -> int:
    cmd = [
        "cargo",
        "test",
        "-p",
        "dlcp-sim",
        "--test",
        "snapshot_property",
        "--release",
    ]
    print(f"+ [P5.2] {' '.join(cmd)}", flush=True)
    started = time.monotonic()
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT))
    elapsed = time.monotonic() - started
    if cp.returncode != 0:
        print(
            f"P5.gate FAIL [P5.2]: cargo test --test snapshot_property "
            f"exited {cp.returncode} after {elapsed:.1f} s",
            file=sys.stderr,
        )
        return 1
    print(f"  P5.2 PASS in {elapsed:.1f} s", flush=True)
    return 0


def _run_soak_suite(python: str) -> int:
    cmd = [
        python,
        "-m",
        "pytest",
        "tests/sim/soak",
        "-n",
        "16",
        "-q",
    ]
    env = os.environ.copy()
    env.setdefault("DLCP_SIM_BACKEND", "rust")
    print(f"+ [P5.4] DLCP_SIM_BACKEND={env['DLCP_SIM_BACKEND']} "
          f"{' '.join(cmd)}", flush=True)
    started = time.monotonic()
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    elapsed = time.monotonic() - started
    if cp.returncode != 0:
        meaning = PYTEST_EXIT_CODES.get(
            cp.returncode, f"unknown pytest exit code {cp.returncode}"
        )
        print(
            f"P5.gate FAIL [P5.4]: pytest tests/sim/soak exited "
            f"{cp.returncode} ({meaning}) after {elapsed:.1f} s",
            file=sys.stderr,
        )
        return 2
    print(f"  P5.4 PASS in {elapsed:.1f} s", flush=True)
    return 0


def main() -> int:
    python = _resolve_python()
    rc = _check_harness(python)
    if rc != 0:
        return rc

    rc1 = _run_property_tests()
    rc2 = _run_soak_suite(python)
    if rc1 == 0 and rc2 == 0:
        print("P5.gate GREEN")
        return 0
    if rc1 != 0 and rc2 != 0:
        return 3
    if rc1 != 0:
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
