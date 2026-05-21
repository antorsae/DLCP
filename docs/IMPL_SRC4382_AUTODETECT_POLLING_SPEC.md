# SRC4382 Auto Detect Polling - Implementation Plan

Date: 2026-05-20
Status: V3.2 rev 0x6E simulator-green SRC4382 Auto Detect cadence candidate; rev 0x6D hardware retest exposed fixed digital source silence after Auto Detect, and rev 0x6E fixes that route-priming path.  Structured hardware retest/soak evidence is still required before release closure.
Parent spec: `docs/SRC4382_AUTODETECT_POLLING_SPEC.md`
Target release pair: canonical MAIN `V3.2` plus CONTROL `V1.71`
Register reference: `firmware/reference/src4382.md` / `firmware/reference/src4382.pdf`

## Goal

Safely resume the SRC4382 Auto Detect polling work while preserving the
route/TAS3108 audio contract.  The plan is deliberately staged:

1. Preserve and test the legacy SRC route / TAS3108 refresh contract.
2. Prove the tests fail on the bad polling-only replacement shape.
3. Add tests that document the real overpolling problem without blessing an
   unproven cadence change.
4. Keep canonical V3.2 on an in-place cadence candidate that preserves the
   stock route/TAS contract.
5. Require structured hardware soak evidence before treating the cadence change
   as releasable.

The implementation is not complete because the simulator is green.  It is
complete only when simulator safety tests, cadence tests, full integration, and
hardware audio checks agree.

## Current Status

The first implementation replaced the legacy `main_i2c_service_27f0` service
with a new Auto Detect state machine.  That remains rejected because it broke
the route/TAS refresh contract.  A later audio complaint against the in-place
countdown candidate was retested on 2026-05-20 and traced to misconnected
speakers, not firmware.  The same hardware retest exposed a real fixed-source
bug: explicit input changes did not reliably force route reconciliation after
Auto Detect had parked the SRC4382 elsewhere.  The deployed front-panel
`S/PDIF` item emits `B0/06/05` and maps to route `1`; external-mux route
requests `0/5/6/7` are a separate stock branch that must restore the default
SRC4382 pair.

The current candidate keeps the legacy service body and route/TAS contract,
adds an in-place `ram_0x0BA` countdown around Auto Detect candidate/status
polling, adds a two-sample source-loss debounce for the selected Auto Detect
route, forces route reconciliation on explicit input commands, writes the
default SRC4382 pair for fixed digital external-mux routes, and has been
rebuilt into canonical V3.2 rev `0x6E`.

The 2026-05-20 frequency sweep keeps `0x12` candidate settle and `0x28`
source-present monitor as the release candidate.  A faster `0x0C` settle gives
about `250 ms` worst-position detection but misses the 10x no-source
traffic-reduction target; a slower `0x18` settle gives lower traffic and still
detects in about `465 ms` in sim, but the margin is too narrow to promote
without a separate hardware source-detection timing check.

Current guard tests:

```bash
cargo test -p dlcp-sim src4382 --lib
cargo test -p dlcp-sim tas3108 --lib
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v32_release_flash_sim.py
```

Current cadence/liveness test:

```bash
.venv_ep0/bin/python -m pytest -q tests/sim/test_v32_src4382_autodetect_polling.py
# 24 passed
```

Latest focused simulator result after rebuilding V3.2 rev `0x6E`:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py
# 33 passed in 34.69s
```

Additional rev `0x6E` release/diagnostics checks:

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

Latest non-hardware verification after the fixed-digital route-prime update:

```bash
cargo test -p dlcp-sim src4382 --lib
# 10 passed; 0 failed; 602 filtered out

cargo test -p dlcp-sim tas3108 --lib
# 15 passed; 0 failed; 597 filtered out

.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v171_v32_ledger_hardware_gate.py \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py
# 116 passed in 39.55s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_release_flash_sim.py
# 4 passed in 53.82s

.venv_ep0/bin/python -m pytest tests -n 16 -q
# 1081 passed, 18 skipped, 10 warnings in 393.86s

