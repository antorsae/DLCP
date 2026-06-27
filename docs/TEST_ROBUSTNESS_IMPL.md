# IMPL Test Robustness

Date: 2026-06-27
Status: Implemented - simulator verified; live hardware not run
Source spec: `docs/TEST_ROBUSTNESS_SPEC.md`
Scope: simulator/release-artifact/hardware-gate test hardening for current MAIN V3.5 + CONTROL V1.73 and future release lines.

## Source Requirements

Goals:

- Make deterministic tests fail on user-visible LCD row corruption, stale suffixes, missing fields, and wrong per-PB identity text.
- Add stale-state and upgrade-state regressions for caches, persistence, release metadata, and cross-MCU state.
- Cover canonical release HEX artifacts in addition to temp source-assembled fixtures where operators flash canonical artifacts.
- Add structural tests for layout-sensitive firmware tables, fixed regions, RAM banks, and release metadata.
- Define a repeatable promotion path for hardware incidents into simulator regressions or opt-in hardware gates.
- Keep the work narrow and pragmatic; add helpers only where they reduce repeated fragile assertions.

Non-goals:

- No whole-suite rewrite.
- No mandatory live hardware in normal simulator gates.
- No CI policy mandate beyond documenting recommended commands.
- No firmware behavior change unless a test exposes a separate product bug.
- No replacement of existing feature-specific specs.

Explicit user decisions:

- The current test suite is too brittle despite large test count.
- The escaped PB1 identity display and CONTROL LCD corruption are significant enough to justify test-quality work.
- The IMPL must be generated through the `$write-impl` review process.

## Required Docs Read

