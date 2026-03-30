# V3.1 MAIN Source Rewrite — Specification

Date: 2026-03-28
Status: implemented (V3.1 hex committed, 80-test gate passing)
Base: V3.0 MAIN source (stock V2.3 byte-identical)
Pair: V1.63b CONTROL firmware

## Purpose

V3.1 is the first **feature-bearing** source-level MAIN firmware build.
It starts from the V3.0 assembly source (`dlcp_main_v30.asm`, which is
byte-identical to stock V2.3) and adds ALL features from V2.4 through
V2.7 as direct source edits.

V3.1 = V3.0 + V2.4 (A/B presets) + V2.5 (MSSP robustness) + V2.6
(DSP robustness) + V2.7 (I2C recovery).  It is functionally what V2.7
was intended to be, with zero deferred features.

## Why V3.1 instead of fixing V2.7

V2.7 failed because of the binary patch composition approach:

1. **Space exhaustion**: Fixes D/E/F needed ~148 bytes but only ~122
   were available in dead-code zones.
2. **Composition bug**: The 4-step string-replacement dropped the V2.6
   volume wrapper, breaking the firmware.
3. **Forward reference errors**: gpasm cannot resolve `call` across
   `org` boundaries when labels appear after their references.

V3.1 eliminates ALL of these problems by design.

---

## Design Philosophy: Clean-Sheet, Not Patching

V3.1 is written as if we were the **original firmware engineer** adding
these features from the start.  There are:

- **No jump-out hooks** (`goto function_056_patch`).  Enhanced functions
  have their new logic **inline in their bodies**.
- **No patch regions** at fixed addresses.  New code flows naturally
  from the surrounding functions.
- **No dead-zone hunting**.  Space is unlimited because functions grow
  to the size they need and the assembler places everything.
- **No hardcoded addresses**.  All references use symbolic labels.
  Addresses shift freely as function bodies grow.

### What this means concretely

Instead of:
```asm
i2c_byte_tx:                        ; stock function_056
    goto    function_056_patch      ; ← jump out to patch region
```

V3.1 writes:
```asm
i2c_byte_tx:                        ; enhanced function_056
    movff   WREG, saved_w           ; save caller's byte
    movwf   SSPBUF, ACCESS          ; initiate I2C TX
    btfsc   SSPCON1, WCOL, ACCESS
    bra     .wcol_path
    call    wait_sspif_bounded      ; bounded wait (inline, not a redirect)
    bc      .timeout
    btfsc   SSPSTAT, BF, ACCESS
    movf    SSPBUF, W, ACCESS       ; drain BF
    call    wait_mssp_idle          ; bounded idle check
    bc      .timeout
    btfsc   SSPCON2, ACKSTAT, ACCESS ; Fix A: ACKSTAT check built-in
    bsf     dsp_fault_flags, 2, BANKED
    return
.timeout:
    call    recover_mssp
    ...
```

The function is **self-contained**.  No trampolines.  No remote stubs.

### Addresses WILL shift

Because function bodies grow (adding bounded waits, ACKSTAT checks,
retry logic), all addresses after the first modification shift.  This
is by design — V3.1 is a new firmware, not a stock-compatible overlay.

The gpsim simulation infrastructure (`manifests.py`) uses hardcoded
stock addresses for overlays.  **These must be updated for V3.1.**
The new addresses come from the gpasm symbol table (`.lst` / `.sym`).

### Hardware-pinned addresses (boot block constraints)

The boot block (ROM, cannot be modified) has three hardcoded `GOTO`
instructions into app space:

| Boot addr | Target | Status |
|-----------|--------|--------|
| 0x0008 | **0x1008** | **LIVE** — high-priority ISR entry. Must have ISR save+dispatch code. |
| 0x0018 | **0x1018** | **DEAD** — low-priority ISR. IPEN is cleared, never reached. Place `retfie 0` safety stub. |
| 0x03B8 | **0x1000** | **LIVE** — boot exit. Must be `org 0x1000` with `goto app_init`. |

V3.1 entry block layout:
```asm
    org 0x1000
app_entry:          ; 0x1000 — boot exit target
    goto app_init
    dw 0xFFFF, 0xFFFF
isr_high_entry:     ; 0x1008 — HIGH-PRIORITY ISR (all interrupts)
    movff FSR2L, isr_save_fsr2l
    movff FSR2H, isr_save_fsr2h
    call  main_isr_dispatch, 0x1
app_init:           ; 0x1014 — main init (label, shifts freely)
    goto main_flash_service
isr_low_stub:       ; 0x1018 — LOW-PRIORITY ISR (dead, safety stub)
    retfie 0
    ; Everything after 0x101A shifts freely
```

---

## Feature Inventory

### From V2.4: A/B Preset Switching

