# Assembly unit-test harnesses for V3.2 MAIN

This directory hosts function-level unit tests that drive a specific V3.2
MAIN helper under gpsim by booting a **purpose-built test firmware** — a
patched copy of `src/dlcp_fw/asm/dlcp_main_v32.asm` whose 0x1000 user-reset
vector has been redirected from the normal cold-init path to a
hand-written `unit_test_entry` driver.

The rest of the V3.2 image (every production helper, including
`main_flash_service_46de`, `eeprom_read_byte`, `eeprom_write_blocking`,
etc.) is linked into the test firmware untouched, so the driver exercises
the real production code — not a stub.  At the same time, cold-init is
bypassed, so the driver sees deterministic CPU/RAM state and can pre-
load its own test vectors without fighting the boot sequence.

## How it works

1. Write a harness `.asm` that defines `unit_test_entry:` and ends with a
   halt loop (`bra $`).  See
   [`harness_main_core_service_265c.asm`](harness_main_core_service_265c.asm)
   for a worked example.  The harness typically:
   - Masks interrupts (`clrf INTCON, ACCESS`) so no ISR disturbs the
     deterministic run.
   - Seeds the inputs the function-under-test reads from (in RAM).
   - Calls the function under test via a normal `call` (all production
     labels are reachable because the entire V3.2 body is still there).
   - Captures observable state — EEPROM via `eeprom_read_byte`, RAM
     registers, or a CRC over an output region — into a well-known RAM
     buffer.
   - Writes a single-byte completion marker to a well-known RAM address.
   - Enters an infinite `bra $` so the Python runner's cycle-count break
     stops the simulator at a known idle state.
   - **Must** start with `        org 0xADDR` for some address in
     `0x1000..0x4BFF`.  The V3.2 source ends with `org 0xF00000`
     (EEPROM), so without a re-seat the harness would be emitted into
     EEPROM space.

2. The builder in [`_unit_test_build.py`](_unit_test_build.py):
   - Copies the V3.2 source and the RAM include into a scratch dir
     (`artifacts/reanalysis/asm_unit_tests/`).
   - Rewrites the 0x1000 reset trampoline to `goto unit_test_entry`.
   - Strips the trailing `END` directive (gpasm halts parsing there),
     appends the harness, writes a fresh `END`.
   - Runs `dlcp_fw.sim.v30_symbols.assemble_v30` on the result.

3. A Python test (e.g.,
   [`test_main_core_service_265c_parity.py`](test_main_core_service_265c_parity.py))
   invokes the builder, feeds the resulting hex to gpsim via a `.stc`
   script that `run`s for a generous cycle budget then dumps the
   reporting RAM region via `x 0xADDR` commands, and asserts the
   observed values against the spec.

## Why this pattern

- **Semantic equivalence testing** — when a production function gets
  refactored, the same harness should produce the same captured state.
  The harness is code-shape-agnostic; it only cares about I/O.
- **Fast** — gpsim runs for ~2 s sim time per test.  Total runtime
  including assembly ≈ 0.5 s.
- **Real helpers** — unlike a pure software mock, every I2C / EEPROM /
  Timer interaction goes through the production code paths.  Catches
  side-effect bugs the mock would miss.
- **Low coupling to production source** — a rename of the reset
  trampoline line would need an update in `_unit_test_build.py`, but
  nothing else breaks.

## When NOT to use this pattern

- For top-level end-to-end scenarios (wire-chain, USB HID, boot path),
  use the existing `tests/sim/*` harnesses that run the production
  firmware unmodified.
- For firmware changes that RELY on cold-init (USB bring-up, Timer0
  start-up, MSSP init), the unit-test harness deliberately skips that
  work and would give false green.  Use `tests/sim/` there.

## Adding a new unit-test harness

1. Create `harness_<fn>.asm` next to the others.
2. Create `test_<fn>_<aspect>.py` that calls
   `build_unit_test_firmware(harness_path, out_dir, name=...)` and runs
   gpsim.  Pick a `name` that uniquely identifies the built firmware so
   two tests can live side-by-side in the same output directory.
3. Use the pytest `gpsim` marker (and `slow` if the cycle budget is
   substantial) so CI selection works.
