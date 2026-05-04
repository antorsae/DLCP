"""P5.4 soak harness — drive `crates/dlcp-sim/tests/snapshot_soak.rs`.

Per `docs/SIM_REWRITE_RUST_SPEC.md` §9 P5.4 the soak suite under
`tests/sim/soak/` runs ≥ 10⁴ scenarios per soak test.  The actual
loop lives in Rust (`crates/dlcp-sim/tests/snapshot_soak.rs`)
where each scenario is ~125 µs of decode + a handful of stimuli;
running 10⁴ scenarios from Python directly via PyO3 would also
work but adds the GIL + FFI overhead per scenario.  Rust loops
finish all five 10⁴-scenario tests in ~2 minutes total wall.

This file is a thin parametrized driver that calls
`cargo test --release -p dlcp-sim --test snapshot_soak <name>`
once per Rust soak test, so `pytest -n 16` parallelises across
the soak tests at the pytest worker level.  Failure dumps land
in `artifacts/sim_soak_failures/` (created by the Rust side); a
test failure here always points at the dumped JSON file by name.

Marked `@pytest.mark.dual_supported` because the soak tests do
not depend on `DLCP_SIM_BACKEND` -- they exercise the Rust
crate directly, so they're meaningful under any backend
selection (rust / dual / gpsim).  Marked `@pytest.mark.slow`
so the fast-subset gate (`pytest -m "not slow"`) skips the
~2-minute soak run.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SOAK_FAILURES_DIR = REPO_ROOT / "artifacts" / "sim_soak_failures"

# The five Rust soak tests in
# `crates/dlcp-sim/tests/snapshot_soak.rs`.  Each runs 10⁴
# scenarios internally and panics with a failure-dump path on
# divergence.
SOAK_TESTS: tuple[str, ...] = (
    "empty_chain_round_trip_soak",
    "empty_chain_replay_determinism_soak",
    "v171_chain_round_trip_soak",
    "v171_chain_replay_determinism_soak",
    "step_split_soak",
)

# Rust soak tests that exercise the V1.71 chain are slow (~2
# minutes wall each) due to the 10⁴ × ~3 ms decode + step path.
# Mark them with a hint so the operator can pick a fast subset.
_V171_TESTS = frozenset({
    "v171_chain_round_trip_soak",
    "v171_chain_replay_determinism_soak",
    "step_split_soak",
})


def _cargo_available() -> bool:
    return shutil.which("cargo") is not None


@pytest.fixture(autouse=True, scope="module")
def _require_cargo() -> None:
    if not _cargo_available():
        pytest.skip(
            "cargo not on PATH; install Rust or `source $HOME/.cargo/env` "
            "before running the soak suite (`tests/sim/soak/`)"
        )


@pytest.mark.dual_supported
@pytest.mark.slow
@pytest.mark.parametrize("test_name", SOAK_TESTS)
def test_rust_snapshot_soak(test_name: str) -> None:
    """Run one Rust soak `#[test]` and assert exit 0.

    The Rust panic message on failure includes the dumped-JSON
    path (`artifacts/sim_soak_failures/<test>_seed_<idx>.json`).
    On failure we surface the last 30 lines of cargo output so
    pytest's traceback shows the panic line + dump path.
    """
    cmd = [
        "cargo",
        "test",
        "--release",
        "-p",
        "dlcp-sim",
        "--test",
        "snapshot_soak",
        test_name,
        "--",
        "--exact",
        "--nocapture",
    ]
    env = os.environ.copy()
    cp = subprocess.run(
        cmd,
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
    )
    if cp.returncode != 0:
        # Show the operator the failing seed + dump path.
        tail = "\n".join(cp.stdout.splitlines()[-30:])
        err_tail = "\n".join(cp.stderr.splitlines()[-30:])
        pytest.fail(
            f"Rust soak test {test_name!r} failed (exit {cp.returncode}).\n"
            f"--- stdout (tail) ---\n{tail}\n"
            f"--- stderr (tail) ---\n{err_tail}\n"
            f"failure dumps: {SOAK_FAILURES_DIR}"
        )
