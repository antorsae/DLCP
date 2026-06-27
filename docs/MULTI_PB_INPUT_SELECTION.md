# Multi-PB Input Selection

Last updated: 2026-06-27
Status: target behavior spec for the current V1.73 CONTROL / V3.5 MAIN line

This document replaces the previous split runtime spec and persistence
addendum. It is now the single behavior spec for multi-PB input selection.

The reviewed implementation ledger is `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`.

## Scope

The DLCP contains one CONTROL MCU and two MAIN MCUs:

- PB1 / MAIN0: physical primary board.
- PB2 / MAIN1: physical secondary board.

The current multi-PB behavior adds a second input screen so PB1 and PB2 can
either share the same selected input or use different physical inputs. The
field-reported target case is:

- PB1 input: S/PDIF
- PB2 input: AES
- Both PB1 and PB2 are switched on from power-off.

The firmware version line remains unchanged:

- CONTROL source: `src/dlcp_fw/asm/dlcp_control_v173.asm`
- CONTROL release artifact: `firmware/patched/releases/DLCP_Control_V1.73.hex`
- MAIN source: `src/dlcp_fw/asm/dlcp_main_v35.asm`
- MAIN release artifact: `firmware/patched/releases/DLCP_Firmware_V3.5.hex`

Revision bytes may bump through the existing release builders. Do not create a
V1.74 CONTROL or V3.6 MAIN name for this work.

As of CONTROL V1.73 rev `0x57`, the source and canonical artifact implement
the CONTROL-owned PB1/PB2 persistence model in simulation. Live hardware gates
remain pending until they are recorded in `docs/MULTI_PB_INPUT_SELECTION_IMPL.md`.

## Mental Model

Persistent input selection has one owner:

```text
CONTROL EEPROM = user input intent
MAIN RAM/EEPROM = applied device state, cache, and fallback
```

That rule is the key simplification. PB1 and PB2 must not have different
persistence owners.

Before this spec, PB2 was stored in CONTROL EEPROM while PB1 effectively
survived power cycles through each MAIN's own input cache. That worked in many
normal boots, but it made the behavior counter-intuitive:

- PB2 had an explicit CONTROL-owned byte.
- PB1 depended on MAIN state and the MAIN save service.
- A CONTROL release flash preserved PB2 intent but did not explicitly own PB1
  intent.
- A stale MAIN PB1 EEPROM byte could become authoritative even though the user
  changed the input from CONTROL.

After this spec, CONTROL owns both PB1 and PB2 user intent. MAIN still stores
and reports its applied input, but that value is no longer the design source of
truth once CONTROL has a valid persisted PB1 value.

## User-Facing Behavior

The setup menu contains two input screens:

1. `Input PB1`
2. `Input PB2`

`Input PB1` selects the primary input intent. `Input PB2` selects either:

- `Same as PB1`
- a concrete input value independent of PB1

PB2 defaults to `Same as PB1` for compatibility. A user must intentionally move
PB2 to a concrete input before PB2 becomes independent.

The input enum is the existing command `0x06` input enum:

| Value | Meaning |
| --- | --- |
| `0x00` | Auto Detect |
| `0x01` | Analogue 1 |
| `0x02` | Analogue 2 |
| `0x03` | Analogue 3 |
| `0x04` | Analogue 4 |
| `0x05` | S/PDIF |
| `0x06` | USB Audio |
| `0x07` | AES |
| `0x08` | Optical |

The labels and exact stock names remain the ones already used by the local UI
code. This spec is concerned with ownership, addressing, and persistence.

## EEPROM Contract

CONTROL EEPROM owns the persistent user intent:

| Address | Owner | Valid encodings | Invalid / erased behavior |
| --- | --- | --- | --- |
| `0x5E` | PB1 input intent | `0xC0..0xC8` means PB1 input `0x00..0x08` | no valid CONTROL PB1 intent yet; defer unless a MAIN0/PB1 BF/06 migration source is proven |
| `0x5F` | PB2 input mode | `0xA0` means `Same as PB1`; `0xB0..0xB8` means PB2 concrete input `0x00..0x08` | decode as `Same as PB1` |

The high-nibble tags are deliberate. Raw `0x00..0x08` bytes must not be treated
as valid CONTROL-owned input intent because they could be unrelated legacy
bytes or erased-adjacent artifacts. Closed decoders make invalid bytes safe.
For the field target, PB1 S/PDIF is `0x5E = 0xC5` and PB2 AES is
`0x5F = 0xB7`.

MAIN EEPROM keeps its existing per-MAIN input cache. It is still useful for:

- stock compatibility,
- applied-state cache before CONTROL reconnects,
- fallback during migration,
- MAIN's existing save/load contract.

MAIN EEPROM must not be documented or used as the long-term owner of PB1 user
intent after this change.

## Save Timing

PB1 and PB2 share the same save model:

- A button or IR action updates CONTROL RAM immediately.
- The corresponding CONTROL EEPROM byte is marked dirty.
- EEPROM is written only when the settings dirty-state save service runs.
- Save code must compare before write and clear the dirty bit only after the
  byte is already equal or has been committed successfully.

Therefore a power cut immediately after changing either PB1 or PB2 can lose the
new setting if the dirty-state save service has not run yet. This caveat is no
longer PB1-specific or PB2-specific; it is the shared CONTROL persistence rule.

Operator rule: after changing inputs, wait at least 5 seconds before cutting
power. Hardware gates should prefer an observable confirmation when available:
CONTROL EEPROM byte equals the encoded value and the matching dirty flag is
clear.

## Boot And Migration

Boot has to respect the existing WAITING handshake. CONTROL currently uses
`0x80` sentinels in runtime caches while it waits for MAIN status frames. That
behavior must remain intact.

Cold boot sequence:

1. `settings_load_eeprom` reads CONTROL settings.
2. PB2 is decoded from `0x5F`.
3. PB1 is decoded from `0x5E` into separate pending RAM, not directly into
   `input_select_cache`.
4. CONTROL enters the existing WAITING / reconnect flow with the legacy
   sentinels unchanged.
5. MAIN BF/06 status frames provide applied input state.
6. After cold WAITING has exited by the existing sentinel rules, or reconnect
   has completed by the existing BF/05 poll-answer rule, CONTROL applies the
   CONTROL-owned PB1 intent if the `0x5E` byte was valid.
7. If `0x5E` was invalid or erased, CONTROL may import a MAIN0 input value only
   from a validated migration source: command `0x06`, payload in `0x00..0x08`,
   and source known to be MAIN0/PB1. If the implementation cannot prove MAIN0
   source, it must defer migration rather than dirtying CONTROL EEPROM from an
   ambiguous BF/06 echo.

This migration rule preserves existing units without trusting ambiguous chain
echoes:

- A unit flashed from current V1.73 to updated V1.73 keeps an existing PB1
  setting only when CONTROL already has valid `0x5E` or a MAIN0/PB1 source can
  be proven. On the current ambiguous BF/06 chain, migration defers until the
  user changes PB1 through CONTROL and the dirty save service writes `0x5E`.
- Once CONTROL has saved `0x5E`, future boots use CONTROL as the authority.
- Invalid PB1 bytes never create impossible input values.
- Invalid or ambiguous BF/06 bytes such as `0x09`, `0x7F`, `0x80`, and `0xFF`
  must never become CONTROL-owned PB1 intent.

## Runtime Routing Contract

The CONTROL-to-MAIN link uses the existing 3-byte frame shape:

```text
route/cmd/data
```

Input selection continues to use command `0x06`.

When PB2 is linked:

- PB1 and PB2 should receive the same selected input.
- CONTROL may use the existing broadcast behavior where safe.
- A later PB1 change updates both boards.

When PB2 is concrete:

- PB1 changes address MAIN0 / PB1.
- PB2 changes address MAIN1 / PB2.
- A later PB1 change must not overwrite PB2's concrete selection.
- A later PB2 concrete change must not overwrite PB1.

The route/addressing helpers should stay centralized. UI handlers, IR handlers,
full-sync code, and reconnect recovery should call the same input-send helper
rather than hand-building divergent command `0x06` frames.

## BF/06 Status Rules

BF/06 remains the MAIN-reported applied input.

CONTROL uses BF/06 for:

- one of the cold WAITING sentinel inputs; reconnect readiness remains governed
  by the existing BF/05 poll-answer path,
- migration when PB1 CONTROL EEPROM is not valid,
- display coherence before a pending CONTROL-owned intent has been applied,
- verification that MAIN accepted the requested input.

CONTROL must not let stale BF/06 overwrite a valid CONTROL-owned PB1 intent
during a normal boot. Once the valid PB1 EEPROM byte is loaded, BF/06 is an
applied-state report, not an ownership transfer.

For PB2, BF/06 similarly reports MAIN1 state. The persistent PB2 mode stays
CONTROL-owned at `0x5F`.

## Full Sync And Reconnect

The existing full-sync burst is one-frame-per-call and must stay that way. The
input step must include the current input intent for each MAIN without adding a
back-to-back mini-burst:

- linked mode: PB1 intent to both MAINs,
- concrete PB2 mode: alternate addressed PB1 and PB2 input frames through the
  existing split-sync helper.

Reconnect must not convert a concrete PB2 selection back to linked unless the
PB2 EEPROM byte is invalid or the user explicitly chooses `Same as PB1`.
Temporary runtime fallback to linked is allowed when the current source-list or
raw-status class cannot represent the persisted concrete PB2 value, but that
fallback must preserve EEPROM `0x5F` and must not rewrite the user's concrete
PB2 intent.

PB2 discovery still matters because some hardware sessions only see PB2 after
MAIN1 becomes healthy. While PB2 is not yet seen:

- PB2 display may show the stored mode.
- PB2 command application can be deferred or retried.
- PB1 behavior must remain usable.

## IR Shortcuts

CONTROL V1.73 has fixed RC5 shortcuts:

- preset A,
- preset B,
- preset toggle,
- explicit standby,
- explicit wake,
- PB1 Optical/S/PDIF toggle.

The PB1 Optical/S/PDIF toggle is a PB1 user-intent change. It must update the
same PB1 runtime state and set the same PB1 persistence dirty flag as the
front-panel `Input PB1` screen. It must also respect the PB2 mode:

- PB2 linked: send the toggled PB1 input to both MAINs.
- PB2 concrete: send the toggled PB1 input only to PB1 / MAIN0.

## MAIN Responsibilities

MAIN V3.5 is not the owner of PB1 user intent, but it still must:

- accept command `0x06` for input changes,
- apply SRC/TAS routing for the selected input,
- report BF/06 with the applied input,
- preserve its existing EEPROM cache behavior,
- avoid regressions in the PB2 channel-6 route payload and route-table lookup
  behavior.

This persistence consolidation is expected to be CONTROL-only. Do not touch MAIN
for this work unless a regression is discovered that cannot be fixed in CONTROL.
If MAIN source is touched anyway, it must stay on the V3.5 line and release
through `scripts/build_v35_release.py`.

## CONTROL Responsibilities

CONTROL V1.73 owns:

- PB1 input intent at EEPROM `0x5E`,
- PB2 input mode at EEPROM `0x5F`,
- dirty-state save timing for both bytes,
- migration from MAIN BF/06 only when the source can be proven MAIN0/PB1,
- split routing decisions,
- UI display state,
- IR shortcut dispatch.

If CONTROL source is touched during this work, it must stay on the V1.73 line
and release through `scripts/build_v173_release.py`.

## Hardware And Release Gates

Non-hardware gates:

- build V1.73 CONTROL with RAM-bank safety,
- build V3.5 MAIN only if MAIN changed,
- focused sim tests for PB1/PB2 persistence,
- existing PB2 channel-6 routing guard only if MAIN or routing behavior changed,
- static tests proving stale docs and stale path references are gone.

Hardware gates:

- first-run invalid-`0x5E` behavior: erase or invalidate CONTROL EEPROM
  `0x5E`, set MAIN0 to a known PB1 input, boot updated CONTROL, then verify
  CONTROL either migrates only from a validated MAIN0 source or defers without
  dirtying `0x5E` when source is ambiguous,
- set PB1 S/PDIF and PB2 AES,
- wait at least 5 seconds after the last input change or verify EEPROM/dirty
  state directly,
- power off both boards,
- power on both boards,
- verify CONTROL intent bytes are `0x5E = 0xC5` and `0x5F = 0xB7` where a tool
  can read them,
- verify MAIN-applied state reports PB1 S/PDIF and PB2 AES through BF/06,
  Diagnostics, USB tooling, or equivalent state probe,
- verify PB2 channel 6 emits audio,
- change PB1 after PB2 is concrete and verify PB2 remains AES,
- use the PB1 RC5 toggle and verify persistence after dirty save,
- release-flash CONTROL through the app-flash-only safe path
  (`scripts/flash_control_safe.sh` / `src/dlcp_fw/flash/dlcp_control_flash.py`)
  and verify both PB1 and PB2 settings survive.

The current AGENTS.md field note still applies until the live gates are closed:
V1.73 is non-hardware gated for persistent PB2 input settings and still needs
live PB2 DOWN, audio-routing, persistence, and IR field gates before hardware
field closure.

## Carried-Forward History

The previous docs recorded three pieces of work:

- Runtime split-input behavior: PB1/PB2 menu split, PB2 `Same as PB1`,
  addressed command `0x06` frames, PB2 DOWN fix, and full-sync/reconnect
  coverage.
- PB2 persistence: CONTROL EEPROM `0x5F` with `0xA0` linked and `0xB0..0xB8`
  concrete encodings.
- Field investigation before this consolidation: PB1 survived power cycles
  through MAIN input cache after MAIN's save service ran, while PB2 survived
  through CONTROL EEPROM.

This consolidated spec keeps the runtime behavior and PB2 encoding, but removes
the divergent PB1/PB2 ownership model.

## Acceptance Criteria

The change is accepted when:

- PB1 and PB2 persistent input intent are both documented as CONTROL-owned.
- PB1 no longer relies on MAIN EEPROM as the design owner once CONTROL has a
  valid `0x5E` value.
- Both PB1 and PB2 use compare-before-write dirty save paths.
- Invalid CONTROL bytes decode safely.
- Existing linked PB2 behavior remains default and compatible.
- PB2 concrete mode remains independent across power cycles and reconnects.
- PB1 RC5 input toggle persists through the same PB1 path as the front panel.
- No stale references to the deleted split docs remain.
