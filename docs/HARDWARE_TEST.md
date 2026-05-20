# DLCP Hardware State-Test Runbook

## Scope

This document defines the real-hardware test strategy for DLCP state-transition
and control-path issues using:

- two MAIN units connected over USB HID
- the real CONTROL unit in the current-loop chain
- a Flipper (or equivalent) that can emit IR commands programmatically
- a USB camera aimed at the CONTROL LCD

This document complements [`docs/HARDWARE_LOOP.md`](HARDWARE_LOOP.md).

Use [`docs/HARDWARE_LOOP.md`](HARDWARE_LOOP.md) for:

- acoustic playback/capture
- sweep generation
- response analysis
- audio regression comparison

Use this document for:

- preset-switch state transitions
- mute/standby/wake timing interactions
- multi-MAIN synchronization
- real-hardware confirmation of simulator findings
- distinguishing simulator-model gaps from product bugs

## Purpose

The current delayed-switch work has reached the point where the remaining
questions are no longer just "does the UART traffic flow?" They are now about
end-to-end user-visible behavior:

- does a preset switch complete on both MAINs?
- does a follow-up `MUTE` actually mute both MAINs?
- does `STANDBY` actually drive both MAINs inactive?
- after wake, does CONTROL leave `Zzz...` and return to a usable display?
- are simulator failures real firmware bugs or harness/model artifacts?

This setup is strong enough to answer most of those questions on real hardware.

## Available Setup

Assumed hardware:

- one CONTROL unit with working LCD
- two MAIN units connected in the same real current-loop topology under test
- USB from host to each MAIN so they can be individually flashed and queried
- one programmable IR emitter (Flipper) aimed at CONTROL
- one USB camera pointed at the LCD

Assumed host capabilities:

- the host can enumerate multiple DLCP HID devices
- the host can address a specific MAIN by HID path
- the host can trigger named IR actions through the Flipper
- the host can capture stills or video frames from the LCD camera

## Canonical Environment

Use the repo virtual environment:

```bash
.venv_ep0/bin/python
```

Do not use system Python.

## What This Setup Can Prove

This setup can directly answer:

1. Whether a remaining simulator failure reproduces on real hardware.
2. Whether a failure is realistic remote use or only an extreme timing edge.
3. Whether CONTROL and the two MAINs converge to the same final state.
4. Whether wake/reconnect problems are user-visible LCD problems or only
   simulator state-model problems.
5. Whether a firmware change actually improves multi-unit behavior, not just
   simulator behavior.

This setup is especially good for timing sweeps such as:

- preset switch, then mute after `50/100/250/500/1000 ms`
- preset switch, then standby after `50/100/250/500/1000 ms`
- repeated `F1/F2` switching followed by mute
- standby/wake loops after a preset switch

## What This Setup Cannot Prove Alone

This setup does **not** fully replace the rust simulator or electrical
instrumentation.

It cannot directly prove:

- exact byte-level current-loop traffic without a line sniffer
- exact CONTROL internal RAM state without dedicated diagnostic firmware
- forced MSSP `SEN`/`PEN` fault handling on real hardware
- UART-ring overflow or parser-collision fault injection
- whether a hidden race is caused by physical line timing or by application
  state unless additional instrumentation is added

Therefore:

- use real hardware for end-to-end truth
- use the rust simulator for synthetic fault injection
- use a logic analyzer/current-loop sniffer only if byte-level transport proof
  becomes necessary

## Existing Repo Capabilities

The repository already provides the USB-side building blocks needed for a
real-hardware harness.

### MAIN flash / probe

- `scripts/dlcp_main_flash.py`
- `scripts/dlcp_preset.py`
- `scripts/dlcp_ep0_flash_probe.py`

Important property:

- MAIN tooling already supports multiple matching HID devices via `--list` and
  explicit `--path`
- this is required when two MAINs are connected simultaneously

### CONTROL flash through MAIN

- `scripts/flash_control_safe.sh`
- module: `dlcp_fw.flash.dlcp_control_flash`

Important property:

- CONTROL is flashed through the MAIN USB path using the main firmware's relay
  mechanism
- this means CONTROL test images can be deployed without a separate CONTROL USB
  cable

### Acoustic loop tooling

- `scripts/hardware_loop.py`

This remains the correct tool for sweep/audio regression work, but it is **not**
the primary entrypoint for the control/state-transition tests in this document.

### Implemented state-test helpers

- `scripts/hardware_lcd_probe.py`
- `scripts/hardware_flipper_ir.py`
- `scripts/hardware_state_test.py`

Important properties:

- `hardware_lcd_probe.py` captures repeated LCD stills and derives a consensus
  OCR result for the CONTROL display.
- `hardware_flipper_ir.py` sends named Hypex-profile RC5 actions through the
  live Flipper serial CLI transport.
- `hardware_state_test.py detect` inventories cameras, Flipper candidates, and
  visible DLCP HID devices.
- `hardware_state_test.py identify-mains --require-left-right` reads each
  visible MAIN over USB/EP0, captures the active-route RAM window, and
  classifies the units as `LEFT` or `RIGHT`.
- In the current two-MAIN wiring, `LEFT` is the PB1 unit attached directly to
  CONTROL, and `RIGHT` is the downstream PB2 unit attached to PB1 over the
  serial link.
- This role classification is the required pre-flash gate. Do not flash by
  assumed USB order.

## Preferred Test Split

Current state:

- deterministic rust-simulator tests and mocked unit tests for the
  hardware helper CLIs all live under `tests/sim/`
- files such as `test_hardware_loop.py` and `test_hardware_state_test.py` are
  **not** live-rig tests; they are unit tests around the helper code

Preferred structure moving forward:

- keep pure unit tests for hardware helper logic in `tests/sim/`
- keep rust-simulator wire/current-loop tests in `tests/sim/` and mark them
  `wire`
- add real live-rig tests under `tests/hardware/` when implemented and mark
  them `hardware`

Pytest policy:

- `@pytest.mark.wire`
  - means a simulator current-loop/wire-chain test
- `@pytest.mark.hardware`
  - means a live hardware test that touches the real rig
- live hardware tests are skipped by default
- enable them explicitly with `--run-hardware`

Recommended commands:

```bash
.venv_ep0/bin/python -m pytest tests/sim -m "wire" -q
.venv_ep0/bin/python -m pytest tests/sim -q
.venv_ep0/bin/python -m pytest tests -m hardware --run-hardware -q
```

This gives a clean answer to “what kind of test is this?” without mixing
simulator-only regressions and rig-dependent validation in the same lane.

## Core Test Principle

For the delayed-switch family of bugs, acceptance must be based on **observable
real state**, not only emitted commands.

The hardware harness should record four things on one timeline:

1. commanded action
   - IR `F1`, `F2`, `Mute`, `Standby`, `Wake`
2. CONTROL-visible state
   - LCD content from the camera
3. per-MAIN observed state
   - active preset
   - post-switch settle / reapply completion
   - availability over USB before and after standby
4. timestamps
   - action time
   - observation time
   - settle time

## Recommended Observation Model

### CONTROL observation

Primary source:

- camera aimed at the LCD
- helper: `scripts/hardware_lcd_probe.py` for tuned C920 capture plus repeated Vision OCR consensus

