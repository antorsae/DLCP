# V1.71 Diag-page protocol timeline (probe v22, rust 3-core, 2026-05-04)

## TL;DR

The diag page's poor responsiveness is **not** protocol saturation
or RXIF starvation — it is V1.71 firmware spending ~80% of CONTROL
CPU time in two foreground loops gated on user-driven events.  Probe
v22 quantifies this on the rust silicon-correct ring (V1.71 CONTROL
+ V3.2 MAIN0 + V3.2 MAIN1) by capturing every UART byte with
universal-tick timestamps + sampling CONTROL's PC across 14 phases
of the operator workflow (boot → 4 RIGHT → 7 LEFT/RIGHT cycles →
steady-state).  Output: `artifacts/probes/v22_run4.txt`.

| Hypothesis | Evidence | Verdict |
|---|---|---|
| Link saturation | <0.5% wire utilization at peak | REJECTED |
| RXIF FIFO starvation | CTL.rx accepted byte count == MAIN1.tx wire byte count, every phase | REJECTED |
| Heartbeat traffic interfering with diag dispatch | Heartbeat is ~1 frame/sec; diag bursts inject 7 reply frames at full link speed (46k tick gaps = back-to-back) | REJECTED |
| V1.71 foreground busy-loop dominating | 47-58% PC time in `display_loop_iteration`; 27-32% in `button_scan_debounce`; only 3-8% in `rx_parser_entry` (where BF/2N dispatch lives) | CONFIRMED |

## Probe details

- Script: `artifacts/probes/v22_diag_page_timeline_probe.py`
- Builds the rust 3-core ring `from_v171_v32`, captures
  `Chain::uart_tx_history` + `uart_rx_history` (timestamped wire
  + FIFO-accepted byte streams) per-phase, samples
  `current_ctl_pc()` between each `step_many(1)` chunk, and
  classifies each PC by the nearest preceding non-`flow_*` label
  loaded dynamically from `src/dlcp_fw/asm/dlcp_control_v171.lst`.
- Conversion: 1 universal tick = 20.833 ns (48 MHz universal
  clock); 1 ms = 48,000 ticks; 1 chain frame (3 bytes @ 31250
  baud) = 50,688 ticks.

### Operator workflow simulated

Mirrors `docs/HARDWARE_TEST.md` §"Diagnostics page":

1. Boot + run-until-connected (LCD: `Volume:-17.0dB A` / `Auto Detect`)
2. Idle 13 seconds (no nav)
3. Press RIGHT four times to reach PB1 Diag (state 4) — LCD becomes `PB1` / `n/a`
4. Idle on PB1 Diag with no further input (~13 sec)
5. Cycle LEFT (PB1 Diag(4) → Setup(3)) then RIGHT (back) seven times
6. Idle on PB1 Diag again (~13 sec)

Final LCD: `PB1` / `OK` — PB1 reached `Healthy` layout after the
4th LEFT/RIGHT cycle (probe shows `v171_diag_present` flipped from
`0x00` to `0x01` between cycle_3 and cycle_4).  PB2 (`present.bit_1`)
never set during the 7 cycles; matches operator HW retest report
("eventually PB1 OK; PB2 still n/a... eventually PB2 should show OK").

## Wire-level evidence (link is far from saturated)

Per-phase byte counts, all three links measured at the wire (TX
history) and at the FIFO-accept point (RX history).  Frame-aligned
where possible (chain frames = 3 bytes).

### Phase 1 — `post_boot_idle` (no navigation, 13.3 sec)

| Link | bytes | frames | bytes/sec | wire utilization |
|---|---|---|---|---|
| CTL.tx → MAIN0.rx | 33 | 11 | 3 | 0.07% |
| MAIN0.tx → MAIN1.rx | 33 | 11 | 3 | 0.07% |
| MAIN1.tx → CTL.rx | 33 | 11 | 3 | 0.07% |

Steady-state heartbeat: ~1 frame per second on each ring edge,
matching the V1.71/V3.2 BF/04 design cadence.  CTL.rx accepts all
33 bytes — zero FIFO drops.  Median inter-frame gap on every
edge ≈ 54M ticks ≈ 1.13 sec.

### Phase 6 — `pb1_diag_steady_initial` (PB1 Diag, no nav, 13 sec)

| Link | bytes | frames | bytes/sec | wire utilization |
|---|---|---|---|---|
| CTL.tx → MAIN0.rx | 21 | 7 | 1 | 0.04% |
| MAIN0.tx → MAIN1.rx | 21 | 7 | 1 | 0.04% |
| MAIN1.tx → CTL.rx | 21 | 7 | 1 | 0.04% |

