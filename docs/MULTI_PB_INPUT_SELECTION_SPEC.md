# Multi-PB Input Selection Spec

Date: 2026-06-21
Last updated: 2026-06-22
Status: Implemented and non-hardware gated; live hardware field closure pending
Targets: CONTROL V1.73+ with MAIN V3.5+
Scope: per-PB front-panel input selection for a two-MAIN DLCP chain.

## Problem Statement

CONTROL currently treats input selection as one global setting.  The front-panel
Input page maps the selected menu row to one `cmd 0x06` input byte and sends a
broadcast frame:

```text
CONTROL -> MAINs: [B0, 0x06, input_select]
```

That is wrong for the common two-MAIN wiring where PB1 receives the physical
external source and forwards the selected digital signal to PB2 over the
input-board/control-cable AES/CAT path.  In that topology, manually selecting
`Optical` on both MAINs makes PB2 listen to its own optical receiver even though
its actual feed is AES/CAT from PB1.  The operator needs independently
addressed input choices, for example:

```text
Input PB1: Optical
Input PB2: AES
```

Auto Detect must also be per-PB.  PB2 in Auto Detect must be allowed to choose
the AES/CAT feed while PB1 is fixed to Optical.

## Current Answer

CONTROL does not maintain a general "number of MAINs in the chain" variable.
V1.73 does maintain hard-coded PB1/PB2 reachability:

- `v171_diag_present` bit 0/1 means PB1/PB2 has completed a Diagnostics burst
  in this CONTROL session.
- `v171_health_seen_mask` bit 0/1 means PB1/PB2 has completed a health reply
  since wake/cold-init.
- `v171_health_age_pb1` and `v171_health_age_pb2` classify freshness/loss.

That is sufficient for this feature's two-PB target.  This spec does not add
arbitrary N-MAIN discovery.

Observed current V1.73/V3.5 simulator timing for a healthy two-MAIN chain:
PB2 health discovery latches split input about `2,000,000` universal ticks
after `run_until_connected`, i.e. about 42 ms after CONTROL reaches the Volume
screen and about 3.8 s after simulated POR.  Hardware timing can vary with bus
backlog and wake/reconnect state, so requirements below are event-based:
PB2 Input becomes available when existing health or Diagnostics evidence marks
PB2 seen; visiting the PB2 Diagnostics page must not be required.

## Goals

1. Preserve the legacy single-PB Input page when PB2 has never been seen.
2. Expose separate PB1 and PB2 Input pages once PB2 has been discovered.
3. Send input changes with addressed current-loop frames:
   - PB1: `[B1, 0x06, input_select]`
   - PB2: `[B2, 0x06, input_select]`
4. Reuse MAIN's existing `cmd06_input_select_handler`; do not add a new MAIN
   command or SRC4382 path.
5. Stop full-sync from overwriting independent per-PB choices with broadcast
   `[B0, 0x06, input_select]`; keep broadcast only for legacy or
   `Same as PB1` linked mode.
6. In two-PB mode, place `Input PB2` immediately after `Input PB1`; preserve
   legacy page identity by remapping current/restored Setup/Diagnostics states
   when the PB2 page is inserted.
7. Keep volume, preset, mute, standby/wake, setup, diagnostics, and health
   behavior unchanged except where explicitly listed.

## Non-Goals

- No DLCP_LINK_V2 replacement.
- No arbitrary chain length beyond PB1/PB2.
- No automatic "slave must be AES" policy; the user chooses PB2 AES or PB2
  Auto Detect.
- No EEPROM persistence in phase 1.
- No HFD/PC UI redesign.
- No MAIN USB/HID changes.
- No SRC4382 sample-rate or diagnostics changes.
- No live hardware flash as part of this spec.

## Hardware And Manual Basis

The DLCP manual R3 provides the hardware premise:

- Section 2.5.1 describes using one input board with two DLCP modules, with the
  first DLCP's control and digital outputs linked through the second DLCP's
  inputs.
- Section 2.5.1.3 describes switch positions for AES input from the control
  cable and sending the digital signal through the control cable.
- Section 2.5.2.2 says the controller keeps source settings equal for all DLCPs
  in stock behavior, but also notes that when USB audio is selected the other
  DLCP sources can be S/PDIF or CAT/AES via hardware selection.
- The datasheet companion `firmware/reference/dlcp.md` lists J2 S/PDIF,
  AES, and Optical input/output pins in section 4.2.

