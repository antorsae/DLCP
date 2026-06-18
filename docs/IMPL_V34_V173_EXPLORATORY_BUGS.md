# V3.4/V1.73 Exploratory Bug Fixes — Implementation Plan

Date: 2026-06-09 (rev 3 — implemented; rev 2 was the post-design-review plan:
BUG-5 redesigned around the existing HOLDING gate, BUG-2 reconnect analysis
corrected against source)
Status: Implemented — sim verified, full `tests/sim` gate green; no live flash
performed (hardware smoke remains the release gate). See Post-Implementation
Evidence at the end of this document.
Source spec: `docs/V34_V173_EXPLORATORY_BUGS.md`
Scope: canonical MAIN `V3.4` (`src/dlcp_fw/asm/dlcp_main_v34.asm`) and CONTROL
`V1.73` (`src/dlcp_fw/asm/dlcp_control_v173.asm`) only. No version promotion.

Regression file (strict xfails to flip green):
`tests/sim/test_v34_v173_exploratory_bug_regressions.py`. BUG-5's regression
needs a contract amendment (see its section) — the other four flip as-is.

## Guiding Principle

Each bug has exactly one root cause, and three of the five reduce to the same
shape: **a piece of state is mutated, dropped, or abandoned by a code path that
does not own it.** The other two are **modal-loop liveness** failures: a loop or
a one-shot stops doing the recovery work the rest of the firmware relies on.

| Bug | Class | One-line root cause | Fix shape |
|-----|-------|---------------------|-----------|
| 1 | Wrong owner | A *volume* frame clears *mute* | MAIN: `cmd 0x03` is the sole mute authority (`cmd 0x07` never touches mute). CONTROL: volume keys emit the explicit `B0/03/03` they already imply |
| 2 | Liveness | WAITING loops never re-arm IR; reconnect "exit check" is vacuous (stale caches) | Re-arm IR each WAITING iteration; exit reconnect on status freshly observed *this* attempt |
| 3 | Wrong owner | LCD transitions don't invalidate Preset row-0 readiness | One `invalidate` call at each transition that overlays the Preset page |
| 4 | Liveness | Filename FSM *gives up* on abort/timeout | Bounded delayed retry instead of permanent blank |
| 5 | Wrong owner | A redundant parser-entry gate *drops* the preset target | Delete the entry gate; the job machinery already defers safely (existing HOLDING gate + new 2-word PENDING park) |

The fixes are deliberately small. None introduces a new background task, a new
protocol command, or a cadence/retry hack as the *primary* mechanism. Each
reuses an existing, already-verified code path — BUG-5 in particular turns out
to be a **deletion**, because the safe deferral it needs already exists in the
job state machine.

## Required Reading

- `docs/V34_V173_EXPLORATORY_BUGS.md` (the ledger this plan closes)
- `docs/IMPL_MUTE_DSP_REFRESH_BUG.md` (the V3.4 mute latch this builds on)
- `docs/IMPL_PRESET_FILENAME_LCD.md`, `docs/IMPL_REFACTORING_V34_V173.md`
- `docs/REFACTORING_V34_V173_SPEC.md` (chain-TX, Preset lifecycle, I2C contracts)
- `docs/V163B_DIAGNOSTICS_MENU_SPEC.md`, `docs/V32_DIAG_TIER1_SPEC.md`
- `docs/SIMULATION.md`, `docs/TEST_SIMULATOR.md`
- `RAM_BANK_SAFETY_IMPL.md` (both images must re-pass RAM-bank safety)

---

## BUG-V34V173-1 — Mute leaks through a volume/full-sync refresh

### Root cause (confirmed against current sources)

MAIN owns two mute facts: the *user-mute latch* (`stock_094.bit5`) and the
*effective-mute* / *shadow* pair (`active_flags.bit4`/`bit5`). The V3.4 mute
fix added a guard so a *volume-dirty* drain re-mutes instead of leaking, **but
only while `active_flags.bit4` is still set** (`dlcp_main_v34.asm:1491-1500`):

```asm
cmd_dispatch_gated__check_reconnect_and_volume_dirty:
    movlb       0x0
    btfss       event_flags_b0, 3, BANKED          ; volume dirty?
    bra         cmd_dispatch_gated__check_reconnect_reapply
    btfss       active_flags_acc, 4, ACCESS        ; <-- guard reads bit4
    bra         cmd_dispatch_gated__apply_unmuted_volume_dirty
    bsf         event_flags_b0, 5, BANKED          ; muted -> re-mute (zero write)
    bra         cmd_dispatch_gated__check_reconnect_reapply
```

The defeat is upstream: `volume_cmd_handler` treats **any changed `cmd 0x07`**
as an implicit unmute and clears the latch *and* `bit4`/`bit5` **before** the
guard runs (`dlcp_main_v34.asm:2167-2176`):

```asm
uart_link_parser__volume_mark_dirty:
    bsf         event_flags_b0, 3, BANKED          ; volume dirty
    ; Real user volume movement is a V1.73 compatibility unmute. ...
    bcf         main_runtime_latch_flags_b0, 5, BANKED            ; <-- clears user-mute latch
    bcf         active_flags_acc, 4, ACCESS        ; <-- clears effective mute
    bcf         active_flags_acc, 5, ACCESS        ; <-- clears shadow
```

With `bit4` cleared, the guard at `:1497` takes the *unmuted* branch and the
drain writes a non-zero TAS `0x30`. A volume frame looks "changed" to MAIN even
when no human touched the volume, because of a cache divergence:

- A host `cmd 0x07` **while muted** updates CONTROL `volume_cache (0x0B9)` and
  sets the changed flag but does **not** touch CONTROL mute
  (`dlcp_control_v173.asm:1129-1147`). MAIN keeps `logical_volume` unchanged via
  the muted mute-zero path. The two caches now diverge.
- CONTROL `full_sync_burst` step 1 (`volume_frame_send`,
  `dlcp_control_v173.asm:2874-2889`) re-broadcasts `B0/07/<cache>`
  unconditionally every cycle. To MAIN that re-broadcast is "changed" vs its
  stale `logical_volume`, so it hits the unmute branch and leaks for ~one
  refresh window until step 3 re-mutes.

The deeper truth: **`cmd 0x07` and `cmd 0x03` are indistinguishable provenance
on the wire** — a host/full-sync volume frame and a real volume-key volume frame
are byte-identical. A MAIN-only heuristic *cannot* tell them apart, so it must
not try.

### The reliable signal already exists

The protocol already carries mute on its own dedicated channel, `cmd 0x03`
(data `0x02`=on, `0x03`=off), and CONTROL broadcasts it every full-sync cycle
(step 3, `mute_frame_send`, `dlcp_control_v173.asm:2970-2989`). Crucially, a
**real** user volume action while muted *does* produce an explicit unmute, while
a host/full-sync volume frame does not:

- IR volume up/down clear CONTROL local mute then send the volume frame
  (`bcf control_flags,5` at `dlcp_control_v173.asm:3282` and `:3304`).
- Front-panel volume up/down do the same (`:7007`, `:7024`).
- With `control_flags.bit5` clear, the next `mute_frame_send` emits `B0/03/03`.
- The host volume RX path (`:1129-1147`) and `volume_frame_send` (`:2874-2889`)
  **never** clear `control_flags.bit5`, so they never produce `B0/03/03`.

Therefore `cmd 0x03` is a sound *sole* authority for mute on MAIN.

### Fix (MAIN — root cause)

Delete the three mute-clearing instructions from `volume_cmd_handler` and rewrite
the comment to state the new contract. `dlcp_main_v34.asm:2167-2176` becomes:

```asm
uart_link_parser__volume_mark_dirty:
    bsf         event_flags_b0, 3, BANKED          ; volume dirty -> verified write
    ; V3.4 BUG-V34V173-1: a volume frame updates the latent volume only.
    ; Mute is owned EXCLUSIVELY by cmd 0x03. A real user volume key while
    ; muted is unmuted by the B0/03/03 CONTROL emits after clearing its
    ; local mute; host/full-sync volume frames carry no such provenance and
    ; must not clear mute. While active_flags.bit4 is set the volume-dirty
    ; drain (asm:1491-1500) routes through the verified mute-zero path.
    ; V3.1 Fix B': do NOT copy computed->logical here (deferred to volume_dsp_write)
    bra         uart_link_parser__handler_return_tail
```

That is the entire MAIN change: three `bcf` words removed (−3 words). A changed
`cmd 0x07` while muted now follows the **identical** path as a muted route
refresh (`cmd 0x06`): set `event_flags.bit3`, hit the guard with `bit4` still
set, route to the verified zero write (`tas3108_write_zero_volume_coeff` ->
`volume_dsp_write`), which clears `bit3` on ACK (`:9895`) or exhausted NACK
(`:9932`) and copies `computed_volume` (the new latent value) to
`logical_volume` on ACK — so the next identical full-sync re-broadcast compares
*unchanged* and exits early. No repeated dirty churn; the latent volume is
applied on the next explicit unmute. The user-mute latch and shadow survive
untouched.

### Why this is correct and minimal

- The resulting code path is already proven green by
  `test_v34_user_mute_survives_input_route_refresh` (muted `cmd 0x06`, sets
  `bit3`, stays muted, zero `0x30`) and
  `test_v34_muted_zero_write_uses_volume_retry_contract` (the muted zero write
  goes through the `volume_dsp_write` ACK/NACK/fault contract). The only thing
  `volume_cmd_handler` did differently was pre-clear `bit4`; removing that makes
  changed-volume behave like those proven cases.
- Explicit unmute (`cmd 0x03 data 0x03`) and the user-mute latch are untouched,
  so `test_v34_explicit_mute_off_unmutes_even_after_refreshes` and the HID
  import latch tests keep passing.
- A useful ownership side effect: SRC4382 non-PCM *auto*-mute (which also sets
  `bit4`) can no longer be cleared by a passing volume frame either — only its
  owner (the SRC source-recovery monitor) releases it, exactly as
  `test_v34_src4382_non_pcm_auto_mute_releases_but_user_mute_does_not` expects.
- It *removes* code, so it gives MAIN size headroom rather than consuming it.

### Test-contract change (must be done in the same change)

`test_v34_v173_exploratory_bug_regressions.py::test_bug_v34v173_1_changed_volume_frame_must_not_clear_user_mute`
(MAIN-only) asserts the new behavior and flips from strict-xfail to pass.

**This directly contradicts an existing green test.**
`test_v34_mute_refresh_bug.py::test_v34_explicit_user_volume_change_unmutes_for_v173_compatibility`
injects the *same* stimulus (a bare changed `cmd 0x07` while muted) and asserts
the opposite (`_assert_unmuted_with_nonzero_volume_coeff`). Both cannot hold for
a deterministic MAIN, and the ledger's "Expected fixed behavior" makes the new
behavior canonical. That test encodes the *old, buggy* heuristic and must be
rewritten to express V1.73 compatibility as the **real chain sequence**, with an
interim assertion pinning both halves of the contract:

```python
def test_v34_explicit_user_volume_change_unmutes_for_v173_compatibility(...):
    chain = _boot_v34_main(v34_mute_hex)
    _mute_main(chain)
    current = (chain.read_main_reg(0, LOGICAL_VOLUME) + 0x60) & 0xFF
    changed = (current + 4) & 0x7F
    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x07, changed)   # CONTROL would have cleared its mute first
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    _assert_user_muted_with_zero_volume_coeff(chain)   # bare volume frame: still muted
    chain.reset_main_dsp_write_log(0)
    _inject_frame(chain, 0x03, 0x03)      # ...and emitted B0/03/03 (the real unmute)
    chain.step_ticks(COMMAND_SETTLE_TICKS)
    _assert_unmuted_with_nonzero_volume_coeff(chain)
```

Rename if desired (e.g. `..._unmutes_via_cmd03`).

### Required companion (CONTROL — chain consistency, not just responsiveness)

The MAIN fix alone is incomplete because it would create the inverse bug. On
CONTROL the volume-screen render is gated on the **same** `control_flags.bit5`
that a volume key clears (`dlcp_control_v173.asm:6897`: `btfsc control_flags,5`
-> `lcd_str_mute`, else render the dB volume at `:6899-6941`). So a volume key
while muted *instantly* makes CONTROL show "unmuted + new volume" and update
`volume_cache`. But the four volume-key handlers (IR `:3282`/`:3304`, front
panel `:7007`/`:7024`) clear `bit5` and send **only** `volume_frame_send` — no
explicit mute frame. They were relying on MAIN's now-removed heuristic for the
unmute.

With MAIN strict, MAIN stays muted until the next full-sync step-3 `B0/03/03` —
and that can be *indefinitely* postponed: `volume_frame_send` resets the
full-sync counter pair on every send (`:2887-2888`), so a held/repeating volume
key keeps debouncing the burst and the mute-off step never fires while the user
is actively turning the volume up. Result: **CONTROL LCD counts the volume up
while MAIN stays silent** for the whole key-repeat plus up to a sync cycle — a
sustained UI/MAIN disagreement that trades one bug for another.

