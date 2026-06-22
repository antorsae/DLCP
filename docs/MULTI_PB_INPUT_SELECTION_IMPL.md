# Multi-PB Input Selection Incremental IMPL

Date: 2026-06-21
Status: Baseline multi-PB input selection implemented and simulator-gated.
BUG-V173-MPB-PB2-DOWN-RAW is simulator/release-gated in V1.73 `x52`, but
live hardware field closure remains pending.
Source spec: `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
Scope: V1.73 CONTROL implementation, tests, docs, and canonical release
artifact; no MAIN code changes and no live hardware flash without explicit
operator approval.

## Current Overall Status

As of the x52 runtime bugfix pass on 2026-06-22, the active candidate was
canonical CONTROL `V1.73 / rev 0x52 / build 20260622`.  This status block is
historical; x53 persistence is tracked separately in
`docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md`.

- Focused source and canonical-HEX regression gates passed, including full
  multi-PB visible behavior, PB2 `Same as PB1` + DOWN, corrupt PB2 full-sync
  intent clamping, linked/independent full-sync, compatibility, and the BF/08
  ACKSTAT-only stale-`!` follow-up.
- Broad non-hardware gates passed against x52:
  `tests/sim -n 16`, `check_phase5_gate.py`, and `check_gpsim_excision.py`.
- No live hardware flash/smoke was performed in this pass, so the field reboot
  is not hardware-validated or field-closed.
- Older baseline status sections below are historical for the incremental
  multi-PB feature and are superseded by this block for BUG-V173-MPB-PB2-DOWN-RAW.

## PB2 Persistence Follow-Up

V1.73 x52 remains the historical runtime-only multi-PB ledger.  PB2 input
persistence is the x53 follow-up and must not be inferred from the x52 runtime
state.

The canonical persistence guardrails are in
`docs/MULTI_PB_INPUT_SELECTION.md`.  The reviewed persistence implementation
ledger is kept separate in
`docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md` so this x52 ledger stays
focused on the implemented multi-PB runtime behavior.

## Summary

This is an incremental change over the current V1.73 split-input draft already
present in `src/dlcp_fw/asm/dlcp_control_v173.asm` and
`tests/sim/test_v173_multi_pb_input_selection.py`.

The existing draft already adds runtime PB2 discovery, `input_split_flags`,
`input_intent_pb2`, addressed PB1/PB2 input senders, split full-sync, and
`BF/06` quarantine.  The requested delta is narrower:

1. Move `Input PB2` from appended state 6 to inserted state 3, immediately
   after `Input PB1`.
2. Make PB2 default to `Same as PB1`, using legacy broadcast input behavior
   while linked.
3. Make the Volume page source row render PB1's intended input only.
4. Preserve page identity and EEPROM safety when the inserted state shifts
   Setup/Diagnostics.

## Source Requirements

Goals:

- Preserve legacy single-PB/PB2-unknown behavior.
- In two-PB mode, render this ring:

```text
Volume -> Preset -> Input PB1 -> Input PB2 -> Setup -> PB1 Diag -> PB2 Diag -> Volume
```

- Show `Input PB2` after PB2 is seen by health or Diagnostics; visiting PB2
  Diagnostics is not required.
- PB2 row 0 is `Same as PB1`, default on first discovery.
- While PB2 is linked, input changes and full-sync use broadcast
  `[B0,0x06,pb1_input_select]`.
- Once PB2 is changed to a concrete source, PB1/PB2 use addressed frames.
- Changing PB2 back to `Same as PB1` relinks and returns to broadcast.
- Volume source text is always PB1-authoritative.
- No MAIN command, MAIN USB, HFD, SRC4382 diagnostic, or EEPROM schema change.

Invariants:

- MAIN V3.5 `cmd06_input_select_handler` remains the input implementation.
- CONTROL runtime split state is cold-boot volatile.
- Ambiguous `BF/06` must not collapse independent PB1/PB2 intent.
- Three-byte current-loop sends remain atomic via `tx_ring_reserve_3`.
- Existing stock/single-PB compatibility tests must remain valid.

Source-spec correction made during review:

- Test requirement 22 now explicitly separates linked and independent behavior.
  Health-only PB2 discovery keeps the PB2 page visible; linked `Same as PB1`
  stays broadcast through standby/wake and health-loss/rejoin coverage, while
  independent PB2 stays addressed.  A true current-loop reconnect/WAITING
  recovery path is not claimed by the focused/simulator tests.

## Baseline / Worktree Prerequisites

This IMPL is deliberately incremental against the current workspace draft, not
a from-clean-stock V1.73 plan.  Before implementation, verify the current tree
already has the first split-input draft:

- `src/dlcp_fw/asm/dlcp_control_v173.asm` contains
  `input_split_latch_pb2_seen`, `input_frame_send_pb2_targeted`,
  `input_frame_send_split_sync`, `input_frame_send_current_input_page`, and
  PB2 title rendering.
- `src/dlcp_fw/asm/dlcp_control_ram.inc` contains `input_split_flags`,
  `INPUT_SPLIT_FLAG_PB2_SEEN`, `INPUT_SPLIT_FLAG_SYNC_TARGET`,
  `input_intent_pb2`, and `input_send_target`.
- `tests/sim/test_v173_multi_pb_input_selection.py` exists and currently pins
  the appended-state draft.

If these prerequisites are absent, stop and update the IMPL for a clean
baseline instead of applying the incremental edits blindly.

## Required Docs Read

- `AGENTS.md`: canonical layout, release artifacts, test matrix, build paths,
  and canonical V3.5/V1.73 release builders.
- `README.md`: current V3.5/V1.73 candidate pair, simulator setup, flashing
  commands, validation commands, CONTROL bootloader path guidance, and
  no-warranty/recovery caveats.
- `CODING_STYLE.md`: CONTROL assembly naming, fixed-address ABI caution,
  comments, and verification expectations.
- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`: source requirements for this work.
- `docs/SIMULATION.md`: rust single-process chain simulator and Python
  `Chain` facade used by tests.
- `docs/TEST_SIMULATOR.md`: historical simulator/test scope and current
  `tests/sim` policy.
- `docs/HARDWARE_TEST.md`: live hardware role-safe PB1/PB2 identification and
  explicit HID-path validation.
- `docs/V171_V32_LINK_HEALTH_FRESHNESS_SPEC.md`: `v171_health_seen_mask`,
  `v171_health_age_pb1/pb2`, `[B1/B2,0x23,0x00]`, stale/lost display model.
- `docs/V16B_SOURCE_REWRITE_SPEC.md`: CONTROL EEPROM layout; `0x75..0xFE`
  remain stock user settings, so this phase must not allocate persistence.
- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md`: fixed-input route contract,
  including AES and Optical SRC4382 route pairs.
- `firmware/reference/DLCP-manual-R3.pdf`: manual basis for shared input board,
  AES via control cable, and stock equal-source behavior.
- `firmware/reference/dlcp.md`: J2 S/PDIF, AES, and Optical I/O pins.
- `docs/REFACTORING_V34_V173_SPEC.md`: CONTROL listing headroom and deployment
  policy to reconcile with the current safe flasher implementation.
- `src/dlcp_fw/flash/dlcp_control_flash.py` and `scripts/flash_control_safe.sh`:
  CONTROL flashing goes through the selected MAIN USB HID relay (`cmd 0x42`);
  default VID/PID is the MAIN DLCP USB device, and timeout guidance says the
  selected MAIN must be connected to CONTROL.

## Pre-Implementation Baseline Evidence

Current V1.73 split-input draft:

- `input_frame_send` at `src/dlcp_fw/asm/dlcp_control_v173.asm:2952` already
  emits legacy broadcast before split, and PB1 addressed once split is latched.
- `input_frame_send_pb2_targeted`, `input_frame_send_split_sync`, and
  `input_frame_send_current_input_page` at `:2989..3020` already implement the
  appended-PB2 draft.
- `input_split_latch_pb2_seen` at `:5980` latches PB2 when
  `v171_health_seen_mask.bit1` or `v171_diag_present.bit1` is set, seeds
  `input_intent_pb2`, and does not require PB2 Diagnostics visit.
- `v171_health_service` at `:5996` currently has special handling for appended
  state 6, then allows top-level states `<4`.
- `rx_parser_entry__check_input_select_cmd` at `:1141` already quarantines
  ambiguous `BF/06` after split is latched.
- `post_connect_init__non_volume_page_dispatch` at `:6894` currently dispatches
  state 3 Setup, state 4 PB1 Diag, state 5 PB2 Diag, state 6 Input PB2.
- `input_menu_max_state_to_w` at `:7281` returns max 6 when split is latched.
- `settings_save_eeprom` at `:2507` currently clamps runtime state 6 to
  legacy state 2; this is insufficient once Setup/Diagnostics shift.
- `input_screen_stage_selected_index`, `input_screen_write_title`, and
  `input_commit_selected_input_intent` at `:8200..8272` distinguish PB1 from
  appended state 6 PB2.
- `input_pb_title_table` at `:8440` already contains PB1/PB2/old/lost titles.
- `src/dlcp_fw/asm/dlcp_control_ram.inc:441` defines `input_split_flags`,
  `INPUT_SPLIT_FLAG_PB2_SEEN`, `INPUT_SPLIT_FLAG_SYNC_TARGET`,
  `input_intent_pb2`, and `input_send_target`.

Current simulator evidence from the canonical dirty working tree:

```text
pb2_latch_after_connected_ticks 2000000 sec 0.041666666666666664 chunks 57
0 Volume:-17.0dB A / Auto Detect
1 Preset A
2 Input PB1: / Auto Detect
3 Setup / BL Timeout
4 PB1 OK / O1
5 PB2 OK / O1
6 Input PB2: / Auto Detect
0 Volume:-17.0dB A / Auto Detect
```

This proves PB2 can be latched by health quickly, but the current menu order
and PB2 default are not the requested behavior.

Existing tests:

- `tests/sim/test_v173_multi_pb_input_selection.py` is the primary target.  It
  currently pins `STATE_INPUT_PB2 = 6`, appended traversal, PB2 default
  `Auto Detect`, addressed sends immediately after split, state-6 health
  service, and state-6 EEPROM clamp.
- `tests/sim/test_v34_v173_compatibility.py` has a compatibility expectation
  for V1.73 mixed-pair Input title around line 331.
- `tests/sim/test_v32_src4382_autodetect_polling.py` and
  `tests/sim/test_v32_src4382_audio_path_regression.py` cover fixed digital
  SRC route/TAS behavior that must continue to pass.

MAIN evidence:

- `src/dlcp_fw/asm/dlcp_main_v35.asm` already accepts addressed `cmd 0x06`;
  no MAIN functional change is expected.
- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md` pins AES as route 3 with
  `0x0D=0x08`, `0x08=0x30` and Optical as route 4 with `0x0D=0x0B`,
  `0x08=0xF0`.