The firmware must not infer jumper positions at runtime.  It should expose
per-PB control so the operator can match the configured wiring.

## User-Facing Behavior

### Legacy Or PB2-Unknown Case

If PB2 has never been seen, preserve the current six-state menu ring and current
Input screen:

```text
Input:
Auto Detect
```

UP/DOWN continue to send the legacy broadcast frame `[B0, 0x06, value]`.

### Two-PB Case

Once PB2 has been seen through health or Diagnostics, the menu ring inserts a
PB2 Input page immediately after PB1 Input:

| State | Legacy label | Two-PB label |
| ---: | --- | --- |
| 0 | Volume | Volume |
| 1 | Preset | Preset |
| 2 | Input | Input PB1 |
| 3 | Setup | Input PB2 |
| 4 | PB1 Diag | Setup |
| 5 | PB2 Diag | PB1 Diag |
| 6 | unavailable | PB2 Diag |

This is intentionally different from the first V1.73 split-input draft, which
appended `Input PB2` after PB2 Diagnostics.  The operator flow must be:

```text
Volume -> Preset -> Input PB1 -> Input PB2 -> Setup -> PB1 Diag -> PB2 Diag -> Volume
```

In two-PB mode the RIGHT/LEFT wrap max is 6; in legacy/PB2-unknown mode it
remains 5.

When PB2 is discovered while CONTROL is already on a legacy page with
`display_state_index >= 3`, CONTROL must remap the current page once so the
visible page identity is preserved:

| Before PB2 latch | After PB2 latch |
| ---: | ---: |
| 3 Setup | 4 Setup |
| 4 PB1 Diag | 5 PB1 Diag |
| 5 PB2 Diag | 6 PB2 Diag |

State 3 (`Input PB2`) is runtime-only and must never become a persistent boot
dependency.  If settings are saved while the UI is on state 3 in split mode,
CONTROL must persist a legacy-safe state such as state 2 (`Input` /
`Input PB1`) instead.  When saving from split-mode Setup/Diagnostics, CONTROL
must map back to legacy state IDs: split state 4 -> EEPROM state 3, split state
5 -> EEPROM state 4, and split state 6 -> EEPROM state 5.  On settings load,
CONTROL must clamp any restored `display_state_index >= 6` to a legacy-safe
state before PB2 discovery.

PB1/PB2 Input page titles are exactly 16-column-safe:

| Page state | Fresh/normal title | Stale title | Lost title |
| --- | --- | --- | --- |
| PB1 Input | `Input PB1:      ` | normal health suffix path | normal health suffix path |
| PB2 Input | `Input PB2:      ` | `Input PB2 old   ` | `Input PB2 lost  ` |

The source row remains the selected source label.  PB2 stale/lost state must not
hide the PB2 page after it has been enabled.

The Volume page source row is PB1-authoritative.  It must display PB1's intended
input label only, regardless of the current/last-visited Input page or PB2's
independent setting.  This eliminates the current erratic behavior where the
Volume page can show PB1 or PB2 input depending on recent navigation/status
traffic.

Because current V1.73 suppresses the non-blocking health service while parked on
Diagnostics-style states, PB2 Input state 3 must explicitly opt back into the
health age/poll service.  It must not start Diagnostics traffic, but PB2 age
must continue to advance so the row-0 title can transition to `old`/`lost`
while the operator is viewing the PB2 Input page.

PB1's source list is unchanged:

```text
Auto Detect
S/PDIF
USB Audio
AES
Optical
Analogue 1
Analogue 2
Analogue 3
Analogue 4
```

PB2's source list has one additional first option:

```text
Same as PB1
Auto Detect
S/PDIF
USB Audio
AES
Optical
Analogue 1
Analogue 2
Analogue 3
Analogue 4
```

`Same as PB1` is the PB2 default when PB2 is first discovered.  It means PB2 is
linked to PB1 for input selection and CONTROL uses legacy broadcast input
behavior for input changes/full-sync while linked:

```text
CONTROL -> MAINs: [B0, 0x06, pb1_input_select]
```

When PB2 is changed from `Same as PB1` to any concrete source, split mode
becomes independent and PB1/PB2 input updates use addressed frames.  Changing
PB2 back to `Same as PB1` relinks PB2 to PB1 and returns input sync to
broadcast behavior.  The UI label is exactly 16-column-safe:
`Same as PB1     `.

For full input-board status (`raw_status_cache == 0x03`) the display rows map
to existing `cmd 0x06` values:

| Display row | `input_select` |
| --- | ---: |
| Auto Detect | `0x00` |
| S/PDIF | `0x05` |
| USB Audio | `0x06` |
| AES | `0x07` |
| Optical | `0x08` |
| Analogue 1 | `0x01` |
| Analogue 2 | `0x02` |
| Analogue 3 | `0x03` |
| Analogue 4 | `0x04` |

For PB2, display row 0 is `Same as PB1` and has no MAIN `input_select` byte of
its own.  Rows 1..9 map to the table above.  Implementation may represent
linked PB2 with a sentinel or flag, but it must never send that sentinel to a
MAIN.

For unknown/out-of-range `raw_status_cache` values, including the boot sentinel
`0x80` before a `BF/05` status arrives, use the full-input semantics of
`raw_status_cache == 0x03`.  That means the shared concrete input rows map as:

| Shared concrete row | Label | MAIN `input_select` data |
| --- | --- | --- |
| 0 | Auto Detect | `0x00` |
| 1 | S/PDIF | `0x05` |
| 2 | USB Audio | `0x06` |
| 3 | AES | `0x07` |
| 4 | Optical | `0x08` |
| 5 | Analogue 1 | `0x01` |
| 6 | Analogue 2 | `0x02` |
| 7 | Analogue 3 | `0x03` |
| 8 | Analogue 4 | `0x04` |

For PB2, row 0 remains `Same as PB1` and is local-only; PB2 concrete rows
1..9 map to shared rows 0..8 above.  Unknown raw-status handling must not render
garbage labels, select rows beyond the valid max, or send a sentinel/out-of-range
`cmd 0x06` byte.

## Field Issue: PB2 Same-As-PB1 DOWN Can Reboot CONTROL

Observed on hardware after flashing the current V1.73/V3.5 combo:

```text
1. Navigate to Input PB2.
2. Confirm row 1 shows `Same as PB1`.
3. Press DOWN.
4. CONTROL reboots.
```

Simulator status before the BUG-V173-MPB-PB2-DOWN-RAW fix:

- With normal `raw_status_cache == 0x03`, the exact path does not reboot in the
  rust sim.  It transitions from `Same as PB1` to `Analogue 4`, clears the
  linked flag, and emits `[B2, 0x06, 0x04]`.
- With invalid/out-of-range `raw_status_cache` values such as `0xFF`, the sim
  reproduces the adjacent invariant break: `Input PB2 / Same as PB1`, then
  DOWN walks the selected/max option state beyond the valid PB2 rows and row 1
  renders garbage.  Hardware may present the same class as a WDT/reset instead
  of a stable garbage row.

Current hypothesis:

- PB2 `Same as PB1` adds an extra row above the existing source list.
- The PB2 max-row adjustment increments `menu_option_max_index`, but the base
  input max calculation does not clamp unexpected `raw_status_cache` values.
- DOWN from row 0 wraps to that inflated max and indexes beyond the valid input
  label table / `input_select` mapping.

Required fix contract:

- PB2 DOWN from `Same as PB1` must never reboot, hang, render garbage, or send
  an out-of-range command.
- `raw_status_cache` values outside the known `0..3` set must clamp to a safe
  valid source-list maximum before the PB2 extra-row increment.
- After DOWN from `Same as PB1`, `menu_option_selected_index <= 9`,
  `menu_option_max_index <= 9`, and row 1 must be one of the valid PB2 labels.

Regression anchor:

```text
tests/sim/test_v173_multi_pb_input_selection.py::
  test_bug_v173_pb2_same_as_pb1_down_clamps_unknown_raw_status
```

Resolution status as of 2026-06-22:

- CONTROL V1.73 source now normalizes unknown/out-of-range `raw_status_cache`
  values to full-input semantics (`0x03`) before the input menu/mapping paths
  use them.
- The PB2 row used for render and commit/send is clamped before label lookup
  and before `cmd 0x06` mapping.
- PB2 targeted send clamps corrupt independent `input_intent_pb2` before
  full-sync/direct send, so no out-of-range `cmd 0x06` byte can reach MAIN.
- The xfail repro was converted to passing coverage and expanded over unknown
  raw-status values `0x04`, `0x7F`, `0x80`, and `0xFF`; valid raw-status DOWN
  behavior remains covered for `0x00..0x03`.
- The rebuilt canonical CONTROL release is `V1.73 / rev 0x52 / build
  20260622`; simulator and release-HEX regressions pass against
  `firmware/patched/releases/DLCP_Control_V1.73.hex`.
