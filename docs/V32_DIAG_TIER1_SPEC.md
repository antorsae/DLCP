# V3.2 Tier-1 Diagnostics Expansion + V1.71 Menu Rework — Spec

Last updated: 2026-04-20 (round 3 — addressed two review passes;
                          5 round-1 + 4 round-2 follow-on findings)
Status: design locked, implementation pending

## Round-3 follow-on revisions (2026-04-20)

Round-2 spec had four follow-on review findings; all addressed:

* **F1 MED** — cross-version compat matrix split into LCD-path
  (CONTROL-mediated) and HID-path (MAIN-local) columns.  Rev 0x37
  MAIN supports HID `cmd 0x44` regardless of CONTROL version.
* **F2 MED** — old-MAIN behavior on `cmd 0x22` corrected: emits
  ONE stray `0x00` byte upstream (cmd-XOR ACK echo of the data
  byte), no `BF/2N` reply.  CONTROL drops the stray byte
  harmlessly.  New rev 0x37 `cmd 0x22` handler must suppress the
  ACK echo (mirroring rev 0x35 `cmd 0x21` fix).
* **F3 LOW** — stale `MCLR` references trimmed from goals + status
  classification.
* **F4 LOW** — `cmd 0x44` payload-size description fixed: 14 bytes
  total (11 cells + 3 trailer), not "14 + 3".

## Round-2 revisions (2026-04-20)

Doc-only review of round-1 spec found five issues; all addressed below:

1. **Reset-cause cells are FLAGS, not counters.**  Cold-init clears
   the entire diag block on every reset, so accumulating a "POR=N"
   count across sessions in RAM is impossible.  The reset cells now
   represent "which cause fired this session" — exactly one of the
   set is non-zero per session.  Cross-session accumulation is a
   Tier-2 EEPROM-backed feature (deferred).
2. **MCLR counter dropped.**  V3.2 sets `_CONFIG3H = 0x00`
   (`MCLRE = 0`), which DISABLES the MCLR pin and repurposes RE3 as
   an input.  An MCLR-pin-asserted reset cannot fire on this
   hardware; the counter would be permanent dead code and the spec
   would imply a config-bit change with board impact.  Reduced to 4
   reset causes: POR, BOR, WDT, SW-reset.
3. **`cmd 0x21` reply burst is UNCHANGED at 7 frames.**  Extending
   it to 12 frames would break compatibility with V3.2 MAINs that
   only emit through `BF/27` (CONTROL would never see `BF/2C`,
   never set the present bit, and treat the reply as incomplete).
   Round-2 design adds a NEW `cmd 0x22` chain query that returns
   the 4 reset flags via 4 frames `BF/28..BF/2B`.  V1.71 fires
   cmd 0x22 ONCE per Diag-page entry (or on a long cadence) since
   reset cause never changes within a session.  Older MAINs (≤ rev
   0x36) emit ONE stray `0x00` byte upstream when `cmd 0x22` arrives
   (the cmd-XOR-chain dispatch's ACK echo path runs even for cmds
   without handlers — see "Old MAIN behavior on cmd 0x22") but no
   `BF/2N` reply.  CONTROL drops the stray byte harmlessly and
   times out the reset cells at 0.
4. **RCON re-arm now covers TO and RI.**  Round-1 only re-armed BOR
   and POR.  Without re-arming TO (WDT timeout flag) and RI (reset-
   instruction flag), a single WDT or SW-reset event would persist
   in `RCON` across subsequent resets and misclassify them.  All
   four cause-flag bits are now re-armed at the end of cold-init.
5. **Rev marker is 0x37 throughout** (was a mix of 0x36 and 0x37);
   JSON sample uses decimal integers (no `0x36` literals).

## Summary

Expands the V3.2 diag block from 7 runtime counters to **7 counters
+ 4 reset-cause flags** (11 cells total).  The reset-cause flags
encode "which cause fired this session" (not an accumulating count);
exactly one of {POR, BOR, WDT, SW-reset} is set to 1 per session.

`cmd 0x21` chain reply burst stays at 7 frames (forward-compatible
with V3.2 ≤ rev 0x36 MAINs).  A new `cmd 0x22` chain query returns
the 4 reset flags via 4 frames (`BF/28..BF/2B`); CONTROL fires it
once per Diag-page entry.  A new HID `cmd 0x44` returns a structured
11-cell diag snapshot in a single USB transaction.

The V1.71 CONTROL menu reworks Diagnostics from position 2 (between
Preset and Input) to positions 4-5 (after Setup), with one screen per
PB.  LCD layout uses Option D — compact sparse per-PB rendering with
`OK` / `n/a` / `..` overflow special cases.

A new `scripts/dlcp_diag.py` enumerates all attached DLCP MAINs and
prints a structured diagnostic report — usable from operator shells
and CI logs alike.

## Goals

