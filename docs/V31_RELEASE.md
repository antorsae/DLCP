# V3.1 Release Workflow

## Scope

This is the operator runbook for the recommended MAIN deployment as of
2026-04-11.

- recommended MAIN release: `firmware/patched/releases/DLCP_Firmware_V3.1.hex`
- recommended CONTROL release: `firmware/patched/releases/DLCP_Control_V1.63b.hex`
- recommended flashing path: bake preset A/B captures into `V3.1.hex` at flash
  time with `scripts/dlcp_main_flash.py`

Non-canonical local experiment images such as `DLCP_Firmware_V3.1_diag*.hex`
and `DLCP_Firmware_V3.1_WITH*_NOPS.hex` are not part of this release workflow.

## Required Local Inputs

Keep the captured preset files under the ignored local artifact directory:

- `artifacts/LX521.4/LX521.4_22MG10F-v5.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v5.json`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.bin`
- `artifacts/LX521.4/LX521.4_22MG10F-v7.json`

The `.json` sidecars preserve the config-name metadata used by the flasher when
it finalizes the active filename slot after flashing.

## Flash Commands

PB1 (left):

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py \
  --hex firmware/patched/releases/DLCP_Firmware_V3.1.hex \
  --capture-a artifacts/LX521.4/LX521.4_22MG10F-v5.bin \
  --capture-b artifacts/LX521.4/LX521.4_22MG10F-v7.bin \
  --all-ch L
```

PB2 (right):

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py \
  --hex firmware/patched/releases/DLCP_Firmware_V3.1.hex \
  --capture-a artifacts/LX521.4/LX521.4_22MG10F-v5.bin \
  --capture-b artifacts/LX521.4/LX521.4_22MG10F-v7.bin \
  --all-ch R
```

What this does:

1. overlays preset A and preset B into the target MAIN image using the version-
   aware flash bases for `V3.1`
2. flashes the resulting app image over USB HID
3. finalizes the active config filename over the stock filename path
4. applies the requested all-channel route policy
5. prints before/after device information so the flashed version, config name,
   and channel mapping are visible in one command

## Quick Checks

Read the current device state without flashing:

```bash
.venv_ep0/bin/python scripts/dlcp_main_flash.py --info-only
```

Read the current preset state without switching:

```bash
.venv_ep0/bin/python scripts/dlcp_preset.py --info-only
```

These checks are useful after each PB flash so the installed version, active
config, routing, and active preset are visible before any acoustic testing.

## Release Notes

- Canonical `V3.1.hex` is now the recommended MAIN release when deployed with
  baked preset captures.
- `V2.8` remains the legacy binary-patched fallback for users who explicitly
  want the last patch-on-stock MAIN.
- Real-hardware acoustic comparison of release and suspect local images is
  covered separately in [`docs/HARDWARE_LOOP.md`](docs/HARDWARE_LOOP.md).
