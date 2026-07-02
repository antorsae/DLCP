# Fable Confirmed Bugs 2026-07-02 IMPL

Date: 2026-07-02
Status: Implemented - simulator gates passed
Source spec: `docs/FABLE_CONFIRMED_BUGS_20260702.md`
Scope: reproduce, regress, and surgically fix the confirmed Fable bug set only on current MAIN V3.5 and CONTROL V1.73.

## Source Requirements

Goals:

- Add deterministic regressions for every confirmed behavior bug before or alongside the fix.
- Prefer tests that fail on the old behavior. For ISR races, require structural proof plus an instruction-boundary reproduction attempt; if the simulator cannot express the interleaving, record the exact failed attempt and keep a synthetic consequence test.
- Keep fixes surgical and minimal.
- Change runtime firmware source only in:
  - `src/dlcp_fw/asm/dlcp_main_v35.asm`
  - `src/dlcp_fw/asm/dlcp_control_v173.asm`
- Do not edit shared CONTROL RAM include files for this pass. In particular, do not add a second owner for `0x02D` in `dlcp_control_ram.inc`.
- Rebuild only current canonical artifacts when their source changes:
  - `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
  - `firmware/patched/releases/DLCP_Control_V1.73.hex`
- Use canonical artifact tests for operator-flashed behavior.

Non-goals:

- No fixes to V3.4, V3.3, V1.72, V1.71, or stock sources.
- No simulator engine feature work unless an existing race regression cannot be attempted with `step_until_pc_hit`, SFR pokes, UART injection, and current facade helpers.
- No broad refactor of UART, wake, diagnostics, input routing, or release builders.
- No live hardware flashing unless separately requested.
- No cosmetic code cleanup. Only update comments immediately adjacent to changed behavior when stale comments would mislead future maintainers.

Explicit user decisions:

- Only V3.5 MAIN and V1.73 CONTROL matter for this pass.
- Reproduction/regression coverage matters as much as the fixes.
- Simplicity and "less is more" are preferred over generalized rewrites.

## Required Docs Read

- `AGENTS.md`: canonical paths, current V3.5/V1.73 release artifacts, build scripts, test inventory, and hardware markers.
- `README.md`: current release pair, CLI flash path, simulator gates, post-flash smoke commands, and explicit HID path rules.
- `CODING_STYLE.md`: assembly style, ISR/fixed-entry risk rules, comment rules, and verification expectations.
- `docs/FABLE_CONFIRMED_BUGS_20260702.md`: source report and required regressions.
- `docs/TEST_ROBUSTNESS_SPEC.md`: evidence standard, canonical artifact parity, stale-state/negative-proof rules.
- `docs/TEST_ROBUSTNESS_IMPL.md`: current canonical artifact metadata/evidence ledger and release-gate pattern.
- `docs/TEST_INCIDENTS.md`: incident evidence and sanitization policy.
- `docs/HARDWARE_TEST.md`: live-rig role gates, skip-by-default policy, release-specific revision/SHA references.
- `docs/SIMULATION.md`: Rust simulator facade capabilities and fidelity caveats.
- `docs/REFACTORING_V34_V173_SPEC.md`: V3.4/V1.73 lineage contracts inherited by V3.5/V1.73.

Current worktree note:

- `docs/FABLE_CONFIRMED_BUGS_20260702.md` is untracked from the current report work.
- Several unrelated proposal docs and `uv.lock` are also untracked. Preserve them.

## Current Implementation Evidence

MAIN V3.5:

- `src/dlcp_fw/asm/dlcp_main_v35.asm:1837` has `wake_request_handler`; the XOR/AND/XOR idiom writes `event_flags.bit2 := gate_was_closed`, so a duplicate wake against an already-open gate can clear a pending wake event.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:1863` has `standby_request_handler`; it preserves a pending event on duplicate standby. Use this as the minimal wake pattern.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2260` validates channel 6 source but `src/dlcp_fw/asm/dlcp_main_v35.asm:2266` writes `channel_5_source_config_b0`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2281` mirrors sanitized channel source RAM into source shadows after validation.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2007` handles `cmd 0x06`; the no-op check at `2018` uses `current_cmd_data | input_select`, suppressing only Auto Detect repeats.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2014` sends muted `cmd06` through the mute refresh path before the fixed-input commit.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2024` writes both `input_select_b0` and `input_select_mirror_b0`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2027` forces `applied_route_shadow_b0 = 0xFF`; repeated identical fixed input therefore re-runs route reconciliation.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7911` `rx_ring_read` does not mask interrupts while checking ring state, dereferencing `INDF2`, and incrementing `rx_ring_rd_b0`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7753` `uart_soft_recover_full` falls through to `uart_parser_resync`, which clears `rx_ring_rd_b0` and `rx_ring_wr_b0`.

CONTROL V1.73:

- `src/dlcp_fw/asm/dlcp_control_v173.asm:1367` documents V3.4+ 16-bit identity, but `1377` gates on minor exactly `0x04`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:800` ISR entry writes `(Common_RAM + 24)` / `0x018`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:7378` cold WAITING emits a poll that activates TX interrupts, then `7388..7403` uses the same `0x018` byte as the four-sentinel accumulator.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:3336` stages PB1 `cmd 0x06` data from `input_select_cache_b0`, so a premature WAITING exit with the `0x80` seed can later transmit an invalid route-shaped payload.
- `src/dlcp_fw/asm/dlcp_control_ram.inc:687` already provides `v171_tx_enq_retry_acc` / `_phys` aliases for access-bank byte `0x02D`. Reuse the existing symbol in V1.73 only; do not add a new RAM owner.

Existing test and facade evidence:

- `src/dlcp_fw/sim/dlcp_sim_native.py` exposes `from_v3x_main_only`, `from_v171_v32`, `inject_main_frames_fifo`, `inject_main_uart_rx_bytes`, `write_main_eeprom_byte`, `read_main_reg`, `write_main_reg`, `inject_control_rx_bytes`, `uart_tx_records_full`, and `step_until_pc_hit`.
- `tests/sim/test_v171_reconnect_wake.py` demonstrates forced OERR by SFR poke.
- `tests/sim/test_v32_src4382_autodetect_polling.py` contains fixed-input quieting and SRC4382 stats patterns.
- `tests/sim/test_v172_v33_diag_identity.py` has V1.73/V3.5 identity fixtures, `inject_control_rx_bytes` helpers, malformed-reply tests, exact LCD assertions, and PB1/PB2 page coverage.
- `tests/sim/test_v173_multi_pb_input_selection.py` has `cmd06` frame scanners, `_force_full_sync_input_step`, and canonical V1.73/V3.5 PB1/PB2 coverage.
- `tests/sim/test_v34_v173_refactoring_contracts.py::test_v35_chain_copy_tos_rewrite_masks_and_restores_prior_gie` is the preferred structural-test style for prior-`GIE` critical sections.
- `tests/sim/test_v35_v173_release_builders.py`, `tests/sim/test_dlcp_v35_release_flash.py`, `tests/sim/test_dlcp_main_flash.py`, `tests/sim/test_dlcp_control_flash_safety.py`, and `tests/sim/test_firmware_version_label.py` own current release-builder, flash-wrapper, static detector, and preflight coverage.

## Gap Analysis

Exists:

- The source report contains enough reproduction evidence to specify targeted tests.
- MAIN-only and CONTROL-chain simulator fixtures support direct state setup for non-race cases.
- Canonical artifact tests already exist for release metadata, flash wrappers, and diagnostics identity.
- Prior `chain_copy` work provides a tested pattern for narrow prior-`GIE` masking.

Missing:

- No V3.5 duplicate-wake idempotence regression and no mandatory full-chain V1.73/V3.5 wake guard.
- No V3.5 channel-6 boot-source sanitizer regression that checks EEPROM offset, primary RAM, and shadow RAM together.
- No V3.5 repeated fixed-input `cmd06` idempotence regression, and no full-chain V1.73 full-sync route-churn guard.
- No V3.5 `rx_ring_read` prior-`GIE` structural guard, cycle-bound guard, burst-drain smoke, or instruction-boundary race attempt.
- No V1.73 V3.4/V3.5 rev16 parser regression with nonzero high revision and canonical post-build coverage.
- No V1.73 cold-WAITING sentinel accumulator structural guard, instruction-boundary race attempt, or synthetic consequence proof for invalid `cmd06` payload leakage.

Stale or risky:

- `wake_request_handler` comments describe duplicate wake as no-op when it can cancel pending work.
- CONTROL identity comment says V3.4+ but code implements V3.4-only.
- CONTROL cold WAITING uses stock ISR scratch for new V1.72/V1.73 foreground predicate logic.
- Public docs contain current release revisions/SHA; any canonical rebuild must update them in the same change.

## Proposed Implementation

### WU0 - Safety Rails, Reproduction Discipline, And Artifact Snapshots

1. Capture pre-build state before any canonical builder runs:

```bash
git status --short
shasum -a 256 firmware/patched/releases/DLCP_Firmware_V3.5.hex firmware/patched/releases/DLCP_Control_V1.73.hex
shasum -a 256 src/dlcp_fw/asm/dlcp_main_v35.asm src/dlcp_fw/asm/dlcp_control_v173.asm
test ! -f src/dlcp_fw/asm/dlcp_main_v35.lst || shasum -a 256 src/dlcp_fw/asm/dlcp_main_v35.lst
test ! -f src/dlcp_fw/asm/dlcp_control_v173.lst || shasum -a 256 src/dlcp_fw/asm/dlcp_control_v173.lst
mkdir -p artifacts/reanalysis/fable_20260702_prebuild
cp firmware/patched/releases/DLCP_Firmware_V3.5.hex artifacts/reanalysis/fable_20260702_prebuild/
cp firmware/patched/releases/DLCP_Control_V1.73.hex artifacts/reanalysis/fable_20260702_prebuild/
cp src/dlcp_fw/asm/dlcp_main_v35.asm artifacts/reanalysis/fable_20260702_prebuild/
cp src/dlcp_fw/asm/dlcp_control_v173.asm artifacts/reanalysis/fable_20260702_prebuild/
test ! -f src/dlcp_fw/asm/dlcp_main_v35.lst || cp src/dlcp_fw/asm/dlcp_main_v35.lst artifacts/reanalysis/fable_20260702_prebuild/
test ! -f src/dlcp_fw/asm/dlcp_control_v173.lst || cp src/dlcp_fw/asm/dlcp_control_v173.lst artifacts/reanalysis/fable_20260702_prebuild/
```

2. Add focused regressions first and run the smallest relevant nodes against pre-fix source/canonical artifacts where practical.
3. For intermediate MAIN/CONTROL assembly checks, use temp/source-assembled fixtures. Do not run canonical builders repeatedly; each builder bumps metadata.
4. Rebuild each touched canonical artifact once after all fixes for that artifact are complete:
   - MAIN once after WU1/WU2/WU3/WU4 are complete.
   - CONTROL once after WU5/WU6 are complete.
5. If a canonical builder succeeds but later gates fail, restore only the touched source/artifact/listing byproducts from git or the prebuild backup; if listings were not backed up, delete and regenerate them before recording evidence. Never revert unrelated worktree files.
6. Record exact old-behavior failures, fixed-behavior passes, artifact revs, build date, and SHA-256 in this IMPL and `docs/FABLE_CONFIRMED_BUGS_20260702.md`.

### WU1 - MAIN Duplicate Wake Must Be Idempotent

Tests:

- Add `tests/sim/test_v35_duplicate_wake_idempotence.py`.
- Add `test_v35_duplicate_wake_frames_preserve_pending_wake_dispatch`.
  - Fixture: source-assembled V3.5 for pre-fix red evidence; canonical `V35_MAIN_HEX` after rebuild.
  - Stimulus: boot MAIN-only, force gate closed, clear `event_flags.bit2`, inject two contiguous `B0/03/01` frames, step through dispatcher.
  - Assertions: gate open, wake bring-up evidence such as `diag_b` advances, and no "gate open but bring-up skipped" state remains.
  - Old-bug failure: second wake clears `event_flags.bit2`; `diag_b` remains zero.
- Add `test_v35_wake_handler_preserves_preexisting_pending_event_at_handler_boundary`.
  - Stop at handler return before dispatcher, or assert only final bring-up evidence after dispatcher. Do not assert an event bit after dispatcher has consumed it.
- Add mandatory full-chain guard, for example `tests/sim/test_v173_v35_wake_duplicate_traffic.py::test_v173_v35_full_chain_standby_wake_completes_both_mains_after_duplicate_wake_traffic`.
  - Fixture: canonical V1.73 + V3.5 after rebuild.
  - Stimulus: standby then wake through CONTROL/front-panel path, with observed duplicate wake traffic tolerated.
  - Assertions: PB1 and PB2 complete wake bring-up, gates are open, mute/audio state returns to the original preset, and CONTROL leaves `Zzz...`/`WAITING` for a usable `Volume` display.
  - If simulator timing cannot naturally align duplicate frames, keep the MAIN-only contiguous-frame test as the primary old-fail regression and name the live standby/wake hardware gate as required for field closure.

Fix:

- Replace the XOR/AND/XOR event-bit assignment in `wake_request_handler` with set-only behavior:
  - if gate was closed, set `event_flags.bit2`;
  - if gate was already open, preserve existing bit2;
  - if bit2 is set, ensure `active_flags.bit3` is set.
- Update only the adjacent wake comment.
- Do not touch V3.4.

### WU2 - MAIN Channel-6 Boot Source Clamp

Tests:

- Add `tests/sim/test_v35_boot_source_sanitizer.py`.
- Add `test_v35_boot_clamps_corrupt_channel6_without_mutating_channel5_or_shadows`.
  - Fixture: source-assembled V3.5 for pre-fix red evidence; canonical `V35_MAIN_HEX` after rebuild.
  - Stimulus: seed EEPROM `0x0B` (channel 5 source) to `0x03`; seed EEPROM `0x0C` (channel 6 source) to corrupt `0x09`; boot MAIN-only.
  - Assertions: primary RAM channel 5 `0x064 == 0x03`, primary RAM channel 6 `0x065 == 0x01`, shadow channel 5 `0x0A9 == 0x03`, shadow channel 6 `0x0AA == 0x01`.
  - Old-bug failure: channel 5 becomes `0x01`; channel 6 remains `0x09`; shadows mirror the wrong values.
- Add required parametrized all-channel sanitizer test, one corrupt source channel per case, proving each EEPROM offset `0x07..0x0C` clamps only its own primary/shadow byte.
- Add structural guard that the channel-6 validation block stores to `channel_6_source_config_b0` and not `channel_5_source_config_b0`.

Fix:

- Change only `restore_eeprom_settings_on_boot__validate_channel6_source` store target from `channel_5_source_config_b0` to `channel_6_source_config_b0`.

### WU3 - MAIN Repeated Fixed-Input `cmd06` Is A No-Op When Unmuted

Tests:

- Add `tests/sim/test_v35_cmd06_idempotence.py`.
- Add `test_v35_repeated_fixed_input_cmd06_does_not_rewrite_route_or_increment_c`.
  - Fixture: source-assembled V3.5 for pre-fix red evidence; canonical `V35_MAIN_HEX` after rebuild.
  - Stimulus: MAIN-only, converge a fixed `B0/06/05`, reset SRC4382 stats and `diag_src_c`, inject identical `B0/06/05` frames.
  - Assertions: `input_select` and `input_select_mirror` remain valid; `applied_route_shadow` and route request remain stable; `diag_src_c` unchanged; SRC4382 route write counts unchanged.
  - Old-bug failure: each repeat increments C and rewrites route registers.
- Add `test_v35_repeated_fixed_input_cmd06_repairs_stale_mirror_without_route_churn` or explicitly document that mirror self-heal is not part of the no-op contract. Preferred behavior: if `input_select == data` but `input_select_mirror` is stale, repair only the mirror and do not force route reconciliation.
- Add `test_v35_repeated_fixed_input_cmd06_while_muted_preserves_mute_refresh_path`.
  - Stimulus: user/effective mute set, input already fixed, reset TAS3108 write log/stats, inject identical fixed `cmd06`.
  - Assertions: user/effective mute bits and user mute latch remain set; latest TAS `0x30` payload is zero or retry evidence advances; no nonzero volume payload is written; no unintended unmute.
  - This is a preservation guard and may pass pre-fix unless paired with a mutation proof.
- Add mandatory full-chain guard, preferably in `tests/sim/test_v173_multi_pb_input_selection.py`.
  - Fixture: canonical V1.73 + V3.5 after rebuild.
  - Stimulus: set fixed asymmetric PB1/PB2 sources, converge routes, force repeated V1.73 full-sync input steps.
  - Assertions: per-MAIN input, mirror, route shadow/request, SRC4382 route writes, and `diag_src_c` remain stable.

Fix:

- Keep HID query and muted refresh branches before no-op detection.
- In the unmuted no-op check, compare equality:
  - `current_cmd_data == input_select` returns after any required mirror repair;
  - different data commits as today.
- Do not change CONTROL full-sync behavior.

### WU4 - MAIN `rx_ring_read` / OERR Resync Race

Tests:

- Add `tests/sim/test_v35_uart_rx_ring_oerr_race.py`.
- Add `test_v35_rx_ring_read_masks_and_restores_prior_gie_around_dequeue`.
  - Fixture: `V35_MAIN_ASM`.
  - Assertions: `rx_ring_read` has prior-`GIE` set/clear paths; `GIE` is cleared only around the ring-empty check, FSR2 setup, `INDF2` read, `rx_ring_rd_b0` increment/wrap, and output staging; exit restores `GIE` only if it entered set; W and BSR contracts are preserved.
  - Old-bug failure: no mask around the dequeue window.
- Add `test_v35_rx_ring_read_masked_span_is_bounded`.
  - Structural/cycle-budget assertion: no parser, route, I2C, UART frame processing, or loop work inside the `GIE=0` window; max masked span must stay comfortably below one 31,250-baud byte time.
- Add burst-drain smoke: inject contiguous valid frames and prove no new OERR/deadlock and parser still handles subsequent fresh frames.
- Add instruction-boundary attempt:
  - Use `step_until_pc_hit` to stop inside or immediately before `rx_ring_read`, seed RX ring bytes, force RCSTA.OERR through SFR poke or raw UART injection, and try to land OERR recovery before foreground increments `rx_ring_rd`.
  - If this cannot be expressed with the current facade, record the exact node, setup, and reason. Do not count a permanent `xfail` as closure.
- Add synthetic consequence proof:
  - Demonstrate old source or temp mutation can produce `rd=1, wr=0`/stale replay after OERR resync.
  - Fixed artifact acceptance is the structural proof plus burst-drain/OERR recovery behavior; do not require a fixed artifact to repair an impossible hand-seeded `rd=1,wr=0` state.

Fix:

- Use the `chain_copy` prior-`GIE` pattern, not unconditional `bsf INTCON,GIE`.
- Mask interrupts only around the minimal ring dequeue critical section.
- Preserve returned W and caller-visible BSR discipline.
- Do not mask parser work, route dispatch, UART frame processing, or I2C.

### WU5 - CONTROL Identity Parser Treats V3.4+ As Rev16

Tests:

- Extend `tests/sim/test_v172_v33_diag_identity.py`.
- Add `test_v173_identity_parser_waits_for_v35_rev16_tail_before_valid`.
  - Fixture: source-assembled V1.73 for pre-fix red evidence; canonical exact-LCD coverage remains in existing `V173_CONTROL_HEX` + `V35_MAIN_HEX` Diag tests after rebuild.
  - Stimulus: arm PB1 and PB2 identity parsers; inject synthetic V3.5 `BF/4F..55` with major `3`, minor `5`, low `0x23`, high `0x01`.
  - Assertions: no valid mask at `BF/53`; expected command is `0x54`; valid only after `BF/55`; stored parser cells contain rev `0x0123`.
  - Old-bug failure for V3.5: validates at `BF/53`, high byte remains `0x00`.
- Add `test_v173_identity_parser_keeps_v33_rev8_commit_policy`.
  - Inject compact V3.3 identity ending at `BF/53`; assert valid at `BF/53` with high byte zero.
- Add structural guard `test_v173_identity_rev16_gate_is_v34_plus_not_v34_only`.

Fix:

- After `major == 3`, implement `minor >= 4` rev16 continuation.
- Keep V3.3 and older compact identities committing at `BF/53`.
- Preserve existing malformed/out-of-order handling.

### WU6 - CONTROL Cold-WAITING Predicate Scratch Must Be ISR-Untouched

Tests:

- Add `tests/sim/test_v173_waiting_predicate_scratch.py` and include it in focused gates.
- Add `test_v173_cold_waiting_sentinel_reduce_uses_isr_untouched_existing_scratch`.
  - Fixture: `V173_CONTROL_ASM`.
  - Assertions: cold WAITING four-sentinel reduce no longer references `(Common_RAM + 24)` / `0x018`; it uses existing `v171_tx_enq_retry_acc` or `_phys` only in straight-line foreground code; no call occurs between accumulator initialization and the branch; no shared include or new RAM alias is needed.
- Add instruction-boundary attempt:
  - Use `step_until_pc_hit` around the cold WAITING reduce, allow/force TX interrupt activity from the poll frame, and attempt to reproduce the ISR clobber interleaving.
  - If exact timing cannot be expressed, record the failed attempt and keep the structural proof as the gating fixed-artifact test.
- Add a structural consequence guard:
  - Prove the cold-WAITING four-sentinel reduce does not use ISR scratch `(Common_RAM + 24)`.
  - Prove the replacement scratch is used only in straight-line code with no call boundary.
  - Do not require a broad sender clamp for arbitrary hand-poisoned connected RAM; that state is not field-reachable once WAITING cannot exit through an ISR-clobbered accumulator.

Fix:

- Replace only the cold WAITING four-sentinel accumulator references.
- Reuse existing access-bank scratch `v171_tx_enq_retry_acc` with a nearby V1.73 source comment explaining it is borrowed only across straight-line foreground predicate code and is ISR-untouched.
- Do not edit `dlcp_control_ram.inc`.
- Do not globally change menu/modal `0x018` uses.
- Do not mask `GIE` around the predicate unless the scratch option proves unsafe.

### WU7 - Release, Docs, And Evidence

- Rebuild canonical V3.5 once if any MAIN source changes.
- Rebuild canonical V1.73 once if any CONTROL source changes.
- Run release artifact SHA capture after rebuild:

```bash
shasum -a 256 firmware/patched/releases/DLCP_Firmware_V3.5.hex firmware/patched/releases/DLCP_Control_V1.73.hex
```

- Update:
  - `docs/FABLE_CONFIRMED_BUGS_20260702.md` with implementation disposition, test node IDs, old-behavior failures, fixed passes, and any simulator-fidelity residuals.
  - `docs/FABLE_CONFIRMED_BUGS_20260702_IMPL.md` with actual files changed, release revisions/SHA, and final evidence.
  - `docs/TEST_ROBUSTNESS_IMPL.md` with a grouped FABLE evidence row or rows for FABLE-001..006 including artifact rev/SHA, old-behavior result, focused result, broad gate, and hardware status.
  - `docs/TEST_INCIDENTS.md` with an incident entry or explicit link to the FABLE report as the incident ledger.
  - `README.md`, `AGENTS.md`, and current V3.5/V1.73 sections of `docs/HARDWARE_TEST.md` whenever canonical release artifacts are rebuilt and intended to remain canonical.
- Do not mark public docs consistent if release revision/SHA updates are deferred.
- Hardware evidence, if later gathered, must be sanitized per `docs/TEST_INCIDENTS.md`; do not commit raw HID paths, serials, screenshots with local media paths, or unsanitized diag JSON.

## Likely Files

Runtime source:

- `src/dlcp_fw/asm/dlcp_main_v35.asm`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`

