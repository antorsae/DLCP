# V1.71/V3.2 Link Health Freshness Spec

Last updated: 2026-05-13
Scope: user-visible per-MAIN freshness for the deployed `V1.71` CONTROL + `V3.2` MAIN chain (`CONTROL -> PB1 -> PB2 -> CONTROL`)

## Problem Statement

The current UI can show stale-good state after the chain has stopped
communicating.

Observed and simulated failure shapes:

- If the chain is healthy and then PB1 becomes non-communicating, CONTROL can
  keep showing the last normal `Volume` screen indefinitely.
- Commands can update CONTROL-local display/cache while neither MAIN receives
  them.
- If PB1/PB2 Diagnostics were warmed before the failure, the PB pages can keep
  showing stale `OK` because `v171_diag_present` means "has ever replied in
  this session", not "has replied recently".
- `WAITING FOR DLCP` is too modal for this class of runtime degradation: it
  hides the working controls and does not tell the operator which PB went
  stale.

The missing concept is CONTROL-owned freshness:

> For each MAIN, CONTROL must know whether it has recently completed an
> addressed transaction with that MAIN relative to CONTROL's current runtime.

MAIN cannot own this relative time because the user-facing clock and LCD live
on CONTROL. MAIN should only provide a cheap, addressed health response.

## Design Bias

Keep the first implementation small. The MVP must solve stale UI and stale
Diagnostics without introducing a new general link protocol, a new USB tool, or
large simulator-fidelity work. Anything not required to make the first red
tests fail and then pass belongs in a later phase.

## Objectives

1. CONTROL tracks per-PB last-success freshness during normal UI operation.
2. Runtime link loss never renders stale cached diagnostics as clean `OK`.
3. Normal controls remain responsive; freshness is shown as a degraded state,
   not a modal lockout.
4. The chain protocol addition is one small addressed query and one small
   reply.
5. Compatibility means older MAIN builds must not break parsing or basic
   operation. Health UI is only authoritative when paired with MAIN firmware
   that implements the health ping.
6. Every bug gets a red test first, then firmware changes, then passing tests.

## Non-Goals

- This does not replace the full `DLCP_LINK_V2_SPEC.md` protocol.
- This does not make CONTROL wait for ACKs before changing local UI state.
- This does not require MAIN EEPROM writes.
- This does not add a MAIN HID endpoint in the MVP.
- This does not require CPU-freeze, stuck-UART, or deep electrical fault
  modeling before the first firmware implementation.

## User-Facing Behavior

### Main Screens

The normal screens stay interactive. CONTROL overlays a right-aligned
link-health suffix on LCD row 2. The suffix is separate from the existing row
1 preset/DSP-fault indicator.

MVP scope is limited to these top-level screens:

| Screen | Row 2 base text | Used chars | Spare chars |
| --- | --- | --- | --- |
| Volume | `Auto Detect` | 11 | 5 |
| Preset | `Active: A` / `Active: B` | 9 | 7 |
| Input | `Auto Detect` | 11 | 5 |
| Setup | `BL Timeout` | 10 | 6 |

Suffix contract:

| Suffix | Meaning | Example row 2 |
| --- | --- | --- |
| none | PB1 and PB2 fresh or unknown-not-yet-timed-out | `Auto Detect     ` |
| `!1` | PB1 stale or lost | `Auto Detect   !1` |
| `!2` | PB1 is fresh and PB2 is stale or lost | `Auto Detect   !2` |
| `!1 2` | PB1 and PB2 stale or lost, or the shared return path is gone | `Auto Detect !1 2` |

Topology note: the chain is a true ring. Some downstream or return-path
failures may prevent PB1 replies from returning too. In that case `!1 2` is
correct even if PB1 might still be executing locally. Reserve `!2` for the
case where PB1 round-trip freshness is known-good while PB2 is stale.

The existing row 1, column 16 preset/fault character remains reserved for:

- `A` / `B`: active preset
- `!`: DSP fault indicator

Health suffixes must not overwrite the row-1 preset/fault character. If a DSP
fault and link-health failure coexist, row 1 may show `!` while row 2 also
shows `!1`, `!2`, or `!1 2`:

```text
|Volume:-17.0dB !|
|Auto Detect !1 2|
```

Implementation requirements:

- The suffix must be patched from inside the normal display loop when health
  state changes. A one-time post-render hook is insufficient because the user
  can sit on one screen while a PB goes stale.
