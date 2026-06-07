# RAM Bank Safety IMPL

Date: 2026-06-07
Status: Implemented - verified
Source spec: `docs/RAM_BANK_SAFETY_SPEC.md`
Scope: Implement a fail-closed RAM bank safety guard for MAIN V3.3 and CONTROL
V1.72, and measure any MAIN size impact from real RAM-bank fixes.

## Required Docs Read

- `AGENTS.md`: canonical layout, source/release artifact paths, build scripts,
  test suite shape, and release pairing rules.
- `README.md`: current V3.3/V1.72 build, validation, flashing, and simulator
  commands.
- `docs/RAM_BANK_SAFETY_SPEC.md`: source requirements for this IMPL.
- `docs/V32_SIZE_OPTIMIZATION_SPEC_and_IMPL.md`: authoritative MAIN size
  measurement pattern and warning that file size is not a valid metric.
- `tests/sim/test_v171_ram_static_analysis.py`: existing CONTROL-only RAM
  static-analysis gate to reuse rather than duplicate.
- `tests/sim/test_preset_filename_lcd_spec.py`: current one-off regression
  guard for the Preset filename BSR bug and native-chain coverage.

No production deployment docs are applicable. This is build/test tooling and
source hygiene; it must not require hardware flashing.

## Source Requirements

Goals:

- Make RAM bank ownership explicit and machine-checkable.
- Fail builds/tests on unsafe `BANKED`, `ACCESS`, `movff`, and `lfsr` RAM use.
- Forbid bank-ambiguous direct RAM operands in target executable sources.
- Reuse the existing static-analysis approach where possible.
- Prove whether MAIN size changed. The expected first-pass result is no MAIN
  size increase.

Non-goals:

- No runtime behavior changes.
- No blanket macro rewrite that adds hidden `movlb` instructions.
- No hardware deployment.
- No full historical source migration beyond target V3.3/V1.72 unless required
  by shared helpers.

User decisions captured:

- The guard must be robust, not best effort.
- Direct RAM access should be forbidden in target source.
- Semantic names should include bank information.
- The implementation must explicitly check whether MAIN size increases.

## Current Implementation Evidence

- `src/dlcp_fw/asm/dlcp_main_ram.inc` contains named V3.3 filename cells at
  physical `0x2F4..0x2FF`, but also many raw `ram_0xNNN` symbols. Current MAIN
  source still uses `ram_0x0A1` directly in the bug area.
- `src/dlcp_fw/asm/dlcp_control_ram.inc` documents banked CONTROL regions in
  comments. V1.72 filename cache lives in bank 2 (`0x220..0x244`,
  `0x255..0x25C`); diagnostics identity lives in bank 2 (`0x245..0x254`);
  Layer 5 diagnostic cache lives in bank 1. The comments are useful but are not
  the source of truth a checker can fully trust.
- `tests/sim/test_v171_ram_static_analysis.py` already parses CONTROL equates,
  detects duplicate same-bank cells, checks BANK-1 `movlb` discipline, rejects
  `movff` with BANK-1 operands, and checks ISR context safety. It is
  CONTROL/V1.71-specific and has warning-only indeterminate handling.
- `tests/sim/test_preset_filename_lcd_spec.py` now has
  `test_v33_an0_hysteresis_monitor_banks_delay_counter_before_uart_ring_alias`,
  a narrow structural guard for the exact recent MAIN bug. This should become a
  regression case covered by the shared RAM checker.
- `src/dlcp_fw/patch/build_v33_release.py` and
  `src/dlcp_fw/patch/build_v172_release.py` assemble via `assemble_v30()` and
  `assemble_v17()` respectively, already manage `.lst` rollback, and are the
  right release-build enforcement points.
- `src/dlcp_fw/sim/v30_symbols.py` and `src/dlcp_fw/sim/v17_symbols.py`
  already centralize gpasm assembly and listing handling.
- `docs/V32_SIZE_OPTIMIZATION_SPEC_and_IMPL.md` gives the correct MAIN size
  metrics: non-`0xFF` count in `0x1000..0x4BFF`, highest used byte below
  `0x4C00`, and free bytes before `0x4C00`.

## Gap Analysis

What exists:

- Narrow source-level regression guards for several BSR-sensitive bugs.
- A CONTROL-only static RAM test with useful parsing and BSR-walk concepts.
- Release builders that can call a checker before accepting generated HEX.
- Established MAIN size measurement snippets.

What is missing:

