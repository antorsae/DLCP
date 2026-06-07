#!/usr/bin/env python3
"""Check source-assembled firmware RAM bank safety."""

from __future__ import annotations

import argparse

from dlcp_fw.analysis.ram_bank_safety import (
    assert_targets_safe,
    check_targets,
    install_alias_block,
    migrate_source_aliases,
)
from dlcp_fw.asm.ram_bank_manifest import TARGET_SPECS


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--target",
        action="append",
        choices=sorted(TARGET_SPECS),
        help="target to check; may be repeated (default: all targets)",
    )
    ap.add_argument(
        "--fix-aliases",
        action="store_true",
        help="install/update generated alias blocks before checking",
    )
    ap.add_argument(
        "--fix-source-aliases",
        action="store_true",
        help="rewrite target source RAM operands to generated aliases before checking",
    )
    args = ap.parse_args(argv)

    targets = args.target or sorted(TARGET_SPECS)
    if args.fix_aliases:
        for target in targets:
            changed = install_alias_block(target)
            print(f"{target}: alias block {'updated' if changed else 'already current'}")
    if args.fix_source_aliases:
        for target in targets:
            changed = migrate_source_aliases(target)
            print(f"{target}: source aliases {'updated' if changed else 'already current'}")
    findings = check_targets(targets)
    if findings:
        for finding in findings:
            print(finding.format())
        return 1
    print("RAM bank safety: OK (" + ", ".join(targets) + ")")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
