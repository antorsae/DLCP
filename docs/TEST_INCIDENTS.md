# Test Incidents

Last updated: 2026-07-02
Scope: sanitized hardware and simulator incidents that must be promoted into
deterministic regressions or opt-in hardware gates.

## Evidence Policy

Raw hardware artifacts are local-only.  Do not commit or paste raw HID paths,
serial numbers, camera names, Flipper serial ports, raw `detect` output, raw
`identify-mains` output, raw `dlcp_diag.py --json`, media paths, or uncropped
LCD media.

Committed/shared incident evidence must use role labels such as `PB1/LEFT` and
`PB2/RIGHT`, redacted or hash-only identifiers, cropped LCD-only media when
media is needed, and stripped metadata.

## Incident Template

```text
Incident ID:
Date:
Firmware artifacts:
  MAIN:
  CONTROL:
Artifact-derived identity:
  MAIN:
  CONTROL:
Observed state:
  LCD rows:
  USB/HID enumeration:
  Audio state:
Operator actions:
Raw evidence:
Sanitized evidence:
Simulator reproducibility:
Regression or hardware gate:
Disposition:
```

## TR-20260702-001 Fable Confirmed V3.5/V1.73 Firmware Bugs

Incident ID: `TR-20260702-001`
Date: 2026-07-02

Firmware artifacts:

- MAIN: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL: `firmware/patched/releases/DLCP_Control_V1.73.hex`

Artifact-derived identity:

- MAIN: fixed canonical V3.5 rev `0x009B`, SHA-256
  `7238d08cacf32f25358cf1a83d86984cb7c1d454ce46051bafe56acc3eed1071`
- CONTROL: fixed canonical V1.73 rev `0x63`, build `20260702`, SHA-256
  `9a28543e99ff1806a470826283323e9438a29dd6a4aa6917a27152a1631c2ee1`

Observed state:

- LCD rows: not a single live observation; report covers confirmed simulator and
  static code paths.
- USB/HID enumeration: not involved.
- Audio state: duplicate MAIN wake and repeated fixed-input route churn can be
  audio-visible; no live audio evidence was collected in this pass.

Operator actions:

- Fable code review reported six behavior bugs in current V3.5/V1.73 source.
  The bugs were independently checked and implemented only on V3.5 MAIN and
  V1.73 CONTROL.

Raw evidence:

- Local chat/review transcript only; no raw hardware identifiers or media.

Sanitized evidence:

- `docs/FABLE_CONFIRMED_BUGS_20260702.md`
- `docs/FABLE_CONFIRMED_BUGS_20260702_IMPL.md`

Simulator reproducibility:

- Deterministic pre-fix focused run failed `27` nodes on old behavior, including
  duplicate wake canceling bring-up, channel-6 boot source mutating channel 5,
  repeated fixed-input `cmd 0x06` route churn, missing RX-ring prior-`GIE`
  structural guard, V3.5 identity committing at `BF/53`, and cold-WAITING use
  of ISR scratch `(Common_RAM + 24)`.
- FABLE-004 RX-ring/OERR and FABLE-006 WAITING scratch are instruction-window
  races. The current simulator cannot deterministically interrupt at the exact
  foreground instruction boundary, so closure is structural plus broad
  simulator regression coverage.

Regression or hardware gate:

- Deterministic regressions:
  `tests/sim/test_v35_duplicate_wake_idempotence.py`,
  `tests/sim/test_v35_boot_source_sanitizer.py`,
  `tests/sim/test_v35_cmd06_idempotence.py`,
  `tests/sim/test_v35_uart_rx_ring_oerr_race.py`,
  `tests/sim/test_v173_waiting_predicate_scratch.py`,
  and V3.5 rev16 additions in `tests/sim/test_v172_v33_diag_identity.py`.
- Focused post-fix gate: `25 passed in 30.30s`.
- Affected broad group: `339 passed in 1346.10s`.
- Release/preflight gate: `105 passed, 3 warnings in 60.06s`.
- RAM safety: `OK (main-v35, control-v173)`.
- Full simulator gate: `2175 passed, 2 skipped, 2 xfailed, 7 warnings in
  1610.69s`.
- Remaining hardware gates: live PB2 DOWN, audio routing, persistence, IR, and
  live CONTROL flashing remain required before hardware field closure.

Disposition:

- Fixed in MAIN V3.5 rev `0x009B` and CONTROL V1.73 rev `0x63` / build
  `20260702`. Live hardware was not run.

## TR-20260630-003 CONTROL Flash Relay Not Armed But Stream ACKs

Incident ID: `TR-20260630-003`
Date: 2026-06-30

Firmware artifacts:

- MAIN: failing path observed on pre-fix canonical V3.5; fixed in
  `firmware/patched/releases/DLCP_Firmware_V3.5.hex` rev `0x0099`
- CONTROL: old deployed V1.73 rev `0x5F` build `20260629` to target V1.73 rev
  `0x60` build `20260630`

Artifact-derived identity:

- MAIN: fixed canonical V3.5 rev `0x0099`, SHA-256
  `fcc882e9ef1ec7cd0c5923530cd7a8e4e63c893a02bf08e418b575fb0ca76e92`