- One manifest that records RAM ownership, bank, operand, and physical address.
- Shared checker code usable by scripts, release builders, and pytest.
- Fail-closed behavior for indeterminate BSR paths.
- MAIN V3.3 coverage.
- CONTROL V1.72 bank-2 coverage.
- A rule forbidding raw `ram_0xNNN` and raw numeric RAM operands in target
  executable source.
- A required size/HEX identity report for checker/source-hygiene work.

Stale or weak patterns:

- Comments such as "callers must `movlb 0x02`" are not enforcement.
- One-off tests like the `an0_hysteresis_monitor` guard do not scale.
- Warning-only indeterminate sites in the existing static analysis are not
  robust enough for the target guard.

## Proposed Implementation

### WU1: Shared RAM Manifest

Add `src/dlcp_fw/asm/ram_bank_manifest.py` as the source of truth. Keep it in
Python rather than YAML for the first pass to avoid a new parser dependency and
to match existing repo helper style.

Required data model:

- target key: `main-v33`, `control-v172`
- cell name with bank/access suffix
- physical address
- bank
- operand
- access mode
- owner
- alias policy

Add path constants in `src/dlcp_fw/paths.py` only if needed by scripts/tests.

Initial manifest coverage must include:

- all named V3.3 MAIN cells in `dlcp_main_ram.inc`
- generated bank-explicit entries for remaining MAIN `ram_0xNNN` cells used by
  `dlcp_main_v33.asm`
- all named CONTROL V1.72 cells in `dlcp_control_ram.inc`
- generated bank-explicit entries for remaining CONTROL raw cells used by
  `dlcp_control_v172.asm`
- SFR/common-RAM exceptions needed by the parser

### WU2: Include Generation/Validation

Add `src/dlcp_fw/analysis/ram_bank_safety.py` with:

- manifest loader
- include emitter for MAIN and CONTROL
- current `.inc` parser
- validation that generated aliases and committed `.inc` content agree
- source scanner for target `.asm` files
- BSR dataflow checker

Do not immediately require developers to run a separate generator manually.
Instead:

- Commit generated/updated `.inc` aliases.
- Add a check that regenerates to memory and fails if the checked-in `.inc`
  differs.
- Print a clear command to regenerate if drift is detected.

### WU3: Source Alias Migration

Mechanically migrate target executable code away from direct RAM names:

- MAIN target: `src/dlcp_fw/asm/dlcp_main_v33.asm`
- CONTROL target: `src/dlcp_fw/asm/dlcp_control_v172.asm`

Rules:

- Replace `ram_0xNNN` executable operands with manifest names.
- Replace raw numeric RAM operands such as `0x73, BANKED` with manifest names.
- Preserve SFR names as-is.
- Preserve instruction sequence length unless a missing `movlb` is a real bug.
- Prefer bank-explicit generated names over broad exemptions when semantic name
  quality is unknown.
- Do not use macros for bulk migration in this work unit.

This WU is expected to change source text but not assembled program bytes,
except for already-required bug fixes that are in the working tree.

### WU4: Fail-Closed Checker CLI

Add `scripts/check_ram_access_safety.py` as the operator/build entry point.
It should call the shared library and support:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py \
  --target main-v33 --target control-v172
```

The checker must fail on:

- raw target RAM operands
- missing manifest entries
- duplicate physical cells without explicit aliasing
- illegal `ACCESS` RAM use
- `BANKED` RAM access where BSR is not proven equal to the manifest bank
- `movff` or `lfsr` using operand aliases instead of physical aliases
- include/manifest drift
- indeterminate BSR state

### WU5: Release Build Integration

Call the checker from:

- `src/dlcp_fw/patch/build_v33_release.py`
- `src/dlcp_fw/patch/build_v172_release.py`

Run the checker before copying the temp HEX to the canonical release path. The
existing rollback behavior for source/listing files must remain intact.

Avoid checking historical sources from these builders unless the builder is
actually emitting that release.

### WU6: Tests

Add `tests/sim/test_ram_bank_safety.py`.

Required tests:

- manifest duplicate physical address fails unless alias is explicit
- raw `ram_0xNNN` target operand fails
- raw numeric RAM operand fails
- SFR numeric/literal/data contexts do not false-positive
- `BANKED` bank-0 cell touched under proven `BSR=2` fails
- `BANKED` bank-2 cell touched under proven `BSR=0` fails
- local `movlb` makes an access pass
- call to a default-clobber routine before RAM access makes BSR indeterminate
  and fails
- `movff *_op, X` fails and `movff *_phys, X` passes
- `lfsr FSRn, *_phys` passes and `lfsr FSRn, *_op` fails
- checker catches a fixture version of the `an0_hysteresis_monitor` bug
- checker passes current `main-v33` and `control-v172`

Update existing one-off tests only after the shared checker covers their bug
class. Do not delete behavioral native-chain preset tests.

### WU7: MAIN Size and Binary Identity Evidence

Add or use a test/helper that assembles V3.3 to temp files before and after
implementation and reports:

- `used_bytes_pre_preset_b`
- `last_used_pre_preset_b`
- `free_bytes_before_0x4C00`
- byte comparison for `0x1000..0x4BFF`

Use `assemble_v30()` directly, not `build_v33_release.py`, because the release
builder bumps identity bytes.

Record the actual result in this IMPL under "Post-Implementation Evidence".
Unexpected MAIN growth blocks acceptance unless the user explicitly accepts it.

Suggested measurement command:

```bash
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from pathlib import Path
import tempfile
from dlcp_fw.paths import V33_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30
from dlcp_fw.sim.hexio import parse_intel_hex

