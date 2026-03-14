# V1.62b Standby TXIE Bug (2026-03-14)

## Symptom

V2.5 + V1.62b on real hardware: pressing STBY on CONTROL shows `Zzz...` on
the LCD, but the two connected PBS (power buffer stages) do not enter standby.
Audio continues playing.

V2.4 + V1.61b on the same unit: standby works correctly.

## Root Cause

`control_uart_soft_recover` in V1.62b contained:

```asm
control_uart_soft_recover:
    bcf PIE1, TXIE, ACCESS    ; ← KILLS TX INTERRUPT
    bcf RCSTA, CREN, ACCESS
    movf RCREG, W, ACCESS
    movf RCREG, W, ACCESS
    bsf RCSTA, CREN, ACCESS
    ...
```

The `bcf PIE1, TXIE` instruction was added as part of the V1.62b OERR
(UART overrun error) recovery to "clean up" the TX state during error
handling. The stock V1.6b OERR handler only toggles CREN and never
touches TXIE.

### Why it breaks standby

CONTROL uses interrupt-driven TX (ISR reads byte from `0x097`, writes to
TXREG). The TX helper at `0x0606` queues a byte in `0x097` and sets TXIE;
the ISR fires and sends it.

When OERR fires on real hardware (common during LCD writes, button scans,
or sync cycles due to interrupt latency), `control_uart_soft_recover` runs
and `bcf PIE1, TXIE` kills the TX interrupt. If a frame byte was pending
in `0x097` (queued by `function_020` but not yet sent by the ISR), that
byte is stranded. The next `function_020` call overwrites `0x097` with a
new byte, silently dropping the stranded one.

The standby command (`cmd=0x03 data=0x00`) is a 3-byte serial frame
`[B0, 03, 00]` sent by `function_034` during the full-sync cycle
(`function_028`). If any byte of this frame is dropped, MAIN receives a
garbled or incomplete frame and never enters standby.

### Why gpsim didn't catch it

gpsim's EUSART model correctly implements OERR (`uart.cc:1468` —
`_RCREG::push()` calls `_RCSTA::overrun()` when `fifo_sp >= 2`). However,
the test harness uses an alternating-step architecture where CONTROL and
MAIN run in separate gpsim processes:

```
CONTROL runs 1M cycles → flush → MAIN runs → flush → repeat
```

CONTROL gets 1M instruction cycles (250ms at 4 MHz Tcy) to drain its
2-deep RCREG between batches of incoming bytes. At 31,250 baud, this is
enough time for ~781 bytes. RCREG never overflows. `btfss RCSTA, OERR`
never triggers. `control_uart_soft_recover` never executes.

On real hardware, both MCUs run simultaneously. MAIN can push a response
frame while CONTROL is busy with a slow operation (HD44780 LCD nibble
writes take hundreds of cycles per character). Two bytes pile up in
RCREG, a third arrives — OERR.

## Fix

Remove `bcf PIE1, TXIE` from `control_uart_soft_recover`:

```python
# build_control_presets_ab_v162b.py, control_uart_soft_recover:
# REMOVED: bcf PIE1, TXIE, ACCESS
```

The OERR recovery now matches the stock approach: toggle CREN to clear
the error, drain the FIFO, reset parser state — without disrupting TX.

## Verification

- Semantic guard: `test_v162b_oerr_recovery_must_not_kill_txie` checks the
  built V1.62b HEX for `bcf PIE1, TXIE` (PIC18 opcode `0x989D`) in the
  patch stub region (`0x7000+`). Fails if the instruction is present.

- Standby pin I/O: `test_stdby_pin_io[v25+v162b]` confirms MAIN enters
  standby with correct pin states across all 8 firmware combinations.

- Real-hardware confirmation: V2.5 + fixed V1.62b flashed and standby
  verified working (2026-03-14).

## Affected Files

| File | Change |
|------|--------|
| `src/dlcp_fw/patch/build_control_presets_ab_v162b.py` | Removed `bcf PIE1, TXIE` from `control_uart_soft_recover` |
| `firmware/patched/releases/DLCP_Control_V1.62b.hex` | Rebuilt without the instruction |
| `tests/sim/test_main_stdby_pin_io.py` | Added semantic guard + standby pin I/O tests |
| `tests/sim/conftest.py` | Added stock V1.5b/V1.6b control fixtures |
| `docs/AB_PRESETS.md` | Status update |