Steady-state on PB1 Diag is *quieter* than post-boot — only ~0.5
frames/sec.  This rules out heartbeat-flood explanations entirely.

### During RIGHT-press windows (e.g. nav_RIGHT_2)

When a button press fires, V1.71 exits the busy-loop and runs a
diag query cadence.  Probe captures one query → 7-frame reply
burst:

| Link | bytes | frames | inter-frame min |
|---|---|---|---|
| CTL.tx → MAIN0.rx | 27 | 9 | 46K ticks (back-to-back) |
| MAIN0.tx → MAIN1.rx | 54 | 18 | 46K ticks (back-to-back) |
| MAIN1.tx → CTL.rx | 72 | 24 | 46K ticks (back-to-back) |

The minimum 46K-tick inter-frame gap (= 960 µs) is the wire-time
limit for a 3-byte frame at 31250 baud.  MAIN0/MAIN1 are emitting
the BF/21..BF/27 reply burst at FULL link speed — the protocol
itself is fine.  Peak instantaneous rate ≈ 12 bytes/sec averaged
over 6 sec, with bursts at 31250 baud during the actual reply.
**No saturation, no FIFO drops**: CTL.rx accepted 72 bytes against
72 bytes wire-emitted.

## CPU-level evidence (busy-loop dominates)

PC histogram, sampled at every `step_many(1)` chunk
(~12K Tcy = ~1 ms intervals).  Numbers are percent of samples
in each function (binned automatically from .lst-derived label
addresses).  Other regions (BF parser body, diag query emit,
diag render) are below the 200-400 sample resolution per phase.

| Phase | display_loop_iteration | button_scan_debounce | rx_parser_entry | eeprom_write_byte |
|---|---|---|---|---|
| post_boot_idle | 50% | 31% | 5% | 0% |
| nav_RIGHT_1 | 49% | 33% | 3% | 4% |
| nav_RIGHT_4 | 49% | 28% | 5% | 4% |
| pb1_diag_steady_initial | 48% | 31% | 4% | 0% |
| cycle_4 (PB1 converges!) | 40% | 30% | 8% | 5% |
| cycle_7 | 47% | 27% | 7% | 5% |
| pb1_diag_steady_post_cycles | 47% | 31% | 5% | 0% |

### Interpretation

- **`display_loop_iteration` (~47-58%)** is V1.71's foreground
  busy-loop body (`asm:2885-2897`).  It branches back to itself
  when `0x9A == 0 && control_flags.bit3 == 0`.  Both predicates
  are zero in the no-IR/no-mute test scenario, so the loop
  iterates ~93 K times per cadence call (per the 2026-04-28
  P3.6b research closure).  This is V1.71 by design — it relies
  on user-driven events to exit the loop and let the cmd 0x21
  cadence + BF parser dispatch run.
- **`button_scan_debounce` (~27-32%)** is the panel-button
  polling+debounce path, also gated on the foreground loop.  The
  binning here also covers `control_core_service_*`,
  `serial_tx_routed_frame`, `full_sync_burst`, and the
  per-channel frame-emit routines (`poll_frame_send`,
  `volume_frame_send`, etc.) that live in the same address
  block (0x0994..0x0DB2 in V1.71 r0x0F).  Together with the
  busy-loop they account for ~80% of CPU time.
- **`rx_parser_entry` (~3-8%)** is the actual byte-arrival
  parser.  Even during the diag-page reply burst, only 5-8% of
  CTL CPU time goes here — RXIF dispatch is fine, but it has
  little room to make progress because the busy-loop is hogging
  the CPU.
- **`eeprom_write_byte` (~3-5% during navigation)** appears
  during nav phases because each nav event commits the new menu
  state to EEPROM, which is a slow blocking sequence.

## Convergence trajectory

`v171_diag_present` cell tracking across the 14 phases:

| Phase | present | target | flags | PB1 cache slot 7 | PB2 cache slot 7 |
|---|---|---|---|---|---|
| post_boot_idle | 0x00 | 0x00 | 0x00 | 0 | 0 |
| nav_RIGHT_1 (Preset) | 0x00 | 0x00 | 0x00 | 0 | 0 |
| nav_RIGHT_2 (Input) | 0x00 | 0x01 | 0x07 | 0x01 | 0 |
| nav_RIGHT_3 (Setup) | 0x00 | 0x01 | 0x06 | 0x01 | 0 |
| nav_RIGHT_4 (PB1 Diag) | 0x00 | 0x00 | 0x06 | 0x01 | 0 |
| pb1_diag_steady_initial | 0x00 | 0x01 | 0x06 | 0x01 | 0 |
| cycle_1 | 0x00 | 0x00 | 0x06 | 0x01 | 0 |
| cycle_2 | 0x00 | 0x00 | 0x06 | 0x01 | 0 |
| cycle_3 | 0x00 | 0x00 | 0x03 | 0x01 | 0 |
| **cycle_4** | **0x01** | 0x01 | 0x07 | 0x01 | **0x01** |
| cycle_5 | 0x01 | 0x01 | 0x02 | 0x01 | 0x01 |
| cycle_6 | 0x01 | 0x01 | 0x02 | 0x01 | 0x01 |
| cycle_7 | 0x01 | 0x00 | 0x07 | 0x01 | 0x01 |
| pb1_diag_steady_post_cycles | 0x01 | 0x00 | 0x07 | 0x01 | 0x01 |