Minimal LCD classifications needed:

- `Volume`
- `Preset`
- `Zzz...`
- `WAITING FOR DLCP`
- `other/unknown`

At first, manual review of captured stills/video is acceptable.
Later, a narrow OCR/template classifier can be added.

### MAIN observation

Primary source:

- USB/HID probing per MAIN by explicit `--path`

Useful observations:

- device identity / HID path
- active preset over EP0
- whether a preset reapply completed
- whether the device is present/responding before and after wake

Important caveat:

- during real standby, USB may disappear or stop responding
- therefore standby entry should be judged primarily by LCD and post-wake
  reappearance, not only by live USB polling during sleep

## Recommended Action Model

Primary source:

- programmable IR via Flipper

The preferred real-hardware path for end-to-end acceptance is the same public
user path that real users trigger:

- `F1`
- `F2`
- `Mute`
- `Standby`
- `Wake`

Avoid using EP0-only preset switching for acceptance of CONTROL/MAIN sync. That
path is still useful for diagnostics, but it bypasses the real CONTROL command
path and can hide UI/sync issues.

## Concrete Smoke Tests

Use these commands as the minimum readiness gate before delayed-switch or
flash-validation work.

### 1. Detect the live setup

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py detect
```

Pass criteria:

- the intended LCD camera appears in `cameras`
- at least one usable Flipper transport candidate appears in `flipper`
- exactly two DLCP HID devices appear in `hid_devices`

### 2. Read both MAINs and classify LEFT/RIGHT

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
```

Pass criteria:

- exactly one MAIN is classified as `LEFT`
- exactly one MAIN is classified as `RIGHT`
- both entries include a stable HID `path`
- both entries expose route labels consistent with the deployment

This command is also the USB memory-read smoke test because it reads:

- `active_flags`
- active preset state
- active config name
- route RAM bytes for each MAIN

### 3. Capture the CONTROL LCD and verify OCR consensus

```bash
.venv_ep0/bin/python scripts/hardware_lcd_probe.py --captures 5
```

Pass criteria:

- the generated `summary.json` contains a stable `consensus.line1`
- the generated `summary.json` contains a stable `consensus.line2`
- the captured stills are readable enough to distinguish `Volume`, `Active: A`
  or `Active: B`, `Zzz...`, and `WAITING FOR DLCP`

### 4. Exercise one public IR preset-switch roundtrip

`hardware_state_test.py` now has a built-in Flipper Zero sender path. When a
single Flipper serial port is visible, no manual command template is needed.

Canonical direct sender:

```bash
.venv_ep0/bin/python scripts/hardware_flipper_ir.py --action F2
```

This sender uses the Hypex RC5 profile:

- address `0x10`
- `F1` -> `0x38`
- `F2` -> `0x39`
- `Mute` -> `0x35`
- `Power` (legacy toggle) -> `0x32`
- `Standby` (endpoint) -> `0x3A`
- `Wake` (endpoint) -> `0x3B`

Endpoint requirement:

- `Standby`/`Wake` endpoint commands require CONTROL firmware `V1.64b` or newer.
- On older CONTROL firmware, only `Power` toggle (`0x32`) is recognized.

Canonical roundtrip command:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py ir-preset-roundtrip \
  --action F2 \
  --expected-preset B
```

Optional fallback for non-canonical transports:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py ir-preset-roundtrip \
  --action F2 \
  --expected-preset B \
  --ir-command-template 'python3 /path/to/send_flipper_ir.py --action {action}'
```

Pass criteria:

- the Flipper command returns success
- the post-action LCD consensus is `Volume` / `Active: B`
- the `LEFT` MAIN reports preset `B`
- the `RIGHT` MAIN reports preset `B`

### V1.71/V3.2 ledger hardware phase runner

The implementation-bug ledger gates below can also be printed or run through
one operator wrapper:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py
```

Default mode is dry-run: it prints every live-rig phase, required environment
variables, and manual preconditions.  To run one phase after positioning the
rig, pass `--execute --phase <name>`.  Multi-phase `--execute` runs pause
before each phase by default so the operator can reposition the CONTROL page or
swap CONTROL firmware between phases; use `--no-pause` only when an external
script handles that positioning.  Examples:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --list --bug BUG-DIAG-02

.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --preflight --phase all

.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --preflight --phase all \
  --report-json artifacts/probes/v171_v32_ledger_gate/preflight.json

.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --execute --phase identity

.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --execute --pause --phase diag-pb1 --phase diag-button-actions --phase diag-ir-actions

.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --execute --pause --bug BUG-DIAG-02
```

`--list` is a pure discovery mode.  It prints all phase, alias, and bug
selectors plus the resolved selected phase list; it does not run pytest or
probe hardware.

`--preflight` is non-destructive.  It does not send IR, press buttons, switch
presets, or enter standby; it only checks visible MAIN HID devices, camera
inventory, and Flipper serial discovery for the selected phases.  For phases
that need LCD OCR, preflight requires either an explicit
`DLCP_HW_CAMERA_SELECTOR` or at least one camera that is not an obvious host
camera such as a MacBook camera, Desk View, or screen capture device.

`--report-json <path>` writes the selected phases, exact commands, preflight
inventory/failures, and executed phase return codes to a machine-readable JSON
file.  Use it for live closure runs so the ledger can cite a durable artifact
instead of only terminal scrollback.

`--bug BUG-...` expands a ledger bug ID to the phase set listed in
`docs/IMPL_V171_V32_BUG_LEDGER.md`, de-duplicating phases when multiple bugs
are selected.

`diag-button-actions` is a convenience alias that expands to the PB1 and PB2
per-page physical-button gates (`diag-buttons-pb1`, `diag-buttons-pb2`).
`diag-ir-actions` similarly expands to the PB1 and PB2 per-page IR gates
(`diag-ir-pb1`, `diag-ir-pb2`).  The full Diagnostics IR gates intentionally
set `DLCP_HW_IR_PROFILE=HYPEX` because they exercise Hypex-profile preset
shortcuts (`F1`/`F2`) and V1.71 explicit `STANDBY`/`WAKE` endpoints.  Use the
receiver sweep or legacy IR stress gates for standard RC5 profile evidence.

The phase runner covers the release identity gate, physical front-panel A/B,
physical front-panel standby/wake, IR preset/mute/standby/wake timing checks,
the no-OCR IR receiver sweep diagnostic, V1.6b-vs-V1.71 real-IR stress,
PB1 Diagnostics layout, PB1/PB2 static
Diagnostics convergence, Diagnostics-page physical LEFT/RIGHT responsiveness,
and Diagnostics-page IR volume/mute/preset/standby/wake dispatch.

### 5. Use role-safe flashing only

Before any MAIN flash, first run:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py identify-mains --require-left-right
```

Then extract the matching HID path and pass it explicitly to the flash tool.

Rule:

- flash the `LEFT` image or `LEFT` routing only to the HID path reported as
  `LEFT`
- flash the `RIGHT` image or `RIGHT` routing only to the HID path reported as
  `RIGHT`

For release wrappers that currently accept only `--path`, the operator must use
the role-derived `path` from `identify-mains`. This is mandatory for PB1/PB2
setups because USB enumeration order is not a safe proxy for physical position.

### 6. Confirm V3.2 release identity and A/B filenames

After flashing V3.2 with baked LX521.4 captures, run the MAIN-only identity
gate.  It can be run with one MAIN connected at a time, matching the
one-board-at-a-time release-flash workflow:

```bash
DLCP_HW_RELEASE_IDENTITY_CONFIRM=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_v32_release_identity_and_ab_filename_ram \
  --run-hardware