- `AGENTS.md`: canonical layout, firmware artifacts, current source/release lines, test inventory, markers, and hardware test references.
- `README.md`: current V3.5/V1.73 setup, flash, validation, simulator, and post-flash smoke commands.
- `CODING_STYLE.md`: verification expectations for source/code-generation changes.
- `docs/TEST_ROBUSTNESS_SPEC.md`: source spec for this IMPL.
- `docs/SIMULATION.md`: Rust simulator public `Chain` API and full/fast simulator gate commands.
- `docs/TEST_SIMULATOR.md`: historical simulator guidance and stale status.
- `docs/HARDWARE_TEST.md`: live-rig role classification, LCD OCR, IR/front-panel gates, hardware skip policy, and smoke commands.
- `docs/ROBUSTNESS.md`: historical robustness evidence and policy that simulation plus hardware validation are both needed.
- `docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md`: incident discovery and deterministic regression promotion context.
- `docs/IMPL_V172_V33_DIAG_MAIN_IDENTITY.md`: Diagnostics identity row format and cmd `0x25` ownership history.
- `docs/PRESET_FILENAME_LCD_SPEC.md` and `docs/IMPL_PRESET_FILENAME_LCD.md`: Preset filename row ownership, scrolling, and dynamic LCD exceptions.
- `docs/MULTI_PB_INPUT_SELECTION.md` and `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`: PB1/PB2 input EEPROM ownership, valid encodings, invalid/erased behavior, dirty-save lifecycle, and migration compatibility.
- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md`, `docs/SRC4382_AUTODETECT_STIMULUS_MATRIX_SPEC.md`, and `docs/SRC4382_USB_DIAGNOSTICS_SPEC.md`: SRC4382 route/table contracts touched by the table-carry audit.

Deployment docs:

- This repository has firmware flashing runbooks, not web-service deployment.  Runtime firmware deployment is out of scope for this IMPL.  Hardware flash/smoke commands are documented only as no-deploy validation evidence.

## Current Implementation Evidence

- `tests/conftest.py`
  - Adds `--run-hardware`; live hardware tests are skipped unless explicitly enabled.
- `tests/sim/test_v172_v33_diag_identity.py`
  - Has clean boot identity tests for V1.72/V3.3, V1.73/V3.4, and V1.73/V3.5.
  - Includes canonical `test_v173_v35_canonical_diag_ok_title_shows_visible_main_identity` and `test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache`, which derive expected V3.5 identity text from `V35_MAIN_HEX`.
  - Remaining permissive predicates are used for page detection or issue-state token tests where token order/count can vary.
- `tests/sim/test_v173_multi_pb_input_selection.py`
  - Contains strong PB1/PB2 persistence coverage, including `test_pb1_spdif_persists_across_cold_boot_with_independent_pb2_aes`.
  - Contains canonical CONTROL HEX coverage in `test_canonical_hex_split_menu_visible_behavior_regression`.
  - Release-facing menu/Volume/Diag checks now use exact 16-character two-row assertions for static rows.
- `tests/sim/test_preset_filename_lcd_spec.py`
  - Has exact Preset row tests and row-owner regressions for filename scrolling.
  - Scrolling/model tests intentionally use prefix/window assertions where exact full-row equality would hide the row-window behavior being exercised.
- `tests/sim/test_flash_table_page_carry_audit.py`
  - Current worktree adds a structural audit for V3.5 low-only TBLPTR tables and V1.73 LCD page-carry/table-placement contracts.
  - The table audit caught the CONTROL table movement risk before flashing rev `0x56`.
- `tests/sim/test_firmware_version_label.py`
  - Reads canonical `V35_MAIN_HEX` and guards HID/EEPROM version bytes.
- `tests/sim/test_dlcp_control_flash_safety.py`
  - Reads canonical `V173_CONTROL_HEX` and guards safe-flash static release/preflight behavior.
- `tests/sim/test_v35_v173_release_builders.py` and `tests/sim/test_dlcp_v35_release_flash.py`
  - Own current V3.5/V1.73 release-builder and release-flash wrapper coverage.
- `README.md`
  - Documents fast/full simulator gates and post-flash `identify-mains`, `dlcp_main_flash --info-only`, and `dlcp_diag.py --json` checks.
- `docs/HARDWARE_TEST.md`
  - Requires `identify-mains --require-left-right` before flashing and explains that USB can disappear during real standby, so LCD/post-wake evidence matters.
- `docs/MULTI_PB_INPUT_SELECTION.md`
  - Defines CONTROL EEPROM bytes `0x5E`/`0x5F`, PB1/PB2 valid encodings, erased/legacy fallback behavior, and dirty-state persistence caveats.

## Pre-Implementation Gap Analysis

These were the gaps identified before the implementation pass; the evidence
matrix and post-implementation section record the closure status.

Exists:

- Large simulator suite with many feature-specific regressions.
- Opt-in hardware test harness and runbook.
- Release builder and flash safety tests for current V3.5/V1.73 artifacts.
- Some exact LCD assertions and current newly added stale identity regression.
- Structural RAM-bank and release-builder gates.

Missing or weak:

- No central test robustness policy before `docs/TEST_ROBUSTNESS_SPEC.md`.
- No shared helper or audit rule to make exact 16-character LCD assertions the default.
- Several high-risk LCD tests still use `startswith` without documenting why partial matching is safe.
- Canonical HEX coverage exists in some files but is uneven and not named as a release-artifact contract.
- Hardware incidents are recorded ad hoc in chat/runbooks rather than through a consistent incident-to-regression workflow.
- Mutation/negative proof is inconsistent; some fixes rely only on happy-path convergence.
- Pathless `dlcp_diag.py --json --cmd44-only` can return a valid empty report when zero MAIN HID devices enumerate, so it is not a sufficient hardware smoke by itself.

Stale:

- `docs/TEST_SIMULATOR.md` still documents gpsim-era details and points back to `AGENTS.md`.
- `README.md` revision examples may lag current worktree revisions when release builders have been run locally.
- `README.md`, `AGENTS.md`, and feature docs can temporarily disagree with canonical artifact revisions after local release-builder work.  Robustness tests must derive expected identity/revision bytes from `V173_CONTROL_HEX` and `V35_MAIN_HEX`, and release-artifact changes must update public docs or record a tracked follow-up.

## Release Artifact Inventory

Current robustness work must treat these canonical release artifacts as first-class
test inputs:

Current canonical artifact metadata under test:

- MAIN `V35_MAIN_HEX`: V3.5 EEPROM rev `0x91`, SHA-256 `2e17a79dfd0686d95559275d70b2d830cf40de3dda4f61984c3a8b7b40819f7e`.
- CONTROL `V173_CONTROL_HEX`: V1.73 rev `0x57`, build `20260627`, SHA-256 `27fd91c6f0b09bed8e05268b7a5f2ce370e994290ce7840e1897856f20a4e88a`.

| Artifact constant | Canonical path | Contract under test | Expected-value source | Required coverage |
| --- | --- | --- | --- | --- |
| `V35_MAIN_HEX` | `firmware/patched/releases/DLCP_Firmware_V3.5.hex` | MAIN identity, cmd `0x25`, runtime/EEPROM release bytes, MAIN flash safety | parse canonical HEX bytes directly, or boot/query cmd `0x25` from a simulator using `V35_MAIN_HEX`; do not use ASM-source revision helpers for canonical expectations | canonical Diagnostics identity tests, `test_firmware_version_label.py`, `test_dlcp_v35_release_flash.py`, `test_dlcp_main_flash.py::test_static_hid_version_detector_accepts_compact_v34_plus_shape[v35]`, targeted `test_dlcp_main_flash.py` preflight/path tests |
| `V173_CONTROL_HEX` | `firmware/patched/releases/DLCP_Control_V1.73.hex` | CONTROL LCD/menu rendering, PB1/PB2 input persistence, Diagnostics parser/display, safe CONTROL flash metadata | `detect_static_hex_control_release_info(parse_intel_hex(V173_CONTROL_HEX))` or equivalent HEX/static parser; do not use README prose | canonical Diagnostics identity tests, canonical PB1/PB2 persistence/dirty-save/corrupt-byte tests, canonical preset filename row-owner gate, `test_dlcp_control_flash_safety.py` |
| `V173_CONTROL_HEX` + `V35_MAIN_HEX` | paired current release artifacts | stale per-PB identity replacement, independent PB input persistence, current preset filename row ownership, user-visible LCD rows | expected MAIN identity from canonical MAIN artifact; expected CONTROL behavior from canonical CONTROL artifact and simulator state | focused robustness gate in WU6 |

Implementation may add source-assembled temp fixtures for source-line mutation
tests, but release-facing acceptance must include the canonical artifacts above.

## Evidence Matrix

Implementation evidence:

| Test node / command | Escaped behavior guarded | Artifacts used | Expected source | Old-behavior result | Focused result | Broader result | Hardware status |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `test_v173_v35_canonical_diag_ok_title_shows_visible_main_identity` and `test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache` | Stale/malformed PB1/PB2 Diagnostics identity such as `PB1 OK v330091` | `V173_CONTROL_HEX` + `V35_MAIN_HEX` | V3.5 identity parsed from canonical MAIN HEX EEPROM/cmd25 bytes | Seeded stale V3.3 valid-cache state is overwritten; stale healthy `PBn OK v3.3 0091` is not final | Included in focused gate: `55 passed in 75.48s` | Full sim: `2082 passed, 2 skipped, 4 xfailed, 10 warnings in 1001.77s` | Not run; no explicit live hardware approval for this docs/tests-only pass |
| `test_v173_canonical_pb1_spdif_pb2_aes_persisted_inputs_survive_cold_boot`, `test_v173_canonical_pb1_pb2_dirty_save_commits_eeprom_and_clean_save_no_churn`, invalid/erased/corrupt canonical tests | PB1/PB2 input persistence divergence, immediate-write mistakes, corrupt-byte import, ambiguous BF/06 import | `V173_CONTROL_HEX` + `V35_MAIN_HEX` | CONTROL EEPROM bytes `0x5E`/`0x5F`, simulator routing state, dirty-save instrumentation | Would fail if PB1/PB2 wrote instantly, never persisted, repeated clean saves, or imported corrupt PB2 intent | Included in focused gate: `55 passed in 75.48s` | Full sim passed | Not run; live persistence/audio gates still required for field closure |
| `test_canonical_hex_split_menu_visible_behavior_regression` and exact LCD helper users | Leading-space, suffix, page-owner, and row-1 blanking regressions on static menu rows | `V173_CONTROL_HEX` + `V35_MAIN_HEX` plus source fixtures where needed | Exact 16-character LCD rows | Leading-space ` Volume...`, missing source row, or wrong page title now fails exact two-row comparison | Included in focused gate: `55 passed in 75.48s` | Full sim passed | Not run |
| `test_v173_v35_canonical_preset_lcd_suffix_and_row1_atomicity_matrix` | Preset page missing filename row or row-owner corruption | `V173_CONTROL_HEX` + `V35_MAIN_HEX` | Canonical preset filename windows and exact row-owner lifecycle | Missing filename row under current artifacts fails | Included in focused gate: `55 passed in 75.48s` | Full sim passed | Not run |
| `test_identify_mains_fails_when_no_main_devices_visible` and existing ambiguous-device test | Treating zero or ambiguous MAIN HID enumeration as hardware closure evidence | Mocked hardware enumeration | `identify-mains --require-left-right` must require two unique roles | Pathless/no-device smoke cannot close a hardware incident | Included in focused gate: `55 passed in 75.48s` | Full sim passed | Not run |
| Release-artifact middle gate and RAM safety commands | Stale release metadata, static detector drift, unsafe flash/preflight path, RAM-bank regressions | `V35_MAIN_HEX`, `V173_CONTROL_HEX` | Static HEX parsers, release builders, flash wrappers, RAM-bank checker | Future-only guard for release-path drift | Middle gate: `67 passed in 0.86s`; RAM safety OK for `main-v35` and `control-v173` | Full sim passed | Not run |

`Old-behavior result` may say "future-only guard" only when the test cannot
practically be run against the old firmware or source mutation.  Otherwise,
record that it fails the stale/cache/corrupt state it was designed to catch.

## Proposed Implementation

### WU1 - Add Test Robustness Guidance And Incident Hook

Update docs:

- Keep `docs/TEST_ROBUSTNESS_SPEC.md` as the source policy.
- Create `docs/TEST_INCIDENTS.md` with a mandatory sanitized incident
  template.  The first entries must cover the known stale Diagnostics identity
  incident and the CONTROL LCD corruption/missing-filename incident.
- Add a short reference from `docs/HARDWARE_TEST.md` to
  `docs/TEST_INCIDENTS.md` and the hardware incident promotion rule in the
  spec.
- The incident template must include:
  - incident ID, date, firmware artifact paths, and artifact-derived
    MAIN/CONTROL versions/revisions;
  - observed LCD rows, USB/HID enumeration status, audio state when relevant,
    and exact operator actions;
  - whether raw evidence is local-only and where sanitized evidence lives;
  - simulator reproducibility result;
  - deterministic regression test node IDs or opt-in hardware gate node IDs;
  - disposition: fixed, guarded, hardware-only gate pending, or not reproducible.
- Raw hardware artifacts stay ignored/local.  Shared or committed incident
  evidence must use role labels (`PB1/LEFT`, `PB2/RIGHT`), redacted or
  hash-only HID IDs, cropped LCD-only media when needed, and stripped metadata.

No code helper is required in this WU.

### WU2 - Add LCD Assertion Helpers Or Local Test Helpers

Preferred simple path:

- Add local helpers in the most affected test modules first:
  - `assert_lcd_exact(chain, (row0, row1), *, context="...")`
  - `wait_for_lcd_exact(chain, (row0, row1), *, limit=..., context="...")`
- If three or more modules need the same helper, move it to `tests/sim/lcd_assertions.py`.

Rules:

- Static screens must assert both LCD rows.  The helpers must reject expected
  rows whose length is not exactly 16 and must assert actual row lengths are
  exactly 16.
- Failure messages must include expected rows, actual rows, display state when
  available, and caller-provided context.
- For dynamic rows, require a separately named helper such as
  `assert_lcd_prefix_allowed(..., reason="issue token order varies")` or
  `assert_lcd_row0_only(..., reason="row1 scroll window is asserted separately")`.
  The `reason` argument is mandatory and must be non-empty.
- Do not add a broad pytest plugin or monkeypatch; keep assertions ordinary and readable.

### WU3 - Convert High-Risk LCD Assertions

Focus only on current V3.5/V1.73 release-facing tests first:

- In `tests/sim/test_v173_multi_pb_input_selection.py`:
  - Convert menu cycle checks around Volume, Preset, Input PB1, Input PB2, Setup, PB1 Diag, and PB2 Diag to exact row assertions where the row is static.
  - Replace `startswith("Volume")` with exact expected Volume title/source rows for tests whose setup makes the source deterministic.
  - Keep prefix checks only for issue rows, dynamic diag tokens, or scrolling rows, and add explicit comments.
- In `tests/sim/test_v172_v33_diag_identity.py`:
  - Keep page-detection helpers permissive if needed for navigation, but final
    canonical healthy identity assertions must compare exact `(row0, row1)`
    tuples with 16-character length checks.  If row 1 is intentionally dynamic,
    use a reason-bearing helper and assert the deterministic row-1 token/window
    contract separately.
  - Add comments for issue-state token prefix tests where token ordering or count is intentionally variable.
- In `tests/sim/test_preset_filename_lcd_spec.py`:
  - Leave scrolling window tests as window/prefix tests, but document why exact full-row equality would make the test less meaningful.

### WU4 - Canonical Artifact Parity

Add or rename release-artifact tests so it is obvious they use canonical HEX:

- Add named V1.73/V3.5 diagnostics identity tests using
  `V173_CONTROL_HEX` + `V35_MAIN_HEX`, not temp assembled `v173_hex` /
  `v35_hex`:
  - `test_v173_v35_canonical_diag_ok_title_shows_visible_main_identity`
  - `test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache`
- The canonical stale-cache test must seed stale V3.3 PB1/PB2 identity bytes,
  set the valid mask, enter PB1/PB2 Diag, and assert the final healthy
  `(row0, row1)` tuple using artifact-derived V3.5 identity text.  It must also
  capture the LCD timeline for both rows and fail if stale healthy
  `PBn OK v3.3 0091` remains visible after the documented settle window.
- Expected V3.5 revision text must be read from `V35_MAIN_HEX` by parsing HEX
  bytes or by querying cmd `0x25` from a simulator boot of `V35_MAIN_HEX`.
  ASM-derived helpers such as `read_v35_release_revision()` are not acceptable
  for canonical artifact expected LCD text.
- Add canonical `V173_CONTROL_HEX` + `V35_MAIN_HEX` PB1/PB2 input persistence
  tests:
  - `test_v173_canonical_pb1_spdif_pb2_aes_persisted_inputs_survive_cold_boot`
  - `test_v173_canonical_pb1_pb2_dirty_save_commits_eeprom_and_clean_save_no_churn`
  - `test_v173_canonical_invalid_erased_corrupt_input_eeprom_does_not_import_ambiguous_status`
  - `test_v173_canonical_pb2_corrupt_runtime_intent_clamps_to_safe_fallback`
- The canonical dirty-save test must perform user PB1/PB2 source changes,
  assert dirty flags are set, assert CONTROL EEPROM bytes `0x5E`/`0x5F` have
  not been committed before the dirty-save service runs, force the save
  service, assert `0x5E`/`0x5F` commit to the selected PB1/PB2 inputs, verify
  dirty flags clear after successful equality/write confirmation, reboot,
  verify PB1/PB2 routing survives, and prove a later clean
  save/reconnect/full-sync emits no repeat EEPROM commit.
- Existing temp-source invalid/erased and closed-allowlist tests remain
  valuable source coverage; do not duplicate their full slow matrix unless the
  canonical artifact has no equivalent smoke.
- Update the Release Artifact Inventory and Evidence Matrix sections in this
  IMPL with actual test node IDs, commands, and results.
- Keep temp assembly fixtures for source-level tests that need uncommitted source changes.
- Do not introduce a `release_artifact` pytest marker yet; record this as Low unless the implementation finds many release-artifact tests.

### WU5 - Stale-State And Negative Regressions

Add or keep focused regressions for these escaped classes:

- Diagnostics stale identity:
  - Seed PB1 and PB2 cached identity bytes plus valid-mask bits to stale V3.3 values.
  - Navigate to each Diag page under V3.5.
  - Assert exact `PBn OK v3.5 NNNN` row and assert stale `PBn OK v3.3 0091` never remains final.
- LCD table/layout:
  - Keep `test_flash_table_page_carry_audit.py`.
  - Assert first-screen title tables are page-local when feasible.
  - Permit only named carry-safe crossing tables.
- Persistence:
  - Keep PB1 S/PDIF + PB2 AES cold-boot test as canonical
    `V173_CONTROL_HEX` + `V35_MAIN_HEX` coverage.
  - Treat invalid/erased PB1/PB2 EEPROM and ambiguous BF/06 import as
    compatibility coverage, not production migration code.  Add the canonical
    artifact smoke tests named in WU4, and keep existing temp-source tests for
    the broader slow compatibility matrix.
- Hardware degraded state:
  - Add `tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_no_main_devices_visible`
    so `identify-mains --require-left-right` cannot be accepted as closure
    evidence when zero MAIN HID devices enumerate.
  - Keep the ambiguous-device gate
    `tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_two_roles_are_not_unique`
    and the existing lower-level `found 0` wake/preset wait assertions as
    supplemental degraded-state coverage.
    If the implementation adds `dlcp_diag --require-devices`, add the matching
    no-device regression and include it in the focused gate instead.
  - If `dlcp_diag.py --json --cmd44-only` remains intentionally allowed to emit
    an empty report for discovery, tests must make clear it is not a live
    closure smoke command.
- Release metadata:
  - Include `tests/sim/test_v35_v173_release_builders.py` in the release-facing
    gate so builder-owned EEPROM/runtime/cmd25 identity fields stay aligned.
  - Include targeted V3.5 release-flash wrapper tests so the operator path that
    publishes/flashes canonical artifacts remains covered.
  - Include
    `tests/sim/test_dlcp_main_flash.py::test_static_hid_version_detector_accepts_compact_v34_plus_shape[v35]`
    as the canonical V3.5 MAIN static HID/release detector smoke.  If the
    implementation renames this parameterized test, update the WU6 node rather
    than dropping canonical MAIN flash/preflight coverage.
- Preset filename/row owner:
  - Add a current V1.73/V3.5 canonical preset filename row-owner/atomicity gate
    using `V173_CONTROL_HEX` + `V35_MAIN_HEX`.
  - The existing V1.73/V3.4
    `test_v173_v34_preset_lcd_suffix_and_row1_atomicity_matrix` remains
    supplemental historical coverage only; it is not sufficient for the current
    release-artifact gate.

### WU6 - Test Commands And Gates

Focused robustness gate for this IMPL:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_flash_table_page_carry_audit.py \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_canonical_diag_ok_title_shows_visible_main_identity \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache \
  tests/sim/test_v173_multi_pb_input_selection.py::test_canonical_hex_split_menu_visible_behavior_regression \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_pb1_spdif_pb2_aes_persisted_inputs_survive_cold_boot \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_pb1_pb2_dirty_save_commits_eeprom_and_clean_save_no_churn \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_invalid_erased_corrupt_input_eeprom_does_not_import_ambiguous_status \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_pb2_corrupt_runtime_intent_clamps_to_safe_fallback \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_fname_foreground_ir_buttons_standby_while_pending_valid_scrolling \
  tests/sim/test_preset_filename_lcd_spec.py::test_v173_v35_canonical_preset_lcd_suffix_and_row1_atomicity_matrix \
  tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_no_main_devices_visible \
  tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_two_roles_are_not_unique \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_dlcp_control_flash_safety.py
```

