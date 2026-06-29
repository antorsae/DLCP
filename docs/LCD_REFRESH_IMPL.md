# LCD Refresh Budget Implementation Plan

Date: 2026-06-28
Status: Reviewed - ready for implementation
Source spec: `docs/LCD_REFRESH.md`
Scope: CONTROL V1.73 LCD refresh reduction on the existing V1.73/V3.5 chain.

## Source Requirements

Goals:

- Stable parked LCD pages should stay below the soft target of 20 visible
  HD44780 DDRAM data writes/s after settle.
- User-visible changes must still feel immediate. Do not slow the foreground
  service loop, button debounce, RX parser, IR dispatch, or health polling to
  meet the write budget.
- Preset row 0 col 15 must not intentionally render blank and later patch in
  `A`, `B`, or `!` when CONTROL already knows the final status.
- Keep the implementation minimal and robust. Prefer dirty-state and cached
  visible-state checks over periodic repaint.
- Add tests that expose the current excessive write rates and guard the future
  behavior.

Non-goals:

- No MAIN firmware changes.
- No LCD driver rewrite.
- No new menu model or general display framework.
- No hardware flash/deploy as part of this planning task.

Explicit user decisions:

- Use the initial minimal plan as the implementation direction.
- Use 4 reviewers/agents, focused on simplicity and tests.
- Treat `<20 writes/s` as a soft target, but make the tests enforce it for the
  fixed firmware unless evidence shows a specific page needs a documented
  exception.

## Required Docs Read

Primary implementation reading:

- `AGENTS.md`: canonical layout, current V1.73/V3.5 artifacts, build scripts,
  test inventory, hardware-test policy.
- `CODING_STYLE.md`: CONTROL assembly style, label/RAM alias conventions,
  verification expectations.
- `docs/LCD_REFRESH.md`: source spec and measured current write rates.
- `docs/PRESET_FILENAME_LCD_SPEC.md`: Preset row-0 lifecycle and filename
  rendering contracts.
- `docs/MULTI_PB_INPUT_SELECTION.md` and
  `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`: PB1/PB2 input ownership, RC5 input
  shortcut, routing, and persistence contracts.
- `docs/SIMULATION.md`: rust simulator facade and `Chain` APIs.
- Touched tests under `tests/sim/`, especially Preset filename, multi-PB input,
  Diagnostics, and refactoring contract tests.

Deployment-only context, if flashing is later approved:

- `README.md` deployment section: CONTROL flash path and bootloader/HID
  constraints.
- `docs/HARDWARE_TEST.md`: hardware tests are explicit `--run-hardware` and
  require live rig/env; not part of this implementation unless the operator
  approves a live gate.

## Current Implementation Evidence

CONTROL source:

- `src/dlcp_fw/asm/dlcp_control_v173.asm:v173_preset_row0_paint`
  currently writes `Preset` plus spaces through col 15, then calls
  `v172_preset_status_patch_service` twice to patch col 14/15. This allows a
  sampled blank col 15 during repeated row-0 repaint.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:v172_preset_filename_service`
  repaints Preset row 0 every 32 service passes via
  `v173_row0_reassert_div_b2.5`. This is the dominant Preset over-refresh.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:v172_preset_status_patch_service`
  already computes/caches row-0 health, preset, and DSP-fault status in
  `v172_fname_row0_status_snap`; this should be reused, not bypassed.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:v172_fname_row1_render_service`
  already renders row 1 incrementally, one character per service tick, when
  `FNAME_ROW_DIRTY` is set. Keep the immediate render-on-dirty behavior, but
  note that active filename scroll still contributes about 35 writes/s and
  needs a scroll-frame budget fix.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:v171_health_patch_suffix` writes four
  row-1 tail cells whenever `V171_HEALTH_FLAG_DISPLAY_DIRTY` is set, even when
  the computed suffix is unchanged.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:input_screen__state_still_active`
  branches back to full `input_screen` while parked on split Input PB2 if the
  health dirty flag is set. This causes repeated row-0 and row-1 redraws.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:v171_diag_loop` refreshes Diagnostics
  at a stable full-screen cadence tied to `V171_DIAG_POLL_RELOAD_LO/HI`.

CONTROL RAM:

- `src/dlcp_fw/asm/dlcp_control_ram.inc:v171_health_suffix_mask` is currently
  documented as LCD suffix scratch. It can likely become the persistent last
  rendered suffix mask if an existing safe scratch byte is used for the newly
  computed mask.