```

Pass criteria:

- HID reports V3.2.
- runtime EEPROM identity/revision matches
  `firmware/patched/releases/DLCP_Firmware_V3.2.hex`.
- preset A active filename RAM and HID cmd `0x03` readback are
  `LX521.4 22MG10F-v5`.
- preset B active filename RAM and HID cmd `0x03` readback are
  `LX521.4 22MG10F-v7`.

### 7. Confirm physical front-panel A/B selection

This is the live confirmation for the original front-panel A/B report.  It is
not an EP0 switch and not an IR `F1`/`F2` shortcut.

Run it twice, once after selecting A and once after selecting B from CONTROL's
physical Preset screen:

```bash
DLCP_HW_FRONT_PANEL_PRESET_CONFIRM=1 \
DLCP_HW_EXPECTED_PRESET=A \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram \
  --run-hardware

DLCP_HW_FRONT_PANEL_PRESET_CONFIRM=1 \
DLCP_HW_EXPECTED_PRESET=B \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_preset_selection_updates_mains_and_filename_ram \
  --run-hardware
```

Pass criteria:

- CONTROL LCD is either `Volume` / `Active: A|B` or `Preset` / `Active: A|B`.
- both MAINs report the selected active preset.
- both MAINs' active filename RAM matches the baked release capture:
  A = `LX521.4 22MG10F-v5`, B = `LX521.4 22MG10F-v7`.

### 8. Confirm physical front-panel STBY/WAKE from Volume

This is the live confirmation for BUG-STDBY-01.  It exercises the real
front-panel STBY button path from the Volume screen; it is not an IR command
and not synthetic GPIO injection.

Start from CONTROL `Volume` / `Active: A|B`, then run:

```bash
DLCP_HW_FRONT_PANEL_STBY_WAKE_CONFIRM=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_manual_front_panel_standby_wake_from_volume \
  --run-hardware -s
```

Operator actions:

1. When the test prints `press physical STBY now`, press the CONTROL
   front-panel `STBY` button once.
2. Wait for the test to observe standby evidence.
3. When the test prints `press physical STBY again now to wake`, press
   front-panel `STBY` again.

Pass criteria:

- standby evidence appears from MAIN state or expected temporary USB absence;
- after wake, both MAINs are active and unmuted on the original preset;
- CONTROL LCD returns to `Volume` / `Active: A|B`;
- CONTROL does not remain on `WAITING FOR DLCP`.

## Immediate Stop Conditions

Do not proceed to flashing or delayed-switch validation if either of these is
true:

- `detect` shows fewer than two DLCP HID devices
- `detect` does not show the intended external LCD camera

Those are host-visibility problems, not firmware results. Fix the USB/camera
setup first, then rerun the smoke tests.

## Minimal Test Matrix

Start with these scenarios.

### A. Baseline preset-switch sanity

1. Boot into stable display.
2. Send `F2`.
3. Wait for settle.
4. Confirm:
   - LCD returns to usable display
   - both MAINs report preset `B`

Repeat with `F1`.

### B. Preset then mute timing sweep

For each delay in `50, 100, 250, 500, 1000 ms`:

1. Send `F2`.
2. After the delay, send `Mute`.
3. Wait for settle.
4. Confirm:
   - LCD is usable
   - both MAINs remain on preset `B`
   - mute state is consistent with user intent

Then repeat with a second `Mute` to test unmute.

Interpretation:

- failure only at `<= 50-100 ms` suggests a stress edge
- failure at `>= 250 ms` is realistic remote-use behavior

### C. Preset then standby timing sweep

For each delay in `50, 100, 250, 500, 1000 ms`:

1. Send `F2`.
2. After the delay, send `Standby`.
3. Confirm LCD reaches `Zzz...`.
4. After a fixed dwell, send `Wake`.
5. Confirm:
   - LCD leaves `Zzz...`
   - CONTROL returns to a usable display
   - both MAINs become reachable again
   - both MAINs preserve the expected preset

Interpretation:

- simulator-only red, hardware green: simulator/harness wake model gap
- hardware red at moderate delays: real firmware bug

### D. Rapid-toggle stress

1. Send `F1/F2/F1/F2/...` with a fixed short delay.
2. End on `F2`.
3. Confirm:
   - both MAINs end on preset `B`
   - follow-up `Mute` still works

This is partly stress, but it is still useful because it approximates repeated
remote presses.

### D2. Real IR receiver sweep diagnostic

Use this before the V1.6b-vs-V1.71 comparison if the rig appears to ignore all
IR commands.  It does not require LCD OCR.  It sends a small Hypex + standard
RC5 action matrix and records MAIN-visible volume, preset, mute, active, input,
and setup/profile deltas.

```bash
DLCP_HW_IR_RECEIVER_SWEEP=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_ir_receiver_profile_sweep_records_any_state_change \
  --run-hardware
```

Default action list:

```text
VOL_UP,VOL_DOWN,STD_VOL_UP,STD_VOL_DOWN,F2,F1,MUTE,MUTE,STD_MUTE,STD_MUTE
```

Override with `DLCP_HW_IR_SWEEP_ACTIONS=...` when narrowing the test.  Artifacts
are written under
`artifacts/probes/hardware_state_test/pytest/ir_receiver_sweep/.../result.json`.

Pass criterion: at least one action changes MAIN-visible state.  A failure here
means the current hardware session has not established any working RC5
receive/dispatch path, so the legacy stress comparison cannot yet distinguish a
V1.71 regression from a sender/profile/rig issue.

### D3. Real IR legacy stress, V1.6b vs V1.71

This is the hardware companion to the BUG-IR-01 simulator parity test.  It
uses legacy RC5 profile commands generated by `scripts/hardware_flipper_ir.py`
(`VOL_UP`/`VOL_DOWN`/`MUTE`/`POWER` for Hypex profile, or
`STD_VOL_UP`/`STD_VOL_DOWN`/`STD_MUTE`/`STD_POWER` for standard RC5 profile),
not the V1.71-only endpoint shortcuts.  Run it twice after the receiver sweep
has shown at least one real IR command changes MAIN-visible state:

1. Flash stock CONTROL V1.6b and establish the baseline gate.
2. Flash CONTROL V1.71 and run the same gate.

Use the safe CONTROL flasher for both payloads after placing CONTROL in
manual `UP + DOWN` bootloader mode.  Power-cycle while holding `UP + DOWN`
for at least 6 seconds and do not touch `SELECT`; the bootloader accepts the
combo only after 11 stable delay loops, about 5.5 seconds.  If the LCD returns
to `Volume`, CONTROL is still in the app and the flash attempt should be
restarted after another bootloader-entry attempt.

```bash
scripts/flash_control_safe.sh \
  --hex 'firmware/stock/control/DLCP Control Firmware V1.6b.hex' \
  --path '<MAIN path connected to CONTROL>' \
  --live-timeout-s 10

