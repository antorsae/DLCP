# IMPL_REFACTORING_V34_V173

Date: 2026-06-08
Status: Implemented and promoted to recommended release pair
Source spec: `docs/REFACTORING_V34_V173_SPEC.md`
Scope: implementation plan and ledger for MAIN V3.4 + CONTROL V1.73
refactoring release pair.

## Required Docs Read

- `AGENTS.md`: canonical layout, source/release artifact paths, tests,
  V3.4/V1.73 build scripts, and current verification snapshot.
- `README.md`: current recommended release pair, setup, simulator, flashing,
  validation, and no-warranty/recovery constraints.
- `docs/REFACTORING_V34_V173_SPEC.md`: source requirements for this IMPL.
- `docs/PRESET_FILENAME_LCD_SPEC.md`: Preset filename LCD protocol and the
  resolved row-0 blank/stuck re-entry bug.
- `docs/IMPL_PRESET_FILENAME_LCD.md`: reviewed implementation evidence for the
  filename LCD wave, including explicit rejection of row-0 full redraw as the
  primary fix shape.
- `docs/RAM_BANK_SAFETY_SPEC.md` and `docs/RAM_BANK_SAFETY_IMPL.md`: RAM
  manifest/checker contracts and current implemented guardrails.
- `docs/HARDWARE_TEST.md`: live hardware role-safe flashing and hardware
  acceptance policy.
- `docs/SIMULATION.md`: current rust/native simulator operating model, broad
  gates, and gpsim retirement constraints.
- `docs/TEST_SIMULATOR.md`: historical simulator framework doc; `AGENTS.md`,
  `README.md`, and `docs/SIMULATION.md` are more authoritative for current
  gates.
- `docs/V33_SIZE_OPTIMIZATION_PROGRESS.md`: current MAIN V3.3 optimized size
  baseline and measurement style.
- `docs/IMPL_V172_V33_DIAG_MAIN_IDENTITY.md`: source and test pattern for
  creating a successor paired MAIN/CONTROL release with diagnostics identity.
- `docs/V32_RELEASE.md` and `docs/V171_RELEASE.md`: previous accepted release
  runbooks and rollback pattern.
- `docs/V32_DIAG_TIER1_SPEC.md` and
  `docs/V171_V32_LINK_HEALTH_FRESHNESS_SPEC.md`: diagnostics/freshness
  compatibility contracts that V1.73/V3.4 must preserve.
- `docs/SIM_REWRITE_RUST_SPEC.md` and `docs/SIM_REWRITE_RUST_PROGRESS.md`:
  native simulator coverage expectations and phase gates.
- `docs/RELEASE_ARCHIVE.md`: release history update target after artifacts
  exist.

## Source Requirements

Goals:

- Create MAIN V3.4 and CONTROL V1.73 as the next source-assembled pair.
- Preserve all V3.3/V1.72 behavior unless a bug fix is explicitly tested.
- Replace lifecycle ambiguity and duplicated code with shared contracts.
- Avoid redraw/retry hacks for Preset LCD; make page ownership deterministic.
- Measure MAIN/CONTROL size, especially MAIN free bytes before `0x4C00`.
- Keep release tooling, RAM safety, tests, and docs consistent.

Non-goals:

- No live hardware flashing unless separately requested.
- No new feature protocol beyond release identity/versioning needed for V3.4
  and V1.73.
- No unrelated historical source cleanup.
- No macro-heavy RAM rewrite that hides size growth.

Explicit user decisions:

- This work targets MAIN V3.4 plus CONTROL V1.73.
- `v172_preset_row0_full_redraw`-style fixes are considered hacks and must not
  be the design center.

## Current Implementation Evidence

Release/path evidence:

- `src/dlcp_fw/paths.py` has `V34_MAIN_ASM`, `V34_MAIN_HEX`,
  `V173_CONTROL_ASM`, and `V173_CONTROL_HEX` alongside the previous
  V3.3/V1.72 constants.
- `scripts/build_v33_release.py` and `scripts/build_v172_release.py` are thin
  wrappers into `dlcp_fw.patch.build_v33_release` and
  `dlcp_fw.patch.build_v172_release`.
- `README.md` identifies recommended MAIN as V3.4 rev `0xAC` and CONTROL as
  V1.73 rev `0x47` build `20260611`.
- `src/dlcp_fw/sim/v30_symbols.py` has canonical listing/source fallback
  through V3.4.
- Native chain helpers are named around older pairs in places even when they
  accept explicit HEX overrides; V3.4/V1.73 tests must prove the new artifacts
  are actually loaded.

MAIN source evidence:

- `src/dlcp_fw/asm/dlcp_main_v33.asm` header still contains stale V3.2 build
  text and lineage comments even though it is V3.3.
- MAIN cold init clears broad RAM ranges and then hand-clears upper bank-2
  runtime state, but `preset_job_state_b2..preset_job_tbl_hi_b2` at
  `0x2DE..0x2E4` are not explicitly cleared by the hand block.
- `preset_job_service` treats any non-zero `preset_job_state_b2` as active and
  falls into state dispatch/cancel logic.
- Parser pass-through route/cmd/data forwarding calls `uart_tx_byte_blocking`
  directly, while filename replies rely on `chain_tx_emitted_b2` to avoid
  same-pass chain traffic.
- `cmd26_filename_query_handler` arms the foreground filename job and reuses
  `fname_tx_gap_lo/hi` as compare scratch before they become pacing counters.
- Filename persistence clears dirty bit 5 but the USB transaction gate bit 6 is
  cleared by later housekeeping, keeping preset selection gated longer than the
  actual persist path may require.
- Reconnect/preset cancellation already stops Timer3 and clears PIE2/PIR2
  timer state in key paths; the remaining risky contract is reconciling
  `preset_job_flags_b2`/`active_flags` forced-mute state with user-muted intent
  across reconnect, standby, and retry.