Current release-artifact middle gate.  This is additive; for release
promotion, run the focused robustness gate above, this middle gate, then the
full simulator gate unless the IMPL records an explicit blocker:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_dlcp_control_flash_safety.py \
  "tests/sim/test_dlcp_main_flash.py::test_static_hid_version_detector_accepts_compact_v34_plus_shape[v35]" \
  tests/sim/test_flash_table_page_carry_audit.py \
  tests/sim/test_dlcp_main_flash.py::test_preflight_accepts_app_only_hex_without_bootloader_bytes \
  tests/sim/test_dlcp_main_flash.py::test_preflight_rejects_explicit_bootloader_drift \
  tests/sim/test_dlcp_main_flash.py::test_cli_blocks_unsafe_flags_without_force \
  tests/sim/test_dlcp_main_flash.py::test_cli_info_only_does_not_require_hex \
  tests/sim/test_dlcp_main_flash.py::test_cli_warns_when_device_revision_is_same_or_newer \
  tests/sim/test_dlcp_main_flash.py::test_pick_device_auto_resolve_requires_unambiguous_match
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
```

Full simulator gate before release promotion:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Hardware smoke, opt-in only:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py detect
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --path "$LEFT_HID" --json --cmd44-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --path "$RIGHT_HID" --json --cmd44-only
```

