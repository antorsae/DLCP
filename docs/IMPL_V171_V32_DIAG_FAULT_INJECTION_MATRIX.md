# V1.71/V3.2 Diagnostics Fault Injection Matrix Implementation Plan

Last updated: 2026-05-20
Scope: implementation plan for `docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md`
Status: implemented for simulator coverage; `P` remains hardware-realistic
not-applicable until PIC18F2455 RA1 analog masking is modeled

## Objective

Convert every displayed V1.71/V3.2 Diagnostics counter from seeded or
source-hook coverage into end-to-end fault-surfacing coverage:

1. Drive a realistic fault or event source in the simulator.
2. Prove V3.2 MAIN firmware increments the intended counter.
3. Prove V1.71 CONTROL receives runtime counters through `cmd 0x21` /
   `BF/21..BF/27`, and reset flags through `cmd 0x22` / `BF/28..BF/2B`.
4. Prove the PB1 or PB2 Diagnostics LCD page renders the value.
5. Prove unrelated displayed counters stay stable unless the stimulus is
   expected to co-trigger them.

The companion matrix is the coverage ledger.  This document records the work
plan and the implemented closure shape.

## Non-Goals

- Do not change the V1.71/V3.2 Diagnostics protocol or LCD layout while closing
  this test gap.
- Do not count direct MAIN diag-RAM seeding as closure evidence.  Seeded tests
  remain useful for parser/render regressions only.
- Do not require live hardware fault injection to close a simulator row.  Live
  hardware gates can be added later as confidence checks.
- Do not hide firmware bugs behind simulator shortcuts.  If a fault stimulus
  reaches the right peripheral model but the counter does not increment, keep
  the red test and fix the firmware or the simulator model explicitly.

## Current Surfaces

Already usable:

- `Chain.inject_main_src4382_address_nack(unit, count)` and
  `Chain.inject_main_src4382_data_nack(unit, count)` for `I`.
- `Chain.reset_main_src4382_stats(unit)` and
  `Chain.read_main_src4382_stats(unit)` for proving SRC4382 injections were
  consumed with cause-specific address/data consumed and remaining-budget
  counters.
- `Chain.set_main_an0_sample(unit, value)` for `A`.
- `Chain.set_main_pin(unit, port, bit, level)` for `P`, subject to the existing
  caveat that the pin must be configured as a general input when driven.  This
  is simulator PORTA-edge observability today; PIC18F2455 ADCON1/PCFG analog
  masking is not modeled for RA1, so do not overclaim hardware-realistic `P`
  closure without adding that model or documenting the narrower precondition.
- TAS3108 write-log readback and MAIN0-only address-NACK injection through the
  existing DSP I2C compatibility helpers.

Implemented in this closure:

- Per-MAIN TAS3108 fault APIs matching the SRC4382 API shape.
- TAS3108 post-address data-byte NACK injection.
- TAS3108 stats read/reset helpers for proof that a DSP fault was consumed.
- End-to-end LCD surfacing tests for `D`, `R`, `A`, `P`, and PB2 mirrors of
  `I`, `S`, and `B`.
- Per-MAIN MSSP STOP-timeout helpers for the bounded-timeout `R` producer.
- Executable manifest coverage in
  `tests/sim/test_v171_v32_diag_fault_matrix_manifest.py`.

## Row Completion Rule

For each row in the matrix, add a focused test that fails if any hop is broken:

| Hop | Required assertion |
| --- | --- |
| Stimulus | The fault/event hook was consumed or the physical-style event happened, with cause-specific stats or explicit event evidence. |
| MAIN RAM | The intended `diag_*` cell increments from firmware execution by the expected delta from a before snapshot. |
| CONTROL cache | The visible PB cache changes to the post-MAIN value through the correct transport, not from a stale or seeded value. Runtime rows use `BF/21..BF/27`; reset rows use `BF/28..BF/2B`. |
| LCD | The PB Diagnostics page is visible and not showing `n/a`; the counter token/value is rendered. |
| Isolation | Other counters are unchanged, except listed co-trigger counters. |