## Gap Analysis

Already implemented:

- Runtime PB2 discovery latch.
- Split RAM aliases.
- Addressed PB1/PB2 input frames.
- Split full-sync alternating addressed frames.
- PB2 stale/lost title strings.
- `BF/06` quarantine once split is latched.

Missing or stale:

- State 3 is still Setup; PB2 Input is appended at state 6.
- PB2 discovery does not remap visible state 3/4/5 to 4/5/6.
- PB2 default is a concrete source, not `Same as PB1`.
- Split immediately uses addressed PB1 frames; it should broadcast while PB2 is
  linked to PB1.
- PB2 row indexing cannot represent the extra first option.
- Volume source rendering can inherit shared source-menu scratch and show PB2.
- Save/load only handles appended state 6, not inserted state remapping.
- Health suffix patching currently treats state 3 as a top-level suffix page;
  after insertion, state 3 PB2 Input must not get row-2 suffix corruption.
- Split Setup will move to state 4, so existing `<4` top-level health/suffix
  predicates would regress Setup unless made semantic rather than numeric.

## Proposed Implementation

### Work Unit 1 - Update Red Tests For The Increment

Modify `tests/sim/test_v173_multi_pb_input_selection.py` first so it fails on
current code:

- Set `STATE_INPUT_PB2 = 3`, `STATE_SETUP_SPLIT = 4`,
  `STATE_DIAG_PB1_SPLIT = 5`, `STATE_DIAG_PB2_SPLIT = 6`.
- Rename state-6 tests to state-3 PB2 Input tests.
- Assert health-only discovery shows `Input PB2` immediately after
  `Input PB1`.
- Assert traversal order is
  `Preset, Input PB1, Input PB2, Setup, PB1 Diag, PB2 Diag, Volume`.
- Add remap tests for latching split while on legacy Setup/PB1 Diag/PB2 Diag.
- Add PB2 default test: `Input PB2:      ` / `Same as PB1     `.
- Add linked-mode tests proving PB1 UP and full-sync emit `[B0,0x06,*]` until
  PB2 selects a concrete source.
- Add linked-mode `BF/06` test: while PB2 is `Same as PB1`, inject
  `BF/06/<new-input>`, prove PB1/linked single intent updates as legacy, and
  prove the next linked full-sync broadcasts the updated value.  This follows
  the source spec's "legacy broadcast/single-intent allowed" rule for linked
  mode.
- Update independent-mode tests so PB2 first moves from `Same as PB1` to the
  requested concrete source, then expects addressed frames.
- Add independent-mode `BF/06` test: divergent PB1/PB2 intent must survive an
  ambiguous `BF/06`, and full-sync must keep using the pre-existing independent
  intents.
- Add relink test: PB2 concrete source -> `Same as PB1` -> next PB1 input and
  full-sync are broadcast.
- Add Volume row regression after visiting PB2 and setting PB2 independent.
- Update persistence tests for split state 3 -> legacy state 2, split 4/5/6 ->
  legacy 3/4/5, and load clamp for `0x06`/`0xFF`.
- Add behavioral EEPROM boot test for persisted legacy Setup state 3 before
  PB2 discovery, trigger PB2 discovery, and prove visible page identity remaps
  to split Setup state 4.  Persisted legacy Diagnostics states 4/5 enter the
  WAITING path in this simulator before normal health-service rediscovery, so
  PB1/PB2 Diagnostics remap is covered by the runtime latch test and source
  mapping instead.  For save/load, add source-level coverage that split runtime
  states 3..6 are written back into legacy EEPROM state space 2..5, because the
  current simulator facade does not expose a direct CONTROL-EEPROM readback
  after runtime settings-save.
- Add raw-status mapping variants for `raw_status_cache` `0x00`, `0x01`,
  `0x02`, and `0x03`: PB1 list remains unchanged; PB2 row 0 is linked;
  concrete PB2 rows subtract one before mapping; max-row wrap/clamp works; no
  sentinel or out-of-range `cmd 0x06` data reaches MAIN.
- Add malformed PB2 row/index negative tests: corrupt selected row/max/index
  and PB2 intent, prove row 0 stays local, emitted input bytes are only
  `0x00..0x08`, and row 10+ cannot read past the source-label table.
- Add PB2 Auto Detect route test for the core wiring case: PB1 fixed Optical,
  PB2 concrete Auto Detect with PB2 SRC status seeded so AES/CAT is the live
  forwarded feed; assert PB1 remains Optical and PB2 converges to AES route/SRC
  state across navigation, full-sync, and wake.

### Work Unit 2 - Add A Linked PB2 Flag, Not A New EEPROM Byte

Reuse current bank-1 split RAM.  Add one flag bit in `input_split_flags`:

```asm
INPUT_SPLIT_FLAG_PB2_LINKED equ 0x02
```

Rules:

- Cold boot clears it with `input_split_flags`.
- On first PB2 latch, set `PB2_SEEN`, clear `SYNC_TARGET`, set `PB2_LINKED`,
  and optionally copy PB1 input into `input_intent_pb2` as hidden fallback.
- PB2 row 0 is represented by `PB2_LINKED`, not by a MAIN input byte.
- Never send a sentinel value to MAIN.
- Once PB2 selects a concrete source, clear `PB2_LINKED`; `input_intent_pb2`
  becomes authoritative.
- Selecting PB2 row 0 again sets `PB2_LINKED` and returns sync to broadcast.

Do not allocate CONTROL EEPROM.  If more RAM is needed, run RAM-bank safety and
document the byte owner before using it.

### Work Unit 3 - Insert PB2 Input At State 3 And Preserve Page Identity

Update the page dispatcher:

```text
legacy/PB2 unknown:
  0 Volume, 1 Preset, 2 Input, 3 Setup, 4 PB1 Diag, 5 PB2 Diag

split/PB2 seen:
  0 Volume, 1 Preset, 2 Input PB1, 3 Input PB2, 4 Setup,
  5 PB1 Diag, 6 PB2 Diag
```

Implementation shape:

- Keep `input_menu_max_state_to_w` returning 5 legacy and 6 split.
- In dispatch, state 3 branches to `input_screen` only when `PB2_SEEN`; else it
  remains Setup.
- State 4 branches to Setup in split mode, PB1 Diag in legacy mode.
- State 5 branches to PB1 Diag in split mode, PB2 Diag in legacy mode.
- State 6 exists only in split mode and renders PB2 Diag.
- In `input_split_latch_pb2_seen`, when setting `PB2_SEEN` for the first time,
  increment current `display_state_index` if it is 3, 4, or 5.  Do not remap
  0, 1, or 2.
- Update comments that still describe PB2 Input as appended state 6.

### Work Unit 4 - Fix Save/Load State Mapping

Replace the current "state >= 6 -> state 2" save-only clamp with explicit
split-aware mapping:

```text
save split state 3 -> EEPROM 2
save split state 4 -> EEPROM 3
save split state 5 -> EEPROM 4
save split state 6 -> EEPROM 5
legacy state 0..5 -> unchanged
any loaded EEPROM state >= 6 -> runtime state 2 before PB2 discovery
```

This preserves visible page identity after rediscovery without making split
state 3 a boot dependency.  Update structural tests around
`settings_save_eeprom` and `settings_load_eeprom`.

### Work Unit 5 - Teach Input Screen PB2 Row 0

Keep PB1 source list unchanged.  For PB2 only:

- If `PB2_LINKED` is set, stage `menu_option_selected_index_b0 = 0`.
- If PB2 is independent, map `input_intent_pb2` through the existing
  cmd06-to-menu-row helper, then add 1 to display row.
- PB2 max row is PB1 max + 1.
- PB2 row 0 renders `Same as PB1     ` from a new 16-byte ROM table entry.
- PB2 rows 1..N render existing source labels by subtracting 1 before table
  indexing and before `map_input_menu_index_to_cmd06_input_select`.
- On commit:
  - PB1 page: current behavior, commit to `input_select_cache_b0`.
  - PB2 row 0: set `PB2_LINKED`, copy PB1 input to hidden PB2 fallback if
    useful, and emit broadcast PB1 input.
  - PB2 row >0: clear `PB2_LINKED`, subtract 1, map to cmd06, commit to
    `input_intent_pb2`, and emit addressed PB2 input.

