# V3.4 Size-Reclaim Campaign — Findings and Landed Result

Status: **target met 2026-06-12**.  Margin before the `0x4C00` preset-table
wall: **252 bytes** (headroom gate floor 24), from a 28-byte starting point.
Landed as the S-series (S1 pair-copy helper, S2 EEPROM-source mode,
S3 duplicate-run subroutines, S4 block descriptors) in `dlcp_main_v34.asm`
rev 0x90.

## Verified-exhausted mechanical classes

All scanners run against the rev-0x89/0x8A source/listing and re-run
against the post-S3 listing (rev 0x8E):

| Class | Result | Evidence |
| --- | --- | --- |
| `call` -> `rcall`, `goto` -> `bra` | **0 sites in relative reach** both scans; nearest miss 1047 words | reach scanner over the `.lst` symbol table |
| Helper factoring of repeated runs (>= 4 instr) | only the movff copy chains score above the call/return overhead | normalized n-gram scan, skip-shadow-aware |
| Cross-jump tail merges | zero candidates >= 8 B | suffix-group scan keyed on identical terminator |
| Shift-loop wrappers (`movlw K / rcall kernel / decfsz` idiom) | pairs only -> +-0 B after wrapper cost | idiom scan, 5 instances over 4 kernels |
| 32-bit constant staging quads | no repeated (cells, value) groups | quad scan |
| n=3..4 movff runs as descriptors | exactly break-even (movff = 4 B; n=4 descriptor = 16 B) | arithmetic; the original n>=5 cut was correct |

## The chain_copy engine (S1/S2/S4) — landed

A single table-driven copier replaces 15 inline copy runs.  Call shape
(descriptor as ONE `db` directive — see lesson 5):

```asm
    call        chain_copy, 0x0
    db          srcPage, dstPage, s0,d0,c0, s1,d1,c1, ..., 0xFF[, 0xFF]
```

- header: physical high bytes; `srcPage == 0xEE` switches the pair source
  to EEPROM via `eeprom_read_byte_W` (S2) — used by the boot settings
  load (13 cells incl. the 0x0D/0x14 odd forms) and the per-route trim
  load (0x10..0x13 -> 0x09B..0x09E).
- rows: `(srcL, dstL, count)` contiguous blocks (S4); scattered singles
  cost 3 B/cell, so one all-scattered site (the bank-1 settings restore)
  stayed inline movff.
- exit: TOS rewritten from TBLPTR (movf/movwf — movff may not target
  TOSx), odd resume PC consumes the pad byte; **BSR = 0 on exit, always**
  (block counters live in bank 3 and the engine banks there).
- scratch: `chain_copy_srch/dsth/srcl/dstl/cnt` at 0x3C5..0x3C9 (bank 3
  upper, movff-only, ISR-untouched, no stock aliasing).

S3: four duplicated 4-cell movff runs factored into plain subroutines
(`s3_coeff_stage_049`, `s3_math_stage_025`, `s3_math_stage_029`,
`s3_adc_stage_427a`).

## Margin ledger

| Step | Margin |
| --- | --- |
| start (rev 0x86..0x8B pristine) | 28-30 B |
| S1 pair-mode chain_copy, 14 sites | 74 B |
| S2 EEPROM-source mode, 2 sites (+pins) | 120 B |
| S3 duplicate-run subroutines, 4 pairs | 154 B |
| S4 block descriptors + single-db packing | **252 B** |

## Root causes found on the way (all fixed)

1. **Rust core TOS write-through gap** (`crates/dlcp-sim`): `movwf` to
   TOSL/TOSH/TOSU updated only the memory mirror; `return` popped the
   stale internal stack entry.  Real silicon honors TOS writes
   (DS39632E §5.1.2.1).  This made chain_copy's TOS-fixup return appear
   to jump back into the descriptor — and because PIC18 second
   instruction words decode as NOP, most descriptors executed as benign
   garbage ("boots fine"), while one site's bytes formed a CALL opcode
   and ran away (PcOutOfBounds at ~13.7 M Tcy).  The session-0 ledger
   blamed PROD liveness at the 19e6 volume chain — **that theory was
   wrong**; with the core fixed, the same conversion set is clean.
   Fix: staged TOS write applied to the call-stack array post-step
   (`tos_sw_write_pending`), pinning test
   `movwf_tos_write_through_patches_computed_return`.
2. **`inject_main_frames_fifo` ISR race** (sim facade): the injector
   wrote MAIN0's RX ring + wr index while the firmware's RX ISR was
   mid-enqueue holding the OLD wr in W (GIEH=0, RCIF=1 at the failing
   tick).  The ISR then overwrote the injected route byte at the stale
   index (B0 -> B1: broadcast became addressed; the PB1->PB2 forward
   silently disappeared) and left a phantom stale cell in the stream.
   Impossible on real hardware (CONTROL's bytes serialize through the
   same UART).  Fix: the facade defers injection (bounded) until
   GIEH=1 and RCIF=0.  Any phase-sensitive chain test could have hit
   this after ANY firmware change.
3. **gpasm pads every `db` directive to word alignment** (PIC18
   absolute mode).  Multi-line descriptors with odd-length rows gain
   phantom 0x00 bytes that desynchronize a stream parser (here: cnt=0
   was read, decfsz wrapped, 256-byte wild copy sprayed RAM and killed
   boot).  Emit descriptor streams as a SINGLE `db` with even total
   length.

## Lessons that bind any retry

1. Every converted chain needs per-site liveness proofs for W, STATUS,
   FSR0, TBLPTR (and BSR once the helper banks): the static RAM checker
   models movlb effects through calls, but audit anyway.
2. Boot-test with `step_tcy` (12 MHz instruction clock), NOT
   `step_ticks` (48 MHz universal clock); a 60 M-tick "boot OK" covers
   only 0.31 s.
3. `step_until_pc_hit(idx, lo, hi, 0)` is a pure PC read
   (checks-before-stepping); chunked stepping misses brief windows.
4. Descriptor-after-call designs need: a TOS write-through pinning test
   in `crates/dlcp-sim`, a >= 120 M-Tcy boot soak, and listing-level
   byte verification of at least one descriptor per emission shape.
5. When a converted build fails a timing-sensitive chain test, prove
   the frame actually reached the wire (`uart_tx_records_full` /
   `uart_rx_records_full`) before blaming the firmware: both sim-side
   root causes above produced "firmware-looking" symptoms.

## Wall facts

- `TABLE_SIZE = 0x0A00` per preset: the bake blankets `0x4C00..0x55FF`
  and `0x5600..0x5FFF` wholesale — no hidden executable flash in or
  between the capture regions; `0x4C00` is a hard wall.
- PIC18F2455 flash ends at `0x5FFF`; both capture banks are spoken for.

## Remaining (unspent) candidate inventory

| Candidate | Est. | Notes |
| --- | --- | --- |
| Per-route trim-ladder table rewrite (`flow_cmd_dispatch_gated_19d6`) | ~+20 B | touches the rev-0x87 SAFETY selector + an empirically load-bearing clrf; do not attempt casually |
| Feature demotion: RA1 edge counter (`diag_p`, sim-only) | ~+20-30 B | needs a ledger entry + test retirement + user sign-off |
| Hand passes over the top functions (32f8/adc_boot_gate_exit/2bb8/2328/38a2/19e6/39a6) | 10-20 % each | the proven road if more is ever needed |
