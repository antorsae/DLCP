# Test Incidents

Last updated: 2026-06-30
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

## TR-20260630-001 V3.5 `chain_copy` TOS Rewrite Interrupt Safety

Incident ID: `TR-20260630-001`
Date: 2026-06-30

Firmware artifacts:

- MAIN: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`
- CONTROL: not involved

Artifact-derived identity:

- MAIN: V3.5 EEPROM rev `0x0095` from canonical MAIN HEX
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

- MAIN: V3.5 EEPROM rev `0x0095` from canonical MAIN HEX
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
