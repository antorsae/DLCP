# Fable Confirmed Bug Report - 2026-07-02

Scope: Fable-reported bugs that were independently checked in this repository on
2026-07-02.

Status summary:

| ID | Severity | Area | Affected artifact | Status |
| --- | --- | --- | --- | --- |
| FABLE-20260702-001 | High/Medium | MAIN standby/wake event dispatch | V3.5 MAIN with V1.73 CONTROL wake traffic | Fixed in MAIN V3.5 rev `0x009B`; regression added |
| FABLE-20260702-002 | Low | MAIN boot EEPROM source validation | V3.5 MAIN, stock-inherited from V2.3 | Fixed in MAIN V3.5 rev `0x009B`; stock/V3.4 unchanged |
| FABLE-20260702-003 | Low | MAIN fixed-input route refresh | V3.5 MAIN with V1.73 CONTROL full-sync traffic | Fixed in MAIN V3.5 rev `0x009B`; regression added |
| FABLE-20260702-004 | Low | MAIN UART RX ring / OERR recovery interrupt safety | V3.5 MAIN | Fixed structurally in MAIN V3.5 rev `0x009B`; sub-instruction trigger not simulated |
| FABLE-20260702-005 | Low | CONTROL diagnostics identity revision parser | V1.73 CONTROL with V3.5+ MAIN identity replies | Fixed in CONTROL V1.73 rev `0x63`; regression uses nonzero rev-hi |
| FABLE-20260702-006 | Low | CONTROL ISR / foreground scratch alias | V1.73 CONTROL cold WAITING handshake | Fixed structurally in CONTROL V1.73 rev `0x63`; sub-instruction trigger not simulated |

Cosmetic/no-behavior findings are listed at the end and are not assigned FABLE
bug IDs.

Implementation disposition:

- Implemented only in current runtime lines `src/dlcp_fw/asm/dlcp_main_v35.asm`
  and `src/dlcp_fw/asm/dlcp_control_v173.asm`.
- Canonical artifacts rebuilt:
  - MAIN V3.5 rev `0x009B`, SHA-256
    `7238d08cacf32f25358cf1a83d86984cb7c1d454ce46051bafe56acc3eed1071`
  - CONTROL V1.73 rev `0x63`, build `20260702`, SHA-256
    `9a28543e99ff1806a470826283323e9438a29dd6a4aa6917a27152a1631c2ee1`
- Focused pre-fix regression run failed `27` nodes on the old behavior.
- Post-fix focused Fable gate: `25 passed in 30.30s`.
- Affected multi-PB/Diagnostics/refactoring/field repro group:
  `339 passed in 1346.10s`.
- Release/preflight gate: `105 passed, 3 warnings in 60.06s`.
- RAM safety: `OK (main-v35, control-v173)`.
- Full simulator gate: `2175 passed, 2 skipped, 2 xfailed, 7 warnings in
  1610.69s`.
- No live hardware was flashed or tested for this implementation pass.

## FABLE-20260702-001 - Duplicate Wake Frame Can Cancel Pending MAIN Wake Bring-Up

### Summary

`wake_request_handler` in `src/dlcp_fw/asm/dlcp_main_v35.asm` clears
`event_flags.bit2` when a wake frame is received while the MAIN gate is already
open. If two contiguous `B0/03/01` wake frames are processed before
`standby_event_dispatch` runs, the first frame opens the gate and queues wake
bring-up, while the second frame clears the pending wake event. The MAIN can then
remain parser-alive with the logical gate open, but without running
`run_wake_rail_gate_and_dsp_cold_init`.

This is a V3.5 MAIN logic bug. V1.73 CONTROL wake behavior and V3.5 MAIN
downstream wake re-broadcasts make duplicate wake traffic plausible, but the
handler defect is in MAIN.

### Severity

Recommended classification: High/Medium.

The trigger is timing-sensitive because the duplicate wake frames must be drained
before the deferred standby/wake dispatcher runs. The consequence is severe:
one downstream MAIN can appear alive at the chain/parser layer while its
rails/DSP/audio wake bring-up did not run, producing a silent-side field symptom.

### Affected Files And Code

- `src/dlcp_fw/asm/dlcp_main_v35.asm:1837` - `wake_request_handler`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:1863` - `standby_request_handler`
  already preserves duplicate standby pending events, which is the desired
  pattern for wake as well.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:3916` - `wake_rebroadcast_downstream`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:3957` - wake bring-up entry rebroadcast
- `src/dlcp_fw/asm/dlcp_main_v35.asm:4070` - wake bring-up exit backstop

Current vulnerable wake logic:

```asm
wake_request_handler:
    clrf        length_mask_or_divisor_low_scratch_byte, ACCESS
    btfss       active_flags_acc, 3, ACCESS
    incf        length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlncf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
    rlncf       length_mask_or_divisor_low_scratch_byte, F, ACCESS
    movf        event_flags_b0, W, BANKED
    xorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    andlw       0xFB
    xorwf       length_mask_or_divisor_low_scratch_byte, W, ACCESS
    movwf       event_flags_b0, BANKED
    btfsc       event_flags_b0, 2, BANKED
    bsf         active_flags_acc, 3, ACCESS
    bra         uart_link_parser__handler_return_tail