| Feature | Description |
|---------|-------------|
| Preset B table | Clone of preset A, at assembler-determined address |
| cmd=0x20 dispatch | New command case in the XOR dispatch chain |
| Flash bank remap | Preset-aware prologues in flash_write/erase/read |
| Filename per-preset | Boot loads correct EEPROM slot, persist writes correct slot |
| USB version literal | Reports "3.1" |

### From V2.5: MSSP/UART Robustness

| Feature | Where in V3.1 |
|---------|---------------|
| Bounded MSSP buffer wait | Inline in `i2c_byte_tx` body |
| Bounded I2C start/stop | Inline in `i2c_tas3108_reg1f_write` body |
| Bounded I2C transaction | Inline in `i2c_secondary_dev_write` body |
| Bounded UART TX wait | Inline in `uart_tx_byte_blocking` body |
| Bounded MSSP idle wait | Inline in `i2c_wait_bus_idle` body |
| Shared wait helpers | `wait_sspif_bounded`, `wait_trmt_bounded`, etc. |
| Two-strike recovery | First timeout → recover peripheral, second → hard reset |

### From V2.6: DSP Robustness

| Feature | Where in V3.1 |
|---------|---------------|
| Fix A: ACKSTAT latch | Built into `i2c_byte_tx` exit path |
| Fix B: Conditional dirty clear | `volume_dsp_write` wrapper replaces stock call |
| Fix B': Deferred volume commit | Stock premature MOVFF sequence NOPed out |

### From V2.7: I2C Recovery

| Feature | Where in V3.1 |
|---------|---------------|
| Fix C: I2C bus-clear | `i2c_bus_clear` function (near other I2C functions) |
| Fix D: DSP ping | `dsp_ping` function (after bus-clear) |
| Fix E: BF/08 fault status | `send_dsp_fault_status` function (near UART TX) |
| Fix F: PEN timeout | Bounded PEN wait inline in `i2c_tas3108_coeff_write` |

---

## Architecture

### Source file layout

```
dlcp_main_v31.asm
├── Header (LIST, #include, RAM include)
├── Configuration bits (identical to stock)
├── org 0x1000: App entry + ISR dispatch (unchanged)
├── USB descriptors (data, version updated to "3.1")
├── Application code — functions in stock order, enhanced in-place:
│   ├── ... (unchanged functions flow through naturally) ...
│   ├── volume_cmd_handler: calls volume_dsp_write (Fix B hook)
│   ├── ... deferred commit NOPed (Fix B') ...
│   ├── cmd_dispatch_xor_chain: includes cmd=0x20 case (V2.4)
│   ├── filename_load_active_slot: preset-aware boot load (V2.4)
│   ├── filename_persist_active_slot: preset-aware EEPROM write (V2.4)
│   ├── flash_write: preset bank remap in prologue (V2.4)
│   ├── flash_erase: preset bank remap in prologue (V2.4)
│   ├── i2c_byte_tx: bounded wait + ACKSTAT check (V2.5 + Fix A)
│   ├── flash_read: preset bank remap in prologue (V2.4)
│   ├── i2c_tas3108_reg1f_write: bounded I2C sequence (V2.5)
│   ├── i2c_bus_clear: 9 SCL clocks + manual STOP (Fix C)
│   ├── i2c_tas3108_coeff_write: bounded PEN wait (V2.5 + Fix F)
│   ├── i2c_secondary_dev_write: bounded I2C transaction (V2.5)
│   ├── uart_tx_byte_blocking: bounded TRMT wait (V2.5)
│   ├── i2c_wait_bus_idle: bounded idle check (V2.5)
│   ├── hard_reset: unchanged
│   ├── ... remaining small functions ...
│   │
│   ├── ; --- New functions (flow naturally after stock functions) ---
│   ├── volume_dsp_write: Fix B/B' wrapper + V2.7 retry/recovery
│   ├── dsp_ping: I2C address probe (Fix D)
│   ├── send_dsp_fault_status: BF/08 TX (Fix E)
│   ├── wait_sspif_bounded: shared bounded wait helper
│   ├── wait_trmt_bounded: shared bounded wait helper
│   ├── wait_mssp_idle_bounded: shared bounded wait helper
│   ├── wait_seed / wait_tick: timeout countdown helpers
│   ├── recover_mssp: MSSP hard reset wrapper
│   ├── recover_uart: UART reinit wrapper
│   │
├── Inline data table (0x47E6, unchanged)
├── ... remaining code ...
├── fill to preset_table_b
├── preset_table_b: Preset B DSP table (clone of A)
├── fill to preset_table_a
├── preset_table_a: Preset A DSP table (stock data)
├── org 0xF00000: EEPROM data
├── END
```

### Memory map

PIC18F2455 has **24KB flash** (0x0000–0x5FFF).  Boot block occupies
0x0000–0x0FFF.  App space is 0x1000–0x5FFF = 20KB.

