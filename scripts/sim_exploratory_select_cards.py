#!/usr/bin/env python3
"""Select interesting exploratory sessions, render their cards, and emit workflow args.

Triages every session under a hunt directory, drops each run's in-progress final
session, then picks a prioritized set (top by triage score) with optional campaign
diversity and a random tail sample, renders their cards, and writes an args.json
that the oracle workflow consumes via `Workflow({scriptPath, args})`.
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from dlcp_fw.paths import PROJECT_ROOT  # noqa: E402

import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_oracle_format", Path(__file__).resolve().parent / "sim_exploratory_oracle_format.py"
)
_fmt = importlib.util.module_from_spec(_spec)
assert _spec.loader is not None
_spec.loader.exec_module(_fmt)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("hunt_dir")
    ap.add_argument("--out", required=True, help="cards output dir")
    ap.add_argument("--top", type=int, default=8, help="top-N by triage score")
    ap.add_argument("--sample", type=int, default=4, help="random tail sample below top-N")
    ap.add_argument("--min-stimuli", type=int, default=6)
    ap.add_argument("--include-inprogress", action="store_true",
                    help="include each run's final (likely in-progress) session")
    ap.add_argument("--seed", type=int, default=1234)
    ap.add_argument("--realistic", action="store_true",
                    help="hunt divergence under realistic stimulus: rank by realistic_score, "
                         "restrict to realistic campaigns, and cap synthetic fault load")
    ap.add_argument("--max-synthetic", type=int, default=0,
                    help="with --realistic, max synthetic-fault stimuli allowed per session")
    args = ap.parse_args(argv)

    realistic_campaigns = {"ui", "preset-filename", "src", "standby-reset"}
    score_key = "realistic_score" if args.realistic else "score"

    root = Path(args.hunt_dir).resolve()
    out_dir = Path(args.out).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    run_dirs = _fmt._iter_run_dirs(root)
    rows: list[dict] = []
    inprogress: set[tuple[str, int]] = set()
    for run_dir in run_dirs:
        run_rows = _fmt._triage_run(run_dir)
        sids = [r["session_id"] for r in run_rows]
        if sids and not args.include_inprogress:
            inprogress.add((str(run_dir), max(sids)))
        rows.extend(run_rows)

    eligible = [
        r for r in rows
        if r.get("score", -1) >= 0
        # keep boot/connect failures (no observations) even with too few stimuli (M4)
        and (r.get("n_stimuli", 0) >= args.min_stimuli
             or r.get("signals", {}).get("no_observations"))
        and (r["run_dir"], r["session_id"]) not in inprogress
    ]
    if args.realistic:
        eligible = [
            r for r in eligible
            if r.get("campaign") in realistic_campaigns
            and r.get("synthetic_fault_load", 0) <= args.max_synthetic
        ]
    eligible.sort(key=lambda r: r.get(score_key, 0), reverse=True)

    top = eligible[: args.top]
    rest = eligible[args.top:]
    rng = random.Random(args.seed)
    sample = rng.sample(rest, min(args.sample, len(rest))) if rest else []
    selected = top + sample

    cards: list[dict] = []
    for r in selected:
        run_dir = Path(r["run_dir"])
        sid = r["session_id"]
        card_name = f"{run_dir.name}__s{sid:04d}.md"
        card_path = out_dir / card_name
        try:
            card_path.write_text(_fmt.render_card(run_dir, sid), encoding="utf-8")
        except SystemExit:
            continue
        cards.append({
            "card": str(card_path),
            "run_id": run_dir.name,
            "session_id": sid,
            "campaign": r.get("campaign"),
            "score": r.get(score_key),
            "raw_score": r.get("score"),
            "realistic_score": r.get("realistic_score"),
            "synthetic_fault_load": r.get("synthetic_fault_load"),
            "final_lcd": r.get("final_lcd"),
            "signals": {k: v for k, v in r.get("signals", {}).items() if v},
        })

    workflow_args = {
        "cards": cards,
        "rubric": str(PROJECT_ROOT / "docs" / "SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md"),
        "taxonomy": str(PROJECT_ROOT / "docs" / "SIM_EXPLORATORY_BUG_TAXONOMY.md"),
        "main_asm": str(PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_main_v34.asm"),
        "control_asm": str(PROJECT_ROOT / "src" / "dlcp_fw" / "asm" / "dlcp_control_v173.asm"),
        "out": str(out_dir / "oracle_report.md"),
    }
    args_path = out_dir / "workflow_args.json"
    args_path.write_text(json.dumps(workflow_args, indent=2) + "\n", encoding="utf-8")

    mode = "realistic" if args.realistic else "divergence"
    print(f"selected {len(cards)} cards ({len(top)} top + {len(sample)} sample) "
          f"[{mode} ranking] -> {out_dir}", file=sys.stderr)
    for c in cards:
        print(f"  {score_key}={c['score']:>3} synth={c.get('synthetic_fault_load')} "
              f"{c['campaign']:<16} {c['run_id'][-8:]}#{c['session_id']} {c['final_lcd']}",
              file=sys.stderr)
    print(str(args_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
