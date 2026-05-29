# V1.71/V3.2 Diagnostics Fault Injection Matrix

Last updated: 2026-05-20
Scope: deployed `DLCP_Control_V1.71.hex` with `DLCP_Firmware_V3.2.hex`
Status: simulator matrix implemented; `P` remains hardware-realistic
not-applicable until PIC18F2455 RA1 analog masking is modeled

## Problem

The Diagnostics page can only be trusted if every displayed counter has an
end-to-end test that starts from a realistic fault or event stimulus and ends
at the user-visible PB Diagnostics page.

The suite now covers the real `n/a` static-page protocol bug class for PB1/PB2,
the stale-pending same/opposite-target entry shape, and every displayed
Diagnostics row from stimulus through MAIN counter, CONTROL cache, and the
parked PB Diagnostics LCD page.  Direct RAM seeding remains in the suite as
parser/rendering coverage only; it is no longer the strongest evidence for any
displayed row in this matrix.

Direct RAM seeding is useful, but it is not enough.  It proves:

- CONTROL can parse and render a value if MAIN's diag RAM already contains it.
- The BF/21..BF/27 protocol path can move seeded bytes into CONTROL cache.
- The LCD renderer formats non-zero cells correctly.

It does not prove:

- The real event hook fires.
- The simulated fault model exercises the same code path that hardware would.
- The counter reaches the LCD without a manual RAM poke.
- Counter isolation holds under real fault traffic.

## Required Test Bar

A counter is not considered fully covered until there is at least one normal
sim test that does all of the following:

1. Injects or drives the real fault/event source.
2. Proves the target MAIN counter increments from firmware execution.
3. Enters the appropriate PB Diagnostics page through CONTROL.
4. Proves CONTROL cache receives the value through the correct transport:
   runtime rows `I/D/S/B/R/A/P` use `cmd 0x21` / `BF/21..BF/27`; reset rows
   `O/V/W/X` use `cmd 0x22` / `BF/28..BF/2B`.
5. Proves the LCD renders the expected counter letter/value.
6. Proves unrelated counters do not move unless the stimulus is expected to
   trigger them too.

For two-MAIN tests, PB1 and PB2 coverage should both exist unless the fault
source is intentionally local to only one MAIN.  PB-page surfacing tests must
prove static-page freshness: after navigating to the target PB page, the final
LCD/cache proof must not depend on repeated LEFT/RIGHT page cycling.  Navigation
may position the page, but it cannot be the mechanism that makes the visible PB
counter land.

## Closure States

Use these terms consistently in release notes and matrix updates:

- `protocol/rendering covered`: seeded MAIN RAM or source hooks prove parsing
  and LCD formatting only.  This is not release closure.
- `fault surfaced`: an injected fault drives MAIN firmware to increment the
  displayed counter and the value reaches CONTROL/LCD.
- `event surfaced`: a real operator/system event, not a fault, drives MAIN
  firmware to increment the displayed counter and the value reaches
  CONTROL/LCD.  This is the intended closure state for `S` and `B`.
- `reset-cause surfaced`: a simulator/RCON-latch reset-cause stimulus drives
  `O/V/W/X` through `cmd 0x22` and the PB Diagnostics LCD page.  Current
  V1.71/V3.2 builds leave WDT disabled, so `W` is structural/sim-forced
  coverage unless a future build enables a physical watchdog.
- `not applicable`: no realistic stimulus exists for the displayed field; the
  row must explain why and name the narrower invariant that remains tested.
- `gap`, `partial`, or `PB1-only`: open for release closure.

Final Diagnostics release closure requires every displayed field to be in
`fault surfaced`, `event surfaced`, `reset-cause surfaced`, or explicitly
justified `not applicable`.  The current simulator matrix is closed under
those states.  For `P`, hardware-realistic release closure is `not applicable`
unless the simulator first models PIC18F2455 ADCON1/PCFG masking and a
realistic RA1 stimulus.  Until then, the required invariant is simulator-only
PORTA-edge observability: exactly one firmware-observed RA1 edge increments
`diag_p`, reaches CONTROL/LCD, and does not repeat while the pin is held steady.

## Operator Classification

The LCD displays a mix of fault indicators, reset-cause flags, and OK behavior
counters. Operator interpretation must not treat all non-zero cells as faults.