- `main_i2c_service_2100` routes a bounded START/SEN timeout into a
  PEN-specific recovery label.
- `i2c_wait_bus_idle` advertises recovery on timeout, but several callers
  continue into the same transaction after a recovered timeout.
- `preset_job_apply_i2c_recover` has its own recovery path that bypasses the
  common diagnostics/BF/08 observability path.

CONTROL source evidence:

- `display_loop_iteration` is a modal wait loop, while Diagnostics avoids it and
  duplicates a non-modal service subset.
- Preset filename logic already uses row-0 readiness gating through
  `v172_fname_row0_status_snap_b2.7`, but the bit/mask is not named as a
  lifecycle flag in the include.
- `v172_fname_deadline_service` has two duplicated 16-bit countdown paths:
  pending-response deadline and delayed-query wait.
- `rx_parser_entry` OERR recovery and reconnect soft-recover hand-copy the same
  EUSART/ring/parser reset sequence.
- Banked BF handlers exit through several local `movlb 0x00` tails instead of
  one shared parser continuation.
- Cold WAITING and reconnect WAITING duplicate button grace, parser-gap, and
  sentinel-clear reduce logic.
- `v172_diag_identity_invalidate_visible` clears both valid and seen masks,
  coupling visible stale/lost invalidation to retry epoch state.
- BF/08 clear-path comments claim `full_sync_lo/hi` are cleared, but the code
  currently clears bank-1 diagnostics reset timeout cells.
- CONTROL release identity is split across boot splash strings, flashed release
  metadata, EEPROM image bytes, and cold-init self-heal logic.

RAM/checker evidence:

- `src/dlcp_fw/asm/dlcp_main_ram.inc` and
  `src/dlcp_fw/asm/dlcp_control_ram.inc` contain generated `_bN`, `_op`, and
  `_phys` aliases, but still expose duplicate stock aliases and some active
  lifecycle cells with `stock_*` names.
- `src/dlcp_fw/analysis/ram_bank_safety.py` supports routine contracts, but
  source coverage is sparse relative to BSR-sensitive helpers.
- Pointer/range bases used by `lfsr` are not as fully modeled as scalar cells.

Test/deploy evidence:

- `README.md` records the current non-hardware release snapshot:
  V3.4/V1.73 FIELD-10 focused regressions passing, V3.4/V1.73 focused
  bug/regression set `95 passed, 3 xfailed`, full simulator gate
  `1655 passed, 2 skipped, 3 xfailed, 7 warnings`, and a 30-minute
  exploratory hunt with no unreconciled HIGH/MEDIUM safety finding.
- `docs/HARDWARE_TEST.md` requires `identify-mains --require-left-right`
  before flashing two MAINs and treats live hardware tests as skipped unless
  `--run-hardware` is passed.
- `docs/V33_SIZE_OPTIMIZATION_PROGRESS.md` contains multiple optimization-era
  V3.3 size rows and is useful for measurement style, not as a hard acceptance
  baseline.  V3.4 implementation must recompute a clean current V3.3 assembly
  baseline before judging growth.

## Gap Analysis

What exists:

- V3.4/V1.73 features and tests are implemented and currently verified, with
  V3.3/V1.72 retained as the previous supported rollback pair.
- RAM bank safety tooling exists and is integrated enough to catch many bank
  mistakes.
- Release builders update V3.4/V1.73 identity fields, run RAM-bank safety, and
  roll back on failure; previous V3.3/V1.72 builders remain available for
  rollback artifacts.
- Preset filename LCD tests already cover the immediate re-entry row-0 blank
  regression.

What is missing:

- New V3.4/V1.73 source, path, builder, release, and test wiring.
- A single release identity source for both new targets.
- Deterministic reset clearing for all volatile MAIN upper bank-2 job state.
- Shared MAIN chain TX arbitration for forwarded bytes and replies.
- Explicit MAIN filename job replacement/cancel policy.
- Explicit MAIN I2C timeout abort/retry contract.
- One CONTROL non-modal service tick used by modal page wrappers.
- Shared CONTROL parser/TX/reconnect lifecycle helpers.
- Named lifecycle bits/aliases for several CONTROL and MAIN state cells.
- Size and acceptance gates specific to V3.4/V1.73.

Stale or risky patterns:

- Preset LCD bugs can be hidden by sleeps, retries, or row redraw recovery.
- CONTROL page loops can continue writing after navigation state changes.
- Comments and code disagree in several lifecycle-sensitive places.
- Some "source simplification" could accidentally increase MAIN code size.

## Proposed Implementation

### WU0: Scaffold V3.4/V1.73 Pair

Create successor sources and artifacts:

- copy `dlcp_main_v33.asm` to `dlcp_main_v34.asm`;
- copy `dlcp_control_v172.asm` to `dlcp_control_v173.asm`;
- add `V34_MAIN_ASM`, `V34_MAIN_HEX`, `V173_CONTROL_ASM`, and
  `V173_CONTROL_HEX` to `src/dlcp_fw/paths.py`;
- add `main-v34` and `control-v173` target specs plus target-specific source
  maps to `src/dlcp_fw/asm/ram_bank_manifest.py`;
- update `src/dlcp_fw/sim/v30_symbols.py` so `V34_MAIN_HEX` resolves to
  `V34_MAIN_ASM.with_suffix(".lst")` for listing fallback;
- use the existing native simulator factory with explicit `control_hex_path`
  and `main_hex_path` overrides for V3.4/V1.73 tests.  Do not rename or remove
  existing simulator factories; at most add a backward-compatible alias or
  test-local helper if needed;
- add patch modules `src/dlcp_fw/patch/build_v34_release.py` and
  `src/dlcp_fw/patch/build_v173_release.py`;
- make those builders call `assert_targets_safe(["main-v34"])` and
  `assert_targets_safe(["control-v173"])` after assembly and before final HEX
  copy from the first scaffolded version;
