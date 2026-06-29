# IMPL: SRC4382 Auto Detect Stimulus Matrix

Date: 2026-06-20
Status: Reviewed - ready for implementation
Source spec: `docs/SRC4382_AUTODETECT_STIMULUS_MATRIX_SPEC.md`
Scope: add deterministic simulation tooling and tests for stock V1.6b/V2.3
versus current V1.73/V3.5 Auto Detect behavior across both MAINs.

## Source Requirements

Goals:

- Run stock CONTROL V1.6b + MAIN V2.3 first, save the exact stimuli and
  observed outputs, then run current CONTROL V1.73 + MAIN V3.5 with the same
  stimuli.
- Simulate the baseline source timeline: silence, S/PDIF, silence,
  S/PDIF plus Analog 1, silence, Optical, silence, USB Audio.
- Observe both MAIN roles in the two-MAIN chain.
- Compare current behavior against stock while accepting intentional V3.5
  robustness differences, especially rejecting `RXCKR != 0` candidates when
  `0x14.UNLOCK` is set.
- Keep the exact 1-second source-change timeline separate from fresh-acquisition
  pass/fail cases so V3.5 hard-loss debounce is classified, not hidden.
- Save versioned, hash-linked artifacts with schema tests.
- Emit deterministic pytest verdicts plus optional LLM-readable artifacts.

Non-goals:

- No firmware change.
- No live hardware flash, acoustic run, or hardware-state mutation.
- No full analog audio detector model.
- No LLM-dependent release gate.

Invariants:

- Auto Detect route/TAS contract remains the existing firmware contract:
  route request `0x093`, applied route shadow `0x0AB`, route event
  `event_flags.bit1`, SRC4382 route pair writes, and TAS3108 `0x30` refresh.
- Artifacts are generated under `artifacts/sim/current/...` for operator runs
  and under pytest temporary directories for tests.
- The implementation must preserve unrelated worktree changes.

## Required Docs Read

- `AGENTS.md`: canonical paths, release artifacts, simulator/test inventory,
  and current verification command conventions.
- `README.md`: current V3.5/V1.73 release pair, simulator build requirements,
  validation commands, and no-warranty flashing caveats.
- `CODING_STYLE.md`: Python/assembly surrounding-style rule and no unrelated
  formatting or renames.
- `docs/SIMULATION.md`: Rust simulator is the only backend; public Python
  facade, chain construction, stepping, mutation, and read-back surfaces.
- `docs/TEST_SIMULATOR.md`: historical simulator policy and test layout.
- `docs/HARDWARE_TEST.md`: live hardware tests are separate, skipped by default,
  and use `--run-hardware`; this work is simulator-only.
- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md`: route/TAS contract and route table.
- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md`: current V3.4+ lock oracle
  and acceptable current-versus-stock divergence.
- `docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md` and
  `scripts/exploratory_oracle_run.py`: existing model-readable exploratory
  artifact/oracle pattern.

Deployment docs:

- README "Upgrade Path" and `docs/HARDWARE_TEST.md` were read only to confirm
  there is no deploy step for this docs/test-only work.  Implementation must not
  flash hardware or publish release hexes.

## Current Implementation Evidence

- `src/dlcp_fw/sim/dlcp_sim_native.py`
  - `Chain.from_v171_v32(control_hex_path, main_hex_path, ...)` builds the
    three-core ring and accepts explicit stock or current hex paths.
  - `Chain.from_v17_chain(control_hex_path, main_hex_path)` provides a
    single-MAIN stock-family path, but this IMPL must use the three-core path so
    both PB roles are covered.
  - `poke_main_src4382_reg`, `read_main_src4382_reg`,
    `read_main_src4382_stats`, and `read_main_src4382_write_values` are already
    exposed, so no Rust simulator change is required for register-level source
    driving.
- `tests/sim/test_v171_v32_source_select_parity.py`
  - Uses `STOCK_CONTROL_HEX_V16B` plus `STOCK_MAIN_COMBINED_HEX` through
    `from_v171_v32(...)` for stock-vs-current parity.
  - Defines the deployed fixed-source menu order and route table used by the
    new matrix.
