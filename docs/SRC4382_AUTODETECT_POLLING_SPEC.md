# SRC4382 Auto Detect Polling Spec

Last updated: 2026-05-20
Status: V3.2 rev 0x6E simulator-green SRC4382 Auto Detect cadence candidate; latest hardware retest found rev 0x6D fixed digital inputs silent after leaving Auto Detect, and rev 0x6E adds explicit fixed-digital SRC route priming.  Structured hardware retest/soak evidence is still required before release closure.
Scope: MAIN V3.2+ SRC4382 Auto Detect cadence, source-detection behavior, I2C robustness, simulator tests, and hardware validation.

## Decision

The first SRC4382 Auto Detect cadence implementation replaced the legacy
`main_i2c_service_27f0` body.  It passed the simulator suite available at the
time, but the first audit found that it broke the route/TAS refresh contract.
A later write-shadow throttle also passed simulator checks, and an initial
hardware run appeared to produce bad audio on 2026-05-20.  That bad-audio
observation was a speaker-wiring false alarm.  The same hardware session then
found a real firmware issue: fixed digital inputs (`S/PDIF`, `USB Audio`, `AES`,
`Optical`) could go silent after Auto Detect because those menu items drive the
external mux route (`0/5/6/7`) without also re-priming the SRC4382 receiver
route.

The current candidate keeps the legacy `main_i2c_service_27f0` route/DSP
contract, modifies only the Auto Detect cadence inside that service, does not
reuse `ram_0x0BF` as a receiver-select shadow, forces route reconciliation on
explicit input commands, and writes the default SRC4382 receiver/transmitter pair
for fixed digital external-mux routes.  It is rebuilt into the canonical V3.2
HEX.  It is simulator-green, but it is not considered fully released until the
fixed-input/Auto-Detect hardware retest and soak evidence below are collected
and validated.

## Related Documents

- `docs/IMPL_SRC4382_AUTODETECT_POLLING_SPEC.md`: implementation plan and gates.
- `docs/SRC4382_USB_DIAGNOSTICS_SPEC.md`: read-only SRC4382 diagnostic endpoint draft.
- `docs/V32_MAIN_HANG_HARDENING_PLAN.md`: broader MAIN liveness and MSSP/I2C recovery.
- `docs/IMPL_V171_V32_BUG_LEDGER.md`: red-test-first bug ledger.
- `docs/HARDWARE_TEST.md`: live-rig validation runbook.
- `firmware/reference/src4382.md` / `firmware/reference/src4382.pdf`: SRC4382 reference.

## Non-Negotiable Audio Contract

The current MAIN code is not a simple SRC4382 polling loop.  It is part of the
audio routing and DSP refresh path.

The required contract is:

1. `main_i2c_service_27f0` polls SRC4382 status and computes the requested DLCP
   input route in `ram_0x093`.
2. `ram_0x0AB` is the last-applied route shadow.
3. When `ram_0x093 != ram_0x0AB`, the service sets `event_flags.bit1`.
4. `cmd_dispatch_gated` consumes `event_flags.bit1`.
5. The dispatch path writes the SRC4382 route pair and then refreshes the
   TAS3108 path, including TAS3108 coefficient `0x30`.
6. Only after that path runs is the route shadow coherent again.

The fixed route table is:

| DLCP route request | SRC4382 `0x0D` | SRC4382 `0x08` |
| ---: | ---: | ---: |
| `1` | `0x09` | `0x70` |
| `2` | `0x0A` | `0xB0` |
| `3` | `0x08` | `0x30` |
| `4` | `0x0B` | `0xF0` |

The CONTROL audio menu's displayed fixed digital choices are a second,
hardware-specific case.  In the default deployed routing profile
(`BF/05 == 3`), the front-panel items emit these `cmd 0x06` input bytes and
MAIN route requests:

| CONTROL menu item | `cmd 0x06` input byte | MAIN route request | SRC4382 `0x0D` | SRC4382 `0x08` |
| --- | ---: | ---: | ---: | ---: |
| `S/PDIF` | `0x05` | `1` | `0x09` | `0x70` |
| `USB Audio` | `0x06` | `2` | `0x0A` | `0xB0` |
| `AES` | `0x07` | `3` | `0x08` | `0x30` |
| `Optical` | `0x08` | `4` | `0x0B` | `0xF0` |