- CONTROL: target payload CRC `0x2780`, stream length `0x77C0`

Observed state:

- LCD rows: normal app screen before flash; manual bootloader mode not confirmed
  for the failing app-mode run
- USB/HID enumeration: MAIN HID relay accepted host reports
- Audio state: not involved

Operator actions:

- Ran CONTROL flash through MAIN from app mode.  Stream reached 99-100 percent
  with `resp[0..3]=42 00 00 00`, then final `0x41` verify returned
  `41 11 00 00 00 00 00 00`.

Raw evidence:

- Local chat/operator trace with no raw HID path committed.

Sanitized evidence:

- `docs/CONTROL_FLASH_RELAY_HANDSHAKE_FAILURE.md`

Simulator reproducibility:

- Old-to-new app-mode simulation reproduced first-pass `41 11 00` with MAIN
  relay session clear and signature accumulator `0x0000`.  A continuous
  two-pass simulation failed both passes, so the reported real second-pass
  success remains a hardware/simulator-fidelity gap.
- Fixed V3.5 app-mode/unarmed simulation now returns `42 12 00 00` on the first
  `0x42` report; the repo flasher aborts before report 2.
- Full-chain simulated manual-bootloader flashes now pass for current-bad to
  fixed target and fixed-good to newer-good, including final `41 00 aa`, target
  application-window readback, and CONTROL release-metadata readback.  The sim
  fix required EUSART `RCREG` latch fidelity and 64-byte program erase rows.

Regression or hardware gate:

- Deterministic regressions:
  `tests/sim/test_dlcp_control_flash_safety.py::test_source_assembled_v35_unarmed_relay_rejects_first_42_report`,
  `tests/sim/test_dlcp_control_flash_safety.py::test_canonical_v35_unarmed_relay_rejects_first_42_report_after_release_build`,
  `tests/sim/test_dlcp_control_flash_safety.py::test_old_relay_false_ack_behavior_reproduces_with_temp_mutation`,
  `tests/sim/test_dlcp_control_flash_safety.py::test_full_chain_fixed_main_flashes_control_v173_through_real_bootloader`,
  and
  `tests/sim/test_dlcp_control_flash_safety.py::test_full_chain_fixed_main_flashes_newer_v173_through_real_bootloader`.
- Remaining hardware gate: live CONTROL flash confirmation through an explicit
  relay MAIN HID path after manual `UP+DOWN` bootloader entry.

Disposition:

- Fixed in MAIN V3.5 rev `0x0099` for simulator-backed firmware/flasher
  behavior.  Manual CONTROL bootloader entry remains the live flashing procedure
  unless app-mode handoff is separately validated; live hardware was not run for
  this fix.

## TR-20260630-001 V3.5 `chain_copy` TOS Rewrite Interrupt Safety

Incident ID: `TR-20260630-001`
Date: 2026-06-30

Firmware artifacts:

- MAIN: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL: not involved

Artifact-derived identity:

- MAIN: V3.5 EEPROM rev `0x0095` at fix time; current canonical MAIN is newer
- CONTROL: not involved

Observed state:

- LCD rows: not directly observable
- USB/HID enumeration: not involved
- Audio state: potential high-impact control-flow corruption if an interrupt
  landed during the descriptor-skip TOS rewrite window

Operator actions:

- None.  This was a structural simulator/source proof failure, not a live
  hardware observation.

Raw evidence:

- The previous strict xfail in
  `tests/sim/test_v34_v173_refactoring_contracts.py` documented that
  `chain_copy` rewrote `TOSL/TOSH` while post-GIE call sites existed.

Sanitized evidence:

- Current V3.5 source branches on prior `GIE`, masks only the TOS commit
  window on the GIE-enabled path, and restores `GIE` only if it was previously
  set.

Simulator reproducibility:

- Required deterministic regression:
  `tests/sim/test_v34_v173_refactoring_contracts.py::test_v35_chain_copy_tos_rewrite_masks_and_restores_prior_gie`

Regression or hardware gate:

- Structural source regression plus canonical V3.5 release build.  No hardware
  gate is required because the contract is PIC18 interrupt/TOS sequencing.

Disposition:

- Fixed in V3.5 rev `0x0095`.  The chain-copy strict xfail is retired for the
  current MAIN release line; the remaining xfail audit reports only the
  historical V3.4 boot-vector ABI xfail.

## TR-20260630-002 PB2 `Analogue 3` Row Mapped To Auto Detect

Incident ID: `TR-20260630-002`
Date: 2026-06-30

Firmware artifacts:

- MAIN: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL: `firmware/patched/releases/DLCP_Control_V1.73.hex`

Artifact-derived identity:

- MAIN: V3.5 EEPROM rev `0x0099` from canonical MAIN HEX
- CONTROL: V1.73 rev `0x60` build `20260630` from canonical CONTROL HEX

Observed state:

- LCD rows: `Input PB2:` / `Analogue 3` rendered correctly
- USB/HID enumeration: not involved
- Audio state: PB2 route intent, `B2/06` frame, and EEPROM encoding could be
  `0x00` Auto Detect instead of `0x03` Analogue 3