Tests:

- `tests/sim/test_v35_duplicate_wake_idempotence.py`
- `tests/sim/test_v173_v35_wake_duplicate_traffic.py`
- `tests/sim/test_v35_boot_source_sanitizer.py`
- `tests/sim/test_v35_cmd06_idempotence.py`
- `tests/sim/test_v35_uart_rx_ring_oerr_race.py`
- `tests/sim/test_v172_v33_diag_identity.py`
- `tests/sim/test_v173_waiting_predicate_scratch.py`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- Release/preflight files may receive node additions only if existing canonical gates are insufficient.

Generated/canonical artifacts:

- `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- builder-produced `.lst`/`.cod` byproducts only if already tracked or expected by tests.

Docs:

- `docs/FABLE_CONFIRMED_BUGS_20260702.md`
- `docs/FABLE_CONFIRMED_BUGS_20260702_IMPL.md`
- `docs/TEST_ROBUSTNESS_IMPL.md`
- `docs/TEST_INCIDENTS.md`
- `README.md`
- `AGENTS.md`
- `docs/HARDWARE_TEST.md`

## Test Plan

Pre-fix evidence table to fill during implementation:

| FABLE ID | Required old-fail node | Fixture | Old expected result | Post-fix acceptance type |
| --- | --- | --- | --- | --- |
| 001 duplicate wake | `test_v35_duplicate_wake_frames_preserve_pending_wake_dispatch` | source-assembled or pre-fix canonical V3.5 | `diag_b`/wake bring-up does not advance after two wake frames | behavioral + full-chain canonical smoke |
| 002 channel 6 clamp | `test_v35_boot_clamps_corrupt_channel6_without_mutating_channel5_or_shadows` | source-assembled or pre-fix canonical V3.5 | CH5 clamped, CH6 corrupt, shadows wrong | behavioral + structural |
| 003 repeated fixed input | `test_v35_repeated_fixed_input_cmd06_does_not_rewrite_route_or_increment_c` | source-assembled or pre-fix canonical V3.5 | C/register write counts advance | behavioral + full-chain canonical |
| 004 rx ring race | structural old-fail plus instruction-boundary attempt | V35 ASM/temp source | no prior-`GIE` critical section; race attempt documented | structural + burst/OERR behavior |
| 005 identity rev16 | `test_v173_identity_parser_waits_for_rev16_high_byte_for_v34_plus` | source-assembled/pre-fix V1.73 | V3.5 commits at `BF/53` with high byte zero | source + canonical exact LCD |
| 006 WAITING scratch | structural old-fail plus race attempt and synthetic consequence | V173 ASM/temp source | reduce uses `0x018`; old consequence can emit `B1/06/80` | structural + reachable-path enum guard |

Focused post-fix tests:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v35_duplicate_wake_idempotence.py \
  tests/sim/test_v173_v35_wake_duplicate_traffic.py \
  tests/sim/test_v35_boot_source_sanitizer.py \
  tests/sim/test_v35_cmd06_idempotence.py \
  tests/sim/test_v35_uart_rx_ring_oerr_race.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v172_v33_diag_identity.py \
  tests/sim/test_v173_waiting_predicate_scratch.py \
  tests/sim/test_v173_multi_pb_input_selection.py
```

