# DLCP Chain Exploratory Stress Campaign Spec

Last updated: 2026-05-31
Scope: simulator-driven CONTROL + PB1/PB2 MAIN chain campaigns
Status: design spec for a future runner, not a deterministic pytest case list

## Purpose

This spec defines how to run exploratory DLCP chain simulations that combine
realistic user activity, injected faults, and varied boot/preset/HFD initial
conditions, then capture externally observable behavior well enough to decide
whether an abnormal outcome is a real firmware bug.

The goal is hidden-bug discovery.  A campaign must generate new combinations
and timings that are not merely hand-transcribed from existing tests.  Existing
tests may be used as evidence that a simulator primitive is valid, but the
campaign itself should explore state windows, interleavings, and fault timing
that are not already captured as fixed input/output examples.

## Non-Goals

- This is not a replacement for deterministic regression tests.  Any real bug
  found by this campaign should be minimized and converted into a focused test.
- This is not live hardware validation.  Hardware-only gates remain separate.
- This must not hard-code a small set of expected LCD/command transcripts and
  replay them as "exploration".
- This must not classify a one-tick transient as a firmware bug unless it
  violates an atomic protocol rule.

## Default Topology

Use the rust native chain simulator through
`dlcp_fw.sim.dlcp_sim_native.Chain`.

Default release pair:

- CONTROL: current `DLCP_Control_V1.73.hex`
- MAIN: current `DLCP_Firmware_V3.4.hex`
- Topology: 3-core ring, `CONTROL -> PB1 MAIN -> PB2 MAIN -> CONTROL`
- Factory: `Chain.from_v171_v32(control_hex_path=..., main_hex_path=...)`
  with explicit paths.  The factory name is historical; the path overrides
  select the actual release images.

The runner should also allow comparison campaigns against prior pairs such as
V1.71/V3.2 and stock V1.6b/V2.3, but the primary bug-hunt target is the
current recommended pair unless the operator overrides it.

## Runner Contract

The future command should be shaped like this:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_chain_exploratory.py \
  --duration 3h \
  --seed auto \
  --campaign all \
  --control-hex firmware/patched/releases/DLCP_Control_V1.73.hex \
  --main-hex firmware/patched/releases/DLCP_Firmware_V3.4.hex \
  --out-dir artifacts/sim/current/exploratory