- `v172_fname_row0_status_snap` already stores the Preset row-0 status cache.
- `v173_row0_reassert_div` is only for the fast Preset belt; it can be deleted
  or repurposed only if the final code still has a justified low-rate use.
- Add at most one new CONTROL RAM byte for PB2 title health-class caching if no
  existing safe byte can be reused. Any alias change must pass
  `scripts/check_ram_access_safety.py --target control-v173`.

Tests:

- `tests/sim/test_preset_filename_lcd_spec.py` contains filename/Preset LCD
  helpers, `lcd_ddram_write_count` usage, row-0 no-blank contracts, and
  foreground IR/RX tolerance tests.
- `tests/sim/test_v34_v173_refactoring_contracts.py` structurally pins Preset
  row-0 readiness ordering and no full-redraw helper names.
- `tests/sim/test_v173_multi_pb_input_selection.py` covers split Input PB1/PB2
  menu behavior, PB1 `S/PDIF`, PB2 `AES`, and canonical persistence.
- `src/dlcp_fw/sim/dlcp_sim_native.py:Chain.inject_host_command` can inject
  host command `0x20` while parked on Preset for visible A/B coherence tests.
- The LCD simulator resets DDRAM write counters on LCD clear-display; budget
  tests must treat any counter reset inside a measured window as a failure.
- The native `Chain` facade supports `lcd_lines()`, `lcd_ddram_write_count`,
  button presses, IR injection, field-shaped input setup, and direct RAM reads.

Measured current rates from `docs/LCD_REFRESH.md`:

- Preset: about 3779 total writes/s; row0 col15 about 416 writes/s.
- Input PB2: about 2125 total writes/s.
- Volume/Input PB1/Setup: about 210-217 total writes/s from health suffix
  churn.
- PB1/PB2 Diag: about 25.6 total writes/s, slightly above target.
- BL Timeout editor: 0 writes/s.

## Gap Analysis

What exists:

- Good page-local ownership boundaries already exist.
- Preset row-0 status caching already exists.
- Filename row 1 is already incremental and should remain so.
- Diagnostics already avoid the severe high-rate behavior.

What is missing:

- A reusable sim assertion for parked-page LCD write budgets.
- A no-blank-suffix budget test that samples Preset row0 col15 during entry,
  A/B toggles, row0 self-heal, and filename scroll.
- Cached unchanged-suffix behavior for the top-level health suffix writer.
- Cached unchanged-health-class behavior for split Input PB2 title.
- Diagnostics unchanged-value LCD suppression sufficient to meet the same soft
  target without changing query cadence.
- Preset filename scroll throttling or sparse updates so long active filenames
  do not exceed the total budget after row0 repaint is fixed.

What is stale:

- Comments that justify high-rate Preset row0 reassert as invisible are now
  wrong: the write-rate test sampled transient blank suffix states.
- `v173_row0_reassert_div` as a fast belt conflicts with the new refresh
  budget.

## Proposed Implementation

### WU1: Add Red Tests First

Use source-built CONTROL test fixtures for development, not the stale canonical
release hex. The focused tests must assemble a temp hex from `V173_CONTROL_ASM`
and pair it with `V35_MAIN_HEX`. After `scripts/build_v173_release.py`
publishes the canonical artifact, run a smaller canonical-hex smoke.

Create `tests/sim/test_lcd_refresh_budget.py` for reusable helpers and parked
budget assertions. Add narrower behavioral tests to existing spec files when
that keeps ownership clearer:

- Preset filename behavior: `tests/sim/test_preset_filename_lcd_spec.py`
- PB1/PB2 input behavior: `tests/sim/test_v173_multi_pb_input_selection.py`
- Diagnostics behavior: `tests/sim/test_v171_layer5_diag_page.py` and
  `tests/sim/test_v171_v32_layer5_diag_chain.py`
- Structural lifecycle assertions:
  `tests/sim/test_v34_v173_refactoring_contracts.py`

Measurement constants:

- `ONE_SECOND_TICKS = 48_000_000`
- 1 second settle window before measurement
- 10 second parked measurement window
- visible DDRAM addresses are `0x00..0x0F` and `0x40..0x4F`
- `LCD_REFRESH_SOFT_LIMIT_WRITES_PER_SEC = 20.0`
- tests use strict `< LCD_REFRESH_SOFT_LIMIT_WRITES_PER_SEC`

