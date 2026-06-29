# IR Preset/Input Switch Shortcuts Implementation Plan

Date: 2026-06-24
Status: Implemented - simulator verified; canonical release published
Source spec: `docs/IR_PRESET_INPUT_SWITCH.md`

## Scope

Implement CONTROL V1.73 fixed Hypex RC5 shortcuts:

- Preserve configured-address F1/F2: `0x38` preset A, `0x39` preset B.
- Preserve configured-address standby/wake: `0x3A` standby, `0x3B` wake.
- Add F4 decimal 61 (`0x3D`) as preset A/B toggle.
- Add F5 decimal 63 (`0x3F`) as PB1 S/PDIF/Optical toggle.
- Add repo hardware-sender names for F4/F5 if hardware smoke is claimed.

MAIN V3.5 protocol changes are out of scope.  F5 must reuse existing
`cmd 0x06` input-select frames.

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
- `src/dlcp_fw/asm/dlcp_control_v173.asm` first compares the decoded address
  against RAM `0x20`, then compares configured action codes in RAM `0x21..0x26`.
- The current broad fixed-shortcut label
  `ir_dispatch_configured_or_fixed_shortcuts__post_configured_fixed_shortcut_probe`
  is also reached by wrong-address and configured-action-success paths.  F4/F5
  must not be appended there without splitting or guarding the path.
- The fixed shortcut cascade currently tests only `0x38..0x3B`; `0x3D` and
  `0x3F` are not named fixed shortcuts.  Legacy V1.5b/V1.6b tests treat
  `0x3D` as unknown; `0x3F` is not in the current fixed cascade or RC5 constant
  list.
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
- `src/dlcp_fw/cli/hardware_flipper_ir.py` currently exposes F1/F2 but not
  F4/F5.

## Gap Analysis

- No constants exist for RC5 `0x3D`/`0x3F`.
- The fixed shortcut dispatch entry path is too broad for the new F4/F5
  requirement and should be split or guarded.
- No F4/F5 behavior tests exist.
- No tests pin wrong-address behavior or configured-action collision
  precedence for the new shortcuts.
- No tests pin F5 PB2 persistence side effects.
- README/HARDWARE_TEST/hardware Flipper action maps do not document or expose
  F4/F5.

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
   - If `PRESET_BIT` is set, branch to existing `v171_ir_preset_a_case`.
   - If `PRESET_BIT` is clear, branch to existing `v171_ir_preset_b_case`.
   - This inherits TX saturation restore, persistence on success, event flag,
     and IR re-arm.

5. Implement `v173_ir_input_optical_spdif_toggle_case` with explicit bank safety:
   - Select bank 0, or use access-safe aliases, before every banked access to
     `input_select_cache_b0`, `rx_parsed_data_acc`, `rx_ring_staging_b0`, and
     related staging bytes.
   - If `input_select_cache_b0 == 0x08`, target S/PDIF payload `0x05`.
   - Otherwise target Optical payload `0x08`.
   - Stage the target payload in `rx_parsed_data_acc`, call
     `map_cmd06_input_select_to_menu_index`, and keep the mapper-derived row in
     `rx_ring_staging_b0`.  Do not hard-code row values.
   - Copy the target payload into `input_select_cache_b0`.
   - Set the same redraw/event bits used by the existing input IR path.
   - Call `input_frame_send` so existing linked/independent PB2 route behavior
     is reused: `B0` when linked/PB2 unknown, `B1` for PB1 when PB2 is
     independent.
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
   - Linked PB2: expect broadcast route `0xB0`; verify MAIN PB1 and PB2 apply
     the expected input/SRC route when linked.
   - Independent PB2 with `input_intent_pb2=0x07` and persisted AES: expect
     route `0xB1`, PB2 runtime intent unchanged, PB2 MAIN remains AES, PB2
     EEPROM `0x5F` unchanged, and `INPUT_SPLIT_FLAG_PB2_PERSIST_DIRTY` clear.
   - Existing input next/previous tests still pass.
   - Document and test, if practical, that F5 intentionally inherits existing
     input next/previous TX-saturation semantics: local PB1 cache/LCD may update
     before `input_frame_send` can reserve TX space.  If this behavior is not
     acceptable for F5, implement restore/no-op-on-saturation instead and add a
     saturation regression.

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
- F5 toggles only PB1/global S/PDIF/Optical intent and respects linked vs
  independent PB2 routing.
- F5 proves MAIN route/SRC effects, not just CONTROL frame bytes.
- README, HARDWARE_TEST, and Flipper sender docs/actions are updated.
- Focused simulator tests and RAM safety pass under `.venv_ep0`.
- Release build is produced only through the canonical V1.73 builder when the
  implementation is meant to publish a new release, and release identity docs
  are updated in the same change.

## Implementation Result

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
