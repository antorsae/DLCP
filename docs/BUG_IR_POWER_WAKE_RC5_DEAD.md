# BUG-IR-POWER-WAKE-RC5-DEAD

Date: 2026-06-28

Status: implemented in CONTROL V1.73 rev `0x5A` and carried by current rev `0x5C`; focused IR/release/LCD/PB2/Field-8 gates pass; full simulator/all-tests gates pass; live hardware not run

## Summary

With CONTROL V1.73 rev `0x58` and rev `0x59`, waking the
DLCP from standby with the Hypex RC5 power key (`addr=0x10`, `cmd=0x32`) works:
CONTROL wakes, MAIN wakes, and music plays.  After that wake, real IR pulse
trains on RB5 are ignored for a long interval.  In the field this appears as
"IR worked for power on, then ceased to work; not even STBY again."

The failure is specific to the live RB5 Manchester decoder path.  Tests that
use `inject_decoded_ir_event` do not reproduce it because they bypass the RBIF
ISR and write `ir_decoded_cmd` / `ir_decoded_addr` directly.

## Affected Builds

- CONTROL: V1.73 rev `0x58` and rev `0x59` source/release line.
- Fixed in CONTROL: V1.73 rev `0x5A` / build `20260628`; current canonical follow-up is rev `0x5C` / build `20260628`.
- MAIN: V3.5 observed, but current evidence points to CONTROL-only behavior.
- Input path: real RC5 pulse train on CONTROL RB5.
- Not sufficient for reproduction: decoded-event injection.

## Reproduction Stimulus

1. Boot CONTROL V1.73 with MAIN V3.5 and wait for the Volume screen.
2. Enter standby with the front panel STBY key.
3. Wake with a real Hypex RC5 pulse train: `addr=0x10`, `cmd=0x32`.
4. Wait until CONTROL is back on the Volume screen and MAIN is playing.
5. Send a real RC5 standby endpoint: `addr=0x10`, `cmd=0x3A`.

Expected: CONTROL decodes the `0x3A` frame and emits standby frame
`B0 03 00`.

Observed before fix: CONTROL remains awake.  `ir_decoded_cmd` remains at
`0x32`, and the live decoder does not consume the `0x3A` pulse train while the
inhibit pair is still nonzero.

## Current Evidence

- `src/dlcp_fw/asm/dlcp_control_v173.asm` `isr_entry__service_portb_change_if_ready`
  checks `(Common_RAM + 28) | (Common_RAM + 27)` (`0x01C:0x01B`) before calling
  `ir_rc5_decode`.  If the pair is nonzero, the ISR clears RBIF and skips the
  live decoder.
- The configured power-key dispatch in
  `ir_dispatch_configured_or_fixed_shortcuts__match_configured_codes` writes
  `0xC350` into `0x01C:0x01B`.
- Foreground decrements that pair slowly.  In sim, after a power-key wake and
  return to Volume, the pair was still nonzero (`0xC2D7` observed in the
  reproduction run), so the next RB5 pulse train was ignored.
- After enough simulated time for the pair to drain, live IR works again.  The
  bug is therefore a long post-wake IR-deaf interval, not loss of IOC/RC5
  configuration.

## Regression Test

`tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`

The test began as a strict `xfail` and now passes for both the source-built
CONTROL fixture and the canonical V1.73 release hex.  It intentionally:

- uses a real RB5 RC5 pulse train, not `inject_decoded_ir_event`;
- avoids `_prime_for_rc5_decode`, because priming clears the failing
  `0x01B/0x01C` state;
- wakes from standby with configured power `0x32`;
- verifies the RC5 inhibit pair `0x01C:0x01B` is clear when the Volume screen
  returns, before sending the next command;
- asserts the first subsequent real standby endpoint `0x3A` is decoded and
  emits `B0 03 00`.

The `xfail` marker was removed in the rev `0x5A` implementation.

Focused evidence captured 2026-06-28:

- Normal strict-`xfail` run:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`
  produced `1 xfailed`.
- Red run with `--runxfail`:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail tests/sim/test_v171_ir_rc5_pulse_train.py::test_v173_power_wake_rearms_real_rc5_decoder_for_next_standby`
  failed at the post-wake standby check.  Final diagnostic:
  `lcd=('Volume:-17.0dB A', 'Auto Detect     ')`,
  `decoded=0x10/0x32`, `flags=0x07`, `inhibit=0x639D`.

Post-fix focused evidence captured 2026-06-28:

- Full real-RB5 pulse-train module:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v171_ir_rc5_pulse_train.py`
  -> `12 passed`.
- Canonical rev `0x5C` release hex passes the power-wake, held-repeat, and
  guard-expiry regressions.
- Full simulator gate:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q`
  -> `2100 passed, 2 skipped, 4 xfailed, 10 warnings in 1578.53s`.
- Full all-tests gate:
  `PYTHONPATH=src .venv_ep0/bin/python -m pytest tests -n 16 -q`
  -> `2100 passed, 21 skipped, 4 xfailed, 7 warnings in 1597.33s`.

## Fix Requirements

- Keep the live RC5 decoder responsive immediately after a power-key wake.
- Do not paper over the issue by priming `0x01B/0x01C` in tests or by relying
  on decoded-event injection.
- Preserve normal IR repeat suppression enough to avoid accidental double power
  toggles from one physical remote press.
- Preserve that suppression across the reconnect-exit boundary: a held power
  key that emits repeats just as the Volume screen returns must not immediately
  bounce CONTROL back to standby.
- Do not make the POWER key stale after wake: after the short repeat window
  expires, a deliberate later power press must toggle standby normally.
- Keep the change in CONTROL V1.73 unless implementation evidence proves MAIN
  also needs a change.
- Rebuild CONTROL through `scripts/build_v173_release.py` after the source fix.
- Do not flash hardware without an explicit operator step.

## Acceptance Criteria

- The new regression passes without `xfail`.
- A real-RB5 held-power-repeat test spanning reconnect exit passes.
- That held-power test uses RC5 inter-frame gaps and includes post-Volume
  same-toggle `0x32` repeats, not only frames sent while WAITING.
- A guard-expiry test proves a later deliberate POWER press still works.
- Existing live RC5 pulse-train tests still pass.
- Existing decoded IR command-matrix tests still pass.
- Wake responsiveness tests still pass.
- Full repo sim suite passes, including slow tests.
- CONTROL release metadata is bumped only by the canonical builder.

Current acceptance status: the target IR, repeat-guard, wake responsiveness,
RAM-safety, release-builder, flash-safety, canonical-artifact, LCD, PB2,
Field-8, full `tests/sim`, and full `tests` gates pass.  Live hardware was not
run; the hardware smoke remains an explicit operator-approved follow-up.