The mute *key* already does the right thing: IR mute toggle (`:3322` `btg
control_flags,5` then `:3329` `rcall mute_frame_send`) and the front-panel mute
button (`:7034`/`:7039`) emit the explicit frame synchronously. The volume keys
must do the same on a mute->unmute transition. Add one DRY helper and call it
from the four volume-key sites in place of the bare `bcf control_flags,5`:

```asm
v173_volume_clear_mute_notify:        ; clear local mute + notify the chain
    btfss   control_flags_acc, 0x5, A ; only on a real mute->unmute transition
    return  0x0                       ; not muted -> no extra chain traffic
    bcf     control_flags_acc, 0x5, A
    goto    mute_frame_send           ; tail-call: emits B0/03/03 promptly
```

`mute_frame_send` is the exact sender the mute key already calls from these same
foreground contexts, so no new TX-arbitration surface is introduced. A volume
key while muted then emits `B0/03/03` **and** `B0/07/<vol>`; MAIN unmutes
immediately and applies the new level, coherent with the LCD. The frame order is
irrelevant — the explicit-unmute path re-applies the latent volume
(`test_v34_explicit_mute_off_unmutes_even_after_refreshes`), so volume-then-
unmute and unmute-then-volume both converge. When not muted the helper is a
no-op, so volume changes on an already-live chain add no extra frames. Keep the
existing per-site reachability exactly: the IR handlers skip the `bcf` entirely
at the volume rails (`:3279-3280`, `:3300-3302`) while the front-panel handlers
do not — the helper replaces only the `bcf`, preserving each site's current
rail behavior.

Add a chain regression (reuse `test_v34_mute_refresh_bug.py` chain helpers:
`_boot_v173_v34_chain`, `mark_ctl_tx_capture_point`, `ctl_tx_record_since_last_capture`):
inject IR volume while muted and assert (a) a `B0/03/03` appears promptly in
CONTROL TX without waiting for a full-sync cycle, and (b) both MAINs end unmuted
with the new non-zero `0x30` — i.e. no window where CONTROL shows volume but a
MAIN is muted.

### Staged-combination compatibility (accepted behavior change)

With an **older CONTROL** (V1.71/V1.72) paired against fixed V3.4, a volume key
while muted updates the CONTROL LCD immediately but MAIN unmutes only when that
CONTROL's full-sync mute step fires (postponed further under key-repeat, as
above). This is the price of removing the unsound heuristic and is bounded by
the full-sync cadence; the recommended V1.73+V3.4 pair has no such window.
Conversely, fixed V1.73 against older MAINs (V3.2/V3.3) is strictly better than
today: the extra explicit `B0/03/03` lands on firmware that already honors it,
and the old MAIN heuristic becomes redundant rather than harmful. State this in
the ledger entry when closing the bug, and re-run
`tests/sim/test_v34_v173_compatibility.py` for the staged combos.

---

## BUG-V34V173-2 — Connected but stuck in WAITING; IR appears dead

### Root cause (verified, sharper than the ledger wording)

Three findings, all verified against the current source:

1. **No IR re-arm in WAITING.** The cold loop (`flow_ccs_0FA0_118C`,
   `dlcp_control_v173.asm:6363-6483`) and the reconnect loop
   (`v171_reconnect_wait_body`, `:6708-6813`) each call only
   `button_scan_debounce`, `poll_frame_send`, `delay_short`, `rx_parser_entry`,
   `v171_service_rx_frame_gap`. Neither runs the foreground IR dispatcher
   (`control_core_service_0DCE`), which contains the only `bsf
   control_flags,IR_ARMED` re-arm sites (`:3456`, `:3487`, `:3514`, `:3536`).
   The IR ISR clears `IR_ARMED` when it captures a frame; if that happens while
   a WAITING loop is foreground, nothing re-arms the decoder until DISPLAY
   resumes — IR is dead for the whole WAITING residence.
2. **The four-sentinel caches are seeded exactly once, at boot.** The only
   `0x80` seed of `input_select_cache/volume_cache/cmd1d_setting_cache/
   raw_status_cache` is at `:6341-6345`, immediately before the cold loop. The
   cold loop's all-four-`!= 0x80` exit (`:6452-6473`) is therefore a real boot
   handshake: MAIN's status-burst replies must overwrite all four.
3. **The reconnect loop reuses the same predicate on *unseeded* caches**
   (`:6760-6785`), and `reconnect_wait_loop` (`:6670-6706`) clears only its
   retry and grace counters — it never re-seeds the caches. After a session has
   run, all four caches hold legitimate non-`0x80` values, so the reconnect
   "exit check" is **vacuously true on the first iteration**: it measures
   history, not whether *this* MAIN answered *this* attempt. The loop then
   unconditionally sets `CONNECTED` (`:6825`) and resumes, alive MAIN or not.
   Meanwhile the RX path can independently set `CONNECTED` from a `BF/03/01`
   (`:1039`) while a WAITING loop is foreground — the split semantics the
   ledger describes.

So the two WAITING loops fail in *opposite* directions: cold is strict
(correctly so — but with IR dead while it holds), reconnect verifies nothing.
The regression test pins the contract: both loops must service/re-arm IR, the
reconnect exit must be driven by status freshly observed during the current
attempt, and `raw_status_cache_b0` must vanish from the reconnect body.

### Fix (CONTROL)

**(a) WAITING IR service: consume + re-arm, do not dispatch.** Add:

```asm
v173_waiting_ir_service:
    btfsc   control_flags_acc, IR_ARMED, A   ; armed -> no pending frame
    return  0x0
    bsf     control_flags_acc, IR_ARMED, A   ; discard the frame, re-arm decoder
    return  0x0
```

and invoke it once per iteration in **both** loop bodies, next to the existing
`rx_parser_entry` calls (cold `:6449-6451`, reconnect `:6738-6739`). It must be
invoked with `call v173_waiting_ir_service, 0x0` — the regression regex is
`\bcall\s+...`, which an `rcall` does not match.

Deliberately *not* dispatching IR commands from WAITING is the safe and simple
choice, for two source-verified reasons:

- The IR volume-down arm decrements `volume_cache` and broadcasts it
  (`:3300-3305`). During **cold** WAITING the cache holds the `0x80` boot
  sentinel; one vol-down press would corrupt the sentinel to `0x7F` (falsely
  satisfying ¼ of the handshake) *and* later broadcast an out-of-range volume.
- The IR standby arm toggles `control_flags.bit1` (`:3265`), which doubles as
  the awake/CONNECTED state the WAITING/reconnect flow itself sequences
  (`:6620`, `:6651`, `:6668`, `:6825`) — dispatching it mid-loop corrupts the
  modal state machine.