with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "v33_size.hex"
    assemble_v30(V33_MAIN_ASM, out, output_lst=Path(td) / "v33_size.lst")
    mem = parse_intel_hex(out)
    used = [a for a in range(0x1000, 0x4C00) if mem.get(a, 0xFF) != 0xFF]
    last = max(used) if used else 0x0FFF
    print(f"used_bytes_pre_preset_b={len(used)}")
    print(f"last_used_pre_preset_b=0x{last:04X}")
    print(f"free_bytes_before_0x4C00={0x4C00 - (last + 1)}")
PY
```

## Likely Files

Code:

- `src/dlcp_fw/asm/ram_bank_manifest.py`
- `src/dlcp_fw/analysis/ram_bank_safety.py`
- `scripts/check_ram_access_safety.py`
- `src/dlcp_fw/patch/build_v33_release.py`
- `src/dlcp_fw/patch/build_v172_release.py`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `src/dlcp_fw/asm/dlcp_main_v33.asm`
- `src/dlcp_fw/asm/dlcp_control_v172.asm`
- optionally `src/dlcp_fw/paths.py`

Tests:

- `tests/sim/test_ram_bank_safety.py`
- `tests/sim/test_preset_filename_lcd_spec.py`
- possibly `tests/sim/test_v171_ram_static_analysis.py` if helpers move to the
  shared module

Docs:

- `docs/RAM_BANK_SAFETY_SPEC.md`
- `docs/RAM_BANK_SAFETY_IMPL.md`

Generated artifacts:

- temp `.hex` and `.lst` files under pytest tmpdirs only
- no new canonical release artifacts unless the implementation explicitly runs
  release builders

## Test Plan

Focused checker tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_ram_bank_safety.py
```

Focused regression tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_preset_filename_lcd_spec.py::test_v33_an0_hysteresis_monitor_banks_delay_counter_before_uart_ring_alias \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_full_native_chain_filename_preset_state_matrix[b-a-b]
```

Builder integration tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v172_v33_release_builders.py
```

Direct checker command:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py \
  --target main-v33 --target control-v172
```

MAIN size command:

```bash
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from pathlib import Path
import tempfile
from dlcp_fw.paths import V33_MAIN_ASM
from dlcp_fw.sim.v30_symbols import assemble_v30
from dlcp_fw.sim.hexio import parse_intel_hex

with tempfile.TemporaryDirectory() as td:
    out = Path(td) / "v33_size.hex"
    assemble_v30(V33_MAIN_ASM, out, output_lst=Path(td) / "v33_size.lst")
    mem = parse_intel_hex(out)
    used = [a for a in range(0x1000, 0x4C00) if mem.get(a, 0xFF) != 0xFF]
    last = max(used) if used else 0x0FFF
    print(f"used_bytes_pre_preset_b={len(used)}")
    print(f"last_used_pre_preset_b=0x{last:04X}")
    print(f"free_bytes_before_0x4C00={0x4C00 - (last + 1)}")
PY
```

Broader simulator gate when implementation touches release builders or target
assembly:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 tests/sim
```

## Deployment and Smoke Plan

No hardware deployment is required for this tooling/source-safety feature.

No-deploy criteria:

- Only checker/library/tests/docs/source alias changes were made.
- MAIN size/bytes are unchanged, or any byte change is documented and tested.
- No user explicitly requests flashing.

If firmware source changes do produce a new accepted release artifact later,
use the normal V3.3/V1.72 commands from `README.md` and record a separate
hardware flash/probe plan. That is outside this IMPL's required acceptance.

## Rollback