- add wrappers `scripts/build_v34_release.py` and `scripts/build_v173_release.py`;
- add MAIN flasher module/wrapper by cloning the V3.3 wrapper with V3.4 paths;
- allow CONTROL safe flasher to accept explicit rollback HEX values and default
  to V1.73 after release-ready evidence approves promotion.

Tests:

- path constants resolve to canonical locations;
- builders can run in temp/rollback mode without touching V3.3/V1.72;
- simulator listing lookup proves V3.4/V1.73 artifacts are loaded, not silently
  mapped to V3.3/V1.72;
- RAM safety CLI choices include both old and new targets;
- builder rollback tests prove RAM-safety failure leaves ASM/LST/HEX unchanged;
- release archive/docs mention V3.4/V1.73 as the default only after the
  acceptance gate passes; before that point, they must describe it as a
  candidate.

### WU1: Centralize Release Identity

MAIN V3.4:

- define a structured source identity block for major `3`, minor `4`, and
  release rev;
- builder derives EEPROM tuple, boot migration literals, HID version label, and
  `cmd 0x25` identity reply nibbles from one `new_rev`;
- tests assert all identity fields agree with built HEX;
- builder/source tests fail on duplicate or stale executable V3.2/V3.3 identity
  literals outside whitelisted comments/history.

CONTROL V1.73:

- define one builder-owned identity tuple for major/minor/patch/rev/build date;
- update boot banner, release metadata, EEPROM image bytes, and cold-init
  self-heal logic consistently;
- tests assert banner and metadata match builder inputs;
- builder/source tests fail on duplicate or stale executable V1.72 identity
  literals outside whitelisted comments/history.

### WU2: MAIN Reset And Runtime State Lifecycle

Refactor cold/runtime clear:

- introduce a compact clear-span helper or table for volatile ranges;
- explicitly clear `preset_job_state_b2..preset_job_tbl_hi_b2`;
- explicitly clear filename job state, diagnostics volatile state, parser-gap,
  recovery, and SRC4382 debounce cells;
- keep reset-cause flags sequenced after volatile clears so reset diagnostics
  remain correct;
- clarify `sw_or_unknown` reset classification or add explicit `RCON.RI` test.
- add lifecycle metadata for the complete active V3.4 upper-bank runtime RAM
  region, including copied V3.3 cells: `volatile_cold_clear`,
  `runtime_preserve`, `eeprom_shadow`, `scratch`, `sfr_alias`, or `derived`;
- derive the cold-init clear test from that metadata and require
  `preserve_reason` for protected ranges, including baked filename RAM
  `0x2C0..0x2DD` and release/persisted settings.

Refactor reconnect cancellation:

- keep the existing Timer3/PIE2/PIR2 shutdown semantics covered;
- add one helper/variant for clearing preset job state and reconciling
  forced-mute versus user-mute intent;
- cancel any active filename reply job during reconnect cleanup before source
  RAM or preset state can change;
- preserve reconnect behavior that should not force immediate volume restore or
  unmute intentionally muted hardware.

Tests:

- static source test proving cold init clears every volatile cell in the
  manifest-owned upper bank-2 lifecycle set;
- negative lifecycle test proving a newly added volatile cell without a
  cold-clear decision fails;
- simulator reset test or source-structure test that stale `preset_job_state`
  cannot survive cold-entry;
- tests for Timer3 stopped state, `preset_job_flags_b2`, force-muted versus
  user-muted behavior, and volume restore after retry/reconnect;
- tests proving reconnect cleanup cancels active filename jobs and cannot
  resume a stale filename reply after reconnect/preset-state changes;
- existing reset-cause diagnostics tests continue to pass.

Size checkpoint:

- measure MAIN V3.4 after this work unit and record delta from V3.3 before
  continuing.

### WU3: MAIN Chain, Filename, And Preset Lifecycle

Chain TX:

- add a tiny `chain_tx_byte_blocking` or equivalent helper that sets
  `chain_tx_emitted_b2` before `uart_tx_byte_blocking`;
- route parser pass-through route/cmd/data forwarding through it;
- audit/status helpers that send BF frames must set the flag through one
  helper or one tested pattern.

Filename:

- define and implement `cmd 0x26` busy policy: CONTROL allocates a fresh wire
  query id for replacement while a transaction is pending; MAIN aborts/restarts
  only for a fresh wire id/route; any same-id duplicate is idempotent or ignored
  even if CONTROL's derived RAM/EEPROM source changed, because stale same-id
  frames are not distinguishable on the wire;
- add a CONTROL no-reuse invariant for the 5-bit generation field: do not reuse
  a wire id for the same route/slot until stale frames for that route/slot are
  expired or drained, unless a stronger wire epoch is added;
- restart from START after clearing state and pacing gap only for a fresh
  wire id/route replacement;
- CONTROL-side route/id checks reject stale frames from aborted jobs;
- have `preset_persist_filename`, `preset_load_filename`, and USB filename
  writers directly cancel `fn_job_state_b2`;
- split compare scratch from pacing countdown if practical, or rename the
  scratch use and keep the timing constant explicit;
- define `FNAME_TX_GAP_RELOAD` as a named constant/comment if two-byte pacing
  remains;
- define `filename_dirty_flags` bit5/bit6 begin/end semantics: bit5 tracks
  RAM-vs-EEPROM dirty state, bit6 tracks active USB/HFD filename write race
  protection; bit6 may clear as soon as a successful persist makes active
  RAM/EEPROM coherent, but must remain set while an active writer can still race
  preset selection.

Preset:

- remove or mark `preset_job_delay` reserved-free;
- factor forced-mute/user-mute reconciliation into a macro/helper if it reduces
  duplication without size growth;
- rename/comment `preset_job_commit_rearm` as a hold-timer rearm path that
  intentionally preserves forced-mute context.

Parser and command dispatch:

