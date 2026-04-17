# V1.71 CONTROL Source Rewrite — Specification

Date: 2026-04-17
Status: draft
Base: V1.7 CONTROL source (stock V1.6b byte-identical — see
  `docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md`)
Pair: V3.1+ MAIN firmware

## Purpose

V1.71 is the first **feature-bearing** source-level CONTROL firmware
build.  It starts from the V1.7 assembly source
(`dlcp_control_v17.asm`, byte-identical to stock V1.6b) and adds
ALL features from V1.61b through V1.64b as direct source edits.

V1.71 = V1.7 + V1.61b (A/B presets) + V1.62b (reconnect / OERR
robustness) + V1.63b (BF/08 DSP-fault parser and UI) + V1.64b
(explicit IR standby/wake endpoints).  It is functionally what the
V1.64b binary overlay was intended to deliver, with zero overlay
regions and no jump-out hooks.

This spec is the CONTROL analog of `docs/V31_SOURCE_REWRITE_SPEC.md`
for MAIN.

## Why V1.71 instead of continuing V1.64b-style binary patching

The four V1.6x binary patch builders
(`build_control_presets_ab_v16b.py`,
`build_control_presets_ab_v162b.py`, `_v163b.py`, `_v164b.py`)
compose a ~980-byte overlay into a single free flash region starting
at `org 0x7000`.  This approach has accumulated problems:

1. **Composition complexity**: the four patch sets share hook sites
   at the full-sync entry (~`0x0B36`), the IR dispatch
   (~`0x0DE6`), the parser entry (~`0x044A`), and the reconnect
   wait (~`0x12BC`).  Each new feature must thread through the
   earlier versions' hooks in order, and the stacking invariants
   are only validated by semantic guard tests.
2. **Latent bug reservoir**: `docs/analysis/V162B_STDBY_TXIE_BUG.md`
   and `docs/analysis/V162B_RECONNECT_WAKE_BUG.md` both stemmed from
   the binary overlay preserving stock invariants that were no
   longer valid once an adjacent hook was inserted.  Writing the
   logic inline removes the indirection that hid those bugs.
3. **No semantic source**: unlike MAIN (`dlcp_main_v30_comments.asm`),
   CONTROL has never had a maintainable assembly source.  All work
   is disassembly + Python patch-builder driven.  That blocks the
   diagnostics/menu plans documented in
   `docs/V163B_DIAGNOSTICS_MENU_SPEC.md`.
4. **Space pressure at the margins**: the 0x7000–0x77FF free zone
   (~4 KB between end of stock application code and start of the
   bootloader at 0x7800) is large in absolute terms, but the V1.64b
   overlay already consumes ~24 % of it, and any future features
   compound both size and composition risk.

V1.71 eliminates ALL of these problems by design.

---

## Design Philosophy: Clean-Sheet, Not Patching

V1.71 is written as if we were the **original firmware engineer**
adding these features from the start.  There are:

- **No jump-out hooks** (`goto patch_region`).  Enhanced functions
  have their new logic inline in their bodies.
- **No fixed-address stub regions** (no `org 0x7000` for patch
  code).  New code flows naturally between neighboring functions.
- **No dead-zone hunting**.  Space is unlimited because functions
  grow to the size they need and the assembler places everything.
- **No hardcoded addresses**.  All branch, call, and data
  references use symbolic labels.  Addresses shift freely as
  function bodies grow.

### What this means concretely

Instead of the V1.62b pattern:
```asm
uart_rx_parser:                     ; stock function_019
    goto    reconnect_recovery_stub ; ← jump out to 0x7000 region
```

V1.71 writes:
```asm
uart_rx_parser:                     ; enhanced function_019
    btfss   RCSTA, OERR, ACCESS     ; RX overflow?
    bra     .no_oerr
    bcf     RCSTA, CREN, ACCESS     ; clear OERR, drop partial byte
    bsf     RCSTA, CREN, ACCESS
    movf    RCREG, W, ACCESS        ; drain any residue
    clrf    rx_parser_state, BANKED ; re-prime parser
    bra     .done
.no_oerr:
    ; ... stock parser body follows ...
    ; BF/08 dispatch case inlined here
.bf08_case:
    movff   RCREG, bf08_fault_byte
    bsf     control_flags, DSP_FAULT_BIT, BANKED
    ...
.done:
    return
```