cargo test --workspace
# passed; snapshot_soak reported 6 passed in 1380.05s
```

The 18 skips in the full `tests` gate include live hardware tests that are
intentionally not executed until the operator provides manual rig evidence.
The latest `cargo test --workspace` run passed; the longest sub-binary was
`snapshot_soak`, which reported `6 passed` in `1380.05s`.  The previous cargo
failure was a test-fixture race, not a firmware diagnostic renderer failure.
The Volume-screen A/B badge cell is also pinned by a steady-idle LCD
DDRAM-write-count regression: the simulator does not reproduce hardware
pulsing as repeated firmware writes to row 0 column 15.

## Non-Negotiable Rules

1. Do not replace `main_i2c_service_27f0` with a polling-only service.
2. Preserve the route event contract: `ram_0x093` plus `event_flags.bit1` must
   drive `cmd_dispatch_gated` or a proven-equivalent replacement.
3. Preserve TAS3108 refresh after SRC route changes, including coefficient
   `0x30` writes in the runtime guard.
4. Do not change CONTROL behavior unless a test shows a V1.71 interaction bug.
5. Do not introduce a new release filename.  Use canonical V3.2/V1.71 builders.
6. Do not add arbitrary SRC4382 USB writes.  Diagnostics remain read-only.
7. Do not use Timer0 or any timer resource for Auto Detect until conflict tests
   prove no impact on USB filename transactions, command dispatch, standby/wake,
   or other timer users.
8. Historical cadence-red evidence must stay documented so the tests remain
   tied to a real pre-fix failure.
9. Safety tests must not be xfailed.

## Work Ownership

Firmware:

- `src/dlcp_fw/asm/dlcp_main_v32.asm`
- `src/dlcp_fw/asm/dlcp_main_ram.inc`
- `scripts/build_v32_release.py`

Simulator and facade:

- `crates/dlcp-sim/src/peripherals/src4382.rs`
- `crates/dlcp-sim/src/peripherals/tas3108.rs`
- `crates/dlcp-sim/src/chain.rs`
- `crates/dlcp-sim-py/src/lib.rs`
- `src/dlcp_fw/sim/dlcp_sim_native.py`

Tests:

- `tests/sim/test_v32_src4382_audio_path_regression.py`
- `tests/sim/test_v32_release_flash_sim.py`
- `tests/sim/test_v32_src4382_autodetect_polling.py`
- adjacent chain/liveness tests:
  - `tests/sim/test_v171_v32_standby_wake_soak.py`
  - `tests/sim/test_v171_v32_layer5_diag_chain.py`
  - `tests/sim/test_v171_v32_link_health_freshness.py`

Docs/ledger:

- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md`
- `docs/SRC4382_USB_DIAGNOSTICS_SPEC.md`
- `docs/IMPL_V171_V32_BUG_LEDGER.md`
- `docs/HARDWARE_TEST.md`

## Phase 0 - Ledger And Baseline

Add or update the ledger entry:

```text
BUG-SRC4382-AD-01 | blocked | MAIN SRC4382 Auto Detect | V3.2 overpolls SRC4382 in Auto Detect; the broad rewrite broke the route/TAS contract, while the later bad-audio observation was retested as a speaker-wiring false alarm.  Rev `0x6D` then exposed fixed digital source silence after Auto Detect; canonical rev `0x6E` now contains the in-place countdown candidate, source-loss debounce, and fixed-digital SRC route priming, but closure remains blocked on structured hardware retest/soak evidence. | tests/sim/test_v32_src4382_audio_path_regression.py; tests/sim/test_v32_src4382_autodetect_polling.py; tests/sim/test_v32_release_flash_sim.py
```

Baseline commands:

```bash
cargo test -p dlcp-sim src4382 --lib
cargo test -p dlcp-sim tas3108 --lib
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v32_release_flash_sim.py
```

Phase 3 firmware work is allowed only while these stay green.

## Phase 1 - Safety Tests Before Cadence Tests

### 1A. Existing Safety Guards

