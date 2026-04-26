# `dlcp-sim` Rust Rewrite — Progress Ledger

Last updated: 2026-04-26
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

- [done] P0.0 Resolve BAUDCON open-question (spec §11b)
  - verify: `.venv_ep0/bin/python scripts/probe_baudcon_mapping.py`
  - artifact: `scripts/probe_baudcon_mapping.py` + an appended note in spec §11b documenting which of the three explanations holds (second mapping; gpsim USART quirk; or test coarseness).
  - notes: must run before Phase 4 dual-run, but blocks no earlier work — placed at P0.0 so it gets resolved early. The probe loads V3.2 MAIN under gpsim, breaks on writes to 0xF98 and 0xFB8, executes `uart_config`, and reports which (if any) trigger.

- [done] P0.1 Add `--capture-ground-truth` pytest flag
  - verify: `rm -rf artifacts/ground_truth/test_v17_chain__test_v17_stock_v16b_chain_reaches_display__* ; .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py::test_v17_stock_v16b_chain_reaches_display --capture-ground-truth -q ; find artifacts/ground_truth -maxdepth 1 -type d -name 'test_v17_chain__test_v17_stock_v16b_chain_reaches_display__*' | grep -q .`
  - artifact: `tests/sim/conftest.py` (extension), `scripts/capture_gpsim_ground_truth.py` (helper)
  - notes: hooks into existing chain-harness `step()` at the conftest level so tests don't need rewrites. The dirname format is `<module-stem>__<sanitized-nodeid>__<sha1[:12]>` so the verify uses `find ... -name '...__*'` to match the hash suffix (length-agnostic glob). The leading `rm -rf` clears any stale directory from a prior run so the gate detects fresh creation; the conftest's per-phase `pytest_runtest_makereport` aggregates setup/call/teardown outcomes into one summary.json (setup-phase failures are translated to `"error"`; aggregator precedence is `failed > error > skipped > passed`) and writes regardless of test outcome. P0.2-P0.4 fill in the streams.

- [done] P0.2 Capture stimulus stream (every external pin/IR/UART/ADC/I²C event with `(tick, core_id, pin, payload)`)
  - verify: `rm -rf artifacts/ground_truth && .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py::test_v17_stock_v16b_blackout_wake_shows_waiting --capture-ground-truth -q && .venv_ep0/bin/python scripts/check_ground_truth_capture.py --kind stimulus && find artifacts/ground_truth -path '*test_v17_chain__test_v17_stock_v16b_blackout_wake_shows_waiting__*/stimulus.jsonl' -size +0 | grep -q .`
  - artifact: `src/dlcp_fw/sim/ground_truth.py` (StimulusRecorder + ContextVar), instrumented mutators in `src/dlcp_fw/sim/{chain_gpsim,wire_chain_gpsim,control_gpsim}.py`, autouse fixture in `tests/sim/conftest.py`, validator at `scripts/check_ground_truth_capture.py`, output at `artifacts/ground_truth/<test>/stimulus.jsonl`.
  - notes: JSONL format with schema_version=1; each event is `{seq, wall_time, schema_version, kind, harness, payload}`. The verify chains pytest, the schema validator, and a non-empty assertion on the blackout-wake test's stimulus.jsonl with `&&` so a pytest failure or a recorder regression both fail the gate. Empty stimulus.jsonl is a soft pass at the validator level for read-only tests, but the per-test non-empty check on the known-active blackout-wake test ensures the recorder actually fires. The `tick` field listed in spec §4 is intentionally deferred (no uniform universal-clock counter exists pre-Phase-3). Instrumentation covers high-level chain mutators (`SingleMainChainHarness.{press,set_blackout,set_main_*_fault,clear_main_*_faults}`, `WireChainHarness.{press,set_link_fault,clear_link_faults,set_main_*_fault,clear_main_*_faults}`) AND lower-level injections that some tests call directly (`GpsimControlHarness.{press,inject_bytes,inject_triplet,inject_frames_fifo,inject_host_commands,inject_decoded_ir_event}`, `MainChainHarness.inject_frames_fifo`). **Replay-determinism through gpsim is P0.5's gate, not P0.2's**. P0.3 + P0.4 add the snapshot/output streams.