- `tests/sim/test_v32_src4382_autodetect_polling.py`
  - Already asserts no-source/source-present cadence, RX4 scan reachability,
    explicit input preemption, fixed-input quieting, and dual-MAIN liveness.
  - It pokes `0x13` directly, so it does not model receiver-specific physical
    source presence.
- `tests/sim/test_v34_src4382_lock_hysteresis.py`
  - Models `0x13.RXCKR` plus `0x14.UNLOCK` and proves V3.4+ lock robustness.
  - It is pinned to V3.4, not V3.5, and it is not a stock/current comparison.
- `scripts/sim_chain_exploratory.py`
  - Already captures MAIN state, SRC registers, TAS state, and JSONL artifacts
    for exploratory campaigns.
  - It is broad and randomized; the requested work needs a deterministic,
    small, reproducible matrix.
- `scripts/exploratory_oracle_run.py`
  - Provides model-command invocation and JSON extraction patterns that can be
    reused if optional LLM judgement is added to the matrix runner.

## Gap Analysis

Existing coverage:

- Manual source selection parity is compared against stock.
- Auto Detect cadence and lock robustness are covered for patched/current
  lineages.
- Both-MAIN chain liveness is covered in focused V3.2/V3.3 tests.

Missing:

- No exact source-presence timeline test.
- No current V1.73/V3.5 Auto Detect matrix.
- No stock-first, current-second trace artifact pair.
- No receiver-aware source model that changes `0x13/0x14/0x12` based on the
  firmware-selected `0x0D` candidate.
- No compact LLM/oracle card for this specific stock/current comparison.

Stale or intentionally out of scope:

- `docs/TEST_SIMULATOR.md` still contains historical gpsim material.  Use
  `docs/SIMULATION.md` and current tests for implementation.
- Analog 1 is not a real SRC4382 receiver.  The matrix records it as a
  competitor/noise condition, not as an auto-detected SRC lock.

## Proposed Implementation

### Work Unit 1: Matrix Harness Module

Create `src/dlcp_fw/sim/src4382_autodetect_matrix.py`.

Responsibilities:

- Define central constants and schema names:
  - `SIM_TICKS_PER_SECOND = 48_000_000`
  - `SHORT_PHASE_TICKS = SIM_TICKS_PER_SECOND`
  - `DRIVER_STEP_TICKS = 250_000`
  - `LOCKED_SOURCE_CONVERGENCE_TICKS = SIM_TICKS_PER_SECOND`
  - `SHORT_SILENCE_GRACE_TICKS = SIM_TICKS_PER_SECOND`
  - `HARD_LOSS_CLEAR_TICKS = 14 * SIM_TICKS_PER_SECOND`
  - `TRACE_REQUIRED_FIELDS`, `MANIFEST_SCHEMA_VERSION`, and route/RX tables.
- Define the deterministic dataclasses or typed dictionaries:
  `SourcePhase`, `DigitalSourceState`, `StimulusPlan`, `ComboConfig`,
  `TraceRow`, `Manifest`, `ComparisonPair`, and `ComparisonResult`.
- Define combo configs:
  - `stock_v16b_v23`: `STOCK_CONTROL_HEX_V16B`, `STOCK_MAIN_COMBINED_HEX`
  - `current_v173_v35`: `V173_CONTROL_HEX`, `V35_MAIN_HEX`
- Build each combo with `Chain.from_v171_v32(...)`.
- Navigate or force Auto Detect consistently:
  - Default acceptance runs must enter or assert Auto Detect through the
    CONTROL-visible boot/menu state used by existing source-select parity tests.
  - Direct RAM seeding is allowed only for labeled unit/helper scenarios and
    must be recorded in `stimuli.json` if used.
- Implement a receiver-aware status driver:
  - Read each MAIN's SRC4382 `0x0D`.
  - Map selected RX to the active source state for that phase.
  - Step no more than `DRIVER_STEP_TICKS`, then poke `0x13`, `0x14`, and
    `0x12` before the next firmware-visible status read.
  - Record the active receiver set, selected candidate, scan candidate index,
    and driver updates in each trace row.
  - Keep PB1/PB2 independent, defaulting to identical state.