The legacy route requests `0/5/6/7` still exist for the stock external-mux
branches.  Those routes must restore the SRC4382 to the default
receiver/transmitter pair `0x0D=0x08`, `0x08=0x30`; otherwise Auto Detect can
leave the SRC parked on the wrong receiver after the user selects a fixed
source.  The regression suite must cover both surfaces: direct route priming
for `0/5/6/7` and the real CONTROL menu path for displayed `S/PDIF`.

Future code may reorganize how Auto Detect finds a route, but it must emit the
same `ram_0x093` / `event_flags.bit1` contract or an explicitly equivalent
replacement with tests that prove the same SRC4382 route pair and TAS3108
payload are produced.  Bypassing `cmd_dispatch_gated`, duplicating only part of
it, or updating SRC4382 without the downstream TAS refresh is a release blocker.

## Problem Statement

The stock-equivalent V3.2 Auto Detect path polls the SRC4382 far more often than
user-visible source detection requires.

Simulator-side counts against the stock-equivalent V3.2 firmware path:

| State | SRC4382 ACKed transmit bytes/s | Approx probes/s | Approx I2C transactions/s |
| --- | ---: | ---: | ---: |
| Auto Detect, no source detected | `912` | `152` | `304` |
| Auto Detect, source present | `1147` | `127` | `381` |

These are not exact hardware bus captures; they are firmware-path counts from
the Rust SRC4382 model.  They show that the current service repeatedly touches
SRC4382 registers at high cadence.  That increases MSSP/I2C exposure and can
contribute to UI stalls or fault counters, but it is not allowed to be fixed by
removing the audio-route side effects above.

The apparent source scan speed is only about 3 Hz in the no-source case:

```text
~152 low-level status probes/s
/ ~12 probes per candidate before advancing
/ 4 candidates
= ~3.2 full four-input scans/s
```

The optimization target is therefore lower bus load, not faster user-visible
source discovery.

## Current Firmware Candidate

Relevant V3.2 paths in the current cadence candidate:

- `periodic_service_loop` calls `main_i2c_service_27f0`.
- `main_i2c_service_27f0` gates on `active_flags.bit3`, increments `ram_0x0BB`,
  and runs the slower secondary-device path when `ram_0x0BB > 0x64`.
- In Auto Detect (`input_select == 0`), it computes
  `ram_0x0BE = ram_0x0B6 + 0x08`, preserving `0x0D.RXCLK=1` while changing
  `0x0D.RXMUX[1:0]`.
- It writes SRC4382 register `0x0D` once when a candidate is selected, sets
  `ram_0x0BA = 0x12` as the settle countdown, and skips additional SRC4382
  traffic until the countdown expires.
- When the countdown expires it reads `0x13`; if `0x13.RXCKR[1:0] == 0`, it
  clears the route request, advances the scan index, and starts the next
  candidate.
- When `0x13.RXCKR[1:0] != 0`, it maps the scan index to route requests
  `3/1/2/4`, reads `0x12` into the legacy `ram_0x0BF` status scratch, and
  reconciles `ram_0x093` / `ram_0x0AB` / `event_flags.bit1`.
- After source-present handling it sets `ram_0x0BA = 0x28` as the slow monitor
  countdown before the next `0x13`/`0x12` status check.
- Fixed-input handling clears both the scan index and the countdown, then uses
  the existing route request and `cmd_dispatch_gated` route/TAS refresh path.
- Explicit `cmd 0x06` input changes invalidate the route shadow and force the
  slow I2C service to run immediately, so selecting a fixed source cannot be
  skipped just because the previous route shadow already matched.
- Legacy external-mux routes `0/5/6/7` now write the default SRC4382
  route pair `0x0D=0x08`, `0x08=0x30` after the external mux/TAS handoff.
- Route application is reconciled through `ram_0x093`, `ram_0x0AB`, and
  `event_flags.bit1`; it is not merely a status poll.

Electrical/protocol baseline:

- V3.2 uses SRC4382 I2C write address `0xE2` and read address `0xE3`, matching
  DLCP straps A1=0, A0=1.
- V3.2 sets `SSPADD = 0x77` on a PIC18F2455-class MAIN.  The effective I2C bus
  is slow enough that reducing transaction count is useful even if the protocol
  timing itself is legal.
- The current issue is transaction rate and redundant work, not a proven
  SRC4382 datasheet timing violation.

## SRC4382 Semantics Used Here

- `0x0D` is Receiver Control 1.  Values `0x08..0x0B` mean `RXCLK=1` (`MCLK`
  reference) plus `RXMUX=RX1..RX4`.
