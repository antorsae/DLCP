# Connected-WAITING Root Cause: Stock Open-Loop Banner Delays (2026-06-10)

Scope: CONTROL `V1.73` (`src/dlcp_fw/asm/dlcp_control_v173.asm`) + MAIN `V3.4`,
post-exploratory-round-1 fixes (`docs/IMPL_V34_V173_EXPLORATORY_BUGS.md`).
Status: **implemented 2026-06-10** (see "Round-2 implementation" at the end):
both CONTROL banner delays deleted, MAIN parallel two-MAIN wake added,
reconnect exit hardened to require a real poll answer. Wake-to-responsive:
250M ticks -> 126M ticks against a 160M-tick red-first bound
(`tests/sim/test_v173_wake_responsiveness.py`). The deeper async-reapply
(chunked `adc_boot_gate` apply) remains a designed follow-up — see the
corrected architecture notes below.

## Symptom under investigation

The 2026-06-09 post-fix exploratory re-run
(`artifacts/sim/current/exploratory/20260609_223720_goal_codex_postfix/final_report.md`)
kept reporting "WAITING while connected" (586 observations / 63 sessions; both
MAIN gates up in 350 of them), with IR/host intents dead during the window —
e.g. session 21: `Waiting for DLCP` for 9+ observations spanning ~15 s of sim
time after a standby→wake, `IR:power` and host frames having no effect, the
oracle confirming session 54 as HIGH-severity liveness.

## Method

Instrumented deterministic replay of session 21 (the cleanest `ui`-campaign
case): reconstruct the session per `scripts/sim_chain_exploratory.py`'s
`replay()` flow, drive the recorded stimuli, replace the wake `press("UP")`
with a manual pin drive (`set_control_pin("C", 0, ...)`), and sample every 2M
ticks: `current_ctl_pc()` histograms, `v173_reconnect_fresh_status_mask`
(0x0AA), `control_flags` conn bit, `is_waiting()`, both MAINs' `RCSTA.CREN`,
MAIN gates, the LCD, and CONTROL TX/RX byte streams.

## Evidence

Through the entire stuck window (>140M ticks observed):

- CONTROL TX after the single wake broadcast (`B0/03/01`, 3 bytes): **zero
  bytes — no `B1/04` polls are ever emitted**, so CONTROL is *not* in the
  reconnect loop.
- `v173_reconnect_fresh_status_mask` stays at its stale pre-wake value (0x03):
  the reconnect entry's `clrf` never ran — confirming the loop was never
  entered.
- `conn=1` the whole time: the wake path sets `control_flags.bit1` at the top
  (`asm:6651`) and clears it only at loop entry (`asm:6668`) — the foreground
  is parked *between* those two instructions.
- PC histogram (300 samples): 99% at `0x01E2/0x01E4` — the inner spin of the
  blocking 16-bit delay (`delay_short` / `control_core_service_01BE` /
  `control_core_service_01D8`).
- The delay counter cells are live: `0x00F:0x00E` decremented `0x10E8 →
  0x0FEE` across 12M ticks ≈ **44.6k ticks (2.79 ms) per unit** — i.e. the
  `delay_short` header's "50 µs per unit" calibration comment is ~56× off for
  this nested-argument call shape (`0x00D=0x03`, inner reload `0x03E5`).

## Root cause

The stock V1.6b WAITING entries begin with **open-loop blocking banner
delays**, executed after painting `Waiting for DLCP` and before entering the
(closed-loop) WAITING loops. All `control_core_service_01BE` call sites in
V1.73, with measured durations at 2.79 ms/unit:

| Site (v173 asm) | Count | Duration | Context |
| --- | ---: | ---: | --- |
| `:6330-6333` | 0x012C = 300 | ~0.8 s | boot splash hold |
| `:6376-6379` | 0x01F4 = 500 | ~1.4 s | release banner hold |
| `:6399-6402` | 0x03E8 = 1000 | ~2.8 s | release banner row-2 hold |
| `:6420-6423` | 0x0FA0 = 4000 | **~11.2 s** | cold-boot `Waiting for DLCP` → cold WAITING loop |
| `:6734-6737` | 0x1388 = 5000 | **~13.9 s** | wake-path `Waiting for DLCP` → reconnect loop |