Release/build gates after source changes:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v35_release.py
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_v35_release_flash.py \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_dlcp_control_flash_safety.py \
  tests/sim/test_dlcp_main_flash.py
```

Canonical release nodes that must remain covered after rebuild include at least:

- `tests/sim/test_dlcp_control_flash_safety.py::test_detect_static_hex_control_release_info_v173`
- `tests/sim/test_dlcp_control_flash_safety.py::test_preflight_reports_v173_target_release`
- `tests/sim/test_dlcp_control_flash_safety.py::test_static_control_release_info_includes_build_date`
- `tests/sim/test_dlcp_control_flash_safety.py::test_canonical_v35_unarmed_relay_rejects_first_42_report_after_release_build`
- `tests/sim/test_dlcp_main_flash.py` static V3.5 HID/release detector and preflight/path tests already used by the release gate.

Broader simulator gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

`-n 32` is allowed as a local acceleration variant if the machine supports it, but the IMPL evidence must record the exact worker count used.

Optional full repo gate if tests outside `tests/sim` or flash wrappers change:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests -n 16 -q
```

Hardware:

- No live flashing in this IMPL.
- If live validation is separately requested, the release can be described as simulator-closed but not field-closed until the named standby/wake and audio-routing gates pass on hardware.

## Deployment And Smoke Plan