- `0x13.RXCKR[1:0]` is the recovered-clock rate class.  `0b00` means clock rate
  not determined.  Current V3.2 uses `RXCKR != 0` as the source-present oracle.
- `0x14.UNLOCK` is the formal DIR AES3 decoder / PLL2 lock status.  It may be
  exposed through diagnostics or used as optional confirmation only after
  hardware validation; do not silently replace the current oracle with it.
- `0x12` reports non-PCM status and should remain gated behind source-present
  detection or a deliberately slow diagnostic snapshot.
- `0x08` participates in the selected route pair.  Any fixed-input or
  Auto-Detect route convergence must produce the table in the audio contract.

## Goals

1. Preserve the legacy SRC route and TAS3108 refresh contract.
2. Add tests that fail on the reverted/broken replacement service, not just tests
   that count current polling traffic.
3. Preserve real audio output: fixed-input and Auto Detect playback must be
   acoustically equivalent to the stock-equivalent V3.2 baseline.
4. Reduce steady-state SRC4382 I2C traffic by at least 10x while Auto Detect is
   active.
5. Preserve user-visible source-detection responsiveness.
6. Stop rewriting SRC4382 `0x0D` unless the candidate receiver changes or the
   route contract requires a fixed route update.
7. Keep volume, mute, standby/wake, preset A/B, fixed input selection, USB, and
   UART forwarding responsive while Auto Detect is active.
8. Improve observability so future `I`/`R` growth can be attributed to SRC4382
   traffic versus TAS3108/DSP traffic.

## Non-Goals

- No product-version fork; the target pair remains MAIN V3.2 plus CONTROL V1.71.
- No CONTROL UI change in this phase.
- No arbitrary SRC4382 write endpoint over USB.
- No attempt to infer IEEE float PCM; SRC4382 does not reliably expose that.
- No replacement of the `0x13.RXCKR != 0` source-present oracle without a
  separate hardware-validated change.
- No Timer0 or other time-base change unless tests prove it cannot disturb USB
  filename transactions, command dispatch, or existing timer users.

## Required Test Classes

### Class A: Audio-Path Safety Tests

These must pass on the current stock-equivalent V3.2 firmware and fail on the
bad replaced-service shape from the first attempt.

Required coverage:

- Static guard: `main_i2c_service_27f0` still contains the legacy route
  reconciliation behavior or an explicitly approved replacement.
- Runtime guard: setting `ram_0x093` and `event_flags.bit1` causes the expected
  SRC4382 route pair and TAS3108 coefficient `0x30` refresh.
- Release-flash guard: decoded LX521 A/B preset payloads are delivered exactly
  to both MAINs' TAS3108 models, including after restoring preset A.
- Negative/mutation guard: a polling-only replacement that omits
  `event_flags.bit1` or TAS refresh must fail at least one safety test.

