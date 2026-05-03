# Task #44 — V1.71+V3.2 LCD vs cmd 0x44 cell-value divergence

**Status:** root cause identified, simulator reproduction landed, **fix landed
2026-05-04 on `feature/sim-rewrite-rust`** (this commit).  Awaiting real-HW
operator retest per §5 step 5.
**Hardware session:** 2026-04-27 (V1.71 CONTROL + 2× V3.2 MAIN).
**Simulator reproduction commits:** `b367528` (rust internal test) + `8d547fe` (Python facade unblock).
**Fix implementation note:** the recommended Fix #1 placement (inside
`app_cold_init`, immediately before the `goto flow_ccs_0FA0_103C` exit) was
NOT possible without breaking the byte-identical vector block contract --
adding code in `app_cold_init` body shifts `isr_entry` past 0x0003a6, which
breaks `test_v171_phase_a_vector_block_byte_identical`.  Instead, the fix
landed at the cold-init exit *target* `flow_ccs_0FA0_103C` (byte 0x103C,
far past the vector block region), as a loop-form (10 instructions, +20
bytes) rather than the 25-instruction unrolled form recommended in §4
below.  Source-contract gate: `tests/sim/test_v171_baseline.py
::test_v171_zeros_diag_cache_at_cold_init`.

## 1. Field observation

On real DLCP rig (V1.71 CONTROL + V3.2 MAIN0 + V3.2 MAIN1, both MAINs at HEALTHY POR):

- **cmd 0x44** (USB HID readout from MAIN-side BANK 2 RAM at `diag_i..diag_p`, 0x2E5..0x2EB) reports
  `Runtime: I0 D0 S0 B0 R0 A0 P0` — **all-zero counters** on both MAINs.
- **CONTROL LCD** on the PB1 / PB2 Diagnostics screens shows substantial Overflow content:
  ```
  PB1: I+ D1 SE B4
  RA A3 O8 V6 W+..

  PB2: I+ D  S+ B
  R+ A9  P  OB W9..
  ```

The LCD reports MAIN counters as `I+`, `D1`, `SE`, etc. (i.e. `15+`, `1`, `14`, etc. per V1.71 Tier-1
Overflow encoding) while cmd 0x44 from the same firmware on the same MAIN reports those counters
as zero. The displays disagree about what MAIN is reporting.

