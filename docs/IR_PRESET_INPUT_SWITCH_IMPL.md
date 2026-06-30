# IR Preset/Input Switch Shortcuts Implementation Plan

Date: 2026-06-30
Status: Implemented; follow-up hardening published in CONTROL V1.73 rev 0x62
Source spec: `docs/IR_PRESET_INPUT_SWITCH.md`

## Scope

Implement CONTROL V1.73 fixed Hypex RC5 shortcuts:

- Preserve configured-address F1/F2: `0x38` preset A, `0x39` preset B.
- Preserve configured-address standby/wake: `0x3A` standby, `0x3B` wake.
- Add F4 decimal 61 (`0x3D`) as preset A/B toggle.
- Add F5 decimal 63 (`0x3F`) as PB1 S/PDIF/Optical toggle.
- Add repo hardware-sender names for F4/F5 if hardware smoke is claimed.

MAIN V3.5 protocol changes are out of scope.  F5 must reuse existing
`cmd 0x06` input-select frames, and those frames must be addressed only to
known/reachable PBs.  `B0/06` broadcast input routing is forbidden.

## Required Docs Read

- `AGENTS.md`: canonical layout, source/release paths, test inventory, V1.73
  release builder rules.
- `CODING_STYLE.md`: CONTROL assembly style, banked-RAM safety, verification
  rules.
- `README.md`: current V3.5/V1.73 behavior, canonical `.venv_ep0` commands,
  IR shortcut list, multi-PB input recommendation, role-safe flash flow.
- `docs/HARDWARE_TEST.md`: Flipper IR sender, role-safe MAIN identification,
  hardware evidence, redaction expectations.
- `docs/MULTI_PB_INPUT_SELECTION.md`: PB2 linked/independent contracts,
  persistence safety, focused test commands.
- `docs/IR_PRESET_INPUT_SWITCH.md`: source requirements for this work.

## Current Implementation Evidence

- `src/dlcp_fw/asm/dlcp_control_ram.inc` defines:
  - `RC5_PRESET_A equ 0x38`
  - `RC5_PRESET_B equ 0x39`
  - `RC5_STANDBY_ENTER equ 0x3A`
  - `RC5_WAKE equ 0x3B`
  - `RC5_PRESET_TOGGLE equ 0x3D`
  - `RC5_INPUT_OPTICAL_SPDIF_TOGGLE equ 0x3F`
- `src/dlcp_fw/asm/dlcp_control_v173.asm` first compares the decoded address
  against RAM `0x20`, then compares configured action codes in RAM `0x21..0x26`.
- The original F4/F5 implementation split the fixed-shortcut probe so only
  address-matched commands that miss all configured action slots enter the
  fixed cascade.  Source tests now assert all six configurable action bytes are
  checked before the fixed F1/F2/F4/F5 cases.
- The fixed shortcut cascade tests `0x38..0x3B`, `0x3D`, and `0x3F`.
  Legacy V1.5b/V1.6b tests still treat `0x3D` as unknown on old firmware.
- Existing preset cases `v171_ir_preset_a_case` and
  `v171_ir_preset_b_case` perform state update,
  `v171_send_preset_frame_and_persist`, TX-abort restore, event flag, and IR
  re-arm.
- `v171_send_preset_frame_and_persist` checks carry only from
  `v171_send_preset_frame_txonly`.  `eeprom_write_byte` spins until
  `EECON1.WR` clears and exposes no EEPROM-abort status.  Therefore F4 can
  inherit/test TX saturation restore, but EEPROM-abort restore is not an
  observable current contract.
- `input_frame_send` emits addressed input frames only: PB1 `B1/06/<input>`
  before PB2 is seen, addressed PB1/PB2 frames while PB2 is linked, and
  addressed PB1 only when PB2 is independent.
- `map_cmd06_input_select_to_menu_index` maps a `cmd 0x06` payload to the LCD
  row through raw-status-dependent logic.  F5 must not hard-code S/PDIF or
  Optical row numbers.
- `tests/sim/test_v173_multi_pb_input_selection.py` has the right source
  iteration fixture: it copies `V17_CONTROL_RAM_INC` and `V173_CONTROL_ASM`,
  assembles a temporary CONTROL HEX, and boots it with V3.5 MAIN.
- `src/dlcp_fw/cli/hardware_flipper_ir.py` already exposes F4/F5 sender names;
  this follow-up does not require a live hardware smoke run.

## Gap Analysis

