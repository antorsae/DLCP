#!/usr/bin/env python3
"""check_ground_truth_capture.py — validate Phase-0 capture artifacts.

Iterates ``artifacts/ground_truth/<test>/`` directories produced by the
``--capture-ground-truth`` pytest plugin and asserts that the requested
stream kind is well-formed.  Phase-0 sub-tasks gate on this:

  P0.2 stimulus  : every dir has a non-empty, parseable stimulus.jsonl
  P0.3 snapshots : every dir has a snapshots/ subdir with files at
                   1ms boundaries (filled in by P0.3).
  P0.4 outputs   : every dir produced uart_tx_*.jsonl + lcd_final.txt
                   + eeprom_final.bin (filled in by P0.4).

P0.5 — replay-against-gpsim — is a separate sub-task and is not
performed here.

Each check returns exit 0 if the corpus is valid, non-zero otherwise.
With no captured directories at all, this script exits non-zero so the
gate flags "you forgot to run the capture" rather than silently
passing.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Iterable

REPO_ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_ROOT = REPO_ROOT / "artifacts" / "ground_truth"


KNOWN_KINDS = ("stimulus", "snapshots", "outputs")


REQUIRED_EVENT_FIELDS = {"seq", "wall_time", "schema_version", "kind", "harness", "payload"}


def _captured_dirs() -> list[Path]:
    if not GROUND_TRUTH_ROOT.exists():
        return []
    return sorted(p for p in GROUND_TRUTH_ROOT.iterdir() if p.is_dir())


def _check_stimulus(dirs: Iterable[Path]) -> list[str]:
    """Validate stimulus.jsonl for each capture dir.  Returns list of
    error strings; empty list means all good."""
    errors: list[str] = []
    for d in dirs:
        path = d / "stimulus.jsonl"
        if not path.exists():
            errors.append(f"{d.name}: stimulus.jsonl is missing")
            continue
        if path.stat().st_size == 0:
            # Empty stimulus is legal for tests that don't drive any
            # external events, but the file MUST exist so a downstream
            # consumer can distinguish "no events" from "capture
            # didn't run".  Treat empty as a soft warning, not an error.
            continue
        with path.open(encoding="utf-8") as fp:
            for line_no, raw in enumerate(fp, start=1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    event = json.loads(raw)
                except json.JSONDecodeError as exc:
                    errors.append(
                        f"{d.name}: stimulus.jsonl line {line_no}: invalid JSON ({exc})"
                    )
                    continue
                missing = REQUIRED_EVENT_FIELDS - set(event)
                if missing:
                    errors.append(
                        f"{d.name}: stimulus.jsonl line {line_no}: "
                        f"missing fields {sorted(missing)}"
                    )
                if event.get("schema_version") != 1:
                    errors.append(
                        f"{d.name}: stimulus.jsonl line {line_no}: "
                        f"unexpected schema_version {event.get('schema_version')!r}"
                    )
    return errors


_SFR_KEY_RE = re.compile(r"^0x[0-9A-Fa-f]{3}$")
_SFR_RANGE = range(0xF60, 0x1000)


def _check_snapshots(dirs: Iterable[Path]) -> list[str]:
    """Validate the per-test `snapshots/` directory.

    P0.3 implements the **minimum-viable** snapshot policy (option A
    from the planning discussion): snapshots are taken at well-
    defined boundaries (after each recorded chain mutator event and
    at test start/end), not on a 1 ms cadence.  The validator
    requires:

      * `snapshots/` exists for every captured test directory.
      * Every snapshot is a paired `.ram.bin` + `.sfr.json` with
        the same prefix; orphan ram.bin or orphan sfr.json files
        fail the gate.
      * Each `*.ram.bin` is exactly 256 bytes (RAM bank 0).
      * Each `*.sfr.json` parses as a JSON object whose keys match
        `^0x[0-9A-Fa-f]{3}$` and decode to addresses in the
        top-of-bank-15 SFR range 0xF60..0xFFF; values are bytes
        (0..255).
      * For tests whose stimulus.jsonl is non-empty (i.e. the test
        actually drove a chain mutator), at least one snapshot
        pair was written.  Tests with empty stimulus are exempt —
        the chain mutators never fired so no snapshots are
        expected.
    """
    errors: list[str] = []
    for d in dirs:
        snaps = d / "snapshots"
        if not snaps.exists():
            errors.append(f"{d.name}: snapshots/ directory is missing")
            continue

        # Build a {prefix: kinds_present} map so we can detect orphans.
        # The "prefix" is everything before the trailing `.ram.bin` or
        # `.sfr.json`.
        prefixes: dict[str, set[str]] = {}
        for entry in snaps.iterdir():
            if entry.suffix == ".bin" and entry.name.endswith(".ram.bin"):
                prefix = entry.name[: -len(".ram.bin")]
                prefixes.setdefault(prefix, set()).add("ram")
            elif entry.suffix == ".json" and entry.name.endswith(".sfr.json"):
                prefix = entry.name[: -len(".sfr.json")]
                prefixes.setdefault(prefix, set()).add("sfr")

        for prefix, kinds in sorted(prefixes.items()):
            if "ram" not in kinds:
                errors.append(
                    f"{d.name}: snapshot {prefix!r} has sfr.json without "
                    f"a matching ram.bin (orphan SFR sidecar)"
                )
            if "sfr" not in kinds:
                errors.append(
                    f"{d.name}: snapshot {prefix!r} has ram.bin without "
                    f"a matching sfr.json (orphan RAM dump)"
                )

        ram_files = sorted(snaps.glob("*.ram.bin"))

        # Empty-stimulus tests are exempt from the "non-empty
        # stimulus → at least one snapshot" rule.
        stim = d / "stimulus.jsonl"
        stim_empty = (not stim.exists()) or stim.stat().st_size == 0
        if not ram_files and not stim_empty:
            errors.append(
                f"{d.name}: stimulus.jsonl is non-empty but snapshots/ "
                "contains no .ram.bin files"
            )

        for ram_path in ram_files:
            size = ram_path.stat().st_size
            if size != 256:
                errors.append(
                    f"{d.name}: {ram_path.name} is {size} bytes "
                    "(expected 256, RAM bank 0)"
                )

        for sfr_path in sorted(snaps.glob("*.sfr.json")):
            try:
                sfr = json.loads(sfr_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                errors.append(f"{d.name}: {sfr_path.name}: invalid JSON ({exc})")
                continue
            if not isinstance(sfr, dict):
                errors.append(
                    f"{d.name}: {sfr_path.name}: top-level must be an object"
                )
                continue
            for key, value in sfr.items():
                if not (isinstance(key, str) and _SFR_KEY_RE.match(key)):
                    errors.append(
                        f"{d.name}: {sfr_path.name}: bad SFR key {key!r} "
                        "(expected ^0x[0-9A-Fa-f]{3}$)"
                    )
                    continue
                addr = int(key, 16)
                if addr not in _SFR_RANGE:
                    errors.append(
                        f"{d.name}: {sfr_path.name}: SFR address {key!r} "
                        f"outside top-of-bank-15 range 0xF60..0xFFF"
                    )
                if not (isinstance(value, int) and 0 <= value <= 255):
                    errors.append(
                        f"{d.name}: {sfr_path.name}: SFR value {value!r} "
                        f"for key {key!r} is not a byte (0..255)"
                    )
    return errors


_LCD_NAME_RE = re.compile(r"^lcd_([A-Za-z0-9_-]+)\.txt$")
_EEPROM_NAME_RE = re.compile(r"^eeprom_([A-Za-z0-9_-]+)\.bin$")
_UART_NAME_RE = re.compile(r"^uart_tx_([A-Za-z0-9_-]+)\.jsonl$")

_REQUIRED_UART_FIELDS = {"seq", "route", "cmd", "data"}


def _check_outputs(dirs: Iterable[Path]) -> list[str]:
    """Validate the per-test UART/LCD/EEPROM artefacts.

    P0.4 lays down a per-harness output triplet at close-time:

      * `uart_tx_<harness_id>.jsonl` — one JSONL line per TX frame
        (`{seq, route, cmd, data}` with byte-clamped values).
      * `lcd_<harness_id>.txt` — exactly two text lines (the 16x2
        LCD raster).  Only emitted by harnesses that drive an LCD
        (currently CONTROL).
      * `eeprom_<harness_id>.bin` — 256 raw bytes of internal
        EEPROM.

    Validator rules:

      * Every captured test directory must contain at least one
        `uart_tx_<id>.jsonl` (since every chain harness produces a
        UART stream — even if it ends up empty for a fully passive
        test, the file itself must be present so a downstream
        consumer can distinguish "no TX" from "capture didn't run").
      * Every JSONL line in those files parses as an object with
        exactly the keys ``seq, route, cmd, data`` and byte values.
      * Every `lcd_<id>.txt` is exactly two newline-terminated lines.
      * Every `eeprom_<id>.bin` is exactly 256 bytes.

    Read-only / empty-stimulus tests are exempt (the harnesses
    never opened, so no triplet was written).
    """
    errors: list[str] = []
    for d in dirs:
        stim = d / "stimulus.jsonl"
        stim_empty = (not stim.exists()) or stim.stat().st_size == 0

        uart_files = sorted(d.glob("uart_tx_*.jsonl"))
        lcd_files = sorted(d.glob("lcd_*.txt"))
        eeprom_files = sorted(d.glob("eeprom_*.bin"))

        if not uart_files and not stim_empty:
            errors.append(
                f"{d.name}: stimulus.jsonl is non-empty but no "
                "uart_tx_*.jsonl files were written (harness close() "
                "should produce one per harness)"
            )

        # Defense in depth against a partial dump: every harness
        # that produced a uart_tx_<hid>.jsonl must also produce an
        # eeprom_<hid>.bin and vice versa.  OutputCapture.dump()
        # rolls back partial state on failure, so this should
        # always hold; if it doesn't, something is bypassing the
        # rollback path.  The set extraction tolerates files whose
        # names match the glob but not the stricter regex (caught
        # by the per-stream filename checks below).
        def _ids(files, regex):
            out: set[str] = set()
            for p in files:
                m = regex.match(p.name)
                if m:
                    out.add(m.group(1))
            return out

        uart_ids = _ids(uart_files, _UART_NAME_RE)
        eeprom_ids = _ids(eeprom_files, _EEPROM_NAME_RE)
        for hid in sorted(uart_ids - eeprom_ids):
            errors.append(
                f"{d.name}: harness {hid!r} has uart_tx_{hid}.jsonl "
                f"but no eeprom_{hid}.bin (partial OutputCapture "
                "dump? gpsim died during EEPROM read?)"
            )
        for hid in sorted(eeprom_ids - uart_ids):
            errors.append(
                f"{d.name}: harness {hid!r} has eeprom_{hid}.bin "
                f"but no uart_tx_{hid}.jsonl (orphan EEPROM dump? "
                "stale artifact from a previous run?)"
            )

        for path in uart_files:
            m = _UART_NAME_RE.match(path.name)
            if not m:
                errors.append(
                    f"{d.name}: {path.name}: malformed UART filename"
                )
                continue
            with path.open(encoding="utf-8") as fp:
                for line_no, raw in enumerate(fp, start=1):
                    raw = raw.strip()
                    if not raw:
                        continue
                    try:
                        rec = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        errors.append(
                            f"{d.name}: {path.name} line {line_no}: "
                            f"invalid JSON ({exc})"
                        )
                        continue
                    missing = _REQUIRED_UART_FIELDS - set(rec)
                    if missing:
                        errors.append(
                            f"{d.name}: {path.name} line {line_no}: "
                            f"missing fields {sorted(missing)}"
                        )
                        continue
                    for key in ("route", "cmd", "data"):
                        v = rec[key]
                        if not (isinstance(v, int) and 0 <= v <= 255):
                            errors.append(
                                f"{d.name}: {path.name} line {line_no}: "
                                f"{key}={v!r} not a byte (0..255)"
                            )

        for path in lcd_files:
            if not _LCD_NAME_RE.match(path.name):
                errors.append(f"{d.name}: {path.name}: malformed LCD filename")
                continue
            text = path.read_text(encoding="utf-8")
            lines = text.split("\n")
            # Trailing newline produces an empty final segment, so
            # exactly 2 LCD lines + 1 trailing empty = 3 entries.
            if len(lines) != 3 or lines[-1] != "":
                errors.append(
                    f"{d.name}: {path.name}: must contain exactly two "
                    f"newline-terminated lines (got {len(lines) - 1})"
                )

        for path in eeprom_files:
            if not _EEPROM_NAME_RE.match(path.name):
                errors.append(
                    f"{d.name}: {path.name}: malformed EEPROM filename"
                )
                continue
            size = path.stat().st_size
            if size != 256:
                errors.append(
                    f"{d.name}: {path.name}: {size} bytes "
                    "(expected 256)"
                )
    return errors


def _print_errors(label: str, errors: list[str]) -> int:
    if errors:
        print(f"FAIL: {label} check failed:", file=sys.stderr)
        for msg in errors:
            print(f"  - {msg}", file=sys.stderr)
        return 1
    return 0


def main(argv: list[str]) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--kind",
        choices=KNOWN_KINDS,
        required=True,
        help="which captured stream to validate",
    )
    args = p.parse_args(argv)

    dirs = _captured_dirs()
    if not dirs:
        print(
            f"FAIL: no capture directories found under {GROUND_TRUTH_ROOT}; "
            "run `pytest tests/sim --capture-ground-truth` first.",
            file=sys.stderr,
        )
        return 2

    print(f"=== check_ground_truth_capture --kind {args.kind} ===")
    print(f"  scanning {len(dirs)} captured test dir(s) under {GROUND_TRUTH_ROOT}")

    if args.kind == "stimulus":
        errors = _check_stimulus(dirs)
    elif args.kind == "snapshots":
        errors = _check_snapshots(dirs)
    elif args.kind == "outputs":
        errors = _check_outputs(dirs)
    else:  # pragma: no cover — argparse choices block this
        print(f"unknown --kind {args.kind!r}", file=sys.stderr)
        return 2

    rc = _print_errors(args.kind, errors)
    if rc == 0:
        print(f"  {args.kind}: OK across {len(dirs)} captured dirs")
    return rc


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
