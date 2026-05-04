#!/usr/bin/env python3
"""P5.3 verifier — assert `dlcp-sim replay` round-trips bit-exact.

Per `docs/SIM_REWRITE_RUST_SPEC.md` §9 P5.3, the replay tool must
write a `.lst`-equivalent trace and (more importantly) reproduce the
post-stimulus snapshot bit-for-bit.

This script generates a synthetic case in a tempdir, runs
`dlcp-sim replay` twice with identical input, asserts both runs
produce identical final snapshots and identical traces.  Then
re-runs once with a deliberately corrupted
`expect_final_snapshot_hex` to assert the mismatch path returns
exit code 3, and once with the actual hex to assert exit code 0.

Exit codes:
    0 — all assertions passed.
    1 — script-level failure (missing binary, file IO, etc.).
    2 — replay tool produced a non-deterministic snapshot or trace.
    3 — mismatch-detection path didn't return nonzero as expected.

Run:
    .venv_ep0/bin/python scripts/check_replay_round_trip.py
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
CLI_BINARY = REPO_ROOT / "target" / "release" / "dlcp-sim"


def fail(code: int, msg: str) -> int:
    print(f"FAIL ({code}): {msg}", file=sys.stderr)
    return code


def ensure_cli_built() -> int | None:
    if CLI_BINARY.exists():
        return None
    print("dlcp-sim binary missing; building release...", file=sys.stderr)
    cp = subprocess.run(
        ["cargo", "build", "--release", "-p", "dlcp-sim-cli"],
        cwd=str(REPO_ROOT),
    )
    if cp.returncode != 0 or not CLI_BINARY.exists():
        return fail(1, "cargo build -p dlcp-sim-cli failed")
    return None


def run_replay(
    case_path: Path,
    *,
    final_snapshot: Path | None = None,
    trace: Path | None = None,
    expect_returncode: int = 0,
) -> subprocess.CompletedProcess[bytes]:
    cmd: list[str] = [str(CLI_BINARY), "replay", str(case_path)]
    if final_snapshot is not None:
        cmd += ["--final-snapshot", str(final_snapshot)]
    if trace is not None:
        cmd += ["--trace", str(trace)]
    cp = subprocess.run(cmd, capture_output=True)
    if cp.returncode != expect_returncode:
        print(cp.stdout.decode(errors="replace"), file=sys.stderr)
        print(cp.stderr.decode(errors="replace"), file=sys.stderr)
        raise SystemExit(
            fail(
                2,
                f"replay returned {cp.returncode}, expected "
                f"{expect_returncode}",
            )
        )
    return cp


def synth_case(workdir: Path, factory: str) -> Path:
    case = {
        "format": "dlcp-sim-replay-v1",
        "initial_factory": factory,
        "initial_snapshot_hex": None,
        "stimuli": [
            {"step_ticks": 2_000_000},
            {"set_uart_blackout": True},
            {"step_ticks": 1_000_000},
            {"set_uart_blackout": False},
            {"step_ticks": 500_000},
        ],
        "expect_final_snapshot_hex": None,
    }
    path = workdir / f"case_{factory}.json"
    path.write_text(json.dumps(case, indent=2))
    return path


def round_trip_check(workdir: Path, factory: str) -> None:
    case_path = synth_case(workdir, factory)
    snap_a = workdir / f"final_a_{factory}.bin"
    snap_b = workdir / f"final_b_{factory}.bin"
    trace_a = workdir / f"trace_a_{factory}.txt"
    trace_b = workdir / f"trace_b_{factory}.txt"

    run_replay(case_path, final_snapshot=snap_a, trace=trace_a)
    run_replay(case_path, final_snapshot=snap_b, trace=trace_b)

    bytes_a = snap_a.read_bytes()
    bytes_b = snap_b.read_bytes()
    if bytes_a != bytes_b:
        raise SystemExit(
            fail(
                2,
                f"factory={factory}: replay non-deterministic "
                f"({len(bytes_a)} vs {len(bytes_b)} bytes)",
            )
        )

    trace_a_text = trace_a.read_text()
    trace_b_text = trace_b.read_text()
    if trace_a_text != trace_b_text:
        raise SystemExit(
            fail(
                2,
                f"factory={factory}: trace differs across replays",
            )
        )

    # Mismatch-detection path: replay the same case with a
    # deliberately corrupted expect_final_snapshot_hex.  The CLI
    # MUST exit 3 (the documented mismatch code).
    bad_case = json.loads(case_path.read_text())
    expected_hex = bytes_a.hex()
    bad_case["expect_final_snapshot_hex"] = (
        ("0" if expected_hex.startswith("f") else "f") + expected_hex[1:]
    )
    bad_path = workdir / f"case_bad_{factory}.json"
    bad_path.write_text(json.dumps(bad_case, indent=2))
    run_replay(bad_path, expect_returncode=3)

    # Positive expect-match: encode actual bytes as the expected
    # hex; CLI must succeed (exit 0).
    good_case = json.loads(case_path.read_text())
    good_case["expect_final_snapshot_hex"] = expected_hex
    good_path = workdir / f"case_good_{factory}.json"
    good_path.write_text(json.dumps(good_case, indent=2))
    run_replay(good_path, expect_returncode=0)

    print(
        f"ok: factory={factory} round-trip + mismatch + match "
        f"({len(bytes_a)} byte snapshot, {len(trace_a_text)} byte trace)"
    )


def main() -> int:
    err = ensure_cli_built()
    if err is not None:
        return err

    workdir = Path(tempfile.mkdtemp(prefix="dlcp_sim_replay_check_"))
    try:
        round_trip_check(workdir, "empty")
        round_trip_check(workdir, "v171_control")
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    print("P5.3 replay round-trip: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