- [done] P0.3 Capture RAM/SFR snapshots at chain-mutator boundaries (option A — minimum-viable)
  - verify: `rm -rf artifacts/ground_truth && .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py::test_v17_stock_v16b_blackout_wake_shows_waiting --capture-ground-truth -q && .venv_ep0/bin/python scripts/check_ground_truth_capture.py --kind snapshots && find artifacts/ground_truth -path '*test_v17_chain__test_v17_stock_v16b_blackout_wake_shows_waiting__*/snapshots/*.ram.bin' | grep -q .`
  - artifact: `artifacts/ground_truth/<test>/snapshots/<seq:010d>.<phase>.<harness_id>[.<event_kind>].{ram.bin,sfr.json}` (RAM bank 0 = 256 bytes; top-of-bank-15 SFR map as hex-keyed JSON), plus `dump_state()`/`harness_id` on `GpsimControlHarness` and `MainChainHarness`, `SnapshotTaker` + `GroundTruthContext` in `src/dlcp_fw/sim/ground_truth.py`, `snapshot_after_event(...)` calls in `src/dlcp_fw/sim/{chain_gpsim,wire_chain_gpsim,control_gpsim}.py`, `--kind snapshots` validator in `scripts/check_ground_truth_capture.py`.
  - notes: option A from the planning discussion — snapshot after each recorded mutator event rather than on a 1ms cadence. Spec §4 listed "every 1 ms simulated time" but a 1ms cadence is impractical (4 KB RAM dump per snapshot × 1000 snapshots/sec × ~2ms gpsim CLI per byte = ≈10× wall-clock blowup; AGENT decision: defer to a later sub-task if needed). The blackout-wake test produces 6 snapshots (~25 KB) and adds ~60s wall-clock for the dumps; full sim suite under capture should land well under the 27-min gpsim baseline. Empty-stimulus tests are exempt from the "≥ 1 snapshot" gate. **The 1ms cadence in spec §4 is now effectively superseded** for Phase-0 purposes; if the Rust ISA test (P1.8) needs finer-grained boundaries, those can be added without breaking this layout.

- [done] P0.4 Capture per-UART TX byte stream + LCD raster + EEPROM
  - verify: `rm -rf artifacts/ground_truth && .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py::test_v17_stock_v16b_blackout_wake_shows_waiting --capture-ground-truth -q && .venv_ep0/bin/python scripts/check_ground_truth_capture.py --kind outputs && find artifacts/ground_truth -path '*test_v17_chain__test_v17_stock_v16b_blackout_wake_shows_waiting__*/uart_tx_*.jsonl' | grep -q . && find artifacts/ground_truth -path '*test_v17_chain__test_v17_stock_v16b_blackout_wake_shows_waiting__*/eeprom_*.bin' | grep -q .`
  - artifact: per-test `uart_tx_<harness_id>.jsonl` (route/cmd/data triplets), `lcd_<harness_id>.txt` (2-line raster, control-only), and `eeprom_<harness_id>.bin` (256 raw bytes), all under `artifacts/ground_truth/<test>/`. Implemented by `OutputCapture` + `OutputCapturable` Protocol in `src/dlcp_fw/sim/ground_truth.py`, `dump_harness_outputs(self)` calls in `GpsimControlHarness.close()` and `MainChainHarness.close()`, and `_check_outputs` in `scripts/check_ground_truth_capture.py`.
  - notes: option-A scope. Drained at harness close() *before* gpsim subprocess teardown so `_read_eeprom_bytes()` can still issue reg() calls. EEPROM read is the dominant cost (~50ms × 256 addr × 3 ops × 2 harnesses ≈ 75s overhead per test); only paid when `--capture-ground-truth` is on. Per-write EEPROM tracking (spec §4 "before/after every write") is **deferred** — a future sub-task could add it via the EECON1.WR write breakpoint, but option A doesn't need it for ISA validation. Empty-stimulus tests are exempt (no harnesses opened, no triplet written).