1. **Reset-cause visibility** — operators flashing new firmware or
   debugging field issues can tell whether a unit POR'd, BOR'd, hit
   WDT, or took a software reset (panic path or bootloader hand-off).
   MCLR is not a reset cause on this hardware (`_CONFIG3H = 0x00`
   disables the MCLR pin); see "RAM layout" §"MCLR is NOT a reset
   cause".
2. **Programmatic retrieval** — a HID-only path to pull diag state
   without touching the chain (cmd 0x21 traffic was implicated in
   the 2026-04-20 hang cascade; HID retrieval bypasses the chain
   entirely).
3. **Operator-glanceable LCD** — sparse rendering shows only what
   matters, with clear special cases for "all clean" and "PB absent".
4. **Diag at the deepest menu** — Diagnostics is for advanced /
   troubleshooting use; everyday operation never needs it.  Move
   it from position 2 (between Preset and Input) to positions 4-5
   (after Setup).

## RAM layout

V3.2 MAIN diag block (BANK 2 upper, wipe-protected, always cleared at
cold init regardless of reset cause):

```
0x2E5  diag_i               I — I2C transport faults                  [counter 0..15+]
0x2E6  diag_d               D — DSP-fault episodes                    [counter]
0x2E7  diag_s               S — standby/shutdown dispatches            [counter]
0x2E8  diag_b               B — bring-up dispatches                    [counter]
0x2E9  diag_r               R — recovery branch entries                [counter]
0x2EA  diag_a               A — AN0 standby triggers                   [counter]
0x2EB  diag_p               P — RA1 edge events                        [counter]
0x2EC  diag_ra1_prev        (RA1 edge-detect shadow, NOT a counter)
0x2ED  diag_reset_por       O — set to 1 if this session began via POR [flag 0|1]
0x2EE  diag_reset_bor       V — set to 1 if BOR (Voltage sag)          [flag]
0x2EF  diag_reset_wdt       W — set to 1 if WDT timeout                [flag]
0x2F0  diag_reset_sw        X — set to 1 if software-reset             [flag]
```

11 visible cells (7 counters + 4 reset-cause flags) + 1 shadow = 12
cells total.  Span 0x2E5..0x2F0 (12 bytes), within the 19 free bytes
of BANK 2 upper (0x2DE..0x2FF, with preset_job state at 0x2DE..0x2E4).
Tier-2 (deferred) could use the remaining 7 bytes (0x2F1..0x2F7) for
chain-link health counters or other future cells.

Each runtime counter (I, D, S, B, R, A, P) is a saturating byte
(`diag_inc_sat` macro caps at 0x0F).

Each reset-cause cell (O, V, W, X) is a binary FLAG: cold init zeroes
all four, then writes 1 to whichever cause fired this reset.  Exactly
one of {O, V, W, X} is non-zero per session.

**MCLR is NOT a reset cause on this hardware.**  V3.2 sets
`_CONFIG3H = 0x00` (`MCLRE = 0`), which disables the MCLR pin and
repurposes RE3 as input.  An MCLR-pin-asserted reset cannot fire;
including a counter for it would be permanent dead code.  The
classification cascade's `else` branch is mapped to SW-reset (see
below) rather than MCLR.

## Reset-cause classification (cold-init logic)

V3.2's cold-init runs at every reset.  At entry, `RCON` reflects which
reset cause fired most recently (silicon clears specific bits on POR,
BOR, WDT; software-reset clears RCON.RI but preserves the others).

PIC18F2455 RCON bit layout (datasheet `39632e.md` §4.4):

| Bit | Name | Meaning when CLEARED | Set on POR? | Software writable? |
|---|---|---|---|---|
| 0 | `BOR` | Brown-out reset occurred | yes | yes |
| 1 | `POR` | Power-on reset occurred | yes | yes |
| 2 | `PD` | SLEEP instruction executed | yes | yes |
| 3 | `TO` | WDT timeout occurred | yes | yes |
| 4 | `RI` | Software reset instruction executed | yes | yes |

Classification cascade (read RCON BEFORE any modification):