- Patch only the row-2 tail columns and only on the top-level screens listed
  above.
- Do not draw the suffix on `WAITING FOR DLCP`, standby, or Diagnostics pages.
- For `!1 2`, reserve columns 13..16 (1-based). Column 12 should remain a
  separator, so any screen opting into the four-character suffix needs base row
  2 text of 11 characters or less.
- For `!1` / `!2`, reserve columns 15..16.
- Silently truncating user-facing text is not acceptable.

Recovery must update the display without a CONTROL reset:

- `!1` clears when PB1 becomes fresh and PB2 is already fresh.
- `!2` clears when PB2 becomes fresh and PB1 is already fresh.
- `!1 2` becomes `!2` if PB1 recovers while PB2 is still stale.
- `!1 2` becomes `!1` if PB2 recovers while PB1 is still stale.
- `!1 2` clears when both PBs are fresh.

### Diagnostics Pages

Diagnostics pages must stop treating stale cache as fresh data.

Per PB display states:

| State | Row 1 | Row 2 | Notes |
| --- | --- | --- | --- |
| never seen | `PBn` | `n/a` | Same as current absent behavior |
| fresh, no abnormal counters | `PBn` | `OK` | Current healthy behavior |
| fresh, abnormal counters | existing sparse counter layout | existing sparse counter layout | Current degraded behavior |
| stale | `PBn old` or `PBn old Ns` | cached counters if nonzero, otherwise blank | Must not show `OK` |
| lost | `PBn lost` | cached counters if nonzero, otherwise blank | Must not show `OK` |

Numeric `old Ns` is optional for the first implementation. Rendering `PBn old`
and `PBn lost` is sufficient for the MVP as long as stale cached data never
renders as clean `OK`.

`v171_diag_present` should remain "has diagnostics cache". Do not overload it
with freshness. Diagnostics rendering should combine:

- diagnostics cache presence
- health seen/unknown state
- current health stale/lost state

Rendering precedence:

1. If no diagnostics cache and no health reply has ever been seen since wake:
   `n/a`.
2. If health is lost: `lost`.
3. If health is stale: `old`.
4. Else render current `OK` / sparse counters.

### Standby and Wake

When CONTROL intentionally enters standby (`CONNECTED` clear), health polling
is inactive. MAINs may be asleep and should not be declared lost merely because
CONTROL stopped polling them.

On wake, CONTROL should reset health to `unknown`. Unknown is not a warning:
no suffix is shown until a PB has actually missed enough health polls to be
stale or lost.

## Chain Protocol Extension

### MAIN Runtime Health Query

Add one addressed chain command:

```text
CONTROL -> MAIN: [B1/B2, 0x23, 0x00]
MAIN    -> CONTROL: [BF, 0x2C, data]
```

MVP rules:

- `B1` addresses PB1.
- `B2` addresses PB2; PB1 forwards it downstream exactly like existing
  addressed diagnostics commands.
- `data` must be `< 0x10`, so it is safe through the current chain forwarder.
- The simplest valid `data` is `0x00`.
- A one-byte `health_seq & 0x0F` may be used if it is cheap, but CONTROL must
  not depend on the sequence for freshness. Receiving a complete expected
  `BF/2C` reply is sufficient.
- The handler must suppress the legacy cmd-XOR ACK echo, mirroring the
  `cmd 0x21` and `cmd 0x22` diagnostics handlers.
- Older MAIN builds that do not implement `cmd 0x23` may emit a stray legacy
  ACK byte or no reply. CONTROL must time out without parser drift.

### Why Not Reuse cmd 0x21?

`cmd 0x21` emits a 7-frame diagnostics burst. It is too heavy for continuous
normal-screen polling and already has page-local semantics. The health ping
must be one request and one reply.

### Why Not Reuse cmd 0x04 Status Poll?

Existing status replies (`BF/03`, `BF/05`, `BF/06`, `BF/07`, `BF/1D`) do not
carry a stable source identity in a way CONTROL can use as per-PB freshness.
They are also entangled with boot/reconnect sentinels. Health should be a
separate addressed transaction.

## MAIN Firmware Changes

Primary files:

- `src/dlcp_fw/asm/dlcp_main_v32.asm`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `scripts/build_v32_release.py`

Required changes:

1. Add `cmd23_health_query_handler` near the existing `cmd21` / `cmd22`
   dispatch path.
2. Emit exactly one reply frame:
   - route `0xBF`
   - cmd `0x2C`
   - data `< 0x10`, initially `0x00` unless `health_seq` is cheap
3. Suppress the legacy cmd-XOR ACK echo.
4. Keep the handler side-effect free unless an optional low-nibble
   `health_seq` byte is added.

Optional later additions:

- `health_seq` MAIN RAM byte for logging/correlation.
- `diag_link_ping` saturating counter: number of health queries served.
- `diag_link_proto` saturating counter: malformed/unsupported link traffic.

These optional fields must not block the first implementation.

## CONTROL Firmware Changes

Primary files:

- `src/dlcp_fw/asm/dlcp_control_v171.asm`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`
- `scripts/build_v171_release.py`

### Runtime State

CONTROL owns freshness. Prefer the simplest implementation that is easy to
audit in assembly.

Recommended MVP RAM:

- `v171_health_age_pb1`
- `v171_health_age_pb2`
- `v171_health_seen_mask`
  - bit 0: PB1 has completed a health reply since wake/cold-init
  - bit 1: PB2 has completed a health reply since wake/cold-init
- `v171_health_flags`
  - bit 0: health reply pending
  - bit 1: pending target snapshot (`0` PB1, `1` PB2)
  - bit 2: display health suffix dirty
- `v171_health_poll_target`
  - `0`: next query PB1
  - `1`: next query PB2

Two explicit age bytes are preferred over packed nibbles unless the RAM audit
proves packing is clearly cheaper. Packed nibbles are easy to make fragile in
PIC assembly and should not be chosen for aesthetics.

Allocate RAM explicitly in `dlcp_control_ram.inc`, preferably after the
current V1.71 BANK1 regions. Add structural tests for required `movlb 0x01`
accesses and `movlb 0x00` restoration where needed.

### Cadence

CONTROL should poll while awake, connected, and not in the strict boot
sentinel window.

MVP cadence:

- Poll one target per health tick, alternating PB1 and PB2.
- Do not block if the TX ring is busy; retry on a later tick.
- Timeout a pending target after a small fixed number of missed health ticks.
- A timed-out target must not starve the other target.
- Stale threshold: 3 consecutive missed seconds or equivalent health ticks.
- Lost threshold: 10 consecutive missed seconds or equivalent health ticks.
- Saturate ages rather than wrapping.

The exact timer source can be chosen during implementation, but tests should
assert user-facing budgets rather than instruction counts:

- stale visible by `stale_threshold + margin`
- lost visible by `lost_threshold + margin`
- recovered suffix cleared within one fresh health reply and one display-loop
  update

Health service must be called from:

- normal `display_loop_iteration`
- Diagnostics `v171_diag_loop`
- reconnect/wake paths only after they have left the strict boot sentinel
  window

Health service must not:

- block on TX ring availability
- spin waiting for replies
- clear or repurpose `CONNECTED`
- force `WAITING FOR DLCP`

### Query Sender

Do not blindly reuse `v171_diag_send_query_w` for `cmd 0x23`. Its current abort
dispatch only distinguishes `cmd 0x21` from "not `0x21`" and can clear the
wrong diagnostics pending bit.

Use either:

- a tiny dedicated `v171_health_send_query`, with its own pending bit and abort
  cleanup, or
- a generalized helper with explicit `0x21` / `0x22` / `0x23` abort dispatch.

The simpler dedicated sender is preferred unless the generalized helper is
smaller after measurement.

### Reply Parser

`BF/2C` must be an exact health-reply parser case. Do not widen the existing
Diagnostics `BF/21..BF/2B` cache range.

Reason: the current Diagnostics parser maps `BF/21..BF/2B` into an 11-cell
cache. Treating `BF/2C` as the next cache entry would write past the cache and
corrupt adjacent CONTROL RAM.

Routing rules:

- Keep the Diagnostics cache range exactly `BF/21..BF/2B`.
- Add an exact `BF/2C` handler before any cache-offset write path or in a
  separate branch that cannot fall through to the cache writer.
- Use the pending-target snapshot, not the live polling target, to decide
  which PB age to reset.
- On expected `BF/2C`, reset that PB age to fresh, set its seen bit, clear
  pending, and mark display dirty.
- Ignore unsolicited `BF/2C` in the first implementation.
- Ensure the parser returns with the expected BSR state, especially after
  touching BANK1 health RAM.

Parser cross-talk tests are required:

- `BF/2C` must not update Diagnostics cache cells.
- `BF/2C` must not clear or toggle Diagnostics pending state.
- Diagnostics replies such as `BF/27` and `BF/2B` must not clear health
  pending state.
- Unsolicited `BF/2C` must not mark a PB fresh.

## USB Diagnostics

No new USB HID endpoint is part of the MVP.

Reasons:

- CONTROL-owned freshness is not directly readable over USB on deployed
  hardware.
- MAIN-local USB liveness does not prove that CONTROL can reach that MAIN
  through the current-loop chain.
- `cmd 0x45` and `cmd 0x46` are reserved by
  `docs/SRC4382_USB_DIAGNOSTICS_SPEC.md`.
- Adding a new HID endpoint, CLI, and sim backend increases scope without
  fixing the user-visible stale UI bug.

Use existing MAIN HID `cmd 0x44` for MAIN-local reset/I2C/MSSP/DSP evidence.
If a later phase needs a MAIN-local link-health snapshot, allocate a
non-conflicting HID command after the SRC4382 reservations and specify exactly
what it can and cannot prove.

## Simulator Scope

Use existing simulator hooks first:

- `set_link_fault("ctl_to_m0", drop=True)`
- `set_link_fault("m0_to_m1", drop=True)`
- `set_link_fault("m1_to_ctl", drop=True)`
- `set_blackout(True)`
- `apply_main_reset(unit, "bor" | "wdt" | ...)`
- `set_mssp_line_hold(...)`
- `set_i2c_fault(...)`

MVP simulator work should only add small wrappers/helpers around existing
surfaces when they make tests clearer:

- PB1 terminal non-response
- PB2 terminal non-response
- downstream link loss
- upstream return loss
- forced/seeded CONTROL health state for pure LCD rendering red tests

Backlog simulator fidelity, not required for MVP:

- true `hold_core_in_reset` exposure
- CPU-freeze hook where PC/timer/peripherals stop and output pins remain
  latched
- UART stuck-low/high and break/idle-stuck modeling
- optional one-way link delay or byte loss burst modeling

## Test Plan

All tests are red first.

### Phase 0 Red Tests

Keep Phase 0 small and independent of new simulator fidelity:

- Warm PB1/PB2 Diagnostics cache, force PB2 health stale/lost, and assert PB2
  no longer renders stale `OK`.
- Seed/force CONTROL health state on a normal screen and assert exact 16-char
  row-2 suffix rendering for none, `!1`, `!2`, and `!1 2`.
- Assert recovery display transitions:
  - `!1` -> none
  - `!2` -> none
  - `!1 2` -> `!2`
  - `!1 2` -> `!1`
  - `!1 2` -> none

### Unit and Structural Tests

MAIN:

- `tests/sim/test_v32_health_ping_cmd23.py`
  - `cmd 0x23` dispatch exists.
  - reply is exactly `BF/2C/<0x00..0x0F>`.
  - no trailing cmd-XOR ACK echo.
  - `B2/23/00` forwards through PB1 and updates PB2 target only.
  - if `health_seq` is implemented, it changes between successful queries.

CONTROL:

- `tests/sim/test_v171_link_health_state.py`
  - ages reset on expected `BF/2C`.
  - ages increment/saturate without replies.
  - one stale PB does not starve the other PB's poll cadence.
  - stale/lost masks derive from thresholds.
  - stale/lost masks clear after the affected PB replies again.
  - standby freezes or suppresses age transitions.
  - unknown after wake does not show a suffix before timeout.

Parser:

- `tests/sim/test_v171_link_health_parser.py`
  - `BF/2C` does not write Diagnostics cache.
  - `BF/2C` does not clear Diagnostics pending bits.
  - Diagnostics `BF/21..BF/2B` do not clear health pending bits.
  - unsolicited `BF/2C` is ignored.
  - BSR is restored after health parser paths.

USB:

- No MVP USB test file.
- Existing `cmd 0x44` tests must keep passing.
- Existing SRC4382 `cmd 0x45` / `cmd 0x46` reservation tests must keep
  passing.

### User-Facing Failure Tests

Create `tests/sim/test_v171_v32_link_health_ux.py`:

1. Healthy chain then PB1 non-communicating:
   - LCD normal screen remains interactive.
   - row-2 suffix becomes `!1` or `!1 2` within threshold, depending on
     topology path.
   - volume UI may change locally, but MAIN registers do not; suffix remains.

2. Healthy chain then PB2 path lost with PB1 round-trip still fresh:
   - row-2 suffix becomes `!2`.
   - PB1 commands still apply when the topology permits.
   - PB2 registers stop changing.
   - after restoring the PB2 path and receiving fresh `BF/2C`, the `!2`
     suffix clears without requiring a CONTROL reset.

3. Shared return path lost:
   - row-2 suffix becomes `!1 2`.
   - test must not require `!2` if PB1 replies cannot return through the ring.

4. Warm PB1/PB2 Diagnostics then PB2 lost:
   - PB2 page transitions from `OK` to `old`/`lost`.
   - PB2 page never renders stale `OK`.
   - PB1 page remains fresh only if PB1 replies are still reachable.
   - after PB2 recovers, the PB2 page transitions back to fresh `OK` or live
     sparse counters, not stale cached `old`/`lost`.

5. Recoverable PB2 BOR:
   - PB2 health becomes stale during reset.
   - PB2 freshness returns after recovery.
   - LCD row-2 suffix clears after recovery.
   - Diagnostics leaves `old`/`lost` and renders fresh data after recovery.
   - reset flags remain visible through existing `cmd 0x44`/Diagnostics.

6. MAIN0 MSSP/I2C stuck:
   - health stays fresh if UART path is alive.
   - MAIN diagnostics show I/R/D counters.
   - UI health suffix stays clear, proving health is link reachability, not
     DSP/I2C health.

### Soak and Property Tests

Extend soak only after targeted tests are green:

- `scripts/sim_v171_v32_standby_wake_soak.py`
- `tests/sim/test_v171_v32_standby_wake_soak.py`

Candidate fault rotation entries:

- `pb1_terminal_nonresponse`
- `pb2_terminal_nonresponse`
- `m0_to_m1_drop`
- `m1_to_ctl_drop`
- `pb1_reset_hold` if a helper exists
- `pb2_reset_hold` if a helper exists

Soak invariants:

- A silent PB must be marked stale/lost before the timeout budget.
- A recovered PB must return fresh.
- LCD row-2 health suffix must clear after a recovered PB becomes fresh.
- Diagnostics pages must leave `old`/`lost` after a recovered PB becomes fresh.
- Stale cache must not render `OK`.
- Controls must remain responsive on non-WAITING screens.
- No health poll may grow RX/TX backlog indefinitely.

Do not add CPU-freeze or UART-stuck fault modes to default soaks until the sim
surfaces exist and targeted tests are stable.

### Hardware Tests

Routine release gate should stay small:

- healthy baseline: suffix absent on a normal screen
- one PB2/downstream fault: LCD shows stale/lost suffix and Diagnostics stops
  showing stale `OK`
- recovery: suffix clears and Diagnostics returns to fresh data
- existing `cmd 0x44` snapshots before/during/after for MAIN-local reset and
  I2C/MSSP/DSP evidence

Extended/manual matrix:

- Disconnect/downstream break between PB1 and PB2.
- Power-cycle PB2 only.
- Power-cycle PB1 only.
- Hold PB2 in reset if physically possible.
- Leave chain idle for a long soak, then issue STBY/WAKE.

Required evidence:

- LCD OCR before fault, during stale/lost, and after recovery.
- Existing USB `cmd 0x44` snapshots for both MAINs.
- MAIN register/diag readback where available.
- Command effect check: UI state vs MAIN register state.

## Implementation Phases

### Phase 0: Ledger and Minimal Red Tests

Deliverables:

- Add ledger entry for `BUG-LINK-HEALTH-01`.
- Add red tests for stale warmed Diagnostics and normal-screen suffix
  rendering using seeded/forced CONTROL health state.
- Add parser cross-talk red tests if feasible without firmware changes.

Exit criteria:

- New tests fail for the expected reasons on current firmware/sim.
- No production firmware changes yet.

### Phase 1: Small Simulator Helpers

Deliverables:

- Add only helper wrappers needed by the targeted tests:
  - PB1 terminal non-response
  - PB2 terminal non-response
  - downstream link loss
  - upstream return loss
  - seeded CONTROL health state

Exit criteria:

- Red tests can express topology failures without ad-hoc link calls in every
  test body.
- Existing sim suite remains green except intentional red feature tests.

### Phase 2: MAIN Health Ping

Deliverables:

- Implement `cmd 0x23` in `dlcp_main_v32.asm`.
- Optionally add `health_seq` RAM allocation only if measured cheap.
- Add structural tests for handler placement, reply shape, and ACK
  suppression.
- Rebuild canonical `DLCP_Firmware_V3.2.hex`.

Exit criteria:

- `tests/sim/test_v32_health_ping_cmd23.py` passes.
- Existing `cmd 0x21`, `cmd 0x22`, and `cmd 0x44` tests still pass.

### Phase 3: CONTROL Freshness Engine

Deliverables:

- Add CONTROL health age state.
- Add non-blocking health poll service.
- Add dedicated query sender or safely generalized query helper.
- Add exact `BF/2C` parser path.
- Keep UI rendering unchanged initially except test-only seeded state if used.

Exit criteria:

- CONTROL state tests pass.
- Parser cross-talk tests pass.
- Health ages change correctly in sim memory.
- No user-visible behavior is changed yet except optional hidden state.

### Phase 4: User-Facing UX

Deliverables:

- Add main-screen health suffix from inside the display loop.
- Add Diagnostics stale/lost rendering.
- Ensure Diagnostics remains non-modal and responsive.

Exit criteria:

- Warmed-cache stale `OK` regression tests pass.
- Normal-screen PB1/PB2 suffix tests pass.
- Recovery clears suffix and Diagnostics stale/lost state.
- IR/front-panel volume, mute, preset, standby/wake still dispatch from
  Diagnostics pages.

### Phase 5: Soak Integration

Deliverables:

- Add link-health terminal failure modes to the standby/wake soak after the
  targeted tests are stable.
- Add progress log fields for per-PB freshness.
- Add LCD log fields for the row-2 health suffix (`""`, `!1`, `!2`, `!1 2`).

Exit criteria:

- Short soak passes with the targeted link-health fault modes.
- Long soak produces actionable logs with health transitions.

### Phase 6: Hardware Gate

Deliverables:

- Add runbook steps to `docs/HARDWARE_TEST.md`.
- Add hardware pytest phases.
- Add release notes to `docs/V171_RELEASE.md` and `docs/V32_RELEASE.md`.

Exit criteria:

- Live rig demonstrates:
  - healthy suffix absent
  - PB2 lost suffix `!2` when PB1 round-trip remains fresh
  - both-lost suffix `!1 2` under full chain non-response/shared return loss
  - Diagnostics no longer shows stale `OK`
  - suffix and Diagnostics stale/lost states clear after the dead PB recovers
  - existing USB `cmd 0x44` snapshots remain readable
  - recovery returns suffix to clear

### Backlog: USB Link Snapshot

Only add a new HID endpoint if MAIN-local link data proves useful after the
MVP is working. Requirements for that later phase:

- Do not use `cmd 0x45` or `cmd 0x46`; they are reserved for SRC4382
  diagnostics.
- State clearly that MAIN USB proves MAIN-local liveness, not CONTROL-owned
  chain freshness.
- Include exact payload length, reserved-byte behavior, parser tests, and sim
  backend shape before implementation.

## Acceptance Criteria

The MVP is complete when:

- A terminal PB1 or PB2 communication failure is visible within the threshold.
- A recovered PB clears the main-screen suffix and Diagnostics stale/lost state
  within the freshness threshold.
- Stale cached Diagnostics data never renders as clean `OK`.
- CONTROL remains interactive on normal screens while stale/lost is shown.
- Recoverable resets and I2C/MSSP faults are distinguishable from link loss
  using existing diagnostics.
- Full sim gate and targeted hardware gates pass.

## Open Questions

1. Exact health cadence:
   - target: one health attempt per PB per second if code/timing permits
   - acceptable MVP: assert stale/lost/recovery budgets in tests rather than a
     fixed instruction-level cadence
2. Exact stale/lost thresholds:
   - proposed: stale after about 3 seconds of missed replies, lost after about
     10 seconds
3. Health reply data byte:
   - simplest: constant `0x00`
   - optional: low-nibble sequence if cheap and useful for logs
4. Diagnostics stale text:
   - numeric `old Ns` is nice, but `old` / `lost` is sufficient for the MVP