- Historical original gaps closed by the 2026-06-24 F4/F5 implementation:
  constants exist, fixed shortcuts are address-gated after configured-action
  matching, the Flipper sender exposes F4/F5, and happy-path F4/F5 simulator
  coverage exists.
- The current F4 toggle path lacks a repeat inhibit, so held or blasted F4 RC5
  repeats can toggle through multiple preset states too quickly.
- Existing F4 behavior tests prove CONTROL state, EEPROM, and MAIN preset bits
  but do not prove MAIN preset jobs finish or DSP coefficient state converges.
- The current F5 path updates PB1 cache/dirty/UI state before calling
  `input_frame_send`; if the TX ring is already saturated, CONTROL can advance
  local input state without queuing any visible route frame.
- F5 has linked/independent happy-path tests, but the single-known-PB F5 path
  and saturated-TX no-op path are not pinned.
- The 2026-06-24 implementation evidence remains historical; the current
  pre-hardening baseline is CONTROL V1.73 rev `0x60` / build `20260630`.

## Proposed Implementation

1. Add constants in `src/dlcp_fw/asm/dlcp_control_ram.inc`:
   - `RC5_PRESET_TOGGLE equ 0x3D`
   - `RC5_INPUT_OPTICAL_SPDIF_TOGGLE equ 0x3F`

2. Split the IR dispatch path in `src/dlcp_fw/asm/dlcp_control_v173.asm`:
   - Wrong-address decoded IR commands must re-arm and return without entering
     the fixed shortcut probe.
   - Configured-action success paths must perform their current action, re-arm,
     and return without entering the fixed shortcut probe.
   - Only address-matched commands that missed every configured action should
     enter the fixed shortcut probe.
   - Keep existing configured-address `0x38..0x3B` shortcut behavior intact.

3. Extend the fixed shortcut cascade:
   - Test `RC5_PRESET_TOGGLE`, branch to `v173_ir_preset_toggle_case`.
   - Test `RC5_INPUT_OPTICAL_SPDIF_TOGGLE`, branch to
     `v173_ir_input_optical_spdif_toggle_case`.

4. Implement `v173_ir_preset_toggle_case` without duplicated send logic:
   - Set the same short shared RC5 inhibit window used by input switching
     before branching, so a held F4 command cannot rapidly toggle A/B/A/B.
   - If `PRESET_BIT` is set, branch to existing `v171_ir_preset_a_case`.
   - If `PRESET_BIT` is clear, branch to existing `v171_ir_preset_b_case`.
   - This inherits TX saturation restore, persistence on success, event flag,
     and IR re-arm.

5. Implement `v173_ir_input_optical_spdif_toggle_case` with explicit bank safety:
   - Select bank 0, or use access-safe aliases, before every banked access to
     `input_select_cache_b0`, `rx_parsed_data_acc`, `rx_ring_staging_b0`, and
     related staging bytes.
   - Before mutating PB1 cache, LCD row state, dirty flags, or EEPROM state,
     call a TX-ring capacity helper and branch on `STATUS.C` immediately.
     `STATUS.C` is the helper ABI and later compare/map instructions clobber
     it.
   - If PB2 is known and linked, prove room for six bytes before local mutation
     so the addressed PB1/PB2 pair cannot be split by queue saturation.  For
     single-known-PB and independent PB2 cases, prove room for one 3-byte frame.
     If the required capacity is unavailable, re-arm IR and return with no
     local input change.
   - If `input_select_cache_b0 == 0x08`, target S/PDIF payload `0x05`.
   - Otherwise target Optical payload `0x08`.
   - Stage the target payload in `rx_parsed_data_acc`, call
     `map_cmd06_input_select_to_menu_index`, and keep the mapper-derived row in
     `rx_ring_staging_b0`.  Do not hard-code row values.
   - Copy the target payload into `input_select_cache_b0`.
   - Set the same redraw/event bits used by the existing input IR path.
   - Call `input_frame_send` so existing linked/independent PB2 route behavior
     is reused: `B1` while only PB1 is known, addressed `B1` plus `B2` when PB2
     is linked and known, and addressed `B1` only when PB2 is independent.  Do
     not emit `B0/06`.
   - Re-arm `IR_ARMED` before return.

6. Add hardware sender support:
   - Add `F4` = RC5 address `0x10`, command `0x3D`.
   - Add `F5` = RC5 address `0x10`, command `0x3F`.
   - Update `tests/sim/test_hardware_flipper_ir.py`.
   - Update `docs/HARDWARE_TEST.md` action map and `README.md` shortcut list.

