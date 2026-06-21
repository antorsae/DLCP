#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tests.sim.memory_corruption_helpers import (
    firmware_path_repair_all_filename_slots,
    final_state,
    protected_filename_watches,
    read_eeprom_slot,
    run_live_like_churn,
    slot,
    start_v173_v35_chain,
    write_trace_artifacts,
    PRESET_B_EEPROM_BASE,
)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run a V1.73/V3.5 memory-corruption trace scenario."
    )
    parser.add_argument(
        "--scenario",
        default="v173-v35-live-like",
        choices=("v173-v35-live-like",),
    )
    parser.add_argument("--seed", type=lambda s: int(s, 0), default=0x35_0173)
    parser.add_argument("--max-records", type=int, default=10_000)
    parser.add_argument(
        "--out-root",
        type=Path,
        default=Path("artifacts/reanalysis/memory_corruption"),
    )
    parser.add_argument("--no-artifacts", action="store_true")
    parser.add_argument(
        "--expect-clean",
        action="store_true",
        help="exit nonzero if a protected write is observed",
    )
    args = parser.parse_args()

    slot_a = slot("LX521.4 22MG10F-v5")
    slot_b = slot("LX521.4 22MG10F-v7")

    chain = start_v173_v35_chain()
    firmware_path_repair_all_filename_slots(chain, slot_a, slot_b)
    watches = protected_filename_watches()
    chain.begin_memory_trace(watches, max_records=args.max_records)
    stimuli = run_live_like_churn(chain)

    summary = chain.memory_trace_summary()
    violation = chain.memory_trace_first_violation()
    state = final_state(chain)
    corrupt_units = []
    for unit in (0, 1):
        if read_eeprom_slot(chain, unit, PRESET_B_EEPROM_BASE) != slot_b:
            corrupt_units.append(unit)

    out_dir = None
    if not args.no_artifacts:
        out_dir = write_trace_artifacts(
            args.out_root,
            args.scenario,
            args.seed,
            chain,
            stimuli,
            watches=watches,
            rerun_command=[sys.executable, *sys.argv],
        )

    print("memory corruption trace")
    print(f"  scenario: {args.scenario}")
    print(f"  stimuli: {len(stimuli)}")
    print(f"  trace records: {summary['record_count']} total={summary['total_count']}")
    print(f"  overflowed: {summary['overflowed']} dropped={summary['dropped_count']}")
    print(f"  first violation: {json.dumps(violation, sort_keys=True) if violation else 'none'}")
    print(f"  corrupt preset-B units: {corrupt_units if corrupt_units else 'none'}")
    print(f"  lcd: {state['lcd']!r}")
    if out_dir is not None:
        print(f"  artifacts: {out_dir}")
    return 1 if args.expect_clean and violation else 0


if __name__ == "__main__":
    raise SystemExit(main())
