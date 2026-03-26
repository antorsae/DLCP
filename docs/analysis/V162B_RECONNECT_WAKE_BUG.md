# V1.62b Reconnect Wake Bug

Date: 2026-03-26
Firmware: DLCP Control V1.62b + DLCP Main V2.5
Severity: field-breaking (all units deaf to commands after standby cycle)
Status: fixed

## Field symptom

V2.5 + V1.62b running on real hardware for several days.  While playing
music, a brief audio glitch ("BLIRB") occurred but playback continued.
User pressed STANDBY:

1. LCD showed "Zzz..." (CONTROL entered standby display)
2. PBS units did NOT power down (MAIN's function_051 partially failed,
   likely due to a transient I2C glitch with the TAS3108 DSP)
3. User pressed the button again to return to ON
4. LCD showed "Waiting for DLCP" (CONTROL entered reconnect_wait_stub)
5. CONTROL reconnected and returned to the main display
6. Volume, preset, and mute commands had no effect on **either** PBS unit

Power cycle restored normal operation.

## Root cause

### The active gate

MAIN's command dispatcher `function_005` at `0x18F2` gates all command
processing on `0x5E.bit3` (the "active" flag):

```asm
0018f2:  btfss   0x5E, 0x3       ; active?
0018f4:  bra     label_144       ; NO -> return 0 (drop command)
```

`label_144` is a bare `return 0x0`.  Every volume, input, mute, and
preset command is silently discarded when bit3 is cleared.

### The standby broadcast

When the user presses STANDBY, CONTROL broadcasts `[B0, 0x03, 0x00]`
to ALL MAINs on the current loop.  Each MAIN's parser at `label_155`
(`0x1C9A`) immediately clears the active flag (`0x5E.bit3 = 0`) and
sets the standby event (`0x7E.bit2`).  Then `function_100` dispatches
to `function_051` (hardware standby: I2C shutdown, pin clear, Timer0
disable, oscillator switch).

The active flag is cleared BEFORE `function_051` runs.  If
`function_051` fails partway (e.g. I2C timeout due to a transient DSP
glitch), the hardware stays powered but the active flag remains cleared.

### The missing wake

Stock V1.6b at `0x1292`-`0x1294`:

```asm
001292:  bsf     0x01F, 1          ; set DISPLAY
001294:  call    function_034      ; sends [B0, 0x03, 0x01] (wake)
```

This sits between the standby-exit logic and the reconnect wait loop
(`label_212`).  It ensures that when CONTROL transitions from
standby/WAITING back to DISPLAY, all MAINs receive a wake frame and
reopen their active gates.

V1.62b replaced `label_212` with a custom `reconnect_wait_stub`.  Its
exit path `reconnect_wait_done` sets bit1 (DISPLAY) and jumps directly
to `label_201` (`0x11D8`), **bypassing the `function_034` call**.

Result: after any Zzz -> WAITING -> DISPLAY cycle, no wake frame is
sent.  All MAINs remain with `0x5E.bit3 = 0`.  Every command is
silently dropped at `function_005`.

### Why both units are affected

The standby command uses route `0xB0` (broadcast).  ALL MAINs on the
current loop receive it and clear their active flags.  Since each MAIN
has its own DSP, a single-MAIN I2C issue cannot explain both units
going deaf.  The broadcast active-flag clear does.

## Fix

One instruction added to `reconnect_wait_done` in
`build_control_presets_ab_v162b.py`:

```asm
reconnect_wait_done:
    ...
    bsf 0x01F, 1, ACCESS           ; enter DISPLAY (existing)
    call 0x0C98                     ; function_034: wake (NEW)
    ...
```

`function_034` checks bit1 (now set) and sends `[B0, 0x03, 0x01]`
(wake) to all MAINs via `function_027`, which adds the `0xB0` route
prefix.  This matches the stock V1.6b control flow at `0x1294`.

### Design choices

- `function_034` (single wake frame) rather than `function_028`
  (full-sync burst): minimizes extra traffic, matches stock intent.
- Placement after `bsf 0x01F, 1`: ensures bit1=1 so function_034
  sends data=0x01 (wake), not data=0x00 (standby).

## Tests

### Semantic guard: `test_v162b_reconnect_exit_contains_wake_call`

Scans the built V1.62b hex for the PIC18 encoding of `call 0x0C98`
(`0xEC4C 0xF006`) immediately after `bsf 0x01F, 1` (`0x821F`) in the
patch stub region `0x7000+`.

- Without fix: **FAILS** (call missing)
- With fix: **PASSES**

### DSP behavioral: `test_main_standby_gate_blocks_dsp_writes`

Standalone MAIN (V2.5) with `dsp34` i2c_regfile slave.  Three phases:

1. **Gate open**: volume `[B0, 0x06, 0x50]` -> 19 DSP registers change via I2C
2. **Gate closed** (after standby `[B0, 0x03, 0x00]`): volume
   `[B0, 0x06, 0x30]` -> **zero** DSP registers change (command dropped
   at `function_005 label_144`)
3. **Gate reopened** (after wake `[B0, 0x03, 0x01]`): volume
   `[B0, 0x06, 0x40]` -> DSP registers change again

Phase 2 reproduces the field bug at the I2C level.  Phase 3 proves the
wake frame (which the fix causes CONTROL to send) restores command
delivery.

### Why no wire-chain end-to-end

A full CONTROL -> wire UART -> MAIN end-to-end through the
standby/reconnect cycle is not included because:

1. **MAIN enters real standby in sim**: `function_051` switches the
   oscillator (`OSCCON.SCS1`) and disables Timer0, changing the
   effective baud rate and halting the main loop scheduler.  MAIN
   cannot respond to CONTROL's reconnect polls, so CONTROL stays in
   "Zzz..." indefinitely.  On real hardware, the bug requires
   `function_051` to *partially fail* (I2C glitch), which cannot be
   reliably reproduced in gpsim.

2. **Display loop compensates**: even without the fix in
   `reconnect_wait_done`, CONTROL's display loop periodically calls
   `function_028` (full-sync) which calls `function_034` (wake).
   The full-sync counter (`0x09F`/`0x0A0`) is reset to 0 in
   `reconnect_wait_done` and triggers at count 0x4E (~78 display
   loop iterations, ~20 seconds).  In the sim this fires before a
   test can reliably assert the gate is closed, masking the bug.
   On real hardware, the race window matters because user commands
   (volume knob, button presses) arrive BEFORE the first full-sync.

## Remaining uncertainty

The exact initiating fault (audio "BLIRB") is not proven to be an I2C
glitch causing `function_051` partial failure.  But the chain from that
point forward is validated:

- Standby broadcast clears all MAINs' active flags: **verified in asm**
- `function_005` gates all commands on the active flag: **verified in asm**
- `reconnect_wait_done` bypassed `function_034`: **verified in asm and hex**
- DSP writes are blocked when gate is closed: **verified in sim at I2C level**
- Wake frame reopens the gate: **verified in sim at I2C level**

The fix is small, stock-aligned, and directly matched to the field
symptom.  It is the right first fix regardless of the initiating fault.
