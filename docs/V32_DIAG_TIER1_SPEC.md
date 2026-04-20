# V3.2 Tier-1 Diagnostics Expansion + V1.71 Menu Rework — Spec

Last updated: 2026-04-20
Status: design locked, implementation pending

## Summary

Expands the V3.2 diag block from 7 runtime counters to **12 counters**
(adds 5 reset-cause counters), extends the `cmd 0x21` chain protocol
reply burst from 7 to 12 frames, adds a new HID `cmd 0x44` that returns
a structured diag snapshot in a single USB transaction, reworks the
V1.71 CONTROL menu so Diagnostics moves from position 2 to positions
4-5 (one screen per PB at the LAST menu positions), and updates the
LCD layout to compact per-PB sparse rendering with `OK` / `n/a` /
`..` overflow special cases (Option D from the 2026-04-20 design
discussion).

A new `scripts/dlcp_diag.py` enumerates all attached DLCP MAINs and
prints a structured diagnostic report — usable from operator shells
and CI logs alike.

## Goals

1. **Reset-cause visibility** — operators flashing new firmware or
   debugging field issues can tell whether a unit POR'd, BOR'd, hit
   WDT, took a software reset, or got MCLR'd.
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
0x2E5  diag_i               I — I2C transport faults
0x2E6  diag_d               D — DSP-fault episodes
0x2E7  diag_s               S — standby/shutdown dispatches
0x2E8  diag_b               B — bring-up dispatches
0x2E9  diag_r               R — recovery branch entries
0x2EA  diag_a               A — AN0 standby triggers
0x2EB  diag_p               P — RA1 edge events
0x2EC  diag_ra1_prev        (RA1 edge-detect shadow, NOT a counter)
0x2ED  diag_reset_por       O — POR (Power-On Reset)
0x2EE  diag_reset_bor       V — BOR (Brown-Out / Voltage sag)
0x2EF  diag_reset_wdt       W — WDT timeout
0x2F0  diag_reset_sw        X — software reset (panic / bootloader)
0x2F1  diag_reset_mclr      M — external MCLR pin
```

12 counter cells + 1 shadow = 13 cells.  Total span 0x2E5..0x2F1
(13 bytes), well within the 19 free bytes of BANK 2 upper
(0x2DE..0x2FF, with preset_job state at 0x2DE..0x2E4).

Each counter is a saturating byte (`diag_inc_sat` macro caps at 0x0F).

## Reset-cause classification (cold-init logic)

V3.2's cold-init runs at every reset.  At entry, `RCON` reflects which
reset cause fired most recently (silicon clears specific bits on POR,
BOR, WDT; software-reset clears RCON.RI but preserves the others).

Classification cascade (read RCON BEFORE re-arming the bits):

```
RCON.POR (bit 1) cleared          → POR        → diag_inc_sat diag_reset_por
elif RCON.BOR (bit 0) cleared     → BOR        → diag_inc_sat diag_reset_bor
elif RCON.TO  (bit 4) cleared     → WDT        → diag_inc_sat diag_reset_wdt
elif RCON.RI  (bit 7) cleared     → SW reset   → diag_inc_sat diag_reset_sw
else                              → MCLR pin   → diag_inc_sat diag_reset_mclr
```

After classification, re-arm RCON.BOR + RCON.POR + RCON.RI so the next
reset is classifiable.

The 12 runtime + reset cells are then unconditionally zeroed (per
2026-04-20 always-clear redesign), THEN the just-classified reset-
cause counter is incremented.  So the snapshot semantics are:

> "Counter N is the count of reset cause N events since the last cold
> init.  After the cold init clears, the current cold init's own
> reset cause is bumped to 1.  All runtime counters start at 0."

Operator implication: every Diag-page entry shows reset-cause counts
from the CURRENT session.  POR=1 + BOR=0 means "the unit has been
running cleanly since the last power-up".  POR=1 + BOR=2 means "the
power supply sagged twice during this session".

## Chain protocol extension — cmd 0x21 reply burst

V3.2's `cmd21_diag_query_handler` extends from 7 frames to **12
frames**.  Each frame is `[BF, 0x2N, data]` with the data byte being
the corresponding diag cell value masked to 0..0x0F (per the
2026-04-20 `andlw 0x0F` chain-byte hygiene fix).

```
Frame  Byte    Counter          Letter
  1    BF/21   diag_i           I
  2    BF/22   diag_d           D
  3    BF/23   diag_s           S
  4    BF/24   diag_b           B
  5    BF/25   diag_r           R
  6    BF/26   diag_a           A
  7    BF/27   diag_p           P
  8    BF/28   diag_reset_por   O
  9    BF/29   diag_reset_bor   V
 10    BF/2A   diag_reset_wdt   W
 11    BF/2B   diag_reset_sw    X
 12    BF/2C   diag_reset_mclr  M     ← LAST FRAME
