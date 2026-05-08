# V1.71 IR non-blocking decoder — implementation spec

**Status:** proposed (task #152). Not yet implemented.

**Motivation:** task #151 confirmed that V1.71's deferred-decode design
(commit `bc61c70`) breaks IR on real hardware — the foreground service
enters `ir_rc5_decode` at an arbitrary phase relative to the RB5 pulse
train, so the entry-LOW check at `asm:556` aborts and the press is
silently dropped. V1.6b stock (in-ISR decode) works because the ISR
runs the decoder immediately at the RB5 falling edge, guaranteeing
RB5=LOW at entry, but pays a 7-10 ms in-ISR stall (Bug C3).

**Goal:** decode RC5 IR without stalling the ISR AND without losing the
falling-edge phase lock the decoder needs.

## Design

### Timer choice

V1.71 currently doesn't use any of Timer0/1/3 for periodic IRQs (idle
timer + full-sync counter at `0x9D/0x9E` and `0x9F/0xA0` are software
counters incremented per `display_loop_iteration`). **Timer1** is free.

PIC18F25K20 Timer1: 16-bit, prescaler /1/2/4/8, internal Fosc/4 = 3 MHz
clock. For an 889 µs interrupt period:

```
Tcy_per_period  = 889e-6 × 3e6 = 2667
TMR1 preload    = 0xFFFF - 2667 + 1 = 0xF595  (with prescaler /1)
```

So `T1CON = 0x81` (TMR1ON=1, T1CKPS=00 /1, RD16=0, sync internal).
`PIE1.TMR1IE = 1` to enable interrupt; check via `PIR1.TMR1IF`.

### State

New banked RAM bytes (all in BANK 1, contiguous after existing V1.71
state at 0x0AA):

```
v171_ir_decoder_state    EQU 0x0AB   ; 0=IDLE, 1..0x20=sampling
v171_ir_decoder_acc_lo   EQU 0x0AC   ; bit accumulator low (16 bits total)
v171_ir_decoder_acc_hi   EQU 0x0AD   ; bit accumulator high
```

`v171_ir_decode_pending` at `0x0AA` is repurposed: still set by the
RBIF ISR for "edge detected" but cleared when Timer1 takes ownership.

### State machine

```
IDLE (state=0):
  Triggered by: RBIF fires AND RB5=LOW AND IR_ARMED set.
  Action: clear acc_lo/hi; arm Timer1 with TMR1 preload at HALF the
          period (889/2 = 445 µs) so the first sample lands in the
          MIDDLE of S1's second half-bit (where it's still LOW for
          bit '1'); enable PIE1.TMR1IE; set state=1.

SAMPLING (state=1..0x20):
  Triggered by: Timer1 ISR (TMR1IF set).
  Action: shift one bit into acc_lo/acc_hi based on RB5 read
          (matches existing decoder polarity: RB5=LOW → bit 1,
          RB5=HIGH → bit 0); reload TMR1 with full-period preload;
          increment state. If state > 0x20, transition to DONE.

DONE (state=0x20):
  Triggered by: SAMPLING completes 32 samples (16 RC5 bits).
  Action: disable Timer1 (T1CON=0); clear PIE1.TMR1IE; extract
          ir_decoded_addr from acc_lo, ir_decoded_cmd from acc_hi
          (per existing decoder bit-layout); clear IR_ARMED; set
          state=0 (IDLE).
```

### ISR integration

`isr_entry` at `asm:786` already handles TXIE/TXIF, RCIE/RCIF, RBIF.
Add a NEW branch for TMR1IF, BEFORE the RBIF check (Timer1 has higher
real-time pressure):

```asm
flow_app_cold_init_03F6:
    btfss   PIR1, RCIF, A
    goto    flow_check_tmr1
    ... (existing RCIF body)

flow_check_tmr1:
    btfss   PIR1, TMR1IF, A
    goto    flow_app_cold_init_0414   ; existing RBIF check
    rcall   v171_ir_sample_handler    ; NEW
    bcf     PIR1, TMR1IF, A
    goto    flow_app_cold_init_0436

flow_app_cold_init_0414:
    btfss   INTCON, RBIF, A
    goto    flow_app_cold_init_0436
    ... (existing button-state guard)
    btfss   control_flags, IR_ARMED, A
    goto    flow_app_cold_init_0434
    btfss   PORTB, RB5, A             ; NEW: only latch if RB5=LOW
    rcall   v171_ir_start_decode      ; NEW (replaces setf pending)

flow_app_cold_init_0434:
    bcf     INTCON, RBIF, A
    ...
```

### New routines

#### `v171_ir_start_decode` (~15 instructions)

```asm
v171_ir_start_decode:
    ; Called from RBIF ISR when RB5=LOW edge detected + IR_ARMED set.
    ; Arms Timer1 to fire at 445 µs (mid-second-half of S1).
    movlb   0x1
    clrf    v171_ir_decoder_acc_lo, BANKED
    clrf    v171_ir_decoder_acc_hi, BANKED
    movlw   0x01
    movwf   v171_ir_decoder_state, BANKED
    movlb   0x0
    movlw   0xFA   ; TMR1 preload high for 445 µs (0xFAAA)
    movwf   TMR1H, A
    movlw   0xAA
    movwf   TMR1L, A
    bcf     PIR1, TMR1IF, A
    bsf     PIE1, TMR1IE, A
    movlw   0x81   ; T1CON: TMR1ON=1, prescaler /1
    movwf   T1CON, A
    return  0x0
```

