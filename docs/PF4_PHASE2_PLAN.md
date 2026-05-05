# PF.4 phase 2 — gpsim wrapper excision plan

Branch: `feature/sim-rewrite-rust`
Spec parent: `docs/SIM_REWRITE_RUST_PROGRESS.md` "P4 followup tracker"
Tracker task: #102 (P4-followup D)
Status: **planning** (this document) → execution across follow-up commits.

## Scope

PF.4 phase 1 (commit 5a56279) deleted 30 gpsim-only test files + 14
gpsim-only operator scripts.  Phase 2 finishes the retirement by:

  1. Surgically removing gpsim code paths from 41 still-`@pytest.mark.
     dual_supported` test files in `tests/sim/` (each currently has a
     rust path AND a gpsim path; phase 2 keeps only rust).
  2. Migrating any non-gpsim utility code OUT of the 6 wrapper modules
     into a backend-agnostic home.
  3. Deleting the 6 wrapper modules: `src/dlcp_fw/sim/{chain_gpsim,
     wire_chain_gpsim, control_gpsim, main_gpsim, main_gpsim_timer3,
     gpsim}.py`.
  4. Editing `src/dlcp_fw/sim/__init__.py` to drop the 6 gpsim re-exports.
  5. Deleting `vendor/gpsim-0.32.1-xtc/` (16 M source tree).
  6. Deleting `artifacts/tools/gpsim-xtc/` (256 M build dir, gitignored
     so git rm -r is a no-op; just operator-side cleanup).
  7. Cleaning up `tests/sim/conftest.py`: `DLCP_SIM_BACKEND` env var
     becomes vestigial (only `rust` makes sense), `dual_supported`
     marker can be retired or kept as an inert marker.

Verification at end: `DLCP_SIM_BACKEND=rust pytest tests/sim -n 16 -q`
matches PF.1's baseline (582 / 39 / 1 / 0 fast subset, 204 / 260 / 7 / 0
slow subset).

## Inventory of the 41 files (per `scripts/check_gpsim_excision.py`)

Generated 2026-05-04 by AST walk; if the file count drifts before
execution, regenerate with `python3 scripts/check_gpsim_excision.py`
and update this section.

### Wrapper imports per file (sources of the surgery work)

```
chain_gpsim:        20 import sites
wire_chain_gpsim:    8 import sites
control_gpsim:      31 import sites
main_gpsim:          4 import sites
main_gpsim_timer3:   1 import site
gpsim:              37 import sites (mostly `gpsim_available()` guards)
TOTAL:              41 unique import-site files
```

### File list (alphabetical, with wrapper-import categories)