Discarding while re-arming loses at most the keypresses pressed *during* a
WAITING residence (there is no connected MAIN to act on them); it permanently
fixes "IR dead", and with fix (b) the reconnect residence is as short as the
chain physically allows. This satisfies the ledger's "dispatch/re-arm IR
directly **or** use a shared WAITING-safe IR service".

**(b) Fresh reconnect status mask.** Add one bank-0 RAM byte
`v173_reconnect_fresh_status_mask` (bank 0 so the parser and the loop, both
running BSR=0, touch it without `movlb` churn). Wiring:

- **Clear at entry**: one `clrf` in the `reconnect_wait_loop` init block
  (`:6690-6706`), beside the retry/grace clears.
- **Set on fresh evidence**, in the RX parser:
  - primary: `bsf ...mask, 0` in the `BF/05` accept path (`:1094-1097`, where
    `raw_status_cache` is stored). This is the definitive poll answer: the
    WAITING loops emit `B1/04` status polls every iteration, MAIN's reply burst
    carries `BF/05`, and the poll bypasses MAIN's active gate so **even a MAIN
    still in standby answers** (`poll_frame_send` header, `:2727-2730`) — the
    wake-from-standby reconnect exits on the first round-trip.
  - secondary: `bsf ...mask, 1` beside the `BF/03/01` wake echo (`:1039`), a
    fast-path for MAINs that lead with the wake echo.
- **Exit**: replace the reconnect four-sentinel block (`:6760-6785`, ~26 words)
  with a two-word test — `movf ...mask, W, B` / `bnz v171_reconnect_wait_done`.
  The cold loop keeps its sentinel exit unchanged.

