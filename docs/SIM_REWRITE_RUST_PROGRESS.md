# `dlcp-sim` Rust Rewrite — Progress Ledger

Last updated: 2026-04-25
Branch: `feature/sim-rewrite-rust`

This file is **machine-readable**.  Sub-tasks have a fixed shape:

```
- [STATUS] P{phase}.{sub} {title}
  - verify: {shell command that returns exit 0 iff this sub-task is done}
  - artifact: {file or directory the sub-task produces}
  - notes: {free text}
```

`STATUS` ∈ `{ pending, in_progress, done, blocked }`. Only one sub-task may be `in_progress` at a time. `scripts/sim_rewrite_next.py` reads this file to find the next pending task.

---

## Phase 0 — Ground-Truth Capture

- [pending] P0.0 Resolve BAUDCON open-question (spec §11b)
  - verify: `.venv_ep0/bin/python scripts/probe_baudcon_mapping.py`
  - artifact: `scripts/probe_baudcon_mapping.py` + an appended note in spec §11b documenting which of the three explanations holds (second mapping; gpsim USART quirk; or test coarseness).
  - notes: must run before Phase 4 dual-run, but blocks no earlier work — placed at P0.0 so it gets resolved early. The probe loads V3.2 MAIN under gpsim, breaks on writes to 0xF98 and 0xFB8, executes `uart_config`, and reports which (if any) trigger.

- [pending] P0.1 Add `--capture-ground-truth` pytest flag
  - verify: `.venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py --capture-ground-truth -q && test -d artifacts/ground_truth/test_v17_chain__test_v17_chain_reaches_volume`
  - artifact: `tests/sim/conftest.py` (extension), `scripts/capture_gpsim_ground_truth.py` (helper)
  - notes: hooks into existing chain-harness `step()` at the conftest level so tests don't need rewrites.

- [pending] P0.2 Capture stimulus stream (every external pin/IR/UART/ADC/I²C event with `(tick, core_id, pin, payload)`)
  - verify: `.venv_ep0/bin/python scripts/check_ground_truth_capture.py --kind stimulus`
  - artifact: `artifacts/ground_truth/<test>/stimulus.jsonl`
  - notes: keep format JSONL so ad-hoc inspection is easy. The check script asserts every captured test directory has a non-empty `stimulus.jsonl` and verifies the events replay through gpsim deterministically.

- [pending] P0.3 Capture RAM/SFR snapshots at 1 ms boundaries
  - verify: `.venv_ep0/bin/python scripts/check_ground_truth_capture.py --kind snapshots`
  - artifact: `artifacts/ground_truth/<test>/snapshots/`
  - notes: snapshots are binary RAM dumps + JSON-encoded SFR map. The check script asserts each test has at least floor(duration_ms) snapshot files in its directory.

- [pending] P0.4 Capture per-UART TX byte stream + LCD raster + EEPROM
  - verify: `.venv_ep0/bin/python scripts/check_ground_truth_capture.py --kind outputs`
  - artifact: `artifacts/ground_truth/<test>/{uart_tx_*.jsonl, lcd_final.txt, eeprom_final.bin}`
  - notes: piggyback on existing `_LogDecoder`. The check script asserts every test that calls `chain.lcd_lines()` produces an `lcd_final.txt`.

- [pending] P0.5 Verify replay of every captured fixture matches gpsim output
  - verify: `.venv_ep0/bin/python scripts/replay_ground_truth.py --all`
  - artifact: `scripts/replay_ground_truth.py`
  - notes: regression safety — ensures fixtures are reproducible. Script must exit 0 on success, non-zero on any divergence.

- [pending] P0.gate Run phase-0 gate
  - verify: `.venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 0`
  - artifact: stdout summary; coverage ≥ 95%.

---

## Phase 1 — Rust ISA Core

- [pending] P1.1 `crates/dlcp-sim/` workspace member skeleton + `Variant`, `Core`, `Memory` types
  - verify: `cd crates/dlcp-sim && cargo build --release`
  - artifact: `crates/dlcp-sim/Cargo.toml`, `src/lib.rs`, `src/core.rs`, `src/memory.rs`
  - notes: include `Cargo.toml` workspace at repo root.

- [pending] P1.2 PIC18 ISA decoder for all 75 instructions
  - verify: `cd crates/dlcp-sim && cargo test --release isa::decode::tests -- --include-ignored`
  - artifact: `crates/dlcp-sim/src/isa/decode.rs`
  - notes: opcode table from DS39632E §24 / DS41303 §25.

- [pending] P1.3 BSR + Access Bank addressing (`a` bit semantics)
  - verify: `cd crates/dlcp-sim && cargo test --release memory::access_bank::tests`
  - artifact: `crates/dlcp-sim/src/memory.rs::access_bank()`
  - notes: K20 access-bank boundary differs from 2455 (USB SFRs on 2455 push it to 0x60).