Source: `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §4.

## 2. Root cause

V1.71 CONTROL renders the Diagnostics LCD from a **local cache** in CONTROL's BANK 1 RAM, not from
MAIN's BANK 2 RAM. The two are independent memories on different cores:

| Source | Address  | Owner       | Updated by                                                  |
| ------ | -------- | ----------- | ----------------------------------------------------------- |
| LCD    | 0x180+   | CONTROL     | BF/2N reply parser (`v171_bf2x_case_check`, asm:1196+)      |
| cmd 0x44 | 0x2E5+ | each MAIN   | MAIN-side hooks (`diag_inc_sat` macro, sprinkled in V3.2)   |

For each PB, CONTROL holds 11 cells starting at the per-PB cache base (`v171_diag_pb1_i = 0x180`,
`v171_diag_pb2_i = 0x18B`):

| Slot | BF cmd | Cell |
| ---- | ------ | ---- |
| 0    | BF/21  | I    |
| 1    | BF/22  | D    |
| 2    | BF/23  | S    |
| 3    | BF/24  | B    |
| 4    | BF/25  | R    |
| 5    | BF/26  | A    |
| 6    | BF/27  | P (RUNTIME LAST — clears RUNTIME_PENDING, marks PB present, toggles target) |
| 7    | BF/28  | O (Tier-1 POR flag)  |
| 8    | BF/29  | V (Tier-1 BOR flag)  |
| 9    | BF/2A  | W (Tier-1 WDT flag)  |
| 10   | BF/2B  | X (RESET LAST — clears RESET_PENDING, sets reset_seen) |

The BF/2N parser writes data **unconditionally** to the cache cell (asm:1276
`movff rx_parsed_data, INDF0`) — i.e. when MAIN replies with data=0, the cache cell IS overwritten
with 0. So the cache CAN be made consistent with MAIN, given a successful reply burst.

### What goes wrong

V1.71 `app_cold_init` (`src/dlcp_fw/asm/dlcp_control_v171.asm:752..784`) configures peripherals
(TBLPTRU, RCSTA, TRIS, ANSEL, ADC, IOCB, baud rate, RCSTA.SPEN, RCSTA.CREN), then jumps to
`flow_ccs_0FA0_103C` (asm:784 `goto flow_ccs_0FA0_103C`).  It does **NOT** zero the diag cache
cells at 0x180..0x195 (PB1 11 cells at 0x180..0x18A + PB2 11 cells at 0x18B..0x195) before the
final `goto`.  After POR the cache holds whatever random RAM state the silicon left there.

If a BF/2N reply burst delivers **all 11 cells**, the cache fully overwrites the POR garbage and
LCD matches cmd 0x44. But if any BF/2N frame is dropped — and on real silicon at least some are,
because:

- the parser-stall watchdog `v171_service_rx_frame_gap` (asm:2633+) reload constant
  `V171_RX_FRAME_GAP_RELOAD = 0xF8` (8-step countdown, ~24 K ticks) is shorter than the
  cmd-to-data spacing in a BF/2N burst (~15.5 K ticks per byte ≥ ~24 K ticks per 3-byte frame
  in the worst case; documented in P3.6b research, see `docs/SIM_REWRITE_RUST_PROGRESS.md` P3.6b
  entry), AND
- BF/2N bursts arrive packed enough that the watchdog can fire mid-frame and clear
  `rx_frame_position`, dropping the next byte at the parser layer

— then the cache cell for the dropped frame stays at its random POR value, and the LCD renders
that garbage.

cmd 0x44 reads MAIN's BANK 2 directly via USB HID and does NOT cross the BF/2N path, so it
reports MAIN's actual state untouched.

## 3. Simulator reproduction

The rust simulator can deterministically reproduce the **symptom** (LCD shows non-zero, MAIN RAM
is zero) by seeding CONTROL's cache with the exact values from the real-HW LCD capture, then
navigating to the Diag page and reading the LCD raster.

### Rust crate test (Phase A, no LCD render)

`crates/dlcp-sim/tests/multicore_parity.rs::control_diag_lcd_render_decouples_from_main_diag_ram_when_cache_seeded`

Demonstrates structural independence: writing to CONTROL's cache cells does not touch MAIN's
BANK 2 RAM, and vice-versa.

### Rust crate test (Phase B, full LCD render)

`crates/dlcp-sim/tests/multicore_parity.rs::control_diag_lcd_render_pb1_screen_reflects_seeded_cache_not_main_ram`

Boots the chain to convergence, navigates to PB1 Diag via 4 RIGHT-press cycles, seeds cache cells
with `[I=0x0F, D=0x01, S=0x0E, B=0x04, R=0x0A, A=0x03, P=0x08]` (the values the real-HW LCD shows),
sets `v171_diag_present = 0x01` so the renderer takes the Overflow layout, lets the cadence redraw
fire, then asserts:

- LCD line 0 = `PB1: I+ D1 SE B4`
- LCD line 1 = `RA A3 P8        `
- MAIN0 BANK 2 (`diag_d`/`s`/`b`/`r`/`a`/`p`) all unchanged at 0x00

The combination proves the LCD content sources from CONTROL's cache, not MAIN's runtime cells.

### Python facade reproduction script

```sh
PYTHONPATH=src .venv_ep0/bin/python scripts/reproduce_bug44_lcd_vs_cmd44.py
```

The script: builds the V1.71+V3.2+V3.2 chain, boots to Volume display, seeds CONTROL's PB1 cache
with the exact real-HW values, navigates to PB1 Diag via 4 short RIGHT-presses (direct PORTA
manipulation with 5 M-tick hold; the facade's `Chain.press()` holds 50 M ticks which V1.71
button-repeat interprets as multiple presses), waits for the redraw cadence, and reports the
LCD raster + cache state.

Output:

```text
[STEP 8] Final LCD reads:
          line0 = 'PB1: I+ D1 SE B4'
          line1 = 'RA A3 P8        '

[STEP 9] CONTROL PB1 cache after LCD render:
          0x180 = 0x0F (seeded 0x0F) OK
          0x181 = 0x01 (seeded 0x01) OK
          0x182 = 0x0E (seeded 0x0E) OK
          0x183 = 0x04 (seeded 0x04) OK
          0x184 = 0x0A (seeded 0x0A) OK
          0x185 = 0x03 (seeded 0x03) OK
          0x186 = 0x08 (seeded 0x08) OK

  BUG #44 SYMPTOM REPRODUCED in rust simulator.