(The cold loop's auto-label `flow_ccs_0FA0_118C` literally encodes the 0x0FA0
argument.)

During these delays the foreground is completely dead: no status polls, no RX
parsing (the 47-byte RX ring overflows under chain traffic), no button scan,
no IR dispatch/re-arm, LCD frozen on the banner. The wake-path delay also runs
with `bit1` already set — which is exactly the mechanical "connected +
WAITING" signature the exploratory scanner counts, and it makes every
standby→wake contribute ~14 s of connected-WAITING per session.

Timeline reconciliation for session 21 (all consistent with 2.79 ms/unit):
banner painted ~tick 460M (during the press hold) → delay expiry projected
~683M → original corpus shows WAITING still at obs#12 (706M, post extra
stimuli settles) and cleared before 806M. The `button:UP` at ev1388 did not
clear it — the delay simply expired.

## Why the round-1 BUG-2 fix is working as designed

Once the delay expires and the reconnect loop is finally entered, the trace
shows the fixed machinery doing exactly what it should: mask cleared at entry,
`B1/04` polls go out, both mask bits set on the first answered round-trip
(`BF/05` + `BF/03/01`), loop exits within ~2M ticks, Volume screen restored.
The loop residence is milliseconds; the *banner delay* is the user-visible
window.

Concurrently, the MAINs are deaf for the first ~6-8 s of the window
(`RCSTA.CREN=0` during the wake DSP-reapply — the same ~8-10 s full
table-apply measured during BUG-5 work). The 14 s CONTROL-side delay fully
masks it today. The delays were presumably the stock open-loop allowance for
exactly that MAIN re-init time — made redundant by the V1.62b reconnect loop
and now *strictly worse* than the V1.73 evidence-driven exit.

Reattribution of two report findings:

- "IR:power / host intents dropped during connected WAITING" (sessions
  20/21/69): the intents die inside the blocking delay (foreground dead), not
  in the round-1 `v173_waiting_ir_service` discard. The report's "dispatch or
  queue" recommendation largely reduces to removing the delay.
- Oracle-confirmed s0054 (HIGH liveness): a `standby-reset` session — its
  cards were additionally scrambled by the now-fixed observation-clock rewind
  (`tests/sim/test_sim_reset_clock_monotonic.py`), so treat its specifics as
  unreliable; the underlying WAITING-residence mechanism is the same banner
  delay.

## Proposed fix (round 2 — not yet implemented)

Replace the two WAITING-entry open-loop delays with the loops' own
closed-loop waits:

1. Wake path (`:6734-6737`): drop the 0x1388 delay to a short LCD-settle (or
   remove it) and let the reconnect loop + fresh-status mask own the wait. The
   loop already polls, parses, re-arms IR, and scans the operator-recovery
   buttons every ~10 ms — turning ~14 s of dead UI into a live WAITING bounded
   only by MAIN re-init (~8 s), with prompt exit on first evidence.
2. Cold path (`:6420-6423`): same treatment with the 0x0FA0 delay; the cold
   sentinel handshake provides the closed-loop wait.
3. Optional deeper item: shorten the MAIN deaf window itself by chunking the
   wake reapply (as the V3.2 async preset job already does for preset
   switches) so MAIN answers polls during re-init.

Expected effect on the exploratory signal: the connected-WAITING class
(586 obs / 63 sessions) collapses to the MAIN-reapply-bounded window with live
IR/buttons, and the dropped-intent examples disappear.

## Repro / verification commands

```bash
# Instrumented replay used for this analysis (probe scripts):
#   /tmp/probe_s21.py, /tmp/probe_s21b.py  (session-21 reconstruction + sampling)
# Raw corpus replay:
RUN_DIR=artifacts/sim/current/exploratory/20260609_223720_goal_codex_postfix/20260609_223720_eb5ef79d1abba467
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py --replay "$RUN_DIR" --session-id 21
```