```

The `xorwf` / `andlw 0xFB` / `xorwf` idiom computes
`event_flags.bit2 := gate_was_closed`. It does not preserve an already-pending
wake event.

### Confirmed Failure Shape

Direct V3.5 MAIN-only simulation with contiguous wake frames reproduced the
state Fable described.

Reproduction shape:

1. Boot canonical V3.5 MAIN in simulation.
2. Force `active_flags.bit3` gate closed.
3. Clear `event_flags.bit2`.
4. Inject contiguous `B0/03/01` wake frames into the MAIN RX FIFO.
5. Step until the parser and standby/wake dispatcher have had time to run.

Observed result:

```text
single wake  -> active 0x8 events 0x84 diag_b 1
double wake  -> active 0x8 events 0x80 diag_b 0
triple wake  -> active 0x8 events 0x80 diag_b 0
```

Interpretation:

- A single wake opens the gate and dispatches wake bring-up.
- Two or more contiguous wakes leave the gate open but clear the pending wake
  event before dispatch.
- `diag_b == 0` confirms `run_wake_rail_gate_and_dsp_cold_init` did not run.

### Natural Full-Chain Observation

A normal V1.73 CONTROL plus V3.5 MAIN full-chain standby/wake smoke did not hit
the failure in one deterministic run: both MAINs woke and wake bring-up counters
advanced. That run did show duplicate `B0/03/01` traffic on chain routes, so the
traffic precondition exists, but the simulator's normal phase/gap behavior may
not naturally align the duplicate frames inside one vulnerable parser drain.

This means the deterministic regression should inject the contiguous wake frames
directly instead of relying only on full-chain timing.

### User-Visible Contract

Duplicate wake traffic must be idempotent. A wake frame may be redundant, but it
must never cancel a pending wake bring-up. After standby, every reachable MAIN
that receives wake must either:

- run `run_wake_rail_gate_and_dsp_cold_init`, or
- already be fully awake with no pending wake work to preserve.

The forbidden state is:

- logical gate open,
- parser/status path alive,
- no pending wake event,
- wake rail/DSP/audio bring-up skipped.

### Proposed Fix Direction

Make `wake_request_handler` set-only for the wake event bit. If the gate was
closed, set `event_flags.bit2`. If the gate was already open, do not clear an
existing pending wake event.

Conceptual shape:

```asm
; if gate was closed, request wake dispatch
; if gate is already open, preserve any pending wake event
btfss active_flags_acc, 3, ACCESS
bsf   event_flags_b0, 2, BANKED

; if a wake is pending, keep/open the logical gate
btfsc event_flags_b0, 2, BANKED
bsf   active_flags_acc, 3, ACCESS
bra   uart_link_parser__handler_return_tail
```

The final patch must preserve V3.5 RAM/banking safety and rebuild the canonical
V3.5 release artifact if the source changes.

### Required Regression Tests

Add a deterministic V3.5 MAIN-only regression:

- Suggested node:
  `tests/sim/test_v35_duplicate_wake_idempotence.py::test_v35_duplicate_wake_frames_preserve_pending_wake_dispatch`
- Fixture/artifact: canonical `V35_MAIN_HEX`
- Stimulus:
  force MAIN gate closed, clear wake event, inject two contiguous `B0/03/01`
  frames via RX FIFO, then step the simulator.
- Expected observable:
  gate opens, wake event is not canceled before dispatch, wake bring-up counter
  advances, and post-wake latch state reaches the normal awake state.
- Old-bug failure mode:
  second wake clears `event_flags.bit2`; `diag_b` remains zero.
- Runtime class: fast/normal.
- Hardware required: no.

Add a secondary behavior guard:

- Suggested node:
  `tests/sim/test_v35_duplicate_wake_idempotence.py::test_v35_already_awake_duplicate_wake_is_noop_without_clearing_pending_event`
- Fixture/artifact: canonical `V35_MAIN_HEX`
- Stimulus:
  set gate open with no pending wake event, inject duplicate wake frames.
- Expected observable:
  no new wake dispatch is scheduled, but any pre-existing pending event would be
  preserved.
- Runtime class: fast.
- Hardware required: no.

Optional full-chain smoke:

- Suggested node:
  `tests/sim/test_v173_v35_wake_duplicate_traffic.py::test_v173_v35_standby_wake_tolerates_duplicate_downstream_wake_frames`
- Fixture/artifacts: canonical `V173_CONTROL_HEX` and `V35_MAIN_HEX`
- Stimulus:
  enter standby, wake via front panel/CONTROL, assert both MAINs complete wake.
- Purpose:
  prove the integrated chain still works, but not as the primary regression for
  this timing-sensitive bug.

## FABLE-20260702-002 - Channel-6 Boot Source Clamp Writes Channel 5

### Summary

`restore_eeprom_settings_on_boot__validate_channel6_source` in
`src/dlcp_fw/asm/dlcp_main_v35.asm` validates `channel_6_source_config` through
`FSR2`, but the out-of-range clamp writes `channel_5_source_config_b0`.

If EEPROM channel 6 contains an invalid value greater than `3`, boot validation
leaves channel 6 corrupt and overwrites channel 5 with `1`.

This is stock-inherited from MAIN V2.3. V3.5 preserved the behavior in source,
but V3.5 is no longer byte-equivalence constrained and can fix it directly.

### Severity

Recommended classification: Low.

The trigger requires corrupt or out-of-band EEPROM data. The user-visible risk is
still real: a corrupted channel 6 source byte can survive boot sanitation and
later feed the route-sync/source-coefficient path as an invalid enum, while a
valid channel 5 setting is silently changed to `1`.

### Affected Files And Code

- `src/dlcp_fw/asm/dlcp_main_v35.asm:2260` -
  `restore_eeprom_settings_on_boot__validate_channel6_source`
- `firmware/disasm/main/gpdasm_output.asm:2642` - stock V2.3 equivalent:
  `lfsr 0x2, 0x065` followed by `movwf 0x64`
- `docs/R_L_ROUTING.md:158` - existing repo note already calls out the CH6
  sanitizer typo as `movwf 0x64` should become `movwf 0x65`.

Current vulnerable V3.5 logic:

```asm
restore_eeprom_settings_on_boot__validate_channel6_source:
    lfsr        FSR2, channel_6_source_config_phys
    movlw       0x03
    cpfsgt      INDF2, ACCESS
    bra         restore_eeprom_settings_on_boot__validate_src_route_status
    movlw       0x01
    movwf       channel_5_source_config_b0, BANKED
