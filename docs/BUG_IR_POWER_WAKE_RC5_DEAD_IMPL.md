# BUG-IR-POWER-WAKE-RC5-DEAD Implementation Plan

Date: 2026-06-28
Status: Implemented - focused IR/release/LCD/PB2/Field-8 gates pass; full simulator/all-tests gates pass; live hardware not run
Source spec: `docs/BUG_IR_POWER_WAKE_RC5_DEAD.md`
Scope: CONTROL V1.73 live-RC5 wake recovery; no MAIN behavior change expected.

## Source Requirements

Goals:

- After CONTROL wakes from standby by real Hypex RC5 power (`addr=0x10`,
  `cmd=0x32`), the next real RB5 RC5 command must decode and dispatch.
- Keep using the live RB5 Manchester decoder in the regression. Do not prove the
  fix with `inject_decoded_ir_event`.
- Preserve enough power-key repeat suppression that a held power key cannot
  immediately bounce the unit back to standby during the same wake transition.
- Preserve that suppression across the reconnect-exit boundary, where CONTROL
  leaves WAITING and resumes the normal display loop.
- Keep the change minimal and in CONTROL V1.73 unless evidence proves MAIN is
  involved.
- Rebuild the canonical CONTROL hex only through `scripts/build_v173_release.py`.

Non-goals:

- No IR profile redesign.
- No new RC5 decoder.
- No MAIN source changes.
- No hardware flash without explicit operator approval.

User decisions:

- Add a regression test now.
- Document the bug.
- Use `$write-impl` for the actual fix plan.
- Re-run the full test suite, including slow tests.

## Required Docs Read

- `AGENTS.md`: canonical layout, current V1.73/V3.5 release lines, builders,
  test inventory, and hardware-test opt-in policy.
- `CODING_STYLE.md`: CONTROL assembly style and verification expectations.
- `README.md`: current operator build/flash overview. Note: the README version
  prose is stale relative to the canonical CONTROL artifact, so tests must not
  derive expected rev text from README prose.
- `docs/SIMULATION.md`: rust simulator facade, `Chain.from_v171_v32`,
  `set_control_pin`, `step_ticks`, `lcd_lines`, and full sim command.
- `docs/HARDWARE_TEST.md`: live hardware tests are opt-in with
  `--run-hardware`; Flipper/Hypex RC5 commands include power `0x32`, standby
  `0x3A`, and wake `0x3B`.
- `docs/BUG_IR_POWER_WAKE_RC5_DEAD.md`: source bug record and acceptance
  criteria.

## Current Implementation Evidence

- `tests/sim/test_v171_ir_rc5_pulse_train.py` already contains the real RB5 RC5
  pulse helper `_drive_rc5_pulse_train`. Existing tests mostly clear
  `0x01B/0x01C` through `_prime_for_rc5_decode`, which masks this bug.