Keep and extend `tests/sim/test_v32_src4382_audio_path_regression.py`:

- Static check: `main_i2c_service_27f0` retains the legacy SRC4382 status-poll
  and route reconciliation shape, or an approved equivalent.
- Runtime check: forcing `ram_0x093` and `event_flags.bit1` writes the expected
  SRC4382 route pair and refreshes TAS3108 coefficient `0x30`.
- Runtime check: the firmware polls `0x0D`, `0x13`, and `0x12` through the
  running MAIN path when Auto Detect is active and source-present.

Keep and extend `tests/sim/test_v32_release_flash_sim.py`:

- Decode LX521 preset A/B payloads from the release artifacts.
- Assert exact logical TAS3108 payload delivery to both MAINs.
- Assert restored preset A still delivers the expected payload.

### 1B. Required Negative Proof

Add one of these before a new Auto Detect implementation is accepted:

- A fixture assembled from the bad replaced-service source, if recoverable from
  git, that fails the route/TAS contract tests.
- A small generated mutation in the test that removes or bypasses
  `event_flags.bit1` / TAS refresh and proves the safety test fails.
- A static "bad service" fixture under `tests/fixtures/` that represents the
  failure mode and is only used by the regression test.

The important point is not the mechanism.  The suite must demonstrate that it
would catch a route/TAS refresh break before hardware listening tests do.

Current implementation:

- `test_v32_audio_path_safety_guard_rejects_missing_route_event_mutation`
  generates a V3.2 mutation that replaces the Auto Detect route-event
  `bsf event_flags, 1` with `nop`.  The mutated firmware still sees the SRC4382
  source-present status and updates the route shadow, but it never writes the
  SRC4382 transmitter route or refreshes TAS3108 coefficient `0x30`; the safety
  helper must raise.
- `test_v32_audio_path_safety_guard_rejects_missing_tas_refresh_mutation`
  generates a V3.2 mutation that keeps the SRC4382 route write path but removes
  the downstream `volume_dsp_write` call.  The safety helper must raise because
  TAS3108 coefficient `0x30` is not refreshed.

## Phase 2 - Cadence Red Tests

`tests/sim/test_v32_src4382_autodetect_polling.py` exists and runs as a normal
release gate.

Required helpers:

- Build MAIN-only V3.2 and V1.71 + two V3.2 chains through the normal Rust/PyO3
  firmware path.
- Seed SRC4382 status registers through facade helpers.
- Reset SRC4382 stats after boot/init settles.
- Assert firmware-visible side effects, not just direct model state.

Cadence/liveness tests:

1. `test_v32_src4382_autodetect_no_source_cadence_is_reduced`
   - Auto Detect active, `0x13.RXCKR=0`.
   - Run one simulated second after stats reset.
   - Assertion: `bytes_acked <= 150`; current observed value is `69`.

2. `test_v32_cadence_guard_rejects_unthrottled_receiver_select_mutation`
   - Generate a V3.2 mutation that changes the candidate settle countdown from
     `0x12` to `0x01`.
   - Assemble the temporary firmware and assert the no-source cadence budget
     fails with excess `bytes_acked`.
   - This pins the cadence guard to a concrete high-traffic red case.

3. `test_v32_src4382_autodetect_source_present_cadence_is_reduced`
   - Auto Detect active, `0x13.RXCKR != 0`, `0x12=0`.
   - Run one simulated second after source-present settle.
   - Assertion: `bytes_acked <= 160`; current observed value is `39`.

4. `test_v32_source_present_cadence_guard_rejects_unthrottled_monitor_mutation`
   - Generate a V3.2 mutation that changes the source-present monitor countdown
     from `0x28` to `0x01`.
   - Assemble the temporary firmware and assert the source-present cadence
     budget fails with excess `bytes_acked`.
   - This pins the source-present monitor guard to a concrete high-traffic red
     case.

5. `test_v32_src4382_no_source_scan_does_not_read_non_pcm_status`
   - Auto Detect active, `0x13.RXCKR=0`, with `0x12` seeded to a non-zero
     sentinel.
   - Assert the no-source scan reads `0x13` but does not read or latch `0x12`.
   - Assert the route request remains clear while no source is present.

