"""Shared logic for versioned MAIN release flash wrappers (V3.1, V3.2, etc.)."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Optional

from dlcp_fw.flash.dlcp_control_flash import DEFAULT_PID, DEFAULT_VID
from dlcp_fw.flash import dlcp_main_flash as main_flash
from dlcp_fw.paths import ARTIFACTS_DIR


CAPTURE_DIR = ARTIFACTS_DIR / "LX521.4"
CAPTURE_A_BIN = CAPTURE_DIR / "LX521.4_22MG10F-v5.bin"
CAPTURE_A_META = CAPTURE_DIR / "LX521.4_22MG10F-v5.json"
CAPTURE_B_BIN = CAPTURE_DIR / "LX521.4_22MG10F-v7.bin"
CAPTURE_B_META = CAPTURE_DIR / "LX521.4_22MG10F-v7.json"


def _parse_int_auto(s: str) -> int:
    return int(s, 0)


def _resolve_route(args: argparse.Namespace, parser: argparse.ArgumentParser) -> Optional[str]:
    routes = [route for route in (args.all_ch, "L" if args.left else None, "R" if args.right else None) if route]
    unique = sorted(set(routes))
    if not unique:
        return None
    if len(unique) != 1:
        parser.error("conflicting route options; use exactly one of --left, --right, or --all-ch L|R")
    return unique[0]


def _require_file(path: Path, *, label: str, parser: argparse.ArgumentParser) -> None:
    if not path.is_file():
        parser.error(f"{label} not found: {path}")


def _append_common_args(argv: list[str], args: argparse.Namespace) -> None:
    if args.vid != DEFAULT_VID:
        argv.extend(["--vid", hex(args.vid)])
    if args.pid != DEFAULT_PID:
        argv.extend(["--pid", hex(args.pid)])
    if args.path:
        argv.extend(["--path", args.path])
    if args.list:
        argv.append("--list")
    if args.info_only:
        argv.append("--info-only")
    if args.preflight_only:
        argv.append("--preflight-only")
    if args.dry_run:
        argv.append("--dry-run")
    if args.verbose:
        argv.append("--verbose")


def build_forward_argv(
    args: argparse.Namespace,
    parser: argparse.ArgumentParser,
    *,
    release_hex: Path,
    version_label: str,
    capture_a_bin: Path | None = None,
    capture_a_meta: Path | None = None,
    capture_b_bin: Path | None = None,
    capture_b_meta: Path | None = None,
) -> list[str]:
    ca_bin = capture_a_bin or CAPTURE_A_BIN
    ca_meta = capture_a_meta or CAPTURE_A_META
    cb_bin = capture_b_bin or CAPTURE_B_BIN
    cb_meta = capture_b_meta or CAPTURE_B_META

    argv: list[str] = []
    _append_common_args(argv, args)

    if args.list or args.info_only:
        return argv

    route = _resolve_route(args, parser)
    if route is None:
        parser.error("a release flash requires exactly one routing target: --left, --right, or --all-ch L|R")

    _require_file(release_hex, label=f"canonical {version_label} MAIN hex", parser=parser)
    _require_file(ca_bin, label="preset A capture", parser=parser)
    _require_file(ca_meta, label="preset A sidecar", parser=parser)
    _require_file(cb_bin, label="preset B capture", parser=parser)
    _require_file(cb_meta, label="preset B sidecar", parser=parser)

    argv.extend(
        [
            "--hex",
            str(release_hex),
            "--capture-a",
            str(ca_bin),
            "--meta-a",
            str(ca_meta),
            "--capture-b",
            str(cb_bin),
            "--meta-b",
            str(cb_meta),
            "--all-ch",
            route,
        ]
    )
    return argv


def release_main(
    argv: list[str] | None,
    *,
    release_hex: Path,
    version_label: str,
    capture_a_bin: Path | None = None,
    capture_a_meta: Path | None = None,
    capture_b_bin: Path | None = None,
    capture_b_meta: Path | None = None,
) -> int:
    ap = argparse.ArgumentParser(
        description=f"Operator wrapper for the canonical {version_label} baked-preset release flash path.",
    )
    ap.add_argument("--vid", type=_parse_int_auto, default=DEFAULT_VID)
    ap.add_argument("--pid", type=_parse_int_auto, default=DEFAULT_PID)
    ap.add_argument("--path", default=None, help="explicit HID path (UTF-8 text)")
    ap.add_argument("--list", action="store_true", help="list matching HID devices and exit")
    ap.add_argument("--info-only", action="store_true", help="print current device info and exit")
    route_group = ap.add_mutually_exclusive_group()
    route_group.add_argument("--left", action="store_true", help=f"flash the canonical {version_label} release and set all channels to L")
    route_group.add_argument("--right", action="store_true", help=f"flash the canonical {version_label} release and set all channels to R")
    route_group.add_argument(
        "--all-ch",
        choices=("L", "R"),
        default=None,
        help="explicit route target; equivalent to --left or --right",
    )
    ap.add_argument("--preflight-only", action="store_true", help="run preflight only; do not write over USB")
    ap.add_argument("--dry-run", action="store_true", help="parse/prepare only, no USB writes")
    ap.add_argument("-v", "--verbose", action="store_true", help="verbose output")
    args = ap.parse_args(argv)

    forward_argv = build_forward_argv(
        args, ap,
        release_hex=release_hex,
        version_label=version_label,
        capture_a_bin=capture_a_bin,
        capture_a_meta=capture_a_meta,
        capture_b_bin=capture_b_bin,
        capture_b_meta=capture_b_meta,
    )
    return main_flash.main(forward_argv)
