# DLCP Simulation Guide

The DLCP simulation harness is a single-process cycle-accurate Rust engine
(`crates/dlcp-sim/`) that runs the V1.71 CONTROL (PIC18F25K20) and V3.2 MAIN
(PIC18F2455) firmware images in a universal-clock topology with native
multi-core ring routing for the current-loop bus.  It replaces the legacy
three-process gpsim harness; gpsim is retained one release cycle as a
regression oracle and is scheduled for retirement under
`docs/SIM_REWRITE_RUST_SPEC.md` PF.4.

The full architecture, phase plan, and silicon-fidelity corner-case
inventory live in:

- `docs/SIM_REWRITE_RUST_SPEC.md` — design + 6-phase plan + risk register.
- `docs/IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md` — silicon-fidelity gap
  closure tracking.
- `docs/SIM_REWRITE_RUST_PROGRESS.md` — machine-readable progress ledger
  (driven by `scripts/sim_rewrite_next.py`).

This document is the day-to-day operator's guide: how to build, how to run
tests, what the public Python and CLI surfaces look like, and where the
gpsim oracle still matters until PF.4.

## Quick Start

### Test gate (rust backend)

```bash
# Full sim suite (default backend = rust):
.venv_ep0/bin/python -m pytest tests/sim -n 16 -q

# Phase-5 exit gate (snapshot/replay/soak):
python3 scripts/check_phase5_gate.py

# Fast subset only (-m "not slow"):
DLCP_SIM_BACKEND=rust .venv_ep0/bin/python -m pytest tests/sim -n 16 -q -m "not slow"
```

### Backend selection

Tests pick the backend via the `DLCP_SIM_BACKEND` env var, decoded by
`tests/sim/conftest.py`:

| Value     | Behaviour                                                 |
|-----------|-----------------------------------------------------------|
| `rust`    | (default) Run the rust silicon-ring engine.  Tests under  |
|           | `tests/sim/` that LACK `@pytest.mark.dual_supported` are  |
|           | auto-skipped.                                             |
| `gpsim`   | Run the legacy gpsim oracle.  All tests run; no auto-skip.|
| `dual`    | Run both backends and assert byte-identical UART/LCD/RAM  |
|           | traces.  The migration safety net.                        |

The conftest uses `rust` when the variable is unset.

### Replay a snapshot/case (P5.3)

```bash
cargo build --release -p dlcp-sim-cli
# Generate a starter case JSON (initial_factory=empty, 4 stimuli):
./target/release/dlcp-sim emit-template empty > /tmp/case.json
# Replay it; the --final-snapshot binary is the post-stimulus
# bincode blob, the --trace text file is the action-level log.
./target/release/dlcp-sim replay /tmp/case.json \
    --final-snapshot /tmp/final.bin \
    --trace /tmp/trace.txt
```

The case JSON schema is documented in
`crates/dlcp-sim-cli/src/main.rs` under the module docstring.  The replay
tool exits 0 on success, 1 on usage error, 2 on stimulus failure, 3 on
`expect_final_snapshot_hex` mismatch.

### Use the Python facade

```python
from dlcp_fw.sim.dlcp_sim_native import Chain

chain = Chain.from_v171_v32()        # V1.71 CONTROL + 2 V3.2 MAINs
chain.run_until_connected(limit=200) # advance until DISPLAY mode
chain.press("RIGHT")                 # inject panel button event
for _ in range(8):
    chain.step()
print(chain.lcd_lines())             # ('Volume         ', '<level bar>')
```

## Architecture

### Universal-clock single-process engine

```text
                          Chain (rust)
                          single process
                       universal-clock tick
                       at 48 MHz / 20.833 ns
   +--------------+   /                            \
   | CONTROL core |--+                              +--+ MAIN0 core
   | PIC18F25K20  |   |  Event queue (per-tick      |  | PIC18F2455
   +--------------+   |  scheduler):                |  +-------------+
          ^           |   - CoreInstructionComplete |       |
          |           |   - UartByteDelivery        |       |
          |           |   - PinPropagation          |       |
          |           |   - PeripheralDeadline      |       v
          |           |                             |  +-------------+
          |   UART    +-----------------------------+  | MAIN1 core  |
          |   ring                                     | PIC18F2455  |
          +-----------------------------------------> +-------------+
                CONTROL <- MAIN1 <- MAIN0 <- CONTROL ring
```

Each `Chain` owns a flat `Vec<Core>` plus a `pinnet` describing the UART
couplings and other inter-core wires (LCD, MCLR, RC2 standby strap).
`Chain::step_ticks(N)` advances all cores in lockstep at the universal-clock
granularity and dispatches events from the priority queue as they fire.

