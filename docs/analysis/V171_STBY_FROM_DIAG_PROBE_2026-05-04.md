# Probe v23: STBY-from-Diag-Page CTL.tx byte-stream comparison (task #95)

## TL;DR

Rust **does** emit the panel-STBY broadcast `B0/03/00` from CONTROL
when STBY is pressed on the PB1 Diag page, contradicting the
operator-HW observation that "MAINs keep playing music" (which
implied no broadcast).  Probe v23 captures the CTL.tx byte stream
directly so the answer is byte-level explicit, not inferred.

  * **Phase A (positive control, Volume screen)**: STBY press
    produces 8 `B0/03/*` frames on CTL.tx (alternating standby
    `00` and step-3 `03` per the V1.71 standby/wake busy-loop
    cadence).  LCD goes to `Zzz...`.
  * **Phase B (PB1 Diag page)**: STBY press produces 8 `B0/03/*`
    frames on CTL.tx — same pattern as Phase A.  LCD goes to
    `Zzz...`.

Probe artifact: `artifacts/probes/v23_run2.txt` (gitignored under
`.gitignore artifacts/probes/`).

## What the V1.71 asm actually does

Reading `src/dlcp_fw/asm/dlcp_control_v171.asm:2885-2925`
(`display_loop_iteration` body):

  1. The busy-loop exits when **any** of `0x9A != 0` (any
     button latched), `control_flags.bit3` (mute event), or
     `control_flags.bit4` set.
  2. After exit, the STBY-edge handler at PC `0x0DB0` rotates
     `0x9A` bit 0 (= STBY-edge) into Carry.  If Carry set,
     it toggles `control_flags.bit1` (the STANDBY_ACTIVE flag).
  3. The caller (`flow_display_state_entry_126E` etc.) sees
     `control_flags.bit1` change and falls through to
     `flow_display_state_entry_1250` (PC `0x1250`), which
     UNCONDITIONALLY calls `standby_wake_broadcast` to emit
     `B0/03/00` on CONTROL's TX line.

There is **no menu-state guard** anywhere in this path -- the
STBY-edge handler is the same code regardless of whether CONTROL
is currently rendering Volume(0), Preset(1), Input(2), Setup(3),
PB1 Diag(4), or PB2 Diag(5).  display_loop_iteration is called
identically from every screen via the standard
"call display_loop_iteration → check predicates → loop" pattern.

So given the asm as written, the rust behavior (`B0/03/00`
broadcast on STBY from any screen) is **firmware-faithful**.

## What the operator-HW retest 2026-05-04 reported

> However in PB1 n/a pressing STDBY would dim control LCD but it
> will NOT actually bring to stdby.

Re-reading the operator wording: the dim is a brief LCD darkening
during the press; the unit does NOT enter standby (MAINs keep
playing audible music; presumably USB enumeration still shows
both MAINs).

If real silicon truly does NOT broadcast `B0/03/00` from the Diag
page, then real silicon is doing something the V1.71 asm does not
clearly describe.  Possibilities:

  1. **Asm-vs-silicon divergence we have not yet identified** --
     a not-obvious gate somewhere in the standby flow that real
     silicon honors but rust does not.  Could be in the
     button_scan_debounce body (a state-dependent write to
     `0x9A`), in the busy-loop predicate (a not-clearly-banked
     read that lands on a different physical RAM cell on HW than
     in rust), or in the standby-entry path.
  2. **MAIN-side gate** -- V3.2 MAIN0/MAIN1 receive `B0/03/00`
     but ignore it from a different cause (e.g. a sentinel/flag
     that only allows standby from a known menu state).  V3.2
     has known cmd-0x03 behaviour but I have not traced the
     full B0/03 path in MAIN.
  3. **Operator interpretation** -- "MAINs keep playing music"
     might be transient (the unit DID briefly enter standby,
     audio briefly faded, then woke very quickly).  An LCD
     "dim" is consistent with the standby screen briefly
     appearing.  Without scope/wire capture or a longer-window
     observation we cannot rule this out.

## What probe v23 measured definitively

Phase A and Phase B both show identical CONTROL behavior in rust:

| Phase | Pre-press LCD | Post-press LCD | B0/03/* frames on CTL.tx |
|---|---|---|---|
| A: Volume screen | `Volume:-17.0dB A` / `Auto Detect` | `Zzz...` | 8 |
| B: PB1 Diag page | `PB1` / `n/a` | `Zzz...` | 8 |

The CTL.tx byte streams are byte-for-byte equivalent in their
B0/03/* dispatches; they differ only in the leading nav-context
bytes (Phase B has a `B1/21/00` cmd-0x21 query at the start because
CONTROL is still polling the PB1 cache when STBY is pressed).

## Probe details

- Script: `artifacts/probes/v23_stby_from_diag_probe.py`
- Uses fresh `Chain.from_v171_v32()` instances per phase (no
  reuse across standby/wake) to avoid menu-state drift.
- Captures `Chain::uart_tx_records_full()` snapshots before and
  after each STBY press, diffs them, and scans for any 3-byte
  window starting `(0xB0, 0x03)` -- intentionally not requiring
  strict 3-byte alignment so a partial-frame leak would still
  be visible.
- Steps the chain ~2 sec sim wall-time after each press to let
  any TX burst complete (the V1.71 standby busy-loop emits
  multiple `B0/03/*` frames during this window).

## Implications + recommended next steps

  1. **Don't ship a rust "fix" until HW data is scoped**.  The
     V1.71 asm path is unambiguous (no menu-state gate); making
     rust gate STBY broadcasts on Diag pages would be a fidelity
     regression unless we have evidence that real silicon
     actually contains that gate.
  2. **Real-HW scope-on-wire test**.  Operator probe MAIN0 (or
     CONTROL) TX/RX with a logic analyser or scope while
     pressing STBY from PB1 Diag.  Three observable outcomes:
     - Wire shows `B0/03/00` on the bus → rust matches HW; the
       audible-music observation is misleading (perhaps standby
       was so brief the operator missed it, or audio faded for
       a beat then recovered on wake).
     - Wire is silent → real silicon has a Diag-page gate that
       rust isn't modeling.  At that point the rust code path or
       firmware decoding would need a closer read to find the
       missing gate.
     - Wire shows a different frame format → V1.71 may have
       wire-level corruption or a modified frame that rust
       doesn't emit.
  3. **MAIN-side investigation (alternative)**.  Read V3.2
     `dlcp_main_v32.asm` BF/03 / B0/03 dispatch paths and check
     whether MAIN ignores `B0/03/00` from the Diag-page-hosting
     CONTROL state (would require CONTROL to encode the menu
     state in some auxiliary byte, which the standby_wake_broadcast
     sequence does NOT seem to do).  Less likely than the
     CONTROL-side gate.

## Status update for task #95

Closed-with-finding: rust does emit `B0/03/00` from PB1 Diag.
The "MAIN keeps playing music" HW operator observation is
inconsistent with this, but the V1.71 asm has no obvious gate
that would suppress the broadcast.  Three possible reconciling
hypotheses listed above; pursuing them needs real-HW
scope-on-wire data which the current rig lacks.

Probe + analysis preserved as audit trail.  No firmware fix or
rust-side change indicated until additional HW data resolves
the ambiguity.
