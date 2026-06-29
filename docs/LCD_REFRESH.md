# LCD Refresh Budget

Status: implemented for CONTROL V1.73 rev `0x5C`

This document captures the LCD refresh behavior observed in the native
CONTROL+PB1+PB2 chain sim and defines the refresh-budget target.

## Goal

CONTROL should keep every visible menu responsive without continuously
rewriting stable LCD text.

Soft target:

- Stable parked menu pages should stay below 20 HD44780 DDRAM data writes per
  second, measured across both 16-character rows after the page has settled.
- No individual status cell should be repainted at a high cadence while its
  displayed value is unchanged.
- Direct user-visible changes should still feel instantaneous.

The 20 writes/s number is a soft engineering target, not a protocol ABI. It is
intended to prevent LCD work from stealing foreground time from RX parsing, IR
handling, health polling, filename traffic, and menu navigation.

## Measurement Model

Measurement uses the native chain simulator's `lcd_ddram_write_count(addr)`
counter. It counts HD44780 DDRAM data bytes written to visible LCD cells. It
does not count LCD command bytes or firmware loop iterations.

Default measurement window:

- Boot current canonical CONTROL+MAIN images.
- Wait for the page to settle.
- Measure a 10 s parked-page window.
- Count row 0 addresses `0x00..0x0F`, row 1 addresses `0x40..0x4F`, and key
  status cells such as row 0 col 15 (`0x0F`).

Short transition bursts are allowed when a page is entered or a user action
changes visible text. The target applies after the burst has completed.

## Pre-Fix Behavior

Measured on the pre-fix canonical V1.73 CONTROL plus V3.5 MAIN images on
2026-06-28, before the LCD refresh-budget fixes.

Top-level split menu ring:

```text
Volume -> Preset -> Input PB1 -> Input PB2 -> Setup -> PB1 Diag -> PB2 Diag -> Volume
```

Observed default idle rates:

| Page | Row 0 writes/s | Row 1 writes/s | Total writes/s | Row 0 col 15 writes/s | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Volume | 1.0 | 216.0 | 217.0 | 0.2 | title stable; row-1 health suffix churn |
| Preset | 3744.0 | 35.2 | 3779.2 | 416.0 | row-0 over-refresh; A/B suffix can briefly blank |
| Input PB1 | 0.0 | 216.8 | 216.8 | 0.0 | title stable; row-1 health suffix churn |
| Input PB2 | 708.8 | 1416.0 | 2124.8 | 44.3 | full-row redraw loop; sampled text stable |
| Setup | 1.6 | 216.0 | 217.6 | 0.1 | title stable; row-1 health suffix churn |
| PB1 Diag | 12.8 | 12.8 | 25.6 | 0.8 | near target; full two-line cadence |
| PB2 Diag | 12.8 | 12.8 | 25.6 | 0.8 | near target; full two-line cadence |
| BL Timeout editor | 0.0 | 0.0 | 0.0 | 0.0 | editor suppresses health suffix |

Field-shaped inputs, PB1 `S/PDIF` and PB2 `AES`, showed the same classification:

| Page | Total writes/s | Notes |
| --- | ---: | --- |
| Volume, PB1 S/PDIF | 209.6 | row-1 health suffix churn |
| Preset | 3849.2 | same row-0 over-refresh |
| Input PB1, S/PDIF | 210.6 | row-1 health suffix churn |
| Input PB2, AES | 2118.4 | same full-row redraw loop |
| Setup | 210.4 | row-1 health suffix churn |
| BL Timeout editor | 0.0 | quiet |

## Post-Fix Behavior

Measured on canonical CONTROL V1.73 rev `0x5C` plus MAIN V3.5 on
2026-06-28, using the same 10 s visible-DDRAM measurement window.

Observed default idle rates:

| Page | Row 0 writes/s | Row 1 writes/s | Total writes/s | Row 0 col 15 writes/s | Notes |
| --- | ---: | ---: | ---: | ---: | --- |
| Volume | 1.0 | 2.0 | 3.0 | 0.2 | bounded status/suffix upkeep only |
| Preset | 0.0 | 19.2 | 19.2 | 0.0 | active long filename scroll; row 0 quiet |
| Input PB1 | 0.0 | 0.0 | 0.0 | 0.0 | stable row cache |
| Input PB2 | 0.0 | 0.0 | 0.0 | 0.0 | stable title/option cache |
| Setup | 1.6 | 2.0 | 3.6 | 0.1 | bounded status/suffix upkeep only |
| PB1 Diag | 1.6 | 1.6 | 3.2 | 0.1 | unchanged-value LCD suppression |
| PB2 Diag | 1.6 | 1.6 | 3.2 | 0.1 | unchanged-value LCD suppression |
| BL Timeout editor | 0.0 | 0.0 | 0.0 | 0.0 | editor remains quiet |

Field-shaped inputs, PB1 `S/PDIF` and PB2 `AES`:

| Page | Total writes/s | Notes |
| --- | ---: | --- |
| Volume, PB1 S/PDIF | 3.0 | bounded status/suffix upkeep only |
| Preset | 19.2 | active long filename scroll; row 0 quiet |
| Input PB1, S/PDIF | 0.0 | stable row cache |
| Input PB2, AES | 0.0 | stable title/option cache |
| Setup | 7.2 | bounded status/suffix upkeep only |
| BL Timeout editor | 0.0 | quiet |

The worst parked page is now Preset with an actively scrolling long filename at
`19.2` visible writes/s, below the `<20 writes/s` soft target. Static Input
pages are quiet after page-entry rendering, and Diagnostics keep the existing
query cadence while suppressing unchanged full-screen LCD writes.