7. Release metadata policy:
   - Source iteration tests assemble a temporary V1.73 HEX and do not require a
     canonical release publish.
   - If implementation publishes a new canonical V1.73 release through
     `scripts/build_v173_release.py`, update README/AGENTS release identity,
     build date, revision, SHA/evidence, and verification snapshot in the same
     change.

## Likely Files

- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `tests/sim/test_v173_multi_pb_input_selection.py` or a new focused
  source-assembled V1.73 IR shortcut test using the same temp-assembly pattern
- `src/dlcp_fw/cli/hardware_flipper_ir.py`
- `tests/sim/test_hardware_flipper_ir.py`
- `README.md`
- `docs/HARDWARE_TEST.md`
- `docs/IR_PRESET_INPUT_SWITCH_IMPL.md` for final implementation evidence

Do not place new source-behavior tests only in files that import canonical
`V173_CONTROL_HEX`; those tests can accidentally exercise stale release output.

## Test Plan

All F4/F5 behavior tests must assemble `V173_CONTROL_ASM` into a temporary HEX
unless the implementation explicitly enters the canonical release-publish path.

1. Dispatch gating and precedence:
   - Wrong-address fixed shortcut commands `0x38`, `0x39`, `0x3A`, `0x3B`,
     `0x3D`, and `0x3F` do not alter preset, standby/wake, input cache, TX
     `cmd 0x06`, or MAIN route.
   - Configure a user action slot, for example MUTE, to `0x3D`; inject
     address `0x10`, command `0x3D`; assert the configured action runs and
     preset toggle does not.
   - Repeat for `0x3F`; assert the configured action runs and input toggle does
     not.
   - Add parameterized collision coverage for every configurable action byte
     `0x21..0x26`, or add a source-level control-flow assertion proving every
     configured-action success path re-arms/returns before the fixed shortcut
     cascade.  Include both new fixed codes and at least one existing fixed
     code such as `0x38` or `0x3A`.
   - Regression: configured-address `0x38`, `0x39`, `0x3A`, `0x3B` still work.

2. F4 preset toggle:
   - Start in A, inject `0x3D`, settle, assert CONTROL `PRESET_BIT`, CONTROL
     EEPROM `0x74`, and both MAIN preset bits move to B.
   - Inject `0x3D` again, settle, assert CONTROL EEPROM/state and both MAINs
     move to A.
   - Include a reboot or EEPROM-readback assertion proving successful
     persistence.
   - Adapt the existing TX-ring saturation pattern from
     `tests/sim/test_v171_v32_user_visible_desync_bugs.py::test_ir_preset_b_tx_saturation_does_not_change_local_preset_state`
     for both A->B and B->A F4 directions.  Assert no frame, no local
     `PRESET_BIT` change, no EEPROM `0x74` change, no MAIN preset change, and
     IR re-arms.
   - Do not require EEPROM-abort testing unless this implementation first adds
     an explicit EEPROM timeout/abort contract.
   - Real-RB5/receiver-layer repeat regression: send F4, then send a held
     repeat inside the inhibit window; assert only one preset transition and no
     opposite-direction `cmd 0x20` frame.
   - DSP completion regression: after F4, assert both MAINs reach the requested
     preset, preset jobs return idle, and the MAIN DSP coefficient image/state
     converges across PB1/PB2.  The old bit-only test was insufficient.

3. F5 input toggle and UI coherence:
   - From PB1 Optical payload `0x08`, inject `0x3F`; expect S/PDIF payload
     `0x05`.
   - From PB1 S/PDIF payload `0x05`, inject `0x3F`; expect Optical payload
     `0x08`.
   - Parametrize non-Optical starts: `0x00`, `0x01..0x04`, `0x06`, `0x07`,
     `0x80`, `0xFF`; expect Optical payload `0x08`.
   - Parametrize raw-status classes `0`, `1`, `2`, `3`, `0x80`, `0xFF`; after
     F5, assert `INPUT_SELECT_CACHE`, mapper-derived selected row, and visible
     Input PB1 LCD row are coherent.
   - Run cases from Volume, Input PB1, and independent Input PB2 contexts to
     prove no PB2-page corruption.