Net effect: reconnect completion now *requires* a frame received during this
attempt (strictly stronger than today's vacuous check) yet completes in one
poll round-trip against any live MAIN (strictly faster than a four-frame
handshake when frames are being dropped). The caches are left alone — they keep
CONTROL's authoritative volume/input/setup values across the reconnect, which
full-sync re-asserts to MAIN after resume. The 8-iteration UART soft-recovery
(`:6786-6813`) stays and now actually matters, since the loop can genuinely
persist while a MAIN is dead. `raw_status_cache_b0` disappears from the
`v171_reconnect_wait_body..v171_reconnect_wait_done` body, as the regression
demands. CONTROL shrinks ~20 words net.

The split `CONNECTED` semantics (RX can set it mid-WAITING) are left as-is:
with the reconnect exit now fresh-evidence-driven, the foreground no longer
depends on `CONNECTED` to leave WAITING, and changing its ownership is out of
scope for this ledger entry.

### Test

`test_bug_v34v173_2_waiting_loops_must_service_ir_and_fresh_status` flips green:
both WAITING bodies `call` an IR service; `v173_reconnect_fresh_status_mask`
exists; the reconnect body no longer references `raw_status_cache_b0`. Re-run
`test_robustness_waiting.py`, `test_chain_gpsim_waiting.py`,
`test_reconnect_wake_gate.py`, `test_v171_v31_chain.py`, and
`test_v171_v32_standby_reconnect.py` to confirm no WAITING/reconnect
regression. Worth adding (cheap): a behavioral chain test that powers a MAIN
off, enters reconnect WAITING, asserts CONTROL *stays* in WAITING (it would
previously exit instantly on stale caches), then powers the MAIN on and asserts
prompt exit.

---

## BUG-V34V173-3 — Preset row 0 blank while row 1 shows a filename

### Root cause (confirmed)

Row-0 readiness is owned by `FNAME_ROW0_NOT_READY`
(`v172_fname_row0_status_snap.bit7`). Preset entry paints row 0 then **clears**
the bit (`dlcp_control_v173.asm:3714`); normal Preset exit **sets** it
(`:3827`). Row-1 filename rendering is gated on the bit being clear — the whole
`v172_preset_filename_service` returns early when it is set (`:5189-5192`).

But standby, cold WAITING, reconnect, and `CONNECTED`-clear can overlay the
physical LCD (standby `zzz` at `:6624-6630`, `Waiting for DLCP` at `:6348-6354`
and `:6653-6660`) **without** invalidating row-0 readiness. The bit stays
clear, so the filename machinery still believes its row-0 title is on the
glass and repaints row 1 — exactly the `('                ', 'Night Mode      ')`
symptom. MAIN cannot draw or blank CONTROL row 0; this is wholly CONTROL-local.

### Fix (CONTROL)

Add a tiny shared helper `v173_preset_lcd_invalidate`:

```asm
v173_preset_lcd_invalidate:
    movlb   0x02
    bsf     v172_fname_row0_status_snap_b2, FNAME_ROW0_NOT_READY, BANKED
    bcf     v172_fname_flags_b2, FNAME_VALID, BANKED   ; row1 must not render stale text
    movlb   0x00
    return  0x0
```

Call it once at each transition that overlays/leaves the Preset page:

- cold WAITING entry — inside `flow_ccs_0FA0_118C`. Note the label is also the
  loop-back target (`bra flow_ccs_0FA0_118C` at `:6473`), so a call placed in
  the body runs per-iteration; the helper is idempotent and the loop period is
  ~10 ms, so this is fine (and self-healing). No loop restructuring needed.
- standby/WAITING entry — `flow_display_state_entry_1250` body (`:6618-6630`),
  runs once per standby entry.
- reconnect WAITING entry — `reconnect_wait_loop` init block (`:6690-6706`),
  runs once per reconnect attempt (the loop-back target is
  `v171_reconnect_wait_body`, not this label).

Setting `FNAME_ROW0_NOT_READY` suppresses the entire filename service until
Preset entry repaints the full row-0 title and clears the bit. Clearing
`FNAME_VALID` additionally drops the cached filename, which is *correct* and
not just defensive: while CONTROL is in standby/WAITING the USB host can talk
to MAIN directly and rewrite the stored filename, so a cache carried across
those transitions is untrustworthy — re-entry re-queries (bounded, existing
machinery). This is the same invalidation Preset *exit* already performs
(`:3827` + `fname_reset_blank` when invalid); we are making every
owner-changing transition perform it too.

### Test

`test_bug_v34v173_3_lcd_lifecycle_must_invalidate_preset_row0_before_waiting`
flips green (each of the three entry bodies contains the invalidation token —
the token regex matches the helper name at the call sites, so `rcall`/`call`
both work here). Re-run `tests/sim/test_preset_filename_lcd_spec.py` (esp. the
V1.73/V3.4 native chain row-0 ordering / standby-wake survival cases) to
confirm no Preset-page regression.

---

## BUG-V34V173-4 — Preset B filename stays blank after a partial reply

### Root cause (confirmed)

MAIN emits filename replies as a paced low-priority job (one `BF/2D..4E` frame
per opportunity). CONTROL arms a one-shot `cmd 0x26` pending deadline. On parser
abort (`fname_abort`, `:1432-1434`) or pending-deadline expiry
(`v172_fname_deadline_expire`, `:5291-5293`) CONTROL calls bare
`fname_reset_blank`, which clears **all** filename flags (VALID/PENDING/
WANT_QUERY/QUERY_WAIT, `:5129-5141`) and **does not retry**. Later legal
`BF/2D..4E` frames are then ignored because `FNAME_PENDING` is clear — the
filename stays blank forever while parked on Preset.

The FSM treats a transient (a dropped frame, a deadline lost to a contended
chain) as terminal. It should treat it as "try again, within a budget."

### Fix (CONTROL)

Add `fname_reset_blank_maybe_retry`: blank as today, then — only while still on
the Preset page and connected, and under a small retry budget — re-arm a bounded
delayed query through the existing machinery. Every exit path must restore
BSR=0 (callers continue in bank-0 parser/service context; the RAM-bank safety
gate enforces this):

```asm
fname_reset_blank_maybe_retry:
    rcall   fname_reset_blank              ; clear cache + flags (unchanged)
    movlb   0x00
    movlw   0x01
    cpfseq  display_state_index_b0, B      ; still on Preset page (state 1)?
    return  0x0                            ; no -> stay blank (BSR=0)
    btfss   control_flags_acc, CONNECTED, A
    return  0x0                            ; disconnected -> stay blank (BSR=0)
    movlb   0x02
    incf    v172_fname_retry_b2, F, BANKED
    movlw   FNAME_RETRY_MAX
    cpfslt  v172_fname_retry_b2, BANKED    ; retry count < MAX ?
    bra     fname_retry_exhausted
    bsf     v172_fname_flags_b2, FNAME_QUERY_WAIT, BANKED  ; re-arm delayed query
    ; reload the post-Preset query delay deadline (reuse FNAME_QUERY_DELAY_*),
    ; which v172_fname_query_delay_service then converts to FNAME_WANT_QUERY.
    movlw   FNAME_QUERY_DELAY_LO
    movwf   v172_fname_deadline_lo_b2, BANKED
    movlw   FNAME_QUERY_DELAY_B_HI         ; B-slot delay (>= A) is a safe upper bound
    movwf   v172_fname_deadline_hi_b2, BANKED
fname_retry_exhausted:
    movlb   0x00
    return  0x0
```

With `FNAME_RETRY_MAX = 3` and increment-then-compare, a failing slot gets the
initial query plus two spaced retries, then stays blank until the page is
re-entered — bounded by construction.

Point both failure sites at it: `fname_abort` (`:1433`) and
`v172_fname_deadline_expire` (`:5292`) call `fname_reset_blank_maybe_retry`
instead of `fname_reset_blank`. Reset `v172_fname_retry_b2` to 0 where
`FNAME_VALID` is set on successful completion and in the Preset entry draw
(`v171_prs_screen_draw_body`, `:3714` region) so each page visit gets a fresh
budget. Define `FNAME_RETRY_MAX` in `dlcp_control_ram.inc`.

The retry rides the existing `FNAME_QUERY_WAIT -> WANT_QUERY -> query_send`
delay path (`:5295-5322`), which already re-checks Preset+connected at fire
time and respects the health-ping hold (`:5317`); the query send mints a fresh
generation id (`:5211-5221`) so stale frames from the aborted attempt cannot be
misattributed. No new timing machinery, no busy-spin. One interaction to note:
the deadline/delay services run inside `v172_preset_filename_service`, which the
BUG-3 invalidate suppresses via `FNAME_ROW0_NOT_READY` — so a retry armed just
before a standby/WAITING transition simply freezes and is superseded by the
fresh query on Preset re-entry. That is the desired behavior.

### Test

`test_bug_v34v173_4_filename_abort_or_timeout_must_schedule_bounded_retry` flips
green (both bodies reach the retry tokens). Re-run
`tests/sim/test_preset_filename_lcd_spec.py`. Worth adding (cheap): a behavioral
case that drops one `BF/2x` frame mid-reply, lets the deadline expire, and
asserts the filename converges on the retry without leaving Preset.

---

## BUG-V34V173-5 — Preset broadcast dropped during a USB filename write

### Root cause (confirmed) — and a decisive source discovery

`preset_select_handler` gates the broadcast on the USB-filename-write bit
**before** it records the requested target (`dlcp_main_v34.asm:9974-9994`):

```asm
preset_select_handler:
    movlb       0x0
    btfsc       filename_dirty_flags_b0, 6, BANKED  ; USB filename write in flight?
    bra         preset_select_handler__return_to_parser          ; <-- drops; target NOT stored
    movf        current_cmd_data_b0, W, BANKED
    andlw       0x01
    movlb       0x2
    movwf       preset_job_target_b2, BANKED        ; <-- store happens only AFTER the gate
```

The handler's own header (`:9961-9972`) says the target *should* be recorded
during the gate and applied once `persist_dirty_runtime_state_to_eeprom` clears bit6 after
persist; the inline comment (`:9976-9979`) admits "Target NOT stored".

The decisive fact (missed by the first draft of this plan): **the job state
machine already contains the safe deferral the header describes.** The
HOLDING→APPLY transition — the only point that calls `preset_load_filename`,
which is the entire hazard the gate exists for — already checks bit6 and parks
(`dlcp_main_v34.asm:10134-10144`, added by a codex review precisely because the
entry-only gate could not cover a USB write *starting mid-job*):

```asm
    ; V3.2 USB-xact gate (codex MEDIUM vs entry-only gate at
    ; preset_select_handler): ... Defer the toggle until force_persist
    ; clears bit6.
    btfsc       filename_dirty_flags_b0, 6, BANKED
    return      0
```

And `persist_dirty_runtime_state_to_eeprom` is already written to tolerate the job's persist
running during a USB transaction (`:3316-3329` explicitly handles
`preset_job_pending` persisting bit5 first, then clears bit6 unconditionally).

So the parser-entry gate is **redundant defense in the wrong place**: the layer
that owns the hazard already guards it, and the entry gate's only net effect is
to drop broadcasts. The root-cause fix is to delete it.

### Fix (MAIN)

**(a) Delete the entry gate** (`:9975-9982`, the `btfsc`+`bra` pair and its
comment block; keep the `movlb 0x0`). The handler then always records the
target and starts/coalesces the job — its remaining body (`:9983-10002`) is
unchanged. −2 words.

**(b) Park PENDING while a USB transaction is open** so the job does not
force-mute and hold-timer against an unbounded host condition. Insert at the
top of `preset_job_pending` (`:10094-10098`), right after its `movlb 0x0`:

```asm
    btfsc       filename_dirty_flags_b0, 6, BANKED  ; USB xact open -> stay PENDING
    return      0
```

+2 words; BSR is already 0 there. Net BUG-5 size: 0 words.

Resulting sequence for a broadcast that lands mid-write: handler records target
and starts the job (PENDING); the job parks un-muted while bit6 is set; the
host's `force_persist` drives `persist_dirty_runtime_state_to_eeprom`, which persists and
clears bit6 (`:3329`); the next main-loop pass un-parks PENDING (persist /
force-mute / 150 ms hold), and the existing HOLDING gate (`:10143`) — now the
backstop for writes that *start* mid-job — passes; the switch applies.
Convergence is one persist + one hold window (sub-second) instead of the ~6 s
full-sync re-broadcast, and nothing is ever dropped: a coalescing re-broadcast
just rewrites the target, exactly as today. Standby/reconnect cancellation of a
parked job (`:10072-10075`) is unchanged — CONTROL's periodic preset broadcast
re-converges after wake, as today. If a host dies mid-transaction and bit6
sticks, the parked job simply waits, and bit6 clears on the next any-reason
persist pass — the same stuck-bit6 exposure the entry gate had, with no new
failure mode (and no force-mute while parked, thanks to (b)).

### Test-contract amendment (required)

The current regression
(`test_bug_v34v173_5_preset_select_must_record_target_before_usb_gate`) asserts
the gate **stays in the handler** with the store moved before it — it pins the
mechanism, not the contract, and the mechanism it pins is the redundant one.
The ledger's expected behavior explicitly allows this design: *"must record the
requested preset target before (**or independent of**) the
`filename_dirty_flags.bit6` USB-filename gate, so a broadcast arriving mid-write
is deferred and applied when the gate clears."* Amend the test (same change, and
update the ledger's regression-test line) to pin the real contract:

```python
def test_bug_v34v173_5_preset_select_must_record_target_independent_of_usb_gate():
    text = V34_MAIN_ASM.read_text(encoding="utf-8", errors="replace")
    handler = _label_body(text, "preset_select_handler", ["preset_select_handler__return_to_parser"])
    assert re.search(r"movwf\s+preset_job_target_b2", handler)
    assert not re.search(r"btfsc\s+filename_dirty_flags_b0,\s*6", handler), (
        "parser-entry gate reintroduced: broadcasts would be dropped again"
    )
    pending = _label_body(text, "preset_job_pending", ["preset_job_pending_no_mute"])
    assert re.search(r"btfsc\s+filename_dirty_flags_b0,\s*6", pending), (
        "PENDING must park (not mute/hold) while a USB filename write is open"
    )
    holding = _label_body(text, "preset_job_holding", ["preset_job_holding_wait"])
    assert re.search(r"btfsc\s+filename_dirty_flags_b0,\s*6", holding), (
        "HOLDING bit6 backstop before preset_load_filename must stay"
    )
```

Add a behavioral companion (primary evidence, structural pin secondary): boot a
V3.4 MAIN, open a USB filename write via the real HID path (cmd `0x03` filename
WRITE so bit6 is set by firmware, not poked), inject `B0/20/<other>`, assert the
job is recorded-and-parked (target stored, preset unchanged, no force-mute);
then complete the host transaction (force_persist), settle, and assert the
preset switched. Previously the broadcast was silently dropped.

Re-run `tests/sim/test_v34_v173_refactoring_contracts.py` and the preset/USB
overlay tests (`test_dlcp_main_flash_capture_overlay.py`,
`test_v32_flasher_sim_backend_hid.py`, `test_v32_flasher_sim_backend_ep0.py`)
to confirm the host's in-flight filename RAM is still protected (it is — by the
HOLDING gate and the PENDING park, the layers that own the hazard).