- [pending] P1.4 FSR INDF + POSTINC/POSTDEC/PREINC/PLUSW
  - verify: `cd crates/dlcp-sim && cargo test --release isa::fsr::tests`
  - artifact: covered in `isa/decode.rs` + dedicated test file.

- [pending] P1.5 Hardware stack (31-deep) with PUSH/POP, STKPTR, STVREN
  - verify: `cd crates/dlcp-sim && cargo test --release stack::tests`
  - artifact: `crates/dlcp-sim/src/stack.rs`
  - notes: stack-overflow + STVREN reset is a real V3.2 hardening test (`feat(v3.2): main_service_rx_frame_gap parser stall watchdog` etc.).

- [pending] P1.6 Reset sources (POR, MCLR, BOR, WDT, RESET, stack-over/underflow)
  - verify: `cd crates/dlcp-sim && cargo test --release reset::tests`
  - artifact: `crates/dlcp-sim/src/reset.rs`.

- [pending] P1.7 Configuration words: parse from hex, drive osc + WDT + IPEN
  - verify: `cd crates/dlcp-sim && cargo test --release config::tests`
  - artifact: `crates/dlcp-sim/src/config.rs`.

- [pending] P1.8 ISA parity test against ground truth
  - verify: `cd crates/dlcp-sim && cargo test --release --test isa_parity`
  - artifact: `crates/dlcp-sim/tests/isa_parity.rs`
  - notes: load V1.71 hex, run from POR, RAM/W/STATUS bit-exact match against `artifacts/ground_truth/test_v171_baseline_*/snapshots/`.

- [pending] P1.gate Run phase-1 gate
  - verify: `cargo test -p dlcp-sim --release --test isa_parity && .venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 1`
  - artifact: stdout summary; coverage report shows all 75 PIC18 opcodes executed at least once.

---

## Phase 2 — Peripherals

- [pending] P2.1 EUSART — TXSTA/RCSTA/SPBRG/SPBRGH/BAUDCON, bit-level shifter, baud generator, OERR/FERR latch, RCREG FIFO
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_eusart_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/eusart.rs`
  - notes: 2455 BAUDCON @ 0xF98 (DS39632E Table 5-1; gpsim places it at 0xFB8 via `P18F2x21` base class — datasheet wins); K20 BAUDCON @ 0xFB8 (DS41303). See spec §11b for dual-run reconciliation.

- [pending] P2.2 MSSP I²C — master mode, SCL stretching, ACK/NACK injection
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_mssp_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/mssp.rs`
  - notes: port behaviour of `vendor/gpsim-0.32.1-xtc/modules/i2c-regfile.cc`.

- [pending] P2.3 Timer3 + Timer0 (only timers actually used)
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_timers_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/timer.rs`.

- [pending] P2.4 ADC (AN0 only on MAIN, full Tacq + Tconv timing)
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_adc_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/adc.rs`
  - notes: AN0 boot threshold 0x0236 / hysteresis 0x0229/0x0228 — must reproduce `test_main_gpsim_an0_boot.py`.

- [pending] P2.5 EEPROM with 2–5 ms post-write completion (deliberate fidelity exceedance over gpsim)
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_eeprom_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/eeprom.rs`
  - notes: document fidelity exception in `docs/SIMULATION_FIDELITY.md` + update tests that asserted instantaneous-write.

- [pending] P2.6 Port pins (RA/RB/RC + LATA/B/C + TRISA/B/C) with pin-coupling primitive
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_gpio_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/gpio.rs` + `crates/dlcp-sim/src/pinnet.rs`.

- [pending] P2.7 IRQ controller — INTCON*, RCON, IPEN priority + GIE/GIEH/GIEL, PIE/PIR
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_irq_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/irq.rs`.

- [pending] P2.8 USB-SIE (2455 only) — HID dispatch path only
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_usbsie_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/usb.rs`
  - notes: scope = cmd 0x20, 0x21, 0x43, 0x44 + filename A/B routing. NOT enumeration.