```

CONTROL's `v171_bf2x_case_check` already accepts cmd 0x21..0x27;
extend the upper bound to 0x2D (exclusive) so 0x21..0x2C all match.

The cell-base + col_offset arithmetic keeps the same shape — cache
slots grow from 7 per PB to 12 per PB.  BF/27 is no longer the
last-frame marker; **BF/2C is**.  Update the present-mask / target-
toggle / PENDING-clear path in the parser case to gate on
`col_offset == 11` (BF/2C) instead of 6.

The cmd-XOR ACK suppression (`bcf active_flags, 6, ACCESS` before
goto) stays in place from the 2026-04-20 round-1 fix.

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
| 2 | 0x0F | payload length (15 bytes) |
| 3..14 | 12 bytes | diag counter values, low-nibble only |
| 15 | 0x03 | firmware flag (V3.x) |
| 16 | 0x36 | firmware revision (current 0x36, bumps with each release) |
| 17 | role | 0 = LEFT, 1 = RIGHT, 0xFF = unknown |
| 18..63 | 0xFF | padding |

Counter byte order matches the chain protocol (I, D, S, B, R, A, P, O, V, W, X, M).

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

Cache extends from 7 cells per PB to 12 cells per PB.  Total 24
cells + state bytes.  Lives in K20 BANK 1 upper:

```
0x180..0x18B    v171_diag_pb1_*   (12 cells: I D S B R A P O V W X M)
0x18C..0x197    v171_diag_pb2_*   (12 cells)
0x198           v171_diag_target
0x199           v171_diag_present
0x19A..0x19B    v171_diag_poll_lo / _hi
0x19C           v171_diag_present_snap
0x19D           v171_diag_lcd_pad_count
0x19E           v171_diag_flags (DIRTY + PENDING bits)
```

Total 31 cells in BANK 1 — well within the 256-byte bank, with no
overlap of K20 EUSART buffers (BANK 0).

## LCD layouts (Option D — locked)

16x2 display, 16 chars per line.

### Healthy (all 12 counters at 0)

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

Always: I D S B R A P O V W X M.  Operator learns position once.
Runtime events at the head; reset-cause group at the tail.

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

LEFT  HID DevSrvsID:4296392456  V3.2 rev 0x36
  Runtime:   I0 D0 S1 B1 R0 A0 P0
  Reset:     O1 V0 W0 X0 M0
  Status:    HEALTHY (1 nonzero — standby/bring-up cycle, expected)

RIGHT HID DevSrvsID:4296392549  V3.2 rev 0x36
  Runtime:   I3 D2 S1 B1 R0 A0 P0
  Reset:     O1 V0 W0 X0 M0
  Status:    DEGRADED (5 nonzero — I2C transport faults: 3, DSP fault: 2)
```

### Sample output (JSON)