---

## New RAM symbols

| Symbol | Image | Bank | Purpose | Reset |
|--------|-------|------|---------|-------|
| `v173_reconnect_fresh_status_mask` | CONTROL | 0 (parser + WAITING loops run BSR=0; avoids `movlb` churn) | fresh per-attempt reconnect liveness bits (bit0=BF/05 seen, bit1=BF/03/01 seen) | cleared at `reconnect_wait_loop` entry |
| `v172_fname_retry_b2` | CONTROL | 2 (beside `v172_fname_*`) | bounded filename retry counter | 0 on `FNAME_VALID` success and fresh Preset entry |
| `FNAME_RETRY_MAX` (equate) | CONTROL | — | retry budget (`0x03`: initial + 2 retries) | — |

No new MAIN RAM and no new MAIN flags — BUG-5 reuses `filename_dirty_flags.bit6`
and the existing job states. Both new CONTROL bytes must land in
already-validated banks: re-run RAM-bank safety for `control-v173` and
`main-v34`.

---

## Build, size, RAM-safety, and release ceremony

MAIN and CONTROL both change, so both canonical images are rebuilt. Per the
release ceremonies in `AGENTS.md`, use the canonical builders (they bump the
revision and re-run RAM-bank safety) for the final artifacts, and use direct
`assemble_v30()` / `assemble_v17()` temp builds for clean pre/post size deltas.

```bash
# Clean current baselines (no rev bump) for size deltas
PYTHONPATH=src .venv_ep0/bin/python -c "from dlcp_fw.sim.v30_symbols import assemble_v30; from dlcp_fw.paths import V34_MAIN_ASM; assemble_v30(V34_MAIN_ASM, '/tmp/v34_pre.hex', output_lst='/tmp/v34_pre.lst')"

# RAM-bank safety must pass for both new+existing targets
PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py \
  --target main-v34 --target control-v173 --target main-v33 --target control-v172

# Canonical releases (bump rev, bake date, re-run RAM-safety, publish HEX)
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
PYTHONPATH=src .venv_ep0/bin/python scripts/build_v173_release.py --build-date <YYYYMMDD>
```

**MAIN size budget is the binding constraint and was sized instruction-level:**
current canonical V3.4 sits at `byte_margin=130` / `free_object_words=65`
against floors of `128` / `64` (the headroom gate in
`test_v34_v173_refactoring_contracts.py`), i.e. ~1 word of slack. The plan
fits because it is net-negative on MAIN:

- BUG-1: −3 words (three `bcf` deletions; comment-only otherwise).
- BUG-5: −2 words (entry gate) + 2 words (PENDING park) = 0.
- Expected net: **−3 words (−6 bytes)** → ~`byte_margin=136` /
  `free_object_words=68`. Any alternative BUG-5 shape that *adds* handler/hook
  code (the first draft of this plan did) blows the floor — do not drift back
  to it.