```asm
; W = current RCON snapshot
movf    RCON, W, ACCESS

btfss   W, 1                  ; RCON.POR clear → POR fired
goto    diag_classify_por
btfss   W, 0                  ; RCON.BOR clear → BOR fired
goto    diag_classify_bor
btfss   W, 3                  ; RCON.TO clear  → WDT fired
goto    diag_classify_wdt
btfss   W, 4                  ; RCON.RI clear  → SW reset fired
goto    diag_classify_sw
; else: no recognized cause cleared (rare — interrupt-during-init,
;       glitch, etc.).  Map to SW-reset bucket since MCLR is
;       physically disabled on this hardware (CONFIG3H = 0x00).
goto    diag_classify_sw

diag_classify_por:
    movlb  0x02
    movlw  0x01
    movwf  diag_reset_por, BANKED
    bra    diag_rcon_rearm
diag_classify_bor:
    movlb  0x02
    movlw  0x01
    movwf  diag_reset_bor, BANKED
    bra    diag_rcon_rearm
diag_classify_wdt:
    movlb  0x02
    movlw  0x01
    movwf  diag_reset_wdt, BANKED
    bra    diag_rcon_rearm
diag_classify_sw:
    movlb  0x02
    movlw  0x01
    movwf  diag_reset_sw, BANKED
    ; fall through

diag_rcon_rearm:
    bsf    RCON, 0, ACCESS    ; arm BOR detection
    bsf    RCON, 1, ACCESS    ; arm POR detection
    bsf    RCON, 3, ACCESS    ; arm WDT TO detection
    bsf    RCON, 4, ACCESS    ; arm RI detection
```

**Order matters.**  The cells are unconditionally zeroed FIRST (per
the always-clear redesign), THEN the just-classified reset-cause
flag is set to 1.  So at the end of cold-init:

* All 7 runtime counters = 0
* Exactly one of {`diag_reset_por`, `diag_reset_bor`,
  `diag_reset_wdt`, `diag_reset_sw`} = 1
* The other 3 reset-cause flags = 0

**Operator implication:** every Diag-page entry shows ONE reset-cause
flag set per session.  Examples:

* `O1, V0, W0, X0` → unit was just power-cycled (POR).
* `O0, V1, W0, X0` → BOR fired since last cold-init.  Power supply
  may be marginal; check the rail.
* `O0, V0, W1, X0` → WDT fired.  Main loop hung — code bug.
* `O0, V0, W0, X1` → software reset (panic path or bootloader hand-
  off after FW update).

To track reset-cause COUNTS across multiple sessions, EEPROM-backed
counters would be needed (Tier-2 deferred work).

## Chain protocol — cmd 0x21 (unchanged) + new cmd 0x22

### `cmd 0x21` — runtime counter reply (UNCHANGED from V3.2 rev 0x36)

V3.2's `cmd21_diag_query_handler` continues to emit 7 frames covering
the runtime counters.  No change.  Existing CONTROL parsers (V1.71
rev that targets V3.2 ≤ 0x36) continue to work.

```
Frame  Byte    Counter   Letter
  1    BF/21   diag_i    I
  2    BF/22   diag_d    D
  3    BF/23   diag_s    S
  4    BF/24   diag_b    B
  5    BF/25   diag_r    R
  6    BF/26   diag_a    A
  7    BF/27   diag_p    P     ← LAST FRAME (CONTROL marks PB present
                                  + clears PENDING + toggles target)
```

The `andlw 0x0F` chain-byte hygiene mask + cmd-XOR ACK suppression
fixes from rev 0x35 stay in place.

### `cmd 0x22` — reset-cause flags reply (NEW for V3.2 rev 0x37)