```json
{
  "ts": "2026-04-20T15:23:00Z",
  "mains": [
    {
      "role": "LEFT",
      "hid_path": "DevSrvsID:4296392456",
      "version": {"flag": 3, "major": 2, "rev": 0x36},
      "counters": {
        "i": 0, "d": 0, "s": 1, "b": 1, "r": 0, "a": 0, "p": 0,
        "por": 1, "bor": 0, "wdt": 0, "sw": 0, "mclr": 0
      },
      "status": "HEALTHY",
      "nonzero_count": 1
    },
    {
      "role": "RIGHT",
      "hid_path": "DevSrvsID:4296392549",
      "version": {"flag": 3, "major": 2, "rev": 0x36},
      "counters": {
        "i": 3, "d": 2, "s": 1, "b": 1, "r": 0, "a": 0, "p": 0,
        "por": 1, "bor": 0, "wdt": 0, "sw": 0, "mclr": 0
      },
      "status": "DEGRADED",
      "nonzero_count": 5,
      "alerts": ["i2c_transport_faults=3", "dsp_fault=2"]
    }
  ]
}
```

### Status classification

- `HEALTHY` — only `O` (POR=1) and at most one `S+B` pair (one
  standby/bring-up cycle is the expected boot sequence) non-zero.
- `DEGRADED` — any runtime counter (I, D, S>1, B>1, R, A, P) at
  non-zero, or any unexpected reset (V, W, X, M) > 0.
- `CRITICAL` — any counter saturated to `+` (15+), or W (WDT) > 0.

The status line is advisory — operators shouldn't rely on it for
go/no-go decisions; the raw counter values are authoritative.

## Test plan

### Phase 1 — V3.2 MAIN

Source-level (Tier A):
- 5 new EQUs at 0x2ED..0x2F1.
- Reset-cause classification cascade present in cold-init.
- cmd 0x21 handler extends to 12 frames (BF/21..2C).
- All 12 frames have `andlw 0x0F` masks.
- cmd-XOR ACK suppression still in place.
- New hid_cmd_diag_snapshot routine for cmd 0x44.
- HID dispatch routes cmd 0x44 to the new handler.

Build (Tier B):
- V3.2 hex assembles, symbol resolution OK.
- EEPROM marker bumps to 0x37.

Behavioral (Tier C):
- Cold init from gpsim cold POR: diag_reset_por == 1, all others == 0.
- Runtime counters stay zero during extended idle (40M cycles).
- cmd 0x21 reply burst: 12 frames in order, all data bytes 0..0x0F.
- HID cmd 0x44 returns 15-byte payload with correct counters + version + role.

### Phase 2 — V1.71 CONTROL

Source-level (Tier A):
- Cache extends to 12 cells per PB.
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
- diag block in BANK 2 upper (0x2E5..0x2F1)
- 12-cell counter set including 5 reset-cause counters
- cmd 0x21 12-frame reply burst with andlw mask + ACK suppression
- cold init always-clear (no RCON gate)
- HID cmd 0x44 supported

Earlier revisions (0x32..0x36) are forward-compatible at the chain
protocol level (the V1.71 CONTROL parser case range 0x21..0x2C
gracefully handles 7-frame replies from 0x32..0x36 MAINs — the
extra 5 cells stay at 0 in the cache).

## Implementation phases (concrete order)

1. **Spec sign-off** — this document.
2. **V3.2 MAIN**: RAM EQUs + reset-cause classification + cmd 0x21
   12-frame burst + HID cmd 0x44 + EEPROM marker bump + tests.
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

- **Should we keep the existing 7-frame cmd 0x21 protocol as-is and
  add a new cmd 0x29 for the 5 reset counters?**  This avoids
  changing the V1.71 parser case range.  Argument for change-in-
  place: simpler protocol contract; CONTROL parser already does
  the col_offset math.  Argument against: forward compatibility
  with future V1.x CONTROL versions that don't know about the new
  reset cells.  **Decision: change in place.  V1.71 IS the target
  CONTROL for V3.2; older CONTROLs aren't in scope.**