- Added regression:
  `test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`. It assembles
  CONTROL from `V173_CONTROL_ASM`, pairs with canonical `V35_MAIN_HEX`, wakes
  via real RC5 power `0x32`, then sends real standby endpoint `0x3A` without
  priming. Pre-fix result was strict `xfail`; rev `0x5A` removes the marker
  and passes source/canonical coverage.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:isr_entry__service_portb_change_if_ready`
  reads `(Common_RAM + 28) | (Common_RAM + 27)` (`0x01C:0x01B`) and skips
  `ir_rc5_decode` while the pair is nonzero.
- `ir_dispatch_configured_or_fixed_shortcuts__match_configured_codes` writes
  `0xC350` to `0x01C:0x01B` when the configured power command matches, toggles
  `control_flags.bit1`, and sets event exit.
- `display_state_entry__standby_wait_loop` transitions from `Zzz...` to the
  reconnect wait path after a wake event.
- `reconnect_wait_loop` already calls `v173_waiting_ir_service`, which discards
  pending IR frames and re-arms while WAITING because dispatching from WAITING
  is unsafe.
- `reconnect_wait_loop__wake_frame_queued` is the narrow boundary after a fresh
  MAIN status answer and successful wake-frame enqueue, immediately before
  `post_connect_init` and normal display resume.

## Gap Analysis

What exists:

- The live decoder and dispatch paths are already covered separately.
- WAITING/reconnect already has a safe discard-and-rearm helper for IR frames.
- The reconnect exit path is already the canonical handoff from wake recovery
  to normal UI.

What is missing:

- No test currently proves real RC5 remains usable after a power-key wake.
- No structural guard prevents the reconnect exit path from returning to normal
  UI with the RC5 inhibit pair still nonzero.
- Existing decoded-event wake responsiveness tests can pass while live RB5 IR
  is blocked.

Stale assumptions:

- `IR_ARMED` being set is not sufficient evidence of live IR readiness; the ISR
  can still skip the decoder while `0x01C:0x01B` is nonzero.

## Proposed Implementation

### WU1: Keep the Red Regression

Keep the new strict-`xfail` regression in
`tests/sim/test_v171_ir_rc5_pulse_train.py` until the source fix lands. The
test must continue to avoid `_prime_for_rc5_decode`.

### WU2: Split Broad Decoder Unblock From Power-Only Repeat Guard

Add semantic CONTROL RAM equates for the stock RC5 inhibit / ISR gate bytes in
`src/dlcp_fw/asm/dlcp_control_ram.inc`, then refresh the generated RAM-safety
alias block with the repo alias fixer so executable code can use access-safe
aliases:

```asm
ir_rc5_inhibit_lo          equ  0x01B
ir_rc5_inhibit_hi          equ  0x01C
```

Then, at `reconnect_wait_loop__wake_frame_queued`, clear the shared RC5 decoder
inhibit pair before `post_connect_init`:

```asm
        ; BUG-IR-POWER-WAKE-RC5-DEAD: these access-bank bytes gate the
        ; live RB5 RC5 decoder in the ISR. Once reconnect has accepted
        ; fresh MAIN evidence and queued wake, normal UI must not resume
        ; with the stock power inhibit still blocking the decoder.
        clrf    ir_rc5_inhibit_lo_acc, A
        clrf    ir_rc5_inhibit_hi_acc, A
