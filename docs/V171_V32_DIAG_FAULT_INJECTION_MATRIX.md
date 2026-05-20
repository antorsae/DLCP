# V1.71/V3.2 Diagnostics Fault Injection Matrix

Last updated: 2026-05-20
Scope: deployed `DLCP_Control_V1.71.hex` with `DLCP_Firmware_V3.2.hex`
Status: active test-gap closure plan

## Problem

The Diagnostics page can only be trusted if every displayed counter has an
end-to-end test that starts from a realistic fault or event stimulus and ends
at the user-visible PB Diagnostics page.

The current suite now covers the real `n/a` stale-pending protocol bug, and it
has real fault/event surfacing for some counters, but the full displayed
counter matrix is not yet closed.  In particular, `D`, `R`, `A`, and `P` still
lean too heavily on source-hook checks and direct RAM seeding.

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
4. Proves CONTROL cache receives the counter through `cmd 0x21` /
   `BF/21..BF/27`.
5. Proves the LCD renders the expected counter letter/value.
6. Proves unrelated counters do not move unless the stimulus is expected to
   trigger them too.

For two-MAIN tests, PB1 and PB2 coverage should both exist unless the fault
source is intentionally local to only one MAIN.

## Current Coverage

| LCD | MAIN cell | Meaning | Current strongest coverage | Status |
| --- | --- | --- | --- | --- |
| `I` | `diag_i` | I2C transport faults | Real SRC4382 address/data NACK injection increments MAIN0 `diag_i`, then PB1 Diag renders `I`. | good for PB1; add PB2 mirror |
| `D` | `diag_d` | DSP fault episode, `dsp_fault_flags.6` transition | Source-hook and seeded-render coverage only. | gap |
| `S` | `diag_s` | standby/shutdown dispatch | Real CONTROL STBY action increments MAIN0 `diag_s`, then PB1 Diag renders `S`. | good for PB1; add PB2 mirror |
| `B` | `diag_b` | bring-up/wake dispatch | Real CONTROL WAKE action increments MAIN0 `diag_b`, then PB1 Diag renders `B`. | good for PB1; add PB2 mirror |
| `R` | `diag_r` | volume-DSP retry-exhausted recovery | Source-hook and cascade-negative coverage only. | gap |
| `A` | `diag_a` | AN0 standby low-threshold trip | Simulator has `set_main_an0_sample`, but no end-to-end LCD surfacing test. | gap |
| `P` | `diag_p` | RA1 edge event | Source-hook and seeded-render coverage only. | gap |
| `O/V/W/X` | reset flags | POR/BOR/WDT/SW reset cause flags | Cold-init/source/HID/protocol coverage exists; live LCD surfacing should remain tied to PB Diag tests. | partial |

Current concrete tests:

- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_entry_clears_stale_pending_timeout_state`
  reproduces the real stale-pending `n/a -> OK after minutes` class.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_injected_src4382_i2c_fault`
  covers `I` from real SRC4382 NACK injection to PB1 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_diag_lcd_surfaces_standby_wake_event_counters`
  covers `S` and `B` from real STBY/WAKE actions to PB1 LCD.
- `tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_lcd_renders_mixed_counters`
  still uses direct MAIN diag RAM seeding. Keep it, but do not treat it as a
  replacement for real fault injection.

## Gap Closure Matrix

### I: I2C Transport Fault

Existing PB1 test is acceptable because it injects real SRC4382 NACK behavior:

- `inject_main_src4382_address_nack(unit, count)`
- `inject_main_src4382_data_nack(unit, count)`

Required follow-up:

- Add a PB2 mirror. The test should configure MAIN1's SRC4382, inject the NACK
  on unit `1`, navigate to PB2 Diag, and assert `PB2: I...` or row-1 cache
  equivalent.

### D: DSP Fault Episode

Required stimulus:

- A TAS3108/DSP I2C fault that drives the `dsp_fault_flags.6` 0->1 transition.

Current blocker:

- The Python-facing simulator exposes SRC4382 NACK injection, but there is no
  equivalent high-level TAS3108 fault injection in the chain facade for the
  exact V3.2 DSP-fault path.

Implementation plan:

1. Expose TAS3108 address/data NACK injection per MAIN, analogous to the
   SRC4382 helpers.
2. Drive a DSP transaction that V3.2 already performs, preferably a volume
   write or ping path.
3. Assert MAIN `diag_d` increments once for the transition.
4. Enter PB1/PB2 Diag and assert `D` renders.
5. Add a transition-gating assertion: a continuing fault should not bump `D`
   every cadence unless the firmware explicitly clears and re-enters the fault
   episode.

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode
```

