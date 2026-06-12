# V3.4 Size-Reclaim Campaign — Session-0 Findings (2026-06-13)

Status: **scouting complete, no reclaim landed**.  Margin before the
`0x4C00` preset-table wall: **28 bytes** (headroom gate floor 24).
Target: **200+ bytes free**.  This document records what was verified
so the campaign proper (V32_SIZE_OPTIMIZATION successor, multi-session)
does not re-walk dead ends.

## Verified-exhausted mechanical classes

All scanners run against the rev-0x89/0x8A source/listing:

| Class | Result | Evidence |
| --- | --- | --- |
| `call` -> `rcall`, `goto` -> `bra` | **0 of 263 sites in relative reach**; nearest miss 1047 words | reach scanner over the `.lst` symbol table; the V3.1 W06 exhaustive sweep + disciplined V3.2+ additions hold |
| Helper factoring of repeated runs (>= 4 instr) | only the 20 movff copy chains score above the call/return overhead | normalized n-gram scan, skip-shadow-aware |
| Cross-jump tail merges (shared suffixes into one copy) | zero candidates >= 8 B | suffix-group scan keyed on identical terminator |

## The movff-chain compressor (`chain_copy`) — built, measured, reverted

14 uniform-page movff runs (5..12 entries, 612 B inline) were converted
to a shared table-driven copier using the inline-descriptor-after-call
pattern (TOS read -> TBLPTR; sentinel-terminated byte pairs; TOS
write-back past the descriptor; PRODH/PRODL as page scratch; FSR0-only
data moves).  **Measured +44 B net** (margin 28 -> 72).

It boots, then **dies at ~13.7 M Tcy** (runaway PC -> PcOutOfBounds),
bisect-isolated to the `flow_cmd_dispatch_gated_19e6` volume chain
(source range 1576..1583), layout-independent.  Prime suspect:
**PRODH/PRODL are live across that chain** (the
`main_core_service_2abc` -> `297e` math hand-off), so the helper's page
scratch corrupts the math state.  Disproven en route, with evidence:

- rust core TOS writes ARE modeled (`stack.rs` tos_write + tests);
- `call` pushes PC+4 (test-pinned), so descriptor offsets were right;
- emitted descriptor bytes verified correct in the listing;
- the `_op` equates are correct low bytes for all operands used.

Lessons that bind any retry:

1. Every converted chain needs **per-site liveness proofs for W,
   STATUS, PROD, FSR0, and TBLPTR** — not just a branch-after-chain
   audit.  The 19e6 failure was a liveness miss, not a mechanism miss.
2. There is **no universally-dead 2-byte scratch** in this firmware;
   a v2 design should carry pages per pair (3-byte entries,
   `(srcL, dstL, srcH<<4|dstH)`, TABLAT-phase-ordered) and use no
   persistent scratch at all.  Per-pair cost rises to 3 B, so only
   chains >= 7 entries stay profitable (~+60-70 B total).
3. **Boot-test with `step_tcy`** (12 MHz instruction clock).  A
   `step_ticks` (48 MHz universal clock) 60 M "boot OK" covers only
   0.31 s and missed the ~1.04 s death — this masked the failure for
   a full bisect round.
4. PIC18 second instruction words decode as NOP, so return-address
   math bugs hide from all normal code; descriptor designs need
   explicit pinning tests in `crates/dlcp-sim` and a dedicated boot
   soak before any conversion lands.

## Remaining candidate inventory (campaign backlog)

| Candidate | Est. | Risk notes |
| --- | --- | --- |
| EEPROM settings-loader table (17 `movlw/eeprom_read_byte_W/movwf` triples, one contiguous block) | ~+18 B | normal call/return; single staged TBLPTR load amortized once |
| Per-route trim-ladder table rewrite (`flow_cmd_dispatch_gated_19d6`) | ~+20 B | touches the rev-0x87 SAFETY selector — must re-run the excursion regression |
| movff-chain compressor v2 (3-byte pairs, no scratch, chains >= 7 only) | ~+60-70 B | bound by lessons 1-4 above |
| Hand passes over the top functions (`main_i2c_service_32f8` 160 B, `adc_boot_gate_exit` 152, `flash_service_2bb8` 150, `2328_2380` 140, `38a2` 126, `19e6` 120, `39a6` 118) | unknown; V3.1/V3.2 precedent ~10-20 % | slow, careful, the proven road |
| Feature demotion: RA1 edge counter (`diag_p`, documented sim-only) | ~+20-30 B | needs a ledger entry + test retirement per the dead-code policy |

Realistic path to 200+: v2 compressor + EEPROM table + 2-3 hand passes,
executed as W-series-style experiments with the full gate per landing.

## Wall facts

- `TABLE_SIZE = 0x0A00` per preset: the bake blankets `0x4C00..0x55FF`
  and `0x5600..0x5FFF` wholesale — **no hidden executable flash** in or
  between the capture regions; `0x4C00` is a hard wall.
- PIC18F2455 flash ends at `0x5FFF`; both capture banks are spoken for.