- Implement required schedules:
  - `continuous_user_timeline`: the exact 1-second sequence from the user
    request.  It preserves time ordering and classifies short-gap route hold as
    `handoff_delayed_by_hard_loss` instead of resetting state silently.
  - `fresh_acquisition_matrix`: S/PDIF, Optical, and USB Audio acquired from a
    fresh or long-unlocked Auto Detect state.
  - `rxckr_hole_locked`, `rxckr_nonzero_unlocked`, `sustained_silence_clear`,
    and `two_digital_sources` focused variants.
- Implement `compare_traces(stock, current, stimuli)` as a first-class contract:
  - pair rows by schedule, phase, PB unit, and sample point;
  - assert identical stimulus hash and execution order;
  - fail when stock reaches a live expected route and current misses/wrongs it,
    except explicitly classified `intended_robustness` or
    `handoff_delayed_by_hard_loss`;
  - classify pair outcomes as `match`, `current_worse`,
    `intended_robustness`, `handoff_delayed_by_hard_loss`, or `needs_human`.
- Build `manifest.json` metadata from the same module: schema version, command
  argv, simulator/backend version when available, exact tick schedule,
  `phase_scale=1.0`, firmware repo-relative paths and SHA256 hashes, release
  identities when available, git dirty summary, `stimuli_sha256`, completion
  status, and card size.
- Set `MANIFEST_SCHEMA_VERSION = 1`.
- Compute `stimuli_sha256` from canonical JSON:
  `json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")`.

Keep this module pure Python and simulator-only.  Do not change Rust unless an
existing facade method is proven insufficient.

### Work Unit 2: CLI Runner

Create `scripts/sim_src4382_autodetect_matrix.py`.

Behavior:

- Default command runs stock first, writes `stimuli.json` and
  `stock_trace.jsonl`, runs current second, writes `current_trace.jsonl`,
  compares, and writes `manifest.json`, `comparison.json`, `comparison.md`,
  and `oracle_card.md`.
- Default output is a unique timestamped directory below
  `SIM_ARTIFACTS_DIR / "src4382_autodetect_matrix"`.
- Options:
  - `--out-root PATH` to choose the parent directory for timestamped runs
  - `--out-dir PATH` to choose an exact directory
  - `--overwrite` to permit reusing a non-empty exact output directory
  - `--model-cmd CMD` optional trusted local/read-only model command
  - `--model-timeout SECONDS`, default `120`
  - `--quiet` for pytest-friendly output
- Exit codes:
  - `0`: deterministic comparison passes
  - `1`: deterministic regression
  - `2`: simulator/setup error
  - `3`: LLM invocation failed when `--model-cmd` was requested
- Refuse to write into a non-empty `--out-dir` unless `--overwrite` is present.
- Write artifacts atomically enough that `manifest.json` can record incomplete
  status if a run fails after partial output.
- Always generate `oracle_card.md`.  Omitting `--model-cmd` skips only model
  invocation, not card generation.
- Parse `--model-cmd` with `shlex.split` and call
  `subprocess.run(argv, shell=False, input=..., timeout=...)`.
- Document that `--model-cmd` argv is recorded for reproducibility and must not
  contain secrets.

The CLI should reuse the module from Work Unit 1 and contain no firmware
knowledge beyond argument parsing and file output.

### Work Unit 3: Deterministic Pytest Coverage

Create `tests/sim/test_src4382_autodetect_stimulus_matrix.py`.

Required tests:

1. `test_receiver_status_driver_tracks_selected_src4382_rx`
   - Unit-level test for RX1/RX2/RX3/RX4 mapping into `0x13/0x14/0x12`.
2. `test_rx4_only_source_is_seen_only_after_firmware_selects_rx4`
   - Integration-level cadence test where RX4 is the only live receiver and
     RX1-RX3 remain absent until firmware writes `0x0D=0x0B`.
