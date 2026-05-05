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

## Root cause hypothesis

V1.71's diag protocol assumes replies arrive in query order (no
out-of-order delivery between PB1 and PB2):

  1. CONTROL sends `B1/0x21` (query PB1), sets `pending_pb = PB1`.
  2. MAIN0 starts the 7-frame BF/21..27 burst.
  3. CONTROL receives BF/21, writes to PB1 cache slot[0].
  4. ~1 sec later, cadence fires again: CONTROL sends `B2/0x21`
     (query PB2), sets `pending_pb = PB2`.
  5. MAIN1 has not yet started replying.
  6. MAIN0's BF/22 (continuation of the previous burst) arrives at
     CONTROL via the wire-chain forwarder.
  7. CONTROL parses BF/22 with `pending_pb = PB2`, writes to PB2
     cache slot[1].  **MISROUTE.**

The misroute is a FIRMWARE-PROTOCOL artifact: the BF frame route
byte is constant `0xBF`, so the parser cannot tell which PB the
reply is from -- it relies on the implicit "last query was for PB
N, so this reply must be from PB N" assumption.  That assumption
holds only if MAIN finishes its full 7-frame burst before CONTROL
fires the next cadence query.

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
the misroute (V1.71 + V3.2 chain produces correct PB1/PB2 cache
content under multiple LEFT/RIGHT navigation cycles).  This matches
the rust path's behavior and confirms the bug is gpsim-modeling
specific, not a firmware defect.

## Resolution path

  1. **Short-term**: keep the gpsim-path xfails on
     `pb_cache_isolation` (whole-test marker) and `mixed_counters`
     (inline `pytest.xfail`) pointing at this finding.  Rust path
     is the canonical coverage going forward.

  2. **Mid-term (PF.4 phase 2)**: gpsim wire-chain infrastructure
     retires when `vendor/gpsim-0.32.1-xtc/` and the 6 wrapper
     modules are deleted (per `docs/PF4_PHASE2_PLAN.md`).  The
     misroute disappears with the harness; the xfails retire.

  3. **Long-term (out of scope)**: a hypothetical fix on V1.71
     would extend the route byte semantics to distinguish BF1
     (PB1 reply) vs BF2 (PB2 reply), so the parser could route
     cache writes deterministically regardless of UART timing.
     This is NOT recommended -- real silicon hits the deterministic
     path naturally; the protocol change would only benefit a
     simulator that's already scheduled for retirement.

## Status

Marked task #117 INVESTIGATED.  Finding: not a firmware defect; not
a rust-side defect; gpsim-modeling artifact that is naturally
resolved by PF.4 phase 2 (gpsim retirement).  The two xfails
(`pb_cache_isolation` whole-test and `mixed_counters` gpsim inline)
should retire when the wire-chain harness is deleted in PF.4
phase 2 batch 9.
