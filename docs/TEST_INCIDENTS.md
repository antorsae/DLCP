# Test Incidents

Last updated: 2026-06-27
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