- [pending] P2.9 Oscillator subsystem — OSCCON, OSCCON2, OSCTUNE, PLL ENABLE/READY
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_osc_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/osc.rs`
  - notes: drives `ticks_per_tcy` per Variant on the 48 MHz universal clock; CONTROL = 16 ticks/Tcy (12 MHz Fosc / 4 = 3 MIPS), MAIN = 12 ticks/Tcy (16 MHz Fosc / 4 = 4 MIPS).

- [pending] P2.gate Run phase-2 gate
  - verify: `cargo test -p dlcp-sim --release --test 'peripheral_*_parity' && .venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 2`
  - artifact: every peripheral has ≥ 1 ground-truth-backed parity test.

---

## Phase 3 — Multi-Core Wiring + Clock Domains + Boot Offsets

- [pending] P3.1 `Chain` struct + global event queue
  - verify: `cd crates/dlcp-sim && cargo test --release chain::scheduler::tests`
  - artifact: `crates/dlcp-sim/src/chain.rs` + `src/scheduler.rs`.

- [pending] P3.2 Pin-coupling API (`couple_uart`, `couple_pin`, `couple_i2c_slave`)
  - verify: `cd crates/dlcp-sim && cargo test --release chain::coupling::tests`
  - artifact: covered in `chain.rs` + `pinnet.rs`.

- [pending] P3.3 Clock-domain handling — per-Core `ticks_per_tcy` (CONTROL=16, MAIN=12), optional `tick_drift_ppm`
  - verify: `cd crates/dlcp-sim && cargo test --release chain::clock::tests`
  - artifact: `crates/dlcp-sim/src/clock.rs`.

- [pending] P3.4 Boot-offset model with three scenarios (CONTROL+MAIN0 same PSU; MAIN1 separate)
  - verify: `cd crates/dlcp-sim && cargo test --release chain::boot_offset::tests`
  - artifact: `crates/dlcp-sim/src/boot_offset.rs`
  - notes: `BootOffsetSpec::Fixed` + `BootOffsetSpec::RangedRandom { seed }` for reproducibility.

- [pending] P3.5 Multicore parity — reproduce `test_v171_v31_chain.py` end-to-end
  - verify: `cd crates/dlcp-sim && cargo test --release --test multicore_parity::test_v171_v31_chain_parity`
  - artifact: `crates/dlcp-sim/tests/multicore_parity.rs`
  - notes: TX byte streams + LCD raster bit-exact against ground truth.

- [pending] P3.6 Multicore parity — un-XFAIL the Task #22 echo-loop tests
  - verify: `cd crates/dlcp-sim && cargo test --release --test multicore_parity::test_v171_v32_diag_chain_polls_pb1_and_pb2_no_xfail`
  - artifact: same test file
  - notes: 5 currently-XFAIL tests in `tests/sim/test_v171_v32_layer5_diag_chain.py` should PASS under new sim.

- [pending] P3.7 Boot-offset parity — MAIN1 boots 1.5 s late, CONTROL `WAITING FOR DLCP` clears within reconnect-wake budget
  - verify: `cd crates/dlcp-sim && cargo test --release --test multicore_parity::test_main1_late_boot_recovery`
  - artifact: same test file.

- [pending] P3.gate Run phase-3 gate
  - verify: `cargo test -p dlcp-sim --release --test multicore_parity && .venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 3`

---

## Phase 4 — Python Bindings + Dual-Run Test Migration

- [pending] P4.1 `crates/dlcp-sim-py/` PyO3 wrapper crate
  - verify: `cd crates/dlcp-sim-py && cargo build --release && .venv_ep0/bin/python -c "import dlcp_sim_native; print(dlcp_sim_native.__version__)"`
  - artifact: `crates/dlcp-sim-py/Cargo.toml`, `src/lib.rs`.

- [pending] P4.2 Python facade `src/dlcp_fw/sim/dlcp_sim_native.py` matching `chain_gpsim.py` API surface
  - verify: `python -c "from dlcp_fw.sim.dlcp_sim_native import Chain; c = Chain.from_v171_v32(); c.step_ticks(48_000_000); print(c.lcd_lines())"`
  - artifact: `src/dlcp_fw/sim/dlcp_sim_native.py`.

- [pending] P4.3 `tests/sim/conftest.py` plugin: `DLCP_SIM_BACKEND={gpsim,dual,rust}` env var
  - verify: `DLCP_SIM_BACKEND=dual .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py -q`
  - artifact: `tests/sim/conftest.py` extension.
  - notes: under DLCP_SIM_BACKEND=dual the conftest plugin runs every test under both gpsim and dlcp-sim and asserts identical externally-visible behaviour (UART byte streams, LCD, EEPROM). Diverging tests fail; pass means both engines agreed.

- [pending] P4.4 Migrate `test_v17_*` tests (single-MAIN baseline)
  - verify: `DLCP_SIM_BACKEND=dual .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py tests/sim/test_v17_shifted_full_parity.py -n 16 -q`
  - artifact: progress ledger marks each test migrated.

- [pending] P4.5 Migrate `test_v171_*` tests
  - verify: `DLCP_SIM_BACKEND=dual .venv_ep0/bin/python -m pytest tests/sim -k v171 -n 16 -q`
  - artifact: ledger update.

- [pending] P4.6 Migrate `test_v31_*` and `test_v32_*` tests
  - verify: `DLCP_SIM_BACKEND=dual .venv_ep0/bin/python -m pytest tests/sim -k 'v31 or v32' -n 16 -q`
  - artifact: ledger update.

- [pending] P4.7 Migrate remaining sim tests (chain, wire, multi-MAIN, etc.)
  - verify: `DLCP_SIM_BACKEND=dual .venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
  - artifact: ledger update; full sim gate green under dual-run.