```

Prefer inline `clrf` instructions unless code size or local control flow makes
a helper materially cleaner. If a helper is used, tests must still assert the
clear-before-`post_connect_init` behavior, not merely the helper name.

Reasoning:

- It leaves the stock long `0xC350` configured-power inhibit active during the
  standby/wake transition, so repeated frames from the same held power press are
  ignored while CONTROL is in the unsafe WAITING/reconnect window.
- It clears the shared decoder gate only when CONTROL has fresh MAIN evidence
  and is about to rejoin normal UI, so the first real user IR command after the
  Volume screen can decode.
- The clear is intentionally unconditional for reconnect exit, not gated on a
  remembered wake source. Any wake/reconnect that is about to resume normal UI
  should have a live decoder; adding wake-source state would increase RAM/control
  flow for no proven user-visible benefit.

The unconditional clear must be paired with a power-only repeat guard so a late
same-hold power repeat after reconnect exit is not treated as a fresh toggle.
Implementation options, in order of preference:

1. Prefer a dedicated `v173_power_repeat_guard` CONTROL RAM equate with
   generated aliases.
2. Reuse an existing byte only with an explicit owner/lifetime audit naming the
   physical byte and proving no EEPROM mirror, dirty flag, diagnostics, health,
   reconnect, or LCD-state collision. RAM-safety evidence alone is not enough.

Set the guard only when the configured-power match branch accepts the current
profile's power command as a state-changing toggle; this bug observes that path
as Hypex `0x32`. Keep it alive through reconnect exit, and make only subsequent
configured-power matches discard and re-arm while the guard is nonzero.
Non-power commands such as explicit standby `0x3A`, volume, preset, mute, and
input shortcuts must remain dispatchable after the shared inhibit pair is
cleared. The guard can decrement in the existing foreground
`ir_dispatch_configured_or_fixed_shortcuts` service; choose a bound that covers
same-press RC5 repeats at the Volume-return boundary but expires quickly enough
that a deliberate second power press still works. Acceptance bound: suppress at
least the first two same-toggle POWER repeats after Volume returns, then expire
no later than `48_000_000` universal ticks (about 1 simulated second) after
Volume return.

Because the guard is power-only, it does not intentionally change volume/mute/
input repeat timing across reconnect exits. If implementation chooses a generic
inhibit instead, it must add tests proving volume/mute/input repeat behavior is
unchanged across non-power reconnect exits.

If implementation evidence proves the guard is unnecessary because real/sim RC5
repeats cannot straddle reconnect exit, the post-clear held-power test below
must capture that evidence. Otherwise, implement the guard.

Do not fix this by:

- clearing `0x01B/0x01C` inside the test;
- using `inject_decoded_ir_event` for acceptance;
- removing the ISR gate without a separate repeat-suppression design;
- reducing `0xC350` to a tiny literal unless tests prove held-power wake cannot
  bounce and reviewers accept the repeat-risk tradeoff.

### WU3: Strengthen Tests for the Actual Fix

After WU2, remove the `xfail` marker from
`test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`.

Add one focused held-power protection test in the same module that spans the
actual reconnect-exit clear boundary:

- boot V1.73/V3.5, enter standby;
- send real RC5 power `0x32`;
- assert CONTROL is in reconnect/WAITING before the first extra frame;
- send one or two extra real `0x32` frames while reconnect/WAITING is active;
- wait for Volume, assert `ir_rc5_inhibit_lo` and `ir_rc5_inhibit_hi`
  (`0x01B/0x01C`) are both zero, then immediately send at least two same-toggle
  real `0x32` repeats at the post-clear/Volume-return boundary with normal RC5
  inter-frame gaps;
- after each post-Volume repeat, assert CONTROL remains on Volume, does not emit
  a new standby frame, and does not enter `Zzz...`;
- then send real standby `0x3A` and assert it works.
- add a guard-expiry test: after Volume return, wait no more than `48_000_000`
  universal ticks, send a fresh configured-power command, and verify it toggles
  standby normally.

Add a structural test in `tests/sim/test_v34_v173_refactoring_contracts.py` or
the pulse-train module that verifies:

- `dlcp_control_ram.inc` names `ir_rc5_inhibit_lo` as `0x01B` and
  `ir_rc5_inhibit_hi` as `0x01C`, and generated aliases include
  `ir_rc5_inhibit_lo_acc` / `ir_rc5_inhibit_hi_acc`;
- the success path is ordered as `call standby_wake_broadcast`, `bnc
  reconnect_wait_loop__wake_frame_queued`, then inside
  `reconnect_wait_loop__wake_frame_queued` both generated access aliases are
  cleared before `bra     post_connect_init`;
- the saturation retry path does not clear the inhibit pair before branching
  back to `reconnect_wait_loop`;
- if a helper is used, its body clears both named bytes and returns, and it is
  called only from the successful `reconnect_wait_loop__wake_frame_queued`
  path.

Do not require a single-use helper name.

Add or parameterize a canonical-release regression after the build:

- source fixture: temp-assembled `V173_CONTROL_ASM + V35_MAIN_HEX`;
- release fixture: canonical `V173_CONTROL_HEX + V35_MAIN_HEX`.

Parameterize
`test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby` over
`source` and `canonical` CONTROL images. The shipped canonical artifact must
pass after `scripts/build_v173_release.py` with this node:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  'tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby[canonical]'
```

Pre-fix evidence must not rely on a successful `xfail` run. Before coding,
record a red run with `--runxfail` or a temporary marker removal. After the fix,
verify no `BUG-IR-POWER-WAKE-RC5-DEAD` `xfail` marker remains.

### WU4: Build and Metadata

Fast optional preflight:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
```

Publish the canonical CONTROL artifact only through:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
```

The builder is the required RAM-safety/release path and must be the only step
that bumps CONTROL release metadata and publishes
`firmware/patched/releases/DLCP_Control_V1.73.hex`.

If the canonical CONTROL release rev/build changes, update current-release
metadata/status in `AGENTS.md` and `README.md` in the same change, or remove
exact current rev claims from README so the canonical hex metadata remains the
single source. Update any `docs/HARDWARE_TEST.md` release-identification text
that names the current CONTROL rev/build, or record an explicit tracked
follow-up with the new rev/date/hash. Do not do unrelated README cleanup;
historical/background docs can remain follow-ups.

