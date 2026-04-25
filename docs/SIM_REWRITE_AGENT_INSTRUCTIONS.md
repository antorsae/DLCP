# Agent Instructions — `dlcp-sim` Rust Rewrite

You are picking up the `feature/sim-rewrite-rust` branch.  This document
is the **operational playbook** an autonomous agent follows.  The
**design** is in `docs/SIM_REWRITE_RUST_SPEC.md`; the **task list** is
in `docs/SIM_REWRITE_RUST_PROGRESS.md`.  Read both before acting.

---

## Mental model

You are replacing the existing gpsim-PTY-bridged-three-process
simulator with a single-process cycle-perfect Rust engine.  The work
is broken into **phases**, each of which has **sub-tasks** with
**verify commands** that return exit 0 iff the sub-task is complete.
Your job is to:

1. Find the next pending sub-task.
2. Implement it.
3. Run its verify command.
4. On pass: commit; the ledger marks it done.  On fail: diagnose, fix, retry.

All sub-task status changes go through `scripts/sim_rewrite_next.py`,
*not* hand-edits to the ledger.

---

## Bootstrap

```bash
cd /Users/antor/gh/XTC/third_party/vendor_binaries/DLCP_firmware/analysis-sim-rewrite-rust
git branch --show-current   # must be feature/sim-rewrite-rust
python3 scripts/sim_rewrite_next.py status
```

`status` prints the current phase, what's done, and the next pending
sub-task with its `verify` command and `artifact` paths.  That tells
you what to build.

---

## Per-sub-task workflow

```bash
# 1. See what's next.
python3 scripts/sim_rewrite_next.py status

# 2. Read the sub-task's notes line for context.  Read the relevant
#    sections of docs/SIM_REWRITE_RUST_SPEC.md for design intent.

# 3. Implement.  Examples:
#    - Phase 0: pytest plugin + capture script under scripts/
#    - Phase 1+2+3: Rust under crates/dlcp-sim/
#    - Phase 4: PyO3 + Python facade
#    - Phase 5: snapshot/replay + soak

# 4. Try advancing.  This will mark the task in_progress, run its
#    verify command, and on pass mark it done.
python3 scripts/sim_rewrite_next.py advance

# 5. If it failed, the divergence log is at
#    artifacts/sim_rewrite_divergences/<id>__<ts>.log .  Read it,
#    fix the issue, rerun `advance`.

# 6. If you can't make progress, capture the blocker:
python3 scripts/sim_rewrite_next.py block P1.5 --reason "depends on Phase 0 ground-truth fixture for v32 boot which isn't captured yet"

# 7. Once a sub-task is done and committed, repeat.
```

---

## Implementation guidance per phase

### Phase 0 — Ground-Truth Capture

You are extending the existing pytest harness to record everything a
test's gpsim run produces.  Critical files:

- `tests/sim/conftest.py` — the pytest plugin entry; this is where the
  `--capture-ground-truth` flag is added.
- `src/dlcp_fw/sim/chain_gpsim.py` and `wire_chain_gpsim.py` — these
  already expose `step()` and `lcd_lines()`; you wrap them with hooks
  that emit JSONL into `artifacts/ground_truth/<test_id>/`.
- `scripts/capture_gpsim_ground_truth.py` — the entry point that drives
  pytest with the capture flag set across the whole suite.
- `scripts/replay_ground_truth.py` — replays a captured stimulus stream
  back through gpsim and asserts the same outputs (sanity check that
  the fixtures are reproducible).

Output format: see `docs/SIM_REWRITE_RUST_SPEC.md` §4.

The phase 0 gate is coverage ≥ 95% of currently-passing `tests/sim/`
tests captured.  If a test can't be captured (e.g. it depends on
hardware), exclude it explicitly with a marker, don't let it lower
coverage silently.

### Phase 1 — Rust ISA Core

Workspace setup first: at the repo root, create `Cargo.toml` workspace
manifest if one doesn't exist; add `members = ["crates/dlcp-sim"]`.
Inside the crate:

- `src/lib.rs` — public surface.
- `src/core.rs` — `Core` struct: flash, RAM, SFRs, W, STATUS, BSR, FSRn, STKPTR, PCL/PCH/PCLATH/PCLATU, cycle counter.
- `src/memory.rs` — banked RAM + Access Bank + SFR routing per `Variant`.
- `src/isa/mod.rs` — instruction decoder + executor.
- `src/isa/decode.rs` — opcode → operation match table.
- `src/isa/exec.rs` — operation implementations.
- `src/stack.rs` — 31-deep hardware stack with STKPTR + STVREN.
- `src/reset.rs` — reset sources + entry behavior.
- `src/config.rs` — configuration words parser (CONFIG1L through CONFIG7H).

Datasheets:

- 2455: `firmware/reference/39632e.md` (DS39632E)
- K20: not in repo.  When you need K20 register layout, fetch
  `https://ww1.microchip.com/downloads/aemDocuments/documents/MCU08/ProductDocuments/DataSheets/41303G.pdf`
  via WebFetch.

The gate is `cargo test -p dlcp-sim --test isa_parity` matching ground
truth bit-exactly.

### Phase 2 — Peripherals

Each peripheral has its own `src/peripherals/<name>.rs` and its own
`tests/peripheral_<name>_parity.rs`.  Order of attack (lowest blocking
risk first):

1. EUSART (everything chains on UART)
2. Port pins + IRQ controller (peripherals fire IRQs through here)
3. Timer3 + Timer0
4. ADC (AN0 only)
5. EEPROM (with realistic write completion)
6. MSSP I²C
7. Oscillator subsystem
8. USB-SIE (last; it's the most complex and only on 2455)

Important: 2455 BAUDCON is at **0xFB8** — same address as gpsim, same
as gputils' `p18f2455.inc`, same as the assembled stock V2.3 BAUDCON
write disassembling to opcode `6EB8` at PC 0x455A.  An earlier draft
of this spec asserted the datasheet places it at 0xF98; that came
from misreading a +0x20-misaligned column header in the PDF→markdown
rendering of DS39632E Table 5-1.  The empirical resolution is in
`scripts/probe_baudcon_mapping.py` (P0.0); spec §11b documents the
closed dual-run question.

### Phase 3 — Multi-Core Wiring

This is where Task #22 is mechanically resolved.  In a single-process
unified scheduler, the cross-process bridge that produced the echo
loop simply doesn't exist.

- `src/chain.rs` — `Chain` struct with `Vec<Core>` + global event queue.
- `src/scheduler.rs` — min-heap event queue with `(deadline_tick, core_id, event_kind)` at the 48 MHz universal clock.
- `src/clock.rs` — per-Core `ticks_per_tcy` derivation from config bits (CONTROL = 16, MAIN = 12).
- `src/pinnet.rs` — pin nodes (RC6 → RC7 wiring, etc.).
- `src/boot_offset.rs` — `BootOffsetSpec::Fixed | RangedRandom { seed }`.

Boot-offset model (per user direction):
- CONTROL + MAIN0 share PSU; default offset ±50 µs (seeded PRNG).
- MAIN1 in separate enclosure; configurable offset.  Tests should sweep
  across {-2 s, 0, +500 ms, +2 s} at minimum.

The gate includes un-XFAILing the 5 Diag-chain tests in
`tests/sim/test_v171_v32_layer5_diag_chain.py` that are XFAILed today
on the gpsim echo-loop.  Those tests should PASS under the new sim.

### Phase 4 — Python Bindings + Migration

- `crates/dlcp-sim-py/` — PyO3 wrapper crate.  Build with `maturin`
  or `cargo build --release` + manual install to `.venv_ep0/lib/...`.
- `src/dlcp_fw/sim/dlcp_sim_native.py` — Python facade with the same
  shape as `chain_gpsim.py`'s `MainChainHarness` /
  `wire_chain_gpsim.py`'s `WireChainHarness`.
- `tests/sim/conftest.py` — add the `DLCP_SIM_BACKEND={gpsim,dual,rust}`
  env-var dispatcher.  Default during P4.1–P4.7: `dual`.  At P4.8: `rust`.

Migration is per-test: each `test_*` file becomes its own sub-task
once dual-run is green.  Don't try to migrate the whole suite at once;
do it batch by batch (P4.4: v17, P4.5: v171, P4.6: v31/v32, P4.7: rest).

The gate: `DLCP_SIM_BACKEND=rust pytest tests/sim -n 16 -q` runs in
under 60 s wall-clock with all green.  Compare to the 27 min gpsim
baseline.

### Phase 5 — Determinism + Snapshot/Replay + Soak

- Snapshot/restore via `serde`.  Round-trip property test:
  `restore(snapshot(c)) == c` for fuzzed states.
- Replay tool: `dlcp-sim replay <case.json>` dumps a `.lst`-equivalent
  trace.
- Soak under `tests/sim/soak/`: 10⁴+ randomized scenarios per soak test,
  reproducible per seed, dumps replay artifact on failure.

P5b (stretch) `cargo fuzz` is optional but recommended.

---

## Commit etiquette on this branch

- Every commit lands on `feature/sim-rewrite-rust`.  Don't merge to main
  until final acceptance (PF.6).
- Commit message format:
  ```
  sim-rewrite: <Pn.x> <one-line title>

  <2–4 sentences on what changed and why this satisfies the sub-task>

  verify: <the verify command from the ledger>
  ```
- Per the project's per-commit codex review hook (`AGENTS.md` →
  "Per-Commit Codex Review"), every commit triggers a codex review.
  Address HIGH/MEDIUM findings before moving to the next sub-task.