```
tests/sim/test_chain_gpsim_waiting.py                  -- chain,gpsim
tests/sim/test_control_v15b_port_compatibility.py      -- control,gpsim
tests/sim/test_control_v16b_port_compatibility.py      -- control,gpsim
tests/sim/test_main_dsp_deafness_chain.py              -- chain,control,gpsim
tests/sim/test_main_gpsim_command_compatibility.py     -- chain,control,gpsim
tests/sim/test_main_gpsim_command_edges.py             -- chain,control,gpsim
tests/sim/test_main_gpsim_command_matrix.py            -- chain,control,gpsim
tests/sim/test_main_gpsim_portability.py               -- chain,main,timer3
tests/sim/test_main_gpsim_preset_banks.py              -- chain,gpsim
tests/sim/test_main_gpsim_usb_engine.py                -- chain,control,gpsim
tests/sim/test_main_stdby_pin_io.py                    -- chain,control,gpsim,wire
tests/sim/test_patch_compatibility.py                  -- main (utility import)
tests/sim/test_reconnect_wake_gate.py                  -- chain,control,gpsim,wire
tests/sim/test_robustness_waiting.py                   -- control,gpsim
tests/sim/test_v171_fault_indicator.py                 -- control,gpsim
tests/sim/test_v171_full_sync_retry.py                 -- control,gpsim
tests/sim/test_v171_ir_endpoints.py                    -- control,gpsim
tests/sim/test_v171_layer1_bounded_tx.py               -- control,gpsim
tests/sim/test_v171_layer2_full_sync_step.py           -- control,gpsim
tests/sim/test_v171_layer5_diag_page.py                -- control,gpsim
tests/sim/test_v171_preset_inline.py                   -- control,gpsim
tests/sim/test_v171_preset_menu.py                     -- control,gpsim
tests/sim/test_v171_reconnect_wake.py                  -- control,gpsim
tests/sim/test_v171_sentinel_reconnect.py              -- control,gpsim
tests/sim/test_v171_v31_chain.py                       -- chain,gpsim
tests/sim/test_v171_v32_layer5_diag_chain.py           -- control,gpsim,wire
tests/sim/test_v17_chain.py                            -- chain,gpsim
tests/sim/test_v17_relocation.py                       -- control
tests/sim/test_v17_shifted_full_parity.py              -- control,gpsim
tests/sim/test_v28_wire_delayed_switch_repros.py       -- control,gpsim,wire
tests/sim/test_v30_relocation.py                       -- chain,gpsim,main
tests/sim/test_v31_command_matrix.py                   -- chain,control,gpsim
tests/sim/test_v31_dsp_boot_equivalence.py             -- chain,control,gpsim
tests/sim/test_v31_happy_path.py                       -- chain,control,gpsim
tests/sim/test_v31_review_findings.py                  -- chain,control,gpsim,wire
tests/sim/test_v31_usb_hid_dispatch.py                 -- chain,control,gpsim
tests/sim/test_v31_usb_preset_ab.py                    -- gpsim (guard only)
tests/sim/test_v31_v163b_robustness.py                 -- chain,control,gpsim,wire
tests/sim/test_v32_layer5_diag_counters.py             -- chain,control,gpsim,main
tests/sim/test_wire_chain_bridge.py                    -- wire (DELETE WITH WRAPPER)
tests/sim/test_wire_chain_gpsim.py                     -- gpsim,wire
```

## Surgery shape per file

The 41 files split into THREE categories:

### A. "delete with wrapper" (purely gpsim infrastructure tests)

These files exercise gpsim-only mechanics that have no rust analogue;
when the wrapper is deleted the test is meaningless.  Per the file's
own docstring (`test_wire_chain_bridge.py:8-11`): "When P4.9 deletes
the gpsim wire-chain infrastructure, the bridge and these tests get
removed together."

  * `tests/sim/test_wire_chain_bridge.py`
  * `tests/sim/test_wire_chain_gpsim.py`

Action: `git rm` together with `wire_chain_gpsim.py` deletion.

### B. "utility-import only" (no `if dlcp_sim_backend == "gpsim":` body)

These files just import a backend-agnostic utility (HEX builders,
config tables, etc.) that happens to live in a `_gpsim`-named module.
The utility must be MIGRATED to a non-gpsim home (e.g.,
`src/dlcp_fw/sim/main_seed.py` for `build_seeded_main_sim_hex`)
BEFORE the wrapper module is deleted.

  * `tests/sim/test_patch_compatibility.py` -- imports
    `build_seeded_main_sim_hex` from `main_gpsim.py`.
  * `tests/sim/test_v17_relocation.py` -- imports `_read_reg` from
    `control_gpsim.py` (also a utility; verify it's not actually
    a runtime call).

Action: identify the utility, audit its dependencies, move to a new
module, update import in this test file (and any other consumers).

### C. "dual-path test bodies with `if dlcp_sim_backend == "gpsim":`"

The bulk: 37 of 41 files.  Each has the standard dual_supported
shape:

```python
try:
    from dlcp_fw.sim.control_gpsim import GpsimControlHarness
    _IMPORT_OK = True
except Exception:
    _IMPORT_OK = False

try:
    from dlcp_fw.sim.dlcp_sim_native import Chain as RustChain
    _RUST_CHAIN_IMPORT_OK = True
except Exception as exc:
    _RUST_CHAIN_IMPORT_OK = False
    _RUST_CHAIN_IMPORT_ERROR = exc

def _require_gpsim() -> None:
    if not gpsim_available():
        pytest.skip("gpsim not installed")
    if not _IMPORT_OK:
        pytest.skip("control_gpsim harness not importable")

def _require_rust() -> None:
    if not _RUST_CHAIN_IMPORT_OK:
        pytest.fail(
            "rust dlcp_sim_native facade not importable -- "
            f"{_RUST_CHAIN_IMPORT_ERROR!r}"
        )

def _run_in_backends(backend, hex_path, body, ...) -> None:
    if backend in {"rust", "dual"}:
        _require_rust()
        chain = RustChain.from_v17_chain(str(hex_path))
        body(chain)
    if backend in {"gpsim", "dual"}:
        _require_gpsim()
        h = GpsimControlHarness(hex_path, ...)
        try:
            body(h)
        finally:
            h.close()

@pytest.mark.dual_supported
@pytest.mark.gpsim
@pytest.mark.slow
def test_xxx(v171_hex: Path, dlcp_sim_backend: str) -> None:
    def _do(h) -> None:
        ...
    _run_in_backends(dlcp_sim_backend, v171_hex, _do)
```