Clamp invalid PB2 row values defensively before label lookup and send mapping.
For x52 runtime malformed-row recovery, row 0 linked or a concrete Auto Detect
fallback are acceptable as long as no row 10+ indexes past a source-label table
and no invalid byte reaches MAIN.  Future EEPROM persistence has a stricter
rule: corrupt persisted state defaults to linked `Same as PB1`.

### Work Unit 6 - Broadcast While Linked, Address While Independent

Refactor `input_frame_send` minimally:

- Prefer reusing the existing `input_frame_send` broadcast body with the
  smallest branch change.  Add a new `input_frame_send_broadcast_pb1` helper
  only if listing evidence proves it is byte-neutral or smaller than branching
  through the current body.
- `input_frame_send` chooses:
  - no split: broadcast PB1;
  - split + `PB2_LINKED`: broadcast PB1;
  - split + independent: addressed PB1.
- `input_frame_send_current_input_page` chooses:
  - PB2 page + linked row 0: broadcast PB1;
  - PB2 page + independent: addressed PB2;
  - otherwise: `input_frame_send`.
- `input_frame_send_split_sync` chooses:
  - no split or linked: broadcast PB1;
  - independent: current alternating addressed PB1/PB2 behavior.

Retain `tx_ring_reserve_3` atomicity and only toggle `SYNC_TARGET` after a
successful addressed frame.  Saturation must not emit partial frames or starve
either PB.

Update `tests/sim/test_v173_atomic_3byte_frame.py` rather than duplicating
structural sender checks elsewhere.  Extend it with behavioral near-saturation
coverage for legacy broadcast, linked broadcast, PB1 addressed, PB2 addressed,
and independent full-sync.  On failed reserve, assert no partial frame bytes
and no `SYNC_TARGET` advance.

### Work Unit 7 - Volume Source Row Is PB1-Only

Find the Volume source-label render path and make it stage from PB1 intent
(`input_select_cache_b0`) every time the Volume page draws.  It must not reuse
`rx_ring_staging_b0` left behind by PB2 Input, PB2 intent, or ambiguous
`BF/06`.

Add a test:

1. PB1 Optical.
2. PB2 AES independent.
3. Navigate to PB2 Input and back to Volume.
4. Assert Volume row 1 is `Optical         ` or the PB1-equivalent label, never
   `AES             `.

### Work Unit 8 - Semantic Health/Suffix Page Classification

Replace numeric "state < 4" assumptions with semantic page classification:

- Health service runs on Volume, Preset, Input PB1, PB2 Input, and Setup.
  In split mode this includes state 4 Setup.  Remove stale state-6 PB2 Input
  special cases.
- Row-2 health suffix patching applies to Volume, legacy Input / split Input
  PB1, and Setup.  It must not patch PB2 Input because the row-0
  `Input PB2 old/lost` title owns that health display.  Preserve the existing
  BL Timeout editor skip for Setup.
- `input_screen_write_title` must use state 3 as PB2 when split, and update
  `Input PB2` -> `old` -> `lost` from `v171_health_age_pb2`.
- Diagnostics traffic remains suppressed on PB2 Input and split Setup.
  Health frames must continue.  Existing non-diagnostic maintenance traffic
  such as mute self-heal remains governed by existing contracts; tests should
  forbid `0x21/0x22` Diagnostics frames, not all non-health traffic.
- Add simulator assertions for PB2 Input stale/lost title redraw and split
  Setup stale/lost suffix plus health aging/poll behavior.

### Work Unit 9 - Update Operator/Hardware Docs

Historical scope note: x52 also tightened CONTROL flash wrapper path handling
so live flashing cannot accidentally use the wrong MAIN HID relay.  Treat that
as operational safety cleanup recorded with this release, not as part of the
multi-PB runtime feature itself.

Update `README.md`, `docs/HARDWARE_TEST.md`,
`docs/REFACTORING_V34_V173_SPEC.md`, and any hardware-test comments that
describe the old appended state-6 PB2 Input flow or conflicting CONTROL flash
path guidance.

Required doc/test updates:

- Menu order: `Input PB1(2) -> Input PB2(3) -> Setup(4) -> PB1 Diag(5) ->
  PB2 Diag(6)`.
- PB2 default: `Same as PB1`.
- Linked mode: input changes and full-sync broadcast PB1 to all PBs.
- Independent mode: PB1/PB2 input changes are addressed.
- PB2 stale/lost title behavior.
- Optional hardware pass criteria: detect; identify MAINs with
  `identify-mains --require-left-right`; use explicit HID paths; capture LCD;
  verify per-MAIN `input_select`/`input_mirror`; capture SRC4382 diagnostics
  where applicable for PB1 Optical, PB2 Same, PB2 AES, and PB2 Auto Detect
  AES/CAT.
- CONTROL flashing rule consistency was handled as the x52 operational cleanup:
  CONTROL is flashed through a MAIN USB HID relay.  Identify and refresh the
  MAIN HID path that is physically connected to CONTROL, normally LEFT/PB1,
  after any MAIN USB re-enumeration.  Pass that relay MAIN path to
  `scripts/flash_control_safe.sh --path`.  If a future implementation proves a
  true independent CONTROL USB bootloader path exists, update
  `dlcp_control_flash.py` evidence and all three docs together.

Update `tests/hardware/test_live_state_transitions.py` navigation counts or
comments if they encode the old state numbers.  Hardware execution still
requires separate user approval.

### Work Unit 10 - Keep MAIN And Host Tools Unchanged

No multi-PB runtime changes should be made to:

- `src/dlcp_fw/asm/dlcp_main_v35.asm`
- `scripts/dlcp_src4382_diag.py`
- MAIN USB command handlers
- release flash scripts

The x52 `scripts/flash_control_safe.sh --path` enforcement was separate
operational cleanup.  Do not use it as precedent for adding unrelated tooling
changes to future multi-PB runtime work.

If implementation unexpectedly needs MAIN changes, stop and update this IMPL
plus review gate before coding them.

## Likely Files

Code:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `firmware/patched/releases/DLCP_Control_V1.73.hex` after release build

Tests:

- `tests/sim/test_v173_multi_pb_input_selection.py`
- `tests/sim/test_v173_atomic_3byte_frame.py`
- `tests/sim/test_v34_v173_compatibility.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- Possibly `tests/sim/test_v32_src4382_autodetect_polling.py` expectation
  updates only if an existing broadcast-front-panel test is intentionally
  split-aware.
- `tests/sim/test_ram_bank_safety.py` only if RAM target metadata changes.
- `tests/hardware/test_live_state_transitions.py` comments/navigation helpers
  if they encode the old appended PB2 Input state.

Docs:

- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`
- `README.md`
- `docs/HARDWARE_TEST.md`
- `docs/REFACTORING_V34_V173_SPEC.md`
- `AGENTS.md`, because canonical CONTROL flash commands changed to require
  explicit relay MAIN HID paths.

## Test Plan

Per-iteration focused red/green tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v173_multi_pb_input_selection.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v173_atomic_3byte_frame.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_compatibility.py
```

Route/audio-path adjacency:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py
```

Release and structural gates:

```bash
.venv_ep0/bin/python scripts/build_v173_release.py
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v35_v173_release_builders.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom
```

Add a canonical release fixture or release-smoke test after
`scripts/build_v173_release.py` that boots
`firmware/patched/releases/DLCP_Control_V1.73.hex` and reruns the split-input
behaviors that gate release.  Temp-assembled source tests are fine for fast
iteration, but release acceptance must include the exact canonical HEX.

Pre-release broad gate when focused tests are green:

```bash
.venv_ep0/bin/python -m pytest tests --collect-only -q
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
.venv_ep0/bin/python scripts/check_phase5_gate.py
.venv_ep0/bin/python scripts/check_gpsim_excision.py
```

Live hardware is not part of implementation acceptance unless separately
approved by the user.  If approved, use the updated `docs/HARDWARE_TEST.md`
role-safe flow: detect, identify PB1/PB2 with explicit HID paths, then set
PB1 Optical plus PB2 Same/AES/Auto Detect from the front panel, capture LCD
lines, read both MAINs by explicit HID path, and record expected
`input_select`/`input_mirror` plus SRC4382 diagnostic evidence where applicable.

## Deployment And Smoke Plan

No deployment is required for IMPL drafting.

For a future release:

1. Save rollback identity before building:

```bash
git rev-parse HEAD
git status --short
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex
```

If a previous known-good artifact is needed, restore it by exact git object or
saved artifact path before flashing; do not assume the mutable canonical path
still points at the old release after a build.

2. Build the exact candidate once:

```bash
.venv_ep0/bin/python scripts/build_v173_release.py
```

3. Hash before tests:

```bash
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
```

4. Run focused and broad gates above, including canonical-HEX split smoke,
   collect-only, RAM safety, and listing headroom margin.  Record the CONTROL
   post-build byte margin.