The function is **self-contained**.  No trampolines.  No remote stubs.

### Addresses WILL shift

Application code starts at 0x004C (right after the vector block)
and ends in stock V1.6b somewhere below the 0x7000 bootloader-side
boundary.  Adding ~1 KB of inline enhancements shifts all
application code after the first modification.  This is by design
— V1.71 is a new firmware, not a stock-compatible overlay.

**Any stock V1.6b addresses cited elsewhere in this document**
(e.g. `0x0B36`, `0x0DE6`, `0x044A`, `0x12BC` in the "Why V1.71"
section above; `0x03A6`, `0x0366`, `0x0190` in the vector block;
the TBD rows in the gpsim overlays table) **are V1.6b reference
points, not V1.71 placement.**  V1.71 places its equivalent code
by semantic label, and the gpasm `.lst` yields the post-shift
addresses for any tool that needs them.

The gpsim simulation infrastructure (`manifests.py`) uses
hardcoded stock addresses for CONTROL overlays.  **These must be
updated for V1.71**, reusing the `parse_gpasm_symbols()` helper
already landed for V3.0/V3.1.

### Hardware-pinned addresses

The PIC18F25K20 CPU exposes three fixed reset / interrupt vectors
that are jumped to regardless of label resolution:

| CPU vector | V1.6b stock target | Status |
|------------|--------------------|--------|
| 0x0000 | `goto 0x7800` (bootloader entry) | **LIVE** — reset vector. The bootloader decides whether to enter update mode or hand control to the application. |
| 0x0008 | `goto 0x03A6` (high-priority ISR body) | **LIVE** — high-priority ISR. Stock clears IPEN, so all interrupts (RCIF, OERR, TMR, IOC-B) land here. |
| 0x0018 | `call 0x0190` + context save | **LATENT** — low-priority ISR. IPEN is cleared; this vector is never reached at runtime, but its bytes are populated. |

In addition, the V1.6b stock image contains what look like auxiliary
branch targets around 0x0040 / 0x0048 (`goto label_031 (0x0366)` /
`goto label_032 (0x03A6)`).  Their call source is not yet fully
identified (likely bootloader handoff or soft-reset entry).  V1.71
preserves these bytes exactly; they are described in A3c of the
IMPL spec.

V1.71 vector-block layout (byte-identical to stock, verified
against the `v16b.asm` byte stream 0x0000–0x004B):

```asm
    org 0x0000
reset_vector:                       ; 0x0000 — reset
    goto    bootloader_entry        ; 0x0000–0x0003 (2 words)
    dw      0xFFFF, 0xFFFF          ; 0x0004–0x0007 unused

isr_high_entry:                     ; 0x0008 — HIGH-PRIORITY ISR
    goto    isr_dispatch            ; 0x0008–0x000B  → isr_entry (0x03A6 in stock)
    ; 0x000C–0x0017: unreached stub.  Stock mirrors the
    ; first 6 instructions of app_init at 0x004C — byte-identical
    ; but never executed because the goto above already transferred.
    ; Preserve verbatim for byte-identity.
    movlw   0x80                    ; 0x000C
    movwf   common_ram_1, ACCESS    ; 0x000E
    movlw   0xFE                    ; 0x0010
    call    uart_init, 0            ; 0x0012–0x0015  (resolves to function_009 @ 0x0190)
    movlw   0x01                    ; 0x0016

isr_low_entry:                      ; 0x0018 — LOW-PRIORITY ISR (latent, IPEN=0)
    call    uart_init, 0            ; 0x0018–0x001B
    movlw   0x75                    ; 0x001C
    movwf   common_ram_13, ACCESS   ; 0x001E

isr_low_hang:                       ; 0x0020 — self-loop (unreached)
    bra     isr_low_hang            ; 0x0020
    ; 0x0022–0x003F: stock 0xFFFF fill (15 words)
    dw      0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF
    dw      0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF
    dw      0xFFFF, 0xFFFF, 0xFFFF, 0xFFFF
    dw      0xFFFF, 0xFFFF, 0xFFFF

aux_vector_031:                     ; 0x0040 — stock aux goto (purpose open; see IMPL A3c)
    goto    early_bootstrap_031     ; → 0x0366 (label_031; likely bootloader → cold-init handoff)
    dw      0xFFFF, 0xFFFF          ; 0x0044–0x0047 unused

aux_vector_032:                     ; 0x0048 — stock aux goto
    goto    isr_dispatch            ; → 0x03A6; mirror of the 0x0008 high-priority vector
    ; 0x004C: application code starts here — shifts freely in V1.71
```