## Likely Files

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `tests/sim/test_v171_ir_rc5_pulse_train.py`
- `tests/sim/test_v34_v173_refactoring_contracts.py`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `AGENTS.md`
- `README.md`

## Test Plan

Focused first:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail \
  tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_ir_rc5_pulse_train.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v173_wake_responsiveness.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v17x_isr_scratch_collision.py \
  tests/sim/test_reconnect_wake_gate.py \
  tests/sim/test_v171_reconnect_wake.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_ir_command_matrix.py \
  tests/sim/test_v173_multi_pb_input_selection.py
```

Release/static:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v35_v173_release_builders.py \
  tests/sim/test_dlcp_control_flash_safety.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  'tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby[canonical]'
```

Full suite per repo docs/user request:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests -n 16 -q
```

Hardware is not part of this implementation without explicit approval. If the
operator later approves a live gate, use `docs/HARDWARE_TEST.md` with explicit
HID path identification and the exact smoke below: front-panel STBY, then
`scripts/hardware_flipper_ir.py --action POWER`, then immediate
`scripts/hardware_flipper_ir.py --action STANDBY`.

## Deployment and Smoke Plan

No deployment/flash during IMPL creation.

After implementation and successful tests, the only approved CONTROL artifact
publication path is `scripts/build_v173_release.py`.

Hardware flashing, if approved separately, must not rely on HID auto-selection.
Identify roles first and pass the relay MAIN path explicitly:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
export CONTROL_RELAY_MAIN_HID="<PB1/LEFT HID path from identify-mains>"
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --preflight-only
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID"
```

Do not use `--yes` for this bug's live gate.

Approved live smoke, if the operator explicitly asks to run it:

1. Boot to Volume and verify both MAINs are active.
2. Enter standby via the front-panel STBY key.
3. Send `POWER` with `scripts/hardware_flipper_ir.py --action POWER`
   (Hypex RC5 `0x32`).
4. Verify Volume returns and MAINs are active/playing.
5. Immediately send `STANDBY` with
   `scripts/hardware_flipper_ir.py --action STANDBY` (RC5 `0x3A`).
6. Verify `Zzz...` and MAIN standby.

Shared evidence must be sanitized: raw detect/identify/result JSON and media
stay local under ignored artifacts; any pasted evidence uses role labels,
redacted/hash-only IDs, LCD-only cropped media, and stripped metadata.

## Acceptance Criteria

- The regression passes with no `xfail`.
- A pre-fix `--runxfail` or marker-removed run is recorded as red, and no
  `BUG-IR-POWER-WAKE-RC5-DEAD` `xfail` marker remains post-fix.
- At Volume return after power wake, `ir_rc5_inhibit_lo/hi` (`0x01B/0x01C`)
  are both zero before the next IR frame.
- A held-power-repeat wake test passes, including at least two same-toggle real
  `0x32` repeats after Volume return.
- A guard-expiry test proves a deliberate later POWER press still toggles
  standby normally.
- A fresh non-power command, explicit standby `0x3A`, decodes immediately after
  the post-wake power-repeat guard path.
- The canonical post-build CONTROL hex passes the same regression as the
  source-built test fixture.
- Existing real-RB5 pulse-train tests pass.
- Decoded IR matrix and wake responsiveness tests pass.
- RAM safety passes for `control-v173`.
- Canonical CONTROL V1.73 hex is rebuilt by the canonical builder.
- Current-release metadata/status is updated in `AGENTS.md` and `README.md`,
  or README exact current-rev claims are removed in favor of canonical hex
  metadata.
- Full `tests/sim` pytest suite passes with slow tests included.
- Full `tests` pytest suite passes with slow tests included, except live
  hardware tests skipped by default, unless the run is blocked by an unrelated
  pre-existing dirty-worktree failure that is documented with node IDs.
- No MAIN source or MAIN hex changes are made.

## Implementation Results

Files changed for this bug:

- `src/dlcp_fw/asm/dlcp_control_ram.inc`
  - Added named `ir_rc5_inhibit_lo/hi` aliases for the stock `0x01B/0x01C`
    ISR live-RC5 gate.
  - Added dedicated bank2 `v173_power_repeat_guard_lo/hi` at physical
    `0x26F/0x270` plus generated access aliases.
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
  - Clears `ir_rc5_inhibit_lo_acc` and `ir_rc5_inhibit_hi_acc` only on the
    successful `reconnect_wait_loop__wake_frame_queued` path, before
    `post_connect_init`.
  - Adds a two-byte configured-POWER-only repeat guard that survives reconnect
    exit, suppresses late held POWER repeats, and expires under the 1-second
    acceptance bound.
  - Ignores `BF/20` preset echo frames while CONTROL is asleep/WAITING so an
    asleep IR preset intent is not overwritten by unrelated host preset traffic
    before wake.
  - Clears the new guard at cold init.
- `tests/sim/test_v171_ir_rc5_pulse_train.py`
  - Removed the BUG-IR strict `xfail`.
  - Parameterized source-built and canonical V1.73 CONTROL fixtures.
  - Added root `0x01B/0x01C` clear assertions, held-POWER repeat coverage, and
    guard-expiry coverage using real RB5 RC5 pulse trains.
- `tests/sim/test_v34_v173_refactoring_contracts.py`
  - Added RAM alias, reconnect-success ordering, retry-path non-clear, and
    POWER-only guard structural contracts.
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
  - Rebuilt only through `scripts/build_v173_release.py`.
- `AGENTS.md`, `README.md`, `docs/HARDWARE_TEST.md`
  - Updated current CONTROL identity/status to rev `0x5C` / build `20260628`
    after the LCD/PB2/Field-8 follow-up fixes.

Canonical artifact:

- `PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py`
  -> `firmware/patched/releases/DLCP_Control_V1.73.hex`, rev `0x5B -> 0x5C`,
  build `20260628`.
- SHA-256:
  `04223d7b6f677671431cef3fac6e1b39986b3f5041e95a7eab722a91c96cdb4f`.

Focused verification:

- `PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173 --fix-aliases`
  -> alias block updated; `RAM bank safety: OK (control-v173)`.
- `PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173`
  -> `RAM bank safety: OK (control-v173)`.
- Structural + source regression slice:
  `tests/sim/test_v34_v173_refactoring_contracts.py::{test_v173_rc5_inhibit_and_power_guard_ram_contract_is_named,test_v173_reconnect_success_clears_live_rc5_gate_before_ui_resume,test_v173_configured_power_uses_separate_post_reconnect_repeat_guard}` plus
  `tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby[source]`
  -> `4 passed`.
- Source held-repeat/expiry slice:
  `tests/sim/test_v171_ir_rc5_pulse_train.py::{test_v173_power_wake_ignores_late_held_power_repeats_before_next_standby[source],test_v173_power_repeat_guard_expires_for_deliberate_second_power_press[source]}`
  -> `2 passed`.
- Canonical artifact slice:
  `tests/sim/test_v171_ir_rc5_pulse_train.py::{test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby[canonical],test_v173_power_wake_ignores_late_held_power_repeats_before_next_standby[canonical],test_v173_power_repeat_guard_expires_for_deliberate_second_power_press[canonical]}`
  -> `3 passed`.
- Full pulse-train module:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_ir_rc5_pulse_train.py`
  -> `12 passed`.
- Reconnect/ISR focused group:
  `tests/sim/test_v173_wake_responsiveness.py tests/sim/test_v17x_isr_scratch_collision.py tests/sim/test_reconnect_wake_gate.py tests/sim/test_v171_reconnect_wake.py`
  -> `12 passed, 1 skipped`.
- Release/flash safety:
  `tests/sim/test_v35_v173_release_builders.py tests/sim/test_dlcp_control_flash_safety.py`
  -> `34 passed`.
- Refactoring contracts:
  `tests/sim/test_v34_v173_refactoring_contracts.py`
  -> `86 passed, 1 xfailed`.

Focused follow-up gates from the full-suite cleanup:

- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -n 16 -q --maxfail=20`
  -> `167 passed in 201.34s`.
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 16 --maxfail=20 tests/sim/test_v171_ir_rc5_pulse_train.py tests/sim/test_v173_multi_pb_input_selection.py tests/sim/test_lcd_refresh_budget.py tests/sim/test_preset_filename_lcd_spec.py tests/sim/test_flash_table_page_carry_audit.py tests/sim/test_v34_v173_compatibility.py tests/sim/test_v34_v173_field_repros_20260613.py tests/sim/test_v34_v173_refactoring_contracts.py tests/sim/test_dlcp_control_flash_safety.py tests/sim/test_v35_v173_release_builders.py`
  -> `534 passed, 3 xfailed in 568.90s`.
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py`
  -> `22 passed in 72.24s`.

