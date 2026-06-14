# DLCP Intermittent-Bug Taxonomy (oracle reference)

Last updated: 2026-06-09
Scope: reference rubric for the agent semantic-oracle pass over
`scripts/sim_chain_exploratory.py` session cards.

This file lists the *failure-mode patterns* this firmware has historically been
prone to, distilled from the regression-test suite and the analysis docs. It is
a pattern catalog for judging exploratory stimulus→response traces — NOT a claim
about which versions currently carry which defect. When a card shows behavior
that rhymes with one of these patterns, that is a candidate to flag; the
adversarial-verify pass then decides whether it is a real firmware bug on the
*current* release pair or a harness artifact.

Pair under test (primary): CONTROL `V1.73` + MAIN `V3.4`.
Topology: 3-core ring `CONTROL → PB1(MAIN0) → PB2(MAIN1) → CONTROL`.

## Class 1 — Cross-unit preset / state desync
Two chained MAINs end on different active presets (or one stuck mid-apply)
after a broadcast preset request and a settle window.
- Signature in cards: `PB1_preset != PB2_preset` (both gate=1) persisting to the
  final observation; `PBn_job` (preset_job_state) non-zero at session end; LCD /
  `ctl_presetB` showing one preset while a MAIN shows the other.
- Trigger families: rapid IR `preset_a`/`preset_b` reversal during the apply
  window; preset flip interleaved with mute, standby, source change, or reset;
  preset request during an in-flight I2C transaction.
- Watch: a transient `PB1!=PB2` *during* apply is EXPECTED (one applies before
  the other). Only a mismatch surviving the settle window is suspicious.

## Class 2 — UI vs MAIN disagreement
CONTROL's visible state (LCD row, `ctl_presetB`, mute, standby, input
indicator) contradicts the stable MAIN state after settle.
- Signature: `ctl_presetB != PB1_preset` persisting; LCD shows `Volume`/`Preset`
  while MAIN gate/preset disagree; explicit IR standby/wake changes MAIN gate but
  not the CONTROL screen (or vice-versa).
- Trigger families: explicit IR standby/wake endpoints; preset via IR vs via
  chain frame; host command + UI action interleaving.

## Class 3 — Standby / wake gate failures
After a wake, a MAIN stays deaf (gate closed) to volume/mute/preset; or standby
does not actually close the gate; or a duplicate standby clears a pending
shutdown latch so wake is not recognized.
- Signature: `PBn_gate=0` after a wake stimulus and subsequent commands produce
  no MAIN state change; gate disagreement `PB1_gate != PB2_gate` persisting;
  command frames sent but MAIN state frozen.
- Trigger families: standby↔wake pairs during source loss / preset apply /
  filename fetch / blackout reconnect; duplicated standby frames; AN0 droop.

## Class 4 — LCD display glitches
Stale row content after a page/standby/reset transition; wrong/blank preset
filename row; non-printable characters outside intentionally-injected filename
bytes; a row that never repaints.
- Signature: LCD row unchanged across many observations while the page should
  have repainted; row-0/row-1 mismatch with `disp_state`; gibberish in LCD that
  is not explained by an injected `bad\x01name`-style slot.
- Trigger families: preset filename START/LEN/char/END transaction; scroll;
  reconnect/WAITING repaint; MAIN reset while CONTROL holds cached filename.

## Class 5 — Mute / volume leak through automated refresh
Audio returns briefly while muted because an automated refresh (input/route
refresh, wake/reapply, SRC4382 Auto Detect) writes a non-zero DSP volume
coefficient without honoring the mute flag.
- Signature: `ctl_mute=1` (or a mute stimulus) yet large `PBn_tas_ack` write
  bursts to volume/coefficient subaddresses after the mute settles; mute state
  flapping; preset/input refresh clearing a mute indicator.
- Trigger families: mute then input/source refresh, full-sync, standby/wake, or
  preset flip; Auto Detect candidate change while muted.