Measure pre/post `used_bytes_pre_preset_b`, `last_used_pre_preset_b`,
`free_object_words`, `byte_margin`, final rev/SHA/CRC, and the `0x1000..0x4BFF`
diff into the Post-Implementation Evidence section. CONTROL is not size-bound
(`byte_margin ≈ 19112`); its net change is small anyway (BUG-2 removes ~26
words of sentinel compare and adds ~10; BUG-1/3/4 helpers add ~40 words total).

The canonical V3.4 rev is currently `0x7F` (set by the mute fix); the V3.4
builder bumps it on the next build. The V1.73 builder bumps
`control_release_metadata[11]` and bakes the build date.

## Test plan

Red proof first (the four unamended regressions strict-xfail; amend BUG-5's
regression to the new contract and prove it red against unfixed source), then
green after each fix:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_exploratory_bug_regressions.py
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q --runxfail tests/sim/test_v34_v173_exploratory_bug_regressions.py
```

Per-bug focused regression sets:

- BUG-1: `test_v34_mute_refresh_bug.py` (incl. the rewritten compatibility test
  and the new prompt-`B0/03/03` chain test), `test_v34_v173_compatibility.py`
  (staged-combo behavior note above).
- BUG-2: `test_robustness_waiting.py`, `test_chain_gpsim_waiting.py`,
  `test_reconnect_wake_gate.py`, `test_v171_v31_chain.py`,
  `test_v171_v32_standby_reconnect.py`, `test_v171_v32_layer5_diag_chain.py`.
- BUG-3 / BUG-4: `test_preset_filename_lcd_spec.py`.
- BUG-5: `test_v34_v173_refactoring_contracts.py`,
  `test_dlcp_main_flash_capture_overlay.py`,
  `test_v32_flasher_sim_backend_hid.py`, `test_v32_flasher_sim_backend_ep0.py`.

Release-adjacent set and full gate before declaring release-ready:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_v34_v173_exploratory_bug_regressions.py \
  tests/sim/test_v34_mute_refresh_bug.py \
  tests/sim/test_v34_v173_compatibility.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_preset_filename_lcd_spec.py \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_firmware_version_label.py

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
```

If a fix touches the Rust sim facade (none is expected — these are firmware-only
edits), rebuild it (`cargo build --release -p dlcp-sim-py && bash crates/dlcp-sim-py/build.sh`).

## Acceptance criteria

- All five regressions in `test_v34_v173_exploratory_bug_regressions.py` pass
  un-xfailed (BUG-5's in its amended independent-of-gate form, with the ledger's
  regression-test line updated to match); no stale xfail remains for these bug
  ids.
- BUG-1: no muted-window test observes a non-zero TAS `0x30`; the compatibility
  test is rewritten to the real `cmd 0x07` + `cmd 0x03/0x03` sequence and passes;
  explicit unmute, the user-mute latch, and SRC auto-mute ownership are
  unaffected. CONTROL volume keys (IR + front panel) emit a prompt `B0/03/03` on
  a mute->unmute transition; a chain test confirms no window where CONTROL shows
  the volume while a MAIN is still muted.
- BUG-2: both WAITING loops re-arm IR every iteration; reconnect exits only on
  `v173_reconnect_fresh_status_mask` evidence observed during the current
  attempt; `raw_status_cache_b0` is gone from the reconnect body; the cold-boot
  sentinel handshake is unchanged.
- BUG-3: cold-WAITING/standby/reconnect entries invalidate Preset row-0
  readiness and the filename cache; no row-0-blank/row-1-filename combination is
  reachable.
- BUG-4: filename abort/timeout schedules a bounded, generation-tagged retry
  while on Preset + connected; budget resets on success and page re-entry.
- BUG-5: the parser-entry gate is deleted; the target is always recorded; the
  job parks in PENDING (un-muted) and at the HOLDING backstop while bit6 is set,
  and applies within one persist + hold window after the gate clears.
- Both images rebuild canonically, re-pass RAM-bank safety, and MAIN holds the
  `free_object_words >= 64` / `byte_margin >= 128` floors (expected to *improve*
  by ~3 words; any regression below floor blocks release).
- Full `tests/sim` gate green. Live-rig deployment remains pending explicit
  flash approval and hardware smoke (BUG-5 is MAIN-only; BUG-1 needs both MAIN
  and CONTROL; BUG-2/3/4 are CONTROL-only — so both images flash together).

## Out of scope / deferred

