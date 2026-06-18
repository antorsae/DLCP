# IMPL SRC4382 Auto Detect Lock Robustness

Date: 2026-06-13
Status: Implemented - simulator gates pass; hardware soak still required before release promotion
Source spec: `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md`
Scope: MAIN V3.4 SRC4382 Auto Detect source-validity fix, simulator tests, build/size gates, and hardware validation.  Implementation is intentionally deferred.

## Source Requirements

Goals:

- Stop selected Auto Detect route teardown on RXCKR estimator holes.
- Use `0x14.UNLOCK` as formal lock evidence where RXCKR is ambiguous.
- Keep the existing `ram_0x093` / `ram_0x0AB` / `event_flags.bit1` route/TAS contract.
- Keep MAIN changes compact because code space before `0x4C00` is tight.
- Add register-script simulator tests that model S/PDIF bitrate/rate-estimator and lock-status conditions through SRC4382 registers `0x13` and `0x14`.

Non-goals:

- No CONTROL change.
- No LCD/UI change.
- No full SRC PLL/audio model.
- No new Auto Detect state machine, Timer0 use, persistent setting, or arbitrary SRC write endpoint.
- No new diagnostic counter unless implementation finds clear free space and value.  The approved simple plan does not require one.

Explicit user decisions:

- Robustness and SRC correctness are more important than fast route teardown on true unplug.
- MAIN space is very tight; prefer the smallest correct branch change.
- Tests must exercise simulated SRC conditions, including S/PDIF bitrate changes and RXCKR estimator holes.

## Required Docs Read