Budget helper requirements:

- Use `lcd_ddram_write_count(addr)` deltas only for visible DDRAM cells.
- Require every measured cell's end counter to be `>=` its start counter.
  A counter reset during the window means an LCD clear occurred and is a
  budget failure, not a zero-write pass.
- Failure output must include row0, row1, total, row0 col15, row1 col15,
  start/end LCD text, sampled variants, and any counter-reset cells.
- Mark long parked-window tests `@pytest.mark.slow`; keep structural and
  event-response tests unmarked.

Required slow parked-budget tests:

1. `test_v173_lcd_refresh_budget_default_pages`
   - Boot chain, explicitly latch PB2 discovery, then use title-driven
     `wait_for_title` navigation rather than a hard-coded blind ring walk.
   - Measure Volume, Preset, Input PB1, Input PB2, Setup, PB1 Diag, PB2 Diag,
     and BL Timeout editor.

2. `test_v173_lcd_refresh_budget_field_pb1_spdif_pb2_aes`
   - Set PB1 to `S/PDIF` and PB2 to `AES`.
   - Measure Volume, Preset, Input PB1, Input PB2, Setup, and BL Timeout.

3. `test_v173_preset_long_filename_scroll_budget`
   - Use a long filename/capture path that forces active row1 scroll.
   - Assert the total parked Preset budget stays below 20 writes/s after the
     initial immediate filename paint has settled.

Required fast event/lifecycle tests:

- Preset row0 col15 is never blank while row0 starts with `Preset`, across
  entry, exit/re-entry, standby/wake while parked, explicit
  `FNAME_ROW0_NOT_READY` self-heal, IR A/B, front-panel A/B, and host command
  `0x20` A/B changes.
- Snappy tests must use low-level pin control or an existing helper that does
  not hide periodic repaint latency. Do not use a long `Chain.press()` settle
  window as proof of responsiveness.
- Host command `0x20` while parked on Preset updates the A/B suffix
  coherently within a small bounded tick budget.
- BF/08 DSP-fault nonzero/zero transitions while parked on Preset update col15
  `!`/`A`/`B` within the same bounded tick budget.
- Health suffix visible states transition healthy -> PB1 stale -> PB2 stale ->
  both stale -> healthy without stale suppression, and BL Timeout enter/exit
  does not lose a pending dirty suffix.
- Split Input PB2 title class transitions normal -> old -> lost -> normal;
  PB1 stale with PB2 nonzero uses the existing shared classification semantics;
  unchanged dirty clears without rewriting row1.
- Input-page tests cover LCD-facing behavior only: visible Input PB1/PB2 rows
  update promptly after local input edits and after any existing CONTROL-visible
  host/BF06 input update path. If V1.73 has no CONTROL-visible host input path,
  document that in the test/IMPL instead of inventing one. Existing multi-PB
  routing and persistence tests must still pass, but this LCD task should not
  add new routing/persistence assertions solely for coverage.

Targeted structural tests:

- Preset service must not contain the every-32-pass row0 reassert branch.
- Preset row0 paint must not write spaces into col14/col15 and rely on later
  steady-state patching.
- Health suffix patch must compare against a cached last-rendered state before
  LCD writes.
- Diagnostics LCD suppression must not change `V171_DIAG_POLL_RELOAD_*`.

Expected pre-fix result: budget tests fail on Preset, Input PB2, health-suffix
pages, Diagnostics, and long filename scroll. Event/lifecycle tests should
expose the transient Preset suffix blank and any hidden stale-state risk.

### WU2: Preset Row 0

Minimal code changes:

1. Do not add a new Preset status-computation helper unless the direct change
   fails. Reuse `v172_preset_status_patch_service` as the single owner of
   col14/col15 status computation.

2. Update `v173_preset_row0_paint`:
   - Write only columns 0-13 as `Preset` plus spaces.
   - Do not write a blank placeholder into col14 or col15.
   - Seed `v172_fname_row0_status_snap_b2` invalid.
   - Call `v172_preset_status_patch_service` twice immediately in the same
     bounded render sequence so col14 and col15 are coherent before the user can
     observe a steady-state row.
   - Preserve the existing readiness lifecycle from
     `docs/PRESET_FILENAME_LCD_SPEC.md`: `FNAME_ROW0_NOT_READY` clears only
     after row0 is coherent and the row1 entry blank/readiness gate has run.
     If the current clear site violates that ordering after the edit, move the
     clear to the page-entry wrapper or split status-paint from readiness clear.