This IMPL does not deploy or flash hardware. Firmware deployment is only through the repo runbooks and requires explicit operator action.

MAIN V3.5 path:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
export LEFT_HID='<hid path reported for LEFT/PB1>'
export RIGHT_HID='<hid path reported for RIGHT/PB2>'
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
: "${RIGHT_HID:?set RIGHT_HID from identify-mains output}"
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$LEFT_HID" --left
.venv_ep0/bin/python scripts/dlcp_v35_release_flash.py --path "$RIGHT_HID" --right
```

CONTROL V1.73 path:

```bash
# Single visible MAIN only:
scripts/flash_control_safe.sh --preflight-only
scripts/flash_control_safe.sh

# Two visible MAINs: use the MAIN HID relay physically connected to CONTROL.
: "${LEFT_HID:?set LEFT_HID from identify-mains output}"
export CONTROL_RELAY_MAIN_HID="$LEFT_HID"
: "${CONTROL_RELAY_MAIN_HID:?set relay MAIN HID path}"
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID"
```

Rules:

- USB enumeration order is not safe. Use explicit HID paths on two-MAIN rigs.
- Do not use `--yes`/unattended live flash automation unless the user separately approves it.
- Power-cycle once after CONTROL flashing so V1.73 starts cleanly from cold boot.

Post-flash smoke commands, if separately requested:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_main_flash.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$LEFT_HID" --json
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$RIGHT_HID" --json
```

