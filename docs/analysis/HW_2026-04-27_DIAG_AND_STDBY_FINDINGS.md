# Hardware Session 2026-04-27 — Findings + Symptom-Equivalent Sim Plan

## 1. Branch + scope

- Branch: `feature/sim-rewrite-rust`
- Rig: V1.71 CONTROL + V3.2 MAIN0 + V3.2 MAIN1 (recommended deployed pair)
- Goals: validate P3.6b on real silicon; observe full STDBY/wake cycle; scope a
  symptom-equivalent sim plan to encode the observations as regression tests.

## 2. Rig identity (verified)

Both MAINs HEALTHY at baseline via cmd 0x44:

| MAIN  | DevSrvsID (initial) | Version    | Config                  | Reset | Runtime |
|-------|---------------------|------------|-------------------------|-------|---------|
| LEFT  | 4297256164          | V3.2 r0x30 | LX521.4 22MG10F-v7      | POR   | all-zero |
| RIGHT | 4297256086          | V3.2 r0x30 | LX521.4 22MG10F-v5      | POR   | all-zero |

EEPROM revision byte at offset 0x82 stays stale — the operator flasher does NOT
write EEPROM. The fact that cmd 0x44 responds at all proves application code is
at canonical V3.2 (cmd 0x44 was added in rev 0x37+).

## 3. Test A — PB1/PB2 Diag pages (P3.6b validation)

Operator manually navigated CONTROL Diag pages via physical RIGHT button
(state 4 = PB1 Diag, state 5 = PB2 Diag).

LCD camera captures (direct image inspection — see task #43 for why the OCR
consensus extractor cannot be trusted on this layout):

```
PB1: I+ D1 SE B4
RA A3 O8 V6 W+..
```

```
PB2: I+ D  S+ B
R+ A9  P  OB W9..
```

Both rows 0 begin with `PBn:` colon prefix. Per V1.71 Tier-1 layout spec
(`docs/V163B_DIAGNOSTICS_MENU_SPEC.md`), the colon prefix means
`v171_diag_present.bit_n = 1` was set successfully on real silicon, i.e. the
BF/2N reply burst from MAIN0 was processed by CONTROL through the
`v171_bf2x_case_check` parser path.

### Conclusion (P3.6b)

**V1.71 firmware is NOT broken on real silicon** — both PB1 and PB2 BF/2N
reply convergences work. The sim-side saturation that occurs in BOTH gpsim
Python harness AND Rust silicon-correct ring is therefore a **shared sim
fidelity gap**, not a firmware bug.

The four `_V171_V32_PB2_BRIDGE_XFAIL` markers in
`tests/sim/test_v171_v32_layer5_diag_chain.py` stay in place. P3.6b stays open
as sim-side investigation; the open hypotheses are now timing/electrical
(not parser-state):

- Clock-domain skew between three cores during the BF/21..BF/27 burst
- UART RX bit-timing margin tighter in sim than silicon
- Transient OERR in sim that real silicon does not exhibit
- BANK 2 RAM aliasing assumption in sim
- RXIF ISR latency model too pessimistic

This conclusion has been propagated to:

- `docs/SIM_REWRITE_RUST_PROGRESS.md` P3.6b entry
- `docs/SIM_REWRITE_RUST_SPEC.md` §7 + §13
- `tests/sim/test_v171_v32_layer5_diag_chain.py` UPDATE block

## 4. Side finding — cmd 0x44 vs LCD cell mismatch (filed task #44)

cmd 0x44 reports all-zero runtime counters from BOTH MAINs:
`Runtime: I0 D0 S0 B0 R0 A0 P0`. But the LCD shows substantial Overflow
activity (10-11 non-zero cells per page).

Hypothesis (unverified): CONTROL POR cache cells `v171_diag_pb1_*` /
`v171_diag_pb2_*` start at random RAM at cold boot. BF/2N replies of zero data
do not fully overwrite the garbage. Therefore the LCD cells reflect garbage
plus partial overwrites, while cmd 0x44's direct read-out from MAIN's
diag_i..diag_p (0x2E5..0x2EB) reflects MAIN-side counters which legitimately
are zero on a healthy idle rig.

Confirms cmd 0x44 wire-payload is a direct RAM copy of diag_i..diag_p with
no transformation:

- `src/dlcp_fw/asm/dlcp_main_v32.asm:9760+` (`hid_cmd_diag_snapshot:`)

## 5. Side finding — Flipper IR not reaching CONTROL

- Flipper Zero `/dev/cu.usbmodemflip_Ovarlide1` detected, CLI returned
  `ir tx RC5 10 35` etc. as expected
- CONTROL did not respond to any IR command (MUTE, F1=preset A, F2=preset B
  all left LCD/USB state unchanged)
- Operator confirmed physical CONTROL buttons still worked → CONTROL alive
- Most likely: Flipper IR LED aim/range, IR receiver demod stuck, or
  IR_ARMED flag stuck low
- Test sequence aborted partway through; not investigated further

## 6. Test B — STDBY/wake cycle (filed task #45)

### Pre-STDBY (~20:35:38 UTC)
- Both MAINs HEALTHY, POR, all-zero counters
- LCD: `Volume:-50.0dB A / Auto Detect`

### Operator pressed STDBY on panel
- LCD black (Zzz)
- USB enumeration empty `[]`
- cmd 0x44: "No DLCP HID devices detected"
- Expected V3.2 STDBY behavior (full power-cut to MAINs)

### Operator pressed STDBY again to wake (~20:37:19 UTC)
- ONLY LEFT MAIN re-enumerated (`DevSrvsID:4297261519`)
- LEFT cmd 0x44: HEALTHY, POR, runtime `I0 D0 S1 B1 R0 A0 P0`
  (Standby-cycle and Bus-fault counters bumped to 1 — expected post-wake
  increments)
- RIGHT MAIN absent
- CONTROL LCD: `Waiting for DLCP`

### Re-polled USB every 3 s for 15 s
- RIGHT MAIN never came back
- LEFT path stable

### Operator pressed STDBY again to retry (~20:42:00 UTC)
- NO RESPONSE from CONTROL
- LCD still `Waiting for DLCP`
- LEFT cmd 0x44: still `S1 B1` — **`S` did NOT increment** despite the panel
  press, meaning CONTROL never propagated a new STDBY frame to LEFT
- RIGHT still absent

### Hard mains-side power cycle (~20:43:30 UTC)
- Both MAINs back: LEFT `4297262389` + RIGHT `4297262305`
- Both HEALTHY, fresh POR, all-zero counters
- LCD back to `Volume:-50.0dB A / Auto Detect`

### Conclusions (filed as task #45)

- Asymmetric wake bug: only one MAIN re-enumerated after wake
- CONTROL stuck in WAITING refused subsequent UI input (S counter didn't
  bump on the second panel press)
- Hard cycle fully recovered both MAINs
- Fits scope of `docs/V32_MAIN_HANG_HARDENING_PLAN.md`

## 7. Symptom-equivalent sim plan (proposed)

### 7.1 Why symptom-equivalent (not bit-exact)

Bit-exact reproduction of every observed cell would require:

1. Randomized POR RAM-init in `Core::reset()` to model garbage at cold boot
   (would let task #44 mismatch reproduce)
2. PSU/inrush/wake-pin-skew model (would let task #45 asymmetric wake
   reproduce)
3. More hardware data than we currently have (scope captures of wake-pin
   transitions on both MAINs during the failed wake; PSU rail capture)

None of (1)-(3) are scoped today.

Symptom-equivalent reproduction at the parser/state-machine level
(no PSU/inrush model needed) is reachable today.

### 7.2 Three proposed `multicore_parity.rs` tests

#### Test 7.2.A — `v32_main_runtime_counters_baseline_and_post_stdby_cycle`

**Mirrors**: cmd 0x44 → `S0 B0` at boot; `S1 B1` after STDBY-cycle.

**Steps**:

1. Boot 3-core ring (existing
   `three_core_ring_v171_v32_v32_boots_under_silicon_topology` fixture)
2. Probe MAIN0 BANK 2 RAM at 0x2E5..0x2EB (runtime cells `diag_i..diag_p`)
   → assert all-zero
3. Inject CTL→MAIN STDBY frame via existing UART injection helpers
4. Inject wake frame
5. Re-probe RAM → assert `S` (diag_s, 0x2E7) and `B` (diag_b, 0x2E8) cells
   incremented to 1

**Primitives**: none new — pure RAM probe + existing UART injection.
**Risk**: low.

**Why this is a faithful proxy for cmd 0x44**: the V3.2 `hid_cmd_diag_snapshot`
handler at `src/dlcp_fw/asm/dlcp_main_v32.asm:9760+` is a direct copy of
diag_i..diag_p into the HID IN buffer with no transformation. Reading the
RAM is bit-equivalent to reading the cmd 0x44 reply payload bytes [3..9].

**Caveat (per codex review)**: bit-equivalence to cmd 0x44 holds, but the
**UART BF/2N reply burst masks each cell with `andlw 0x0F`** at
`src/dlcp_fw/asm/dlcp_main_v32.asm:9267` (the chain-forwarder-safe data
range). So if a cell's high nibble is non-zero (which V1.71 Tier-1
encoding can produce — `'+' = 0x2B`, `'A'..'E' = 0x41..0x45` use bit 7-6),
RAM is bit-equivalent to cmd 0x44 but NOT to the BF/2N stream. Test A
asserts against cmd 0x44 semantics, not BF/2N. A future test could
target the BF/2N nibble-mask fidelity separately.