Related round-1 artifacts: `docs/IMPL_V34_V173_EXPLORATORY_BUGS.md` (BUG-2 fix
this analysis vindicates), `tests/sim/test_sim_reset_clock_monotonic.py` (the
observation-clock fix that de-confounds the reset-storm sessions).

## Round-2 implementation (2026-06-10)

Red-first test: `tests/sim/test_v173_wake_responsiveness.py` —
`test_v173_v34_wake_to_responsive_under_bound` (boots the native V1.73+V3.4
chain from source, standby->wake, asserts wake-to-responsive ≤ 160M ticks and
that the first IR key after recovery works) plus a structural pin that the two
WAITING entries never re-grow an open-loop `01BE` banner delay. Pre-fix red:
**250,000,000 ticks**.

Implemented changes:

1. **CONTROL: both WAITING-entry banner delays deleted** (the 0x0FA0 cold
   delay and the 0x1388 wake delay). The loops own the wait. Measured effect
   alone: 250M -> 232M ticks — which exposed the real dominant term:
2. **The two MAINs woke SEQUENTIALLY.** Fine-grained probing of the fixed
   build showed MAIN0 deaf (`adc_boot_gate`, CREN=0) for ~116M ticks, and
   MAIN1 only *starting* its own identical deaf gate afterwards — MAIN0's
   UART quiesce eats the forwarded wake, so MAIN1 only hears the Bug #45 H2
   re-emit at MAIN0's gate *exit*. Ring forwarding through deaf MAIN1 also
   blackholes MAIN0's poll answers. Total ≈ 2 gates ≈ 232M ticks.
3. **MAIN: parallel two-MAIN wake.** `adc_boot_gate` now re-broadcasts
   `B0/03/01` downstream at gate **entry**, before `uart_quiesce_for_wake`
   (new shared `wake_rebroadcast_downstream` helper; the exit-time H2 re-emit
   stays as backstop, now via the same helper). Both MAINs gate concurrently;
   a duplicate wake is consumed idempotently by an awake MAIN. The no-pop
   bring-up ordering (zero-coeff -> table apply -> amp enable) is untouched.
4. **CONTROL: reconnect exit hardened to bit0-only.** With the wake echo now
   reliably forwarded *before* the deaf windows, exiting on mask bit1 would
   resume the display against a still-deaf chain; the exit now requires a
   real `BF/05` poll answer (bit0), bit1 stays as telemetry.

Result: wake-to-responsive **126M ticks** (one gate + one poll round-trip),
21% under the bound; the first post-wake IR key works. Canonical releases:
MAIN `V3.4 rev 0x81`, CONTROL `V1.73 rev 0x42 build 20260610`. MAIN listing
margins after the +2-word helper net: `byte_margin=134` /
`free_object_words=67` (floors 128/64 hold).

Incidental calibration finding (future cleanup, not changed here): the
`delay_short` header claims ~50 µs/unit but the measured cost is ~2.79 ms/unit
(sim ticks), so the WAITING loops' `delay_short(0xC8)` iterates every ~560 ms
(not ~10 ms) and the operator-recovery grace window arms far later than its
"~10 s" comment suggests. Behavior predates this work and all suites pass
against it; recalibrating is a separate, firmware-wide audit.

## Remaining follow-up (designed, not implemented)

Chunking the MAIN wake apply itself (the ~116M-tick deaf gate) must preserve
`adc_boot_gate`'s acoustic ordering: the amp enable (`LATB.3`) may only rise
after the coefficient table is fully applied. An async conversion therefore
has to defer the amp enable and the post-apply service calls into the job's
COMMIT (the V3.2 async preset-job machinery is the template), and exempt the
reapply job from the service's standby/reconnect cancels. That is a
self-contained designed effort gated on the no-pop validation runbook
(`docs/NO_POP_FIRMWARE_FLASH.md`, `docs/HARDWARE_TEST.md` §re-flash pop
monitoring) — not a tack-on. With it, wake-to-responsive drops from ~126M
ticks to roughly the rail-settle + one poll round-trip.
