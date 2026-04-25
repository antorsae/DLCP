#!/usr/bin/env python3
"""sim_rewrite_next.py — automation entry point for the dlcp-sim Rust rewrite.

Reads docs/SIM_REWRITE_RUST_PROGRESS.md, finds the next pending sub-task,
runs its verify command, and updates the ledger atomically.  Designed so
an autonomous agent (or a human) can call

    python3 scripts/sim_rewrite_next.py status     # see current state
    python3 scripts/sim_rewrite_next.py advance    # try the next pending task
    python3 scripts/sim_rewrite_next.py verify-phase 0   # full phase gate
    python3 scripts/sim_rewrite_next.py report     # overview

…with minimal manual bookkeeping.  All edits go through this script so
status flips are atomic and the markdown stays valid.

Sub-task line shape (must match exactly):

    - [STATUS] P{phase}.{sub} {title}
      - verify: {shell command}
      - artifact: {path}
      - notes: {free text}

Where STATUS ∈ { pending, in_progress, done, blocked }.
"""

from __future__ import annotations

import argparse
import datetime as dt
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
LEDGER = REPO_ROOT / "docs" / "SIM_REWRITE_RUST_PROGRESS.md"
DIVERGENCE_DIR = REPO_ROOT / "artifacts" / "sim_rewrite_divergences"

VALID_STATUSES = ("pending", "in_progress", "done", "blocked")
TASK_RE = re.compile(
    r"^- \[(?P<status>pending|in_progress|done|blocked)\] (?P<id>P\w+(?:\.\w+)?) (?P<title>.+)$"
)
VERIFY_RE = re.compile(r"^  - verify: (?P<cmd>.+)$")
ARTIFACT_RE = re.compile(r"^  - artifact: (?P<path>.+)$")
NOTES_RE = re.compile(r"^  - notes: (?P<notes>.+)$")


@dataclass
class Task:
    id: str
    title: str
    status: str
    verify: str | None = None
    artifact: str | None = None
    notes: str | None = None
    line_idx: int = -1

    @property
    def phase(self) -> str:
        return self.id.split(".")[0]

    def is_gate(self) -> bool:
        return self.id.endswith(".gate")


def parse_ledger(text: str) -> list[Task]:
    tasks: list[Task] = []
    lines = text.splitlines()
    current: Task | None = None
    for idx, line in enumerate(lines):
        m = TASK_RE.match(line)
        if m:
            if current is not None:
                tasks.append(current)
            current = Task(
                id=m.group("id"),
                title=m.group("title").strip(),
                status=m.group("status"),
                line_idx=idx,
            )
            continue
        if current is None:
            continue
        m = VERIFY_RE.match(line)
        if m:
            current.verify = m.group("cmd").strip()
            continue
        m = ARTIFACT_RE.match(line)
        if m:
            current.artifact = m.group("path").strip()
            continue
        m = NOTES_RE.match(line)
        if m:
            current.notes = m.group("notes").strip()
            continue
    if current is not None:
        tasks.append(current)
    return tasks


def write_status(text: str, task: Task, new_status: str) -> str:
    """Return a new ledger text with `task` flipped to `new_status`.

    Preserves everything else byte-for-byte.
    """
    if new_status not in VALID_STATUSES:
        raise ValueError(f"invalid status {new_status!r}")
    lines = text.splitlines(keepends=True)
    line = lines[task.line_idx]
    new_line = re.sub(
        r"\[(pending|in_progress|done|blocked)\]",
        f"[{new_status}]",
        line,
        count=1,
    )
    lines[task.line_idx] = new_line
    return "".join(lines)


def update_last_updated(text: str) -> str:
    today = dt.date.today().isoformat()
    return re.sub(
        r"^Last updated: \d{4}-\d{2}-\d{2}",
        f"Last updated: {today}",
        text,
        count=1,
        flags=re.MULTILINE,
    )


def cmd_status(tasks: list[Task]) -> int:
    by_phase: dict[str, list[Task]] = {}
    for t in tasks:
        by_phase.setdefault(t.phase, []).append(t)

    print("=== dlcp-sim rewrite — progress ===\n")
    for phase, phase_tasks in by_phase.items():
        done = sum(1 for t in phase_tasks if t.status == "done")
        total = len(phase_tasks)
        print(f"  {phase}: {done}/{total} done")

    next_task = find_next_pending(tasks)
    if next_task is None:
        in_prog = [t for t in tasks if t.status == "in_progress"]
        if in_prog:
            print(f"\n  in_progress: {in_prog[0].id} — {in_prog[0].title}")
        else:
            print("\n  ALL TASKS COMPLETE.")
        return 0

    print(f"\n  next pending: {next_task.id} — {next_task.title}")
    if next_task.verify:
        print(f"  verify command: {next_task.verify}")
    if next_task.artifact:
        print(f"  artifact: {next_task.artifact}")
    return 0


def find_next_pending(tasks: list[Task]) -> Task | None:
    for t in tasks:
        if t.status == "pending":
            return t
    return None


def find_in_progress(tasks: list[Task]) -> Task | None:
    for t in tasks:
        if t.status == "in_progress":
            return t
    return None