**Doc-fixup follow-up [LOW]**: the comment block above
`hid_cmd_diag_snapshot:` near `dlcp_main_v32.asm:9742` describes a
14-byte payload (`0x0E`) with version trailers; the actual code at
`:9765` emits an 11-byte payload (`0x0B`) per Round-5 spec note in
`docs/V32_DIAG_TIER1_SPEC.md`. Tighten or delete the stale comment
on a follow-up pass.

#### Test 7.2.B — `right_main_held_in_reset_control_stuck_in_waiting`

**Mirrors**: "only LEFT came back; CONTROL `Waiting for DLCP`".

**Steps**:

1. Build 3-core ring with MAIN1 (RIGHT) held in reset for entire run via
   `Chain::set_pin_low(1, PortLetter::A, MCLR_BIT)`
2. Boot CONTROL + MAIN0 to convergence
3. Within V1.71 reconnect-wake budget, assert CONTROL LCD shows
   `Waiting for DLCP`

**Primitive needed**: improve **MCLR-pin-held-low fidelity** in the
executor so `set_pin_low` on the MCLR pin actually halts the held core's
instruction execution. This is a behavioural-correctness improvement,
not a new debug hook.

**Why MCLR fidelity over `Chain::pause_core`** (per codex review):

- `set_pin_high/low` is currently documented as direct PORT injection for
  input pins (`crates/dlcp-sim/src/chain.rs:269,283,298`), not reset
  semantics. Extending it to honour MCLR is a real-silicon model that the
  sim is missing today.
- A physical reset-held-low model also benefits **P3.7 late-boot/recovery**
  (`docs/SIM_REWRITE_RUST_SPEC.md:304`), any future PSU/wake-skew tests, and
  any release-from-reset scenario.
- A hypothetical `Chain::pause_core(idx)` would only be a debug hook with
  no real-silicon analogue; if it's ever added it should be private/
  test-only.

**Risk**: medium — depends on how invasive the MCLR-held-low addition is
in the executor's per-core step gate.

#### Test 7.2.C — `control_in_waiting_state_does_not_emit_stdby_frame_on_button_press`

**Mirrors**: "second STDBY press from panel — no response, `S1` did not
increment, no UART frame on the wire".

**Steps (as actually landed in c993454)**:

1. Use Test B setup (MAIN1 held in reset → CONTROL in WAITING).
2. Inject STDBY-button-press by driving CONTROL **RA3 LOW** (active-low
   button) via `Chain::set_pin_low(0, PortLetter::A, 3)`, then back HIGH
   after enough ticks for the 4-tick debounce.
3. Step the chain further; capture CONTROL.TX byte stream after the
   press.
4. **Assertions** (simpler form than originally proposed — see status
   note below):
   - **No new `B0/03/00` or `B0/03/01` frame** on CONTROL.TX after the
     press (the panel STDBY route emits this triplet, see
     `src/dlcp_fw/asm/dlcp_control_v171.asm:2702-2718`,
     `standby_wake_broadcast`).
   - **CONTROL LCD still reads `Waiting for DLCP`** after the press —
     proves CONTROL did not transition out of the gated state.