3. Remove the fast every-32-pass reassert block from
   `v172_preset_filename_service`.
   - Keep the explicit `FNAME_ROW0_NOT_READY` self-heal path.
   - Do not add sleeps.
   - If tests prove a post-wake blanking belt is still needed, add a one-shot
     invalidation/repaint on the specific overlay/lifecycle path, never a
     free-running repaint.

4. Update comments and structural tests that currently describe or require the
   fast belt and readiness ordering.

Expected result:

- Preset parked row0 becomes quiet.
- Row0 col15 never blanks as a known-status placeholder.
- Filename row1 still renders incrementally.

### WU3: Shared Health Suffix

Minimal code changes:

1. Treat `v171_health_suffix_mask_b1` as the last rendered suffix mask. Do not
   add a new RAM byte for this unless source inspection proves it is necessary.
   Reserve new RAM only for the PB2 title-class cache if no existing byte is
   safe.
2. Compute the new suffix mask into an existing safe scratch byte in the same
   routine.
3. If the new mask equals the last rendered mask:
   - Clear `V171_HEALTH_FLAG_DISPLAY_DIRTY`.
   - Return without LCD writes.
4. If changed:
   - Store the new mask as last rendered.
   - Execute the existing four-cell suffix write.
   - Clear `V171_HEALTH_FLAG_DISPLAY_DIRTY`.
5. On page entries or row1 full paints, mark the suffix cache invalid (`0xFF`)
   or synchronously patch the suffix so the first visible suffix still paints
   promptly.
   - Include `input_screen__draw_option_and_service`.
   - Include `setup_screen`.
   - Include `menu_option_editor_wait_and_update` exit paths.
6. Suppressed pages/editor states must not clear a pending dirty health
   transition unless the suffix is not visible and the cache is explicitly
   invalidated for repaint on exit.
7. Keep BL Timeout editor suppression exactly as-is while inside the editor,
   but invalidate or repaint the suffix on exit.

Expected result:

- Volume/Input PB1/Setup stable pages drop from about 210 writes/s to near zero
  after the first suffix paint.
- A real health transition still updates immediately on the next foreground
  pass.

### WU4: Split Input PB2

Minimal code changes:

1. Add one cached PB2 title class byte if required:
   - `0 = normal`, `1 = old`, `2 = lost`, `0xFF = invalid`.
   - Place it through the existing CONTROL RAM alias process.
2. On Input PB2 page entry, `input_screen_write_title` writes the title and
   updates the cached class.
3. Compute the class through the existing `v171_health_diag_check_stale`
   semantics or the same equivalent logic already used by the current PB title
   writer. Do not compare only raw PB2 age; preserve PB1-stale/PB2-shared
   classification behavior.
4. In `input_screen__state_still_active`, replace the branch back to full
   `input_screen` on health dirty with a narrow helper:
   - If not split Input PB2, keep current behavior.
   - If split Input PB2 and health class unchanged, clear display dirty and
     return to the normal control path with no LCD writes.
   - If class changed, rewrite row0 title only, update cache, clear display
     dirty, and leave row1 untouched.
5. Preserve row1 option writes on actual UP/DOWN input changes.

Expected result:

- Input PB2 stable page drops from about 2125 writes/s to near zero after page
  entry.
- `Input PB2:`, `Input PB2 old`, and `Input PB2 lost` still update promptly
  when health class changes.

### WU5: Preset Filename Row1 Scroll

Preset row0 and suffix fixes are not enough because active filename scroll is
about 35 writes/s. Keep the first filename paint immediate, then reduce ongoing
scroll writes with the smallest change that passes tests:

- Preferred minimal option: slow only the scroll-frame dirty cadence by
  increasing the moving-scroll `FNAME_SCROLL_DIV_*` interval so a full
  16-character repaint is not requested more often than the budget permits.
  Endpoint hold constants can remain for user-visible rest/far pauses; they do
  not control the moving-scroll frame rate.
- Alternative if the cadence feels too sluggish: add sparse/diff row updates so
  only changed cells are written during scroll frames.

Do not slow `v172_fname_row1_render_service` once `FNAME_ROW_DIRTY` is set; a
new filename should still appear promptly. The budget applies after the initial
paint has settled and the page is parked with an actively moving long-name
scroll window, not only averaged across endpoint holds.