- `AGENTS.md`: canonical paths, V3.4/V1.73 release/build/test commands, and V3.4/V1.73 as recommended pair.
- `README.md`: current V3.4/V1.73 operator setup, build, flash, validate, and simulator commands.
- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md`: source spec for this IMPL.
- `docs/SRC4382_AUTODETECT_POLLING_SPEC.md`: older Auto Detect cadence and route/TAS contract; its RXCKR-only selected-loss window is superseded.
- `docs/IMPL_SRC4382_AUTODETECT_POLLING_SPEC.md`: implementation history and route/TAS failure lessons.
- `docs/REFACTORING_V34_V173_SPEC.md` and `docs/IMPL_REFACTORING_V34_V173.md`: V3.4 size and lifecycle constraints.
- `docs/RAM_BANK_SAFETY_SPEC.md` and `docs/RAM_BANK_SAFETY_IMPL.md`: RAM aliasing/build gate constraints.
- `docs/HARDWARE_TEST.md`: live-rig validation expectations.
- `firmware/reference/src4382.md`: SRC4382 register semantics for `0x13.RXCKR`, `0x14.UNLOCK`, and `0x0E.RXAMLL`.

## Current Implementation Evidence

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
  - `src4382_loss_debounce EQU 0x2F3` is already available and wipe-protected.
  - `poll_src4382_route_monitor` reads `0x13`, treats `RXCKR == 0` as source-loss evidence, and currently confirms after six selected-route misses.
  - The same service maps scan index to route request, reads `0x12` only on source-present, and reconciles `ram_0x093` with `ram_0x0AB`.
  - `cmd_dispatch_gated` writes the selected SRC4382 route pair and refreshes TAS3108; this path must remain the only route-apply path.
  - SRC4382 init writes register `0x0E = 0x08`, enabling receiver auto-mute on formal lock loss.
- `tests/sim/test_v34_autodetect_loss_debounce.py`
  - Current rev `0x88` test proves a short RXCKR blip is held and sustained RXCKR zero confirms, but it does not model `0x14.UNLOCK`.
- `tests/sim/test_v34_detect_cycle_volume_excursion.py`
  - Guards against route-flux causing louder TAS3108 volume writes during detect cycles.  Confirmed-loss portions must be updated to drive `UNLOCK = 1`.
- `tests/sim/test_v34_diag_src_counters.py`
  - Pins `N/L/C/T/M` counter behavior.  `L` should become confirmed hard-lock loss, not RXCKR-only loss.
- `crates/dlcp-sim/src/peripherals/src4382.rs`
  - SRC4382 is a register-file model.  This is sufficient for this fix because firmware observes registers, not audio waveforms.
- `crates/dlcp-sim-py/src/lib.rs`
  - `poke_main_src4382_reg`, `read_main_src4382_stats`, and write-log helpers already expose enough surface for the required tests.

Current measured canonical V3.4 size in this workspace:

```text
last_used_pre_preset_b=0x4B05
free_bytes_before_0x4C00=250
free_object_words=125
```

## Gap Analysis

Exists:

- Reduced Auto Detect cadence.
- Route/TAS contract and regression tests.
- One-byte selected-route debounce at bank2 `0x2F3`.
- SRC4382 register seeding and read/write stats in the simulator.
- V3.4 build and RAM-bank safety gates.

Missing:

- Firmware use of `0x14.UNLOCK` in Auto Detect source-validity decisions.
- Tests for firmware-visible `0x13`/`0x14` combinations.
- S/PDIF bitrate/rate-estimator transition tests (`RXCKR` nonzero -> zero -> different nonzero while `UNLOCK == 0`).
- Mutation tests that fail RXCKR-only teardown.

Stale:

- Older docs/tests that define selected-source loss as RXCKR-only and expect scan restart within 1 s.
- Current sustained-loss tests that do not explicitly drive `0x14.UNLOCK`.

## Proposed Implementation

### WU1 - Tests First

Add `tests/sim/test_v34_src4382_lock_hysteresis.py`.

Constants:

```python
SRC_REG_NON_PCM = 0x12
SRC_REG_RX_STATUS = 0x13
SRC_REG_RX_LOCK = 0x14
UNLOCK_BIT = 0x04
SRC_LOSS_DEBOUNCE = 0x2F3
DIAG_SRC_L = 0x3C1
DIAG_SRC_C = 0x3C2
```

Use existing `Chain.from_v171_v32(control_hex_path=str(V173_CONTROL_HEX), main_hex_path=str(V34_MAIN_HEX))`.

Tests:

1. `test_spdif_rate_estimator_transitions_hold_selected_route`
   - Converge Auto Detect with `0x13=0x01`, `0x14=0x00`.
   - Drive sequence `0x13: 0x01,0x00,0x02,0x00,0x03`, holding `0x14=0x00`.
   - Assert route shadow unchanged, `L` unchanged, `C` unchanged after convergence, no louder TAS `0x30` writes.
2. `test_locked_rxckr_zero_longer_than_threshold_does_not_confirm_loss`
   - Hold `0x13=0x00`, `0x14=0x00` longer than the hard-loss threshold.
   - Assert route held and `L` unchanged.
3. `test_short_unlock_flap_does_not_confirm_loss`
   - Hold `0x13=0x00`, `0x14=0x04` for fewer samples than threshold.
   - Assert route held and `L` unchanged.
4. `test_sustained_unlock_confirms_once_and_rescans`
   - Hold `0x13=0x00`, `0x14=0x04` through threshold.
   - Assert `L + 1`, route clears, scan resumes, then `0x13=0x01`, `0x14=0x00` reacquires.
5. `test_unlocked_rxckr_nonzero_candidate_does_not_apply_route`
   - Start with no selected route; drive `0x13=0x01`, `0x14=0x04`.
   - Assert no route commit/TAS route refresh for that candidate.
6. Mutation guard:
   - Build a temporary ASM mutation that changes the `0x14` branch to RXCKR-only behavior or lowers `SRC4382_HARD_LOSS_CONFIRM_SAMPLES` back to the old short value.
   - Assert at least one focused test fails.

Update existing tests:

- Any test that intends true confirmed source loss must poke `SRC_REG_RX_LOCK = 0x04`.
- Any test that intends rate/estimator blips must poke or leave `SRC_REG_RX_LOCK = 0x00`.
- Reduce long detect-cycle runtime by using one full-threshold hard-loss cycle plus, if needed, a targeted setup that seeds `SRC_LOSS_DEBOUNCE` near threshold for route-flux volume regression coverage.  Keep at least one full-threshold test realistic.

### WU2 - Compact MAIN Firmware Change

Edit only `src/dlcp_fw/asm/dlcp_main_v34.asm`.

Add source-only equates/comments near `src4382_loss_debounce`:

```asm
SRC4382_REG_RX_LOCK              EQU  0x14
SRC4382_UNLOCK_MASK              EQU  0x04
SRC4382_HARD_LOSS_CONFIRM_SAMPLES EQU 0x14
```

No new RAM is required.  Reuse `src4382_loss_debounce_b2`.

Selected-route RXCKR-zero path:

```asm
; after 0x13 read returned W=0 and stock_0AB != 0
movlw       SRC4382_REG_RX_LOCK
call        i2c_secondary_dev_random_read, 0x0
bc          poll_src4382_route_monitor__join_after_monitor_or_timeout ; hold route
andlw       SRC4382_UNLOCK_MASK
bz          poll_src4382_route_monitor__clear_loss_debounce_for_soft_hold       ; locked