```

Note: rust's POR clears RAM to zero, so the bug does NOT spontaneously manifest in the simulator.
The seeded reproduction encodes the **architectural divergence** (cache-vs-MAIN RAM independence)
that allows the field bug, without modeling the random POR RAM state itself.

## 4. Suggested fix

### Fix #1 (PRIMARY, defensive — recommended)

**Initialize the diag cache cells to zero in `app_cold_init`.**

Insert the following block IN PLACE of (i.e., immediately before) the existing
`goto flow_ccs_0FA0_103C` at `src/dlcp_fw/asm/dlcp_control_v171.asm:784`.  The current
`app_cold_init` ends with `bsf RCSTA, CREN, A` at asm:783 followed by an unconditional `goto`
at asm:784; any block placed AFTER the `goto` (e.g. between asm:784 and `isr_entry:` at
asm:786) is unreachable, so the new clrfs MUST be inserted before line 784.

```asm
        ; ... existing app_cold_init body up through asm:783 ...
        bsf     RCSTA, CREN, A                              ; reg: 0xfab, bit: 4 (asm:783)

        ; --- Task #44 fix: zero the V1.71 Tier-1 diag cache cells ---
        ; Without this, the cells start at random POR RAM and a partial
        ; BF/2N reply burst (e.g. some frames dropped by the parser-stall
        ; watchdog v171_service_rx_frame_gap) leaves the LCD rendering
        ; garbage that diverges from cmd 0x44's direct read of MAIN BANK 2.
        ; See docs/analysis/TASK_44_LCD_VS_CMD44_DIVERGENCE.md.
        movlb   0x01
        clrf    v171_diag_pb1_i,        BANKED  ; phys 0x180
        clrf    v171_diag_pb1_d,        BANKED  ; phys 0x181
        clrf    v171_diag_pb1_s,        BANKED  ; phys 0x182
        clrf    v171_diag_pb1_b,        BANKED  ; phys 0x183
        clrf    v171_diag_pb1_r,        BANKED  ; phys 0x184
        clrf    v171_diag_pb1_a,        BANKED  ; phys 0x185
        clrf    v171_diag_pb1_p,        BANKED  ; phys 0x186
        clrf    v171_diag_pb1_reset_por,BANKED  ; phys 0x187
        clrf    v171_diag_pb1_reset_bor,BANKED  ; phys 0x188
        clrf    v171_diag_pb1_reset_wdt,BANKED  ; phys 0x189
        clrf    v171_diag_pb1_reset_sw, BANKED  ; phys 0x18A
        clrf    v171_diag_pb2_i,        BANKED  ; phys 0x18B
        clrf    v171_diag_pb2_d,        BANKED  ; phys 0x18C
        clrf    v171_diag_pb2_s,        BANKED  ; phys 0x18D
        clrf    v171_diag_pb2_b,        BANKED  ; phys 0x18E
        clrf    v171_diag_pb2_r,        BANKED  ; phys 0x18F
        clrf    v171_diag_pb2_a,        BANKED  ; phys 0x190
        clrf    v171_diag_pb2_p,        BANKED  ; phys 0x191
        clrf    v171_diag_pb2_reset_por,BANKED  ; phys 0x192
        clrf    v171_diag_pb2_reset_bor,BANKED  ; phys 0x193
        clrf    v171_diag_pb2_reset_wdt,BANKED  ; phys 0x194
        clrf    v171_diag_pb2_reset_sw, BANKED  ; phys 0x195
        clrf    v171_diag_target,       BANKED  ; phys 0x196 (banked 0x096)
        clrf    v171_diag_present,      BANKED  ; phys 0x197 (banked 0x097)
        clrf    v171_diag_reset_seen,   BANKED  ; phys 0x19D (banked 0x09D)
        movlb   0x00                            ; restore default bank
        ; --- end Task #44 fix ---

        goto    flow_ccs_0FA0_103C                          ; dest: 0x00103c (was asm:784)