The vector block (0x0000–0x004B) is pinned because every byte is
referenced by CPU hardware or the bootloader.  Everything after
0x004C shifts freely.

### Bootloader block

The stock bootloader occupies 0x7800–0x7FFF (2 KB).  V1.71 clones
it byte-for-byte via a `db` region guarded by `org 0x7800`.  The
bootloader is **not rewritten** by this spec — it remains a verbatim
copy of the V1.6b bootloader image.

---

## Feature Inventory

### From V1.61b: A/B Preset Switching

| Feature | Description |
|---------|-------------|
| Preset state flag | `control_flags.PRESET_BIT` (per Table below) mirrored into EEPROM 0x74 |
| Preset menu screen | New screen 0 inserted before Volume, shows "Preset A/B" and navigates with UP/DOWN |
| IR shortcuts | RC5 `0x38` → preset A, RC5 `0x39` → preset B |
| Version byte | EEPROM version tuple bumped (value TBD — see Acceptance Criteria 5) |
| Volume indicator | On the Volume screen, LCD column 15 shows `A` or `B` when connected |
| Full-sync burst | Preset change enqueues 3 retries of the preset-switch frame `[B0, 0x20, preset_byte]` sent to MAIN (route 0xB0 = broadcast, cmd 0x20 = `preset_select` per the protocol table in `v16b.asm`, data = `0x00` for A / `0x01` for B).  The V1.61b builder pins the exact bytes; final V1.71 emission must match that builder. |

### From V1.62b: Reconnect Robustness + OERR Recovery

| Feature | Where in V1.71 |
|---------|-----------------|
| UART OERR drain + parser reset | Inline at the head of `uart_rx_parser` body |
| TXIE guard | `uart_tx_enqueue` re-asserts `PIE1.TXIE` after every recovery path |
| Reconnect handshake state | Flag bits tracking `reconnect_pending`, `reconnect_primed`, `reconnect_wait_done` |
| Wake frame on reconnect exit | `reconnect_wait_body` calls `serial_send_wake_frame` before returning to the display loop — closes the V162B_RECONNECT_WAKE_BUG gap |
| Full-sync retry on missing echo | Full-sync entry retries the preset-switch frame (see the V1.61b row above) when the expected echo from MAIN is absent within a bounded window |

### From V1.63b: BF/08 DSP-Fault Parser + UI

| Feature | Where in V1.71 |
|---------|-----------------|
| BF/08 dispatch case | Inlined into `uart_rx_parser` third-byte state machine |
| Fault byte store | RAM address `bf08_fault_byte` (currently 0x0BC in V1.63b) |
| DSP fault sticky flag | `control_flags.DSP_FAULT_BIT` |
| LCD indicator | Volume screen shows `!` at column 15 when fault flag is set; preset indicator otherwise |
| Resync-on-clear | Fault flag 1→0 transition resets the full-sync counter (`sync_tick_hi/lo`) to force an immediate burst |

### From V1.64b: Explicit IR Standby/Wake Endpoints

| Feature | Where in V1.71 |
|---------|-----------------|
| RC5 `0x3A` → explicit standby | Handled in `ir_dispatch` before the POWER-toggle fall-through |
| RC5 `0x3B` → explicit wake | Handled in `ir_dispatch` before the POWER-toggle fall-through |
| POWER toggle preserved | RC5 `0x32` still toggles standby, matching stock behavior |

---

## Architecture

### Source file layout

