# IR Preset/Input Switch Shortcuts

Date: 2026-06-24
Status: Implemented in source/tests; canonical release not republished

## Purpose

Add two fixed Hypex RC5 shortcuts to CONTROL V1.73 for fast listening tests:

- F4 toggles the active A/B preset.
- F5 toggles the PB1 input between S/PDIF and Optical.

This is for rapid A/B testing of either DSP presets or input sources without
walking the LCD menu.  It should preserve the existing F1/F2 explicit preset
shortcuts and the current standby/wake shortcuts.

## Verified Current Mapping

Current CONTROL source defines these fixed RC5 shortcuts in
`src/dlcp_fw/asm/dlcp_control_ram.inc` and dispatches them in
`src/dlcp_fw/asm/dlcp_control_v173.asm`:

| Button meaning | RC5 decimal | RC5 hex | Current behavior |
|---|---:|---:|---|
| F1 | 56 | `0x38` | Preset A |
| F2 | 57 | `0x39` | Preset B |
| Standby | 58 | `0x3A` | Force standby |
| Wake | 59 | `0x3B` | Force wake |

So F1 and F2 are already correct for preset A/B.

The requested new codes are interpreted as RC5 decimal command values:

| Requested button | RC5 decimal | RC5 hex | New behavior |
|---|---:|---:|---|
| F4 | 61 | `0x3D` | Preset toggle A <-> B |
| F5 | 63 | `0x3F` | Input toggle S/PDIF <-> Optical |

RC5 command values are 6-bit values (`0x00..0x3F`).  Therefore the requested
codes are decimal `61` and `63`, not hexadecimal `0x61` or `0x63`.

`0x3D` and `0x3F` are not currently claimed by the fixed V1.73 shortcut
cascade.  Legacy V1.5b/V1.6b compatibility tests already treat `0x3D` as an
unknown command; `0x3F` is inside the valid RC5 command range but is not named
by the current fixed shortcut constants.

## Requirements

1. Keep F1/F2 behavior unchanged:
   - RC5 `0x38` selects preset A.
   - RC5 `0x39` selects preset B.

2. Keep standby/wake behavior unchanged:
   - RC5 `0x3A` remains explicit standby.
   - RC5 `0x3B` remains explicit wake.

3. Add F4 preset toggle:
   - RC5 `0x3D` toggles `PRESET_BIT`.
   - If currently A, it selects B.
   - If currently B, it selects A.
   - It must reuse the existing preset frame + persistence path so TX/EEPROM
     behavior remains identical to the explicit F1/F2 preset shortcuts.  Today
     the observable abort path is TX-ring saturation before the EEPROM write;
     EEPROM write itself has no exposed abort status.
   - It must not emit a preset frame that leaves CONTROL state, persisted state,
     and MAIN state intentionally inconsistent.

4. Add F5 input toggle:
   - RC5 `0x3F` toggles PB1/global input intent between S/PDIF and Optical.
   - If PB1 is currently Optical (`cmd 0x06` payload `0x08`), switch to
     S/PDIF (`0x05`).
   - For any other PB1 input, switch to Optical (`0x08`).  This makes the first
     F5 press deterministic from Auto Detect, USB, AES, analogue, or corrupt
     local cache state.
   - It must update the PB1 input cache and emit the existing input-select
     frame path.
   - If PB2 is linked as `Same as PB1`, reuse existing broadcast behavior.
   - If PB2 is independently configured, reuse existing targeted PB1 behavior
     and do not overwrite PB2 intent.  This preserves the recommended tandem
     setup: `Input PB1: Auto Detect` or a concrete external source, and
     `Input PB2: AES`.

5. Dispatch precedence and address gating:
   - Existing user-configured IR actions stored in RAM `0x20..0x26` keep their
     current precedence.
   - F4/F5 fixed shortcuts run only when the decoded address matches the
     configured IR address, normally Hypex address `0x10`, and no configured
     action consumed the command.
   - The implementation must not simply append F4/F5 to the current broad
     post-configured fixed shortcut label if that label is also reached by
     wrong-address or already-consumed configured-action paths.  Split or guard
     the dispatch path so wrong-address `0x38..0x3F` and configured-action
     collisions re-arm/return without fixed shortcut side effects.
   - F1/F2/standby/wake behavior remains unchanged for the configured address.

