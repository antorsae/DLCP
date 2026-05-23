# V1.63b Diagnostics Menu + V3.1 MAIN Counters — Specification

Date: 2026-03-29
Status: draft / not implemented in committed repo builds
Depends on: V1.63b CONTROL + V3.1 MAIN or newer

Current committed behavior note:

- `V1.63b` CONTROL currently implements the `BF/08` fault parser, LCD `!`
  indicator, and resync-on-clear behavior described in
  `docs/V27_V163B_SPEC.md` / `docs/V31_SOURCE_REWRITE_SPEC.md`.
- The diagnostics page and counter-polling protocol in this document
  remain a forward-looking design and are not present in
  `src/dlcp_fw/patch/build_control_presets_ab_v163b.py` or the committed
  `src/dlcp_fw/asm/dlcp_main_v31.asm` / release HEX pair as of
  2026-03-30.

## Purpose

Add a new diagnostics page to `V1.63b` CONTROL so the first two PBs
(`DLCP 1` and `DLCP 2`) expose runtime fault and recovery counters from
`V3.1+` MAIN firmware.

The immediate goal is field diagnosis of transient glitches where one PB
briefly stops producing audio and then recovers.  The page must answer:

- did the PB see low-level I2C/DSP trouble?
- did it enter a shutdown/standby-style path?
- did it execute a bring-up/wake path afterward?
- did the known analog/GPIO trigger paths fire?

## Scope

This spec defines:

- the CONTROL menu insertion point
- the compact per-PB counter set
- the V3.1 code paths that should increment each counter
- the MAIN-side requirement for a new counter-retrieval function

This spec does not yet lock:

- persistence across hard reset or power cycle

## Version Gate

This functionality is defined only for:

- `V1.63b` CONTROL
- `V3.1+` MAIN

It is not a backportable compatibility requirement for:

- `V2.x` MAIN
- `V3.0` MAIN
- earlier CONTROL versions

Required compatibility rule:

- if a PB is not running `V3.1+` MAIN, it is treated as unsupported for this feature
- unsupported PBs must not be interpreted as partially implementing `cmd=0x21`
- CONTROL must render `n/a` for unsupported or non-responding PBs on the Diagnostics page

Testing rule:

- feature-complete diagnostics tests use `V3.1+` MAIN only
- older MAIN versions may be used only for negative compatibility checks such as `n/a` handling

## Menu Placement

Add one new top-level page immediately after `Preset`.

Required navigation order:

- `Volume(0) <-> Preset(1) <-> Diagnostics(2) <-> Input(3) <-> Setup(4)`

The diagnostics page is a single top-level menu entry and uses one fixed
compact 16x2 layout.

Minimum CONTROL behavior:

- Diagnostics has separate PB1 and PB2 pages.
- Row 0 shows the PB status prefix:
  - `PBn OK` when only OK-context counters are non-zero.
  - `PBn! ...` when one or more issue counters are non-zero.
- Row 1 shows OK-context counters in the healthy layout, or remaining
  overflow counters in the issue layout.
- If a PB has not (yet) replied to a diagnostics query, show `n/a` for
  that page.  This collapses the original draft's two cases (PB exists
  but does not support the query, vs. chain has fewer than 2 PBs) into
  a single sentinel because the chain protocol does not give CONTROL
  an independent way to distinguish "topology absence" from "PB silent
  / unsupported" — every probe goes through the same query path.  The
  draft's `--` rendering is retired (revised 2026-04-19); both cases
  now share the `n/a` rendering.  Operationally, both states drive the
  same action ("troubleshoot the chain"), so the lost distinction is
  not load-bearing.

Current V1.71 sparse layout:

- Display order is `I D R A P V W X S B O`.
- `I/D/R/A/P/V/W/X` are issue indicators and select `PBn!`.
- `S/B/O` are OK-context counters and never select `PBn!` by themselves.
- Healthy row 0 is `PBn OK` padded to 16 columns.
- Healthy row 1 shows non-zero `S/B/O` tokens, for example `S1 B1 O1`.
- Issue row 0 is `PBn!` plus up to four non-zero tokens.
- Issue row 1 shows additional tokens if more than four non-zero tokens exist.
- `S/B/O` are placed after issue counters and render only if they fit.

Encoding:

- `x = ' '` when the counter is zero
- `x = '1'..'9','A'..'E'` for values `1..14`
- `x = '+'` for values `>=15`

## Compact Per-PB Counter Set

Per PB, expose these 7 counters:

| Token | Meaning | Increment point in `V3.1` | Why it matters |
|---|---|---|---|
| `I2C` | DSP-write transport fault count | Increment when `dsp_fault_flags.2` is asserted in `i2c_byte_tx`, and also when `coeff_write_pen_timeout` forces the same NACK path | Captures low-level bus trouble even if recovery is quick |
| `DSP` | DSP-fault episode count | Increment when `dsp_fault_flags.6` transitions from clear to set, or equivalently when `send_dsp_fault_status` reports a non-zero fault state for a new episode | Separates a real DSP-path failure from a transient retry |
| `RCV` | Recovery branch count | Increment when `volume_dsp_write` enters the retry-exhausted recovery branch and calls `i2c_bus_clear` / `dsp_ping` | Shows whether self-recovery logic actually fired |
| `S` | Standby/shutdown dispatch count | Increment when `standby_event_dispatch` calls `hw_standby_shutdown` | Distinguishes true shutdown-style silence from a pure DSP write fault |
| `B` | Bring-up / wake dispatch count | Increment when `standby_event_dispatch` calls `adc_boot_gate` | Shows whether the PB executed a wake / re-bring-up path after silence |
| `AN0` | Analog standby-trigger count | Increment when `an0_hysteresis_monitor` clears `active_flags.3` and sets `event_flags.2` because AN0 dropped below threshold | Separates spontaneous analog-triggered standby from commanded standby |
| `RA1` | RA1 event count | Increment on a new explicit V3.1 RA1 edge/event hook | Requested diagnostic item; useful if the discussed RA1 event is implicated in the glitch |

## Operator Classification

The diagnostics page displays both fault indicators and normal event counters.
Do not treat every non-zero displayed cell as a fault.

| Display token | Operator classification | Notes |
|---|---|---|
| `S` | OK behavior | Standby/shutdown dispatch count. Expected after intentional standby. |
| `B` | OK behavior | Bring-up/wake dispatch count. Expected after intentional wake/bring-up. |
| `O` | OK behavior | Power-on reset. It renders under `PBn OK` and never selects `PBn!` by itself. |
| `I` | Issue indicator | I2C/MSSP transport fault. Should stay zero in normal playback. |
| `D` | Issue indicator | DSP/TAS3108 fault episode. |
| `R` | Issue indicator | Firmware entered a recovery branch after DSP/I2C trouble. |
| `A` | Issue/suspicious indicator | AN0 standby-sense trigger. Expected only when AN0 is deliberately driven. |
| `P` | Suspicious event telemetry | RA1 edge event. Expected only if RA1 is deliberately toggled. |
| `V` | Issue indicator | Brown-out reset / rail sag. |
| `W` | Issue indicator | Watchdog reset. |
| `X` | Contextual issue indicator | Software reset. OK only when explained by a known flash/reset/reboot action. |

`S`, `B`, and `O` are intentionally classified as OK behavior counters. They
are useful for reconstructing whether the PB executed standby/wake or came up
from POR, but their presence alone is not evidence of a fault.

## UART Protocol

Use a page-local addressed pull model. Do not add these counters to the
normal periodic status burst.

Chosen query command:

- CONTROL -> MAIN `cmd=0x21`, `data=0x00`

Chosen addressed queries:

- `B1 21 00` = query PB1
- `B2 21 00` = query PB2

This relies on the existing route handling:

- `B1` is consumed by the local PB
- `B2` is forwarded/decremented by PB1 and becomes `B1` at PB2

Chosen reply burst from MAIN (revised 2026-04-19 — supersedes the
original 4-frame packed scheme):

- `BF 21 <I>` data byte = diag_i  (low nibble; high nibble = 0)
- `BF 22 <D>` data byte = diag_d
- `BF 23 <S>` data byte = diag_s
- `BF 24 <B>` data byte = diag_b
- `BF 25 <R>` data byte = diag_r
- `BF 26 <A>` data byte = diag_a
- `BF 27 <P>` data byte = diag_p  (last frame; CONTROL clears the
                                   pending flag and toggles next-target
                                   in its parser case for this cmd)

Notes:

- Reply data bytes carry ONE counter per frame in the LOW nibble
  (high nibble forced to 0).  The earlier 4-frame packed scheme
  (`pack(I,D)` / `pack(S,B)` / `pack(R,A)` / `pack(0,P)`) was retired
  because high counter values produced data bytes >= 0x80, which both
  the K20 CONTROL parser and the chain forwarder re-interpret as
  route bytes — corrupting PB2's reply path through PB1's forwarder.
  Single-counter frames keep every data byte in 0x00..0x0F.
- `0x0F` is the saturating maximum — CONTROL renders it as `+`.
- `BF/08` remains unchanged for live DSP-fault indication.

## Code Paths To Monitor

These are the concrete V3.1 paths worth instrumenting because they are
the ones exercised in known or suspected recovery chains:

### 1. I2C / DSP fault path

- `i2c_byte_tx`
  - Sets `dsp_fault_flags.2` on `SSPCON2.ACKSTAT`
- `i2c_tas3108_coeff_write`
  - `coeff_write_pen_timeout` sets `dsp_fault_flags.6` and forces `dsp_fault_flags.2`
- `volume_dsp_write`
  - retries on NACK
  - on exhaustion, optionally runs `i2c_bus_clear` + `dsp_ping`
  - sends `BF/08` via `send_dsp_fault_status`

These map directly to `I2C`, `DSP`, and `RCV`.

### 2. Standby / wake path

- `standby_request_handler`
  - clears active state and raises the shared standby event
- `wake_request_handler`
  - sets active state and raises the same event
- `standby_event_dispatch`
  - calls `hw_standby_shutdown` when going down
  - calls `adc_boot_gate` when coming up

These map directly to `S` and `B`.

### 3. Analog-triggered standby path

- `an0_hysteresis_monitor`
  - when AN0 drops below the low threshold, clears active state and raises the standby event

This maps directly to `AN0`.

### 4. RA1-trigger path

The current repo proves stock runtime AN0 standby behavior, but it does
not yet prove a stock runtime consumer for MAIN `RA1`.

Therefore `RA1` in this spec is intentionally defined as a new explicit
V3.1 instrumentation point:

- detect the discussed RA1 edge/event in the new source build
- increment a dedicated counter
- expose it in the same diagnostics record as the other counters

That keeps the requested RA1 observability in scope without pretending
the stock firmware already had a documented RA1 recovery path.

## Counters Intentionally Excluded From LCD

Do not spend one of the visible per-PB diagnostics cells on these:

- raw retry-current value in `dsp_fault_flags[5:3]`
- UART timeout count
- hard-reset count
- generic poll / parser traffic counts

Reason: they either do not map cleanly to the audible symptom, are not
per-PB useful on a 16x2 LCD, or are better left to a deeper future page.

## MAIN-Side Requirements

`V3.1+` MAIN adds a new diagnostics retrieval handler for `cmd=0x21`.

### MAIN RAM layout

Store the counters as one byte each in the currently unused RAM gap
between the live `0x11F..0x122` block and the live `0x12C..0x136` block.

Chosen layout:

- `0x123` `diag_i`
- `0x124` `diag_d`
- `0x125` `diag_s`
- `0x126` `diag_b`
- `0x127` `diag_r`
- `0x128` `diag_a`
- `0x129` `diag_p`
- `0x12A` `diag_ra1_prev`
- `0x12B` reserved

Why bytes, not nibble-packed RAM:

- increment sites stay simple and cheap
- no read-modify-write bit packing is needed
- memory cost is negligible

### MAIN counter semantics

- Runtime counters only; do not expose current fault bits directly
- Saturating byte counters with a logical maximum of `15`
- If counter `< 15`, increment
- If counter `>= 15`, leave at `15`
- Increment on event entry, not inside loops
- Preserve across ordinary firmware `RESET` recovery
- Preserve across standby/wake cycles
- Clear only on POR/BOR or an explicit future clear action

### MAIN init / clear behavior

Do not include the diagnostics bytes in the normal unconditional runtime
clear path that wipes `event_flags`, `0x07F`, `0x0BD`, and related
startup state.

Instead:

- inspect reset cause via `RCON` during startup
- if the reset cause is POR or BOR, clear the diagnostics block
- otherwise preserve the diagnostics block

This is required so fault evidence survives:

- `hard_reset` recovery
- watchdog-like recovery paths
- standby/wake bring-up cycles