5. Hash again; any source/HEX change invalidates the gate.
6. Flash only with explicit user approval and current CONTROL-relay MAIN HID
   selection:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py detect
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
# Use the MAIN HID relay physically connected to CONTROL, normally LEFT/PB1.
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
CONTROL_RELAY_MAIN_HID="$LEFT_HID"
: "${CONTROL_RELAY_MAIN_HID:?set relay MAIN HID path}"
# Power-cycle CONTROL while holding UP+DOWN for ~6s to enter bootloader.
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex
```

Do not omit `--path` for live CONTROL flashing.  The chosen rule and evidence
must be consistent in `README.md`, `docs/HARDWARE_TEST.md`, and
`docs/REFACTORING_V34_V173_SPEC.md`.  The safe wrapper now enforces this for
live flashing: `--path` remains optional for static `--preflight-only`, but a
live flash without the relay MAIN HID path exits before USB writes.

No-deploy criteria:

- RAM-bank safety fails.
- Any focused split-input, compatibility, or SRC route test fails.
- CONTROL source/HEX changes after the release candidate hash.
- Live hardware PB1/PB2 role identity is ambiguous.

Rollback:

- Reflash the prior known-good `firmware/patched/releases/DLCP_Control_V1.73.hex`
  only after restoring it by exact git object or saved artifact/hash.
- Use the same refreshed CONTROL-relay MAIN HID path selection rule as
  deployment.
- MAIN V3.5 does not need rollback for this feature if MAIN remains untouched.
- Because x52 split input was runtime-only, cold boot clears PB2
  linked/independent state.  The x53 persistence follow-up stores only a
  sanitized PB2 input setting and keeps it pending until PB2 is rediscovered.

## Acceptance Criteria

- Legacy/single-PB/PB2-unknown Input page remains `Input:` and emits broadcast.
- Healthy two-PB chain discovers PB2 via health and inserts `Input PB2` at
  state 3 without PB2 Diagnostics visit.
- Split traversal order matches the source spec exactly.
- PB2 first discovery renders `Same as PB1` and uses broadcast input changes
  and full-sync.
- Linked-mode `BF/06` updates the single linked/PB1 intent and the next
  linked full-sync broadcasts that updated value.
- PB2 concrete source changes use addressed PB2 frames; PB1 changes use
  addressed PB1 frames only while independent.
- Relinking PB2 to `Same as PB1` restores broadcast behavior.
- Volume source row always reflects PB1 intent.
- Setup/PB1 Diag/PB2 Diag retain visible identity across PB2 latch and
  save/load mapping.
- PB2 Input stale/lost title updates while health frames continue and
  Diagnostics frames are absent.
- Split Setup keeps health polling and row-2 suffix behavior.
- Ambiguous `BF/06` cannot collapse independent PB1/PB2 intent.
- PB2 row 0/sentinel never reaches MAIN; malformed PB2 row/index is clamped.
- Raw-status variants `0x00..0x03` preserve PB1 mapping and PB2 row offset.
- Canonical `DLCP_Control_V1.73.hex` is tested after build before any flash.
- Focused tests, RAM-bank safety, release-builder tests, and broad simulator
  gate pass or any blocker is documented before release.

## Risks And Notes

- Code size pressure is real in CONTROL.  Prefer branch reshaping and small
  helpers over table-heavy abstractions.
- PB2 row 0 adds one 16-byte string plus logic.  Reuse existing source-label
  tables instead of duplicating PB2 source labels.
- Moving Setup to split state 4 affects any code that assumes Setup is always
  state 3.  Search every `display_state_index == 0x03` or `<4` check.
- The current `rx_ring_staging_b0` is shared by menu rendering, IR input
  shortcuts, and source mapping.  Volume PB1-only rendering should stage from
  PB1 explicitly to avoid latent shared-scratch display bugs.
- Existing uncommitted worktree changes must be preserved.  Commit only if the
  user asks, with focused pathspecs.

## Reviewer Findings And Iteration History

Initial 8-reviewer pass completed on 2026-06-21.

High/Medium dispositions incorporated:

- Simplicity/scope: reuse `tests/sim/test_v173_atomic_3byte_frame.py`; prefer
  smallest branch change over a new broadcast helper unless size-neutral.
- Correctness/contract: added split Setup health/suffix classification,
  linked-vs-independent `BF/06` semantics, PB2 Auto Detect route proof, and
  clarified non-diagnostic maintenance traffic on PB2 Input.
- Ops/tests/deploy: added split Setup health tests, canonical-HEX release
  smoke, reconciled CONTROL-through-MAIN-relay HID selection flow, listing
  headroom, rollback-before-build capture, and collect-only.
- UX/API-consumer: corrected source-spec requirement 22; added
  `docs/HARDWARE_TEST.md` updates and concrete hardware evidence requirements.
- Security/privacy: added saturation behavior tests and malformed PB2
  row/sentinel validation.
- Performance/reliability: added linked `BF/06` full-sync test and split Setup
  health/suffix gates.
- Data/migration compatibility: added behavioral EEPROM boot/rediscovery for
  persisted Setup state 3, runtime latch coverage for legacy states 3/4/5, and
  source-level save/load mapping coverage for split runtime states back to
  legacy EEPROM state space.
- Maintainability/observability: added baseline/worktree prerequisites,
  focused atomic and listing-margin gates, and hardware runbook scope.

Baseline final rerun status before the BUG-V173-MPB-PB2-DOWN-RAW addendum:

- Simplicity/scope: no High, Medium, or Low findings.
- Correctness/contract: no High, Medium, or Low findings.
- Ops/tests/deploy: no High, Medium, or Low findings.
- UX/API-consumer: no High, Medium, or Low findings.
- Security/privacy: no High, Medium, or Low findings.
- Performance/reliability: no High, Medium, or Low findings.
- Data/migration compatibility: no High, Medium, or Low findings.
- Maintainability/observability: no High, Medium, or Low findings.

Gate status: passed.  No unresolved High, Medium, or Low findings remain.

## Implementation Evidence

Implemented on 2026-06-21 against the incremental split-input V1.73 draft.

Actual files changed for this feature:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `tests/sim/test_v173_atomic_3byte_frame.py`
- `tests/sim/test_v172_v33_diag_identity.py`
- `tests/sim/test_v34_v173_field_repros_20260613.py`
- `README.md`
- `docs/HARDWARE_TEST.md`
- `docs/REFACTORING_V34_V173_SPEC.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`

Implementation summary:

- Added `INPUT_SPLIT_FLAG_PB2_LINKED` in CONTROL split RAM.
- On PB2 discovery, PB2 now defaults to `Same as PB1` and the visible page is
  remapped so legacy Setup/PB1 Diag/PB2 Diag keep their user-visible identity.
- Split two-PB menu order is now
  `Volume -> Preset -> Input PB1 -> Input PB2 -> Setup -> PB1 Diag -> PB2 Diag`.
- PB2 row 0 is local CONTROL state only; no sentinel input byte is sent to
  MAIN.
- Linked PB2 mode uses legacy broadcast `[B0,0x06,pb1]` for normal sends and
  full-sync. Independent PB1/PB2 mode uses addressed PB1/PB2 frames.
- `BF/06` remains accepted in legacy/linked mode and quarantined in
  independent split mode.
- Volume input text is staged from PB1 intent only.
- Split state save maps runtime states `3..6` back to legacy EEPROM states
  `2..5`; loaded invalid states clamp before PB2 discovery.
- Health/suffix classification was updated for split Setup and PB2 Input;
  Diagnostics traffic remains page-local.
- PB2 Auto Detect coverage now proves PB1 fixed Optical and PB2 Auto Detect
  routed to AES survive navigation, independent full-sync, host preset traffic,
  standby, and wake.
- Existing diagnostics tests were updated to locate PB1/PB2 Diagnostics by
  LCD title plus legacy/split state candidates, because V1.72 uses states
  `4/5` while V1.73 split mode uses `5/6`.

Build evidence:

```text
.venv_ep0/bin/python scripts/build_v173_release.py
release revision: 0x4B -> 0x4C

shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
bf4f2bb2b4a29d4c7ffa6542558be101a54067c214236c4e46e9a2a4e009ef8c  firmware/patched/releases/DLCP_Control_V1.73.hex
12a7985317257eb640cbabc3406548f60630b071fa64e96cb12b4dfb349ad28a  src/dlcp_fw/asm/dlcp_control_v173.asm
```

CONTROL size evidence from `src/dlcp_fw/asm/dlcp_control_v173.lst`:

```text
Program Memory Bytes Used: 15118
Program Memory Bytes Free: 17650
```

Canonical HEX smoke evidence:

```text
Chain.from_v171_v32(V173_CONTROL_HEX, V35_MAIN_HEX)
chunks=57
lcd=('Volume:-17.0dB A', 'Auto Detect     ')
```

Test evidence:

```text
.venv_ep0/bin/python -m pytest -q tests/sim/test_v173_atomic_3byte_frame.py tests/sim/test_v173_multi_pb_input_selection.py
32 passed in 213.31s (0:03:33)

.venv_ep0/bin/python -m pytest -q tests/sim/test_v172_v33_diag_identity.py tests/sim/test_v34_v173_field_repros_20260613.py
43 passed, 2 xfailed in 768.51s (0:12:48)

.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_v173_release_builders.py tests/sim/test_v34_v173_compatibility.py
15 passed in 128.94s

.venv_ep0/bin/python -m pytest -q tests/sim/test_v32_src4382_audio_path_regression.py
9 passed in 16.09s

.venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
RAM bank safety: OK (control-v173)

.venv_ep0/bin/python scripts/check_phase5_gate.py
P5.gate GREEN; P5.4 soak: 5 passed in 216.31s

.venv_ep0/bin/python scripts/check_gpsim_excision.py
gpsim retirement clean: no live references found

.venv_ep0/bin/python -m pytest --collect-only -q tests/sim
1900 tests collected in 0.62s