- [done] P0.5 Verify replay of every captured fixture matches gpsim output
  - verify: `rm -rf artifacts/ground_truth && .venv_ep0/bin/python -m pytest tests/sim/test_v17_chain.py::test_v17_stock_v16b_blackout_wake_shows_waiting --capture-ground-truth -q && .venv_ep0/bin/python scripts/replay_ground_truth.py --all`
  - artifact: `scripts/replay_ground_truth.py`, plus `DLCP_GROUND_TRUTH_OUT` env-var override path through `tests/sim/conftest.py` (`_ground_truth_root()`).
  - notes: approach B from the planning discussion — re-runs each captured test via pytest with the conftest output path overridden into a tempdir, then bit-exact diffs against the blessed corpus. Stimulus diff filters `wall_time` (run-local). Snapshots and outputs (UART/LCD/EEPROM) are bit-exact. summary.json is not diffed (carries run-local timestamps and durations). Verify takes ~7 min (217s capture + 217s replay for the blackout-wake test); a divergence dumps the failing replay capture to `artifacts/sim_rewrite_divergences/P0.5__<test>__replay/` for post-hoc inspection. Approach A (standalone JSONL replay without pytest) is the obvious follow-up if/when the Rust replayer needs harness-construction-from-stream — out of scope for P0.5.

- [done] P0.gate Run phase-0 gate
  - verify: `.venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 0`
  - artifact: stdout summary; the `verify-phase` runner skips gate tasks so this command no longer recurses on itself; reruns every non-gate sub-task's verify and reports pass/fail for each. The full-suite "≥ 95% coverage" blessing is intentionally separate (`scripts/run_phase0_blessing.py`) so the gate stays bounded.

---

## Phase 1 — Rust ISA Core

- [done] P1.1 `crates/dlcp-sim/` workspace member skeleton + `Variant`, `Core`, `Memory` types
  - verify: `cd crates/dlcp-sim && cargo build --release`
  - artifact: `crates/dlcp-sim/Cargo.toml`, `src/lib.rs`, `src/core.rs`, `src/memory.rs`
  - notes: include `Cargo.toml` workspace at repo root.

- [done] P1.2 PIC18 ISA decoder for all 75 instructions
  - verify: `cd crates/dlcp-sim && cargo test --release isa::decode::tests -- --include-ignored`
  - artifact: `crates/dlcp-sim/src/isa/decode.rs`
  - notes: opcode table from DS39632E §26 (Instruction Set Summary, Table 26-2) / DS41303 §25.

- [done] P1.3 BSR + Access Bank addressing (`a` bit semantics)
  - verify: `cd crates/dlcp-sim && cargo test --release memory::access_bank::tests`
  - artifact: `crates/dlcp-sim/src/memory.rs::access_bank()`
  - notes: K20 and 2455 share the same 0x60 access-bank boundary — DS39632E §5.3 + DS41303G §5.3. The 2455's USB SFRs at 0xF66-0xF7F live entirely within the 0xF60-0xFFF SFR window so they don't move the boundary anywhere; the access-bank test in `memory::access_bank::tests::variant_independent_routing` pins this. (An earlier version of this note claimed the boundaries differ — that was wrong.)

- [done] P1.4 FSR INDF + POSTINC/POSTDEC/PREINC/PLUSW
  - verify: `cd crates/dlcp-sim && cargo test --release isa::fsr::tests`
  - artifact: covered in `isa/decode.rs` + dedicated test file.

- [done] P1.5 Hardware stack (31-deep) with PUSH/POP, STKPTR, STVREN
  - verify: `cd crates/dlcp-sim && cargo test --release stack::tests`
  - artifact: `crates/dlcp-sim/src/stack.rs`
  - notes: stack-overflow + STVREN reset is a real V3.2 hardening test (`feat(v3.2): main_service_rx_frame_gap parser stall watchdog` etc.).

- [done] P1.6 Reset sources (POR, MCLR, BOR, WDT, RESET, stack-over/underflow)
  - verify: `cd crates/dlcp-sim && cargo test --release reset::tests`
  - artifact: `crates/dlcp-sim/src/reset.rs`.

