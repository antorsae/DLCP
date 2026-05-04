#!/usr/bin/env python3
"""check_gpsim_excision.py — track PF.4 (gpsim retirement) progress.

The PF.4 retirement is split into two phases (per
`docs/SIM_REWRITE_RUST_PROGRESS.md` "P4 followup tracker"):

  Phase 1 — done (commit-pending after this script lands):
      Delete the 30 gpsim-only test files + 14 gpsim-only operator
      scripts.  The 6 wrapper modules in `src/dlcp_fw/sim/`,
      `vendor/gpsim-0.32.1-xtc/`, and `artifacts/tools/gpsim-xtc/`
      are KEPT because 40 still-`@pytest.mark.dual_supported`
      tests in `tests/sim/` retain a `if dlcp_sim_backend ==
      "gpsim":` conditional branch and therefore still
      `from dlcp_fw.sim.{wrapper}` at module import time.

  Phase 2 — deferred:
      40-file dual_supported gpsim conditional-branch surgery:
      remove the gpsim imports + the `if dlcp_sim_backend ==
      "gpsim":` branches from each, then delete the 6 wrappers,
      the vendor tree, and the artifacts/tools build dir.

This script asserts:
  * Phase-1 deletions actually happened (the 30 + 14 paths are
    absent).
  * No remaining import in tests/ or scripts/ references one of
    the 14 deleted operator scripts.
  * Phase-2 inventory is reproducible: the script counts how
    many test files still import a gpsim wrapper, and how many
    of those carry @pytest.mark.dual_supported.

Exit codes:
    0 — phase 1 verified clean; phase 2 inventory reported.
    1 — a phase-1 deletion target is still present.
    2 — a deleted operator script is still imported somewhere.

Run:
    .venv_ep0/bin/python scripts/check_gpsim_excision.py
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Phase-1 deletion inventory: these 44 paths must be ABSENT.
PHASE_1_DELETED_TESTS: list[str] = [
    "tests/asm_unit_tests/test_main_core_service_265c_parity.py",
    "tests/sim/test_chain_gpsim_v141_v24_v25_recovery.py",
    "tests/sim/test_chain_gpsim_v161b_v24_v25_i2c_faults.py",
    "tests/sim/test_chain_gpsim_v25_recovery.py",
    "tests/sim/test_chain_gpsim_v25_v162b_recovery.py",
    "tests/sim/test_control_gpsim_command_emission_legacy.py",
    "tests/sim/test_control_gpsim_full_config_persistence.py",
    "tests/sim/test_control_gpsim_host_command_injection.py",
    "tests/sim/test_control_gpsim_ir_compatibility.py",
    "tests/sim/test_control_gpsim_ir_preset_switch.py",
    "tests/sim/test_control_gpsim_preset_eeprom_diff.py",
    "tests/sim/test_control_gpsim_response_parser.py",
    "tests/sim/test_control_main_powercycle_sync.py",
    "tests/sim/test_control_v164b_ir_endpoints.py",
    "tests/sim/test_gpsim_control_lcd.py",
    "tests/sim/test_gpsim_control_presets.py",
    "tests/sim/test_main_gpsim_an0_boot.py",
    "tests/sim/test_main_gpsim_cmd03_instruction_path.py",
    "tests/sim/test_main_gpsim_fault_injection.py",
    "tests/sim/test_main_gpsim_filename_ab.py",
    "tests/sim/test_main_gpsim_i2c_regfile.py",
    "tests/sim/test_main_gpsim_mailbox.py",
    "tests/sim/test_main_gpsim_timer3_compare.py",
    "tests/sim/test_main_v25_timeout_recovery.py",
    "tests/sim/test_v27_v163b_robustness.py",
    "tests/sim/test_v30_gpsim_equivalence.py",
    "tests/sim/test_v31_combined_dsp_table_apply.py",
    "tests/sim/test_wire_chain_gpsim_i2c_faults.py",
    "tests/sim/test_wire_chain_gpsim_internal_faults.py",
    "tests/sim/test_wire_chain_gpsim_stock_faults.py",
]

PHASE_1_DELETED_SCRIPTS: list[str] = [
    "scripts/capture_gpsim_ground_truth.py",
    "scripts/capture_v171_early_boot_parity.py",
    "scripts/check_ground_truth_capture.py",
    "scripts/gpsim_headless_chain_diagnose.py",
    "scripts/gpsim_lcd_capture_decode.py",
    "scripts/gpsim_menu_command_audit.py",
    "scripts/gpsim_tui_simulator.py",
    "scripts/probe_baudcon_mapping.py",
    "scripts/probe_v171_layer2_chain.py",
    "scripts/replay_ground_truth.py",
    "scripts/run_phase0_blessing.py",
    "scripts/simctl.py",
    "scripts/test_button_inject.py",
    "scripts/test_full_boot.py",
]

# Wrapper module names that phase-2 surgery will eventually delete
# from `src/dlcp_fw/sim/`.  Used by the phase-2 inventory grep so
# the count drops to 0 once the 40 dual_supported test files have
# been migrated and the wrappers themselves can land in the
# delete-set.
PHASE_2_WRAPPERS: list[str] = [
    "chain_gpsim",
    "wire_chain_gpsim",
    "control_gpsim",
    "main_gpsim",
    "main_gpsim_timer3",
    "gpsim",
]


def fail(rc: int, msg: str) -> int:
    print(f"FAIL ({rc}): {msg}", file=sys.stderr)
    return rc


def assert_phase1_deleted() -> int:
    """Walk PHASE_1_DELETED_{TESTS,SCRIPTS} and assert each path
    is absent from the working tree.  A still-present file
    suggests an incomplete or reverted deletion."""
    still_present: list[str] = []
    for rel in PHASE_1_DELETED_TESTS + PHASE_1_DELETED_SCRIPTS:
        if (REPO_ROOT / rel).exists():
            still_present.append(rel)
    if still_present:
        return fail(
            1,
            "PF.4 phase-1 deletion incomplete -- the following paths "
            f"still exist:\n  - "
            + "\n  - ".join(still_present),
        )
    return 0


def assert_no_imports_to_deleted_scripts() -> int:
    """Grep tests/ and scripts/ for any remaining import that
    references one of the 14 deleted operator scripts.  An
    operator script's module name is its filename without `.py`,
    e.g. `gpsim_tui_simulator.py` -> `gpsim_tui_simulator`."""
    broken: list[str] = []
    for script_rel in PHASE_1_DELETED_SCRIPTS:
        module = Path(script_rel).stem
        # Match `import scripts.{module}` or
        # `from scripts.{module}`.
        pattern = rf"\b(import|from)\s+scripts\.{re.escape(module)}\b"
        cp = subprocess.run(
            ["grep", "-rEl", pattern, "tests", "scripts", "src"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        # grep returns 1 if no match; treat that as clean.
        if cp.returncode == 0 and cp.stdout.strip():
            for line in cp.stdout.strip().splitlines():
                broken.append(f"{module} still imported by {line}")
    if broken:
        return fail(
            2,
            "Deleted operator scripts are still imported elsewhere:\n  - "
            + "\n  - ".join(broken),
        )
    return 0


def report_phase2_inventory() -> None:
    """Count test files still importing each PHASE_2_WRAPPER, and
    how many of those carry @pytest.mark.dual_supported.  Phase 2
    is done when the wrapper-import count drops to 0 across both
    tests/ and scripts/."""
    print("\nPhase-2 inventory (wrapper imports remaining):")
    grand_total: set[Path] = set()
    grand_dual: set[Path] = set()
    for wrapper in PHASE_2_WRAPPERS:
        pattern = rf"from dlcp_fw\.sim\.{re.escape(wrapper)}\b"
        cp = subprocess.run(
            ["grep", "-rEl", pattern, "tests", "scripts", "src"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
        )
        files = sorted(set(cp.stdout.strip().splitlines())) if cp.stdout.strip() else []
        dual = []
        for f in files:
            try:
                text = (REPO_ROOT / f).read_text()
            except OSError:
                continue
            if "dual_supported" in text:
                dual.append(f)
                grand_dual.add(REPO_ROOT / f)
            grand_total.add(REPO_ROOT / f)
        print(
            f"  {wrapper:>20}: {len(files):3d} import sites "
            f"({len(dual)} of which are @pytest.mark.dual_supported)"
        )
    print(
        f"  {'TOTAL':>20}: {len(grand_total):3d} unique import-site files; "
        f"{len(grand_dual)} of those are @pytest.mark.dual_supported "
        f"(those need surgery before phase 2 can delete the wrapper)."
    )


def main() -> int:
    rc1 = assert_phase1_deleted()
    if rc1 != 0:
        return rc1
    rc2 = assert_no_imports_to_deleted_scripts()
    if rc2 != 0:
        return rc2
    print("PF.4 phase-1 verified clean.")
    report_phase2_inventory()
    return 0


if __name__ == "__main__":
    sys.exit(main())