```

The clamp target should be `channel_6_source_config_b0`.

### Confirmed Failure Shape

Direct V3.5 MAIN-only simulation reproduced the bad boot state.

Reproduction shape:

1. Boot canonical V3.5 MAIN in simulation.
2. Seed EEPROM channel 5 source (`0x0B`) to valid value `0x03`.
3. Seed EEPROM channel 6 source (`0x0C`) to corrupt value `0x09`.
4. Step through boot restore.
5. Read MAIN RAM `0x064` and `0x065`.

Observed result:

```text
gate True
ch5_ram 0x1
ch6_ram 0x9
```

Interpretation:

- Channel 5 was incorrectly clamped from valid `0x03` to `0x01`.
- Channel 6 remained invalid at `0x09`.

### User-Visible Contract

Boot EEPROM sanitation must clamp each channel source byte independently.

For channel source bytes:

- valid values `0..3` must survive unchanged;
- invalid channel N values must clamp channel N only;
- clamping channel 6 must not mutate channel 5.

### Proposed Fix Direction

Change the channel-6 clamp store from:

```asm
movwf       channel_5_source_config_b0, BANKED
```

to:

```asm
movwf       channel_6_source_config_b0, BANKED
```

This should be same-size in source and machine code.

### Required Regression Tests

Add a deterministic V3.5 MAIN-only boot-restore regression:

- Suggested node:
  `tests/sim/test_v35_boot_source_sanitizer.py::test_v35_boot_clamps_corrupt_channel6_without_mutating_channel5`
- Fixture/artifact: canonical `V35_MAIN_HEX`
- Stimulus:
  seed EEPROM channel 5 source to `0x03`, seed channel 6 source to `0x09`,
  boot MAIN-only simulation.
- Expected observable:
  RAM channel 5 remains `0x03`; RAM channel 6 clamps to `0x01`; matching
  channel source shadows mirror the sanitized values after boot restore.
- Old-bug failure mode:
  RAM channel 5 becomes `0x01`; RAM channel 6 remains `0x09`.
- Runtime class: fast.
- Hardware required: no.

Add a broader table-style sanitizer regression if this area is touched again:

- Suggested node:
  `tests/sim/test_v35_boot_source_sanitizer.py::test_v35_boot_source_sanitizer_clamps_each_channel_independently`
- Fixture/artifact: canonical or freshly assembled V3.5 MAIN.
- Stimulus:
  test each channel `1..6` with one corrupt byte and five distinct valid bytes.
- Expected observable:
  only the corrupt channel is clamped.
- Runtime class: normal if parametrized, fast if collapsed into one boot per
  channel.
- Hardware required: no.

## FABLE-20260702-003 - Repeated Fixed-Input Cmd06 Frames Force Route Re-Reconcile

### Summary

`cmd06_input_select_handler` in `src/dlcp_fw/asm/dlcp_main_v35.asm` only treats
repeated Auto Detect `cmd 0x06` frames as no-ops. Repeated fixed-input frames
with the same value as the current `input_select` still commit the input,
force `applied_route_shadow` to `0xFF`, and reload the SRC4382 route-refresh
watchdog.

The next SRC route monitor pass sees `0xFF != pending_route_request`, treats the
unchanged input as a route change, increments the V3.4/V3.5 forensic C counter,
and rewrites the SRC4382 receiver/transmitter route registers. V1.73 CONTROL
full-sync emits value-bearing `cmd 0x06` frames, so this can repeat during fixed
input uptime.

### Severity

Recommended classification: Low.

The issue does not immediately select the wrong input, but it destroys the
diagnostic value of `diag_src_c` during fixed-input uptime and adds needless
I2C traffic on the live SRC4382/audio route path. Low/Medium is reasonable if
the C counter is being used as field evidence for route churn.

### Affected Files And Code

- `src/dlcp_fw/asm/dlcp_main_v35.asm:2007` - `cmd06_input_select_handler`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2018` - current no-op guard only suppresses
  `current_cmd_data | input_select == 0`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:2027` - identical fixed input still forces
  `applied_route_shadow_b0 = 0xFF`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:3408` - route monitor compares pending
  route against `applied_route_shadow`.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:3411` - mismatch marks input/route dirty.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:3413` - mismatch increments forensic C.
- `tests/sim/test_v173_multi_pb_input_selection.py:1195` and nearby tests -
  V1.73 full-sync emits value-bearing fixed-input `cmd06` frames.

Current V3.5 no-op guard:

```asm
cmd06_input_select_check_noop:
    movf        current_cmd_data_b0, W, BANKED
    iorwf       input_select_b0, W, BANKED
    bnz         cmd06_input_select_commit
    bra         uart_link_parser__handler_return_tail
```

That only no-ops Auto Detect repeats (`0x00 | 0x00 == 0`). It does not no-op
fixed-input repeats such as `0x05 == input_select`.

### Confirmed Failure Shape

Direct V3.5 MAIN-only simulation reproduced the unnecessary route churn with
repeated fixed S/PDIF-style `B0/06/05` frames.

Reproduction shape:

1. Boot canonical V3.5 MAIN in simulation.
2. Model a source-present SRC4382 state.
3. Inject `B0/06/05` once and allow the route to converge.
4. Reset SRC4382 traffic stats and forensic C.
5. Inject identical `B0/06/05` frames repeatedly.