Full requested gates:

- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
  -> `2100 passed, 2 skipped, 4 xfailed, 10 warnings in 1578.53s`.
- `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests -n 16 -q`
  -> `2100 passed, 21 skipped, 4 xfailed, 7 warnings in 1597.33s`.

The intermediate full-gate failures in LCD table/page-carry, preset filename
refresh, PB2 input-row behavior, compatibility, and Field-8 asleep-preset
traffic were fixed in the same pass and are covered by the full gates above.

No hardware flash or live smoke was run. Units were not connected and this bug's
hardware gate requires explicit operator approval plus role-identified HID path.

## Reviewer Findings

Pre-implementation evidence:

- Regression added as strict `xfail`:
  `tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`.
- Focused strict-`xfail` run:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`
  -> `1 xfailed`.
- Focused red run:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`
  -> `1 failed`; post-wake standby RC5 was ignored with
  `decoded=0x10/0x32`, `flags=0x07`, `inhibit=0x639D`.
- Broad requested all-tests run:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests -n 16 -q`
  -> `38 failed, 2052 passed, 21 skipped, 5 xfailed, 7 warnings` in
  `1575.11s`.  The failing nodes are existing CONTROL/LCD/PB2/preset-field
  areas, not the new strict-xfail regression.

Initial gate:

| Reviewer | Severity | Finding | Disposition |
| --- | --- | --- | --- |
| Correctness/contract | High | Held-power repeat protection was not proven at the reconnect-exit clear boundary. | Addressed in WU2/WU3 by requiring a post-clear boundary test and a power-only guard if needed. |
| Security/privacy | Medium | Flash examples omitted explicit relay HID path. | Addressed in Deployment with `identify-mains`, `CONTROL_RELAY_MAIN_HID`, explicit `--path`, and no `--yes`. |
| Security/privacy | Low | Hardware evidence privacy handling was implicit. | Addressed in Deployment with a sanitization checklist. |
| UX/API-consumer | High | Hardware smoke sequence was underspecified and could start from the wrong state. | Addressed with exact front-panel STBY -> Flipper POWER -> Flipper STANDBY smoke. |
| UX/API-consumer | High | Pathless flash examples were unsafe for two-MAIN operator contract. | Addressed with explicit path flow. |
| UX/API-consumer | Medium | Canonical post-build artifact was not behavior-tested. | Addressed with required canonical V173_CONTROL_HEX regression. |
| UX/API-consumer | Medium | Release metadata docs were treated as optional. | Addressed by requiring `AGENTS.md` and `README.md` current-release updates when rev/build changes. |
| UX/API-consumer | Medium | Held-power test was not anchored to WAITING/reconnect timing. | Addressed with explicit pre/post WAITING and post-clear assertions. |
| UX/API-consumer | Low | Hardware action names should use public Flipper action names. | Addressed with `POWER` and `STANDBY` commands. |
| Simplicity/scope | Medium | Single-use helper and helper-name structural test were over-specific. | Addressed by preferring inline clear and behavior/sequence structural assertion. |
| Simplicity/scope | Medium | Unconditional reconnect-exit clear affects all reconnect exits. | Addressed by documenting it as intentional and avoiding wake-source state. |
| Simplicity/scope | Low | Release-doc update rule was too opportunistic. | Addressed by requiring current artifact metadata updates. |
| Simplicity/scope | Low | RAM safety listed twice as required. | Addressed by making standalone check optional preflight and builder required. |
| Ops/tests/deploy | High | Hardware/deploy validation did not define an executable gate for the exact field failure. | Addressed with explicit front-panel STBY -> Flipper POWER -> Flipper STANDBY smoke. |
| Ops/tests/deploy | Medium | Strict-xfail regression could be reported as green without proving the fix. | Addressed with required `--runxfail`/temporary-marker red evidence and post-fix xfail removal check. |
| Ops/tests/deploy | Medium | Release/static validation omitted builder and safe-control-flash tests. | Addressed with focused `test_v35_v173_release_builders.py` and `test_dlcp_control_flash_safety.py`. |
| Ops/tests/deploy | Medium | Release-doc synchronization was not required after metadata bump. | Addressed with AGENTS/README/HARDWARE_TEST current-ID update or explicit tracked follow-up. |
| Ops/tests/deploy | Low | Held-power test timing was underspecified. | Addressed with explicit WAITING and post-Volume assertions. |
| Ops/tests/deploy | Low | Structural test requirement was too loose. | Addressed with success-path/retry-path ordered structural assertions. |
| Performance/reliability | High | Plan could remove the only post-wake repeat suppressor before proving held power cannot bounce. | Addressed with power-only post-reconnect guard and same-toggle post-Volume repeat test. |
| Performance/reliability | Medium | Success-only structural placement was too weak. | Addressed with exact `standby_wake_broadcast`/`bnc`/success-label ordering and no retry-path clear. |
| Performance/reliability | Medium | Focused plan omitted ISR scratch and reconnect/OERR reliability guards. | Addressed with `test_v17x_isr_scratch_collision.py`, `test_reconnect_wake_gate.py`, and `test_v171_reconnect_wake.py`. |
| Performance/reliability | Low | Full-suite command was broader than the documented full sim gate. | Addressed by listing `tests/sim -n 16 -q` as required and broader `tests -n 16 -q` for the user's all-tests request. |
| Maintainability/observability | High | Held-power repeat protection was not proven across reconnect exit. | Addressed with post-Volume same-toggle power repeats and root-state assertions. |
| Maintainability/observability | Medium | Root-cause state was not asserted as an acceptance condition. | Addressed by requiring `0x01B/0x01C == 0` at Volume before standby `0x3A`. |
| Maintainability/observability | Medium | Structural guard was too shallow. | Addressed by requiring named-byte clear contract before `post_connect_init`. |
| Maintainability/observability | Medium | Canonical release prose was optional. | Addressed by requiring AGENTS/README current-release metadata handling. |
| Maintainability/observability | Low | Shared-RAM clear lacked a contract comment. | Addressed in WU2 snippet. |
| Data/migration compatibility | High | Held-power protection did not cover reconnect-exit boundary. | Addressed with post-clear same-toggle repeat test and power-only guard requirement. |
| Data/migration compatibility | Medium | Generic reconnect clear can affect non-power IR families. | Addressed by requiring power-only guard; generic guard alternatives need volume/mute/input tests. |
| Data/migration compatibility | Medium | `0x01B/0x01C` lacked semantic aliases/manifest coverage. | Addressed by requiring `ir_rc5_inhibit_lo/hi` equates or explicit alias equivalent plus structural tests. |
| Data/migration compatibility | Low | Release prose could remain stale after metadata bump. | Addressed by requiring AGENTS/README current-release identity handling or README exact-rev removal. |

Reviewer rerun summary:

- Simplicity/scope: zero High/Medium/Low.
- Correctness/contract: zero High/Medium/Low.
- Ops/tests/deploy: zero High/Medium/Low after replacing the placeholder
  canonical node and stale hardware note.
- UX/API-consumer: zero High/Medium/Low after replacing the placeholder
  canonical node and stale hardware note.
- Security/privacy: zero High/Medium/Low.
- Performance/reliability: zero High/Medium/Low after adding the 1-second
  guard-expiry upper bound.
- Data/migration compatibility: zero High/Medium remaining after requiring
  generated access aliases and dedicated/audited guard RAM ownership.
- Maintainability/observability: zero High/Medium/Low after requiring named
  inhibit bytes, root-state assertions, a contract comment, concrete canonical
  pytest node, and configured-power wording.

Final review state: zero unresolved High or Medium findings. No Low findings
remain.