```
dlcp_control_v171.asm
├── Header (LIST, #include p18f25k20.inc, #include dlcp_control_ram.inc)
├── Configuration bits (identical to stock V1.6b)
├── org 0x0000: Reset + ISR vectors (byte-identical to stock)
├── org 0x004C: Application code — functions in stock order,
│   enhanced in-place:
│   ├── app_init: stock init
│   ├── isr_dispatch: stock-exact ISR routing (bug-for-bug)
│   ├── isr_save_context: stock-exact context save
│   ├── lcd_command / lcd_write: unchanged
│   ├── eeprom_read_byte / eeprom_write_byte: unchanged
│   ├── ir_rc5_decode: unchanged (stock scan-code decode)
│   ├── ir_dispatch: extended for 0x38/0x39 preset shortcuts and
│   │   0x3A/0x3B standby/wake (V1.61b + V1.64b)
│   ├── uart_rx_parser: OERR drain + BF/08 dispatch case
│   │   (V1.62b + V1.63b)
│   ├── uart_tx_enqueue: TXIE re-enable guard (V1.62b)
│   ├── eeprom_settings_load: loads preset state from EEPROM 0x74
│   │   (V1.61b)
│   ├── serial_full_sync: preset-aware sync burst + retry (V1.61b)
│   ├── serial_send_frame: unchanged
│   ├── serial_send_wake_frame: standalone wake emitter (V1.62b)
│   ├── reconnect_wait_body: wake frame on exit (V1.62b)
│   ├── bf08_fault_handler: fault byte store + sticky flag (V1.63b)
│   ├── volume_display: column-15 indicator logic; preset letter
│   │   or `!` fault indicator (V1.61b + V1.63b)
│   ├── menu_dispatch: preset menu screen plugged into existing
│   │   menu navigation (V1.61b)
│   ├── menu_screen_preset: new Preset A/B screen (V1.61b)
│   ├── main_event_loop: hooks for preset indicator + fault
│   │   indicator refresh (V1.61b + V1.63b)
│   └── ... remaining stock functions ...
├── Data/string tables (each referenced via label arithmetic)
├── org 0x7800: Bootloader block (byte-identical clone of stock)
├── org 0xF00000: EEPROM data
│   ├── 0x60–0x70: stock display state
│   ├── 0x71–0x73: version tuple (value TBD)
│   ├── 0x74: preset state byte (default 0x00 = A)
│   ├── 0x75–0xFE: stock user settings
│   └── 0xFF: stock EEPROM checksum
└── END
```

### Memory map

PIC18F25K20 has **32 KB flash** (0x0000–0x7FFF) and 1,536 bytes of
accessible GPR.  Application region is 0x004C–0x77FF, with the
bootloader pinned at 0x7800–0x7FFF.

| Range | Content | Size |
|-------|---------|------|
| 0x0000 | Reset vector + ISR dispatch + aux vectors | 76 bytes |
| 0x004C | Application code (enhanced in-place) | ~27 KB in stock |
| ~end-of-code | Erased fill (`0xFFFF`) | variable |
| 0x7800 | Bootloader (byte-identical clone) | 2,048 bytes |

**Bootloader CANNOT move** — it occupies the top 2 KB of flash and
is the reset-vector target.  Any relocation requires understanding
(and probably rewriting) its USB/serial update protocol, which is
explicitly out of scope.

**Code space budget**: 0x004C to 0x77FF = ~30.6 KB.  Stock V1.6b
application code ends well below 0x7000 (the free zone that
V1.61b–V1.64b overlays exploit starts there).  V1.71 inline
enhancements add on the order of 1–1.5 KB.  Even with pessimistic
estimates the budget has ample headroom, but the exact pre- and
post-V1.71 code-end addresses MUST be measured from the gpasm
`.lst` before any release is produced (Acceptance Criterion 10).

### Runtime state (same bit semantics as V1.61b–V1.64b where
compatible)

A table of CONTROL flag bits (currently documented for V1.63b as a
single 8-bit register at address 0x01F, with partial reservations
in V1.62b init):

| Bit | Name | Source | Purpose |
|-----|------|--------|---------|
| 0 | `IR_ARMED` | stock | IR receive gate |
| 1 | `CONNECTED` | stock | display / MAIN connection state |
| 2 | `STANDBY_BUS` | stock | standby wire state |
| 3 | `RECONNECT_PENDING` | V1.62b | reconnect gate |
| 4 | `RECONNECT_PRIMED` | V1.62b | parser re-prime complete |
| 5 | `RECONNECT_WAIT_DONE` | V1.62b | wait completed, wake allowed |
| 6 | `PRESET_BIT` | V1.61b | 0 = A, 1 = B |
| 7 | `DSP_FAULT_BIT` | V1.63b | sticky DSP fault indicator |

