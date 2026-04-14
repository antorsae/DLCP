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
- real-hardware confirmation of gpsim findings
- distinguishing simulator-model gaps from product bugs

## Purpose

The current delayed-switch work has reached the point where the remaining
questions are no longer just "does the UART traffic flow?" They are now about
end-to-end user-visible behavior:

- does a preset switch complete on both MAINs?
- does a follow-up `MUTE` actually mute both MAINs?
- does `STANDBY` actually drive both MAINs inactive?
- after wake, does CONTROL leave `Zzz...` and return to a usable display?
- are gpsim failures real firmware bugs or simulator/harness artifacts?

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

1. Whether a remaining gpsim failure reproduces on real hardware.
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

This setup does **not** fully replace gpsim or electrical instrumentation.

It cannot directly prove:

- exact byte-level current-loop traffic without a line sniffer
- exact CONTROL internal RAM state without dedicated diagnostic firmware
- forced MSSP `SEN`/`PEN` fault handling on real hardware
- UART-ring overflow or parser-collision fault injection
- whether a hidden race is caused by physical line timing or by application
  state unless additional instrumentation is added

Therefore:

- use real hardware for end-to-end truth
- use gpsim for synthetic fault injection
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
- `Standby` / `Wake` -> `0x32` (toggle semantics)

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

- gpsim-only red, hardware green: simulator/harness wake model gap
- hardware red at moderate delays: real firmware bug

### D. Rapid-toggle stress

1. Send `F1/F2/F1/F2/...` with a fixed short delay.
2. End on `F2`.
3. Confirm:
   - both MAINs end on preset `B`
   - follow-up `Mute` still works

This is partly stress, but it is still useful because it approximates repeated
remote presses.

### E. Reconnect soak

1. Switch to preset `B`.
2. Run repeated standby/wake cycles.
3. After each wake:
   - confirm LCD becomes usable
   - confirm both MAINs are reachable
   - confirm preset remains `B`
   - confirm `Mute` and `Unmute` still work

## How To Distinguish Real Bug vs. Harness Issue

Use this decision rule.

### If gpsim fails, but hardware passes

Classify as:

- likely simulator/harness issue

Examples:

- gpsim remains at `Zzz...`, but real hardware wakes normally
- gpsim loses sync after standby, but both real MAINs converge correctly

### If both gpsim and hardware fail the same user-visible scenario

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
- gpsim for synthetic bus/parser faults
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
9. Compare outcome with gpsim expectations.

## Current Best Use Of This Setup

For the delayed-switch remediation specifically, this hardware setup is already
good enough to answer the most important open question:

- is the remaining standby/wake failure a real firmware bug or a gpsim/harness
  wake-model problem?

It is also good enough to answer:

- are the remaining failures realistic remote-use issues or only extremely tight
  timing edges?

That makes this setup the right next validation layer before adding more
simulator complexity.
