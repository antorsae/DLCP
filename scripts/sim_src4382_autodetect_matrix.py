#!/usr/bin/env python3
"""Run the SRC4382 Auto Detect stock/current stimulus matrix."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

from dlcp_fw.sim.src4382_autodetect_matrix import (
    default_output_root,
    run_matrix,
    timestamped_output_dir,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out-root",
        type=Path,
        default=default_output_root(),
        help="parent directory for timestamped run directories",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="exact output directory; must be empty unless --overwrite is used",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="allow writing to a non-empty --out-dir",
    )
    parser.add_argument(
        "--model-cmd",
        help="trusted local/read-only command that reads prompt on stdin and emits JSON",
    )
    parser.add_argument(
        "--model-timeout",
        type=int,
        default=120,
        help="seconds before optional model invocation is killed",
    )
    parser.add_argument("--quiet", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    out_dir = args.out_dir or timestamped_output_dir(args.out_root)
    if out_dir.exists() and any(out_dir.iterdir()) and not args.overwrite:
        print(
            f"refusing non-empty output directory without --overwrite: {out_dir}",
            file=sys.stderr,
        )
        return 2

    try:
        result = run_matrix(
            out_dir=out_dir,
            argv=[sys.argv[0], *(argv if argv is not None else sys.argv[1:])],
            model_cmd=args.model_cmd,
            model_timeout=args.model_timeout,
        )
    except Exception as exc:
        if args.model_cmd and (out_dir / "oracle_error.json").exists():
            if not args.quiet:
                print(f"SRC4382 matrix model invocation failed; artifacts: {out_dir}")
            return 3
        print(f"SRC4382 matrix setup/run failed: {exc}", file=sys.stderr)
        return 2

    comparison = result["comparison"]
    if not args.quiet:
        print(f"SRC4382 Auto Detect matrix artifacts: {out_dir}")
        print(f"deterministic result: {comparison['overall']}")
    return 0 if comparison["pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