Prefer a helper with this shape in `tests/sim/test_v171_v32_layer5_diag_chain.py`:

```python
def assert_diag_counter_surfaces(
    chain,
    *,
    pb_idx: int,
    main_idx: int,
    offset: int,
    label: str,
    min_delta: int = 1,
    allowed_cotriggers: set[int] | None = None,
    stimulus_stats: Mapping[str, int] | None = None,
) -> None:
    ...
```

The helper must take before/after snapshots of both MAIN diag blocks, both
CONTROL PB caches, LCD rows, and any relevant peripheral injection stats.  It
must reject already-nonzero stale state unless the target counter increases by
the expected delta after the real stimulus.  LCD assertions should be
label-aware, but should not depend on incidental spacing outside the compact
Diagnostics layout.

Add a separate reset-row helper or mode for `O/V/W/X`.  It must use
`cmd 0x22` / `BF/28..BF/2B`, assert the reset cache cells, and assert the
reset-seen/last-frame behavior that marks the reset burst complete.  Do not run
reset rows through the runtime `cmd 0x21` helper.

## Implementation Phases

### Phase 0: Stabilize Test Helpers

- Add a shared MAIN diag snapshot helper if the existing
  `_rust_main_diag_block` is not enough for delta assertions.
- Add a visible-page/cache wait helper that can target PB1 or PB2 and does not
  rely on indefinite navigation wiggles after the visible page is stable.
- Add `assert_visible_pb_diag_refreshes_static(pb_idx, ...)`: after the test
  enters the PB page, it must send no navigation input, assert the display
  state is the target PB page, observe the next bounded cadence, prove the
  visible PB target is queried, and fail if the LCD remains `n/a`.
- Add an isolation assertion that reports the complete before/after tuple for
  both MAINs and both CONTROL PB caches.
- Keep the stale-pending `n/a` regression test independent and parameterize it
  for PB1 and PB2.  Seed runtime/reset pending bits with zero timeout bytes,
  cover same-target and opposite-target states, enter the page once, static-wait
  without LEFT/RIGHT cycling, and require `n/a` to clear within the bounded
  cadence.
- Add an executable required-test manifest or `diag_fault_matrix` marker before
  closure.  It must fail if a required row/PB case is missing, skipped, or
  xfailed, unless that row is explicitly documented as `not applicable`.

### Phase 1: Close Existing Real-Coverage Mirrors

Add PB2 coverage for rows that already have a realistic PB1 stimulus:

- `I`: configure MAIN1 SRC4382 in the same deterministic no-source state, inject
  address or data NACK on unit `1`, then prove PB2 Diag renders `I`.
- `S` and `B`: drive a normal CONTROL standby/wake cycle and prove both MAIN0
  and MAIN1 increment `diag_s` and `diag_b`; then prove PB1 and PB2 cache/LCD
  surfacing.

Candidate tests:

```text
test_v171_v32_diag_lcd_surfaces_injected_src4382_i2c_fault_pb2
test_v171_v32_diag_lcd_surfaces_standby_wake_event_counters_pb2
```

Update the matrix status for `I`, `S`, and `B` only after the PB2 assertions are
green.

### Phase 2: Expose TAS3108 Fault Hooks

Add a symmetric per-MAIN TAS3108 facade before implementing `D` and `R`.

Rust core:

- `crates/dlcp-sim/src/peripherals/tas3108.rs`
  - add data-byte NACK injection, mirroring SRC4382 semantics;
  - expose cause-specific stats containing at least fault-injection address
    NACKs consumed, data NACKs consumed, and remaining address/data NACK
    counts;
  - keep aggregate `bytes_nacked` as observability only.  Do not use it as
    proof that a fault budget was consumed because normal address mismatches
    also NACK when SRC4382 traffic is on the same bus;
  - make stats reset separate from fault-budget reset.  `reset_main_tas3108_stats`
    must not clear injected-fault budgets;
  - keep address mismatch behavior isolated from the injection counters.