| Range | Content | Size |
|-------|---------|------|
| 0x1000 | App entry + ISR dispatch | 24B |
| 0x1018 | USB descriptors | 148B |
| 0x10AC | Application code (enhanced in-place) | ~15.3KB |
| ~0x4C00 | Erased fill | ~variable |
| 0x4A00 | Preset B table (clone of A) | 2560B |
| 0x5400 | Free gap (overflow space) | 512B |
| 0x5600 | Preset A table (stock, pinned to flash ceiling) | 2560B |

**Preset A CANNOT move** — it occupies the last 2560 bytes of the
24KB flash.  There is zero space above 0x5FFF.

**Code space budget**: 0x1000 to 0x49FF = ~14.7KB for code.  Stock
uses ~14.4KB.  V3.1 enhancements add ~600B.  Fits with ~300B margin.

If code grows beyond 0x49FF, it can overflow into the 512B gap at
0x5400–0x55FF (between preset B and preset A).  This matches the
V2.5/V2.7 layout where patch stubs lived at 0x5400.

### Runtime state (same addresses as V2.4–V2.7)

| Address | Bit | Purpose |
|---------|-----|---------|
| 0x05E.2 | Preset select (0=A, 1=B) |
| 0x07E.0 | Filename flush flag |
| 0x07E.3 | Volume dirty bit (stock, clear path changed) |
| 0x07E.7 | Boot-complete gate (gates PEN timeout hook) |
| 0x07F.2 | ACKSTAT error latch (sticky per volume attempt) |
| 0x07F[5:3] | NACK retry counter (0–5, then give up) |
| 0x07F.6 | DSP ping fault latch |
| 0x0BD.5 | Filename dirty bit |

### EEPROM layout

| Slot | Address | Size |
|------|---------|------|
| Preset A filename | 0x60–0x7D | 30 bytes |
| Version tuple | 0x80–0x82 | 3 bytes (kept at 2.30) |
| Preset B filename | 0x83–0xA0 | 30 bytes |

---

## gpsim Simulation Infrastructure Update

### What changes

The gpsim overlays in `manifests.py` replace blocking functions with
simulation stubs (mailbox RX/TX, timer shims, etc.).  These overlays
use hardcoded stock addresses that will differ in V3.1.

### Approach

Add a **V3.1 manifest builder** that:
1. Reads the V3.1 symbol table (from gpasm `.lst` or a generated map)
2. Builds overlays at the correct V3.1 addresses
3. Uses the same simulation logic (mailbox, timer shims, etc.)

Or, more simply: after V3.1 assembles, extract the new addresses of
the overlay target functions from the listing, and add V3.1-specific
overlay entries to `manifests.py` keyed by function name.

### Functions that need overlays

| Function | Stock addr | V3.1 addr | Overlay purpose |
|----------|-----------|-----------|-----------------|
| `rx_ring_read` | 0x45FA | TBD | Mailbox RX stub |
| (function_109 check) | 0x4872 | TBD | RX-available check |
| `uart_tx_byte_blocking` | 0x4896 | TBD | Mailbox TX stub |
| `i2c_wait_bus_idle` | 0x48B6 | TBD | MSSP idle sim |
| `timer3_blocking_delay` | 0x447E | TBD | Timer3 shim |
| `adc_boot_gate` | 0x2D8C | TBD | ADC boot bypass |

These addresses are determined after assembly and extracted from the
gpasm listing file.

---

## CONTROL firmware

V3.1 MAIN pairs with **V1.63b CONTROL** (unchanged from V2.7 spec):
- Fix E': BF/08 parser (DSP fault handler)
- Fix E'': DSP fault UI indicator ("!" on LCD)
- Fix E''': Resync on fault clear

The V1.63b CONTROL hex is already built and committed.

---

## Test strategy

### New file: `tests/sim/test_v31_v163b_robustness.py`

Replicates all 5 tests from `test_v27_v163b_robustness.py` using
`V31_MAIN_HEX` instead of `PATCHED_MAIN_HEX_V27`.  All must PASS.

| Test | V3.1 expectation |
|------|-----------------|
| bus_clear_recovers_after_mssp_stop_fault | PASS |
| dsp_ping_latches_fault_on_persistent_nack | PASS |
| wire_dsp_fault_reporting (V3.1 + V1.63b) | PASS |
| wire_mssp_stop_cascade_full_recovery (V3.1 + V1.63b) | PASS |
| pen_timeout_recovers | PASS |

---

## Acceptance criteria

1. `gpasm` assembles `dlcp_main_v31.asm` without errors
2. All 5 V3.1 robustness tests PASS (zero xfails)
3. Data regions (config, EEPROM, preset A table) byte-identical to stock
4. USB version reports "3.1"
5. Source is clean: semantic labels, symbolic SFRs, no raw branch targets,
   no `goto *_patch` redirects, no `org` within the code body
6. Preset B table is a clone of preset A
7. gpsim manifests updated for V3.1 function addresses