### WU6: Diagnostics Budget

Diagnostics is slightly above target and visually stable. Use the smallest
change that makes the budget pass:

- Required approach for this IMPL: skip full Diagnostics LCD writes when the
  computed line content is unchanged, if this can be done with existing cache
  bytes and a small helper.
- Do not change `V171_DIAG_POLL_RELOAD_LO` or `V171_DIAG_POLL_RELOAD_HI` as a
  shortcut. That changes query/reset/identity cadence, not just LCD refresh.

Do not change reset/runtime query semantics without rerunning the existing
Diagnostics tests.

### WU7: Build And Verification

After code changes:

0. Before publishing the release artifact, record rollback evidence for the
   current canonical CONTROL hex:

```bash
git rev-parse HEAD
git hash-object firmware/patched/releases/DLCP_Control_V1.73.hex
```

1. Run fast focused source-assembled tests, including unmarked tests from the
   new LCD budget file:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -m "not slow" \
  tests/sim/test_lcd_refresh_budget.py \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v173_multi_pb_input_selection.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v171_layer5_diag_page.py
```

2. Run the slow budget and existing slow diagnostics tests in parallel:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -m slow -n 16 \
  tests/sim/test_lcd_refresh_budget.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_page_cadence_is_not_fast_polling
```

3. Run RAM safety:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
```

4. Build canonical CONTROL only after tests pass:

```bash
.venv_ep0/bin/python scripts/build_v173_release.py
```

5. Run canonical-artifact smoke and release-adjacent tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_lcd_refresh_budget.py::test_v173_lcd_refresh_budget_default_pages \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_control_flash_safety.py \
  tests/sim/test_firmware_version_label.py
```

6. If time/blast radius warrants, run:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Likely Files

Code:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc` if one new RAM cache byte is needed

Tests:

- New: `tests/sim/test_lcd_refresh_budget.py`
- Existing updates likely:
  - `tests/sim/test_preset_filename_lcd_spec.py`
  - `tests/sim/test_v34_v173_refactoring_contracts.py`
  - `tests/sim/test_v173_multi_pb_input_selection.py`
  - `tests/sim/test_v171_layer5_diag_page.py`
  - `tests/sim/test_v171_v32_layer5_diag_chain.py`

Docs:

- `docs/LCD_REFRESH.md`: update measured post-fix rates.
- `docs/LCD_REFRESH_IMPL.md`: record implementation evidence.
- `AGENTS.md` only if files are moved/renamed; no move is planned.

Release artifacts, only after code/test pass:

- `firmware/patched/releases/DLCP_Control_V1.73.hex`

## Deployment And Smoke Plan

No deployment for this IMPL-writing task.

Future implementation changes runtime CONTROL behavior. After tests and
canonical build, deployment remains operator-approved only:

```bash
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh
```

With two visible MAINs, use the relay MAIN HID path:

```bash
export CONTROL_RELAY_MAIN_HID="$LEFT_HID"
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID"
```

Operator constraints before live flash:

- Identify visible MAIN HID paths before starting.
- If two MAINs are visible, pass the relay `--path` explicitly.
- Put CONTROL in the documented UP+DOWN bootloader mode.
- Refresh/re-read HID paths after flashing before any hardware smoke.
- Record the pre-build git object/hash from WU7 for rollback.

No-deploy criteria:

- Any focused sim budget or responsiveness test fails.
- RAM safety fails.
- CONTROL build fails or release metadata is inconsistent.
- Hardware is not connected or operator has not approved flashing.

Post-flash smoke, if later approved:

- Power-cycle CONTROL after flash.
- Navigate every LCD page and confirm no visible flicker/blank A-B suffix.
- Run the relevant hardware LCD/front-panel gates from `docs/HARDWARE_TEST.md`
  only with `--run-hardware` and required env.

Rollback:

- Reflash the previous known-good CONTROL V1.73 hex from the recorded git
  object or saved rollback artifact using
  `scripts/flash_control_safe.sh --hex <rollback-control.hex> --preflight-only`
  followed by the matching live flash command and `--path` if needed.
- MAIN V3.5 does not need rollback for this change.

## Acceptance Criteria

- New budget tests pass on canonical V1.73/V3.5.
- Every stable visible page is <20 visible DDRAM data writes/s after settle,
  including PB1 `S/PDIF` / PB2 `AES`.
- Preset row0 col15 never blanks while active preset/fault status is known.
- Page navigation, Preset A/B, Input PB1/PB2 selection, BL Timeout edits, IR
  preset shortcuts, host-triggered preset changes, CONTROL-visible host/BF06
  input changes, and BF/08 fault set/clear transitions remain responsive.
- Existing Preset filename, multi-PB input, Diagnostics, release-builder, and
  RAM-safety tests pass.
- `docs/LCD_REFRESH.md` contains post-fix measured rates.
- No hardware flash is claimed unless the approved flash and smoke evidence is
  recorded.

## Risks And Mitigations

- Risk: removing the Preset fast belt reopens the historical post-wake blank
  row0 issue.
  Mitigation: keep explicit invalidation/self-heal, add no-blank lifecycle tests
  for Preset entry/re-entry/standby-wake, and add only one-shot repaint if the
  tests prove it is needed.

- Risk: health suffix caching hides a real stale/lost transition.
  Mitigation: compare computed suffix mask, invalidate on page entry, and add a
  test that forces health mask transitions.

- Risk: Input PB2 cached class can desync from visible title.
  Mitigation: update cache only when title is written, invalidate on page entry,
  and test normal -> old -> lost -> normal transitions.

- Risk: Diagnostics unchanged-render suppression hides a real counter/version
  change.
  Mitigation: compare full rendered line content, preserve
  `V171_DIAG_POLL_RELOAD_*`, and rerun runtime/reset/identity Diagnostics
  tests plus OK -> old -> lost -> OK display tests.

- Risk: slowing active filename scroll makes long preset names feel stale.
  Mitigation: keep first filename paint immediate, change only ongoing scroll
  frame cadence or use sparse updates, and test both prompt initial paint and
  parked long-name write budget.

## Implementation Evidence

Final implementation date: 2026-06-28

Actual files changed:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `tests/sim/test_lcd_refresh_budget.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `docs/LCD_REFRESH.md`
- `docs/LCD_REFRESH_IMPL.md`

