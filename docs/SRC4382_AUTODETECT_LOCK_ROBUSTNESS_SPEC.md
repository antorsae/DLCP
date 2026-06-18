# SRC4382 Auto Detect Lock Robustness Spec

Last updated: 2026-06-13
Status: Proposed for MAIN V3.4 follow-up after live V3.4/V1.73 field evidence
Scope: MAIN `src/dlcp_fw/asm/dlcp_main_v34.asm`, SRC4382 Auto Detect source-validity decisions, simulator tests, release build/size gates, and hardware validation.

## Decision

The existing Auto Detect loss decision is too brittle for real S/PDIF-like
sources.  `0x13.RXCKR[1:0]` is a recovered-clock rate classifier.  It can read
`0b00` while the receiver is still locked and audio is valid, for example during
rate re-measurement, jitter, track-boundary rate changes, or source-side
re-clocking.  MAIN must not clear a selected Auto Detect route on RXCKR alone.

The robust contract is:

1. Keep RXCKR as the fast scan/rate-class evidence.
2. Use `0x14.UNLOCK` as the formal lock evidence when RXCKR is ambiguous.
3. Once a route is selected, hold the route through RXCKR estimator holes while
   `UNLOCK == 0`.
4. Declare source loss only after sustained `RXCKR == 0` and `UNLOCK == 1`.
5. Keep the implementation compact.  MAIN space before the `0x4C00` preset-B
   table is tight, so this is an in-place branch change, not a new Auto Detect
   state machine.

This spec supersedes the old `docs/SRC4382_AUTODETECT_POLLING_SPEC.md` contract
that said sustained RXCKR loss must resume scanning within 1 s.  That contract
was based on the wrong oracle for selected-route loss.  Fast acquisition remains
important, but selected-route teardown must favor audio continuity over quick
scan restart.

## Evidence

SRC4382 reference evidence:

- The DIR recovered-clock rate class is estimated by internal detection logic
  and is exposed through register `0x13.RXCKR[1:0]`.
- `RXCKR == 0b00` means "Clock rate not determined", not formal source absence.
- Register `0x14.UNLOCK` is the DIR AES3 decoder plus PLL2 lock status:
  `0` means locked, `1` means unlocked.
- Register `0x0E.RXAMLL` enables receiver automatic mute on loss of lock.  The
  current MAIN init writes `0x0E = 0x08`, so hardware already mutes true lock
  loss while firmware decides whether to scan.

Firmware evidence:

- `poll_src4382_route_monitor` owns Auto Detect scanning, selected-source monitoring,
  `ram_0x093` route requests, `ram_0x0AB` route shadow, and route-change
  `event_flags.bit1`.
- `cmd_dispatch_gated` owns the selected SRC4382 route pair writes and the
  downstream TAS3108 refresh.  Auto Detect must keep using that contract.
- Current V3.4 rev `0x88` hardening widens RXCKR-only debounce to six misses,
  but it is still an RXCKR-only teardown path.
- Current simulator helpers can seed SRC4382 registers through
  `poke_main_src4382_reg`, so tests can drive firmware-visible `0x13` and
  `0x14` status patterns directly.

Current measured canonical MAIN margin in this workspace:

```text
last_used_pre_preset_b=0x4B05
free_bytes_before_0x4C00=250
free_object_words=125
```

Acceptance still follows the V3.4 floor: `free_object_words >= 64`
(`free_bytes_before_0x4C00 >= 128`).  This feature must prefer a much smaller
delta: target `<= 20` added object words, absolute maximum `<= 32` added object
words unless the implementation first finds compensating deletions.

## Source Validity Contract

Definitions:

```text
rxckr = SRC4382[0x13] & 0x03
unlock = SRC4382[0x14] & 0x04
hard_loss_counter = existing src4382_loss_debounce byte at bank2 0x2F3
```

### Auto Detect Scan, No Selected Route

For scan candidates when `ram_0x0AB == 0`:

- `rxckr == 0`: candidate absent; continue scan as today.
- `rxckr != 0` and `unlock == 0`: candidate valid; apply the existing
  route/TAS contract.
- `rxckr != 0` and `unlock != 0`: candidate is not valid yet; do not apply a
  route.  Treat as a scan miss or no-commit so Auto Detect continues searching.
- A transport timeout while reading `0x13` or `0x14` is not source evidence.
  Use existing I2C recovery behavior; do not commit a route on incomplete data.

### Selected Route Monitor

For monitor samples when `ram_0x0AB != 0`:

- `rxckr != 0`: source-present evidence; clear `hard_loss_counter`, continue
  the existing `0x12` non-PCM path, and keep the selected route.
- `rxckr == 0` and `unlock == 0`: rate-estimator hole while DIR remains locked.
  Clear or hold `hard_loss_counter` at zero, copy `ram_0x0AB` back into
  `ram_0x093`, do not count `L`, do not count route-change `C`, do not mute, do
  not scan, and do not rewrite SRC/TAS route state.
- `rxckr == 0` and `unlock != 0`: hard-loss evidence.  Increment
  `hard_loss_counter`, but keep the selected route until the threshold is met.