## Acceptance Criteria

- Each confirmed FABLE bug `001..006` has at least one deterministic regression, structural proof, or simulator-fidelity-documented race attempt.
- Old behavior is shown to fail a focused regression where feasible; for races, old structural failure plus instruction-boundary attempt plus synthetic consequence is recorded.
- MAIN V3.5 duplicate wake preserves wake dispatch and full-chain standby/wake completes both MAINs in canonical sim.
- MAIN V3.5 channel-6 boot sanitizer clamps channel 6, not channel 5, and primary/shadow source bytes agree.
- MAIN V3.5 repeated unmuted fixed-input `cmd06` is idempotent, full-chain V1.73 full-sync does not churn routes, stale mirror handling is tested or explicitly scoped, and muted refresh is preserved.
- MAIN V3.5 `rx_ring_read` has a prior-`GIE` preserving, cycle-bounded critical section around dequeue and no new burst/OERR regression.
- CONTROL V1.73 parses V3.4 and V3.5 identities as rev16, still supports compact V3.3 identity, and canonical exact LCD rows are tested for PB1/PB2.
- CONTROL V1.73 cold WAITING sentinel accumulator no longer aliases ISR scratch `0x018`; fixed reachable paths emit only valid `cmd06` input enums.
- Canonical V3.5 and V1.73 artifacts are rebuilt once per touched artifact, SHA/revisions are recorded, and release metadata/docs are updated in the same change.
- Focused gates, RAM safety, release/preflight gates, and broad simulator gate pass or have explicit documented residual risks.

## Rollback And Compatibility

- Rollback is the prior canonical V3.5/V1.73 artifacts captured before builder work.
- Use focused pathspecs only for rollback of touched files/artifacts. Never revert unrelated untracked docs or user changes.
- WU2 is stock-inherited but fixed only in V3.5. Older stock/V3.4 behavior remains historical.
- WU5 keeps V3.3 compact identity compatibility and V3.4 extended identity compatibility.
- WU6 changes only cold WAITING predicate scratch; reconnect stays on fresh-status evidence.
- If any work unit proves too risky, land smaller independent subsets with tests and rebuild only the affected artifact.

## Risks And Open Questions

- WU4 exact assembly shape must preserve W output, BSR expectations, and prior `GIE`; the masked span must be short enough not to create the OERR class it fixes.
- WU6 must reuse existing `v171_tx_enq_retry_acc` without adding a new RAM alias or crossing a call boundary.
- Instruction-level race reproduction may still be limited by the facade. The implementation must try the current hooks and document any simulator-fidelity gap before claiming closure.
- MAIN V3.5 flash headroom should be checked after WU1/WU3/WU4 via release-builder/listing output and existing headroom gates.

## Post-Implementation Evidence

Actual files changed:

- MAIN runtime source: `src/dlcp_fw/asm/dlcp_main_v35.asm`
- CONTROL runtime source: `src/dlcp_fw/asm/dlcp_control_v173.asm`
- Canonical artifacts: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`, `firmware/patched/releases/DLCP_Control_V1.73.hex`
- Regression tests:
  - `tests/sim/test_v35_duplicate_wake_idempotence.py`
  - `tests/sim/test_v35_boot_source_sanitizer.py`
  - `tests/sim/test_v35_cmd06_idempotence.py`
  - `tests/sim/test_v35_uart_rx_ring_oerr_race.py`
  - `tests/sim/test_v173_waiting_predicate_scratch.py`
  - `tests/sim/test_v172_v33_diag_identity.py`
- Docs: this IMPL, `docs/FABLE_CONFIRMED_BUGS_20260702.md`, `docs/TEST_ROBUSTNESS_IMPL.md`, `docs/TEST_INCIDENTS.md`, `README.md`, `AGENTS.md`, `docs/HARDWARE_TEST.md`

Actual release revisions and SHA-256:

- Prebuild backup directory: `artifacts/reanalysis/fable_20260702_prebuild/`
- Prebuild MAIN V3.5 canonical HEX: rev `0x009A`, SHA-256 `7d84601e588df6840c9f1d5d849cc7b74eaa9d0b07ec7c9f9c2c8487adfeb157`
- Prebuild CONTROL V1.73 canonical HEX: rev `0x62`, build `20260630`, SHA-256 `5b1c5bf41ade024a6fdad1df8715a7952e9be630d64be7445a71b0c45e684b4a`
- Built MAIN: `built canonical V3.5 release ... (release rev 0x009A -> 0x009B)`
- Built CONTROL: `built canonical V1.73 CONTROL release ... (release rev 0x62 -> 0x63)`
- Final MAIN V3.5 canonical HEX: rev `0x009B`, SHA-256 `7238d08cacf32f25358cf1a83d86984cb7c1d454ce46051bafe56acc3eed1071`
- Final CONTROL V1.73 canonical HEX: rev `0x63`, build `20260702`, SHA-256 `9a28543e99ff1806a470826283323e9438a29dd6a4aa6917a27152a1631c2ee1`
- Final MAIN source SHA-256: `00af0e3caf6132dacadc1149ab559d86f1c11fcaefe5a7b33f734f6a1dd0aff7`
- Final CONTROL source SHA-256: `8df404e5571c70e005c3da70084a2db7ff38941e8e490e4b1b5634f8f900f639`
- Final MAIN listing SHA-256: `bec738de640e6cf74e52c6ccf7400fe6e8e2e71e2dd9617d5b9a6a46d8edc956`
- Final CONTROL listing SHA-256: `115ac16ef5eedcc51041cb6249e564b1b06e9433b658337da3ae501969364df7`

Headroom:

- MAIN listing: `Program Memory Bytes Used: 19044`, `Program Memory Bytes Free: 5532`; tested margin before `0x4C00` is `1706` bytes, above the `1700` gate.
- CONTROL listing: `Program Memory Bytes Used: 16564`, `Program Memory Bytes Free: 16204`.

Focused pre-fix failures captured:

- `.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_duplicate_wake_idempotence.py tests/sim/test_v35_boot_source_sanitizer.py tests/sim/test_v35_cmd06_idempotence.py tests/sim/test_v35_uart_rx_ring_oerr_race.py tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_parser_waits_for_v35_rev16_tail_before_valid tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_parser_source_gate_is_v34_plus_not_v34_only tests/sim/test_v173_waiting_predicate_scratch.py::test_v173_waiting_four_sentinel_reduce_uses_non_isr_scratch --tb=short`
- Result on old source/canonical artifacts: `27 failed, 6 passed in 36.60s`.
- Representative old failures: duplicate wake left `diag_b == 0`; corrupt channel 6 left CH6 as `0x09` and clamped CH5; repeated fixed-input `cmd06` incremented `DIAG_SRC_C`; `rx_ring_read` lacked any `INTCON,7` mask/restore; V3.5 identity became valid at `BF/53`; cold WAITING still used `(Common_RAM + 24)`.

Instruction-boundary race attempts and outcomes:

- FABLE-004 RX-ring/OERR: simulator cannot place an ISR exactly between foreground `rx_ring_rd` dereference and increment. Closure is structural: `rx_ring_read` now saves prior `GIE`, clears `GIE` for the bounded dequeue span, restores only if previously enabled, and passes the span-budget test.
- FABLE-006 WAITING scratch: simulator cannot deterministically interrupt inside the four-sentinel straight-line reduce. Closure is structural: the accumulator now uses `v171_tx_enq_retry_acc`, no call boundary exists inside the reduce, and `Common_RAM+24` remains ISR-owned.
- A synthetic forced `input_select_cache=0x80` after normal connect can still create an impossible invalid full-sync state; this is not treated as a field-reachable sender clamp requirement for this pass.

Focused post-fix test commands/results:

- Focused Fable regressions after canonical rebuild:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_duplicate_wake_idempotence.py tests/sim/test_v35_boot_source_sanitizer.py tests/sim/test_v35_cmd06_idempotence.py tests/sim/test_v35_uart_rx_ring_oerr_race.py tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_parser_waits_for_v35_rev16_tail_before_valid tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_parser_keeps_legacy_v33_bf53_commit_path tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_parser_source_gate_is_v34_plus_not_v34_only tests/sim/test_v173_waiting_predicate_scratch.py --tb=short`
  -> `25 passed in 30.30s`
- Affected broad behavior/structural group:
  `.venv_ep0/bin/python -m pytest -q tests/sim/test_v173_multi_pb_input_selection.py tests/sim/test_v172_v33_diag_identity.py tests/sim/test_v34_v173_refactoring_contracts.py tests/sim/test_v34_v173_field_repros_20260613.py --tb=short`
  -> `339 passed in 1346.10s (0:22:26)`

RAM safety commands/results:

- `.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35 --target control-v173`
  -> `RAM bank safety: OK (main-v35, control-v173)`

Release/preflight commands/results:

- `.venv_ep0/bin/python scripts/build_v35_release.py && .venv_ep0/bin/python scripts/build_v173_release.py`
  -> MAIN `0x009A -> 0x009B`, CONTROL `0x62 -> 0x63`
- `.venv_ep0/bin/python -m pytest -q tests/sim/test_v35_v173_release_builders.py tests/sim/test_dlcp_v35_release_flash.py tests/sim/test_dlcp_main_flash.py tests/sim/test_dlcp_control_flash_safety.py tests/sim/test_firmware_version_label.py --tb=short`
  -> `105 passed, 3 warnings in 60.06s`

Full simulator/full repo gate commands/results:

- `.venv_ep0/bin/python -m pytest tests/sim -n 32 -q`
  -> `2175 passed, 2 skipped, 2 xfailed, 7 warnings in 1610.69s (0:26:50)`
- Skips: stock CONTROL V1.4/V1.5b rust-button precondition; V1.7x ISR scratch in-delay phase hook.
- Xfails: historical V3.4 table page crossing; historical V3.4 seeded bootloader-vector stub.

Hardware/deploy evidence or no-deploy reason:

- No live flashing, live audio, or live IR hardware was run. The user requested firmware/tests/docs work, not a live hardware deployment. Hardware field gates remain required for PB2 DOWN, audio routing, persistence, IR, and live CONTROL flashing.