```

Minimum options:

- `--duration`: wall-clock budget, for example `30m` or `3h`.
- `--seed`: deterministic seed.  `auto` records a generated seed.
- `--campaign`: weighted campaign set, for example `all`, `ui`, `src`,
  `preset-filename`, `diag`, `fault-recovery`, `upload`.
- `--control-hex`, `--main-hex`: explicit firmware images.
- `--out-dir`: artifact root.
- `--stop-after-high`: optional limit for high-severity incidents.
- `--replay`: replay a prior manifest/events pair instead of generating new
  stimuli.

Each run writes:

```text
artifacts/sim/current/exploratory/<timestamp>_<seed>/
├── manifest.json
├── events.jsonl
├── snapshots.jsonl
├── observations.jsonl
├── incidents.jsonl
├── summary.md
└── replay.json
```

The runner must be deterministic from `manifest.json` plus `events.jsonl`.

## Campaign Structure

A campaign is a sequence of sessions.  Each session should run long enough for
state machines to settle, but short enough that minimization is practical.
Suggested range: 30 simulated seconds to 5 simulated minutes per session, with
wall-clock time as the outer budget.

Each session has:

1. Initial condition generation.
2. Boot/connect warmup.
3. State-aware stimulus scheduling.
4. Continuous observation capture.
5. Oracle checks and incident classification.
6. Optional recovery period after an incident so secondary bugs can surface.

The scheduler should prefer unexplored combinations by maintaining coverage
bins such as:

- visible page or UI mode
- active preset slot
- source mode and SRC lock state
- standby/wake state
- link health state
- active fault family
- pending protocol transaction type
- PB target
- recent user action family

Two sessions are considered meaningfully different when they occupy different
coverage bins or hit the same bin with different timing relative to a firmware
state window.

## Initial Conditions

Initial conditions should be generated before normal runtime unless explicitly
testing a runtime upload or reset.  Prefer real firmware paths when possible;
direct RAM/EEPROM pokes are allowed only for initial state setup and must be
logged as such.

### Firmware and Boot State

Vary:

- firmware pair: current pair, prior pair, or mixed pair when explicitly
  selected
- reset source: POR, BOR, software reset, WDT-simulated reset, full-chain reset,
  PB-only reset
- startup offset: normal simultaneous boot, delayed PB1, delayed PB2, delayed
  CONTROL, reconnect after blackout
- CONTROL EEPROM: active preset, IR profile, volume/input/menu profile
- MAIN EEPROM: active preset marker, source shadow, preset filename/storage
  bytes, release revision identity

### Preset and HFD State

The runner should be able to seed or create HFD-like state for both PBs:

- preset A name blank, short, exactly one line, long enough to scroll, or
  contains unsupported bytes that should be sanitized by firmware
- preset B name using the same categories
- PB1/PB2 names matching or intentionally mismatched
- active preset filename RAM differs from EEPROM, representing an unpersisted
  runtime rename
- HFD upload interrupted before completion
- HFD upload followed by immediate preset flip, standby, source change, or
  reset
- one preset has valid coefficients while the other is blank or partially
  updated

Do not require fixed names in this spec.  The runner should use a generator
with named categories and log the actual generated strings and byte payloads.

### Audio/SRC State

Vary:

- Auto Detect, USB Audio, coax/RCA SPDIF, optical SPDIF, AES/EBU, or other
  explicit input mode supported by the firmware
- SRC4382 receiver status registers: locked, unlocked, source-lost, transient
  loss, non-PCM, candidate changes
- TAS3108/DSP state: normal, stale prior preset, muted, fault latched, recently
  recovered
- PB1-only source injection versus both PBs observing forwarded chain state

## Stimulus Families

Stimuli must be timestamped, target-specific, and labeled as either realistic
operator action, realistic host action, environmental fault, or synthetic
protocol corruption.

### User-Initiated Stimuli

Use real CONTROL-facing paths:

- decoded IR events: volume up/down, mute, explicit preset A/B, standby, wake,
  source up/down, menu/navigation commands
- front-panel key pins: RIGHT, LEFT, UP, DOWN, SELECT/OK, STBY where modeled
- menu navigation while parked on Volume, Preset, Setup, Input, PB1 Diag,
  PB2 Diag, and any reachable secondary page
- repeated or bounced key timing within realistic debounce windows
- volume sweeps while source state changes or DSP is busy
- standby/wake pairs during source loss, preset apply, filename fetch, or diag
  query

### Host/HFD Stimuli

Use firmware HID and chain command paths:

- HFD-like filename/config uploads
- preset switch commands
- memread/version/probe commands
- partial uploads followed by reconnect/reset
- rapid host commands during CONTROL foreground UI activity
- host commands while a MAIN protocol reply burst is already in progress

### Fault Stimuli

Use simulator fault primitives where available:

- SRC4382 address NACK and data NACK, per PB
- TAS3108 address NACK and data NACK, per PB
- MSSP START/STOP stuck bits
- I2C clock stretch and line-hold faults
- AN0 droop/restore and RA1 edge activity
- PB-only reset sources: POR, BOR, WDT-simulated, software reset, stack reset
- full-chain reset
- UART link drop by hop: `ctl_to_m0`, `m0_to_m1`, `m1_to_ctl`
- blackout/reconnect windows
- raw UART byte corruption, partial 3-byte frames, duplicated bytes, and stale
  old-MAIN echo frames
- source loss, lock flap, and non-PCM transitions in SRC4382 model registers

Synthetic byte/protocol faults must be separated in the log from realistic
operator or electrical stimuli.  A firmware bug found only through impossible
bytes is lower priority unless it can lock the UI or corrupt durable state.

## State-Window Targeting

The scheduler should not inject faults uniformly at random only.  It should
actively target known fragile windows, without reusing exact existing test
scripts:

- first boot full-sync and reconnect full-sync
- PB1/PB2 Diagnostics runtime query and reset-cause query
- Diagnostics page parked while user commands arrive
- Preset filename START/LEN/char/END transaction
- Preset filename incremental LCD repaint and scroll
- source-selection transition and SRC4382 Auto Detect candidate convergence
- TAS3108 preset apply and volume write
- standby close-gate, wake open-gate, and AN0 standby-sense path
- UART frame-gap timeout windows
- TX/RX ring near-full conditions
- MAIN reset while CONTROL has pending cache, identity, or filename state
- HFD upload commit boundary

The runner should discover these windows by observable state, recent command
history, or configured symbolic addresses.  It should not depend on a single
hardcoded PC address when a higher-level observable is available.

## Observation Capture

Capture enough outside-facing evidence to distinguish a firmware bug from a
test harness artifact.  Snapshot cadence should be adaptive: low-rate during
idle, high-rate around stimuli and incidents.

### LCD/UI

Record:

- `lcd_lines()`
- DDRAM write counts for row-0 and row-1 cells
- current display state index
- whether the visible row contains nonprintable/gibberish characters
- time since last LCD change
- visible page inferred from row text and display state

### Chain and UART

Record:

- CONTROL TX frames via `tx_frames()` and `ctl_tx_record_since_last_capture()`
- CONTROL RX accepted bytes via `ctl_rx_record_since_last_capture()`
- MAIN0 and MAIN1 TX/RX accepted bytes via per-main capture APIs
- full UART TX/RX histories around incidents
- `bridge_byte_stats()` deltas by hop
- frame alignment, partial-frame tails, repeated bursts, and link-drop periods
- approximate per-hop byte rate and high-water estimates

### SRC/SRS and I2C

Record per MAIN:

- SRC4382 register snapshots for receiver status and non-PCM/source-loss state
- SRC4382 read/write stats and write values
- TAS3108 stats and recent write payloads
- DSP register snapshots for volume, mute, preset-dependent coefficient entry
  points, and fault-relevant registers
- MSSP fault injection state and consumed fault counters

If any local tool uses the legacy name `SRS`, treat it as an alias for this
SRC4382/SRC observation class and normalize the artifact field to `src4382`.

### Firmware State

Record a small, stable state vector rather than dumping all RAM every tick:

- CONTROL connected/waiting flags
- display state and menu state
- volume, mute, active preset, input/source mode
- diag present/stale/lost bits and cached PB rows
- filename fetch state, active query id, pending age/deadline, cache length,
  render column, scroll state
- MAIN active flags, preset job state, delayed switch state
- MAIN diag counters and reset-cause flags
- relevant PC samples when liveness is suspect

Any direct RAM address used here must be named through a symbol/equate mapping
or documented in the runner source.

## Oracles and Bug Classifiers

An oracle is a general rule, not a fixed transcript.  The runner should emit an
incident when a rule is violated for longer than the rule's persistence window.

### Liveness

Potential bug if:

- CONTROL remains in WAITING after both MAINs are reachable and replying
- LCD does not change for a long window while the UI should be handling inputs
- PC samples stay in a tight loop that is not an expected idle loop
- filename/diag/identity/protocol pending state never expires or completes
- link traffic continues at high rate after the initiating condition is gone
- a ring remains saturated and later commands cannot get through

### UI Correctness

Potential bug if:

- LCD shows nonprintable or implausible characters outside intentionally
  generated filename bytes after sanitization
- old row content remains visible after a page transition, reset, or WAITING
  screen repaint
- Preset row shows a stale filename after slot change, failed query, link loss,
  or MAIN reset
- Volume, mute, active preset, standby, or source indicators contradict stable
  firmware state after a settle window
- PB1/PB2 Diagnostics shows `OK` while issue counters or reset issue flags
  require an issue layout
- PB identity/version is shown when the PB is stale/lost or marked issue-only

### Protocol Correctness

Potential bug if:

- chain frames become persistently misaligned
- BF command ranges collide, for example filename, identity, diagnostics, and
  fault frames are parsed as each other
- old/pre-feature echo frames can finalize a new feature transaction
- START/LEN/char/END style transactions complete with wrong id, wrong length,
  duplicate late LEN, missing END, or wrong target
- one PB's reply updates the other PB's cache or visible status
- command responses continue after timeout/reset should have discarded them

### Audio/SRC/DSP Correctness

Potential bug if:

- explicit source selection does not converge when the corresponding source is
  modeled as locked and valid
- Auto Detect thrashes source route writes after a stable source is present
- source-loss or non-PCM state latches permanently after the modeled condition
  clears, unless firmware policy explicitly requires a manual action
- PB2 selects a local back-panel source when the modeled chain contract says it
  should follow PB1-forwarded audio
- TAS3108/DSP writes do not converge after fault budgets are exhausted and
  cleared
- mute/volume/preset DSP state differs between PB1 and PB2 after a stable
  broadcast settle window

### Fault Surfacing and Recovery

Potential bug if:

- an injected realistic fault does not increment or surface the intended
  diagnostic counter after the appropriate settle window
- a cleared fault leaves the UI in issue state forever without a persistent
  underlying cause
- `PBn lost`, `PBn stale`, and `PBn OK` transitions contradict observed reply
  freshness
- reset-cause information is attributed to the wrong PB
- recovery paths create repeated counter growth without new fault stimulus

### Saturation and Backpressure

Potential bug if:

- CONTROL or MAIN emits partial protocol frames under TX-ring pressure
- frame senders do not abort atomically when the ring is full
- a legal burst starves user inputs or standby/wake beyond the documented
  responsiveness budget
- bridge byte rates remain elevated after all pending jobs should be complete
- RX overrun recovery fails to restore frame parsing

## Severity

Use these severities in `incidents.jsonl`:

- `HIGH`: liveness loss, unrecoverable audio/control loss, durable corruption,
  wrong PB target, or safety-relevant standby/wake failure.
- `MEDIUM`: recoverable but user-visible incorrect UI/protocol/audio behavior,
  incorrect diagnostics, repeated source/DSP convergence failure, or serious
  saturation.
- `LOW`: cosmetic LCD artifact, misleading transient, counter wording issue, or
  behavior only reachable through synthetic impossible bytes.
- `INFO`: unusual but currently explainable behavior worth tracking.

## Incident Record

Each incident line must contain:

```json
{
  "incident_id": "EXP-000123",
  "severity": "MEDIUM",
  "oracle": "protocol.filename.length",
  "seed": "0x1234abcd",
  "campaign": "preset-filename",
  "session_id": 17,
  "tick": 123456789,
  "symptom": "transaction finalized with missing character",
  "expected_rule": "received_len must equal expected_len before END is accepted",
  "observed": {"received_len": 11, "expected_len": 12},
  "last_events": ["event ids or compact summaries"],
  "snapshots": ["snapshot ids"],
  "artifacts": ["relative paths"],
  "replay_status": "not_minimized"
}
```

## Replay and Minimization

The runner must support two phases:

1. Replay the full session from manifest/events and reproduce the incident.
2. Minimize by dropping event chunks, shrinking delays, lowering fault counts,
   and reducing unrelated initial-condition variation.

A minimized bug is ready for a deterministic pytest when:

- it reproduces from one seed and one event list
- unrelated stimuli have been removed
- the oracle still fails
- the final event sequence is short enough to reason about
- the runner can export a pytest skeleton with the same firmware images and
  stimulus calls

## Bug vs Harness Artifact Checklist

Before calling an incident a firmware bug, check:

- Does replay reproduce it?
- Does the abnormal state persist beyond a documented settle window?
- Did the simulator inject an impossible state directly into firmware RAM?
- Is the observed behavior explained by an existing simulator fidelity gap?
- Does comparing PB1/PB2 or prior firmware isolate the regression?
- Are UART accepted bytes different from attempted wire bytes, indicating a
  modeled transport loss rather than parser logic?
- Did a synthetic corruption stimulus intentionally violate protocol framing?

If the answer is ambiguous, mark the incident `INFO` or `LOW` and include the
uncertainty.  Do not promote to `MEDIUM` or `HIGH` without replay evidence.

## Recommended 3-Hour Campaign Mix

For a future `/goal use spec and run chain for 3 hours` prompt, use a weighted
mix rather than a single long random walk:

- 20 percent: UI/menu/IR activity during normal playback.
- 15 percent: Preset filename and HFD upload churn.
- 15 percent: SRC/source-selection and Auto Detect under source loss/NACKs.
- 15 percent: standby/wake/reset/reconnect windows.
- 15 percent: Diagnostics parked pages under real event and fault traffic.
- 10 percent: TX/RX saturation, partial frames, and old/pre-feature echoes.
- 10 percent: comparison sessions against prior or mixed firmware pairs.

Rotate campaigns after each session or after an incident.  Continue after
recoverable incidents so independent bugs can surface, but stop if the same
high-severity signature repeats enough times to consume the run.

## Implementation Notes

- Use a deterministic PRNG and log every generated choice.
- Prefer real operator/host paths before direct register mutation.
- Treat direct RAM or EEPROM writes as setup only unless the campaign is
  explicitly testing synthetic corruption.
- Keep one canonical state sampler so incidents are comparable across campaigns.
- Use capture marks before scheduled stimuli to keep frame logs bounded.
- Normalize PB names as `PB1` for MAIN0 and `PB2` for MAIN1 in all artifacts.
- Store enough release identity to detect stale hex artifacts.
- A future CI gate should only check that the runner starts, replays, and writes
  valid artifacts.  The long exploratory campaign is operator-driven, not a
  normal CI job.