def cmd_advance(args: argparse.Namespace) -> int:
    """Pick the next pending task, mark in_progress, run verify, on pass mark done."""
    text = LEDGER.read_text()
    tasks = parse_ledger(text)

    in_prog = find_in_progress(tasks)
    if in_prog is not None:
        target = in_prog
        print(f"resuming in-progress task {target.id}: {target.title}")
    else:
        target = find_next_pending(tasks)
        if target is None:
            print("no pending tasks")
            return 0
        print(f"advancing task {target.id}: {target.title}")
        text = write_status(text, target, "in_progress")
        text = update_last_updated(text)
        LEDGER.write_text(text)

    if target.verify is None:
        print(f"  task {target.id} has no verify command; treating as manual")
        if not args.force_pass:
            print("  rerun with --force-pass to mark done without a verify command")
            return 0
        text = LEDGER.read_text()
        tasks = parse_ledger(text)
        target = next(t for t in tasks if t.id == target.id)
        text = write_status(text, target, "done")
        text = update_last_updated(text)
        LEDGER.write_text(text)
        print("  marked done (manual override)")
        return 0

    print(f"  running: {target.verify}")
    res = subprocess.run(
        target.verify,
        shell=True,
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
    )
    if res.returncode != 0:
        DIVERGENCE_DIR.mkdir(parents=True, exist_ok=True)
        ts = dt.datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
        log = DIVERGENCE_DIR / f"{target.id}__{ts}.log"
        log.write_text(
            f"# task: {target.id} {target.title}\n"
            f"# verify: {target.verify}\n"
            f"# exit: {res.returncode}\n"
            f"# --- stdout ---\n{res.stdout}\n"
            f"# --- stderr ---\n{res.stderr}\n"
        )
        print(f"  FAILED (exit {res.returncode}); details: {log}")
        print(f"  status remains in_progress; fix the underlying issue and rerun")
        return res.returncode

    print("  PASS")
    text = LEDGER.read_text()
    tasks = parse_ledger(text)
    target = next(t for t in tasks if t.id == target.id)
    text = write_status(text, target, "done")
    text = update_last_updated(text)
    LEDGER.write_text(text)
    print(f"  marked {target.id} as done")
    return 0


def cmd_verify_phase(args: argparse.Namespace) -> int:
    """Run all verify commands for a given phase; report pass/fail by sub-task."""
    text = LEDGER.read_text()
    tasks = parse_ledger(text)
    phase_id = f"P{args.phase}"
    phase_tasks = [t for t in tasks if t.phase == phase_id]
    if not phase_tasks:
        print(f"no tasks for phase {phase_id}")
        return 1

    failures: list[Task] = []
    for t in phase_tasks:
        if t.verify is None:
            continue
        print(f"--- {t.id} {t.title}")
        res = subprocess.run(
            t.verify,
            shell=True,
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        status = "PASS" if res.returncode == 0 else f"FAIL (exit {res.returncode})"
        print(f"    {status}")
        if res.returncode != 0:
            failures.append(t)

    print(f"\n=== phase {phase_id} summary ===")
    print(f"  total verify-able tasks: {sum(1 for t in phase_tasks if t.verify)}")
    print(f"  failures: {len(failures)}")
    for t in failures:
        print(f"    - {t.id} {t.title}")
    return 0 if not failures else 1


def cmd_report(args: argparse.Namespace) -> int:
    text = LEDGER.read_text()
    tasks = parse_ledger(text)
    counts = {s: 0 for s in VALID_STATUSES}
    for t in tasks:
        counts[t.status] += 1
    total = len(tasks)
    print(f"total tasks: {total}")
    for s in VALID_STATUSES:
        print(f"  {s}: {counts[s]}")
    by_phase: dict[str, dict[str, int]] = {}
    for t in tasks:
        by_phase.setdefault(t.phase, dict.fromkeys(VALID_STATUSES, 0))[t.status] += 1
    print("\nby phase:")
    for phase, c in by_phase.items():
        line = f"  {phase}: " + " ".join(f"{k}={v}" for k, v in c.items() if v)
        print(line)
    return 0


def cmd_block(args: argparse.Namespace) -> int:
    """Mark a specific sub-task as blocked, with an explanation."""
    text = LEDGER.read_text()
    tasks = parse_ledger(text)
    target = next((t for t in tasks if t.id == args.task_id), None)
    if target is None:
        print(f"task {args.task_id} not found")
        return 1
    text = write_status(text, target, "blocked")
    text = update_last_updated(text)
    LEDGER.write_text(text)
    DIVERGENCE_DIR.mkdir(parents=True, exist_ok=True)
    note = DIVERGENCE_DIR / f"{target.id}__blocked.md"
    note.write_text(
        f"# Blocked: {target.id} — {target.title}\n\n"
        f"_Reason_: {args.reason}\n\n"
        f"Recorded: {dt.datetime.utcnow().isoformat()}Z\n"
    )
    print(f"marked {target.id} as blocked; reason recorded at {note}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("status", help="show current phase + next pending sub-task")

    p_advance = sub.add_parser("advance", help="run the next pending task and update status")
    p_advance.add_argument("--force-pass", action="store_true", help="mark task done even with no verify command")

    p_phase = sub.add_parser("verify-phase", help="run all verify commands for a phase")
    p_phase.add_argument("phase", type=int)

    sub.add_parser("report", help="overview of all task counts by status and phase")

    p_block = sub.add_parser("block", help="mark a sub-task as blocked")
    p_block.add_argument("task_id", help="e.g. P1.5")
    p_block.add_argument("--reason", required=True, help="why it's blocked")

    args = p.parse_args()

    if not LEDGER.exists():
        print(f"ledger not found: {LEDGER}", file=sys.stderr)
        return 1

    if args.cmd == "status":
        text = LEDGER.read_text()
        tasks = parse_ledger(text)
        return cmd_status(tasks)
    if args.cmd == "advance":
        return cmd_advance(args)
    if args.cmd == "verify-phase":
        return cmd_verify_phase(args)
    if args.cmd == "report":
        return cmd_report(args)
    if args.cmd == "block":
        return cmd_block(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