This layout is inherited verbatim from the V1.64b binary overlay.
V1.71 preserves the encoding so downstream tools (EEPROM probes,
test fixtures) continue to interpret the byte correctly.  Any
deviation requires a migration note in `AGENTS.md`.

### EEPROM layout (delta from stock)

| Slot | Address | Size | Purpose |
|------|---------|------|---------|
| Display state | 0x60–0x70 | 17 bytes | Stock (volume, input, etc.) |
| Version tuple | 0x71–0x73 | 3 bytes | V1.71 identifier (exact values TBD) |
| Preset state | 0x74 | 1 byte | `0x00` = A, `0x01` = B (V1.61b) |
| User settings | 0x75–0xFE | 138 bytes | Stock |
| EEPROM checksum | 0xFF | 1 byte | Stock (0x02) |

The EEPROM region is byte-identical to stock V1.6b **except** the
version tuple at 0x71–0x73 and the preset byte at 0x74.  All other
bytes must match stock.

---

## gpsim Simulation Infrastructure Update

### What changes

The gpsim overlays in `src/dlcp_fw/sim/manifests.py` replace
blocking CONTROL functions with simulation stubs (LCD capture, IR
injection, UART loopback shim, EEPROM shadow).  These overlays use
hardcoded stock addresses that will differ in V1.71.

### Approach

Reuse the `parse_gpasm_symbols(lst_path)` helper and
`assemble_v30(...)` tooling already landed for V3.0 / V3.1 (see
`src/dlcp_fw/sim/v30_symbols.py`).  Rename/add a CONTROL-specific
variant such as `parse_v16b_symbols(lst_path)` and a
`control_overlays_dynamic(symbols)` manifest builder that templates
overlay ASM with the correct V1.71 addresses.

Or, more simply: after V1.71 assembles, extract the new addresses
of the overlay target functions from the listing and inject
V1.71-specific overlay entries keyed by semantic function name.

### Functions that need overlays (stock addresses TBD — audit
during Phase 1 of the IMPL spec)

| Function | Stock addr | V1.71 addr | Overlay purpose |
|----------|-----------|------------|-----------------|
| `lcd_command` | TBD | TBD | LCD command capture |
| `lcd_write_char` | TBD | TBD | LCD char capture |
| `ir_rc5_decode` | TBD | TBD | IR frame injection |
| `uart_rx_parser` | TBD | TBD | Parser stimulus + trap |
| `uart_tx_enqueue` | TBD | TBD | TX byte capture |
| `eeprom_read_byte` | TBD | TBD | EEPROM read shim |
| `eeprom_write_byte` | TBD | TBD | EEPROM write shim |
| `main_event_loop` | TBD | TBD | Boot-gate fast-forward |

All final addresses are determined post-assembly from the gpasm
listing file.

---

## MAIN firmware pairing

V1.71 CONTROL pairs with **V3.1+ MAIN**:

- V3.1 MAIN emits BF/08 fault frames (Fix E from V27_V163B_SPEC)
  → V1.71 CONTROL parses them into `bf08_fault_byte` and asserts
  `DSP_FAULT_BIT`.
- V3.1 MAIN accepts the preset-switch command `cmd=0x20` → V1.71
  CONTROL drives it from the preset menu and IR shortcuts.
- V3.2 MAIN (feature/v32-delayed-switch-integration) hardens the
  wire-chain delayed-switch path — V1.71 preserves the V1.62b
  reconnect wake behavior that cooperates with that path.

### Backward compatibility

V1.71 MUST still function against stock V2.3 MAIN in a degraded
mode (no presets, no fault UI):

- Preset commands sent to stock MAIN (`cmd=0x20`) are silently
  ignored — stock MAIN's dispatch has no 0x20 case.  CONTROL
  still updates its local state and EEPROM, and MAIN does not
  crash.
- BF/08 is never received from stock MAIN, so the fault UI never
  fires — Volume screen shows the preset letter or nothing.