; unlocked: count sustained hard loss only
movlb       0x02
incf        src4382_loss_debounce_b2, F, BANKED
movlw       SRC4382_HARD_LOSS_CONFIRM_SAMPLES
cpfslt      src4382_loss_debounce_b2, BANKED
bra         poll_src4382_route_monitor__confirm_route_loss
; fall through/branch to soft hold

poll_src4382_route_monitor__clear_loss_debounce_for_soft_hold:
movlb       0x02
clrf        src4382_loss_debounce_b2, BANKED
movlb       0x0
movff       applied_route_shadow_phys, pending_route_request_phys
bra         poll_src4382_route_monitor__reload_source_monitor_countdown
```

Acquisition RXCKR-nonzero path when no route selected:

```asm
; before applying a candidate while stock_0AB == 0
movlw       SRC4382_REG_RX_LOCK
call        i2c_secondary_dev_random_read, 0x0
bc          poll_src4382_route_monitor__join_after_monitor_or_timeout
andlw       SRC4382_UNLOCK_MASK
bnz         poll_src4382_route_monitor__advance_scan_after_miss
; then continue into existing route-map/source-present path
```

Keep the existing `0x12` non-PCM read behind source-present evidence.
Keep `event_flags.bit1` and `cmd_dispatch_gated` as the only route/TAS apply path.

If the exact assembly flow needs fewer words, the implementation may omit the acquisition-side `0x14` read only if:

- selected-route hard-loss handling remains `UNLOCK`-gated,
- the IMPL is updated with the size reason,
- reviewer pass is rerun, and
- tests explicitly document the residual acquisition limitation.

Preferred target is to keep both selected-route and acquisition correctness.

### WU3 - Build, Size, And RAM Gates

Run a temp assembly during development.  Before final release build, run:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_ram_bank_safety.py
```

Measure size with the snippet from the source spec.  Acceptance requires:

- `free_object_words >= 64` hard floor.
- Added object words `<= 32` unless compensating deletion keeps the floor and the IMPL is updated.
- Prefer `<= 20` added words.

### WU4 - Docs And Evidence

Update this IMPL after implementation with:

- actual files changed,
- actual object-word delta,
- exact test commands/results,
- hardware soak/probe evidence or no-hardware reason,
- unresolved Low issues,
- final acceptance status.

Do not update recommended/release combo until hardware validation passes.

## Likely Files

Code:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `src/dlcp_fw/asm/dlcp_main_v34.lst`

Tests:

- `tests/sim/test_v34_src4382_lock_hysteresis.py`
- `tests/sim/test_v34_autodetect_loss_debounce.py`
- `tests/sim/test_v34_detect_cycle_volume_excursion.py`
- `tests/sim/test_v34_diag_src_counters.py`
- optional mutation helper local to the new test file