### MAIN reply behavior

On `cmd=0x21`, MAIN immediately emits the 7-frame single-counter
reply burst (revised 2026-04-19):

- `BF 21 <I>` data byte = diag_i  (low nibble; high nibble = 0)
- `BF 22 <D>` data byte = diag_d
- `BF 23 <S>` data byte = diag_s
- `BF 24 <B>` data byte = diag_b
- `BF 25 <R>` data byte = diag_r
- `BF 26 <A>` data byte = diag_a
- `BF 27 <P>` data byte = diag_p

No periodic emission is added outside this explicit request path.
Each data byte is in 0x00..0x0F; CONTROL packs the seven values into
its 7-byte per-PB cache verbatim.

## CONTROL-Side Requirements

`V1.71` diagnostics page must:

- poll the first two PBs using the addressed `0x21` query path
- cache the seven returned counter values per PB (one cell each)
- render the compact single-screen encoding above
- skip a silent or unsupported PB after a single timed-out cadence
  cycle so the responding PB keeps refreshing
- redraw the LCD when a reply burst completes and the cache snapshot
  is coherent, not on every individual BF/2N cell
- never block the existing volume/input/setup behavior if a PB does not answer

Recommended behavior on missing support:

- unknown / unsupported response: show `n/a`
- timeout from a PB: retain last good value briefly, then fall back to `n/a`

### CONTROL transmit path

Do not use the generic routed-frame helper used by normal setting writes,
because that helper resets the full-sync counter after each send.

Diagnostics queries should instead use a dedicated raw 3-byte enqueue
sequence in the style of the existing status-poll sender:

- enqueue route byte
- enqueue `0x21`
- enqueue `0x00`

### CONTROL receive path

Extend the existing parser tail that already handles `BF/08` so it also
recognizes the full 7-frame burst:

- `BF/21` (diag_i)
- `BF/22` (diag_d)
- `BF/23` (diag_s)
- `BF/24` (diag_b)
- `BF/25` (diag_r)
- `BF/26` (diag_a)
- `BF/27` (diag_p — LAST FRAME; clears PENDING flag and toggles
                   the next-target slot in the parser case)

Cache model (as implemented in V1.71):

- 7 bytes for PB1 (`v171_diag_pb1_i..pb1_p` at 0x080..0x086)
- 7 bytes for PB2 (`v171_diag_pb2_i..pb2_p` at 0x087..0x08D)
- 1 byte `v171_diag_target` (0x08E) — current poll target (0=PB1, 1=PB2)
- 1 byte `v171_diag_present` (0x08F) — bitmask of PBs that have replied
- 2 bytes `v171_diag_poll_lo`/`_hi` (0x090..0x091) — 16-bit cadence countdown
- 1 byte `v171_diag_present_snap` (0x092) — last-rendered present mask
- 1 byte `v171_diag_lcd_pad_count` (0x093) — pad-loop scratch
- 1 byte `v171_diag_flags` (0x094) — DIRTY (bit 0) + PENDING (bit 1)

Do not reuse the reconnect handshake sentinels (`0x0B8`, `0x0B9`,
`0x0A7`, `0x0A1`) for this cache.

### CONTROL poll policy

To avoid extra UART chatter:

- send no diagnostics queries outside the Diagnostics page
- on entering the page, query PB1 once and PB2 once
- while the page stays active, refresh the visible PB at a low rate
- roughly 1 s cadence is sufficient; avoid tens-of-Hz polling because
  it produces excessive BF/2N traffic and repeated full-LCD redraws

This keeps diagnostics traffic page-local and negligible on the
31,250 baud link.

## LCD Examples

All clear, no OK-context counters:

```text
PB1 OK

```

OK-context activity only:

```text
PB1 OK
S1 B1 O1
```

Issue activity, with OK-context counters appended after issue counters:

```text
PB1! I2 R1 B1 O1

```

Values above 9 and saturated display (`>=15`):

```text
PB1! IA D2 R+ A1
P1 V1 W1 X1 S+
```

## First-Pass Implementation Notes

The highest-value counters for the exact “silent for a short interval,
then recovered” symptom are:

1. `S`
2. `B`
3. `I2C`
4. `DSP`
5. `RCV`
6. `AN0`
7. `RA1`

Interpretation guidance:

- `S` and `B` are OK behavior counters; they record standby/wake dispatches
  and are not faults by themselves
- unexpected `S/B` growth during playback points toward a real down/up state
  transition, but the issue is the unexpected transition, not the counters
- `I2C` rising without `S/B` points toward a transport-only DSP disturbance
- `DSP` plus `RCV` points toward retry exhaustion and active recovery
- `AN0` implicates the standby-sense analog path
- `RA1` keeps the discussed external event in scope

## High-Fidelity Validation Plan

Validation for this feature should use the real wire-chain gpsim harness:

- real CONTROL firmware image
- real MAIN firmware image on PB1 and PB2
- real bridged UART chain `CONTROL <> MAIN #1 <> MAIN #2`
- real front-panel button injection for menu navigation and standby/wake
- targeted per-PB fault injection only through the wire-chain harness

Do not treat lower-fidelity pair tests or mailbox-only models as sufficient
coverage for this feature.

### Required primary counter coverage

Each exposed counter must have at least one primary wire-chain e2e test that
proves it increments on the intended path:

| Counter | Required primary test |
|---|---|
| `I` | PB1 transient DSP-write NACK during a real user action such as `UP` |
| `D` | PB2 persistent DSP-fault episode, asserted long enough to create one fault episode |
| `R` | PB2 retry exhaustion entering the recovery branch |
| `S` | Real `STBY` press causing both PBs to enter standby |
| `B` | Real wake from `Zzz` causing both PBs to re-bring up |
| `A` | PB1 AN0-triggered standby event |
| `P` | PB2 RA1 event hook firing |

Notes:

- `D` and `R` are allowed to co-occur with `I`; they do not need perfectly isolated scenarios
- the test requirement is that the target counter increments with correct event semantics
- every primary test must assert PB isolation when the event is injected on only one PB

### Required end-to-end test matrix

At minimum, implement the following high-impact wire-chain cases:

1. Idle zero screen on the Diagnostics page shows `PBn OK`; any non-zero
   OK-context `S/B/O` counters render on row 1 and do not select `PBn!`.
2. No diagnostics UART chatter on non-Diagnostics pages.
3. Entering Diagnostics starts polling; leaving Diagnostics stops polling.
4. PB1 `I` primary test: transient DSP-write NACK increments only PB1 `I`.
5. PB2 `D` primary test: persistent DSP-fault episode increments PB2 `D`.
6. PB2 `R` primary test: retry exhaustion increments PB2 `R`.
7. Both-PB `S` primary test: real standby path increments `S` once per PB.
8. Both-PB `B` primary test: real wake path increments `B` once per PB.
9. PB1 `A` primary test: AN0-triggered standby increments PB1 `A`.
10. PB2 `P` primary test: RA1 event increments PB2 `P`.
11. PB routing/cache isolation: PB2-only fault changes line 2 only.
12. Partial reply / link-fault robustness: one PB reply path broken while the other still updates.
13. Saturation display: each counter family reaches `+` and never wraps.
14. Retention across ordinary firmware reset / reconnect.
15. Clear-on-cold-start only: POR/BOR clears the diagnostics block.

### Test implementation notes

- Prefer a dedicated `tests/sim` wire-chain file for this feature rather than
  mixing it into lower-fidelity tests.
- Use `main_units=2` in all diagnostics e2e tests unless a special compatibility
  case explicitly needs fewer PBs.
- Assert the Diagnostics LCD rendering directly, not just internal cache bytes.
- When possible, also assert the underlying UART request/reply traffic:
  - CONTROL sends `B1 21 00` and `B2 21 00`
  - MAIN replies with the 7-frame burst `BF/21`..`BF/27` (one
    counter per frame, low-nibble data; `BF/27` is the last frame)
- For reset-retention coverage, verify both behaviors:
  - ordinary firmware reset preserves counters
  - POR/BOR clears counters
- AN0, RA1, and reset-cause coverage may require small new harness controls;
  those hooks should be treated as part of the feature-complete test surface.

## Open Points

- Choose CONTROL patch-local cache bytes for the packed PB1/PB2 reply data
- Decide exact refresh cadence while the Diagnostics page is open
- Confirm the exact electrical meaning of the discussed MAIN `RA1` event before implementation
- Define the exact startup `RCON` test used to distinguish POR/BOR from
  firmware recovery reset