Live hardware pytest remains skipped unless the operator explicitly passes
`--run-hardware` and the required environment variables from `docs/HARDWARE_TEST.md`.
Raw stdout/stderr, command JSON, HID paths, serials, camera names, Flipper
serial ports, and media paths are local-only.  Commit only sanitized
derivatives that use PB role labels and redacted/hash-only identifiers.

## Likely Files

Docs:

- `docs/TEST_ROBUSTNESS_SPEC.md`
- `docs/TEST_ROBUSTNESS_IMPL.md`
- `docs/HARDWARE_TEST.md`
- `docs/TEST_INCIDENTS.md`

Tests:

- `tests/sim/test_v172_v33_diag_identity.py`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `tests/sim/test_preset_filename_lcd_spec.py`
- `tests/sim/test_flash_table_page_carry_audit.py`
- `tests/sim/test_firmware_version_label.py`
- `tests/sim/test_dlcp_control_flash_safety.py`
- `tests/sim/test_v35_v173_release_builders.py`
- `tests/sim/test_dlcp_v35_release_flash.py`
- `tests/sim/test_dlcp_main_flash.py`
- `tests/sim/test_hardware_state_test.py`
- `tests/sim/test_dlcp_diag.py` if a strict no-device/require-devices mode is added
- optionally `tests/sim/lcd_assertions.py`