Actual implementation summary:

- Removed the fast Preset row-0 reassert loop from
  `v172_preset_filename_service`.
- Changed Preset row-0 paint to own cols `0..13` only, with the existing
  status patch service owning cols `14..15`.
- Preserved the Preset row0/readiness lifecycle by deferring
  `FNAME_ROW0_NOT_READY` clear until standalone self-heal or the row-1
  renderer is ready to start filename output.
- Added one-shot Preset LCD invalidation after the defensive LCD clear overlay.
- Reused `v171_health_suffix_mask` as the rendered shared-health suffix cache
  and added explicit suffix invalidation on full row-1 paints.
- Reused the retired row-0 reassert byte as `v173_input_pb2_title_class` and
  added `v173_input_option_row_cache` for Input page LCD caching.
- Narrowed split Input PB2 health-dirty handling to a title-class patch instead
  of full page redraw when the visible title class is unchanged.
- Suppressed unchanged BF/2x Diagnostics cache writes and only marked
  health/diag dirty when a fresh reply changes reachability state.
- Reflected MAIN/host cmd `0x20` preset echoes into CONTROL's local
  `PRESET_BIT` so the parked Preset A/B suffix updates without periodic row-0
  repaint.
- Increased the active moving filename scroll divider from `0x08` to `0x18`.
  Initial filename paint remains immediate; only ongoing scroll frames are
  slowed.

Exact tests run and results:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -m "not slow" \
  tests/sim/test_lcd_refresh_budget.py \
  tests/sim/test_v34_v173_refactoring_contracts.py::test_v173_preset_row0_readiness_gates_row1_filename_rendering \
  --maxfail=1
```

Result: `5 passed, 3 deselected in 11.73s`

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -m slow -n 16 \
  tests/sim/test_lcd_refresh_budget.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_page_cadence_is_not_fast_polling \
  --maxfail=1
```

Result: `4 passed in 84.06s`

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -m "not slow" \
  tests/sim/test_lcd_refresh_budget.py \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_v173_multi_pb_input_selection.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v171_layer5_diag_page.py \
  --maxfail=1
```

Result: `296 passed, 200 deselected, 1 xfailed in 111.32s`

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
```

Result: `RAM bank safety: OK (control-v173)`

Rollback evidence before canonical build:

```text
git rev-parse HEAD
17b59e97bc8c0d9307317cf661e04363933677c6

git hash-object firmware/patched/releases/DLCP_Control_V1.73.hex
82991246ae2c866eeade22ce7c2f53ebb84d3d19
```

Canonical build:

```bash
.venv_ep0/bin/python scripts/build_v173_release.py
```

Result:

```text
built canonical V1.73 CONTROL release: firmware/patched/releases/DLCP_Control_V1.73.hex (release rev 0x5B -> 0x5C)
```

Post-build CONTROL hex SHA-256:

```text
04223d7b6f677671431cef3fac6e1b39986b3f5041e95a7eab722a91c96cdb4f
```

Release-adjacent smoke:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_lcd_refresh_budget.py::test_v173_lcd_refresh_budget_default_pages \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_control_flash_safety.py \
  tests/sim/test_firmware_version_label.py
```

Result: `45 passed in 73.76s`

Post-fix measured LCD write rates on canonical CONTROL V1.73 rev `0x5C` plus
MAIN V3.5:

| Page | Row 0 writes/s | Row 1 writes/s | Total writes/s |
| --- | ---: | ---: | ---: |
| Volume | 1.0 | 2.0 | 3.0 |
| Preset | 0.0 | 19.2 | 19.2 |
| Input PB1 | 0.0 | 0.0 | 0.0 |
| Input PB2 | 0.0 | 0.0 | 0.0 |
| Setup | 1.6 | 2.0 | 3.6 |
| PB1 Diag | 1.6 | 1.6 | 3.2 |
| PB2 Diag | 1.6 | 1.6 | 3.2 |
| BL Timeout editor | 0.0 | 0.0 | 0.0 |
| Volume, PB1 S/PDIF | 1.0 | 2.0 | 3.0 |
| Preset, PB1 S/PDIF PB2 AES | 0.0 | 19.2 | 19.2 |
| Input PB1, S/PDIF | 0.0 | 0.0 | 0.0 |
| Input PB2, AES | 0.0 | 0.0 | 0.0 |
| Setup, PB1 S/PDIF PB2 AES | 3.2 | 4.0 | 7.2 |
| BL Timeout editor, field inputs | 0.0 | 0.0 | 0.0 |

Deploy/no-deploy evidence:

- Hardware was not flashed.
- The only published artifact change is the rebuilt canonical CONTROL hex.
- Live hardware smoke remains operator-approved only.

Remaining low-risk issues:

- Preset long-name scrolling is intentionally close to the soft target at
  `19.2 writes/s`. A future sparse/diff row-1 renderer would add more margin,
  but was avoided here to keep this fix minimal.
- No live hardware LCD observation was run in this implementation pass.

Final status: implemented and sim-verified for CONTROL V1.73 rev `0x5C`.

## Reviewer Findings And Iteration History

Review count requested: 4 reviewer agents.

Reviewer roles:

1. Simplicity/scope
2. Correctness/contract
3. Ops/tests/deploy
4. Performance/reliability

Initial 4-reviewer findings addressed in this revision:

- Removed Diagnostics cadence/reload fallback; required unchanged-content LCD
  suppression with `V171_DIAG_POLL_RELOAD_*` unchanged.
- Changed pre-release tests to source-assembled CONTROL temp hexes, with
  canonical artifact smoke only after `scripts/build_v173_release.py`.
- Preserved Preset row0/readiness lifecycle and removed the proposed new status
  helper as the default path.
- Added targeted tests for long filename scroll budget, host preset command,
  BF/08 fault transitions, low-latency event response, Preset
  standby/wake/self-heal, health suffix transitions, BL Timeout exit, PB2 title
  health classification, and LCD-facing input-page updates.
- Required monotonic DDRAM write counters so LCD clears cannot undercount a
  measurement window.
- Made the budget threshold strict `<20 writes/s`.

Final re-check status: all 4 reviewers reported no High/Medium findings.

Second re-check findings addressed:

- Narrowed multi-PB coverage to LCD-facing input-page behavior and retained
  existing routing/persistence tests rather than adding broad new assertions.
- Added unmarked `test_lcd_refresh_budget.py` coverage to the fast pre-build
  command and moved slow tests into the parallel slow gate.
- Clarified host/BF06 input visibility handling and BF/08 fault set/clear
  coverage.
- Corrected filename scroll mitigation to tune moving-scroll
  `FNAME_SCROLL_DIV_*` or use sparse/diff updates, not endpoint hold constants.