A separate query that returns the 4 reset-cause flags via 4 frames.
CONTROL fires this ONCE per Diag-page entry (not on every cadence
cycle — the flags don't change within a session).

```
Frame  Byte    Flag             Letter
  1    BF/28   diag_reset_por   O
  2    BF/29   diag_reset_bor   V
  3    BF/2A   diag_reset_wdt   W
  4    BF/2B   diag_reset_sw    X     ← LAST FRAME
```

Each data byte is `andlw 0x0F` masked (chain-forwarder safe).
Each flag value is 0 or 1 (cold-init writes exactly one flag per
session).

`cmd 0x22` handler structure mirrors `cmd 0x21`:
- 4 frames, BF/2N + low-nibble flag value
- `andlw 0x0F` mask before each `rcall uart_tx_byte_blocking`
- `bcf active_flags, 6` before the parser-tail goto (suppress
  cmd-XOR ACK echo)
- BF/2B is the last-frame marker that CONTROL uses to update the
  reset-cause cache and clear `RESET_PENDING`

### CONTROL parser side

`v171_bf2x_case_check` accepts cmd 0x21..0x2B (extended from 0x21..
0x27).  The cmd-byte → cache-slot mapping:

```
cmd 0x21 → cache slot 0 (diag_i)
cmd 0x22 → cache slot 1 (diag_d)
cmd 0x23 → cache slot 2 (diag_s)
cmd 0x24 → cache slot 3 (diag_b)
cmd 0x25 → cache slot 4 (diag_r)
cmd 0x26 → cache slot 5 (diag_a)
cmd 0x27 → cache slot 6 (diag_p)         ← marks PB present + toggles target
cmd 0x28 → cache slot 7 (diag_reset_por)
cmd 0x29 → cache slot 8 (diag_reset_bor)
cmd 0x2A → cache slot 9 (diag_reset_wdt)
cmd 0x2B → cache slot 10 (diag_reset_sw) ← marks reset-cache fresh
```

Two LAST-FRAME markers, one per query type:

* `BF/27` — still the runtime-burst end.  CONTROL marks PB present,
  clears the runtime PENDING flag, toggles the runtime target.
* `BF/2B` — the reset-burst end.  CONTROL clears a separate
  `RESET_PENDING` flag (does NOT touch the runtime present mask
  or target).

This decoupling preserves backward compatibility:

* **V3.2 ≤ rev 0x36 MAINs** receive `cmd 0x22` but have no handler
  for it.  The cmd-XOR-chain dispatch path still fires (it runs
  for every parsed cmd, regardless of whether a handler exists),
  setting `active_flags.bit6` and storing the data byte in
  `ram_0x0BC`.  At the parser tail, this emits ONE stray `0x00`
  byte upstream (the cmd-XOR ACK echo of the data byte; cmd was
  `B1/0x22/0x00`, so the echoed byte is `0x00`).  No 4-frame
  `BF/28..BF/2B` reply burst is emitted (the reset-cause handler
  doesn't exist on rev ≤ 0x36).

  CONTROL handles the stray `0x00` harmlessly: when its parser
  is at `frame_position == 0` (waiting for a route byte), non-
  route bytes (< 0x80) are silently dropped.  CONTROL's
  `RESET_PENDING` flag eventually times out (~4 cadence cycles)
  and the reset-cause cells stay at 0 in the cache — the LCD
  shows runtime counters but no reset-cause flags (which is
  correct: the older firmware doesn't track them).

  See "Cross-version compatibility" §"Old MAIN behavior on
  cmd 0x22" for the full byte-level trace.

* **V3.2 ≥ rev 0x37 MAINs** receive `cmd 0x22` and reply with
  the 4-frame `BF/28..BF/2B` burst.  The new handler MUST also
  suppress the cmd-XOR ACK echo (`bcf active_flags, 6, ACCESS`
  before the parser-tail goto, mirroring the rev 0x35 fix on
  `cmd 0x21`) so no trailing stray byte appears after the
  4-frame burst.  CONTROL's reset-cause cache fills, and the
  Diag-page render shows whichever flag is set.

CONTROL's reset-cause query is fired ONCE per Diag-page entry (the
flag value never changes within a session, so polling more often
wastes chain bandwidth).  After the BF/2B last-frame marker lands,
CONTROL clears RESET_PENDING and never re-issues cmd 0x22 until the
operator exits and re-enters the Diag page.

If `BF/2B` doesn't arrive within a generous timeout (e.g., 4
cadence cycles after cmd 0x22 was sent), CONTROL gives up and
treats the reset-cause cache as "unknown" — does not render those
cells.

## HID protocol extension — new cmd 0x44 (diag snapshot)

A new HID cmd that returns a structured diag snapshot in a single
USB transaction.  No chain traffic; reads MAIN's local diag block
directly.

### Request (host → MAIN)

64-byte HID OUT report:

| Offset | Value | Meaning |
|---|---|---|
| 0 | 0x44 | cmd byte |
| 1 | 0x00 | subcmd reserved (future expansion) |
| 2..63 | 0x00 | unused, must be zero |

### Response (MAIN → host)

64-byte HID IN report:

| Offset | Value | Meaning |
|---|---|---|
| 0 | 0x44 | cmd echo |
| 1 | status | 0x00 = OK, 0x01 = busy/error |
| 2 | 0x0E | payload length (14 bytes) |
| 3..9 | 7 bytes | runtime counters: I, D, S, B, R, A, P (0..0x0F) |
| 10..13 | 4 bytes | reset-cause flags: O, V, W, X (each 0 or 1) |
| 14 | 0x03 | firmware flag (V3.x) |
| 15 | 0x37 | firmware revision (this spec defines rev 0x37; bumps each release) |
| 16 | role | 0 = LEFT, 1 = RIGHT, 0xFF = unknown |
| 17..63 | 0xFF | padding |

Cell byte order in the payload exactly matches the cache layout:
slots 0..6 are the runtime counters, slots 7..10 are the reset-cause
flags.  No MCLR cell (MCLR pin disabled on this hardware — see
"RAM layout" §"MCLR is NOT a reset cause on this hardware").

Cmd 0x44 is read-only and idempotent.  No side effects (does NOT
trigger cmd 0x21 reply burst, does NOT touch the chain, does NOT
increment any counter — observational only, like the existing
cmd 0x06 version probe).

### Why a new cmd instead of extending cmd 0x43?

Cmd 0x43 (diag flash/EEPROM memread) is a generic memory-read tool
intended for low-level debugging (preset capture, EEPROM dump).
Adding RAM as a region would invite operator shell scripts to read
arbitrary RAM addresses, which is fragile across firmware revisions.
Cmd 0x44 returns a STRUCTURED snapshot whose layout is documented
and versioned — host tooling can rely on the field positions.

## V1.71 CONTROL menu rework

Current menu state cycle:

```
Volume(0) → Preset(1) → Diagnostics(2) → Input(3) → Setup(4)  → Volume(0)
```

New menu state cycle:

```
Volume(0) → Preset(1) → Input(2) → Setup(3) → PB1 Diag(4) → PB2 Diag(5) → Volume(0)
```

- 6 fixed states (was 5).
- PB1 Diag and PB2 Diag are ALWAYS in the menu cycle.  PB2 Diag
  renders `n/a` when `v171_diag_present.1` is clear (single-MAIN
  topology, or PB2 silent / unsupported).
- RIGHT cycles forward, LEFT backward.  From PB2 Diag, RIGHT wraps
  back to Volume.
- Diag is now the deepest menu — operators reach it intentionally,
  not by accident during routine browsing.

Implementation: `display_state_max` constant 4 → 5; menu dispatch
table grows two entries (PB1 entry + PB2 entry, each calling a new
`v171_diag_pb_screen` parameterized by PB index 0 or 1).

## CONTROL diag cache layout (V1.71)

Cache extends from 7 cells per PB to 11 cells per PB.  Total 22 PB
cache cells + state bytes.  Lives in K20 BANK 1 upper:

```
0x180..0x18A    v171_diag_pb1_*   (11 cells: I D S B R A P O V W X)
0x18B..0x195    v171_diag_pb2_*   (11 cells)
0x196           v171_diag_target
0x197           v171_diag_present
0x198..0x199    v171_diag_poll_lo / _hi
0x19A           v171_diag_present_snap
0x19B           v171_diag_lcd_pad_count
0x19C           v171_diag_flags        (DIRTY + RUNTIME_PENDING + RESET_PENDING bits)
0x19D           v171_diag_reset_seen   (per-PB bitmask: bit0=PB1 reset cells fresh,
                                                       bit1=PB2 reset cells fresh)
```

Total 30 cells in BANK 1 — well within the 256-byte bank, no overlap
with K20 EUSART buffers (BANK 0).

**Two PENDING bits**:
- `RUNTIME_PENDING` — set when CONTROL fires `cmd 0x21`, cleared on
  `BF/27` reception.  Cadence-driven, fires every ~1 s.
- `RESET_PENDING`   — set when CONTROL fires `cmd 0x22`, cleared on
  `BF/2B` reception.  Fires ONCE per Diag-page entry (per PB).

## LCD layouts (Option D — locked)

16x2 display, 16 chars per line.

### Healthy (all 7 runtime counters at 0; reset flags ignored from rendering when their own values are 0)

```
PB1
OK
```

```
PB2
OK
```

### Absent / silent PB

(triggers when `v171_diag_present.X` is clear after cadence cycles
have had time to fire)

```
PB2
n/a
```

### 1-9 non-zero counters

```
PB1: I3 D2 S1 R7      ← title + 4 counters fit in line 1 (16 chars)
A2 V1 X1 O3 B4        ← 5 more counters in line 2 (15 chars + 1 space)
```

Line 1 format: `PBN:` (4 chars) + ` X# X# X# X#` (12 chars) = 16.
Line 2 format: `X# X# X# X# X# ` (15 chars + trailing space) = 16.

If fewer than 4 non-zero counters fit in line 1, line 2 is blank.
If between 5 and 9, line 2 fills with 1-5 counters.

### >9 non-zero counters

```
PB1: I3 D2 S1 R7
A2 V1 X1 O3 B4..      ← 9 visible + .. overflow marker on last 2 chars
```

The `..` marker tells the operator there are MORE counters at non-
zero than fit on screen.  For the full 12-cell snapshot, use
`scripts/dlcp_diag.py` (HID retrieval).

### Counter encoding (unchanged from current)

| Cell value | LCD char |
|---|---|
| 0 | (omitted from sparse render) |
| 1..9 | `1`..`9` |
| 10..14 | `A`..`E` |
| 15+ | `+` |

### Display order (static)

Always: I D S B R A P O V W X.  Operator learns position once.
Runtime events at the head; reset-cause flags at the tail.

For the reset-cause flags (O V W X), exactly one is non-zero per
session, so at most ONE of those four chars appears in the rendering
at any time.

## Python tooling — `scripts/dlcp_diag.py`

Operator-facing CLI that enumerates all visible DLCP MAINs, queries
cmd 0x44 on each, and prints a structured report.

### Usage

```bash
# Default: scan all visible MAINs, print human-readable report.
.venv_ep0/bin/python scripts/dlcp_diag.py

# JSON output for CI / scripting.
.venv_ep0/bin/python scripts/dlcp_diag.py --json

# Specific MAIN by HID path.
.venv_ep0/bin/python scripts/dlcp_diag.py --path 'DevSrvsID:4296...'

# Watch mode (re-query every N seconds).
.venv_ep0/bin/python scripts/dlcp_diag.py --watch --interval 5

# Reset counters via the standard re-flash path (operator confirmation
# required because the only way to clear the diag block in firmware is
# a cold init, and the only sure way to trigger one is a re-flash with
# the unit's current image).
.venv_ep0/bin/python scripts/dlcp_diag.py --clear-via-reflash
```

### Sample output (human-readable)

```
DLCP Diagnostics  (2026-04-20T15:23:00Z)
========================================

LEFT  HID DevSrvsID:4296392456  V3.2 rev 0x37
  Runtime:   I0 D0 S1 B1 R0 A0 P0
  Reset:     O1 V0 W0 X0     (POR — power-on)
  Status:    HEALTHY (1 nonzero counter — standby/bring-up cycle, expected)

RIGHT HID DevSrvsID:4296392549  V3.2 rev 0x37
  Runtime:   I3 D2 S1 B1 R0 A0 P0
  Reset:     O0 V1 W0 X0     (BOR — brown-out)
  Status:    DEGRADED (5 nonzero — I2C transport faults: 3, DSP fault: 2,
                                    + brown-out reset since cold-init)
```

### Sample output (JSON)

```json
{
  "ts": "2026-04-20T15:23:00Z",
  "spec_rev": "V32_DIAG_TIER1",
  "mains": [
    {
      "role": "LEFT",
      "hid_path": "DevSrvsID:4296392456",
      "version": {"flag": 3, "major": 2, "rev": 55, "rev_hex": "0x37"},
      "counters": {
        "i": 0, "d": 0, "s": 1, "b": 1, "r": 0, "a": 0, "p": 0
      },
      "reset_cause": {
        "por": 1, "bor": 0, "wdt": 0, "sw": 0,
        "active": "por"
      },
      "status": "HEALTHY",
      "nonzero_count": 1
    },
    {
      "role": "RIGHT",
      "hid_path": "DevSrvsID:4296392549",
      "version": {"flag": 3, "major": 2, "rev": 55, "rev_hex": "0x37"},
      "counters": {
        "i": 3, "d": 2, "s": 1, "b": 1, "r": 0, "a": 0, "p": 0
      },
      "reset_cause": {
        "por": 0, "bor": 1, "wdt": 0, "sw": 0,
        "active": "bor"
      },
      "status": "DEGRADED",
      "nonzero_count": 5,
      "alerts": [
        "i2c_transport_faults=3",
        "dsp_fault=2",
        "brown_out_reset_this_session"
      ]
    }
  ]
}
```

JSON-format notes:

* `version.rev` is an integer (`55` = `0x37` decimal); `version.rev_hex`
  is a parallel string for human readability.  Tools choosing one
  or the other depending on whether they want numeric comparison
  or hex display.
* `reset_cause.active` is the spelled-out label for whichever flag is
  set, or `null` if all four are 0 (which would indicate a corrupted
  cold-init — should not happen in practice).
* `counters.*` and `reset_cause.por/bor/wdt/sw` are independent
  fields rather than a flat dict so consumers don't have to know
  which keys are runtime vs reset.

### Status classification

- `HEALTHY` — only `O` (POR=1) and at most one `S+B` pair (one
  standby/bring-up cycle is the expected boot sequence) non-zero.
- `DEGRADED` — any runtime counter (I, D, S>1, B>1, R, A, P) at
  non-zero, or any unexpected reset flag (V = BOR, W = WDT,
  X = SW-reset) set.
- `CRITICAL` — any counter saturated to `+` (15+), or W (WDT) > 0.

The status line is advisory — operators shouldn't rely on it for
go/no-go decisions; the raw counter values are authoritative.

## Test plan

### Phase 1 — V3.2 MAIN

Source-level (Tier A):
- 4 new EQUs at 0x2ED..0x2F0 (POR / BOR / WDT / SW flags;
  no MCLR cell — pin disabled by `_CONFIG3H = 0x00`).
- Reset-cause classification cascade present in cold-init,
  classifying into one of 4 buckets.
- All 4 RCON cause-bits re-armed (BOR + POR + TO + RI).
- cmd 0x21 handler UNCHANGED at 7 frames.
- New `cmd 0x22` handler emits 4 frames (BF/28..BF/2B), each with
  `andlw 0x0F` mask + cmd-XOR ACK suppression.
- New `hid_cmd_diag_snapshot` routine for cmd 0x44.
- HID dispatch routes cmd 0x44 to the new handler.
- Chain dispatch routes cmd 0x22 to the new handler.

Build (Tier B):
- V3.2 hex assembles, symbol resolution OK.
- EEPROM marker bumps to 0x37.

Behavioral (Tier C):
- Cold init from gpsim cold POR: `diag_reset_por == 1`, all other
  reset flags == 0, all 7 runtime counters == 0.
- Cold init from gpsim warm WDT trigger: `diag_reset_wdt == 1`,
  `diag_reset_por == 0`, runtime counters == 0.
- Runtime counters stay zero during extended idle (40M cycles).
- cmd 0x21 reply burst: 7 frames in order, all data bytes 0..0x0F.
  (Unchanged from rev 0x36 behavior.)
- cmd 0x22 reply burst: 4 frames in order (BF/28..BF/2B), each
  data byte 0 or 1, exactly one byte = 1.
- HID cmd 0x44 returns a 14-byte payload (length byte = 0x0E):
  11 cell bytes (7 counters + 4 reset flags) followed by a 3-byte
  trailer (flag = 0x03, rev = 0x37, role).  Total cells + trailer
  = 14 bytes; offsets 17..63 of the 64-byte HID IN report are
  0xFF padding.  See "HID protocol extension" §"Response" for the
  exact byte layout.
- Sustained-Diag-page test (existing failing test from
  `test_v171_v32_layer5_chain_sustained_diag_page_keeps_control_responsive`):
  must now pass with cmd 0x22 fired only once per page entry
  (no per-cadence-cycle cmd 0x22 traffic).

### Phase 2 — V1.71 CONTROL

Source-level (Tier A):
- Cache extends to 11 cells per PB (7 runtime + 4 reset).
- Menu state max = 5.
- Menu dispatch table has PB1 Diag at index 4, PB2 Diag at index 5.
- v171_diag_pb_screen is a single routine with PB-index parameter.
- Renderer skips zero counters; up to 9 visible; `..` overflow marker
  on the last 2 chars when >9 non-zero.
- All special-case lines (`OK`, `n/a`) emit exactly the expected
  characters.

Build (Tier B):
- V1.71 hex assembles with padded layout (full 32 KB coverage).

Behavioral (Tier C):
- Standalone CONTROL: menu navigation Volume → … → PB2 → Volume
  works in both directions.
- Wire-chain: per-PB rendering matches the cache state.
- Wire-chain: sustained Diag-page cadence does NOT cause a CONTROL
  hang (the regression test that currently fails — must pass after
  the protocol extensions land).

### Phase 3 — Python tooling

- Unit test for cmd 0x44 response parser.
- Integration test (mocked HID) verifies report formatting.
- Live-rig test (skipped without hardware) verifies cmd 0x44 is
  reachable on a real V3.2 MAIN.

## Migration / EEPROM marker

EEPROM version tuple `0x03, 0x02, 0x36` → `0x03, 0x02, 0x37`.

Field units showing 0x37 have all of:
- diag block in BANK 2 upper (0x2E5..0x2F0)
- 7 runtime counters + 4 reset-cause flags (no MCLR — pin disabled
  by `_CONFIG3H = 0x00`)
- cmd 0x21 7-frame reply burst with andlw mask + ACK suppression
  (UNCHANGED from rev 0x36)
- NEW cmd 0x22 4-frame reset-flags reply burst (BF/28..BF/2B)
- cold init always-clear (no RCON gate) + reset-cause classification
  with full RCON re-arm (BOR + POR + TO + RI)
- HID cmd 0x44 supported (returns 14-byte payload total: 11 cell
  bytes + 3-byte trailer; length byte at response[2] = 0x0E)

Cross-version compatibility — separate the LCD path (CONTROL-mediated)
from the HID path (MAIN-local).  HID cmd 0x44 lives entirely in MAIN
firmware and is reachable from the host regardless of which CONTROL
firmware is attached:

| MAIN | CONTROL | LCD reset display (CONTROL-mediated) | HID `cmd 0x44` (MAIN-local) |
|---|---|---|---|
| ≤ rev 0x36 | pre-Tier1 | runtime counters only | not supported (cmd 0x44 absent on ≤ 0x36) |
| ≤ rev 0x36 | Tier1 | runtime counters only; CONTROL fires `cmd 0x22` once per page entry, MAIN echoes a stray 0x00 byte (see "Old MAIN behavior on cmd 0x22" below), CONTROL drops it; reset cells stay at 0 in cache; LCD shows runtime counters only | not supported |
| rev 0x37 | pre-Tier1 | runtime counters only on LCD (CONTROL doesn't fire `cmd 0x22`) | **fully supported** — host can pull the 11-cell snapshot via `cmd 0x44` even though CONTROL doesn't render reset flags on the LCD |
| rev 0x37 | Tier1 | full Tier-1 feature set: runtime + reset cells populated, full LCD render | **fully supported** |

The HID retrieval path bypasses the chain entirely — operators with a
0x37 MAIN can use `scripts/dlcp_diag.py` regardless of which CONTROL
firmware is on the unit.  This is the recommended path for monitoring
and CI workflows because it doesn't require navigating the LCD menu
and doesn't touch the chain (cmd 0x21 cadence is implicated in the
2026-04-20 Diag-page hang cascade).

### Old MAIN behavior on `cmd 0x22`

The chain-protocol contract says "unknown cmd → no reply" — but in
the actual V3.2 ≤ rev 0x36 MAIN implementation the cmd-XOR-chain
dispatch path stores the data byte in `ram_0x0BC` and sets
`active_flags.bit6` regardless of whether any handler claimed the
cmd.  At the parser tail, `bit6` set causes the staged byte to be
emitted upstream as the cmd-XOR ACK echo.

So a `cmd 0x22 / data 0x00` query on a ≤ rev 0x36 MAIN produces:

* No 4-frame `BF/28..BF/2B` reply burst (the reset-cause handler
  doesn't exist).
* ONE stray `0x00` byte upstream (the cmd-XOR ACK echo of the
  data byte).

CONTROL handles the stray `0x00` harmlessly: when the parser
`frame_position == 0` (no route byte received yet), non-route bytes
(< 0x80) are silently dropped.  The stray byte does not advance any
parser state.

This is why the spec characterizes the degradation as "graceful":
the failure mode is one harmless dropped byte per Diag-page entry,
not a frame-misalignment cascade.

For the Tier-1 implementation, the new V3.2 rev 0x37 `cmd 0x22`
handler MUST suppress the cmd-XOR ACK echo (`bcf active_flags, 6,
ACCESS` before the parser-tail goto, mirroring the rev 0x35 fix
applied to `cmd 0x21`) so that the chain stays clean even when both
sides know about Tier-1.

## Implementation phases (concrete order)

1. **Spec sign-off** — this document.
2. **V3.2 MAIN**: RAM EQUs + reset-cause classification + new cmd 0x22
   4-frame burst (cmd 0x21 unchanged) + HID cmd 0x44 + EEPROM marker
   bump + tests.
3. **V1.71 CONTROL**: cache extension + menu rework + new
   v171_diag_pb_screen + tests.
4. **`scripts/dlcp_diag.py`**: CLI + Python module + tests.
5. **Docs**: HARDWARE_TEST.md §Diagnostics page rewrite to reflect
   the new menu position + per-PB layout + `dlcp_diag.py` workflow.
6. **Operator runbook**: V32_RELEASE.md and V171_RELEASE.md updated
   with the new diag features and rev marker.

## Open questions

- **Should HID cmd 0x44 also include the chain-link health summary?**
  E.g., bytes 18-23 could carry a per-link OERR / FERR / TX-saturation
  count.  Useful for diagnosing chain bus issues without the operator
  needing to walk to the Diag page.  Would require extending the
  diag block further into BANK 2 upper (still room).  **Decision
  pending — defer to Phase 2 if Phase 1 lands cleanly.**

- **Should `dlcp_diag.py` write a structured log file (e.g.,
  CSV/SQLite) when in `--watch` mode?**  Useful for soak testing.
  **Decision: yes, add `--log PATH` argument; format = JSON-lines
  with one snapshot per line.**

- **Tier-2 follow-on: cross-session reset-cause counters in EEPROM.**
  Tier-1 reset-cause cells are RAM flags (set to 1 for the current
  cause; cleared on every cold-init).  Operators can't see "this
  unit has BORed 17 times this week".  Tier-2 would add 4 EEPROM-
  backed counters that increment alongside the RAM flags but never
  clear, exposed via a new HID cmd 0x45 (so the existing cmd 0x44
  return shape stays stable).  EEPROM endurance is not a concern
  (resets are rare events).  **Deferred — file a follow-up task
  if the operator finds Tier-1 RAM flags insufficient.**

- **Spec previously claimed cmd 0x21 would be extended to 12 frames
  with forward compat.**  That claim was wrong (a 7-frame MAIN
  would never emit BF/2C, so a CONTROL gating "burst complete" on
  BF/2C would hang).  Round-2 design splits the problem cleanly:
  cmd 0x21 stays at 7 frames, BF/27 stays the runtime-burst end;
  reset flags get their own cmd 0x22 with BF/2B as its end marker.
  Forward AND backward compat preserved with one caveat:
  - Older MAINs (≤ rev 0x36) DO emit one stray `0x00` byte upstream
    when `cmd 0x22` arrives — the cmd-XOR-chain dispatch path's
    cmd-XOR ACK echo runs even for cmds that have no handler.  No
    `BF/2N` reply burst follows.  CONTROL drops the stray byte
    harmlessly (parser at `frame_position == 0` silently drops
    non-route bytes).  See "Old MAIN behavior on cmd 0x22" for
    the full byte-level trace.
  - Older CONTROLs simply don't fire cmd 0x22 at all.
  Tooling and tests built against this spec must include the
  one-byte stray-traffic budget on the old-MAIN side; it's not
  zero traffic.