4. F5 route and PB2 safety:
   - Linked PB2: expect addressed `B1/06` and `B2/06` with no `B0/06`; verify
     MAIN PB1 and PB2 apply the expected input/SRC route when linked.
   - Single-known-PB boot/discovery window through F5: expect only `B1/06`;
     PB2 concrete intent remains pending until PB2 is discovered.
   - Independent PB2 with `input_intent_pb2=0x07` and persisted AES: expect
     route `0xB1`, PB2 runtime intent unchanged, PB2 MAIN remains AES, PB2
     EEPROM `0x5F` unchanged, and `INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY` clear.
   - Existing input next/previous tests still pass.
   - TX saturation regression: force the TX ring full before F5; assert no
     `cmd 0x06`, PB1 cache/row/dirty state unchanged, EEPROM unchanged, MAIN
     route unchanged, and IR re-armed.

5. BSR/banked-RAM safety:
   - Add a source-level assertion around the new F5 case proving `movlb 0x00`
     or access-safe aliases precede banked RAM touches.
   - Add a simulator test that enters the F5 dispatch with nonzero BSR, if the
     harness can force it; otherwise document source-level coverage plus
     `check_ram_access_safety`.

6. Hardware sender/docs:
   - `resolve_action_spec("F4")` returns RC5 `0x10/0x3D`.
   - `resolve_action_spec("F5")` returns RC5 `0x10/0x3F`.
   - CLI formatting emits `ir tx RC5 10 3D` and `ir tx RC5 10 3F`.
   - HARDWARE_TEST action map lists F4/F5.

Focused commands:

```bash
.venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'ir or input'
.venv_ep0/bin/python -m pytest tests/sim/test_v171_ir_rc5_pulse_train.py -q -k 'f4 or receiver_dispatches_volume_mute_preset_and_input_shortcuts'
.venv_ep0/bin/python -m pytest tests/sim/test_hardware_flipper_ir.py -q
.venv_ep0/bin/python -m pytest tests/sim/test_v171_ir_command_matrix.py tests/sim/test_v171_preset_inline.py tests/sim/test_v171_ir_endpoints.py -q
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
```

Canonical publish command, only when intentionally publishing the release:

```bash
.venv_ep0/bin/python scripts/build_v173_release.py
```

## Deployment And Smoke Plan