Observed result:

```text
after repeat 1: C 1, SRC4382 writes 0D=1, 08=1
after repeat 2: C 2, SRC4382 writes 0D=2, 08=2
after repeat 3: C 3, SRC4382 writes 0D=3, 08=3
```

Interpretation:

- `input_select` stayed unchanged at `0x05`.
- `applied_route_shadow` reconverged to the same route each time.
- Every identical repeat still counted as route churn and rewrote the SRC4382
  route pair.

### User-Visible Contract

Repeated fixed-input `cmd 0x06` frames must be idempotent while unmuted.

For unmuted MAIN behavior:

- `cmd06(data == input_select)` must not dirty the route shadow;
- it must not increment `diag_src_c`;
- it must not rewrite SRC4382 route registers;
- it must still answer/query through the existing status paths.

For muted MAIN behavior:

- existing mute-refresh behavior must be preserved. Repeated input frames while
  muted are allowed to take the refresh path so the zero-volume coefficient
  rewrite/retry contract remains intact.

### Proposed Fix Direction

Keep the current muted-refresh branch before the no-op guard. For the unmuted
path, compare equality instead of only suppressing Auto Detect repeats.

Conceptual shape:

```asm
; muted path remains first and still sets event_flags.bit3
; unmuted path: identical input is a true no-op
movf        current_cmd_data_b0, W, BANKED
xorwf       input_select_b0, W, BANKED
bz          uart_link_parser__handler_return_tail
bra         cmd06_input_select_commit
```

The final patch must verify instruction size/placement. The change should be
small, but the exact branch shape should be selected against available local
space and gpasm output.

### Required Regression Tests

Add a V3.5 MAIN-only fixed-input idempotence regression:

- Suggested node:
  `tests/sim/test_v35_cmd06_idempotence.py::test_v35_repeated_fixed_input_cmd06_does_not_rewrite_route_or_increment_c`
- Fixture/artifact: canonical `V35_MAIN_HEX`
- Stimulus:
  converge `B0/06/05`, reset SRC4382 traffic stats and `diag_src_c`, inject
  repeated identical `B0/06/05` frames.
- Expected observable:
  `input_select` remains `0x05`; `applied_route_shadow` remains the converged
  route; `diag_src_c` does not increment; SRC4382 `0x0D` and `0x08` write counts
  do not increase; no route-dirty event remains pending.
- Old-bug failure mode:
  each repeat increments `diag_src_c` and adds one SRC4382 route-pair rewrite.
- Runtime class: fast/normal.
- Hardware required: no.

Add a muted-path preservation regression:

- Suggested node:
  `tests/sim/test_v35_cmd06_idempotence.py::test_v35_repeated_fixed_input_cmd06_while_muted_preserves_mute_refresh_path`
- Fixture/artifact: canonical or freshly assembled `V35_MAIN_HEX`
- Stimulus:
  set user/effective mute state, inject repeated identical fixed-input
  `cmd 0x06`.
- Expected observable:
  mute-refresh/zero-volume retry behavior remains active; this bug fix must not
  make muted input refresh a no-op.
- Runtime class: normal.
- Hardware required: no.

Add optional full-chain evidence:

- Suggested node:
  `tests/sim/test_v173_v35_full_sync_input_idempotence.py::test_v173_v35_fixed_input_full_sync_does_not_churn_main_route_counters`
- Fixture/artifacts: canonical `V173_CONTROL_HEX` and `V35_MAIN_HEX`
- Stimulus:
  select fixed PB1/PB2 inputs, allow first route convergence, then force several
  full-sync input steps.
- Expected observable:
  V1.73 continues to emit addressed value-bearing `cmd06` frames, but each V3.5
  MAIN suppresses identical fixed-input repeats without C-counter or SRC4382
  route-write churn.
- Runtime class: normal.
- Hardware required: no.

- The proposed guard must be checked against the existing muted-refresh tests
  before claiming closure.

## FABLE-20260702-004 - Rx Ring Read Can Race With ISR OERR Parser Resync

### Summary

`rx_ring_read` in `src/dlcp_fw/asm/dlcp_main_v35.asm` consumes from the native
UART RX software ring without masking interrupts. It reads `rx_ring_rd`, uses it
to dereference `0x0200 + rd`, then increments `rx_ring_rd`.

The high-priority ISR OERR path can call `uart_soft_recover_full`, which falls
through into `uart_parser_resync` and clears both `rx_ring_rd` and `rx_ring_wr`.
If that OERR recovery runs between the foreground dereference and the foreground
`incf rx_ring_rd_b0`, the indices can end as `rd=1, wr=0`. The parser then sees
the ring as non-empty and can consume stale bytes from the old ring contents as
fresh chain frames.

This is a confirmed structural race. A natural timing reproduction has not been
shown; the consequence was confirmed by synthetic post-race state injection.

### Severity

Recommended classification: Low.

The bad state is serious because stale ring bytes can become spurious user-visible
commands. The trigger window is very narrow: if OERR is already pending when
`GIE` is re-enabled after a long masked window, the ISR should normally run before
foreground resumes into `rx_ring_read`. The race requires OERR/RCIF to become
interrupt-pending during the small dequeue window, or an equivalent
instruction-level interleaving.

### Affected Files And Code

