#!/usr/bin/env python3
"""replay_ground_truth.py — verify capture determinism (P0.5).

Walks every directory under ``artifacts/ground_truth/<test>/``, looks
up the originating pytest nodeid from each ``summary.json``, re-runs
the same test with ``--capture-ground-truth`` writing into a temp
directory (via the ``DLCP_GROUND_TRUTH_OUT`` env override on the
conftest plugin), then bit-exact diffs the replayed capture against
the blessed one.

This is approach B from the Phase-0 planning discussion: the test
code itself reproduces harness construction, so the replay does not
need to deserialize harness kwargs from stimulus.jsonl.  The diff
covers:

  * stimulus.jsonl       — events compared as ordered tuples of
                           (kind, harness, payload), ignoring the
                           run-local ``wall_time`` and ``seq``
                           fields (seq is reproducible but adds
                           noise on intentional reorderings).
  * snapshots/*.ram.bin  — bit-exact.
  * snapshots/*.sfr.json — JSON-equal (key/value sets must match).
  * uart_tx_*.jsonl      — bit-exact (per-line JSON; same encoding
                           since the writer sorts keys).
  * lcd_*.txt            — bit-exact.
  * eeprom_*.bin         — bit-exact.

summary.json is not diffed — it carries run-local timestamps and
durations that aren't reproducible.  A test whose original outcome
was ``failed`` or ``error`` is replayed and reported, but failure
of the replay's PYTEST run is treated as "matches the original
outcome" if the original also failed.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_ROOT = REPO_ROOT / "artifacts" / "ground_truth"
DEFAULT_PYTHON = REPO_ROOT / ".venv_ep0" / "bin" / "python"


# stimulus.jsonl fields that vary across runs and must be filtered
# out of the diff.
_STIM_VOLATILE_FIELDS = ("wall_time",)


def _load_stimulus(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out: list[dict] = []
    with path.open(encoding="utf-8") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            out.append(json.loads(line))
    return out


def _normalize_stimulus(events: list[dict]) -> list[dict]:
    norm: list[dict] = []
    for e in events:
        d = {k: v for k, v in e.items() if k not in _STIM_VOLATILE_FIELDS}
        norm.append(d)
    return norm


def _diff_stimulus(blessed: Path, replayed: Path) -> list[str]:
    """Compare stimulus.jsonl (modulo wall_time)."""
    a = _normalize_stimulus(_load_stimulus(blessed))
    b = _normalize_stimulus(_load_stimulus(replayed))
    if a == b:
        return []
    errors: list[str] = []
    if len(a) != len(b):
        errors.append(
            f"stimulus event count differs: blessed={len(a)} replayed={len(b)}"
        )
    for i, (ea, eb) in enumerate(zip(a, b)):
        if ea != eb:
            errors.append(
                f"stimulus event #{i} differs:\n"
                f"  blessed:  {ea!r}\n"
                f"  replayed: {eb!r}"
            )
            if len(errors) >= 5:
                errors.append("  ...further stimulus differences elided")
                break
    return errors


def _diff_binary(label: str, a: Path, b: Path) -> list[str]:
    if not a.exists() and not b.exists():
        return []
    if not a.exists():
        return [f"{label} missing in blessed (only in replayed)"]
    if not b.exists():
        return [f"{label} missing in replayed (only in blessed)"]
    if not filecmp.cmp(str(a), str(b), shallow=False):
        return [
            f"{label} differs ({a.stat().st_size} vs "
            f"{b.stat().st_size} bytes)"
        ]
    return []


def _diff_json(label: str, a: Path, b: Path) -> list[str]:
    if not a.exists() or not b.exists():
        return _diff_binary(label, a, b)
    try:
        ja = json.loads(a.read_text(encoding="utf-8"))
        jb = json.loads(b.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{label} JSON decode error: {exc}"]
    if ja == jb:
        return []
    return [f"{label} JSON content differs"]


def _list_files(d: Path, glob: str) -> set[str]:
    if not d.exists():
        return set()
    return {p.name for p in d.glob(glob)}


def _diff_snapshot_dir(blessed: Path, replayed: Path) -> list[str]:
    a = blessed / "snapshots"
    b = replayed / "snapshots"
    if not a.exists() and not b.exists():
        return []
    a_files = _list_files(a, "*")
    b_files = _list_files(b, "*")
    errors: list[str] = []
    only_a = sorted(a_files - b_files)
    only_b = sorted(b_files - a_files)
    # `.meta.json` files were introduced in a forward-compatible
    # extension (P1.8d / Task #18: per-snapshot gpsim cycle
    # counter).  Treat them as additive: a blessed fixture that
    # predates the schema extension may not have them, and a
    # newly-replayed run that adds them is not a determinism
    # regression.  Diff their contents only when both sides have
    # the file.
    only_b = [name for name in only_b if not name.endswith(".meta.json")]
    if only_a:
        errors.append(f"snapshots only in blessed: {only_a[:5]}{'...' if len(only_a) > 5 else ''}")
    if only_b:
        errors.append(f"snapshots only in replayed: {only_b[:5]}{'...' if len(only_b) > 5 else ''}")
    common = sorted(a_files & b_files)
    for name in common:
        if name.endswith(".ram.bin"):
            errors.extend(_diff_binary(f"snapshots/{name}", a / name, b / name))
        elif name.endswith(".sfr.json") or name.endswith(".meta.json"):
            errors.extend(_diff_json(f"snapshots/{name}", a / name, b / name))
    return errors


def _diff_outputs(blessed: Path, replayed: Path) -> list[str]:
    errors: list[str] = []
    for label_glob in ("uart_tx_*.jsonl", "lcd_*.txt", "eeprom_*.bin"):
        a_names = _list_files(blessed, label_glob)
        b_names = _list_files(replayed, label_glob)
        only_a = sorted(a_names - b_names)
        only_b = sorted(b_names - a_names)
        if only_a:
            errors.append(f"{label_glob} only in blessed: {only_a}")
        if only_b:
            errors.append(f"{label_glob} only in replayed: {only_b}")
        for name in sorted(a_names & b_names):
            errors.extend(_diff_binary(name, blessed / name, replayed / name))
    return errors


def _diff_capture(blessed: Path, replayed: Path) -> list[str]:
    errors: list[str] = []
    errors.extend(_diff_stimulus(blessed / "stimulus.jsonl", replayed / "stimulus.jsonl"))
    errors.extend(_diff_snapshot_dir(blessed, replayed))
    errors.extend(_diff_outputs(blessed, replayed))
    return errors


def _archive_failure(blessed_name: str, replay_dir: Path) -> None:
    """Copy a (replay) capture directory into the divergence
    archive so an operator can inspect it post-hoc.

    Best-effort: wraps every step (mkdir, rmtree of an existing
    archive, copytree) in a single try/except so a permission
    error, device-full, or read-only filesystem at any stage
    doesn't mask the underlying determinism failure that triggered
    the archive request.
    """
    if not replay_dir.exists():
        return
    div_root = REPO_ROOT / "artifacts" / "sim_rewrite_divergences"
    archive = div_root / f"P0.5__{blessed_name}__replay"
    try:
        div_root.mkdir(parents=True, exist_ok=True)
        if archive.exists():
            shutil.rmtree(archive)
        shutil.copytree(replay_dir, archive)
    except (OSError, shutil.Error):
        # Surface the archive failure on stderr so the operator
        # knows the divergence tarball is missing, then drop the
        # exception so the determinism gate's own report keeps
        # going.
        print(
            f"warning: failed to archive replay capture for "
            f"{blessed_name!r} to {archive}; original divergence "
            "report follows.",
            file=sys.stderr,
        )


def _replay_one(blessed: Path, python: Path, *, verbose: bool) -> tuple[list[str], str]:
    """Return ``(diff_errors, status)``.

    ``status`` ∈ {"replayed", "skipped_original_skipped",
    "skipped_no_summary"}.  Caller's interpretation:

      * ``"replayed"``                 — replay actually ran;
        ``diff_errors`` empty ⇒ deterministic, non-empty ⇒ fail.
      * ``"skipped_original_skipped"`` — original outcome was
        ``skipped`` so there's nothing to diff; reported in the
        summary as skipped, NOT a failure.
      * ``"skipped_no_summary"``       — summary.json is missing
        or has no nodeid; we can't replay, so the caller treats
        this as a failure (the captured fixture is malformed).
    """
    summary_path = blessed / "summary.json"
    if not summary_path.exists():
        return ["summary.json missing — cannot recover originating nodeid"], "skipped_no_summary"
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
    nodeid = summary.get("nodeid")
    if not nodeid:
        return ["summary.json has no 'nodeid' — cannot replay"], "skipped_no_summary"
    original_outcome = summary.get("outcome", "passed")

    # Originally-skipped tests don't open harnesses, so they have
    # no captured artefacts to diff.  Re-running them and
    # comparing two empty corpora would falsely report
    # "deterministic" without actually exercising the gpsim path.
    # Report and skip — counted in the summary but not a failure.
    if original_outcome == "skipped":
        if verbose:
            print(f"  skipping {blessed.name} (original outcome=skipped)")
        return [], "skipped_original_skipped"

    if verbose:
        print(f"  replaying {blessed.name} (nodeid={nodeid})")

    with tempfile.TemporaryDirectory(prefix="replay_gt_") as td:
        replay_root = Path(td) / "ground_truth"
        env = os.environ.copy()
        env["DLCP_GROUND_TRUTH_OUT"] = str(replay_root)
        # Hash randomization could in principle affect dict iteration
        # order in Python; pin it for replay reproducibility.
        env["PYTHONHASHSEED"] = "0"
        # Force gpsim backend: ground-truth fixtures were captured
        # against gpsim, so the replay must run against gpsim too.
        # Post-P4.8 the default backend is rust; without this
        # override the replay would silently re-run against the
        # rust engine and divergences would be misattributed.
        env["DLCP_SIM_BACKEND"] = "gpsim"
        cmd = [
            str(python),
            "-m", "pytest",
            nodeid,
            "--capture-ground-truth",
            "-q",
            "--no-header",
        ]
        cp = subprocess.run(
            cmd,
            cwd=str(REPO_ROOT),
            env=env,
            capture_output=True,
            text=True,
        )
        replay_dir = replay_root / blessed.name

        if cp.returncode != 0 and original_outcome == "passed":
            _archive_failure(blessed.name, replay_dir)
            return [
                f"replay pytest exited {cp.returncode} but original "
                f"outcome was 'passed':\n{cp.stdout[-500:]}\n{cp.stderr[-500:]}"
            ], "replayed"
        if not replay_dir.exists():
            return [
                f"replay produced no capture at {replay_dir} "
                f"(pytest exit={cp.returncode}); "
                f"stdout tail: {cp.stdout[-300:]!r}"
            ], "replayed"

        diff_errors = _diff_capture(blessed, replay_dir)
        if diff_errors:
            _archive_failure(blessed.name, replay_dir)
        return diff_errors, "replayed"


def _captured_dirs(only_for: str | None = None) -> list[Path]:
    if not GROUND_TRUTH_ROOT.exists():
        return []
    out: list[Path] = []
    for p in sorted(GROUND_TRUTH_ROOT.iterdir()):
        if not p.is_dir():
            continue
        if only_for is not None and only_for not in p.name:
            continue
        out.append(p)
    return out


def main(argv: Iterable[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--all",
        action="store_true",
        help="Replay every captured fixture under artifacts/ground_truth/.",
    )
    parser.add_argument(
        "--test",
        default=None,
        help=(
            "Replay only fixtures whose directory name contains this "
            "substring (useful for one-off verification)."
        ),
    )
    parser.add_argument(
        "--python",
        default=str(DEFAULT_PYTHON),
        help=f"Python interpreter to invoke pytest with (default: {DEFAULT_PYTHON})",
    )
    parser.add_argument(
        "-v",
        action="store_true",
        dest="verbose",
        help="Print per-test progress.",
    )
    args = parser.parse_args(list(argv))

    if not args.all and args.test is None:
        parser.error("must specify --all or --test <substring>")

    python = Path(args.python)
    if not python.exists():
        print(f"FAIL: python interpreter not found: {python}", file=sys.stderr)
        return 2

    dirs = _captured_dirs(only_for=args.test)
    if not dirs:
        print(
            "FAIL: no captured fixtures under "
            f"{GROUND_TRUTH_ROOT}; run "
            "`pytest tests/sim/<some_test> --capture-ground-truth` first.",
            file=sys.stderr,
        )
        return 2

    print(f"=== replay_ground_truth: {len(dirs)} fixture(s) ===")
    failures: list[tuple[str, list[str]]] = []
    skipped: list[str] = []
    replayed = 0
    for blessed in dirs:
        errors, status = _replay_one(blessed, python, verbose=args.verbose)
        if status == "skipped_original_skipped":
            skipped.append(blessed.name)
            print(f"  SKIP {blessed.name}  (original outcome=skipped)")
            continue
        if status == "skipped_no_summary":
            failures.append((blessed.name, errors))
            print(f"  FAIL {blessed.name}  (cannot replay: missing/invalid summary.json)")
            continue
        replayed += 1
        if errors:
            failures.append((blessed.name, errors))
            print(f"  FAIL {blessed.name}")
        else:
            print(f"  OK   {blessed.name}")

    if failures:
        print()
        print(f"=== {len(failures)} fixture(s) diverged on replay ===", file=sys.stderr)
        for name, errs in failures:
            print(f"\n--- {name} ---", file=sys.stderr)
            for msg in errs:
                print(f"  {msg}", file=sys.stderr)
        return 1
    summary_msg = f"  replay determinism OK across {replayed} fixture(s)"
    if skipped:
        summary_msg += f"  ({len(skipped)} skipped)"
    print()
    print(summary_msg)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