6. `test_v32_src4382_source_present_latches_non_pcm_status`
   - Auto Detect active, `0x13.RXCKR != 0`, with `0x12` seeded to a non-zero
     sentinel.
   - Assert the source-present path reads `0x12`, stages it in `ram_0x0BF`,
     and converges through the route shadow.
   - This pins `ram_0x0BF` as the legacy non-PCM/status scratch rather than a
     receiver-select write shadow.

7. `test_v32_src4382_writes_0d_only_when_candidate_changes`
   - No-source Auto Detect.
   - Assert the receiver-select write sequence starts
     `0x08,0x09,0x0A,0x0B`, has no adjacent duplicates, and stays bounded.

Historical pre-fix `--runxfail` evidence:

```text
no-source stock-equivalent baseline:
  913 ACKed transmit bytes > 150
source-present stock-equivalent baseline:
  1109 ACKed transmit bytes > 50
stock-equivalent repeated receiver-select writes:
  19 writes to 0x0D in the 125 ms candidate dwell > 1
```

`test_v32_src4382_full_scan_detects_worst_position_source_within_500ms` is
green and must stay green.

8. `test_v32_src4382_full_scan_detects_worst_position_source_within_500ms`
   - Source appears only on the worst-position candidate.
   - Firmware maps to the existing route request within `500 ms`.
   - Scanning stops after source-present detection.

9. `test_v32_discovery_guard_rejects_overly_slow_candidate_settle_mutation`
   - Generate a V3.2 mutation that changes the candidate settle countdown from
     `0x12` to `0x24`.
   - Assemble the temporary firmware and assert the worst-position discovery
     budget fails before route/TAS convergence.
   - This pins the slow side of the frequency sweep so lower bus traffic cannot
     be achieved by missing the `500 ms` source-discovery target.

10. `test_v32_src4382_explicit_input_preempts_autodetect_and_converges_route`
   - Auto Detect scan is active.
   - Inject fixed input command.
   - Route converges promptly through the legacy contract and Auto Detect does
     not overwrite it while fixed input is selected.

11. `test_v32_src4382_fixed_input_goes_quiet_after_route_converges`
   - Switch from Auto Detect to a fixed input and let the route converge.
   - Reset SRC4382 stats, then run one simulated second.
   - Assert the reduced Auto Detect service does not keep polling `0x0D`,
     `0x13`, or `0x12` after fixed input selection has taken over.

12. `test_v32_src4382_nack_does_not_block_volume_command`
   - Inject SRC4382 address or data NACK.
   - Inject volume while the fault is active.
   - MAIN returns to the loop, the user command applies, `diag_i` increments,
   and the volume command still applies under the reduced Auto Detect
   load.

13. `test_v32_src4382_autodetect_mute_unmute_remain_responsive`
   - Keep Auto Detect active with no SRC4382 source.
   - Inject mute-on and mute-off frames.
   - MAIN drains the RX ring, updates mute state, and refreshes TAS3108
     coefficient `0x30`.

14. `test_v32_src4382_autodetect_standby_wake_remain_responsive`
   - Keep Auto Detect active with no SRC4382 source.
   - Inject standby and wake frames.
   - MAIN drains the RX ring, closes the active gate on standby, and reopens it
     on wake.

15. `test_v32_src4382_autodetect_preset_change_remains_responsive`
   - Keep Auto Detect active with no SRC4382 source.
   - Inject a preset-select frame for the opposite active preset.
   - MAIN drains the RX ring and completes the preset job back to IDLE.

16. `test_v171_v32_src4382_autodetect_dual_main_chain_soak_stays_responsive`
   - Boot the V1.71 CONTROL + two V3.2 MAIN firmware path.
   - Configure both MAINs for Auto Detect.
   - Exercise no-source bounded traffic, source-present route convergence
     through the current candidate route pair and TAS3108 coefficient `0x30`,
     and a forwarded volume command.
   - Assert CONTROL stays connected and both MAINs remain responsive.