| LCD | Classification | Notes |
| --- | --- | --- |
| `S` | OK behavior | Standby/shutdown dispatch count. Expected after intentional standby. |
| `B` | OK behavior | Bring-up/wake dispatch count. Expected after intentional wake/bring-up. |
| `O` | OK behavior | Power-on reset. It renders under `PBn OK` and never selects `PBn!` by itself. |
| `I` | Issue indicator | I2C/MSSP transport fault. |
| `D` | Issue indicator | DSP/TAS3108 fault episode. |
| `R` | Issue indicator | Recovery branch entry after DSP/I2C trouble. |
| `A` | Issue/suspicious indicator | AN0 standby-sense trigger; expected only if AN0 is intentionally driven. |
| `P` | Suspicious event telemetry | RA1 edge event; expected only if RA1 is intentionally toggled. |
| `V` | Issue indicator | Brown-out reset / rail sag. |
| `W` | Issue indicator | Watchdog reset. |
| `X` | Contextual issue indicator | Software reset; OK only if explained by known flash/reset/reboot action. |

`S`, `B`, and `O` are validation targets because the LCD must surface real
standby/wake/reset context, not because they are fault counters. Unexpected
`S/B` growth during playback can help explain an observed symptom, but the
fault is the unexpected state transition, not the counter increment itself.

## Current Coverage

| LCD | MAIN cell | Meaning | Current strongest coverage | Status |
| --- | --- | --- | --- | --- |
| `I` | `diag_i` | I2C transport faults | Real SRC4382 address/data NACK injection increments MAIN0/MAIN1 `diag_i`, then PB1/PB2 Diag renders `I`. | fault surfaced |
| `D` | `diag_d` | Volume-write DSP fault episode: retry exhaustion first sets `dsp_fault_flags.6` | Real TAS3108 volume-write address NACK exhausts retry budget, increments MAIN0/MAIN1 `diag_d`, then PB1/PB2 Diag renders `D`. | fault surfaced |
| `S` | `diag_s` | standby/shutdown dispatch | Real CONTROL STBY increments both MAINs, then PB1/PB2 Diag renders `S`. | OK event surfaced |
| `B` | `diag_b` | bring-up/wake dispatch | Real CONTROL WAKE increments both MAINs, then PB1/PB2 Diag renders `B`. | OK event surfaced |
| `R` | `diag_r` | Recovery branch entries: bounded MSSP/I2C timeout recovery or volume-DSP retry exhaustion | Real TAS3108 volume-write retry exhaustion and bounded MSSP STOP timeout both increment MAIN0/MAIN1 `diag_r`, then PB1/PB2 Diag renders `R`. | fault surfaced |
| `A` | `diag_a` | AN0 standby low-threshold trip | Real AN0 high-armed then low trip via `set_main_an0_sample` increments MAIN0/MAIN1 `diag_a`, then PB1/PB2 Diag renders `A`. | event surfaced |
| `P` | `diag_p` | RA1 PORTA-edge observability event | Simulator PORTA-edge stimulus via `set_main_pin(unit, "A", 1, level)` increments exactly once, holds steady without repeat, then PB1/PB2 Diag renders `P`. | not applicable for hardware-realistic release; simulator invariant covered |
| `O/V/W/X` | reset flags | POR/BOR/WDT/SW reset cause flags | Distinct per-MAIN simulator/RCON-latch reset-cause stimuli drive V3.2 cold-init classification, then PB1/PB2 Diag receives each reset flag through `cmd 0x22`; `O` renders as OK-context telemetry, while `V/W/X` select issue layout.  `W` is structural/sim-forced in current releases because WDT is disabled by policy. | reset-cause surfaced |

Current concrete tests:

- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_diag_static_wait_updates_pb1_and_pb2`
  covers the parked-page `n/a` class for PB1 and PB2 without LEFT/RIGHT
  convergence cycling.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_diag_visible_page_refreshes_on_next_cadence`
  covers the visible-page target-cadence bug for both PB pages.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_entry_clears_stale_pending_timeout_state`
  reproduces the stale-pending `n/a -> OK after minutes` class for PB1/PB2,
  with same-target and opposite-target pending runtime/reset transactions.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_injected_src4382_i2c_fault`
  covers `I` from real SRC4382 address/data NACK injection to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_standby_wake_event_counters`
  covers `S` and `B` from real STBY/WAKE actions to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode`
  covers `D` from real TAS3108 volume-write fault injection to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_volume_dsp_recovery_counter`
  covers the volume-write retry-exhaustion `R` producer to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_bounded_i2c_timeout_recovery_counter`
  covers the bounded MSSP STOP-timeout `R` producer to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_an0_standby_trigger`
  covers `A` from an AN0 high-armed/low-trip event to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_ra1_edge_counter`
  covers the simulator-only `P` PORTA-edge invariant to PB1/PB2 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_reset_cause_flags`
  covers `O/V/W/X` from distinct per-MAIN RCON reset-cause latch stimuli to
  PB1/PB2 cache/LCD via `cmd 0x22` / `BF/28..BF/2B`; the `O` case also verifies
  that OK-context reset telemetry can appear at the end of a `PBn!` issue row
  when there is room.
- `tests/sim/test_v171_v32_diag_fault_matrix_manifest.py`
  is the executable coverage manifest.  It fails if required row/PB tests are
  missing, skipped, xfailed, or if runtime/reset transports are conflated in
  this document.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_lcd_renders_mixed_counters`
  still uses direct MAIN diag RAM seeding. Keep it, but do not treat it as a
  replacement for real fault injection.