The ring topology — `CONTROL → MAIN0 → MAIN1 → CONTROL` — matches the
DLCP current-loop bus exactly: bytes from CONTROL fan out to MAIN0; MAIN0
forwards to MAIN1; MAIN1 returns to CONTROL.  Three unidirectional UART
couplings, no per-process bridge.

### Public surfaces

The rust engine is exposed in three layers:

1. **Native rust crate** (`crates/dlcp-sim/`) — used by Rust unit /
   integration tests in `crates/dlcp-sim/tests/` and by the workspace's
   binary crates.
2. **PyO3 facade** (`crates/dlcp-sim-py/src/lib.rs`,
   `src/dlcp_fw/sim/dlcp_sim_native.py`) — the Python `Chain` class
   used by `tests/sim/`.  The PyO3 module compiles to
   `target/release/libdlcp_sim_native.dylib` (macOS) /
   `libdlcp_sim_native.so` (Linux); `bash crates/dlcp-sim-py/build.sh`
   symlinks it as `dlcp_sim_native.so` for `import` resolution.
3. **CLI** (`crates/dlcp-sim-cli/src/main.rs`) — the `dlcp-sim` binary
   with `replay`, `emit-template`, and `encode-hex` subcommands.

### Determinism + replay (Phase 5)

Every chain state is serializable via `bincode` from the rust crate:

```rust
use dlcp_sim::snapshot::{encode, decode};

let bytes = encode(&chain);
let restored: Chain = decode(&bytes)?;
assert_eq!(encode(&restored), bytes);   // byte-stable round-trip
```

These are rust-side functions today; the Python facade does not yet
expose `Chain.snapshot()` / `Chain.restore()` directly.  Python tests
that want snapshot/replay round-trip should drive the
`./target/release/dlcp-sim replay` CLI via `subprocess` -- the CLI
case JSON (a required `format: "dlcp-sim-replay-v1"` discriminator,
an `initial_factory` or `initial_snapshot_hex`, a stimulus list, and
an optional `expect_final_snapshot_hex`) is parsed by the CLI and
handed to `dlcp_sim::snapshot::encode/decode` internally; the JSON
envelope is NOT the same shape as the bincode bytes those functions
consume directly.  Alternatively, run
`cargo test --release -p dlcp-sim --test snapshot_property` for the
proptest property suite.

The 5-test soak harness at `crates/dlcp-sim/tests/snapshot_soak.rs` runs
10⁴ scenarios per test (50,000 total) asserting byte-stable round-trip,
two-chain replay determinism, and step-split idempotence
(`step_ticks(N) ≡ step_ticks(a) + step_ticks(N-a)`).

## Public Python `Chain` API

Highlights — see the docstrings in `src/dlcp_fw/sim/dlcp_sim_native.py`
for the full surface.

### Construction

| Method                      | Returns chain shape |
|-----------------------------|---------------------|
| `Chain.from_v171_v32()`     | V1.71 CONTROL + 2 V3.2 MAINs (3-core ring) |
| `Chain.from_v171_v31()`     | V1.71 CONTROL + 1 V3.1 MAIN |
| `Chain.from_v32_main_only()`| 1 V3.2 MAIN only (no CONTROL) |
| `Chain.from_v17_chain(...)` | V1.7 CONTROL + 1 MAIN, configurable hexes |
| `Chain.from_v17_control_only(...)` | V1.7 CONTROL alone |

### Stepping the simulator

| Method                         | Semantic |
|--------------------------------|----------|
| `step_ticks(n)`                | Advance N universal-clock ticks (1 K20-Tcy = 16 ticks) |
| `step_tcy(tcy)`                | Advance N CONTROL Tcy |
| `step()`                       | Advance one default 200 K-Tcy chunk |
| `step_many(n_chunks)`          | Advance N default chunks |
| `run_until_connected(limit)`   | Step until CONTROL marks itself connected, or `limit` chunks |
| `run_until_waiting(limit)`     | Step until CONTROL transitions to WAITING (Zzz) |
| `step_until_pc_hit(core_idx, pc_lo, pc_hi, max_tcy)` | gpsim `break e <addr>` analog |

### Stimulus injection