.venv_ep0/bin/python -m pytest -q tests/sim -n 16
1894 passed, 2 skipped, 4 xfailed, 7 warnings in 1396.56s (0:23:16)
```

During the first full simulator run, 13 stale diagnostics-navigation tests
failed because they hard-coded PB1/PB2 Diagnostics as states `4/5`.  The
firmware behavior was the requested split menu; the test helpers were corrected
to accept legacy `4/5` and split `5/6` only when the LCD title matches the
requested PB.  The focused diagnostics rerun and final full `tests/sim` rerun
above are green.

Deployment evidence:

- No live hardware flash was performed.
- No `scripts/flash_control_safe.sh` command was run.
- The release artifact is built and simulator-gated only.  Flashing still
  requires explicit operator approval and the MAIN HID relay path described in
  the deployment section.

---

# BUG-V173-MPB-PB2-DOWN-RAW Bugfix IMPL Addendum

Date: 2026-06-22
Status: Implemented and non-hardware gated.  The canonical V1.73 CONTROL
release was rebuilt as `rev 0x52 / build 20260622`; simulator invariants,
release-HEX regressions, and broad non-hardware gates are fixed.  Live hardware
field closure remains pending and must not be inferred from simulator evidence.
Source spec: `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
Scope: CONTROL V1.73 input-menu bounds fix, simulator regression, canonical
CONTROL rebuild/release gate.  No MAIN changes.

## Bug Summary

Live hardware report after flashing the current V1.73/V3.5 combo:

```text
1. Navigate to Input PB2.
2. Row 1 is Same as PB1.
3. Press DOWN.
4. CONTROL reboots.
```

Directed simulator evidence does not reproduce the reboot when
`raw_status_cache == 0x03`; that path moves from `Same as PB1` to
`Analogue 4` and emits `[B2,0x06,0x04]`.  The simulator does reproduce the
same bounds-class failure when `raw_status_cache` is out of range, for example
`0xFF`: DOWN from PB2 row 0 wraps to an inflated stale max and produces
`menu_option_selected_index == 0x27`, `menu_option_max_index == 0x44`, and a
garbage LCD row.  Real hardware can plausibly surface this same invalid table
walk as WDT/reset rather than a stable garbage row.

Original implementation state before this bugfix was intentionally red/open:
the regression was `xfail(strict=True)`, CONTROL had the unknown raw-status
fall-through and unguarded PB2 row/table paths described below, and no
canonical-HEX or live-hardware closure existed.  WU1-WU5 are now implemented
for simulator/release-artifact closure, with hardware smoke still pending
explicit operator approval.

## Required Docs Read

- `AGENTS.md`: canonical V1.73/V3.5 paths, build scripts, tests, and release
  artifact policy.
- `README.md`: current V3.5/V1.73 setup, simulator build, release-flash path,
  and operator commands.
- `CODING_STYLE.md`: CONTROL assembly style, fixed-address caution, and release
  builder verification expectations.
- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`: source behavior and field issue
  contract for PB2 `Same as PB1` + DOWN.
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`: implemented split-input baseline
  and release/test gates.
- `docs/SIMULATION.md`: rust simulator and Python `Chain` facade.
- `docs/TEST_SIMULATOR.md`: simulator test scope; use `AGENTS.md` for current
  gate breadth.
- `docs/REFACTORING_V34_V173_SPEC.md`: inherited V1.73 builder, RAM safety,
  listing/headroom, deployment, and hardware-role requirements.
- `docs/IMPL_REFACTORING_V34_V173.md`: inherited V1.73 release gate,
  compatibility, builder rollback, and size-check implementation pattern.
- `docs/HARDWARE_TEST.md`: explicit live-hardware approval and role-safe
  PB1/PB2 identification if hardware smoke is requested later.

Docs considered but not directly in scope: `docs/V16B_SOURCE_REWRITE_SPEC.md`
and SRC4382-specific docs do not change the planned patch because this work
does not alter the V1.6b source-port contract, MAIN firmware, SRC4382 routing,
or audio-path initialization.

## Pre-Bugfix Evidence

- Before this bugfix, `src/dlcp_fw/asm/dlcp_control_v173.asm`
  `input_screen__render_option_row` computed the source-list max from
  `raw_status_cache` at the then-current
  `input_screen__status_*_sets_limit` chain.  Known values map to max
  `0x05`, `0x06`, `0x07`, or `0x08`.
- The unknown-value branch after `input_screen__status_three_sets_limit` fell
  through to `input_screen__draw_option_and_service` without writing
  `menu_option_max_index_b0`.
- `input_screen_adjust_pb2_max_index` then increments the existing max for PB2
  so row 0 can be `Same as PB1`.  If the existing max is stale or foreign, PB2
  DOWN wraps to an invalid row.
- `input_screen_prepare_option_label` subtracts 1 for PB2 concrete rows and
  reuses the existing input-label table.  It has no final guard against a row
  beyond the source table.
- Before this bugfix, `map_input_menu_index_to_cmd06_input_select` and
  `map_cmd06_input_select_to_menu_index` also branch on `raw_status_cache`.
  Unknown raw values could fall through without producing the same
  full-input mapping implied by a display max of 8.
- `raw_status_cache` is documented in `src/dlcp_fw/asm/dlcp_control_ram.inc` as
  boot sentinel `0x80` until a `BF/05` status arrives, so invalid/unknown values
  are not only synthetic corruption inputs.
- Before this bugfix, the exact hardware path with normal
  `raw_status_cache == 0x03` was not a dedicated passing regression; existing
  valid-status coverage rendered the page but did not pin DOWN from PB2
  `Same as PB1`.
- The repro anchor is now
  `tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status`.
  It was originally a strict XFAIL.  Under pre-fix `--runxfail` it failed on
  `assert 39 <= 9`, proving the invalid selected row.  It is now passing
  coverage.
- Existing split-input tests assemble a temporary HEX from
  `src/dlcp_fw/asm/dlcp_control_v173.asm`.  A release-closure test must also
  boot the canonical `firmware/patched/releases/DLCP_Control_V1.73.hex`.

## Gap Analysis

Already covered:

- PB2 linked/default behavior.
- PB2 DOWN from row 0 under normal `raw_status_cache == 0x03` was observed in
  directed sim, but it is not yet pinned as a regression.
- Raw-status variants `0x00..0x03` for valid input-board states.
- Existing linked/independent PB1/PB2 routing and full-sync behavior.

Missing:

- Defensive clamp for unexpected `raw_status_cache` values before PB2 max-row
  increment.
- A single, consistent unknown-raw-status semantic across max-row calculation,
  menu-label selection, menu-index-to-`cmd 0x06`, and `cmd 0x06`-to-menu-index.
- Equivalent unknown-raw-status hardening or proof for IR input previous/next,
  because those shortcuts share raw-status limit logic and call the same
  menu-index-to-`cmd 0x06` mapper.
- Regression proving PB2 `Same as PB1` + DOWN cannot select or render any row
  outside the valid PB2 set.
- Regression for the exact user path under valid `raw_status_cache` values,
  including `0x03`, not only invalid-cache mitigation.
- Guard coverage for already-corrupt selected/max/staged row state before label
  lookup and before commit/send.
- Release-gate evidence that the fix is present in the canonical
  `DLCP_Control_V1.73.hex`, not only a temp-assembled test hex.
- CONTROL listing/headroom evidence after the app-code edit.
- Explicit status separation: simulator invariants can be fixed without
  claiming the live field reboot is closed.

## Proposed Implementation

### WU1 - Keep The Repro, Then Make It Red For The Firmware

This repro was kept as a strict XFAIL until the assembly fix landed, then
converted to passing coverage.  The pre-fix red evidence command was:

```bash
.venv_ep0/bin/python -m pytest --runxfail \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status -q
```

The expected pre-fix failure was `MENU_OPTION_SELECTED > 0x09`, not a Python
test harness error.

### WU2 - Normalize Unknown `raw_status_cache` To Full-Input Semantics

Treat unknown `raw_status_cache` values as the full-input status class
(`raw_status_cache == 0x03`) everywhere this menu contract uses raw status.
This includes display max, label selection, menu-index-to-`cmd 0x06`, and
`cmd 0x06`-to-menu-index mapping.

Required behavior:

```text
raw_status_cache 0 -> base max 5
raw_status_cache 1 -> base max 6
raw_status_cache 2 -> base max 7
raw_status_cache 3 -> base max 8
raw_status_cache other -> behave exactly like raw_status_cache 3
PB2 seen/state 3 -> final max = base max + 1, capped at 9
```

For unknown raw status, the full-input label-to-command mapping is:

```text
row 0 Auto Detect -> 0x00
row 1 S/PDIF      -> 0x05
row 2 USB Audio   -> 0x06
row 3 AES         -> 0x07
row 4 Optical     -> 0x08
row 5 Analogue 1  -> 0x01
row 6 Analogue 2  -> 0x02
row 7 Analogue 3  -> 0x03
row 8 Analogue 4  -> 0x04
PB2 row 0 Same as PB1 is local-only and must never reach the wire
```

Implementation preference:

- Reuse the existing status chains where possible, but do not leave a display
  path and command path with different semantics.
- Prefer a small local normalize/check helper only if listing evidence shows it
  is no larger or clearly safer than duplicating a tiny fallback in each
  existing chain.
- Do not add a new table unless listing evidence proves it is smaller.
- Update `map_input_menu_index_to_cmd06_input_select` and
  `map_cmd06_input_select_to_menu_index` if needed so unknown raw status maps
  exactly like raw status `0x03`, not merely to any valid byte.