Docs:

- `docs/SRC4382_AUTODETECT_LOCK_ROBUSTNESS_SPEC.md`
- `docs/IMPL_SRC4382_AUTODETECT_LOCK_ROBUSTNESS.md`
- optionally `docs/SRC4382_AUTODETECT_POLLING_SPEC.md` to add a superseded-note for the old selected-loss contract.

## Test Plan

Focused:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_diag_src_counters.py \
  tests/sim/test_v34_mute_refresh_bug.py
```

Simulator/model:

```bash
cargo test -p dlcp-sim src4382 --lib
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_ram_bank_safety.py
```

Broader:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q -k "v34 or v173 or src4382 or ram_bank"
```

Full sim gate if the branch touches shared I2C helpers, route/TAS dispatch, simulator core, or RAM manifest:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

## Deployment And Smoke Plan

No deploy is performed while writing this IMPL.  Runtime deployment is firmware flashing only after implementation and tests.

Hardware validation commands after flashing both MAINs and CONTROL:

```bash
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_v34_release_flash.py --info-only
PYTHONPATH=src .venv_ep0/bin/python scripts/dlcp_diag.py --json
```

Operator soak:

- Auto Detect with the known failing S/PDIF source.
- 30 minutes minimum continuous playback.
- Exercise track/rate transitions if available.
- Record before/after diagnostics and subjective/observable audio result.

No-release criteria:

- `L` or `C` grows during locked bitrate transitions.
- Route shadow changes without deliberate source change.
- Any audible filter change, dropout, or volume excursion recurs.
- MAIN size floor fails.

## Rollback

Rollback is flashing the previous known MAIN V3.4 release hex and preserving V1.73 CONTROL.  Because this work is MAIN-only and does not alter EEPROM layout, no data migration rollback is needed.

## Acceptance Criteria

- New lock-hysteresis tests fail on RXCKR-only behavior and pass after the fix.
- Existing route/TAS, mute, diagnostic, and I2C recovery tests pass.
- V3.4 release build succeeds and stays above the size floor.
- No CONTROL source or hex changes are required.
- Hardware soak confirms no spontaneous route/filter/audio changes under the source that reproduced the bug.

## Review Passes

Ten independent local review passes were run per user request.  The initial draft was revised before this final IMPL status.

| Pass | Role | Findings | Disposition |
| --- | --- | --- | --- |
| 1 | SRC datasheet correctness | High: initial draft still allowed no-route acquisition from `RXCKR != 0` while `UNLOCK == 1`. | Fixed: acquisition now requires `UNLOCK == 0` unless code size forces documented fallback. |
| 2 | MAIN size/simplicity | Medium: first design implied extra diagnostics/RAM. | Fixed: no new RAM, no new counter, reuse `0x2F3`, read `0x14` only on ambiguous paths. |
| 3 | Route/TAS contract | High: plan needed explicit ban on bypassing `cmd_dispatch_gated`. | Fixed: WU2 and acceptance preserve `ram_0x093`/`0x0AB`/`event_flags.bit1`. |
| 4 | Simulator fidelity | Medium: "simulate S/PDIF" was underspecified. | Fixed: tests use firmware-visible `0x13`/`0x14` register scripts for bitrate estimator and lock states. |
| 5 | Regression/mutation coverage | Medium: tests could pass if only threshold increased. | Fixed: mutation guard required for RXCKR-only behavior and lowered threshold. |
| 6 | Diagnostics semantics | Medium: `L` meaning could remain RXCKR-only. | Fixed: `L` is confirmed hard loss only; soft estimator holes do not increment it. |
| 7 | Hardware ops | Low: no automated acoustic detector. | Accepted: hardware soak requires operator evidence and diag snapshots; no release without it. |
| 8 | RAM/bank safety | Medium: new state could collide with bank2 diagnostics. | Fixed: no new RAM; run `test_ram_bank_safety.py`. |
| 9 | Backward compatibility | Low: acquisition-side `UNLOCK` read may slightly slow first lock. | Accepted: read occurs only after RXCKR evidence and is required for correctness; user-visible budget remains tested. |
| 10 | Lifecycle/docs | Medium: old polling spec's 1 s teardown contract could mislead implementers. | Fixed: new spec explicitly supersedes that selected-loss contract and likely-files section permits a superseded-note. |