scripts/flash_control_safe.sh \
  --hex firmware/patched/releases/DLCP_Control_V1.71.hex \
  --path '<MAIN path connected to CONTROL>' \
  --live-timeout-s 10
```

```bash
DLCP_HW_IR_LEGACY_STRESS=1 \
DLCP_HW_EXPECTED_CONTROL_VERSION=V1.6b \
DLCP_HW_IR_PROFILE=HYPEX \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume \
  --run-hardware

DLCP_HW_IR_LEGACY_STRESS=1 \
DLCP_HW_EXPECTED_CONTROL_VERSION=V1.71 \
DLCP_HW_IR_PROFILE=HYPEX \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_ir_legacy_command_stress_from_volume \
  --run-hardware
```

If the CONTROL setup byte is known or suspected to be the standard RC5 profile
instead of the Hypex profile, rerun the same gate with
`DLCP_HW_IR_PROFILE=STANDARD`.  Standard profile maps to RC5 address `0x00`
with `Vol+ = 0x10`, `Vol- = 0x11`, `Mute = 0x0D`, and `Power = 0x0C`.

Each pytest run writes
`artifacts/probes/hardware_state_test/pytest/legacy_ir_stress/.../result.json`.
The result records the requested `DLCP_HW_EXPECTED_CONTROL_VERSION`, the
expected CONTROL hex path, static release metadata, payload CRC, and
payload/application/bootloader SHA-256 hashes.  Use those fields when attaching
the V1.6b and V1.71 run artifacts to `BUG-IR-01`; they prove which firmware
image the live run was intended to validate, even though the CONTROL version is
not directly readable over the MAIN relay during the test.

Pass criteria:

- volume up/down changes both MAIN logical volume readbacks and restores them
- MUTE toggles on and off on both MAINs
- POWER enters standby and a second POWER wakes both MAINs
- after wake, CONTROL's LCD returns to a usable `Volume` screen

The gate intentionally uses only IR commands that should work on both V1.6b
and V1.71.  It does not use the V1.71-only explicit preset or standby/wake
endpoint shortcuts.

### E. Reconnect soak

1. Switch to preset `B`.
2. Run repeated standby/wake cycles.
3. After each wake:
   - confirm LCD becomes usable
   - confirm both MAINs are reachable
   - confirm preset remains `B`
   - confirm `Mute` and `Unmute` still work

## Five High-Impact Live Tests

These are the first five live-rig tests worth implementing because they answer
the current open questions in the delayed-switch branch with the least
ambiguity.

### 1. Preset-switch convergence baseline

Goal:

- prove one `F1` or `F2` request converges on both MAINs and the LCD

Implementation:

- add a hardware test that sends one IR preset command
- poll both MAINs by explicit HID path until both report the target preset
- capture repeated LCD OCR until the display returns to a usable `Volume` /
  `Active: A|B` state
- record left-settle time, right-settle time, and LCD recovery time

Why it matters:

- this is the foundation for all other live-rig tests
- if the simplest preset switch does not converge cleanly, the higher-stress
  cases are not interpretable

Implemented paths:

- CLI:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py preset-convergence --action F2
```

- Optional live pytest:

```bash
.venv_ep0/bin/python -m pytest -q tests/hardware/test_live_state_transitions.py \
  --run-hardware -k preset_convergence
```

### 2. Rapid-toggle final-state convergence

Goal:

- reproduce the user-reported “a few remote switches later things desync”
  symptom with realistic button timing

Implementation:

- add a timed action-sequence runner that emits `F1/F2/F1/F2`
- run it with inter-press delays such as `100 ms`, `250 ms`, and `500 ms`
- require final convergence to the last requested preset on both MAINs
- require the LCD to recover and a follow-up probe to succeed on both MAINs

Why it matters:

- this is the closest direct test of the real field complaint
- it catches split-brain outcomes where PB1 and PB2 disagree after bursty use

Implemented paths:

- CLI:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py rapid-toggle-convergence \
  --sequence F1,F2,F1,F2 \
  --inter-press-ms 250
```

- Optional live pytest:

```bash
.venv_ep0/bin/python -m pytest -q tests/hardware/test_live_state_transitions.py \
  --run-hardware -k rapid_toggle_convergence
```

### 3. Preset then mute/unmute timing sweep

Goal:

- determine whether a follow-up mute shortly after a switch is ignored,
  delayed, or leaves the chain in the wrong state

Implementation:

- add a hardware timing-sweep test: `F2`, then `MUTE` after
  `50/100/250/500/1000 ms`
- repeat `MUTE` again to test unmute
- at minimum require:
  - both MAINs remain reachable
  - both MAINs stay on the expected preset
  - the LCD remains usable before and after mute/unmute
- if a stable MAIN-side mute bit becomes available through EP0, include that as
  the state assertion

Why it matters:

- this is the best direct live-rig test for the “goes silent / mute ignored”
  symptom

Implemented paths:

- CLI:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py preset-mute-timing-sweep \
  --delays-ms 50,100,250,500,1000
```

- Optional live pytest:

```bash
.venv_ep0/bin/python -m pytest -q tests/hardware/test_live_state_transitions.py \
  --run-hardware -k preset_mute_timing_sweep
```

### 4. Preset then standby/wake timing sweep

Goal:

- determine whether delayed-switch traffic interferes with standby entry or
  reconnect after wake

Implementation:

- add a timing-sweep test: `F2`, then `STANDBY` after `50/100/250/500/1000 ms`
- require standby entry confirmation:
  - preferred: LCD OCR reaches `Zzz...`
  - guarded fallback (for very dim standby backlight): consecutive LCD `None/None`
    probes after a known-good pre-standby LCD read, with supporting standby
    evidence (for example HID not reachable during sleep)
- wake after a fixed dwell with `WAKE`
- wake validation is two-phase:
  - Phase A (`FUNCTIONAL_WAKE_TIMEOUT` on failure): both MAINs are visible and
    responsive, active, and converged to the expected preset
  - Phase B (`ROLE_DECODE_UNSTABLE` on failure): decoded LEFT/RIGHT identity
    stabilizes for consecutive polls
- path->role mapping captured before standby is used only as temporary identity
  continuity during wake grace when raw decode is `UNKNOWN`; live decode is
  still required to pass Phase B
- require:
  - LCD leaves `Zzz...`
  - CONTROL returns to a usable screen
  - both MAINs reappear over USB
  - both MAINs preserve the expected preset

Why it matters:

- this is the strongest real-hardware discriminator between firmware bug and
  simulator wake-model gap

Implemented paths:

- CLI:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py preset-standby-wake-timing-sweep \
  --delays-ms 50,100,250,500,1000 \
  --standby-dwell-s 1.0 \
  --wake-phase-a-timeout-s 15 \
  --wake-phase-b-timeout-s 25 \
  --wake-role-stable-polls 3
```

Wake reliability defaults to bounded endpoint retries (`--wake-max-attempts 3`,
`--wake-retry-delay-s 1.0`) so missed IR packets do not fail immediately. On
wake failure, the harness emits a structured tail of recent poll samples
(`--wake-diagnostics-tail`, default `30`) including visibility, role decode,
sticky-role usage, active/preset bits, and read errors.

Optional strict LCD mode (disable dim-backlight fallback and require literal
`Zzz...`):

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py preset-standby-wake-timing-sweep \
  --delays-ms 50,100,250,500,1000 \
  --standby-dwell-s 1.0 \
  --no-standby-blank-fallback
```