3. `test_manifest_trace_and_comparison_schemas_are_valid`
   - Runs the matrix into `tmp_path`.
   - Parses `stimuli.json`, `manifest.json`, both JSONL traces,
     `comparison.json`, and `comparison.md`.
   - Asserts required files, schema versions, row fields/types/enums, PB1/PB2
     coverage per phase, exact tick schedules, firmware hashes, and
     `stimuli_sha256` linkage.
4. `test_stock_reference_trace_runs_before_current_trace`
   - Runs the default matrix into `tmp_path`.
   - Asserts `stimuli.json`, `stock_trace.jsonl`, `current_trace.jsonl`,
     `manifest.json`, `comparison.json`, `comparison.md`, and `oracle_card.md`
     exist.
   - Asserts artifact metadata records stock before current.
5. `test_compare_traces_uses_stock_reference_first`
   - Exercises `compare_traces(...)` directly with synthetic paired outcomes.
   - Fails if stock misses the intended reference behavior or if current is
     hardcoded without stock/current pairing.
6. `test_current_v35_fresh_acquisition_detects_spdif_optical_and_usb`
   - Runs the fresh-acquisition matrix.
   - Asserts current detects S/PDIF, Optical, and USB Audio on both MAINs.
   - Asserts no waiting/wedge, no PB divergence, and no muted PCM.
7. `test_continuous_user_timeline_classifies_short_gap_handoff`
   - Runs silence, S/PDIF, silence, S/PDIF+Analog 1, silence, Optical, silence,
     USB Audio with no hidden reset.
   - Asserts short-gap previous-route hold is represented by verdict fields
     rather than treated as either fresh acquisition success or wrong-route
     failure.
8. `test_current_rejects_unlocked_rxckr_candidate_without_counting_as_regression`
   - Uses `RXCKR != 0`, `UNLOCK=1`.
   - Allows stock to commit and requires current to reject, with comparison
     classification `intended_robustness`.
9. `test_current_holds_locked_rxckr_hole_after_acquisition`
   - Acquires a route, then drives `RXCKR=0`, `UNLOCK=0`.
   - Asserts route is held on current and not flagged as regression if stock
     behaves differently.
10. `test_sustained_hard_loss_eventually_clears_or_rescans`
    - Drives no-source/unlock for `HARD_LOSS_CLEAR_TICKS`.
    - Asserts current does not hold a dead route indefinitely.
    - Mark `slow` if runtime exceeds the local norm.
11. `test_two_digital_sources_selects_only_live_route_and_keeps_pbs_consistent`
    - Runs RX2+RX4 simultaneous lock.
    - Records selected route and scan position for stock/current.
    - Fails only on non-live selection, wedge, or unscripted PB divergence.
12. `test_forced_optical_failure_fails_before_model_invocation`
    - Forces/mocks current PB1 and PB2 Optical miss cases.
    - Asserts deterministic comparison returns failure and no model call occurs.
13. `test_oracle_card_is_generated_without_invoking_model`
   - Asserts card includes stock/current summaries, comparison flags, and raw
     repo-relative artifact paths.
   - Asserts the card is under the size cap and contains no `/Users/`, `$HOME`,
     HID serial tokens, environment dumps, or raw JSONL.
14. `test_cli_writes_artifacts_and_returns_nonzero_on_forced_regression`
   - Uses a synthetic comparison fixture or monkeypatch to force a wrong route,
     proving the CLI returns `1` without invoking any model.
15. `test_cli_invokes_fake_model_without_shell_and_records_errors`
   - Uses a fake local command that reads stdin and writes JSON.
   - Asserts `oracle_verdict.json` on success, `oracle_error.json` plus exit
     `3` on malformed JSON or timeout, and no shell expansion behavior.

Runtime control:

- Share a single default-matrix fixture/artifact within the test module where
  safe.
- Keep unit/schema tests separate from full-chain runs.
- Keep sustained hard-loss tests isolated from reused default-matrix fixtures
  and mark them `slow` if they exceed the local norm.
- Acceptance evidence uses `phase_scale=1.0`; no scaled canonical artifacts.
- Treat `LOCKED_SOURCE_CONVERGENCE_TICKS = 1s` as an empirical budget during
  implementation; if measured cadence proves it too tight, update the spec and
  IMPL explicitly rather than silently loosening tests.