The current release-gate cadence file implements items 1-18 above.

17. `test_v32_src4382_single_source_loss_sample_does_not_flap_route`
   - Source is already selected through Auto Detect.
   - Force one monitor sample of `0x13.RXCKR == 0`.
   - Assert the selected route and route shadow remain stable, then restore
     source-present status and assert the debounce latch clears.

18. `test_v32_src4382_sustained_source_loss_resumes_scan_within_1s`
   - Source is already selected through Auto Detect.
   - Hold `0x13.RXCKR == 0`.
   - Assert the route clears only after consecutive loss samples and the scan
     resumes within `1 s`.

## Phase 3 - Candidate Firmware Implementation

This phase is implemented in the current V3.2 source/HEX as an in-place
candidate.  Earlier firmware/audit attempts now separate into two classes:

- A broad service rewrite that broke the SRC route/TAS refresh contract in the
  simulator-visible audio path.
- A smaller dwell throttle inside `main_i2c_service_27f0` whose initial
  bad-audio report was retested and traced to speaker wiring, not firmware.
- A fixed-input route gap in rev `0x6D`: selecting a displayed fixed digital
  source after Auto Detect did not reliably force route reconciliation, so the
  fixed source could inherit the previous Auto Detect receiver state.  The
  real front-panel `S/PDIF` item emits `B0/06/05` and should converge to MAIN
  route `1` (`0x0D=0x09`, `0x08=0x70`) on the deployed `BF/05 == 3` routing
  profile; external-mux route requests `0/5/6/7` are a separate stock branch
  that must restore the default SRC4382 pair.

The current V3.2 candidate intentionally does not replace
`main_i2c_service_27f0`.  It preserves the service, adds a small countdown gate
inside the Auto Detect branch, and keeps all route/DSP side effects delegated to
the existing `cmd_dispatch_gated` contract.  Rev `0x6E` also forces route
reconciliation when `cmd 0x06` changes the input, preserves the displayed
S/PDIF route (`B0/06/05` -> route `1`, `0x0D=0x09`, `0x08=0x70`), and makes
external-mux routes `0/5/6/7` restore SRC4382 `0x0D=0x08`, `0x08=0x30`.

Implementation shape:

- Keep `cmd_dispatch_gated` route/DSP refresh behavior unchanged.
- Modify only the Auto Detect scanning cadence inside the existing service,
  rather than replacing the whole service.
- Preserve the existing route request mapping:
  - scan index `0` / RX value `0x08` -> route `3`
  - scan index `1` / RX value `0x09` -> route `1`
  - scan index `2` / RX value `0x0A` -> route `2`
  - scan index `3` / RX value `0x0B` -> route `4`
- When a source is detected, set the same route request and `event_flags.bit1`
  contract as stock-equivalent V3.2.
- If using the existing `ram_0x0BA` dwell byte to gate the expensive poll path,
  add a firmware-shape test and hardware proof that the route/TAS contract is
  still intact.
- Do not store the last-written receiver select in `ram_0x0BF`; the guard
  reserves it for the legacy register `0x12` status scratch.
- Do not read `0x12` during no-source scanning.
- Read `0x12` only on source-present route changes in this implementation.
- Keep existing bounded MSSP timeout/recovery behavior for SRC4382 NACKs.

Implemented details:

- No-source scan: write `0x0D` for the current candidate, set
  `ram_0x0BA = 0x12`, skip SRC4382 traffic while the countdown decrements, then
  read `0x13`.
- No-source miss: clear `ram_0x093`, advance `ram_0x0B6` modulo four, and leave
  the next candidate write to the following Auto Detect service call.
- Source-present hit: map the scan index to the legacy route request, read
  `0x12` into `ram_0x0BF`, reconcile `ram_0x093`/`ram_0x0AB`, and set
  `event_flags.bit1` when the route changes.