- [done] P1.7 Configuration words: parser surface for osc + WDT + IPEN consumers
  - scope: lays the typed parser (`Config::from_bytes` + accessors for
    PLLDIV/CPUDIV/USBDIV/FOSC/FCMEN/IESO/PWRTEN/BOREN/BORV/VREGEN/WDTEN/
    WDTPS/MCLRE/LPT1OSC/PBADEN/CCP2MX/STVREN/LVP/XINST/DEBUG).  The
    actual reset/peripheral wiring (e.g. STVREN gating in `apply_reset`,
    oscillator selection in P2's clock model, BOREN/IPEN in P2 BOR /
    interrupt-priority models) is the consumer's job and lands in P2
    when peripheral instantiation arrives.
  - verify: `cd crates/dlcp-sim && cargo test --release config::tests`
  - artifact: `crates/dlcp-sim/src/config.rs`.

- [done] P1.8a Intel HEX loader for flash + USER_ID + CONFIG + EEPROM
  - verify: `cd crates/dlcp-sim && cargo test --release hex::tests`
  - artifact: `crates/dlcp-sim/src/hex.rs`
  - notes: parses Intel HEX (record types 00 = data, 01 = EOF, 04 = extended-linear-address); routes bytes to the four PIC18 memory windows that may appear in either V1.71 (K20) or V3.2 (2455) releases:
      - `flash[0..0x8000]` (32 KiB program memory)
      - User ID memory at `0x200000..0x200007` (8 bytes; PIC18 application-defined identification, e.g. CONTROL release-metadata revision byte)
      - CONFIG region at `0x300000..0x30000D` (14 bytes)
      - EEPROM window at `0xF00000..0xF000FF` (256 bytes)
    DEVID at `0x3FFFFE..0x3FFFFF` is read-only on silicon and never appears in shipped releases — surface a loud error if it does. Rejects unknown record types loudly and verifies record checksums. Tested with `firmware/patched/releases/DLCP_Control_V1.71.hex` and `firmware/patched/releases/DLCP_Firmware_V3.2.hex` (both currently use only types 00/01/04).

- [done] P1.8b Cycle-accurate executor for all 75 PIC18 instructions
  - verify: `cd crates/dlcp-sim && cargo test --release exec::tests`
  - artifact: `crates/dlcp-sim/src/exec.rs`
  - notes: `Core::step(&mut self, &mut Stack) -> u8 cycles` fetches the word at PC, decodes via P1.2's `decode`, and dispatches over `Instruction`. STATUS-flag fidelity (Z/C/OV/N/DC) per DS39632E §26 / DS41303 §25 instruction encyclopedia. Variant-aware via `Memory::variant()`. Per-instruction unit tests cover STATUS transitions plus Access-Bank/BSR/FSR/PRODL/PRODH/TBLPTR/TABLAT side effects. This is the largest sub-task in P1.8 — expect ~1500–2500 LOC of executor code + per-instruction tests.

    **Cycle-cost cheat-sheet (DS39632E Table 26-2):**
      - 1 Tcy default for byte/bit/literal/skip-not-taken.
      - **2 Tcy:** unconditional branches/jumps (`GOTO`, `CALL`, `RCALL`, `BRA`); conditional branches when the predicate is true (`BC`, `BN`, `BNC`, `BNN`, `BNOV`, `BNZ`, `BOV`, `BZ` — 1 Tcy when not taken); returns (`RETURN`, `RETFIE`, `RETLW`); two-word data moves (`MOVFF`, `LFSR`); and table ops (`TBLRD*`, `TBLRD*+`, `TBLRD*-`, `TBLRD+*`, `TBLWT*`, `TBLWT*+`, `TBLWT*-`, `TBLWT+*`).
      - `RESET` and `SLEEP` are 1 Tcy per Table 26-2 (the post-instruction reset / power-down latency is separate from the instruction cycle count).
      - **Skip-taken extra cycle:** `BTFSC`, `BTFSS`, `CPFSEQ`, `CPFSGT`, `CPFSLT`, `TSTFSZ`, `DECFSZ`, `DCFSNZ`, `INCFSZ`, `INFSNZ` cost 1 Tcy when the predicate is false (skip not taken), 2 Tcy when true and the skipped target is a 1-word instruction, **3 Tcy** when the skipped target is a 2-word instruction (`GOTO`, `CALL`, `MOVFF`, `LFSR`).