Surgery for each file in this category:

  1. Delete `from dlcp_fw.sim.gpsim import gpsim_available`.
  2. Delete the `try: from dlcp_fw.sim.control_gpsim import ...`
     block + `_IMPORT_OK` flag.  (Keep the rust try/except.)
  3. Delete `_require_gpsim()` function.
  4. Simplify `_run_in_backends`: drop the `backend` parameter, drop
     the `if backend in {"gpsim", "dual"}:` block, drop unused
     `chunk_cycles` / `hold_cycles` / `eeprom_kwargs` helpers that
     were gpsim-specific.  Rename to `_run_with_rust` or similar.
  5. Drop `dlcp_sim_backend: str` from each test signature; drop
     `dlcp_sim_backend` from each `_run_in_backends(...)` call.
  6. Drop `@pytest.mark.gpsim` from each test (`@pytest.mark.dual_
     supported` stays since it still indicates the migration boundary
     for legacy tooling, until the marker is retired wholesale).

Verify per file:

  ```bash
  DLCP_SIM_BACKEND=rust .venv_ep0/bin/python -m pytest \
    tests/sim/<file>.py -q
  ```

  Expected: identical pass/skip/xfail counts to current rust mode.

### Special case: `test_v171_v32_layer5_diag_chain.py`

Already partially migrated in PF.3 (the wiggle helper exists).  The
remaining XFAIL'd tests reference both wrappers and need careful
treatment under task #117.  Audit BEFORE this file lands phase-2
surgery.

## Wrapper deletion order

After all 41 files are surgically migrated and tests are green:

  1. Audit `main_gpsim.py` for non-gpsim utilities (e.g.,
     `build_seeded_main_sim_hex`, `MainI2CRegFileDevice`,
     `default_main_i2c_regfile_devices`, `main_adc_to_voltage`).
     Move utilities to a new module
     (`src/dlcp_fw/sim/main_runtime.py` or similar).
  2. Same audit for `control_gpsim.py` -- e.g., `_read_reg`,
     `_write_reg`, `_KEY_ALIASES`, `SCAN_BITS`.  Move utilities.
  3. Same for `chain_gpsim.py`, `wire_chain_gpsim.py` (if any
     non-gpsim code lives there).  `gpsim.py` is the gpsim binary
     locator -- delete entirely.
  4. `git rm src/dlcp_fw/sim/{chain_gpsim,wire_chain_gpsim,control_
     gpsim,main_gpsim,main_gpsim_timer3,gpsim}.py`.
  5. Edit `src/dlcp_fw/sim/__init__.py` to remove the 6 re-exports
     (lines 4-21 of that file as of HEAD).
  6. `git rm -r vendor/gpsim-0.32.1-xtc/`.
  7. Update `scripts/gpsim-xtc` and `scripts/gpsim` (CLI wrappers
     that invoke the now-absent build) to either delete or convert
     to "this binary has been retired" stubs.
  8. Update `tests/sim/conftest.py`: drop `DLCP_SIM_BACKEND_GPSIM`
     and `DLCP_SIM_BACKEND_DUAL` from the valid set; the
     `pytest_collection_modifyitems` auto-skip becomes inert if the
     marker is retired.  Decide whether to keep `dual_supported` as
     an inert marker (for one release cycle) or remove it.
  9. Update `AGENTS.md` "Source Code Map" / "Tests" sections to
     remove gpsim references.
 10. Update `scripts/check_gpsim_excision.py`: phase 2 inventory
     should now report 0; convert to a regression gate that fails
     if any wrapper import re-appears.