## Pre-Fix Root Causes

### Preset Row 0 Reassert

`v172_preset_filename_service` reasserts row 0 every 32 foreground service
passes while parked on the Preset page. The service loop is fast enough that
this becomes thousands of row-0 writes per second.

Relevant source:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`: `v172_preset_filename_service`
- `src/dlcp_fw/asm/dlcp_control_ram.inc`: `v173_row0_reassert_div`

The current Preset render path can temporarily show row 0 as:

```text
Preset
```

with spaces through col 15 before a later status patch writes `A` or `B`.
That blank-then-real sequence is user-visible risk and should be removed.

### Input PB2 Health-Dirty Redraw

While parked on split Input PB2, a health display dirty flag can branch back to
`input_screen`, causing full row redraws. This is how Input PB2 reaches roughly
2.1k DDRAM writes/s even when the sampled text remains unchanged.

Relevant source:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`: `input_screen__state_still_active`
- `src/dlcp_fw/asm/dlcp_control_v173.asm`: `input_screen_write_title`

### Shared Health Suffix Writer

Volume, Input PB1, and Setup opt into `v171_health_patch_suffix`, which writes
the row-1 tail cells. The current observed stable rate is about 210-217 row-1
writes/s.

Relevant source:

- `src/dlcp_fw/asm/dlcp_control_v173.asm`: `v171_health_patch_suffix`

The BL Timeout editor correctly suppresses this path while active.

## Target Behavior

### Stable Page Budget

For each parked visible page, after one second of settle:

- Total visible DDRAM writes across both rows should be below 20 writes/s over a
  10 s window.
- Prefer 0 writes/s for pages whose text is fully stable.
- Diagnostic pages may refresh periodically, but should be reduced below the
  same 20 writes/s soft target where practical.
- Filename scrolling must also respect the total budget. If a full 16-character
  row is rewritten for each scroll step, the scroll cadence must be slow enough
  to keep the total page rate below target. A partial/cached row update is
  better.

### Responsiveness Budget

Reducing refresh rate must not make the UI feel delayed.

Expected responsiveness:

- Page navigation should render the new page immediately after the existing
  button debounce/event path recognizes LEFT or RIGHT.
- A local preset, input, mute, volume, or setup-option change should update the
  affected LCD cells in the same event handling pass.
- IR and host-triggered preset/input changes should update visible state on the
  next foreground service pass after the command is accepted.
- Delayed/background data, such as a filename fetched from MAIN, may update when
  the data arrives, but the page title and status cells must remain coherent in
  the meantime.

Do not add artificial sleeps or wait-for-periodic-refresh behavior to achieve
the write-rate target. The fix should be dirty-state driven: write immediately
when visible state changes, then become quiet.

### No Blank-Then-Real Status Cells

Status cells must not intentionally pass through a blank value when the final
value is already known.

Rules:

- Preset row 0 col 15 should be `A`, `B`, or a deliberate fault/status glyph
  whenever CONTROL knows the active preset.
- Do not render `Preset          ` and later patch `A` or `B` as a separate
  steady-state mechanism.
- If a full-row repaint is required, include the final current status glyphs in
  that repaint or patch them immediately in the same bounded render sequence.
- If the new value is not known, preserve the previous coherent value until a
  real replacement is available.
- A blank is valid only when blank is the intended final visible state, not as a
  transient placeholder for a known status value.

### Dirty-State Contract

Each LCD owner should maintain enough local state to decide whether a write is
necessary.

Recommended contract:

- Page entry paints the full page once.
- Page-local changes patch only the changed cell or row.
- Background services compute the desired visible suffix/title first, compare
  it to a cached rendered value, and return without LCD writes if unchanged.
- Defensive self-heal should be triggered by explicit invalidation events, not
  by a fast free-running foreground loop. If a periodic belt is still kept, it
  should be slow enough to remain inside the global write budget.

## Implementation Direction

Priority order:

1. Fix Preset row 0.
   - Replace the every-32-pass row0 reassert with dirty/invalidation-driven
     repaint plus, at most, a slow bounded self-heal.
   - Ensure the row0 repaint emits the final A/B/fault status coherently.
   - Keep filename query/scroll behavior responsive without using row0 churn as
     a safety mechanism.

2. Fix Input PB2 redraw.
   - Replace full `input_screen` redraw on unchanged health-dirty state with a
     cached title/status decision.
   - Redraw Input PB2 title only when its health class changes between normal,
     old, and lost.
   - Patch row1 option text only when the selected input label changes.

3. Fix shared health suffix churn.
   - Cache the last rendered row-1 suffix.
   - Write the suffix only when the computed suffix changes or on a deliberately
     slow self-heal cadence.
   - Preserve the BL Timeout editor suppression.

4. Reduce Diagnostics cadence if it remains above target.
   - Diag is close to the target and visually stable, so it is lower priority.
   - Prefer sparse cell updates when only identity/link values change.

## Test Requirements

Add a sim regression that parks on every visible page and asserts:

- Total visible DDRAM writes are below the configured soft limit after settle.
- Preset row 0 col 15 never samples as a blank while active preset is known.
- Page navigation and local edits still update the visible LCD state promptly.
- Field-shaped PB1/PB2 input configuration is covered, including PB1 `S/PDIF`
  and PB2 `AES`.

The test should report measured rates in failure output so regressions are easy
to classify. The threshold should default to 20 writes/s but remain named as a
soft target in the test/doc terminology until the firmware fix has stabilized.