- Source-present monitor: set `ram_0x0BA = 0x28` before the next status poll.
- Source-loss debounce: when a selected Auto Detect route sees one
  `0x13.RXCKR == 0` monitor sample, retain the route and set
  `src4382_loss_debounce`; clear the route and resume scanning only after a
  consecutive miss.  Any source-present sample or fixed-input path clears the
  debounce latch.
- Fixed input: clear `ram_0x0B6` and `ram_0x0BA`, then run the existing fixed
  route path.

Future fuller state-machine candidate, if needed:

```text
AD_DISABLED_FIXED_INPUT
AD_SCAN_SET_CANDIDATE
AD_SCAN_SETTLE
AD_SCAN_READ_STATUS
AD_SCAN_CONFIRM_PRESENT
AD_SOURCE_PRESENT_MONITOR
AD_FAULT_BACKOFF
```

RAM allocation is not specified here.  Any allocation must have a collision test
and must avoid USB endpoint buffers, BDT, known wipe regions, and link-health
freshness RAM.

Time base constraints:

- Possible: reuse the existing slow-service cadence byte, but only with conflict
  tests and hardware acoustic validation.
- Possible: add a small timer-derived tick only with conflict tests and hardware
  acoustic validation.
- Not acceptable as final release behavior: raw cooperative-loop pass count.
- The reverted Timer0 approach is not accepted by this plan without new
  conflict tests and hardware validation.

## Phase 4 - Diagnostics

MVP diagnostics remain simulator-side:

- SRC4382 per-register read/write counts.
- SRC4382 NACK injection.
- TAS3108 completed payload logs.

Optional firmware diagnostics, if flash/RAM allow:

- Read-only USB endpoint fields from `docs/SRC4382_USB_DIAGNOSTICS_SPEC.md`.
- Auto Detect state, candidate, selected route, last `0x12`/`0x13`, fault count,
  recovery count, and ticks since last successful SRC4382 transaction.

Do not add a CONTROL LCD page in this phase.

## Phase 5 - Verification Gates

Focused simulator gates:

```bash
cargo test -p dlcp-sim src4382 --lib
cargo test -p dlcp-sim tas3108 --lib
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v32_release_flash_sim.py
```

Integration gates:

```bash
.venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v32_release_flash_sim.py \
  tests/sim/test_v171_v32_standby_wake_soak.py \
  tests/sim/test_v171_v32_layer5_diag_chain.py \
  tests/sim/test_v171_v32_link_health_freshness.py
# 54 passed in 323.97s

.venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

Long soak:

```bash
time .venv_ep0/bin/python scripts/sim_v171_v32_standby_wake_soak.py \
  --usb-probe-every 10 \
  --seconds 18000 \
  2>&1 | tee artifacts/probes/v171_v32_standby_wake_soak_src4382_ad.log
```

Hardware gates:

1. Fixed-input acoustic baseline versus stock-equivalent V3.2.
2. Candidate fixed-input acoustic parity.
3. Auto Detect source-present acoustic parity.
4. Auto Detect no-source 30-minute UI/fault soak.
5. Fixed-input 1-hour playback/fault soak.
6. User actions while playing: volume, mute, preset A/B, standby/wake, explicit
   input.
7. Optional SCL/SDA capture showing no continuous high-rate `0x0D` rewrite.

Manual hardware evidence is acceptable when the live pytest wrapper is not run,
but it must use `docs/SRC4382_AD_MANUAL_EVIDENCE_TEMPLATE.md` following the
runbook in `docs/HARDWARE_TEST.md`.  A free-form "sounds OK" note is not enough
to close the bug; the report must explicitly cover fixed-input audio, Auto
Detect audio, the listed user actions, soak durations, UI stalls, and `I`/`R`
growth, with a concrete date-like and time-like timestamp, source/input,
preset, volume, low-band check material, explicit confirmation that CONTROL is
running V1.71 and both MAINs are visible/running V3.2, current release SHA256
hashes, PB1/PB2 `I`/`R` before/after snapshots, a yes/no Volume-screen A/B
badge abnormal-refresh observation, and a concrete explanation for any `I`/`R`
growth recorded.  Store the completed
report as an artifact, for example
`artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md`,
so the ledger `DONE:` evidence can cite a stable path.  Validate the completed
artifact with `scripts/validate_src4382_manual_evidence.py` before updating the
ledger.  The artifact summary gate accepts a validated manual evidence artifact
for `BUG-SRC4382-AD-01` even when the live pytest closure report is absent, so
the manual path is a real substitute for the wrapper rather than a second
requirement.  If the manual artifact is present but invalid, artifact summary
prints `manual_evidence_failed` and lists the validator errors inline.

Current hardware preflight:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --preflight \
  --bug BUG-SRC4382-AD-01 \
  --report-json artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_preflight_current.json
# Preflight FAIL: no MAIN HID devices currently visible; also missing
# DLCP_HW_SRC4382_FIXED_INPUT_AUDIO_OK,
# DLCP_HW_SRC4382_AUTODETECT_AUDIO_OK,
# DLCP_HW_SRC4382_USER_ACTIONS_OK,
# DLCP_HW_SRC4382_SOAK_OK.
# Report: artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_preflight_current.json
```