- `rev 0x50` is superseded by `rev 0x51`; x51 moved the temporary raw-status
  fallback scratch off the live IR inhibit timer byte.
- `rev 0x51` is superseded by `rev 0x52`; x52 keeps the PB2 DOWN fix and fixes
  the broad-gate follow-up where ACKSTAT-only `BF/08/0x04` could leave a stale
  LCD `!` even though MAIN's persistent DSP-fault bit was clear.
- Status is simulator/release-gated, not hardware field-closed.  Field closure
  still requires approval-gated smoke on the exact rebuilt release and PB1/PB2
  state evidence after the DOWN action.

## Chain Protocol

Reuse existing route semantics:

```text
B0 = broadcast
B1 = addressed PB1
B2 = addressed PB2; PB1 forwards/decrements it so PB2 sees addressed traffic
BF = MAIN -> CONTROL reply prefix
```

No MAIN wire command changes are required.  MAIN already dispatches
`cmd 0x06` after route handling, and addressed diagnostics/health traffic
already uses `[B1/B2, cmd, data]`.

## CONTROL State Model

Phase 1 is runtime-only.  Do not claim or write new CONTROL EEPROM bytes.
`docs/V16B_SOURCE_REWRITE_SPEC.md` documents EEPROM `0x75..0xFE` as stock user
settings, and V1.73 source comments document the image as stock-equivalent
except `0x70..0x74`.  Persistent split input is a separate future feature gated
by an EEPROM ownership audit, schema doc, migration tests, and hardware
settings-preservation tests.

CONTROL shall maintain explicit intended input bytes:

```text
input_intent_pb1
input_intent_pb2
input_split_flags      # includes a latched "PB2 discovered this session" bit
input_full_sync_target  # optional, if alternating sync is smaller
input_pb2_linked_to_pb1 # optional flag/sentinel for "Same as PB1"
```

Implementation may alias `input_intent_pb1` to an existing byte only if the
ambiguous `BF/06` parser can no longer overwrite split-mode intent.  The safer
default is separate CONTROL-owned intent bytes seeded from the legacy input
cache at boot/PB2 discovery.

Rules:

- Cold boot starts in legacy mode and seeds PB1 from the existing source cache.
- PB2 starts as `Same as PB1` when PB2 is first discovered.  A concrete PB2
  intent byte is seeded from PB1 only if the implementation needs a hidden
  fallback value; the visible/active PB2 state remains linked until the user
  selects a concrete PB2 source.
- `(v171_health_seen_mask | v171_diag_present) & 0x02` is a discovery trigger,
  not the live render predicate.  When it becomes true, latch PB2 discovered in
  `input_split_flags` and keep the PB2 Input page visible until cold boot.
- PB2 discovery through health is sufficient.  The PB2 Input page must appear
  even if the operator has not visited PB2 Diagnostics.
- When PB2 discovery inserts state 3, remap any current visible legacy page
  `3..5` to split state `4..6` so Setup/PB1 Diag/PB2 Diag do not change under
  the user's cursor.
- Split state 3 is not persisted; save/restore maps it to a legacy-safe state.
  Split states 4..6 persist as legacy states 3..5.
- State 3 opts into the non-blocking PB health service so stale/lost rendering
  remains live while the PB2 Input page is displayed.
- First-time split requires PB2 discovery through existing health/Diagnostics;
  there is no force-split menu in phase 1.
- Once PB2 has been seen, keep the PB2 Input page visible until cold boot even
  if PB2 later becomes stale/lost.
- While PB2 has never been seen, use the current broadcast sender.
- Once PB2 has been seen and PB2 is independent, full-sync must use addressed
  PB input frames instead of broadcast input frames.
- Once PB2 has been seen and PB2 is `Same as PB1`, input changes and full-sync
  intentionally use broadcast `[B0,0x06,pb1_input_select]` to preserve legacy
  all-PB behavior.
- Volume-page source rendering reads PB1 intent only.  PB2 intent, PB2 linked
  state, and ambiguous `BF/06` echoes must not change the Volume source label
  once PB2 is independent.  In linked `Same as PB1` mode, `BF/06` may update
  the single PB1/linked intent just as legacy broadcast mode does.

## BF/06 Status Rule

MAIN status bursts include ambiguous `BF/06/<input_select>`.  `BF` replies do
not identify which PB produced the value.  In independent split/two-PB mode,
`BF/06` must not overwrite PB1 or PB2 intended input bytes.

Required behavior:

- Legacy/PB2-unknown mode: keep current parser behavior.
- Two-PB linked mode (`PB2 = Same as PB1`): legacy broadcast/single-intent
  behavior is allowed because PB2 is not independent.
- Two-PB independent mode: treat `BF/06` as observed legacy status only, or
  ignore it for input intent.  It must not redraw PB1/PB2 pages from an
  ambiguous MAIN echo, collapse divergent selections, or alter split full-sync
  payloads.

## Full-Sync Contract

Current full-sync step 2 emits `[B0, 0x06, input_select_cache_b0]`.

Required behavior:

- Legacy mode: keep current full-sync step 2.
- Two-PB linked mode (`PB2 = Same as PB1`): keep broadcast step 2 and send
  PB1's input value to all MAINs.
- Two-PB independent mode: replace step 2 with an addressed sender that emits
  one PB input frame per full-sync cycle, alternating PB1 and PB2, unless
  emitting both is proven smaller and bus-safe.
- The addressed sender must begin with the same `tx_ring_reserve_3` atomicity
  pattern as existing 3-byte senders.
- A saturated TX ring must drop the whole frame and advance no sender state that
  would starve PB1 or PB2 retries.
- In two-PB independent mode no `[B0, 0x06, ...]` input frame may appear after
  PB2 enablement.  Broadcast input frames remain valid only while PB2 is
  explicitly `Same as PB1`.

## MAIN Behavior

No MAIN functional change is expected.

The existing MAIN `cmd06_input_select_handler` must keep:

- committing the input byte into `input_select`;
- mirroring the setting;
- invalidating route shadow and scheduling SRC4382 route refresh in V3.5;
- using the existing SRC4382 fixed-input route table and Auto Detect behavior.

Tests must prove addressed `cmd 0x06` through CONTROL/PB1 chain ingress before
CONTROL full-sync is changed:

- PB1 consumes `[B1,0x06,*]` locally.
- PB1 forwards `[B2,0x06,*]` downstream as an addressed PB2 frame.
- PB2 consumes the forwarded/decremented frame.
- Non-addressed MAIN state remains unchanged.

## Compatibility

- Single-MAIN chain: unchanged UI and broadcast input frame.
- Two-MAIN chain before PB2 discovery: unchanged UI and broadcast input frame.
- Two-MAIN chain after PB2 discovery: PB1/PB2 Input pages are available.
  PB2 starts at `Same as PB1`, so initial input behavior remains broadcast
  until the user selects an independent PB2 source.
- Two-MAIN chain after PB2 discovery with independent PB2 source: PB1/PB2 input
  changes and full-sync use addressed frames.
- Cold boot reverts to legacy until PB2 is rediscovered because phase 1 is
  runtime-only.
- Older MAIN without V3.5 identity still may enable PB2 based on existing health
  or Diagnostics presence.  If PB2 presence is unknown, do not require split UI.
- Existing tests that assert `("Input:          ", "Auto Detect     ")` remain
  valid for stock, single-PB, and PB2-unknown compatibility cases.
- Existing persisted Setup/Diagnostics display states must keep visible page
  identity through PB2 discovery by remapping state `3..5` to split state
  `4..6`.

## Security Assumptions

This feature assumes local physical trust for the front panel, IR receiver, USB
operator tools, and current-loop link.  It does not add authentication.  The
robustness requirement is to validate menu indices/input bytes, avoid ambiguous
`BF/06` intent writes in split mode, and keep malformed/current-loop traffic
  from causing partial-frame or RAM-bank hazards.  Linked `Same as PB1` mode is
  the exception to the `BF/06` quarantine because it intentionally preserves
  legacy single-intent behavior.

## Test Requirements

Add or update simulator tests for:

1. Legacy single-PB/PB2-unknown behavior still emits `[B0,0x06,value]` and
   renders `Input:`.
2. A V1.73/V3.5 two-PB chain enables state 3 (`Input PB2`) after PB2 health
   discovery without visiting PB2 Diagnostics.
3. RIGHT/LEFT traversal and wrap in both six-state and seven-state modes:
   - legacy/PB2-unknown: `Volume -> Preset -> Input -> Setup -> PB1 Diag ->
     PB2 Diag -> Volume`;
   - two-PB: `Volume -> Preset -> Input PB1 -> Input PB2 -> Setup ->
     PB1 Diag -> PB2 Diag -> Volume`.
4. PB2 discovery while currently on legacy Setup/PB1 Diag/PB2 Diag remaps the
   visible page to split state 4/5/6 respectively.