- Optional live pytest:

```bash
.venv_ep0/bin/python -m pytest -q tests/hardware/test_live_state_transitions.py \
  --run-hardware -k preset_standby_wake_timing_sweep
```

For the V1.71/V3.2 bug-ledger `BUG-IR-02` closure, run the live pytest through
`scripts/run_v171_v32_ledger_hardware_gate.py --bug BUG-IR-02` or set
`DLCP_HW_REQUIRE_STANDBY_LCD_ZZZ=1`; that makes the pytest wrapper pass
`--no-standby-blank-fallback` and requires literal `Zzz...` LCD evidence before
WAKE.

### 5. Reconnect and responsiveness soak

Goal:

- catch low-probability desync or “MAIN stops reacting after a while” failures

Implementation:

- build a looped scenario of:
  - preset switch
  - standby
  - wake
  - follow-up action such as mute or another preset switch
- run 25 to 100 iterations
- after each iteration require:
  - LEFT reachable
  - RIGHT reachable
  - same final preset on both
  - usable LCD
- stop on first failure and retain artifacts for that iteration

Why it matters:

- this is the best practical liveness test for multi-unit convergence under
  normal user behavior rather than synthetic fault injection

Implemented paths:

- CLI:

```bash
.venv_ep0/bin/python scripts/hardware_state_test.py reconnect-responsiveness-soak \
  --iterations 5 \
  --standby-dwell-s 1.0
```

- Optional live pytest:

```bash
.venv_ep0/bin/python -m pytest -q tests/hardware/test_live_state_transitions.py \
  --run-hardware -k reconnect_responsiveness_soak
```

## Recommended Implementation Order

Implemented in this order:

1. preset-switch convergence baseline
2. rapid-toggle final-state convergence
3. preset then mute/unmute timing sweep
4. preset then standby/wake timing sweep
5. reconnect and responsiveness soak

Reason:

- the first two give the quickest signal on whether the branch still has a real
  preset-convergence problem
- the middle two directly target the user-visible regressions
- the soak is highest value after the shorter tests are stable enough to trust
  as building blocks

## How To Distinguish Real Bug vs. Harness Issue

Use this decision rule.

### If the simulator fails, but hardware passes

Classify as:

- likely simulator/harness issue

Examples:

- the simulator remains at `Zzz...`, but real hardware wakes normally
- the simulator loses sync after standby, but both real MAINs converge correctly

### If both simulator and hardware fail the same user-visible scenario

Classify as:

- likely real firmware bug

Especially strong when:

- failure occurs at `>= 250 ms`
- failure is reproducible across repeated runs

### If only extreme timing fails on hardware

Classify as:

- likely edge-case race

Still important, but not equivalent to a normal-use product break unless field
evidence shows users can hit it regularly.

### If hardware outcome depends on MAIN position

Classify as:

- likely chain propagation / downstream forwarding issue

Example:

- MAIN0 tracks correctly but MAIN1 does not

### If both MAINs are correct, but CONTROL LCD is wrong

Classify as:

- likely CONTROL/UI/reconnect issue

## Practical Limits Of Real-Hardware Coverage

Real hardware can settle the current delayed-switch questions well, but not all
future robustness work.

Keep these boundaries:

- real hardware for end-to-end truth
- rust simulator for synthetic bus/parser faults
- optional future sniffer for current-loop byte capture

Do not try to infer stuck-`PEN` or stuck-`SEN` conclusions from this hardware
setup alone.

## Harness Architecture

The dedicated hardware-state harness now exists and is separate from the
acoustic loop tool.

Implemented entrypoints:

- `scripts/hardware_state_test.py`
- `scripts/hardware_lcd_probe.py`
- `scripts/hardware_flipper_ir.py`

Responsibilities:

1. enumerate MAIN HID devices and assign stable labels
2. flash MAIN and CONTROL images by explicit HID path
3. trigger Flipper IR actions
4. capture LCD frames/stills/video
5. poll per-MAIN post-action state
6. write one merged timeline JSON artifact per run

Artifact layout:

```text
artifacts/probes/hardware_state_test/
├── ir_preset_roundtrip/<timestamp>/
│   ├── baseline/
│   │   └── lcd/<timestamp>/
│   ├── after/
│   │   └── lcd/<timestamp>/
│   └── result.json
└── hardware_lcd/
    └── runs/<timestamp>/
        ├── capture_*.jpg
        └── summary.json
```

## Initial Operator Workflow

Use this flow for PB1/PB2 validation and any role-safe flash session.

1. Run `scripts/hardware_state_test.py detect` and confirm the camera, Flipper
   transport, and two DLCP HID devices are visible.
2. Run `scripts/hardware_state_test.py identify-mains --require-left-right` and
   record the returned `LEFT.path` and `RIGHT.path`.
3. Flash desired MAIN builds only by explicit `--path`, using the path that
   matches the intended `LEFT` or `RIGHT` role.
4. Flash desired CONTROL build through the `LEFT`/PB1 MAIN path unless a test
   explicitly requires otherwise.
5. Run `scripts/hardware_lcd_probe.py` once to confirm the LCD camera/OCR setup
   is readable.
6. Trigger one scripted IR scenario through Flipper, either directly or via
   `scripts/hardware_state_test.py ir-preset-roundtrip`.
7. Poll both MAINs after each scenario.
8. Save:
   - HID paths used
   - firmware versions used
   - IR sequence and timing
   - LCD images/video
   - per-MAIN observed preset/state
9. Compare outcome with simulator expectations.

## Current Best Use Of This Setup

For the delayed-switch remediation specifically, this hardware setup is already
good enough to answer the most important open question:

- is the remaining standby/wake failure a real firmware bug or a simulator/harness
  wake-model problem?

It is also good enough to answer:

- are the remaining failures realistic remote-use issues or only extremely tight
  timing edges?

That makes this setup the right next validation layer before adding more
simulator complexity.

## Re-flash pop monitoring (V3.2+ no-pop flash entry)

Validates the V3.2 `flash_entry_quiet_shutdown` path against the pre-V3.2
single-Tcy `RESET` POP described in
[`docs/NO_POP_FIRMWARE_FLASH.md`](NO_POP_FIRMWARE_FLASH.md).

This rig has **no automated audible-pop detector** — the
`hardware_loop.py` audio-loopback tooling is for sweep/regression work,
not transient transient-impulse classification.  The check is
human-in-the-loop: an operator listens to the speaker while a re-flash
cycle is triggered and reports pop / no-pop.

### Prerequisites

