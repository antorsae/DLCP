# DLCP Simulator Rewrite — Rust Cycle-Perfect Engine (`dlcp-sim`)

Last updated: 2026-04-25
Branch: `feature/sim-rewrite-rust`
Status: **Phase 0 — pending**

---

## 1. Goals and Non-Goals

### Goals

- **Cycle-perfect, deterministic** simulation of the DLCP system: 1× CONTROL (PIC18F25K20) + N× MAIN (PIC18F2455).
- **Single process, single global cycle counter** — eliminate the Python-level cross-process UART bridge that today causes the Task #22 echo-loop and silent causality skid in `wire_chain_gpsim.py`.
- **Native multi-clock-domain support** — CONTROL @ 12 MHz Fosc / 3 MHz Tcy and MAIN @ 16 MHz Fosc / 4 MHz Tcy advance on the same shared event queue, *without* post-hoc cycle scaling.
- **Boot-offset realism** — model the real-system property that CONTROL+MAIN0 share a PSU (boot within a few µs of each other) while MAIN1 is in a separate enclosure with its own PSU (arbitrary offset, including booting *after* CONTROL has been running for seconds).
- **≥ 50× faster than the current gpsim PTY harness** for wire-chain tests. Target: full sim gate runs in **< 1 minute** (today: 27 min).
- **In-process Python API** (PyO3) — no PTY, no log parsing, no `.stc` script files, no subprocess overhead.
- **Differential testing as the migration safety net** — every passing gpsim test must pass on `dlcp-sim` with identical externally-visible behavior (RAM traces, TX byte streams, LCD raster, EEPROM contents) before gpsim is retired for that test.

### Non-Goals