## Gap Closure Matrix

The row notes below are retained as implementation rationale.  The simulator
closures described in "Current Coverage" above have landed; future edits should
use this section to explain regressions or newly discovered hardware-only gaps.

### I: I2C Transport Fault

Existing PB1 test is acceptable because it injects real SRC4382 NACK behavior:

- `inject_main_src4382_address_nack(unit, count)`
- `inject_main_src4382_data_nack(unit, count)`

Implemented follow-up:

- The SRC4382 NACK test is parameterized for MAIN0/PB1 and MAIN1/PB2, and for
  both address and data NACK injection.

### D: DSP Fault Episode

Required stimulus:

- A real volume-write TAS3108 I2C fault that exhausts
  `volume_dsp_write` retries and reaches the first-set
  `dsp_fault_flags.6` path.

Implemented simulator support:

- The Python-facing simulator now exposes high-level per-MAIN TAS3108 address
  and data NACK injection, plus cause-specific stats/reset helpers.

Implementation plan:

1. Expose TAS3108 address/data NACK injection per MAIN, analogous to the
   SRC4382 helpers.
2. Drive a real volume change through CONTROL or MAIN frame injection so
   `volume_dsp_write` runs.
3. Assert MAIN `diag_d` increments once only when `dsp_fault_flags.6` was
   previously clear.  A ping-only failure is not a valid `D` closure stimulus
   unless firmware first adds a transition-gated `diag_d` hook to `dsp_ping`.
4. Enter PB1/PB2 Diag and assert `D` renders.
5. Add a transition-gating assertion: a continuing volume-write fault should
   not bump `D` every cadence unless firmware explicitly clears and re-enters
   the fault episode.

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode
```

### S/B: Standby and Bring-Up Events

Existing PB1 test is acceptable because it drives real CONTROL STBY/WAKE.

Implemented follow-up:

- The STBY/WAKE event test asserts both MAINs increment `S`/`B`, then surfaces
  the counters on both PB1 and PB2 Diagnostics pages.

### R: Recovery Branch Entry

Required stimulus:

- Cover at least one real recovery producer, and before release closure either
  cover both producers or explicitly document why one producer is out of scope:
  bounded MSSP/I2C timeout recovery, and `volume_dsp_write` retry exhaustion.

Likely implementation path:

1. Add or expose TAS3108 NACK injection that can persist through the full
   volume-DSP retry budget.
2. Issue a real volume command through CONTROL or MAIN frame injection.
3. Assert MAIN `diag_r` increments.
4. Assert MAIN stays responsive after the recovery branch.
5. Enter PB Diag and assert `R` renders.
6. Add a companion bounded-timeout `I+R` LCD surfacing test, or keep the row
   open with a named reason until that producer is covered.

Risk:

- The same stimulus is expected to increment `I` for ACKSTAT NACK transport
  faults, `R` for retry exhaustion or bounded timeout recovery, and `D` only if
  `dsp_fault_flags.6` was previously clear.  The test should explicitly allow
  these expected co-triggers, but `R` is the required counter for this row.

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_volume_dsp_recovery_counter
```

### A: AN0 Standby Trigger

Required stimulus:

- Use `Chain.set_main_an0_sample(unit, value)` to drop AN0 below the runtime
  low threshold while the MAIN is active.

Implementation plan:

1. Boot a healthy V1.71/V3.2 chain.
2. For the selected MAIN, set AN0 above threshold and confirm `diag_a == 0`.
3. Hold AN0 at or above `0x0229` through at least one full `0x64-count`
   monitor cadence, or poll the armed hysteresis bit, so
   `an0_hysteresis_monitor` is armed.