No expected firmware source changes:

- `src/dlcp_fw/asm/dlcp_control_v173.asm` and `src/dlcp_fw/asm/dlcp_main_v35.asm` should not be touched by this IMPL unless a new test exposes a separate firmware bug.

## Compatibility, Migration, And Deletion Policy

- Existing tests should be tightened in place where possible.
- Do not mass-convert every prefix assertion; convert high-risk release-facing rows first and leave documented dynamic exceptions.
- Do not delete historical gpsim documentation in this work; only cite that it is stale where relevant.
- No production migration code is expected, but persistence/migration
  compatibility tests are in scope for CONTROL EEPROM input bytes, including
  valid PB1/PB2 encodings, erased/legacy bytes, corrupt bytes, dirty-save
  behavior, and no ambiguous BF/06 import.
- No protocol/API compatibility impact unless the implementation chooses to add
  a diagnostic CLI `--require-devices` option.  If it does, keep default
  discovery behavior backwards-compatible and make the stricter mode opt-in.

## Deployment And Smoke Plan

No deployment or firmware flashing is required for implementing this IMPL.

If implementation changes only docs/tests/helpers:

- Record `No deploy: test/docs-only`.
- Do not run write-mode `scripts/flash_control_safe.sh` or MAIN flash scripts
  unless a separate firmware change occurs.  Read-only `--info-only` and
  `--preflight-only` commands are allowed for explicit smoke/preflight
  evidence.
