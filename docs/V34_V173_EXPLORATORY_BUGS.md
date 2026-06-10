# V3.4/V1.73 Exploratory Bug Ledger

Last updated: 2026-06-09 — **all five bugs FIXED** (implementation + evidence in
`docs/IMPL_V34_V173_EXPLORATORY_BUGS.md`; canonical MAIN `V3.4 rev 0x80`,
CONTROL `V1.73 rev 0x41 build 20260609`)
Scope: CONTROL `V1.73` + MAIN `V3.4`

This ledger records the current-release bugs promoted from the exploratory chain
runs and source review. Each entry names the source of the bug and the focused
regression test (all implemented, un-xfailed, and green in
`tests/sim/test_v34_v173_exploratory_bug_regressions.py`).

## BUG-V34V173-1: Mute Leaks Through Volume / DSP Refresh

Symptom: after CONTROL enters mute, one or both MAINs can later write non-zero
TAS3108 register `0x30` payloads. This is real audio-state leakage, not only an
LCD/UI mismatch.

Source of bug (verified 2026-06-09 against current sources):

- MAIN `volume_cmd_handler` treats any *changed* `cmd 0x07` volume byte as an
  explicit V1.73-compatibility unmute: it clears `stock_094.bit5`,
  `active_flags.bit4`, and `active_flags.bit5`, then sets `event_flags.bit3`
  (`dlcp_main_v34.asm:2154-2176`). The comment at `:2169-2171` records the design
  assumption the bug violates — "periodic full-sync volume frames do not reach
  this branch because unchanged volume exits above".
- The V3.4 mute-refresh fix (`dlcp_main_v34.asm:1491-1500`) routes a volume-dirty
  drain back through the mute service **only while `active_flags.bit4` is still
  set**. The changed-`0x07` path above clears `active_flags.bit4` *first*, so the
  guard is bypassed and the subsequent `event_flags.bit3` -> `volume_dsp_write`
  drain writes a non-zero TAS `0x30`.
- Precondition (what makes a full-sync frame look "changed"): a host volume
  `cmd 0x07` *while muted* updates CONTROL `volume_cache (0x0B9)` without clearing
  CONTROL mute (`dlcp_control_v173.asm:1129-1147`), while MAIN keeps
  `logical_volume` unchanged via the muted volume-dirty mute-zero path
  (`dlcp_main_v34.asm:1491-1500`). The two caches diverge.
- CONTROL `full_sync_burst` step 1 then re-broadcasts `B0/07/<cache>`
  unconditionally (`dlcp_control_v173.asm:2680-2707`, `:2874-2889`). To MAIN that
  re-broadcast looks *changed* (vs its stale `logical_volume`), so it reaches the
  unmute branch and both MAINs leak a non-zero `0x30` for ~one refresh window
  until the next refresh re-mutes — the original "audio returns periodically
  after MUTE" symptom.