4. Drop AN0 below `0x0228` through another bounded monitor cadence.
5. Assert MAIN `diag_a` increments.
6. Enter PB Diag and assert `A` renders.
7. Verify the expected side effect: the low crossing also schedules standby
   through `event_flags.bit2`, so `S` can be an expected co-trigger after
   `standby_event_dispatch`. If that makes the test hard to keep stable,
   isolate the MAIN-only counter test first, then add the full CONTROL LCD
   path.

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_an0_standby_trigger
```

### P: RA1 Edge Event

Required stimulus:

- Toggle MAIN RA1 through the simulator pin model and let
  `ra1_edge_monitor` observe it from `periodic_service_loop`.

Implemented caveat:

- `Chain.set_main_pin(unit, port, bit, level)` already exists.  The remaining
  release caveat is not simulator observability; it is that V3.2 assigns no
  real product function to RA1 and the simulator does not yet model the
  PIC18F2455 ADCON1/PCFG analog masking that would make a hardware-realistic
  RA1 stimulus meaningful.

Precondition:

- `P` is simulator PORTA-edge observability.  V3.2 assigns no real hardware
  product function to RA1, and the simulator does not currently model
  PIC18F2455 ADCON1/PCFG analog masking for this pin.  Do not call this row
  hardware-realistic unless that masking is modeled or the release note uses
  the narrower simulator-only precondition.

Implementation plan:

1. Boot healthy and sample the baseline RA1 level through firmware.
2. Step until `ra1_edge_monitor` has observed that baseline, then snapshot
   `diag_p`.
3. Drive exactly one opposite-level RA1 change.
4. Step to the next `ra1_edge_monitor` pass.
5. Assert MAIN `diag_p` increments by exactly one.
6. Hold RA1 steady and assert no further increment.
7. Enter PB Diag and assert `P` renders.

Expected Co-Triggers:

| Stimulus | Required counter | Expected co-triggers | Not expected |
| --- | --- | --- | --- |
| SRC4382 address/data NACK | `I` | none unless the test deliberately combines faults | `D/R/A/P` |
| TAS3108 volume-write ACKSTAT NACK through retry exhaustion | `R`; `D` if bit 6 was clear | `I`; conditional `D` | `A/P` |
| TAS3108 ping-only NACK | none for `D` under current source | possible `I` | `D` unless firmware adds a hook |
| Bounded MSSP timeout recovery | `R` | `I` | `D` unless volume-write fault state also transitions |
| AN0 high-armed then low trip | `A` | possible `S` after standby dispatch | `D/R/P` |
| One RA1 PORTA edge | `P` | none | second `P` increment while held steady |

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_ra1_edge_counter
```

## Implemented Simulator Hooks

Hooks added or used to close the matrix:

| Hook | Used for | Notes |
| --- | --- | --- |
| `inject_main_tas3108_address_nack(unit, count)` | `D`, `R` | Mirrors SRC4382 NACK helpers. |
| `inject_main_tas3108_data_nack(unit, count)` | TAS3108 byte-level fault coverage | Present for byte-level DSP write failure coverage and compatibility with future row refinements. |
| cause-specific TAS3108 stats and remaining fault budgets | `D`, `R` | Tests use consumed address/data counters instead of aggregate `bytes_nacked`. |
| `reset_main_tas3108_stats(unit)` / read stats | `D`, `R` | Stats reset does not clear injected-fault budgets. |
| `set_main_mssp_stop_fault(unit, ...)` / `force_reset_main_mssp_unit(unit)` | bounded-timeout `R` | Per-MAIN MSSP STOP-timeout producer coverage. |
| `set_main_pin(unit, "A", 1, level)` | `P` | Drives the simulator-only RA1 PORTA-edge invariant without RAM pokes. |
| PB2 versions of helper flows | all rows | Prevents PB1-only false confidence. |
| `tests/sim/test_v171_v32_diag_fault_matrix_manifest.py` | required-test manifest | Fails if required row/PB/fault-kind tests are missing, skipped, xfailed, reduced to direct diag-RAM seeding, or if runtime/reset transports are conflated. |

## Acceptance Commands

Focused matrix manifest and row gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 \
  tests/sim/test_v171_v32_diag_fault_matrix_manifest.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_entry_clears_stale_pending_timeout_state \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_injected_src4382_i2c_fault \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_standby_wake_event_counters \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_volume_dsp_recovery_counter \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_bounded_i2c_timeout_recovery_counter \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_an0_standby_trigger \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_ra1_edge_counter \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_reset_cause_flags
```

Full sim gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Release Rule

Do not call Diagnostics fully validated while any displayed counter is only
covered by source hooks, direct RAM seeding, PB1-only tests, or navigation-
driven convergence.  For release notes, distinguish:

- "Protocol/rendering covered" means seeded MAIN RAM reaches CONTROL/LCD.
- "Fault surfaced" means a real injected fault/event increments MAIN RAM and
  reaches CONTROL/LCD.
- "Event surfaced" means a real operator/system event increments MAIN RAM and
  reaches CONTROL/LCD.
- "Reset-cause surfaced" means a simulator/RCON-latch reset-cause stimulus
  reaches CONTROL/LCD through `cmd 0x22`.  It does not imply the current
  firmware enables WDT; `W` remains structural/sim-forced today.

The release target is every displayed field in one of the explicit closure
states above.  As of this update there are no simulator open rows; `P` is
closed only under the documented simulator-only PORTA-edge invariant and
remains not applicable for hardware-realistic closure until PIC18F2455 RA1
analog masking is modeled.