| Method                         | Semantic |
|--------------------------------|----------|
| `press(key)`                   | Inject panel button (`UP/DOWN/LEFT/RIGHT/SELECT/STBY/...`) |
| `set_blackout(enabled)`        | Toggle chain-wide UART blackout |
| `set_main_an0_sample(unit, value)` | Override MAIN's AN0 ADC sample |
| `set_link_fault(name, *, drop=None, extra_cycles=None)` | gpsim `set_link_fault` analog (P4-followup #101) |
| `inject_control_rx_bytes(bytes)` | V1.71-specific software RX ring push (writes RAM at 0x066-0x098) |

The rust `Chain` also exposes `inject_uart_rx_byte(core_idx, byte)` (a
generic hardware-level UART RX-FIFO inject; see
`crates/dlcp-sim/src/chain.rs`) used by the cargo-fuzz target at
`crates/dlcp-sim/fuzz/`.  No Python wrapper is exposed yet; if you need
silicon-level RX injection from a Python test, raise it as a
P4-followup ticket and add the PyO3 wrapper.

### Read-back / introspection

| Method                         | Semantic |
|--------------------------------|----------|
| `lcd_lines()`                  | `(line1, line2)` snapshot of HD44780 DDRAM |
| `is_connected()`               | CONTROL's "connected" flag |
| `is_waiting()`                 | CONTROL's WAITING-screen flag |
| `read_reg(addr)`               | CONTROL data RAM byte |
| `read_main_reg(unit, addr)`    | MAIN data RAM byte (0=MAIN0, 1=MAIN1) |
| `read_core_flash(core_idx, addr, length)` | Program flash slice |
| `current_ctl_pc()`             | CONTROL program counter |
| `current_main_pc()`            | MAIN0 program counter |
| `bridge_byte_stats()`          | Per-link byte-count snapshot (P4-followup #99) |
| `uart_tx_records_full()`       | Full `(tick, src, dst, byte)` TX history |
| `uart_rx_records_full()`       | Full `(tick, src, dst, byte)` RX-accepted history |

### Mutation (overlay primitives, P4-followup #103)

| Method                         | Semantic |
|--------------------------------|----------|
| `patch_core_flash(core_idx, addr, payload)` | Generic flash overlay |
| `set_core_pc(core_idx, pc)`    | gpsim `pc=0x...` analog |
| `apply_standby_bypass_overlay(chain, *, control_hex_path)` | Module-level helper; mirror of gpsim's `control_disable_standby_check_dynamic` manifest |

## File Map

### Simulation engine

| Path                                         | Role |
|----------------------------------------------|------|
| `crates/dlcp-sim/`                           | Rust silicon-ring engine (lib + integration tests) |
| `crates/dlcp-sim/src/chain.rs`               | `Chain` core, event queue, UART/pin coupling |
| `crates/dlcp-sim/src/core.rs`                | PIC18 core (PC, RAM, flash, peripherals) |
| `crates/dlcp-sim/src/exec.rs`                | PIC18 instruction decoder + executor |
| `crates/dlcp-sim/src/peripherals/`           | EUSART, GPIO, MSSP, IRQ, ADC, oscillator, EEPROM, USB SIE, timers, SRC4382, TAS3108 |
| `crates/dlcp-sim/src/snapshot.rs`            | bincode encode/decode (P5.1) |
| `crates/dlcp-sim/tests/snapshot_property.rs` | P5.2 property tests (proptest) |
| `crates/dlcp-sim/tests/snapshot_soak.rs`     | P5.4 soak tests (10⁴ scenarios per test) |
| `crates/dlcp-sim/fuzz/`                      | P5b.1 cargo-fuzz target (operator runs `cargo +nightly fuzz`) |
| `crates/dlcp-sim-py/`                        | PyO3 wrapper crate |
| `crates/dlcp-sim-cli/`                       | `dlcp-sim replay` CLI |

### Python harness

| Path                                         | Role |
|----------------------------------------------|------|
| `src/dlcp_fw/sim/dlcp_sim_native.py`         | Python facade for the rust engine; the modern entry point |
| `tests/sim/conftest.py`                      | Backend selector + auto-skip plugin for `DLCP_SIM_BACKEND={rust,dual,gpsim}` |
| `tests/sim/soak/`                            | Pytest wrapper that runs the rust soak suite |

### Operator runbooks

| Path                                       | Role |
|--------------------------------------------|------|
| `scripts/check_phase5_gate.py`             | P5 exit gate (property + soak) |
| `scripts/check_phase4_gate.py`             | P4 fast-vs-slow timing gate |
| `scripts/check_replay_round_trip.py`       | P5.3 verifier |
| `scripts/sim_rewrite_next.py`              | Progress-ledger automation |

### Legacy oracle (retained one release cycle, scheduled for PF.4 retirement)

| Path                                       | Role |
|--------------------------------------------|------|
| `vendor/gpsim-0.32.1-xtc/`                 | Vendored gpsim fork; built under `artifacts/tools/gpsim-xtc/` |
| `src/dlcp_fw/sim/{chain,wire_chain,control,main}_gpsim.py` | Python wrappers for the gpsim subprocess pipeline |
| `src/dlcp_fw/sim/main_gpsim_timer3.py`     | Timer3 shim for legacy harnesses |
| `src/dlcp_fw/sim/gpsim.py`                 | Low-level gpsim CLI session driver |
| `scripts/gpsim-xtc`                        | Wrapper that exports `GPSIM_MODULE_PATH` and invokes the local build |

These files are still imported by 70 test files in `tests/`
(per the 2026-05-04 inventory at `docs/SIM_REWRITE_RUST_PROGRESS.md`
P4.9 entry) -- some of which also have `@pytest.mark.dual_supported`
markers but conditionally branch into the gpsim path on
`DLCP_SIM_BACKEND=gpsim`, while others are pure gpsim-only (no
marker -- auto-skipped under rust).  The auto-skipped count under
rust is the authoritative measurement; the latest PF.1 verification
(see ledger `docs/SIM_REWRITE_RUST_PROGRESS.md` PF.1 notes) is the
single source of truth for "how many tests are still skipped" --
the relationship between the 70 import-sites count and the
skipped-test count is not a 1:1 mapping (a single import-site file
can contribute zero or many skipped tests).

All 70 import-site files are preserved as the regression oracle
through one release cycle per
`docs/SIM_REWRITE_RUST_SPEC.md` §11.  PF.4's coordinated excision
will:

1. Delete `vendor/gpsim-0.32.1-xtc/` and `artifacts/tools/gpsim-xtc/`.
2. Delete the 6 wrapper Python files above.
3. Delete the still-gpsim-only test files that import them.
4. Delete the 9 supporting `scripts/` entries (3 ground-truth scripts +
   6 other gpsim-driver scripts).
5. Author `scripts/check_gpsim_excision.py` to assert that no remaining
   import references the deleted modules.

The deletion is co-scheduled with PF.6 (the PR opening) so a single
release cycle bounds the gpsim retention.

## Migration Notes

If you came from the gpsim-era guide:

- The three-process `chain_gpsim` / `wire_chain_gpsim` pipeline is gone.
  A single `Chain.from_v171_v32()` call gives you the equivalent
  three-core silicon ring.
- gpsim STC scripts (`break e <addr>`, `pc=<addr>`, `run`) map to
  `chain.step_until_pc_hit(...)`, `chain.set_core_pc(...)`, and
  `chain.step_ticks(...)`.
- gpsim CLI register reads (`reg(0x...)`) map to `chain.read_reg(addr)`
  and `chain.read_main_reg(unit, addr)`.
- gpsim per-bridge faults (`set_link_fault("ctl_to_m0", drop=True)`)
  use the same name on rust, with the topology divergence documented
  under `Chain.bridge_byte_stats` (rust ring exposes `m1_to_ctl` not
  `m0_to_ctl`).
- gpsim overlay manifests (`control_disable_standby_check_dynamic`)
  layer on top of `Chain.patch_core_flash` via
  `apply_standby_bypass_overlay`.
- gpsim's `chunk_cycles` config is gone — the rust scheduler runs both
  cores in lockstep at instruction-level granularity.

## Known Limitations

- The rust executor does not model bit-level UART timing.  TX bytes
  deliver immediately when the source's TXSR completes shifting; idle-
  line transitions are not simulated.  Tests that asserted on bit-level
  edge counts via gpsim's `bridge_shift_stats` should switch to byte
  counts via `Chain.bridge_byte_stats`.
- `Chain.set_link_fault(extra_cycles=N)` raises
  `NotImplementedError` — the rust silicon ring has no bridge-delay
  model.  Tests that need propagation-delay semantics must stay
  `@pytest.mark.gpsim`-only.
- 299 tests across 33 files are still `@pytest.mark.gpsim`-only and
  auto-skip under `DLCP_SIM_BACKEND=rust`.  Migration is tracked under
  the "P4 followup tracker" in `docs/SIM_REWRITE_RUST_PROGRESS.md`.

## Related Documentation

- `docs/SIM_REWRITE_RUST_SPEC.md` — full design + phase plan + risk register.
- `docs/IMPL_SIM_REWRITE_RUST_FIDELITY_SPEC.md` — silicon-fidelity gap
  closure plan (PIC18 ISA edge cases, peripheral fidelity, multi-core
  scheduler invariants).
- `docs/SIM_REWRITE_RUST_PROGRESS.md` — machine-readable progress
  ledger.
- `docs/SIMULATION_FIDELITY.md` — running list of intentional fidelity
  exceedances vs gpsim (e.g. EEPROM write-completion timing).
- `docs/TEST_SIMULATOR.md` — pytest commands, marker map, harness fixtures.
- `AGENTS.md` (= `CLAUDE.md`) — repository-wide canonical paths,
  release ceremonies, and per-commit codex review.
