# V1.71 IR Non-Blocking Decoder Tombstone

**Status:** retired and removed from the V1.71 source.

## Current Policy

CONTROL V1.71 uses the stock-compatible V1.6b RBIF ISR path for RC5 decode:

```text
RB5 edge -> RBIF -> isr_entry -> ir_rc5_decode -> ir_decoded_cmd/addr
```

The earlier foreground-deferred service and Timer1 sampling experiment were
removed.  They decoded in simulation but did not decode real Flipper IR on
hardware, and leaving the Timer1 start path dormant was a re-wiring trap: it
could enable `PIE1.TMR1IE` without a live `TMR1IF` handler.

## Deleted Pieces

- `v171_service_pending_ir_decode`
- `v171_ir_start_decode`
- `v171_ir_sample_handler`
- `v171_ir_decode_done`
- `v171_ir_post_process`
- `v171_ir_decode_pending`
- `v171_ir_state`, `v171_ir_sample_count`, `v171_ir_buf0..3`,
  `v171_ir_flags`, `v171_ir_tmp`
- `V171_IR_TMR1_*` preload constants and `V171_IR_TOTAL_SAMPLES`

## Tests

The active regression gates are:

- `tests/sim/test_v171_hang_modes.py::test_v171_ir_decode_uses_hardware_validated_stock_isr_path`
  pins the stock-compatible in-ISR path and asserts the deleted symbols stay
  absent.
- `tests/sim/test_v171_hang_modes.py::test_v171_display_loop_no_longer_calls_legacy_ir_service`
  pins that foreground IR service remains absent.
- `tests/sim/test_v171_ir_deferred_phase_miss.py::test_v171_no_deferred_decode_pending_byte_is_unused`
  pokes retired RAM address `0x0AA` and asserts it remains a no-op.
- `tests/sim/test_v171_ir_rc5_pulse_train.py` drives real RC5 waveforms at
  RB5 and checks the live stock-compatible decoder path.

## Reintroducing A Non-Blocking Decoder

Do not re-use the deleted Timer1 bodies.  A future non-blocking design needs a
fresh spec, live `TMR1IF` ISR integration, real-hardware IR validation, and
new tests that fail if Timer1 can be armed without a handler.