- Do not alter MAIN `cmd 0x06` handling.

### WU3 - Clamp Rows Before Label Lookup And Before Commit/Send

The render path currently prepares the label before recomputing max, so a max
clamp alone cannot protect an already-corrupt row.  Add a local guard that
ensures the row used for PB2 label lookup and the row used for commit/send are
inside the valid range before table indexing or `cmd 0x06` mapping.

Required behavior:

- If PB2 is seen and display state is `Input PB2`, row 0 remains `Same as PB1`.
- PB2 concrete rows must be clamped to the valid range before decrementing to
  the shared source-label/menu-index space.
- If `menu_option_selected_index`, `menu_option_max_index`,
  `rx_ring_staging_b0`, or `input_intent_pb2` is already corrupt/out of range,
  the next render or DOWN action must land on a valid PB2 row, render valid LCD
  text, and send either no frame for `Same as PB1` re-linking or a valid exact
  `cmd 0x06` data byte.
- Do not remove DOWN wrap from PB2 row 0; the wrap is valid once the max row is
  trustworthy.

Implementation preference:

- Keep the guard close to the existing input-screen helpers so it is obvious
  which row is being protected.
- If reordering max calculation before label prep is smaller and clearer than a
  second clamp, use that approach, but retain tests proving both render and
  commit/send are guarded.

### WU4 - Convert The Repro To Passing Coverage And Add Boundary Cases

After the firmware fix, the implemented coverage does the following:

- Removes the strict XFAIL marker from
  `test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status`.
- Asserts clean PB2 `Same as PB1` + DOWN with unknown `raw_status_cache` values
  lands exactly on `Analogue 4` / `0x04` because unknown raw status uses
  full-input `0x03` semantics.  `MENU_OPTION_SELECTED <= 0x09`,
  `MENU_OPTION_MAX <= 0x09`, and the LCD label must be valid.
- Parametrizes the test over at least `0x04`, `0x7F`, `0x80`, and `0xFF`.
- Adds a non-XFAIL regression for the exact reported user path with valid
  `raw_status_cache == 0x03`: PB2 `Same as PB1`, DOWN, no reset/hang/garbage,
  selected/max `<= 0x09`, expected valid label, and exact emitted `cmd 0x06`
  data.  Prefer parametrizing valid `0x00..0x03`.
- Adds exact label-to-`cmd 0x06` assertions for every PB2 concrete row under
  invalid raw statuses `0x04`, `0x7F`, `0x80`, and `0xFF`; byte-range-only
  assertions are insufficient.
- Adds equivalent PB1/legacy Input coverage for invalid raw statuses, especially
  boot sentinel `0x80`, because the same helpers are shared before PB2 is seen.
- Adds malformed-state tests that pre-corrupt selected/max/staged row/PB2 intent
  to rows `>= 10`, then prove valid LCD text, selected/max bounds, exact valid
  `cmd 0x06` data, and no reset/hang.
- Adds a canonical-HEX fixture/test that imports `V173_CONTROL_HEX`, boots
  `firmware/patched/releases/DLCP_Control_V1.73.hex` after
  `scripts/build_v173_release.py`, and reruns the PB2 `Same as PB1` + DOWN
  regression against that exact artifact.  Parameterize it over normal full-input
  `raw_status_cache == 0x03` and invalid/boot-sentinel raw values including
  `0x80`.
- Adds IR input previous/next tests under invalid raw statuses, including boot
  sentinel `0x80`, proving the shortcut cannot select/send out-of-range values
  and uses the same full-input semantics as the menu paths.  If implementation
  chooses to defer IR, it must first add a proof test or source audit showing IR
  cannot hit the stale-limit/out-of-range class.
- Keeps the existing valid raw-status tests for `0x00..0x03` and the linked vs
  independent PB1/PB2 routing tests.

### WU5 - Release Build, Structural Gates, And Hardware Smoke Policy

Run focused tests first:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_pb2_same_as_pb1_down_preserves_valid_raw_status_limits \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_unknown_raw_status_pb2_exact_label_to_cmd06_mapping \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_malformed_pb2_state_recovers_to_active_max_commit \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_independent_pb2_corrupt_intent_defaults_to_valid_row \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_raw_status_sentinel_survives_bf06_and_menu_mapping \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_unknown_raw_status_legacy_pb1_uses_full_input_table \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_unknown_raw_status_ir_previous_next_use_full_input_table \
  tests/sim/test_v173_multi_pb_input_selection.py::test_pb2_input_raw_status_variants_keep_extra_same_as_pb1_row \
  tests/sim/test_v173_multi_pb_input_selection.py::test_independent_pb1_and_pb2_input_pages_emit_addressed_cmd06 \
  tests/sim/test_v173_multi_pb_input_selection.py::test_pb2_same_as_pb1_row_restores_linked_broadcast_mode
```

Then rebuild and gate the canonical release artifact:

```bash
git rev-parse HEAD
git status --short
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
.venv_ep0/bin/python scripts/build_v173_release.py
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
.venv_ep0/bin/python -m pytest tests --collect-only -q
.venv_ep0/bin/python -m pytest -q tests/sim/test_v173_multi_pb_input_selection.py
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_canonical_hex_pb2_same_as_pb1_down_raw_status_regression
.venv_ep0/bin/python -m pytest -q tests/sim/test_v173_atomic_3byte_frame.py
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom
.venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_compatibility.py
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
```

The two post-build SHA-256 captures must match.  If source or HEX changes after
the first post-build hash, rerun the release sequence from `build_v173_release.py`.
Record CONTROL listing/headroom evidence from the refactoring contract gate;
V1.73 must retain `free_object_words >= 64` / `byte_margin >= 128` before
`control_release_metadata` and bootloader/pin/config boundaries.  Also record
the pre/post app-code byte or object-word delta and justify any non-trivial
growth, any new helper, or any new table used for raw-status normalization.

Run the broader gate before publishing/flashing:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
.venv_ep0/bin/python scripts/check_phase5_gate.py
.venv_ep0/bin/python scripts/check_gpsim_excision.py
```

Live hardware validation remains approval-gated.  Simulator/test completion may
mark the invariant mitigation complete, but the live field reboot is not
field-closed until operator-approved smoke passes on the exact rebuilt release
HEX.

If hardware smoke is approved:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py detect
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# refresh/export LEFT_HID/RIGHT_HID from the latest identify output
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
CONTROL_RELAY_MAIN_HID="$LEFT_HID"
: "${CONTROL_RELAY_MAIN_HID:?set relay MAIN HID path}"
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex
# cold power-cycle CONTROL plus both MAINs, then re-identify
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
```

Refresh/export HID role paths from the latest identify output before each use.
Record only redacted/hash-only HID path identifiers in committed/shared docs.
Raw `hardware_state_test.py detect`, `identify-mains`, `dlcp_diag.py --json`,
`result.json`, `summary.json`, HID paths/serials, Flipper serial ports, camera
inventories, and `--show-path` JSON stay in ignored local artifacts or shell
variables unless explicit local troubleshooting requires them.  Shared evidence
must be sanitized into role labels plus hash-only identifiers.  Shared
photos/videos must be cropped to the LCD/front panel, stripped of EXIF or
metadata, and kept free of incidental room/operator content.

`--preflight-only` is static HEX/bootloader-integrity evidence only; it does
not prove HID path validity or CONTROL bootloader/relay connectivity.  Those
are proven by immediate role identification plus live ACK/CRC flash evidence.
No-flash runs are smoke-only unless an on-device app hash/readback proves the
exact rebuilt release image.  Field closure must flash/preflight the canonical
`firmware/patched/releases/DLCP_Control_V1.73.hex` in the approved run, cold
power-cycle, and re-identify before testing.

Hardware closure evidence must include:

- release HEX hash, CONTROL revision/build, and git HEAD/status;
- PB1/PB2 identity from role-safe `identify-mains --require-left-right`;
- LCD/photo/video evidence of `Input PB2 / Same as PB1`, DOWN, and CONTROL
  staying up on the exact expected PB2 row for the observed raw-status/source
  list class; for normal full-input `raw_status_cache == 0x03`, DOWN from
  `Same as PB1` must land on `Analogue 4`;
- PB1/PB2 observed input state after DOWN, using `input_select` /
  `input_mirror` RAM probe or SRC diagnostics, showing the exact expected
  command/input state; for normal full-input `raw_status_cache == 0x03`, PB2
  must receive/select `0x04`;
- PB1/PB2 diagnostics still healthy after the action.

Use a tracked evidence note or template such as
`artifacts/probes/multi_pb_input_persistence_evidence_TEMPLATE.md` for future
hardware runs.  The run-specific artifact should record the required fields
above plus explicit pass/fail for PB2 DOWN, audio-routing, and persistence
closure, with raw HID paths and EEPROM dumps kept local/redacted.

Without that hardware evidence, final status must say "simulator/release-gated,
not hardware-validated/field-closed".

## Implementation Evidence - BUG-V173-MPB-PB2-DOWN-RAW

Actual files changed for this bugfix:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `README.md` (release identity and operator workflow only; unrelated README
  SRC4382/Main-headroom edits were pre-existing dirty work in this workspace)
- `AGENTS.md` (current non-hardware-gated CONTROL release evidence)
- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`
- `docs/HARDWARE_TEST.md`
- `docs/REFACTORING_V34_V173_SPEC.md`

Firmware implementation:

- Added `input_raw_status_full_fallback_save` / `input_raw_status_restore`,
  which temporarily coerce unknown raw status to full-input semantics inside
  the legacy map helpers, then restore `raw_status_cache` so the BF/05 cache
  remains authoritative.
- Added explicit unknown-full fallback in IR input previous/next without
  mutating `raw_status_cache`.
- Added `input_screen_compute_menu_max` and current-max-aware
  `input_screen_clamp_staged_row`, so render and commit/send clamp to the
  active source-list max, including reduced valid raw-status classes `0x00..2`.
- Kept the existing render-loop raw-status limit chain local to
  `input_screen__render_option_row` instead of introducing another call in the
  hot LCD loop.  The helper is used by entry/commit clamp paths; the render
  chain remains semantically identical and is pinned by valid-status,
  unknown-status, malformed-row, and exact label-to-`cmd 0x06` tests.  This
  avoided a broader control-flow reshape in size-sensitive CONTROL code.
- Added PB2 targeted-send clamping so corrupt independent `input_intent_pb2`
  cannot emit out-of-range `cmd 0x06` bytes during full-sync or direct send.
- Defaulted invalid `cmd 0x06` intent-to-row mapping to Auto Detect, so corrupt
  independent PB2 intent cannot reuse stale staging.
- Preserved MAIN `cmd 0x06`; no MAIN code changed.
- Updated the `input_frame_send` source header to describe linked broadcast
  versus independent addressed behavior.

Regression tests added/updated:

- `test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status`
- `test_bug_v173_pb2_same_as_pb1_down_preserves_valid_raw_status_limits`
- `test_bug_v173_unknown_raw_status_pb2_exact_label_to_cmd06_mapping`
- `test_bug_v173_unknown_raw_status_legacy_pb1_uses_full_input_table`
- `test_bug_v173_malformed_pb2_state_recovers_to_active_max_commit`
- `test_bug_v173_independent_pb2_corrupt_intent_defaults_to_valid_row`
- `test_bug_v173_raw_status_sentinel_survives_bf06_and_menu_mapping`
- `test_bug_v173_unknown_raw_status_ir_previous_next_use_full_input_table`
- `test_bug_v173_split_ir_previous_next_keep_route_style_and_pb2_intent`
- `test_bug_v173_canonical_hex_pb2_same_as_pb1_down_raw_status_regression`
- `test_canonical_hex_split_menu_visible_behavior_regression`
- `test_pb2_full_sync_clamps_corrupt_intent_before_send`
- `test_bug_v173_canonical_hex_pb2_full_sync_clamps_corrupt_intent`
- `test_health_only_pb2_discovery_survives_wake_and_health_loss_route_style`
- `test_legacy_eeprom_display_state_rediscovery_preserves_visible_page`
- `test_independent_pb2_intent_is_runtime_only_across_por_reset`
- `test_bug_v173_bf08_ackstat_only_does_not_leave_sticky_lcd_fault`

Release/build evidence:

```text
pre-build SHA-256:
  firmware/patched/releases/DLCP_Control_V1.73.hex
    bf4f2bb2b4a29d4c7ffa6542558be101a54067c214236c4e46e9a2a4e009ef8c
  src/dlcp_fw/asm/dlcp_control_v173.asm
    2506374f172a3e6f267322f93b2c45c91c432166bf8371815b3064ce2b8610f4

.venv_ep0/bin/python scripts/build_v173_release.py
  built canonical V1.73 CONTROL release ... (release rev 0x4C -> 0x4D)

source changed after the 0x4D reviewer pass:
  pre-0x4E HEX SHA-256:
    a51e53d5e5d0cb8cc55dfd10eade1b97ebdbc37024cde8bb79389f1d53477ca1
  pre-0x4E source SHA-256:
    8f915da8e4462d6fe61c1461ec02332d8226f9d938115334088bc887060d91c

.venv_ep0/bin/python scripts/build_v173_release.py
  built canonical V1.73 CONTROL release ... (release rev 0x4D -> 0x4E)

comment/source-doc cleanup after the 0x4E focused run:
  pre-0x4F HEX SHA-256:
    011becdd2ba533ac4076e109c235a46c6b58f178d50045507e576647d9077f96
  pre-0x4F source SHA-256:
    2c25865dd4a233dddb5845e36aa59ba026eab0b15e2c69d2f625a58f3271c087

.venv_ep0/bin/python scripts/build_v173_release.py
  built canonical V1.73 CONTROL release ... (release rev 0x4E -> 0x4F)

reviewer-discovered send-boundary bug fixed after x4F:
  PB2 targeted full-sync now clamps corrupt independent input_intent_pb2 before
  it can emit cmd 0x06.

.venv_ep0/bin/python scripts/build_v173_release.py
  built canonical V1.73 CONTROL release ... (release rev 0x4F -> 0x50)

post-x50 SHA-256 (superseded before field use by x51):
  firmware/patched/releases/DLCP_Control_V1.73.hex
    0e51122a04a9db4fc1868aad14361181f9d839386a1c2cfd03688f14c12d9a25
  src/dlcp_fw/asm/dlcp_control_v173.asm
    da1e986d5bd152fecabc5b0ccd8fc9553b307a48dee676059cc978cb026d4501
  src/dlcp_fw/asm/dlcp_control_ram.inc
    bdd782125e0f78074c45e7889e849cd46cffe0a052246bca2f55cd82cfb55e18

post-x50 reviewer follow-up:
  x50 used 0x028/Common_RAM+40 as the raw-status fallback scratch.  Final
  reliability review found that 0x028 overlaps live IR inhibit/decode timer
  state in the IR input previous/next path.  x51 moves the fallback save to the
  existing v171_tx_enq_retry 0x02D scratch byte, used only across straight-line
  mapping code or inside the bounded TX enqueue helper.

.venv_ep0/bin/python scripts/build_v173_release.py
  built canonical V1.73 CONTROL release ... (release rev 0x50 -> 0x51)

post-x51 SHA-256:
  firmware/patched/releases/DLCP_Control_V1.73.hex
    9b7b4d9232ca84a25c7ab68940c3ca1aed50e051b1d980fc1fac5dd1e58ce71d
  src/dlcp_fw/asm/dlcp_control_v173.asm
    f5c2c4239b42773a6ef0d3423b7cba06dc5193c1d8481bc3873e79872f74843c
  src/dlcp_fw/asm/dlcp_control_ram.inc
    32444126a475b98f40b8ffdc7cf01adc621e95ae54bafde4bb9867272a3277e8

post-x51 CONTROL metadata:
  Firmware V1.73
  Rev x51 20260622
  control_release_metadata: 0x01 0x07 0x33 0x51, date 0x20 0x26 0x06 0x22
  git HEAD: e02c619
  scoped dirty status included README/docs plus CONTROL source/HEX/test paths;
  unrelated dirty files existed before this bugfix and were preserved.

post-x51 broad-gate follow-up:
  The full simulator gate exposed a stale LCD fault indicator, not a PB2 DOWN
  regression: ACKSTAT-only BF/08 payload 0x04 from MAIN could set CONTROL's
  sticky DSP_FAULT_BIT even though MAIN's persistent DSP fault bit 6 was clear.
  x52 stores the raw BF/08 payload for diagnostics but latches LCD "!" only for
  payload bit 6.  Payload 0x00 or 0x04 clears/does-not-set the sticky LCD fault.

.venv_ep0/bin/python scripts/build_v173_release.py
  built canonical V1.73 CONTROL release ... (release rev 0x51 -> 0x52)

post-x52 SHA-256:
  firmware/patched/releases/DLCP_Control_V1.73.hex
    66ab68c47d4737fb72b6a1232ea6cd34592fab407dba6515e5a5a97906f2e5f6
  src/dlcp_fw/asm/dlcp_control_v173.asm
    131d4e7a078cbfd3eb43a202b34cf3a93f15c2f3059bdb1f53ba05d0dcda6eed
  src/dlcp_fw/asm/dlcp_control_ram.inc
    67ec799d18c45634e0204ed38ce8d969ec13832196223f46711e3d90c3891943

post-x52 CONTROL metadata:
  Firmware V1.73
  Rev x52 20260622
  control_release_metadata: 0x01 0x07 0x33 0x52, date 0x20 0x26 0x06 0x22
```

Size/headroom evidence:

```text
temporary pre-bugfix assembly from the same dirty baseline:
  Program Memory Bytes Used: 15118
  Program Memory Bytes Free: 17650

post-fix canonical listing:
  Program Memory Bytes Used: 15290
  Program Memory Bytes Free: 17478
  low app-code last used word: 0x3287
  free byte gap before control_release_metadata 0x77B0: 17704 bytes
  free byte gap before bootloader start 0x7800: 17784 bytes
  threshold pass: both gaps exceed the 128-byte/64-word V1.73 listing floor
  growth rationale: +172 bytes versus the temporary pre-bugfix assembly buys
    non-mutating raw-status fallback, active max clamp, PB2 send-boundary
    clamping, and targeted comments/tests without adding lookup tables
  config bits remain at 0x300000
```

Test evidence:

```text
.venv_ep0/bin/python -m pytest tests --collect-only -q
  1959 tests collected in 0.59s

.venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
  RAM bank safety: OK (control-v173)

.venv_ep0/bin/python -m pytest \
  tests/sim/test_v171_layer1_bounded_tx.py::test_ram_inc_defines_v171_tx_saturate_count_at_correct_address \
  tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_bf08_ackstat_only_does_not_leave_sticky_lcd_fault \
  tests/sim/test_v34_preset_src_hole_field_bug.py::test_coalesced_target_during_apply_restarts_from_row0_correct_source \
  tests/sim/test_v34_preset_src_hole_field_bug.py::test_ir_b_to_a_under_locked_rxckr_hole_never_unmutes_wrong_pb2_coefficients \
  tests/sim/test_v34_preset_src_hole_field_bug.py::test_ir_b_to_a_phase_hit_without_src_hole_never_omits_pb2_tas59_write \
  -q
  6 passed in 187.87s

.venv_ep0/bin/python -m pytest \
  tests/sim/test_v173_multi_pb_input_selection.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v173_atomic_3byte_frame.py \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v34_v173_listing_size_gates_keep_refactoring_headroom \
  tests/sim/test_dlcp_control_flash_safety.py::test_safe_control_wrapper_defaults_to_v173_release \
  tests/sim/test_dlcp_control_flash_safety.py::test_safe_control_wrapper_requires_explicit_path_for_live_flash \
  tests/sim/test_dlcp_control_flash_safety.py::test_preflight_reports_v173_target_release \
  -q
  83 passed in 632.40s

.venv_ep0/bin/python -m pytest tests/hardware/test_live_state_transitions.py --collect-only -q
  19 tests collected in 0.03s

.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
  1934 passed, 2 skipped, 4 xfailed, 7 warnings in 1613.79s

.venv_ep0/bin/python scripts/check_phase5_gate.py
  P5.gate GREEN; P5.4 soak: 5 passed in 232.90s

.venv_ep0/bin/python scripts/check_gpsim_excision.py
  gpsim retirement clean: no live references found; scanned 31573 python files

final post-test SHA-256:
  firmware/patched/releases/DLCP_Control_V1.73.hex
    66ab68c47d4737fb72b6a1232ea6cd34592fab407dba6515e5a5a97906f2e5f6
  src/dlcp_fw/asm/dlcp_control_v173.asm
    131d4e7a078cbfd3eb43a202b34cf3a93f15c2f3059bdb1f53ba05d0dcda6eed
  src/dlcp_fw/asm/dlcp_control_ram.inc
    67ec799d18c45634e0204ed38ce8d969ec13832196223f46711e3d90c3891943

post-commit x52 provenance:
  git HEAD: 1fe8cae0d26075991f1d8039456e7dae145894a1
  scoped x52 implementation/release paths: clean in `git status --short`
  current docs-only follow-up paths:
    M docs/MULTI_PB_INPUT_SELECTION_IMPL.md
    M docs/MULTI_PB_INPUT_SELECTION_SPEC.md
    ?? docs/MULTI_PB_INPUT_SELECTION.md
    ?? docs/MULTI_PB_INPUT_SELECTION_PERSISTENCE_IMPL.md
```

No live hardware flash or smoke was performed in this pass.  The issue is
therefore simulator/release-gated, not hardware-validated, and not field-closed.

## Actual X52 Files

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `tests/sim/test_v173_atomic_3byte_frame.py`
- `tests/sim/test_dlcp_control_flash_safety.py`
- `tests/hardware/test_live_state_transitions.py`
- `scripts/flash_control_safe.sh`
- `README.md`
- `AGENTS.md`
- `docs/MULTI_PB_INPUT_SELECTION_SPEC.md`
- `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`
- `docs/HARDWARE_TEST.md`
- `docs/REFACTORING_V34_V173_SPEC.md`

## Acceptance Criteria

- PB2 `Same as PB1` + DOWN cannot reboot/hang/render garbage in simulator
  coverage for valid raw statuses `0x00..0x03` and unknown statuses including
  `0x04`, `0x7F`, `0x80`, and `0xFF`.
- For unknown `raw_status_cache`, display max, label selection,
  menu-index-to-`cmd 0x06`, and `cmd 0x06`-to-menu-index all behave like full
  input status `0x03`.
- `MENU_OPTION_MAX <= 0x09` and `MENU_OPTION_SELECTED <= 0x09` after PB2 DOWN
  and after malformed-state render/commit tests.
- LCD row 1 is one of the valid PB2 source labels; garbage table entries are
  never rendered.
- No emitted `cmd 0x06` carries a sentinel or out-of-range data byte, and each
  displayed concrete label maps to the exact expected byte.
- IR input previous/next under invalid/boot-sentinel raw status is hardened
  with the same full-input semantics and covered by the named regression tests.
- Existing valid raw-status behavior for `0x00..0x03` still passes.
- Existing linked broadcast and independent addressed behavior still passes.
- `check_ram_access_safety.py --target control-v173` passes after any assembly
  edit.
- CONTROL listing/headroom gate remains above the V1.73 floor.
- Canonical V1.73 release HEX is rebuilt and the bug regression is tested
  against that exact HEX for valid `0x03` and invalid/boot-sentinel raw values
  before any flash/publish.
- README current CONTROL rev/build/hash and the source-spec field-issue
  status are updated after the canonical rebuild, including explicit
  simulator/release-gated vs hardware-validated wording.
- The `input_frame_send` source header describes current linked broadcast vs
  independent targeted behavior.
- Hardware field closure is claimed only if the approval-gated smoke records the
  evidence listed above; otherwise status remains simulator/release-gated only.

## Risks And Constraints

- CONTROL flash size remains constrained; prefer a tiny branch/set fix over a
  new abstraction.
- The live report is a reboot while sim currently shows invalid menu state.
  Treat the sim repro as necessary but not sufficient hardware proof.
- Do not "fix" this by removing DOWN wrap from PB2 row 0; wrap behavior is
  useful and valid when the max row is clamped.
- Unknown `raw_status_cache` normalization can expose duplicated raw-status
  chains; fix the menu and IR input-selection chains required for this bug
  unless a source-level proof shows a path cannot hit the stale-limit class.
- Preserve all unrelated dirty worktree changes.

## Reviewer Findings And Iteration History - BUG-V173-MPB-PB2-DOWN-RAW

Initial 8-reviewer gate:

- Reviewers: Simplicity/scope, Correctness/contract, Ops/tests/deploy,
  UX/API-consumer, Security/privacy, Performance/reliability, Data/migration
  compatibility, Maintainability/observability.
- High/Medium themes:
  - canonical release HEX was not exercised by the bug regression;
  - max-row clamp alone did not define exact label-to-command behavior;
  - row/table guards were missing before label lookup and commit/send;
  - exact valid-status user path was not pinned as passing;
  - CONTROL listing/headroom evidence and pre/post release hashes were missing;
  - hardware closure wording overclaimed because sim does not reproduce the
    exact live reboot symptom;
  - inherited V1.73 release docs were missing from required reads.
- Disposition: all High/Medium findings addressed in this revised addendum by
  WU2-WU5, expanded required docs, exact canonical-HEX gate, full-input
  unknown-status mapping, malformed-row tests, headroom/hash gates, and
  simulator-vs-field-closure status split.
- Rerun disposition: data/UX rerun findings tightened the source spec and
  hardware closure contract.  `docs/MULTI_PB_INPUT_SELECTION_SPEC.md` now
  defines unknown/out-of-range raw status, including boot sentinel `0x80`, as
  full-input `0x03` semantics.  Hardware field closure now requires the exact
  post-DOWN label and PB2 input state/command evidence; weaker hardware evidence
  is smoke-only and must not be called field-closed.
- Final targeted pre-implementation rerun disposition: ops/deploy had no
  High/Medium findings.  Reliability findings about the then-current xfail,
  firmware fall-through, missing row guards, absent IR tests, and missing size
  evidence were accepted as red evidence for WU1-WU5.
- Post-implementation disposition: WU1-WU5 are implemented in source and the
  canonical V1.73 CONTROL release is rebuilt as `x52`.  The multi-PB file,
  canonical-HEX regressions, PB2 send-boundary clamp, split IR previous/next
  hardening, BF/08 ACKSTAT-only stale-indicator regression, compatibility,
  listing, RAM-safety, full simulator, Phase 5, and gpsim-excision gates passed.
  The remaining release blocker is live hardware field closure.  No unresolved
  High/Medium findings remain for the simulator/release IMPL.
- Resolved reviewer notes:
  - Raw HID paths, serials, `--show-path` JSON, and unredacted media are banned
    from committed/shared evidence; only role labels plus redacted/hash-only
    identifiers are allowed there.
  - IR source previous/next is hardened and covered by regression tests.
  - PB2 row-0 DOWN under unknown raw status lands exactly on `Analogue 4` /
    `0x04`; "any valid row" applies only to malformed-state recovery tests.
- Remaining Low / explicitly scoped limitations:
  - Persisted legacy Setup state `3` has behavioral boot/rediscovery coverage;
    persisted legacy Diagnostics states `4/5` enter WAITING in the current
    simulator path, so their migration is covered by runtime latch/source
    mapping evidence rather than a full behavioral boot assertion.
  - Split-state EEPROM save/load mapping is source-level structural evidence;
    the current CONTROL simulator does not expose a direct EEPROM readback
    facade for a stronger save/reboot/read assertion.
  - Health-loss plus standby/wake route-style behavior is covered; a true
    current-loop reconnect/WAITING recovery test is not claimed by the focused
    simulator gate.
  - New persistence docs are intent-to-add and uncommitted until the next
    intentional commit; no commit was requested in this pass.
- Release blockers outside simulator/release IMPL completion:
  - Live hardware field closure remains pending and must use the exact
    approval-gated x52 flash/smoke evidence above.