5. Saving settings while on split state 3 persists/clamps to a legacy-safe
   state, saving split state 4/5/6 persists legacy 3/4/5, and cold boot with
   EEPROM `0x00` values `0x06` and `0xFF` resumes safely before PB2 discovery.
6. PB2 first-discovery default renders `Input PB2: / Same as PB1`, and PB1
   input changes/full-sync emit broadcast `[B0,0x06,value]` while PB2 remains
   linked.
7. Volume page source row always follows PB1 intent, including after visiting
   PB2 Input and after PB2 is set to an independent source.
8. PB1 Optical emits `[B1,0x06,0x08]` and updates only PB1 after PB2 is
   independent.
9. PB2 AES emits `[B2,0x06,0x07]` through CONTROL/PB1 ingress and updates only
   PB2.
10. PB1 Optical and PB2 AES remain visibly distinct after navigating away/back.
11. PB1 fixed input plus PB2 Auto Detect survives navigation, full-sync,
   standby/wake, and preset changes.
12. PB2 can be changed from independent source back to `Same as PB1`; the next
    PB1 input change/full-sync returns to broadcast all-PB behavior.
13. PB1/PB2 route shadows/SRC4382 pairs diverge correctly:
   - PB1 Optical -> route 4 -> SRC4382 `0x0D=0x0B`, `0x08=0xF0`
   - PB2 AES -> route 3 -> SRC4382 `0x0D=0x08`, `0x08=0x30`
14. Independent split full-sync emits no `[B0,0x06,*]` and preserves divergent
    MAIN state.
15. Ambiguous `BF/06` status traffic cannot overwrite PB1/PB2 intent in
    independent split mode.
16. PB2 stale/lost keeps the PB2 page visible and renders `Input PB2 old` /
    `Input PB2 lost`.
17. Parking on PB2 Input while PB2 stops responding still advances health age
    and transitions the title to `old`/`lost`.
18. While parked on PB2 Input, health frames `[B1/B2,0x23,0x00]` are allowed
    but Diagnostics frames such as `[B1/B2,0x21,*]` / `[B1/B2,0x22,*]` are not
    emitted.
19. Addressed input senders are structurally and behaviorally covered by a
    V1.73-specific atomic 3-byte sender test pattern; historical V1.71 sender
    expectations must remain intact.
20. TX-ring saturation leaves no partial frame bytes and does not advance the
    alternating full-sync target in a way that starves PB1 or PB2.
21. Runtime-only phase 1 behavior is explicit: cold boot clears PB2 page/intent
    until PB2 is rediscovered.
22. Health-only PB2 discovery followed by standby/wake or reconnect keeps the
    latched PB2 Input page visible.  If PB2 is still `Same as PB1`, full-sync
    remains broadcast; if PB2 is independent, full-sync remains addressed.

## Release And Hardware Gates

Focused developer checks must include new split-input tests, existing source
select/SRC4382 route tests, V1.73/V3.5 compatibility tests, RAM-bank safety, and
CONTROL size/headroom evidence.

Before publishing or flashing a canonical CONTROL release, build the release
candidate first, then run the gates against that exact canonical HEX.  Do not
rebuild after the test gate; if source or HEX changes, restart this sequence.

```bash
.venv_ep0/bin/python scripts/build_v173_release.py
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target control-v173
.venv_ep0/bin/python -m pytest tests --collect-only -q
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
.venv_ep0/bin/python scripts/check_phase5_gate.py
.venv_ep0/bin/python scripts/check_gpsim_excision.py
shasum -a 256 firmware/patched/releases/DLCP_Control_V1.73.hex src/dlcp_fw/asm/dlcp_control_v173.asm
```

The two hash captures must match.  Any source or HEX change after the first
hash capture invalidates the gate and requires rebuilding plus rerunning the
full release-ready sequence.

If MAIN source changes unexpectedly, also require:

```bash
.venv_ep0/bin/python scripts/check_ram_access_safety.py --target main-v35
.venv_ep0/bin/python scripts/build_v35_release.py
```

Live hardware validation requires explicit user approval and the role-safe
runbook in `docs/HARDWARE_TEST.md`: run `hardware_state_test.py detect`, then
`identify-mains --require-left-right`, use explicit HID paths, capture PB1/PB2
diagnostics/SRC4382 snapshots, and record audio confirmation for PB1 Optical /
PB2 AES and PB2 Auto Detect AES/CAT.