- [done] P1.8c isa_parity::isa_covers_all_75_pic18_opcodes
  - verify: `cd crates/dlcp-sim && cargo test --release --test isa_parity isa_covers_all_75_pic18_opcodes`
  - artifact: `crates/dlcp-sim/tests/isa_parity.rs` (the `isa_covers_all_75_pic18_opcodes` test from spec §5).
  - notes: synthesizes a flash image that exercises every documented opcode at least once; `Core::step` walks it; asserts every `Instruction` variant has been hit. Pure decoder + executor — no gpsim required. Lands the test file that P1.8d/e will extend.

- [done] P1.8d isa_parity::isa_matches_gpsim_ground_truth_for_v171_reset_through_init
  - verify: `cd crates/dlcp-sim && cargo test --release --test isa_parity isa_matches_gpsim_ground_truth_for_v171_reset_through_init`
  - artifact: `crates/dlcp-sim/tests/isa_parity.rs` (the matching test function from spec §5).
  - notes: V1.71 CONTROL hex loaded via P1.8a, run from POR for the cycle count captured in `early_boot_v171_<N>.meta.json` (currently 10 Tcy), RAM bank 0 (256 B) + SFR window 0xF60..0xFFF (160 B) bit-exact against a runtime gpsim snapshot. Closure required: (a) full K20 POR-default SFR table per DS40001303H Tbl 4-4 landed in `reset.rs::apply_k20_por_sfr_defaults`; (b) TXSTA TRMT preserve-on-write mask in `exec.rs::sfr_write_mask` + new `apply_sfr_sw_write` RMW helper; (c) test mirror dropped PCLATH/PCLATU per §5.1.4 (only software-readable PCL transfer triggers PCH→PCLATH); (d) cycle-loop bound changed from `<` to `<=` to match gpsim's "break c N then complete current instr" semantics. Six SFR cells exempted as documented gpsim K20 modeling gaps (IPR1/IPR2/BAUDCON/PSTRCON/HLVDCON missing POR; OSCCON post-callback transient) — see `GPSIM_K20_DEVIATIONS` in the test for per-cell rationale.

- [blocked] P1.8e isa_parity::isa_matches_gpsim_ground_truth_for_v32_reset_through_an0_gate_pass
  - verify: `cd crates/dlcp-sim && cargo test --release --test isa_parity isa_matches_gpsim_ground_truth_for_v32_reset_through_an0_gate_pass`
  - artifact: `crates/dlcp-sim/tests/isa_parity.rs` (the matching test function from spec §5).
  - notes: load V3.2 MAIN hex via P1.8a, run from POR until the AN0 standby-gate pass milestone, RAM/W/STATUS/STKPTR bit-exact against a runtime gpsim fixture. The AN0 gate requires the ADC (AN0 sample) and the standby-state machine, which are P2 peripheral work — **this sub-task is expected to block on P2.x landing the ADC/comparator model**. Keeping it in the ledger so the dependency is visible; expect to flip its status to `blocked` once P1.8d lands and the prerequisite gap is concrete.

- [done] P1.gate Run phase-1 gate
  - verify: `cargo test -p dlcp-sim --release --test isa_parity && .venv_ep0/bin/python scripts/sim_rewrite_next.py verify-phase 1`
  - artifact: stdout summary; coverage report shows all 75 PIC18 opcodes executed at least once.

---

## Phase 2 — Peripherals