- `src/dlcp_fw/asm/dlcp_main_v35.asm:7911` - `rx_ring_read`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7925` - reads `rx_ring_rd_b0`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7927` - dereferences `INDF2`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7929` - increments `rx_ring_rd_b0`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:5945` - ISR OERR branch
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7753` - `uart_soft_recover_full`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7769` - `uart_parser_resync`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7771` - clears `rx_ring_rd_b0`
- `src/dlcp_fw/asm/dlcp_main_v35.asm:7772` - clears `rx_ring_wr_b0`

Current foreground dequeue shape:

```asm
rx_ring_read:
    clrf        addr_high_table_row_or_checksum_scratch_byte, ACCESS
    rcall       rx_ring_has_data
    bz          rx_ring_read__return_byte_or_zero
    ...
    movf        rx_ring_rd_b0, W, BANKED
    rcall       setup_fsr2_page2_from_w
    movf        INDF2, W, ACCESS
    movwf       addr_high_table_row_or_checksum_scratch_byte, ACCESS
    incf        rx_ring_rd_b0, F, BANKED
    ...
```

Current OERR resync shape:

```asm
uart_soft_recover_full:
    bcf         RCSTA, 4, ACCESS
    rcall       uart_fifo_drain_2
    bsf         RCSTA, 4, ACCESS
    ; fall through to uart_parser_resync

uart_parser_resync:
    movlb       0x0
    clrf        rx_ring_rd_b0, BANKED
    clrf        rx_ring_wr_b0, BANKED
    clrf        rx_frame_position_b0, BANKED
    ...
```

### Confirmed Failure Shape

A natural timing reproduction was not run. The post-race state and stale-frame
consequence were confirmed synthetically on canonical V3.5 MAIN.

Synthetic consequence reproduction:

1. Boot canonical V3.5 MAIN in simulation.
2. Place stale bytes `B0/06/05` at RX ring indices `1..3`.
3. Force post-race indices `rx_ring_rd=1`, `rx_ring_wr=0`.
4. Step the foreground parser.

Observed result:

```text
before rd 1 wr 0 input 0x0
after  rd 67 wr 0 input 0x5 mirror 0x5 applied 0xff
```

Interpretation:

- The parser treated stale ring bytes as a fresh fixed-input command.
- `input_select` and `input_select_mirror` changed to `0x05`.
- `applied_route_shadow` was dirtied, proving the stale command reached real
  behavior.

### User-Visible Contract

OERR recovery must not make stale RX ring bytes visible as fresh commands.

Specifically:

- `uart_parser_resync` may drop pending staged/ring data;
- foreground dequeue must not resurrect data after an ISR resync;
- post-OERR indices must be a valid empty-ring state, not `rd != wr` unless the
  ring contains newly received bytes after the resync.

### Proposed Fix Direction

Make the `rx_ring_read` dequeue critical section interrupt-safe. Preserve the
prior `GIE` state, mask interrupts only around the ring-empty check, ring byte
read, and `rx_ring_rd` update, then restore `GIE` only if it was previously set.

Do not unconditionally set `GIE` on exit; callers may enter with interrupts
already masked.

The patch should follow the V3.5 `chain_copy` TOS-rewrite pattern: save prior
interrupt state, mask a narrowly scoped critical section, restore only the
previous state.

### Required Regression Tests

Add a structural V3.5 source regression:

- Suggested node:
  `tests/sim/test_v35_uart_rx_ring_oerr_race.py::test_v35_rx_ring_read_masks_and_restores_prior_gie_around_dequeue`
- Fixture/artifact: `V35_MAIN_ASM`
- Stimulus:
  parse `rx_ring_read`.
- Expected observable:
  the ring-empty check, byte dereference, and `rx_ring_rd` increment are inside a
  prior-`GIE` preserving critical section; exit restores `GIE` only when it was
  set on entry.
- Old-bug failure mode:
  no `GIE` mask exists around the dequeue window.
- Runtime class: fast.
- Hardware required: no.

Add a synthetic state documentation regression:

- Suggested node:
  `tests/sim/test_v35_uart_rx_ring_oerr_race.py::test_v35_post_oerr_rd1_wr0_state_replays_stale_ring_bytes`
- Fixture/artifact: canonical `V35_MAIN_HEX`
- Stimulus:
  force stale bytes at RX ring indices `1..3`, force `rd=1, wr=0`, and step the
  parser.
- Expected observable:
  pre-fix canonical artifact demonstrates the dangerous stale-command replay;
  after the fix, this test may either remain as documentation of the forbidden
  synthetic state or be inverted to assert the state cannot be produced by the
  OERR path.
- Runtime class: fast/normal.
- Hardware required: no.

Add an interleaving test only if the simulator gains instruction-level interrupt
injection:

- Suggested node:
  `tests/sim/test_v35_uart_rx_ring_oerr_race.py::test_v35_oerr_between_ring_read_and_rd_increment_leaves_ring_empty`
- Fixture/artifact: current source-assembled V3.5 MAIN.
- Stimulus:
  inject OERR exactly after `INDF2` read and before `incf rx_ring_rd_b0`.
- Expected observable:
  post-recovery indices remain an empty-ring state and no stale frame is parsed.
- Runtime class: normal.
- Hardware required: no, but requires simulator hook not currently available.

### Open Questions

- Natural field probability is unknown. The structural race and stale-frame
  consequence are confirmed; the timing path is not naturally reproduced.
- The exact smallest assembly patch needs size/banking review because `rx_ring_read`
  is a hot helper and must preserve W/STATUS behavior visible to callers.

## FABLE-20260702-005 - CONTROL V1.73 Treats 16-Bit MAIN Identity As V3.4-Only

### Summary

`v172_bf4f_payload_rev_lo` in `src/dlcp_fw/asm/dlcp_control_v173.asm` says that
`V3.4+` identities continue after `BF/53` with `BF/54..55` high-revision
frames. The implementation only continues for exactly `major == 3` and
`minor == 4`.

MAIN V3.5 emits the full seven-frame `cmd 0x25` identity reply, including
`BF/54` and `BF/55`. CONTROL V1.73 currently commits a V3.5 identity early at
`BF/53`, clears the high revision byte to zero, and ignores the trailing high
revision frames.

The current canonical V3.5 revision is below `0x0100`, so the visible
Diagnostics title is not wrong today. The bug becomes visible when V3.5 crosses
revision `0x00FF`, or if a future V3.6 keeps the same identity protocol.

### Severity

Recommended classification: Low.

The bug is forward-compatibility and diagnostic-display correctness, not current
audio/runtime behavior. It is still release-facing because Diagnostics identity
is used to verify flashed MAIN artifacts.

### Affected Files And Code

- `src/dlcp_fw/asm/dlcp_control_v173.asm:1367` - comment states `V3.4+`
  continues with `BF/54..55`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:1374` - parser requires major `0x03`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:1377` - parser requires minor exactly
  `0x04`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:1383` - fallback commits legacy 8-bit
  revision and clears rev high byte.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:9243` - V3.5 MAIN documents seven identity
  frames.
- `src/dlcp_fw/asm/dlcp_main_v35.asm:9270` - current V3.5 high-revision nibbles
  are both zero.

Current V1.73 gate:

```asm
        ; BF/53 completes the legacy low revision byte.  V3.4+ continues
        ; with BF/54..55 for the high byte; older identities commit here
        ; with high byte 0.
        ...
        movlw   0x03
        cpfseq  v172_diag_id_tmp_major_b2, BANKED
        bra     v172_bf4f_commit_rev8
        movlw   0x04
        cpfseq  v172_diag_id_tmp_minor_b2, BANKED
        bra     v172_bf4f_commit_rev8
        movlw   0x54
        movwf   v172_diag_id_expected_cmd_b2, BANKED
        bra     v172_bf4f_exit_bsr0