Status: confirmed by the 2026-06-09 coefficient exploratory pass — both an
artifact-skeptic and a source-reading firmware-skeptic returned is_real (session
card `...2ccde9ef02052428__s0009`, obs #32-37). The existing fix
(`test_v34_mute_refresh_bug.py`) only covers the *unchanged* full-sync case; the
changed-volume-while-muted case is the residual gap.

Regression test:

- `tests/sim/test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_1_changed_volume_frame_must_not_clear_user_mute`
  (MAIN-only: injects a changed `cmd 0x07` while muted — the MAIN-side root
  cause. The full-chain trigger above is host-volume-while-muted -> full-sync
  re-broadcast.)

Expected fixed behavior: while user mute is latched, a volume frame updates the
latent volume value but cannot clear MAIN mute latches or produce any non-zero
TAS `0x30` write. Only explicit mute-off, or a future protocol-level provenance
for user-volume-as-unmute, may release mute.

Fixed 2026-06-09: MAIN `volume_cmd_handler` no longer touches mute (`cmd 0x03`
is the sole mute authority); CONTROL volume keys emit an explicit `B0/03/03`
on a mute->unmute transition via `v173_volume_clear_mute_notify`, so the LCD
(which renders volume vs `Mute` from the same `control_flags.bit5`) and MAIN
audio stay coherent. Chain proof:
`test_v34_mute_refresh_bug.py::test_v173_v34_chain_volume_key_while_muted_unmutes_promptly`.
Staged-combo note: an older CONTROL (V1.71/V1.72) against fixed V3.4 unmutes a
muted volume key only at its next full-sync mute step (postponed under
key-repeat); the recommended V1.73+V3.4 pair has no such window. Fixed V1.73
against older MAINs (V3.2/V3.3) is strictly compatible — the extra explicit
`B0/03/03` lands on firmware that already honors it.

## BUG-V34V173-2: CONTROL Can Be Connected And Stuck In WAITING

Symptom: CONTROL shows `Waiting for DLCP` while both MAINs are alive and link
traffic is present. IR commands then appear dead.

Source of bug:

- CONTROL uses split connected semantics: `control_flags.CONNECTED` can be set
  by `BF/03/01` while the foreground remains inside the modal WAITING loop.
- The WAITING exit predicate is the legacy four-sentinel cache check
  (`input_select_cache`, `volume_cache`, `cmd1d_setting_cache`,
  `raw_status_cache`) rather than a fresh reconnect/status mask.
- Cold and reconnect WAITING loops poll/parse RX and scan buttons, but they do
  not call the foreground IR dispatcher. The IR ISR can clear `IR_ARMED`; no
  normal loop re-dispatches or re-arms it until DISPLAY resumes.

Regression test:

- `tests/sim/test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_2_waiting_loops_must_service_ir_and_fresh_status`

Expected fixed behavior: WAITING loops must either dispatch/re-arm IR directly
or use a shared WAITING-safe IR service, and reconnect exit must be driven by
fresh status observed during the current reconnect attempt.

Fixed 2026-06-09: both WAITING loops call `v173_waiting_ir_service`
(consume-and-re-arm; dispatching from WAITING is deliberately avoided — IR
vol-down would corrupt the 0x80 volume boot sentinel and the standby arm
toggles `control_flags.bit1`, which the WAITING flow owns). Reconnect exit now
tests `v173_reconnect_fresh_status_mask` (cleared at attempt entry; set by the
BF/05 poll answer or the BF/03/01 wake echo). Source review during the fix
also established that the legacy reconnect sentinel compare was *vacuously
true* on stale prior-session cache values — the 0x80 seed happens exactly once
at cold boot — so the old loop "reconnected" without verifying liveness at
all; the new exit is both stricter and faster (one poll round-trip).

## BUG-V34V173-3: Preset Row 0 Can Be Blank While Row 1 Shows Filename

Symptom: LCD can show row 0 as sixteen spaces while row 1 still renders a valid
preset filename, e.g. `('                ', 'Night Mode      ')`.

Source of bug:

- MAIN cannot draw or blank CONTROL LCD row 0; this is CONTROL-local.
- CONTROL clears `FNAME_ROW0_NOT_READY` after Preset entry paints row 0, but the
  bit is only invalidated on normal Preset exit.
- Standby, WAITING, reconnect, or `CONNECTED` clear can replace the physical LCD
  owner without invalidating Preset row-0 readiness or filename state.
- `v172_preset_status_patch_service` only patches row-0 suffix columns; it
  cannot reconstruct `"Preset"` after the physical row was blanked.

Regression test:

- `tests/sim/test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_3_lcd_lifecycle_must_invalidate_preset_row0_before_waiting`

Expected fixed behavior: any transition that leaves or overlays the Preset page
must set `FNAME_ROW0_NOT_READY` and suppress/reset filename rendering until the
Preset entry routine has repainted the full row-0 title and blanked row 1.

Fixed 2026-06-09: `v173_preset_lcd_invalidate` (sets `FNAME_ROW0_NOT_READY`,
clears `FNAME_VALID`) is called at cold-WAITING, standby, and reconnect
entries. Clearing `FNAME_VALID` is correct, not just defensive: the USB host
can rewrite MAIN's stored filename while CONTROL is away, so Preset re-entry
re-queries instead of trusting a stale cache.

## BUG-V34V173-4: Preset B Filename Can Stay Blank After Partial Reply

Symptom: CONTROL can show `Preset         B` with blank row 1 even though both
MAINs have non-empty B filename RAM and converged B DSP coefficients.

Source of bug:

- MAIN V3.4 emits filename replies as a paced, low-priority job, one 3-byte
  frame per service opportunity, backing off behind other chain TX work.
- CONTROL V1.73 arms a one-shot pending deadline for `cmd 0x26`.
- On parser abort or pending deadline expiry, CONTROL calls `fname_reset_blank`,
  clears `VALID`, `PENDING`, `WANT_QUERY`, and `QUERY_WAIT`, and does not retry
  while it is still on the Preset page.
- Later legal `BF/2D..4E` frames are ignored because `FNAME_PENDING` is clear.

Regression test:

- `tests/sim/test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_4_filename_abort_or_timeout_must_schedule_bounded_retry`

Expected fixed behavior: after a malformed/partial current-slot filename reply
or deadline expiry, CONTROL must schedule a bounded delayed retry while still on
Preset and connected. It must not leave `display_state_index == Preset` with an
invalid filename cache and no `PENDING`, `WANT_QUERY`, or `QUERY_WAIT` recovery.

Fixed 2026-06-09: `fname_abort` and `v172_fname_deadline_expire` now call
`fname_reset_blank_maybe_retry`, a bounded wrapper over the pre-existing
`fname_reset_and_delay_query` machinery (`FNAME_RETRY_MAX = 3` total attempts;
budget resets on success and Preset re-entry). Boundedness against a MAIN that
never answers is pinned by
`test_v34_v173_compatibility.py::test_v173_v32_old_main_filename_query_times_out_blank`
(exactly 3 queries, then terminally quiet and blank).

## BUG-V34V173-5: Preset Broadcast Dropped During USB Filename Write (cross-PB desync)

Symptom: a preset-change broadcast that arrives at a MAIN while that MAIN has an
in-flight USB `cmd 0x03` filename WRITE (`filename_dirty_flags.bit6` set) is
silently dropped on that unit. If only one of the two chained MAINs is mid-write,
the two end on *different* active presets (and different DSP coefficients) until
CONTROL's `full_sync_burst` re-broadcasts the preset (~6 s; longer under sustained
host/USB traffic that keeps debouncing the full-sync counter).