- add semantic aliases/helper comments for parser tail-byte ownership currently
  hidden behind `active_flags.bit6` / `stock_0BC`;
- add source tests or generated comments for the cumulative XOR dispatch chain
  so inserting V3.4 commands cannot silently break later command matching;
- keep any BF frame helper extraction size-gated: only accept it if
  byte-neutral/net-shrinking or if it removes a tested timing/BSR risk.

Tests:

- every MAIN chain sender is covered by `chain_tx_emitted` source checks;
- fresh-wire-id repeated `cmd 0x26` during START, LEN, char, and END phases
  restarts deterministically and cannot splice stale frames;
- same-id duplicates during START, LEN, char, and END phases do not restart and
  cannot validate as a separate replacement, including same-id/different-derived
  RAM-or-EEPROM-source cases;
- generation wraparound stale-burst tests prove a wrapped id is not reused for a
  route/slot until stale frames are expired or drained;
- measured native UART timestamps for `BF/2D..4E` filename frames fail if any
  frame start-to-start gap falls below the preserved 2 ms minimum;
- diagnostics identity/status interleaving while a filename job is active does
  not corrupt RX state, cause parser drift, or create retry storms;
- filename writers abort active filename replies;
- bit5/bit6 tests prove early safe bit6 clearing after successful persist and
  preserved race protection during active USB/HFD filename writes;
- parser-tail alias tests cover `active_flags.bit6` / `stock_0BC` ownership;
- cumulative XOR dispatch-chain test proves existing and new commands still
  dispatch to the intended handlers after V3.4 additions;
- structural protocol-range tests prove only filename emitters use `BF/2D..4E`,
  diagnostics identity stays `BF/4F..53`, and `cmd 0x25`/`cmd 0x26` dispatch
  constants remain pinned;
- preset A/B behavior and filename LCD tests pass.

Size checkpoint:

- measure MAIN V3.4 after this work unit; helpers that are not byte-neutral
  must be justified as bug fixes or replaced with smaller source patterns.

### WU4: MAIN I2C Recovery Contract

Fix or refactor:

- route START/SEN timeout in `main_i2c_service_2100` to the generic timeout
  path, not PEN-specific recovery;
- make `i2c_wait_bus_idle` timeout return carry/error that callers must handle;
- update callers so timeout recovery aborts/restarts rather than continuing an
  ambiguous transaction;
- create a source-side or test-side call-site inventory for every bounded I2C
  wait site, recording entry/exit BSR, WREG/STATUS/FSR/TBLPTR clobbers,
  timeout branch target, and correct post-timeout action;
- share common recovery observability for async preset apply with a retry same
  entry return mode;
- split `i2c_recover_flags` meanings into distinct bits.

Tests:

- static tests for SEN/PEN timeout labels;
- structural tests proving every wait-site branches on carry/timeout or is
  documented safe to continue;
- simulator fault tests proving bounded I2C timeout increments diagnostics and
  does not continue a corrupted transaction;
- async APPLY timeout tests proving BF/08 surfacing, diagnostics counters,
  non-overlapping `i2c_recover_flags` meanings, and same-entry retry behavior;
- existing SRC4382/TAS route and audio-path regression tests pass.

Size checkpoint:

- measure MAIN V3.4 after this work unit and preserve the call-site inventory
  in the IMPL evidence if any helper grows code.

### WU5: CONTROL Non-Modal Display And Preset LCD Lifecycle

Introduce:

- `control_foreground_service_tick` or equivalent one-pass service;
- document the final source order in a short code comment and pin it with a
  source test.  The intended order is parser/gap service, page
  entry/exit/reconnect reconciliation, Preset row0 readiness/title service,
  Preset row0 health/fault/preset-letter patch service, filename row service,
  diagnostics suffix service, then bounded LCD work;
- modal wrappers for old page loops that call the tick;
- shared page navigation/disconnect exit predicate;
- named masks for `v172_fname_row0_status_snap_b2`, especially row0-not-ready;
- shared countdown decrement primitive for filename pending/deferred query, only
  if byte-neutral/net-shrinking or needed to fix a tested divergence; otherwise
  preserve duplicated countdown paths with source tests proving identical
  decrement semantics and separate expiry actions;
- shared reset-and-query guard for "still on Preset and connected", only if it
  removes a concrete stale-query path; otherwise preserve duplicated predicates
  with source tests/comments;
- cache slot compare helper for A/B, only if byte-neutral/net-shrinking;
  otherwise preserve local snippets and test both slots.

CONTROL helper stop/go table:

| Candidate | Required contract | Current duplicate/risk | Decision rule |
| --- | --- | --- | --- |
| Modal page wrapper | every page gets one non-modal tick and shared exit checks | page loops diverge and Diagnostics has a separate service subset | Required; tests pin call order and navigation exits. |
| Filename countdown primitive | pending-response and delayed-query countdowns expire differently but decrement consistently | duplicated 16-bit countdown code | Required only if byte-neutral/net-shrinking or if tests show divergence; otherwise leave duplicated with source tests/comments proving identical decrement and separate expiry behavior. |
| Reset-and-query guard | query only while still on Preset and connected | repeated page/connection predicates | Required if it removes a concrete stale-query path; otherwise source-test current predicates. |
| Cache slot compare | same-slot cache reuse avoids fresh queries | A/B compare snippets can drift | Required if byte-neutral/net-shrinking; otherwise keep local snippets and test both slots. |
| Parser tail / UART recover / TX helpers | BSR-safe continuation and atomic 3-byte reservation | duplicated banked exits and soft-recover sequences | Required where current duplication has lifecycle divergence; optional DRY work stays duplicated with contracts unless byte-neutral/net-shrinking. |
| WAITING/reconnect helpers | shared sentinel/button/parser-gap reinit semantics | cold and reconnect WAITING bodies drift | Required only for known divergence; otherwise add source comments/tests around preserved duplication. |

Preserve:

- row-1 filename rendering remains incremental;
- same-slot cache reuse does not requery;
- row-0 readiness gates row-1 rendering;
- no whole-row redraw recovery helper is introduced as a fix.

Tests:

- immediate Preset re-entry no sampled row0 blank while row1 shows filename;
- dynamic DDRAM trace tests for immediate LEFT/RIGHT transitions across
  Preset/Input/Setup/Diagnostics;
- source tests proving preset letter writes are limited to columns 14/15 and
  row0 readiness cannot erase row1;
- V1.73 source/dynamic tests preserve the one-LCD-budget priority where Preset
  row0 health/fault/preset-letter patching runs before row1 filename rendering;
- A, B, A->B, B->A, A->B->A, B->A->B still show correct row0 and filename;
- Preset B -> next page -> standby -> wake -> back to Preset still shows
  Preset B and filename;
- query count remains zero on same-slot cache reuse.

Size checkpoint:

- measure CONTROL V1.73 after this work unit, including distance to
  `control_release_metadata` and bootloader/pin regions.

### WU6: CONTROL Parser, TX, WAITING, Reconnect, Diagnostics

Parser/TX:

- add `rx_parser_continue_bsr0` and use it for banked BF parser exits only if
  current exits have a concrete BSR divergence risk; otherwise source-test the
  existing exits and document preserved duplication;
- add `rx_parser_service_with_gap` wrapper only if byte-neutral/net-shrinking or
  needed to fix a tested parser-gap divergence; otherwise test the existing
  call sites;
- add UART soft-recover/ring-clear macro/helper with gap-timeout variant only if
  it removes a concrete lifecycle divergence; otherwise preserve duplicated
  code with comments/source tests;
- add atomic 3-byte staged frame helper only if it reduces duplicated
  reserve/enqueue code without disturbing carry contracts and is
  byte-neutral/net-shrinking.

WAITING/reconnect:

- share cold/reconnect button grace code, sentinel all-clear reduce code, and
  connected-state timer/full-sync reinit code only where a concrete divergence
  exists or the helper is byte-neutral/net-shrinking; otherwise preserve the
  duplicated code with source tests/comments.

Diagnostics/health:

- decouple identity visible invalidation from retry epoch;
- implement epoch behavior exactly: page entry/reconnect/source change may
  issue one query; timeout marks seen/no-retry until page re-entry or
  reconnect; stale/lost suppresses suffix without resetting epoch; issue pages
  suppress suffix without clearing valid cache; fresh visible replies update
  only the identity suffix;
- remove or use `v171_health_seen_mask`;
- factor reset-timeout give-up logic;
- fix BF/08 clear-path comment/code mismatch.

Settings/preset encoding:

- centralize preset byte decode/encode so `0x01` means B and `0x00`, `0xFF`,
  or invalid values mean A;
- use the same helper/map for boot restore and persist writers.

Tests:

- source structural tests for shared parser tails and wrappers;
- existing OERR, reconnect, waiting, diagnostics identity, and IR tests pass;
- tests for diagnostics identity timeout, stale/lost, fresh recovery while
  visible, issue-page suppression, and retry after page re-entry/reconnect;
- tests for preset byte encoding from EEPROM, live state, and settings persist;
- reconnect saturation must follow one required path: either preserve and
  document the current caveat with a test proving the documented behavior, or
  fix it with a persistent-saturation test proving RIGHT/LEFT operator reset
  escape remains reachable.

Size checkpoint:

- measure CONTROL V1.73 after this work unit, and reject helper extraction if it
  grows app code without removing duplicated lifecycle risk.

### WU7: RAM Bank Safety And Source Hygiene

Extend existing guardrails after the WU0 builder enforcement is already in
place:

- keep `main-v34` and `control-v173` target specs current while keeping
  `main-v33` and `control-v172` intact;
- add semantic aliases for active lifecycle `stock_*` cells used by V3.4/V1.73;
- model every V3.4/V1.73 `lfsr` pointer/range base with owner, length,
  lifecycle, and access policy, and generate/use range-base `_phys` aliases for
  RAM operands;
- expand `;@routine` contracts for BSR-sensitive helpers in both sources;
- reduce duplicate parser logic between manifest and checker where practical;
- keep generated `.inc` content validated against the manifest.

Tests:

- `scripts/check_ram_access_safety.py --target main-v33 --target control-v172 --target main-v34 --target control-v173`;
- rerun the WU0 builder rollback tests proving RAM safety failure leaves
  ASM/LST/HEX unchanged;
- negative checker tests for raw RAM operands, wrong `_phys`/`_op` use, and
  missing routine contracts;
- negative checker tests proving raw numeric RAM `lfsr` fails even when the
  range is modeled, plus positive coverage for generated `_phys` range-base
  aliases and whitelist coverage only for non-RAM/SFR bases;
- ensure V3.3/V1.72 checker targets still pass unless intentionally superseded.

### WU8: Tests, Size, Docs, And Release Gate

