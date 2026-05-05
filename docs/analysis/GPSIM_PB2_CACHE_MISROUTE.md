# gpsim PB2 cache misroute — investigation findings (task #117)

Branch: `feature/sim-rewrite-rust`
Author: 2026-05-04
Tracker: task #117 (P4-followup, gpsim wire-chain multi-frame
BF/22..27 cache misroute on PB2)

## Symptom

`tests/sim/test_v171_v32_layer5_chain_pb_cache_isolation` fails on
gpsim with `_V171_V32_PB2_BRIDGE_XFAIL` set.  Same root cause causes
`test_v171_v32_layer5_chain_pb2_bridge_canary` to fail at hop (f)
(PB2 cache slot[6] never receives BF/27 payload).  The post-PF.3
wiggle helper is not the problem — it correctly drives the cmd
0x21/0x22 cadence and gets `v171_diag_present` to 0x03.

## Probe setup

`/tmp/probe_gpsim_cache_misroute.py` (kept for ad-hoc reproduction
under `DLCP_SIM_BACKEND=gpsim`):

  * Loads canonical `V171_CONTROL_HEX` + `V32_MAIN_HEX` into
    `WireMultiMainChainHarness(main_units=2)`.
  * Seeds distinct diag values:
      - MAIN0 (PB1): `diag_i=0x5`, `diag_d=0x1`
      - MAIN1 (PB2): `diag_i=0xC`, `diag_d=0x2`
  * Navigates 4 RIGHT to PB1 Diag(4), then alternates RIGHT/LEFT
    every 8 chain steps for 80 iterations.
  * Reports per-iteration PB1/PB2 cache evolution + bridge byte
    deltas.

## Empirical findings

```
PB1 cache (expected I=0x5, D=0x1):  [0x5, 0x1, 0, 0, 0, 0, 0]   CORRECT
PB2 cache (expected I=0xC, D=0x2):  [0x0, 0x1, 0, 0, 0, 0, 0]   WRONG
MAIN0 diag block (untouched):       [0x5, 0x1, 0, 0, 0, 0, 0]   correct
MAIN1 diag block (untouched):       [0xC, 0x2, 0, 0, 0, 0, 0]   correct
diag_present = 0x03                 (both bits set)
bridge bytes:
  ctl_to_m0: delta=356      (CONTROL queries)
  m0_to_m1:  delta=67898    (MAIN0 forwards downstream)
  m1_to_m0:  delta=68504    (MAIN1 replies upstream)
  m0_to_ctl: delta=67898    (MAIN0 forwards reply to CONTROL)
```

Two facts to note:

  1. **MAIN1's data is being transmitted on the wire** (m1_to_m0 =
     68504 edges) — MAIN1 IS replying.  But that data never lands in
     PB2 cache (slot[0] stays 0x0).
  2. **PB2 cache slot[1] = 0x1** (MAIN0's diag_d), NOT 0x2 (MAIN1's
     diag_d).  PB2 cache is being filled with PB1 data.

Cache evolution timeline (probe iter ↔ event):

```
iter 10: PB1 slot[0] = 0x5     (MAIN0's BF/21 frame -> PB1 cache, correct)
iter 25: PB2 slot[1] = 0x1     (MAIN0's BF/22 frame -> PB2 cache, MISROUTE)
iter 35: present = 0x02        (PB2 bit set -- but on stolen data!)
iter 40: PB1 slot[1] = 0x1     (MAIN0's BF/22 again, this time in PB1)
iter 45: present = 0x03        (PB1 bit set -- on the second BF/22)
```

PB2 cache slot[0] never receives MAIN1's diag_i=0xC.  PB2 cache
slot[1..6] never receive MAIN1's data at all.  All "PB2" cache
content is actually PB1 data.

## Root cause: skip-on-silent target toggle race

V1.71's diag protocol routes incoming BF/2N frames into the cache
indexed by `v171_diag_target` (PB1 or PB2).  The MAIN reply route
byte is constant `0xBF` (see `dlcp_main_v32.asm:9294` --
`cmd_0x21_handler_emits_clean_seven_frame_burst` -- and
`dlcp_control_v171.asm:1235` -- the BF parser writes by live
`v171_diag_target`).  Reply origin is implied, not labeled.