Source of bug (verified against current sources):

- `preset_select_handler` gates the broadcast on `filename_dirty_flags.bit6`:
  `btfsc filename_dirty_flags_b0, 6 / bra preset_select_handler_done` runs
  **before** `movwf preset_job_target_b2` (`dlcp_main_v34.asm:9974-9994`). So while
  bit6 is set the broadcast is dropped and the requested target is **not stored**.
- The handler's own header contract (`dlcp_main_v34.asm:9957-9972`) says the
  target **should be recorded** during the gate and picked up once
  `main_core_service_265c` clears bit6 after persist. The implementation
  contradicts the header (inline comment at `:9976-9979` admits "Target NOT
  stored"); recovery instead depends on the ~6 s CONTROL full-sync re-broadcast.

Status: the USB-filename-write trigger was confirmed by the 2026-06-09 exploratory
pass (both skeptics is_real; see
`artifacts/sim/.../hunt20260609/FINDING_preset_drop_during_usb_filename_write.md`).
A related IR-preset variant (a broadcast reaching only one MAIN) was split-verdict
in the coefficient pass — the artifact-skeptic found a real cross-PB divergence,
the firmware-skeptic judged it expected/self-healing — so this entry is scoped to
the source-grounded contract violation, not the IR variant.

Regression tests:

- `tests/sim/test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_5_preset_select_must_record_target_independent_of_usb_gate`
  (structural: no drop-gate in the handler; PENDING parks; HOLDING backstop
  stays — amended from the original `..._must_record_target_before_usb_gate`,
  which pinned the redundant entry-gate mechanism rather than the contract)
- `tests/sim/test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_5_preset_broadcast_defers_until_usb_gate_clears`
  (behavioral: broadcast mid-write is recorded and parked un-muted, then
  applied as soon as the gate clears)

Expected fixed behavior: `preset_select_handler` must record the requested preset
target before (or independent of) the `filename_dirty_flags.bit6` USB-filename
gate, so a broadcast arriving mid-write is deferred and applied when the gate
clears — not dropped and left to the ~6 s full-sync re-broadcast. Severity is
LOW-MEDIUM: real cross-PB desync, but narrow (needs a preset change to coincide
with a concurrent HFD filename write) and self-healing.

Fixed 2026-06-09 by deletion: the parser-entry gate was redundant defense in
the wrong layer — the HOLDING->APPLY transition already carries a bit6
backstop immediately before `preset_load_filename` (the only code that can
clobber the host's in-flight filename RAM), and `main_core_service_265c`
already tolerates the job persisting concurrently. The handler now always
records the target; a new 2-word PENDING park keeps the deferred job un-muted
until the host's `force_persist` clears bit6, after which the switch applies
within one persist + hold window instead of the ~6 s full-sync re-broadcast.