### Work Unit 4: Optional LLM Judgement

Implement optional LLM judgement in the CLI with a small local helper modeled
after `scripts/exploratory_oracle_run.py`:

- Pass only `oracle_card.md` content and a concise rubric to `--model-cmd`.
- Require JSON object output with `overall`, `confidence`, and `findings`.
- Write the parsed object to `oracle_verdict.json`.
- On timeout, nonzero exit, or malformed JSON, write `oracle_error.json` with
  `run_ok=false`, command argv, timeout, card digest, exit code, parse error,
  and bounded stderr/stdout snippets.
- If the model returns malformed JSON, fail only the CLI invocation using
  `--model-cmd`; pytest coverage for card generation stays model-free.
- Reuse or factor the existing JSON-object extraction helper instead of copying
  a second incompatible parser.  Do not reuse the existing shell-based model
  invocation path.
- Invoke with `shell=False`, a bounded timeout, stdin only, and a prompt that
  forbids file writes, tools, network actions, or repo mutation.
- Redact the card before invocation and test the redaction.

The prompt must tell the model:

- Stock is the reference trace.
- Current is allowed to reject unlocked candidates because V3.4+ uses
  `0x14.UNLOCK`.
- Any fresh or cleared Optical locked PCM phase where current fails route `4`
  on either MAIN is a likely regression.
- Any PB1/PB2 divergence under identical scripted source state is a likely
  regression.

### Work Unit 5: Documentation Touch-Up

Update docs only if needed after implementation:

- Add a short "Related tests" note to
  `docs/SRC4382_AUTODETECT_STIMULUS_MATRIX_SPEC.md` with actual command output.
- Add `scripts/sim_src4382_autodetect_matrix.py` to the canonical CLI entry list
  in `AGENTS.md` because the spec exposes it as a maintained operator runner.

## Likely Files

Add:

- `src/dlcp_fw/sim/src4382_autodetect_matrix.py`
- `scripts/sim_src4382_autodetect_matrix.py`
- `tests/sim/test_src4382_autodetect_stimulus_matrix.py`

Possibly update:

- `docs/SRC4382_AUTODETECT_STIMULUS_MATRIX_SPEC.md`
- `docs/IMPL_SRC4382_AUTODETECT_STIMULUS_MATRIX.md`
- `AGENTS.md`
- `src/dlcp_fw/sim/oracle_json.py` only if sharing JSON extraction is cleaner
  than importing a script helper.

Do not touch:

- firmware release hex files
- MAIN or CONTROL assembly
- Rust simulator internals unless the Python facade proves insufficient

## Test Plan

Focused tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_src4382_autodetect_stimulus_matrix.py
```

Adjacent SRC tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_source_select_parity.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py
```

Broader simulator gate when runtime budget allows:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q \
  -k "src4382 or autodetect or source_select or v35 or v173"
```

Manual artifact smoke:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_src4382_autodetect_matrix.py
```

Optional LLM smoke:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_src4382_autodetect_matrix.py \
  --model-cmd '<trusted-read-only-model-command>' \
  --model-timeout 120