No live deployment is part of this IMPL.  If hardware smoke is requested after
implementation, use the role-safe runbook from README/HARDWARE_TEST:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py detect
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
export LEFT_HID='<role-derived LEFT/PB1 path, local shell only>'
export RIGHT_HID='<role-derived RIGHT/PB2 path, local shell only>'
export CONTROL_RELAY_MAIN_HID="$LEFT_HID"
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID" --preflight-only
# Put CONTROL in its bootloader: power-cycle while holding UP+DOWN for about
# 6 seconds; do not press SELECT.
scripts/flash_control_safe.sh --path "$CONTROL_RELAY_MAIN_HID"
# Cold power-cycle once after flashing, then refresh role-derived HID paths.
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
# Re-export LEFT_HID/RIGHT_HID if paths changed after USB re-enumeration.
.venv_ep0/bin/python scripts/hardware_lcd_probe.py
.venv_ep0/bin/python scripts/hardware_flipper_ir.py --action F1
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/hardware_flipper_ir.py --action F2
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/hardware_flipper_ir.py --action F4
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$LEFT_HID" --info-only
.venv_ep0/bin/python scripts/dlcp_preset.py --path "$RIGHT_HID" --info-only
.venv_ep0/bin/python scripts/hardware_flipper_ir.py --action F5
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$LEFT_HID" --json
.venv_ep0/bin/python scripts/dlcp_diag.py --path "$RIGHT_HID" --json
```

Expected hardware observations:

- After F1, both MAIN preset readbacks report A.
- After F2, both MAIN preset readbacks report B.
- After F4 from B, both MAIN preset readbacks report A; a second F4 returns
  both to B.
- After F5, PB1/LEFT diagnostics show the toggled PB1 input/route evidence.  If
  PB2/RIGHT is configured independent AES, PB2/RIGHT diagnostics remain on AES.
  If PB2 is linked, both MAINs follow PB1 as expected.

If MAIN was not changed, do not reflash MAIN for this smoke.  If MAIN flashing
is separately required, first export both role-derived paths and flash only by
explicit `--path`.

Hardware evidence must redact raw HID paths and serials from committed/shared
artifacts.  Use role names plus hash-only identifiers when evidence leaves the
local ignored artifact directory.

No-deploy criteria: simulator preset sync fails, F5 emits invalid `cmd 0x06`
data, wrong-address or configured-collision tests fail, PB2 independent intent
or persistence changes, standby/wake regression, route/SRC end-to-end failure,
or RAM safety failure.

## Acceptance Criteria

- `docs/IR_PRESET_INPUT_SWITCH.md` exists and documents verified F1/F2 plus
  requested F4/F5 decimal/hex codes.
- CONTROL source has named constants and dispatch for `0x3D` and `0x3F`.
- Fixed shortcuts fire only for configured-address, unconsumed commands.
- F4 toggles A/B using the existing preset send/persist/TX-abort path.
- Held/blasted F4 is rate-limited by a repeat inhibit and cannot toggle twice
  inside one inhibit window.
- F5 toggles only PB1/global S/PDIF/Optical intent and respects linked vs
  independent PB2 routing.
- F5 is a no-op when the first input route frame cannot reserve TX-ring space.
- F5 proves MAIN route/SRC effects, not just CONTROL frame bytes.
- README, HARDWARE_TEST, and Flipper sender docs/actions are updated.
- If no hardware smoke is run, README/HARDWARE_TEST may continue to list F4/F5
  sender support while documenting simulator-only closure for this hardening.
- Focused simulator tests and RAM safety pass under `.venv_ep0`.
- Release build is produced only through the canonical V1.73 builder when the
  implementation is meant to publish a new release, and release identity docs
  are updated in the same change.

## 2026-06-30 Follow-Up Implementation Result

Implemented and published on 2026-06-30.

Changed files for this follow-up:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `firmware/patched/releases/DLCP_Control_V1.73.hex`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `tests/sim/test_v171_ir_rc5_pulse_train.py`
- `README.md`
- `AGENTS.md`
- `docs/TEST_ROBUSTNESS_IMPL.md`
- `docs/IR_PRESET_INPUT_SWITCH.md`
- `docs/IR_PRESET_INPUT_SWITCH_IMPL.md`

Behavior implemented:

- F4 `0x3D` now seeds the short shared RC5 inhibit window before branching to
  the existing preset A/B handlers, so a held F4 frame cannot immediately
  toggle A/B/A/B.
- F5 `0x3F` now proves TX capacity before mutating PB1 input cache, selected
  LCD row state, dirty flags, or EEPROM-save state.
- F5 uses the existing 3-byte reserve for single-known-PB and independent-PB2
  cases, and a new 6-byte reserve for known+linked PB2 so the addressed
  `B1/06` + `B2/06` pair cannot split due to queue saturation.
- `B0/06` input broadcast remains forbidden; addressed routing continues to be
  provided by `input_frame_send`.

Old-behavior red checks:

- The new real-RB5 F4 held-repeat test passed on source-assembled CONTROL and
  failed on the pre-hardening canonical x60 artifact because x60 had no F4
  inhibit.
- Independent reviewer probes reproduced the x60 F5 bug: with the TX ring
  saturated, F5 emitted no `cmd 0x06` frame but still changed PB1 cache, set
  PB1 dirty, and could later persist PB1 EEPROM ahead of MAIN route state.

Canonical release:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py
# built canonical V1.73 CONTROL release:
# firmware/patched/releases/DLCP_Control_V1.73.hex (release rev 0x60 -> 0x62)

shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex
# 5b1c5bf41ade024a6fdad1df8715a7952e9be630d64be7445a71b0c45e684b4a
```

Verification:

```bash
.venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'f4 or f5 or fixed_ir_shortcut_probe'
# 29 passed, 149 deselected in 99.05s

.venv_ep0/bin/python -m pytest tests/sim/test_v171_ir_rc5_pulse_train.py -q -k 'f4_held_repeat or receiver_dispatches_volume_mute_preset_and_input_shortcuts'
# 4 passed, 18 deselected in 18.25s

.venv_ep0/bin/python -m pytest tests/sim/test_v35_v173_release_builders.py tests/sim/test_v34_v173_release_builders.py -q
# 14 passed in 0.06s

.venv_ep0/bin/python -m pytest tests/sim/test_v171_ir_command_matrix.py tests/sim/test_v171_preset_inline.py tests/sim/test_v171_ir_endpoints.py tests/sim/test_hardware_flipper_ir.py -q
# 28 passed in 117.03s

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
# RAM bank safety: OK (control-v173)
```

No live hardware smoke and no full all-tests gate were run for this x61
hardening pass.  Live PB2 DOWN, audio-routing, persistence, IR, and
test-robustness field gates remain required before hardware field closure.