Focused commands:

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_preset_filename_lcd_spec.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v172_v33_diag_identity.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v172_v33_release_builders.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_release_builders.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_dlcp_v34_release_flash.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_refactoring_contracts.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_compatibility.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_i2c_recovery_contract.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_ram_bank_safety.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_firmware_version_label.py
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v33 --target control-v172 --target main-v34 --target control-v173
```

Add V3.4/V1.73-specific focused tests as new modules or parameterizations:

- `tests/sim/test_v34_v173_release_builders.py`;
- `tests/sim/test_v34_v173_refactoring_contracts.py`;
- `tests/sim/test_v34_v173_compatibility.py`;
- `tests/sim/test_v34_v173_i2c_recovery_contract.py`;
- `tests/sim/test_v34_v173_ram_bank_safety.py`;
- V3.4/V1.73 parameter rows in existing preset filename, diagnostics identity,
  SRC4382, reconnect, and release-flash tests where appropriate.

`tests/sim/test_v34_v173_compatibility.py` must explicitly cover:

- V1.73+V3.3 and V1.72+V3.4 filename behavior for `cmd 0x26`, cache reuse,
  re-entry, pacing/interleaving, and no regression from V3.3/V1.72;
- V1.73 old/pre-feature MAIN filename echo adversarial cases for bytes `0x2D`,
  `0x2E`, `0x2F`, and `0x4E` at frame positions 0/1/2 and synthetic
  START/LEN/END-looking streams, proving no false `VALID`, no stuck `ARMED`,
  and blank-row timeout behavior;
- V1.73+V3.2 diagnostics no-identity timeout and V1.71+V3.4 old-CONTROL
  behavior.

Broad gates:

```sh
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests --collect-only -q
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
PYTHONPATH=src .venv_ep0/bin/python scripts/check_phase5_gate.py
PYTHONPATH=src .venv_ep0/bin/python scripts/check_gpsim_excision.py
```

Run PyO3/cargo native-simulator build or Rust tests first when local changes
touch the native simulator crate or PyO3 facade.

Size gates:

- assemble current V3.3 cleanly and then assemble V3.4 without builder rev
  bumps for apples-to-apples measurement.  The clean V3.3 build is the baseline;
  do not use historical ledger rows as acceptance numbers;
- record `used_bytes_pre_preset_b`, `last_used_pre_preset_b`, and
  `free_bytes_before_0x4C00`;
- record the listing/object-word end address before `org 0x4C00`;
- require the current accepted MAIN listing-fit floor of at least 10 free bytes
  before `org 0x4C00`; the original `free_object_words >= 64` target was
  superseded by necessary FIELD-5/FIELD-10 safety fixes and tight MAIN space;
- keep the per-WU MAIN size checkpoints from WU2/WU3/WU4 in the final evidence;
- assemble V1.72 and V1.73 and record app-space extent plus metadata location;
- record the last app-code word and distance to `control_release_metadata` plus
  any bootloader/pin/config boundary, and reject overlap;
- require CONTROL `free_object_words >= 64` (`byte_margin >= 128`) between last
  app-code word and `control_release_metadata`, and separately before any
  bootloader/pin/config boundary;
- block unexplained MAIN growth and block any candidate below the numeric
  headroom margins.

Docs:

- update `AGENTS.md` with V3.4/V1.73 paths only when source/artifacts exist;
- update `README.md` recommended pair only after final acceptance;
- update `docs/RELEASE_ARCHIVE.md`;
- keep `docs/PRESET_FILENAME_LCD_SPEC.md` behavior unchanged unless tests prove
  a V1.73 lifecycle improvement needs wording.

## Likely Files

Code/source:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `src/dlcp_fw/asm/ram_bank_manifest.py`
- `src/dlcp_fw/analysis/ram_bank_safety.py`
- `src/dlcp_fw/sim/v30_symbols.py`
- `src/dlcp_fw/sim/dlcp_sim_native.py`
- `src/dlcp_fw/paths.py`
- `src/dlcp_fw/patch/build_v34_release.py`
- `src/dlcp_fw/patch/build_v173_release.py`
- `src/dlcp_fw/flash/dlcp_v34_release_flash.py`

Scripts/artifacts:

- `scripts/build_v34_release.py`
- `scripts/build_v173_release.py`
- `scripts/dlcp_v34_release_flash.py`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`

Tests:

- `tests/sim/test_v34_v173_release_builders.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `tests/sim/test_dlcp_v34_release_flash.py`
- `tests/sim/test_v34_v173_compatibility.py`
- `tests/sim/test_v34_v173_i2c_recovery_contract.py`
- `tests/sim/test_v34_v173_ram_bank_safety.py`
- existing V3.3/V1.72 tests parameterized for V3.4/V1.73 as needed
- `tests/hardware/test_live_state_transitions.py` only if live acceptance
  wording/fixtures need a candidate version parameter

Docs:

- `docs/REFACTORING_V34_V173_SPEC.md`
- `docs/IMPL_REFACTORING_V34_V173.md`
- `AGENTS.md`
- `README.md`
- `docs/RELEASE_ARCHIVE.md`
- possibly `docs/HARDWARE_TEST.md`

## Test Plan

Contract tests before implementation:

- assert V3.4/V1.73 paths/constants/builders resolve to canonical files;
- assert MAIN cold-init clear manifest covers all volatile job state, including
  `preset_job_*`;
- assert parser forwarders and local replies participate in `chain_tx_emitted`;
- assert CONTROL page loops call the shared non-modal display tick;
- assert BF/08 clear-path comment/code and aliases agree.

Focused behavioral tests:

- V3.4/V1.73 chain reaches Volume and Preset page in native chain;
- simulator fixture proves V3.4/V1.73 HEX/listing artifacts are loaded;
- Preset A/B filename matrix: A, B, A->B, B->A, A->B->A, B->A->B;
- Preset B -> next page -> STDBY -> WAKE -> Preset returns as B with filename;
- Diagnostics PB1/PB2 identity shows `v3.4 NNNN` with V1.73;
- V1.73 remains backward-compatible with V3.3/V3.2 identity/no-identity cases
  where existing V1.72 tests require compatibility;
- mixed-version matrix covers V1.73+V3.4, V1.73+V3.3, V1.72+V3.4,
  V1.73+V3.2 no-identity timeout, and V1.71+V3.4 old-control behavior;
- mixed-version filename cases cover `cmd 0x26`, cache reuse, Preset re-entry,
  measured pacing/interleaving, and old-MAIN echo adversarial streams;
- I2C fault injection tests for SEN/PEN and async preset apply recovery.

Static/tool tests:

- RAM bank checker for `main-v34` and `control-v173`;
- source contract tests for shared helpers;
- release builder rollback tests;
- V3.4 flash wrapper tests and CONTROL safe-flash explicit-hex/default tests;
- path and artifact tests;
- version label tests.

Broad tests:

- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests --collect-only -q`
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
- `PYTHONPATH=src .venv_ep0/bin/python scripts/check_phase5_gate.py`
- `PYTHONPATH=src .venv_ep0/bin/python scripts/check_gpsim_excision.py`