- Only when `hard_loss_counter >= SRC4382_HARD_LOSS_CONFIRM_SAMPLES` may MAIN
  count `L`, clear the selected route, and resume scanning.
- A transport timeout while reading `0x13` or `0x14` holds the selected route.
  It may affect existing I/R diagnostics, but it must not count as source loss.

The hard-loss threshold shall be a literal/equate near 8-10 real seconds at the
current source-present monitor cadence.  Initial target:

```text
SRC4382_HARD_LOSS_CONFIRM_SAMPLES = 0x14
```

This intentionally delays scan restart after a true unplug.  That is acceptable:
the SRC4382 receiver auto-mute path handles true lock loss, while false route
teardown during live music causes audible dropouts, filter/route churn, and
previously exposed volume-transient hazards.

## Non-Goals

- No CONTROL firmware change.
- No new LCD UI.
- No arbitrary SRC4382 write endpoint.
- No full SRC4382 PLL/audio math model in Rust.
- No new Auto Detect state machine unless the compact in-place branch change
  cannot fit or cannot pass tests.
- No Timer0 or new timing resource.
- No new persistent setting.
- No new diagnostic counter unless the implementation finds enough code space
  and the test value is clearly worth it.  `L` remains confirmed hard loss.

## Simulator Test Requirements

Tests must simulate the exact firmware-visible SRC conditions, not just generic
"source present" booleans.  Use register scripts over `0x13` and `0x14`.

Required focused tests:

1. **S/PDIF rate transition holds route**: after Auto Detect selects an S/PDIF
   route, drive a locked bitrate sequence such as
   `RXCKR: 0x01 -> 0x00 -> 0x02 -> 0x00 -> 0x03` with `UNLOCK == 0`.
   Expected: route shadow unchanged, `L` unchanged, `C` unchanged after initial
   convergence, no TAS3108 louder-than-baseline writes.
2. **Long estimator hole while locked**: hold `RXCKR == 0`, `UNLOCK == 0` for
   longer than the hard-loss threshold.  Expected: route held, `L` unchanged,
   no scan writes to `0x0D` beyond normal monitor traffic.
3. **Short unlock flap**: hold `RXCKR == 0`, `UNLOCK == 1` for fewer samples
   than the hard-loss threshold.  Expected: route held and no `L`.
4. **Sustained hard unlock**: hold `RXCKR == 0`, `UNLOCK == 1` through the
   threshold.  Expected: one confirmed `L`, route clears, scan resumes, and
   later `RXCKR != 0`, `UNLOCK == 0` reacquires a route.
5. **False acquisition rejected**: while no route is selected, drive
   `RXCKR != 0`, `UNLOCK == 1`.  Expected: no route commit and no TAS route
   refresh for that candidate.
6. **Acquisition still fast when locked**: while no route is selected, drive
   `RXCKR != 0`, `UNLOCK == 0`.  Expected: route/TAS convergence remains within
   the existing user-visible Auto Detect budget.
7. **Mutation guards**: generated source mutations that either remove the
   `UNLOCK` gate or restore RXCKR-only loss confirmation must fail focused
   tests.

Existing tests that intentionally force confirmed loss cycles must be updated to
drive `0x14.UNLOCK = 1`; tests that represent estimator/rate blips must keep
`0x14.UNLOCK = 0`.

## Release Gates

Focused gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_mute_refresh_bug.py
```

Simulator/model gate:

```bash
cargo test -p dlcp-sim src4382 --lib
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_ram_bank_safety.py
```

Broader release gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v34 or v173 or src4382 or ram_bank"
```

Build/size gate:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.paths import V34_MAIN_HEX
from dlcp_fw.sim.hexio import parse_intel_hex
mem = parse_intel_hex(V34_MAIN_HEX)
used = [a for a in range(0x1000, 0x4C00) if mem.get(a, 0xFF) != 0xFF]
last = max(used) if used else 0x0FFF
free = 0x4C00 - (last + 1)
print(f"last_used_pre_preset_b=0x{last:04X}")
print(f"free_bytes_before_0x4C00={free}")
print(f"free_object_words={free // 2}")
assert free // 2 >= 64
PY
```

## Hardware Validation

Before recommending the resulting MAIN build:

1. Flash the new V3.4 MAIN build on both MAINs and current V1.73 CONTROL.
2. Use Auto Detect with the real S/PDIF source that reproduced the field issue.
3. Play continuously for at least 30 minutes with ordinary preset/menu usage.
4. Exercise S/PDIF track boundaries and sample-rate changes when available.
5. Record `scripts/dlcp_diag.py --json` before/after and confirm:
   - no spontaneous route churn,
   - `L` does not grow during locked bitrate transitions,
   - `C` does not grow except for deliberate source changes,
   - no audible filter change, dropout, or volume excursion.

## Acceptance Criteria

- Selected Auto Detect routes survive RXCKR estimator holes while `UNLOCK == 0`.
- True hard loss still resumes scan after sustained `RXCKR == 0` and
  `UNLOCK == 1`.
- Route/TAS refresh contract remains unchanged.
- MAIN build remains above the V3.4 size floor.
- Focused and broader simulator gates pass.
- Hardware soak shows no spontaneous filter/route/audio changes under the
  previously failing source.