- Do not count pathless `scripts/dlcp_diag.py --json --cmd44-only` as a live
  closure smoke.  It may remain useful for discovery, but closure evidence must
  come after `identify-mains --require-left-right` and use explicit role paths.

If a follow-up firmware bug is exposed and fixed:

- Follow that feature's release-builder and flash-safety docs.
- Run `scripts/flash_control_safe.sh --preflight-only` for CONTROL changes.
- Run MAIN release wrapper preflight/info-only commands for MAIN changes.
- Use `docs/HARDWARE_TEST.md` role-safe commands before any live flash.

## Documentation Follow-Ups

Current release/runbook metadata must be updated in the same change when tests
or builders prove it stale.  This includes `README.md`, `AGENTS.md`,
`docs/HARDWARE_TEST.md`, and feature docs touched by the implementation.

Follow-ups are allowed only for historical/background docs that do not guide
current flashing, current simulator gates, or current release validation.  Any
follow-up must be recorded with:

- path;
- observed mismatch;
- canonical source of truth;
- reason it is deferred;
- tracking location or issue ID;
- owner;
- closure condition.

## Acceptance Criteria

- `docs/TEST_ROBUSTNESS_SPEC.md` exists and is linked or referenced from the implementation evidence.
- This IMPL is reviewed with zero unresolved High/Medium findings.
- High-risk LCD/menu/diag tests use exact 16-character two-row assertions for
  static screens; any row0-only, prefix, or window assertion uses an explicit
  dynamic helper/comment with a non-empty reason.
- Stale PB1/PB2 identity cache regression exists for canonical
  `V173_CONTROL_HEX` + `V35_MAIN_HEX`, derives expected revision text from the
  canonical MAIN artifact, fails on the old valid-mask behavior, and records
  whether stale healthy identity text appears after the settle window.
- PB1/PB2 persistence has canonical cold-boot coverage for both units and
  compatibility coverage for valid, invalid, erased/legacy, corrupt, and
  dirty-save/no-repeat-clean-save behavior.
- Canonical V1.73/V3.5 HEX artifacts are included in release-facing
  diagnostics, input/UI, release-builder, release-flash, firmware-label, and
  control-flash-safety gates.
- Layout-sensitive LCD/TBLPTR tables have structural guards.
- Current release-facing docs (`README.md`, `AGENTS.md`,
  `docs/HARDWARE_TEST.md`, and feature docs touched by the implementation)
  match canonical artifact metadata in the same change.  Only
  historical/background docs may be deferred through the Documentation
  Follow-Ups template above.
- Focused robustness, middle release-artifact, and full release-promotion gate
  commands are recorded with pass/fail evidence after implementation.
- `docs/TEST_INCIDENTS.md` exists with sanitized entries for the known stale
  identity and LCD corruption incidents, and hardware incident promotion is
  linked from `docs/HARDWARE_TEST.md`.
- Live hardware status is either run with role-scoped, sanitized evidence or
  explicitly marked not run with a reason.

## Risks And Assumptions

- Some prefix assertions are legitimate for dynamic rows.  The implementation must not make scrolling or issue-token tests brittle by forcing exact rows where the firmware intentionally varies output.
- Full `tests/sim -n 16` may be long; use focused gates first and reserve the full gate for release promotion.
- Current worktree has unrelated firmware/docs changes.  Implementation must preserve unrelated changes and use focused pathspecs if a commit is later requested.
- A test-only tightening pass may expose real firmware bugs.  If that happens, update this IMPL with the new evidence and create a feature-specific fix plan before changing firmware.