- both MAINs flashed with `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
  (per [`docs/V32_RELEASE.md`](V32_RELEASE.md))
- speakers connected at normal listening volume (not muted, no
  external pad)
- a quiet listening environment so a low-amplitude click is audible

### Operator walk-through (~3 minutes per MAIN)

For each MAIN (run twice — left, then right):

1. Confirm the unit is playing audio (or at least driving a quiet
   non-zero coefficient through the DSP).  A unit at preset zero with
   no input is still a valid baseline because the pop comes from the
   amp pin tristate transition, not the audio content.
2. Trigger a re-flash:
   ```bash
   .venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --left
   ```
   (or `--right`)
3. Listen at the speaker as `HID cmd 0x40` lands.  Expected behavior
   on V3.2 with `EEPROM 03/02/33`: no audible pop — at most a single
   very-quiet click at the moment of `RESET`, similar in level to the
   normal standby transition.
4. Wait for the unit to re-enumerate and the flasher to print the
   post-flash device info.

Repeat the cycle once more on the same MAIN to confirm the result is
reproducible.  Two cycles per MAIN (= 4 total flash operations across
the pair) is the minimum acceptance gate for this work.

### Pass criteria

| Cycle | Expected | Failure interpretation |
|---|---|---|
| Cycle 1, MAIN0 | no pop | If pop: `flash_entry_quiet_shutdown` did not run, or version marker not bumped — verify EEPROM `03/02/33` via `dlcp_main_flash.py --info-only` after flash |
| Cycle 2, MAIN0 | no pop | If first was clean but second is loud: `flash_entry_quiet_shutdown` may be aborting via the bounded I2C-timeout path on a wedged secondary device |
| Cycle 1+2, MAIN1 | no pop | Same interpretations apply per-PB — the helper runs identically on both MAINs |

If any of the four cycles produces an audible pop comparable to the
pre-V3.2 baseline, the no-pop work has regressed; capture the EEPROM
version byte and the most recent `dlcp_main_flash.py` log and review
against the spec's "What NOT To Do" section.

### Power-cut abort recovery (optional)

To verify the EEPROM-marker-first ordering, power-cut the unit ~50 ms
into the new Phase A (i.e. during the 100 ms `timer3_blocking_delay`
between rail drop and the final amp gate).  Power back on — the unit
must drop straight into the bootloader because
`main_flash_service_46de` already committed `EEPROM[0xFF] = 0` before
the helper started.  Verify the bootloader can still accept a
subsequent flash stream by running `scripts/dlcp_v32_release_flash.py`
again; the unit should re-enumerate and re-flash cleanly.

This abort/recovery test is operator-discretion — it requires power
control on the unit and isn't part of the routine 2-cycle gate.

## Diagnostics page (V1.71 + V3.2 Layer 5)

Validates the V1.71 CONTROL Diagnostics page against V3.2 MAIN counters.

> **Updated 2026-05-09 (BUG-DIAG-01/02 fix).**  Pre-2026-05-04 versions
> of this runbook described the Diagnostics page as a single
> two-row Diagnostics(2) screen (`1:I D S B R A P` / `2:I D S B R A P`),
> framed it as a "Task #22 discriminator" (gpsim two-MAIN echo-loop),
> and expected both rows to render counter values within ~2 seconds.
> Both framings have been retracted.  V1.71 Tier-1 (per
> `docs/V32_DIAG_TIER1_SPEC.md` and `dlcp_control_v171.asm:4805+`)
> split that single-screen layout into per-PB pages at states 4
> (PB1) and 5 (PB2), each rendering one of four `PBn` / `n/a` /
> `OK` / `PBn:` layouts.  Current V1.71/V3.2 firmware must update the
> active PB page from a static wait.  LEFT/RIGHT cycling is no longer an
> accepted workaround for persistent `PBn` / `n/a`; after about 1 second
> on the page, `n/a` is acceptable only when that PB is genuinely absent
> or silent.

### Prerequisites

- both MAINs flashed with `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
  (use `scripts/dlcp_v32_release_flash.py --left` / `--right` per
  [`docs/V32_RELEASE.md`](V32_RELEASE.md))
- CONTROL flashed with `firmware/patched/releases/DLCP_Control_V1.71.hex`
  (use `scripts/flash_control_safe.sh --hex ...` per
  [`docs/V171_RELEASE.md`](V171_RELEASE.md))
- both MAINs cold-booted at least once after flash so the V3.2 RCON-gated
  cold-init has cleared the diag block

### Operator walk-through (5 minutes)

V1.71 Tier-1 (per `docs/V32_DIAG_TIER1_SPEC.md` and
`dlcp_control_v171.asm:4805+`) splits the diagnostics page into a
6-state menu ring with one PB per page:

```
Volume(0) → Preset(1) → Input(2) → Setup(3) → PB1 Diag(4) → PB2 Diag(5) → Volume(0)
```

Each PB Diag page is its own 16x2 LCD screen.  Layout dispatches by
health (per `dlcp_control_v171.asm:3484+,3603+`):

| Layout | Row 0 | Row 1 |
|---|---|---|
| Absent (PB has never replied) | `PBn` (+ 13 spaces) | `n/a` (+ 13 spaces) |
| Healthy (all 7 runtime counters + abnormal reset flags V/W/X == 0; the POR `O` reset-cause flag may be 1 on normal cold boot) | `PBn` (+ 13 spaces) | `OK` (+ 14 spaces) |
| Degraded (1..9 non-zero cells) | `PBn:` + up to 4 cell entries | up to 5 cell entries |
| Overflow (10..11 non-zero cells) | `PBn:` + 4 cell entries (full) | 5 cell entries + `..` overflow indicator |

Walk-through:

1. Power-cycle both MAINs and CONTROL.  Wait for CONTROL to reach
   the Volume screen.
2. From Volume, press the physical `RIGHT` touch button FOUR times to navigate
   `Volume(0) → Preset(1) → Input(2) → Setup(3) → PB1 Diag(4)`.
3. Observe the LCD for about 1 second.  The first frame after the
   4-RIGHT navigation may briefly show:
   ```
   PB1
   n/a
   ```
   It must then update to `PB1` / `OK` (all-zero counters) or
   `PB1:` + cell entries (some non-zero counters).  If it stays
   `PB1` / `n/a`, PB1 is absent/silent or the diagnostics reply path
   is broken.
4. While still on PB1 Diag, verify normal controls remain responsive:
   volume up/down, mute, preset A/B, standby, and wake IR actions must
   still dispatch.  LEFT/RIGHT physical navigation must not feel stalled.
5. To check PB2: press the physical `RIGHT` touch button once more (PB1 Diag → PB2 Diag,
   state 4 → 5).  PB2's page renders the same `PBn` / `n/a` /
   `OK` / `PBn:` layouts independently.  Wait about 1 second and
   require the same static update behavior.
6. Press the physical `LEFT` touch button repeatedly to return to Volume.
   CONTROL's diag query path is page-local, so leaving the page
   stops all diag traffic.

### Pass criteria

Operator runs the walk-through twice (once for PB1 at state 4,
once for PB2 at state 5):

| What | Expected | Failure attribution |
|---|---|---|
| Row 0 renders `PB1` (PB1 page) or `PB2` (PB2 page) prefix | yes | If wrong literal appears: V1.71 CONTROL not flashed correctly, or operator did not navigate to the correct state (4 or 5) |
| Row 1 may briefly show `n/a`, then reaches `OK` or cell entries within about 1 second of static wait | yes | If row 1 stays `n/a`: that PB is genuinely absent/silent, that PB's MAIN doesn't recognize cmd 0x21 (V3.2 not flashed), or there is a real reply-path bug |
| Row 0 flips to `PBn:` + cell entries when at least 1 counter is non-zero | yes | If row 0 stays bare `PBn` literal with non-zero counter activity expected: V1.71 layout dispatch broken |
| Physical LEFT/RIGHT navigate away from each PB page promptly | yes | If CONTROL hangs or misses the touch: diagnostics foreground service is starving normal button scan |
| Volume, mute, preset, standby, and wake IR actions still dispatch while on PB1/PB2 pages | yes | If actions are delayed or ignored: diagnostics foreground service is starving normal UI/IR dispatch |
| No effect on Volume/Preset/Input/Setup operation after leaving Diagnostics | yes | Diag traffic is page-local; if other features regress, send_query may be leaking outside the screen body |