- IR RC5 `0x3A`/`0x3B` dispatch to CONTROL's standby/wake
  serial-frame emitters (`[B0, 0x03, 0x00]` / `[B0, 0x03, 0x01]`).
  These frames are part of the stock protocol (CONTROL already
  emitted them via the IR POWER toggle path); stock V2.3 MAIN
  accepts them unchanged.  The V1.64b / V1.71 change is purely on
  the CONTROL side — which IR code maps to which already-stock
  command.

This back-compat is critical for recovery-image deployments that
flash CONTROL before MAIN.

---

## Test strategy

### Byte-identical equivalence gate (from IMPL spec)

Before feature testing, the V1.7 baseline (byte-identical to
stock V1.6b) must pass the equivalence tests described in
`docs/IMPL_V16B_SOURCE_REWRITE_SPEC.md`.  V1.71 edits build on
that proven baseline.

### New file: `tests/sim/test_v171_v31_robustness.py`

Replicates the 5 wire-chain robustness tests from
`tests/sim/test_v31_v163b_robustness.py` using V1.71 paired with
V3.1 MAIN.  All must PASS.

| Test | V1.71 + V3.1 expectation |
|------|--------------------------|
| bus_clear_recovers_after_mssp_stop_fault | PASS |
| dsp_ping_latches_fault_on_persistent_nack | PASS |
| wire_dsp_fault_reporting | PASS |
| wire_mssp_stop_cascade_full_recovery | PASS |
| pen_timeout_recovers | PASS |

### V1.71-only feature tests

| Test file | Focus |
|-----------|-------|
| `tests/sim/test_v171_preset_menu.py` | Preset screen navigation, LCD indicator, EEPROM 0x74 persistence |
| `tests/sim/test_v171_ir_endpoints.py` | RC5 0x32/0x38/0x39/0x3A/0x3B dispatch (V1.61b + V1.64b) |
| `tests/sim/test_v171_reconnect_wake.py` | Wake frame on reconnect exit (V162B_RECONNECT_WAKE_BUG regression guard) |
| `tests/sim/test_v171_fault_indicator.py` | LCD `!` indicator and resync-on-clear (V1.63b parity) |
| `tests/sim/test_v171_stock_backcompat.py` | V1.71 + stock V2.3 MAIN degraded mode |

### Semantic-guard regressions

Ensure that `tests/sim/test_verify_presets_ab_v16b_semantic_guards.py`
and its v162b/v163b/v164b siblings either:

- still pass against the V1.64b binary overlay (unchanged), **and**
- grow a parallel `test_v171_semantic_guards.py` that checks
  V1.71-specific invariants (preset bit, fault bit, wake-frame
  emission sites, IR dispatch cases).

---

## Acceptance criteria

1. `gpasm` assembles `dlcp_control_v171.asm` without errors.
2. All V1.71 robustness tests PASS (zero xfails) paired with
   V3.1 MAIN.
3. V1.71 vector block (0x0000–0x004B) is byte-identical to stock
   V1.6b.
4. Bootloader region (0x7800–0x7FFF) is byte-identical to stock
   V1.6b.
5. Config bits (`_CONFIG1H` … `_CONFIG7H` in MPASM terms) are
   byte-identical to stock V1.6b.
6. EEPROM region is byte-identical to stock V1.6b **except**
   version tuple (0x71–0x73) and preset byte (0x74).
7. Source is clean: semantic labels, symbolic SFRs (via
   `p18f25k20.inc`), no raw branch targets, no `goto *_patch`
   redirects, no `org` within the application code body (only
   0x0000 for vectors, 0x7800 for bootloader, 0xF00000 for EEPROM).
8. V1.64b-equivalent IR endpoints present (0x38/0x39/0x3A/0x3B).
9. V1.63b-equivalent BF/08 parser and fault UI present.
10. Post-assembly code-end address is measured and recorded in the
    release notes; gpsim manifests updated for V1.71 function
    addresses; no overlap with the bootloader at 0x7800.
11. Pairs with V3.1 MAIN for the full chain-level robustness gate
    and V3.2 MAIN for the delayed-switch wire tests without
    regressions.
12. Back-compat gate: V1.71 against stock V2.3 MAIN does not crash
    and degrades gracefully.