Remaining low-risk items:

- FABLE-004 and FABLE-006 are closed by structural proof and bounded source changes, not by true sub-instruction interrupt injection. Current simulator hooks are not precise enough to prove those windows behaviorally.
- Cosmetic Fable observations remain intentionally unfixed in this pass.

Final status:

- Implemented for V3.5 MAIN and V1.73 CONTROL only.
- Canonical artifacts rebuilt and docs updated to MAIN rev `0x009B` and CONTROL rev `0x63` / build `20260702`.
- Simulator/release/RAM gates listed above passed.

## Reviewer Findings And Iteration History

Reviewer gate requirement: 8 independent reviewer agents/passes.

Initial draft review ran with these roles:

1. Simplicity/scope reviewer.
2. Correctness/contract reviewer.
3. Ops/tests/deploy reviewer.
4. UX/operator-visible contract reviewer.
5. Security/safety reviewer.
6. Performance/reliability reviewer.
7. Data/migration compatibility reviewer.
8. Maintainability/observability reviewer.

Findings ledger:

| Reviewer | Severity | Issue | Disposition | IMPL section changed |
| --- | --- | --- | --- | --- |
| UX/operator | High | WU1 lacked mandatory full-chain standby/wake proof. | Closed in revision; full-chain canonical wake guard required. | WU1, Test Plan, Acceptance |
| Security/safety | High | `dlcp_control_ram.inc` widened scope beyond V1.73. | Closed in revision; shared include removed from scope, reuse existing symbol only. | Source Requirements, WU6, Likely Files |
| Ops/tests | High | FABLE-006 lacked mandatory failing behavioral/synthetic consequence regression. | Closed in revision; race attempt and synthetic consequence required, without broad sender clamp. | WU6, Test Plan, Acceptance |
| Simplicity/scope | Medium | WU6 poisoned RAM could force unrelated sender clamp. | Closed in revision; direct arbitrary poison is not fixed-artifact acceptance unless spec expands. | WU6 |
| Simplicity/scope | Medium | Builders after each source fix would churn metadata. | Closed in revision; temp assembly first, one canonical rebuild per touched artifact. | WU0, Test Plan |
| Simplicity/scope | Low | Cosmetic edits allowed. | Closed in revision; cosmetics removed. | Source Requirements |
| Correctness/contract | Medium | WU6 normal path may pass old bug. | Closed in revision; instruction-boundary attempt plus synthetic consequence required. | WU6, Test Plan |
| Correctness/contract | Medium | Muted `cmd06` preservation was vague. | Closed in revision; concrete mute/TAS assertions required without adding a muted route-idempotence requirement. | WU3 |
| Correctness/contract | Low | Channel source shadows not asserted. | Closed in revision; primary and shadow assertions required. | WU2 |
| Ops/tests/deploy | Medium | Release/preflight gate too narrow. | Closed in revision; middle release/flash/preflight gate added. | Test Plan, WU7 |
| Ops/tests/deploy | Medium | WU5 canonical coverage optional. | Closed in revision; canonical V1.73 coverage mandatory after rebuild. | WU5 |
| Ops/tests/deploy | Medium | Hardware/runbook docs omitted. | Closed in revision; `docs/HARDWARE_TEST.md` update required when artifacts rebuild. | WU7, Likely Files |
| UX/operator | Medium | Full-chain routing churn not covered. | Closed in revision; V1.73 full-sync route-stability test required. | WU3 |
| UX/operator | Medium | Diagnostics identity PB2/canonical coverage weak. | Closed in revision; PB1/PB2 exact canonical LCD coverage required. | WU5 |
| UX/operator | Medium | Boot-source shadow contract missing. | Closed in revision; EEPROM offset, primary RAM, and shadow RAM asserted. | WU2 |
| Security/safety | Medium | Release rollback and identity preservation weak. | Closed in revision; prebuild SHA/backups and rollback rule added. | WU0, Rollback |
| Security/safety recheck | Medium | Rollback backup omitted source-side `.lst` files. | Closed in revision; WU0 now snapshots source ASM and `.lst` files when present and defines regenerate/delete fallback. | WU0 |
| Security/safety | Medium | Flashing guidance weaker than README. | Closed in revision; exact README commands and explicit path rules added. | Deployment |
| Security/safety | Medium | Race tests allowed non-gating shortcuts. | Closed in revision; no permanent xfail closure, structural/current artifact tests required. | WU4, WU6 |
| Maintainability | Medium | `TEST_ROBUSTNESS_IMPL.md` omitted from evidence docs. | Closed in revision; required grouped FABLE evidence row. | WU7, Likely Files |
| Data/compat | Medium | V3.4 rev16 compatibility not pinned. | Closed in revision; WU5 parametrizes V3.4 and V3.5. | WU5 |
| Performance/reliability | Medium | Instruction-boundary race attempts skipped too early. | Closed in revision; `step_until_pc_hit`/SFR/UART attempts required. | WU4, WU6 |
| Performance/reliability | Medium | WU4 GIE window not bounded. | Closed in revision; cycle/span and burst-drain guards required. | WU4 |
| Performance/reliability | Medium | New semantic alias could break RAM safety. | Closed in revision; no new alias, use existing symbol. | WU6 |
| Performance/reliability | Low | WU1 bit assertion could be timing-fragile. | Closed in revision; handler boundary or final dispatch evidence required. | WU1 |
| Performance/reliability | Low | Stale `input_select_mirror` behavior unspecified. | Closed in revision; mirror repair or explicit scope required. | WU3 |

Reviewer recheck:

- Completed after revision. All eight affected reviewer roles confirmed zero unresolved High or Medium findings. Focused rechecks also reported no remaining Low findings.