Current manual evidence artifact validation:

```bash
.venv_ep0/bin/python scripts/validate_src4382_manual_evidence.py
# FAIL: artifacts/probes/v171_v32_ledger_gate/bug_src4382_ad_01_manual_evidence.md
# The artifact has been refreshed to current MAIN rev 0x6E, but still leaves
# the required rig/audio, fixed-digital-source, soak, Volume A/B badge,
# PB1/PB2 I/R, and pass/fail fields blank pending a live hardware retest.
```

Current artifact-readiness summary:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --summarize-artifacts \
  --require-all-ready \
  --python .venv_ep0/bin/python
# FAIL: artifact readiness 0 ready / 10 not ready.
# BUG-SRC4382-AD-01 is manual_evidence_failed, including the blank
# Volume A/B badge observation field, plus the other required blank
# rig/audio/soak/PB1/PB2 I/R/pass-fail fields.
# Report: artifacts/probes/v171_v32_ledger_gate/artifact_summary_current.json
```

Current completion audit:

```bash
.venv_ep0/bin/python scripts/run_v171_v32_ledger_hardware_gate.py \
  --audit-completion \
  --report-json artifacts/probes/v171_v32_ledger_gate/completion_audit_current.json
# NOT COMPLETE: BUG-SRC4382-AD-01 remains blocked along with the other
# non-done hardware-confirmation rows; artifact readiness 0 ready / 10 not ready.
```

## Completion Checklist

- Safety tests pass on current stock-equivalent V3.2.
- Safety tests fail on a bad polling-only replacement or mutation.
- Exact LX521 TAS3108 payload tests pass for both MAINs and presets.
- The stock-equivalent high-cadence baseline is documented in the spec and the
  current lower-traffic candidate is enforced by tests.
- Explicit-input and SRC4382 NACK/no-stall tests pass.
- V1.71/V3.2 SRC4382 chain soak is implemented and passing; source-loss
  debounce is implemented and passing.
- The Volume-screen A/B badge cell is covered by a steady-idle LCD
  DDRAM-write-count regression; repeated firmware writes to row 0 column 15
  are not the simulator-observed cause of hardware pulsing.
- Firmware candidate preserves the route/TAS contract and rejects polling-only
  or TAS-refresh-breaking mutations.
- Full simulator gate passes.
- Hardware acoustic parity passes.
- Hardware soak shows no UI stall or unexplained `I`/`R` growth.
- If hardware is closed from manual evidence, the completed artifact passes
  `scripts/validate_src4382_manual_evidence.py`, including current release
  SHA256 hashes, concrete PB1/PB2 `I`/`R` before/after snapshots, and a yes/no
  Volume-screen A/B badge observation.
- The ledger completion audit rejects a premature `BUG-SRC4382-AD-01` `done`
  row unless the same manual evidence artifact validates.

Until the hardware items above are true, `BUG-SRC4382-AD-01` remains
`blocked`, not done.