- Do NOT auto-fix LOW findings unless they sit in the same area; track
  them in the next commit's description.

---

## Anti-patterns to avoid

- **Don't hand-edit the ledger status.**  Use `sim_rewrite_next.py`.
  Atomic flips matter for restartability.
- **Don't skip dual-run during Phase 4.**  Even if a test "obviously"
  works on the new sim, the differential check is the safety net for
  catching peripheral-fidelity drift.
- **Don't try to preserve gpsim quirks** — but also don't trust the
  PDF→markdown rendering of `firmware/reference/39632e.md` blindly,
  because some tables there have alignment artifacts that disagree
  with the underlying datasheet.  When the datasheet text and gpsim
  disagree, cross-check against gputils' `p18f2455.inc` (the
  assembler that built the V3.2 hex) and the resulting opcode in
  `firmware/disasm/main/gpdasm_output.asm` before deciding which
  side to follow.  The deliberate fidelity exceptions (e.g. EEPROM
  write-completion latency) are enumerated in spec §11; BAUDCON is
  not one of them — that earlier-flagged "divergence" was resolved
  to *no divergence* by `scripts/probe_baudcon_mapping.py` (P0.0).
- **Don't model peripherals you don't need.**  Scope is the V1.71 +
  V3.2 firmware path.  USB enumeration, audio DSP, comparators, CCP
  modules not used by firmware — out of scope.
- **Don't optimize prematurely.**  Get to dual-run green first; only
  then chase the 50× wall-clock target.  An emulator that's correct
  but 5× faster is more valuable than one that's 50× faster but
  diverges from gpsim.

---

## When you're stuck

1. Re-read the relevant section of `docs/SIM_REWRITE_RUST_SPEC.md`.
2. Check the divergence log at `artifacts/sim_rewrite_divergences/`.
3. If the gate fails because a fixture is missing, escape upward and
   complete the depended-on sub-task first.
4. If you genuinely can't make progress, mark the task blocked:
   ```
   python3 scripts/sim_rewrite_next.py block P2.8 \
     --reason "USB-SIE HID dispatch needs reverse-engineering of cmd 0x44 packet shape; spec doesn't cover this"
   ```

---

## Final acceptance handoff

When all of `PF.1`–`PF.5` are `done`:

```bash
python3 scripts/sim_rewrite_next.py advance   # PF.6 (open PR)
gh pr create --title "..." --body "$(cat <<'EOF'
## Summary
- Replaces gpsim-PTY-bridged-three-process simulator with single-process cycle-perfect Rust engine
- Wall-clock: <60 s vs. 27 min on gpsim
- Task #22 echo-loop dissolved; 5 XFAILs flipped to PASS
- All sim tests green under `DLCP_SIM_BACKEND=rust`

## Test plan
- [x] dual-run (gpsim + rust) green for full sim gate (P4 gate)
- [x] rust-only green in <60 s (PF.2)
- [x] snapshot/replay round-trip (P5.1)
- [x] soak suite green (P5.4)

EOF
)"
```

That's the deliverable.  Until then, just keep advancing.