Review gate summary:

- High findings remaining: 0
- Medium findings remaining: 0
- Low findings remaining: 2
  - No full SRC PLL/audio math model; acceptable because firmware observes registers and tests drive those registers.
  - Hardware threshold may need post-soak tuning; acceptable because release promotion is blocked on hardware evidence.

## Implementation Evidence

Status: implemented in MAIN V3.4.  CONTROL was not changed.

Final build:

```text
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
built canonical V3.4 release: firmware/patched/releases/DLCP_Firmware_V3.4.hex (EEPROM rev 0x94 -> 0x95)
```

Final size:

```text
last_used_pre_preset_b=0x4B37
free_bytes_before_0x4C00=200
free_object_words=100
delta_object_words_vs_spec_baseline=+25
```

The implementation is 25 object words over the measured spec baseline.  That
misses the preferred `<= 20` target by 5 words, but it stays within the
documented absolute `<= 32` cap and preserves the repo-pinned 200-byte V3.4
listing floor.  The extra words are not feature creep: tests exposed a second
same-route reapply source, repeated unmuted CONTROL `cmd06/data=0`, which had to
be made idempotent to stop SRC route churn during locked Auto Detect playback.

Files changed:

- `src/dlcp_fw/asm/dlcp_main_v34.asm`
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`
- `src/dlcp_fw/asm/dlcp_main_v34.lst`
- `tests/sim/test_v34_src4382_lock_hysteresis.py`
- `tests/sim/test_v34_autodetect_loss_debounce.py`
- `tests/sim/test_v34_detect_cycle_volume_excursion.py`
- `tests/sim/test_v34_diag_src_counters.py`
- `docs/IMPL_SRC4382_AUTODETECT_LOCK_ROBUSTNESS.md`

Firmware behavior implemented:

- Selected-route RXCKR zero now reads SRC4382 `0x14` and counts hard loss only
  when `UNLOCK` is set.
- Locked RXCKR holes clear the loss debounce, hold `0x093 == 0x0AB`, and do not
  increment `L`.
- No-route acquisition rejects `RXCKR != 0` candidates while `UNLOCK` is set.
- Selected-route monitor skips the receiver-select scan write and goes straight
  to status read.
- Repeated unmuted CONTROL Auto Detect `cmd06/data=0` is idempotent, so it no
  longer forces `0x0AB = 0xFF` and reapplies the same route.  The muted path
  deliberately keeps the existing refresh behavior so BUG-MUTE-REFRESH-01 still
  rewrites the zero coefficient through the retry contract.

Pre-fix red evidence:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_src4382_lock_hysteresis.py
4 failed, 3 passed in 72.84s
```

Post-fix verification:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_detect_cycle_volume_excursion.py \
  tests/sim/test_v34_diag_src_counters.py
20 passed in 205.65s
```

```text
cargo test -p dlcp-sim src4382 --lib
11 passed; 605 filtered out
```

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v32_src4382_autodetect_polling.py \
  tests/sim/test_v32_src4382_audio_path_regression.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_ram_bank_safety.py
82 passed in 76.14s
```

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py
20 passed in 34.56s
```

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 16 tests/sim -k "v34 or v173 or src4382 or ram_bank"
231 passed in 122.60s
```

Hardware evidence:

- Not run in this implementation pass.  Release promotion remains blocked until
  the hardware soak in this IMPL's deployment plan passes on the real S/PDIF
  source that reproduced the spontaneous filter/dropout behavior.

Final acceptance status:

- Simulator/model acceptance: passed.
- Size acceptance: passed, including the repo-pinned 200-byte listing floor.
- Hardware acceptance: pending.