- Remove checker integration from the two release builders.
- Revert manifest/checker/test/doc files with focused pathspecs.
- Revert only the alias migration hunks that were part of this work.
- Do not touch unrelated working-tree changes.
- If a canonical HEX was rebuilt during implementation, restore it only if it
  was part of this work and only with an explicit pathspec.

## Risks and Mitigations

- Risk: A full alias migration is noisy and could obscure real instruction
  changes.
  Mitigation: require pre/post temp assembly and `0x1000..0x4BFF` byte
  comparison, plus `git diff --word-diff` review around executable source.
- Risk: CFG/BSR analysis is too weak and produces false positives.
  Mitigation: fail closed, then add explicit routine contracts or local
  `movlb`; do not add broad allowlists.
- Risk: Checker accidentally treats data tables, literals, or SFRs as RAM.
  Mitigation: tests for SFR/data contexts and manifest access classes.
- Risk: Macros increase MAIN size.
  Mitigation: macros are optional and not used for bulk first-pass migration;
  size report is acceptance-blocking.

## Acceptance Criteria

- `scripts/check_ram_access_safety.py --target main-v33 --target control-v172`
  passes on current target source and fails on fixture bug cases.
- V3.3 and V1.72 release builders invoke the checker.
- Target executable RAM references use manifest-backed, bank-explicit aliases.
- Existing one-off BSR regression is covered by the shared checker.
- MAIN size metrics and byte comparison are recorded below.
- Focused checker, preset regression, and builder tests pass.
- Broader `tests/sim` is run if assembly or builder behavior changed.
- No hardware deployment is performed unless separately requested.

## Post-Implementation Evidence

Implemented on 2026-06-07 as a fail-closed source-hygiene, build-gate, and
whole-target CFG BSR proof for source-assembled MAIN V3.3 and CONTROL V1.72.
The implementation forbids raw/ambiguous RAM operands in target executable
source, adds generated bank-explicit aliases, enforces `_phys` aliases for
`movff` and `lfsr`, and proves every target-source `BANKED` RAM access reachable
from the configured CFG roots has the manifest bank selected on every static
path. Unknown calls clobber BSR unless a structured routine contract says
otherwise.

The checker also verifies routine-contract bodies. Active recursive edges use
the declared contract as the induction assumption, then the contracted routine
body is summarized separately and must still match its declared exit state.

Actual files changed:

- `src/dlcp_fw/asm/ram_bank_manifest.py`
- `src/dlcp_fw/analysis/ram_bank_safety.py`
- `scripts/check_ram_access_safety.py`
- `src/dlcp_fw/patch/build_v33_release.py`
- `src/dlcp_fw/patch/build_v172_release.py`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `src/dlcp_fw/asm/dlcp_main_v33.asm`
- `src/dlcp_fw/asm/dlcp_control_v172.asm`
- `tests/sim/test_ram_bank_safety.py`
- `tests/sim/test_preset_filename_lcd_spec.py`
- `tests/sim/test_v171_ram_static_analysis.py`
- `tests/sim/test_v171_layer5_diag_page.py`
- `tests/sim/test_v32_layer5_diag_counters.py`

Real RAM-bank fixes found by the Phase 2 proof:

- MAIN `flow_main_i2c_service_27f0_ad_monitor` could reach a bank-0
  `stock_0BA_b0` write after an unknown helper-return context; added a local
  `movlb 0x0`.
- MAIN `dsp_ping` had a source-visible path through I2C transmit/STOP wait
  helpers before bank-0 `dsp_fault_flags_b0`; added a local `movlb 0x0` before
  the ACKSTAT/fault-flag access and verified the recursive recovery contract.
- CONTROL `button_scan_debounce` was callable from mixed BSR contexts before
  bank-0 debounce scratch access; added a local `movlb 0x00`.
- CONTROL V1.72 diagnostics identity cadence returns through bank-0 service
  state while the caller then touches bank-1 diagnostics cache; added a local
  `movlb 0x01`.
- CONTROL menu/service continuations now either have explicit local `movlb`
  assertions or checked routine contracts.
- CONTROL table-labeled stock aliases at `0x065`, `0x06D`, `0x06F`, and
  `0x074` are now generated so table regions still assemble even though they
  are excluded from executable BSR proof.
- The broad suite exposed a deterministic Preset filename parser regression:
  after a prior BF reply, `rx_frame_position=1` plus a stale route latch let
  route-less old echo bytes `2F id / 2D id / 4E id` finalize a filename. The
  parser now requires a fresh supported route for filename reply frames and
  clears `control_flags.bit2` after each consumed frame.

MAIN size evidence:

- Baseline comparison artifact: current canonical
  `firmware/patched/releases/DLCP_Firmware_V3.3.hex`
- Candidate build path: temp direct `assemble_v30(V33_MAIN_ASM, ...)`
- Canonical `used_bytes_pre_preset_b`: `15129`
- Canonical `last_used_pre_preset_b`: `0x4B93`
- Canonical `free_bytes_before_0x4C00`: `108`
- Canonical used program words before `0x4C00`: `7624`
- Canonical free program words before `0x4C00`: `54`
- Candidate `used_bytes_pre_preset_b`: `15140`
- Candidate `last_used_pre_preset_b`: `0x4B97`
- Candidate `free_bytes_before_0x4C00`: `104`
- Candidate used program words before `0x4C00`: `7626`
- Candidate free program words before `0x4C00`: `52`
- Delta: `+11` non-`0xFF` bytes, `+2` program words, highest used word moved
  `+4` bytes.
- Program bytes `0x1000..0x4BFF` vs canonical V3.3 HEX: `9266` differing bytes.
  This is expected after inserting two MAIN instructions before absolute code
  references; the program-word size delta is the acceptance metric.
- Result: MAIN size increased by exactly two program words because the checker
  found two real MAIN BSR hazards that required local `movlb` assertions. This
  leaves `52` free program words / `104` free non-`0xFF` bytes before Preset B.

Tests:

- `PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v33 --target control-v172`
  - `RAM bank safety: OK (main-v33, control-v172)`
- Temp direct assembly of V3.3 MAIN and V1.72 CONTROL:
  - `assembly-ok`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py`
  - `15 passed in 0.37s`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_preset_filename_lcd_spec.py::test_v33_an0_hysteresis_monitor_banks_delay_counter_before_uart_ring_alias tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_full_native_chain_filename_preset_state_matrix`
  - `7 passed in 46.04s`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v172_v33_release_builders.py`
  - `4 passed in 0.39s`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_preset_filename_lcd_spec.py::test_v172_native_raw_parser_old_echo_frame_positions_do_not_finalize`
  - `3 passed in 17.55s`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 tests/sim`
  - `1409 passed, 1 skipped, 7 warnings in 563.36s (0:09:23)`

Deploy/no-deploy:

- No hardware flash or deploy was performed.
- No canonical release builder was run to produce a new release artifact.

Final status:

- Phase 2 whole-target CFG/routine-contract BSR proof is implemented for MAIN
  V3.3 and CONTROL V1.72 target source.
- Final broad simulator coverage passed.
- `git diff --check` passed after the final evidence update.

## Reviewer Findings and Iteration History

### Pass 1: Simplicity/Scope Reviewer

Finding S1, Medium: The first draft proposed mandatory RAM access macros for
all target source. That risks firmware-size growth and large churn before the
checker proves value.

Disposition: Addressed. The implementation now prefers manifest-backed aliases
and static proof first. Macros are optional for later narrow use only.

Finding S2, Low: A Python manifest is less declarative than YAML.

Disposition: Accepted. Python avoids adding dependencies and matches local
helper style. A later YAML migration can happen if the manifest grows beyond
comfortable review size.

### Pass 2: Correctness/Contract Reviewer

Finding C1, High: A warning-only "indeterminate BSR" state would not have
caught the recent class robustly enough.

Disposition: Addressed in Phase 2. The checker now builds a source CFG,
propagates BSR state through branch targets, skip instructions, calls, returns,
and routine contracts, and fails closed on unknown or multi-bank states before
target-source `BANKED` RAM access.

Finding C2, Medium: The draft did not distinguish 8-bit operand aliases from
physical addresses for `movff` and `lfsr`.

Disposition: Addressed. The spec and IMPL now require `_op` vs `_phys`
separation and explicit tests.

### Pass 3: Ops/Tests/Deploy Reviewer

Finding O1, High: MAIN size comparison was underspecified and might use the
release builder, which mutates revision bytes.

Disposition: Addressed. The IMPL requires direct temp `assemble_v30()` builds
and records the V3.2 size-spec metrics.

Finding O2, Medium: Builder integration was missing; a standalone test would be
too easy to bypass during release builds.

Disposition: Addressed. The IMPL now requires checker invocation from both
canonical release builders.

### Final Review Summary

High findings remaining: 0
Medium findings remaining: 0
Low findings remaining: 1

Remaining Low:

- S2: Python manifest instead of YAML. This does not block implementation
  because the repository already uses Python helper modules for assembly,
  symbol parsing, and manifests, and avoiding a dependency is the simpler first
  pass.
