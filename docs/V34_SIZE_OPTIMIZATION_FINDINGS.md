# V3.4 Size-Reclaim Campaign — Findings and Landed Result

Status: **target met 2026-06-12** by the original S-series, then refreshed
**2026-06-14** after the FIELD safety fixes had spent the reserve down to the
user-relaxed 10-byte floor.  Current MAIN V3.4 rev `0xA5` margin before the
`0x4C00` preset-table wall: **102 bytes** (`listing_app_end=0x4B9A`), from
the immediate pre-campaign 10-byte floor (`listing_app_end=0x4BF6`).

Historical 2026-06-12 result: margin was **250 bytes by the headroom-gate
measure** (raw listing scan: 252; the gate convention is authoritative), from
a 28-byte starting point.  Landed as the S-series (S1 pair-copy helper, S2
EEPROM-source mode, S3 duplicate-run subroutines, S4 block descriptors) in
`dlcp_main_v34.asm` rev 0x90.

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
| S4 block descriptors + single-db packing | **250 B** (gate measure) |
| FIELD safety/counter work through rev 0xA4 | 10 B |
| T1 SRC4382 secondary-write table walker, rev 0xA5 | **102 B** |

## T1 SRC4382 secondary-write table walker — landed 2026-06-14

Scope:

- `main_i2c_service_32f8`: the ordered SRC4382/cfg71 cold-init write stream
  was converted from 16 inline `(value -> stock_006, register -> write)`
  blocks to `main_i2c_service_32f8_table` plus `i2c_secondary_write_rows`.
- `hw_standby_shutdown`: the three rail-drop writes
  `(0x00,0x1B)`, `(0x00,0x1C)`, `(0x00,0x1D)` reuse the same row walker via
  `hw_standby_shutdown_i2c_table`.

Measured result:

- Before T1: `listing_app_end=0x4BF6`, free bytes before `0x4C00` = 10.
- After T1 canonical rebuild: `listing_app_end=0x4B9A`, free bytes before
  `0x4C00` = 102.
- Net reclaim: **+92 bytes** of margin.
- Canonical build: `scripts/build_v34_release.py`, EEPROM rev
  `0xA4 -> 0xA5`.

Behavior-preservation proof:

- The cold-init table is pinned by
  `test_v34_src4382_cold_init_table_preserves_exact_ordered_writes`.
- The standby rail-drop table is pinned by
  `test_v34_standby_shutdown_secondary_write_table_preserves_rail_drop_order`.
- The executable walker label deliberately does **not** end in `_table`; the
  RAM-safety CFG treats `_table` labels as data anchors.
- The walker avoids TOS/return-address tricks and uses `TBLPTR` plus
  `stock_008_acc` as a local access-bank loop counter.  `stock_008_acc` is
  scratch at both call sites and is not clobbered by `i2c_secondary_dev_write`
  or its timeout/NACK recovery paths.  An FSR0-backed counter was rejected
  during implementation because the diagnostic timeout path uses FSR0.
- `TBLPTRU` is cleared inside the walker before the first `tblrd*+`, so callers
  only stage `TBLPTRL/H` and row count.

Verification:

```bash
PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim/test_v34_v173_refactoring_contracts.py
# 18 passed, 1 xfailed in 0.20s

PYTHONPATH=src .venv_ep0/bin/python - <<'PY'
from dlcp_fw.analysis.ram_bank_safety import check_targets
findings = check_targets(['main-v34'])
print('findings', len(findings))
PY
# findings 0

PYTHONPATH=src .venv_ep0/bin/python scripts/build_v34_release.py
# built canonical V3.4 release ... (EEPROM rev 0xA4 -> 0xA5)

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q \
  tests/sim/test_ram_bank_safety.py \
  tests/sim/test_v34_v173_refactoring_contracts.py \
  tests/sim/test_v34_v173_release_builders.py \
  tests/sim/test_v34_src4382_lock_hysteresis.py \
  tests/sim/test_v34_autodetect_loss_debounce.py \
  tests/sim/test_v34_preset_src_hole_field_bug.py \
  tests/sim/test_v34_field_bugs_20260610.py \
  tests/sim/test_v34_v173_field_repros_20260613.py
# 97 passed, 3 xfailed in 623.93s

PYTHONPATH=src .venv_ep0/bin/python -m pytest -q tests/sim
# 1630 passed, 2 skipped, 3 xfailed, 4 warnings in 4307.58s
```

Parked/rejected follow-up levers for this wave:

- The additional `movlw/movwf` init runs around source lines 5334/6043/9845
  were not touched: they need a different RAM/SFR table writer, and T1 already
  met the target with a smaller proof surface.
- XOR dispatch ladders remain rejected: likely break-even on PIC18 and higher
  behavioral risk.
- New `chain_copy`/descriptor rewrites remain rejected for this wave because
  the existing chain-copy interrupt-safety proof is still explicitly xfailed.
- Feature demotion remains off the table.

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