## Verification gates (after each batch and the final commit)

  * `python3 scripts/check_gpsim_excision.py` -> phase-1 clean +
    phase-2 import count drops.
  * `DLCP_SIM_BACKEND=rust .venv_ep0/bin/python -m pytest tests/sim
    -n 16 -q -m "not slow"` matches the PF.1 baseline (no new
    failures introduced).
  * `DLCP_SIM_BACKEND=rust .venv_ep0/bin/python -m pytest tests/sim
    -n 16 -q -m slow` similarly matches.
  * After wrapper deletion: `git grep "from dlcp_fw.sim.chain_gpsim"`
    etc. should return no hits.

## Effort estimate

  * Surgery (37 category-C files): ~5-15 min per file × 37 = 4-9 hours
    of focused per-file editing.
  * Utility migration (audits + moves): ~2-4 hours.
  * Wrapper + vendor + artifact deletion + final verify: ~1-2 hours.
  * **Total: 7-15 hours** across multiple sessions.

Suggested batching for parallel agents:

  * Batch 1 (5 files, ~30-60 min): test_v171_preset_inline.py,
    test_v171_preset_menu.py, test_v171_ir_endpoints.py,
    test_v171_fault_indicator.py, test_v171_full_sync_retry.py
  * Batch 2 (5 files): test_v171_reconnect_wake.py,
    test_v171_sentinel_reconnect.py, test_v171_layer1_bounded_tx.py,
    test_v171_layer2_full_sync_step.py, test_v171_layer5_diag_page.py
  * Batch 3 (6 files, V1.7 tests + V31): test_v17_chain.py,
    test_v17_shifted_full_parity.py, test_v171_v31_chain.py,
    test_v31_command_matrix.py, test_v31_dsp_boot_equivalence.py,
    test_v31_happy_path.py
  * Batch 4 (5 files, more V31): test_v31_review_findings.py,
    test_v31_usb_hid_dispatch.py, test_v31_usb_preset_ab.py,
    test_v31_v163b_robustness.py, test_v32_layer5_diag_counters.py
  * Batch 5 (6 files, command/main): test_main_gpsim_command_*,
    test_main_gpsim_portability.py, test_main_gpsim_preset_banks.py,
    test_main_gpsim_usb_engine.py
  * Batch 6 (5 files, chain/wire): test_chain_gpsim_waiting.py,
    test_main_dsp_deafness_chain.py, test_main_stdby_pin_io.py,
    test_reconnect_wake_gate.py, test_robustness_waiting.py
  * Batch 7 (4 files, control + V28): test_control_v15b_port_*,
    test_control_v16b_port_*, test_v28_wire_delayed_switch_repros.py,
    test_v30_relocation.py
  * Batch 8 (utility migration + special cases): test_patch_
    compatibility.py, test_v17_relocation.py, test_v171_v32_layer5_
    diag_chain.py
  * Batch 9 (delete-with-wrapper): test_wire_chain_bridge.py,
    test_wire_chain_gpsim.py

## What NOT to do

  * Do not delete the wrapper modules in the same commit as the
    test surgery -- the test files will lose their import target
    mid-surgery and break the rust suite.
  * Do not retire the `dual_supported` marker until conftest cleanup
    -- pytest will warn `PytestUnknownMarkWarning` for files still
    carrying it.
  * Do not touch `scripts/gpsim_*` or related operator tooling that
    was already deleted in phase 1; those paths are gone.
  * Do not edit `vendor/gpsim-0.32.1-xtc/` -- it goes via `git rm -r`
    in step 6 of the wrapper deletion order, not via per-file edits.

## Tracking

After each batch lands a commit:

  * Update `scripts/check_gpsim_excision.py`'s phase-2 inventory in
    the next run; the per-wrapper count should monotonically drop.
  * Update task #102's description with a strikethrough of completed
    files / batches so future agents see the remaining backlog.

## References

  * Spec: `docs/SIM_REWRITE_RUST_SPEC.md` §3 "Migration protocol"
  * Progress ledger: `docs/SIM_REWRITE_RUST_PROGRESS.md` "P4
    followup tracker"
  * Phase 1 commit: 5a56279 (initial 30+14 deletion)
  * Phase 2 #112 (commit 802e932): scripts/check_gpsim_excision.py
    AST walker for inventory
  * PF.3 partial (commit 4118a4e + 7ddf60b): un-XFAIL'd
    diag_page_polls + addressed codex review