```

### Confirmed Failure Shape

Synthetic CONTROL-side identity replies reproduced the bug.

V3.5 identity with synthetic revision `0x0123`:

```text
valid 0x1 seen 0x1 flags 0x0 expected 0x53
major 0x3 minor 0x5 revlo 0x23 revhi 0x0
```

Interpretation:

- CONTROL validated the identity after `BF/53`.
- Low byte `0x23` was stored.
- High byte was forced to `0x00`.
- `expected_cmd` remained `0x53`, so `BF/54/55` were not incorporated.

Control comparison with V3.4 synthetic revision `0x1023`:

```text
valid 0x1 expected 0x55
major 0x3 minor 0x4 revlo 0x23 revhi 0x10
```

Interpretation:

- The high-byte parser works for exactly V3.4.
- The gate excludes V3.5 despite the documented V3.4+ contract.

### Existing Coverage Gap

Existing tests prove two useful but insufficient facts:

- V3.5 MAIN emits `BF/54..55`.
- Canonical V1.73/V3.5 Diagnostics title displays the current artifact-derived
  revision correctly.

Those tests do not catch this bug because the current canonical V3.5 revision
has high byte `0x00`, so early `BF/53` commit and full `BF/55` commit render the
same four-digit value.

### User-Visible Contract

CONTROL Diagnostics identity must parse the full 16-bit revision for all MAIN
versions that implement the seven-frame `cmd 0x25` reply.

For current protocol policy:

- V3.3 and older compact identities may commit after `BF/53` with high byte
  zero.
- V3.4 and newer identities must wait for `BF/54..55` and store the high byte.
- Future V3.5/V3.6 releases must not silently truncate revisions above `0x00FF`.

### Proposed Fix Direction

After confirming `major == 3`, change the minor-version gate from exact
`minor == 4` to `minor >= 4`, or replace it with an explicit per-version policy
that includes V3.4 and V3.5.

Conceptual behavior:

```text
if major != 3:
    commit legacy rev8
elif minor < 4:
    commit legacy rev8
else:
    expect BF/54 then BF/55 and commit rev16