- `crates/dlcp-sim/src/chain.rs`
  - add per-MAIN helpers that locate the TAS3108 slave coupled to a MAIN.

Python facade:

- `crates/dlcp-sim-py/src/lib.rs`
  - expose `inject_main_tas3108_address_nack(unit, count)`;
  - expose `inject_main_tas3108_data_nack(unit, count)`;
  - expose `reset_main_tas3108_stats(unit)` / `read_main_tas3108_stats(unit)`.
- `src/dlcp_fw/sim/dlcp_sim_native.py`
  - wrap those methods with the same validation style used by the SRC4382
    helpers.

Keep the existing MAIN0-only `set_dsp_i2c_fault` compatibility helper for old
tests, but do not use it as the primary V1.71/V3.2 matrix API.

Phase 2 acceptance requires the native module to be rebuilt and visible to
Python:

```bash
cargo test -p dlcp-sim -p dlcp-sim-py
cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.sim.dlcp_sim_native import Chain
for name in (
    "inject_main_tas3108_address_nack",
    "inject_main_tas3108_data_nack",
    "reset_main_tas3108_stats",
    "read_main_tas3108_stats",
):
    assert hasattr(Chain, name), name
PY
```

### Phase 3: Close `D` and `R`

`D` stimulus:

- Inject a TAS3108 fault into a real volume-write sequence that exhausts
  `volume_dsp_write` retries.  Under current V3.2 source, ping-only failures
  set or clear `dsp_fault_flags.6` but do not increment `diag_d`.
- Trigger a real volume change through CONTROL or MAIN frame injection so
  `volume_dsp_write` runs.
- Assert `diag_d` increments once only if `dsp_fault_flags.6` was previously
  clear.  If product semantics should count ping-only DSP episodes, first add a
  transition-gated firmware hook in `dsp_ping_nack`, then update this plan.
- Continue stepping under the same persistent fault and assert `diag_d` does
  not increment every cadence unless firmware clears and re-enters the fault
  state by design.

`R` stimulus:

- Cover both `R` producers before release closure, or keep the row open with a
  named out-of-scope rationale: bounded MSSP/I2C timeout recovery, and
  `volume_dsp_write` retry exhaustion.
- For the volume-write producer, force `volume_dsp_write` to exhaust its retry
  budget and enter the recovery branch.
- For the bounded-timeout producer, drive a SEN/PEN/BF timeout shape through
  the existing MSSP fault model and assert the expected `I+R` pair.
- Assert `diag_r` increments and the MAIN remains responsive after recovery.
- Allow expected co-triggers: ACKSTAT NACKs can increment `I`, retry exhaustion
  increments `R`, and `D` increments only if bit 6 was previously clear.  A
  bounded MSSP timeout recovery can increment `I+R` without `D`.  Require `R`
  to move for the `R` row.

Candidate tests:

```text
test_v171_v32_diag_lcd_surfaces_tas3108_dsp_fault_episode
test_v171_v32_diag_lcd_surfaces_volume_dsp_recovery_counter
test_v171_v32_diag_lcd_surfaces_bounded_i2c_timeout_recovery_counter
```

Run each test for PB1 and PB2, either parametrized by `main_idx/pb_idx` or with
separate names if the setup diverges.

### Phase 4: Close `A`

Use the existing AN0 sample hook:

1. Boot the V1.71/V3.2 chain to Volume.
2. Set AN0 at or above `0x0229` and hold through one full `0x64-count`
   monitor cadence, or poll the armed hysteresis bit.
3. Assert `diag_a == 0` while armed and above threshold.
4. Drop AN0 below `0x0228` through another bounded monitor cadence.
5. Assert `diag_a` increments from MAIN execution.
6. Prove PB Diagnostics cache and LCD surfacing.

Risk:

- The AN0 trip schedules standby through MAIN firmware, so `S` can be an
  expected co-trigger after `standby_event_dispatch`.  If that makes the first
  end-to-end test unstable, land a MAIN-only red/green test first, then add the
  CONTROL/LCD test once the standby side effect is bounded.