**Status (post-c993454 codex re-review)**: the originally drafted
3-way diagnostic (UART byte-stream + debounce-cells `0x09A`/`0x0BE` +
`0x01F.bit1` `control_flags.CONNECTED`) was deferred; the implemented
test only locks in the byte-stream + LCD-stay form above.  The
deferred diagnostic would have classified *whether* the gate is
structural (state machine refuses to leave WAITING) or soft (debounce
timer reset).  The simpler form is enough to lock the gate-held
contract for the hardware-observed second-STDBY-press case but does
not classify the gate's nature.  Tracked as a follow-up upgrade.

**Why this gate is expected to hold** (per codex cross-reference): the
V1.71 reconnect_wait_loop intentionally consumes only RIGHT (RC5) and
LEFT (RA4) in `0x9A` for soft-CPU-reset; STDBY (RA3 → bit 0) is *not*
consumed by the reconnect-loop button gate
(`src/dlcp_fw/asm/dlcp_control_v171.asm:5018,5028,5029,5031,5032`).

**Frame correction (HIGH severity per codex review of the original
proposal)**: the panel STDBY frame is `[B0, 0x03, 0x00]` (standby) or
`[B0, 0x03, 0x01]` (wake). The earlier `B1/3A/00` candidate was wrong:
`0x3A` is the **RC5 IR** standby endpoint, *not* a panel-button serial
frame.

**Pin correction (HIGH severity per codex review)**: the STDBY button is
**RA3 active-low** (not RA2). See
`src/dlcp_fw/asm/dlcp_control_v171.asm:1968` button-scan-debounce
comment.

**Primitives**: same as Test B + RA3 pin injection (already supported by
existing `set_pin_high/low` API).
**Risk**: medium — depends on whether the gate is structural or soft;
the deferred 3-way upgrade would resolve which it is.

#### Test 7.2.D (optional, encodes task #44) — `control_diag_lcd_render_decouples_from_main_diag_ram_when_cache_seeded`

**Mirrors**: §4 side finding — cmd 0x44 reports MAIN runtime cells all-zero
while CONTROL LCD shows substantial Overflow cell content. Suggested by
codex review as a way to encode task #44 in the sim *without* needing
randomized POR RAM-init.

**Steps**:

1. Boot 3-core ring to convergence
2. Directly seed CONTROL's PB1/PB2 diag cache cells
   (`v171_diag_pb1_*`, `v171_diag_pb2_*` in BANK 1 — exact addresses to
   be looked up in `dlcp_control_ram.inc`) to non-zero values that
   correspond to V1.71 Tier-1 Overflow encoding
3. Probe MAIN0 BANK 2 RAM at 0x2E5..0x2EB → assert all-zero (MAIN side
   genuinely idle)
4. Render CONTROL LCD by stepping into the diag-page render path and
   walking the LCD-raster output
5. **Assert**: LCD row content reflects the seeded cache values, NOT
   MAIN's actual RAM state. This proves the rendering decouples MAIN
   counters from CONTROL display when CONTROL cache holds stale/garbage.

**Why this matters**: real silicon's task #44 mismatch is most-likely
caused by CONTROL POR cache cells starting at random RAM, never fully
overwritten by zero-data BF/2N replies. A deterministic Rust sim can't
*spontaneously* produce that mismatch (sim POR clears RAM to known
values), but a **seeded probe** still exercises the same control-flow
divergence and locks down the contract: "CONTROL LCD is sourced from
its local cache, which can desync from MAIN counters".

**Primitives**: direct CONTROL RAM seeding (already available via the
sim's RAM-write path used by other multicore_parity tests).
**Risk**: low to medium — main risk is locating the exact RAM addresses
of V1.71's per-PB cache cells in `dlcp_control_ram.inc`.

### 7.3 Build order

A → B → C → D.

- A is independent + low risk + validates the RAM-probe approach for
  cmd 0x44 cells
- B introduces the MCLR-held-low fidelity improvement
- C reuses B's setup and adds the button-pin probe (the originally
  drafted state-cell probes -- `0x09A`/`0x0BE`/`0x01F.bit1` -- were
  deferred during implementation, see §7.2.C status note and §9
  Test C entry; the as-landed test asserts only the byte-stream +
  LCD-stay form)
- D is independent of B/C; it can be parallelised with A or deferred