### S/B: Standby and Bring-Up Events

Existing PB1 test is acceptable because it drives real CONTROL STBY/WAKE.

Required follow-up:

- Add PB2 assertion in the same test or a companion test. Both MAINs should
  increment `S` on standby and `B` on wake in the normal two-MAIN chain.
- Keep the existing STBY/WAKE reconnect tests separate. Those prove system
  recovery; this matrix proves Diagnostics surfacing.

### R: Recovery Branch Entry

Required stimulus:

- Force `volume_dsp_write` to exhaust retries and enter its recovery branch.

Likely implementation path:

1. Add or expose TAS3108 NACK injection that can persist through the full
   volume-DSP retry budget.
2. Issue a real volume command through CONTROL or MAIN frame injection.
3. Assert MAIN `diag_r` increments.
4. Assert MAIN stays responsive after the recovery branch.
5. Enter PB Diag and assert `R` renders.

Risk:

- The same stimulus may also increment `D` if it creates a DSP fault episode.
  The test should explicitly allow `D` if expected, but `R` is the required
  counter for this row.

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
3. Drop AN0 below threshold long enough for `an0_hysteresis_monitor` to trip.
4. Assert MAIN `diag_a` increments.
5. Enter PB Diag and assert `A` renders.
6. Verify the expected side effect: the MAIN may also schedule standby through
   `event_flags.bit2`. If that makes the test hard to keep stable, isolate the
   MAIN-only counter test first, then add the full CONTROL LCD path.

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_an0_standby_trigger
```

### P: RA1 Edge Event

Required stimulus:

- Toggle MAIN RA1 through the simulator pin model and let
  `ra1_edge_monitor` observe it from `periodic_service_loop`.

Current blocker:

- The chain facade must provide a reliable per-MAIN pin setter for RA1, or a
  helper should be added if only CONTROL pin helpers are currently ergonomic.

Implementation plan:

1. Add a per-MAIN GPIO pin helper if needed.
2. Boot healthy, snapshot `diag_p`.
3. Toggle RA1 low/high or high/low once.
4. Step enough for `periodic_service_loop`.
5. Assert MAIN `diag_p` increments once.
6. Enter PB Diag and assert `P` renders.

Candidate test name:

```text
test_v171_v32_diag_lcd_surfaces_ra1_edge_counter
```

## Required Simulator Hooks

Missing or weak hooks to add before the matrix can close:

| Hook | Needed for | Notes |
| --- | --- | --- |
| `inject_main_tas3108_address_nack(unit, count)` | `D`, `R` | Mirror SRC4382 NACK helpers. |
| `inject_main_tas3108_data_nack(unit, count)` | `D`, `R` | Needed for byte-level DSP write failure coverage. |
| `reset_main_tas3108_stats(unit)` / read stats | `D`, `R` | Lets tests prove the injected fault was actually consumed. |
| `set_main_pin(unit, port, bit, level)` or RA1-specific helper | `P` | Needed to drive `ra1_edge_monitor` without RAM pokes. |
| PB2 versions of existing helper flows | `I`, `S`, `B`, later `D/R/A/P` | Prevent PB1-only false confidence. |

## Acceptance Commands

Focused matrix gate, once the missing rows are implemented:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v32_layer5_diag_counters.py \
  tests/sim/test_v32_src4382_autodetect_polling.py
```

Full sim gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Release Rule

Do not call Diagnostics fully validated while any displayed counter is only
covered by source hooks or direct RAM seeding.  For release notes, distinguish:

- "Protocol/rendering covered" means seeded MAIN RAM reaches CONTROL/LCD.
- "Fault surfaced" means a real injected fault/event increments MAIN RAM and
  reaches CONTROL/LCD.

The release target is all displayed fields in the second category.