- [pending] P4.8 Switch default backend to Rust; gpsim now opt-in only
  - verify: `.venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
  - artifact: `tests/sim/conftest.py` default flip + `pytest.ini` update.
  - notes: with no env var, the default backend should be `rust` and the full sim gate must be green.

- [pending] P4.9 Delete `chain_gpsim.py`, `wire_chain_gpsim.py`, `_CliSession`, `gpsim.py`, `.stc` script generators
  - verify: `.venv_ep0/bin/python scripts/check_gpsim_excision.py`
  - artifact: large code excision commit + `scripts/check_gpsim_excision.py` (asserts the named files are absent and that no remaining import references them).
  - notes: created during this sub-task as part of the excision commit; script returns non-zero if any of the listed paths still exist.

- [pending] P4.gate Run phase-4 gate
  - verify: `.venv_ep0/bin/python scripts/check_phase4_gate.py`
  - artifact: timing comparison report committed to `docs/SIM_REWRITE_RUST_PROGRESS.md`; helper script asserts `DLCP_SIM_BACKEND=rust pytest tests/sim` is green AND wall-clock < 60 s.

---

## Phase 5 — Determinism + Snapshot/Replay + Soak

- [pending] P5.1 Snapshot/restore round-trip on `Chain` (serde)
  - verify: `cd crates/dlcp-sim && cargo test --release snapshot::tests`
  - artifact: `crates/dlcp-sim/src/snapshot.rs`.

- [pending] P5.2 Property test: `restore(snapshot(c)) == c` for fuzzed states
  - verify: `cd crates/dlcp-sim && cargo test --release --test snapshot_property`
  - artifact: `crates/dlcp-sim/tests/snapshot_property.rs`.

- [pending] P5.3 Replay tool: `dlcp-sim replay <case.json>`
  - verify: `.venv_ep0/bin/python scripts/check_replay_round_trip.py`
  - artifact: `crates/dlcp-sim-cli/src/main.rs` + `scripts/sim_replay.py` wrapper + `scripts/check_replay_round_trip.py` (asserts a synthetic divergence file replays to bit-exact reproduction).

- [pending] P5.4 Soak suite under `tests/sim/soak/` — 10⁴+ scenarios per soak test
  - verify: `.venv_ep0/bin/python -m pytest tests/sim/soak -n 16 -q`
  - artifact: `tests/sim/soak/test_*.py`.

- [pending] P5.gate Run phase-5 gate
  - verify: `cargo test -p dlcp-sim --release --test snapshot_property && .venv_ep0/bin/python -m pytest tests/sim/soak -n 16 -q`

- [pending] P5b.1 (stretch) `cargo fuzz` target on IR command stream + boot-offset RNG
  - verify: `cd crates/dlcp-sim && cargo fuzz run ir_stream -- -max_total_time=300`
  - artifact: `crates/dlcp-sim/fuzz/`.

---

## Final acceptance

- [pending] PF.1 All `tests/sim/` tests pass under `DLCP_SIM_BACKEND=rust`.
- [pending] PF.2 Wall-clock comparison: rust-only sim gate < 60 s; gpsim-only > 1500 s.
- [pending] PF.3 5 currently-XFAIL `test_v171_v32_layer5_diag_chain.py` tests un-XFAILed and passing.
- [pending] PF.4 `vendor/gpsim-0.32.1-xtc/` retained one release cycle as oracle reference.
- [pending] PF.5 `docs/SIMULATION.md` rewritten to reflect new architecture.
- [pending] PF.6 PR opened on `feature/sim-rewrite-rust` → main.

---

## How to update this file

- **Status changes go through `scripts/sim_rewrite_next.py`**, which writes the ledger atomically (`os.replace`) so a crash never leaves a partial file. Hand-editing the `[pending|in_progress|done|blocked]` markers is *not* a supported workflow.
- Hand-edits to titles, notes, verify commands, and artifact paths are fine — commit them on the same branch as the related work.
- `advance` flips a `pending` task to `in_progress` and runs its verify command.
- On verify pass: status → `done`.
- On verify fail: status stays `in_progress`, failure dumped to `artifacts/sim_rewrite_divergences/`.
- A verify entry of literally `manual` (case-insensitive, optionally backtick-wrapped) marks the sub-task as human-validated; `advance --force-pass` is required to flip it to `done`.