`v171_diag_target` is normally toggled on BF/27 reception (the last
frame of the burst, in `v171_bf2x_case_check`) so it stays stable
for the full query/reply round-trip.  But the cadence loop also has
a "skip-on-silent" gate (`dlcp_control_v171.asm:4026-4039`): if
`RUNTIME_PENDING` is still set when the next cadence expires (i.e.
the previous burst hasn't completed), CONTROL pre-emptively toggles
`v171_diag_target` via `btg v171_diag_target, 0, BANKED` and
issues the next query.  This guard exists to avoid polling a silent
PB forever; the cost is that a slow-but-not-silent PB's tail
frames get re-routed.

Sequence on gpsim:

  1. CONTROL sends `B1/0x21` (query PB1).  `target = PB1`,
     `RUNTIME_PENDING = 1`.
  2. MAIN0 starts the 7-frame BF/21..27 burst.
  3. CONTROL receives BF/21, writes to PB1 cache slot[0]
     (correct).  Continues receiving subsequent frames in PB1
     slot[1..6].
  4. ~1 sec later, cadence fires.  `RUNTIME_PENDING` is STILL set
     (BF/27 hasn't arrived yet because gpsim's PTY-bridged UART is
     slow).  Skip-on-silent fires: `btg target` → `target = PB2`.
     `B2/0x21` query goes out.
  5. MAIN0's tail frames (BF/22..27 from the original burst) now
     arrive at CONTROL with `target = PB2`.  They land in PB2
     cache slot[1..6].  When BF/27 finally arrives, the parser
     sets `present` bit for the live target (PB2) -- which is why
     `present = 0x02` flips at iter 35 in the probe even though
     PB2 cache holds PB1 data on slots that landed.
  6. MAIN1 has not yet started replying within the test budget,
     so PB2 slot[0] (which would carry MAIN1's actual BF/21
     payload) stays 0x0.

The misroute is jointly produced by the firmware's
implicit-ordering assumption AND gpsim's slow UART -- not solely
one or the other.  See "Caveats" below.

## Why rust passes

The rust silicon-correct ring (`crates/dlcp-sim/`) delivers bytes
deterministically per cmd 0x21 query — each query gets exactly one
complete burst reply before the executor advances to the next
cadence cycle.  Out-of-order delivery between PB1 and PB2 doesn't
happen on the rust path; the implicit "last query → next reply"
mapping holds.

## Why gpsim hits the misroute

gpsim's wire-chain harness uses PTY-bridged UART forwarding with
file-based byte streaming (`_StreamingUartBridge` in
`src/dlcp_fw/sim/wire_chain_gpsim.py`).  The bridge introduces
delivery latency (per-edge mapping over the file FIFO) that can let
MAIN0's late burst frames overlap with CONTROL's next cadence
query, breaking the implicit query-reply ordering.

## Real-silicon implication

Per the operator HW retest 2026-05-04, real silicon does NOT exhibit
the misroute on the tested config (V1.71 + V3.2 chain, default
RUNTIME_PENDING window) -- PB1/PB2 cache content is correct after
multiple LEFT/RIGHT navigation cycles.  This matches the rust path.

That said: the firmware DOES rely on an implicit ordering assumption
(query order == reply order), and the skip-on-silent toggle exists
specifically because that assumption can fail.  The 2026-05-04 HW
retest demonstrates safety in ONE config; it does not prove the
ordering assumption is robust under all real timing margins
(longer cable runs, slower MAIN-side burst issue rate, etc.).
That's a real protocol fragility -- gpsim happens to be the
harness that surfaces it.

## Caveats

  * The probe only seeded `diag_i` (slot[0]) and `diag_d` (slot[1])
    on both MAINs.  This run proves PB2 cache slot[0] (=0x0, missing
    MAIN1's diag_i=0xC) and slot[1] (=0x1, has MAIN0's value) are
    wrong.  Slots [2..5] are zero on both MAINs, so this probe alone
    can't say whether they'd also receive cross-PB data.  The canary
    test (`pb2_bridge_canary`'s hop (f) failure) seeds `diag_p=0x07`
    on MAIN1 specifically and confirms slot[6] also fails to land,
    so the misroute extends to the full burst -- but slots [2..5]
    remain experimentally indistinguishable in the seeded probes.

  * The probe configuration is `WireMultiMainChainHarness(main_units
    =2, fast_boot=False, disable_standby_check=False)` -- the same
    config used by `pb_cache_isolation` / `pb2_bridge_canary`.
    Different chunk-cycle settings might produce different
    overlap windows.

## Resolution path

  1. **Short-term**: keep the gpsim-path xfails on
     `pb_cache_isolation` (whole-test marker) and `mixed_counters`
     (inline `pytest.xfail`) pointing at this finding.  Rust path
     is the canonical coverage going forward.

  2. **Mid-term (PF.4 phase 2)**: gpsim wire-chain infrastructure
     retires when `vendor/gpsim-0.32.1-xtc/` and the 6 wrapper
     modules are deleted (per `docs/PF4_PHASE2_PLAN.md`).  The
     misroute disappears with the harness; the xfails retire.

  3. **Long-term (out of scope for this branch)**: a fix on V1.71
     would extend the route byte semantics to distinguish BF1
     (PB1 reply) vs BF2 (PB2 reply), so the parser could route
     cache writes deterministically regardless of UART timing.
     This is NOT being scheduled here because the only test
     harness that has reproduced the misroute (gpsim wire-chain)
     is itself scheduled for retirement in PF.4 phase 2, AND the
     2026-05-04 HW retest didn't see the failure on the tested
     config.  But: real silicon CAN in principle hit the same
     overlap window if MAIN's burst-issue rate is slow enough
     relative to V1.71's cadence period and `RUNTIME_PENDING`
     skip-on-silent gate; if a future field bug surfaces with
     "PB2 cache shows PB1 data", the BF1/BF2 route-byte fix
     would be the canonical resolution.  Tracking that latent
     fragility as a candidate-only follow-up rather than an
     active defect.

## Status

Task #117 INVESTIGATED.  Finding: a real firmware-protocol
fragility (implicit query-reply ordering), not a gpsim simulator
defect per se.  The fragility is exposed by gpsim's slow PTY
UART; rust + the 2026-05-04 HW retest don't hit the overlap
window on the tested config.  The two xfails
(`pb_cache_isolation` whole-test and `mixed_counters` gpsim
inline) can retire when the wire-chain harness is deleted in
PF.4 phase 2 batch 9.  The latent firmware fragility is filed as
a candidate field-bug; only chase it if a real-silicon report
matches the pattern.
