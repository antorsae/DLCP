# Multi-PB Input Selection Persistence IMPL

Date: 2026-06-22
Status: Implemented in local CONTROL V1.73 x53 candidate; simulator gated
Source spec: `docs/MULTI_PB_INPUT_SELECTION.md`
Related spec: `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
Scope: CONTROL V1.73+ PB2 input-setting persistence.  No MAIN code, no HFD/PC
UI changes, no current-loop protocol changes, and no live hardware flash.

## Current Executable Scope

This IMPL is intentionally separate from the runtime-only multi-PB x52 ledger
in `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`.

The implemented persistence change is narrow:

1. Audit CONTROL EEPROM ownership and choose one safe byte plus, if needed, a
   migration/schema discriminator.
2. Decode that byte through a closed allowlist into a pending PB2 setting.
3. Apply the pending setting only after existing PB2 health/Diagnostics
   discovery latches PB2 as present.
4. Save only sanitized runtime state on explicit settings-save paths.
5. Keep the x52 runtime clamps at every LCD/menu/send use site.

Do not persist menu rows, raw `cmd 0x06` payloads, or live route bytes.

Implemented result:

- EEPROM `0x5F` is the CONTROL-owned PB2 input persistence byte.
- `0xA0` means linked `Same as PB1`.
- `0xB0..0xB8` mean concrete PB2 `cmd 0x06` payloads `0x00..0x08`.
- `0xFF`, legacy raw payloads `0x00..0x08`, and every unknown byte decode
  to linked.
- Valid concrete values remain pending until PB2 is discovered.
- Unavailable persisted concrete values fall back to linked for the boot and
  are not overwritten by unrelated settings saves.
- PB2 user changes set a dirty bit; save compares EEPROM and skips identical
  writes.

## Required Docs Read

- `AGENTS.md`: canonical paths, V1.73/V3.5 release artifacts, build/test gates,
  and path policy.
- `README.md`: current V3.5/V1.73 candidate, simulator setup, release caveats,
  and the PB2 DOWN/audio-routing/persistence field-closure status.
- `CODING_STYLE.md`: CONTROL assembly style and verification rules.
- `docs/MULTI_PB_INPUT_SELECTION.md`: persistence guardrails and acceptance
  requirements.
- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`: runtime-only multi-PB behavior and
  source/menu/send contracts.
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`: historical x52 runtime implementation
  ledger and simulator/release evidence.
- `docs/V16B_SOURCE_REWRITE_SPEC.md`: CONTROL EEPROM layout; `0x75..0xFE` are
  stock user settings and `0x71..0x74` are already owned by V1.7x metadata and
  preset state.
- `docs/HARDWARE_TEST.md`: settings-preservation and role-safe live hardware
  evidence requirements.
- `src/dlcp_fw/flash/dlcp_control_flash.py`: release flashing streams CONTROL
  program flash up to `0x77BF` and ignores EEPROM/config regions.

## Baseline Evidence Used

- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md` states the original phase-1
  multi-PB work was runtime-only and did not write new CONTROL EEPROM bytes.
- `docs/V16B_SOURCE_REWRITE_SPEC.md` documents EEPROM `0x60..0x70` as stock
  display/input settings, `0x71..0x73` as version tuple, `0x74` as preset, and
  `0x75..0xFE` as stock user settings.
- `src/dlcp_fw/flash/dlcp_control_flash.py::build_control_stream` fills and
  streams program memory only; the docstring says non-program regions,
  including EEPROM, are ignored.  Therefore boot firmware must handle erased or
  legacy EEPROM itself.
- `src/dlcp_fw/asm/dlcp_control_v173.asm::input_split_latch_pb2_seen`
  previously set `PB2_SEEN`, set `PB2_LINKED`, and copied PB1 input into
  `input_intent_pb2` when PB2 was first discovered.  Persistence changes that
  latch path so a sanitized pending setting can be applied there.
- `input_screen_compute_menu_max`, `input_screen_clamp_staged_row`,
  `input_screen_prepare_selected_row`, `input_screen_prepare_option_label`, and
  the targeted/full-sync send paths are the intended x52 use-site safety net.
  WU0 below treats active PB2 redraw clamp order as a blocking precondition
  because persistence must not feed any stale/corrupt row into label lookup or
  send mapping.
- `tests/sim/test_v173_multi_pb_input_selection.py` already covered x52 invalid
  raw-status behavior around PB2 `Same as PB1` + DOWN; persistence adds
  EEPROM-preload and round-trip coverage without weakening those tests.

## Closed Gaps