Automated opt-in physical-button responsiveness gate:

```bash
DLCP_HW_LAYER5_AT_DIAG=1 \
DLCP_HW_LAYER5_BUTTON_ACTIONS=1 \
DLCP_HW_EXPECTED_DIAG_PAGE=PB1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_manual_diagnostics_buttons_remain_responsive \
  --run-hardware -s
```

Run this twice: once from PB1 Diagnostics with
`DLCP_HW_EXPECTED_DIAG_PAGE=PB1`, and again from PB2 Diagnostics with
`DLCP_HW_EXPECTED_DIAG_PAGE=PB2`.  The test prompts for a physical RIGHT press,
then asks the operator to navigate back to the same PB page, then prompts for a
physical LEFT press.

Automated opt-in IR dispatch gate:

```bash
DLCP_HW_LAYER5_AT_DIAG=1 \
DLCP_HW_LAYER5_IR_ACTIONS=1 \
DLCP_HW_EXPECTED_DIAG_PAGE=PB1 \
DLCP_HW_IR_PROFILE=HYPEX \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_diagnostics_page_ir_actions_dispatch_on_real_silicon \
  --run-hardware
```

Run this twice: once after manually navigating CONTROL to PB1 Diagnostics with
`DLCP_HW_EXPECTED_DIAG_PAGE=PB1`, and again after manually navigating CONTROL
to PB2 Diagnostics with `DLCP_HW_EXPECTED_DIAG_PAGE=PB2`.  Wait about
1 second on the target page before starting each run.  The test sends
Hypex-profile real Flipper IR volume, mute, `F1`/`F2` preset, explicit
`STANDBY`, and explicit `WAKE` actions from that page, so it will leave
Diagnostics after the standby/wake portion and may change the active preset
during the run.  It asserts both MAINs wake and CONTROL's LCD returns to
`Volume`.

### Counter semantics

| LCD char | Meaning |
|---|---|
| `I` | I2C transport faults (`i2c_byte_tx` ACKSTAT + `coeff_write_pen_timeout`) |
| `D` | DSP-fault episodes (`dsp_fault_flags.6` 0→1 transition) |
| `S` | Standby/shutdown dispatches |
| `B` | Bring-up / wake dispatches |
| `R` | Recovery branch entries |
| `A` | AN0-triggered standby events |
| `P` | RA1 edge events |

Counter values render as:

| Char | Meaning |
|---|---|
| ` ` (space) | counter is zero (no events) |
| `1`..`9` | counter values 1..9 |
| `A`..`E` | counter values 10..14 |
| `+` | counter is saturated at 0x0F (15+ events) |

V3.2 hardens this further with a self-healing upper bound: if a
counter cell ever holds a value above 0x0F (RAM corruption from FSR
overrun, uninitialized cells on a non-BOR reset, stray write into the
diag block, etc.), the next `diag_inc_sat` invocation clamps the cell
back to 0x0F before any other check fires.  Combined with the
`andlw 0x0F` mask in the cmd 0x21/0x22 send helper
(`dlcp_main_v32.asm:9299-9301`), the diag page can no longer get
stuck rendering non-physical glyphs from a corrupted in-RAM cell.

### Triggering counter increments

Some counters are easy to bump on the rig:

- **`B`** (bring-up): power-cycle the unit; `B` should bump by 1 on
  the affected PB
- **`S`** (standby): IR `STANDBY` then IR `WAKE`; `S` and `B` both
  bump by 1
- **`A`** (AN0): pull the AN0 line low to simulate the standby
  trigger (rig-specific)

The remaining counters (`I`, `D`, `R`, `P`) need a fault-injection
harness to bump and aren't part of the basic operator walk-through.

### What this validates (post BUG-DIAG-01/02)

This walk-through validates that V1.71 CONTROL is correctly parsing
the V3.2 BF/2N diag-reply burst without depending on user navigation
to advance the diagnostics cadence.  It also validates that the
Diagnostics foreground loop continues to service normal UI work:
physical navigation and decoded IR commands for volume, mute, preset,
standby, and wake.

If both per-PB pages converge to `OK` / `PB1:`+cells / `PB2:`+cells
(or stable `PBn` / `n/a` for a genuinely silent PB) after a static
wait, V1.71 + V3.2 are operating correctly.  If `PB2` / `n/a` is stuck
on the PB2 page (state 5) while the PB1 page (state 4) converges, that
points at a real V3.2 PB2 reply-path, V1.71 parser-target bug, or PB2
wiring/absence issue.

## WAITING FOR DLCP recovery (V1.71 operator reset, 2026-04-21)

Validates the V1.71 operator-escape hatch for the
`WAITING FOR DLCP` wedge that can occur after STDBY+WAKE when
V3.2 MAIN fails to re-emit its sentinel-clearing burst.  See
[`docs/V171_RELEASE.md`](V171_RELEASE.md) §"What's New vs V1.64b"
for the feature definition and
[`docs/V32_MAIN_HANG_HARDENING_PLAN.md`](V32_MAIN_HANG_HARDENING_PLAN.md)
§"MAIN Wake-Path Sentinel Re-Emit" for the MAIN-side root cause.
The 2026-05-09 V3.2 ledger gate also covers the related duplicate-standby
case where two `B0/03/00` frames arrive before MAIN's shutdown dispatcher:
duplicate standby must preserve the pending shutdown event instead of leaving
the logical gate closed with hardware latches still enabled.

### Prerequisites

- CONTROL flashed with V1.71 (per
  [`docs/V171_RELEASE.md`](V171_RELEASE.md))
- both MAINs flashed with V3.2 (per
  [`docs/V32_RELEASE.md`](V32_RELEASE.md))
- PICkit 5 attached to CONTROL as the ICSP recovery path during
  first testing.  The escape uses the PIC18 `RESET` instruction,
  which is a software-MCLR equivalent: PC→0, BSR→0, SP cleared, no
  flash or EEPROM writes.  PICkit is independent of the firmware
  state — it can always reflash the CONTROL via the ICSP header
  even if a runtime path becomes pathological.

### Operator walk-through — inducing the wedge

1. Power-cycle the full chain.  Wait for CONTROL to reach the
   Volume screen.
2. Press `STDBY` on the CONTROL panel.  LCD shows `Zzz...`.
3. Press `STDBY` again (= WAKE).  LCD may briefly show
   `WAITING FOR DLCP` and then recover to Volume — this is the
   healthy path.  If CONTROL reaches Volume within ~2 s, the wedge
   did not reproduce on this cycle.  Retry steps 2-3 several times.