## Reviewer Findings And Iteration History

Initial draft created from `docs/TEST_ROBUSTNESS_SPEC.md` on 2026-06-27.

### Review Round 1

Eight reviewers ran on the initial draft:

1. Simplicity/scope reviewer.
2. Correctness/contract reviewer.
3. Ops/tests/deploy reviewer.
4. UX/API-consumer reviewer.
5. Security/privacy reviewer.
6. Performance/reliability reviewer.
7. Data/migration compatibility reviewer.
8. Maintainability/observability reviewer.

Round-1 High/Medium findings and disposition:

| ID | Severity | Reviewer role | Issue | Disposition | Resolving section | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R1-COR-01 | High | Correctness/contract | Canonical stale Diagnostics identity regression was not required. | Required canonical `V173_CONTROL_HEX` + `V35_MAIN_HEX` stale-cache tests with artifact-derived expected revision text and focused-gate node IDs. | WU4, WU6, Acceptance Criteria | Closed |
| R1-DATA-01 | High | Data/migration | Canonical PB1/PB2 persistence coverage was not required. | Required canonical cold-boot, dirty-save, invalid/erased/corrupt, and runtime-intent tests while preserving temp-source compatibility matrix. | WU4, WU5, WU6, Acceptance Criteria | Closed |
| R1-UX-01 | Medium | UX/API-consumer | LCD helper API allowed row-1 omission. | Required exact two-row helpers, 16-character row validation, and reason-bearing dynamic helpers. | WU2, WU3, Acceptance Criteria | Closed |
| R1-OPS-01 | High | Ops/tests/deploy | Hardware smoke used pathless `dlcp_diag.py` and could pass with zero MAIN HID devices. | Required `identify-mains --require-left-right`, explicit `$LEFT_HID`/`$RIGHT_HID` smoke commands, and no-device/ambiguous-device regressions. | WU5, WU6, Deployment And Smoke Plan | Closed |
| R1-SEC-01 | Medium | Security/privacy | Hardware incident promotion lacked durable template and redaction rules. | Required `docs/TEST_INCIDENTS.md`, sanitized entries, and local-only raw hardware evidence rules. | WU1, WU6, Acceptance Criteria | Closed |
| R1-OPS-02 | Medium | Ops/tests/deploy | Release builder/flash metadata gates were missing. | Added release-builder, V3.5 release-flash, firmware-label, control-flash-safety, MAIN-flash, and RAM-safety middle gates. | WU5, WU6, Release Artifact Inventory | Closed |
| R1-MAINT-01 | Medium | Maintainability/observability | Required docs omitted feature-specific contracts. | Added Diagnostics identity, Preset filename LCD, multi-PB input, and SRC4382 docs to Required Docs Read. | Required Docs Read | Closed |
| R1-DATA-02 | Medium | Data/migration | Persistence/migration policy incorrectly said "No data migration." | Scoped production migration code out while keeping EEPROM compatibility/migration tests in scope. | Compatibility, Migration, And Deletion Policy | Closed |
| R1-UX-02 | Medium | UX/API-consumer | Current-release preset filename/row-owner coverage was V3.4-only. | Required current V1.73/V3.5 canonical preset filename row-owner/atomicity gate. | WU5, WU6, Acceptance Criteria | Closed |
| R1-MAINT-02 | Medium | Maintainability/observability | Release metadata prose can be stale. | Required artifact-derived expected values and same-change current release/runbook doc updates. | Gap Analysis, Documentation Follow-Ups, Acceptance Criteria | Closed |

Affected-role re-reviews found additional issues, all addressed:

| ID | Severity | Reviewer role | Issue | Disposition | Resolving section | Status |
| --- | --- | --- | --- | --- | --- | --- |
| R2-MAINT-01 | Medium | Maintainability/observability | Release Artifact Inventory and Evidence Matrix were missing. | Added both sections with canonical artifacts, expected-value sources, required coverage, and evidence fields. | Release Artifact Inventory, Evidence Matrix | Closed |
| R2-SCOPE-01 | Medium | Simplicity/scope | Middle gate could be read as replacing focused robustness nodes. | Marked middle gate as additive and required focused, middle, then full simulator gates for release promotion. | WU6 | Closed |
| R2-UX-03 | Medium | UX/API-consumer | Diagnostics final assertions could still pass row0-only. | Required exact `(row0, row1)` canonical healthy assertions or reason-bearing dynamic helper with separate row-1 token/window contract. | WU3, Acceptance Criteria | Closed |
| R2-OPS-03 | Medium | Ops/tests/deploy | `test_dlcp_main_flash.py` subset was missing from middle gate. | Added targeted MAIN flash/preflight/path tests and the canonical V3.5 static detector node. | WU6 | Closed |
| R2-DATA-03 | Medium | Data/migration | Current release metadata docs could be deferred. | Required same-change current release/runbook metadata updates; deferred follow-ups allowed only for historical/background docs. | Documentation Follow-Ups, Acceptance Criteria | Closed |
| R2-SEC-02 | Low | Security/privacy | Raw stdout/stderr and Flipper serial ports were not explicitly local-only. | Added them to local-only raw hardware evidence list. | WU6 | Closed |
| R3-OPS-04 | Medium | Ops/tests/deploy | Focused gate named ambiguous-device coverage but no explicit zero-device node. | Required new `test_identify_mains_fails_when_no_main_devices_visible` and added it to focused gate. | WU5, WU6 | Closed |
| R4-DATA-04 | Medium | Data/migration | Dirty-save lifecycle allowed commit-only proof and could miss immediate-write regression. | Required dirty flags set, no pre-service EEPROM commit, forced save commit, dirty clear, reboot persistence, and no repeat clean commit. | WU4, Acceptance Criteria | Closed |
| R5-MAINT-03 | Medium | Maintainability/observability | Canonical MAIN flash/preflight coverage was ambiguous. | Named existing V35 parameterized static detector node and kept targeted preflight/path tests in middle gate. | Release Artifact Inventory, WU5, WU6 | Closed |
| R5-MAINT-04 | Medium | Maintainability/observability | Review ledger lacked per-item traceability. | Converted findings to tables with severity, role, issue ID, disposition, resolving section, and status. | Reviewer Findings And Iteration History | Closed |