- EEPROM ownership is documented in `docs/MULTI_PB_INPUT_SELECTION.md`;
  `0x5F` is used because it is erased in the baked image and outside the
  existing settings load/save ownership.
- The `0xA0`/`0xB0..0xB8` encoding prevents legacy raw source bytes from being
  trusted as intentional PB2 settings.
- Pending PB2 state now exists at `input_pending_pb2`; it is applied only by
  `input_split_latch_pb2_seen`.
- Exhaustive decoder coverage checks every byte in `0x00..0xFF`.
- The simulator facade now exposes CONTROL EEPROM readback for direct
  save/load assertions.
- EEPROM write-count checks use memory trace `EepromCommit` records.
- Live hardware field closure remains separate; this implementation does not
  claim hardware audio/SRC validation.

## Proposed Implementation

### WU0: Blocking Precondition Hardening

Do not start EEPROM persistence until active PB2 redraw, commit, and send paths
are proven to clamp the row immediately before label lookup and send mapping.
If inspection shows a direct redraw branch to `input_screen_prepare_option_label`
without a fresh clamp, fix that first.

Required precondition tests:

- structural order test proving the active input screen clamps before
  `input_screen_prepare_option_label`;
- behavioral redraw test with corrupt staged PB2 row while on `Input PB2`;
- behavior/structural proof that full-sync and targeted PB2 send paths clamp
  corrupt independent `input_intent_pb2` before any `cmd 0x06` byte is emitted;
- CONTROL EEPROM readback or equivalent oracle support for later save/load
  tests, plus EEPROM commit/write-count observability using memory trace
  `EepromCommit` records or a simulator facade.

### WU1: EEPROM Ownership Audit

Create a byte-by-byte CONTROL EEPROM map for `0x00..0xFF` with owner, current
use, stock value, current value, migration default, preservation rule, rollback
behavior, and test coverage.  Update the canonical EEPROM docs before assembly
reads or writes the new byte.

Stop if no safe byte is proven.  Do not borrow `0x75..0xFE` without a stronger
migration plan because those bytes are stock user settings.

### WU2: Migration Discriminator

Either prove the selected byte is erased/unused across stock/current images and
available field captures, or add a schema marker/versioned encoding.  Without
that proof or marker, every pre-migration value must decode to linked
`Same as PB1`, even if the byte numerically matches a future enum.

The release flash path must remain app-flash-only; it must not be required to
initialize EEPROM defaults.

### WU3: Closed Decoder And Pending State

Define a CONTROL-owned persisted enum with explicit allowlisted values for:
`linked`, `auto`, `spdif`, `usb`, `aes`, `optical`, and `analogue1..4`.

Load code must decode the raw EEPROM byte into pending sanitized state, not
directly into `display_state_index`, `menu_option_selected_index`,
`input_intent_pb2`, route bytes, or `cmd 0x06` payloads.  `0xFF` and every
unknown/pre-migration value decode to pending linked.

Pending state must not set `PB2_SEEN`, expose `Input PB2`, or emit addressed
PB2 frames before PB2 is discovered.

### WU4: Latch-Time Apply

Modify `input_split_latch_pb2_seen` so PB2 discovery applies the pending
sanitized setting:

- pending linked/unknown/pre-migration: set `PB2_LINKED` and use broadcast.
- pending valid concrete source: clear `PB2_LINKED` and set
  `input_intent_pb2` from the allowlisted source map.
- pending valid concrete source that is unavailable for the current
  `raw_status_cache` source-list class: use linked for this boot and do not
  overwrite EEPROM unless the user explicitly saves a new PB2 setting.

The existing remap of legacy Setup/PB1 Diag/PB2 Diag pages to split states must
remain intact.

### WU5: Save, Dirty Flag, And Endurance

Save PB2 input state only when the user explicitly changes/commits the PB2
setting.  Add a PB2 persistence dirty/intent flag or equivalent so a generic
settings save can distinguish "the user changed PB2" from "runtime fallback is
active for this boot."  Compare with the current EEPROM value or a shadow byte
and skip writes when unchanged.

Navigation, redraw, health polling, reconnect, full-sync, standby/wake, and
PB2 relink/discovery cycles must not write the PB2 EEPROM byte by themselves.

When a valid persisted concrete source falls back to linked because the current
source-list class does not expose that source, an unrelated settings save must
preserve the original persisted enum.  Only a direct user PB2 change may replace
it.

If runtime PB2 state is corrupt at save time, write linked/default rather than
serializing an invalid byte.

### WU6: Use-Site Validation

Keep or add defensive clamps before:

- LCD label lookup.
- menu UP/DOWN wrap.
- PB2 row-to-source mapping.
- `cmd 0x06` payload generation.
- full-sync and targeted PB2 sends.
- malformed `BF/06` payload handling in legacy, linked, and independent modes.