```

This places the zero-init AFTER all peripheral configuration (so RCSTA.SPEN/CREN, TRIS, baud
rate, etc. are already up — same way as the existing layout) but BEFORE the existing
`goto flow_ccs_0FA0_103C` so the block is on the live execution path.  The `movlb 0x00` after
the clrfs restores the bank for the goto target, which expects access bank.

A loop with FSR0 is more compact (~6-8 instructions vs ~25) but the unrolled form above is
clearer and the flash budget on V1.71 has headroom (per `docs/V32_DIAG_TIER1_SPEC.md`).

**Cost:** ~25 instruction words once, executes only at POR / cold reset.

**Effect:** all cache cells start at 0. On a healthy idle rig, the LCD renders `PB1` + 13 spaces
(or `PB2`) on entry to the Diag page, matching cmd 0x44's all-zero report. After a partial BF/2N
burst the LCD shows the actual delivered values plus zeros for any dropped cells — still
truthful, no random garbage.

**Risk:** very low. Only changes cold-init behavior; no runtime path affected; idempotent under
re-boot.

**Verifies on rust:** The reproduction script's seeding of the cache cells exactly demonstrates
what POR garbage looks like; the `clrf` fix would make those cells start at 0, removing the
divergence surface for unreceived frames.

### Fix #2 (SECONDARY, root cause of dropped frames)

**Suppress / lengthen the parser-stall watchdog while `rx_parsed_cmd` is in the BF/2N range.**

Two variants:

a) **Increase reload** — change `V171_RX_FRAME_GAP_RELOAD` from `0xF8` to a value that gives
   the BF/2N burst enough budget. Per the P3.6b instrumentation, frames arrive ~15.5 K ticks
   apart (~5.2 K Tcy). A reload of `0xE0` (32 steps × ~3.1 K ticks each ≈ 100 K ticks) would
   cover even the worst-case BF/2N spacing with margin. Risk: changes parser-stall timing for
   ALL frame types, may delay legitimate stall detection.

b) **Conditional suppression** — gate the watchdog reload on
   `rx_parsed_cmd ∈ [0x21, 0x2B]`. While in BF/2N parsing, skip the watchdog
   countdown so a slow data byte doesn't get nuked. Risk: more invasive (multiple call-sites);
   the watchdog's purpose is exactly to recover from stuck mid-frame state, so suppressing it
   needs careful bound checking.

**Cost:** Variant (a) is 1 byte change in `dlcp_control_ram.inc:127`. Variant (b) is ~4-6
instruction words at the watchdog reload site (asm:2645).

**Effect:** Reduces / eliminates the dropped-frame condition that creates the cache-vs-MAIN
divergence in the first place.

**Risk:** medium. Variant (a) is the safer of the two; variant (b) may regress other parser
flows. Either fix is OPTIONAL if Fix #1 is applied (the divergence becomes invisible because
cells start at 0 — the LCD shows the truth: zero counters).

### Recommended deployment

Apply **Fix #1 alone** as the V1.71 release patch. The LCD will agree with cmd 0x44 immediately
because the cache starts at 0 and any received BF/2N frames overwrite the 0s with the same value
they came from on the wire. Dropped frames simply show 0 on the LCD, which is the correct
display for "no data received yet."

Defer Fix #2 as a P3.6b research follow-up. The dropped-frame condition is a separate
correctness concern (chain-protocol robustness); fixing the LCD divergence does not require
fixing the dropped-frame root cause, and the dropped-frame fix is harder to validate without
running the full instrumented probe in `crates/dlcp-sim/tests/multicore_parity.rs::three_core_ring_v171_v32_v32_*`.

## 5. Verification path

1. **Apply Fix #1** to `src/dlcp_fw/asm/dlcp_control_v171.asm`.
2. **Rebuild canonical V1.71 release** via `scripts/build_v171_release.py` (auto-bumps revision byte).
3. **Re-run rust simulator tests** — confirm the new V1.71 cold-init shows zero cache cells:
   ```
   cargo test --release -p dlcp-sim --test multicore_parity \
       three_core_ring_v171_v32_v32_boots_under_silicon_topology
   cargo test --release -p dlcp-sim --test multicore_parity \
       control_diag_lcd_render_decouples_from_main_diag_ram_when_cache_seeded
   ```
4. **Add a positive-path regression test** that boots the chain, navigates to PB1 Diag without
   seeding any cache cells, and asserts the LCD shows `PB1` + 13 spaces (Absent layout) until
   actual BF/2N replies arrive — proving the cold-init zeroed the cells.
5. **Real-HW retest** (operator, with hardware rig): flash V1.71 with the cold-init `clrf`
   patch, navigate to Diag page on a fresh POR boot, verify cmd 0x44 == LCD content for at
   least one cadence cycle.

## 6. Cross-references

- `docs/analysis/HW_2026-04-27_DIAG_AND_STDBY_FINDINGS.md` §4 — original field observation
- `docs/V163B_DIAGNOSTICS_MENU_SPEC.md` — Tier-1 layout encoding (Overflow / Healthy / Absent)
- `docs/V32_DIAG_TIER1_SPEC.md` — cmd 0x44 specification + flash budget
- `docs/SIM_REWRITE_RUST_PROGRESS.md` P3.6b — parser-stall watchdog research (drove Fix #2 hypothesis)
- `crates/dlcp-sim/tests/multicore_parity.rs:3814+` — Phase A reproduction (structural)
- `crates/dlcp-sim/tests/multicore_parity.rs:4026+` — Phase B reproduction (LCD render)
- `src/dlcp_fw/asm/dlcp_control_v171.asm:752+` — `app_cold_init` (where Fix #1 lands)
- `src/dlcp_fw/asm/dlcp_control_v171.asm:1196+` — `v171_bf2x_case_check` (BF/2N parser)
- `src/dlcp_fw/asm/dlcp_control_v171.asm:2633+` — `v171_service_rx_frame_gap` (parser-stall watchdog)
- `src/dlcp_fw/asm/dlcp_control_ram.inc:127` — `V171_RX_FRAME_GAP_RELOAD = 0xF8`
- `src/dlcp_fw/asm/dlcp_control_ram.inc:239+` — `v171_diag_pb1_i..pb2_reset_sw` cache cell layout
