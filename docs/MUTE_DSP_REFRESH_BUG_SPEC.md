# Mute DSP Refresh Bug Spec

Date: 2026-06-09
Status: active bug, simulator red test added as strict xfail
Scope: MAIN V3.4 with CONTROL V1.73 release pair
Bug ID: BUG-MUTE-REFRESH-01

## Summary

On live hardware, pressing MUTE mutes audio, but audio periodically returns for
about one second every few seconds.  The simulator reproduces the core failure
inside MAIN V3.4 without CONTROL or IR involvement: a later input/route refresh
clears the user-mute state and writes a non-zero TAS3108 volume coefficient.

The visible result is that CONTROL can still believe mute is active while the
DSP volume coefficient is no longer zero.

## Evidence

Regression test added:

- `tests/sim/test_v34_mute_refresh_bug.py::test_v34_user_mute_survives_input_route_refresh`

Current expected-red behavior:

```text
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py
-> 1 xfailed

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail tests/sim/test_v34_mute_refresh_bug.py
-> fails with active=0x28, events=0x80, dsp30=00120bdb
```

Deterministic reproducer:

1. Boot canonical `DLCP_Firmware_V3.4.hex` in the Rust MAIN-only simulator.
2. Inject `B0 03 02` (`cmd 0x03`, mute on).
3. MAIN sets `active_flags.bit4` and `active_flags.bit5`, and TAS3108 register
   `0x30` is written as `00000000`.
4. Inject `B0 06 00` (`cmd 0x06`, Auto Detect/input refresh).
5. MAIN currently clears `active_flags.bit4`, leaves `active_flags.bit5`, and
   TAS3108 register `0x30` is written as `00120bdb`.

Relevant code evidence:

- `src/dlcp_fw/asm/dlcp_main_v34.asm` `cmd03_mute_on_handler` sets user mute
  and schedules the mute-DSP refresh.
- `src/dlcp_fw/asm/dlcp_main_v34.asm` `cmd06_input_select_handler` forces route
  re-evaluation.
- `src/dlcp_fw/asm/dlcp_main_v34.asm` `poll_src4382_route_monitor` can set
  `event_flags.bit1` for route refresh after input/SRC housekeeping.
- `src/dlcp_fw/asm/dlcp_main_v34.asm` `cmd_dispatch_gated` handles
  `event_flags.bit3` by clearing `active_flags.bit4` unless `event_flags.bit5`
  is already set in the same pass, computes a non-zero coefficient, and calls
  `volume_dsp_write`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm` `full_sync_burst` periodically emits
  volume, input, mute, cmd1d, standby/wake, and preset as separate frames, so a
  MAIN-side input/route refresh can recur during ordinary operation.

## Required Behavior

Mute is a target state, not a best-effort last write.  While user mute is
active, any path that refreshes TAS3108 volume coefficient `0x30` must either
write `00000000` or avoid writing a non-zero coefficient.

Required invariants:

1. `cmd 0x03 data 0x02` is the primary user-mute-on command.  After it is
   applied, `active_flags.bit4` and the DSP coefficient must remain muted until
   an explicit unmute path runs.
2. `cmd 0x03 data 0x03` is the primary user-mute-off command.  It may restore
   the latent logical/computed volume coefficient.
3. Automated refreshes, including input/route refresh, SRC4382 Auto Detect
   route reconciliation, CONTROL periodic full-sync input frames, wake/reapply
   route refresh, and DSP retry/recovery, must not clear user mute or write a
   non-zero coefficient while user mute is active.
4. Preset force-mute remains distinct from user mute.  Preset commit/cancel may
   restore volume only when MAIN itself forced the mute and the user did not
   request mute during the job.
5. Existing verified-write behavior must remain: successful writes clear the
   dirty bit and copy computed volume to logical volume only after TAS3108 ACK;
   NACK/retry/fault behavior must stay bounded and visible.
6. CONTROL should not need a timing workaround.  The robust fix belongs in MAIN
   unless implementation evidence proves a CONTROL bug too.

## Similar Bug Search

The following surfaces must be audited and, where practical, covered by tests:

- Direct input/route refresh after mute: confirmed reproducer, current strict
  xfail.
- Fixed-input refresh after mute: confirmed by exploratory sim on 2026-06-09;
  `B0 06 05` after `B0 03 02` currently leaves `active=0x28` and
  `dsp30=00120bdb`.
- Natural V1.73/V3.4 full-chain cadence: CONTROL full-sync emits input and mute
  as separate frames, so the direct MAIN bug is reachable during normal use.
- Explicit fixed-input and SRC4382 Auto Detect route reconciliation: these use
  the same route-refresh and TAS coefficient path.
- Standby/wake while muted: confirmed by exploratory sim on 2026-06-09;
  after `B0 03 00` then `B0 03 01`, wake/reapply currently leaves
  `active=0x28` and `dsp30=00120bdb`.
- HID/settings import: the HID path can set `event_flags.bit3` and also imports
  a persisted mute bit.  The fix must preserve explicit imported mute state but
  avoid accidental non-zero coefficient writes while imported/user mute is true.
- Wake/reconnect/reapply: wake writes zero coefficient, reapplies tables, then
  schedules input/volume/preset reconciliation.  If user mute is still active,
  this must not restore a non-zero coefficient.
- Preset commit/cancel: this has deliberate forced-mute release semantics and
  should be regression-tested so the fix does not make preset switching stay
  muted when MAIN forced mute and the user did not.
- Explicit volume commands while muted: exploratory sim on 2026-06-09 shows an
  unchanged volume frame does not write, but a changed volume frame currently
  clears mute and writes a non-zero coefficient.  Implementation must either
  preserve this intentionally with a named compatibility test, or adopt the
  stronger target-state rule that volume changes update latent volume but do
  not unmute without `cmd 0x03 data 0x03`.
- Preset select while already muted: exploratory sim on 2026-06-09 did not
  reproduce a non-zero TAS coefficient write for `B0 20 01`; keep this as a
  green regression surface because preset apply uses related forced-mute state.

## Tests Required For Closure

At minimum:

- Convert the current strict xfail in `tests/sim/test_v34_mute_refresh_bug.py`
  into a normal passing regression.
- Add full-chain V1.73/V3.4 coverage proving a mute-on state survives periodic
  full-sync input/route refresh and both MAINs retain TAS3108 coefficient
  `0x30 == 00000000`.
- Add explicit unmute coverage proving `cmd 0x03 data 0x03` restores the
  non-zero coefficient after mute.
- Add SRC4382 Auto Detect/fixed-input coverage while muted, reusing existing
  `test_v32_src4382_autodetect_polling.py` helpers where possible.
- Add wake/reconnect or standby/wake coverage if code audit shows the wake
  reapply path can schedule a non-zero refresh while muted.
- Add preset forced-mute regression coverage so preset switch commit/cancel
  still restores volume only when appropriate.

## Non-Goals

- Do not change CONTROL full-sync cadence merely to hide this bug.
- Do not remove TAS3108 verified-write/NACK retry behavior.
- Do not add sleep/retry timing guards as the primary fix.
- Do not broaden into unrelated V3.4/V1.73 refactors.

## Acceptance Criteria

- All new BUG-MUTE-REFRESH-01 tests pass without xfail.
- The focused test command for the new bug tests passes.
- The relevant existing SRC4382, preset, standby/wake, and V3.4/V1.73 tests pass.
- Built V3.4 MAIN size delta is recorded, including whether free space changed.
- Any hardware run is documented separately; sim closure is required before live
  hardware retest.
