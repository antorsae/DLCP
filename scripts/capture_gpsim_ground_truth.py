#!/usr/bin/env python3
"""capture_gpsim_ground_truth.py — drive the Phase-0 ground-truth capture.

Runs the sim test suite (or a subset, via passthrough args) under
``--capture-ground-truth`` so the conftest plugin emits per-test
fixtures into ``artifacts/ground_truth/<test_id>/``.

Usage:

    # Sweep the whole sim suite with parallelism:
    .venv_ep0/bin/python scripts/capture_gpsim_ground_truth.py -n 16

    # Capture one test or a glob (anything after `--` is forwarded to
    # pytest verbatim):
    .venv_ep0/bin/python scripts/capture_gpsim_ground_truth.py -- \
        tests/sim/test_v17_chain.py::test_v17_stock_v16b_chain_reaches_display

The script is intentionally a thin wrapper.  Spec §4 lists the
deliverables for the artifact bundle (stimulus.jsonl, snapshots/,
uart_tx_*.jsonl, lcd_final.txt, eeprom_final.bin, summary.json); the
conftest plugin and harness instrumentation produce them.  Sub-tasks
P0.2-P0.4 add each stream incrementally.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGETS = ("tests/sim",)


def _resolve_python() -> str:
    venv = REPO_ROOT / ".venv_ep0" / "bin" / "python"
    if venv.exists():
        return str(venv)
    return sys.executable


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description="Run the sim suite under --capture-ground-truth."
    )
    parser.add_argument(
        "-n",
        dest="parallel",
        default=None,
        help="forward as `-n <N>` to pytest-xdist (parallel workers)",
    )
    parser.add_argument(
        "--no-default-target",
        action="store_true",
        help=(
            "do not implicitly pass tests/sim; useful when you provide "
            "a more specific target via passthrough."
        ),
    )
    parser.add_argument(
        "passthrough",
        nargs=argparse.REMAINDER,
        help="arguments after `--` are forwarded to pytest verbatim",
    )
    args = parser.parse_args(argv)

    cmd: list[str] = [_resolve_python(), "-m", "pytest", "--capture-ground-truth", "-q"]
    if args.parallel is not None:
        cmd.extend(["-n", str(args.parallel)])

    passthrough = args.passthrough[:]
    if passthrough and passthrough[0] == "--":
        passthrough = passthrough[1:]
    if passthrough:
        cmd.extend(passthrough)
    elif not args.no_default_target:
        cmd.extend(DEFAULT_TARGETS)

    print(f"+ {' '.join(cmd)}", flush=True)
    env = os.environ.copy()
    # Force gpsim backend: this script captures GPSIM ground-truth
    # fixtures.  Post-P4.8 the default backend is rust; without
    # this override the capture would silently re-run against the
    # rust engine and the resulting fixture would be mislabelled.
    env["DLCP_SIM_BACKEND"] = "gpsim"
    cp = subprocess.run(cmd, cwd=str(REPO_ROOT), env=env)
    return cp.returncode


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
