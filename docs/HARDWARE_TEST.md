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

## Preferred Test Split

Current state:

- deterministic simulator tests, gpsim tests, and mocked unit tests for the
  hardware helper CLIs all live under `tests/sim/`
- files such as `test_hardware_loop.py` and `test_hardware_state_test.py` are
  **not** live-rig tests; they are unit tests around the helper code

Preferred structure moving forward:

- keep pure unit tests for hardware helper logic in `tests/sim/`
- keep gpsim wire/current-loop tests in `tests/sim/` and mark them `wire`
- add real live-rig tests under `tests/hardware/` when implemented and mark
  them `hardware`

Pytest policy:

- `@pytest.mark.wire`
  - means a gpsim current-loop/wire-chain test
- `@pytest.mark.hardware`
  - means a live hardware test that touches the real rig
- live hardware tests are skipped by default
- enable them explicitly with `--run-hardware`

Recommended commands:

```bash
.venv_ep0/bin/python -m pytest tests/sim -m "wire" -q
.venv_ep0/bin/python -m pytest tests/sim -m "gpsim and not wire" -q
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
  gpsim wake-model gap

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
This is the live-rig confirmation that distinguishes a true firmware
issue from the gpsim harness's two-MAIN echo-loop modeling limit
(currently quarantined under Task #22).

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

1. Power-cycle both MAINs and CONTROL.  Wait for CONTROL to reach
   the Volume screen.
2. From Volume, press the IR `RIGHT` key twice to navigate
   `Volume(0) → Preset(1) → Diagnostics(2)`.
3. Observe the LCD.  Expected initial render with no fault history:
   ```
   1:I D S B R A P
   2:I D S B R A P
   ```
   (counter chars are spaces when the counter is zero)
4. Wait ~2 seconds.  Both rows should refresh — `1:` and `2:` rows
   show the live counter values polled from each PB.
5. Press the IR `LEFT` key twice to return to Volume.  CONTROL's
   diag query path is page-local, so leaving the page stops all
   diag traffic.

### Pass criteria

| What | Expected | Failure attribution |
|---|---|---|
| Both rows render `1:` and `2:` prefix | yes | If only `1:` appears: V1.71 CONTROL not flashed correctly |
| `1:` shows counter chars or `n/a` | yes | If `1:n/a` permanently: PB1 MAIN doesn't recognize cmd 0x21 (V3.2 not flashed) |
| `2:` shows counter chars or `n/a` | yes | If `2:n/a` permanently: PB2 MAIN doesn't recognize cmd 0x21, OR Task #22 reproduces on hardware |
| LEFT exits the page cleanly | yes | If CONTROL hangs: violates Layer 1 bounded-TX guarantee |
| No effect on Volume/Preset/Input/Setup operation | yes | Diag traffic is page-local; if other features regress, send_query may be leaking outside the screen body |

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

### Resolves which Task #22 question

If the operator walk-through shows `2:I D S B R A P` (or the same
counter values as PB1 with PB2-specific values) within ~2 seconds
of entering the page, the Task #22 quarantined sim failures are
**gpsim-only** — no firmware bug.  Lifting the 4 xfail markers in
`tests/sim/test_v171_v32_layer5_diag_chain.py` should be paired with
a harness-level investigation rather than a firmware change.

If the operator walk-through shows `2:n/a` permanently while `1:` shows
live counters, the Task #22 sim failures **reproduce on hardware** —
the V1.71 parser or the V3.2 reply path has a real bug that needs a
firmware fix.