6. Scope:
   - CONTROL V1.73 source and tests are in scope.
   - MAIN V3.5 should not need protocol changes; F5 must use existing
     `cmd 0x06` input-select frames.
   - Hardware IR helper/docs are in scope if the implementation claims
     hardware smoke through named repo actions; add F4/F5 there instead of
     relying on ad hoc raw IR commands.
   - No new EEPROM setting is required for F4/F5.
   - No change is required to the existing configurable input next/previous IR
     commands.

## Implementation Notes

- Add named constants for the new RC5 values near the existing RC5 constants:
  `RC5_PRESET_TOGGLE equ 0x3D` and
  `RC5_INPUT_OPTICAL_SPDIF_TOGGLE equ 0x3F`.
- Audit the current fixed-shortcut entry path before inserting the new cases.
  Only address-matched, unconsumed commands should reach the fixed shortcut
  probe.
- The preset toggle can branch to the existing preset-A or preset-B cases based
  on `PRESET_BIT`, instead of duplicating send/persist/abort logic.
- The input toggle should use direct `cmd 0x06` payloads (`0x05` S/PDIF,
  `0x08` Optical) and then call the existing input sender.  It should avoid
  inventing a new route command.
- Any new banked-RAM access in the IR dispatch path must explicitly select the
  correct bank or use access-safe aliases before touching the byte.
- If the UI row cache is updated, derive it through the existing
  `map_cmd06_input_select_to_menu_index` helper.  Do not hard-code row numbers
  for S/PDIF or Optical, because the visible row depends on `raw_status_cache`.

## Required Tests

Add simulator coverage proving:

- F1 `0x38` still selects preset A and F2 `0x39` still selects preset B.
- F4 `0x3D` toggles A -> B and B -> A, including repeated presses.
- F4 uses the same TX-saturation abort/restore semantics as explicit preset
  A/B, and successful F4 toggles persist through the existing EEPROM path.
  Do not require EEPROM-abort testing unless the implementation first adds an
  explicit EEPROM timeout/abort contract.
- Standby `0x3A` and wake `0x3B` still dispatch as before.
- Wrong-address fixed shortcut commands `0x38..0x3F` do not dispatch.
- If a configured IR action is assigned a fixed shortcut command, including
  existing `0x38..0x3B` or new `0x3D`/`0x3F`, the configured action consumes it
  and the fixed preset/input/standby/wake shortcut does not also run.
  Cover every configurable action byte `0x21..0x26`, or add a source-level
  control-flow assertion proving every configured-action success path returns
  before the fixed shortcut cascade.
- F5 `0x3F` from Optical emits S/PDIF payload `0x05`.
- F5 `0x3F` from S/PDIF, Auto Detect, AES, USB, analogue, or unknown/corrupt
  PB1 cache emits Optical payload `0x08`.
- With PB2 linked, F5 emits broadcast route `0xB0`.
- With PB2 independent, F5 emits targeted PB1 route `0xB1` and leaves PB2
  intent, PB2 persistence dirty flag, and PB2 EEPROM byte unchanged.
- F5 updates PB1 MAIN input/SRC route state end to end, not only CONTROL's TX
  frame log.
- F5 leaves LCD/input-menu state coherent across raw-status classes.
- Source or simulator tests cover BSR/banked-RAM safety for the new IR path.
- `hardware_flipper_ir.py` can send named `F4`/`F5` actions if hardware smoke
  uses the repo IR sender.
- Existing input next/previous IR behavior still passes.

Focused commands expected after implementation:

```bash
.venv_ep0/bin/python -m pytest tests/sim/test_v171_ir_command_matrix.py tests/sim/test_v171_preset_inline.py tests/sim/test_v171_ir_endpoints.py -q
.venv_ep0/bin/python -m pytest tests/sim/test_v173_multi_pb_input_selection.py -q -k 'ir or input'
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
```

If assembly source changes, also assemble/check the V1.73 release path with the
repo-standard builder or focused temporary assembly gate, per `CODING_STYLE.md`.