- A heavier protocol redesign for "user-volume-as-unmute" provenance (the
  ledger's "future" option) is unnecessary: the CONTROL companion makes the
  volume key emit the explicit `B0/03/03` it already means, without a new
  command or wire format.
- Dispatching IR *commands* from inside WAITING (vs. re-arming). The discard
  semantics are deliberate; see BUG-2 fix (a) for the two hazards dispatch
  would introduce.
- Re-owning the split `CONNECTED` flag (RX-set vs. foreground-modal) — the
  reconnect fix removes the foreground's dependence on it; a full ownership
  cleanup is a separate refactor.
- The split-verdict IR-preset variant noted under BUG-5 in the ledger (judged
  self-healing); this plan addresses only the source-grounded USB-filename-write
  contract violation.
- Any V3.5 / V1.74 promotion or unrelated refactor.

## Open items to confirm during implementation

- BUG-2: pick the exact free bank-0 slot for `v173_reconnect_fresh_status_mask`
  (verify against `dlcp_control_ram.inc`; RAM-safety gate enforces banking).
  Confirm the BF/05 accept path and the `:1039` wake-echo site both run with
  BSR=0 as the surrounding banked cache writes imply.
- BUG-4: the Preset `display_state_index` value is confirmed `0x01`
  (`dlcp_control_ram.inc:40`); tune `FNAME_RETRY_MAX` / the reused
  `FNAME_QUERY_DELAY_*` spacing against a contended-chain sim before freezing.
- BUG-5: confirm `preset_job_pending`'s park sits before the bit5
  filename-persist call (deferring that persist to `persist_dirty_runtime_state_to_eeprom`,
  its canonical owner) and that `preset_job_cancel` still reaches parked jobs
  (it does — the cancel checks at `:10072-10075` run before the state
  dispatch).
- BUG-1: confirm the IR volume-rail behavior note (IR handlers skip unmute at
  the rails; front-panel handlers do not) is preserved verbatim by the helper
  substitution, and that `mute_frame_send`'s sender path is unchanged.

---

## Post-Implementation Evidence (2026-06-09)

All five fixes implemented exactly as planned above; no design deviations.
The open items resolved as: `v173_reconnect_fresh_status_mask` took the
retired bank-0 slot `0x0AA` (the old deferred-IR latch, freed long ago);
`v172_fname_retry` took bank-2 `0x05D` beside the other `v172_fname_*` cells;
BUG-4's retry helper reuses the pre-existing `fname_reset_and_delay_query`
(discovered during implementation — the doc's sketch collapsed to a 6-word
bounded wrapper); the BUG-5 PENDING park sits before the bit5 persist and
`preset_job_cancel` reaches parked jobs as predicted.

Files changed:

- `src/dlcp_fw/asm/dlcp_main_v34.asm` (BUG-1 unmute deletion + contract
  comment; BUG-5 entry-gate deletion + header rewrite + PENDING park)
- `src/dlcp_fw/asm/dlcp_control_v173.asm` (helper trio after
  `mute_frame_send`; 4 volume-key sites -> `v173_volume_clear_mute_notify`;
  BF/05 + BF/03/01 mask setters; reconnect entry mask clear + invalidate;
  cold/standby invalidates; WAITING IR service calls ×2; reconnect
  sentinel-block -> mask exit; `fname_reset_blank_maybe_retry` + redirects +
  budget resets)
- `src/dlcp_fw/asm/dlcp_control_ram.inc` (two new cells + `FNAME_RETRY_MAX`;
  aliases regenerated via `check_ram_access_safety.py --fix-aliases`)
- `tests/sim/test_v34_v173_exploratory_bug_regressions.py` (un-xfailed; BUG-5
  amended to the independent-of-gate contract + new behavioral test; fixed a
  latent `_label_body` defect — labels with trailing `; address:` comments
  never matched, which strict-xfail had silently absorbed)
- `tests/sim/test_v34_mute_refresh_bug.py` (compat test rewritten to the real
  `cmd 0x07` + `cmd 0x03/0x03` sequence with interim still-muted assert; new
  `test_v173_v34_chain_volume_key_while_muted_unmutes_promptly` proving a
  prompt `B0/03/03` inside a 250 ms window that periodic full-sync cannot
  reach)
- `tests/sim/test_v34_v173_compatibility.py`
  (`test_v173_v32_old_main_filename_query_times_out_blank` amended to the
  bounded-retry contract: exactly `FNAME_RETRY_MAX = 3` queries against a
  dead-end MAIN, then terminally quiet)
- `tests/sim/test_preset_filename_lcd_spec.py` (added `FNAME_WANT_QUERY_MASK`;
  fixed a latent consume-on-read double-drain in
  `_assert_native_filename_cache_or_query_completed` ->
  `_assert_native_filename_query_completed`, exposed because Preset re-entry
  after standby now legitimately re-queries instead of silently reusing the
  cache)
- `docs/V34_V173_EXPLORATORY_BUGS.md` (per-bug Fixed notes, amended BUG-5
  regression-test lines, BUG-1 staged-combo note)
- `firmware/patched/releases/DLCP_Firmware_V3.4.hex`,
  `firmware/patched/releases/DLCP_Control_V1.73.hex` (canonical rebuilds)

Red-first proof: with the xfail markers removed and the amended/new tests in
place, all 8 bug tests failed against the unfixed sources (6 regression-file
tests + the rewritten compat test + the chain volume-key test), each at the
expected assertion (e.g. the compat rewrite failed with the leaked
`0x30=00120bdb` payload).

Implementation detour worth recording: the chain volume-key test kept failing
after the source fixes because `_boot_v173_v34_chain` loads the **canonical**
`DLCP_Control_V1.73.hex`, which still carried the pre-fix binary. A
single-Tcy PC trace (`step_tcy(1)` + `current_ctl_pc`) proved the running
CONTROL was executing the old vol-up arm (`incf; bcf bit5;` no helper) at
shifted addresses. Rebuilding the canonical releases resolved it — the
regression-file fixtures assemble from source and had masked the staleness.

Canonical artifact identities:

- MAIN `V3.4`: EEPROM rev `0x7F -> 0x80`; hex SHA-256
  `9d8a4153309c32bf5e53153628ba27d4f4c2a015770e0a87903bc4837fc1f034`.
- CONTROL `V1.73`: release rev `0x40 -> 0x41`, build date `20260609`,
  payload CRC16 `0x33F2`; hex SHA-256
  `dfd352134f090ccf749b8b39d7e2fc92016db12b9c1df7fe214bca370501a819`.
  `scripts/flash_control_safe.sh --preflight-only` reports
  `V1.73 / rev 0x41 / build 20260609`, no USB writes.

MAIN size (floors `byte_margin >= 128`, `free_object_words >= 64`):

- Baseline before this work: `last_used=0x4B7D`, `byte_margin=130`,
  `free_object_words=65`.
- After fixes (canonical V3.4): `last_used=0x4B74`, `byte_margin=138`,
  `free_object_words=69` — the net-deletion design *gained* 8 bytes of
  margin, as predicted. CONTROL margin remains huge (the headroom gate in
  `test_v34_v173_refactoring_contracts.py` passes for both images).

Test evidence:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_exploratory_bug_regressions.py
# 6 passed (all five bugs + BUG-5 behavioral; zero xfail)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_mute_refresh_bug.py
# 17 passed

PYTHONPATH=src .venv_ep0/bin/python scripts/check_ram_access_safety.py \
  --target main-v34 --target control-v173 --target main-v33 --target control-v172
# RAM bank safety: OK (main-v34, control-v173, main-v33, control-v172)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_i2c_recovery_contract.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_dlcp_v34_release_flash.py \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_firmware_version_label.py \
  tests/sim/test_dlcp_main_flash_capture_overlay.py \
  tests/sim/test_v32_flasher_sim_backend_hid.py \
  tests/sim/test_v32_flasher_sim_backend_ep0.py
# 102 passed

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 \
  tests/sim/test_robustness_waiting.py tests/sim/test_chain_gpsim_waiting.py \
  tests/sim/test_reconnect_wake_gate.py tests/sim/test_v171_v31_chain.py \
  tests/sim/test_v171_v32_standby_reconnect.py
# 14 passed (compatibility ran separately below)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_compatibility.py
# 5 passed (incl. the amended bounded-retry timeout test)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q -n 8 tests/sim/test_preset_filename_lcd_spec.py
# 193 passed

PYTHONPATH=src .venv_ep0/bin/python -m pytest tests/sim -n 16 -q
# 1497 passed, 1 skipped, 7 warnings in 471.39s
# (the skip is the long-standing rust-facade V1.5b port-compat anchor issue,
#  pre-existing and unrelated to this work)
```

Deploy/hardware evidence: no live flashing or hardware validation was
performed in this implementation turn. BUG-1 needs both images flashed
together on the rig (MAIN strictness + CONTROL explicit unmute are a pair);
hardware smoke per `docs/HARDWARE_TEST.md` remains the release gate.