Candidate test:

```text
test_v171_v32_diag_lcd_surfaces_an0_standby_trigger
```

### Phase 5: Close `P`

Use `Chain.set_main_pin(unit, "A", 1, level)` unless the test proves RA1 needs a
dedicated held-level helper.

Sequence:

1. Boot healthy and sample the baseline RA1 level.
2. Step until `ra1_edge_monitor` has observed that baseline, then snapshot
   `diag_p`.
3. Drive exactly one opposite-level RA1 change.
4. Step to the next `ra1_edge_monitor` pass.
5. Assert `diag_p` increments by exactly one.
6. Hold RA1 steady and assert no further increment.
7. Prove PB Diagnostics cache and LCD surfacing.

If `set_main_pin` is a no-op because RA1 is not a general input at the needed
time, add a simulator-visible failure assertion first, then implement the
minimum pin-helper change needed to model the board-level stimulus.  Do not
call this hardware-realistic RA1 coverage unless PIC18F2455 ADCON1/PCFG masking
is modeled or the matrix documents the narrower simulator-only PORTA-edge
precondition.  Under the current simulator model, the `P` row can close only as
`not applicable` for hardware-realistic release closure plus a simulator-only
PORTA-edge invariant; it cannot be labelled `event surfaced` without that model
upgrade.

Candidate test:

```text
test_v171_v32_diag_lcd_surfaces_ra1_edge_counter
```

### Phase 6: Reset-Flag Follow-Up

The matrix originally treated `O/V/W/X` as partial because reset-flag parsing
existed but live LCD surfacing remained tied to PB Diagnostics flow.  The
implemented simulator closure now keeps reset rows separate from runtime rows
and verifies PB1/PB2 surfacing through `cmd 0x22`.

- `test_v171_v32_diag_lcd_surfaces_reset_cause_flags` drives distinct
  POR/BOR/WDT/SW RCON latch states per MAIN, then proves `O/V/W/X` reach
  PB1/PB2 cache/LCD.  The `O` case adds a real post-reset `I` abnormal so the
  sparse LCD renderer emits `O1`; clean POR alone intentionally renders `OK`.
- Keep these tests separate from the seven runtime counters so they do not hide
  regressions in `BF/21..BF/27`.

## Documentation Updates

For each completed phase:

- Update `docs/V171_V32_DIAG_FAULT_INJECTION_MATRIX.md` with the exact new test
  names and status.
- If a product bug is discovered, add or update the relevant row in
  `docs/IMPL_V171_V32_BUG_LEDGER.md`.
- Keep `AGENTS.md` indexed if any new top-level doc is added or renamed.
- Do not mark a row "fault surfaced" unless the new test starts from a
  realistic fault/event source rather than a RAM poke.

## Acceptance Gates

Focused manifest and row gate:

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

Broader focused gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v32_layer5_diag_counters.py \
  tests/sim/test_v32_src4382_autodetect_polling.py
```

Full simulator gate:

```bash
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Mandatory native rebuild/gate after TAS3108, GPIO, PyO3, or facade changes:

```bash
cargo test -p dlcp-sim -p dlcp-sim-py
cargo build --release -p dlcp-sim-py
bash crates/dlcp-sim-py/build.sh
```

## Stop Condition

This plan is complete only when the matrix shows every displayed Diagnostics
field as either:

- `fault surfaced`: a real injected fault/event increments MAIN RAM and reaches
  CONTROL/LCD; or
- `event surfaced`: a real operator/system event increments MAIN RAM and
  reaches CONTROL/LCD; or
- `reset-cause surfaced`: a reset-cause stimulus reaches CONTROL/LCD through
  `cmd 0x22`; or
- `not applicable`: a documented reason explains why no realistic stimulus
  exists for that displayed field.

Any row described as source-hook-only, seeded-render-only, or PB1-only remains
open.  As of this implementation, all simulator rows have explicit closure
state in the matrix; `P` is intentionally not hardware-realistic closure.