```

The final assembly should preserve parser state-machine behavior for malformed
and out-of-order `BF/4F..55` sequences.

### Required Regression Tests

Add a CONTROL parser regression:

- Suggested node:
  `tests/sim/test_v172_v33_diag_identity.py::test_v173_v35_identity_parser_waits_for_rev16_high_byte`
- Fixture/artifact: canonical or freshly assembled `V173_CONTROL_HEX`; MAIN can
  be canonical V3.5 or any connected helper chain because the test injects
  CONTROL RX frames.
- Stimulus:
  arm PB1 identity parser, inject synthetic `BF/4F..55` with major `3`, minor
  `5`, low revision `0x23`, high revision `0x01`.
- Expected observable:
  CONTROL does not validate at `BF/53`; after `BF/55`, valid mask is set,
  stored revision is `0x0123`, and Diagnostics renders `PB1 OK v3.5 0123`.
- Old-bug failure mode:
  CONTROL validates at `BF/53`, stores high byte `0x00`, and displays
  `PB1 OK v3.5 0023`.
- Runtime class: fast/normal.
- Hardware required: no.

Add a compatibility regression:

- Suggested node:
  `tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_parser_keeps_v33_rev8_commit_policy`
- Fixture/artifact: canonical or freshly assembled `V173_CONTROL_HEX`.
- Stimulus:
  inject compact V3.3-style identity ending at `BF/53`.
- Expected observable:
  CONTROL still validates old compact identity with high byte zero.
- Runtime class: fast.
- Hardware required: no.

Add a structural source guard:

- Suggested node:
  `tests/sim/test_v172_v33_diag_identity.py::test_v173_identity_rev16_gate_is_v34_plus_not_v34_only`
- Fixture/artifact: `V173_CONTROL_ASM`
- Stimulus:
  inspect the `v172_bf4f_payload_rev_lo` block.
- Expected observable:
  the block implements `minor >= 4` or an explicit allowlist that includes
  minor `4` and `5`.
- Runtime class: fast.
- Hardware required: no.

### Open Questions

- If a future MAIN V4.x identity keeps the same seven-frame protocol, the policy
  should be generalized beyond `major == 3`; current evidence only supports the
  documented V3.4+ lineage.
- The current V3.5 builder should eventually have a mutation/release-builder
  test that crosses `0x00FF`, but this report does not require changing release
  revision policy.

## FABLE-20260702-006 - CONTROL ISR Clobbers Cold-WAITING Predicate Scratch

### Summary

`isr_entry` in `src/dlcp_fw/asm/dlcp_control_v173.asm` writes
`(Common_RAM + 24)` / physical `0x018` on every interrupt while checking the TX
interrupt predicate. The cold `WAITING FOR DLCP` loop also uses that same byte as
the accumulator for its four-sentinel all-clear predicate:

```text
input_select_cache != 0x80
AND volume_cache != 0x80
AND cmd1d_setting_cache != 0x80
AND raw_status_cache != 0x80
```

If a TX interrupt lands after the input-sentinel result was stored as `0` and
before the later `andwf` instructions, the ISR can rewrite the accumulator to
`1`. In the specific transient where input is still seeded at `0x80` but the
other three sentinels have cleared, CONTROL can leave cold WAITING before the
input status reply was received.

This is not a stock ISR defect by itself. The stock ISR already used `0x018`.
The V1.72/V1.73-added cold WAITING all-sentinel reduce reused an ISR-owned
access-bank byte for a new multi-instruction predicate.

### Severity

Recommended classification: Low.

The interrupt window is narrow and currently not reproduced with a natural
full-chain simulation. The consequence can be user visible, however: CONTROL may
transition out of `WAITING FOR DLCP` with `input_select_cache` still holding the
`0x80` boot sentinel. Later PB1 input full-sync uses `input_select_cache`
directly as the `cmd 0x06` data byte, so a poisoned connected state can emit an
invalid `B1/06/80` frame unless a fresh `BF/06` status reply repairs the cache
first. Chain data bytes must stay below `0x80`; `0x80` is route-byte shaped.

### Affected Files And Code

- `src/dlcp_fw/asm/dlcp_control_v173.asm:800` - ISR entry.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:811` - ISR writes
  `(Common_RAM + 24)`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:815` - ISR updates the same byte with
  the TXIF predicate.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:7378` - cold WAITING emits the
  `B1/04/00` poll that enables TX interrupt activity through the TX ring.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:7384` - cold WAITING four-sentinel
  reduce starts.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:7388` -
  `input_select_cache` predicate is stored into `(Common_RAM + 24)`.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:7393`,
  `src/dlcp_fw/asm/dlcp_control_v173.asm:7398`, and
  `src/dlcp_fw/asm/dlcp_control_v173.asm:7403` - later sentinels AND into the
  same byte.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:3103` - periodic full-sync step 2
  emits input.
- `src/dlcp_fw/asm/dlcp_control_v173.asm:3336` - PB1 input frame data comes
  directly from `input_select_cache`.

Relevant ISR shape:

```asm
isr_entry:
    clrf    WREG, A
    btfsc   PIE1, TXIE, A
    movlw   0x01
    movwf   (Common_RAM + 24), A
    clrf    WREG, A
    btfsc   PIR1, TXIF, A
    movlw   0x01
    andwf   (Common_RAM + 24), F, A
```

Relevant cold WAITING shape:

```asm
    movlw   0x80
    subwf   input_select_cache_b0, W, B
    btfss   STATUS, Z, A
    movlw   0x01
    movwf   (Common_RAM + 24), A
    ...
    andwf   (Common_RAM + 24), F, A
    ...
    andwf   (Common_RAM + 24), F, A
    ...
    andwf   (Common_RAM + 24), F, A
    btfsc   STATUS, Z, A
    bra     boot_waiting_for_dlcp_loop
```

### Confirmed Failure Shape

Static source inspection confirms all required pieces:

- Cold boot seeds `input_select_cache`, `volume_cache`, `cmd1d_setting_cache`,
  and `raw_status_cache` to `0x80`.
- The cold WAITING loop polls with `poll_frame_send`, delays, parses RX, and then
  checks all four sentinels.
- `poll_frame_send` enqueues a three-byte frame through `tx_byte_enqueue`.
- `tx_byte_enqueue` sets `PIE1.TXIE`, so TX interrupts are expected while the
  loop continues.
- The ISR writes `0x018` as part of every TX predicate check.
- The cold WAITING all-clear predicate also uses `0x018`.
- The post-WAITING input send path can stage `input_select_cache` directly as a
  PB1 `cmd 0x06` payload.

Instruction-level reproduction has not been run because the current test facade
does not expose a simple hook to force an interrupt between
`movwf (Common_RAM + 24)` and the following `andwf` sequence.

### Existing Coverage Gap

Existing WAITING and reconnect tests cover macro behavior: eventually reach
Volume, stay in WAITING when the chain is absent, and recover from reconnect
faults. They do not prove that foreground predicates use ISR-untouched scratch,
and they do not inject interrupts at exact instruction boundaries inside the
cold WAITING sentinel reduce.

The reconnect loop no longer uses this same four-sentinel reduce for its exit;
it now exits on `v173_reconnect_fresh_status_mask.bit0`. The highest-risk
remaining site is the cold WAITING all-clear predicate.

### User-Visible Contract

CONTROL must not leave cold `WAITING FOR DLCP` until every boot-handshake
sentinel has been replaced by a real MAIN status reply. A shared ISR scratch
byte must not be able to turn a failed sentinel predicate into a passed one.

