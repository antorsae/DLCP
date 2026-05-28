# V3.2 Release Workflow

## Scope

This is the operator runbook for the recommended MAIN deployment as of
2026-04-21.

- recommended MAIN release: `firmware/patched/releases/DLCP_Firmware_V3.2.hex`
- recommended CONTROL release: `firmware/patched/releases/DLCP_Control_V1.71.hex`
  (see [`docs/V171_RELEASE.md`](V171_RELEASE.md) for the matching CONTROL flow)
- canonical MAIN build path: `scripts/build_v32_release.py` (bumps the EEPROM revision byte, then rebuilds the same canonical hex)
- recommended flashing path: use `scripts/dlcp_v32_release_flash.py`, which
  bakes preset A/B captures into canonical `V3.2.hex` at flash time
- active implementation bugs for the V1.71/V3.2 pair are tracked in
  [`docs/IMPL_V171_V32_BUG_LEDGER.md`](IMPL_V171_V32_BUG_LEDGER.md)
- Diagnostics counter fault-injection closure is tracked separately in
  [`docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`](V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
  and
  [`docs/IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`](IMPL_V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)

V3.2 supersedes V3.1 for two-MAIN chains. The headline change is the
async delayed-preset-switch remediation (see
[`docs/V28_DELAYED_SWITCH_REMEDIATION_PLAN.md`](V28_DELAYED_SWITCH_REMEDIATION_PLAN.md))
plus the MAIN-side counters that drive the V1.71 CONTROL Diagnostics page
(see [`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`](V163B_DIAGNOSTICS_MENU_SPEC.md)).

Non-canonical local experiment images (e.g. `DLCP_Firmware_V3.2.lst`,
`DLCP_Firmware_V3.2.cod`) are gpasm byproducts and not part of this
release workflow.

## Current Validation Status (2026-05-23)

The current canonical release identities are:

- MAIN: `V3.2 / rev 0x6E`
- CONTROL: `V1.71 / rev 0x35 / build 20260528`

Current local non-hardware verification:

- `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q` ->
  previous dedicated simulator gate `1067 passed, 1 skipped, 7 warnings in 702.71s`
- `.venv_ep0/bin/python -m pytest tests -n 16 -q` ->
  `1081 passed, 18 skipped, 10 warnings in 393.86s`

The rev `0x6E` MAIN includes the SRC4382 Auto Detect cadence candidate,
source-loss debounce, and fixed-digital SRC route priming from
`docs/SRC4382_AUTODETECT_POLLING_SPEC.md`.  It is ready for targeted operator
hardware retest, but the active ledger still requires structured live-rig
evidence before final closure.

Diagnostics counter matrix status: the full displayed counter matrix in
[`docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`](V171_V32_DIAG_FAULT_INJECTION_MATRIX.md)
now has simulator coverage for every displayed row without `gap`, `partial`,
`PB1-only`, source-hook-only, seeded-render-only, or navigation-driven rows.
`P` is explicitly simulator-only PORTA-edge coverage and remains
hardware-realistic not-applicable until PIC18F2455 RA1 analog masking is
modeled.  The bug-ledger audit and live-rig evidence remain separate final
release requirements.

The historical 2026-04-22 hardware issue for this pair was originally seen on:

- then-current MAIN revision: `V3.2 / rev 0x53`
- then-current CONTROL revision: `V1.71 / rev 0x19`
- reproduced symptom: after `STDBY -> WAKE`, CONTROL could remain on
  `WAITING FOR DLCP` while both MAINs were already awake and visible

The source tree now carries simulator regressions for the wake/reconnect
contract, including duplicate standby-frame idempotence on MAIN, plus the
active V1.71/V3.2 bug ledger.  Live hardware confirmation is still required
before the ledger rows can be marked `done`.  See
[`docs/analysis/V171_V32_STDBY_WAKE_WAITING_REAL_HW_2026-04-22.md`](analysis/V171_V32_STDBY_WAKE_WAITING_REAL_HW_2026-04-22.md)
and [`docs/IMPL_V171_V32_BUG_LEDGER.md`](IMPL_V171_V32_BUG_LEDGER.md).

## What's New vs V3.1

- async delayed preset switch (preset_job state machine) avoids the
  V3.1 sync-write hangs on long preset apply sequences
- 7 saturating-byte diagnostic counters (I, D, S, B, R, A, P) plus the RA1
  edge-detect shadow at `0x2E5..0x2EC`; the full runtime/reset diagnostics
  block spans `0x2E5..0x2F0`
- `cmd 0x21` reply burst — 7 frames `BF/21..27`, one counter per frame
  in the data byte's low nibble; consumed by the V1.71 CONTROL
  Diagnostics screen
- pop-free flash entry — the HID `cmd 0x40` re-flash trigger now
  routes through `flash_entry_quiet_shutdown` (DSP digital mute,
  secondary-device rail drop, graceful LAT pin drop, 100 ms timer3
  settle) before the bootloader-entry `RESET`.  Suppresses the
  audible POP that pre-V3.2 builds emit at re-flash time.  See
  [`docs/NO_POP_FIRMWARE_FLASH.md`](NO_POP_FIRMWARE_FLASH.md) for
  the spec and [`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md)
  §"Re-flash pop monitoring" for the operator validation
  walk-through.  The EEPROM version marker stays in the
  `0x03, 0x02, 0xNN` V3.2 lineage and now increments on each canonical
  release build.
- **Tier-1 reset-cause classification (landed 2026-04-20)** — 4
  RAM flag cells at `0x2ED..0x2F0` are populated at cold-init from
  the RCON snapshot: POR, BOR (Brown-Out), WDT, SW-reset (panic /
  bootloader hand-off).  Exactly one flag is set to 1 per session.
  See [`docs/V32_DIAG_TIER1_SPEC.md`](V32_DIAG_TIER1_SPEC.md).
- **Tier-1 chain `cmd 0x22` reset-flags reply burst** —
  4 frames `BF/28..BF/2B`, low-nibble flag value.  V1.71 CONTROL
  fires this ONCE per Diagnostics-page entry (the flags don't
  change within a session).  Older MAINs (≤ rev 0x36) emit one
  stray `0x00` ACK byte and CONTROL drops it harmlessly.
- **Tier-1 HID `cmd 0x44` diag snapshot** — host
  retrieval path that bypasses the chain entirely.  Returns an
  11-byte payload (length byte = `0x0B`): 7 runtime counters + 4
  reset-cause flags.  Use `scripts/dlcp_diag.py` (Phase 2.4) for
  operator-friendly enumeration of all attached MAINs; raw cmd
  0x44 is also reachable via any HID tool that can issue 64-byte
  reports to the DLCP HID interface.

Counter survival: ALL diag cells (runtime counters + reset-cause
flags) are unconditionally cleared at every cold-init — re-flash via
bootloader gives a clean counter slate (operator request 2026-04-20,
locked into the V3.2 Tier-1 lineage).  Cross-session count preservation
requires EEPROM-backed counters (Tier-2 deferred work, see
V32_DIAG_TIER1_SPEC.md §"Open questions").

## Required Local Inputs

Keep the captured preset files under the ignored local artifact
directory:

- `artifacts/LX521.4/LX521.4_22MG10F-v5.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v5.json`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.json`

The `.json` sidecars preserve the config-name metadata used by the
flasher when it finalizes the active filename slot after flashing.

## Flash Commands

PB1 (left):

```bash
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --left
```

PB2 (right):

```bash
.venv_ep0/bin/python scripts/dlcp_v32_release_flash.py --right
```

What this does:

1. overlays preset A and preset B into the target MAIN image using the
   version-aware flash bases for `V3.2`
2. reads version + EEPROM revision from both the target hex and the
   selected device, warning if the connected device is already at the
   same or newer firmware identity
3. if `--path` is omitted, auto-selects the target only when exactly
   one connected MAIN already reports the requested uniform route
   (`all L` for `--left`, `all R` for `--right`)
4. flashes the resulting app image over USB HID
5. finalizes the active config filename over the stock filename path
6. applies the requested all-channel route policy
7. prints before/after device information so the flashed version,
   config name, and channel mapping are visible in one command

The canonical builder is transactional: if `gpasm` fails, the source
EEPROM revision byte is rolled back and the existing canonical hex is
left untouched.

Equivalent advanced form:

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py \
  --hex firmware/patched/releases/DLCP_Firmware_V3.2.hex \
  --capture-a artifacts/LX521.4/LX521.4_22MG10F-v5.bin \
  --meta-a artifacts/LX521.4/LX521.4_22MG10F-v5.json \
  --capture-b artifacts/LX521.4/LX521.4_22MG10F-v7.bin \
  --meta-b artifacts/LX521.4/LX521.4_22MG10F-v7.json \
  --all-ch L
```

## Quick Checks

Read the current device state without flashing:

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py --info-only
```

Read the current preset state without switching:

```bash
.venv_ep0/bin/python scripts/dlcp_preset.py --info-only
```

These checks are useful after each PB flash so the installed version,
active config, routing, and active preset are visible before any
acoustic testing.

After flashing V3.2, run the MAIN identity/A-B filename gate:

```bash
DLCP_HW_RELEASE_IDENTITY_CONFIRM=1 \
  .venv_ep0/bin/python -m pytest -q \
  tests/hardware/test_live_state_transitions.py::test_live_v32_release_identity_and_ab_filename_ram \
  --run-hardware
```

If validating settings preservation, record the pre-flash logical volume low
byte, input byte, and setup/profile byte (`ram_0x0B8`) first, then run:

```bash
DLCP_HW_RELEASE_SETTINGS_CONFIRM=1 \
DLCP_HW_EXPECTED_VOLUME_LOW=<pre_flash_low> \
DLCP_HW_EXPECTED_INPUT=<pre_flash_input> \
DLCP_HW_EXPECTED_SETUP_PROFILE=<pre_flash_profile> \
  .venv_ep0/bin/python -m pytest -q -s \
  tests/hardware/test_live_state_transitions.py::test_live_v32_release_flash_preserves_expected_user_settings \
  --run-hardware
```

After pairing with V1.71 CONTROL, select A and B from the physical
front-panel Preset screen and run the front-panel confirmation for
each target:

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

## CONTROL Pairing

V3.2 MAIN is designed to pair with V1.71 CONTROL.  Earlier CONTROL
releases (V1.41..V1.64b) will continue to drive V3.2 MAIN for basic
volume/preset/input/setup operation, but the V1.71-specific features
do not light up:

- **Diagnostics page** — V1.71 only.  V1.64b and earlier render `n/a`
  permanently because they don't know cmd 0x21 / `BF/21..27`.
- **Layer 1 bounded TX** — V1.71 only; earlier releases retain the
  V1.6b unbounded TX busy-wait that can hang on a stuck TX ring.
- **Layer 2 one-frame-per-trigger full-sync** — V1.71 only; reduces
  burst-rate amplification under reconnect/full-sync churn.

For new deployments, flash V1.71 CONTROL alongside V3.2 MAIN.  For
existing deployments running V1.64b, V3.2 MAIN is a drop-in MAIN-only
upgrade if the operator does not need the new Diagnostics screen.

## Compatibility Matrix

| MAIN | CONTROL | Notes |
|---|---|---|
| V3.2 | V1.71 | recommended; full Layer 5 Diagnostics + Layer 1/2 hardening |
| V3.2 | V1.64b | basic operation works; no Diagnostics; Layer 1 unbounded |
| V3.2 | V1.63b | basic operation works; no Diagnostics; Layer 1 unbounded |
| V3.2 | V1.62b | basic operation works; no Diagnostics; Layer 1 unbounded |
| V2.x | V1.71 | basic operation works; Diagnostics shows `n/a` (V2.x has no counters) |

## Verification

Sim coverage for the V3.2 + V1.71 combination is in:

- `tests/sim/test_v32_layer5_diag_counters.py` (Phase A — MAIN counters)
- `tests/sim/test_v171_layer5_diag_page.py` (Phase B — CONTROL page)
- `tests/sim/test_v171_v32_layer5_diag_chain.py` (Phase C — wire-chain)
- `tests/sim/test_v171_v32_standby_reconnect.py` (standby/wake reconnect gate)
- `tests/sim/test_v28_wire_delayed_switch_repros.py` (delayed-switch
  remediation regressions)

See [`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md) §"Diagnostics page" and
[`docs/IMPL_V171_V32_BUG_LEDGER.md`](IMPL_V171_V32_BUG_LEDGER.md) for the
live-rig confirmation gates.  For Diagnostics counter-specific release closure,
also require the separate fault-injection matrix and implementation plan linked
above.

## Release Notes

- Canonical `V3.2.hex` is the recommended MAIN release when deployed
  with baked preset captures (this doc + V1.71 CONTROL).
- `V3.1.hex` remains a viable fallback for single-PB installs that
  don't need the async preset switch fix or the Diagnostics page.
- `V2.8` remains the legacy binary-patched fallback for users who
  explicitly want the last patch-on-stock MAIN.
- Real-hardware acoustic comparison of release and suspect local
  images is covered separately in
  [`docs/HARDWARE_LOOP.md`](HARDWARE_LOOP.md).

## Current Note

- Canonical V3.2 release builds now carry a monotonic EEPROM revision
  marker. Treat the HID `V3.2` label and the EEPROM revision byte as a
  pair when deciding whether a device is newer or older than a target hex.
