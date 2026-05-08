# V1.71 IR non-blocking decoder — implementation spec

**Status:** corrected after codex review (2026-05-09). Implementation
in progress (task #152).

**Motivation:** task #151 confirmed that V1.71's deferred-decode design
(commit `bc61c70`) breaks IR on real hardware — the foreground service
enters `ir_rc5_decode` at an arbitrary phase relative to the RB5 pulse
train, so the entry-LOW check at `asm:556` aborts and the press is
silently dropped. V1.6b stock (in-ISR decode) works because the ISR
runs the decoder immediately at the RB5 falling edge, guaranteeing
RB5=LOW at entry, but pays a 7-10 ms in-ISR stall (Bug C3).

**Goal:** decode RC5 IR without stalling the ISR AND without losing the
falling-edge phase lock the decoder needs.

## Why option 1 / 2 / 3.5 were rejected

Codex review of the design choice (2026-05-09):

* **Option 1 (revert bc61c70):** restores in-ISR decode at the cost of
  re-introducing the 10 ms ISR blackout (Bug C3). At 31,250 baud one
  byte arrives every ~320 µs and the EUSART FIFO holds 2; a 10 ms
  blackout spans ~31 byte times of dropped UART.
* **Option 2 (RB5=LOW gate before setf pending):** doesn't fix the
  bug. Foreground may still enter the decoder after RB5 returns HIGH.
  Worse: silently drops edges when IOC fires while RB5 is HIGH,
  removing the 0xFF abort signature as a debug signal. "Lower-noise,
  not more correct."
* **Option 3.5 (decode in Timer1 ISR after small delay):** equivalent
  to option 1. With `IPEN=0` no nested ISR service happens until
  `retfie`, so the 10 ms blackout is the same regardless of which ISR
  holds the CPU.

**Option 3 (full state machine) is the only design that solves Bug C3
AND the deferred-decode phase miss.**

## Design

### Timer choice

V1.71 currently doesn't use Timer1 for periodic IRQs. PIC18F25K20
Timer1: 16-bit, prescaler /1/2/4/8, internal Fosc/4 = 3 MHz Fcy.

**Preload math (rust-sim-tuned post-codex review of 61e17a7):**

```text
~890 µs effective    -> TMR1 FULL preload 0xF5D8 (866 µs raw +
                        ~24 µs ISR-path overhead per sample)
~1303 µs first       -> TMR1 FIRST preload 0xF0BC (raw; ~13 µs
                        first-sample-only ISR overhead)
```

The ORIGINAL spec values (`0xF595` full / `0xFAC9` first) were
calculated against an under-estimated ~7-Tcy ISR-path overhead per
sample.  The actual overhead is ~60-70 Tcy (vector dispatch + Q4
alignment + isr_entry prologue + check_tmr1 path + handler header
to btfsc + reload tail + epilogue), so cumulative drift over 25
sample intervals pushed sample 26 past bit-13's second half.
Symptom on the original values: cmds with cmd LSB = 1 (RC5 0x39
preset B and 0x3B wake) failed Manchester pair-validation on the
last sample pair.  See `dlcp_control_ram.inc` "PRELOAD VALUES
(V1.71-tuned post-correction)" block for the empirical sweep
data and the picked-mid-of-working-range margin rationale.

`T1CON=0x81` sets `RD16=1` + `TMR1ON=1` (internal Fcy/4, prescaler /1,
16-bit writes via TMR1H buffer + TMR1L). Codex flagged that 16-bit-mode
writes need the high-byte first / low-byte second sequence; using
`T1CON=0x01` (8-bit) would let us write TMR1L+TMR1H independently but
costs an extra Tcy of jitter. Choose `0x81` (16-bit) for cleanliness.

**Sleep caveat:** Timer1 internal Fcy/4 clock does NOT run during true
Sleep. RBIF wake fires first, the IR ISR re-arms Timer1 after wake.
CONTROL has no USB-polling concern.

### State

New banked RAM bytes in BANK 1, allocated AFTER the existing V1.71
diag-renderer state (codex-recommended free region; bytes 0x0AB-0x0AD
that the original spec proposed are already in use by
`bf08_fault_byte` / `v171_rx_frame_gap_timeout` /
`v171_tx_saturate_count`):

```asm
v171_ir_state          equ 0x0D5   ; physical 0x1D5
v171_ir_sample_count   equ 0x0D6   ; physical 0x1D6
v171_ir_buf0           equ 0x0D7   ; 4-byte shift buffer (32 samples)
v171_ir_buf1           equ 0x0D8
v171_ir_buf2           equ 0x0D9
v171_ir_buf3           equ 0x0DA
v171_ir_flags          equ 0x0DB
v171_ir_tmp            equ 0x0DC
```

Access via `movlb 0x01` (these are bank-1 GPR addresses; physical
0x1D5..0x1DC). Add collision/BSR-discipline structural tests mirroring
the V1.71 diag renderer's test pattern.

`v171_ir_decode_pending` at `0x0AA` is REMOVED (the foreground service
goes away with this change). The byte becomes free for future use.

### State machine

```
IDLE (state=0):
  Triggered by: RBIF fires AND RB5=LOW AND IR_ARMED set.
  Action: clear buf0..buf3, sample_count=0; arm Timer1 with
          FIRST preload (V171_IR_TMR1_FIRST_HI/LO = 0xF0BC, ~1303
          µs raw + ~13 µs ISR overhead) so the first sample lands
          in S2 first half (HIGH for sentinel '1'); enable
          PIE1.TMR1IE; set state=1.

SAMPLING (state=1, sample_count=0..0x1F):
  Triggered by: Timer1 ISR (TMR1IF set).
  Action: shift one bit into the byte at byte_index =
          sample_count >> 3 (0..3) within buf0..buf3, BYTE-INDEXED
          to match the legacy decoder's POSTINC0-every-8-samples
          fill pattern (asm:574-580): buf0 takes samples 1..8,
          buf1 takes 9..16, buf2 takes 17..24, buf3 takes 25..32.
          Polarity matches existing decoder at asm:573-576 (C=1,
          btfsc PORTB.RB5, bcf C → C=0 if RB5 HIGH, then rlcf
          into the indexed byte).  Reload TMR1 with FULL preload
          (V171_IR_TMR1_FULL_HI/LO = 0xF5D8); increment
          sample_count.  If sample_count >= 32, transition to DONE.

  Why byte-indexed (codex HIGH vs the v2 spec): a literal 32-bit
  rolling shift across the 4-byte chain would put samples 25-32
  in buf0 (reversed from the legacy decoder's low-address-first
  fill) -- the existing post-process at asm:587+ assumes the
  legacy layout.  Byte-indexed accumulation matches it exactly:
  no copy reordering needed at DONE.

DONE (state=2):
  Triggered by: SAMPLING accumulated 32 samples.
  Action: disable Timer1 (T1CON=0); clear PIE1.TMR1IE; call
          v171_ir_post_process to validate Manchester pairs and
          extract addr/cmd; clear IR_ARMED; set state=0 (IDLE).
```

### Bit-to-byte mapping (post-process)

The existing `ir_rc5_decode` body (asm:546-668) accumulates 32 samples
through `FSR0=0x010` post-incrementing every 8 samples (asm:580
`movf POSTINC0, F, A`). The 32-sample stream is then compressed into
RC5 14-bit-frame fields by `flow_ir_rc5_decode_025E` (asm:587+) which
walks the buffer through `control_core_service_02EE` (codex-identified
correct helper; asm:600, 609, 632, 657) for Manchester pair
validation.

The new design preserves this post-processing: after Timer1 accumulates
32 samples into `v171_ir_buf0..buf3`, we copy those 4 bytes into
`(Common_RAM+16)..(Common_RAM+19)` (0x010-0x013) and `rcall` into the
existing decoder's POST-entry-check body at `flow_ir_rc5_decode_025E`
(asm:587). This reuses the existing Manchester pair validation +
addr/cmd extraction without rewriting it.

**Caveat:** the existing decoder body does the entry-LOW check at
asm:556 AND the bit-bang sampling AND the post-process in one routine.
We need to factor the post-process into a reachable label. One clean
approach: rename the existing entry-point to `ir_rc5_decode_legacy`
(unused after this change; kept for reference) and create a NEW
`v171_ir_post_process` that holds only the post-process logic.

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
    goto    flow_app_cold_init_0414      ; existing RBIF check
    rcall   v171_ir_sample_handler       ; NEW
    bcf     PIR1, TMR1IF, A
    goto    flow_app_cold_init_0436

flow_app_cold_init_0414:
    btfss   INTCON, RBIF, A
    goto    flow_app_cold_init_0436
    ... (existing button-state guard)
    btfss   control_flags, IR_ARMED, A
    goto    flow_app_cold_init_0434
    btfsc   PORTB, RB5, A                ; NEW: skip if RB5 HIGH
    goto    flow_app_cold_init_0434      ;   (no falling-edge phase)
    rcall   v171_ir_start_decode         ; NEW (replaces setf pending)

flow_app_cold_init_0434:
    bcf     INTCON, RBIF, A
    ...
```

### New routines

(Estimated sizes; verify after assembling.)

#### `v171_ir_start_decode` (~15 instructions)

Arms Timer1 with FIRST preload (V171_IR_TMR1_FIRST = 0xF0BC, ~1303 µs
raw -> sample 1 lands ~1316 µs after falling edge with ~13 µs
first-sample-only ISR overhead), clears buffer + counter, sets
state=1. Returns to ISR.

#### `v171_ir_sample_handler` (~25 instructions)

Reads RB5, shifts into ``buf[sample_count >> 3]`` (byte-indexed),
increments sample_count. If count >= 32, transitions to DONE
(calls post_process); else reloads TMR1 with FULL preload
(V171_IR_TMR1_FULL = 0xF5D8, ~866 µs raw + ~24 µs per-sample ISR
overhead = ~890 µs effective sample-to-sample interval).

#### `v171_ir_post_process` (factored from existing `flow_ir_rc5_decode_025E`)

Copies `v171_ir_buf0..buf3` into `(Common_RAM+16..19)`, runs the
existing Manchester pair-validation logic, extracts addr/cmd, writes
to `ir_decoded_cmd` / `ir_decoded_addr`, clears IR_ARMED, sets
state=0.

### Removal of legacy code

After the new path works:

* Delete `v171_service_pending_ir_decode` body (asm:2614-2631).
* Replace the call in `display_loop_iteration` (asm:2766) with an
  inline `nop` to preserve byte alignment, OR remove the call and
  let downstream addresses shift (gpasm handles relabeling).
* `v171_ir_decode_pending` at 0x0AA becomes free RAM (no callers).
* Keep `ir_rc5_decode` body itself for now as `ir_rc5_decode_legacy`
  reference (no callers in V1.71); future cleanup can remove it.

### Code-shift risk

This adds ~70-100 instructions to V1.71. Layer 5 chain timing tests
have shown sensitivity to ~2-byte shifts before; ~50-100 instruction
shift will likely require bumping a few `limit=N` parameters. Plan:
after assembling, run the V1.71 test gate; bump limits only where a
single test fails with timing-only assertions.

## Validation plan

1. **V1.71 phase-miss test should FAIL after this lands.**
   `tests/sim/test_v171_ir_deferred_phase_miss.py::test_v171_deferred_decode_aborts_when_foreground_misses_low_window`
   currently PASSES (bug present). New decoder doesn't read 0x0AA at
   all → poking it has no effect → no abort → test fails. That
   failure flags the fix — UPDATE the test (delete or rewrite to pin
   the new behavior).

2. **V1.6b sister test must STILL PASS.**
   `test_v16b_stock_in_isr_decode_immune_to_phase_miss` is unaffected
   (V1.6b stock is untouched).

3. **Pulse-train test must STILL PASS.**
   `test_v171_ir_rc5_pulse_train.py::test_v171_rc5_pulse_train_decodes_standby_endpoint`
   drives a real Manchester pulse train at RB5; the new Timer1-driven
   decoder MUST produce the same TX standby frame.

4. **Endpoint dispatch must STILL PASS.**
   `test_v171_ir_endpoints.py` (preset / standby / wake dispatch)
   uses `inject_decoded_ir_event` which writes directly to
   `ir_decoded_cmd`/`ir_decoded_addr` — unaffected by the decoder
   change.

5. **Layer 5 chain timing tests:** all `test_v171_v32_layer5_*` tests
   must pass; bump `limit=N` parameters as needed for code-shift
   compensation.

6. **New collision/BSR-discipline tests** for the new RAM bytes,
   mirroring the V1.71 diag-renderer pattern (look for the existing
   diag-renderer's collision test as a template).

7. **Hardware validation:** flash V1.71+new decoder onto a real
   CONTROL unit, exercise IR remote (volume up/down, preset A/B,
   standby/wake). Confirm decoded values reach MAIN. This is an
   operator step; document procedure in `docs/HARDWARE_TEST.md`.

## Implementation milestones

1. **M1 (commit 4c88d81 / 6d983da / f7365bb):** spec corrected, no
   code change.
2. **M2 (commit f4e25bd / 3da7145):** RAM equates + 3 routine bodies
   (no callers).  Routines are unreachable in the current firmware
   so existing tests still pass.  M2 fixed the carry-clobber bug in
   the sample handler (codex MEDIUM vs f4e25bd) by switching to
   FSR0-based addressing.
3. **M3 BLOCKED:** wiring the ISR + start_decode caller produced
   correct deferred-decode-bug fix (phase-miss test now correctly
   fails on the new firmware = bug detected as fixed) but
   regressed the pulse-train test (cmd decoded as 0x38 instead of
   0x3A; later 0xFF abort).  Root cause:
     a. **`movff` doesn't honour BSR.**  ``movff v171_ir_buf0,
        dest`` evaluates the operand to 0x0D7 and treats it as
        physical 0x0D7 (BANK 0, channel-source array), NOT BANK 1's
        0x1D7.  Need to use ``lfsr`` + ``POSTINC`` for buffer copy
        OR define a separate full-12-bit equate.  (Found and fixed
        during M3 attempt; the lfsr/POSTINC approach is cleaner.)
     b. **Cumulative ISR-overhead drift.**  Each sample handler
        invocation costs ~17 µs of overhead (ISR header + dispatch +
        sample-handler body).  Over 32 samples this drifts the
        sample window cumulatively by ~544 µs.  Late-frame samples
        (the test repro showed sample 24 already showing wrong
        bit-value, codex review notes that point is borderline --
        24 × 17 µs = 408 µs is just inside the 444 µs half-bit
        margin; the actual onset of mistimed reads may be a few
        samples later).  Either way, by the C0 / C1 region the
        Manchester pair validation breaks.
     c. **Buffer layout doesn't match legacy post-process.**
        V1.6b stock decodes the test pulse train to cmd=0x3A by
        producing buf=`66 A9 59 02`, while my Timer1-driven
        sampler produces `B3 54 AD 80` (different sample phasing).
        The legacy post-process at `flow_ir_rc5_decode_025E`
        expects a specific buffer-bit layout that my sample timing
        doesn't match.  Need to either match the legacy decoder's
        EXACT phase, or write a NEW post-process for the new
        buffer layout.
4. **M3 next-attempt requirements:**
     a. Compensate for ISR overhead in TMR1 reload preload (subtract
        ~50 Tcy from the per-sample reload value to keep samples
        aligned to half-bit centers).
     b. Decide on first-sample alignment: option A is to enter the
        decoder at the falling edge and place sample 1 at mid of S1
        second half; option B is to skip S1 entirely (we know S1=1
        from the falling edge) and start at mid of S2 first half.
        Option B is cleaner because the post-process can decode 13
        bits + treat S1 as known.
     c. Either replicate the legacy decoder's exact sample phase
        AND reuse `flow_ir_rc5_decode_025E` post-process, OR write
        a NEW post-process that takes the new buffer layout.  The
        latter is cleaner but more code; the former requires
        instrumenting the legacy decoder to find its first-sample
        phase precisely.
     d. **Hardware validation is mandatory** before declaring M3
        done -- sim ISR overhead may differ from real silicon, so
        the empirically-tuned reload values may need adjustment on
        a real V1.71 unit.
5. **M4-M6 (deferred until M3 complete):**
     - M4: Update tests (delete or rewrite phase-miss test; verify
       pulse-train passes; bump Layer 5 limits if needed).
     - M5: Hardware validation handoff.

## Lessons learned during M3 attempt

* `movff` is NOT BSR-sensitive.  Bank-1 RAM access via the BANKED
  equate works for `clrf`/`movf`/`movwf`/`bsf`/`bcf`/`btfsc`/
  `btfss` (which DO use BSR) but NOT for `movff` (which uses
  full-12-bit literal addressing).  Use `lfsr` + `POSTINC0/1`
  patterns instead, OR define a separate full-address equate.
* The legacy decoder's per-iteration delay (`call control_core_
  service_01D8` with W=0xBA / W=0x76) is harder to model than I
  estimated: nested decrement loops with subtle borrow semantics.
  My initial trace put per-iteration at ~595 µs, but a codex
  re-count gave ~885 µs ≈ one Manchester half-bit -- closer to
  what we'd expect for "sample at mid of each half-bit" cadence.
  My earlier ~595 µs estimate was wrong; the legacy timing must
  be re-counted or sim-instrumented before claiming a phase
  alignment in M3 next-attempt.
* The ISR-overhead compensation is not unique to my design --
  ANY non-blocking IR decoder running from a Timer1 ISR has to
  account for the per-tick overhead.  This is a real-silicon
  timing issue, not a sim quirk.

## Hardware-validation responsibility

Sim validation is necessary but NOT sufficient.  The operator must
flash a real V1.71 unit and confirm IR works on hardware before the
change is considered released.