Current tests:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v32_release_flash_sim.py
```

Current safety coverage includes a generated bad-firmware mutation that removes
the Auto Detect route-event `bsf event_flags, 1` and proves the guard fails
before TAS3108 coefficient `0x30` is refreshed.

### Class B: Cadence And Liveness Tests

The current cadence-budget tests are release gates for the simulator candidate.
They deliberately combine lower traffic assertions with route/TAS liveness and
user-action responsiveness so a polling-only or audio-breaking change cannot
pass by merely reducing I2C traffic.

Target tests:

| Test | Current release expectation | Purpose |
| --- | --- | --- |
| Auto Detect no-source traffic | `<= 150` ACKed transmit bytes/s; current observed `69`. | Proves the >10x reduction from the stock-equivalent baseline. |
| Auto Detect source-present traffic | `<= 160` ACKed transmit bytes/s; current observed `39`. | Proves source-present monitoring stays low-rate after convergence. |
| Source-present cadence mutation | Generated firmware that changes the `0x28` source-present monitor countdown to `0x01` must fail the cadence budget. | Pins the source-present traffic budget to a concrete high-traffic red case. |
| No-source non-PCM status gating | Do not read or latch `0x12` while `0x13.RXCKR=0`. | Prevents stale non-PCM status from influencing routing before a source exists. |
| Source-present non-PCM status latch | Read `0x12` and stage it in `ram_0x0BF` only after `0x13.RXCKR != 0`. | Pins `ram_0x0BF` as the legacy non-PCM/status scratch, not a receiver-select write shadow. |
| Source-loss debounce | One transient `0x13.RXCKR == 0` monitor sample must not clear the selected route; sustained loss must resume scanning within `1 s`. | Prevents Auto Detect route flapping on a single unstable SRC4382 status sample. |
| `0x0D` write cadence | Receiver-select values advance `0x08,0x09,0x0A,0x0B` with no adjacent duplicates. | Proves `0x0D` is not rewritten unless the candidate changes. |
| Worst-position source discovery | Green canary. | Source found within the `500 ms` target. |
| Slow-discovery mutation | Generated firmware that changes the candidate settle countdown to `0x24` must miss the `500 ms` discovery budget. | Pins the lower-traffic boundary so Auto Detect cannot pass by becoming too slow. |
| Explicit input preemption | Must remain responsive. | Fixed input converges promptly through the route/TAS path and Auto Detect does not overwrite it. |
| Manual fixed-digital route priming | External-mux route requests `0/5/6/7` must write `0x0D=0x08`, `0x08=0x30` and refresh TAS. | Prevents the external-mux branches from inheriting an unrelated Auto Detect receiver. |
| CONTROL S/PDIF menu path | Front-panel `S/PDIF` must emit `B0/06/05`; both MAINs must converge to route `1`, write `0x0D=0x09`, `0x08=0x70`, and refresh TAS after Auto Detect. | Prevents repeating the RCA S/PDIF manual-selection blind spot. |
| Fixed-input quiet mode | `0` ACKed SRC4382 bytes/s after fixed-input route convergence. | Proves the reduced Auto Detect scan is silent once a manual input is selected. |
| SRC4382 NACK/no-stall | Must remain responsive. | Fault increments diagnostics, retry traffic stays bounded, and a volume command still applies. |
| Mute/unmute responsiveness | Must remain responsive. | Mute and unmute parse under Auto Detect load and refresh TAS3108 coefficient `0x30`. |
| Standby/wake responsiveness | Must remain responsive. | Standby closes the active gate and wake reopens it while Auto Detect is active. |
| Preset responsiveness | Must remain responsive. | Preset select parses and completes while Auto Detect is active. |
| Long-run chain liveness | Must remain responsive. | V1.71 + two V3.2 MAINs stay responsive under source changes and commands. |

Current cadence tests:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v32_src4382_autodetect_polling.py
# 24 passed
```

The same file also includes a green responsiveness canary for worst-position
source discovery, no-source `0x12` gating, source-present `0x12` latching into
`ram_0x0BF`, source-loss debounce, explicit fixed-input preemption,
fixed-input quiet mode, mute/unmute, standby/wake, preset-select, SRC4382
NACK/no-stall behavior, and V1.71 + two-V3.2 chain liveness, plus generated
near-unthrottled receiver-select/source-present monitor mutations and an
overly slow candidate-settle mutation that must fail the cadence and discovery
budgets, so a future redesign cannot pass by only documenting the budgets or by
making Auto Detect too fast or too slow.

Current simulator coverage now includes source-loss debounce for the selected
Auto Detect route: one transient no-clock sample is ignored, while sustained
no-clock returns the service to scanning within the bounded window.

## Current Candidate Design

The current candidate is intentionally smaller than a new standalone Auto
Detect state machine.  It keeps the existing service, route mapping, route
event, and downstream TAS refresh behavior, and adds only two countdowns in the
Auto Detect branch:

Target cadence:

| Mode | Action | Cadence |
| --- | --- | --- |
| Fixed input | Route convergence through the legacy contract | prompt, one route event |
| Fixed input | SRC4382 health/status read | off by default, or `<= 1 Hz` for diagnostics |
| Auto Detect scan | Candidate dwell | `75-125 ms` |
| Auto Detect scan | Full four-input scan | `300-500 ms` |
| Auto Detect scan | `0x0D` write | once per candidate change |
| Auto Detect scan | `0x13.RXCKR` read | once per candidate after settle; optional confirm read |
| Source-present monitor | `0x13.RXCKR` read | `2-5 Hz` |
| Source-present monitor | `0x12` read | `1-2 Hz`, or only after `0x13.RXCKR != 0` |
| Fault backoff | Retry delay | `>= 250 ms`, optionally `1 s` after repeated faults |

2026-05-20 frequency revisit after the speaker-wiring retest:

| Candidate settle | Source-present monitor | No-source bytes/s | Source-present bytes/s | Worst-position detect |
| ---: | ---: | ---: | ---: | ---: |
| `0x06` | `0x08` | `181` | `159` | `142.5 ms` |
| `0x0C` | `0x18` | `99` | `63` | `250.0 ms` |
| `0x12` | `0x28` | `69` | `39` | `357.5 ms` |
| `0x18` | `0x40` | `51` | `27` | `465.0 ms` |
| `0x24` | `0x60` | `36` | `21` | missed `500 ms` target |

Current decision: keep `0x12`/`0x28` as the release candidate.  `0x0C` is
faster but falls short of the 10x no-source traffic-reduction target.  `0x18`
meets the 500 ms target in the simulator and is a viable low-frequency
follow-up, but the margin is too narrow to promote without a separate hardware
source-detection timing check.

The implemented no-source scan writes `0x0D`, waits `0x12` slow-service
cadence ticks, then reads `0x13`.  In the current simulator that yields roughly
`12` receiver-select writes and `11` status reads per firmware-visible second,
or `69` ACKed SRC4382 transmit bytes/s.  The source-present monitor uses
`0x28` slow-service ticks between status checks and currently measures `39`
ACKed SRC4382 transmit bytes/s after route convergence.

Fuller future state machine, if the small in-place candidate is not sufficient:

```text
0 = AD_DISABLED_FIXED_INPUT
1 = AD_SCAN_SET_CANDIDATE
2 = AD_SCAN_SETTLE
3 = AD_SCAN_READ_STATUS
4 = AD_SCAN_CONFIRM_PRESENT
5 = AD_SOURCE_PRESENT_MONITOR
6 = AD_FAULT_BACKOFF
```

Future implementation rules:

- Keep `cmd_dispatch_gated` route/DSP behavior unchanged.
- Perform at most one SRC4382 transaction per Auto Detect service call.
- Do not start Auto Detect work while preset apply, volume/mute DSP write,
  standby/wake, USB diagnostics, or explicit input handling is active.
- When Auto Detect finds a route, set the same route request and event contract
  as the legacy code.
- Do not read `0x12` during no-source scanning; read it on source-present route
  changes.
- On NACK or bounded MSSP timeout, enter backoff instead of immediate high-rate
  retry.
- Do not reuse `ram_0x0BF` as an Auto Detect write shadow; it is the legacy
  register `0x12` status scratch in the stock-equivalent path.
- Any timing source, including the existing slow-service cadence byte or Timer0,
  needs conflict tests and hardware acoustic validation before release.

## Diagnostics and Observability

Layer 5 `I` remains the aggregate I2C/MSSP fault counter and `R` remains the
aggregate recovery counter.  Do not change those meanings.

Future USB diagnostics may expose:

```text
ad_state
ad_candidate_idx
ad_selected_idx
ad_last_written_0d
ad_last_reg_12
ad_last_reg_13
ad_present_miss_count
src4382_poll_count
src4382_write_count
src4382_read_count
src4382_i2c_fault_count
src4382_recovery_count
ticks_since_last_success
```

LCD changes are out of scope for this spec.

## Simulator Requirements

Already implemented or required for the current guards:

- SRC4382 per-register read/write counters.
- SRC4382 address/data NACK injection.
- Chain/PyO3 helpers to seed and inspect MAIN-attached SRC4382 state.
- TAS3108 completed-write payload logging.
- Python facade access to the SRC4382/TAS3108 logs.

Focused model tests:

```bash
cargo test -p dlcp-sim src4382 --lib
cargo test -p dlcp-sim tas3108 --lib
```

The simulator must continue to test through running firmware.  Direct model
seeding is acceptable for status-register setup, but proof of behavior must come
from firmware-visible side effects.

## Hardware Validation

The simulator cannot prove the audio path is correct by itself.  Before another
cadence implementation becomes a release candidate, collect hardware evidence:

1. Fixed input audio sanity check:
   - Stock-equivalent V3.2 + V1.71.
   - Known source and preset.
   - Confirm low-band output on a correctly wired speaker path or with a
     repeatable measurement.
2. Candidate fixed input:
   - Same source/preset/volume.
   - Acceptance: every fixed digital input used by the operator (`S/PDIF`,
     `USB Audio`, `AES`, `Optical`) produces audio after leaving Auto Detect,
     and low-band output is equivalent to baseline within the agreed tolerance.
3. Auto Detect source-present:
   - Same acoustic check after Auto Detect selects the source.