Use allowlists for valid persisted values and valid command payloads.  Reject
malformed `BF/06` payloads such as `0x09`, `0x0A`, `0x7F`, `0x80`, and `0xFF`
rather than treating them as menu indices.

## Likely Files

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- a focused EEPROM/persistence test helper if existing fixtures cannot preload
  arbitrary CONTROL EEPROM bytes cleanly
- `docs/V16B_SOURCE_REWRITE_SPEC.md` or a newer EEPROM map doc
- `docs/MULTI_PB_INPUT_SELECTION.md`
- `docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md`
- `docs/HARDWARE_TEST.md` if hardware evidence steps change

## Test Plan

Focused tests:

- Exhaustive pure decoder test for every raw value `0x00..0xFF`; only
  allowlisted encoded values restore concrete settings, and all other values
  restore pending linked.
- Discriminator collision tests: raw bytes equal to every future enum value
  without a valid discriminator/proof decode linked; the same bytes restore
  concrete settings only through the documented discriminator or proven-unused
  path.
- Boot tests for at least `0xFF`, `0x80`, `0x7F`, `0x00`, and all allowlisted
  enum values.  Assert no reset/hang, no garbage LCD, no invalid frame, and no
  PB2 page before PB2 discovery.
- Valid persisted enum x `raw_status_cache` source-list classes `0x00..0x03`
  plus unknown values `0x04`, `0x7F`, `0x80`, and `0xFF`; latch-time apply
  must either use the same full-input semantics as `0x03` or fall back linked
  without sending invalid frames.
- Unavailable persisted concrete source -> linked fallback for this boot ->
  unrelated settings save -> EEPROM still contains the original persisted enum.
- PB2 discovery applies pending linked vs pending concrete state exactly once
  and preserves visible page remap behavior.
- Single-PB/PB2-unknown boot with valid PB2 EEPROM value keeps legacy `Input:`
  UI and broadcast sends until PB2 discovery.
- Save/readback tests for linked and every valid concrete PB2 value; corrupt
  runtime state saves linked/default.  These require CONTROL EEPROM readback or
  an equivalent oracle.
- Split runtime states `3..6` save to legacy EEPROM states `2..5`, reboot,
  rediscover PB2, and preserve visible page identity.  In particular, saved
  legacy PB1 Diag state `4` must become split state `5`, and saved legacy PB2
  Diag state `5` must become split state `6`; if the simulator cannot exercise
  this, make it a named hardware/manual gate before implementation closure.
- Endurance tests prove repeated navigation/redraw/health/reconnect/full-sync/
  relink cycles perform no PB2 EEPROM writes, using EEPROM write-count/commit
  observability.
- Release-flash/settings-preservation test proves app flashing preserves the
  PB2 byte or intentionally migrates it per the documented rule.
- Display-state EEPROM invalid values including `0x06`, `0x07`, `0x0A`,
  `0x7F`, `0x80`, `0xFE`, and `0xFF` remain legacy-safe before PB2 discovery.
- Malformed `BF/06` payloads `0x09`, `0x0A`, `0x7F`, `0x80`, and `0xFF` cannot
  corrupt PB1/PB2 intent in legacy, linked, or independent modes.

Implementation evidence:

- Firmware source: `src/dlcp_fw/asm/dlcp_control_v173.asm`
  (`+126/-5`) and `src/dlcp_fw/asm/dlcp_control_ram.inc` (`+7/-0`).
- Simulator API/readback support:
  `src/dlcp_fw/sim/dlcp_sim_native.py` (`+6/-0`) and
  `crates/dlcp-sim-py/src/lib.rs` (`+6/-0`).
- Tests: `tests/sim/test_v173_multi_pb_input_selection.py` (`+430/-4`).
- Docs: this IMPL, `docs/MULTI_PB_INPUT_SELECTION.md`,
  `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`, `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`,
  `README.md`, and `AGENTS.md`.
- Canonical CONTROL release artifact: `firmware/patched/releases/DLCP_Control_V1.73.hex`
  rebuilt as `V1.73 / rev 0x53 / build 20260622`.
- CONTROL listing headroom before metadata `0x77B0`: `app_end=0x336A`,
  `byte_margin=17478`, `free_object_words=8739`.
- The release builder was run after firmware source changes and before the
  final docs/test-only evidence edits.  It was not rerun afterward because it
  would create a false x54 revision without a firmware source change.

Completed focused gates:

```bash
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'pb2_full_sync_clamps_corrupt_intent or malformed_pb2_state_recovers_to_active_max_commit or pb2_same_as_pb1_down_clamps_unknown_raw_status'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'decoder_is_closed_allowlist or display_state_save_load_remaps or pb2_menu_state_and_malformed_row'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'user_selected_concrete_round_trips or same_as_pb1_round_trips or split_display_states_save or malformed_bf06_payloads or dirty_flag_prevents'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'every_user_selected_concrete or valid_pb2_eeprom_stays_pending or corrupt_runtime_pb2_intent or navigation_full_sync_and_relink'
.venv/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -n 8
PYTHONPATH=src .venv/bin/python scripts/check_ram_access_safety.py --target control-v173
```

Focused results:

- WU0 clamp/send/readback subset: `11 passed, 56 deselected`.
- Structural decoder/display/menu subset: `3 passed, 104 deselected`.
- First persistence subset: `15 passed, 92 deselected`.
- Added all-source/latent/corrupt/endurance subset:
  `4 passed, 107 deselected in 66.92s`.
- Full multi-PB file: `111 passed in 164.64s`.
- RAM bank safety: `RAM bank safety: OK (control-v173)`.

Completed release gates:

```bash
.venv/bin/python -m pytest tests --collect-only -q
.venv/bin/python -m pytest tests/sim -n 16 -q
.venv/bin/python scripts/check_phase5_gate.py
.venv/bin/python scripts/check_gpsim_excision.py
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm src/dlcp_fw/asm/dlcp_control_ram.inc docs/MULTI_PB_INPUT_SELECTION.md docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md tests/sim/test_v173_multi_pb_input_selection.py src/dlcp_fw/sim/dlcp_sim_native.py crates/dlcp-sim-py/src/lib.rs
git rev-parse HEAD
git status --short --porcelain=v1 -- docs/MULTI_PB_INPUT_SELECTION.md docs/MULTI_PB_INPUT_SELECTION_SPEC.md docs/MULTI_PB_INPUT_SELECTION_IMPL.md docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md README.md AGENTS.md src/dlcp_fw/asm/dlcp_control_v173.asm src/dlcp_fw/asm/dlcp_control_ram.inc tests/sim/test_v173_multi_pb_input_selection.py src/dlcp_fw/sim/dlcp_sim_native.py crates/dlcp-sim-py/src/lib.rs firmware/patched/releases/DLCP_Control_V1.73.hex
```

Release-gate results:

- collect-only: `2003 tests collected in 0.95s`.
- full simulator gate:
  `1978 passed, 2 skipped, 4 xfailed, 1 warning in 1665.78s`.
- Phase 5 gate: `P5.gate GREEN`.
- gpsim excision: `gpsim retirement clean: no live references found`.
- git HEAD: `1fe8cae0d26075991f1d8039456e7dae145894a1`.
- scoped status: expected modified/added implementation, docs, tests, sim API,
  and canonical CONTROL HEX paths; no commit was requested.

SHA-256:

- `firmware/patched/releases/DLCP_Control_V1.73.hex`:
  `3a7dd25e29c3ce731a2783d1370fb5f2b387ba4a4be7c6a48b3bb19dfb207302`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`:
  `c75161a4c1394d129d4c536c98117e97669e597e8ced87ad9d3a173fd4f9820a`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`:
  `a8c191ac6c2b1b383d5ba5d1d85ae1ee6f4286e34fe395efd103da32d796c611`
- `tests/sim/test_v173_multi_pb_input_selection.py`:
  `3aad2418dca196261e2a9955f038eb55d7bb94e7e61eaa3f7bfd1c43f4b1aae6`
- `src/dlcp_fw/sim/dlcp_sim_native.py`:
  `a437e9a99fca96fb88d29537592b20585d549e36dea94ebeeb6c7204ccff1e7a`
- `crates/dlcp-sim-py/src/lib.rs`:
  `a804abcfca2a4037d896fe7e48cbedabf621185f1a05b902f208f1309476a5f9`

Docs are tracked by the scoped git status rather than self-hashed here because
this IMPL is itself the final evidence document.

## Deployment And Hardware Smoke

No deployment is part of this IMPL.  Live hardware requires explicit operator
approval and the role-safe flow in `docs/HARDWARE_TEST.md`.

Hardware closure must separate:

- PB2 DOWN reboot closure: exact CONTROL revision, PB2 `Same as PB1`, DOWN,
  no reboot/USB re-enumeration/boot splash, and PB1/PB2 state evidence.
- Full multi-PB audio closure: PB1 Optical, PB2 AES, PB2 Auto Detect AES/CAT,
  SRC4382 snapshots from each MAIN, and operator audio confirmation.
