# SRC4382 Auto Detect Stimulus Matrix Spec

Last updated: 2026-06-20
Status: Reviewed
Scope: simulator-driven Auto Detect comparison for stock CONTROL V1.6b + MAIN V2.3 versus current CONTROL V1.73 + MAIN V3.5, both MAIN roles, saved trace artifacts, deterministic regression tests, and optional LLM triage.

## Decision

Add a deterministic Auto Detect stimulus matrix that treats stock
CONTROL V1.6b + MAIN V2.3 as the behavioral reference, then runs the same
stimuli against the current CONTROL V1.73 + MAIN V3.5 pair.

The matrix must run stock first, save the exact stimulus schedule and observed
outputs, run current second with the same schedule, and emit both a deterministic
comparison verdict and a model-readable trace card for LLM judgement.

The user-requested 1-second source-change timeline is a continuous handoff
trace, not the only pass/fail oracle.  V3.4+ MAIN intentionally holds a
previously selected route during short `RXCKR=0`/`UNLOCK=1` gaps until its
hard-loss debounce expires.  The implementation must therefore keep two
contracts separate:

- `continuous_user_timeline`: exact short source gaps; records whether current
  switches like stock, holds the previous route within the hard-loss grace
  window, or wedges/selects a non-live route.
- `fresh_acquisition_matrix`: each digital source is acquired from a cleared or
  long-unlocked Auto Detect state; this is the deterministic gate proving
  S/PDIF, Optical, and USB Audio can be found on both MAINs.

The deterministic test gate must not depend on LLM output.  LLM judgement is
for operator triage of behavioral differences after the stock/current traces
exist.  Any confirmed bug found by the LLM must be minimized into a normal
pytest assertion before it can close a regression.

## User Requirements

- Simulate active input changes over time, including silence, S/PDIF, silence,
  S/PDIF plus Analog 1, silence, Optical, silence, and USB Audio.
- Run the original stock pair first and preserve its stimuli plus outputs.
- Run the current pair on the same stimuli.
- Compare both MAINs in the two-MAIN chain, not only a single MAIN.
- Use stock behavior as the reference while still allowing the current firmware
  to be stricter when that strictness is intentional and demonstrably safer.
- Use LLM judgement to decide whether current Auto Detect behavior looks healthy
  or regressed, but keep the release gate deterministic.

## Current Code Evidence

- `src/dlcp_fw/sim/dlcp_sim_native.py` exposes `Chain.from_v171_v32(...)`,
  which can build a three-core ring with arbitrary CONTROL and MAIN hex paths.
  Existing tests already use it with `STOCK_CONTROL_HEX_V16B` and
  `STOCK_MAIN_COMBINED_HEX` for stock, and with patched release paths for
  current chains.
- The same facade exposes `poke_main_src4382_reg`, `read_main_src4382_reg`,
  `read_main_src4382_stats`, and `read_main_src4382_write_values`, so tests can
  drive the SRC4382 register model while firmware still performs real MSSP
  reads/writes.
- `tests/sim/test_v171_v32_source_select_parity.py` proves the existing stock
  versus current manual-source route matrix pattern, including both PB roles.
- `tests/sim/test_v32_src4382_autodetect_polling.py` proves existing Auto Detect
  cadence, no-source/source-present handling, RX4 worst-position detection,
  fixed-input preemption, and dual-MAIN liveness for V3.2/V3.3 lineage.
- `tests/sim/test_v34_src4382_lock_hysteresis.py` and
  `tests/sim/test_v34_autodetect_loss_debounce.py` prove the V3.4+ lock
  robustness contract around `0x13.RXCKR` and `0x14.UNLOCK`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm` defines the current hard-loss debounce
  path; short silence is not equivalent to a cleared Auto Detect source.
- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md` defines the route/TAS contract:
  Auto Detect computes `ram_0x093`, route changes set `event_flags.bit1`, the
  dispatch path writes the SRC4382 route pair, and TAS3108 `0x30` is refreshed.
- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md` supersedes RXCKR-only route
  teardown for V3.4+ by using `0x14.UNLOCK` as formal lock evidence.

## Simulated Source Model

The simulator currently exposes SRC4382 registers, not physical named inputs.
The matrix must therefore add a small test-local or helper-owned source model:

1. Observe each MAIN's current SRC4382 receiver select register `0x0D`.
2. Decode `0x0D & 0x03` as `RX1`, `RX2`, `RX3`, or `RX4`.
3. After each bounded simulator step, update the selected receiver status
   before the next possible firmware status read.  The driver must record the
   candidate receiver, active receiver set, and status values it poked.
4. For the selected receiver, write firmware-visible status registers:
   - `0x13`: RXCKR recovered-clock class, zero when absent or in estimator hole.
   - `0x14`: `UNLOCK` bit, clear for formal lock and set for hard unlock.
   - `0x12`: non-PCM flag, zero for PCM unless a stimulus explicitly requests
     non-PCM.
5. Keep this model per MAIN so PB1 and PB2 may diverge if a future test needs
   one-sided source faults.

Receiver names for this matrix:

| Receiver | SRC4382 `0x0D` | DLCP route | Menu label |
| --- | ---: | ---: | --- |
| RX1 | `0x08` | `3` | AES |
| RX2 | `0x09` | `1` | S/PDIF |
| RX3 | `0x0A` | `2` | USB Audio |
| RX4 | `0x0B` | `4` | Optical |

Analog 1 is not an SRC4382 receiver.  The Analog 1 phase is retained in the
stimulus matrix as a competitor/noise condition, but it must not be faked as an
SRC4382 lock.  Unless future code evidence finds a real analog signal-presence
oracle in Auto Detect, `S/PDIF + Analog 1` means Auto Detect should behave the
same as S/PDIF for the SRC4382 path.

## Timing Constants

All canonical acceptance runs use `phase_scale=1.0`.  Scaled timing is allowed
only for explicitly marked unsafe/dev runs and cannot satisfy acceptance.

| Constant | Value | Purpose |
| --- | ---: | --- |
| `SIM_TICKS_PER_SECOND` | `48_000_000` | Rust simulator universal-clock second |
| `SHORT_PHASE_TICKS` | `1 * SIM_TICKS_PER_SECOND` | User-requested 1-second source/silence phases |
| `DRIVER_STEP_TICKS` | `250_000` | Maximum closed-loop driver step before status refresh |
| `LOCKED_SOURCE_CONVERGENCE_TICKS` | `1 * SIM_TICKS_PER_SECOND` | Budget for fresh locked-source acquisition |
| `SHORT_SILENCE_GRACE_TICKS` | `1 * SIM_TICKS_PER_SECOND` | Grace where V3.5 may hold previous route |
| `HARD_LOSS_CLEAR_TICKS` | `14 * SIM_TICKS_PER_SECOND` | Sustained unlock window expected to force re-scan/clear |

## Required Stimulus Schedules

### Continuous User Timeline

The exact user-requested continuous timeline is:

| Phase | Duration | Digital source state | Analog state | Expected reference behavior |
| --- | ---: | --- | --- | --- |
| `silence_a` | 1 s | none | none | no selected digital route |
| `spdif` | 1 s | RX2 locked PCM | none | route `1`, `0D=0x09`, `08=0x70` |
| `silence_b` | 1 s | none | none | stock/current may clear; V3.5 may hold prior route within hard-loss grace |
| `spdif_plus_analog1` | 1 s | RX2 locked PCM | Analog 1 present | route `1`; analog presence does not win SRC4382 Auto Detect |
| `silence_c` | 1 s | none | none | no WAITING/wedge; held previous route is classified, not silently passed |
| `optical` | 1 s | RX4 locked PCM | none | route `4` if prior route cleared; otherwise classify delayed handoff |
| `silence_d` | 1 s | none | none | no wrong route, no WAITING/wedge |
| `usb_audio` | 1 s | RX3 locked PCM | none | route `2` if prior route cleared; otherwise classify delayed handoff |

This schedule must preserve real time ordering.  The harness must not reset
MAIN scan state between phases unless the reset is explicitly recorded in
`stimuli.json` and excluded from the continuous handoff verdict.

### Fresh Acquisition Matrix

The deterministic acquisition gate runs each locked source from a cleared Auto
Detect state.  The cleared state may be produced by a fresh chain instance or by
a recorded sustained hard-unlock phase of at least `HARD_LOSS_CLEAR_TICKS`.

| Case | Initial condition | Digital source state | Expected current behavior |
| --- | --- | --- | --- |
| `fresh_spdif` | cleared Auto Detect | RX2 locked PCM | route `1`, `0D=0x09`, `08=0x70` |
| `fresh_optical` | cleared Auto Detect | RX4 locked PCM | route `4`, `0D=0x0B`, `08=0xF0` |
| `fresh_usb_audio` | cleared Auto Detect | RX3 locked PCM | route `2`, `0D=0x0A`, `08=0xB0` |
| `sustained_silence_clear` | selected route then no source | none for `HARD_LOSS_CLEAR_TICKS` | current clears/re-scans and does not stay permanently wedged |

Additional focused variants:

- `rxckr_hole_locked`: selected source has `RXCKR=0`, `UNLOCK=0`.
  Current V3.5 should hold route; stock may clear or flap.
- `rxckr_nonzero_unlocked`: candidate has `RXCKR != 0`, `UNLOCK=1`.
  Current V3.5 should reject acquisition; stock may commit.  This difference is
  expected and must be classified as intended robustness, not a regression.
- `two_digital_sources`: RX2 and RX4 locked at the same time.  The trace must
  record which route each firmware selects and the scan position that led to it.
  The deterministic gate should only fail if current selects a non-live route,
  wedges, or diverges between PB roles without a scripted one-sided source.

## Trace Output Contract

Each run must write artifacts under `SIM_ARTIFACTS_DIR`:

```text
artifacts/sim/current/src4382_autodetect_matrix/<timestamp-or-test-id>/
```

Required files:

```text
stimuli.json
manifest.json
stock_trace.jsonl
current_trace.jsonl
comparison.json
comparison.md
oracle_card.md
oracle_verdict.json        # optional, only when --model-cmd is used
oracle_error.json          # optional, only when --model-cmd fails
```

`manifest.json` must include:

- `format`: `src4382_autodetect_matrix`
- `schema_version`: `1`
- UTC generation timestamp and command argv
- simulator/backend version when available
- timebase constants, `phase_scale`, and exact integer tick schedule
- stock/current execution order
- combo firmware repo-relative paths plus SHA256 hashes for CONTROL and MAIN
- release identity/revision when available
- git dirty status summary
- `stimuli_sha256`, computed from canonical JSON serialization with sorted keys,
  fixed separators, and UTF-8 bytes
- completion status for each output artifact

Every trace row must include:

- combo id: `stock_v16b_v23` or `current_v173_v35`
- phase id and simulated elapsed ticks
- unit id: `PB1` or `PB2`
- active digital receivers and analog metadata for the phase
- selected scan candidate receiver and candidate index
- selected receiver register `0x0D`
- transmitter/bypass register `0x08`
- RXCKR register `0x13`
- lock register `0x14`
- non-PCM register `0x12`
- MAIN `input_select`, route request `0x093`, route shadow `0x0AB`,
  source-status byte `0x05F`, and event flags `0x07E`
- SRC4382 traffic counters and write values for `0x0D` and `0x08`
- source-driver status updates applied before firmware reads
- TAS3108 `0x30` latest payload presence and muted/non-muted classification
- CONTROL LCD lines and connected/waiting flags
- normalized verdict fields: `detected_route`, `expected_route`,
  `wrong_route`, `route_missing_after_budget`, `pb_divergence`, `waiting`,
  `muted_pcm`, `held_previous_within_hard_loss`,
  `handoff_delayed_by_hard_loss`, `intended_robustness`, and `notes`

`comparison.json` must pair stock/current outcomes by schedule, phase, and PB
unit.  Each paired outcome must classify the current result as one of:

- `match`
- `current_worse`
- `intended_robustness`
- `handoff_delayed_by_hard_loss`
- `needs_human`

## Deterministic Acceptance

The current combo passes the deterministic gate when:

1. The fresh-acquisition cases find S/PDIF, Optical, and USB Audio on both
   MAINs within `LOCKED_SOURCE_CONVERGENCE_TICKS`.
2. For fresh Optical, both MAINs reach route `4` and write SRC4382 `0D=0x0B`,
   `08=0xF0`.
3. For fresh S/PDIF, both MAINs reach route `1` and write SRC4382 `0D=0x09`,
   `08=0x70`.
4. For fresh USB Audio, both MAINs reach route `2` and write SRC4382 `0D=0x0A`,
   `08=0xB0`.
5. Continuous short-silence phases do not wedge, enter `WAITING`, mute locked
   PCM, or select a receiver that is neither live nor the previous route inside
   the hard-loss grace window.
6. A delayed continuous handoff caused by V3.5 hard-loss hold is explicitly
   classified as `handoff_delayed_by_hard_loss`; it is not counted as a fresh
   acquisition success.
7. The sustained hard-loss case clears/re-scans instead of holding a dead route
   indefinitely.
8. PB1 and PB2 do not diverge when the scripted source state is identical.
9. CONTROL remains connected and does not enter `WAITING`.
10. PCM phases are not muted by non-PCM logic.
11. Current behavior is not worse than stock for the same stimulus unless the
   difference is explicitly explained by the V3.4+ `UNLOCK` robustness or
   hard-loss debounce contract.

## LLM Judgement Contract

The LLM input must be `oracle_card.md`, not raw unbounded logs.  The card must
be compact, bounded, and redacted:

- no absolute home-directory paths such as `/Users/...`
- no HID serial tokens, environment values, or raw JSONL dumps
- repo-relative artifact paths only
- maximum card size recorded in `manifest.json`

The card must summarize:

- stock phase outcomes
- current phase outcomes
- deterministic comparison flags
- known acceptable divergences, especially current rejecting
  `RXCKR != 0` with `UNLOCK=1`
- repo-relative artifact paths for audit

The LLM must return JSON with:

```json
{
  "overall": "pass|regression|needs_human",
  "confidence": 0.0,
  "findings": [
    {
      "severity": "high|medium|low",
      "phase": "string",
      "unit": "PB1|PB2|both",
      "issue": "string",
      "evidence": "string",
      "required_followup": "string"
    }
  ]
}
```

The implementation may reuse the JSON extraction pattern from
`scripts/exploratory_oracle_run.py`, but the matrix runner must invoke any
model command with `subprocess.run(..., shell=False, timeout=...)` and pass only
stdin/stdout.  The prompt must forbid file writes, tool actions, network
actions, and repo mutation.  A missing or failing LLM invocation must not make
deterministic pytest fail unless the test explicitly targets the oracle wrapper.
Operators must not pass secrets in `--model-cmd`; command argv is recorded for
reproducibility.

## Non-Goals

- No firmware change in this work unit.
- No live hardware flashing or hardware acoustic validation.
- No full analog-input signal detector model.
- No replacement of existing Auto Detect tests.
- No checked-in golden trace artifacts unless a future maintainer explicitly
  chooses to version a minimized fixture.
- No subjective LLM-only release gate.

## Required Test Coverage

- Unit tests for receiver/status model behavior.
- A focused deterministic pytest that runs stock first, current second, and
  verifies the baseline schedule across both MAINs.
- A fresh-acquisition test proving current detects S/PDIF, Optical, and USB
  Audio from a cleared Auto Detect state.
- A continuous user-timeline test proving short-silence handoff behavior is
  classified rather than hidden.
- A variant test for `RXCKR != 0` plus `UNLOCK=1` proving current rejection is
  accepted when stock commits.
- A variant test for locked RXCKR holes proving current holds route.
- A sustained hard-loss test proving current eventually clears/re-scans.
- A `two_digital_sources` test that records scan position and fails only on
  non-live route, wedge, or unscripted PB divergence.
- Tests for manifest, trace schema, comparison schema, card redaction, and
  artifact creation in a temporary output directory.
- A forced Optical failure test for PB1 and PB2 proving deterministic failure
  occurs before model invocation.
- A no-network/no-model test for oracle-card generation.

## Operator Commands

Focused implementation gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_src4382_autodetect_stimulus_matrix.py
```

Adjacent SRC gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py
```

Manual artifact generation:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_src4382_autodetect_matrix.py
```

Optional LLM judgement:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/sim_src4382_autodetect_matrix.py \
  --model-cmd '<trusted-read-only-model-command>' \
  --model-timeout 120
```

## Acceptance Criteria

- The new SPEC and IMPL are reviewed with no unresolved High or Medium findings.
- The implementation adds deterministic tests and a trace-producing runner.
- The runner writes stock and current traces from the same stimulus schedule.
- The deterministic comparison detects Optical Auto Detect failures on current
  V1.73 + V3.5 if they occur in simulation.
- The LLM card can be generated without invoking a model, and model invocation
  remains optional.
- No firmware bytes, release hex files, or hardware state are changed by this
  work unit.