Follow-up review synthesis:

- Eight independent review passes were run for the follow-up IMPL.
- High findings on F4 repeat inhibit and F5 saturated-TX no-op are closed by
  the source changes and red/green tests above.
- Medium findings on receiver-layer fidelity and configured-action precedence
  are closed by the real-RB5 held-repeat test and the expanded source-flow
  assertion over action bytes `0x21..0x26`.
- Medium finding on linked PB2 partial TX capacity is closed by the F5
  6-byte preflight before local mutation.
- Release-ledger ambiguity is closed by publishing x61 and recording x60 as
  the pre-hardening baseline.

## Historical 2026-06-24 Implementation Result

Implemented on 2026-06-24.

Changed files:

- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`
- `src/dlcp_fw/cli/hardware_flipper_ir.py`
- `tests/sim/test_hardware_flipper_ir.py`
- `tests/sim/test_v173_multi_pb_input_selection.py`
- `README.md`
- `docs/HARDWARE_TEST.md`
- `docs/IR_PRESET_INPUT_SWITCH.md`
- `docs/IR_PRESET_INPUT_SWITCH_IMPL.md`

Behavior implemented:

- RC5 `0x3D` toggles preset A/B through the existing preset send/persist path.
- RC5 `0x3F` toggles PB1 S/PDIF/Optical through the existing `cmd 0x06`
  input sender.
- Fixed shortcuts now run only for configured-address commands that missed all
  user-configured action slots.
- F5 preserves linked-vs-independent PB2 behavior by reusing the existing input
  frame routing path.

Verification:

```bash
.venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'ir or input'
# 142 passed in 1133.87s (0:18:53)

.venv_ep0/bin/python -m pytest tests/sim/test_hardware_flipper_ir.py -q
# 7 passed in 0.03s

.venv_ep0/bin/python -m pytest tests/sim/test_v171_ir_command_matrix.py tests/sim/test_v171_preset_inline.py tests/sim/test_v171_ir_endpoints.py -q
# 21 passed in 203.70s (0:03:23)

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
# RAM bank safety: OK (control-v173)

git diff --check
# clean
```

Deployment evidence:

- No live hardware smoke was run for this change.
- Canonical V1.73 release publish was run on 2026-06-25:
  `.venv_ep0/bin/python scripts/build_v173_release.py`.
- `firmware/patched/releases/DLCP_Control_V1.73.hex` was rebuilt as
  `V1.73 / rev 0x54 / build 20260625`.
- CONTROL V1.73 HEX SHA-256:
  `ce6aa82d4cd874c5a6a40b3d93cc2be6413cbcdf7c04553d4b9bc3ca2c378280`.
- Release publish verification:
  `.venv_ep0/bin/python -m pytest tests/sim/test_v34_v173_release_builders.py -q`
  -> `7 passed in 0.07s`.

## Reviewer Findings And Iteration History

Initial draft prepared by Codex on 2026-06-24.

Eight initial reviewer passes completed:

- Simplicity/scope
- Correctness/contract
- Ops/tests/deploy
- UX/API-consumer
- Security/privacy
- Performance/reliability
- Data/migration compatibility
- Maintainability/observability

High/Medium findings addressed in this revision:

- Fixed shortcut dispatch must be address-matched and unconsumed; do not append
  F4/F5 to the existing broad post-probe label.
- F5 banked-RAM access needs explicit BSR/access-bank safety.
- F5 tests need end-to-end MAIN route/SRC validation, not only frame checks.
- F5 UI row/cache behavior must use the mapper or be tested across raw-status
  classes; hard-coded row values were removed.
- New behavior tests must assemble the current V1.73 source into a temp HEX
  instead of relying only on canonical `V173_CONTROL_HEX`.
- F4 success must prove persistence; F4 abort coverage should use TX
  saturation only because EEPROM abort is not observable today.
- F5 must not dirty or rewrite PB2 persistence.
- Hardware smoke must either add named F4/F5 Flipper actions or be manual-only;
  this plan adds the sender/docs/tests.
- Commands changed from `.venv/bin/python` to `.venv_ep0/bin/python`.
- Hardware smoke now references role-safe identification, explicit `--path`,
  and redaction rules.
- Follow-up findings on the smoke shell command, post-action observations, and
  full configured-action collision coverage were addressed.

Final review status: zero unresolved High or Medium findings.  No Low findings
remain that block implementation.