- Persistence closure: erased/legacy EEPROM first boot, valid setting restore,
  settings preservation across release flash, and no unexpected EEPROM writes
  during navigation/health/full-sync.

Use a tracked evidence note or template such as
`artifacts/probes/multi_pb_input_persistence_evidence_TEMPLATE.md` for each
hardware run.  Required fields: date, operator, exact hex hash, CONTROL
revision/build, git HEAD/status, PB1/PB2 role identification, HID identifiers
as role labels or locally salted hashes, LCD/photo/video references, SRC4382 or
RAM evidence, EEPROM pre/post summaries, write-count/commit evidence, and
explicit pass/fail for PB2 DOWN, audio-routing, and persistence closure.

Raw HID paths, probe identifiers, and field EEPROM dumps stay local/ignored.
Shared artifacts should contain role labels, hash-only identifiers, byte
ownership/classification, migration decisions, redacted value summaries, and
hashes where useful, not raw serial/path strings or full EEPROM captures.

## Acceptance Criteria

- A documented CONTROL EEPROM byte and migration/discriminator rule exists
  before any source reads/writes it.
- `0xFF` and every unknown/pre-migration byte decodes to pending linked
  `Same as PB1`.
- Raw EEPROM bytes never become LCD rows, menu indices, route bytes, or
  `cmd 0x06` payloads.
- Valid persisted PB2 settings remain latent until PB2 discovery.
- Single-PB/PB2-unknown behavior remains legacy and broadcast-only.
- PB2 discovery applies pending settings safely, including unavailable-source
  fallback.
- Use-site clamps remain in place and are covered by tests.
- Exhaustive invalid-byte tests pass.  Full release-flash/settings-preservation
  coverage remains a release gate before hardware deployment.
- EEPROM writes happen only on explicit save/commit and skip unchanged values.
- V1.73 x52-compatible behavior remains unchanged when persistence bytes are
  absent, erased, legacy, or invalid.

## Reviewer Findings And Iteration

Initial eight-reviewer pass covered simplicity/scope, correctness/contract,
ops/tests/deploy, UX/API-consumer, security/privacy, performance/reliability,
data/migration compatibility, and maintainability/observability.

Blocking themes incorporated in this draft:

- Persistence is separated from the x52 runtime IMPL.
- EEPROM ownership requires a byte-by-byte audit and migration discriminator.
- Erased/unknown/pre-migration bytes are first-class inputs and default linked.
- Valid persisted PB2 state remains latent until PB2 discovery.
- The CONTROL release flash path is app-flash-only and cannot be the default
  initializer.
- Exhaustive `0x00..0xFF` decoder coverage is mandatory.
- EEPROM endurance and save-only write semantics are explicit.
- Hardware closure distinguishes reboot, audio-routing, and persistence
  evidence.

Iteration 1 rerun findings and dispositions:

- Ops/tests/deploy Medium: release provenance needed `git rev-parse HEAD` and
  `git status --short`; added to release gate.
- UX/API Medium: saved legacy Diagnostics states `4/5` needed explicit
  coverage; added split-state save/load behavioral tests and hardware/manual
  fallback gate.
- UX/API Medium: unavailable-source fallback could be overwritten by unrelated
  settings save; added PB2 dirty/intent flag and preservation test.
- Simplicity/scope Medium: runtime IMPL mixed flasher policy with multi-PB
  feature scope; clarified as x52 operational cleanup in the runtime IMPL.
- Correctness/contract Medium: split-state EEPROM save/readback lacked an
  oracle; added CONTROL EEPROM readback/equivalent-oracle precondition.
- Security/privacy Medium: persisted-enum tests needed unknown raw-status
  values beyond `0x80`; added `0x04`, `0x7F`, `0x80`, and `0xFF` apply tests.
- Maintainability/observability Medium: new canonical docs were untracked;
  marked them intent-to-add so normal `git diff` includes reviewable content.
- Maintainability/observability Medium: hardware evidence was prose-only; added
  tracked evidence-template path and required fields.
- Performance/reliability Medium: active PB2 redraw clamp was only a soft
  check; promoted WU0 to a blocking precondition.

Final rerun gate status:

- High findings: none recorded.
- Medium findings: none recorded.
- Final implementation audit against this IMPL found the previously missing
  all-concrete save/readback, single-PB latent setting, corrupt-runtime save,
  and endurance/no-write tests; those are now covered by the focused and full
  gates above.
- Low findings:
  - live hardware PB2 DOWN, audio-routing, and persistence/settings-preservation
    gates were not run because no flash/deploy approval was part of this IMPL;
  - docs remain intent-to-add/uncommitted until the next intentional commit;
    no commit was requested for this pass.