## Class 6 — IR decode timing / lost commands
An IR command produces no state change (lost), or is processed twice; bursts of
IR during serial/foreground load drop commands.
- Signature: an `IR:*` stimulus with no corresponding state delta where one is
  expected (e.g. `IR:volume_up` and `vol` unchanged, `IR:preset_b` and no
  preset/job movement, `IR:standby` and no gate change); or a single IR press
  causing a double increment.
- Trigger families: IR while a chain reply burst is in flight; rapid repeats;
  IR while parked on Diagnostics page.

## Class 7 — Liveness / unbounded waits
CONTROL stuck in WAITING though both MAINs reply; a pending transaction
(filename/identity/diag) never completes or expires; link traffic stays high
after the initiating condition clears; a ring stays saturated and later commands
cannot get through.
- Signature: `waiting=1 & connected=1` persisting; `fname` pending flags set
  with no completion; `lcd_idle_streak` long while inputs are arriving; bridge
  byte deltas staying high after jobs should be done; commands after saturation
  produce no MAIN delta.
- Trigger families: blackout/reconnect; TX/RX ring near-full; reset while
  CONTROL has pending cache/identity/filename.

## Class 8 — Fault surfacing / recovery
An injected realistic fault does not increment the intended diag counter; a
cleared fault leaves the UI in issue state forever; reset-cause attributed to
the wrong PB; recovery path grows counters without new stimulus; `PBn OK` shown
while issue counters require an issue layout.
- Signature: SRC4382/TAS3108 NACK or MSSP-stuck injected but `PBn_diag`
  unchanged after settle; diag counter saturates (0x0F) and never recovers;
  Diagnostics page `OK` contradicting non-zero counters; reset flag on the wrong
  unit.
- Trigger families: per-PB SRC/TAS NACK, MSSP START/STOP stuck, line hold, AN0
  droop, PB-only vs full-chain reset, while parked on PB1/PB2 Diagnostics.

## Class 9 — Protocol / chain framing
Chain frames become misaligned; BF command ranges collide (filename / identity /
diagnostics / fault parsed as each other); an old pre-feature echo frame
finalizes a new-feature transaction; START/LEN/char/END completes with wrong id,
wrong length, missing END, or wrong target; one PB's reply updates the other PB's
cache; responses continue after a timeout/reset should have discarded them.
- Signature: filename cache marked valid with `len != explen`; identity/diag
  fields landing in the wrong cache; PB2 status reflecting PB1's reply; frame
  tails showing partial/duplicated triplets parsed as commands.
- Trigger families: synthetic raw bytes / partial frames / duplicated bytes /
  stale echo (lower priority unless durable); overlapping real transactions.

## Class 10 — Live audio on wrong DSP coefficient image
A MAIN reports a settled healthy preset state and restores live audio, but the
actual TAS3108 preset coefficient image does not match the clean image for that
reported preset.
- Signature: `PBn_job=0`, gate open, effective mute clear, SRC4382 reports a
  live PCM source (`RXCKR[1:0] != 0`, non-PCM clear), latest TAS `0x30`
  non-zero, no DSP/ACK fault flags, LCD/CONTROL preset agrees with the MAIN,
  yet the MAIN's TAS `0x37..0x90` image differs from the golden image for the
  reported preset.  This includes partial images such as a missing TAS burst
  with all status indicators healthy.
- Trigger families: A/B preset reversal during the async APPLY window, especially
  B->A or A->B when the second request lands at a narrow PB2 APPLY phase; SRC4382
  RXCKR/lock-estimator churn while Auto Detect is active; preset flip interleaved
  with volume, route, standby/wake, or filename traffic.
- Severity discipline: this is `HIGH` whenever live audio is restored on the
  wrong image.  Do not down-rank it because the phase aligner is SRC RXCKR churn
  or another realistic environmental timing perturbation.

## Severity & artifact discipline
Use `docs/SIM_CHAIN_EXPLORATORY_STRESS_SPEC.md` §Severity and
§"Bug vs Harness Artifact Checklist". In particular, before promoting a finding:
real firmware bugs must persist beyond a documented settle window, must not be
caused by the harness poking impossible state directly into RAM, must not be a
known simulator-fidelity gap, and synthetic-byte-only findings are LOW unless
they durably lock the UI/audio or corrupt persistent state.