- [done] P2.1 EUSART — TXSTA/RCSTA/SPBRG/SPBRGH/BAUDCON, bit-level shifter, baud generator, OERR/FERR latch, RCREG FIFO
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_eusart_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/eusart.rs` + `crates/dlcp-sim/tests/peripheral_eusart_parity.rs`
  - notes: 2455 BAUDCON @ 0xFB8 (resolved P0.0 — matches gpsim, gputils, and disassembly opcode `6EB8`; the earlier "datasheet @ 0xF98" reading was a markdown rendering artifact). K20 BAUDCON @ 0xFB8 (DS41303). See spec §11b for the closed dual-run reconciliation. Phase-2 scope: TX path with baud-period-derived TRMT/TXIF timing; RX silent (Phase-3 chain wiring will deliver bytes via the pin net); OERR/FERR/RX9D preserved across SW writes via `sfr_write_mask` (RCSTA mask = 0xF8). Bit-level UART byte-stream comparison against gpsim is a Phase-4 dual-run gate. Foundation work landed simultaneously: `peripherals` module + `Core::peripherals` field + `Peripherals::tick_tcy` hooked into `Core::advance_cycles` + `Peripherals::on_sfr_write` hooked into `exec::write_addr_masked`.

- [done] P2.2 MSSP I²C — master mode, SCL stretching, ACK/NACK injection
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_mssp_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/mssp.rs` + `crates/dlcp-sim/tests/peripheral_mssp_parity.rs`
  - notes: Phase-2 minimum-viable I²C master-mode peripheral. Models SFR-write reactivity (SEN/PEN trigger state-machine progression), SCL period from SSPADD (`Fbus = Fcy / (4 × (SSPADD+1))`; `SSPADD=0x77 → 480 Tcy/bit at 4 MIPS Fcy = 33 kHz`), BF (SSPSTAT bit 0) tracking on SSPBUF write, SSPIF (PIR1 bit 3) assertion on start-or-stop completion, and SEN/PEN auto-clear at sequence end. Bit-level bus comparison against gpsim's `i2c-regfile.cc` slave is Phase-4 dual-run scope. ACK/NACK injection requires the pin network landing in Phase 3. Wired into `Peripherals::{on_sfr_write, tick_tcy, reset_state}` alongside EUSART.

- [done] P2.3 Timer3 + Timer0 (only timers actually used)
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_timers_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/timer.rs` + `crates/dlcp-sim/tests/peripheral_timers_parity.rs`
  - notes: Phase-2 minimum-viable timer peripheral. Models internal-clock-source counting (T0CS=0 / TMR3CS=0) at Tcy granularity scaled by the prescaler (Timer0 PSA + T0PS<2:0> -> 1:1..1:256; Timer3 T3CKPS<1:0> -> 1:1..1:8). 8-bit (T08BIT=1) and 16-bit Timer0 modes both wired; Timer3 always 16-bit. Overflow asserts INTCON.TMR0IF / PIR2.TMR3IF respectively. SFR-write side effects: writes to T0CON/T3CON or to TMR0L/H / TMR3L/H reset the prescaler-Tcy accumulator per DS §10.2 / §13.4. External pin sources (T0CKI, T1OSC) and 16-bit latched-buffer reads on TMR0L/TMR3L are deferred to Phase 3 / P2.7.

- [done] P2.4 ADC (AN0 only on MAIN, full Tacq + Tconv timing)
  - verify: `cd crates/dlcp-sim && cargo test --release --test peripheral_adc_parity`
  - artifact: `crates/dlcp-sim/src/peripherals/adc.rs` + `crates/dlcp-sim/tests/peripheral_adc_parity.rs`
  - notes: Phase-2 minimum-viable ADC for the AN0 boot-threshold path.  Models GO/DONE 0->1-with-ADON trigger, fixed 12-Tcy conversion delay, ADRESH:ADRESL load with the test-injected `Adc::set_an0_sample` value (right-justified or left-justified per ADCON2.ADFM), GO/DONE auto-clear on completion, PIR1.ADIF assertion.  V3.2 thresholds 0x0236 / 0x0229 / 0x0228 are pinned in the parity test.  Phase-3 pin network will replace the test-injection path with a virtual analog source pin; full Tacq + Tconv timing derived from ADCON2.{ACQT, ADCS} is deferred to P2.7 alongside the other ADCON2 fidelity items.

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