Operator actions:

- From linked PB2 (`Same as PB1`), press `UP` through the full PB2 input table
  and force settings save after each concrete selection.

Raw evidence:

- Full simulator gate failed
  `tests/sim/test_v173_multi_pb_input_selection.py::test_every_user_selected_concrete_pb2_source_saves_documented_encoding`
  with PB2 LCD on `Analogue 3` but `input_intent_pb2 == 0x00`.

Sanitized evidence:

- The PB2 visible-row mapper previously returned the cmd06 payload through the
  shared TX staging byte before copying it into durable PB2 intent.  V1.73 now
  stores the mapped PB2 intent directly and no longer copies from TX staging
  in the PB2 concrete-row commit path.

Simulator reproducibility:

- Required deterministic regressions:
  - `tests/sim/test_v173_multi_pb_input_selection.py::test_every_user_selected_concrete_pb2_source_saves_documented_encoding`
  - `tests/sim/test_v173_multi_pb_input_selection.py::test_bug_v173_unknown_raw_status_pb2_exact_label_to_cmd06_mapping`

Regression or hardware gate:

- Source-assembled simulator regressions plus canonical V1.73 release build.
  Live audio/persistence hardware gates are still required before field closure.

Disposition:

- Fixed in V1.73 rev `0x60`.  Focused PB2 all-row mapping subset passed:
  `10 passed in 122.44s`.

## TR-20260627-001 Stale Diagnostics MAIN Identity

Incident ID: `TR-20260627-001`
Date: 2026-06-27

Firmware artifacts:

- MAIN: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL: `firmware/patched/releases/DLCP_Control_V1.73.hex`

Artifact-derived identity:

- MAIN: V3.5 EEPROM rev `0x91` from canonical MAIN HEX
- CONTROL: V1.73 rev `0x57` build `20260627` from canonical CONTROL HEX

Observed state:

- LCD rows:
  - PB1 observed as malformed/stale `PB1 OK v330091` with row 1 `O1`
  - Expected healthy layout is `PB1 OK v3.5 0091` / `O1              `
- USB/HID enumeration: operator reported both MAIN units visible over USB
- Audio state: not the primary symptom

Operator actions:

- Navigate to CONTROL Diagnostics after flashing/current V3.5 + V1.73 work.

Raw evidence:

- Local-only chat/operator observation.  No raw HID paths or media committed.

Sanitized evidence:

- Role-only LCD text above.

Simulator reproducibility:

- Required deterministic regression:
  `tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_canonical_diag_entry_invalidates_stale_identity_cache`

Regression or hardware gate:

- Canonical simulator regression plus focused robustness gate in
  `docs/TEST_ROBUSTNESS_IMPL.md`.

Disposition:

- Guarded by canonical simulator regression.  Focused robustness gate passed
  (`55 passed in 75.48s`) and full simulator gate passed
  (`2082 passed, 2 skipped, 4 xfailed, 10 warnings in 1001.77s`).  Live
  hardware was not run in this docs/tests-only pass.

## TR-20260627-002 CONTROL LCD Corruption And Missing Filename

Incident ID: `TR-20260627-002`
Date: 2026-06-27

Firmware artifacts:

- MAIN: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL: `firmware/patched/releases/DLCP_Control_V1.73.hex`

Artifact-derived identity:

- MAIN: V3.5 EEPROM rev `0x91` from canonical MAIN HEX
- CONTROL: V1.73 rev `0x57` build `20260627` from canonical CONTROL HEX

Observed state:

- LCD rows:
  - Volume page observed with a leading space before `Volume`
  - Preset page observed as `Preset         B` with missing filename row
  - Diagnostics observed `PB2! X1`
- USB/HID enumeration: PB2 degraded or not fully healthy in Diagnostics
- Audio state: front-panel mute changed MAIN state, but IR control then stopped
  responding

Operator actions:

- Power on with both MAINs, use IR for power, press front-panel mute/preset
  actions, navigate to Preset and Diagnostics pages.

Raw evidence:

- Local-only chat/operator observation.  No raw HID paths or media committed.

Sanitized evidence:

- Role-only LCD text above.

Simulator reproducibility:

- Required deterministic regressions:
  - exact two-row LCD assertions in release-facing menu/Diagnostics tests
  - `tests/sim/test_preset_filename_lcd_spec.py::test_v173_v35_canonical_preset_lcd_suffix_and_row1_atomicity_matrix`
  - `tests/sim/test_hardware_state_test.py::test_identify_mains_fails_when_no_main_devices_visible`

Regression or hardware gate:

- Canonical simulator regressions plus opt-in role-safe hardware smoke in
  `docs/TEST_ROBUSTNESS_IMPL.md`.

Disposition:

- Guarded by exact LCD/preset filename/no-device simulator regressions.
  Focused robustness gate passed (`55 passed in 75.48s`) and full simulator
  gate passed (`2082 passed, 2 skipped, 4 xfailed, 10 warnings in 1001.77s`).
  Live hardware was not run in this docs/tests-only pass.