```

Simulator build caveat:

- A prior collect-only attempt in this workspace hit a Python native extension
  mismatch: `symbol not found in flat namespace '_PyIter_NextItem'`.  If that
  recurs during implementation, rebuild the PyO3 simulator module with:

```bash
PYO3_PYTHON="$PWD/.venv_ep0/bin/python" cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
```

Then rerun focused tests using `.venv_ep0/bin/python`.

## Deployment And Smoke Plan

No deployment or hardware flash is required.  This is simulator/test tooling.

No-deploy criteria:

- Any change to firmware hexes, assembly, or release builders is out of scope.
- Any live hardware command is out of scope unless the user separately requests
  it after reviewing simulator evidence.

If a later firmware fix is requested based on these traces, that fix must get a
separate SPEC/IMPL or explicit implementation request.

## Rollback Plan

- Remove the new helper module, script, and test file.
- Remove or revert only the new SPEC/IMPL documentation if the work unit is
  abandoned.
- Delete generated artifacts under
  `artifacts/sim/current/src4382_autodetect_matrix/`.
- No EEPROM, hardware, firmware, or release artifact rollback is needed.

## Risks And Assumptions

- The SRC4382 source model is register-level.  It is sufficient for firmware
  Auto Detect logic, but it is not a physical optical/coax/USB electrical model.
- Analog 1 cannot be faithfully auto-detected through SRC4382.  The matrix
  treats analog presence as metadata/noise unless future code evidence proves
  another firmware signal-presence path.
- Stock behavior is the reference, but not every stock behavior is inherently
  better.  The comparison must classify V3.5 `UNLOCK` strictness as intended
  robustness when the trace proves that is the only divergence.
- Short 1-second silence is not a cleared-source guarantee on V3.5.  Continuous
  handoff delays must be classified separately from fresh acquisition failures.
- Long simulation cadence can make tests slow.  Use focused phase budgets and
  mark slow variants if needed.
- The implementation may run in a dirty worktree.  Use focused pathspecs and do
  not revert unrelated changes.

## Acceptance Criteria

- New tests generate stock and current traces from the same stimulus schedule.
- Fresh-acquisition locked PCM cases pass for current V1.73/V3.5 on both MAINs.
- The exact continuous user timeline is saved and classifies short-gap handoff
  behavior without hidden resets.
- A simulated current Optical Auto Detect failure produces a deterministic
  failure before any LLM is invoked.
- The unlocked-candidate divergence is classified as intended robustness.
- Sustained hard loss clears/re-scans rather than holding a dead route forever.
- `two_digital_sources` records scan position and fails only on non-live route,
  wedge, or unscripted PB divergence.
- Manifest, trace schema, comparison schema, firmware hashes, and card
  redaction are test-gated.
- The oracle card is compact, file-backed, and model-agnostic.
- Focused and adjacent tests pass or documented simulator build blockers are
  recorded in this IMPL.
- No deployment is performed.

## Post-Implementation Evidence

- Files changed:
  - `src/dlcp_fw/sim/oracle_json.py`
  - `src/dlcp_fw/sim/src4382_autodetect_matrix.py`
  - `scripts/sim_src4382_autodetect_matrix.py`
  - `tests/sim/test_src4382_autodetect_stimulus_matrix.py`
  - `AGENTS.md` canonical CLI list
  - this SPEC/IMPL documentation pair
- LOC delta for new executable/test files:
  - `oracle_json.py`: 67 lines
  - `src4382_autodetect_matrix.py`: 957 lines
  - `sim_src4382_autodetect_matrix.py`: 82 lines
  - `test_src4382_autodetect_stimulus_matrix.py`: 322 lines
- Exact test commands and results:
  - `PYTHONPATH=src .venv_ep0/bin/python -m py_compile src/dlcp_fw/sim/oracle_json.py src/dlcp_fw/sim/src4382_autodetect_matrix.py scripts/sim_src4382_autodetect_matrix.py tests/sim/test_src4382_autodetect_stimulus_matrix.py` -> passed
  - `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_src4382_autodetect_stimulus_matrix.py` -> `15 passed in 134.45s`
  - `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_v32_source_select_parity.py tests/sim/test_v32_src4382_autodetect_polling.py tests/sim/test_v32_src4382_audio_path_regression.py tests/sim/test_v34_src4382_lock_hysteresis.py tests/sim/test_v34_autodetect_loss_debounce.py` -> `79 passed in 332.34s`
- Generated artifact path:
  - `artifacts/sim/current/src4382_autodetect_matrix/20260620T215845Z/`
- Deterministic comparison result:
  - CLI command `PYTHONPATH=src .venv_ep0/bin/python scripts/sim_src4382_autodetect_matrix.py` -> `deterministic result: pass`
  - `comparison.json` summary: `match=20`, `handoff_delayed_by_hard_loss=4`, `intended_robustness=2`, `needs_human=8`
  - Fresh S/PDIF and fresh Optical matched stock/current on both MAINs.
  - Continuous short-gap Optical/USB phases held previous S/PDIF on current V3.5 and were classified as hard-loss-delay, not fresh-acquisition success.
  - `rxckr_nonzero_unlocked` showed stock committing route `1` while current rejected it as intended robustness.
  - Fresh USB Audio produced route `3` on both stock and current against the nominal route-`2` expectation, so the comparator classified it as `needs_human` rather than a current-only regression.
- LLM smoke command/result:
  - No external model command was run.  The focused pytest suite covers fake-model success and malformed-output error paths with shell-free invocation.
- Deploy/smoke evidence or no-deploy reason:
  - No firmware hex, assembly, release builder, live hardware, EEPROM, or flash state was intentionally changed.
- Remaining low-risk issues:
  - The `needs_human` USB Audio route observation should be inspected before using the matrix as evidence for USB Auto Detect correctness.
- Final acceptance status:
  - Implementation complete for simulator tooling/tests/artifacts.  No deployment performed.

## Reviewer Findings And Iteration History

Review gate target: 8 independent reviewer passes.

Initial reviewer ledger and disposition:

| Pass | Role | High | Medium | Low | Disposition |
| --- | --- | ---: | ---: | ---: | --- |
| 1 | Simplicity/scope | 0 | 4 | 2 | Revised: added `two_digital_sources`; removed skippable oracle card and phase-scale acceptance path; made AGENTS update mandatory; dropped unrelated V3.5 smoke gate. |
| 2 | Correctness/contract | 2 | 2 | 2 | Revised: split continuous handoff from fresh acquisition; added hard-loss timing constants and `compare_traces(...)` contract; made schema tests explicit. |
| 3 | Ops/tests/deploy | 2 | 5 | 0 | Revised: defined silence verdicts; required artifact schemas, firmware hashes, AGENTS entry, Optical negative tests, and no-deploy scope. |
| 4 | UX/API-consumer | 2 | 5 | 1 | Revised: default acceptance uses CONTROL-visible Auto Detect state; added comparison schema, card requirement, two-source case, and discoverability. |
| 5 | Security/privacy | 0 | 2 | 1 | Revised: bounded/redacted oracle card; shell-free timeout-bound model command; no edit-capable model example; AGENTS update mandatory. |
| 6 | Performance/reliability | 2 | 5 | 1 | Revised: closed-loop driver cadence; hard-loss semantics; runtime sharing/slow marking; model timeout; unique output dirs and overwrite guard. |
| 7 | Data/migration compatibility | 1 | 2 | 1 | Revised: added versioned manifest, firmware hashes, schedule hash, row schemas, `two_digital_sources`, and required card output. |
| 8 | Maintainability/observability | 2 | 4 | 2 | Revised: added central constants/schema, manifest provenance, trace validation, oracle error metadata, and generic dirty-worktree guidance. |

Follow-up review summary:

| Pass | Role | High | Medium | Low notes carried forward |
| --- | --- | ---: | ---: | --- |
| 1 | Simplicity/scope | 0 | 0 | Keep CONTROL-visible Auto Detect setup lightweight; focused/adjacent SRC gates remain authoritative. |
| 2 | Correctness/contract | 0 | 0 | Treat the 1-second acquisition budget as measured during implementation; model command read-only behavior is trust-based. |
| 3 | Ops/tests/deploy | 0 | 0 | Sustained hard-loss may be slow; optional model command remains outside deterministic gate. |
| 4 | UX/API-consumer | 0 | 0 | Pin initial schema version; model command read-only behavior is trust-based. |
| 5 | Security/privacy | 0 | 0 | Do not pass secrets in `--model-cmd` argv because argv is recorded. |
| 6 | Performance/reliability | 0 | 0 | Keep sustained hard-loss isolated; treat 1-second acquisition budget as empirical. |
| 7 | Data/migration compatibility | 0 | 0 | Prefer repo-relative paths and canonical JSON hashing for `stimuli_sha256`. |
| 8 | Maintainability/observability | 0 | 0 | Use `SIM_ARTIFACTS_DIR` for the default output root. |

Clean review summary: 8 follow-up reviewer passes, 0 unresolved High, 0
unresolved Medium.  Low notes above are folded into the implementation
requirements and do not block implementation.