### 7.4 Ledger placement

Sibling sub-tasks under the existing P3.6 split. Propose
**P3.8a / P3.8b / P3.8c / P3.8d** in `docs/SIM_REWRITE_RUST_PROGRESS.md`,
sequenced before `P3.gate`.

Each sub-task should explicitly carry the qualifier
**"symptom-equivalent (not bit-exact)"** in its title so the ledger does
not let them retire P3.6b on completion. P3.6b stays the
`v171_diag_present == 0x03` open issue.  Task #22
(gpsim-PB2-only saturation) remains representative.  Task #94 was
filed 2026-05-04 to investigate a rust-specific surface; briefly
closed as duplicate but RE-OPENED the same day after user
pushback.  Probes v15-v18 confirmed: real HW shows diag values
after just 4 RIGHT presses (no further input), but rust chain
goes silent post-nav -- zero TX from any core for 10M ticks
(~208ms wall) -- so V1.71's foreground busy-loop never re-fires
the cmd 0x21 cadence.  Most likely cause: Timer3/Timer1 ISR
vector dispatch on rust failing to drive periodic interrupts.
Separate scope from the P3.8 sub-tasks; task #94 is the active
investigation.

## 8. Questions for codex review

A. **Test scoping**: are Tests A/B/C correctly scoped, or should any be
   merged or split?

B. **Test A faithfulness**: I claim that reading MAIN's BANK 2 RAM at
   0x2E5..0x2EB is bit-equivalent to reading the cmd 0x44 reply payload
   [3..9], based on the inline copy in `hid_cmd_diag_snapshot:`. Is there
   a path I'm missing where the HID emit-side transforms or filters
   bytes differently than the asm shows?

C. **Test B primitive choice**: should `Chain::pause_core(idx)` be added as
   a first-class primitive, or should we instead improve MCLR-pin-held-low
   fidelity in the executor and use `set_pin_low`? Argue one over the other
   and tell me which existing/future tests would benefit from each.

D. **Test C probe shape**: I propose "no new outgoing UART frame on
   CONTROL.TX after a button press while in WAITING" as the assertion. Is
   there a stronger or more diagnostic assertion (e.g., assert specific
   V1.71 internal state cells) that would diagnose the gate's nature
   (structural vs debounce) at the same time?

E. **Hardware-data extraction**: should we extract more hardware data
   (oscilloscope on wake pin / USB D+ during failed wake; multiple
   STDBY/wake repeats; second rig for cross-check) BEFORE writing
   Tests A/B/C, or is what we have enough for the symptom-equivalent goal?

F. **Coverage gaps**: anything in §3-§6 that's NOT addressed by Tests
   A/B/C and would justify a fourth probe? (e.g., the second-STDBY-press
   ignored case, or the cmd 0x44/LCD mismatch from §4)

G. **Risk to existing P3.6b investigation**: do Tests A/B/C accidentally
   block or shadow the P3.6b sim-fidelity-gap investigation (timing/
   electrical hypotheses)? Or are they complementary?

## 9. Codex review log (2026-04-27)

This section records what the codex review pass surfaced when this doc
was first drafted. Items are listed by severity. Doc sections above
have already been revised to reflect codex's corrections; this log
preserves the audit trail.

**[HIGH]** Test C frame format was wrong. Original proposal: `B1/3A/00`.
Corrected to `B0/03/00` (standby) / `B0/03/01` (wake) per
`src/dlcp_fw/asm/dlcp_control_v171.asm:2702-2718` (`standby_wake_broadcast`).
The `0x3A` byte is the **RC5 IR** standby endpoint, never a panel-button
serial frame. Section 7.2.C now uses the correct frame.

**[HIGH]** Test C button pin was unspecified. Codex pointed out the STDBY
button is **RA3 active-low** (not RA2 or any other pin) per
`src/dlcp_fw/asm/dlcp_control_v171.asm:1968`. Section 7.2.C now names RA3.

**[MEDIUM]** Test C probe-shape upgrade. Original assertion was "no new
outgoing UART frame on CONTROL.TX". Codex proposed a 3-way diagnostic
shape: byte-stream + debounce-cells (`0x09A`/`0x0BE`) + CONNECTED flag
(`0x01F.bit1`). The 3-way shape diagnoses whether the gate is structural
(state machine refuses to leave WAITING) or soft (debounce timer reset)
regardless of test outcome.

