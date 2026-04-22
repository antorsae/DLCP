# No-Pop Firmware Flash (V3.2+)

Last updated: 2026-04-19 (status: IMPLEMENTED in committed V3.2)
Scope: Suppress the audible POP emitted by MAIN when the host triggers a
firmware update (HID cmd `0x40`) on `V3.2` and all later source-assembled
releases.

## Implementation Status

**Landed in committed V3.2 source as of 2026-04-19.**  This document is
now descriptive of the shipped behavior; the original "proposed" framing
is preserved below for historical context.

- Helper at `src/dlcp_fw/asm/dlcp_main_v32.asm` — search for label
  `flash_entry_quiet_shutdown:` (~line 8568).
- Dispatch site redirect at `flow_hid_command_dispatch_13d0` — search
  for the call to `main_flash_service_46de` followed by
  `goto flash_entry_quiet_shutdown` (~line 745).
- EEPROM version marker floor bumped from `0x03, 0x02, 0x32` to
  `0x03, 0x02, 0x33`. Canonical `V3.2` release builds now keep
  incrementing that third byte monotonically; the current build may
  be above `0x33`.
- Operator hardware-validation runbook lives in
  [`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md) §"Re-flash pop monitoring".

## Summary

The pre-V3.2 flash-entry path ended with an unqualified `RESET`
instruction that tristates every amp/relay pin in a single Tcy. That step
was the audible pop. The V3.2 change sequences a digital DSP mute,
secondary-device rail drop, and a graceful LAT pin drop BEFORE the
`RESET`, matching the pop-free sequence `hw_standby_shutdown` already
uses for the standby path.

The change is comment/code-only in `src/dlcp_fw/asm/dlcp_main_v32.asm`,
adds ~28 instructions of new code, one redirect at the flash trigger
call site, and changes neither the USB HID protocol nor the bootloader.

## Problem Statement

On real hardware, re-flashing MAIN produces a loud pop at the instant the
running app receives `HID cmd 0x40` (the "enter bootloader" trigger). Standby
and mute operations on the same hardware are silent. The asymmetry is
firmware-level, not hardware-level — see the traces below.

### Code evidence

Flash-entry path in `src/dlcp_fw/asm/dlcp_main_v32.asm`
(within `flow_hid_command_dispatch_13d0`):

```asm
    ; ... stage default settings, clear scratch, set dirty flags ...
    call    main_core_service_265c, 0x0     ; routine housekeeping
    clrf    ram_0x008, ACCESS               ; EEPROM addr hi = 0x00
    setf    ram_0x007, ACCESS               ; EEPROM addr lo = 0xFF
    clrf    ram_0x009, ACCESS               ; value = 0x00
    call    main_flash_service_46de, 0x0    ; EEPROM[0xFF] = 0
    call    hard_reset, 0x0                 ; <-- single-Tcy RESET: POP
```

`hard_reset` at `0x48D4`:

```asm
hard_reset:
    clrf    INTCON, ACCESS
    dw      0xF000
    dw      0xF000
    reset                                    ; PIC18 hardware reset
    dw      0xF000
    dw      0xF000
    return  0
```

Compare to `hw_standby_shutdown` at `0x3C0C` — which is silent — and to
`preset_force_mute` at the bottom of the V3.2 preset-job block.

### Pop origin

On `RESET`, the MCU POR restores `TRISA/B/C` to all-inputs and clears all
`LAT` registers in one instruction cycle (≤ 250 ns at 16 MHz). Every pin that
was driving the amp rails (`LATA.bit3/4/5` source select, `LATA.bit6`,
`LATB.bit3/bit4` amp enable) transitions from driven-output to high-Z in that
single cycle. The amp's input network sees this as a DC step and amplifies
it. The DSP is still producing whatever sample it had staged in the TAS3108
coefficient registers at the instant of reset, so the amp also sees an
unknown digital output disappearing abruptly when I2C is torn down. Both
effects combine at the amp input.

## Why Standby And Mute Are Silent

`hw_standby_shutdown` (at `0x3C0C`) explicitly staggers the transition:

1. Writes 0 to secondary-device `0x71` registers `0x1B/0x1C/0x1D` via
   `i2c_secondary_dev_write` — drops the audio rails.
2. Drops `LATB.bit4`, `LATA.bit6`, `LATA.bit3/4/5` (amp enable + source
   select) while the pins are still being driven, landing them cleanly at
   logic LOW rather than high-Z.
3. Runs the 4-iteration rail-bleed loop (`flow_hw_standby_shutdown_3c58` @
   `0x3C58`): toggles `0x71.0x1C` between 0/1 with `250 ms` of
   `timer3_blocking_delay` between each toggle — a controlled ~1 second
   discharge to ground.
4. Drops `LATB.bit3` (final amp gate), stops Timer0, then `goto usb_shutdown`.

`cmd03_mute_on/off` does not touch any analog pin. The mute path eventually
runs `i2c_tas3108_coeff_write` with `i2c_coeff_0..3 = 0`, which sets the
TAS3108 volume coefficient to zero — a purely numeric change with no analog
discontinuity.

## Design

### Principle

Replace the single `call hard_reset` at the flash-trigger site with a
two-phase call:

- **Phase A**: digital DSP mute + secondary-device rail drop + graceful LAT
  drop + short timer3 settle. This is structurally the subset of
  `hw_standby_shutdown` that suppresses the pop.
- **Phase B**: fall into the existing `hard_reset` so the bootloader hand-off
  is unchanged.

`hard_reset` itself is NOT modified. Other callers
(`uart_tx_byte_blocking` two-strike panic, `volume_dsp_write` final
escalation) reach `hard_reset` from already-broken states and must not be
made to touch a potentially-wedged I2C bus on the way out.

### EEPROM marker ordering

The `EEPROM[0xFF] = 0` marker that tells the bootloader to stay in update
mode must be committed BEFORE Phase A starts. If the new Phase A sequence
aborts for any reason (e.g. I2C bus clamped so a bounded wait times out and
the recovery path is re-entered), the EEPROM marker is already in place and
the next `RESET` — or a subsequent software/WDT reset — still lands in the
bootloader. The order is therefore:

```
main_flash_service_46de    ; EEPROM[0xFF] = 0 (idempotent, ~4 ms)
flash_entry_quiet_shutdown ; Phase A
hard_reset                  ; Phase B (tail)
```

### Phase A — the `flash_entry_quiet_shutdown` helper

Place this new helper anywhere free flash space exists in the V3.2 app code
region (the 0x47FC..0x496F window has several small unused gaps; practical
placement is immediately after `usb_shutdown` at `0x48F0`, within the
existing "Remaining Code" block). The exact address does not matter — gpasm
will resolve the label.

```asm
; ---------------------------------------------------------------------------
; Function: flash_entry_quiet_shutdown      (V3.2+ pop-free flash entry)
; ---------------------------------------------------------------------------
; Called ONLY from the flash-trigger handler in flow_hid_command_dispatch_13d0
; after EEPROM[0xFF]=0 has been committed. Drives the same sequence that
; hw_standby_shutdown uses to land the amp inputs at a known quiescent point
; BEFORE the PIC18 RESET instruction tristates every pin.
;
; Deliberately OMITS the parts of hw_standby_shutdown that would break
; flash entry:
;   - no OSCCON.SCS1 change (USB needs HS osc until the RESET fires)
;   - no SPBRG change
;   - no usb_shutdown / UCON clear (RESET itself disconnects USB cleanly)
;   - no T0CON / INTCON.T0IE teardown (Timer3 settle needs the tick source)
;   - no 4 x 250 ms rail-bleed loop (100 ms post-mute is enough once the
;     DSP is digitally zeroed and secondary rails are dropped)
;
; Falls into hard_reset; never returns on normal completion.
; Bounded-wait failures in i2c_secondary_dev_write / i2c_tas3108_coeff_write
; still reach the goto hard_reset at the bottom — worst case is a single
; click, never a hang.
; ---------------------------------------------------------------------------
flash_entry_quiet_shutdown:
    rcall       preset_force_mute               ; (1) DSP coefficients = 0
    clrf        ram_0x006, ACCESS               ; (2) drop audio rails via 0x71
    movlw       0x1B
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x1C
    call        i2c_secondary_dev_write, 0x0
    clrf        ram_0x006, ACCESS
    movlw       0x1D
    call        i2c_secondary_dev_write, 0x0
    bcf         LATB, 4, ACCESS                 ; (3) amp enable - gracefully
    bcf         LATA, 6, ACCESS                 ;     dropped to a known LOW
    bcf         LATA, 3, ACCESS                 ;     while pins are still
    bcf         LATA, 4, ACCESS                 ;     being driven (the RESET
    bcf         LATA, 5, ACCESS                 ;     would have tristated them)
    clrf        ram_0x004, ACCESS               ; (4) 100 ms timer3 settle
    movlw       0x64
    movwf       ram_0x003, ACCESS
    call        timer3_blocking_delay, 0x0
    bcf         LATB, 3, ACCESS                 ; (5) final amp gate down
    goto        hard_reset                      ; (6) now do the RESET
```

### Phase A call-site change

In `flow_hid_command_dispatch_13d0` change exactly one line:

```diff
     clrf        ram_0x008, ACCESS
     setf        ram_0x007, ACCESS
     clrf        ram_0x009, ACCESS
     call        main_flash_service_46de, 0x0    ; EEPROM[0xFF] = 0
-    call        hard_reset, 0x0
+    goto        flash_entry_quiet_shutdown      ; V3.2+: pop-free reset path
     bra         flow_hid_command_dispatch_15aa
```

`goto` (rather than `call`) is preferred: `flash_entry_quiet_shutdown` is a
one-way terminator, identical to the original `call hard_reset` in that
regard, and `goto` saves one stack slot and one instruction.

## What NOT To Do

- **Do not modify `hard_reset`.** Panic callers
  (`uart_tx_byte_blocking → v31_hard_reset_jump2`, volume-write final
  escalation) reach it from broken states. Adding I2C work in `hard_reset`
  itself turns a recoverable panic into a hang when the MSSP is wedged.
- **Do not call `usb_shutdown` before `RESET`.** The `RESET` instruction
  already disconnects USB cleanly; pre-disabling UCON lengthens the
  device-absent window and can cause the host to report an unexpected
  disconnect instead of a clean bootloader re-enumeration.
- **Do not add the `OSCCON.SCS1` switch from `hw_standby_shutdown`.** With
  USB active, the HS oscillator must stay engaged until `RESET`. Switching
  to the internal INTOSC while UCON is alive causes the host to see a hang
  instead of a clean disconnect.
- **Do not include the 4 × 250 ms rail-bleed loop** (`flow_hw_standby_
  shutdown_3c58`). Standby can afford 1 s; flash entry cannot, and the loop
  is unnecessary once the DSP is digitally zeroed and the secondary rails
  are dropped.
- **Do not reorder `main_flash_service_46de` after the quiet shutdown.** The
  EEPROM marker must be committed first so any partial shutdown is still
  rescued by the next reset.
- **Do not replace `preset_force_mute`'s `i2c_tas3108_coeff_write` with
  the bounded DSP write path (`volume_dsp_write`).** `volume_dsp_write`
  has its own retry + bus-clear + ping escalation that can itself call
  `hard_reset` — we need a single synchronous mute attempt that returns
  unconditionally so the full Phase A sequence always completes.

## Safety Analysis

| Concern | Resolution in this design |
|---------|---------------------------|
| I2C wedged at flash time | `i2c_secondary_dev_write` is V3.1+ bounded via `wait_sen_bounded` / `wait_pen_bounded`; on timeout it returns. Execution still reaches `goto hard_reset`. Worst case: a single click, never a hang. |
| `preset_force_mute` I2C wedged | Same bounded waits apply through `i2c_tas3108_coeff_write`. No new hang path introduced. |
| Host HID timeout for "device vanished" | Added latency ≈ 150 ms (3 × secondary writes ≈ 1.5 ms each + 100 ms timer3 settle + ~5 ms DSP coefficient write). `dlcp_main_flash.py` uses libusb with a multi-second enumeration window — well within margin. |
| Bootloader re-enumeration | Unchanged. `RESET` still fires at the same final step, USB is still disconnected by the hardware reset, the bootloader still reads `EEPROM[0xFF] = 0` and stays in update mode. |
| Existing hard_reset panic paths | Untouched. `uart_tx_byte_blocking` and volume-write escalation still reach `hard_reset` directly. |
| EEPROM wear | No extra EEPROM writes. `main_flash_service_46de` runs exactly once per flash entry, same as before. |
| Code-size impact | ~28 instructions (~56 bytes) new; one instruction changed (`call` → `goto`). No relocation cascade (see verification #1 below). |
| Test coverage | Simulation gate (`tests/sim/test_dlcp_main_flash.py`) passes unchanged — it does not model audio. Pop regression needs hardware loopback capture; see Test Strategy below. |

## Implementation Steps

1. Edit `src/dlcp_fw/asm/dlcp_main_v32.asm`.
2. Insert the `flash_entry_quiet_shutdown` block in the
   0x47FC..0x496F "Remaining Code" region (practical placement: right after
   `usb_shutdown` at `0x48F0`, before `main_core_service_48fe`). The exact
   address is gpasm-resolved; no `org` directive is needed.
3. At the flash-trigger site inside `flow_hid_command_dispatch_13d0`, replace
   `call hard_reset, 0x0` with `goto flash_entry_quiet_shutdown`.
4. Re-assemble:

   ```bash
   .venv_ep0/bin/python -c "from dlcp_fw.sim.v30_symbols import assemble_v30; \
       from dlcp_fw.paths import V32_MAIN_ASM, V32_MAIN_HEX; \
       assemble_v30(V32_MAIN_ASM, V32_MAIN_HEX)"
   ```

5. Bump the EEPROM version marker at `dlcp_main_v32.asm` line near
   `org 0xF00000` + 0x82 from `0x03, 0x02, 0x32` to `0x03, 0x02, 0x33` (or
   the next committed V3.x revision number) so field units can be
   distinguished from the pop-prone build.

## Test Strategy And Gate Policy

Classification per the V3.2 hang-hardening-plan convention:

- **wire/gpsim required** — existing gate must still pass:
  - `tests/sim/test_dlcp_main_flash.py` (flash protocol / bootloader
    handshake) — expected unchanged pass. This gate does NOT model audio so
    the pop suppression itself cannot be verified here; what IS verified is
    that the protocol handshake, EEPROM marker, and bootloader hand-off
    still work after the reorder.
  - `tests/sim/test_v31_v163b_robustness.py` — DSP ping + volume retry
    behavior must be unchanged (no accidental coupling through
    `preset_force_mute`).
- **hardware required for release candidate**:
  - Human-in-the-loop ear test on the two-MAIN rig — see
    [`docs/HARDWARE_TEST.md`](HARDWARE_TEST.md) §"Re-flash pop
    monitoring" for the operator walk-through.  Minimum is **2
    re-flash cycles per MAIN** (4 total flash operations across the
    pair); the rig has no automated audible-pop detector, so
    automated soak tests are not a substitute.
  - Post-flash boot should remain pop-free (this is already handled by
    `adc_boot_gate`'s staged delays; verify no regression).
  - Optional: `scripts/hardware_loop.py` capture of the audio output
    across a re-flash cycle, comparing pre/post peak amplitude in the
    0 ms .. 500 ms window after `HID cmd 0x40` is sent.  Useful for
    deeper investigation but not required for routine acceptance.
- **abort/recovery hardware test** (optional, operator-discretion):
  power-cut the unit 50 ms into the new Phase A (i.e. during the
  100 ms timer3 settle). Power-on recovery MUST drop straight into the
  bootloader (EEPROM marker already set). Verify the bootloader can
  still accept a subsequent flash stream.

Minimum release gate:

1. `test_dlcp_main_flash.py` pass.
2. `test_v31_v163b_robustness.py` pass.
3. Human-in-the-loop ear test ≥ 2 re-flash cycles per MAIN with zero
   audible pops.

## Rollback

Because the change is entirely additive in code space and the EEPROM marker
is still written first, rollback is trivial:

- Revert the `goto flash_entry_quiet_shutdown` back to `call hard_reset, 0x0`
  in `flow_hid_command_dispatch_13d0`.
- Leave the dead `flash_entry_quiet_shutdown` helper in place (it consumes
  ~56 bytes of flash but has no side effect) OR delete it.
- Re-assemble; gpasm output should diff only the single changed instruction.
  A reverted build is safe to deploy alongside a forward build because the
  HID protocol is unchanged.

## Follow-up Opportunities

These are out of scope for this change but worth tracking as distinct
hardening items:

- **Apply the same pattern to the `V3.x` USB-disconnect handler path**
  (`main_usb_service_475c` → `usb_shutdown`) — when the user yanks the USB
  cable, UCON is cleared with no prior DSP mute, and there's a small click
  that the current standby path does NOT suppress because `usb_shutdown`
  skips `hw_standby_shutdown`. Same Phase A helper can be reused.
- **Panic path upgrade** — for the `volume_dsp_write` final escalation, if
  the retry counter is exhausted AND the bus-clear/ping path succeeded
  (i.e. the bus is NOT wedged), invoke `flash_entry_quiet_shutdown` instead
  of `hard_reset` so a healthy-bus panic is also pop-free. The
  bus-not-healthy panic still goes through bare `hard_reset`. Requires
  adding a branch inside the escalation chain to differentiate the two
  cases.
- **Observability** — increment a "quiet-shutdown exit" counter in EEPROM
  or a well-known RAM slot so soak tests can confirm the pop-suppression
  was actually exercised during flash entry (as opposed to completing by
  some recovery path). Fits the V3.2 workstream 7 diagnostics plan.

## Definition Of Done

- No audible pop on hardware flash entry across **2 consecutive
  re-flash cycles per MAIN** (= 4 total flash operations across the
  pair).  Two cycles is the minimum gate because the rig has no
  automated pop detector and longer soaks don't add information once
  the helper has been observed firing twice.
- Simulation gates unchanged
  (`tests/sim/test_dlcp_main_flash.py`,
  `tests/sim/test_v31_v163b_robustness.py`).
- (Optional) Post-flash abort/recovery verified per the optional
  power-cut test above.
- EEPROM version marker advanced so field builds are distinguishable
  from the pop-prone V3.2 baseline (done — `0x03, 0x02, 0x33`).
- Canonical release notes updated to reflect the no-pop entry path
  (done — `docs/V32_RELEASE.md` describes V3.2 as the recommended
  MAIN deployment; release-policy update for downstream docs lands
  with the next release-cut commit).