No `cmd 0x06` input frame may carry a boot sentinel value such as `0x80`.

### Proposed Fix Direction

Do not mask global interrupts around the WAITING predicate unless space pressure
leaves no better option. That would add avoidable serial/IR latency in the loop
that is specifically meant to keep polling and parsing alive.

Prefer a dedicated foreground scratch byte that the ISR never writes. A small
fix can replace the cold WAITING block's `(Common_RAM + 24)` accumulator with an
ISR-untouched scratch cell, for example an existing non-ISR access scratch with
documented lifetime discipline or a newly named V1.73 predicate accumulator if
RAM space is available. The implementation should also add a source comment
stating that cold WAITING predicate scratch must not alias ISR prologue scratch.

The broader modal-menu uses of `0x018` should be audited separately. Most are
OR-reduce/event-predicate sites where ISR clobbering produces a transient redraw
or one-pass modal exit rather than an invalid connected state.

### Required Regression Tests

Add a structural source regression:

- Suggested node:
  `tests/sim/test_v34_v173_refactoring_contracts.py::test_v173_cold_waiting_sentinel_reduce_uses_isr_untouched_scratch`
- Fixture/artifact: `V173_CONTROL_ASM`.
- Stimulus:
  inspect the source block from `boot_waiting_for_dlcp_loop` through the branch
  back to that label.
- Expected observable:
  the block's all-sentinel accumulator does not reference `(Common_RAM + 24)` /
  `0x018`, and the source names the replacement scratch as ISR-untouched.
- Old-bug failure mode:
  the current block uses `(Common_RAM + 24)` for `movwf` and all three `andwf`
  operations.
- Runtime class: fast.
- Hardware required: no.

Add an instruction-interleaving regression if the simulator exposes a suitable
hook:

- Suggested node:
  `tests/sim/test_v171_sentinel_reconnect.py::test_v173_cold_waiting_tx_interrupt_cannot_clear_missing_input_sentinel`
- Fixture/artifact: canonical V1.73 CONTROL with a V3.5 MAIN chain or a focused
  CONTROL harness.
- Stimulus:
  set cold-WAITING state with `input_select_cache=0x80` and the other three
  sentinels cleared, then inject or force a TX interrupt after the input
  sentinel writes the predicate accumulator and before the final branch.
- Expected observable:
  CONTROL remains on `WAITING FOR DLCP`; no `B1/06/80`, `B2/06/80`, or
  `B0/06/80` frame is emitted.
- Old-bug failure mode:
  CONTROL exits WAITING and can later stage `0x80` as PB1 input data.
- Runtime class: normal.
- Hardware required: no, if instruction-interrupt injection is available.

Add a belt-and-suspenders chain-protocol guard:

- Suggested node:
  `tests/sim/test_v173_multi_pb_input_selection.py::test_v173_never_emits_cmd06_with_route_shaped_sentinel_payload`
- Fixture/artifact: canonical or freshly assembled V1.73 CONTROL.
- Stimulus:
  exercise cold boot, reconnect, full-sync, source menu actions, and persisted
  PB1/PB2 inputs while scanning CONTROL TX history.
- Expected observable:
  every emitted `cmd 0x06` frame has data `< 0x80`.
- Old-bug failure mode:
  this only catches the bug if the race is reproduced or if a test primes the
  poisoned state; it is still useful as a permanent protocol invariant.
- Runtime class: normal.
- Hardware required: no.

### Open Questions

- The exact interrupt phase has not been naturally reproduced. This should be
  treated as a confirmed structural race, not yet as a measured field-rate bug.
- The final fix should choose the scratch byte only after checking the CONTROL
  RAM manifest and existing BSR discipline. Reusing a banked scratch without a
  structural guard would trade one race for a bank-alias risk.
- If the source is refactored to share WAITING predicate helpers, the helper
  must preserve the cold-boot strict-sentinel contract while keeping reconnect
  on fresh-status evidence.

## Cosmetic / No-Behavior Findings

These findings are real source-cleanliness issues from the same review pass, but
they do not change firmware behavior and should not be prioritized as field
bugs.

### COSMETIC-20260702-A - Duplicate IR Command Clear

`src/dlcp_fw/asm/dlcp_control_v173.asm:7079-7080` clears
`ir_decoded_cmd_acc` twice during cold init:

```asm
clrf    ir_decoded_cmd_acc, A
clrf    ir_decoded_cmd_acc, A
clrf    ir_decoded_addr_acc, A
```

This is harmless because both writes store zero to the same byte before normal
startup state is used. A future cleanup can remove the duplicate line and keep
the adjacent `ir_decoded_addr_acc` clear.

### COSMETIC-20260702-B - Stale Identity Init Comment

`src/dlcp_fw/asm/dlcp_control_v173.asm:7155` says:

```asm
movlw   0x07                                        ; V1.72 minor byte
```

The literal `0x07` is still correct for the V1.73 control-family minor byte
stored at EEPROM `0x71`; the comment is stale. A cleanup should rename the
comment to V1.7x/control minor byte wording instead of implying V1.72-specific
behavior.

### COSMETIC-20260702-C - Orphaned Stock Channel-Config Senders

`src/dlcp_fw/asm/dlcp_control_v173.asm:3155-3232` contains unreachable stock
channel/config sender bodies immediately after:

```asm
poll_frame_send_aborted:
    return  0x0
```

The block is already effectively labeled as orphan/unreachable near its tail and
cannot execute through normal control flow. It is source noise, not a live
behavior path. Removing it would be a no-behavior cleanup only if assembler
layout/addresses are deliberately allowed to shift or are revalidated by the
existing relocation/source-structure tests.