#### `v171_ir_sample_handler` (~30 instructions)

```asm
v171_ir_sample_handler:
    ; Timer1 ISR body.  Shift one bit into acc, advance state, reload TMR1.
    movlb   0x1
    bsf     STATUS, C, A
    btfsc   PORTB, RB5, A
    bcf     STATUS, C, A
    rlcf    v171_ir_decoder_acc_lo, F, BANKED
    rlcf    v171_ir_decoder_acc_hi, F, BANKED
    incf    v171_ir_decoder_state, F, BANKED
    movlw   0x21
    cpfslt  v171_ir_decoder_state, BANKED
    goto    v171_ir_decode_done
    ; Reload TMR1 for next 889 µs sample.
    movlb   0x0
    movlw   0xF5
    movwf   TMR1H, A
    movlw   0x95
    movwf   TMR1L, A
    return  0x0

v171_ir_decode_done:
    ; 32 samples collected.  Disable Timer1, decode result, write outputs.
    movlb   0x0
    bcf     T1CON, TMR1ON, A
    bcf     PIE1, TMR1IE, A
    bcf     PIR1, TMR1IF, A
    movlb   0x1
    movf    v171_ir_decoder_acc_lo, W, BANKED
    movwf   ir_decoded_cmd, A
    movf    v171_ir_decoder_acc_hi, W, BANKED
    movwf   ir_decoded_addr, A
    bcf     control_flags, IR_ARMED, A
    clrf    v171_ir_decoder_state, BANKED
    return  0x0
```

NB: the bit-to-byte mapping (which acc is "addr" and which is "cmd")
needs to match the current `ir_rc5_decode` byte layout. Verify
empirically against test_v171_ir_rc5_pulse_train.py during
implementation — the test expects `cmd=0x3A, addr=0x10` from a known
pulse train.

### Removal of legacy code

After the new path works:

- Delete `v171_service_pending_ir_decode` body (asm:2614-2631).
- Replace the call site in `display_loop_iteration` (asm:2766) with
  `nop` to preserve byte alignment, OR remove the call and let
  downstream addresses shift (gpasm will handle).
- Keep `ir_rc5_decode` body itself for now (it's referenced from the
  V1.7 / V1.6b stock paths via the V17 source rebuild — we only need
  to stop CALLING it from V1.71's foreground).

### Code-shift risk

This adds ~50-80 instructions to the V1.71 hex. Layer 5 chain timing
tests have shown sensitivity to ~2-byte shifts before; ~50 instruction
shift will likely require bumping a few `limit=N` parameters in those
tests. Mitigation: after assembly, run the full V1.71 test gate; bump
limits only where a single test fails with timing-only assertions.

## Validation plan

1. **Unit:** `test_v171_ir_deferred_phase_miss.py` test
   `test_v171_deferred_decode_aborts_when_foreground_misses_low_window`
   should FAIL after this lands (decoder no longer aborts under the
   poked-pending scenario — sample-driven decoder ignores the pending
   byte entirely). Update the test to either delete it (bug fixed) or
   pin the new behavior.
2. **Pulse train:** `test_v171_ir_rc5_pulse_train.py`
   `test_v171_rc5_pulse_train_decodes_standby_endpoint` MUST still
   pass (same standby-frame TX outcome, different decoder internals).
3. **Endpoint dispatch:** `test_v171_ir_endpoints.py` MUST still pass
   (the inline dispatch path is untouched).
4. **Sister regression:** `test_v16b_stock_in_isr_decode_immune_to_phase_miss`
   MUST still pass (V1.6b stock untouched).
5. **Layer 5 chain timing:** all `test_v171_v32_layer5_*` tests must
   pass; bump `limit=N` parameters if needed for code-shift compensation.
6. **Hardware validation:** flash V1.71 + new decoder onto a real CONTROL
   unit, exercise IR remote (volume up/down, preset A/B, standby/wake).
   Confirm decoded values reach MAIN.

## Hardware-validation responsibility

This change is firmware-touching and timing-critical. Sim validation is
necessary but NOT sufficient. The operator must flash a real V1.71 unit
and confirm IR works on hardware before the change is considered
released. Document the test procedure in `docs/HARDWARE_TEST.md` under
a new "IR validation" section.

## Estimated work

- Spec doc (this file): done.
- Implementation: 4-6 hours (asm writing + assembling + iterating
  on sim test failures).
- Sim test validation: 1-2 hours.
- Code-shift fixes for Layer 5 tests: 30-60 min.
- Hardware validation: operator step (out of scope for this PR).

Total: ~1 day of focused work for the firmware change; full
sim-test gate convergence may take longer if unexpected interactions
surface.