- Not a general-purpose PIC18 simulator. We model only what the DLCP firmware uses: K20 + 2455 + the specific peripheral subset listed in §6.
- Not preserving gpsim's CLI, `.stc` scripts, `.lst` parsing, or interactive PTY interface. *Per user direction: no legacy compatibility.*
- Not modeling the TAS3108 DSP audio path. Only the I²C-slave side (already covered by today's `i2c_regfile` module) is in scope.
- Not modeling USB enumeration end-to-end. Only the PIC18F2455 USB-SIE HID dispatch path that the firmware actually exercises (cmd 0x20/0x21/0x43/0x44 etc.).

---

## 2. Architecture Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│  Rust crate: crates/dlcp-sim/                                   │
│                                                                 │
│  ┌───────────────┐  ┌───────────────┐  ┌───────────────┐        │
│  │ Core: K20     │  │ Core: 2455    │  │ Core: 2455    │        │
│  │ (CONTROL)     │  │ (MAIN0)       │  │ (MAIN1)       │        │
│  │ Tcy=333 ns    │  │ Tcy=250 ns    │  │ Tcy=250 ns    │        │
│  │ ┌───────────┐ │  │ ┌───────────┐ │  │ ┌───────────┐ │        │
│  │ │ ISA, RAM, │ │  │ │ ISA, RAM, │ │  │ │ ISA, RAM, │ │        │
│  │ │ Flash,    │ │  │ │ Flash,    │ │  │ │ Flash,    │ │        │
│  │ │ EEPROM    │ │  │ │ EEPROM    │ │  │ │ EEPROM    │ │        │
│  │ └─────┬─────┘ │  │ └─────┬─────┘ │  │ └─────┬─────┘ │        │
│  │   Peripherals │  │   Peripherals │  │   Peripherals │        │
│  │   (EUSART,    │  │   (EUSART,    │  │   (EUSART,    │        │
│  │   MSSP, T3,   │  │   MSSP, T3,   │  │   MSSP, T3,   │        │
│  │   ADC, EE,    │  │   ADC, EE,    │  │   ADC, EE,    │        │
│  │   IRQ, GPIO)  │  │   IRQ, GPIO,  │  │   IRQ, GPIO,  │        │
│  │               │  │   USB-SIE)    │  │   USB-SIE)    │        │
│  └───────┬───────┘  └───────┬───────┘  └───────┬───────┘        │
│          │ pin nodes        │ pin nodes        │ pin nodes      │
│          └──────────────────┴──────────────────┘                │
│                       Pin Network                               │
│      (UART current loop, I²C slaves, LCD strobes, etc.)         │
│                              │                                  │
│  ┌───────────────────────────▼──────────────────────────────┐   │
│  │       Global Event Queue (single ns-resolved clock)      │   │
│  │      All cores tick on this; causality is intrinsic      │   │
│  └──────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
                              │
              PyO3 bindings (Python extension module)
                              │
┌─────────────────────────────▼───────────────────────────────────┐
│ Python: dlcp_fw.sim.dlcp_sim_native                             │
│   - Chain(cores=[...], boot_offsets={"main1": 1_500_000_000ns}) │
│   - chain.step_ns(N) / chain.step_until(addr=0x...)             │
│   - core.ram[addr], core.regs.W, core.regs.STATUS_C, ...        │
│   - chain.snapshot(), chain.restore(snap)                       │
│   - chain.replay(stimulus_log)                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Key invariants

- **Time** is `u64` nanoseconds (range: 584 years; sufficient).
- Each core has `cycles_per_ns` derived from its config-bit oscillator selection. The scheduler advances *time*, not *cycles*; each core derives "did I tick?" from its own `cycles_per_ns` × elapsed `ns`.
- The global event queue is a min-heap of `(deadline_ns, core_id, callback)`. Peripheral timers, baud bit-edges, interrupt firings — all post events into this single queue.
- Pin nodes are first-class: `RC6` on MAIN0 wired to `RC7` on MAIN1 means a write event on the source pin schedules a read-side update at the same `ns` (subject to per-edge propagation delay if modeled).
- **No cross-core post-hoc rescaling.** The "skid" / "causality enforcement" / `max_shift_cycles` machinery in `wire_chain_gpsim.py` is deleted on day one — it cannot exist in this architecture.

---

## 3. Why Rust + Standalone (Not Fork-and-Improve gpsim)

| Constraint                          | Fork-and-improve gpsim          | Standalone Rust                  |
|-------------------------------------|---------------------------------|----------------------------------|
| Single-process multi-MCU            | Possible via gpsim MultiNode but never used; needs harness rewrite anyway | Native, day one. |
| Eliminate PTY                       | libgpsim binding (Cython) needed; gpsim's API is C++ glibc-era, churn-prone | PyO3 + Rust idioms, clean. |
| Determinism + replay                | gpsim has hidden global state, no snapshot API | `serde` derives on every state struct from start. |
| Native bit-level UART, no quantization | gpsim's `FileRecorder` is poll-based; would need module work | First-class peripheral, designed for it. |
| Speed                               | gpsim ~5–10× slower than necessary due to event-callback layering | Aggressive inlining, no virtual dispatch in hot path. |
| No-legacy mandate (per user)        | We'd preserve cruft we don't want | Clean break, no legacy. |
| LLM implementation pace             | C++ + autotools + 20-yr codebase | Rust + Cargo + clean spec. |
| Differential testing safety net     | Can't run two gpsims against each other | gpsim is ground truth; Rust matches. |

**Decision:** standalone Rust simulator, `crates/dlcp-sim/`. gpsim stays in-tree as the ground-truth oracle through Phase 4; gets dropped from the test path once dual-run is green.

---

## 4. Phase 0 — Ground-Truth Capture

**Goal:** Freeze every passing gpsim test as a regression fixture so the new simulator can be developed against a fixed target.

### Deliverables

- `scripts/capture_gpsim_ground_truth.py` — pytest entry that, for every `tests/sim/` test currently passing on gpsim, records:
  - **Stimulus stream**: every external pin/IR/button/UART/ADC/I²C event with `(ns, core_id, pin/peripheral, payload)` tuples.
  - **RAM/SFR snapshots** at fixed cycle boundaries (every 1 ms simulated time + at every breakpoint hit).
  - **TX byte stream per UART** (per-core, with `ns` timestamp).
  - **LCD raster** (final + at every redraw).
  - **EEPROM image** (final + before/after every write).
  - **Cycle counters** per core at exit.

- `artifacts/ground_truth/<test_id>/` directory format:
  ```
  artifacts/ground_truth/test_v171_baseline_*/  
    stimulus.jsonl       # one event per line
    snapshots/
      0000000000.ram.bin # RAM at cycle 0
      0000000000.sfr.json
      0001000000.ram.bin # RAM at +1 ms
      ...
    uart_tx_main0.jsonl  # (ns, byte) tuples
    uart_tx_main1.jsonl
    uart_tx_control.jsonl
    lcd_final.txt
    eeprom_final.bin
    summary.json         # cycle counts, pass/fail, etc.
  ```

- `tests/sim/conftest.py` plugin that, when `--capture-ground-truth` is passed, intercepts the gpsim harness `step()` calls and records all of the above transparently.

### Exit gate (Phase 0 done when):

```bash
.venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 0
```

…reports:
- ≥ 95% of currently-passing `tests/sim/` tests have a non-empty `artifacts/ground_truth/<test_id>/` directory.
- Every captured fixture is replayable: `scripts/replay_ground_truth.py <test_id>` re-runs the stimulus through gpsim and asserts identical outputs.

### Estimated effort: 1 day (LLM-paced)

---

## 5. Phase 1 — Rust ISA Core

**Goal:** Cycle-accurate PIC18 instruction interpreter that runs a single MCU from reset and produces traces matching gpsim ground truth.

### Deliverables

- `crates/dlcp-sim/Cargo.toml` workspace member.
- `crates/dlcp-sim/src/isa/mod.rs` — instruction decoder + executor.
- `crates/dlcp-sim/src/core.rs` — `Core` struct holding flash, RAM, SFRs, cycle counter.
- `crates/dlcp-sim/src/memory.rs` — banked RAM + Access Bank + SFR routing per chip variant (`Variant::Pic18F25K20` vs. `Variant::Pic18F2455`).

### Coverage requirements

- All 75 PIC18 instructions per DS39632E §24 / DS41303 §25:
  - Byte-oriented: ADDWF, ADDWFC, ANDWF, CLRF, COMF, CPFSEQ, CPFSGT, CPFSLT, DECF, DECFSZ, DCFSNZ, INCF, INCFSZ, INFSNZ, IORWF, MOVF, MOVFF, MOVWF, MULWF, NEGF, RLCF, RLNCF, RRCF, RRNCF, SETF, SUBFWB, SUBWF, SUBWFB, SWAPF, TSTFSZ, XORWF
  - Bit-oriented: BCF, BSF, BTFSC, BTFSS, BTG
  - Literal: ADDLW, ANDLW, IORLW, LFSR, MOVLB, MOVLW, MULLW, RETLW, SUBLW, XORLW
  - Control: BC, BN, BNC, BNN, BNOV, BNZ, BOV, BRA, BZ, CALL, CLRWDT, DAW, GOTO, NOP, POP, PUSH, RCALL, RESET, RETFIE, RETURN, SLEEP
  - Table: TBLRD\* (with all four variants: TBLRD\*, TBLRD\*+, TBLRD\*-, TBLRD+\*), TBLWT\* (same four)
- BSR + Access Bank addressing (`a` bit semantics: `a=0` → Access Bank, `a=1` → BSR-selected bank).
- FSRn INDF / POSTINC / POSTDEC / PREINC / PLUSW addressing modes.
- Hardware stack (31-deep) with PUSH/POP and STKPTR semantics including STVREN config bit.
- Reset sources: POR, MCLR, BOR, WDT, RESET instruction, stack overflow/underflow.
- Configuration words: parse from hex, drive oscillator config + WDT + STVREN + IPEN.

### Verification gate

`crates/dlcp-sim/tests/isa_parity.rs`:

```rust
#[test]
fn isa_matches_gpsim_ground_truth_for_v171_reset_through_init() {
    // Loads V1.71 hex, runs from POR for 100,000 cycles,
    // diff-checks RAM + W + STATUS + STKPTR against
    // artifacts/ground_truth/test_v171_baseline_*/snapshots/*
    // Tolerance: bit-exact.
}

#[test]
fn isa_matches_gpsim_ground_truth_for_v32_reset_through_an0_gate_pass() { ... }

#[test]
fn isa_covers_all_75_pic18_opcodes() { /* fuzzer-style coverage gate */ }
```

### Exit gate

```bash
cargo test -p dlcp-sim --test isa_parity --release
```

…all green; coverage report shows every PIC18 instruction executed at least once across the test corpus.

### Estimated effort: 2 days

---

## 6. Phase 2 — Peripherals

**Goal:** Implement the peripheral subset required by V1.71 + V3.2 firmware, with bit-level timing fidelity.

### Peripheral inventory (per `firmware/disasm/main/gpdasm_output.annotated.asm` + `firmware/disasm/control/v1.6b_disasm.annotated.asm` + V1.71/V3.2 source)

| Peripheral | K20 | 2455 | Notes                                                  |
|------------|-----|------|--------------------------------------------------------|
| EUSART     | ✓   | ✓    | Bit-level TX/RX shifter; baud generator; OERR/FERR latch; RCREG FIFO; TXSTA/RCSTA/SPBRG/SPBRGH/BAUDCON. K20 BAUDCON @ 0xFB8; 2455 BAUDCON @ **0xF98** (NOT gpsim's buggy 0xFAA — see §11 risk). |
| MSSP I²C   | —   | ✓    | Master mode for TAS3108 writes; SCL stretching; ACK/NACK bus injection (port `i2c-regfile.cc` semantics). SSPADD=0x77 → 33.3 kHz on 16 MHz Fosc. |
| Timer3     | ✓   | ✓    | 16-bit timer; T3CON; gate; capture/compare integration with CCP. |
| Timer0     | ✓   | ✓    | 8/16-bit; prescaler; interrupt source for CONTROL idle timer. |
| ADC        | —   | ✓    | AN0 only on MAIN; ADCON0/1/2; full Tacq + Tconv timing; threshold reads tested against 0x0236 / 0x0229 / 0x0228 hysteresis. |
| EEPROM     | ✓   | ✓    | 256 B; **realistic 2–5 ms post-write completion** (gpsim does this in nanoseconds — known fidelity gap). |
| Port pins  | ✓   | ✓    | RA/RB/RC + LATA/B/C + TRISA/B/C; pin-coupling primitive for UART current loop, button matrix, LCD strobes. |
| IRQ ctrl   | ✓   | ✓    | INTCON, INTCON2, INTCON3, IPEN priority + GIE/GIEH/GIEL, PIE1/PIR1, PIE2/PIR2 (+ PIE3/PIR3 on K20). |
| USB-SIE    | —   | ✓    | HID endpoint dispatch only: cmd 0x20 (preset switch), 0x21 (diag query), 0x43 (memread), 0x44 (Tier-1 diag snapshot), filename A/B routing. NOT full enumeration. |
| Oscillator | ✓   | ✓    | OSCCON, OSCCON2, OSCTUNE, PLL ENABLE/READY. K20: HSPLL @ 12 MHz crystal → 12 MHz Fosc / 3 MHz Tcy. 2455: ECPIO / HSPLL → 16 MHz Fosc / 4 MHz Tcy. |
| WDT        | ✓   | ✓    | If firmware enables it. Currently disabled by config in both V1.71 + V3.2 — verify and stub if so. |

### Per-peripheral verification gate

Each peripheral has its own `crates/dlcp-sim/tests/peripheral_<name>_parity.rs` that diffs against ground truth.  Examples:

- **EUSART**: ground-truth fixture is `test_v17_chain.py` UART byte stream; new sim must produce same bytes at same `ns` ± 8 cycles (bit-edge quantization tolerance).
- **MSSP**: ground-truth is `test_main_gpsim_i2c_regfile.py` STOP/START + ACK/NACK sequences; bit-exact.
- **ADC**: `test_main_gpsim_an0_boot.py` — same threshold-pass cycle count.
- **EEPROM**: `test_v171_baseline.py` EEPROM-after-write image bit-exact; `ns` stamp of write-complete IRQ matches **datasheet** (not gpsim — this is one of the few places we *deliberately* exceed gpsim fidelity).

### Exit gate

```bash
cargo test -p dlcp-sim --test 'peripheral_*_parity' --release
```

…all green.

### Estimated effort: 2–3 days

---

## 7. Phase 3 — Multi-Core Wiring + Clock Domains + Boot Offsets

**Goal:** Wire N cores onto a single global event queue with correct clock-domain scaling and realistic boot offsets.

### Deliverables

- `crates/dlcp-sim/src/chain.rs` — `Chain` struct holding `Vec<Core>` + global event queue + pin network.
- Pin-coupling API:
  ```rust
  let mut chain = Chain::new();
  let control = chain.add_core(Variant::Pic18F25K20, hex_path_v171, ClockSpec::from_config_bits());
  let main0   = chain.add_core(Variant::Pic18F2455,  hex_path_v32,  ClockSpec::from_config_bits());
  let main1   = chain.add_core(Variant::Pic18F2455,  hex_path_v32,  ClockSpec::from_config_bits());
  
  // Current-loop UART chain: CONTROL → MAIN0 → MAIN1 → MAIN0 → CONTROL (ring)
  chain.couple_uart(control.tx_pin(), main0.rx_pin(), 31_250);
  chain.couple_uart(main0.tx_pin(),   main1.rx_pin(), 31_250);
  // ... bidirectional reply path
  ```

- **Clock domain handling**:
  - Each `Core` has `Tcy_ns: u32` derived from its `ClockSpec`. CONTROL = 333 ns; MAIN = 250 ns (round-down; precise FP not needed since baud rates are integer multiples).
  - Single global `now_ns: u64`. To advance one instruction on a core, the scheduler dequeues the next event (any peripheral or instruction-complete deadline) and calls back into the appropriate core.
  - Crystal skew (optional): per-core `Tcy_drift_ppm: i32` field (default 0). When non-zero, each instruction's deadline is `Tcy_ns × (1 + drift_ppm × 1e-6)`; default seeded PRNG produces reproducible drift sequences.

- **Boot-offset model** — three configurable scenarios per `Chain`:
  ```rust
  pub struct BootOffsetConfig {
      // CONTROL boots first; MAIN0 follows within ±50 µs (same PSU).
      // Default: PRNG ±50 µs, seed=42.
      pub control_to_main0_offset_ns: BootOffsetSpec,
      
      // MAIN1 is in a separate enclosure with its own PSU.
      // Default: configurable; tests pick from {-2_000_000_000, 0, +500_000_000, +2_000_000_000} ns.
      pub main1_offset_ns: BootOffsetSpec,
  }
  
  pub enum BootOffsetSpec {
      Fixed(i64),
      RangedRandom { min_ns: i64, max_ns: i64, seed: u64 },
  }
  ```
  Cores with negative offsets boot *before* `now_ns=0`; their first `Tcy_ns` events fire at `now_ns = -offset` from their POR. Cores with positive offsets stay in pre-POR (RAM = config-determined, no instruction execution) until their offset elapses.

### Verification gate

`crates/dlcp-sim/tests/multicore_parity.rs`:

- Reproduce `test_v171_v31_chain.py` end-to-end (CONTROL + MAIN0); diff TX byte streams + LCD raster + final EEPROM bit-exact against ground truth.
- Reproduce `test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_diag_page_polls_pb1_and_pb2` (the Task #22 XFAIL); under the new architecture this must **PASS**, not XFAIL — and the result is the canonical proof that the echo-loop was a sim artifact, not a firmware bug.
- Boot-offset tests: with `main1_offset = +1_500_000_000 ns` (MAIN1 boots 1.5 s after CONTROL), CONTROL's `WAITING FOR DLCP` LCD must clear within the V1.71 reconnect-wake budget after MAIN1 comes online. Diff against `test_chain_gpsim_v25_v162b_recovery.py` family.

### Exit gate

```bash
cargo test -p dlcp-sim --test multicore_parity --release
.venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 3
```

…all green; the 5 currently-XFAIL Diag-chain tests are flagged as candidates for un-XFAIL.

### Estimated effort: 1 day

---

## 8. Phase 4 — Python Bindings + Dual-Run Test Migration

**Goal:** Expose `dlcp-sim` to pytest via PyO3; run every existing gpsim test against both engines; declare migration complete when all match.

### Deliverables

- `crates/dlcp-sim-py/Cargo.toml` — PyO3 wrapper crate.
- `crates/dlcp-sim-py/src/lib.rs` — Python module:
  - `Chain`, `Core`, `Variant`, `ClockSpec`, `BootOffsetConfig`
  - `core.ram`, `core.flash`, `core.regs`, `core.eeprom`, `core.lcd`
  - `chain.step_ns(N)`, `chain.step_until_addr(core_id, addr)`, `chain.run_until_breakpoint(core_id, addr)`
  - `chain.snapshot() -> bytes`, `chain.restore(bytes)`
  - `chain.replay(stimulus_log_path)`
- `src/dlcp_fw/sim/dlcp_sim_native.py` — thin Python wrapper presenting the same API surface as `chain_gpsim.py` / `wire_chain_gpsim.py` so tests can swap engines transparently.
- `tests/sim/conftest.py` plugin: when `DLCP_SIM_BACKEND=dual` env var is set, every test is run twice (once on gpsim, once on `dlcp-sim`) and divergent outputs trip an `assert`.
- `tests/sim/conftest.py` plugin: when `DLCP_SIM_BACKEND=rust` env var is set, only `dlcp-sim` runs.

### Migration protocol

- **Per-test migration**:
  1. Run `DLCP_SIM_BACKEND=dual pytest tests/sim/test_<name>.py`.
  2. If it passes, mark the test as migrated in `docs/SIM_REWRITE_RUST_PROGRESS.md`.
  3. If it fails, the divergence is captured in `artifacts/sim_rewrite_divergences/<test_id>.json`; an agent investigates, fixes the Rust side, re-runs.
  4. gpsim is treated as the source of truth except for the deliberate fidelity exceptions enumerated in §11 (e.g. EEPROM write-completion latency, BAUDCON address).

- **Drop gpsim**:
  - Once all `tests/sim/` tests pass under `DLCP_SIM_BACKEND=rust`, set `dlcp-sim` as default.
  - Remove `chain_gpsim.py`, `wire_chain_gpsim.py`, `_CliSession`, `gpsim.py` subprocess machinery, `.stc` script generation. Large deletion.
  - Keep `vendor/gpsim-0.32.1-xtc/` for one release cycle as a regression reference, then remove.

### Exit gate

```bash
DLCP_SIM_BACKEND=dual .venv_ep0/bin/python -m pytest tests/sim -n 16 -q  # all pass
DLCP_SIM_BACKEND=rust .venv_ep0/bin/python -m pytest tests/sim -n 16 -q  # all pass
.venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 4
```

Wall-clock target: rust-only run completes in < 1 minute (vs. 27 min on gpsim).

### Estimated effort: 1–2 days

---

## 9. Phase 5 — Determinism + Snapshot/Replay + Soak

**Goal:** Capabilities that gpsim never had: bit-exact reproducibility, snapshot/restore, and 10⁴-step soak / fuzzing infrastructure.

### Deliverables

- **Snapshot/restore**: `chain.snapshot() -> bytes` serializes all core state (RAM, SFRs, flash, EEPROM, peripheral registers, event queue, RNG state). `chain.restore(bytes)` round-trips. Verified with property test: `restore(snapshot(c1)) == c1` for all reachable states.
- **Replay**: a failing test serializes its initial state + stimulus stream; debugger replays bit-for-bit. Format: `dlcp-sim replay <case.json>` writes a `.lst`-equivalent trace.
- **Crystal skew + bit error injection**: per-test seeded PRNG; deterministic output despite stochastic inputs.
- **Soak harness**: `tests/sim/soak/` directory; each soak test runs 10⁴+ scenarios in CI-budgeted parallelism. Failures automatically dump the seed + replay artifact for triage.
- **Fuzz hooks** (optional, exploratory): `cargo fuzz` target that fuzzes the IR command stream + boot-offset RNG against firmware state-machine invariants. Out of scope for the MVP gate; tracked as P5b stretch goal.

### Exit gate

```bash
cargo test -p dlcp-sim --test snapshot_property --release
.venv_ep0/bin/python -m pytest tests/sim/soak -n 16 -q
.venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 5
```

### Estimated effort: 1 day (soak), +2 days (fuzz, optional)

---

## 10. Per-Phase Exit Gates (Machine-Checkable)

Every phase has a single command that returns exit code 0 iff the gate is met.  These are the contracts the automation in `scripts/sim_rewrite_next.py` checks.

| Phase | Gate command                                                                                  |
|-------|-----------------------------------------------------------------------------------------------|
| 0     | `python scripts/sim_rewrite_next.py verify-phase 0` — coverage of ground-truth fixtures ≥ 95%. |
| 1     | `cargo test -p dlcp-sim --test isa_parity --release`                                          |
| 2     | `cargo test -p dlcp-sim --test 'peripheral_*_parity' --release`                               |
| 3     | `cargo test -p dlcp-sim --test multicore_parity --release` + Task #22 unxfail check.          |
| 4     | `DLCP_SIM_BACKEND=dual pytest tests/sim -n 16 -q` (full sim gate green)                       |
| 5     | `cargo test -p dlcp-sim --test snapshot_property` + soak suite green                          |

The progress ledger (`docs/SIM_REWRITE_RUST_PROGRESS.md`) tracks sub-task status; phase-level gates are the authoritative completion signal.

---

## 11. Risk Register and Deliberate Fidelity Choices

| Risk / decision                                              | Mitigation / rationale                                       |
|--------------------------------------------------------------|--------------------------------------------------------------|
| Subtle PIC18 ISA edge cases not covered by spec text         | Differential test against gpsim (oracle) for entire ISA exercised by V1.71 + V3.2 firmware. Any divergence: gpsim wins, Rust fixes. |
| 2455 BAUDCON address divergence (gpsim @ 0xFAA, datasheet @ 0xF98) | Rust port follows datasheet. If any firmware byte writes to BAUDCON, gpsim's behavior is wrong; we'll see this as a dual-run divergence and Rust will be correct. *Verify firmware writes to BAUDCON; if it does and the wrong-address gpsim behavior is what current tests rely on, surface the issue and gate in §11b.* |
| K20 vs. 2455 SFR drift                                       | Encoded as static data tables per `Variant`; no code branching in hot path. |
| Peripheral fidelity escapes harming firmware regressions    | Phase 4 dual-run is mandatory before gpsim retires per-test. Hardware-only tests (`tests/hardware/`) remain the final tiebreaker per `docs/SIMULATION_FIDELITY.md`. |
| Multi-core scheduler bugs (race, deadlock)                   | Phase 3 has a reproducer for the Task #22 echo-loop; that's a stress test in itself. Plus property tests on event-queue invariants. |
| Boot-offset model under-fits real hardware                   | Stretch goal P3b: model BOR / brown-out sequence + real PSU rise time per `tests/hardware/test_live_state_transitions.py` data. |
| Crystal skew test instability                                | All skew injections are seeded-PRNG; CI uses fixed seed; soak uses sweep across seed corpus. |
| EEPROM write-completion timing change ≠ gpsim                | This is an *intentional* exceedance of gpsim fidelity. Document in `docs/SIMULATION_FIDELITY.md` and update test assertions that depend on the gpsim "instantaneous EEPROM" assumption. |

### §11b — BAUDCON gpsim divergence: investigation gate

Before Phase 4 dual-run begins, run the audit:

```bash
.venv_ep0/bin/python scripts/audit_baudcon_writes.py
```

…which scans V1.71 + V3.2 source + assembled hex for any write to address 0xF98 or 0xFAA. If firmware does write BAUDCON:

- If only writes to **0xF98** (datasheet): Rust is correct; gpsim is wrong. Likely we'll see test failures during dual-run that flag tests that were silently asserting the wrong gpsim behavior; treat each as a gpsim oracle exception and update the test's expected output.
- If writes to **0xFAA**: very unlikely (would require buggy firmware) — but if so, that's a real-hardware bug to file separately.

---

## 12. Out-of-Scope (For This Effort)

- Replacing gpsim's role as a debugging tool (some humans use the gpsim interactive prompt directly) — the **scripts** that wrap gpsim are gone; the gpsim binary stays in `vendor/` until the team decides otherwise.
- Modeling the TAS3108 audio path (filters, coefficient effects on signal). Out of scope — we keep the I²C-slave fault-injection stub.
- Modeling actual USB host enumeration. We model only what `dlcp_fw.flash.dlcp_main_flash` and `dlcp_fw.flash.dlcp_diag` (cmd 0x44 Tier-1 diag) exercise.
- Real-time audio capture/loopback (today done by `dlcp_fw.flash.read_coeffs` + `tests/hardware/`) — these are physical-only tests and stay outside the simulator.

---

## 13. Glossary

| Term              | Meaning                                                            |
|-------------------|--------------------------------------------------------------------|
| Tcy               | Instruction cycle time = Fosc / 4 (250 ns on MAIN, 333 ns on CONTROL). |
| Fosc              | Oscillator frequency (16 MHz on MAIN, 12 MHz on CONTROL).          |
| BSR               | Bank Select Register (PIC18 banked addressing).                    |
| Access Bank       | First 96 bytes of each bank, accessed without BSR (`a=0` operand). |
| EUSART            | Enhanced USART = the 31.25 kbaud current-loop transceiver.         |
| MSSP              | Master Synchronous Serial Port = I²C / SPI controller.             |
| Current loop      | 31.25 kbaud opto-isolated 3-wire serial protocol used CONTROL ↔ MAIN. |
| Pin node          | Bidirectional wire between MCU port pins; modeled as event-driven net. |
| Boot offset       | Wall-time delta between when each MCU's POR completes.             |
| Ground truth      | Captured gpsim output blessed as "what the new sim must reproduce". |
| Dual-run          | Test executed under both gpsim and Rust sim with bit-exact diff.   |
| XFAIL             | pytest expected-failure marker for known-broken tests.             |
| Task #22          | Pre-existing tracking task for the `chain_gpsim.py` two-MAIN echo-loop. Phase 3 invalidates the bug; XFAILs become PASSes. |

---

## 14. Cross-References

- gpsim K20 port: `vendor/gpsim-0.32.1-xtc/src/p18fk.cc`, `p18fk.h:122` (class `P18F25K20`)
- gpsim 2455 port: `vendor/gpsim-0.32.1-xtc/src/p18x.cc`
- Existing chain harness: `src/dlcp_fw/sim/chain_gpsim.py`, `wire_chain_gpsim.py`
- Existing fidelity doc: `docs/SIMULATION_FIDELITY.md`
- Datasheet (MAIN): `firmware/reference/39632e.md` (DS39632E PIC18F2455/2550/4455/4550)
- Datasheet (CONTROL): Microchip DS41303 (PIC18F25K20) — fetch when needed; not in repo
- Clock derivation: `docs/analysis/MAIN_CLOCK_TIMING.md`
- AN0 boot detail: `docs/analysis/MAIN_AN0_STANDBY_TRACE.md`
- V1.71 source: `src/dlcp_fw/asm/dlcp_control_v171.asm`
- V3.2 source: `src/dlcp_fw/asm/dlcp_main_v32.asm`

---

## 15. How an Autonomous Agent Picks This Up

The branch `feature/sim-rewrite-rust` is structured so a fresh agent can do:

```bash
.venv_ep0/bin/python scripts/sim_rewrite_next.py status
```

…to see the current phase + next pending sub-task, and:

```bash
.venv_ep0/bin/python scripts/sim_rewrite_next.py advance
```

…to attempt the next sub-task autonomously (run the gate, if green mark sub-task done; if red, print the exact failure for the agent to fix).

`docs/SIM_REWRITE_RUST_PROGRESS.md` is the canonical machine-readable ledger; `scripts/sim_rewrite_next.py` is the canonical entry point. Both are self-describing.