Hardware tests:

- not required for implementation acceptance unless user asks for live flash;
- if run, use role-safe flashing and record OCR/raw artifacts.

## Deployment And Smoke Plan

No deployment is required for implementation.  Runtime behavior changes are
firmware changes, but live flashing requires separate user approval.

If approved later:

1. Detect hardware and identify MAIN roles:
   ```sh
   PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py detect
   PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
   # Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
   ```
2. Flash MAINs by explicit role-derived HID path:
   ```sh
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$LEFT_HID" --left
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --path "$RIGHT_HID" --right
   PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
   # Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
   ```
3. Flash CONTROL V1.73 through the role-safe MAIN path:
   Before the live CONTROL flash, power-cycle CONTROL while holding UP+DOWN for
   about 6 seconds to enter bootloader.  Do not press SELECT.  Because this may
   re-enumerate MAIN HID paths, identify MAINs again and refresh/export
   `LEFT_HID` and `RIGHT_HID` immediately before `flash_control_safe.sh`.
   ```sh
   PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
   # Refresh/export LEFT_HID and RIGHT_HID from the latest bootloader identify output.
   scripts/flash_control_safe.sh --path "$LEFT_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex --preflight-only
   scripts/flash_control_safe.sh --path "$LEFT_HID" --hex firmware/patched/releases/DLCP_Control_V1.73.hex
   ```
4. Cold power-cycle CONTROL plus both MAINs, then re-identify and refresh paths:
   ```sh
   PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
   # Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
   ```
5. Run info/smoke probes:
   ```sh
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
   PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json --ch-map LEFT="$LEFT_HID" --ch-map RIGHT="$RIGHT_HID"
   ```
6. Before trusting Preset OCR, verify app-resident PB1/PB2 Diagnostics MAIN
   identity reports `v3.4 NNNN` from both MAINs.
7. Capture Preset A/B, Preset B -> next menu -> STDBY -> WAKE -> Preset, and
   Diagnostics PB1/PB2 LCD evidence with `scripts/hardware_lcd_probe.py` or
   an equivalent raw LCD/OCR artifact.
8. Save a hardware report under `artifacts/` containing commands, HID paths,
   routes, release identities, and capture filenames.

No-deploy criteria:

- role detection cannot identify both MAINs;
- simulator gate fails;
- RAM safety fails;
- MAIN size growth is unexplained;
- Preset LCD immediate re-entry bug recurs;
- release identity is inconsistent.

Rollback:

Reflash previous canonical V3.3/V1.72 artifacts by explicit HID path:

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v33_release_flash.py --path "$LEFT_HID" --left
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v33_release_flash.py --path "$RIGHT_HID" --right
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
# Power-cycle CONTROL while holding UP+DOWN for ~6s to enter bootloader; do not press SELECT.
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# Refresh/export LEFT_HID and RIGHT_HID from the latest bootloader identify output.
scripts/flash_control_safe.sh --path "$LEFT_HID" --hex firmware/patched/releases/DLCP_Control_V1.72.hex --preflight-only
scripts/flash_control_safe.sh --path "$LEFT_HID" --hex firmware/patched/releases/DLCP_Control_V1.72.hex
# Cold power-cycle CONTROL plus both MAINs, then refresh paths again.
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# Refresh/export LEFT_HID and RIGHT_HID from the latest identify output.
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json --ch-map LEFT="$LEFT_HID" --ch-map RIGHT="$RIGHT_HID"
```

Rollback CONTROL first if only CONTROL changed.

## Acceptance Criteria

- Review gate: 5 independent roles, no unresolved High/Medium findings.
- V3.4/V1.73 sources, builders, constants, wrappers, and release artifacts exist.
- V3.4/V1.73 simulator/listing wiring proves new artifacts are loaded.
- V3.4/V1.73 identity is internally consistent and builder-derived.
- No Preset LCD row-0 full redraw/retry workaround is introduced.
- MAIN `preset_job_*` cannot survive cold init as live random state.
- MAIN chain TX arbitration covers forwarded and locally generated frames.
- MAIN filename and preset job lifecycle has fresh-id replacement, same-id
  idempotence, measured 2 ms pacing, and cancellation policy under
  diagnostics/status interleaving.
- MAIN I2C timeout recovery has explicit abort/retry semantics.
- CONTROL page/display services have a shared non-modal tick.
- CONTROL diagnostics identity epoch, preset-byte decode, and row0/row1 LCD
  lifecycle contracts are tested.
- CONTROL parser/TX/reconnect duplicated lifecycle code is consolidated or
  explicitly left duplicated with measured size rationale.
- RAM bank safety passes for old and new targets and is enforced by V3.4/V1.73
  builders with rollback tests.
- Mixed-version deploy/rollback simulator matrix passes.
- Focused and full simulator gates pass.
- MAIN and CONTROL size deltas pass the numeric headroom gates and are recorded.
- Hardware deploy status is recorded as `not run` unless live flashing is
  separately approved and performed.

## Risks And Mitigations

- MAIN size growth: mitigate with per-WU size measurement and reject helpers
  that increase code without fixing a bug.
- CONTROL timing shifts: mitigate with native-chain LCD/timing tests and keep
  row-1 filename rendering incremental.
- Helper abstraction overreach: prefer source macros only when they preserve
  output size or make repeated error-prone code impossible to diverge.
- Release path churn: V3.4/V1.73 has passed promotion; keep V3.3/V1.72
  available only as the explicit rollback pair.
- Hardware risk: no live flash in this implementation unless separately
  approved.

## Reviewer Findings And Iteration History

Review roles:

1. Simplicity/scope reviewer
2. Correctness/contract reviewer
3. Ops/tests/deploy reviewer
4. Firmware lifecycle/RAM/size reviewer
5. UI/LCD/protocol compatibility reviewer

### Pass 1 Findings Addressed In Revision 1

High/Medium findings addressed:

- Added mixed-version deploy/rollback matrix for V1.73+V3.4, V1.73+V3.3,
  V1.72+V3.4, V1.73+V3.2 no-identity timeout, and V1.71+V3.4.
- Added V3.4/V1.73 simulator/listing wiring and tests proving new artifacts
  are loaded.
- Required `main-v34`/`control-v173` RAM safety targets, old+new regression,
  and builder-integrated `assert_targets_safe` rollback tests.
- Chose deterministic `cmd 0x26` replacement semantics and required stale-frame
  rejection plus diagnostics/status interleaving tests.  Revision 2 later
  refined this to fresh-id replacement plus same-id idempotence because same-id
  stale frames are not distinguishable on the current wire protocol.
- Required hard filename pacing and `chain_tx_emitted` participation for all
  reply producers.
- Added lifecycle metadata/cold-init manifest requirements for V3.4 RAM cells.
- Replaced vague I2C recovery wording with a call-site inventory and per-site
  timeout handling tests.
- Pinned CONTROL non-modal display tick ordering, row0 status masks, diagnostic
  identity epoch behavior, and centralized preset byte decoding.
- Expanded focused and broad test commands, including V3.4 flash wrapper tests,
  safe-control explicit-hex/default tests, current `tests/sim -n 16 -q`, phase
  gates, and gpsim excision gate.
- Added per-WU MAIN/CONTROL size checkpoints and CONTROL metadata/bootloader
  distance gates.
- Added live-smoke evidence requirements and explicit rollback evidence if
  hardware flashing is performed.

### Pass 2 Findings Addressed In Revision 2

High/Medium findings addressed:

- Removed simulator factory rename/API churn from WU0; V3.4/V1.73 tests use
  explicit HEX overrides with existing native simulator factories.
- Added a CONTROL helper stop/go table so optional DRY work is left duplicated
  with source tests/comments unless it is byte-neutral/net-shrinking or removes
  a concrete lifecycle divergence risk.
- Made live smoke and rollback commands role-safe with explicit `$LEFT_HID` and
  `$RIGHT_HID` paths plus `dlcp_diag.py --ch-map`.
- Replaced impossible same-id filename replacement with fresh-id replacement
  and same-id idempotence; added tests for both paths.
- Added filename bit5/bit6 transaction-gate tasks and tests.
- Made Preset row0 health/fault/preset-letter patching part of the row0 phase
  before row1 filename rendering.
- Added old/pre-feature MAIN filename echo adversarial tests and precise
  V1.73+V3.3 / V1.72+V3.4 filename compatibility tests.
- Pinned filename frame pacing to the preserved 2 ms start-to-start contract
  with native timestamp tests.
- Added async preset APPLY recovery observability tests for BF/08, diagnostics
  counters, non-overlapping flags, and same-entry retry.
- Replaced stale hardcoded V3.3 size numbers with a clean current V3.3
  reassembly baseline requirement.
- Moved builder-integrated RAM safety and rollback tests into WU0.
- Expanded V3.4 cold-init lifecycle metadata to the complete active upper-bank
  runtime RAM region, including copied V3.3 cells.

### Pass 3 Findings Addressed In Revision 3

High/Medium findings addressed:

- Made WU5/WU6 optional helper bullets match the stop/go table directly.
- Added numeric 64-object-word MAIN and CONTROL headroom gates.
- Made reconnect saturation a required preserve-and-test or fix-and-test gate.
- Reconciled the filename countdown primitive requirement with size discipline:
  shared primitive only if byte-neutral/net-shrinking or fixes divergence;
  otherwise duplicated paths require source tests.
- Tightened filename replacement to fresh wire id/route only; same-id duplicates
  are idempotent/ignored even if CONTROL's derived source changed.

### Pass 4 Findings Addressed In Revision 4

High/Medium findings addressed:

- Added MAIN M6 implementation work for parser tail-byte ownership aliases and
  cumulative XOR dispatch-chain protection.
- Added reconnect filename-job cancellation and tests.
- Relaxed CONTROL C3/C4 SPEC wording to match the size-aware helper policy:
  centralize where byte-neutral/net-shrinking or risk-reducing; otherwise keep
  duplicated code only with contracts/source tests.
- Added live CONTROL bootloader-entry and post-flash cold power-cycle steps for
  both V1.73 flash and V1.72 rollback.
- Required fresh `LEFT_HID`/`RIGHT_HID` capture after every `identify-mains`
  step before any CONTROL flash, smoke probe, or rollback command.

### Pass 5 Findings Addressed In Revision 5

High/Medium findings addressed:

- Added filename generation wraparound no-reuse/drain invariant and stale-burst
  tests.
- Added explicit V3.4/V1.73 structural protocol-range tests for `BF/2D..4E`,
  `BF/4F..53`, `cmd 0x25`, and `cmd 0x26`.
- Required bootloader power-cycle entry followed by immediate MAIN
  re-identify/path refresh before CONTROL flash and rollback.
- Closed the raw numeric RAM `lfsr` loophole by requiring generated `_phys`
  range-base aliases for all RAM `lfsr` operands.
- Defined size gates as current MAIN free-byte floor plus CONTROL
  `free_object_words >= 64` / `byte_margin >= 128`, with CONTROL measured from
  last app-code word to metadata/boundaries.

### Final Focused Clean Pass

Focused reviewers for correctness/protocol, ops/deploy, and RAM/size reported
no High/Medium findings after Revision 5.

Current gate summary:

- High findings: none
- Medium findings: none
- Low findings: non-blocking only
- Status: `Reviewed - ready for implementation`