Notes:

- PB1 cache slot 7 (= `diag_p` from BF/27) gets written to 0x01
  *during nav_RIGHT_2* — the parser is fast enough to dispatch a
  single BF/27 frame inside a single nav-event window — but
  `present.bit_0` is NOT set yet because the parser-target
  toggle has not aligned with the BF/27 RUNTIME-LAST tail.
- `present.bit_0` finally sets at cycle_4 (4 LEFT/RIGHT cycles
  after first arriving at PB1 Diag).  PB2 cache slot 7 also gets
  written 0x01 in the same cycle.  This is the convergence point
  that flips the LCD layout from `Absent` (`PB1` / `n/a`) to
  `Healthy` (`PB1` / `OK`).
- `present.bit_1` (PB2 ready) does NOT set during the 7-cycle
  window — needs more navigation cycling, matching the operator
  HW report ("PB2 still n/a... eventually PB2 should show OK").

## Why this is firmware design, not a sim/protocol bug

1. The link is at <1% utilization throughout — there is no
   physical saturation that could drop bytes.
2. CTL.rx FIFO accepts every byte that arrives at the wire
   (TX-history bytes equal RX-history bytes for every phase on
   the MAIN1→CTL edge).  No silicon FIFO drops.
3. The MAIN0/MAIN1 reply burst is emitted at full link speed
   (46K tick = 960 µs back-to-back), so the protocol's frame
   density is at the wire limit during the burst — V1.71 has all
   the bytes it needs.
4. CONTROL spends ~50% of CPU time in `display_loop_iteration`
   and ~30% in `button_scan_debounce`, both gated on
   user-driven events.  The BF parser only runs when those
   loops yield, which is rare in the no-IR/no-mute test
   scenario.
5. Real HW shows the same behavior: operator retest 2026-05-04
   with V3.2 rev 0x3F + V1.71 rev 0x0F — multiple LEFT/RIGHT
   cycles needed to converge each PB.

## Implications for any "make the diag page faster" work

If V1.71 were rewritten to reduce time spent in
`display_loop_iteration` / `button_scan_debounce`, the diag
cadence would naturally converge faster.  Concrete options:

1. **Force-cadence the cmd 0x21 query** out of an interrupt
   (Timer1/2/3 cadence) instead of letting it ride on the
   foreground busy-loop's exit predicate.  The rust simulator
   already verifies Timer3 IRQ dispatch works correctly
   (`peripheral_timers_parity::timer3_overflow_dispatches_to_high_vector_via_executor`),
   but V1.71 firmware never actually enables Timer3 (T3CON=0
   per probe v19).
2. **Tighten the busy-loop exit predicate** so it polls the
   cadence reload counter as well as the user-event flags
   (`0x9A` and `control_flags.bit3`).  This would convert the
   loop from "wait for user" to "wait for any of {user, cadence
   tick}".
3. **Skip the busy-loop entirely when the diag page is active**.
   The renderer already has its own per-frame service in
   `v171_diag_loop`; gating the foreground loop on the menu
   state would let the diag cadence run at its design rate
   (~1 cmd 0x21 per second per PB).

Any of (1)-(3) would also benefit the operator on real HW: PB1
+ PB2 would converge after entering the page, instead of needing
explicit LEFT/RIGHT cycling.

## Reusable artifacts produced by this probe

- `crates/dlcp-sim-py/src/lib.rs::uart_{tx,rx}_records_full` —
  PyO3 methods returning timestamped `(tick, src, dst, byte)`
  records.  Useful for any future frame-level timing analysis.
- `src/dlcp_fw/sim/dlcp_sim_native.py::Chain.uart_{tx,rx}_records_full` —
  Python facade wrappers.
- The probe's `_load_pc_index` + `_bisect_pc` + `classify_pc`
  pattern reads `dlcp_control_v171.lst` at startup so PC binning
  stays accurate across firmware revisions without any hardcoded
  addresses.