**Status correction (post-c993454 codex re-review)**: the 3-way shape
described above did NOT actually land in the implemented Test C.  The
test as committed only scans CONTROL.TX for the `B0/03/0x` triplet
plus a final LCD-still-WAITING assertion (no `0x09A` / `0x0BE`
debounce snapshot, no `0x01F.bit1` CONNECTED-flag check).  Section
7.2.C's text reflects that simpler form; the stronger 3-way probe is
deferred and would be a follow-up upgrade.  The byte-stream + LCD
combination is enough to lock in the gate-held contract for the
hardware-observed second-STDBY-press case, but does not classify
*why* the gate held (structural vs soft).

**[MEDIUM]** Test B primitive choice. Original proposal offered two
options: `Chain::pause_core(idx)` first-class API OR improved MCLR
fidelity. Codex argued for **MCLR fidelity** because (a) it has a
real-silicon analogue, (b) `pause_core` would be a pure debug hook, and
(c) MCLR fidelity also unblocks P3.7 and any future PSU/wake-skew work.
Section 7.2.B now commits to the MCLR-fidelity path.

**[MEDIUM]** Coverage gap → Test D added. Codex flagged that the §4
cmd 0x44 / LCD cell mismatch (filed task #44) was not addressed by
Tests A/B/C and proposed an optional fourth test D that seeds CONTROL
diag cache nonzero while MAIN diag RAM stays zero, then asserts LCD
can disagree with MAIN's `0x2E5..0x2EB`. This encodes the task-#44
contract without needing randomized POR RAM-init. Section 7.2.D added.

**Status update (post-c993454 codex re-review)**: The c993454-shipped
Test D was characterised by codex as "mostly separate-memory
tautology" -- it asserted RAM-address independence but never entered
`v171_diag_pb_screen` or asserted the LCD raster.  That stronger
LCD-render version (task #52) was deferred during the c993454
landing and has now landed as **P3.8d-strong**
(`control_diag_lcd_render_pb1_screen_reflects_seeded_cache_not_main_ram`):
two-core chain + HD44780 slave, navigates to PB1 Diag via 4
RIGHT-press cycles, seeds the cache, walks chunked steps until the
cadence-driven redraw flips the layout to `PB1:` (cells visible),
asserts LCD shows seeded values (`E` for `diag_pb1_s = 0x0E` -- a
value MAIN cannot produce naturally) AND MAIN0 `diag_d`/`s`/`b`/
`r`/`a`/`p` remain `0x00`.  The original "mostly tautology" weak
test stays in place as a fast structural regression alongside the
strong probe.

**[LOW]** Test A faithfulness caveat. RAM probe is bit-equivalent to
cmd 0x44 reply payload `[3..9]`, but the **UART BF/2N reply burst masks
each cell with `andlw 0x0F`** at `src/dlcp_fw/asm/dlcp_main_v32.asm:9267`.
So RAM ≡ cmd 0x44 (always), RAM ≡ BF/2N (only for nibble-range data).
Section 7.2.A now documents this caveat.

**[LOW]** Stale comment in `src/dlcp_fw/asm/dlcp_main_v32.asm:9742`
claims the cmd 0x44 payload is 14 bytes (`0x0E`) with version trailers;
the actual code at `:9765` emits an 11-byte payload (`0x0B`) per Round-5
spec note. Tracked as a doc-fixup in Section 7.2.A.

**Ledger guidance.** Codex emphasised: name P3.8a/b/c/d as
**"symptom-equivalent (not bit-exact)"** and do NOT use them to retire
P3.6b. P3.6b stays the `v171_diag_present == 0x03` open issue, now
understood as a test-scenario artifact (V1.71 foreground busy-loop
exits after first BF/2N dispatch without continuous user events --
per the 2026-04-28 P3.6b research closure).  Task #94 was opened
2026-05-04 to investigate a candidate rust-zero-replies surface but
closed the same day as duplicate of the 2026-04-28 closure (probes
v10/v11 with new uart_rx_history primitives confirmed rust accepts
all bytes and dispatches BF/2N just like gpsim).  Separate scope
from the P3.8 sub-tasks.  Section 7.4 carries the
"symptom-equivalent" qualifier explicitly.