4. User actions while playing:
   - Volume, mute, preset A/B, standby/wake, and explicit input remain responsive.
5. Long soak:
   - At least 30 minutes Auto Detect no-source and 1 hour fixed-input playback.
   - Acceptance: no UI stalls, concrete PB1/PB2 `I`/`R` before/after
     snapshots, and no unexplained `I`/`R` growth.
6. Optional SCL/SDA capture:
   - Verify reduced transaction bursts and no continuous 100+ Hz `0x0D` rewrite
     pattern.

## Acceptance Criteria

The SRC4382 Auto Detect polling work is complete only when:

- Class A audio-path safety tests pass on current V3.2 and fail on a broken
  polling-only replacement.
- The exact LX521 TAS3108 payload tests pass for both MAINs and both presets.
- A future cadence design has red tests that fail on the stock-equivalent
  high-traffic baseline and pass after the change.
- No-source Auto Detect SRC4382 traffic is materially lower than the current
  stock-equivalent baseline.
- Source-present Auto Detect SRC4382 traffic is materially lower than the
  current stock-equivalent baseline.
- Full four-input source discovery remains within `500 ms`.
- Explicit fixed-input selection converges promptly and is not overwritten by
  Auto Detect.
- Displayed fixed digital inputs converge through their matching SRC4382 route
  pair after Auto Detect and produce audio on hardware; the real front-panel
  S/PDIF path is explicitly covered.
- External-mux route requests restore the default SRC4382 route pair after Auto
  Detect.
- Volume/mute/preset/standby/wake remain responsive while Auto Detect scans.
- SRC4382 I2C faults increment diagnostics and do not stall MAIN.
- Full simulator gate passes.
- Hardware acoustic and soak gates pass, or the cadence change remains blocked.
- If manual hardware evidence is used instead of the live pytest wrapper, the
  completed evidence artifact passes `scripts/validate_src4382_manual_evidence.py`
  with explicit V1.71 CONTROL and two-V3.2-MAIN confirmation, current release
  SHA256 hashes, PB1/PB2 `I`/`R` before/after snapshots, and Volume-screen A/B
  badge observation recorded.

Latest focused simulator gate after rebuilding canonical V3.2 rev `0x6E`:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py
# 33 passed in 34.69s
```

Latest rev `0x6E` release/diagnostics checks:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_release_flash_sim.py \
  tests/sim/test_v32_flasher_sim_backend_hid.py::test_v32_runtime_eeprom_identity_matches_release_hex_without_seed \
  tests/sim/test_dlcp_main_flash.py::test_build_v32_release_bumps_runtime_eeprom_revision_marker
# 6 passed in 60.69s

.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_layer5_diag_chain.py::test_v171_v32_layer5_chain_lcd_renders_zero_idle \
  tests/sim/test_v171_v32_link_health_freshness.py
# 14 passed in 69.93s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_link_health_freshness.py::test_volume_screen_preset_badge_cell_is_not_refreshed_during_steady_idle
# 1 passed in 6.91s

cargo test -p dlcp-sim lcd --lib
# 8 passed
```

Latest full non-hardware gate after rebuilding canonical V3.2 rev `0x6E`:

```bash
.venv_ep0/bin/python -m pytest tests -n 16 -q
# 1081 passed, 18 skipped, 10 warnings in 393.86s

cargo test --workspace
# passed; snapshot_soak reported 6 passed in 1380.05s
```

The current manual hardware evidence artifact is not valid for closure:
`scripts/validate_src4382_manual_evidence.py` rejects it because, although the
artifact structure and release labels now match MAIN rev `0x6E`, the required
hardware/audio, fixed-digital-source, soak, PB1/PB2 `I`/`R`, and verdict fields
are still blank; the validator now also requires a yes/no A/B badge abnormal
refresh observation.  `BUG-SRC4382-AD-01` therefore remains blocked until a rev
`0x6E` hardware retest artifact validates.

Latest operator observation follow-up: a visibly pulsing A/B badge on the
Volume screen is not reproduced as firmware-origin steady-idle badge churn.
The simulator now exposes a per-DDRAM-cell LCD write counter, and the focused
test above proves CONTROL does not rewrite row 0 column 15 during steady idle.
If the badge still pulses on hardware after flashing the rev `0x6E`/`0x2D`
pair, triage it as repeated display-loop exits/re-entry or LCD electrical
behavior, not as SRC4382 polling traffic.