### Final Review Summary

Final review status: ready for implementation.

- Eight independent reviewer roles reviewed the initial IMPL.
- Affected-role re-reviews were run after revisions for correctness/contract,
  ops/tests/deploy, UX/API, security/privacy, performance/reliability,
  data/migration, maintainability/observability, and simplicity/scope.
- Final re-review result: zero unresolved High findings and zero unresolved
  Medium findings.
- Remaining Low items: none requiring pre-implementation revision.  The
  `release_artifact` pytest marker remains intentionally deferred unless the
  implementation finds enough canonical-artifact tests to justify the marker.

## Post-Implementation Evidence

Implementation status: complete for docs/tests/helper hardening.  No firmware source or release HEX changes were made in this pass.

Actual files changed:

- `docs/TEST_INCIDENTS.md`
- `docs/TEST_ROBUSTNESS_IMPL.md`
- `README.md`
- `AGENTS.md`
- `docs/HARDWARE_TEST.md`
- `docs/MULTI_PB_INPUT_SELECTION.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`
- `tests/sim/lcd_assertions.py`
- `tests/sim/test_v172_v33_diag_identity.py`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `tests/sim/test_preset_filename_lcd_spec.py`
- `tests/sim/test_hardware_state_test.py`
- `tests/sim/test_v173_atomic_3byte_frame.py`

Test commands and results:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_flash_table_page_carry_audit.py \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_canonical_diag_ok_title_shows_visible_main_identity \
  tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache \
  tests/sim/test_v173_multi_pb_input_selection.py::test_canonical_hex_split_menu_visible_behavior_regression \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_pb1_spdif_pb2_aes_persisted_inputs_survive_cold_boot \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_pb1_pb2_dirty_save_commits_eeprom_and_clean_save_no_churn \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_invalid_erased_corrupt_input_eeprom_does_not_import_ambiguous_status \
  tests/sim/test_v173_multi_pb_input_selection.py::test_v173_canonical_pb2_corrupt_runtime_intent_clamps_to_safe_fallback \
  tests/sim/test_preset_filename_lcd_spec.py::test_v172_v33_fname_foreground_ir_buttons_standby_while_pending_valid_scrolling \
  tests/sim/test_preset_filename_lcd_spec.py::test_v173_v35_canonical_preset_lcd_suffix_and_row1_atomicity_matrix \
  tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_no_main_devices_visible \
  tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_two_roles_are_not_unique \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_dlcp_control_flash_safety.py
# 55 passed in 75.48s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_dlcp_control_flash_safety.py \
  "tests/sim/test_dlcp_main_flash.py::test_static_hid_version_detector_accepts_compact_v34_plus_shape[v35]" \
  tests/sim/test_flash_table_page_carry_audit.py \
  tests/sim/test_dlcp_main_flash.py::test_preflight_accepts_app_only_hex_without_bootloader_bytes \
  tests/sim/test_dlcp_main_flash.py::test_preflight_rejects_explicit_bootloader_drift \
  tests/sim/test_dlcp_main_flash.py::test_cli_blocks_unsafe_flags_without_force \
  tests/sim/test_dlcp_main_flash.py::test_cli_info_only_does_not_require_hex \
  tests/sim/test_dlcp_main_flash.py::test_cli_warns_when_device_revision_is_same_or_newer \
  tests/sim/test_dlcp_main_flash.py::test_pick_device_auto_resolve_requires_unambiguous_match
# 67 passed in 0.86s

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35
# RAM bank safety: OK (main-v35)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
# RAM bank safety: OK (control-v173)

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
# 2082 passed, 2 skipped, 4 xfailed, 10 warnings in 1001.77s
```

Deploy/smoke evidence: no deploy.  This was a docs/tests-only hardening pass; no write-mode CONTROL or MAIN flash commands were run.  Live hardware was not run because the requested change was simulator/test robustness, and live hardware gates remain opt-in with role-scoped sanitized evidence requirements.

Unresolved low-risk issues: none for this IMPL.  The `release_artifact` pytest marker remains intentionally deferred unless later canonical-artifact coverage grows enough to justify it.