4. When CONTROL stays on `WAITING FOR DLCP` for > 5 s with no
   recovery, the wedge has reproduced.  Confirm both MAINs are
   still alive on USB by running
   `scripts/dlcp_main_flash.py --info-only` in a host terminal —
   both PBs should report version `V3.2` and route.

### Operator walk-through — recovery

5. Once CONTROL has been stuck on `WAITING FOR DLCP` for at least
   ~10 s (the grace window), press the front-panel `RIGHT` button.
   The IR remote does NOT trigger this escape — the WAITING loops
   sample only the front-panel button GPIOs (PORTA/PORTC) via
   `button_scan_debounce`, not the IR dispatch path that fills
   `ir_decoded_cmd`.
6. CONTROL should immediately reset — LCD blanks briefly, then the
   boot sequence re-runs showing the firmware version string and
   then either the Volume screen (if MAIN now answers the fresh
   full-sync burst) or `WAITING FOR DLCP` again (if MAIN is still
   silent).  In the second case, repeat step 5 — each reset
   restarts the full boot handshake.
7. If repeated resets do not clear `WAITING FOR DLCP`, the wedge is
   not on CONTROL's side and the MAIN-side fail-safe work in
   `docs/V32_MAIN_HANG_HARDENING_PLAN.md` §"MAIN Wake-Path Sentinel
   Re-Emit" is required.  Escalate rather than keep resetting.

### Pass criteria

| What | Expected | Failure attribution |
|---|---|---|
| Wedge reproduces on some cycle | yes (within ~20 cycles) | If wedge never reproduces, V3.2 wake path may already be fixed — revisit the open item in `V32_MAIN_HANG_HARDENING_PLAN.md` §3b |
| First RIGHT press < 10 s ignored | yes (grace gate) | If RIGHT press during early boot resets CONTROL, grace counter may be misconfigured — inspect `v171_waiting_grace_count_lo`/`_hi` and `V171_WAITING_GRACE_THRESHOLD_HI` |
| First RIGHT press > 10 s triggers reset | yes (visible LCD blank + re-boot) | If the button does nothing: button_scan_debounce path is broken, or the MAIN is responding and CONTROL already exited WAITING in the iteration between button presses |
| LEFT press works symmetrically with RIGHT | yes | If only RIGHT works, button-bit mapping regressed (should be 0x9A.5 and 0x9A.4) |
| ICSP recovery still available via PICkit 5 | yes | If PICkit can no longer talk to the unit at all, the cause is independent of this firmware path (cabling / ICSP header). The soft `RESET` instruction does not write flash or EEPROM and cannot itself disable ICSP. |

### Notes

- The button bitmap at `0x9A` is an edge latch: holding RIGHT or
  LEFT through the grace boundary may not fire the reset at the
  exact threshold.  Release and re-press if the first press after
  ~10 s seems ignored (tracked as codex LOW on `HEAD=2a07c02`,
  Task #76).
- A soft-reset CONTROL rejoins the chain as if just powered on:
  MAIN state is unaffected.  Audio on MAIN should continue
  uninterrupted during the CONTROL reset window.  If audio cuts,
  something other than the CONTROL WAITING path wedged.
- There is no sim test for this path; the validation loop is
  exclusively hand-traced source review + codex review + this
  operator walk-through.  Tracked gap; adding a rust-simulator behavioral
  test that drives button pins in the WAITING state is an open
  workstream.

## SRC4382 Auto Detect Acoustic Gate

This closes the hardware side of `BUG-SRC4382-AD-01` after the simulator has
proved the SRC4382 route/TAS3108 contract and the reduced Auto Detect polling
cadence.  The live check is intentionally acoustic because the previous bad
audio observation was caused by speaker misconnection; the gate now verifies
the corrected speaker path, the rev `0x6E` fixed-digital route-priming fix,
and future route/TAS regressions.

### Prerequisites

- CONTROL flashed with canonical V1.71.
- both MAINs flashed with canonical V3.2.
- known audio source available on at least one fixed digital input and through
  Auto Detect; if possible, exercise `S/PDIF`, `USB Audio`, `AES`, and
  `Optical` individually.
- operator has verified the speaker wiring and has enough low-band content or
  measurement to catch route/TAS audio-path regressions.

### Procedure

1. Start on a fixed digital input with a known preset and volume.  Confirm
   playback has normal low-band output.
2. Switch to Auto Detect and confirm the same source is selected and playback
   still has normal low-band output.
3. Leave Auto Detect and select each available fixed digital source.  None may
   be silent, and each must retain normal low-band output.
4. While playing, exercise volume, mute, preset A/B, standby/wake, and explicit
   input selection.  CONTROL must stay responsive.  Watch the Volume-screen
   A/B badge as well; current simulator coverage proves steady idle should not
   rewrite that LCD cell repeatedly, so any visible pulsing should be recorded
   as hardware/UI evidence rather than attributed to SRC4382 traffic.
5. Run the SRC4382 soak from `docs/SRC4382_AUTODETECT_POLLING_SPEC.md` or an
   equivalent operator soak: at least 30 minutes Auto Detect no-source and at
   least 1 hour fixed-input playback.  There must be no UI stall and no
   unexplained `I`/`R` growth.  Record PB1/PB2 `I`/`R` diagnostics before and
   after the soak so any growth can be attributed instead of inferred.
6. Record the manual evidence using
   `docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md`, then record the manual
   confirmation.

### Manual evidence checklist

When reporting results without running the pytest hardware gate, fill the
tracked template at `docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md` so
`BUG-SRC4382-AD-01` can be closed from a concrete operator record.  Save the
completed report as an artifact, for example:

```text
artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md
```

The ledger `DONE:` line should reference that artifact path and a concrete
`PASS` verdict; weak free-form notes are not enough for closure.

The minimum closure evidence is a concrete dated run record with a date-like
and time-like timestamp, source/input, preset, volume, and low-band check
material filled in, a `pass` verdict with all required yes/no fields passing,
soak durations meeting the stated thresholds, current release SHA256 hashes,
concrete PB1/PB2 `I`/`R` before/after snapshots, and no unexplained `I`/`R`
growth.  Any `I`/`R` counter growth must include a concrete explanation.  Also record whether the
Volume-screen A/B badge pulsed or otherwise looked like abnormal LCD refresh.
`n/a` is acceptable only for optional captures.
Validate the completed artifact before closing the ledger item:

```bash
.venv_ep0/bin/python scripts/validate_src4382_manual_evidence.py \
  artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md
```

Then confirm the artifact summary marks `BUG-SRC4382-AD-01` ready for a ledger
update.  A valid manual report is accepted even when the live pytest closure
report is absent; an invalid report is printed as `manual_evidence_failed`
with the validator errors listed inline:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --summarize-artifacts --require-all-ready \
  --report-json artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json
```

### Pytest recording command

```bash
DLCP_HW_SRC4382_AD_ACOUSTIC_CONFIRM=1 \
DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK=1 \
DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK=1 \
DLCP_HW_SRC4382_USER_ACTIONS_OK=1 \
DLCP_HW_SRC4382_SOAK_OK=1 \
.venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_src4382_autodetect_acoustic_manual_confirmation \
  --run-hardware
```

Equivalent ledger-runner selector:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --execute --bug BUG-SRC4382-AD-01
```
